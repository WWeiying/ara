"""Prepared full-qualification consumer of sealed packed/RVFI epoch evidence."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
from types import FunctionType, SimpleNamespace

import csr_satp_sepc_cycle_adapter as adapter

original, life, require = adapter.original, adapter.life, adapter.require
RUN_SEAL = '642d106324512b604d588a8a8bc003f0f3225b8fc126c36ccf70ec11d7d6d146'
EVIDENCE = life.OUT / 'csr-satp-sepc-rvfi-epoch-agent-20261008-01.json'
EVIDENCE_SHA = '4c933576f241a6795bc7f7113404e02f0edf21c834e5eaefdb1f399df795362f'
CACHE = adapter.packed.HOLD / 'csr-owner.vcd'


def manifest(run, seal, out):
    require(run == adapter.packed.RUN and seal == RUN_SEAL, 'Exact executed run/seal')
    require(run.parent == out.parent == life.OUT and run.resolve() == run and out.resolve() == out
            and not out.exists(), 'Fresh canonical qualification output')
    record = life.read_bound(run.with_name(run.name + '.prepared.json'), seal)
    require(life.read_bound(run / 'manifest.json', seal) == record, 'Executed manifest seal')
    original.runner.verify_prepared(run, record, terminal=True)
    original.terminal_gate(*[json.loads((run / name).read_bytes()) for name in
                            ('simulation-status.json', 'started.json', 'live-identity.json')], record)
    evidence = life.read_bound(EVIDENCE, EVIDENCE_SHA)
    require(evidence['status'] == 'SOURCE_BOUND_PACKED_AND_RVFI_EPOCH_OWNER_COMPONENT_VERIFIED_NOT_QUALIFICATION'
            and evidence['qualification_performed'] is False, 'Sealed owner-component evidence')
    life.check(evidence['source_contract']['pins'])
    proof = adapter.source_contract()
    saved = evidence['source_contract']
    require(all(saved.get(k) == v for k, v in proof.items() if k != 'pins') and
            all(saved['pins'].get(path) == sha for path, sha in proof['pins'].items()), 'Exact source/sampling proof replay')
    failure = json.loads((adapter.packed.HOLD / 'failure.json').read_bytes())
    require(failure == dict(status='QUALIFICATION_HOLD_NOT_ADMITTED', reason='Exact CSR probe declarations'), 'Original HOLD unchanged')
    members = sorted(p for p in (run / 'code.vdb').rglob('*') if p.is_file())
    require(members and not any(p.is_symlink() for p in (run / 'code.vdb').rglob('*')), 'Complete nonaliased VDB')
    pins = life.merge_pins(record['pins'], evidence['source_contract']['pins'])
    files = [*members, EVIDENCE, CACHE, adapter.packed.HOLD / 'vpd2vcd.log', adapter.packed.HOLD / 'failure.json',
        run.with_name(run.name + '.prepared.json'), *[run / n for n in
        ('manifest.json', 'simulation-status.json', 'started.json', 'live-identity.json', 'commit_trace.csv',
         'vector_trace.csv', 'run.vcs.log', 'console.log', 'csr-owner.vpd')],
        Path(__file__).resolve(), Path(__file__).with_name('test_collect_csr_satp_sepc_packed_successor.py')]
    files += list((life.ROOT / 'verification/ara_verify').rglob('*.py'))
    pins = life.merge_pins(pins, {str(p): life.digest(p) for p in files}); life.check(pins)
    require(pins[str(CACHE)] == evidence['source_contract']['pins'][str(CACHE)], 'Exact previously converted VCD')
    return dict(status='PREPARED_FULL_CSR_QUALIFICATION_SUCCESSOR_NOT_COLLECTED', run=str(run), run_seal=seal,
        output=str(out), input_pins=pins, cached_vcd=str(CACHE), cached_vcd_sha256=pins[str(CACHE)],
        original_collector_sha256=adapter.packed.COLLECTOR_SHA, owner_evidence=str(EVIDENCE),
        owner_evidence_sha256=EVIDENCE_SHA, qualification_performed=False, EDA_launched=False,
        gate_policy='Original complete collect code; private wave_audit replacement and exact converter-cache substitution only')


def prepare(run, seal, out, plan):
    require(plan.parent == life.OUT and plan.resolve() == plan and not plan.exists(), 'Fresh plan file')
    result = manifest(run, seal, out); life.save(plan, result)
    return result


def verify(plan, seal):
    record = life.read_bound(plan, seal); life.check(record['input_pins'])
    require(record == manifest(Path(record['run']), record['run_seal'], Path(record['output'])), 'Full successor plan/source drift')
    return record


def cached_converter(record, command, **kwargs):
    out = Path(record['output']); run = Path(record['run'])
    expected = [str(original.runner.converter.CONVERTER), '-splitpacked', str(run / 'csr-owner.vpd'), str(out / 'csr-owner.vcd')]
    require(command == expected and kwargs.get('stderr') == subprocess.STDOUT and kwargs.get('check') is True
            and type(kwargs.get('timeout')) is int and kwargs['timeout'] == 120 and
            set(kwargs) == {'stdout', 'stderr', 'check', 'timeout'}, 'Only exact original VPD converter request may use cache')
    cache = Path(record['cached_vcd']); require(life.digest(cache) == record['cached_vcd_sha256'], 'Cached VCD drift')
    destination = out / 'csr-owner.vcd'
    with cache.open('rb') as source, destination.open('xb') as target: shutil.copyfileobj(source, target)
    require(life.digest(destination) == record['cached_vcd_sha256'], 'Copied VCD differs')
    kwargs['stdout'].write('SEALED_VCD_REUSED_NO_CONVERTER_EXECUTION ' + record['cached_vcd_sha256'] + '\n')
    return subprocess.CompletedProcess(command, 0)


def consumer(record):
    namespace = dict(original.collect.__globals__)
    # The full original collector body and every gate remain intact.
    namespace['wave_audit'] = adapter.wave_audit
    namespace['subprocess'] = SimpleNamespace(**dict(vars(subprocess),
        run=lambda command, **kwargs: cached_converter(record, command, **kwargs)))
    return FunctionType(original.collect.__code__, namespace)


def collect(plan, seal):
    record = verify(plan, seal); out = Path(record['output'])
    pins = life.merge_pins(record['input_pins'], {str(plan): seal}); life.check(pins)
    consumer(record)(Path(record['run']), record['run_seal'], out)
    core = out / 'qualification.json'; result = json.loads(core.read_bytes())
    require(result['status'] == 'CSR_SATP_SEPC786_FULL_SCALAR_NATIVE_OWNER_QUALIFIED_NOT_ADMITTED'
            and result['native_CSR_owners'] == 30 and result['full_scalar_differential_qualified'] is True,
            'Original full qualification not completed')
    life.check(result['input_pins']); life.check(result['output_pins']); life.check(pins)
    closure = dict(status='FULL_CSR_PACKED_RVFI_EPOCH_QUALIFIED_NOT_ADMITTED',
        core_qualification=str(core), core_sha256=life.digest(core), prepared_plan=str(plan), prepared_seal=seal,
        input_pins=pins, original_core_output_pins=result['output_pins'],
        raw_gain=result['raw_gain'], coverage_admitted=False, EDA_launched=False,
        original_HOLD_preserved=True, core_qualification_not_overwritten=True)
    target = out / 'packed-epoch-closure.json'; life.save(target, closure)
    print(json.dumps(dict(status=closure['status'], closure=str(target), closure_sha256=life.digest(target))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('mode', choices=('prepare', 'verify', 'collect'))
    parser.add_argument('--plan', type=Path, required=True); parser.add_argument('--plan-seal')
    parser.add_argument('--run', type=Path, default=adapter.packed.RUN); parser.add_argument('--run-seal', default=RUN_SEAL)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(); plan = args.plan.absolute()
    if args.mode == 'prepare':
        require(args.output is not None, 'Prepare requires output')
        prepare(args.run.absolute(), args.run_seal, args.output.absolute(), plan)
        print(json.dumps(dict(status='PREPARED_NO_COLLECT', plan=str(plan), seal=life.digest(plan))))
    elif args.mode == 'verify':
        verify(plan, args.plan_seal); print('FULL_SUCCESSOR_PREPARED_VERIFY_PASS_NO_COLLECT')
    else: collect(plan, args.plan_seal)
