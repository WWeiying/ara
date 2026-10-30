#!/usr/bin/env python3
"""One-run audit of a known prose-only drift; never overwrite the failed worker."""
import argparse
import hashlib
from pathlib import Path
import shlex
import subprocess

from native_runtime_check import CASES,check_log
import attention_run as s

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RUN = ROOT/'verification/out/akv-native-pair-runtime-20261024-01'
BUILD = ROOT/'verification/out/akv-native-pair-runtime-build-20261024-03'
DOCUMENT = ROOT/'hardware/docs/akv_pair_runtime_integration.md'
OLD_DOCUMENT = '52fda9198077da106a13bf1d55cfa8f5eab15320e5ea6110ee3ec831fff1b04c'


def classify_drift(pins,current):
    s.require(pins.get(str(DOCUMENT)) == OLD_DOCUMENT,'Wrong document/version exception')
    drift = {p for p,h in pins.items() if current.get(p) != h}
    s.require(drift == {str(DOCUMENT)},'Not exactly the known documentation-only drift')
    return dict(path=str(DOCUMENT),expected=OLD_DOCUMENT,current=current[str(DOCUMENT)])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    a = p.parse_args()
    out = a.output.resolve()
    s.require(not out.is_relative_to(RUN) and not out.is_relative_to(BUILD),'Independent audit output required')
    out.mkdir(parents=True,exist_ok=False)
    original = s.hashes([RUN/'status.json',RUN/'result.json'])
    try:
        status,result = s.read_json(RUN/'status.json'),s.read_json(RUN/'result.json')
        s.require(status.get('state') == result.get('state') == 'FAIL' and status['child_pid'] is None and
                  status['build'] == str(BUILD) and status['error'] == "ValueError('Source/image/evidence pin drift')" and
                  all(status.get(k) == 0 for k in ('running_exit_code','checking_exit_code',
                      'manifest-before_exit_code','manifest-after_exit_code','image_contract_exit_code')),
                  'Wrong failure or unfinished original worker')
        build = s.read_json(BUILD/'build.json')
        s.require(build.get('state') == 'BUILT_NOT_EXECUTED' and build.get('execution') == 'NOT_RUN' and
                  build.get('cases') == CASES and build.get('runs') == 12 and
                  build.get('expected_commands') == 3680 and build.get('post_pins_match') is True and
                  build.get('canonical_modified') is False,'Wrong original build')
        s.require(s.digest(BUILD/'source-pins.json') == build['source_pins_sha256'],'Build pin receipt drift')
        pins = s.read_json(RUN/'source-pins.json')
        build_pins = s.read_json(BUILD/'source-pins.json')
        s.merge_pins(build_pins,build['artifact_sha256'])
        s.require(all(pins.get(path) == sha for path,sha in build_pins.items()),'Missing original build pin')
        s.merge_pins(pins,build_pins)
        s.require(pins.get(build['elf']) == build['elf_sha256'] == s.digest(Path(build['elf'])),'ELF drift')
        drift = classify_drift(pins,s.hashes(map(Path,pins)))
        old_doc = subprocess.check_output(['git','show','3dcb283e:hardware/docs/akv_pair_runtime_integration.md'],cwd=ROOT)
        s.require(hashlib.sha256(old_doc).hexdigest() == OLD_DOCUMENT,'Original document not recoverable')
        (out/'document-at-seal.md').write_bytes(old_doc)
        (out/'document-after-edit.md').write_bytes(DOCUMENT.read_bytes())
        # Compiler-generated dependencies distinguish documentation from code.
        dependencies = sorted(BUILD.glob('deps-*.log'))+[BUILD/'features-deps.log']
        s.require(len(dependencies) == 14,'Incomplete compiler dependency evidence')
        for path in dependencies:
            s.require(pins.get(str(path)) == s.digest(path),'Dependency evidence not pinned')
            deps = shlex.split(path.read_text().replace('\\\n',' ').split(':',1)[1])
            s.require(str(DOCUMENT) not in deps and all(not x.endswith('.md') for x in deps),
                      'Document was a compiler input')
        image,accepted = s.checked_image(ROOT/'verification/out/qbacc-soc-accept-20261023-02',Path(build['simv']))
        s.require(image == build['accepted_image_pins'],'Image identity mismatch')
        s.verify_pins(accepted)
        log,trace,uvm_path = RUN/'work/run.vcs.log',RUN/'work/vector_trace.csv',RUN/'work/uvm_result.json'
        parsed = check_log(log.read_text())
        s.check_result(uvm_path,build['elf_sha256'],image)
        uvm = s.read_json(uvm_path)
        s.require(uvm['log_sha256'] == s.digest(log) and uvm['vector_trace_sha256'] == s.digest(trace),
                  'Independent UVM evidence identity')
        s.require(s.digest(RUN/'manifest-before.log') == s.digest(RUN/'manifest-after.log'),
                  'Before/after RTL manifest evidence differs')
        code_pins = {p:h for p,h in pins.items() if p != str(DOCUMENT)}
        s.merge_pins(code_pins,s.hashes([Path(__file__),HERE/'test_native_document_drift.py',
            RUN/'source-pins.json',BUILD/'build.json',BUILD/'source-pins.json',log,trace,uvm_path,
            RUN/'manifest-before.log',RUN/'manifest-after.log',RUN/'image-contract.log']))
        s.verify_pins(code_pins)
        s.require(s.hashes(map(Path,original)) == original,'Original failure report changed')
        s.atomic_json(out/'execution-pins.json',code_pins)
        parsed.update(state='FUNCTIONAL_ACCEPTED_DOCUMENT_ONLY_DRIFT',
            original_worker_state='FAIL',original_reports_unchanged=True,
            original_failure=original,document_drift=drift,compiler_dependency_files_checked=14,
            execution_inputs_match=True,post_pins_match=False,simulator_exit_code=0,
            elf_sha256=build['elf_sha256'],execution_pins_sha256=s.digest(out/'execution-pins.json'),
            evidence_sha256=s.hashes([out/'document-at-seal.md',out/'document-after-edit.md',log,trace,uvm_path]),
            production_deployment_accepted=False,whole_model_claim=False,
            scope='One explicit non-executable document drift only; raw candidate OFF/ON/OFF functional evidence, not clean original-worker PASS or performance')
        s.atomic_json(out/'result.json',parsed)
        print('FUNCTIONAL_ACCEPTED_DOCUMENT_ONLY_DRIFT original_worker=FAIL')
    except BaseException as exc:
        s.atomic_json(out/'result.json',dict(state='FAIL',error=repr(exc)))
        raise


if __name__ == '__main__':
    main()
