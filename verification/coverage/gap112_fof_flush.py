"""Compact GAP112 software preflight / reviewed 180s old-image runner; no retry."""
import argparse
import inspect
import json
import re
import shutil
from pathlib import Path
import subprocess
from types import SimpleNamespace

import build_opivx_vsbc_preflight as shared
import collect_opivx_vsbc_strict as strict
import run_pure_war_simulation as frozen
from closure_point_inventory import read_xml

life, require = shared.life, shared.require
ROOT, OUT = life.ROOT, life.OUT
NAME = 'vgap112_fof_flush_csr'
APP = ROOT / 'apps/riscv-tests/isa/rv64uv' / (NAME + '.c')
START = ROOT / 'verification/tests/gap112_start.S'
BASE = OUT / 'queue-mask-offline-admitted-740-agent-20261007-01'
BASE_SEAL = '752d493c5fa8179ddd414d7810da479b1a56341a1600dff56c5b5afa0a3304b5'
IMAGE_SHA = '2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3'
FROZEN_SHA = '2e7ded5ac7c1caeff20a0d1febbb7123dbd30973a9fdef0435ad051673e11626'
BUILD = OUT / 'repaired-aligned-build-20260930-01'
SOURCE = OUT / 'old-image-source-evidence-20261006-01/ara_dispatcher.sv'
SCOPE = 'ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher'
RAM = '-m0x80000000:0x200000'
BUDGET = 180
CHECKS = 194
COMPILED = OUT/'gap112-fof-flush-preflight-740-agent-20261007-01'
COMPILED_ELF_SHA = '764a60091be4ccb9c876fda5b5013ed377846385c8f3dd35f72157965bd0e8ec'
G0, G1, WORD = 0x13579bdf, 0x2468ace0, 0x12345678
NAMES = ('gf_source', 'gf_div', 'gf_neighbor', 'gf_prefix', 'gf_segment', 'gf_field0', 'gf_field1',
         'gf_csr', 'g75_result', 'num_failed', 'g75_trap', 'trap_fail', 'tohost',
         'gf_long_div', 'gf_fof', 'gf_read_vl', 'gf_recovery')


def expected():
    return dict(gf_source=[G0]+[1000+17*i for i in range(64)]+[G1],
        gf_div=[G0]+[(1000+17*i)//3 for i in range(64)]+[G1],
        gf_neighbor=[G0]+[0x89abc000+i for i in range(32)]+[G1],
        gf_prefix=[G0, WORD, G1], gf_segment=[0x77000000+i for i in range(8)],
        gf_field0=[G0]+[0x77000000+2*i for i in range(4)]+[G1],
        gf_field1=[G0]+[0x77000001+2*i for i in range(4)]+[G1], gf_csr=[1, 0, 4, 0])


def validate(commits, symbols):
    require(not any(c.pc == symbols['trap_fail'] for c in commits), 'Unexpected trap')
    memory = {a: v for c in commits for a, v in c.memory_accesses if v is not None}
    for name, values in expected().items():
        require([memory.get(symbols[name]+4*i) for i in range(len(values))] == values,
                'Independent memory/source/guard/CSR mismatch: '+name)
    require(memory.get(0x801ffffc) == WORD and memory.get(symbols['g75_result']) == CHECKS and
            memory.get(symbols['g75_result']+4) == memory.get(symbols['num_failed']) == 0,
            'Full selfcheck/boundary signature differs')
    require(all(memory.get(symbols['g75_trap']+i) == 0 for i in (0, 8, 16)), 'Trap ledger differs')
    require([v for c in commits for a, v in c.memory_accesses
             if a == symbols['tohost'] and v is not None] == [1], 'Exact successful tohost required')
    pair = [c for c in commits if c.pc in (symbols['gf_fof'], symbols['gf_read_vl'])]
    require(len(pair) == 2 and pair[0].pc == symbols['gf_fof'] and
            pair[1].pc == pair[0].pc+4 and pair[0].instruction & 127 == 7 and
            pair[0].instruction >> 25 & 1 == 0 and pair[0].instruction >> 20 & 31 == 16 and
            pair[1].instruction >> 20 == 0xc20, 'Exact masked FOF/immediate VL read differs')
    return dict(status='GAP112_INDEPENDENT_SOFTWARE_ORACLE_PASS_NOT_DUT', checks=CHECKS,
        defined_array_bytes=sum(len(v)*4 for v in expected().values()), traps=0,
        fof_reduced_VL=1, vstart=0, division_elements=64, non_destination_v10_elements=32,
        destination_prestart_elements=0, fof_tail_comparison='NOT_UNIQUELY_DEFINED_NOT_REQUIRED',
        raw78_hit_claimed=False)


def binding():
    pins = {}
    def pin(path, sha=None):
        path = Path(path); actual = life.digest(path)
        require(sha is None or actual == sha, 'Frozen input drift: '+str(path))
        pins[str(path)] = actual
        return path
    manifest = life.read_bound(BASE/'admission-manifest.json', BASE_SEAL)
    pin(BASE/'admission-manifest.json', BASE_SEAL)
    bits = json.loads(pin(BASE/'combined-bits.json', manifest['output_pins'][str(BASE/'combined-bits.json')]).read_bytes())
    require(len(bits['tests']) == len(set(bits['tests'])) == 740, 'Exact formal740 required')
    command = pin(BUILD/'compile.command.json', '30cdd93809c183f5004767d6190ca33d1d78aed68e73dcf42d6fef793269cbb1')
    require('sim_l2_mb=2' in json.loads(command.read_bytes())['command'], 'Frozen2MiB RAM required')
    book = json.loads(pin(BUILD/'build-source-pins.json',
        '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b').read_bytes())
    pin(SOURCE, book[str(ROOT/'hardware/src/ara_dispatcher.sv')])
    for relative in ('hardware/src/segment_sequencer.sv','hardware/tb/ara_tb.sv','hardware/src/ara_soc.sv'):
        pin(ROOT/relative, book[str(ROOT/relative)])
    text = SOURCE.read_text()
    require('state_q == WAIT_IDLE_FLUSH && lsu_ex_state_q == LSU_FLUSH_DONE' in text and
            'if (state_qq != WAIT_IDLE) begin\n              state_d = WAIT_IDLE;' in text and
            'if (!ara_req.vm) begin\n                  state_d = WAIT_IDLE_FLUSH;' in text,
            'FOF/flush/CSR source gate drift')
    require("eew_valid_q          <= '0;" in text and
            'active_group_needs_reshuffle |= eew_valid_q[base + r] &&' in text,
            'Initial invalid EEW gate drift')
    for rel, sha in bits['design'].items(): pin(Path(str(life.IMAGE)+'.vdb/snps/coverage/db')/rel, sha)
    row = bits['metrics']['fsm'][SCOPE]
    require((row['width'],row['checksum']) == (92,'1099616778'), 'Dispatcher FSM shape differs')
    vector = format(int(row['bits'],16),'092b'); require(vector[78]=='0','Raw78 no longer fresh')
    shape = read_xml(Path(str(life.IMAGE)+'.vdb/snps/coverage/db/shape/fsm.verilog.shape.xml'))
    definition = next(x for x in shape.iter('fsmdef') if x.get('chksum')==row['checksum'])
    coordinates=[]
    for f in definition.iter('fsmfsm'):
        states=f.findall('state'); names={x.get('id'):x.get('name') for x in states}
        for x in states: coordinates.append(dict(kind='state',name=x.get('name')))
        for x in f.findall('transition'):
            coordinates.append(dict(kind='transition',source=names[x.get('fromid')],
                destination=names[x.get('toid')],attributes=dict(x.attrib)))
    target=coordinates[78]
    require(len(coordinates)==92 and target['source']=='WAIT_IDLE_FLUSH' and
            target['destination']=='WAIT_IDLE' and target['attributes']['line']=='1752', 'Exact compiled raw78 differs')
    target.update(scope=SCOPE,raw_index=78,width=92,checksum=row['checksum'],before=False,
        full_before_vector=vector,source_assignment_line=4634,
        compiled_line_is_shared_state_encoding_not_local_assignment=True,
        hypothesis='Independent DIV keeps idle low while maskedFOF completes; immediate CSR awaits FLUSH_DONE decode')
    return pins,target


def rvv_inventory(dis):
    rvv=[]
    for line in dis.splitlines():
        match=re.match(r'\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+',line)
        if not match:continue
        word=int(match[2],16)
        if word&127==0x57 or word&127 in (7,39) and word>>12&7 in (0,5,6,7):
            rvv.append((int(match[1],16),word))
    return rvv


def build(out,reuse=False):
    require(out.parent==OUT and out.resolve()==out and not out.exists(),'Fresh preflight required')
    pins,target=binding(); plan=life.read_bound(life.PLAN,life.PLAN_SEAL)
    require(plan['simv']==str(life.IMAGE) and len(plan['image'])==66 and
            plan['image'][str(life.IMAGE)]==IMAGE_SHA,'Frozen runtime66 differs')
    pins=life.merge_pins(pins,plan['image'])
    files=[APP,START,ROOT/'verification/tests/gap75.ld',Path(__file__).resolve(),
        Path(__file__).with_name('test_gap112_fof_flush.py'),Path(frozen.__file__).resolve(),
        ROOT/'verification/tests/gap112_fof_flush_review.txt',
        Path(shared.__file__).resolve(),Path(strict.__file__).resolve(),shared.LLVM/'clang',
        shared.LLVM/'ld.lld',shared.LLVM/'llvm-readelf',shared.LLVM/'llvm-objdump',shared.SPIKE,Path('/usr/bin/cc').resolve()]
    files+=list((ROOT/'verification/ara_verify').glob('*.py'))
    pins=life.merge_pins(pins,{str(f):life.digest(f) for f in files})
    if reuse:
        require(life.digest(COMPILED/'input.elf')==COMPILED_ELF_SHA and
                life.digest(COMPILED/'compile-command.json')=='26e5c13cbe547c0d3ccdd6f53d8ad9818cd8a950fd8880401f594d5fc4edee3f' and
                life.digest(COMPILED/'host')=='992ef36a1508e62611c5b8d0efe728e844bd70b7ec3a4de463dd9b1661df5e42',
                'Exact existing compiled fixture required')
        for name in ('input.elf','compile-command.json','compile.log','host','host.log','failure.json'):
            pins[str(COMPILED/name)]=life.digest(COMPILED/name)
    pins=life.merge_pins(pins,{str(life.PLAN):life.PLAN_SEAL});life.check(pins)
    out.mkdir();life.save(out/'target-before.json',target)
    try:
        host=['/usr/bin/cc','-std=c11','-Wall','-Wextra','-Werror','-DG112_HOST',str(APP),'-o',str(out/'host')]
        if reuse:
            shutil.copyfile(COMPILED/'host',out/'host');(out/'host').chmod(0o755)
        with (out/'host.log').open('x') as log:
            if not reuse:subprocess.run(host,check=True,stdout=log,stderr=log,timeout=30)
            subprocess.run([str(out/'host')],check=True,stdout=log,stderr=log,timeout=10)
        command=[str(shared.LLVM/'clang'),'--target=riscv64-unknown-elf','-march=rv64gcv_zfh_zvfh',
            '-mabi=lp64d','-mcmodel=medany','-mno-relax','-msmall-data-limit=0','-O2',
            '-mno-implicit-float','-fno-vectorize','-fno-slp-vectorize','-fno-unroll-loops','-ffreestanding',
            '-fuse-ld=lld','-nostdlib','-T',str(ROOT/'verification/tests/gap75.ld'),str(START),str(APP),'-o',str(out/'input.elf')]
        if reuse:
            shutil.copyfile(COMPILED/'input.elf',out/'input.elf')
            shutil.copyfile(COMPILED/'compile-command.json',out/'compile-command.json')
            shutil.copyfile(COMPILED/'compile.log',out/'compile.log')
        else:
            life.save(out/'compile-command.json',command)
            with (out/'compile.log').open('x') as log:subprocess.run(command,check=True,stdout=log,stderr=log,timeout=90)
        symbols={n:shared._elf_symbol(out/'input.elf',shared.LLVM/'llvm-readelf',n) for n in NAMES}
        require(symbols['gf_read_vl']==symbols['gf_fof']+4 and max(symbols.values())<0x801fe000,'ELF/stack/witness separation differs')
        dis=subprocess.check_output([str(shared.LLVM/'llvm-objdump'),'-d',str(out/'input.elf')],text=True,timeout=30)
        rvv=rvv_inventory(dis)
        require(len(rvv)==17,'Exact17 explicit RVV instructions; implicit lowering forbidden')
        life.save(out/'linked-proof.json',dict(symbols=symbols,RVV_opcodes=rvv,stack=0x801ff000,boundary=0x801ffffc))
        command=[str(shared.SPIKE),'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0',RAM,'-l','--log-commits',str(out/'input.elf')]
        life.save(out/'spike-command.json',command)
        with (out/'spike.trace').open('x') as log,(out/'spike.stdout').open('x') as stdout:
            subprocess.run(command,check=True,stdout=stdout,stderr=log,timeout=60)
        commits=shared.parse_spike_commits(out/'spike.trace');result=validate(commits,symbols)
        counts=strict.reference_counts(commits,symbols)
        life.save(out/'validation.json',result);life.save(out/'symbols.json',symbols)
        life.check(pins)
        pins=life.merge_pins(pins,{str(f):life.digest(f) for f in out.iterdir() if f.is_file()})
        life.save(out/'preflight-manifest.json',dict(status='GAP112_HOST_SPIKE_PREFLIGHT_PASS_NOT_DUT',
            input_elf=str(out/'input.elf'),elf_sha256=life.digest(out/'input.elf'),pins=pins,
            symbols=symbols,validation=result,reference_counts=counts,target=target,baseline=740,
            baseline_seal=BASE_SEAL,VCS_started=False,coverage_admitted=False,
            compiled_fixture_reused=reuse,ELF_rebuilt=not reuse))
        print(json.dumps(dict(output=str(out),seal=life.digest(out/'preflight-manifest.json'),validation=result,reference_counts=counts)))
    except Exception as exc:
        life.save(out/'failure.json',dict(status='PREFLIGHT_FAILED_NOT_DUT',reason=str(exc)));raise


def prepared(out,prepath,seal):
    require(out.parent==OUT and out.resolve()==out and not out.exists(),'Fresh run required')
    p=life.read_bound(prepath,seal)
    require(p['status']=='GAP112_HOST_SPIKE_PREFLIGHT_PASS_NOT_DUT' and
            p['baseline_seal']==BASE_SEAL and p['VCS_started'] is False and p['coverage_admitted'] is False,'Exact preflight required')
    life.check(p['pins']);require(life.digest(Path(frozen.__file__))==FROZEN_SHA,'Frozen lifecycle drift')
    require(p['target']==binding()[1],'Current740 source/target drift')
    result=validate(shared.parse_spike_commits(prepath.parent/'spike.trace'),p['symbols'])
    require(result==p['validation'],'Complete software replay differs')
    command=[str(life.IMAGE),'-l','run.vcs.log','+NO_FSDB','+ntb_random_seed=1',
        '+PRELOAD='+p['input_elf'],'+TESTCASE='+NAME,'+COMMIT_TOHOST=80001000',
        '+COMMIT_TRACE='+str(out/'commit_trace.csv'),'+VECTOR_TRACE='+str(out/'vector_trace.csv'),
        '+ARA_DEBUG_SEGMENT','-cm','line+cond+fsm+tgl+branch','-cm_dir',str(out/'code.vdb'),'-cm_name',NAME]
    pins=life.merge_pins(p['pins'],{str(prepath):seal})
    return dict(case=NAME,output=str(out),command=command,pins=pins,timeout_s=180,
        image_sha256=IMAGE_SHA,elf_sha256=p['elf_sha256'],preflight=str(prepath),preflight_seal=seal,
        old_image_files_checked=66,software_checks=CHECKS,target=p['target'],foreground_lifetime=True,
        automatic_retry=False,coverage_admitted=False,admission_performed=False,terminal_oracle_verified=False,
        systemd_policy=dict(RuntimeMaxSec=240,TimeoutStopSec=10,KillMode='control-group'),
        qualification_required='Full scalar/native-vector/lifecycle plus FOF set-valued tail; raw78 must be measured, not assumed')


def namespace(prepath,p,record):
    require(life.digest(Path(frozen.__file__))==FROZEN_SHA,'Frozen lifecycle drift')
    ns=dict(frozen.__dict__)
    ns.update(PRE=prepath.parent,ELF_SEAL=p['elf_sha256'],BUDGET=180,IMAGE_SEAL=IMAGE_SHA,
              preflight=SimpleNamespace(NAME=NAME),command=lambda out:record['command'])
    exec(compile(inspect.getsource(frozen.run),str(Path(__file__))+':frozen-foreground','exec'),ns)
    return ns


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode',choices=('build','prepare','verify','run'))
    ap.add_argument('--output',type=Path,required=True);ap.add_argument('--preflight',type=Path)
    ap.add_argument('--seal');ap.add_argument('--prepared-seal');ap.add_argument('--parent-authorized',action='store_true')
    ap.add_argument('--reuse-compiled',action='store_true')
    a=ap.parse_args();out=a.output.absolute()
    if a.mode=='build':
        require(not(a.preflight or a.seal or a.prepared_seal or a.parent_authorized),'Build is software-only')
        build(out,a.reuse_compiled);return
    require(not a.reuse_compiled,'Reuse is software-build-only')
    require(a.preflight and a.seal and (a.mode!='prepare')==bool(a.prepared_seal) and
            (a.mode=='run')==a.parent_authorized,'Exact preflight and separate run authorization required')
    prepath=a.preflight.absolute();record=prepared(out,prepath,a.seal)
    sidecar=out.with_name(out.name+'.prepared.json')
    if a.mode=='prepare':
        require(not sidecar.exists(),'No duplicate prepare');life.save(sidecar,record)
        print(json.dumps(dict(prepared=str(sidecar),seal=life.digest(sidecar),timeout_s=180)));return
    require(life.read_bound(sidecar,a.prepared_seal)==record,'Reviewed sidecar drift')
    if a.mode=='verify':print('GAP112_PREPARED_VERIFY_PASS_NO_VCS')
    else:namespace(prepath,life.read_bound(prepath,a.seal),record)['run'](out,record)


if __name__=='__main__':main()
