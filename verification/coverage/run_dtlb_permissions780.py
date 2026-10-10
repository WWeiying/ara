"""Prepare-only by default; frozen PPN host lifecycle, scalar fixture, formal780."""
import argparse
from pathlib import Path
import sys
from types import FunctionType, SimpleNamespace

import run_dtlb_ppn_swap1200 as host
import preflight_dtlb_permissions_scalar779 as software

life, require = host.life, host.require
PRE = life.OUT/'dtlb-permissions-preflight779-agent-20261008-04/preflight.json'
PRE_SHA = '11b9c4c2c67477cc3aeff130ead4ba57b3fd5cb93b43b906b0a0f67b80fd0800'
BASE = software.audit.GAIN
BASE_SHA = software.audit.GAIN_SEAL
CASE = 'dtlb_permissions_matrix'
PROBE = Path(__file__).with_name('dtlb_permissions780_probe.tcl').resolve()
SCHEMA = 'DTLB_PERMISSIONS780_FROZEN1200_V1'

# Private bindings: preserve the tested owning-service/PID/budget implementation byte-for-byte.
namespace = dict(vars(host), PRE=PRE, PRE_SHA=PRE_SHA, CASE=CASE, PROBE=PROBE,
                 SCHEMA=SCHEMA, pre=SimpleNamespace(BASE_SHA=BASE_SHA))
for name in ('command','validate_record','check','process_identity','run'):
    original = getattr(host,name)
    function = FunctionType(original.__code__,namespace,name,original.__defaults__,original.__closure__)
    namespace[name] = globals()[name] = function


def prepare(output,service):
    import collect_dtlb_ppn_swap1200 as native
    import collect_dtlb_permissions780 as collector
    q=life.read_bound(PRE,PRE_SHA)
    require(q['status']=='SPIKE_SOURCE_PTE_CSR_TRAP_GOLD_PASS_NOT_DUT' and
            q['coverage_admitted'] is False and q['EDA_launched'] is False and
            q['ppn780_union_bound'] is True and q['counts']['software_checks']==8378 and
            q['counts']['page_fault_loads']==3 and q['counts']['page_fault_stores']==2 and
            q['scalar_isa_evidence']['software_march']=='rv64gc_zfh', 'Final04 scalar preflight')
    commits=software.parse_spike_commits(PRE.parent/'spike.trace')
    require(software.validate(commits,q['symbols'])==q['counts'], 'Strict reference replay')
    require(output.parent==life.OUT and output.resolve()==output and not output.exists() and
            not output.with_name(output.name+'.prepared.json').exists(), 'Fresh independent run')
    image=life.read_bound(life.PLAN,life.PLAN_SEAL)
    require(image['simv']==str(life.IMAGE) and len(image['image'])==66, 'Exact frozen66 image')
    base=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    require(base['coverage_admitted'] is True and base['baseline']==str(software.p.BASE) and
            base['baseline_seal']==software.p.BASE_SHA, 'Formal780 genealogy')
    pins=life.merge_pins(q['input_pins'],q['output_pins'])
    pins=life.merge_pins(pins,image['image'])
    pins=life.merge_pins(pins,{str(PRE):PRE_SHA,str(life.PLAN):life.PLAN_SEAL,
                             str(BASE/'admission-manifest.json'):BASE_SHA})
    for name in ('combined-inputs.txt','combined-bits.json','dtlb-toggle-gain.json'):
        path=BASE/name
        pins=life.merge_pins(pins,{str(path):base['output_pins'][str(path)]})
    proof,source_pins=native.source_layout()
    pins=life.merge_pins(pins,source_pins)
    files=[PROBE,Path(__file__),Path(host.__file__),Path(collector.__file__),Path(native.__file__),
           native.CONVERTER,Path(__file__).with_name('test_run_dtlb_permissions780.py')]
    require(life.digest(native.CONVERTER)==native.CONVERTER_SHA, 'Pinned VPD converter')
    for module in tuple(sys.modules.values()):
        file=getattr(module,'__file__',None)
        if file and str(life.ROOT/'verification') in file and Path(file).is_file(): files.append(Path(file))
    for path in files: pins=life.merge_pins(pins,{str(path.resolve()):life.digest(path)})
    life.check(pins)
    record=dict(schema=SCHEMA,case=CASE,output=str(output),command=command(output),pins=pins,
                preflight=str(PRE),preflight_seal=PRE_SHA,baseline=str(BASE),baseline_seal=BASE_SHA,
                timeout_s=1200,systemd_runtime_max_s=1260,automatic_retry=False,
                coverage_admitted=False,qualification_automatic=False,service=service,
                source_layout=proof,collector=str(Path(collector.__file__).resolve()),
                budget_basis='Same full64KiB guard predecessor elapsed681.9367s;600s not justified.',
                expected_slot_updates=56,main_phase_slot_updates=48,
                primary_missing_capacity=142,extra_R_W_D_missing_capacity=96,
                expected_gain_not_measured=True)
    validate_record(record)
    path=output.with_name(output.name+'.prepared.json');life.save(path,record)
    print('PREPARED_NO_EDA',path,life.digest(path),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['prepare','check','run'])
    parser.add_argument('--output',type=Path);parser.add_argument('--input',type=Path)
    parser.add_argument('--seal');parser.add_argument('--service',default='ara-dtlb-permissions780-parent-20261008-01.service')
    args=parser.parse_args()
    if args.mode=='prepare':
        require(args.output is not None,'Output required');prepare(args.output.absolute(),args.service)
    else:
        require(args.input is not None and args.seal is not None,'Prepared input/seal required')
        if args.mode=='check': check(args.input.absolute(),args.seal);print('CHECK_PASS_NO_EDA')
        else: run(args.input.absolute(),args.seal)
