"""One parent-authorized 600s frozen-image matrix run; no automatic admission."""
import argparse
from pathlib import Path
import build_tlb_asid_matrix as pre

life,require = pre.life,pre.require


def command(elf,output):
    return [str(life.IMAGE),'-l','run.vcs.log','+NO_FSDB','+ntb_random_seed=1',
            '+PRELOAD='+str(elf),'+TESTCASE=tlb_asid_vpn_rsw_matrix','+COMMIT_TOHOST=80001000',
            '+COMMIT_TRACE='+str(output/'commit_trace.csv'),'+VECTOR_TRACE='+str(output/'vector_trace.csv'),
            '-cm','line+cond+fsm+tgl+branch','-cm_dir',str(output/'code.vdb'),
            '-cm_name','tlb_asid_vpn_rsw_matrix','+ARA_UVM_TRACE_LIMIT=100000',
            '+ARA_CONTRACT_TRACE_LIMIT=100000']


def prepare(path,seal,output):
    q = life.read_bound(path,seal)
    require(q['status'] == 'SPIKE107_CHECKS_AND_INDEPENDENT_PTE_CSR_GUARDS_PASS_NOT_RTL' and
            q['software_checks'] == 107 and q['baseline'] == 768 and not q['coverage_admitted'] and
            not q['VCS_launched'] and q['prediction']['conditional_fresh_positions'] >= 300,
            'Unqualified/insufficient matrix')
    require(not output.exists(),'Fresh run required')
    image = life.read_bound(life.PLAN,life.PLAN_SEAL)
    require(image['simv'] == str(life.IMAGE) and len(image['image']) == 66,'Frozen66 image required')
    pins = life.merge_pins(q['input_pins'],image['image'])
    pins = life.merge_pins(pins,{str(path):seal,str(life.PLAN):life.PLAN_SEAL})
    for p in (Path(__file__).resolve(),Path(__file__).with_name('test_run_tlb_asid_matrix.py')):
        pins = life.merge_pins(pins,{str(p):life.digest(p)})
    elf = path.parent/'input.elf'
    require(str(elf) in pins and q['symbols']['tohost'] == 0x80001000,'Exact ELF/tohost required')
    life.check(pins)
    prepared = output.with_name(output.name+'.prepared.json')
    life.save(prepared,dict(schema='TLB_MATRIX_FROZEN_ONE_RUN_V1',case='tlb_asid_vpn_rsw_matrix',output=str(output),
        command=command(elf,output),pins=pins,timeout_s=600,preflight=str(path),preflight_seal=seal,
        coverage_admitted=False,automatic_retry=False,official_percentage=False))
    print('PREPARED '+str(prepared)+' '+life.digest(prepared),flush=True)


def run(path,seal):
    r = life.read_bound(path,seal);output = Path(r['output'])
    require(r['schema'] == 'TLB_MATRIX_FROZEN_ONE_RUN_V1' and r.get('case') == 'tlb_asid_vpn_rsw_matrix' and r['timeout_s'] == 600 and
            r['automatic_retry'] is False and r['coverage_admitted'] is False and
            not output.exists() and r['command'] == command(Path(r['preflight']).parent/'input.elf',output),
            'Exact bounded command differs')
    r = dict(r,pins=life.merge_pins(r['pins'],{str(path):seal}))
    life.run(output,r)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=['prepare','run']);p.add_argument('--input',type=Path,required=True)
    p.add_argument('--seal',required=True);p.add_argument('--output',type=Path)
    a=p.parse_args()
    if a.mode == 'prepare':
        require(a.output is not None,'Output required');prepare(a.input.absolute(),a.seal,a.output.absolute())
    else:run(a.input.absolute(),a.seal)
