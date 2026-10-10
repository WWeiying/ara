"""Software-only preparation and separately authorized frozen-image Gather WAR run."""
import argparse
import copy
import json
from pathlib import Path
import re
import subprocess
import sys
from types import FunctionType, ModuleType, SimpleNamespace
import xml.etree.ElementTree as ET

import preflight_vsmul_saturation796 as template
import collect_vsmul_saturation796 as mature
import run_pure_war_simulation as worker
import coverage_bitmap_delta as bitmap
import targeted_toggle_evidence_v2 as toggle
from rank_cva6_scalar_data767 import typed_nodes
from report_global777_compact import semantic
from collect_c910_float_edge_initialized777 import coverage_identity

life, require, build = template.life, template.require, template.build
ROOT, OUT = life.ROOT, life.OUT
APP = ROOT/'apps/riscv-tests/isa/rv64uv/vgather_war797.c'
BASE = OUT/'vsmul-saturation-offline-admitted797-parent-20261008-01'
BASE_SHA = '775485fa0a5cfbb8bb1715374e60d3228d341522b2df3c666754407b30ef55f4'
REPORT = OUT/'current-population797-inherited796-agent-20261008-01'
REPORT_SHA = '1ebc05103bc71ee6ec26d97e51ed4867fed3d35a21ee38490956c3ccadf2c5c6'
NAME, BUDGET, CHECKS = 'vgather_war797', 300, 3192
IMAGE_SHA = '2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3'
GUARD = template.GUARD
ROLES = ('gw_load_source','gw_load_index','gw_gather','gw_overwrite',
         'gw_store_index','gw_store_gather','gw_store_overwrite')
NAMES = ('tohost','num_failed','g75_result','trap_fail','gw_checks','gw_source',
         'gw_snapshot','gw_csr') + ROLES
SCOPE = 'ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_vldu'


def case(c):
    require(type(c) is int and 0 <= c < 4, 'Exact four rounds')
    src = bytes((37*i+19+41*c) % 256 for i in range(1024))
    idx = bytes((255-i) % 256 if c % 2 == 0 else
                (255-((i//4)*73+c*17) % 256) for i in range(1024))
    mem = bytes((91*i+0x83+29*c) % 256 for i in range(1024))
    return dict(sources=[src,idx,mem], snapshots=[idx,bytes(src[i] for i in idx),
                bytes(mem[i] for i in idx)], csr=[1024,1024,3,0,0,0])


def image(data):
    return GUARD.to_bytes(8,'little')*2 + data + GUARD.to_bytes(8,'little')*2


def header():
    array = lambda data: '{'+','.join(hex(v)+'ULL' for v in template.words(data))+'}'
    cube = lambda key: '{'+','.join('{'+','.join(array(image(d)) for d in case(c)[key])+'}' for c in range(4))+'}'
    return ('#include <stdint.h>\n#define GW_GUARD UINT64_C('+hex(GUARD)+')\n'
        'volatile uint64_t gw_source[4][3][132] __attribute__((aligned(128))) = '+cube('sources')+';\n'
        'static const uint64_t gw_source_gold[4][3][132] = '+cube('sources')+';\n'
        'static const uint64_t gw_snapshot_gold[4][3][132] = '+cube('snapshots')+';\n'
        'static const uint64_t gw_csr_gold[6] = {1024,1024,3,0,0,0};\n')


def baseline():
    base = life.read_bound(BASE/'admission-manifest.json', BASE_SHA)
    require(base['coverage_admitted'] is True, 'Formal797 authority')
    paths = [BASE/n for n in ('combined-inputs.txt','combined-bits.json','combined-toggle-bits.json')]
    pins = {str(p):base['output_pins'][str(p)] for p in paths}
    life.check(pins)
    ledger = paths[0].read_text().splitlines()
    before, tgl = (json.loads(p.read_bytes()) for p in paths[1:])
    require(len(ledger)==len(set(ledger))==798 and before['tests']==ledger[1:] and len(tgl)==2989,
            'Exact797 prefix and2989 Toggle scopes')
    require({m:len(v) for m,v in before['metrics'].items()}==dict(line=1892,cond=2023,branch=2155,fsm=92), 'Full6162 metrics')
    pins[str(BASE/'admission-manifest.json')] = BASE_SHA
    for rel,h in before['design'].items():
        pins[str(Path(ledger[0])/'snps/coverage/db'/rel)] = h
    life.check(pins)
    return before,tgl,ledger,pins


def targets():
    before,rows,ledger,pins = baseline()
    bookpath = OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
    book = life.read_bound(bookpath,'6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b')
    pins[str(bookpath)] = life.digest(bookpath)
    for rel in ('hardware/src/ara_sequencer.sv','hardware/src/vlsu/vldu.sv','hardware/include/ara_pkg.sv'):
        pins[str(ROOT/rel)] = book[str(ROOT/rel)]
    slide = OUT/'old-image-source-evidence-20261006-01/sldu.sv'
    pins[str(slide)] = book[str(ROOT/'hardware/src/sldu/sldu.sv')]
    shape = Path(ledger[0])/'snps/coverage/db/shape/tgl.verilog.shape.xml'
    definitions = [d for d in toggle.xml(shape).findall('tgldef') if d.get('chksum')==rows[SCOPE]['checksum']]
    require(len(definitions)==1, 'Unique native target definition')
    nodes,_ = typed_nodes(ET.tostring(definitions[0],encoding='unicode'), rows[SCOPE])
    q = life.read_bound(REPORT/'qualification.json',REPORT_SHA)
    el = REPORT/'combined.el'; pins[str(REPORT/'qualification.json')] = REPORT_SHA
    pins[str(el)] = '2704de24f115e289d8c1e60c3847dc39d7f7d13e955eb284ddc66f6fd42596c9'; life.check(pins)
    opaque,masks = semantic(el.read_text())
    require(not any(r[3]=='WHOLE_SCOPE' and (SCOPE==r[0] or SCOPE.startswith(r[0]+'.')) for r in opaque), 'Target whole-scope EL overlap')
    result=[]
    names={'vinsn_issue_d.hazard_wait_complete','vinsn_issue_q.hazard_wait_complete',
           'vinsn_commit.hazard_wait_complete'} | {
           'vinsn_queue_%s.vinsn[%d].hazard_wait_complete'%(dq,slot) for dq in ('d','q') for slot in range(4)}
    for n in nodes:
        if n['name'] not in names: continue
        require(n['logical_width']==8 and n['missing_slots']==16 and
                not any(k[0]==SCOPE and (k[2]==n['name'] or n['name'].startswith(k[2]+'.')) for k in masks), 'All16 raw zeros/no field EL')
        result.append(dict(scope=SCOPE,name=n['name'],checksum=rows[SCOPE]['checksum'],
                           raw_coordinates=n['missing_coordinates'],compiled_attributes=n))
    require(len(result)==11 and sum(len(t['raw_coordinates']) for t in result)==176, 'Exact797 target capacity')
    life.check(pins)
    return result,pins


def expected_footprint(symbols):
    wanted={}
    def add(name,data): wanted.update({symbols[name]+i:v for i,v in enumerate(data)})
    add('gw_source',b''.join(image(d) for c in range(4) for d in case(c)['sources']))
    add('gw_snapshot',b''.join(image(d) for c in range(4) for d in case(c)['snapshots']))
    add('gw_csr',b''.join(v.to_bytes(8,'little') for c in range(4) for v in case(c)['csr']))
    reads=set(wanted)
    add('g75_result',CHECKS.to_bytes(4,'little')+bytes(4)); add('num_failed',bytes(4))
    add('gw_checks',CHECKS.to_bytes(4,'little'))
    return wanted,reads


def validate(trace,symbols):
    commits=build.parse_spike_commits(trace)
    require('exception ' not in trace.read_text() and not any(c.pc==symbols['trap_fail'] for c in commits), 'Unexpected Spike trap')
    require(symbols['gw_overwrite']==symbols['gw_gather']+4, 'Exact adjacent pair')
    events={n:[] for n in ROLES}; observed={}; reads=set(); terminal=[]
    wanted,required=expected_footprint(symbols)
    for c in commits:
        for n in events:
            if c.pc==symbols[n]: events[n].append(c)
        access=mature.common.scalar_memory(c.instruction)
        for a,v in c.memory_accesses:
            if v is not None:
                width=access[1] if access else 1
                require(access is not None or c.instruction&127==39, 'Known memory writer')
                require(not symbols['gw_source']<=a<symbols['gw_source']+12672, 'Immutable source/guards')
                for i in range(width):
                    if a+i in wanted:observed[a+i]=v>>(8*i)&255
                if a==symbols['tohost']:terminal.append(v)
            elif access and access[0]=='read':
                require(len(c.gpr_writes)==1, 'Observable scalar read')
                v=next(iter(c.gpr_writes.values()))
                for i in range(access[1]):
                    if a+i in wanted:observed[a+i]=v>>(8*i)&255;reads.add(a+i)
    require(observed==wanted and required<=reads and terminal==[1], 'Independent full source/guards/snapshots/CSR/check oracle')
    require(all(len(v)==4 for v in events.values()), 'Four rounds every RVV role')
    for r in range(4):
        gold=case(r)
        for n,reg,data in [('gw_load_source',8,gold['sources'][0]),('gw_load_index',0,gold['sources'][1]),
                           ('gw_gather',16,gold['snapshots'][1]),('gw_overwrite',8,gold['snapshots'][2])]:
            c=events[n][r]
            expected={reg+i:int.from_bytes(data[i*128:(i+1)*128],'little') for i in range(8)}
            require(c.vector_writes==expected and c.vector_vstart==0 and c.vector_vl==1024 and c.vector_sew==8, 'Every full8-register writer/context')
        g,l=events['gw_gather'][r],events['gw_overwrite'][r]
        require(g.instruction&127==87 and g.instruction>>26==12 and g.instruction>>25&1==1 and
                g.instruction>>7&31==16 and g.instruction>>15&31==0 and g.instruction>>20&31==8 and
                l.instruction&127==7 and l.instruction>>26&3==1 and l.instruction>>7&31==8 and
                l.instruction>>20&31==0, 'Exact unmasked Gather/indexed-load tuple')
        gi=commits.index(g);require(commits[gi+1]==l, 'No intervening retirement at pair')
    require(sum(bool(c.vector_writes) for c in commits)==16, 'Only16 explicit full-group writers')
    return dict(checks=CHECKS,rounds=4,vector_writers=16,primary_bytes=16384,
                source_guard_bytes=12672,snapshot_guard_bytes=12672,CSR_values=24,retirements=len(commits))


def module_pins():
    modules=[sys.modules[__name__],template,mature,worker,bitmap,toggle];seen=set();pins={}
    while modules:
        m=modules.pop()
        if id(m) in seen:continue
        seen.add(id(m));f=getattr(m,'__file__',None)
        if f:
            p=Path(f).resolve()
            if p.suffix=='.py' and ROOT/'verification' in p.parents:
                pins[str(p)]=life.digest(p)
                modules.extend(v for v in vars(m).values() if isinstance(v,ModuleType))
    p=Path(__file__).with_name('test_gather_war797.py').resolve();pins[str(p)]=life.digest(p)
    return pins


def preflight(out):
    require(out.parent==OUT and not out.exists(), 'Fresh preflight only')
    ts,pins=targets();t=template.shared.template
    command=json.loads(t.TEMPLATE.read_bytes())
    require(sum(a.endswith('/vgap99_csr_satp_mprv.c') for a in command)==1, 'Exact compile template app')
    command=[str(APP) if a.endswith('/vgap99_csr_satp_mprv.c') else str(out/'input.elf') if a.endswith('/input.elf') else a for a in command]
    command+=['-I'+str(out),'-fno-unroll-loops','-mno-implicit-float']
    pins=life.merge_pins(pins,module_pins())
    for p in (APP,t.TEMPLATE,t.START,ROOT/'verification/tests/gap75.ld',Path(command[0]),
              build.SPIKE,build.LLVM/'llvm-readelf',build.LLVM/'llvm-objdump'):
        pins[str(p.resolve())]=life.digest(p)
    life.check(pins);out.mkdir()
    try:
        (out/'gather_war797_gold.h').write_text(header());life.save(out/'compile-command.json',command)
        with (out/'build.log').open('x') as f:subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,timeout=120,check=True)
        from elftools.elf.elffile import ELFFile
        with (out/'input.elf').open('rb') as f:
            segments=[(p['p_paddr'],p['p_paddr']+p['p_memsz']) for p in ELFFile(f).iter_segments() if p['p_type']=='PT_LOAD']
        require(segments and all(0x80000000<=a<b<=0x8003f000 for a,b in segments), 'RAM/stack fit')
        symbols={n:build._elf_symbol(out/'input.elf',build.LLVM/'llvm-readelf',n) for n in NAMES}
        require(symbols['tohost']==0x80001000, 'Frozen tohost')
        dis=subprocess.check_output([str(build.LLVM/'llvm-objdump'),'-d',str(out/'input.elf')],text=True,timeout=30)
        (out/'disassembly.txt').write_text(dis)
        mnemonics=re.findall(r'^\s*[0-9a-f]+:\s+(?:[0-9a-f]{8}|(?:[0-9a-f]{2}\s+){3}[0-9a-f]{2})\s+([\w.]+)',dis,re.M)
        rvv=[n for n in mnemonics if n.startswith('v')]
        require(sorted(rvv)==sorted(['vsetvli','vle8.v','vle8.v','vrgather.vv','vluxei8.v','vse8.v','vse8.v','vse8.v']), 'Only8 explicit static RVV instructions')
        base=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
        elfs={p:h for p,h in base['input_pins'].items() if p.endswith('.elf')}
        require(len(elfs)>=797 and life.digest(out/'input.elf') not in elfs.values(), 'No historical ELF duplicate')
        life.save(out/'elf-dedup.json',dict(known_ELFs=len(elfs),same_ELF=False,ELF_sha=life.digest(out/'input.elf')))
        spike=[str(build.SPIKE),'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0',
               '-m0x80000000:0x200000','-l','--log-commits',str(out/'input.elf')]
        life.save(out/'spike-command.json',spike)
        with (out/'spike.trace').open('x') as f:subprocess.run(spike,stdout=f,stderr=subprocess.STDOUT,timeout=120,check=True)
        counts=validate(out/'spike.trace',symbols)
        counts['runtime']=t.runtime(build.parse_spike_commits(out/'spike.trace'),symbols,segments)
        life.check(pins);pins=life.merge_pins(pins,{str(p):life.digest(p) for p in out.iterdir() if p.is_file()})
        result=dict(status='GATHER_WAR797_HOST_SPIKE_PASS_NOT_DUT',input_pins=pins,symbols=symbols,
                    ELF=str(out/'input.elf'),reference=str(out/'spike.trace'),counts=counts,targets=ts,
                    baseline=797,baseline_seal=BASE_SHA,expected_target_queue_slots=[2,1,0,3],
                    target_capacity_slots=176,actual_gain=None,coverage_admitted=False,VCS_started=False)
        life.save(out/'preflight.json',result)
        print(json.dumps(dict(preflight=str(out/'preflight.json'),seal=life.digest(out/'preflight.json'),ELF_sha=life.digest(out/'input.elf'),counts=counts)),flush=True)
    except Exception as e:
        life.save(out/'failure.json',dict(error=str(e),VCS_started=False));raise


def command(out,elf):
    return [str(life.IMAGE),'-l','run.vcs.log','+NO_FSDB','+ntb_random_seed=1','+PRELOAD='+str(elf),
            '+TESTCASE='+NAME,'+COMMIT_TOHOST=80001000','+COMMIT_TRACE='+str(out/'commit_trace.csv'),
            '+VECTOR_TRACE='+str(out/'vector_trace.csv'),'-cm','line+cond+fsm+tgl+branch',
            '-cm_dir',str(out/'code.vdb'),'-cm_name',NAME]


def prepare(out,prepath,preseal,existing=False):
    require(out.parent==OUT and (out.is_dir() if existing else not out.exists()), 'Fresh direct run or explicit terminal directory')
    require(prepath.parent.parent==OUT and prepath.name=='preflight.json', 'Independent preflight path')
    pre=life.read_bound(prepath,preseal);life.check(pre['input_pins'])
    require(pre['status']=='GATHER_WAR797_HOST_SPIKE_PASS_NOT_DUT' and pre['baseline']==797 and
            pre['coverage_admitted'] is False and pre['VCS_started'] is False, 'Exact software preflight')
    require(validate(Path(pre['reference']),pre['symbols'])=={k:v for k,v in pre['counts'].items() if k!='runtime'}, 'Full independent reference replay')
    ts,pins=targets();require(ts==pre['targets'], 'Exact797 typed zeros')
    plan=life.read_bound(life.PLAN,life.PLAN_SEAL)
    require(plan['simv']==str(life.IMAGE) and len(plan['image'])==66 and plan['image'][str(life.IMAGE)]==IMAGE_SHA, 'Frozen simv66')
    pins=life.merge_pins(life.merge_pins(pins,pre['input_pins']),plan['image'])
    pins=life.merge_pins(pins,module_pins());pins[str(prepath)]=preseal;pins[str(life.PLAN)]=life.PLAN_SEAL
    life.check(pins)
    return dict(schema='GATHER_WAR797_RUN_V1',case=NAME,output=str(out),command=command(out,Path(pre['ELF'])),pins=pins,
                preflight=str(prepath),preflight_seal=preseal,elf_sha256=life.digest(Path(pre['ELF'])),
                image_sha256=IMAGE_SHA,timeout_s=BUDGET,baseline=797,targets=ts,
                scalar_reference_instructions=pre['counts']['runtime']['entry_to_tohost_instructions'],
                systemd_policy=dict(RuntimeMaxSec=360,TimeoutStopSec=10,KillMode='control-group'),
                authorization_source='SEPARATE_PARENT_AGENT_REVIEW_REQUIRED_BEFORE_RUN',foreground_lifetime=True,
                automatic_retry=False,no_FSDB=True,coverage_admitted=False,admission_performed=False,RTL_modified=False,
                qualification_required='Full scalar/memory/CSR/guards/all16 VRF writers/source3 known prestate;797 exact6162/2989 OR and positive target gain')


def invoke_run(out,manifest):
    pre=life.read_bound(Path(manifest['preflight']),manifest['preflight_seal']);elf=Path(pre['ELF'])
    ns=dict(worker.run.__globals__,BUDGET=BUDGET,PRE=elf.parent,ELF_SEAL=manifest['elf_sha256'],IMAGE_SEAL=IMAGE_SHA,
            preflight=SimpleNamespace(NAME=NAME),command=lambda o:command(o,elf))
    FunctionType(worker.run.__code__,ns,argdefs=worker.run.__defaults__)(out,
        dict(manifest,authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL'))


def reference(pre):
    commits=build.parse_spike_commits(Path(pre['reference']))
    start=next(i for i,c in enumerate(commits) if c.pc==0x80000000)
    require(start==5, 'Exact reference boot ROM prefix')
    ref=commits[start:start+pre['counts']['runtime']['entry_to_tohost_instructions']]
    require(ref[-1].memory_accesses==((pre['symbols']['tohost'],1),), 'Exact complete terminal prefix')
    return ref


def footprint(rows,symbols,ref):
    wanted,required=expected_footprint(symbols);observed={};reads=set();terminal=[]
    retired=[r for r in rows if r['event']=='retire']
    require(len(retired)==len(ref) and [int(r['order']) for r in retired]==list(range(len(ref))), 'Complete continuous retirement')
    for r,c in zip(retired,ref):
        require(int(r['pc'],16)==c.pc and int(r['insn'],16)==c.instruction and not int(r['trap']), 'Every scalar PC/opcode/no trap')
        access=mature.common.scalar_memory(c.instruction);rm,wm=int(r['mem_rmask'],16),int(r['mem_wmask'],16)
        if access is None:require(not rm and not wm, 'No unsupported memory effect');continue
        kind,width=access;a=int(r['mem_addr'],16);mask=((1<<width)-1)<<(a&7)
        require(a%width==0 and 0x80000000<=a<a+width<=0x80040000 and
                rm==(mask if kind=='read' else 0) and wm==(mask if kind=='write' else 0), 'Exact memory BE/alignment/bounds')
        value=int(r['rd_wdata'] if kind=='read' else r['mem_wdata'],16)&((1<<(8*width))-1)
        if kind=='read' and any(a+i in required for i in range(width)):require(int(r['rd'])!=0, 'Observable witness')
        if kind=='write':
            require(not any(symbols['gw_source']<=a+i<symbols['gw_source']+12672 for i in range(width)), 'Immutable sources')
            if a==symbols['tohost']:terminal.append((r,value))
        for i in range(width):
            if a+i in wanted:
                observed[a+i]=value>>(8*i)&255
                if kind=='read':reads.add(a+i)
    require(observed==wanted and required<=reads and terminal==[(retired[-1],1)], 'Every byte/CSR/guard and exact final terminal')
    return dict(checks=CHECKS,required_read_bytes=len(required),CSR_values=24,retirements=len(ref))


def native(run,ref,symbols,pre):
    vc=mature.vc
    lanes,vlen,activities=vc._parse_vector_trace(run/'vector_trace.csv')
    starts,retires,rejected=vc._parse_architecture_mapping(run/'commit_trace.csv')
    require((lanes,vlen)==(4,1024) and not rejected, 'Frozen geometry/no trapped native request')
    mapping=vc._map_spike_commits(vc._map_architecture_retires(starts,retires,rejected),ref)
    require(set(activities)<=set(mapping), 'No unmapped native activity')
    states={};prestates={}
    for i,c in enumerate(ref):prestates[i]=dict(states);states.update(c.vector_writes)
    filtered=copy.deepcopy(activities);counts={n:0 for n in ROLES};records=[];transport=[]
    for seq,index in sorted(mapping.items()):
        c=ref[index];activity=activities.get(seq);role=next((n for n in ROLES if c.pc==symbols[n]),None)
        if activity is None:require(role is None, 'Required native activity missing');continue
        require(activity.instruction==c.instruction and activity.allocations>0 and
                activity.allocations==activity.completions, 'Exact native owner/complete lifecycle')
        # Gather is an architectural SLDU writer, not identity reshuffle transport.
        identity=[w for w in activity.writes if w.source==3 and role!='gw_gather']
        if identity:
            actual=mature.known_writes(identity,seq,c)
            require(actual and all(reg in prestates[index] and prestates[index][reg] is not None and
                    value==prestates[index][reg]>>(8*byte)&255 for (reg,byte),(value,w) in actual.items()), 'All source3 known architectural prestate')
            transport.append(dict(arch_seq=seq,compared_bytes=len(actual)))
        filtered[seq].writes=[w for w in activity.writes if w.source!=3 or role=='gw_gather']
        if role is None:require(not filtered[seq].writes and not c.vector_writes, 'No implicit writer');continue
        phase=counts[role];counts[role]+=1;require(phase<4, 'Exactly4 roles')
        require(activity.vstart==0 and activity.vl==1024, 'Exact full active group')
        if role.startswith('gw_store'):
            require(not filtered[seq].writes and not c.vector_writes, 'Store cannot write VRF');continue
        reg,data,producer=(8,case(phase)['sources'][0],4) if role=='gw_load_source' else (
            (0,case(phase)['sources'][1],4) if role=='gw_load_index' else (
            (16,case(phase)['snapshots'][1],3) if role=='gw_gather' else (8,case(phase)['snapshots'][2],4)))
        require(activity.use_vd and activity.vd==reg and activity.eew==0 and filtered[seq].writes and
                all(w.source==producer and w.eew==0 for w in filtered[seq].writes), 'Exact Gather/LD producer and context')
        actual=mature.known_writes(filtered[seq].writes,seq,c)
        wanted={(reg+i//128,i%128):v for i,v in enumerate(data)}
        require(set(actual)==set(wanted) and all(actual[k][0]==v for k,v in wanted.items()), 'Every known primary byte without skip')
        records.append(dict(role=role,phase=phase,arch_seq=seq,compared_bytes=len(actual)))
    require(all(v==4 for v in counts.values()) and len(records)==16 and sum(r['compared_bytes'] for r in records)==16384, 'All16 complete writers and12 stores')
    def parse(path):
        require(Path(path)==run/'vector_trace.csv', 'Bound raw trace only');return lanes,vlen,filtered
    result=FunctionType(vc.compare_vector_commits.__code__,{**vc.compare_vector_commits.__globals__,'_parse_vector_trace':parse},
                        argdefs=vc.compare_vector_commits.__defaults__)(Path(pre['reference']),run/'commit_trace.csv',run/'vector_trace.csv',0x80000000)
    require(result['status']=='PASS' and result['stopped_at_spike_index'] is None and
            result['vector_destination_requests']==result['prefix_vector_destination_requests']==result['compared_instructions']==16 and
            result['compared_bytes']==16384 and result['first_mismatch'] is None and
            all(result[k]==0 for k in ('skipped_unknown_bytes','non_bit_exact_instructions','unobservable_instructions')) and
            not result['incomplete_requests'] and not result['unretired_requests'] and not result['trapped_requests'] and
            all(r['unknown_write_bytes']==r['skipped_unknown_bytes']==r['mismatch_count']==0 for r in result['instructions']), 'Complete generic strict vector diff')
    return dict(primary_writers=records,identity_transport=transport,architectural_vector_diff=result)


def gain(run,out,manifest):
    before,tgl,ledger,_=baseline();db=run/'code.vdb';require(str(db) not in ledger, 'Unique native sample')
    folder=db/'snps/coverage/db/testdata'/NAME
    require(list(folder.parent.iterdir())==[folder], 'One native identity')
    pins=coverage_identity(folder,run,manifest,Path(ledger[0]))
    inputs=out/'single-inputs.txt';inputs.write_text(ledger[0]+'\n'+str(db)+'\n')
    single=bitmap.collect(inputs);combined=bitmap.combine(before,single)
    proof=mature.exact_raw_union(before,single,combined,population=797)
    sample,sha=toggle.rows(folder/'tgl.verilog.data.xml',list(tgl))
    require(sha==pins[str(folder/'tgl.verilog.data.xml')], 'Actual Toggle file SHA')
    merged=mature.exact_toggle_union(tgl,sample);additions=toggle.gains(tgl,merged)
    ts=[dict(scope=t['scope'],name=t['name'],new_coordinates=[i for i in t['raw_coordinates'] if i in additions[t['scope']]]) for t in manifest['targets']]
    # Each target load advances by three LDU accepts, visiting all four slots.
    slots={int(t['name'].split('vinsn[')[1].split(']')[0]) for t in ts if 'vinsn[' in t['name'] and t['new_coordinates']}
    require(slots==set(range(4)), 'HOLD: target wait_complete did not hit all4 queue slots')
    for name,data in [('single-bits.json',single),('proposed-combined-bits.json',combined),('single-toggle-bits.json',sample),
                      ('proposed-combined-toggle-bits.json',merged),('full-toggle-gain.json',additions)]:life.save(out/name,data)
    return dict(baseline=797,full6162=proof,full2989=True,metrics=bitmap.delta(before,combined)['metrics'],
                targets=ts,target_new_slots=sum(len(t['new_coordinates']) for t in ts),target_queue_slots=sorted(slots),
                full_toggle_new_slots=sum(map(len,additions.values())),official_percentage=None),pins


def collect(run,seal,out):
    require(out.parent==OUT and not out.exists(), 'Fresh independent collection')
    m=life.read_bound(run.with_name(run.name+'.prepared.json'),seal)
    require(m==prepare(run,Path(m['preflight']),m['preflight_seal'],existing=True), 'Prepared exact replay')
    pre=life.read_bound(Path(m['preflight']),m['preflight_seal']);ref=reference(pre)
    proxy=SimpleNamespace(NAME=NAME,ELF=Path(pre['ELF']),ELF_SHA=m['elf_sha256'],IMAGE_SHA=IMAGE_SHA,BUDGET=BUDGET)
    terminal=FunctionType(mature.terminal.__code__,{**mature.terminal.__globals__,'runner':proxy})(run,m)
    pins=mature.mature.evidence_pins(run,seal,m);life.check(pins);out.mkdir()
    try:
        rows=mature.common.read_csv((run/'commit_trace.csv').read_bytes(),mature.common.COMMIT_FIELDS)
        vectors=mature.common.read_csv((run/'vector_trace.csv').read_bytes(),mature.common.VECTOR_FIELDS)
        lifecycle=mature.control.lifecycle(rows,vectors);mature.mature.logs(run,lifecycle)
        witness=footprint(rows,pre['symbols'],ref)
        scalar=mature.common.spike_trace.compare_commit_prefix(Path(pre['reference']),run/'commit_trace.csv',0x80000000,
            terminal_tohost_address=pre['symbols']['tohost'],rtl_exception_log=run/'trace_hart_0.log',rvfi_store_data_layout='unshifted')
        mature.common.scalar_exact(scalar,mature.common.reference_counts(ref,pre['symbols']))
        mem=mature.memory.scalar_memory_exact(rows,ref);vector=native(run,ref,pre['symbols'],pre)
        delta,gainpins=gain(run,out,m)
        pins=life.merge_pins(life.merge_pins(pins,gainpins),{str(f):life.digest(f) for f in out.iterdir() if f.is_file()});life.check(pins)
        q=dict(status='GATHER_WAR797_FULL_STRICT_AND_NEW_TARGET_GAIN_PASS_NOT_ADMITTED',terminal=terminal,
               scalar=scalar,scalar_memory=mem,native=vector,footprint=witness,lifecycle=lifecycle,raw_gain=delta,
               input_pins=pins,prepared_seal=seal,coverage_admitted=False,EDA_launched=False,RTL_modified=False)
        life.save(out/'qualification.json',q);print('QUALIFIED_NOT_ADMITTED',life.digest(out/'qualification.json'),delta['target_new_slots'])
    except Exception as e:life.save(out/'failure.json',dict(status='FAIL_OR_HOLD_NOT_ADMITTED',reason=str(e)));raise


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode',choices=('preflight','prepare','verify','run','collect'))
    ap.add_argument('--output',type=Path,required=True);ap.add_argument('--preflight',type=Path)
    ap.add_argument('--preflight-seal');ap.add_argument('--run',type=Path);ap.add_argument('--seal')
    ap.add_argument('--parent-authorized',action='store_true');a=ap.parse_args(argv)
    require((a.mode=='run')==a.parent_authorized, 'Only parent-authorized run may launch')
    out=a.output.resolve()
    if a.mode=='preflight':preflight(out);return
    if a.mode=='collect':require(a.run is not None and a.seal, 'Bound run/seal required');collect(a.run.resolve(),a.seal,out);return
    require(a.preflight is not None and a.preflight_seal, 'Exact preflight SHA required')
    require((a.mode!='prepare')==bool(a.seal), 'Verify/run need prepared SHA')
    m=prepare(out,a.preflight.resolve(),a.preflight_seal);side=out.with_name(out.name+'.prepared.json')
    if a.mode=='prepare':
        require(not side.exists(), 'No prepared overwrite');life.save(side,m);print('PREPARED_NO_VCS',life.digest(side))
    else:
        require(life.read_bound(side,a.seal)==m, 'Prepared SHA/content drift')
        if a.mode=='verify':print('VERIFY_PASS_NO_VCS')
        else:invoke_run(out,m)


if __name__=='__main__':main()
