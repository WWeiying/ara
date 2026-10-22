"""One software-qualified RVV control/payload matrix, frozen image, no automatic admission."""
import argparse
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import build_opivx_vsbc_preflight as shared
import run_pure_war_simulation as frozen
import targeted_toggle_evidence as toggle

life, require = shared.life, shared.require
NAME = 'rvv_lmul8_payload_walk'
APP = life.ROOT/'apps/riscv-tests/isa/rv64uv/rvv_lmul8_payload_walk.c'
BASE = life.OUT/'gap113-full8-cached-offline-admitted-742-agent-20261007-01'
BASE_SHA = 'f07f7ccdcfc7257faad21aabdc45a48008658c70ee26abda275065f1e204a730'
IMAGE_SHA = '2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3'
TEMPLATE = life.OUT/'narrow-reject-r1-cached-preflight-719-20261006-01/compile-command.json'
TEMPLATE_SHA = 'fb14cd104d038c5dde54a278563b0ae6486aa0739c0922957ed2a959f109927d'
BUDGET = 600
CHECKS = 7803
GUARD = 0xa5a5a5a5a5a5a5a5
MASK = (1 << 64)-1

def expected(cell, kind):
    count = (64,128)[cell]
    seed = lambda i: (1 << (i % 64)) ^ (MASK if i >= 64 else 0)
    shifted = lambda i: (seed(i)^0xaa55aa55aa55aa55) >> 3
    words = [GUARD]*132
    if kind == 'narrow':
        for i in range(count//2):
            words[2+i] = (shifted(2*i)&0xffffffff) | ((shifted(2*i+1)&0xffffffff)<<32)
    else:
        for i in range(count):
            words[2+i] = seed(i) if kind == 'source' else shifted(i) if kind == 'shift' else shifted(i)&0xffffffff
    return b''.join(x.to_bytes(8,'little') for x in words)

def control_expected(cell):
    vl = (3,33,1024)[cell]
    return bytes([0xa5]*16 + [((i^(i//8))^0xaa)&255 if i < vl and i%2 else 0
                              for i in range(1024)] + [0xa5]*16)

def validate(commits, symbols, text):
    require('exception ' not in text, 'Unexpected Spike exception')
    memory, terminal = {}, []
    for c in commits:
        for address,value in c.memory_accesses:
            if value is None: continue
            width = shared.store_width(c.instruction)
            require(0 <= value < 1 << (8*width), 'Unknown memory store width')
            memory.update({address+j: value>>(8*j)&255 for j in range(width)})
            if address == symbols['tohost']: terminal.append(value)
    require(terminal == [1], 'Exactly one successful terminal required')
    def read(name,offset,size):
        a=symbols[name]+offset
        require(all(a+j in memory for j in range(size)), 'Missing independent readback '+name)
        return bytes(memory[a+j] for j in range(size))
    require(read('g75_result',0,8)==CHECKS.to_bytes(4,'little')+bytes(4) and
            read('num_failed',0,4)==bytes(4), 'Software check ledger differs')
    for cell in range(2):
        for kind in ('source','shift','narrow','wide'):
            require(read('pw_'+kind,cell*1056,1056)==expected(cell,kind),'Full footprint differs '+kind)
        vl=(64,128)[cell]; l=(2,3)[cell]; h=(1,2)[cell]
        want=[vl,24+l,0,vl,16+h,0,vl,24+l,0]
        require(read('pw_csr',cell*72,72)==b''.join(x.to_bytes(8,'little') for x in want),'CSR differs')
    for cell,vl in enumerate((3,33,1024)):
        require(read('pw_control',cell*1056,1056)==control_expected(cell),'Defined mask/tail/guards differ')
        require(read('pw_control_csr',cell*24,24)==b''.join(x.to_bytes(8,'little') for x in (vl,3,0)),
                'Small/full VL control CSR differs')
    require(read('pw_bytes',0,1056)==bytes([0xa5]*16+[(i^(i//8))&255 for i in range(1024)]+[0xa5]*16),
            'Byte source/guard differs')
    require(read('pw_mask',0,128)==bytes([0xaa]*128),'Mask source changed')
    writers=sum(bool(c.vector_writes) for c in commits)
    require(writers==24,'Missing/extra explicit vector writers')
    return dict(status='INDEPENDENT_SPIKE_MEMORY_CSR_PASS_NOT_DUT',checks=CHECKS,
                defined_snapshot_bytes=12800,csr_values=27,vector_writers=writers,traps=0)

def binding():
    admission=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    pins=dict(admission['output_pins']);life.check(pins)
    pins[str(BASE/'admission-manifest.json')]=BASE_SHA
    combined=life.read_bound(BASE/'combined-bits.json',pins[str(BASE/'combined-bits.json')])
    require(len(combined['tests'])==len(set(combined['tests']))==742,'Formal742 unique population required')
    prefix=life.OUT/'gap113-toggle-prefix-raw740-20261007-01.json'
    initial=json.loads(prefix.read_bytes()); pins[str(prefix)]=life.digest(prefix)
    scopes=list(initial['scopes']); union={s:r['prefix_union'] for s,r in initial['scopes'].items()}
    # The last two formally admitted tests extend the sealed740 prefix, not a renamed report.
    raw=json.loads(Path(initial['source_raw_result']).read_bytes())
    ledger=raw.get('input_ledger',raw.get('inputs',[]))
    if not ledger:
        ledger=(life.OUT/'final-raw740-dve-agent-20261007-01/inputs.txt').read_text().splitlines()
    require([str(x) for x in ledger[-740:]]==combined['tests'][:740],'Exact740 prefix differs')
    for db in combined['tests'][740:]:
        files=list((Path(db)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(files)==1,'One native Toggle test required')
        rows,sha=toggle.rows(files[0],scopes);pins[str(files[0])]=sha
        for s,r in rows.items():
            old=initial['scopes'][s]
            require(r['width']==old['actual_raw_width'],'Native Toggle width drift')
            value=bin(int(r['bits'],16))[2:].zfill(r['width'])[:len(union[s])]
            union[s]=''.join('1' if a=='1' or b=='1' else '0' for a,b in zip(union[s],value))
    targets=[]
    for s,r in initial['scopes'].items():
        for field in r['missing']:
            if not any(x in field['signal'] for x in ('conv','elem_count','usage','select','pointer')):continue
            offset=field['raw_offset'];width=field['signal_width']*2
            bits=union[s][offset:offset+width]
            if '0' in bits: targets.append(dict(scope=s,signal=field['signal'],raw_offset=offset,
                before742=bits,attributes=field['attributes'],bit_direction_order_not_inferred=True))
    for path,sha in initial['pins'].items(): pins[path]=sha
    book=life.OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
    sources=json.loads(book.read_bytes());pins[str(book)]=life.digest(book)
    for rel in ('hardware/src/lane/operand_queue.sv','hardware/src/lane/operand_queues_stage.sv',
                'hardware/src/lane/lane_sequencer.sv','hardware/include/ara_pkg.sv'):
        source=life.ROOT/rel
        if rel.endswith('/lane_sequencer.sv'):
            source=life.OUT/'old-image-source-evidence-20261006-01/lane_sequencer.sv'
        pins[str(source)]=sources[str(life.ROOT/rel)]
    image=life.read_bound(life.PLAN,life.PLAN_SEAL)
    require(len(image['image'])==66 and image['image'][str(life.IMAGE)]==IMAGE_SHA,'Frozen image66 differs')
    pins=life.merge_pins(pins,image['image']);pins[str(life.PLAN)]=life.PLAN_SEAL
    return targets,pins

def build(out):
    require(out.parent==life.OUT and not out.exists(),'Fresh independent preflight required')
    targets,pins=binding()
    command=life.read_bound(TEMPLATE,TEMPLATE_SHA)
    old=str(life.ROOT/'apps/riscv-tests/isa/rv64uv/vnarrow_reject_r1_matrix_cached.c')
    require(command.count(old)==1 and command[-2]=='-o','Frozen compile template differs')
    command=[str(APP) if x==old else '-march=rv64gv_zfh_zvfh' if x=='-march=rv64gcv_zfh_zvfh' else x for x in command]
    command[1:1]=['-mno-implicit-float','-fno-unroll-loops'];command[-1]=str(out/'input.elf')
    deps=[APP,Path(__file__).resolve(),Path(__file__).with_name('test_rvv_lmul8_payload_walk.py'),
          Path(shared.__file__),Path(frozen.__file__),TEMPLATE,shared.SPIKE]+list((life.ROOT/'verification/ara_verify').rglob('*.py'))
    deps += [Path(x) for x in command if x.startswith('/') and Path(x).is_file()]
    pins=life.merge_pins(pins,{str(p):life.digest(p) for p in deps});life.check(pins)
    out.mkdir()
    try:
        life.save(out/'compile-command.json',command)
        with (out/'compile.log').open('x') as log:
            subprocess.run(command,check=True,timeout=120,stdout=log,stderr=subprocess.STDOUT)
        names=['tohost','_start','g75_result','num_failed','pw_source','pw_shift','pw_narrow','pw_wide',
               'pw_csr','pw_control','pw_control_csr','pw_bytes','pw_mask']
        symbols={n:shared._elf_symbol(out/'input.elf',shared.LLVM/'llvm-readelf',n) for n in names}
        spike=[str(shared.SPIKE),'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0',
               '-m0x80000000:0x200000','-l','--log-commits',str(out/'input.elf')]
        life.save(out/'spike-command.json',spike)
        with (out/'spike.log').open('x') as log:
            subprocess.run(spike,check=True,timeout=90,stdout=log,stderr=subprocess.STDOUT)
        commits=shared.parse_spike_commits(out/'spike.log')
        result=validate(commits,symbols,(out/'spike.log').read_text())
        terminal=[i for i,c in enumerate(commits) if (symbols['tohost'],1) in c.memory_accesses]
        require(len(terminal)==1,'Successful tohost prefix required')
        entry=next(i for i,c in enumerate(commits) if c.pc==symbols['_start'])
        life.save(out/'reference-counts.json',dict(terminal_prefix=terminal[0]+1,
            architectural_entry_prefix=terminal[0]+1-entry,post_terminal=len(commits)-terminal[0]-1))
        life.save(out/'symbols.json',symbols);life.save(out/'validation.json',result)
        life.save(out/'target-before742.json',targets);life.check(pins)
        outputs={str(p):life.digest(p) for p in out.iterdir() if p.is_file()}
        manifest=dict(case=NAME,pins=pins,outputs=outputs,validation=result,baseline=str(BASE),baseline_seal=BASE_SHA,
                      elf_sha256=life.digest(out/'input.elf'),budget_s=BUDGET,coverage_admitted=False,rtl_changed=False)
        life.save(out/'preflight-manifest.json',manifest)
        print(json.dumps(dict(preflight=str(out),seal=life.digest(out/'preflight-manifest.json'),**result)))
    except BaseException as e:
        life.save(out/'failure.json',dict(error=str(e),not_DUT_failure=True));raise

def command(out,pre):
    return [str(life.IMAGE),'-l','run.vcs.log','+NO_FSDB','+ntb_random_seed=1',
        '+PRELOAD='+str(pre/'input.elf'),'+TESTCASE='+NAME,'+COMMIT_TOHOST=80001000',
        '+COMMIT_TRACE='+str(out/'commit_trace.csv'),'+VECTOR_TRACE='+str(out/'vector_trace.csv'),
        '-cm','line+cond+fsm+tgl+branch','-cm_dir',str(out/'code.vdb'),'-cm_name',NAME]

def prepare(out,pre,seal):
    require(not out.exists() and out.parent==life.OUT,'Fresh independent run required')
    m=life.read_bound(pre/'preflight-manifest.json',seal)
    require(m['case']==NAME and m['validation']['checks']==CHECKS and m['budget_s']==BUDGET,'Software contract differs')
    pins=life.merge_pins(m['pins'],m['outputs']);pins[str(pre/'preflight-manifest.json')]=seal;life.check(pins)
    validate(shared.parse_spike_commits(pre/'spike.log'),json.loads((pre/'symbols.json').read_bytes()),(pre/'spike.log').read_text())
    return dict(case=NAME,output=str(out),command=command(out,pre),pins=pins,timeout_s=BUDGET,
                preflight=str(pre),preflight_seal=seal,elf_sha256=m['elf_sha256'],baseline_tests=742,
                image_sha256=IMAGE_SHA,old_image_files_checked=66,automatic_retry=False,
                coverage_admitted=False,admission_performed=False,terminal_oracle_verified=False)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode',choices=('build','prepare','run'));ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--preflight',type=Path);ap.add_argument('--preflight-seal');ap.add_argument('--prepared-seal')
    a=ap.parse_args();out=a.output.resolve()
    if a.mode=='build':build(out);return
    require(a.preflight and a.preflight_seal,'Explicit sealed software preflight required')
    pre=a.preflight.resolve();record=prepare(out,pre,a.preflight_seal);side=out.with_name(out.name+'.prepared.json')
    if a.mode=='prepare':
        require(not side.exists(),'One-shot sidecar exists');life.save(side,record)
        print(json.dumps(dict(prepared=str(side),seal=life.digest(side))));return
    require(a.prepared_seal and life.read_bound(side,a.prepared_seal)==record,'Reviewed preparation drift')
    path=Path(frozen.__file__);ns=dict(__name__='payload_walk_private_lifecycle',__file__=str(path))
    exec(compile(path.read_bytes(),str(path),'exec'),ns)
    ns.update(PRE=pre,ELF_SEAL=record['elf_sha256'],IMAGE_SEAL=IMAGE_SHA,BUDGET=BUDGET,
              preflight=SimpleNamespace(NAME=NAME),command=lambda output: command(output,pre))
    ns['run'](out,record)

if __name__=='__main__':main()
