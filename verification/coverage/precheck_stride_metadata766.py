"""Static producer-chain and independent integer golden precheck, never simulation."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import rank_ordinary_rvv_toggle766 as ranking

n=ranking.n;ROOT=ranking.ROOT;OUT=ranking.OUT
RANK=OUT/'ordinary-rvv-toggle-ranking766-agent-20261007-01.json'
RANK_SHA='861293d0d6adb01bdcec1acee8366ff087120d67fca6e7cb9466eeca69713853'
APP=ROOT/'apps/riscv-tests/isa/rv64uv/vgap_stride_metadata_full64.c'
PATTERNS=(0x5555555555555555,0xaaaaaaaaaaaaaaaa,(1<<64)-1,0)


def golden():
    source=bytearray([0xb6]*128);source[64:66]=bytes([0x3c,0x3c])
    stored=bytearray([0x69]*544)
    for r in range(16):stored[32*r+16]=0x3c
    stored[528:530]=bytes([0x3c,0x3c])
    vrf=bytearray([0x5a]*4096);vrf[1024:1026]=bytes([0x3c,0x3c])
    guard=bytes([0x96]*16)
    return dict(source=bytes(source),stored=bytes(stored),vrf_guarded=guard+bytes(vrf)+guard,
                csrs=dict(vl=2,vtype=0,vstart=0,vcsr=0,fcsr=0),checks=605)


def validate(actual):
    expected=golden();n.require(set(actual)==set(expected),'Complete independent oracle regions')
    for key,value in expected.items():n.require(actual[key]==value,'Independent full-region mismatch: '+key)


def addresses(base,vl,stride):
    n.require(0<=vl<=2 and 0<=stride<1<<64,'Bounded host stimulus shape')
    return [(base+i*stride)&((1<<64)-1) for i in range(vl)]


def ring_proof():
    evidence=[]
    for initial in range(4):
        slots=[[] for _ in range(4)];p=initial
        for value in PATTERNS:
            for _ in range(4):slots[p].append(value);p=(p+1)%4
        n.require(all(tuple(values)==PATTERNS for values in slots),'Every possible initial ring pointer')
        for values in slots:
            up=down=0
            for a,b in zip(values,values[1:]):up|=(~a)&b;down|=a&(~b)
            n.require((up&((1<<64)-1))==down==((1<<64)-1),'Complete bit-direction sweep per slot')
        evidence.append(dict(initial_accept_pointer=initial,all_four_slots_all_patterns=True))
    return evidence


def source_contract(dispatcher,load,store,vlsu,package,requester):
    for token in ('ara_req.op     = VLSE;','ara_req.op     = VSSE;','ara_req.stride = acc_req_i.rs2;'):
        n.require(token in dispatcher,'Frozen producer stride assignment')
    n.require(dispatcher.count('ara_req.stride = acc_req_i.rs2;')>=2,'Both load/store producers')
    for text in (load,store):
        n.require('vinsn_queue_d.vinsn[vinsn_queue_q.accept_pnt] = pe_req_i;' in text and
                  'vinsn_queue_d.accept_pnt += 1;' in text,'Full metadata copy and deterministic ring advance')
    n.require(re.search(r'VlduInsnQueueDepth\s*=\s*4\s*;',package) and
              re.search(r'VstuInsnQueueDepth\s*=\s*4\s*;',package),'Exact four-slot depths')
    n.require(vlsu.count('.pe_req_i')>=3 and 'pe_req_i.op != VQBEXEC && !pe_req_is_akv' in vlsu,
              'Ordinary instruction ownership gate')
    n.require("default: '0 // this is a read operation" in requester,'Read-request payload zeros are not data stimulus targets')


def prepare(out):
    n.require(out.parent==OUT and not out.exists(),'Fresh source/host precheck output')
    n.require(n.digest(RANK)==RANK_SHA,'Exact766 ranking seal')
    rank=json.loads(RANK.read_bytes());config=json.loads(ranking.CONFIG.read_bytes())
    pins=dict(rank['pins']);bookpath=OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
    n.require(n.digest(bookpath)==config['pins'][str(bookpath)],'Frozen source ledger bound')
    book=json.loads(bookpath.read_bytes());pins[str(bookpath)]=n.digest(bookpath)
    specs=[('hardware/src/ara_dispatcher.sv','verification/out/old-image-source-evidence-20261006-01/ara_dispatcher.sv'),
        ('hardware/src/vlsu/vldu.sv',None),('hardware/src/vlsu/vstu.sv',None),('hardware/src/vlsu/vlsu.sv',None),
        ('hardware/include/ara_pkg.sv',None),('hardware/src/lane/operand_requester.sv',None)]
    texts=[]
    for rel,snapshot in specs:
        p=ROOT/(snapshot or rel);n.require(n.digest(p)==book[str(ROOT/rel)]==config['pins'][str(p)],'Frozen source/snapshot binding')
        pins[str(p)]=n.digest(p);texts.append(p.read_text())
    source_contract(*texts);ring=ring_proof();validate(golden())
    n.require(all(addresses(0x80010040,1,p)==[0x80010040] for p in PATTERNS),'Legal base-only real accesses')
    target_scopes=[r for r in rank['scopes'] if r['scope'].endswith(('.i_vldu','.i_vstu'))]
    targets=[]
    for r in target_scopes:
        for x in r['objects']:
            if re.fullmatch(r'vinsn_queue_[dq]\.vinsn\[[0-3]\]\.stride',x['name']):
                n.require(x['logical_bits']==64 and x['left']=='63' and x['right']=='0','Exact queue stride declaration')
                n.require(not any(g['scope']==r['scope'] and x['name'] in g['targets'] for g in config['toggle_groups']),
                          'Do not target an existing exclusion')
                targets.append(dict(scope=r['scope'],checksum=r['checksum'],**x))
    n.require(len(targets)==14,'Exact remaining queue fields: three load slots plus four store slots, d/q')
    for p in (APP,Path(__file__).resolve(),Path(__file__).with_name('test_precheck_stride_metadata766.py')):
        pins[str(p)]=n.digest(p)
    clang=Path('/usr/bin/clang').resolve();objdump=Path('/usr/bin/llvm-objdump').resolve()
    n.require('Terapines' not in str(clang) and 'ZCC' not in str(clang),'Non-ZCC LLVM only')
    pins[str(clang)]=n.digest(clang);pins[str(objdump)]=n.digest(objdump)
    for p,h in pins.items():n.require(n.digest(p)==h,'End-of-precheck drift')
    out.mkdir()
    cmd=[str(clang),'--target=riscv64-unknown-elf','-march=rv64gcv_zfh','-mabi=lp64d','-O2',
         '-ffreestanding','-fno-vectorize','-fno-slp-vectorize','-c',str(APP),'-o',str(out/'app.o')]
    run=subprocess.run(cmd,capture_output=True,text=True,timeout=60)
    (out/'compile.log').write_text(run.stdout+run.stderr);n.require(run.returncode==0,'Actual LLVM source/assembler precheck')
    dis=subprocess.run([str(objdump),'-d',str(out/'app.o')],capture_output=True,text=True,check=True)
    (out/'app.disassembly.txt').write_text(dis.stdout)
    n.require('vlse8.v' in dis.stdout and 'vsse8.v' in dis.stdout and 'vs1r.v' in dis.stdout,'Actual target/snapshot opcodes')
    pins[str(out/'app.o')]=n.digest(out/'app.o');pins[str(out/'app.disassembly.txt')]=n.digest(out/'app.disassembly.txt')
    return dict(status='SOURCE_AND_HOST_ORACLE_PRECHECK_PASS_NOT_SPIKE_OR_DUT',baseline=766,pins=pins,
        ranking_seal=RANK_SHA,case='vgap_stride_metadata_full64',commands=cmd,
        targets=targets,conditional_expected_new_serialized_slots=sum(t['missing_slots'] for t in targets),
        measured_gain=None,official_percentage=False,ring_induction=ring,
        operations='16 VL1 strided loads and16 VL1 strided stores; four complete64bit patterns each visit every ring slot; '
                   'one legal VL2 unit-stride recovery; no fault/no-op/force or unsupported-address access.',
        oracle_regions={k:len(v) for k,v in golden().items() if isinstance(v,bytes)},
        software_checks=605,csr_expected=golden()['csrs'],
        gain_assumptions='Actual decoded stride must remain full64 and every instruction must be accepted normally; '
                         'cycle data and actual VDB must confirm. A simulation failure is retained, never admitted.',
        budget_seconds=600,budget_basis='34 single-element memory operations plus one full4096byte VRF snapshot '
            'and605 word/CSR checks, no long DIV/FP/custom engine; actual Spike retirement count required before authorization.',
        historical_dedup='Existing vls has small strides3/4/8/40 and negative4, vss positive3/4/8/16; mask-full-width '
            'is integer add/compare/gather. Actual766 still has these14 queue fields unhit, rejecting claimed prior complete full64-per-slot sweep. '
            'ELF duplicate check remains pending: object-only precheck is not an executable preflight.',
        no_ELF_built=True,Spike_run=False,VCS_launched=False,DVE_launched=False)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();value=prepare(out)
    with (out/'precheck.json').open('x') as s:json.dump(value,s,indent=2);s.write('\n')
    print('SOURCE_HOST_READY',n.digest(out/'precheck.json'),value['conditional_expected_new_serialized_slots'])
