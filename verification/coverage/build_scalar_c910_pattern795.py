"""Finite224 normal FP64 cases, exact integer rounding and software-only preflight."""
import argparse
from fractions import Fraction
from math import isqrt
import json
from pathlib import Path
import subprocess
import build_scalar_div_subnormal794 as reused

life,require,build=reused.life,reused.require,reused.build
BASE=life.OUT/'scalar-div-subnormal-offline-admitted795-parent-20261008-01'
BASE_SHA='4d13a15758c65791a43798467bb63c516d0747d631f6fede476eb63202001660'
APP=life.ROOT/'apps/riscv-tests/isa/rv64uv/scalar_c910_pattern795.c'
PLAN=life.OUT/'scalar-c910-pattern-plan795-agent-20261008-01.json'
PLAN_SHA='d056a44d02a3315a5ad588ffefdabff88f3ecb04fdf8a74e41b1e94493ae9d38'
MASK=(1<<52)-1


def value(bits):
    require(type(bits) is int and 0<=bits<1<<64,'Exact unsigned FP64 word')
    exp=(bits>>52)&2047
    require(0<exp<2047,'Only finite normal operands')
    sig=(1<<52)|(bits&MASK);power=exp-1023-52
    x=Fraction(sig<<max(power,0),1<<max(-power,0))
    return -x if bits>>63 else x


def exponent(x):
    require(x>0,'Positive exact magnitude')
    e=x.numerator.bit_length()-x.denominator.bit_length()
    if x<Fraction(1<<max(e,0),1<<max(-e,0)):e-=1
    return e


def increment(q,nonexact,midpoint,negative,rm):
    require(type(rm) is int and 0<=rm<=4,'Architectural valid RM only')
    if not nonexact:return 0
    return int((midpoint>0 or midpoint==0 and q&1) if rm==0 else
        False if rm==1 else negative if rm==2 else not negative if rm==3 else midpoint>=0)


def encode(q,e,negative):
    if q==1<<53:q>>=1;e+=1
    require((1<<52)<=q<(1<<53) and -1022<=e<=1023,'Normal finite result scope')
    return (int(negative)<<63)|((e+1023)<<52)|(q&MASK)


def gold(a,b,sqrt,rm):
    x=value(a)
    if sqrt:
        require(x>0,'Positive SQRT radicand')
        e=exponent(x)//2;power=2*(52-e)
        scaled=x*Fraction(1<<max(power,0),1<<max(-power,0))
        n,d=scaled.numerator,scaled.denominator
        q=isqrt(n//d);nonexact=q*q*d!=n
        comparison=4*n-d*(2*q+1)**2
        require(q*q*d<=n<(q+1)**2*d,'Independent integer-isqrt bracketing')
        sign=False
    else:
        ratio=x/value(b);sign=ratio<0;ratio=abs(ratio);e=exponent(ratio);power=52-e
        scaled=ratio*Fraction(1<<max(power,0),1<<max(-power,0))
        q,r=divmod(scaled.numerator,scaled.denominator);nonexact=r!=0
        comparison=2*r-scaled.denominator
    q+=increment(q,nonexact,comparison,sign,rm)
    flags=int(nonexact)
    return dict(a=a,b=b,sqrt=bool(sqrt),rm=rm,result=encode(q,e,sign),fflags=flags,fcsr=(rm<<5)|flags)


def cells():
    result=[];tails=(0x155555555555,0x2aaaaaaaaaaa)
    for j in range(64):
        seed=0x5555555555555;shift=j%52
        fraction=(((seed<<shift)|(seed>>(52-shift if shift else 52)))&MASK)^(1<<(j%52))
        for t in range(2):
            a=(t<<63)|((1023+(-32,0,32)[j%3])<<52)|fraction
            b=(1023<<52)|(j<<46)|tails[t]
            result.append(gold(a,b,False,0))
    for j in range(32):
        for parity in range(2):
            tail=(0x1555555555555 if j%2==0 else 0xaaaaaaaaaaaaa)&((1<<47)-1)
            a=((1023+parity)<<52)|(j<<47)|tail
            result.append(gold(a,0x3ff0000000000000,True,0))
    for i,j in enumerate((0,7,15,23,31,39,47,63)):
        e=result[2*j+i%2]
        for rm in range(1,5):result.append(gold(e['a'],e['b'],False,rm))
    require(len(result)==224 and sum(e['sqrt'] for e in result)==64,'Exact160DIV/64SQRT finite matrix')
    return result


def header():
    text='#ifndef __ASSEMBLER__\nstruct pattern_cell { unsigned long a,b,result; unsigned flags,rm,sqrt; };\n'
    text+='static const struct pattern_cell pattern_cells[224] = {\n'
    for e in cells():
        text+='  {0x%016xul,0x%016xul,0x%016xul,%du,%du,%du},\n'%(e['a'],e['b'],e['result'],e['fflags'],e['rm'],e['sqrt'])
    return text+'};\n#endif\n'


def source_evidence():
    base=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    plan=life.read_bound(PLAN,PLAN_SHA)
    p=life.OUT/plan['typed_inventory'];rank=life.read_bound(p,plan['typed_inventory_sha256'])
    require(rank['baseline_seal']==BASE_SHA and sum(map(len,plan['primary']['coordinates'].values()))==90,'Exact795 typed90')
    book=life.read_bound(reused.old.BUILD/'build-source-pins.json',reused.old.SOURCE_SHA)
    pins={str(BASE/'admission-manifest.json'):BASE_SHA,str(PLAN):PLAN_SHA,
        str(p):plan['typed_inventory_sha256'],str(reused.old.BUILD/'build-source-pins.json'):reused.old.SOURCE_SHA}
    for name in ('ct_vfdsu_prepare.v','ct_vfdsu_srt.v','ct_vfdsu_srt_radix16_with_sqrt.v','ct_vfdsu_srt_radix16_bound_table.v','ct_vfdsu_round.v'):
        p=life.ROOT/reused.REL/name;require(life.digest(p)==book[str(p)],'Frozen exact producer');pins[str(p)]=book[str(p)]
    for p,h in rank['input_pins'].items():require(life.digest(Path(p))==h,'Typed795 inventory authority');pins[p]=h
    s=(life.ROOT/reused.REL/'ct_vfdsu_srt.v').read_text()
    require("assign initial_divisor_in[55:0]   = {ex1_divisor[52:0],3'b000};" in s and
        "ex1_div ? initial_divisor_in[55:49]:{7{1'b0}}" in s,'DIV initial selector source')
    e=[x for x in cells()[:128]]
    require({64+((x['b']&MASK)>>46) for x in e}==set(range(64,128)),'All64 legal DIV bound selectors')
    return dict(pins=pins,target=plan['primary'],all64_DIV_selectors=True,
        measured_gain=False,SQRT_later_selector_runtime_unproven=True,direction_order_not_assumed=True)


def validate(commits,symbols):
    commits=list(commits);expected=cells()
    arithmetic=[c for c in commits if c.pc in (symbols['pattern_div_insn'],symbols['pattern_sqrt_insn'])]
    require(len(arithmetic)==224,'All224 arithmetic retirements')
    for commit,e in zip(arithmetic,expected):
        require(commit.pc==symbols['pattern_sqrt_insn' if e['sqrt'] else 'pattern_div_insn'] and
            commit.instruction==(0x5a007153 if e['sqrt'] else 0x1a107153) and commit.fpr_writes=={2:e['result']},
            'Independent exact arithmetic opcode/result owner')
    require(all(c.instruction&3==3 and not c.vector_writes and c.pc!=symbols['trap_fail'] for c in commits),'NoC/vector/trap')
    writes={a:v for c in commits for a,v in c.memory_accesses if v is not None}
    for i,e in enumerate(expected):
        require([writes.get(symbols['pattern_observed']+24*i+8*j) for j in range(3)]==
            [e['result'],e['fflags'],e['fcsr']],'All224 independent results/flags/FCSR')
    require(writes.get(symbols['pattern_csr']) is not None and
        writes[symbols['pattern_csr']]==writes.get(symbols['pattern_csr']+8),'Complete FCSR restoration')
    require([writes.get(symbols['g75_result']),writes.get(symbols['g75_result']+4),
        writes.get(symbols['num_failed']),writes.get(symbols['tohost'])]==[675,0,0,1],'675checks and tohost1')
    return reused.old.architecture.reference_counts(commits,symbols)


def prepare(out):
    require(not out.exists(),'Fresh independent software preflight')
    evidence=source_evidence();pins=evidence['pins'].copy()
    command=json.loads(reused.old.TEMPLATE.read_bytes())
    command=[str(APP) if x.endswith('/vgap99_csr_satp_mprv.c') else str(out/'input.elf')
        if x.endswith('/input.elf') else '-march=rv64gv_zfh_zvfh' if x.startswith('-march=') else x for x in command]
    command+=['-include',str(out/'pattern-gold.h')]
    for p in (APP,Path(__file__).resolve(),Path(__file__).with_name('test_scalar_c910_pattern795.py'),
        Path(reused.__file__).resolve(),reused.old.TEMPLATE,Path(command[0]),build.SPIKE,
        build.LLVM/'llvm-readelf',build.LLVM/'llvm-objdump',life.ROOT/'verification/tests/gap75_start.S',life.ROOT/'verification/tests/gap75.ld'):
        pins[str(p)]=life.digest(p)
    life.check(pins);out.mkdir()
    with (out/'pattern-gold.h').open('x') as f:f.write(header())
    life.save(out/'compile-command.json',command)
    with (out/'build.log').open('x') as f:subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=120)
    symbols={s:build._elf_symbol(out/'input.elf',build.LLVM/'llvm-readelf',s) for s in
        ('tohost','trap_fail','g75_result','num_failed','pattern_observed','pattern_csr','pattern_guards','pattern_div_insn','pattern_sqrt_insn')}
    with (out/'input.disasm').open('x') as f:subprocess.run([str(build.LLVM/'llvm-objdump'),'-d',str(out/'input.elf')],stdout=f,check=True,timeout=30)
    spike=[str(build.SPIKE),'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0','-l','--log-commits',str(out/'input.elf')]
    life.save(out/'spike-command.json',spike)
    with (out/'spike.trace').open('x') as f:subprocess.run(spike,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=120)
    counts=validate(build.parse_spike_commits(out/'spike.trace'),symbols)
    life.save(out/'gold.json',cells());life.save(out/'source-targets.json',evidence);life.check(pins)
    for p in out.iterdir():pins[str(p)]=life.digest(p)
    life.save(out/'preflight.json',dict(status='SPIKE_SCALAR_C910_NORMAL224_INTEGER_GOLD_PASS_NOT_NATIVE',
        baseline=795,baseline_seal=BASE_SHA,pins=pins,symbols=symbols,counts=counts,cells=224,DIV_cells=160,SQRT_cells=64,
        checks=675,target_mutable_capacity=90,native_owners_expected=896,RTL_changed=False,EDA_started=False,
        budget_proposal_s=600,runtime_gain_unproven=True))
    print('SPIKE_PREFLIGHT_PASS',out,life.digest(out/'preflight.json'),counts)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();prepare(a.output.resolve())
