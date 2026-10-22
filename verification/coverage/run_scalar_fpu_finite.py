"""One bounded scalar FPU fixture; rational/Spike preflight and frozen VCS image."""
import argparse
import csv
import gzip
import json
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
import run_load_ni_tlb_control as old
import scalar_fpu_finite_oracle as oracle

life, build, require = old.life, old.build, old.require
APP = life.ROOT/'apps/riscv-tests/isa/rv64uv/scalar_fpu_finite.c'
PRE = life.OUT/'scalar-fpu-finite-preflight-agent-20261007-01'
RUN = life.OUT/'scalar-fpu-finite-old-image-agent-20261007-01'
QUAL = life.OUT/'scalar-fpu-finite-qualified-agent-20261007-01'
REVIEW = life.OUT/'fp32-fp64-fma-scoped-review-741-agent-20261007-01.json'
REVIEW_SHA = '3225bfd410ae64453f10b45a7e0d81532ba6c1f5bc2c012206a9fb66065be323'
PREFIX = 'ara_tb.dut.i_ara_soc.i_system.i_ariane.ex_stage_i.fpu_gen.fpu_i.fpu_gen.i_fpnew_bulk'
SYMBOLS = ('tohost','trap_fail','num_failed','g75_result','sf_observed','sf_csr','sf_guard_checks','sf_canary','sf_cases') + tuple('sf_op%d'%i for i in range(20))


def instruction(row, word):
    require(word & 0x7f == (0x43 if row['operation']=='fma' else 0x53), 'Scalar FP opcode differs')
    require((word>>25)&3 == int(row['width']==64) and (word>>12)&7 == (3 if row['rounding']=='rup' else 0),
            'Format/static rounding differs')
    if row['operation'] != 'fma':
        require((word>>27)&31 == (2 if row['operation']=='mul' else 0), 'Arithmetic function differs')
    require((word>>7)&31 == 3 and (word>>15)&31 == 0 and (word>>20)&31 == 1 and
            (row['operation']!='fma' or word>>27 == 2), 'Exact operand/destination FPR differs')


def boxed(row): return row['result'] | (0xffffffff00000000 if row['width']==32 else 0)


def validate_reference(commits,symbols,rows):
    writes={a:v for c in commits for a,v in c.memory_accesses if v is not None}
    require(not any(c.vector_writes or c.pc==symbols['trap_fail'] for c in commits), 'Vector/trap not permitted')
    pcs={symbols['sf_op%d'%i] for i in range(20)}
    active=[c for c in commits if c.pc in pcs]
    require([c.pc for c in active]==[symbols['sf_op%d'%i] for i in range(20)], 'Exact20 arithmetic sequence differs')
    arithmetic=[c for c in commits if c.instruction & 0x7f in (0x43,0x47,0x4b,0x4f) or
        (c.instruction & 0x7f == 0x53 and (c.instruction>>27)&31 in (0,1,2,3,4,5))]
    require(arithmetic==active, 'Additional scalar arithmetic outside reviewed20')
    for row,c in zip(rows,active):
        instruction(row,c.instruction)
        require(c.fpr_writes=={3:boxed(row)}, 'Independent rational/Spike FPR result differs')
        at=symbols['sf_observed']+24*row['index']
        require([writes.get(at+8*j) for j in range(3)]==[boxed(row),row['flags'],64|row['flags']],
                'Rational result/flags/frm independent readback differs')
    require([writes.get(symbols['g75_result']),writes.get(symbols['g75_result']+4),
        writes.get(symbols['num_failed']),writes.get(symbols['sf_guard_checks']),writes.get(symbols['tohost'])]
        ==[40,0,0,35,1], '40 arithmetic +35 guards terminal differs')
    csr=[writes.get(symbols['sf_csr']+8*i) for i in range(4)]
    require(csr[0] is not None and csr==[csr[0],72,64,csr[0]], 'CSR seed/restoration differs')
    return old.architecture.reference_counts(commits,symbols)


def compiled(pins):
    review=life.read_bound(REVIEW,REVIEW_SHA)
    paths={Path(i['path']).name:life.ROOT/i['path'] for i in review['compiled_pins']}
    for i in review['compiled_pins']: pins=life.merge_pins(pins,{str(life.ROOT/i['path']):i['sha256']})
    life.check(pins)
    def xml(p): return ET.fromstring(gzip.decompress(p.read_bytes()))
    design,info,shape=(xml(paths[n]) for n in ('verilog.design.xml','tgl.verilog.info.xml','tgl.verilog.shape.xml'))
    nodes={n.get('id'):(n,m) for m in design.findall('srcdef') for n in m.findall('srcinst')}
    def path(k):
        n,_=nodes[k];p=n.get('pid');return (path(p)+'.' if p in nodes else '')+n.get('name')
    hierarchy={path(k):m for k,(_,m) in nodes.items()}
    checks={n.get('name'):n.get('chksum') for n in info.iter('instance_data')}
    records=[]
    for fmt,width,regs,chk in ((0,32,2,'3893821548'),(1,64,3,'2370198160')):
        scope=PREFIX+'.gen_operation_groups[0].i_opgroup_block.gen_parallel_slices[%d].active_format.i_fmt_slice.gen_num_lanes[0].active_lane.lane_instance.i_fma'%fmt
        module=hierarchy[scope]; defs=[n for n in shape if n.get('id')==module.get('id') and n.get('chksum')==chk]
        require(checks[scope]==chk and module.get('name')=='fpnew_fma' and len(defs)==1,'Compiled instance ambiguity')
        signature=defs[0].get('name')
        require('FpFormat=%d,NumPipeRegs=%d,PipeConfig=3,WIDTH=%d,'%(fmt,regs,width) in signature,
                'Frozen specialization differs')
        names={'product','product_shifted','addend_after_shift','addend_shifted'}
        targets=[dict(n.attrib,kind=n.tag) for n in defs[0].find('tglshape') if n.get('name') in names]
        require(len(targets)==4 and all(n['portnode']=='0' and n['file']=='381' and n['excluded']=='0' for n in targets),
                'Four complete local arithmetic vectors differ')
        records.append(dict(scope=scope,checksum=chk,compiled_parameters=signature,targets=targets,
            all_other_objects_and_descendants_protected=True,native_qualified=False))
    return pins,records


def command(elf):
    return [str(life.IMAGE),'-l','run.vcs.log','+NO_FSDB','+ntb_random_seed=1','+PRELOAD='+str(elf),
        '+TESTCASE=scalar_fpu_finite','+COMMIT_TOHOST=80001000','+COMMIT_TRACE='+str(RUN/'commit_trace.csv'),
        '+VECTOR_TRACE='+str(RUN/'vector_trace.csv'),'-cm','line+cond+fsm+tgl+branch',
        '-cm_dir',str(RUN/'code.vdb'),'-cm_name','scalar_fpu_finite','+ARA_UVM_TRACE_LIMIT=100000',
        '+ARA_CONTRACT_TRACE_LIMIT=100000']


def prepare():
    require(not PRE.exists() and not RUN.exists(),'Fresh one-shot preflight required')
    image=life.read_bound(life.PLAN,life.PLAN_SEAL)
    require(len(image['image'])==66 and image['simv']==str(life.IMAGE),'Frozen66 image differs')
    book=life.read_bound(old.BUILD/'build-source-pins.json',old.SOURCE_SHA)
    pins=life.merge_pins(image['image'],{str(life.PLAN):life.PLAN_SEAL,
        str(old.BUILD/'build-source-pins.json'):old.SOURCE_SHA,str(REVIEW):REVIEW_SHA})
    sources=('hardware/deps/cva6/core/fpu_wrap.sv','hardware/deps/cva6/core/ex_stage.sv',
        'hardware/deps/cva6/core/decoder.sv','hardware/deps/cva6/core/issue_read_operands.sv',
        'hardware/deps/cva6/core/scoreboard.sv','hardware/deps/fpnew/src/fpnew_fma.sv',
        'hardware/deps/fpnew/src/fpnew_rounding.sv','hardware/deps/fpnew/src/fpnew_classifier.sv',
        'hardware/deps/fpnew/src/fpnew_pkg.sv','hardware/deps/fpnew/src/fpnew_top.sv',
        'hardware/deps/fpnew/src/fpnew_opgroup_block.sv','hardware/deps/fpnew/src/fpnew_opgroup_fmt_slice.sv')
    for rel in sources: pins=life.merge_pins(pins,{str(life.ROOT/rel):book[str(life.ROOT/rel)]})
    require(book[str(life.ROOT/'hardware/deps/fpnew/src/fpnew_fma.sv')]==
        'f46700037a6f9efe9b74855d3d21ebaeaf42f5dd522b9e812bbc56ad7193ec71','Reviewed unchanged FMA source differs')
    cmd=json.loads(old.TEMPLATE.read_bytes())
    cmd=[str(APP) if x.endswith('/vgap99_csr_satp_mprv.c') else str(PRE/'input.elf') if x.endswith('/input.elf') else x for x in cmd]
    cmd[1:1]=['-I'+str(PRE)]
    for p in (APP,old.TEMPLATE,Path(__file__).resolve(),Path(oracle.__file__).resolve(),
        Path(__file__).with_name('test_scalar_fpu_finite.py'),life.ROOT/'verification/tests/gap75_start.S',
        life.ROOT/'verification/tests/gap75.ld',Path(cmd[0]),build.LLVM/'llvm-readelf',build.LLVM/'llvm-objdump',build.SPIKE):
        pins=life.merge_pins(pins,{str(p):life.digest(p)})
    for module in tuple(sys.modules.values()):
        f=getattr(module,'__file__',None)
        if f and str(life.ROOT/'verification') in f and Path(f).is_file():
            p=Path(f).resolve();pins=life.merge_pins(pins,{str(p):life.digest(p)})
    pins,instances=compiled(pins);life.check(pins);PRE.mkdir()
    try:
        rows=oracle.cases();life.save(PRE/'oracle.json',rows)
        with (PRE/'scalar_fpu_finite_vectors.h').open('x') as f:f.write(oracle.header(rows))
        life.save(PRE/'compile-command.json',cmd)
        with (PRE/'build.log').open('x') as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=120)
        elf=PRE/'input.elf';symbols={n:build._elf_symbol(elf,build.LLVM/'llvm-readelf',n) for n in SYMBOLS}
        with (PRE/'input.disasm').open('x') as f:subprocess.run([str(build.LLVM/'llvm-objdump'),'-d',str(elf)],stdout=f,check=True,timeout=30)
        spike=[str(build.SPIKE),'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0','-l','--log-commits',str(elf)]
        life.save(PRE/'spike-command.json',spike)
        with (PRE/'spike.trace').open('x') as f:subprocess.run(spike,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=120)
        counts=validate_reference(build.parse_spike_commits(PRE/'spike.trace'),symbols,rows)
        life.check(pins)
        for p in PRE.iterdir():pins=life.merge_pins(pins,{str(p):life.digest(p)})
        value=dict(status='EXACT20_SCALAR_FP_RATIONAL_SPIKE_PASS_NOT_RTL',pins=pins,symbols=symbols,
            counts=counts,operations=20,result_flags_checks=40,guard_checks=35,instances=instances,
            scope='Finite scalar F/D ADD/MUL/FMA only. FP32 boxed and explicit RNE/RUP, frm seeded RDN preserved.',
            coverage_admitted=False,native_exclusion_approved=False)
        life.save(PRE/'preflight.json',value);pins=life.merge_pins(pins,{str(PRE/'preflight.json'):life.digest(PRE/'preflight.json')})
        record=dict(case='scalar_fpu_finite',pins=pins,command=command(elf),timeout_s=600,
            preflight_seal=life.digest(PRE/'preflight.json'),automatic_retry=False,rtl_changed=False,coverage_admitted=False)
        prepared=RUN.with_name(RUN.name+'.prepared.json');life.save(prepared,record)
        print('PREPARED '+life.digest(prepared),flush=True)
    except Exception as e:life.save(PRE/'failure.json',dict(reason=str(e),coverage_admitted=False));raise


def execute(seal):
    p=RUN.with_name(RUN.name+'.prepared.json');m=life.read_bound(p,seal)
    require(m['command']==command(PRE/'input.elf') and m['timeout_s']==600 and not RUN.exists(),'Exact one-shot command differs')
    life.run(RUN,dict(m,pins=life.merge_pins(m['pins'],{str(p):seal})))


def collect(seal):
    require(not QUAL.exists(),'Fresh terminal qualification only')
    p=RUN.with_name(RUN.name+'.prepared.json');m=life.read_bound(p,seal)
    pre=life.read_bound(PRE/'preflight.json',m['preflight_seal']);pins=life.merge_pins(m['pins'],{str(p):seal})
    require(json.loads((RUN/'manifest.json').read_text())==dict(m,pins=pins),'Actual runtime differs')
    require(json.loads((RUN/'simulation-status.json').read_text())['returncode']==0,'Successful terminal required')
    for f in RUN.rglob('*'):
        if f.is_file():pins=life.merge_pins(pins,{str(f):life.digest(f)})
    life.check(pins);QUAL.mkdir()
    try:
        lines=(RUN/'console.log').read_text().splitlines()
        require(lines.count('Core Test *** SUCCESS ***')==1 and not any(re.match(r'^(UVM_ERROR|UVM_FATAL|Error-)',x) for x in lines),
            'Software/core error differs')
        require(re.findall(r'\[ARA_CONTRACT\] requests=(\d+) responses=(\d+) exceptions=(\d+).*?protocol_errors=(\d+) outstanding=(\d+)',
            '\n'.join(lines))==[('0','0','0','0','0')],'No CVX requests permitted')
        scalar=old.architecture.spike_trace.compare_commit_prefix(PRE/'spike.trace',RUN/'commit_trace.csv',0x80000000,
            terminal_tohost_address=0x80001000,rvfi_store_data_layout='unshifted')
        life.save(QUAL/'scalar-comparison.json',scalar);old.architecture.scalar_exact(scalar,pre['counts'])
        with (RUN/'commit_trace.csv').open() as f:trace=list(csv.DictReader(f))
        require(all(r['event']=='retire' and not int(r['trap']) for r in trace) and
            [int(r['order']) for r in trace]==list(range(len(trace))),'Full scalar-only retire prefix differs')
        with (RUN/'vector_trace.csv').open() as f:require(all(r['event']=='config' for r in csv.DictReader(f)),'Unexpected vector activity')
        memory={}
        for row in trace:
            store=old.architecture.scalar_store(row)
            if store:
                address,data=store
                for i,value in enumerate(data):memory[address+i]=value
        def word(address,size=8):return sum(memory[address+i]<<(8*i) for i in range(size))
        rows=life.read_bound(PRE/'oracle.json',pins[str(PRE/'oracle.json')]);observed=[]
        for row in rows:
            pc=pre['symbols']['sf_op%d'%row['index']];active=[r for r in trace if int(r['pc'],16)==pc]
            require(len(active)==1,'Missing/duplicate actual arithmetic');instruction(row,int(active[0]['insn'],16))
            data=[word(pre['symbols']['sf_observed']+24*row['index']+8*i) for i in range(3)]
            require(data==[boxed(row),row['flags'],64|row['flags']],'Actual numeric/NaNbox/flags/frm differs')
            observed.append(dict(index=row['index'],name=row['name'],width=row['width'],pc=hex(pc),
                result=hex(data[0]),flags=data[1],fcsr=data[2],retire_cycle=int(active[0]['cycle'])))
        require([word(pre['symbols']['g75_result'],4),word(pre['symbols']['g75_result']+4,4),
            word(pre['symbols']['num_failed'],4),word(pre['symbols']['sf_guard_checks'])]==[40,0,0,35], 'Complete native counters differ')
        csr=[word(pre['symbols']['sf_csr']+8*i) for i in range(4)]
        require(csr==[csr[0],72,64,csr[0]],'Actual CSR restoration differs')
        life.save(QUAL/'observed.json',dict(operations=observed,csr=csr,result_flags_checks=40,guard_checks=35))
        life.check(pins);life.save(QUAL/'qualification.json',dict(status='EXACT20_SCALAR_FP_RATIONAL_SPIKE_DUT_QUALIFIED',
            input_pins=pins,output_pins={str(f):life.digest(f) for f in QUAL.iterdir()},instances=pre['instances'],
            operations=20,result_flags_checks=40,guard_checks=35,scalar_exact_counts=pre['counts'],
            rtl_changed=False,coverage_admitted=False,native_exclusion_approved=False,
            uvm_check_report_pass=False,missing_uvm_summary_preserved=True,
            scope=pre['scope'],protection='Every port/control/rounding/sticky/flags/status/reset/tag/pipeline/child and modified logic retained.'))
        print('QUALIFIED '+life.digest(QUAL/'qualification.json'),flush=True)
    except Exception as e:life.save(QUAL/'failure.json',dict(reason=str(e),coverage_admitted=False));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepare',action='store_true');p.add_argument('--run-seal');p.add_argument('--collect-seal')
    a=p.parse_args();require(sum(map(bool,(a.prepare,a.run_seal,a.collect_seal)))==1,'One mode required')
    if a.prepare:prepare()
    elif a.run_seal:execute(a.run_seal)
    else:collect(a.collect_seal)
