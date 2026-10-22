"""One raw780-zero MaskB producer; software-only, never launches VCS/DVE."""
import argparse
import gzip
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

import preflight_vfirst_long_mask as reuse
import build_operand_index_snapshot_preflight as inventory
from closure_point_inventory import points
import report_global777_compact as report

life, need, ROOT, OUT = reuse.life, reuse.require, reuse.ROOT, reuse.OUT
APP = ROOT/'apps/riscv-tests/isa/rv64uv/vmask_b_sext4_scalar.c'
BASE = OUT/'dtlb-ppn-swap-offline-admitted780-agent-20261008-01'
BASE_SHA = '4b679eed5892200a4d166748d9ae504a31d5dddcb3cdbca0e1f3ec61cab2bb7b'
REPORT = OUT/'current-population780-compact-prepared-agent-20261008-01'
Q_SHA = '815e7297de2aea348eccd2850901773d88b93082b52239e3fbc678b62de9f16d'
SCOPE = 'ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_queues.i_operand_queue_mask_b'
SYMBOLS = ('tohost','num_failed','g75_result','mb_checks','mb_source','mb_snapshot','mb_ledger',
           'mb_load','mb_scalar','mb_readback','trap_fail')


def image(phase):
    need(phase in (0,1), 'Only two defined phases')
    values = [0x7fff if phase else 0x8001] + [0x3100 + i*37 for i in range(1,64)]
    return b''.join(v.to_bytes(2,'little') for v in values)


def gold(phase):
    x = int.from_bytes(image(phase)[:2],'little',signed=True) & ((1<<64)-1)
    return [x,64,0,64,8,0,0,0]


def bind(row, definition):
    need(row['width']==101 and row['checksum'] is None and definition.get('chksum')=='1417162425',
         'Exact inherited compiled MaskB layout')
    p = next(p for p in points('branch',definition,101) if p['raw_index']==70)
    need((p['native_id'],p['vector'],p['attributes']['chksum'])==('5','6','718333796'), 'Exact compiled branch vector')
    bits = p['native_vector']['vector']
    need([i+1 for i,b in enumerate(bits[::-1]) if b=='1']==[8,9,11], 'Exact SExt4/SupportIntExt4/EW16 vector')
    group = next(g for g in definition.iter('branch_spec') if g.get('id')=='5')
    case = next(e for e in group if e.get('id')=='336')
    need(any(i.get('index')=='8' and i.get('name').strip()=='OpQueueConversionSExt4' for i in case), 'SExt4 source case')
    need(any(i.get('index')=='11' and i.get('name').strip()=='EW16' for e in group for i in e), 'EW16 source case')
    need(not (int(row['bits'],16)>>(100-70)&1), 'Already hit780')
    return p


def targets():
    manifest = life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    bitmap_path = BASE/'combined-bits.json'
    bitmap = life.read_bound(bitmap_path,manifest['output_pins'][str(bitmap_path)])
    q = life.read_bound(REPORT/'qualification.json',Q_SHA)
    need(q['population']==780 and q['admission_seal']==BASE_SHA, 'Qualified exact780 policy')
    pins = {str(BASE/'admission-manifest.json'):BASE_SHA,str(bitmap_path):manifest['output_pins'][str(bitmap_path)],
            str(REPORT/'qualification.json'):Q_SHA}
    book = ROOT/'verification/out/repaired-aligned-build-20260930-01/build-source-pins.json'
    sourcebook = life.read_bound(book,'6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b')
    pins[str(book)] = life.digest(book)
    for rel in ('hardware/src/lane/operand_queue.sv','hardware/src/lane/operand_queues_stage.sv',
                'hardware/src/ara_sequencer.sv','hardware/include/ara_pkg.sv'):
        pins[str(ROOT/rel)] = sourcebook[str(ROOT/rel)]
    for name in ('ara_dispatcher.sv','lane_sequencer.sv'):
        snapshot = OUT/'old-image-source-evidence-20261006-01'/name
        original = ROOT/('hardware/src/'+('lane/' if name=='lane_sequencer.sv' else '')+name)
        pins[str(snapshot)] = sourcebook[str(original)]
    life.check(pins)
    db = inventory.old.BUILD/'sim/simv.vdb/snps/coverage/db'
    for relative,h in bitmap['design'].items(): pins[str(db/relative)] = h
    definition = inventory.s.Design(inventory.old.BUILD/'sim/simv.vdb').definition(SCOPE,'branch')
    point = bind(bitmap['metrics']['branch'][SCOPE],definition)
    text = (REPORT/'combined.el').read_text()
    need(life.digest(REPORT/'combined.el')==q['source_design_native_pins'][str(REPORT/'combined.el')], 'Exact approved EL bytes')
    pins[str(REPORT/'combined.el')] = life.digest(REPORT/'combined.el')
    other,_ = report.semantic(text)
    need(not any(s==SCOPE and re.match(r'^Branch\s+5(?:\D|$)',line) for s,h,machine,line in other), 'Target group already waived')
    life.check(pins)
    return dict(scope=SCOPE,point=point,before_hit=False,excluded=False,raw_width=101,
        raw_checksum=None,inherited_shape_checksum='1417162425',native_GUI_qualified=False,
        witness='VMVXS: SEW16->SExt4, eew_vs2=EW16; VFU_None->MaskB; lane0 VL1; SupportIntExt4=1',
        source_lines=dict(dispatcher=2658,lane_sequencer=1143,operand_queue=353),pins=pins)


def validate(trace,symbols):
    commits = reuse.build.parse_spike_commits(trace)
    need('exception ' not in trace.read_text() and not any(c.pc==symbols['trap_fail'] for c in commits),'No software trap')
    memory, snapshots, ops, loads = {},{},[],[]
    for c in commits:
        for a,v in c.memory_accesses:
            if v is None: continue
            decoded = reuse.old.rvc.decode(c.instruction)
            if decoded:
                need(decoded['kind']=='write','Store effect decode'); width=decoded['size']
            elif c.instruction&0x7f==0x23: width=1<<(c.instruction>>12&7)
            else:
                need(c.instruction&0x7f==0x27,'Known vector memory writer'); width=1
            for i in range(width): memory[a+i]=v>>(8*i)&255
            if c.pc==symbols['mb_readback']:
                need(width==1 and a not in snapshots,'Exact snapshot footprint'); snapshots[a]=v
        if c.pc==symbols['mb_scalar']: ops.append(c)
        if c.pc==symbols['mb_load']: loads.append(c)
    need(len(ops)==len(loads)==2 and [c for c in commits if c.vector_writes]==loads,'Only two loads write VRF')
    def observed(a,n):
        need(all(a+i in memory for i in range(n)),'Missing memory witness')
        return bytes(memory[a+i] for i in range(n))
    for phase in range(2):
        full=reuse.GUARD.to_bytes(8,'little')*2+image(phase)+reuse.GUARD.to_bytes(8,'little')*2
        for name in ('mb_source','mb_snapshot'):
            need(observed(symbols[name]+phase*160,160)==full,'Whole source/snapshot/guards')
        need([int.from_bytes(observed(symbols['mb_ledger']+phase*64+i*8,8),'little') for i in range(8)]==gold(phase),'rd and all CSRs')
        need(loads[phase].vector_writes=={8:int.from_bytes(image(phase),'little')},'All128 loaded bytes')
        op=ops[phase]; rd=op.instruction>>7&31
        need(op.instruction&0xfe0ff07f==0x42002057 and rd!=0 and op.gpr_writes=={rd:gold(phase)[0]} and not op.vector_writes,'Exact VMVXS scalar retirement')
        need(all(snapshots.get(symbols['mb_snapshot']+160*phase+16+i)==v for i,v in enumerate(image(phase))),'Whole v8 preserved')
    need(len(snapshots)==256,'Exact whole snapshot count')
    for name,value,size in (('mb_checks',96,4),('num_failed',0,4),('g75_result',96,4),('tohost',1,8)):
        need(int.from_bytes(observed(symbols[name],size),'little')==value,'Successful96-check terminal')
    need(int.from_bytes(observed(symbols['g75_result']+4,4),'little')==0,'No failures')
    return dict(checks=96,scalar_returns=2,source_loaded_bytes=256,preserved_snapshot_bytes=256,VRF_writers=2,
                scalar_return_VRF_writers=0,CSR_ledger_values=14)


def prepare(out):
    need(out.parent==OUT and not out.exists(),'Fresh software-only output')
    target=targets(); pins=target['pins'].copy()
    command=json.loads(reuse.template.TEMPLATE.read_bytes())
    command=[str(APP) if x.endswith('/vgap99_csr_satp_mprv.c') else str(out/'input.elf') if x.endswith('/input.elf') else x for x in command]
    command+=['-fno-unroll-loops']
    for p in (APP,Path(__file__).resolve(),Path(__file__).with_name('test_preflight_mask_b_sext4.py'),
              Path(reuse.__file__),reuse.template.TEMPLATE,reuse.template.START,ROOT/'verification/tests/gap75.ld',
              Path(reuse.template.__file__),Path(reuse.build.__file__),Path(reuse.old.rvc.__file__),
              Path(command[0]),reuse.build.SPIKE,reuse.build.LLVM/'llvm-objdump',reuse.build.LLVM/'llvm-readelf'):
        pins[str(p.resolve())]=life.digest(p)
    life.check(pins); out.mkdir(); life.save(out/'target-before.json',target); life.save(out/'compile-command.json',command)
    with (out/'build.log').open('x') as stream: subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,timeout=120,check=True)
    from elftools.elf.elffile import ELFFile
    with (out/'input.elf').open('rb') as stream:
        segments=[(p['p_paddr'],p['p_paddr']+p['p_memsz']) for p in ELFFile(stream).iter_segments() if p['p_type']=='PT_LOAD']
    symbols={n:reuse.build._elf_symbol(out/'input.elf',reuse.build.LLVM/'llvm-readelf',n) for n in SYMBOLS}
    dis=subprocess.check_output([str(reuse.build.LLVM/'llvm-objdump'),'-d',str(out/'input.elf')],text=True,timeout=30)
    (out/'disassembly.txt').write_text(dis)
    vectors=re.findall(r'^\s*[0-9a-f]+:\s+(?:[0-9a-f]{8}|[0-9a-f]{4})\s+(v[\w.]+)',dis,re.M)
    need(sorted(vectors)==sorted(('vsetvli','vle16.v','vmv.x.s','vs1r.v')),'Only four explicit static RVV instructions')
    spike=[str(reuse.build.SPIKE),'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0',
           '-m0x80000000:0x200000','-l','--log-commits',str(out/'input.elf')]
    life.save(out/'spike-command.json',spike)
    with (out/'spike.trace').open('x') as stream: subprocess.run(spike,stdout=stream,stderr=subprocess.STDOUT,timeout=120,check=True)
    counts=validate(out/'spike.trace',symbols)
    counts['runtime']=reuse.template.runtime(reuse.build.parse_spike_commits(out/'spike.trace'),symbols,segments)
    life.check(pins); pins=life.merge_pins(pins,{str(p):life.digest(p) for p in out.iterdir() if p.is_file()})
    life.save(out/'preflight.json',dict(status='MASK_B_SEXT4_HOST_SPIKE_PASS_NOT_DUT',input_pins=pins,
        ELF=str(out/'input.elf'),symbols=symbols,counts=counts,target=target,baseline=780,VCS_started=False,coverage_admitted=False))
    print(json.dumps(dict(output=str(out),seal=life.digest(out/'preflight.json'),ELF_sha=life.digest(out/'input.elf'),counts=counts)))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--output',type=Path,required=True)
    out=parser.parse_args().output.resolve()
    try: prepare(out)
    except Exception as e:
        if out.exists(): life.save(out/'failure.json',dict(error=str(e),VCS_started=False,no_retry=True))
        raise
