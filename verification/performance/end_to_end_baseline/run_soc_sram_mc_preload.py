#!/usr/bin/env python3
"""One bounded component image, real ELF and explicit boundary-fixture preload runs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import struct
import subprocess
import sys

from audit import digest, require, verify_pins
from run_soc_sram_mc import extracted_slice
from sram_mc_preload import DEFAULT_BASE, DEFAULT_CAPACITY, Geometry, prepare

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RUNS = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
OUT = RUNS/'e2e_soc_sram_mc_preload_20261106_01'
PREVIOUS = RUNS/'e2e_soc_sram_mc_wide_20261106_01'
PREVIOUS_SHA = 'c8e3f1323e145aaf7e64cb31577d82cc6f83b35682bd52621191cc6fe1c9209f'
ELF_BUILD = RUNS/'e2e_wide_soc_memory_smoke_build_20261106_01'
ELF_RECEIPT_SHA = 'e7b8183b27ea68dd6adfd393ad5ac8972a67be1fdf5b67a2c9df11ba59f252ce'
ELF = ELF_BUILD/'wide_soc_memory_smoke.elf'
ELF_SHA = 'a63841ff39b370d06dbe039273ab4dd339fbd43c201ad6515416fa7f45bcd087'
MACRO = Path('/home/wangwy/ara/backend/library/mem/ts1n28hpcpsvtb8192x128m4swbaso_180a/VERILOG/ts1n28hpcpsvtb8192x128m4swbaso_180a_tt0p9v25c.v')
OBJCOPY = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-objcopy')
OWNED = tuple(HERE/name for name in ('sram_mc_preload.py', 'sram_mc_preload.svh', 'sram_mc_preload_tb.sv',
                                   'run_soc_sram_mc_preload.py', 'test_sram_mc_preload.py'))


def expected_case(width):
    g = Geometry(width)
    words = g.capacity//g.word_bytes
    return dict(width=width, banks=g.banks, columns=g.columns, words=words, reads=words+1,
                checked_bytes=g.capacity+g.word_bytes, holds=g.banks+1, boundaries=g.banks-1, resets=2)


def fields(line, tag):
    words = line.split()
    require(words and words[0] == tag, 'Wrong preload result tag')
    pairs = [word.split('=') for word in words[1:]]
    require(pairs and all(len(pair) == 2 and re.fullmatch('[a-z_]+', pair[0]) and pair[1].isdigit()
                          for pair in pairs), 'Malformed preload fields')
    require(len({key for key, value in pairs}) == len(pairs), 'Duplicate preload field')
    return {key: int(value) for key, value in pairs}


def check(text):
    require(not re.search(r'Fatal:|Error[-:]|Assertion[^\n]*failed|MC_\w*FAIL|UVM_(?:ERROR|FATAL)', text),
            'Simulator/assertion failure, regardless of process status')
    lines = text.replace('\r', '').splitlines()
    loads = [fields(line, 'MC_PRELOAD_LOADED') for line in lines if line.startswith('MC_PRELOAD_LOADED')]
    expected = [dict(width=w, bank=b, column=c, words=8192) for w in (128, 256)
                for b in range(Geometry(w).banks) for c in range(Geometry(w).columns)]
    key = lambda row: (row['width'], row['bank'], row['column'])
    require(sorted(loads, key=key) == expected, 'Missing/duplicate bank/column preload call')
    cases = [fields(line, 'MC_PRELOAD_CASE_PASS') for line in lines if line.startswith('MC_PRELOAD_CASE_PASS')]
    require(sorted(cases, key=lambda row: row['width']) == [expected_case(w) for w in (128, 256)],
            'Inexact full-capacity byte readback/reset/hold coverage')
    terminal = [fields(line, 'MC_PRELOAD_COMPONENT_PASS') for line in lines if line.startswith('MC_PRELOAD_COMPONENT_PASS')]
    require(terminal == [dict(cases=2)] and sum(line.startswith('MC_') for line in lines) == 19,
            'Missing/extra preload terminal or coverage record')
    return dict(cases=sorted(cases, key=lambda row: row['width']), macro_preload_calls=len(loads),
                checked_bytes=sum(row['checked_bytes'] for row in cases),
                oracle='Independent flat byte oracle; all 1 MiB read through actual source-block SRAM ports')


def boundary_fixture():
    """Known nonzero data spans every bank/column; last 64 bytes are BSS."""
    capacity = DEFAULT_CAPACITY
    # Include high address bits so bank/column swaps cannot alias a short-period pattern.
    payload = bytes((i*29+(i>>4)*17+(i>>13)*7+(i>>17)*53+0x5a) & 255 for i in range(capacity-64))
    raw = bytearray(4096)
    struct.pack_into('<16sHHIQQQIHHHHHH', raw, 0, b'\x7fELF\x02\x01\x01'+bytes(9),
                     2, 243, 1, DEFAULT_BASE, 64, 0, 0, 64, 56, 1, 0, 0, 0)
    struct.pack_into('<IIQQQQQQ', raw, 64, 1, 5, 4096, DEFAULT_BASE, DEFAULT_BASE,
                     len(payload), capacity, 4096)
    return bytes(raw)+payload, payload+bytes(64)


def run(output):
    output = output.absolute()
    require(output == output.resolve() and output.is_relative_to(RUNS), 'Fresh sole-verification output required')
    output.mkdir(parents=True, exist_ok=False)
    pins, commands = {}, []
    result = dict(state='SOC_SRAM_MC_PRELOAD_COMPONENT_FAIL', target_executed=False,
                  full_soc_accepted=False, performance_measured=False, timing_accepted=False,
                  default_loader_changed=False, actual_foundry_model_used=True)

    def pin(path, expected=None):
        path = Path(path).resolve(strict=True)
        actual = digest(path)
        require(expected is None or actual == expected, 'Accepted identity mismatch: '+str(path))
        require(str(path) not in pins or pins[str(path)] == actual, 'Input drift: '+str(path))
        pins[str(path)] = actual
        return actual

    def inventory(name):
        (output/name).write_text(json.dumps(pins, indent=2)+'\n')

    def command(argv, label, timeout):
        argv = list(map(str, argv)); pin(argv[0]); verify_pins(pins)
        record = dict(label=label, argv=argv, timeout_seconds=timeout); commands.append(record)
        result['active_command'] = label
        (output/'status.json').write_text(json.dumps(result, indent=2)+'\n')
        with (output/(label+'.log')).open('xb') as stream:
            child = subprocess.Popen(argv, cwd=output, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            try: code = child.wait(timeout=timeout)
            except BaseException:
                os.killpg(child.pid, signal.SIGKILL); child.wait(); raise
        record['returncode'] = code; verify_pins(pins)
        log = (output/(label+'.log')).read_text(errors='replace')
        require(code == 0 and not re.search(r'Error[-:]|Fatal:', log), label+' failed; preserve first attempt')
        return log

    try:
        pin(PREVIOUS/'result.json', PREVIOUS_SHA)
        previous = json.loads((PREVIOUS/'result.json').read_text())
        require(previous['state'] == 'SOC_SRAM_MC_EXTRACTED_COMPONENT_PASS' and previous['post_pins_match'],
                'Unaccepted source-block producer')
        pin(PREVIOUS/'source-pins.json', previous['source_pins_sha256'])
        for path, sha in json.loads((PREVIOUS/'source-pins.json').read_text()).items(): pin(path, sha)
        for path, sha in previous['artifacts'].items(): pin(path, sha)
        pin(ELF_BUILD/'result.json', ELF_RECEIPT_SHA)
        elf_receipt = json.loads((ELF_BUILD/'result.json').read_text())
        require(elf_receipt['state'] == 'WIDE_SOC_MEMORY_SMOKE_ELF_BUILT_NOT_EXECUTED' and
                elf_receipt['elf_sha256'] == ELF_SHA and elf_receipt['artifacts'][str(ELF)] == ELF_SHA,
                'Real ELF producer identity mismatch')
        pin(ELF_BUILD/'source-pins.json', elf_receipt['source_pins_sha256'])
        pin(ELF, ELF_SHA)
        snapshot = output/'source-snapshot'; snapshot.mkdir()
        sources = (*OWNED, HERE/'audit.py', HERE/'run_soc_sram_mc.py',
                   ROOT/'hardware/src/ara_soc.sv', ROOT/'hardware/deps/common_cells/include/common_cells/registers.svh', MACRO)
        for source in sources:
            pin(source); target = snapshot/source.name
            target.write_bytes(source.read_bytes()); pin(target, digest(source))
        wrapper, body, default = extracted_slice((snapshot/'ara_soc.sv').read_text())
        slice_file = snapshot/'ara_soc_sram_mc_slice.sv'; slice_file.write_text(wrapper); pin(slice_file)
        pin(sys.executable)
        command([sys.executable, '-B', snapshot/'test_sram_mc_preload.py'], 'host-tests', 60)
        real_oracle = output/'real-oracle.bin'
        command([OBJCOPY, '-O', 'binary', '--gap-fill', '0', '--pad-to', hex(DEFAULT_BASE+DEFAULT_CAPACITY),
                 ELF, real_oracle], 'real-elf-independent-objcopy', 30)
        require(real_oracle.stat().st_size == DEFAULT_CAPACITY, 'Independent real ELF oracle size')
        pin(real_oracle)
        fixture, expected = boundary_fixture()
        fixture_elf = output/'boundary-fixture.elf'; fixture_elf.write_bytes(fixture); pin(fixture_elf)
        fixture_oracle = output/'boundary-oracle.bin'; fixture_oracle.write_bytes(expected); pin(fixture_oracle)
        images = {}
        for name, elf, oracle in (('real', ELF, real_oracle), ('boundary', fixture_elf, fixture_oracle)):
            images[name] = []
            for width in (128, 256):
                directory = output/'images'/name/f'w{width}'
                manifest = prepare(elf, directory, width=width)
                require((directory/'image.bin').read_bytes() == oracle.read_bytes(), 'Independent oracle disagreement')
                for path, sha in manifest['artifacts'].items(): pin(path, sha)
                pin(directory/'manifest.json')
                images[name].append(dict(width=width, manifest=str(directory/'manifest.json'),
                                         manifest_sha256=digest(directory/'manifest.json')))
        vcs = shutil.which('vcs'); require(vcs is not None, 'Host VCS unavailable')
        pin(vcs)
        vcs1 = Path(vcs).resolve().parent.parent/'linux64/bin/vcs1'
        if vcs1.is_file(): pin(vcs1)
        build = output/'build'; build.mkdir(); image = build/'simv'
        inventory('source-pins-precompile.json')
        command([vcs, '-full64', '-sverilog', '-timescale=1ns/1ps', '-assert', 'svaext',
                 '+define+UNIT_DELAY+no_warning+SRAM_MC_PRELOAD_ENABLE', '+notimingcheck',
                 '+incdir+'+str(snapshot), snapshot/MACRO.name, slice_file, snapshot/'sram_mc_preload_tb.sv',
                 '-top', 'sram_mc_preload_tb', '-Mdir='+str(build/'csrc'), '-o', image], 'compile', 240)
        pin(image)
        for library in sorted(build.rglob('*.so')): pin(library)
        inventory('source-pins-presimulation.json')
        measured = {}
        for name, oracle in (('real', real_oracle), ('boundary', fixture_oracle)):
            measured[name] = check(command([image, '+SRAM_MC_PRELOAD_DIR='+str(output/'images'/name),
                                           '+MC_ORACLE='+str(oracle)], 'functional-'+name, 180))
        verify_pins(pins)
        result.update(state='SOC_SRAM_MC_PRELOAD_COMPONENT_PASS', post_pins_match=True, active_command=None,
                      images=images, measured=measured, real_elf_sha256=ELF_SHA, macro_sha256=digest(MACRO),
                      actual_source_sha256=digest(ROOT/'hardware/src/ara_soc.sv'),
                      extracted_block_sha256=hashlib.sha256(body.encode()).hexdigest(),
                      default_words_expression=default, checked_bytes=sum(r['checked_bytes'] for r in measured.values()),
                      limitations=['Opt-in adapter only; dirty ara_tb and default loader remain untouched',
                                   'Unmodified original macro preloadData and UNIT_DELAY functional model; timing checks disabled',
                                   'Real existing ELF plus explicitly synthetic all-bank/column boundary fixture; no CPU execution',
                                   'No full-SoC boot, gate-level hierarchy, FPGA, synthesis, MMU/PMP, timing or PPA acceptance'])
    except BaseException as exc:
        result.update(error=repr(exc), post_pins_match=False)
        raise
    finally:
        inventory('source-pins.json')
        (output/'commands.json').write_text(json.dumps(commands, indent=2)+'\n')
        result['source_pins_sha256'] = digest(output/'source-pins.json')
        result['artifacts'] = {str(path): digest(path) for path in sorted(output.rglob('*'))
            if path.is_file() and not path.is_relative_to(output/'build') and path.name not in ('status.json', 'result.json')}
        (output/'status.json').write_text(json.dumps(result, indent=2)+'\n')
        (output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({key:value for key,value in result.items() if key != 'artifacts'}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUT)
    run(parser.parse_args().output)
