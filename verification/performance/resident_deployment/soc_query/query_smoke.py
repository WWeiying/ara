#!/usr/bin/env python3
"""One seven-query native smoke after the one-shot SoC builder exits; no polling."""
import argparse
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import select
import shlex
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent/'ara_dsa_signoff_integration/verification/out'
DISCOVERY = OUT/'resident_deployment_discovery_20261112_020612'
DISCOVERY_SHA = '70146a39a651bb8fa7b6eaea5a3afda8fc8365f4339ab46f657b3159a2c33cbf'
COMMON = OUT/'stage2_qwen3_attn_m4_build_20261109_04/inputs/sdk/apps/common'
PROTOCOL = OUT/'stage3_attention_sdk_vcs_20261110_01'
GNU = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin')
EXPECTED = [0x000F010808400101, 0x6B1A5B, 0x000001FF06084002, 0x1803E5B,
            0x0000040000040301, 0, 0]
PATTERN = (r'^RESIDENT_QUERY info0=([0-9a-f]{16}) info1=([0-9a-f]{16}) '
           r'info2=([0-9a-f]{16}) info3=([0-9a-f]{16}) info4=([0-9a-f]{16}) '
           r'status=0 valid=1 pv=1 qk=1 lanes=4 vlen=1024 errors=0$')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, data):
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True)+'\n')


def verify(pins):
    for path, digest in pins.items():
        require(sha(path) == digest, 'Identity drift: '+str(path))


def builder(directory):
    sys.path.insert(0, str(directory/'inputs'))
    spec = importlib.util.spec_from_file_location('resident_query_builder', directory/'inputs/soc_build.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def wait_builder(owner):
    try:
        fd = os.pidfd_open(owner['main_pid'])
    except ProcessLookupError:
        return
    try:
        try:
            group = Path('/proc', str(owner['main_pid']), 'cgroup').read_text()
            require('/'+owner['unit'] in group, 'Builder PID incarnation changed')
        except FileNotFoundError:
            require(select.select([fd], [], [], 0)[0], 'Builder disappeared without exit')
        require(select.select([fd], [], [], 7800)[0], 'Builder did not exit before deadline')
    finally:
        os.close(fd)


def check_native(text, rows):
    matches = re.findall(PATTERN, text, re.M)
    require(len(matches) == 1 and [int(v, 16) for v in matches[0]] == EXPECTED[:5],
            'Missing/duplicate/incorrect native query+SDK result')
    require(text.count('Core Test *** SUCCESS ***') == 1 and
            not re.search(r'(?im)^\s*(?:Error-|Error:|Fatal:|Fatal-|UVM_ERROR\s+@|UVM_FATAL\s+@)', text),
            'Core or simulator failure')
    actual = []
    for row in rows:
        require(row['trap'] == '0', 'Unexpected scalar trap')
        instruction = int(row['insn'], 16)
        if instruction & 0x707F == 0x405B:
            require(instruction >> 20 == 0 and row['event'] == 'retire', 'Malformed AKVINFO retirement')
            actual.append(int(row['rd_wdata'], 16))
    require(actual == EXPECTED, 'RVFI must retire exactly seven native AKVINFO results')
    return dict(state='PASS', retired_queries=7, words=[f'{v:016x}' for v in actual],
                sdk_resident_valid=1, sdk_resident_pv=1, sdk_resident_qk=1,
                full_model_executed=False, resident_arithmetic_executed=False,
                platform_authority_granted=False, legacy_words_unchanged=True)


def prepare(out, image):
    require(out.parent == OUT and out.name.startswith('enablement_soc_resident_deployment_query_') and
            not out.exists(), 'Fresh unique signoff query output required')
    require(image.parent == OUT and image.name.startswith('enablement_soc_resident_deployment_'),
            'Wrong successor image output')
    s = builder(image)
    plan, imagepins = s.preflight(image)
    require(plan['configuration']['resident_capability'] == EXPECTED[4], 'Old zero capability image')
    out.mkdir(); inputs = out/'inputs'; inputs.mkdir()
    pins = dict(imagepins)

    def copy(source, destination, expected):
        require(sha(source) == expected, 'Unpinned query compiler input: '+str(source))
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        pins[str(source)] = pins[str(destination)] = expected

    for name in ('query_smoke.py', 'query.c', 'query_test.py'):
        copy(HERE/name, inputs/name, sha(HERE/name))
    require(sha(DISCOVERY/'source-pins.json') == DISCOVERY_SHA, 'Discovery review drift')
    sdkpins = read(DISCOVERY/'source-pins.json')
    sdkroot = DISCOVERY/'inputs/software/akv'
    for path in sdkroot.rglob('*'):
        if path.is_file():
            copy(path, inputs/'sdk'/path.relative_to(sdkroot), sdkpins[str(path)])
    commonpins = read(OUT/'stage2_qwen3_attn_m4_build_20261109_04/source-pins.json')
    for path in COMMON.rglob('*'):
        if path.is_file():
            copy(path, inputs/'common'/path.relative_to(COMMON), commonpins[str(path)])
    protocolpins = read(PROTOCOL/'source-pins.json')
    require(read(PROTOCOL/'result.json')['state'] == 'PASS', 'Protocol helper not accepted')
    for path in (PROTOCOL/'inputs/verification/ara_verify').rglob('*.py'):
        copy(path, inputs/'verification/ara_verify'/path.relative_to(PROTOCOL/'inputs/verification/ara_verify'),
             protocolpins[str(path)])
    link = (inputs/'common/arch.link.ld').read_text()
    require(link.count('LENGTH = 0x00100000') == 1, 'Common linker geometry drift')
    (inputs/'link.ld').write_text(link.replace('ALIGNMENT', '16').replace('LENGTH = 0x00100000', 'LENGTH = 0x01000000'))
    pins[str(inputs/'link.ld')] = sha(inputs/'link.ld')
    owner = read(image/'owner.json')
    require(owner['owner_pid'] == owner['main_pid'] and owner['unit'] == s.unit(image), 'Wrong builder owner')
    new = dict(image=str(image), builder_owner=owner, environment=plan['environment'],
               python=plan['python'], automatic_retry=False, smoke_seconds=300)
    save(out/'plan.json', new)
    pins[str(out/'plan.json')] = sha(out/'plan.json')
    pins[str(image/'source-pins.json')] = sha(image/'source-pins.json')
    pins[str(image/'owner.json')] = sha(image/'owner.json')
    pins[str(DISCOVERY/'source-pins.json')] = DISCOVERY_SHA
    for name in ('riscv64-unknown-elf-gcc', 'riscv64-unknown-elf-objdump'):
        path = (GNU/name).resolve(); pins[str(path)] = sha(path)
    for name in ('libm.a', 'libc.a', 'libgcc.a', 'libnosys.a'):
        path = Path(subprocess.check_output([str(GNU/'riscv64-unknown-elf-gcc'),
                    '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-print-file-name='+name],
                    text=True).strip()).resolve(strict=True)
        pins[str(path)] = sha(path)
    verify(pins); save(out/'source-pins.json', pins)
    review = sha(out/'source-pins.json')
    command = ['/usr/bin/systemd-run', '--user', '--unit=resident-query-'+out.name+'.service',
        '--property=Type=exec', '--property=KillMode=control-group', '--property=RuntimeMaxSec=8400',
        '--property=MemoryMax=8G', '--property=CPUQuota=100%',
        '--property=StandardOutput=append:'+str(out/'service.stdout.log'),
        '--property=StandardError=append:'+str(out/'service.stderr.log'),
        plan['python'], '-B', '-u', str(inputs/'query_smoke.py'), 'execute', '--output', str(out),
        '--review-sha256', review]
    save(out/'launch.json', command)
    print(json.dumps(dict(output=str(out), review_sha256=review, command=command)), flush=True)
    subprocess.run(command, check=True)


def execute(out, review):
    require(Path(__file__).resolve() == out/'inputs/query_smoke.py' and sha(out/'source-pins.json') == review,
            'Frozen reviewed query worker required')
    plan, pins = read(out/'plan.json'), read(out/'source-pins.json')
    s = builder(Path(plan['image'])); b = s.tools(); base, _ = b.helpers(Path(plan['image'])/'inputs')
    owner = b.owner('resident-query-'+out.name+'.service')
    require(not (out/'attempt.json').exists(), 'Only one smoke attempt permitted')
    save(out/'attempt.json', dict(review_sha256=review, **owner))
    status = dict(state='WAITING_BUILDER_EXIT_EVENT', child_pid=None, **owner)
    save(out/'status.json', status)
    report = dict(state='FAIL', automatic_retry=False, full_model_executed=False)
    try:
        verify(pins)
        wait_builder(plan['builder_owner'])
        image = Path(plan['image'])
        s.preflight(image)
        built = read(image/'build.json')
        require(built['state'] == 'RESIDENT_DEPLOYMENT_SOC_BUILT_NOT_EXECUTED' and
                built['post_pins_match'] is True and built['post_image_match'] is True,
                'Build did not pass; query is forbidden')
        imagepins = b.image_inventory(image/'sim')
        require(imagepins == read(image/'image-pins.json') == built['image_pins'], 'Image inventory drift')
        pins.update(imagepins)
        inputs, work = out/'inputs', out/'work'; work.mkdir()
        os.environ.clear(); os.environ.update(plan['environment'])
        os.environ['PYTHONPATH'] = str(inputs/'verification')
        commands = []

        def run(label, argv, timeout=120):
            verify(pins)
            argv = list(map(str, argv)); commands.append(dict(label=label, argv=argv, timeout=timeout))
            save(out/'commands.json', commands)
            base.execute(argv, work, out/(label+'.log'), timeout, status, out/'status.json', label)
            verify(pins)

        run('checker-tests', [plan['python'], '-B', inputs/'query_test.py'])
        flags = ['-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-mcmodel=medany', '-mno-relax',
                 '-O2', '-fno-tree-vectorize', '-fno-tree-slp-vectorize', '-ffunction-sections',
                 '-fdata-sections', '-DNR_LANES=4', '-DVLEN=1024',
                 '-I'+str(inputs/'sdk/include'), '-I'+str(inputs/'common')]
        sources = [inputs/'query.c', inputs/'sdk/src/akv_runtime.c',
                   *[inputs/'common'/n for n in ('crt0.S', 'printf.c', 'string.c', 'serial.c', 'util.c', 'print_trap_cause.c')]]
        objects = []
        for index, source in enumerate(sources):
            obj = work/f'query_{index}.o'
            extra = ['-ffreestanding', '-fno-builtin', '-fno-tree-loop-distribute-patterns'] if source.name == 'string.c' else []
            run(f'cc-{index}', [GNU/'riscv64-unknown-elf-gcc', *flags, *extra, '-MD', '-MF', obj.with_suffix('.d'), '-c', source, '-o', obj])
            objects.append(obj)
        elf = work/'query.elf'
        run('link', [GNU/'riscv64-unknown-elf-gcc', *flags[:4], '-static', '-nostartfiles', '-nostdlib',
            *objects, '-Wl,--gc-sections', '-T', inputs/'link.ld', '-Wl,--start-group', '-lm', '-lc',
            '-lgcc', '-lnosys', '-Wl,--end-group', '-o', elf])
        compiled = {}
        for dep in work.glob('*.d'):
            for name in shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1]):
                path = Path(name).resolve(strict=True)
                require(not path.is_relative_to(ROOT/'software'), 'Dirty/live SDK compiler input')
                compiled[str(path)] = sha(path)
        save(out/'compiler-input-pins.json', compiled)
        pins.update(compiled); pins[str(elf)] = sha(elf)
        save(out/'execution-pins.json', pins)
        run('query', [image/'sim/simv', '-no_save', '-l', work/'run.vcs.log', '+PRELOAD='+str(elf),
            '+UVM_TESTNAME=ara_cvxif_smoke_test', '+TESTCASE=resident_deployment_query',
            '+NO_FSDB', '+NO_INSTR_TRACE', '+VECTOR_TRACE='+str(work/'vector.csv'),
            '+COMMIT_TRACE='+str(work/'commit.csv'), '+ARA_CONTRACT_TRACE_LIMIT=2000000',
            '+ARA_UVM_TRACE_LIMIT=2000000'], plan['smoke_seconds'])
        with (work/'commit.csv').open() as stream:
            report = check_native((work/'run.vcs.log').read_text(), list(csv.DictReader(stream)))
        run('protocol', [plan['python'], '-B', '-m', 'ara_verify.uvm_dut', '--require-events',
            '--log', work/'run.vcs.log', '--simv', image/'sim/simv', '--elf', elf,
            '--output', work/'protocol.json'])
        proof = read(work/'protocol.json')
        require(proof['status'] == 'PASS' and proof['issues'] == [] and
                proof['simv_sha256'] == sha(image/'sim/simv') and proof['elf_sha256'] == sha(elf) and
                proof['log_sha256'] == sha(work/'run.vcs.log') and proof['sim_image_sha256'] ==
                {p: h for p, h in imagepins.items() if p == str(image/'sim/simv') or p.endswith('.so')},
                'Independent CVXIF/image/ELF identity check failed')
        counts = proof['contract_counts']
        require(counts['requests'] == counts['responses'] and counts['requests'] >= 7 and
                all(counts[k] == 0 for k in ('exceptions', 'protocol_errors', 'outstanding', 'mmu_request_cycles')),
                'Query exceptions/drain/VLSU failure')
        require(all(value == 0 for name in ('backend_counts', 'axi_read_counts', 'axi_write_counts')
                    for value in proof[name].values()) and proof['uvm_backend_event_count'] == 0,
                'Query entered the compute/backend/VLSU datapath')
        verify(pins); s.preflight(image)
        report.update(source_pins_sha256=review, image=str(image/'sim/simv'),
                      image_pins_sha256=sha(image/'image-pins.json'), post_pins_match=True)
    except BaseException as error:
        report = dict(state='FAIL', error=repr(error), automatic_retry=False, full_model_executed=False)
    save(out/'result.json', report)
    status.update(state=report['state'], child_pid=None); save(out/'status.json', status)
    artifacts = {str(path.relative_to(out)): sha(path) for path in out.rglob('*') if path.is_file()
                 and path.name not in ('service.stdout.log', 'service.stderr.log')}
    save(out/'artifact-pins.json', artifacts)
    print(json.dumps(report), flush=True)
    return int(report['state'] != 'PASS')


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    sub = parser.add_subparsers(dest='action', required=True)
    prep = sub.add_parser('prepare'); prep.add_argument('--output', required=True, type=Path)
    prep.add_argument('--image', required=True, type=Path)
    run = sub.add_parser('execute'); run.add_argument('--output', required=True, type=Path)
    run.add_argument('--review-sha256', required=True)
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare(args.output.resolve(), args.image.resolve())
        return 0
    return execute(args.output.resolve(), args.review_sha256)


if __name__ == '__main__':
    raise SystemExit(main())
