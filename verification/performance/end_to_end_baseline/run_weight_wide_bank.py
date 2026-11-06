#!/usr/bin/env python3
"""One bounded frozen-DUT bank integration attempt, with actual generic SRAM."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RUNS = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
OUT = RUNS / 'e2e_weight_wide_bank_20261106_01'
DUT_SHA = 'afc5492ae3766f327ab56fe47ab3bc77c0fca9f65f0816355c27d9e054b34570'
OWNED = tuple(HERE / n for n in ('qbs_weight_wide_bank_tb.sv', 'run_weight_wide_bank.py', 'test_weight_wide_bank.py'))
RTL = (
    ('hardware/include/qbs_pkg.sv', '5cba22278054776e56d74f01a4833f521729a16953a264fe959dbe8848c33a97'),
    ('hardware/deps/tech_cells_generic/src/rtl/tc_sram.sv', 'e815e5d70aa530f8bcd99dd68c8791c7f8b46295e5fdfd75651eb2807f79abe9'),
    ('hardware/src/vlsu/qbs/qbs_payload_sram.sv', '186d3b03fe2a7781fcfaa01c7bb698adf0196de9f3b5f9388a08bbbbe0062695'),
    ('hardware/src/vlsu/qbs/qbs_weight_line_assembler.sv', 'ff2735b3a6fece3d5a1ec44e8ca3a4c0d7cf2e4c473820b7c9ba4231058a4d5c'),
    ('hardware/src/vlsu/qbs/qbs_weight_wide_mapper.sv', '284414b65a90cf635ecc1b15c2a8e28a1e1956b741091221db05f10d6ab839df'),
    ('hardware/src/vlsu/qbs/qbs_weight_wide_bank.sv', DUT_SHA),
)
# Native bytes, elements, low length, high length. No package imports.
PROFILES = {1:(144,256,128,0),2:(210,256,128,64),3:(18,32,16,0),
            4:(176,256,128,32),5:(110,256,64,32),6:(34,32,32,0),
            7:(84,256,64,0),8:(22,32,16,0),9:(18,32,16,0)}
RESOURCES = dict(mapper_packet_bits=948,logical_low_bytes=512,logical_high_bytes=256,
                 logical_sram_bytes=768,target_sram_mc_min_words=8,target_sram_mc_physical_bytes=2048,
                 compute_window_bits=128,assembler_payload_bits=4096,side_storage_bits=640,compiled_target_sram_mc=0)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(1048576), b''):
            h.update(data)
    return h.hexdigest()


def write_new(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def word16(profile, k, plane):
    if profile in (1,4):
        return (k//64)*2+(k//16)%2 if plane==0 else (k//16)%2
    if profile==2:
        return (k//128)*4+(k//16)%4 if plane==0 else (k//128)*2+(k//16)%2
    if profile in (5,7):
        return (k//128)*2+(k//16)%2 if plane==0 else (k//16)%2
    return (k//16)%2 if profile==6 and plane==0 else 0


def epoch_counts(profile, rows, grouped, phase):
    size,elements,low,high = PROFILES[profile]
    packets = ((phase+rows*size+31)//32 if grouped else
               sum(((phase+r*size)%32+size+31)//32 for r in range(rows)))
    read_bytes = rows*sum(max(0,min(16,length-16*word16(profile,k,p)))
                          for k in range(0,elements,16) for p,length in enumerate((low,high)))
    return dict(packets=packets,native=rows*size,payload=rows*(low+high),side=rows*(size-low-high),
                reads=elements//16,read_bytes=read_bytes,idle=3)


def expected_profiles():
    result=[]
    for p in PROFILES:
        row=dict(profile=p,cases=512,packets=0,native=0,payload=0,side=0,reads=0,read_bytes=0,idle=0)
        for n in range(1,5):
            for g in (0,1):
                for phase in range(32):
                    for key,value in epoch_counts(p,n,g,phase).items():
                        row[key]+=2*value
        result.append(row)
    return result


def fields(line, tag):
    require(line.startswith(tag+' '), 'Wrong record tag')
    out={}
    for word in line[len(tag)+1:].split():
        key,sep,value=word.partition('=')
        require(sep and key not in out and re.fullmatch('[0-9]+',value), 'Malformed/duplicate field')
        out[key]=int(value)
    return out


def check(text):
    require(not re.search(r'Fatal:|Error[-:]|Assertion.*failed|UVM_(?:FATAL|ERROR)',text),
            'Component tool/assertion failure, regardless of exit code')
    lines=text.replace('\r','').splitlines()
    records=lambda tag:[fields(line,tag) for line in lines if line.startswith(tag)]
    require(records('WB_SUITE_BEGIN')==[dict(version=1)],'Missing/duplicate suite begin')
    require(records('WB_RESOURCE')==[RESOURCES],'Actual resource declaration mismatch')
    profiles=records('WB_PROFILE_PASS')
    require(len(profiles)==9,'Incomplete normal profile inventory')
    for actual,expected in zip(profiles,expected_profiles()):
        require(set(actual)==set(expected)|{'max_drain','unthrottled_stalls','mixed_stalls','side_mixed_stalls'} and
                all(actual.get(k)==v for k,v in expected.items()) and
                1<=actual['max_drain']<=3 and actual['unthrottled_stalls']==0 and
                0<=actual['side_mixed_stalls']<=actual['mixed_stalls'],
                'Profile byte/read/II1/drain coverage mismatch: '+str(expected['profile']))
    aborts,reuses=records('WB_ABORT_PASS'),records('WB_REUSE_PASS')
    require(len(aborts)==len(reuses)==72,'Incomplete clear/reset/reuse coverage')
    expected_order=[(p,g,stage,reset) for p in PROFILES for g in (0,1) for stage in (0,1) for reset in (0,1)]
    reuse_totals=dict(packets=0,native=0,payload=0,side=0,reads=0,read_bytes=0,idle=0)
    for abort,reuse,(p,g,stage,reset) in zip(aborts,reuses,expected_order):
        require(set(abort)=={'profile','group','stage','reset','packets','accepted','committed','discarded','outputs'} and
                (abort['profile'],abort['group'],abort['stage'],abort['reset'])==(p,g,stage,reset), 'Abort order/fields')
        size,_,low,high=PROFILES[p]
        require(0<abort['accepted']<=4*size and 0<=abort['committed']<=min(abort['accepted'],4*(size-low-high)) and
                abort['discarded']==abort['accepted']-abort['committed']>0 and
                1<=abort['packets']<=abort['accepted']<=32*abort['packets'], 'Abort exact byte conservation')
        if stage==0:
            require(abort['accepted']==(32 if g else min(32,size)) and abort['committed']==0 and
                    abort['outputs']==0 and abort['packets']==1,'Mapper pending abort fixture')
        else:
            require(1<=abort['outputs']<=8,'Actual assembler output was not pending')
        rp,rn=p%9+1,p%4+1
        require(reuse==dict(profile=rp,rows=rn,group=1-g,phase=(p*7+stage)%32),'Immediate reuse coverage')
        counts=epoch_counts(rp,rn,1-g,(p*7+stage)%32)
        for key,value in counts.items():
            reuse_totals[key]+=value
        # One extra synchronous read is cancelled by clear/reset after its edge.
        reuse_totals['reads']+=1
        reuse_totals['read_bytes']+=rn*16*(1+int(PROFILES[rp][3]!=0))
    endings=records('WB_BANK_COMPONENT_PASS')
    require(len(endings)==1,'Missing/duplicate normal PASS terminal')
    end=endings[0]
    total={key:sum(p[key] for p in expected_profiles())+reuse_totals[key]
           for key in ('packets','native','payload','side','reads','read_bytes','idle')}
    total['packets']+=sum(a['packets'] for a in aborts)
    total['native']+=sum(a['accepted'] for a in aborts)
    total['side']+=sum(a['committed'] for a in aborts)
    wanted=dict(cases=4608,reuse_cases=72,abort_cases=72,cancel_cases=72,
                accepted=total.pop('native'),**total)
    require(set(end)==set(wanted)|{'input_stalls','blocked_outputs','early_reads','max_drain','unthrottled_stalls',
                                  'mixed_stalls','side_mixed_stalls'} and
            all(end[k]==v for k,v in wanted.items()) and all(end[k]>0 for k in ('input_stalls','blocked_outputs','early_reads')) and
            end['unthrottled_stalls']==0 and 1<=end['max_drain']<=3,'Final exact integration accounting/service gate')
    require(end['mixed_stalls']==sum(p['mixed_stalls'] for p in profiles)>0 and
            end['side_mixed_stalls']==sum(p['side_mixed_stalls'] for p in profiles)>0,
            'Missing actual mixed-target/side-bearing atomic stall coverage')
    require(end['accepted']-end['payload']-end['side']==sum(a['discarded'] for a in aborts),'Global cleared-pending conservation')
    require(sum(line.startswith('WB_') for line in lines)==156,'Unexpected suite records')
    return dict(profiles=profiles,aborts=aborts,reuses=reuses,totals=end,resources=RESOURCES,
                independent_native_oracle=True,actual_sram_byte_writes_checked=True,
                committed_counter_compared_each_edge=True,read_half_and_idle_hold_checked=True,
                controls_and_counts_x_checked=True,per_epoch_read_count_checked=True,
                actual_mixed_target_atomic_stall_checked=True,side_state_stable_under_map_stall_checked=True,
                unthrottled_input_ii1_checked=True,drain_bound_edges=3,
                drain_bound_derivation='final-input edge -> mapper-to-assembler -> first SRAM word -> optional last carry flush',
                resource_scope='Logical SRAM 768B; existing TARGET_SRAM_MC minimum eight 8x256 macros = 2048B. '
                               'Declared mapper/assembler/side data bits are not a total flop count or area estimate.')


class Pins:
    def __init__(self):
        self.values={}

    def pin(self,path,expected=None):
        path=Path(path).resolve(strict=True);value=digest(path)
        require(expected is None or expected==value,'Frozen source mismatch: '+str(path))
        require(str(path) not in self.values or self.values[str(path)]==value,'Source/image drift: '+str(path))
        self.values[str(path)]=value

    def verify(self):
        for path,value in self.values.items():
            require(digest(path)==value,'Final source/image drift: '+path)


def ownership():
    observations=[]
    for name in ('e2e_sdk_dispatch_model_pair_20261106_01','e2e_rms_norm_vcs_20261106_01','e2e_weight_wide_mapper_20261106_02'):
        path=RUNS/name/'source-pins.json';data=path.read_bytes();pins=json.loads(data)
        conflicts=[str(p) for p in OWNED if str(p) in pins]
        require(not conflicts,'Owned tests already sealed by consumer: '+repr(conflicts))
        observations.append(dict(path=str(path),sha256=hashlib.sha256(data).hexdigest(),conflicts=conflicts,
                                 inherited_documentation={k:v for k,v in pins.items() if k.lower().endswith('.md')}))
    return observations


def run(output,dut_sha,execute_frozen):
    require(execute_frozen and dut_sha==DUT_SHA,'Explicit frozen-DUT execution authorization required')
    output=Path(output).absolute()
    require(output==OUT and output.resolve()==OUT,'Only assigned fresh integration output allowed')
    observations=ownership()
    output.mkdir(exist_ok=False)
    pins,commands=Pins(),[]
    result=dict(state='WEIGHT_WIDE_BANK_COMPONENT_FAIL',dut_sha256=DUT_SHA,phase='PREPARING',
                soc_integrated=False,production_path_changed=False,performance_measured=False,area_measured=False,
                one_component_attempt=True,retry_permitted=False)

    def command(argv,label,bound):
        argv=list(map(str,argv));pins.pin(argv[0]);pins.verify()
        result['phase']=label
        row=dict(label=label,argv=argv,cwd=str(output),timeout=bound);commands.append(row)
        with (output/(label+'.log')).open('xb') as stream:
            child=subprocess.Popen(argv,cwd=output,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
            try: code=child.wait(timeout=bound)
            except BaseException:
                os.killpg(child.pid,signal.SIGKILL);child.wait();raise
        row['returncode']=code;pins.verify()
        return code,(output/(label+'.log')).read_text()

    try:
        write_new(output/'worker-pin-inventory.json',observations)
        snapshot=output/'source-snapshot';snapshot.mkdir()
        for path,expected in [(p,None) for p in OWNED]+[(ROOT/p,h) for p,h in RTL]:
            pins.pin(path,expected)
            dest=snapshot/path.name
            with dest.open('xb') as stream: stream.write(path.read_bytes())
            pins.pin(dest,digest(path))
        pins.pin(Path(sys.executable).resolve())
        write_new(output/'helpers-frozen.json',{str(p):digest(p) for p in OWNED})
        code,log=command([sys.executable,'-B',snapshot/'test_weight_wide_bank.py'],'unit-tests',60)
        require(code==0,'Frozen host checker tests failed; no component compile attempted')
        vcs=shutil.which('vcs');require(vcs is not None,'Host VCS unavailable');pins.pin(vcs)
        vcs1=Path(vcs).resolve().parent.parent/'linux64/bin/vcs1'
        require(vcs1.is_file(),'VCS compiler executable missing');pins.pin(vcs1)
        build=output/'build';build.mkdir();image=build/'simv'
        write_new(output/'source-pins-precompile.json',pins.values)
        sources=[snapshot/Path(p).name for p,_ in RTL]+[snapshot/'qbs_weight_wide_bank_tb.sv']
        code,log=command([vcs,'-full64','-sverilog','-timescale=1ns/1ps','-assert','svaext',*sources,
                          '-top','qbs_weight_wide_bank_tb','-Mdir='+str(build/'csrc'),'-o',image],'compile',180)
        require(code==0 and not re.search(r'Fatal:|Error[-:]',log),'First component compile failure; preserved, do not rerun')
        pins.pin(image)
        for path in sorted(build.rglob('*.so')): pins.pin(path)
        code,log=command([image],'functional',180)
        require(code==0,'First component execution failure; preserved, do not rerun')
        measured=check(log)
        write_new(output/'measured.json',measured)
        pins.verify()
        result.update(state='WEIGHT_WIDE_BANK_COMPONENT_PASS',phase='COMPLETE',post_pins_match=True,
                      measured=measured['totals'],resources=RESOURCES,
                      limitations=['Bank-local mapper/assembler/actual generic SRAM integration only, not SoC/model performance',
                                   'TARGET_SRAM_MC physical minimum is declared from existing macros, not simulated or synthesized',
                                   'No DUT edits; no historical mapper reruns; no whole-git-HEAD pin'])
    except Exception as exc:
        result.update(error=repr(exc),first_failure_preserved=True,post_pins_match=False)
    write_new(output/'source-pins.json',pins.values);write_new(output/'commands.json',commands)
    result['source_pins_sha256']=digest(output/'source-pins.json')
    result['artifacts']={str(p):digest(p) for p in sorted(output.rglob('*'))
                         if p.is_file() and not p.is_relative_to(output/'build')}
    write_new(output/'result.json',result)
    print(json.dumps(result,indent=2))
    return 0 if result['state']=='WEIGHT_WIDE_BANK_COMPONENT_PASS' else 1


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=OUT)
    parser.add_argument('--dut-sha256',required=True)
    parser.add_argument('--execute-frozen',action='store_true')
    args=parser.parse_args(argv)
    return run(args.output,args.dut_sha256,args.execute_frozen)


if __name__=='__main__':
    sys.dont_write_bytecode=True
    sys.exit(main())
