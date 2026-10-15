#!/usr/bin/env python3
"""Preserve prepare02; recover its completed reference without another execution."""
import argparse
import difflib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OLD = HERE.parent / 'vi0_missing2_prefix112_prepare02'
sys.path.insert(0, str(HERE.parent))


def load(path):
    return json.loads(path.read_text())


def main(kind):
    text = (OLD / 'frozen_prepare.py').read_text()
    old = "commit_parses=1, original_stopped_tuple=None))"
    new = "commit_parses=1))"
    assert text.count(old) == 1
    fixed = text.replace(old, new)
    generated = HERE / 'frozen_prepare.py'
    if generated.exists():
        assert generated.read_text() == fixed
    else:
        generated.write_text(fixed)
        (HERE / 'report_correction.diff').write_text(''.join(difflib.unified_diff(
            text.splitlines(True), fixed.splitlines(True))))
    ns = {'__file__': str(generated), '__name__': 'owned_report_successor'}
    exec(compile(fixed, str(generated), 'exec'), ns)
    sha, save, require = ns['sha'], ns['save'], ns['require']
    if kind == 'e16_m8':
        ns['prepare'](kind)
        return
    out = OLD / kind
    require(load(out / 'STOPPED.json')['error'] ==
            "TypeError(\"dict() got multiple values for keyword argument 'original_stopped_tuple'\")",
            'Exact report serialization failure required')
    dest = HERE / kind
    dest.mkdir()
    pins = {str(p): sha(p) for p in out.rglob('*') if p.is_file()}
    save(dest / 'preserved_input_pins.json', pins)
    execution = load(out / 'reference/execution.json')
    require(type(execution['returncode']) is int and execution['returncode'] == 0,
            'Durable original Spike child returncode')
    sys.path.insert(0, str(out))
    spec = importlib.util.spec_from_file_location('owned_e8_recovered_reference', out / 'reference_check.py')
    ref = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ref)
    # Build receipts contain exact ELF paths; no build/reference rerun is permitted here.
    soc_elf = next((out / 'soc01').rglob('*.elf'))
    spike_elf = next((out / 'spike01').rglob('*.elf'))
    gold = load(out / 'model.json')
    measured = ref.audit_trace(out / 'reference/commits.log', spike_elf, gold)
    save(dest / 'reference.json', dict(measured, actual_execution=execution,
        commit_sha256=sha(out / 'reference/commits.log'),
        commit_bytes=(out / 'reference/commits.log').stat().st_size,
        offline_recovery_parses=1, prior_successful_parse_result_not_durable=True,
        new_Spike_executions=0))
    require(all(sha(p) == digest for p, digest in pins.items()), 'Preserved artifacts changed')
    save(dest / 'READY.json', dict(status='ACCEPTED_SOURCE_REFERENCE_ONLY_NOT_DUT',
        source_label='rvv_permute_restart_e8_m4_ops2', runtime_id='gather_vi0_e8_m4_prefix112',
        sew=8, lmul='m4', vlenb=128, capacity=512, calls=112, predecessors=111,
        results=57344, guards=224, helpers=1456, setup_values_per_call=2178,
        physical_predicate_bytes=128, setup_bytes_per_call=2690,
        endpoint=[0, 2, 0, 6, 3, 3],
        soc_elf=dict(path=str(soc_elf), sha256=sha(soc_elf)),
        spike_elf=dict(path=str(spike_elf), sha256=sha(spike_elf)),
        actual_firmware_retired=measured['firmware_retired_to_htif_store'],
        actual_reference_elapsed_s=execution['elapsed_s'], actual_reference_returncode=0,
        reference_sha256=sha(dest / 'reference.json'), host_sha256=sha(out / 'host/host.json'),
        original_binary_proof_sha256=sha(out / 'original_binary_proof.json'),
        source_proof_sha256=sha(out / 'source_elf_proof.json'), original_artifact_root=str(out),
        historical_stall_closed=False, full2688_accepted=False, Linux_execution=False,
        new_DUT_runs=0, pins=dict(pins, **{str(p): sha(p) for p in dest.rglob('*') if p.is_file()},
            **{str(Path(__file__)): sha(Path(__file__)), str(generated): sha(generated),
               str(HERE / 'report_correction.diff'): sha(HERE / 'report_correction.diff')})))
    print('e8_m4 RECOVERED_REFERENCE_PASS', measured['firmware_retired_to_htif_store'], flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case', choices=['e8_m4', 'e16_m8'])
    main(parser.parse_args().case)
