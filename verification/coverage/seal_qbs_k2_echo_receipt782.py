"""Read-only closure of successful core gates and exclusive echo-guard sidecar."""
import argparse
import json
from pathlib import Path

import collect_qbs_k2_row_pending782_echo as echo

life,require=echo.old.life,echo.old.require
CORE=life.OUT/'qbs-k2-row-pending-qualified782-echo-parent-20261008-01/qualification.json'
CORE_SHA='376472de5f4ad629a48c64d5d4f88f5fa3cbf36af2a231db2713d027741e0b2e'
ECHO_SHA='fa220d870614b4f3a602792a11f9e3574aed7f17c141ab6ca07d42b1b4da4847'
TEST_SHA='e077381a78fcdc7df50613d83f06cb9c29d944c33af19f0595a02f54fcb30f71'


def record():
    core=life.read_bound(CORE,CORE_SHA)
    require(core['status']=='FUNCTIONAL_NATIVE_QUALIFIED_CYCLE_PROFILE_REVIEW_REQUIRED_NOT_ADMITTED' and
        core['coverage_admitted'] is False and core['baseline']==782 and
        core['baseline_seal']==echo.old.runner.BASE_SHA,'Exact core qualification')
    runtime_path=CORE.with_name('runtime-audit.json')
    runtime_sha=core['output_pins'][str(runtime_path)]
    runtime=life.read_bound(runtime_path,runtime_sha)
    echo.old.runner.old.exact(runtime,dict(status='M4_K2_FULL_NATIVE_VRF_CSR_SOURCE_LIFECYCLE_PASS_NOT_FULL_ISA',
        custom_write_bytes=512,custom_active_bytes=128,custom_zero_tail_bytes=384,full_vrf_bytes=4096,
        initial_vrf_bytes=4096,csr_values=12,source_guard_bytes=4032,checks=6,
        full_scalar_isa_verified=False,spike_custom_isa_pass=False,coverage_admitted=False),'Core runtime')
    ep=Path(echo.__file__).resolve();tp=ep.with_name('test_qbs_k2_row_pending782_echo.py')
    require(life.digest(ep)==ECHO_SHA and life.digest(tp)==TEST_SHA and
        life.digest(Path(echo.old.__file__))==echo.OLD_SHA,'Frozen exact guard sources')
    require(echo.PATTERN==r'^\s*(?:QBS_PENDING_PROBE_REJECT\b|UCLI_ERROR\b|Error-)','Exact diagnostic grammar')
    run=Path(core['focused_vpd']).parent
    console=run/'console.log'
    require(str(console) in core['input_pins'],'Unbound completed console')
    text=console.read_text()
    lines=text.splitlines()
    require(lines.count('QBS_PENDING_PROBE_READY')==1 and not echo.actual_error(text),'Actual diagnostic/READY gate')
    script=echo.old.runner.PROBE.read_text()
    # Forty-two native-object emissions are execution evidence, not source echo.
    actual=[s for s in lines if s.startswith('QBS_PENDING_OBJECT ')]
    require(len(actual)==len(set(actual))==42 and
        'puts "QBS_PENDING_OBJECT $object"' in script,'Complete actual object inventory')
    pins=life.merge_pins(core['input_pins'],core['output_pins'])
    pins=life.merge_pins(pins,{str(CORE):CORE_SHA,str(ep):ECHO_SHA,str(tp):TEST_SHA,
        str(Path(__file__).resolve()):life.digest(Path(__file__)),
        str(Path(__file__).with_name('test_seal_qbs_k2_echo_receipt782.py').resolve()):
        life.digest(Path(__file__).with_name('test_seal_qbs_k2_echo_receipt782.py'))})
    life.check(pins)
    return dict(status='CORE_FUNCTIONAL_QUALIFICATION_AND_ANCHORED_ECHO_GUARD_VERIFIED_NOT_ADMITTED',
        core_qualification=str(CORE),core_qualification_sha256=CORE_SHA,runtime_sha256=runtime_sha,
        input_pins=pins,guard=dict(pattern=echo.PATTERN,flags='MULTILINE',actual_error=False,ready=1,actual_objects=42),
        original_collector_sha256=echo.OLD_SHA,publication_failure='Original echo attempted exclusive save of existing qualification; successful core kept unchanged',
        changes_to_core=False,cycle_witness_verified=False,coverage_admitted=False,
        full_scalar_isa_verified=False,custom_spike_pass=False)


def publish(path,value):
    require(path.parent==life.OUT and not path.exists(),'Fresh exclusive receipt required')
    life.save(path,value)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    path=a.output.resolve();publish(path,record())
    print(json.dumps(dict(receipt=str(path),seal=life.digest(path))),flush=True)
