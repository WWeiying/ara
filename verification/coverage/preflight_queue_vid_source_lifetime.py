"""Software-only VID consumer WAR matrix; frozen738 zero is a hypothesis, not a hit."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import build_opivx_vsbc_preflight as shared
from inventory_operand_debug import Design, points
from closure_point_inventory import definition, read_xml

life, ROOT, OUT = shared.life, shared.ROOT, shared.OUT
APP = ROOT / 'apps/riscv-tests/isa/rv64uv/vqueue_vid_source_lifetime.c'
BASE = OUT / 'clip17-offline-admitted-738-parent-20261006-01'
BASE_SHA = '972d4dec87035fb12343d25305666a8d9c5a88ea8215ef330638e468386249f7'
BUILD = OUT / 'repaired-aligned-build-20260930-01'
SNAP = OUT / 'old-image-source-evidence-20261006-01/lane_sequencer.sv'
TEMPLATE = OUT / 'narrow-reject-r1-cached-preflight-719-20261006-01/compile-command.json'
TEMPLATE_SHA = 'fb14cd104d038c5dde54a278563b0ae6486aa0739c0922957ed2a959f109927d'
CELLS = [(e,l) for e in (8,16,32,64) for l in (1,2)]
CHECKS = 8 * (3 * 288 + 3)
require = shared.require

def expected(cell, kind):
    sew, lmul = CELLS[cell]; mask = (1 << sew) - 1
    result = bytearray([0xa5] * 288)
    for i in range(128*lmul//(sew//8)):
        # Python integer model, not the app's C division/shift implementation.
        value = (mask - 13*i) % (1 << sew)
        if kind == 'div': value //= 3
        if kind == 'vid': value = i % (1 << sew)
        result[16+i*(sew//8):16+(i+1)*(sew//8)] = value.to_bytes(sew//8,'little')
    return bytes(result)

def validate(commits, symbols, trace):
    require('exception ' not in trace, 'Unexpected trap')
    memory, terminal, writes = {}, [], 0
    for c in commits:
        require(c.instruction & 3 == 3, 'Compressed retirement forbidden')
        writes += len(c.vector_writes)
        for a,v in c.memory_accesses:
            if v is None: continue
            w = shared.store_width(c.instruction)
            require(0 <= v < 1 << (8*w), 'Store width mismatch')
            for j in range(w): memory[a+j] = v >> (8*j) & 255
            if a == symbols['tohost']: terminal.append(v)
    def read(name, offset, size):
        a=symbols[name]+offset
        require(all(a+j in memory for j in range(size)), 'Missing bytes '+name)
        return bytes(memory[a+j] for j in range(size))
    require(terminal == [1], 'Spike terminal differs')
    require(int.from_bytes(read('g75_result',0,4),'little') == CHECKS and
            read('g75_result',4,4) == read('num_failed',0,4) == bytes(4), 'Self-check differs')
    for n,(sew,lmul) in enumerate(CELLS):
        for k in ('source','div','vid'):
            require(read('qv_'+k,n*288,288) == expected(n,k), 'Independent buffer/guard mismatch')
        values = (128*lmul//(sew//8), (sew.bit_length()-4)*8+(lmul==2), 0)
        require(read('qv_csr',n*24,24) == b''.join(v.to_bytes(8,'little') for v in values), 'CSR mismatch')
        pair = [c for c in commits if symbols['qv_pair_'+str(n)] <= c.pc < symbols['qv_pair_'+str(n)]+8]
        require(len(pair)==2 and pair[0].instruction>>26 == 32 and
                (pair[0].instruction>>12)&7 == 6 and (pair[0].instruction>>20)&31 == 8 and
                (pair[0].instruction>>7)&31 == 16 and pair[1].instruction>>26 == 20 and
                (pair[1].instruction>>15)&31 == 17 and (pair[1].instruction>>7)&31 == 8,
                'Adjacent DIV/VID pair missing')
    require(writes > 0, 'No VRF writes')
    return dict(status='HOST_SPIKE_PASS_NOT_DUT_QUALIFICATION', checks=CHECKS, buffer_bytes=6912,
                csr_values=24, traps=0, native_stall_measured=False, coverage_hit_claimed=False)

def binding():
    admission=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    pins=dict(admission['output_pins']); life.check(pins)
    pins[str(BASE/'admission-manifest.json')]=BASE_SHA
    before=life.read_bound(BASE/'combined-bits.json',pins[str(BASE/'combined-bits.json')])
    require(len(before['tests'])==len(set(before['tests']))==738, 'Formal738 required')
    book=BUILD/'build-source-pins.json'; sources=json.loads(book.read_bytes())
    paths=['hardware/src/ara_sequencer.sv','hardware/src/lane/operand_requester.sv',
           'hardware/src/lane/operand_queue.sv','hardware/src/lane/operand_queues_stage.sv']
    for rel in paths: pins[str(ROOT/rel)] = sources[str(ROOT/rel)]
    pins[str(SNAP)] = sources[str(ROOT/'hardware/src/lane/lane_sequencer.sv')]
    pins[str(book)] = life.digest(book)
    d=Design(BUILD/'sim/simv.vdb'); tree=read_xml(d.db/'shape/cond.verilog.shape.xml')
    targets=[]
    for lane in range(4):
        scope='ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[%d].i_lane.i_operand_requester'%lane
        r=before['metrics']['cond'][scope]
        require((r['width'],r['checksum'])==(1256,'1592560956'), 'Requester shape drift')
        p=points('cond',definition(tree,d.hierarchy[scope],r['checksum']),r['width'])[665]
        require(p['raw_index']==665 and p['vector']=='010' and p['line']=='496', 'Target expression mapping')
        hit=bool(int(r['bits'],16) >> (r['width']-1-665) & 1)
        require(not hit, 'Primary already hit738')
        targets.append(dict(scope=scope,metric='cond',before=False,point=p))
    for rel,h in before['design'].items(): pins[str(d.db/rel)]=h
    image=life.read_bound(life.PLAN,life.PLAN_SEAL)
    require(len(image['image'])==66 and image['image'][str(life.IMAGE)]==
            '2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3','Frozen image mismatch')
    pins=life.merge_pins(pins,image['image']); life.check(pins)
    return targets,pins

def build(output):
    require(output.parent==OUT and not output.exists(), 'Fresh output only')
    targets,pins=binding()
    # The inherited compile command is data only: replace exactly the app/output and ISA.
    template=life.read_bound(TEMPLATE,TEMPLATE_SHA)
    require(template[0]==str(shared.LLVM/'clang') and template[-2]=='-o', 'Compiler template mismatch')
    old=str(ROOT/'apps/riscv-tests/isa/rv64uv/vnarrow_reject_r1_matrix_cached.c')
    require(template.count(old)==1, 'Template app ambiguity')
    command=[str(APP) if x==old else '-march=rv64gv_zfh_zvfh' if x=='-march=rv64gcv_zfh_zvfh' else x for x in template]
    command.insert(1,'-mno-implicit-float'); command.insert(2,'-fno-unroll-loops'); command[-1]=str(output/'input.elf')
    for p in [APP,Path(__file__).resolve(),Path(__file__).with_name('test_preflight_queue_vid_source_lifetime.py'),
              Path(shared.__file__),TEMPLATE,ROOT/'verification/tests/gap75_start.S',ROOT/'verification/tests/gap75.ld',
              shared.LLVM/'clang',shared.LLVM/'ld.lld',shared.LLVM/'llvm-readelf',shared.SPIKE]:
        pins[str(p)]=life.digest(p)
        if p.is_symlink(): pins[str(p.resolve())]=life.digest(p.resolve())
    life.check(pins); output.mkdir()
    try:
        life.save(output/'compile-command.json',command)
        with (output/'compile.log').open('x') as log:
            subprocess.run(command,check=True,timeout=120,stdout=log,stderr=subprocess.STDOUT)
        names=['tohost','g75_result','num_failed','qv_source','qv_div','qv_vid','qv_csr']+['qv_pair_'+str(n) for n in range(8)]
        symbols={n:shared._elf_symbol(output/'input.elf',shared.LLVM/'llvm-readelf',n) for n in names}
        spike=[str(shared.SPIKE),'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0',
               '-m0x80000000:0x200000','-l','--log-commits',str(output/'input.elf')]
        life.save(output/'spike-command.json',spike)
        with (output/'spike.log').open('x') as log:
            subprocess.run(spike,check=True,timeout=60,stdout=log,stderr=subprocess.STDOUT)
        trace=(output/'spike.log').read_text(); commits=shared.parse_spike_commits(output/'spike.log')
        result=validate(commits,symbols,trace)
        # Audit all executed RVV PCs: each cell has 1 vset, 1 load, DIV, VID, 2 stores.
        rvv={c.pc for c in commits if c.instruction&127 in (0x57,0x07,0x27)}
        require(len(rvv)==48, 'Unexpected implicit/missing RVV instruction PCs')
        life.check(pins)
        life.save(output/'validation.json',result); life.save(output/'symbols.json',symbols)
        artifacts={str(p):life.digest(p) for p in output.iterdir() if p.is_file()}
        manifest=dict(schema='QUEUE_VID_LIFETIME_SOFTWARE_PREFLIGHT_V1',pins=pins,outputs=artifacts,
                      targets=targets,baseline=str(BASE),baseline_seal=BASE_SHA,checks=CHECKS,
                      elf_sha256=life.digest(output/'input.elf'),native_qualification=False,application_approval=False)
        life.save(output/'preflight-manifest.json',manifest)
        print(json.dumps(dict(output=str(output),seal=life.digest(output/'preflight-manifest.json'),**result)))
    except Exception as exc:
        life.save(output/'failure.json',dict(error=str(exc),not_DUT_failure=True)); raise

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--output',type=Path,required=True)
    build(ap.parse_args().output.resolve())
