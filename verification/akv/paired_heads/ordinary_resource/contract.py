"""Same frozen Attention ELF across old and unified-resource SoC images."""
import argparse
from pathlib import Path
import sys
from historical_sources import HistoricalSources

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE.parent))
import threeway_run as original
sys.path.insert(0, str(HERE.parent / 'contexts'))
import run_context as context
sys.path.insert(0, str(ROOT / 'verification/akv/shared_reader_integration'))
from run_handoff import checked_soc

s = original
Execution = context.Execution
STORAGE = 'shared_reader_unified_q2_kv32_v1'
ACCEPTANCE = 'ORDINARY_RVV_RESOURCE_SAME_ELF_PASS'
DEFAULT_BUILD = ROOT / 'verification/out/akv-paired-heads-threeway-build-20261023-01'
DEFAULT_BASELINE = ROOT / 'verification/out/akv-paired-heads-threeway-20261024-01'
DEFAULT_SOC = ROOT / 'verification/out/shared-storage-integration-soc-build-20261025-01'
IMAGE_GATE = ROOT / 'verification/out/qbacc-soc-accept-20261023-02'
EVIDENCE_NAMES = ('run.vcs.log', 'vector_trace.csv', 'commit_trace.csv', 'uvm_result.json')


def consumed_evidence(directory, result):
    required = [directory / 'work' / n for n in EVIDENCE_NAMES]
    required.append(directory / 'source-pins.json')
    pins = result['evidence_sha256']
    s.require(all(pins.get(str(p)) == s.digest(p) for p in required),
              'Missing or mismatched consumed evidence pin')
    s.verify_pins(pins)
    return pins


def raw(directory):
    text = (directory / 'work/run.vcs.log').read_text()
    parsed = original.check_log(text)
    records = [s.numeric_fields(line[len('[AKV_PERF] '):], s.PERF_FIELDS)
               for line in text.splitlines() if line.startswith('[AKV_PERF] ')]
    s.require(len(records) == 3864, 'Incomplete raw hardware records')
    return parsed, records


def protocol(directory, elf_hash, image):
    path = directory / 'work/uvm_result.json'
    s.check_result(path, elf_hash, image)
    proof = s.read_json(path)
    s.require(proof['log_sha256'] == s.digest(directory / 'work/run.vcs.log') and
              proof['vector_trace_sha256'] == s.digest(directory / 'work/vector_trace.csv'),
              'Protocol input identity mismatch')
    # Require all four original checker switches, not merely an empty PASS.
    s.require(proof.get('contract_event_count', 0) > 0 and
              proof.get('uvm_backend_event_count', 0) > 0 and
              proof.get('axi_read_counts', {}).get('completed', 0) > 0 and
              proof.get('axi_write_counts', {}).get('matched', 0) > 0,
              'Missing independent event/backend/AXI read/write proof')


def checked_baseline(directory, build, historical=None):
    build_check, prior_check = (original.checked_build, context.checked_prerequisite) if historical is None else historical.validators(original, context)
    report, build_pins, _ = build_check(build)
    image, accepted = s.checked_image(IMAGE_GATE, Path(report['simv']))
    # This validator deliberately supports the archived worker's older schema.
    pins, _ = prior_check(directory, build, image)
    result = s.read_json(directory / 'result.json')
    s.merge_pins(pins, consumed_evidence(directory, result))
    s.merge_pins(pins, build_pins)
    s.merge_pins(pins, accepted)
    parsed, records = raw(directory)
    s.require(all(result.get(k) == v for k, v in parsed.items()), 'Old receipt/raw mismatch')
    protocol(directory, report['elf_sha256'], image)
    if historical is not None:
        pins = historical.translate(pins)
    s.verify_pins(pins)
    return report, parsed, records, pins


def unified_image(directory):
    soc, snapshot, pins, image = checked_soc(directory)
    s.require(snapshot.get('storage_variant') == STORAGE, 'Need unified Q2/KV32 snapshot, not shared-only')
    return soc, pins, image


def compare(old, new, old_records, new_records):
    for parsed in (old, new):
        s.require(parsed.get('state') == 'PASS' and len(parsed['trials']) == 6 and
                  [(t['trial'], t['variant']) for t in parsed['trials']] ==
                  [(i, v.value) for i, v in enumerate(original.ORDER)], 'Incomplete or reordered trials')
    s.require(len(old_records) == len(new_records) == 3864 and old_records == new_records,
              'Per-command hardware records differ')
    s.require(old['raw_hardware_summary'] == new['raw_hardware_summary'], 'Hardware summary differs')
    calls = []
    for before, after in zip(old['trials'], new['trials']):
        s.require({k: v for k, v in before.items() if k != 'cycles'} ==
                  {k: v for k, v in after.items() if k != 'cycles'},
                  'Cross-image same-variant output/CSR/work mismatch')
        s.require(type(before['cycles']) is type(after['cycles']) is int and
                  before['cycles'] > 0 and after['cycles'] > 0, 'Invalid complete-call cycles')
        calls.append(dict(trial=before['trial'], variant=before['variant'],
                          old_cycles=before['cycles'], unified_cycles=after['cycles'],
                          delta_cycles=after['cycles'] - before['cycles']))
    no_regression = all(c['delta_cycles'] <= 0 for c in calls)
    return dict(state='PASS' if no_regression else 'FAIL', functional_same_work_pass=True,
                no_per_call_regression=no_regression, calls=calls,
                hardware_records_equal=3864,
                acceptance=ACCEPTANCE if no_regression else 'COMPLETE_CALL_REGRESSION',
                numerical='Original all512 finite/tolerance and on-chip exact-repeat/native-pair checks; '
                          'cross-image checksum/FCSR/VCSR per corresponding trial, not a full output dump',
                scope='Real KV128 derived Qheads0,1,6,7; ordinary RVV and original experimental native paths; '
                      'same ELF complete-call resource regression, not full-model performance',
                model_execution=False, production_promoted=False, ppa_measured=False)


def own_pins():
    files = [*HERE.glob('*.py'), HERE / 'README.md', *s.script_files(),
             ROOT / 'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',
             Path(sys.executable).resolve()]
    for module in tuple(sys.modules.values()):
        name = getattr(module, '__file__', None)
        if name:
            path = Path(name).resolve()
            if path.is_relative_to(ROOT) and path.is_file():
                files.append(path)
    return s.hashes(files)


def checked_candidate(directory, build, baseline, soc_build):
    historical = HistoricalSources(ROOT, directory / 'historical-source', s)
    report, old, old_records, pins = checked_baseline(baseline, build, historical)
    soc, soc_pins, image = unified_image(soc_build)
    result, status = (s.read_json(directory / name) for name in ('result.json', 'status.json'))
    s.require(result.get('state') == status.get('state') == 'PASS' and
              'child_pid' in status and status['child_pid'] is None and
              status.get('running_exit_code') == 0 and result.get('simulator_exit_code') == 0 and
              result.get('post_pins_match') is True and result.get('independent_protocol_checked') is True,
              'Candidate not terminal checked PASS')
    s.require(status.get('elf') == report['elf'] and status.get('simv') == soc['simv'] and
              result.get('elf_sha256') == report['elf_sha256'] and
              result.get('snapshot_sha256') == soc['snapshot_sha256'] and
              result.get('baseline') == str(baseline) and result.get('build') == str(build) and
              result.get('soc_build') == str(soc_build), 'Candidate source/image/ELF association')
    source = s.read_json(directory / 'source-pins.json')
    s.require(result.get('source_pins_sha256') == s.digest(directory / 'source-pins.json'), 'Receipt drift')
    s.merge_pins(pins, soc_pins)
    s.merge_pins(pins, own_pins())
    s.require(all(source.get(p) == h for p, h in pins.items()), 'Missing consumed source/build/worker pins')
    s.verify_pins(source)
    s.merge_pins(pins, source)
    s.merge_pins(pins, consumed_evidence(directory, result))
    protocol(directory, report['elf_sha256'], image)
    new, new_records = raw(directory)
    s.require(result.get('raw_replay') == new, 'Candidate raw replay drift')
    comparison = compare(old, new, old_records, new_records)
    s.require(comparison['state'] == 'PASS' and result.get('comparison') == comparison, 'Comparison mismatch')
    s.merge_pins(pins, s.hashes([directory / 'status.json', directory / 'result.json']))
    return comparison, pins


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Offline terminal same-ELF raw/protocol receipt audit; no simulation')
    parser.add_argument('--build', type=Path, default=DEFAULT_BUILD)
    parser.add_argument('--baseline', type=Path, default=DEFAULT_BASELINE)
    parser.add_argument('--soc-build', type=Path, default=DEFAULT_SOC)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    comparison, pins = checked_candidate(*(p.resolve(strict=True) for p in
        (args.candidate, args.build, args.baseline, args.soc_build)))
    args.output.mkdir(parents=True, exist_ok=False)
    s.atomic_json(args.output / 'source-pins.json', pins)
    s.atomic_json(args.output / 'result.json', dict(comparison, source_pins_sha256=
                  s.digest(args.output / 'source-pins.json')))
