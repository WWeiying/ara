#!/usr/bin/env python3
"""Freeze target arithmetic inputs and run bounded scalar Spike probes, never VCS."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
import oracle as o

HERE = Path(__file__).resolve().parent
ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent/'ara_dsa_signoff_integration/verification/out'
REV = 'f50092f2d22238c6be4b6c159a1ad71a4ea68678'
GNU = '/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-'
SPIKE = '/home/wangwy/software/toolchains/spike/bin/spike'
BUILDER = Path('verification/performance/chain_profile/q6_decode/build.py')
CAPTURE = Path('verification/performance/akv_pair_eval/build.py')
FOUNDATION = Path('verification/performance/resident_rvv/qk_shared/full_call_sdk/flags_v2/fixture.py')
SOFTFLOAT = Path('verification/fpnew_upstream_20261009/oracle.py')
ROTATION = Path('verification/performance/resident_rvv/rotation/pv_rotation.S')
OWN = ('oracle.py','prepare.py','probe.c','start.S','test_oracle.py','README.md')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with path.open('x') as f:
        json.dump(value,f,indent=2,sort_keys=True,allow_nan=False)
        f.write('\n')


def strict_json(text):
    def pairs(rows):
        result = {}
        for key,value in rows:
            o.require(key not in result,'Duplicate JSON key')
            result[key] = value
        return result
    def bad(value):
        raise ValueError('Nonfinite JSON: '+value)
    return json.loads(text,object_pairs_hook=pairs,parse_constant=bad)


def c_features(f):
    floating = ('softcap','mask_scale','position_slope','sinks')
    def literal(value):
        return o.number(value).hex()+'f'
    return '{'+','.join('.'+k+'='+('{' + ','.join(literal(x) for x in v) + '}'
        if isinstance(v,list) else literal(v) if k in floating else str(v)) for k,v in f.items())+'}'


def parse_results(trace, base, count):
    values = {}
    for address,value in re.findall(r'\bmem 0x([0-9a-f]+) 0x([0-9a-f]+)',trace):
        address,value = int(address,16),int(value,16)
        if base <= address < base+count*8:
            o.require((address-base)%4 == 0 and value <= 0xffffffff and address not in values,
                      'Duplicate/misaligned/wide result store')
            values[address] = value
    o.require(set(values) == set(range(base,base+count*8,4)),'Missing/extra probe result')
    return [(values[base+i*8],values[base+i*8+4]) for i in range(count)]


def probe(b, inputs, own, label, requests, directed):
    out = b.output/label
    out.mkdir()
    requests = sorted(requests)
    o.require(0 < len(requests) <= 64 and len(directed) <= 16,'Probe bound')
    header = ['#define REQUEST_COUNT %d' % len(requests),'#define DIRECTED_COUNT %d' % len(directed),
        'static const libm_request_t requests[] = {'+','.join(
            '{%d,0x%08x}' % (name == 'tanhf',value) for name,value in requests)+'};',
        'static const transform_request_t directed_requests[] = {'+(','.join(
            '{0x%x,0x%x,%d,%d,%d,%s}' % (r['dot'],r['scale'],r['mask'],r['head'],r['index'],c_features(r['features']))
            for r in directed) or '{0}')+'};']
    (out/'requests.h').write_text('\n'.join(header)+'\n')
    save(out/'requests.json',dict(libm=[dict(function=n,input=x) for n,x in requests],directed=directed))
    b.pin(out/'requests.h'); b.pin(out/'requests.json')
    flags = ['-march=rv64gcv_zfh_zvfh','-mabi=lp64d','-mcmodel=medany','-mno-relax',
        '-O3','-fno-fast-math','-ffp-contract=off','-fno-tree-vectorize','-fno-builtin',
        '-ffunction-sections','-fdata-sections','-I'+str(inputs/'software/akv/include'),'-I'+str(out)]
    objects = []
    for source in (own/'probe.c',own/'start.S',inputs/'software/akv/src/akv_features.c'):
        obj = b.output/(label+'_'+source.stem+'.o')
        b.compile(GNU+'gcc',flags,source,obj)
        objects.append(obj)
    elf = out/'probe.elf'
    b.run(label+'-link',[GNU+'gcc',*flags[:4],'-nostdlib','-nostartfiles','-static',
        '-Wl,-Ttext-segment=0x80000000','-Wl,--gc-sections','-Wl,-Map='+str(out/'link.map'),
        *objects,'-Wl,--start-group','-lm','-lc','-lgcc','-lnosys','-Wl,--end-group','-o',elf])
    dis = b.run(label+'-disassembly',[GNU+'objdump','-d','-M','no-aliases,numeric',elf]).decode()
    body = dis.split('<probe_main>:',1)[1].split('\n\n',1)[0]
    restores = re.findall(r'csrrs\s+(x\d+),fcsr,x0\n[^\n]*csrrw\s+x0,fcsr,(x\d+)',body)
    o.require(restores and all(flags != saved for flags,saved in restores),'FCSR restore register overlap')
    o.require('csrrwi\tx0,fcsr,0' in body or re.search(r'csrrwi\s+x0,fcsr,0',body),'Missing clean probe FCSR')
    names = b.run(label+'-symbols',[GNU+'nm','-n','-S','--defined-only',elf]).decode()
    symbols = {p[-1]:int(p[0],16) for line in names.splitlines() if len(p := line.split()) in (3,4)}
    o.require(all(name in symbols for name in ('expf','tanhf','probe_results','tohost')),'Target libm binding missing')
    trace = out/'spike.trace'
    argv = [SPIKE,'-m16','--isa=rv64gcv_zfh_zvfh_zvl1024b','--instructions=300000',
            '-l','--log-commits','--log='+str(trace),str(elf)]
    b.commands.append(dict(label=label+'-spike',argv=argv,cwd=str(out),timeout_seconds=15))
    with (out/'console.log').open('x') as log:
        result = subprocess.run(argv,cwd=out,stdout=log,stderr=subprocess.STDOUT,timeout=15,check=False)
    b.commands[-1]['returncode'] = result.returncode
    o.require(result.returncode == 0,'Target scalar probe failed')
    text = trace.read_text()
    exits = re.findall(r'\bmem 0x%016x 0x([0-9a-f]+)' % symbols['tohost'],text)
    o.require(exits == ['0000000000000001'],'Missing clean target completion')
    rows = parse_results(text,symbols['probe_results'],len(requests)+len(directed))
    o.require(all(flags <= 31 for _,flags in rows),'Non-RNE probe FCSR')
    records = [dict(function=name,input=value,output=rows[i][0],fflags=rows[i][1])
               for i,(name,value) in enumerate(requests)]
    o.sample_table(requests,records)
    return records,rows[len(requests):],dict(elf=str(elf),elf_sha256=sha(elf),trace_sha256=sha(trace),
        requests=len(requests),directed=len(directed),clean_fcsr=True,restore_register_pairs=restores)


def prepare(output):
    o.require(output.parent == OUT and not output.exists() and
              re.fullmatch(r'stage4_resident_features_target_[A-Za-z0-9_]+',output.name),'Fresh owned output required')
    output.mkdir()
    helper = o.load(ROOT/BUILDER,'stage4_probe_builder')
    b = helper.Builder(output)
    result = dict(state='FAIL',vcs_launched=False,native_attention_executed=False,performance_measured=False)
    try:
        b.pin(ROOT/BUILDER)
        inputs = output/'inputs'
        b.archive(ROOT,REV,['software/akv',str(FOUNDATION),str(SOFTFLOAT),str(CAPTURE),str(ROTATION)],inputs)
        own = inputs/'target'
        own.mkdir()
        for name in OWN:
            b.pin(HERE/name)
            shutil.copyfile(HERE/name,own/name)
        for p in inputs.rglob('*'):
            if p.is_file(): b.pin(p)
        b.pin(SPIKE)
        for name in ('libm.a','libc.a','libgcc.a','libnosys.a','cc1','as','ld'):
            option = '-print-file-name=' if name.endswith('.a') else '-print-prog-name='
            path = Path(b.run('locate-'+name,[GNU+'gcc','-march=rv64gcv_zfh_zvfh','-mabi=lp64d',option+name]).decode().strip())
            b.pin(path.resolve())
        ctx = o.Context(inputs)
        b.pin(ctx.oracle.LIB)
        cap = o.load(inputs/CAPTURE,'stage4_capture')
        cap.DATA = OUT/'e2e_qwen3_f16_native_data_20261106_02'
        cap.CAPTURE = OUT/'e2e_qwen3_f16_attention_capture_20261106_01'
        b.pins.update(cap.validate_data(cap.DATA,cap.CAPTURE))
        data = {n:(cap.DATA/('decode_'+n+'.bin')).read_bytes()
                for n in ('query','query_f16','key','value','mask')}
        conversion = o.Arithmetic(ctx)
        qhalf = [conversion.cast(32,16,x) for x in o.unpack(data['query'],32)]
        o.require(struct_pack(qhalf,16) == data['query_f16'],'F16 Q differs from captured RNE bytes')
        dots = [o.dot_rows(ctx,data,c) for c in o.CASES]
        tanh = set()
        for case,(rows,_,_) in zip(o.CASES,dots):
            tanh |= o.prepare_scores(ctx,data,case,rows,discover=True)[2]
        for r in o.directed():
            o.transform(o.Arithmetic(ctx),r['dot'],r['scale'],r['mask'],r['head'],r['index'],r['features'],tanh)
        first,directed,proof1 = probe(b,inputs,own,'tanh',tanh,o.directed())
        table = o.sample_table(tanh,first)
        exp,perf_exp = {('expf',0)},set()
        maxima = []
        for i,(case,(rows,_,_)) in enumerate(zip(o.CASES,dots)):
            scores = o.prepare_scores(ctx,data,case,rows,table)[0]
            pairs,maximum = o.alpha_requests(scores,case)
            requests = {('expf',o.Arithmetic(ctx).sub(old,new)) for old,new in pairs}
            exp |= requests
            if i == 0: perf_exp = requests
            maxima.append(maximum)
        o.require(any(value != 0 for _,value in perf_exp),'Performance controls do not exercise nonzero alpha')
        second,_,proof2 = probe(b,inputs,own,'exp',exp,[])
        table.update(o.sample_table(exp,second))
        o.require(table[('expf',0)] == (o.ONE,0),'expf(0) must be exact and flag-free')
        checks,used = [],set()
        for r,actual in zip(o.directed(),directed):
            a = o.Arithmetic(ctx,table)
            expected = o.transform(a,r['dot'],r['scale'],r['mask'],r['head'],r['index'],r['features'])
            o.require(actual == (expected,a.flags),'Independent scalar transform mismatch: '+r['name'])
            used |= a.used
            checks.append(dict(name=r['name'],bits=expected,fflags=a.flags))
        goldens = []
        for case,(rows,flags,phases) in zip(o.CASES,dots):
            golden,consumed = o.expected(ctx,data,case,rows,flags,phases,table)
            used |= consumed
            goldens.append(dict(case=case,expected=golden))
        o.require(used == set(table),'Unused or missing target libm sample')
        save(output/'target-libm.json',dict(schema=1,sdk_revision=REV,samples=first+second,
            probes=[proof1,proof2],rounding_mode=0,host_libm_used=False))
        save(output/'oracle.json',dict(schema=1,cases=goldens,directed=checks,
            query_conversion_outside_roi=True,excluded_query_conversion_fflags=conversion.flags,
            initial_fflags_cases=[0,8],host_libm_used=False,full_call_target_executed=False))
        save(output/'build-contract.json',dict(schema=1,sdk_revision=REV,
            entry='akv_experimental_attention_execute_features_v2_native',automatic=0,
            performance_order=[0,1,1,0],getenv={'AKV_PAIR_HEADS':'1'},
            macros={'AKV_EXPERIMENTAL_RESIDENT_ATTENTION':1,'AKV_EXPERIMENTAL_RESIDENT_FEATURES_V2':1,'AKV_REFILL_OVERLAP':0},
            wrapper=str(ROTATION),wrapper_sha256=sha(inputs/ROTATION),
            link_flags=['-Wl,--wrap=akv_experimental_pv_f16_pair'],rotation_selected=1,
            baseline_legacy_commands=237,candidate_legacy_commands=4,candidate_resident_commands=6,
            query_inputs='Captured F16 bytes, prepared outside ROI; no Q conversion flags in golden',
            roi='Entry/preflight and complete native call through normalization stores plus vector drain/fence',
            requires_retired_rotation_body=True,requires_candidate_wrapper_bypass=True,
            fallback_case=dict(actual_frm=1,options_frm=0,requested=[0,1],automatic=0,
                compare_same_frm_off=True,require_no_resident=True,oracle_scope='Pair/route check; not RNE golden'),
            source_controls_are_derived=True,firmware_built=False,vcs_authorized=False))
        b.run('host-tests',[sys.executable,'-B',own/'test_oracle.py','--inputs',inputs,'--receipt',output])
        o.require(all(sha(path) == digest for path,digest in b.pins.items()),'Input drift')
        result.update(state='ORACLE_PROBES_PASS_FIRMWARE_PENDING',post_pins_match=True,
            cases=len(goldens),directed=len(checks),libm_samples=len(table),probes=[proof1,proof2],
            performance_alpha_inputs=[v for _,v in sorted(perf_exp)],
            native_arithmetic_executed=False,scalar_feature_transform_executed=True)
    except Exception as exc:
        result['error'] = repr(exc)
    save(output/'source-pins.json',b.pins)
    (output/'commands.json').write_text(json.dumps(b.commands,indent=2,sort_keys=True)+'\n')
    result['source_pins_sha256'] = sha(output/'source-pins.json')
    result['artifacts'] = {str(p):sha(p) for p in output.rglob('*') if p.is_file()}
    save(output/'result.json',result)
    print(json.dumps({k:v for k,v in result.items() if k != 'artifacts'},indent=2))
    return result['state'] == 'ORACLE_PROBES_PASS_FIRMWARE_PENDING'


def struct_pack(values,width):
    import struct
    return struct.pack('<'+{16:'H',32:'I'}[width]*len(values),*values)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    parser.add_argument('--output',type=Path,required=True)
    raise SystemExit(not prepare(parser.parse_args().output.absolute()))
