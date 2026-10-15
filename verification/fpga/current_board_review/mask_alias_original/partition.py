#!/usr/bin/env python3
"""Bounded original prefixes and exact printed tuples; host/Spike only."""
import argparse
import difflib
import json
from pathlib import Path
import re
import shutil
import subprocess

import port as full

HERE = full.HERE
PARENT = HERE / 'prepared01'


def partitions():
    for original, (sew, lmul, cap) in zip(full.NAMES, full.SHAPES):
        last = 97 if cap == 512 else 65
        for kind in ('prefix', 'tuple'):
            begin = 0 if kind == 'prefix' else last
            yield dict(id=original + '_' + kind, original=original, sew=sew,
                       lmul=lmul, cap=cap, kind=kind, first=begin, last=last,
                       configurations=last - begin + 1)


def partition_source(source, p):
    last_l = p['last'] // 16
    substitutions = {
        'seed<3': 'seed<1',
        'raw_op<OP_COUNT': 'raw_op<1',
        'for(unsigned l=0;l<7;++l)for(unsigned mode=0;mode<4;++mode)':
            (f'for(unsigned l={0 if p["kind"] == "prefix" else last_l};l<={last_l};++l)'
             f'for(unsigned mode=0;mode<(l=={last_l} ? 1U:4U);++mode)'),
        'for(unsigned trial=0;trial<(RESTART_MASKS ? 4U:1U);++trial)':
            (f'for(unsigned trial={0 if p["kind"] == "prefix" else 1};'
             f'trial<(l=={last_l} ? 2U:4U);++trial)'),
    }
    for old, new in substitutions.items():
        full.require(source.count(old) == 1, 'Unexpected original loop: ' + old)
        source = source.replace(old, new)
    return source


def host(prepared, out, parts):
    directory = out / 'host'
    directory.mkdir()
    results, negatives = [], []
    for p in parts:
        name, count = p['id'], p['configurations']
        case = prepared / name
        source = (case / 'case.c').read_text()
        csr = '__asm__ volatile("csrr %0,vlenb":"=r"(max_start));'
        full.require(source.count(csr) == 1, 'Host CSR stub mismatch')
        c = directory / (name + '.c')
        c.write_text(source.replace(csr, 'max_start=128; /* host only */'))
        mock = (HERE / 'host_mock.c').read_text()
        full.require(mock.count('calls!=5376') == 1, 'Host count check mismatch')
        m = directory / (name + '.mock.c')
        m.write_text(mock.replace('calls!=5376', f'calls!={count}'))
        exe = directory / name
        cmd = ['/usr/bin/cc', '-O2', '-Wall', '-Wextra', '-Werror',
               f'-DSEW={p["sew"]}', f'-DCAP={p["cap"]}', *DEFINES,
               '-I' + str(case / 'original'), c, m, '-o', exe]
        full.run(cmd, directory / (name + '.compile.log'))
        expected = full.host_expected(p['sew'], p['cap'])[p['first']:p['last'] + 1]
        full_log = PARENT / 'host' / (p['original'] + '.policy0.log')
        parent_rows = [s for s in full_log.read_text().splitlines() if s.startswith('CALL ')]
        full.require(expected == parent_rows[p['first']:p['last'] + 1], 'Original partition mismatch')
        expected = [re.sub(r'^CALL \d+ ', f'CALL {i} ', row) for i, row in enumerate(expected)]
        for policy in range(3):
            log = directory / (name + f'.policy{policy}.log')
            seconds = full.run([exe, str(policy)], log)
            text = log.read_text()
            full.require([s for s in text.splitlines() if s.startswith('CALL ')] == expected,
                         'Partition input/order differs: ' + name)
            full.require(f'RVV_MASK_PASS sew={p["sew"]} cases={count} errors=0' in text and
                         f'HOST_END calls={count} injected=0 result=0' in text, 'Host incomplete')
            results.append(dict(name=name, policy=policy, calls=count, elapsed_s=seconds, status='PASS'))
        mutations = (1, 2, 3, 4, 5, 6) if p['kind'] == 'prefix' else (1, 2, 5, 6)
        for mutation in mutations:
            log = directory / (name + f'.negative{mutation}.log')
            full.run([exe, '0', str(mutation)], log, expected=1)
            full.require('RVV_MASK_FAIL' in log.read_text() and
                         f'HOST_END calls={count} injected=1 result=1' in log.read_text(),
                         'Negative oracle did not reject mutation')
            negatives.append(dict(name=name, mutation=mutation, rejected=True))
    full.save(directory / 'status.json', dict(status='HOST_PASS_NOT_DUT', results=results, negatives=negatives))


DEFINES = ['-DRESTART_MASKS=1', '-DALIASES=1', '-DSCALAR_FORMS=0',
           '-DCARRY_FORMS=0', '-DCOMPARISON_ALIASES=0']


def build(prepared, out, parts):
    flags = ['-Os', '-march=rv64gcv', '-mabi=lp64d', '-mcmodel=medany',
             '-ffreestanding', '-fno-builtin', '-fno-stack-protector',
             '-fno-tree-vectorize', '-fno-tree-slp-vectorize', '-msmall-data-limit=0',
             '-ffunction-sections', '-fdata-sections', '-Wall', '-Wextra', '-Werror',
             '-nostdlib', '-static', '-Wl,--build-id=none', '-Wl,--gc-sections',
             '-T', prepared / 'replay.ld']
    for backend in ('soc', 'spike'):
        directory = out / backend
        directory.mkdir()
        entries = {}
        for p in parts:
            name = p['id']
            case = prepared / name
            elf = directory / (name + '.elf')
            cmd = [full.CC, *flags, f'-DSEW={p["sew"]}', *DEFINES,
                   '-I' + str(case / 'original')]
            if backend == 'spike':
                cmd.append('-DSPIKE_REFERENCE=1')
            cmd += [case / 'case.c', case / 'original/scenario.S', case / 'main.c',
                    prepared / 'startup.S', prepared / 'runtime.c', '-lgcc', '-o', elf]
            full.run(cmd, directory / (name + '.compile.log'))
            full.run([full.CC.with_name('riscv64-unknown-elf-objdump'), '-d', elf], directory / (name + '.dis'))
            nm = subprocess.check_output([str(full.CC.with_name('riscv64-unknown-elf-nm')),
                                          '-n', str(elf)], text=True, timeout=15)
            symbols = {m[3]: int(m[1], 16) for m in re.finditer(r'^([0-9a-f]+)\s+(\w)\s+(\S+)$', nm, re.M)}
            full.require(symbols['__bss_end'] < 0x800f0000, 'Memory boundary exceeded')
            full.save(directory / (name + '.symbols.json'), symbols)
            entries[name] = dict(path=str(elf), sha256=full.sha(elf), cases=[name],
                                 configurations=p['configurations'],
                                 pass_markers=[f'RVV_MASK_PASS sew={p["sew"]} cases={p["configurations"]} errors=0',
                                               f'BOARD_CASE_PASS {name}', 'BOARD_REPLAY_PASS'])
        full.save(directory / 'programs.json', dict(schema_version=1,
                  backend='vcs-soc' if backend == 'soc' else 'spike-htif',
                  programs=entries, prepared=str(prepared), provenance_sha256=full.sha(prepared / 'provenance.json'),
                  compiler=dict(path=str(full.CC), sha256=full.sha(full.CC)), vcs_started=False))


def reference(out, parts):
    directory = out / 'reference'
    directory.mkdir()
    results = []
    for p in parts:
        name = p['id']
        elf = out / 'spike' / (name + '.elf')
        symbols = json.loads((out / 'spike' / (name + '.symbols.json')).read_text())
        cmdfile = directory / (name + '.cmd')
        cmdfile.write_text(f'until pc 0 {symbols["replay_exit"]:x}\nreg 0 a0\nreg 0 minstret\nreg 0 mcycle\nstr {symbols["replay_log"]:x}\nrs\n')
        log = directory / (name + '.log')
        seconds = full.run([full.SPIKE, '-d', '--debug-cmd=' + str(cmdfile),
                            '--isa=' + full.ISA, '-m2', elf], log, timeout=120)
        text = log.read_text()
        values = re.findall(r'^0x([0-9a-f]{16})$', text, re.M)
        full.require(len(values) == 3 and int(values[0], 16) == 0, 'Completion counter/exit missing')
        for marker in (f'RVV_MASK_PASS sew={p["sew"]} cases={p["configurations"]} errors=0',
                       f'BOARD_CASE_PASS {name}', 'BOARD_REPLAY_PASS', 'RVV_MASK_TRIAL vl=512 vstart=256'):
            full.require(marker in text, 'Missing reference marker: ' + marker)
        full.require('BOARD_REPLAY_TRAP' not in text and 'RVV_MASK_FAIL' not in text, 'Reference failure')
        results.append(dict(name=name, configurations=p['configurations'], status='PASS',
                            instructions_to_replay_exit=int(values[1], 16), elapsed_s=seconds,
                            isa=full.ISA, elf_sha256=full.sha(elf), log_sha256=full.sha(log)))
    full.save(directory / 'status.json', dict(status='PARTITION_SPIKE_PASS_NOT_DUT', results=results))
    return results


def main(out):
    out = out.resolve()
    full.require(out.is_relative_to(HERE) and out != HERE and not out.exists(), 'Fresh owned output required')
    full.prepare.check(PARENT / 'prepared')
    evidence = json.loads((PARENT / 'original_provenance.json').read_text())
    for path, digest in evidence['files'].items():
        full.require(full.sha(Path(path)) == digest, 'Original input drift: ' + path)
    parts = list(partitions())
    pins = dict(evidence['files'])
    for path in [Path(__file__), PARENT / 'original_provenance.json', PARENT / 'status.json',
                 PARENT / 'reference/vstart_probe/status.json']:
        if path.exists():
            pins[str(path)] = full.sha(path)
    for p in parts:
        for path in (PARENT / 'host' / (p['original'] + '.policy0.log'),):
            pins[str(path)] = full.sha(path)
    out.mkdir()
    prepared = out / 'prepared'
    prepared.mkdir()
    for n in ('startup.S', 'runtime.c', 'replay.ld'):
        shutil.copyfile(PARENT / 'prepared' / n, prepared / n)
    for p in parts:
        case = prepared / p['id']
        source_case = PARENT / 'prepared' / p['original']
        shutil.copytree(source_case / 'original', case / 'original')
        old = (source_case / 'case.c').read_text()
        new = partition_source(old, p)
        (case / 'case.c').write_text(new)
        (case / 'partition.diff').write_text(''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                             fromfile='full_original_port/case.c', tofile='partition/case.c')))
        shutil.copyfile(source_case / 'adaptation.diff', case / 'runtime_adaptation.diff')
        (case / 'main.c').write_text((source_case / 'main.c').read_text().replace(p['original'], p['id']))
    full.save(out / 'partition_provenance.json', dict(schema_version=1, parts=parts, files=pins,
              tuple=dict(seed=0, raw_op=0, mode=0, vl=512, vstart=256, start_choice=1,
                         target='vmand.mm v8,v8,v16', opcode='66882457'),
              limitation='Original printed boundary, not proven last accepted internal instruction; tuple-only drops predecessor state',
              full_original_replay=False, original_linux_replay=False))
    full.save(prepared / 'provenance.json', dict(schema_version=1, cases=parts,
              partition_provenance_sha256=full.sha(out / 'partition_provenance.json'),
              files={str(p.relative_to(prepared)): full.sha(p) for p in prepared.rglob('*') if p.is_file()}))
    try:
        host(prepared, out, parts)
        build(prepared, out, parts)
        results = reference(out, parts)
        for path, digest in pins.items():
            full.require(full.sha(Path(path)) == digest, 'Input drift after validation: ' + path)
        full.prepare.check(prepared)
        status = dict(status='BOUNDED_PARTITIONS_READY_NOT_DUT', results=results,
                      soc_programs=str(out / 'soc/programs.json'), VCS_launched=False, RTL_modified=False)
        full.save(out / 'status.json', status)
        print(json.dumps(status, indent=2))
    except Exception as error:
        full.save(out / 'failure.json', dict(status='NOT_PASS', error=str(error)))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    main(parser.parse_args().out)
