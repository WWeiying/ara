#!/usr/bin/env python3
"""Run one pinned ELF on one full processor; check data and independent UVM."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import struct
import subprocess
import sys

from audit import digest, require, verify_pins
from prepare_wide_soc import ROOT, VERIFY, RUNS, HERE
import wide_soc_memory_smoke_test as memory

PLATFORM = re.compile(r'^WIDE_SOC_PLATFORM bits=(\d+) lanes=(\d+) vlen=(\d+) '
                      r'words=(\d+) bytes=(\d+) memory_width=(\d+)$', re.M)
ACTIVITY = re.compile(r'^WIDE_SOC_MEMORY bits=(\d+) reads=(\d+) writes=(\d+) '
                      r'upper_writes=(\d+) full_ar=(\d+) returns=(\d+) max_read_run=(\d+)$', re.M)


def elf_admission(data, bus_bytes):
    require(bus_bytes in (16, 32) and len(data) >= 64 and data[:6] == b'\x7fELF\x02\x01',
            'Little-endian ELF64 required')
    h = struct.unpack_from('<16sHHIQQQIHHHHHH', data)
    require(h[1:4] == (2, 243, 1) and h[4] == 0x80000000 and h[8] == 64 and h[9] == 56 and
            0 < h[10] <= 1024 and 64 <= h[5] <= len(data)-h[9]*h[10], 'ELF header/entry/table')
    loads = []
    for index in range(h[10]):
        kind, flags, offset, vaddr, paddr, filesz, memsz, align = struct.unpack_from(
            '<IIQQQQQQ', data, h[5] + index*h[9])
        if kind != 1 or not memsz: continue
        require(filesz <= memsz and offset <= len(data)-filesz and
                vaddr == paddr and 0x80000000 <= paddr < paddr+memsz <= 0x81000000,
                'Invalid/translated/out-of-RAM load segment')
        # Match exactly the supplied DPI loader: filesz==0 segments are skipped.
        if not filesz: continue
        require(paddr % bus_bytes == 0, 'DPI load segment is not bus-word aligned')
        end = ((paddr + memsz + bus_bytes - 1)//bus_bytes)*bus_bytes
        require(end <= 0x81000000, 'Rounded preload exceeds physical memory')
        loads.append(dict(address=paddr, file_bytes=filesz, memory_bytes=memsz,
                          rounded_end=end, flags=flags))
    require(loads and all(a['rounded_end'] <= b['address']
                         for a, b in zip(sorted(loads, key=lambda x:x['address']),
                                         sorted(loads, key=lambda x:x['address'])[1:])),
            'Overlapping rounded DPI preload ranges')
    return loads


def check_platform(text, width):
    require(not re.search(r'Fatal:|Error[-:]|Assertion[^\n]*failed|WIDE_SOC_\w*(?:FAIL|REQUIRES)', text),
            'Simulator/platform failure')
    require(not re.search(r'\[ARA_CONTRACT_TRACE\][^\n]*\bresp=1/1 fire=1\b[^\n]*\bexc=1\b|mcause_val', text),
            'Unexpected architectural exception in no-fault smoke')
    rows = [tuple(map(int, row)) for row in PLATFORM.findall(text)]
    require(rows == [(width, 4, 1024, 16777216//(width//8), 16777216, width)],
            'Actual memory, lane or vector geometry differs')
    activity = [tuple(map(int, row)) for row in ACTIVITY.findall(text)]
    require(len(activity) == 1, 'Missing/duplicate actual physical memory counters')
    bits, reads, writes, upper, full_ar, returns, run = activity[0]
    require(bits == width and reads > 0 and writes > 0 and upper > 0 and full_ar > 0 and
            0 <= reads-returns <= 1 and run >= 2, 'Physical memory service not exercised')
    return dict(width=bits, reads=reads, writes=writes, upper_writes=upper,
                full_ar=full_ar, returns=returns, max_consecutive_read_returns=run,
                scope='All SoC memory traffic, not QBS-specific or an ROI bandwidth measurement')


def check_program(text, kind):
    if kind == 'memory':
        # The program checker consumes UART markers only. The complete log is
        # independently checked by the platform guard and UVM, including its
        # mandatory zero-error summary (not an error message in the UART).
        uart = '\n'.join(line for line in text.replace('\r', '').splitlines()
                         if line.startswith('WIDE_SOC_MEMORY_SMOKE_')) + '\n'
        result = memory.check_log(uart)
        require(result['vlenb'] == 128, 'Unexpected architectural VLEN')
        return result
    require(kind == 'handoff', 'Unsupported program kind')
    lines = text.replace('\r', '').splitlines()
    require(lines.count('QBS/AKV handoff smoke: PASS traps=0') == 1 and
            not re.search(r'QBS/AKV handoff smoke: (?:SKIP|FAIL)|mismatch|unexpected trap', text, re.I),
            'Handoff result/trap/feature mismatch')
    return dict(handoff_pass=True, architectural_traps=0)


def run(args):
    out = args.output.absolute()
    require(out == out.resolve() and out.is_relative_to(RUNS), 'Fresh sole-verification run required')
    require(1 <= args.timeout <= 10800, 'Bounded VCS run required')
    out.mkdir(parents=True, exist_ok=False)
    work = out / 'work'; work.mkdir()
    pins, commands = {}, []
    result = dict(state='PREPARING', child_pid=None, kind=args.kind, performance_measured=False,
                  real_pmp_accepted=False, linux_accepted=False, synthesis_run=False)

    def pin(path, expected=None):
        path = Path(path).resolve(strict=True)
        sha = digest(path)
        require(expected is None or sha == expected, 'Input identity differs: ' + str(path))
        require(str(path) not in pins or pins[str(path)] == sha, 'Input pin conflict')
        pins[str(path)] = sha

    def save():
        (out / 'status.json').write_text(json.dumps(result, indent=2) + '\n')

    def command(argv, label, timeout):
        argv = list(map(str, argv)); pin(argv[0]); verify_pins(pins)
        commands.append(dict(argv=argv, label=label, timeout_seconds=timeout))
        result['state'] = label.upper()
        env = os.environ.copy()
        env.update(PATH='/usr/bin:/bin', PYTHONPATH=str(VERIFY / 'verification'),
                   PYTHONDONTWRITEBYTECODE='1', LC_ALL='C', READELF='/usr/bin/readelf')
        with (work / (label + '.console.log')).open('xb') as stream:
            child = subprocess.Popen(argv, cwd=work, env=env, stdout=stream,
                                     stderr=subprocess.STDOUT, start_new_session=True)
            result['child_pid'] = child.pid; save()
            try:
                code = child.wait(timeout=timeout)
            except BaseException:
                os.killpg(child.pid, signal.SIGKILL); child.wait(); raise
        result['child_pid'] = None
        commands[-1]['returncode'] = code
        require(code == 0, label + ' failed')
        verify_pins(pins)

    try:
        for path in (Path(__file__), HERE / 'test_wide_soc_smoke.py', HERE / 'audit.py',
                     HERE / 'wide_soc_memory_smoke_test.py', HERE / 'prepare_wide_soc.py'):
            pin(path)
        for name, expected in ((args.soc / 'result.json', args.soc_sha),
                               (args.program / 'result.json', args.program_sha)):
            pin(name, expected)
        soc = json.loads((args.soc / 'result.json').read_text())
        require(soc['state'] == 'PHYSICAL_WIDE_SOC_BUILT_NOT_EXECUTED' and soc['post_pins_match'] and
                soc['width'] in (128, 256), 'Unaccepted full processor image')
        program = json.loads((args.program / 'result.json').read_text())
        require(program['post_pins_match'] and program['state'] in
                ('WIDE_SOC_MEMORY_SMOKE_ELF_BUILT_NOT_EXECUTED',
                 'WIDE_SOC_HANDOFF_SMOKE_ELF_BUILT_NOT_EXECUTED'), 'Program not independently built')
        require((args.kind == 'memory') == (program['state'] == 'WIDE_SOC_MEMORY_SMOKE_ELF_BUILT_NOT_EXECUTED'),
                'Wrong ELF kind')
        for root, report in ((args.soc, soc), (args.program, program)):
            pin(root / 'source-pins.json', report['source_pins_sha256'])
            for file, sha in json.loads((root / 'source-pins.json').read_text()).items(): pin(file, sha)
            for file, sha in report['artifacts'].items(): pin(file, sha)
        for file, sha in soc['image_pins'].items(): pin(file, sha)
        simv, elf = Path(soc['simv']), Path(program['elf'])
        pin(elf, program['elf_sha256'])
        loads = elf_admission(elf.read_bytes(), soc['width']//8)
        for path in (VERIFY / 'verification/ara_verify').glob('*.py'): pin(path)
        pin(sys.executable)
        emit = lambda p, v: p.write_text(json.dumps(v, indent=2) + '\n')
        emit(out / 'source-pins.json', pins)
        result.update(simv=str(simv), elf=str(elf), elf_sha256=program['elf_sha256'],
                      width=soc['width'], preload_segments=loads)
        command([simv, '-no_save', '-l', work / 'run.vcs.log', '+PRELOAD=' + str(elf),
                 '+TESTCASE=physical_wide_' + args.kind, '+NO_FSDB', '+NO_INSTR_TRACE', '+QBS_PERF',
                 '+VECTOR_TRACE=' + str(work / 'vector_trace.csv'),
                 '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000'], 'simulation', args.timeout)
        text = (work / 'run.vcs.log').read_text()
        platform, functional = check_platform(text, soc['width']), check_program(text, args.kind)
        command([sys.executable, '-B', '-m', 'ara_verify.uvm_dut', '--require-events', '--require-backend',
                 '--require-axi', '--require-axi-write', '--vector-trace', work / 'vector_trace.csv',
                 '--log', work / 'run.vcs.log', '--simv', simv, '--elf', elf,
                 '--output', work / 'uvm_result.json'], 'protocol', 600)
        protocol = json.loads((work / 'uvm_result.json').read_text())
        require(protocol['status'] == 'PASS' and protocol['log_sha256'] == digest(work / 'run.vcs.log') and
                protocol['vector_trace_sha256'] == digest(work / 'vector_trace.csv') and
                protocol['elf_sha256'] == program['elf_sha256'] and
                protocol['sim_image_sha256'] == soc['image_pins'], 'Independent protocol evidence')
        verify_pins(pins)
        result.update(state='PHYSICAL_WIDE_SOC_SMOKE_PASS', measured=functional, platform=platform,
                      independent_protocol_checked=True, post_pins_match=True,
                      source_pins_sha256=digest(out / 'source-pins.json'),
                      limitations=['Same ELF on real full-processor generic-memory image; not model timing',
                                   'Flat physical-RAM checks, not real MMU/PMP or Linux wide-path acceptance'])
    except BaseException as exc:
        result.update(state='FAIL', error=repr(exc)); raise
    finally:
        save()
        (out / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
        result['artifacts'] = {str(p): digest(p) for p in [*(work.glob('*.log')),
            work / 'vector_trace.csv', work / 'uvm_result.json', out / 'source-pins.json',
            out / 'commands.json'] if p.is_file()}
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--soc', type=Path, required=True); parser.add_argument('--soc-sha', required=True)
    parser.add_argument('--program', type=Path, required=True); parser.add_argument('--program-sha', required=True)
    parser.add_argument('--kind', choices=('memory', 'handoff'), required=True)
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--timeout', type=int, default=7200)
    args = parser.parse_args()
    def stop(sig, frame): raise InterruptedError('Signal ' + str(sig))
    for sig in (signal.SIGINT, signal.SIGTERM): signal.signal(sig, stop)
    run(args)
