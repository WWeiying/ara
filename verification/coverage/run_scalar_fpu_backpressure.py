"""One natural DIV/SQRT backpressure experiment; no force, admission or retries."""
import argparse
import csv
import gzip
from fractions import Fraction
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
from types import FunctionType
import xml.etree.ElementTree as ET
import run_scalar_fpu_finite as base
import audit_gap115_axi_v2 as wave
import qualify_load_ni_tlb_control as converter
import coverage_bitmap_delta as bitmap
import targeted_toggle_evidence as toggle

life, build, old, require = base.life, base.build, base.old, base.require
ROOT, OUT = life.ROOT, life.OUT
APP = ROOT/'apps/riscv-tests/isa/rv64uv/scalar_fpu_backpressure.c'
PROBE = Path(__file__).with_name('scalar_fpu_backpressure_probe.tcl')
PRE = OUT/'scalar-fpu-backpressure-preflight-771-agent-20261007-04'
RUN = OUT/'scalar-fpu-backpressure-old-image-771-agent-20261007-02'
QUAL = OUT/'scalar-fpu-backpressure-qualified-771-agent-20261007-01'
BASE = OUT/'sv39-alias-offline-admitted-771-agent-20261007-01'
BASE_SHA = 'ad9e01dcd0ea3ef442d7f28934bf1695dca61c7b6d1c7580bd2a49f0c2569860'
SCOPE = 'ara_tb.dut.i_ara_soc.i_system.i_ariane.ex_stage_i.fpu_gen.fpu_i'
SYMBOLS = ('tohost','trap_fail','num_failed','g75_result','bp_inputs',
           'bp_observed','bp_csr','bp_guards','bp_batch0','bp_batch1')

def signal(name):
    return SCOPE+('.' if name in ('state_q','flush_i','fpu_valid_i','fpu_ready_o') else '.fpu_gen.')+name


def encoded(value, width):
    raw = struct.pack('>f' if width == 32 else '>d', float(value))
    decoded = struct.unpack('>f' if width == 32 else '>d', raw)[0]
    require(Fraction(decoded) == value, 'Oracle input/result not exactly representable')
    bits = int.from_bytes(raw, 'big')
    return bits | (0xffffffff00000000 if width == 32 else 0)


def cases():
    rows = []
    for width in (32,64):
        # Identical dyadic magnitudes with independent signs: exact +/-1 division.
        magnitudes = [Fraction(0xaaaaab, 1 << 23), Fraction(0xd55555, 1 << 23),
                      Fraction(0xb6db6d, 1 << 23), Fraction(0xe38e39, 1 << 23)]
        inputs, expected = [], []
        for i, value in enumerate(magnitudes):
            numerator = -value if i & 1 else value
            denominator = -value if i & 2 else value
            inputs += [encoded(numerator,width), encoded(denominator,width)]
            expected.append(encoded(numerator/denominator,width))
        exponent = 50 if width == 32 else 500
        roots = [Fraction(3, 1 << exponent), Fraction(5)*(1 << exponent),
                 Fraction(9,2), Fraction(17,4)]
        inputs += [encoded(v*v,width) for v in roots]
        expected += [encoded(v,width) for v in roots]
        rows.append(dict(width=width,inputs=inputs,expected=expected,flags=0))
    return rows


def header(rows):
    def array(name,key):
        values=',\n'.join(' {'+', '.join('0x%016xul'%v for v in r[key])+'}' for r in rows)
        return 'static const unsigned long %s[2][%d] = {\n%s\n};\n'%(name,len(rows[0][key]),values)
    return array('bp_inputs','inputs')+array('bp_expected','expected')


def opcode(word, width, index):
    require(word & 0x7f == 0x53 and (word>>12)&7 == 0 and
            (word>>25)&3 == int(width==64) and (word>>7)&31 == destination(index),
            'Exact static RNE/format/destination differs')
    require((word>>27)&31 == (3 if index<4 else 11) and
            (word>>15)&31 == (index*2 if index<4 else index+6) and
            (word>>20)&31 == (index*2+1 if index<4 else 0), 'Exact DIV/SQRT sources differ')

def destination(index):
    return 14+index if index<4 else 24+index


def validate(commits,symbols,rows):
    writes={a:v for c in commits for a,v in c.memory_accesses if v is not None}
    require(not any(c.vector_writes or c.pc==symbols['trap_fail'] for c in commits), 'Vector/trap forbidden')
    require(all(c.instruction & 3 == 3 for c in commits), 'No compressed instructions in scoped memory audit')
    require(not any(c.instruction&0x7f==0x27 and (c.instruction>>20)&31 in {8,9,*range(18,28)}
                    for c in commits), 'Uninitialized callee-saved FPR memory effects forbidden')
    arithmetic=[c for c in commits if c.instruction&0x7f==0x53 and (c.instruction>>27)&31 in (0,1,2,3,4,5,11)]
    require(len(arithmetic)==16, 'Exactly16 arithmetic operations required')
    for batch,row in enumerate(rows):
        for i,c in enumerate(arithmetic[batch*8:batch*8+8]):
            require(c.pc==symbols['bp_batch%d'%batch]+4*i,'Contiguous arithmetic PCs differ')
            opcode(c.instruction,row['width'],i)
            require(c.fpr_writes=={destination(i):row['expected'][i]}, 'Independent exact FPR/NaNbox differs')
            require(writes.get(symbols['bp_observed']+64*batch+8*i)==row['expected'][i], 'Full result readback differs')
    csr=[writes.get(symbols['bp_csr']+8*i) for i in range(5)]
    require(csr[0] is not None and csr==[csr[0],64,64,64,csr[0]], 'FCSR/flags/restoration differs')
    require([writes.get(symbols['g75_result']),writes.get(symbols['g75_result']+4),
             writes.get(symbols['num_failed']),writes.get(symbols['tohost'])]==[22,0,0,1], 'Complete22-check terminal differs')
    return old.architecture.reference_counts(commits,symbols)


def command(elf):
    return [str(life.IMAGE),'-l','run.vcs.log','+NO_FSDB','+ntb_random_seed=1','+PRELOAD='+str(elf),
            '+TESTCASE=scalar_fpu_backpressure','+COMMIT_TOHOST=80001000',
            '+COMMIT_TRACE='+str(RUN/'commit_trace.csv'),'+VECTOR_TRACE='+str(RUN/'vector_trace.csv'),
            '-cm','line+cond+fsm+tgl+branch','-cm_dir',str(RUN/'code.vdb'),'-cm_name','scalar_fpu_backpressure',
            '+ARA_UVM_TRACE_LIMIT=100000','+ARA_CONTRACT_TRACE_LIMIT=100000','-ucli','-do',str(PROBE)]


def prepare():
    require(not PRE.exists() and not RUN.exists() and not RUN.with_suffix('.prepared.json').exists(),
            'One fresh experiment only')
    manifest=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    before=life.read_bound(BASE/'combined-bits.json',manifest['output_pins'][str(BASE/'combined-bits.json')])
    require(len(before['tests'])==len(set(before['tests']))==771, 'Exact formal771 population')
    image=life.read_bound(life.PLAN,life.PLAN_SEAL)
    require(len(image['image'])==66 and image['simv']==str(life.IMAGE), 'Frozen66 image')
    book=life.read_bound(old.BUILD/'build-source-pins.json',old.SOURCE_SHA)
    pins=life.merge_pins(image['image'],{str(life.PLAN):life.PLAN_SEAL,
         str(old.BUILD/'build-source-pins.json'):old.SOURCE_SHA,str(BASE/'admission-manifest.json'):BASE_SHA,
         str(BASE/'combined-bits.json'):manifest['output_pins'][str(BASE/'combined-bits.json')]})
    for rel in ('hardware/deps/cva6/core/fpu_wrap.sv','hardware/deps/cva6/core/issue_read_operands.sv',
                'hardware/deps/cva6/core/scoreboard.sv','hardware/deps/fpnew/src/fpnew_top.sv',
                'hardware/deps/fpnew/src/fpnew_opgroup_multifmt_slice.sv',
                'hardware/deps/fpnew/src/fpnew_divsqrt_th_64_multi.sv'):
        pins=life.merge_pins(pins,{str(ROOT/rel):book[str(ROOT/rel)]})
    text=(ROOT/'hardware/deps/cva6/core/fpu_wrap.sv').read_text()
    for anchor in ('if (fpu_valid_i & ~fpu_in_ready)', 'hold_inputs = 1\'b1;',
                   'state_d     = STALL;', 'operand_a_q  <= operand_a_d;',
                   'operand_b_q  <= operand_b_d;', "assign fpu_out_ready = 1'b1;"):
        require(anchor in text, 'Holding source contract drift')
    db=Path(str(life.IMAGE)+'.vdb')/'snps/coverage/db'
    def xml(path):
        raw=path.read_bytes()
        return ET.fromstring(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw)
    files=[db/'shape/tgl.verilog.info.xml',db/'shape/tgl.verilog.shape.xml',db/'design/verilog.design.xml',
           db/'auxiliary/verilog.sourceinfo.xml']
    for file in files:pins=life.merge_pins(pins,{str(file):life.digest(file)})
    info,shape,design,sourceinfo=[xml(file) for file in files]
    require([n.get('name') for n in sourceinfo.iter('fileinfo') if n.get('id')=='423']==
            [str(ROOT/'hardware/deps/cva6/core/fpu_wrap.sv')], 'Actual compiled wrapper source owner')
    matching=[n for n in info.iter('instance_data') if n.get('name')==SCOPE]
    require(len(matching)==1,'Exact wrapper native scope')
    checksum=matching[0].get('chksum')
    definitions=[n for n in shape if n.get('chksum')==checksum]
    require(len(definitions)==1,'Unique wrapper Toggle definition')
    names={'fpu_gen.operand_a_q','fpu_gen.operand_b_q','state_q','fpu_gen.hold_inputs','fpu_gen.use_hold'}
    targets=[dict(n.attrib,kind=n.tag) for n in definitions[0].find('tglshape') if n.get('name') in names]
    require({n['name'] for n in targets}==names,
            'Complete holding typed shape')
    cmd=json.loads(old.TEMPLATE.read_bytes())
    cmd=[str(APP) if x.endswith('/vgap99_csr_satp_mprv.c') else str(PRE/'input.elf')
         if x.endswith('/input.elf') else '-march=rv64gv_zfh_zvfh' if x.startswith('-march=') else x for x in cmd]
    cmd[1:1]=['-I'+str(PRE)]
    for path in (APP,PROBE,old.TEMPLATE,Path(cmd[0]),build.SPIKE,build.LLVM/'llvm-objdump',
                 build.LLVM/'llvm-readelf',ROOT/'verification/tests/gap75_start.S',ROOT/'verification/tests/gap75.ld',
                 Path(__file__).with_name('test_scalar_fpu_backpressure.py'),converter.CONVERTER):
        pins=life.merge_pins(pins,{str(path):life.digest(path)})
    require(pins[str(converter.CONVERTER)]==converter.CONVERTER_SHA, 'Frozen converter identity')
    for module in tuple(sys.modules.values()):
        file=getattr(module,'__file__',None)
        if file and str(ROOT/'verification') in file and Path(file).is_file():
            path=Path(file).resolve();pins=life.merge_pins(pins,{str(path):life.digest(path)})
    life.check(pins);PRE.mkdir()
    rows=cases();life.save(PRE/'oracle.json',rows)
    with (PRE/'scalar_fpu_backpressure_vectors.h').open('x') as f:f.write(header(rows))
    life.save(PRE/'compile-command.json',cmd)
    with (PRE/'build.log').open('x') as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=120)
    symbols={s:build._elf_symbol(PRE/'input.elf',build.LLVM/'llvm-readelf',s) for s in SYMBOLS}
    with (PRE/'input.disasm').open('x') as f:
        subprocess.run([str(build.LLVM/'llvm-objdump'),'-d',str(PRE/'input.elf')],stdout=f,check=True,timeout=30)
    spike=[str(build.SPIKE),'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0','-l','--log-commits',str(PRE/'input.elf')]
    life.save(PRE/'spike-command.json',spike)
    with (PRE/'spike.trace').open('x') as f:subprocess.run(spike,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=120)
    counts=validate(build.parse_spike_commits(PRE/'spike.trace'),symbols,rows)
    life.check(pins)
    for path in PRE.iterdir():pins=life.merge_pins(pins,{str(path):life.digest(path)})
    pre=dict(status='SPIKE_EXACT16_DIVSQRT_PASS_BACKPRESSURE_UNPROVEN',pins=pins,symbols=symbols,counts=counts,
        hypothesis='Natural shared DIVSQRT busy -> valid&&!ready -> capture -> stable STALL -> ready handshake',
        independent_results=True,flags=0,checks=22,baseline=771,coverage_admitted=False,
        scope=SCOPE,toggle_checksum=checksum,typed_targets=targets)
    life.save(PRE/'preflight.json',pre)
    record=dict(case='scalar_fpu_backpressure',pins=life.merge_pins(pins,{str(PRE/'preflight.json'):life.digest(PRE/'preflight.json')}),
        preflight_seal=life.digest(PRE/'preflight.json'),command=command(PRE/'input.elf'),timeout_s=600,
        coverage_admitted=False,automatic_retry=False,rtl_changed=False)
    path=RUN.with_suffix('.prepared.json');life.save(path,record)
    print('PREPARED',life.digest(path),flush=True)


def wave_audit(path):
    parse=FunctionType(wave.vcd.__code__,dict(wave.vcd.__globals__,ROOT='ara_tb',WIDTHS={'clk':1,'rst_n':1}))
    it=iter(parse(path));_,decl=next(it)
    widths={'state_q':1,'flush_i':1,'fpu_valid_i':1,'fpu_ready_o':1,'fpu_in_ready':1,
            'hold_inputs':1,'use_hold':1,'operand_a_d':64,'operand_b_d':64,'operand_a_q':64,'operand_b_q':64}
    require(all(decl.get(signal(n),{}).get('width')==w for n,w in widths.items()), 'Exact probe declarations')
    def value(state,name):
        bits=state.get(decl[signal(name)]['code'],'x')
        require(set(bits)<=set('01'), 'Unknown active probe '+name)
        return int(bits,2)
    pending=None;witnesses=[];stalls=0;released=False
    for time,before,after in it:
        if before.get(decl['ara_tb.clk']['code'])!='0' or after.get(decl['ara_tb.clk']['code'])!='1' or before.get(decl['ara_tb.rst_n']['code'])!='1':continue
        state=value(before,'state_q')
        if released:
            require(state==0,'Accepted held request did not return to READY')
            released=False
        require(value(before,'flush_i')==0,'Unexpected flush during straight-line fixture')
        if pending is not None:
            require(state==1 and value(before,'use_hold')==1 and value(before,'hold_inputs')==0,
                    'Captured request not owned by STALL')
            require([value(before,'operand_a_q'),value(before,'operand_b_q')]==pending['operands'], 'Held operands changed')
            stalls+=1
            if value(before,'fpu_in_ready'):
                require(value(before,'fpu_ready_o')==1,'Missing upstream completion token')
                witnesses.append(dict(pending,release_time=time));pending=None;released=True
        elif state==0 and value(before,'fpu_valid_i') and not value(before,'fpu_in_ready'):
            require(value(before,'hold_inputs')==1 and value(before,'fpu_ready_o')==0,'Missing capture controls')
            pending=dict(capture_time=time,operands=[value(before,'operand_a_d'),value(before,'operand_b_d')])
    require(pending is None,'Unreleased holding transaction')
    return dict(observed=bool(witnesses),captured_released=len(witnesses),stall_cycles=stalls,witnesses=witnesses)


def collect(record):
    require(not QUAL.exists(),'Fresh qualification output')
    pre=life.read_bound(PRE/'preflight.json',record['preflight_seal']);life.check(record['pins'])
    require(json.loads((RUN/'manifest.json').read_text())==record,'Executed manifest differs')
    require(json.loads((RUN/'simulation-status.json').read_text()).get('returncode')==0,'Successful terminal required')
    lines=(RUN/'console.log').read_text().splitlines()
    require(lines.count('Core Test *** SUCCESS ***')==1 and lines.count('BP_PROBE_READY')==1 and
            not any(re.search(r'\b(?:UVM_ERROR|UVM_FATAL)\b(?!\s*:\s*0\s*$)|Error-|BP_PROBE_ERROR',x) for x in lines), 'Terminal error/probe')
    contracts=re.findall(r'\[ARA_CONTRACT\] requests=(\d+) responses=(\d+) exceptions=(\d+) protocol_errors=(\d+) outstanding=(\d+) req_stalled=(\d+) resp_stalled=(\d+)', '\n'.join(lines))
    require(contracts==[('0',)*7], 'Exact zero CVX contract')
    QUAL.mkdir()
    scalar=old.architecture.spike_trace.compare_commit_prefix(PRE/'spike.trace',RUN/'commit_trace.csv',0x80000000,
        terminal_tohost_address=0x80001000,rvfi_store_data_layout='unshifted')
    old.architecture.scalar_exact(scalar,pre['counts']);life.save(QUAL/'scalar-comparison.json',scalar)
    with (RUN/'commit_trace.csv').open() as f:retired=list(csv.DictReader(f))
    require(all(r['event']=='retire' and not int(r['trap']) for r in retired) and
            [int(r['order']) for r in retired]==list(range(len(retired))), 'Complete retire-only prefix')
    memory={}
    for row in retired:
        store=old.architecture.scalar_store(row)
        if store:
            address,data=store
            for i,b in enumerate(data):memory[address+i]=b
    def word(addr,size=8):return sum(memory[addr+i]<<(8*i) for i in range(size))
    symbols=pre['symbols'];rows=cases()
    require([word(symbols['bp_observed']+8*i) for i in range(16)]==[v for r in rows for v in r['expected']], 'Exact native16 results/NaNbox')
    csr=[word(symbols['bp_csr']+8*i) for i in range(5)]
    require(csr==[csr[0],64,64,64,csr[0]], 'Native flags/FCSR/restoration')
    require([word(symbols['g75_result'],4),word(symbols['g75_result']+4,4),word(symbols['num_failed'],4),
             word(symbols['bp_guards']),word(symbols['bp_guards']+8)]==[22,0,0,0x539af02c168be47d,0xce71049af28635bd], 'Native guards/checks')
    with (RUN/'vector_trace.csv').open() as f:require(all(r['event']=='config' for r in csv.DictReader(f)), 'Unexpected vector activity')
    vpd=RUN/'scalar-fpu-backpressure.vpd'
    require(0<vpd.stat().st_size<=64*1024*1024,'Bounded probe size')
    with (QUAL/'converter.log').open('x') as log:
        subprocess.run([str(converter.CONVERTER),str(vpd),str(QUAL/'probe.vcd')],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
    observed=wave_audit(QUAL/'probe.vcd');life.save(QUAL/'backpressure.json',observed)
    with (QUAL/'single-inputs.txt').open('x') as f:f.write(str(life.IMAGE)+'.vdb\n'+str(RUN/'code.vdb')+'\n')
    single=bitmap.collect(QUAL/'single-inputs.txt')
    manifest=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    before=life.read_bound(BASE/'combined-bits.json',manifest['output_pins'][str(BASE/'combined-bits.json')])
    delta=bitmap.delta(before,bitmap.combine(before,single));life.save(QUAL/'raw-four-metric-delta.json',delta)
    # Exact local Toggle union over every admitted member; never infer direction offsets.
    before_t=None;togglepins={}
    for name in before['tests']:
        files=list((Path(name)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(files)==1,'Unique historical Toggle member')
        current,sha=toggle.rows(files[0],[SCOPE]);togglepins[str(files[0])]=sha
        before_t=current if before_t is None else toggle.union(before_t,current)
    files=list((RUN/'code.vdb/snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    require(len(files)==1,'Unique candidate Toggle member')
    sample,sha=toggle.rows(files[0],[SCOPE]);togglepins[str(files[0])]=sha
    after=toggle.union(before_t,sample)
    gain=toggle.gains(before_t,after);life.save(QUAL/'local-toggle-delta.json',gain)
    pins=life.merge_pins(record['pins'],togglepins)
    for path in RUN.rglob('*'):
        if path.is_file():pins=life.merge_pins(pins,{str(path):life.digest(path)})
    life.check(pins)
    life.save(QUAL/'qualification.json',dict(status='ARCHITECTURE_PASS_BACKPRESSURE_OBSERVED' if observed['observed'] else
        'ARCHITECTURE_PASS_NO_BACKPRESSURE_NO_RETRY',baseline=771,input_pins=pins,
        output_pins={str(p):life.digest(p) for p in QUAL.iterdir()},checks=22,scalar_counts=pre['counts'],
        vector_status='UNOBSERVABLE_ZERO_DATA_REQUESTS',backpressure=observed,coverage_admitted=False,
        official_percentage_claimed=False,automatic_retry=False))
    print('QUALIFIED',life.digest(QUAL/'qualification.json'),flush=True)


def run(seal):
    path=RUN.with_suffix('.prepared.json');record=life.read_bound(path,seal)
    require(record['command']==command(PRE/'input.elf') and record['timeout_s']==600 and not RUN.exists(),'Exact fresh command')
    life.run(RUN,record)
    collect(record)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepare',action='store_true');p.add_argument('--run-seal')
    args=p.parse_args();require(bool(args.prepare)!=bool(args.run_seal),'One mode required')
    if args.prepare:prepare()
    else:run(args.run_seal)
