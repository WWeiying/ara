#!/usr/bin/env python3
"""Accept only the measured, integrated unchanged-RTL optimization with current evidence."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


decision = load(HERE/'decision.py', 'final_pair_decision')
owner = decision.owner
require, sha, canonical = decision.require, decision.sha, decision.canonical
OUT = owner.OUT
SDK = 'b7c9e6c3c1f8c5e469c130f46ec5bbfaf37a55d1'
LLAMA = '03959acc0f649f9071668d5b72888284e4676d2b'
DECISION = OUT/'akv_pair_initial_decision_20261107_01.json'
DECISION_SHA = 'c015d4382eb6af6edd7e4585651c5717e8655922ced455aa122d8eff0d7858e5'
DOC = owner.ROOT/'hardware/docs/AKV_PAIR_FULL_CALL_OPTIMIZATION_20261107.md'


def inventory(directory):
    directory = Path(directory).resolve(strict=True)
    report = json.loads((directory/'result.json').read_text())
    require(report['state'] == 'PASS' and report['post_pins_match'] is True and
            report['independent_protocol_checked'] is True, 'No checked PASS: '+str(directory))
    pinfile = directory/'source-pins.json'
    require(sha(pinfile) == report['source_pins_sha256'], 'Changed source inventory')
    pins = json.loads(pinfile.read_text())
    require(pins and report['artifacts'], 'Empty evidence inventory')
    owner.verify(pins)
    owner.verify(report['artifacts'])
    return report


def current_run(name, checker_directory, kind):
    directory = OUT/name
    report = inventory(directory)
    require(report['kind'] == kind and report['performance_measured'] is (kind != 'boundary') and
            report['hardware_changed'] is False and report['whole_model'] is False, 'Wrong acceptance scope')
    builddir = Path(report['build'])
    _, software_pins = owner.checked_software(builddir)
    owner.verify(software_pins)
    checker = load(HERE/checker_directory/'check.py', 'final_'+checker_directory)
    fresh = checker.check_run(directory/'work/run.vcs.log', builddir)
    vectors = checker.check_vector_workcounts(directory/'work/vector_trace.csv', builddir)
    require(canonical(fresh) == canonical(report['measured']) and
            canonical(vectors) == canonical(report['vector_command_work']), 'Raw numerical/work evidence differs')
    proof = json.loads((directory/'work/uvm_result.json').read_text())
    require(proof['status'] == 'PASS' and proof['issues'] == [] and
            proof['elf_sha256'] == report['software_sha256'] and
            proof['log_sha256'] == sha(directory/'work/run.vcs.log') and
            proof['vector_trace_sha256'] == sha(directory/'work/vector_trace.csv'), 'Independent protocol mismatch')
    manifest = json.loads((builddir/'build.json').read_text())
    require(manifest['sdk_head'] == SDK, 'Not the integrated SDK')
    return report


def accept(output):
    output = Path(output).resolve()
    require(output.parent == OUT.resolve() and not output.exists(), 'Fresh acceptance directory required')
    output.mkdir()
    result = dict(state='FAIL', goal_met=False, hardware_changed=False, whole_model_speedup_measured=False,
                  ppa_measured=False, fpga_validated=False)
    try:
        require(DOC.is_file() and sha(DECISION) == DECISION_SHA, 'Final report or frozen promotion evidence missing')
        initial = json.loads(DECISION.read_text())
        require(initial['state'] == 'EVIDENCE_RECHECKED' and
                initial['candidate_eligible_for_call_local_integration'] is True and
                initial['deployment_approved'] is False and
                initial['decision_source_sha256'] == sha(HERE/'decision.py'), 'No stable initial performance gate')
        for path, digest in initial['evidence'].items():
            require(sha(path) == digest, 'Initial raw audit/worker receipt changed')
            inventory(Path(path).parent)
        for name in ('boundary', 'smollm'):
            old = json.loads((OUT/f'akv_pair_{name}_vcs_20261107_01/result.json').read_text())
            require(old['state'] == 'FAIL', 'Original rejected worker was relabeled')
        primary = current_run('akv_pair_integration_vcs_20261107_01', 'integration', 'qwen3_abba')
        boundary = current_run('akv_pair_integration_boundary_vcs_20261107_01', 'integration_boundary', 'boundary')
        require(primary['configuration'] == boundary['configuration'] and
                primary['image_sha256'] == boundary['image_sha256'], 'Image/configuration mismatch')
        effect = decision.effect(primary['measured']['measured_total_cycles'])
        require(effect['cycle_reduction'] >= .05 and effect['improvement_exceeds_arm_spread'] and
                effect['all_paired_samples_faster'], 'Integrated benefit not reproducible')
        require(boundary['measured']['state'] == 'PASS' and
                boundary['vector_command_work']['native_commands'] == 3968,
                'New-API boundary/fallback work missing')
        ggml_dir = OUT/'akv_pair_ggml_build_20261107_02'
        ggml = json.loads((ggml_dir/'result.json').read_text())
        require(ggml['state'] == 'GGML_AUTO_PAIR_COMPILED_NOT_EXECUTED' and ggml['sdk_commit'] == SDK and
                ggml['llama_commit'] == LLAMA and ggml['adapter_references_canonical_auto_api'] is True and
                ggml['dirty_sources_excluded'] is True, 'Actual committed GGML integration not compiled')
        require(sha(ggml_dir/'source-pins.json') == ggml['source_pins_sha256'], 'GGML source inventory drift')
        owner.verify(json.loads((ggml_dir/'source-pins.json').read_text()))
        owner.verify(ggml['artifacts'])
        refs = {}
        for name in ('chain_q6_integrity_vcs_20261107_01', 'chain_profile_runs_20261107_01/smoke'):
            ref = inventory(OUT/name)
            require(ref['image_sha256'] == primary['image_sha256'], 'Unchanged-path regression uses another image')
            refs[name] = dict(receipt_sha256=sha(OUT/name/'result.json'),
                              note='Revalidated immutable representative evidence; unchanged implementation, not a new run')
        unchanged = subprocess.check_output(['git', '-C', str(owner.ROOT), 'diff', '--name-only',
            '785084122af984c1dd3fd6318efaf70cdcb017e8', 'HEAD', '--',
            'hardware/src', 'hardware/include', 'software/qbs'], text=True)
        require(not unchanged.strip(), 'RTL or QBS changed during software-only optimization')
        require(not subprocess.check_output(['git', '-C', str(owner.ROOT), 'diff', '--name-only', '--',
                'hardware/src', 'hardware/include'], text=True).strip(), 'Working RTL differs')
        sdk_tree = subprocess.check_output(['git', '-C', str(owner.ROOT), 'rev-parse', SDK+':software/akv'], text=True)
        head_tree = subprocess.check_output(['git', '-C', str(owner.ROOT), 'rev-parse', 'HEAD:software/akv'], text=True)
        require(sdk_tree == head_tree, 'Committed production SDK differs from tested archive')
        evidence = [DECISION, DOC, ggml_dir/'result.json', ggml_dir/'source-pins.json',
                    OUT/'akv_pair_integration_vcs_20261107_01/result.json',
                    OUT/'akv_pair_integration_boundary_vcs_20261107_01/result.json',
                    Path(__file__), HERE/'decision.py']
        owner.save(output/'source-pins.json', {str(p): sha(p) for p in evidence})
        result.update(state='PASS', goal_met=True, initial_performance=initial,
                      integrated_full_call_effect=effect, sdk_commit=SDK, llama_commit=LLAMA,
                      current_rvv_qbs_reference_evidence=refs, source_pins_sha256=sha(output/'source-pins.json'),
                      scope='Current-image SDK full-call performance plus new-API boundary/fallback and real GGML compilation; not model/board/PPA acceptance')
    except BaseException as exc:
        result.update(error=repr(exc))
        raise
    finally:
        owner.save(output/'result.json', result)
    print(json.dumps(dict(state=result['state'], effect=effect, output=str(output)), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output', type=Path, required=True)
    accept(parser.parse_args().output)
