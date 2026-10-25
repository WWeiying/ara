#!/usr/bin/env python3
"""Replay an accepted real Attention ELF on the isolated shared-reader SoC."""
import argparse
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import signal
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run_handoff import s, Execution, checked_soc, ROOT
PAIRED = HERE.parent / 'paired_heads'
sys.path.insert(0, str(PAIRED))
spec = importlib.util.spec_from_file_location('shared_reader_real_runtime', PAIRED / 'run_live_regression.py')
original = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = original
spec.loader.exec_module(original)
KINDS = ('decode', 'prefill', 'quant_q4_0', 'quant_q8_0')


def compare_outputs(reference, candidate):
    old, new = reference['trials'], candidate['trials']
    s.require(len(old) == len(new) and bool(old), 'Incomplete runtime calls')
    for before, after in zip(old, new):
        keys = set(before) - {'cycles', 'hardware_totals'}
        s.require(keys == set(after) - {'cycles', 'hardware_totals'} and
                  all(before[k] == after[k] for k in keys), 'Output/CSR or case ordering differs')
    totals_present = all('hardware_totals' in r for r in [*old, *new])
    return dict(calls=len(old), output_signatures_and_csrs_identical=True,
        per_call_counters_available=totals_present,
        per_call_counters_identical=(all(a['hardware_totals'] == b['hardware_totals'] for a,b in zip(old,new))
                                     if totals_present else None),
        command_counters_available='hardware_records' in reference and 'hardware_records' in candidate,
        command_counters_identical=(reference['hardware_records'] == candidate['hardware_records']
                                    if 'hardware_records' in reference and 'hardware_records' in candidate else None),
        task_cycles_identical=all(a.get('cycles') == b.get('cycles') for a,b in zip(old,new)),
        task_cycles_available=all('cycles' in a and 'cycles' in b for a,b in zip(old,new)))


def run(args):
    s.require(args.kind in KINDS, 'Wrong kind')
    build, prior = args.build.resolve(strict=True), args.prior.resolve(strict=True)
    if args.kind.startswith('quant_'):
        sys.path.insert(0, str(HERE.parent / 'quantized_kv'))
        import run_strided_attention as quant
        report, pins = quant.checked_build(build)
        kind = args.kind.removeprefix('quant_')
        s.require(report['kind'] == kind, 'Quantized profile differs')
        capture = ROOT / 'verification/out/akv-quantkv-host-capture-20261024-01' / (
            'capture-k-' + kind + '-v-q8_0') / 'decode/block/kqv_out-0.bin'
        s.merge_pins(pins, s.hashes([capture]))
        def checker(text):
            return quant.check_log(text, int(kind == 'q4_0'), capture.read_bytes(),
                                  (ROOT / 'hardware/src/vlsu/vlsu.sv').read_text())
    else:
        report, _, pins = original.checked_build(build, args.kind)
        checker = original.checker(args.kind)
    status, old_result = (s.read_json(prior / name) for name in ('status.json','result.json'))
    s.require(status.get('state') == old_result.get('state') == 'PASS' and status.get('child_pid') is None and
              old_result.get('elf_sha256') == report['elf_sha256'], 'Wrong original accepted run')
    s.verify_pins(old_result['evidence_sha256'])
    raw_old = checker((prior / 'work/run.vcs.log').read_text())
    for key, value in raw_old.items():
        s.require(key in ('state', 'independent_protocol_checked') or old_result.get(key) == value,
                  'Original raw result mismatch: ' + key)
    soc, _, extra, image = checked_soc(args.soc_build.resolve(strict=True))
    s.merge_pins(pins, extra)
    s.merge_pins(pins, old_result['evidence_sha256'])
    own = [Path(__file__), HERE / 'test_real_runtime.py', prior / 'status.json', prior / 'result.json',
        *s.script_files(), Path(sys.executable).resolve()]
    for module in tuple(sys.modules.values()):
        name = getattr(module, '__file__', None)
        if name:
            path = Path(name).resolve()
            if path.is_relative_to(ROOT) and path.is_file():
                own.append(path)
    s.merge_pins(pins, s.hashes(own))
    out = args.output.resolve()
    s.require(not out.is_relative_to(build) and not out.is_relative_to(prior), 'Independent output required')
    out.mkdir(parents=True, exist_ok=False)
    work = out / 'work'; work.mkdir()
    simv, elf = Path(soc['simv']), Path(report['elf'])
    s.atomic_json(out / 'source-pins.json', pins)
    receipt = s.digest(out / 'source-pins.json')
    owner = Execution(out)
    owner.state.update(kind=args.kind, build=str(build), prior=str(prior), simv=str(simv), elf=str(elf))
    owner.save()

    def identity():
        s.require(s.digest(out / 'source-pins.json') == receipt, 'Run receipt changed')
        s.verify_pins(pins)
        s.require(s.hashes(s.image_files(simv)) == image, 'Shared image changed')

    try:
        identity()
        owner.execute([sys.executable,'-B','-m','ara_verify.vcs_source_manifest','--output',
            simv.parent/'vcs_source_manifest.json','--check'],out/'manifest-before.log',300,'MANIFEST_BEFORE')
        owner.execute(['bash',ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',
            simv.parent,elf,'akv_v2'],out/'image-contract.log',180,'IMAGE_CONTRACT')
        log, trace = work/'run.vcs.log', work/'vector_trace.csv'
        owner.execute([simv,'-no_save','-l',log,'+PRELOAD='+str(elf),'+TESTCASE=shared_real_'+args.kind,
            '+NO_FSDB','+NO_INSTR_TRACE','+AKV_PERF','+AKV_SUMMARY','+VECTOR_TRACE='+str(trace),
            '+ARA_CONTRACT_TRACE_LIMIT=2000000','+ARA_UVM_TRACE_LIMIT=2000000'],
            work/'console.log',10800,'RUNNING')
        parsed = checker(log.read_text())
        matched = compare_outputs(raw_old, parsed)
        owner.execute([sys.executable,'-B','-m','ara_verify.uvm_dut','--require-events','--require-backend',
            '--require-axi','--require-axi-write','--vector-trace',trace,'--log',log,'--simv',simv,'--elf',elf,
            '--output',work/'uvm_result.json'],work/'checker.log',600,'CHECKING')
        s.check_result(work/'uvm_result.json',report['elf_sha256'],image)
        protocol = s.read_json(work/'uvm_result.json')
        s.require(protocol['log_sha256']==s.digest(log) and protocol['vector_trace_sha256']==s.digest(trace),
                  'Independent protocol inputs differ')
        owner.execute([sys.executable,'-B','-m','ara_verify.vcs_source_manifest','--output',
            simv.parent/'vcs_source_manifest.json','--check'],out/'manifest-after.log',300,'MANIFEST_AFTER')
        identity()
        parsed.update(state='PASS',kind=args.kind,matched_baseline=matched,post_pins_match=True,
            independent_protocol_checked=True,elf_sha256=report['elf_sha256'],source_pins_sha256=receipt,
            production_promoted=False,model_execution=False,
            evidence_sha256=s.hashes([log,trace,work/'uvm_result.json',out/'source-pins.json',
                out/'manifest-before.log',out/'manifest-after.log',out/'image-contract.log']))
        s.atomic_json(out/'result.json',parsed)
        owner.state['state']='PASS'
    except BaseException as exc:
        state='TIMEOUT' if isinstance(exc,subprocess.TimeoutExpired) else 'FAIL'
        owner.state.update(state=state,error=repr(exc))
        s.atomic_json(out/'result.json',dict(state=state,error=repr(exc)))
        raise
    finally:
        owner.state.update(child_pid=None,finished=datetime.now(timezone.utc).isoformat())
        owner.save()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kind',choices=KINDS,required=True)
    for name in ('soc-build','build','prior','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    def interrupted(sig,_frame):
        raise InterruptedError(f'Signal {sig}')
    signal.signal(signal.SIGTERM,interrupted); signal.signal(signal.SIGINT,interrupted)
    run(args)
