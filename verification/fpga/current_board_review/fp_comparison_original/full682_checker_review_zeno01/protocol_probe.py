"""Real frozen-M8 lifecycle schema + missing-whole-event negatives, no simulator."""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
OWNER=HERE.parent/'full682_vcs_m8_plan01'
TRACE=Path('/home/wangwy/fpga_runs/current_board_memory_candidate08/frozen/sources/verification/ara_verify/trace.py')
sys.path.insert(0,str(OWNER))
import checker as c
sp=importlib.util.spec_from_file_location('zeno_frozen_M8_trace',TRACE)
v=importlib.util.module_from_spec(sp);sp.loader.exec_module(v)
FIELDS=['cycle','event','order','port','trans_id','pc','insn','rd','rd_wdata','mem_addr','mem_rmask','mem_wmask','mem_wdata','trap']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    paths=[TRACE,OWNER/'strict.py',OWNER/'checker.py',OWNER/'model.py',OWNER/'elf.py']
    pins={str(p):sha(p) for p in paths}
    s=c.specification(c.PREP/'run01/soc.elf')
    instructions=[int(s['routines'][0][i]['insn'],16) for i in (2,3)]
    expected=dict(retired_offloads=[dict(insn=insn,backend_required=True) for insn in instructions])
    items=[]
    for i,insn in enumerate(instructions):
        for event in ('cvx_req','arch_start','uop_alloc','uop_done','cvx_resp','retire'):
            r={k:'0' for k in FIELDS};r.update(cycle=str(len(items)),event=event,order=str(i),
              port='0',trans_id=str(i),insn=f'{insn:08x}',pc=f"{s['routines'][0][i+2]['pc']:016x}")
            items.append(r)
    def check(rows,label):
        path=HERE/(label+'.csv')
        with path.open('x',newline='') as f:
            w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
        result=v.validate_trace(path)
        assert 'status' not in result and all(isinstance(x,int) for x in result.values())
        protocol=[r for r in rows if r['event']!='retire']
        return protocol,result
    protocol,generic=check(items,'positive')
    positive=c.protocol_gate(protocol,expected,generic)
    negative=[];generic_accepts=[]
    for name,rows in [
      ('all_arch_uop_dropped',[r for r in items if r['event'] not in ('arch_start','uop_alloc','uop_done')]),
      ('one_whole_backend_pair_dropped',[r for r in items if not(r['event'] in ('uop_alloc','uop_done') and r['order']=='1')])]:
        protocol,g=check(rows,name);generic_accepts.append(name)
        try:c.protocol_gate(protocol,expected,g)
        except ValueError as e:negative.append(dict(name=name,error=str(e),generic_accepted=True))
        else:raise ValueError('Composition accepted '+name)
    # Whole transport/arch/uop packet and its retire dropped: generic is self-consistent.
    protocol,g=check([r for r in items if r['order']=='0'],'whole_instruction_packet_dropped')
    generic_accepts.append('whole_instruction_packet_dropped')
    try:c.protocol_gate(protocol,expected,g)
    except ValueError as e:negative.append(dict(name='whole_instruction_packet_dropped',error=str(e),generic_accepted=True))
    else:raise ValueError('Composition accepted whole packet drop')
    # Lifecycle-valid duplicated packet with new owners/orders remains generic-valid.
    duplicate=[dict(r) for r in items]
    for r in items[:6]:
        x=dict(r,order='2',trans_id='2',cycle=str(len(duplicate)));duplicate.append(x)
    protocol,g=check(duplicate,'whole_packet_duplicated')
    try:c.protocol_gate(protocol,expected,g)
    except ValueError as e:negative.append(dict(name='whole_packet_duplicated',error=str(e),generic_accepted=True))
    else:raise ValueError('Composition accepted duplicated balanced packet')
    reordered=[]
    for i,packet in enumerate((items[6:],items[:6])):
        for r in packet:reordered.append(dict(r,order=str(i),trans_id=str(i),cycle=str(len(reordered))))
    protocol,g=check(reordered,'whole_packet_reordered')
    try:c.protocol_gate(protocol,expected,g)
    except ValueError as e:negative.append(dict(name='whole_packet_reordered',error=str(e),generic_accepted=True))
    else:raise ValueError('Composition accepted reordered balanced packets')
    assert all(sha(Path(p))==h for p,h in pins.items()),'Owner changed during microHost'
    result=dict(status='REAL_FROZEN_M8_PROTOCOL_COMPOSITION_HOST_PASS_NOT_FULL682',schema_keys=sorted(generic),
      schema_has_status=False,positive=positive,negative=negative,pins=pins,pins_pre_post_unchanged=True,
      scope='Two actual helper VLE16 encodings; protocol discrimination only, not replacement for full682 Host/reference',
      DUT_started=False)
    with (HERE/'protocol_evidence.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(result['status'],len(negative),sorted(generic))
if __name__=='__main__':main()

