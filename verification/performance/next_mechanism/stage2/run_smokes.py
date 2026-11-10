#!/usr/bin/env python3
"""Freeze and run unchanged control/handoff smokes, sequentially, on a sealed SoC."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
BASE = ROOT / 'verification/performance/chain_profile/build_soc.py'
SIBLING = 'build_smokes.py'
SCOPE = ('Unchanged HEAD QBS enabled control/exception recovery and QBS/normal-RVV/AKV2 '
         'handoff smokes. Firmware self-checks plus independent unchanged CVXIF/VID/AXI '
         'protocol checks and exact exception-instruction binding; no performance or '
         'independent trap-CSR retirement acceptance.')


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def input_pins(base, soc, software, cases, contracts):
    hw = json.loads((soc / 'build.json').read_text())
    sw = json.loads((software / 'build.json').read_text())
    expected = dict(schema_version=1, config='stage2_lane_coexecution',
        revision=hw['configuration']['revision'], nr_lanes=4, vlen=1024, qbs_enabled=1,
        akv_enabled=1, akv_v2_enabled=1, sim_l2_bytes=16777216,
        shared_simd_multiplier=1, shared_fma=0,
        qbs_lane_multiplier=hw['configuration']['qbs_lane_multiplier'], ideal_dispatcher=0)
    base.require(hw['state'] == 'STAGE2_SOC_BUILT_NOT_EXECUTED' and hw['post_pins_match'] and
                 hw['configuration'] == expected and expected['qbs_lane_multiplier'] in (0, 1),
                 'Wrong/unsealed SoC configuration')
    base.require(sw['state'] == 'BUILT_NOT_EXECUTED' and sw['post_pins_match'] and
                 sw['configuration'] == dict(nr_lanes=4, vlen=1024, march='rv64gcv_zfh_zvfh', abi='lp64d') and
                 sw['dirty_makefile_used'] is False and sw['sdk_akv_assembly_used'] is False and
                 sw['archive_paths'] == ['apps/common', 'apps/qbs_control_smoke', 'apps/qbs_akv_handoff_smoke'],
                 'Wrong/unsealed fresh smoke build')
    pins = {}
    for directory, record in ((soc, hw), (software, sw)):
        pinfile = directory / 'source-pins.json'
        base.require(base.digest(pinfile) == record['source_pins_sha256'], 'Source inventory identity differs')
        bundles = [json.loads(pinfile.read_text())]
        if directory == soc:
            bundles.append(record['image_pins'])
        for bundle in bundles:
            for path, digest in bundle.items():
                base.require(path not in pins or pins[path] == digest, 'Conflicting input pin: ' + path)
                pins[path] = digest
        for path in (directory / 'build.json', pinfile):
            pins[str(path)] = base.digest(path)
    simv = Path(hw['simv']).resolve(strict=True)
    base.require(simv.is_relative_to(soc) and str(simv) in hw['image_pins'] and
                 hw['image_pins'][str(simv)] == base.digest(simv) and
                 len(hw['image_pins']) > 1, 'Missing/wrong SoC image closure')
    for case in cases:
        program = sw['programs'][case]
        elf = Path(program['elf']).resolve(strict=True)
        base.require(elf.is_relative_to(software) and elf.read_bytes()[:4] == b'\x7fELF' and
                     base.digest(elf) == program['elf_sha256'], 'ELF identity/location differs')
        for key in ('pass_line', 'expected_exception_instructions', 'required_words'):
            base.require(program[key] == contracts[case][key], 'Case contract differs: ' + key)
        base.require(pins.get(str(elf)) == program['elf_sha256'], 'ELF omitted from source pins')
    base.verify(pins)
    return hw, sw, pins


def check_exceptions(case, events, contracts):
    """Bind each real CVXIF exception response to its accepted instruction, not fake retire."""
    pending, observed = {}, []
    for _, req, req_id, insn, resp, resp_id, exc in events:
        old = pending.pop(resp_id, None) if resp else None
        if req:
            if req_id in pending:
                raise ValueError('Live CVXIF ID reused')
            pending[req_id] = insn
        if resp:
            instruction = old if old is not None else pending.pop(resp_id, None)
            if instruction is None:
                raise ValueError('Exception accounting response without request')
            if exc:
                observed.append(instruction)
    if pending or observed != contracts[case]['expected_exception_instructions']:
        raise ValueError('Unexpected/missing exception instruction sequence: ' + repr(observed))
    return dict(count=len(observed), instructions=[f'{word:08x}' for word in observed])


def prepare(args):
    base = load(BASE, 'smoke_run_base')
    out = args.output.resolve()
    base.require(out.parent == OUT and not out.exists(), 'Fresh direct signoff output required')
    base.require(1 <= args.timeout <= 10800, 'Invalid per-case timeout')
    soc, software = args.soc_build.resolve(strict=True), args.software_build.resolve(strict=True)
    sibling = software / 'inputs' / SIBLING
    software_record = json.loads((software / 'build.json').read_text())
    software_pinfile = software / 'source-pins.json'
    base.require(base.digest(software_pinfile) == software_record['source_pins_sha256'],
                 'Smoke helper inventory identity differs')
    base.require(json.loads(software_pinfile.read_text()).get(str(sibling)) == base.digest(sibling),
                 'Smoke helper is not the sealed software-build input')
    contracts = load(sibling, 'smoke_contracts')
    cases = [args.case] if args.case else list(contracts.CASES)
    base.require(set(cases) <= set(contracts.CASES), 'Unknown smoke case')
    hw, sw, pins = input_pins(base, soc, software, cases, contracts.CASES)
    out.mkdir()
    inputs = out / 'inputs'
    inputs.mkdir()
    for source, name in ((Path(__file__), 'run_smokes.py'), (sibling, SIBLING), (BASE, 'base_build.py')):
        target = inputs / name
        target.write_bytes(source.read_bytes())
        pins[str(source)] = pins[str(target)] = base.digest(source)
    inventory = sorted(str(p) for p in (ROOT / 'verification/ara_verify').rglob('*.py'))
    for name in inventory:
        pins[name] = base.digest(name)
    contract = ROOT / 'hardware/scripts/llama_q4km_extract/check-sim-l2.sh'
    pins[str(contract)] = base.digest(contract)
    for tool in ('bash', 'timeout', 'systemctl', 'readelf'):
        path = Path(shutil.which(tool) or ('/missing-' + tool)).resolve(strict=True)
        pins[str(path)] = base.digest(path)
    pins[str(Path(sys.executable).resolve())] = base.digest(sys.executable)
    base.save(out / 'selection.json', dict(soc_build=str(soc), software_build=str(software),
        cases=cases, timeout=args.timeout, protocol_seconds=600, scope=SCOPE,
        checker_inventory=inventory, simv_sha256=base.digest(hw['simv']),
        source_commit=sw['source_commit']))
    pins[str(out / 'selection.json')] = base.digest(out / 'selection.json')
    base.verify(pins)
    base.save(out / 'source-pins.json', pins)
    base.save(out / 'status.json', dict(state='PREPARED_NOT_EXECUTED', child_pid=None))
    print('PREPARED_NOT_EXECUTED ' + str(inputs / 'run_smokes.py'), flush=True)
    return out


def execute(out):
    if Path(__file__).resolve() != out / 'inputs/run_smokes.py':
        raise ValueError('Execute frozen output entry point only')
    base = load(out / 'inputs/base_build.py', 'smoke_run_base')
    checker = load(out / 'inputs' / SIBLING, 'smoke_contracts')
    config = json.loads((out / 'selection.json').read_text())
    pins = json.loads((out / 'source-pins.json').read_text())
    report = dict(state='FAIL', scope=config['scope'], cases=[], rtl_executed=False)
    status = dict(state='PREFLIGHT', child_pid=None, started=datetime.now(timezone.utc).isoformat())
    try:
        base.verify(pins)
        cgroup = Path('/proc/self/cgroup').read_text()
        service = [part for part in cgroup.strip().split('/') if part.endswith('.service')][-1]
        main_pid = int(subprocess.check_output(['systemctl', '--user', 'show', '--value',
                       '--property=MainPID', service], text=True).strip())
        base.require(main_pid in (os.getpid(), os.getppid()),
                     'Require a direct service worker or its long-lived campaign child')
        base.require(Path(f'/proc/{main_pid}/cgroup').read_text() == cgroup,
                     'Smoke worker escaped its service owner CGroup')
        base.save(out / 'owner.json', dict(pid=os.getpid(), service_main_pid=main_pid,
                                          service=service, cgroup=cgroup,
                                          service_cmdline=Path(f'/proc/{main_pid}/cmdline').read_bytes().decode().split('\0'),
                                          runner=str(Path(__file__).resolve())))
        actual_inventory = sorted(str(p) for p in (ROOT / 'verification/ara_verify').rglob('*.py'))
        base.require(actual_inventory == config['checker_inventory'], 'Checker inventory drift')
        hw, sw, _ = input_pins(base, Path(config['soc_build']), Path(config['software_build']),
                              config['cases'], checker.CASES)
        simv = Path(hw['simv'])
        os.environ.update(PYTHONPATH=str(ROOT / 'verification'), PYTHONDONTWRITEBYTECODE='1',
                          READELF='/usr/bin/readelf', LC_ALL='C')
        sys.path.insert(0, str(ROOT / 'verification'))
        from ara_verify import uvm_dut
        for case in config['cases']:
            work = out / case
            work.mkdir(exist_ok=False)
            elf = Path(sw['programs'][case]['elf'])
            status['case'] = case
            base.execute(['bash', ROOT / 'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',
                          simv.parent, elf], work, work / 'image-contract.log', 180,
                         status, out / 'status.json', 'IMAGE_CONTRACT')
            argv = [simv, '-no_save', '-l', work / 'run.vcs.log', '+PRELOAD=' + str(elf),
                    '+TESTCASE=' + case, '+NO_FSDB', '+NO_INSTR_TRACE',
                    '+VECTOR_TRACE=' + str(work / 'vector_trace.csv'),
                    '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000']
            print('STAGE2_SMOKE_RUNNING ' + case, flush=True)
            report['rtl_executed'] = True
            base.execute(argv, work, work / 'console.log', config['timeout'],
                         status, out / 'status.json', 'RUNNING')
            log, vector, proof = work / 'run.vcs.log', work / 'vector_trace.csv', work / 'protocol.json'
            text = log.read_text()
            measured = checker.check_log(case, text)
            base.execute([sys.executable, '-B', '-m', 'ara_verify.uvm_dut', '--require-events',
                          '--require-backend', '--require-axi', '--require-axi-write',
                          '--vector-trace', vector, '--log', log, '--simv', simv,
                          '--elf', elf, '--output', proof], work, work / 'protocol.log',
                         config['protocol_seconds'], status, out / 'status.json', 'PROTOCOL_CHECK')
            protocol = json.loads(proof.read_text())
            base.require(protocol['status'] == 'PASS' and protocol['issues'] == [] and
                         protocol['elf_sha256'] == sw['programs'][case]['elf_sha256'] and
                         protocol['simv_sha256'] == config['simv_sha256'] and
                         protocol['log_sha256'] == base.digest(log) and
                         protocol['vector_trace_sha256'] == base.digest(vector),
                         'Independent protocol/identity check failed')
            events, issues = uvm_dut._events(text, '[CVXIF/EVENT]', uvm_dut._UVM_EVENT, 10)
            base.require(not issues, 'Malformed CVXIF exception evidence')
            exceptions = check_exceptions(case, events, checker.CASES)
            base.require(protocol['contract_counts']['exceptions'] == exceptions['count'],
                         'Independent contract exception count differs')
            base.verify(pins)
            report['cases'].append(dict(state='PASS', **measured, exceptions=exceptions,
                elf_sha256=sw['programs'][case]['elf_sha256'], protocol_checked=True,
                artifacts={str(p): base.digest(p) for p in work.iterdir() if p.is_file()}))
        base.verify(pins)
        base.require(actual_inventory == sorted(str(p) for p in
                     (ROOT / 'verification/ara_verify').rglob('*.py')), 'Post-checker inventory drift')
        report.update(state='PASS', post_pins_match=True, source_commit=sw['source_commit'],
                      soc_build=config['soc_build'], software_build=config['software_build'],
                      simv_sha256=config['simv_sha256'],
                      source_pins_sha256=base.digest(out / 'source-pins.json'))
    except BaseException as exc:
        report['error'] = repr(exc)
    report['artifacts'] = {str(p): base.digest(p) for p in out.rglob('*') if p.is_file()
                           and p.name not in ('report.json', 'status.json') and 'inputs' not in p.parts}
    base.save(out / 'report.json', report)
    status.update(state=report['state'], child_pid=None, finished=datetime.now(timezone.utc).isoformat())
    base.save(out / 'status.json', status)
    print('STAGE2_SMOKES_' + report['state'] + ' ' + str(out / 'report.json'), flush=True)
    return int(report['state'] != 'PASS')


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--soc-build', type=Path)
    parser.add_argument('--software-build', type=Path)
    parser.add_argument('--case', choices=('qbs_control_smoke', 'qbs_akv_handoff_smoke'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=1800, help='Simulation seconds per case')
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--execute', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.execute:
        def interrupted(sig, _frame):
            raise InterruptedError('Signal ' + str(sig))
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, interrupted)
        return execute(args.output.resolve())
    if args.soc_build is None or args.software_build is None:
        parser.error('--soc-build and --software-build are required')
    out = prepare(args)
    if not args.prepare_only:
        os.execv(sys.executable, [sys.executable, '-B', str(out / 'inputs/run_smokes.py'),
                                 '--output', str(out), '--execute'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
