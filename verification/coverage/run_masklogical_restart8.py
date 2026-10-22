"""Independent eight-operation acceptance; no dependency on the fixed 23-case suite."""
import argparse
import csv
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from run_masklogical_same_source_repair_v2 import bind_build, original

ROOT = original.ROOT
sys.path.insert(0, str(ROOT / 'verification/tests'))
import build_masklogical_restart8 as reference

PRE = ROOT / 'verification/out/masklogical-restart8-preflight-20261008-01'
ELF_SHA = '4693fb8d1fb19d65200eb47e9bcf933040be23f8cec09d850d5098a8bdd8b403'
TIMEOUT = 900


def audit(out):
    require = original.require
    for name in ('console.log', 'run.vcs.log'):
        text = (out / name).read_text()
        require(not original.check_contract_log(out / name), 'Contract failure: ' + name)
        require('FAILED:' not in text and '$finish called from file' in text and
                'V C S   S i m u l a t i o n   R e p o r t' in text,
                'Abnormal simulator termination: ' + name)
        contracts = [original.parse_contract_summary(line) for line in text.splitlines()
                     if line.startswith('[ARA_CONTRACT]')]
        require(len(contracts) == 1 and contracts[0]['exceptions'] == 0,
                'Missing contract summary or unexpected exception: ' + name)
        require(text.splitlines().count(reference.PASS_LINE) == 1,
                'Missing exact 8337-check self-test: ' + name)
    readback = reference.audit_native_readback(out)
    sites = reference.elf_sites(out / 'input.elf')
    wanted = [(s['pc'], s['word']) for s in sites]
    elf = reference.ELFFile(BytesIO((out / 'input.elf').read_bytes()))
    eoc = elf.get_section_by_name('.symtab').get_symbol_by_name('_eoc')[0]['st_value']
    starts, retired, tail = [], [], []
    count = exits = 0
    with (out / 'commit_trace.csv').open(newline='') as stream:
        for row in csv.DictReader(stream):
            word, pc = int(row['insn'], 16), int(row['pc'], 16)
            logical = word & 127 == 0x57 and (word >> 12) & 7 == 2 and word >> 26 in reference.FUNCTS
            if row['event'] == 'arch_start' and logical:
                # ara_commit_monitor emits a zero PC placeholder here. The
                # architecture sequence binds VRF activity; only retire has PC.
                starts.append((int(row['order']), word))
            if row['event'] != 'retire':
                continue
            require(int(row['order']) == count and row['trap'] == '0', 'Retirement gap or trap')
            count += 1
            if logical:
                retired.append((pc, word))
            if pc == eoc or tail:
                tail.append(pc)
            if int(row['mem_wmask'], 16) and int(row['mem_addr'], 16) == 0xd0000000:
                require(pc == eoc + 8 and int(row['mem_wmask'], 16) == 255 and
                        int(row['mem_wdata'], 16) == 0, 'Wrong native MMIO exit')
                exits += 1
    require([word for _, word in starts] == [s['word'] for s in sites] and retired == wanted,
            'Expected exactly eight ordered mask-logical starts and retirements')
    require(len({seq for seq, _ in starts}) == 8, 'Duplicate architecture identity')
    require(exits == 1 and len(tail) >= 3 and
            all(pc == eoc + 4 * (i % 4) for i, pc in enumerate(tail)), 'Invalid MMIO terminal loop')
    lanes, vlen, activities = original._parse_vector_trace(out / 'vector_trace.csv')
    require((lanes, vlen) == (4, 1024), 'Wrong vector geometry')
    target_sequences = {seq for seq, _ in starts}
    logical_sequences = {seq for seq, a in activities.items()
                         if a.instruction & 127 == 0x57 and (a.instruction >> 12) & 7 == 2
                         and a.instruction >> 26 in reference.FUNCTS}
    require(logical_sequences == target_sequences, 'Unmapped/extra mask-logical activity')
    for op, ((seq, word), site) in enumerate(zip(starts, sites)):
        a = activities[seq]
        require(a.instruction == word and a.allocations == a.completions == 1 and a.use_vd and
                a.vd == site['vd'] and a.vl == 1024 and a.vstart == 256,
                f'Allocation/completion/shape mismatch: op={op}')
        values = original._architectural_bytes(a.writes, lanes, vlen)
        require(set(values) == {(site['vd'], byte) for byte in range(128)},
                f'Missing full destination or unexpected register write: op={op}')
        want = reference.expected(op)[8:136]
        for (reg, byte), (value, _) in values.items():
            require(value == want[byte], f'VRF prefix/result mismatch: op={op} v{reg} byte={byte}')
    return dict(status='PASS', cases=8, checks=8337, independent_readback=readback,
                architecture_starts=8, allocations=8, completions=8, vrf_bytes=1024,
                prefix_bits=2048, active_bits=6144, tail_bits=0, guard_bytes=128,
                retired_instructions=count, mmio_exit_stores=exits, coverage_admitted=False)


def execute(build, out):
    original.require(not out.exists(), 'Fresh output directory required')
    out.mkdir(parents=True)
    started = time.monotonic()
    state = dict(status='PREPARING', cases=8, coverage_admitted=False)
    original.save(out / 'status.json', state)
    try:
        image, pins = bind_build(build)
        pre = json.loads((PRE / 'manifest.json').read_text())
        original.require(pre['status'] == 'SPIKE_PREFLIGHT_PASS' and pre['native_sha256'] == ELF_SHA,
                         'Wrong frozen eight-case preflight')
        for key in ('source_pins', 'tool_pins', 'binary_pins'):
            for path, digest in pre[key].items():
                original.require(path not in pins or pins[path] == digest, 'Conflicting pin: ' + path)
                pins[path] = digest
        paths = [Path(__file__), PRE / 'manifest.json']
        paths += [Path(m.__file__) for m in list(sys.modules.values())
                  if getattr(m, '__file__', None) and
                  str(Path(m.__file__).resolve()).startswith(str(ROOT / 'verification')) and
                  Path(m.__file__).is_file()]
        for path in paths:
            digest = original.digest(path)
            original.require(str(path) not in pins or pins[str(path)] == digest, 'Helper drift: ' + str(path))
            pins[str(path)] = digest
        original.check_pins(pins)
        original.require(original.digest(PRE / 'input.elf') == ELF_SHA, 'Frozen ELF changed')
        shutil.copyfile(PRE / 'input.elf', out / 'input.elf')
        pins[str(out / 'input.elf')] = ELF_SHA
        original.save(out / 'source-pins.json', pins)
        command = [str(image), '-l', 'run.vcs.log', '+NO_FSDB', '+ntb_random_seed=1',
                   '+PRELOAD=' + str(out / 'input.elf'), '+TESTCASE=masklogical_restart8',
                   '+COMMIT_TRACE=' + str(out / 'commit_trace.csv'),
                   '+VECTOR_TRACE=' + str(out / 'vector_trace.csv'),
                   '-cm', 'line+cond+fsm+tgl+branch', '-cm_dir', str(out / 'code.vdb'),
                   '-cm_name', 'masklogical_restart8']
        original.save(out / 'command.json', dict(command=command, cwd=str(out), build=str(build),
                                                timeout_s=TIMEOUT, cases=8, checks=8337))
        original.check_pins(pins)
        original.save(out / 'status.json', dict(state, status='RUNNING'))
        with (out / 'console.log').open('x') as log:
            with subprocess.Popen(command, cwd=out, stdout=log, stderr=subprocess.STDOUT,
                                  start_new_session=True) as proc:
                original.save(out / 'started.json', dict(pid=proc.pid, image=str(image), epoch=time.time(),
                    image_sha256=original.digest(image), elf_sha256=ELF_SHA))
                exit_status = 'EXITED'
                try:
                    proc.wait(timeout=TIMEOUT)
                except BaseException as error:
                    exit_status = 'TIMEOUT' if isinstance(error, subprocess.TimeoutExpired) else 'INTERRUPTED'
                    if proc.poll() is None:
                        try:
                            os.killpg(proc.pid, signal.SIGTERM)
                        except ProcessLookupError:
                            pass
                        try:
                            proc.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            os.killpg(proc.pid, signal.SIGKILL)
                            proc.wait()
                    raise
                finally:
                    original.save(out / 'simulation-status.json', dict(status=exit_status,
                        pid=proc.pid, returncode=proc.returncode, elapsed_s=time.monotonic()-started))
                original.require(proc.returncode == 0, f'Simulator exited {proc.returncode}')
        original.check_pins(pins)
        state = audit(out)
        original.check_pins(pins)
        original.save(out / 'audit.json', state)
    except (Exception, KeyboardInterrupt) as error:
        state = dict(status='TIMEOUT' if isinstance(error, subprocess.TimeoutExpired) else 'FAIL',
                     reason=f'{type(error).__name__}: {error}', coverage_admitted=False)
    state['elapsed_s'] = time.monotonic() - started
    original.save(out / 'status.json', state)
    return 0 if state['status'] == 'PASS' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(execute(args.build.resolve(), args.output.resolve()))
