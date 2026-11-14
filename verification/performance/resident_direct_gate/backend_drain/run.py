"""Prepare one ELF against a sealed image; execute only after separate hash review."""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import struct
import subprocess
import sys
import time

ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
OWN = ROOT.parent / 'ara_dsa_signoff_integration/verification/performance/resident_direct_gate/backend_drain'
IMAGE = OUT / 'enablement_soc_resident_deployment_20261112_022423'
AUDIT = OUT / 'enablement_soc_resident_deployment_query_audit_20261112_022423'
QUERY = OUT / 'enablement_soc_resident_deployment_query_20261112_022423'
PROTOCOL = OUT / 'resident_deployment_compute_vcs_20261112_02'
GNU = Path('/home/wangwy/llama/platforms/cva6-qemu/tools/bin')
FILES = ('start.S', 'link.ld', 'cases.S', 'main.c', 'fixture.py', 'check.py', 'test_check.py', 'run.py')
DIFFERENCES = {'hardware/deps/cva6/core/' + n + '.sv' for n in
               ('commit_stage', 'csr_regfile', 'cva6', 'decoder', 'id_stage')} | {'hardware/tb/ara_tb.sv'}
EVIDENCE = ('hardware/src/lane/operand_requester.sv', 'hardware/src/lane/lane.sv',
            'hardware/src/ara_system.sv', 'hardware/tb/ara_commit_monitor.sv',
            'hardware/include/ara_pkg.sv', 'hardware/src/ara_dispatcher.sv',
            'hardware/src/ara_sequencer.sv', 'hardware/src/vlsu/vlsu.sv',
            'hardware/src/vlsu/akv/akv_engine.sv')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    with Path(path).open('x') as f:
        json.dump(value, f, indent=2)
        f.write('\n')


def require(ok, why):
    if not ok:
        raise ValueError(why)


def verify(pins):
    for path, value in pins.items():
        require(sha(path) == value, 'Input drift: ' + path)


def unit(out):
    return 'resident-gate-drain-' + out.name + '.service'


def identity(inputs):
    hw, original = read(IMAGE / 'build.json'), read(IMAGE / 'source-pins.json')
    require(sha(IMAGE / 'source-pins.json') == hw['source_pins_sha256'] ==
            '6f72deab767889eee7d2de0126c51721063da5970805884e683c2c7631e7cd46', 'Image build receipt identity')
    require(hw['state'] == 'RESIDENT_DEPLOYMENT_SOC_BUILT_NOT_EXECUTED' and hw['post_pins_match'] and
            hw['post_image_match'], 'Image build receipt rejected')
    require(all(hw['configuration'][k] == v for k, v in dict(nr_lanes=4, vlen=1024, shared_fma=1,
            resident_pv_enabled=1, resident_qk_enabled=1, ideal_dispatcher=0,
            resident_capability=0x40000040301).items()), 'Image configuration drift')
    verify(hw['image_pins'])
    require(sha(AUDIT / 'source-pins.json') == '65acdb4a490f9eab144277174a9422c0b1d1adc4f1da857676f037432b7a65f4',
            'Accepted query audit identity')
    verify(read(AUDIT / 'source-pins.json'))
    verify({str(AUDIT / p): h for p, h in read(AUDIT / 'artifact-pins.json').items()})
    a = read(AUDIT / 'result.json')
    require(a['state'] == 'PASS' and a['original_worker_state'] == 'FAIL' and
            not a['original_worker_relabelled'] and not a['native']['resident_arithmetic_executed'] and
            read(QUERY / 'result.json')['state'] == 'FAIL', 'Query audit scope drift')
    pins = dict(hw['image_pins'])
    entries, changes = [], []
    prefix = str(IMAGE / 'source') + '/'
    for path, expected in original.items():
        if not path.startswith(prefix):
            continue
        require(sha(path) == expected, 'Frozen source drift: ' + path)
        pins[path] = expected
        relative = path[len(prefix):]
        if relative.startswith('hardware/'):
            current = ROOT / relative
            actual = sha(current)
            pins[str(current)] = actual
            entries.append(dict(path=relative, frozen_sha256=expected, current_sha256=actual,
                                equal=actual == expected))
            if actual != expected:
                changes.append(relative)
                diff = ''.join(difflib.unified_diff(Path(path).read_text().splitlines(True),
                    current.read_text().splitlines(True), fromfile=path, tofile=str(current)))
                (inputs / ('identity-' + relative.replace('/', '_') + '.diff')).write_text(diff)
    require(set(changes) == DIFFERENCES, 'Unexpected hardware identity differences: ' + repr(changes))
    for relative in EVIDENCE:
        source = IMAGE / 'source' / relative
        require(str(source) in pins and pins[str(source)] == pins[str(ROOT / relative)], 'Evidence source mismatch')
        dst = inputs / 'evidence' / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dst)
    for directory, names in ((IMAGE, ('build.json', 'source-pins.json', 'image-pins.json', 'compile.command.json', 'sources.f')),
                             (AUDIT, ('result.json', 'source-pins.json', 'artifact-pins.json', 'native.json', 'protocol.json')),
                             (QUERY, ('result.json',)), (PROTOCOL, ('source-pins.json', 'result.json'))):
        for name in names:
            pins[str(directory / name)] = sha(directory / name)
    approved = read(PROTOCOL / 'source-pins.json')
    for file in (PROTOCOL / 'inputs/verification/ara_verify').rglob('*.py'):
        require(str(file) in approved and sha(file) == approved[str(file)], 'Frozen protocol helper drift')
        pins[str(file)] = sha(file)
    save(inputs / 'identitydiff.json', dict(image=str(IMAGE), configuration=hw['configuration'],
        hardware_files=len(entries), backend_src_include_files=sum(e['path'].startswith(('hardware/src/', 'hardware/include/')) for e in entries),
        changed=changes, entries=entries, original_query_state='FAIL',
        accepted_query_audit_scope=a['scope'], gate_tested=False, linux_tested=False,
        scope='Current backend bytes in a legacy-core image; not current gate or Linux integration'))
    return pins, hw


def elf_word(elf, pc):
    raw = Path(elf).read_bytes()
    require(raw[:6] == b'\x7fELF\x02\x01', 'Not ELF64 little-endian')
    offset = struct.unpack_from('<Q', raw, 32)[0]
    size, count = struct.unpack_from('<HH', raw, 54)
    for i in range(count):
        ptype, _, fileoff, vaddr, _, filesz, _, _ = struct.unpack_from('<IIQQQQQQ', raw, offset + i * size)
        if ptype == 1 and vaddr <= pc and pc + 4 <= vaddr + filesz:
            return struct.unpack_from('<I', raw, fileoff + pc - vaddr)[0]
    raise ValueError('Instruction PC not in loaded ELF segment')


def prepare(out):
    require(Path(__file__).resolve().parent == OWN and not out.exists(), 'Fresh preparation only')
    out.mkdir()
    inputs = out / 'inputs'
    inputs.mkdir()
    pins = {}
    for name in FILES:
        shutil.copyfile(OWN / name, inputs / name)
        pins[str(OWN / name)] = sha(OWN / name)
    inherited, hw = identity(inputs)
    pins.update(inherited)
    # Existing bare-metal preload/link convention, without any SoC/SDK rebuild.
    from fixture import generate
    golden = generate(inputs)
    commands = []
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    def command(label, argv):
        completed = subprocess.run(list(map(str, argv)), cwd=out, env=env, text=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
        (out / (label + '.log')).write_text(completed.stdout)
        commands.append(dict(label=label, argv=list(map(str, argv)), returncode=completed.returncode))
        save(out / (label + '.command.json'), commands[-1])
        require(completed.returncode == 0, 'Preparation failed: ' + label + '\n' + completed.stdout[-2000:])
        return completed.stdout
    cc = GNU / 'riscv64-linux-gcc'
    for program in ('cc1', 'as', 'ld'):
        name = command('tool-' + program, [cc, '-print-prog-name=' + program]).strip()
        path = Path(name) if '/' in name else Path(shutil.which(name) or name)
        pins[str(path.resolve())] = sha(path)
    for file in (cc, GNU / 'riscv64-linux-gcc.br_real', GNU / 'riscv64-linux-nm', GNU / 'riscv64-linux-objdump'):
        if file.exists():
            pins[str(file)] = sha(file)
    flags = ['-O2', '-march=rv64gcv_zfh_zvfh', '-mabi=lp64', '-mcmodel=medany', '-mno-relax',
             '-msmall-data-limit=0', '-ffreestanding', '-fno-builtin', '-fno-stack-protector',
             '-fno-tree-loop-distribute-patterns', '-fno-tree-vectorize', '-fno-tree-slp-vectorize', '-nostdinc']
    objects = []
    for name in ('start.S', 'cases.S', 'main.c', 'data.S'):
        obj = inputs / (name + '.o')
        command('cc-' + name, [cc, *flags, '-c', inputs / name, '-o', obj])
        objects.append(obj)
    elf = inputs / 'drain.elf'
    command('link', [cc, *flags, '-nostdlib', '-static', '-T' + str(inputs / 'link.ld'), *objects, '-o', elf])
    nm = command('nm', [GNU / 'riscv64-linux-nm', '-n', elf])
    command('objdump', [GNU / 'riscv64-linux-objdump', '-d', elf])
    addresses = {line.split()[2]: int(line.split()[0], 16) for line in nm.splitlines() if len(line.split()) == 3}
    symbols = {}
    for name, case in golden['cases'].items():
        pc = addresses[name + '_issue']
        require(pc % 64 == 0, 'Target not 64-byte aligned')
        words = (case['insn'], (0xc20 << 20) | (2 << 12) | (case['csr_rd'] << 7) | 0x73,
                 (1 << 25) | (11 << 15) | ((case['eew'] + 4) << 12) | (case['vd'] << 7) | 0x27)
        for j, suffix in enumerate(('issue', 'csr', 'save')):
            key = name + '_' + suffix
            require(addresses[key] == pc + 4*j and elf_word(elf, addresses[key]) == words[j],
                    'Custom/CSR/save adjacency or encoding mismatch: ' + key)
            symbols[key] = dict(pc=addresses[key], insn=words[j])
    save(inputs / 'symbols.json', symbols)
    command('checker-preflight', [sys.executable, '-B', inputs / 'test_check.py'])
    save(out / 'preflight.json', dict(state='HOST_CHECKER_AND_ELF_PREFLIGHT_PASS',
        simulator_executed=False, synthetic_checker_tests_only=True, four_aligned_adjacent_sequences=True,
        golden='exact rational, intermediate FP16/FP32 representability checked', payload_elements=768,
        source_elements=512, guarded_buffers=5, automatic_retry=False))
    for path in inputs.rglob('*'):
        if path.is_file():
            pins[str(path)] = sha(path)
    for path in (out / 'preflight.json', out / 'checker-preflight.log'):
        pins[str(path)] = sha(path)
    work = out / 'work'
    simulate = [hw['simv'], '-no_save', '-l', str(work / 'run.vcs.log'), '+PRELOAD=' + str(elf),
        '+UVM_TESTNAME=ara_cvxif_smoke_test', '+TESTCASE=resident_gate_backend_drain', '+NO_FSDB', '+NO_INSTR_TRACE',
        '+COMMIT_TRACE=' + str(work / 'commit.csv'), '+VECTOR_TRACE=' + str(work / 'vector.csv'),
        '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000', '+COMMIT_WATCHDOG=100000']
    protocol = [sys.executable, '-B', '-m', 'ara_verify.uvm_dut', '--require-events', '--require-backend',
        '--require-axi', '--require-axi-write', '--vector-trace', str(work / 'vector.csv'),
        '--log', str(work / 'run.vcs.log'), '--simv', hw['simv'], '--elf', str(elf), '--output', str(work / 'protocol.json')]
    save(out / 'plan.json', dict(simulate=simulate, protocol=protocol, hard_limit_seconds=300,
        automatic_retry=False, environment=dict(PATH='/usr/bin:/bin', HOME='/home/wangwy', LC_ALL='C',
            SNPSLMD_LICENSE_FILE='27000@t7920', PYTHONPATH=str(PROTOCOL / 'inputs/verification'), PYTHONDONTWRITEBYTECODE='1',
            READELF='/usr/bin/readelf'), expected_sim_image={p: h for p, h in hw['image_pins'].items()
                if p == hw['simv'] or p.endswith('.so')}, scope='backend-only, legacy core, no gate/Linux acceptance'))
    pins[str(out / 'plan.json')] = sha(out / 'plan.json')
    verify(pins)
    save(out / 'source-pins.json', pins)
    review = sha(out / 'source-pins.json')
    launch = ['systemd-run', '--user', '--unit=' + unit(out), '--property=Type=exec',
        '--property=KillMode=control-group', '--property=RuntimeMaxSec=300', '--property=TimeoutStopSec=20',
        '--property=StandardOutput=append:' + str(out / 'service.stdout.log'),
        '--property=StandardError=append:' + str(out / 'service.stderr.log'),
        sys.executable, '-B', '-u', str(inputs / 'run.py'), 'execute', '--output', str(out), '--review-sha256', review]
    save(out / 'launch-command.json', launch)
    save(out / 'prepared.json', dict(state='PREPARED_NOT_LAUNCHED', review_sha256=review,
        elf_sha256=sha(elf), identitydiff_sha256=sha(inputs / 'identitydiff.json'), source_pin_count=len(pins)))
    print(json.dumps(read(out / 'prepared.json')), flush=True)


def execute(out, review):
    require(Path(__file__).resolve() == out / 'inputs/run.py' and sha(out / 'source-pins.json') == review,
            'Frozen reviewed runner required')
    owner = subprocess.check_output(['systemctl', '--user', 'show', unit(out), '-p', 'MainPID', '--value'], text=True).strip()
    require(owner == str(os.getpid()), 'Worker must be owned directly by service')
    save(out / 'attempt.json', dict(pid=os.getpid(), cgroup=Path('/proc/self/cgroup').read_text()))
    from check import check, InsufficientWindow
    start = time.monotonic()
    plan, pins = read(out / 'plan.json'), read(out / 'source-pins.json')
    result = dict(state='FAIL', gate_tested=False, linux_tested=False, board_tested=False, automatic_retry=False)
    work = out / 'work'
    work.mkdir()
    def stop(signum, frame):
        raise TimeoutError('Service stop/deadline signal ' + str(signum))
    signal.signal(signal.SIGTERM, stop)
    def run(label, command):
        remaining = 300 - (time.monotonic() - start)
        require(remaining > 0, '300-second worker budget exhausted')
        with (work / (label + '.log')).open('x') as log:
            child = subprocess.Popen(command, cwd=work, env=plan['environment'], stdout=log, stderr=subprocess.STDOUT,
                                     start_new_session=True)
            save(work / (label + '.process.json'), dict(pid=child.pid, command=command))
            try:
                rc = child.wait(timeout=remaining)
            finally:
                if child.poll() is None:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
        require(rc == 0, label + ' failed: ' + str(rc))
    try:
        verify(pins)
        run('simulation', plan['simulate'])
        run('protocol', plan['protocol'])
        p = read(work / 'protocol.json')
        require(p['status'] == 'PASS' and not p['issues'] and p['sim_image_sha256'] == plan['expected_sim_image'] and
                p['elf_sha256'] == sha(out / 'inputs/drain.elf') and p['log_sha256'] == sha(work / 'run.vcs.log') and
                all(p['contract_counts'][k] == 0 for k in ('exceptions', 'outstanding', 'protocol_errors')),
                'Existing protocol checker did not pass with exact image/ELF/log identities')
        result.update(check(work, out / 'inputs'))
        verify(pins)
        result.update(post_pins_match=True, protocol_sha256=sha(work / 'protocol.json'))
    except InsufficientWindow as error:
        result.update(state='INSUFFICIENT_WINDOW_NOT_PASS', error=str(error))
    except BaseException as error:
        result.update(state='FAIL', error=repr(error))
    result['elapsed_seconds'] = time.monotonic() - start
    save(out / 'result.json', result)
    artifacts = {str(p.relative_to(out)): sha(p) for p in work.rglob('*') if p.is_file()}
    artifacts['result.json'] = sha(out / 'result.json')
    save(out / 'artifact-pins.json', artifacts)
    print(json.dumps(result), flush=True)
    return int(result['state'] != 'BACKEND_ONLY_CHECKED')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'execute'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--review-sha256')
    args = parser.parse_args()
    out = args.output.resolve()
    require(out.parent == OUT and out.name.startswith('resident_gate_drain_'), 'Owned output required')
    if args.action == 'prepare':
        prepare(out)
        return 0
    return execute(out, args.review_sha256)


if __name__ == '__main__':
    raise SystemExit(main())
