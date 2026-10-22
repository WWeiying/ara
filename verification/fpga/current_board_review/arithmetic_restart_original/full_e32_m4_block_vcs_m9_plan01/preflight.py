"""Small marker/three-seed actual SoC-PC gate before the full worker Host."""
import json
import time
import checker as c
import context
from host_records import Builder

def main():
    start=time.monotonic();spec=c.specification();builder=Builder(spec)
    rows=list(builder.marker_rows())
    actual=bytes(int(r['mem_wdata'],16)&255 for r in rows if int(r['mem_wmask'],16))
    c.require(actual==c.marker().encode()+bytes([10]),'Builder UART exact marker and real newline')
    c.console_gate(actual.decode(),simulator=False)
    context.marker_decode(actual.decode().rstrip('\n'))
    s,code,h,gold=context.artifacts();q=c.lifecycle.Lifecycle(s,code,[h[f'op_{i}'][0]['pc'] for i in range(35)],gold)
    paths=[]
    for seed,ordinal in enumerate((1366,3361,5356)):
        b=Builder(spec);b.regs[3]=s['__global_pointer$'];b.regs[10]=seed
        path=context.linked()[2]['leaf_paths']['FP'][str(seed)]
        records=list(b.path(path));memory=[r for r in records if int(r['mem_rmask'],16) or int(r['mem_wmask'],16)]
        c.require(len(memory)==264,'Eight fresh LW plus256SW')
        c.require(gold[ordinal-1]['seed']==seed and gold[ordinal-1]['op']==25 and gold[ordinal-1]['vl']==0,'Original FP first-call identity')
        for row,event in zip(memory,q.fp[seed]):
            c.require((int(row['pc'],16),int(row['mem_addr'],16))==(int(event['pc'],16),event['address']),'Actual SoC path/event correspondence')
        c.require(int(memory[-1]['mem_addr'],16)==s['b']+508,'Each seed final b127')
        paths.append(dict(seed=seed,original_ordinal=ordinal,rows=len(records),LW=8,SW=256,first_SW=q.fp[seed][8]['pc'],last_SW=q.fp[seed][-1]['pc']))
    c.require(c.owner_counts()['compulsory_memory_owners']==29925 and c.owner_counts()['required_target_owners']==3762,'Source-enumerated owner scope')
    c.common.base.verify_pins(c.read(c.REF/'closed01/admission.json')['pins'])
    context.save(c.HERE/'preflight01.json',dict(status='MARKER_THREE_SEED_SOC_PC_PREFLIGHT_PASS',
        elapsed_s=time.monotonic()-start,marker_bytes=len(actual),marker_actual_hex=actual.hex(),paths=paths,
        owner_counts=c.owner_counts(),SoC_ELF_sha256=c.ELF_SHA,physical_group4=True,main_frame=272,
        full_source_Host=False,reference_or_DUT_runs=0))
    print('MARKER_THREE_SEED_PREFLIGHT_PASS',flush=True)

if __name__=='__main__':main()
