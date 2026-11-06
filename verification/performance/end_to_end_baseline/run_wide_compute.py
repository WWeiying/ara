#!/usr/bin/env python3
"""One frozen compute-only 128/256 weight-ingress pair, unchanged FP arithmetic."""
import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path('/home/wangwy/openproject/ara_dsa')
HERE = ROOT/'verification/performance/end_to_end_baseline'
RUNS = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
OUT = RUNS/'e2e_wide_compute_20261106_01'
PRIOR = RUNS/'e2e_projection_resources_20261106_01'
OWNED = tuple(HERE/n for n in ('qbs_wide_compute_tb.sv','run_wide_compute.py','test_wide_compute.py'))
FROZEN = {
    'qbs_compute_engine.sv':'f8cdc47107dd434743d30c0372f4dba029a91b2cfc7f931ca6c3e11b9203546a',
    'qbs_payload_buffer.sv':'89533788729c81e7c94e576029166722aea16c4efca9bc127553d69bdeb1856b',
    'qbs_block_adapter.sv':'c52a24a41049e15e4c58f69d1a9567dd31014c99ae6d0bf98fb591a0e3e35871',
    'qbs_weight_wide_bank.sv':'afc5492ae3766f327ab56fe47ab3bc77c0fca9f65f0816355c27d9e054b34570',
    'qbs_weight_wide_mapper.sv':'284414b65a90cf635ecc1b15c2a8e28a1e1956b741091221db05f10d6ab839df',
    'qbs_weight_line_assembler.sv':'ff2735b3a6fece3d5a1ec44e8ca3a4c0d7cf2e4c473820b7c9ba4231058a4d5c',
}
COMMON = ('cf_math_pkg','lzc','rr_arb_tree')
FPNEW = ('fpnew_pkg','lfsr_sr','fpnew_classifier','fpnew_rounding','fpnew_cast_multi','fpnew_fma',
         'fpnew_opgroup_fmt_slice','fpnew_opgroup_multifmt_slice','fpnew_opgroup_block','fpnew_top')
QBS = ('qbs_profile_decoder','qbs_dot_array','qbs_activation_context','qbs_payload_sram','qbs_payload_buffer',
       'qbs_block_adapter','qbs_weight_wide_mapper','qbs_weight_line_assembler','qbs_weight_wide_bank',
       'qbs_profile_engine_int','qbs_half_scale','qbs_fp_accumulator','qbs_compute_engine')
SOURCES = (ROOT/'hardware/deps/common_cells/src/cf_math_pkg.sv',
           ROOT/'hardware/deps/fpnew/src/fpnew_pkg.sv',ROOT/'hardware/include/qbs_pkg.sv',
           *(ROOT/f'hardware/deps/common_cells/src/{n}.sv' for n in COMMON[1:]),
           *(ROOT/f'hardware/deps/fpnew/src/{n}.sv' for n in FPNEW[1:]),
           ROOT/'hardware/deps/tech_cells_generic/src/rtl/tc_sram.sv',
           *(ROOT/f'hardware/src/vlsu/qbs/{n}.sv' for n in QBS))
BLOCKS = {1:(144,256),2:(210,256),3:(18,32),4:(176,256),5:(110,256),6:(34,32),
          7:(84,256),8:(22,32),9:(18,32)}
COUNTERS = ('tiles','weight','activation','pairs','capacity','dot','uops','updates')
REAL_SHA = {'real-m1.txt':'43e708aace40f353988b0d9112bd9e4658995802c032f6778a1adba466ab0682',
            'real-m4.txt':'80b27afd08cb584798ff7284c893e4ef28642b3a860aa4d898075f7c16f4b22a'}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda:stream.read(1048576),b''):
            h.update(data)
    return h.hexdigest()


def write_json(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def extend_generator(text):
    """Retain all 36 original cases/functions; add only missing tails and epoch probe."""
    anchor = '  fprintf(output, "QBSCMD1 36\\n");'
    end = '  fclose(output);\n  if (failed) return 1;\n  printf("wrote 36 QBS command cases to %s\\n", argv[1]);'
    require(text.count(anchor)==text.count(end)==1,'C generator anchor drift')
    extra = '''  for (unsigned p = 1; p <= 9; ++p) {
    unsigned id = 36 + (p - 1) * 3;
    failed |= emit_case(output, id, p, QBS_WEIGHT_LAYOUT_ROW_MAJOR,
                        QBS_ACTIVATION_LAYOUT_ROW_MAJOR, 3, 2, 2);
    failed |= emit_case(output, id+1, p, QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
                        QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED, 4, 4, 2);
    failed |= emit_case(output, id+2, p, QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
                        QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED, 8, 6, 2);
  }
  failed |= emit_case(output, 63, QBS_WEIGHT_PROFILE_Q4_K,
                      QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
                      QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED, 4, 9, 2);
'''
    return text.replace(anchor,anchor.replace('36','64'),1).replace(end,extra+end.replace('wrote 36','wrote 64'),1)


def combine_vectors(texts):
    result=[];count=0
    for text in texts:
        lines=text.splitlines();require(lines and lines[0].split()[:1]==['QBSCMD1'],'Vector header')
        original=int(lines[0].split()[1]);seen=0
        for line in lines[1:]:
            if line.startswith('CMD '):
                words=line.split();require(int(words[1])==seen,'Input ordinal')
                words[1]=str(count);count+=1;seen+=1;line=' '.join(words)
            result.append(line)
        require(seen==original,'Input count')
    return f'QBSCMD1 {count}\n'+'\n'.join(result)+'\n'


def expected_counters(shape, matrix=True):
    p,m,n,k=(shape[x] for x in ('profile','m','n','kb'))
    size,elements=BLOCKS[p];act=292 if elements==256 else 34
    storage=m if shape['al']==1 else 4 if shape['al']==2 else 8
    waves=[m] if m<=4 else [4,m-4]
    cycles=sum(elements//(4 if matrix and elements==256 and w>=3 else 8 if w==1 else 4 if w==2 else 2)
               for w in waves)
    tiles=k*((n+3)//4)
    return [tiles*len(waves),n*k*size,storage*k*act,m*n*k*elements,
            n*k*cycles*(16 if matrix else 8),tiles*cycles,m*n*k*(6 if p in (1,4,7) else 3),m*n*k]


def parse_vectors(text, matrix=True):
    lines=iter(text.splitlines())
    def take():
        try: return next(lines).split()
        except StopIteration: raise ValueError('Truncated vector') from None
    header=take();require(len(header)==2 and header[0]=='QBSCMD1','Vector header')
    count=int(header[1]);require(1<=count<=1000,'Vector count');result=[]
    for ordinal in range(count):
        row=take();require(len(row)==9 and row[0]=='CMD','Command schema')
        cid,p,wl,al,m,n,k=map(int,row[1:8]);flags=int(row[8],16)
        require(cid==ordinal and p in BLOCKS and wl in (1,2) and al in (1,2,3) and
                1<=m<=8 and 1<=n<=(16 if m>4 else 32) and 1<=k<=256 and 0<=flags<=31 and
                (al!=2 or m==4) and (al!=3 or m>4),'Command geometry')
        size,elements=BLOCKS[p];act=292 if elements==256 else 34
        storage=m if al==1 else 4 if al==2 else 8
        weights=bytearray(k*n*size);acts=bytearray(k*storage*act)
        for kk in range(k):
            for base in range(0,n,4):
                nr=min(4,n-base)
                require(take()==['T',str(kk),str(base),str(nr)],'Tile cursor')
                while True:
                    r=take()
                    if r==['ENDT']:break
                    require(len(r)==5 and r[0] in ('W','A') and re.fullmatch('[0-9a-fA-F]{4}',r[3]) and
                            re.fullmatch('[0-9a-fA-F]{32}',r[4]),'Native beat schema')
                    target,offset=int(r[1]),int(r[2]);mask=int(r[3],16)
                    require(mask>0 and mask&(mask+1)==0 and offset>=0,'Prefix/native range')
                    if r[0]=='W':
                        require(0<=target<nr and offset+mask.bit_length()<=size,'Weight range')
                        start=(kk*n+base+target)*size+offset;seen=weights
                    else:
                        require(base==0 and 0<=target<(m if al==1 else 1) and
                                offset+mask.bit_length()<=(act if al==1 else storage*act),'Activation range')
                        start=kk*storage*act+target*act+offset;seen=acts
                    for b in range(mask.bit_length()):
                        require(seen[start+b]==0,'Duplicate native byte');seen[start+b]=1
        require(all(weights) and all(acts),'Missing native bytes')
        output={};stride=16 if m>4 else 32
        for _ in range(m*n):
            r=take();require(len(r)==3 and r[0]=='O' and re.fullmatch('[0-9a-fA-F]{8}',r[2]),'Output schema')
            index=int(r[1]);require(index not in output and 0<=index//stride<m and 0<=index%stride<n,'Output owner')
            output[index]=int(r[2],16)
        r=take();require(len(r)==9 and r[0]=='C','Counter schema');c=list(map(int,r[1:]))
        shape=dict(case=cid,profile=p,wl=wl,al=al,m=m,n=n,kb=k,flags=flags,outputs=output,counters=c)
        require(c==expected_counters(shape,matrix),'Independent work counters')
        require(take()==['END'],'Command boundary');result.append(shape)
    require(next(lines,None) is None,'Trailing vector content')
    return result


def fields(line,tag,hex_fields=()):
    require(line.startswith(tag+' '),'Wrong tag');row={}
    for word in line.split()[1:]:
        key,sep,value=word.partition('=')
        pattern='[0-9a-fA-F]{8}' if key in hex_fields else '[0-9]+'
        require(sep and key not in row and re.fullmatch(pattern,value),'Malformed/duplicate trace field')
        row[key]=int(value,16 if key in hex_fields else 10)
    return row


def check_log(text,shapes,wide):
    require(not re.search(r'Fatal:|Error[-:]|Assertion.*failed|UVM_(?:FATAL|ERROR)',text),'Tool/assertion failure')
    records=defaultdict(list)
    allowed={'WC_CONFIG','WC_FP','WC_OUTPUT','WC_CASE','WC_FAULT','WC_PASS'}
    for line in text.splitlines():
        if not line.startswith('WC_'):continue
        tag=line.split()[0];require(tag in allowed,'Unexpected record')
        records[tag].append(fields(line,tag,('a','b','c') if tag=='WC_FP' else ('bits',) if tag=='WC_OUTPUT' else ()))
    require(records['WC_CONFIG']==[dict(version=1,wide=wide,weight_bits=256 if wide else 128,matrix=1)],'Elaborated configuration')
    episodes={i:s for i,s in enumerate(shapes)}
    episodes.update({1000+i:shapes[0] for i in range(5)})
    expected_order=[1000+i for i in range(5)]+list(range(len(shapes)))
    require([r.get('episode') for r in records['WC_CASE']]==expected_order,'Numerical/recovery case inventory/order')
    case_rows={};output=defaultdict(dict);events=defaultdict(list)
    for r in records['WC_OUTPUT']:
        require(set(r)=={'episode','index','bits'} and r['episode'] in episodes and
                r['index'] not in output[r['episode']],'Duplicate/unexpected output')
        output[r['episode']][r['index']]=r['bits']
    for r in records['WC_CASE']:
        eid=r['episode'];s=episodes[eid];c=s['counters']
        expected=dict(episode=eid,case=s['case'],recovery=int(eid>=1000),
                      **{k:s[k] for k in ('profile','m','n','kb','wl','al','flags')},
                      **dict(zip(COUNTERS,c)),accepted=c[1],act_accepted=c[2],result_wait=5)
        require(set(r)==set(expected)|{'beats','stalls','overlap','probe_edges','probe_bytes'} and
                all(r[k]==v for k,v in expected.items()),'Numerical/flags/work/result-hold mismatch')
        require(output[eid]==s['outputs'],'Output bytes differ from C reference')
        require(0<r['beats']<=r['accepted']<=r['beats']*(32 if wide else 16),'Transport accounting')
        probe=s['profile']==1 and s['m']==4 and s['n']==9 and s['kb']==2
        require((r['probe_edges']>0 and r['probe_bytes']>0 and r['probe_bytes']%64==0) if wide and probe
                else r['probe_edges']==r['probe_bytes']==0,'Owned 4-to-1 epoch metadata/window coverage')
        case_rows[eid]=r
    wanted_fp=set('episode acc block kind state op mod rm a b c'.split())
    for r in records['WC_FP']:
        require(set(r)==wanted_fp and r['episode'] in episodes,'FP event schema/owner')
        s=episodes[r['episode']]
        require(r['acc'] in s['outputs'] and r['block']<s['kb'],'FP event accumulator/block')
        state=r['state'];require(state in range(6) and r['kind']==(0 if state<2 else
            2 if state==2 and s['profile'] in (3,6,8,9) else 1),'FP operation port/state')
        events[(r['episode'],r['acc'])].append(r)
    for eid,s in episodes.items():
        seq=[0,1,2,3,4,5] if s['profile'] in (1,4,7) else [0,2,4]
        total=0
        for acc in s['outputs']:
            got=events[(eid,acc)]
            require([(r['block'],r['state']) for r in got]==[(k,st) for k in range(s['kb']) for st in seq],
                    'FP sequence missing/duplicated/reordered')
            total+=len(got)
        require(total==s['counters'][6],'FP issued-event conservation')
    faults=records['WC_FAULT']
    require(len(faults)==5 and all(set(r)=={'kind','pending','drain'} and r['kind']==i and
            r['pending']==int(i==0) and 0<r['drain']<=2048 for i,r in enumerate(faults)),'Pending/pipeline fault coverage')
    end=dict(normal=len(shapes),recovery=5,faults=5,
             overlap=sum(r['overlap'] for r in case_rows.values()),stalls=sum(r['stalls'] for r in case_rows.values()))
    require(records['WC_PASS']==[end] and end['overlap']>0 and end['stalls']>0,'Terminal/overlap/backpressure coverage')
    for p in range(1,10):
        require(any(r['profile']==p and r['n']>4 and r['overlap']>0 for r in case_rows.values()),
                'Missing profile-specific compute/prefetch overlap')
    return dict(cases=list(case_rows.values()),faults=faults,totals=end),events


def check_pair(base,wide,vector):
    shapes=parse_vectors(vector)
    require(any((s['profile'],s['m'],s['n'],s['kb'])==(1,4,9,2) for s in shapes),'Missing owned epoch probe fixture')
    b,be=check_log(base,shapes,0);w,we=check_log(wide,shapes,1)
    require(be==we,'FP operation operands/order differ per accumulator and K-block')
    return dict(state='WIDE_WEIGHT_COMPUTE_PAIR_PASS',matrix_dot=1,normal_per_image=len(shapes),
                recovery_per_image=5,faults_per_image=5,fp_event_count=sum(map(len,be.values())),
                fp_sequence_operands_equal=True,default=b,wide=w,
                limitations=['Compute component only, not reader/MMU/SoC/SDK or model performance',
                             'Generic actual SRAM only; no physical timing/area or speedup claim',
                             'Real M1 input is a Qwen2.5 prefill-row slice, not actual Decode'])


def preflight():
    for name,expected in FROZEN.items():
        require(digest(ROOT/'hardware/src/vlsu/qbs'/name)==expected,'Frozen RTL drift: '+name)
    require(len(SOURCES)==len(set(SOURCES)) and all(p.is_file() for p in SOURCES),'Minimal source inventory')
    require(not any(any(x in p.name for x in ('qbs_engine.','shared_reader','qbs_read_engine','akv')) for p in SOURCES),
            'Unneeded parallel-owned RTL in inventory')
    for name,expected in REAL_SHA.items():
        require(digest(PRIOR/name)==expected,'Accepted real vector identity')
    old=json.loads((PRIOR/'result.json').read_text())
    require(old['state']=='RTL_PORT_AUDIT_PASS' and all(old['artifacts'].get(str(PRIOR/n))==h for n,h in REAL_SHA.items()),
            'Accepted real vector artifact binding')
    return dict(sources=len(SOURCES),frozen=FROZEN,real_inputs='Accepted Qwen2.5 prefill M1/M4 K1536 N8')


def run(execute_frozen):
    require(execute_frozen,'Explicit frozen execution flag required')
    preflight();OUT.mkdir(exist_ok=False)
    pins={};commands=[]
    result=dict(state='WIDE_WEIGHT_COMPUTE_PAIR_FAIL',phase='PREPARING',retry_permitted=False,
                no_rtl_edits=True,soc_integrated=False,performance_measured=False,area_measured=False)
    def pin(path,expected=None):
        p=Path(path).resolve(strict=True);h=digest(p)
        require(expected is None or h==expected,'Identity mismatch: '+str(p))
        require(str(p) not in pins or pins[str(p)]==h,'Input drift: '+str(p));pins[str(p)]=h
    def verify():
        for p,h in pins.items(): require(digest(p)==h,'Execution pin drift: '+p)
    def command(argv,label,bound):
        argv=list(map(str,argv));exe=shutil.which(argv[0]);require(exe is not None,'Missing tool '+argv[0]);argv[0]=exe;pin(exe)
        verify();result['phase']=label
        entry=dict(argv=argv,label=label,timeout=bound);commands.append(entry)
        with (OUT/(label+'.log')).open('xb') as stream:
            child=subprocess.Popen(argv,cwd=OUT,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
            try:code=child.wait(timeout=bound)
            except BaseException:
                os.killpg(child.pid,signal.SIGKILL);child.wait();raise
        entry['returncode']=code;verify()
        text=(OUT/(label+'.log')).read_text()
        require(code==0 and not re.search(r'Fatal:|Error[-:]|Assertion.*failed|UVM_(?:FATAL|ERROR)',text),
                'First failure preserved: '+label)
        return text
    try:
        snapshot=OUT/'source-snapshot';snapshot.mkdir()
        for path in (*OWNED,*SOURCES):
            pin(path,FROZEN.get(path.name));dest=snapshot/path.name
            require(not dest.exists(),'Snapshot basename collision')
            with dest.open('xb') as stream:stream.write(path.read_bytes())
            pin(dest,pins[str(path)])
        for path in (ROOT/'hardware/deps/common_cells/include').rglob('*.svh'):pin(path)
        for name in ('matrix_dot_pair.py','projection_resources.py','audit.py'):pin(HERE/name)
        for path in (PRIOR/'result.json',ROOT/'verification/performance/evidence/projection_resources_20261106_01/result.json',
                     ROOT/'verification/qbs/qbs_command_vectors.c',ROOT/'verification/qbs/qbs_ref.c',
                     ROOT/'verification/qbs/qbs_ref.h'):
            pin(path)
        receipt=json.loads((ROOT/'verification/performance/evidence/projection_resources_20261106_01/result.json').read_text())
        require(receipt['run_result_sha256']==digest(PRIOR/'result.json'),'Compact receipt binding')
        for name,h in REAL_SHA.items():pin(PRIOR/name,h)
        pin(Path(sys.executable));write_json(OUT/'helpers-frozen.json',{str(p):pins[str(p)] for p in OWNED})
        command([sys.executable,'-B',snapshot/'test_wide_compute.py'],'unit-tests',60)
        oracle=OUT/'oracle';oracle.mkdir();source=oracle/'qbs_command_vectors.c'
        source.write_text(extend_generator((ROOT/'verification/qbs/qbs_command_vectors.c').read_text()));pin(source)
        cc=['gcc','-O2','-std=c11','-Wall','-Wextra','-Werror','-ffp-contract=off','-frounding-math',
            '-I'+str(ROOT/'verification/qbs')]
        inputs=[source,ROOT/'verification/qbs/qbs_ref.c']
        for i,path in enumerate(inputs):
            deps=command([*cc,'-M','-MT','object',path],f'generator-deps-{i}',60)
            for name in shlex.split(deps.replace('\\\n',' ').split(':',1)[1]):pin(OUT/name if not Path(name).is_absolute() else name)
        generator=oracle/'generator';command([*cc,*inputs,'-lm','-o',generator],'generator-compile',120);pin(generator)
        raw=oracle/'synthetic64.txt';command([generator,raw],'generator',120);pin(raw)
        merged=combine_vectors([raw.read_text(),*((PRIOR/n).read_text() for n in REAL_SHA)])
        parse_vectors(merged,matrix=False)
        sys.path.insert(0,str(HERE))
        from matrix_dot_pair import candidate_vectors
        vector=OUT/'vectors-matrix1.txt';vector.write_text(candidate_vectors(merged));pin(vector)
        shapes=parse_vectors(vector.read_text());require(len(shapes)==66,'Fixture count')
        require({s['profile'] for s in shapes}==set(range(1,10)) and set(range(1,8))<={s['n'] for s in shapes},'Fixture coverage')
        write_json(OUT/'fixture.json',dict(cases=66,original=36,tail_cases=27,owned_epoch_case=63,
                   real_cases=[64,65],real_input_scope=preflight()['real_inputs'],
                   shared_arithmetic='WideMatrixDot=1 for BOTH ingress widths; identical O/flags/C/payloads',
                   shapes=[{k:v for k,v in s.items() if k!='outputs'} for s in shapes]))
        vcs=shutil.which('vcs');require(vcs is not None,'VCS unavailable');pin(vcs)
        pin(Path(vcs).resolve().parent.parent/'linux64/bin/vcs1')
        write_json(OUT/'source-pins-precompile.json',pins)
        images=[]
        for mode in (0,1):
            build=OUT/f'build-{mode}';build.mkdir();image=build/'simv'
            command([vcs,'-full64','-sverilog','-timescale=1ns/1ps','-assert','svaext',
                     '+incdir+'+str(ROOT/'hardware/deps/common_cells/include'),
                     *(snapshot/p.name for p in SOURCES),snapshot/'qbs_wide_compute_tb.sv',
                     '-top','qbs_wide_compute_tb',f'-pvalue+qbs_wide_compute_tb.Wide={mode}',
                     '-Mdir='+str(build/'csrc'),'-o',image],f'compile-{mode}',300)
            pin(image);libraries=list(build.rglob('*.so'));require(libraries,'Missing VCS libraries')
            for path in libraries:pin(path)
            images.append(image)
        write_json(OUT/'source-pins-presimulation.json',pins)
        logs=[command([image,'+QBS_COMMAND_VECTOR_FILE='+str(vector)],f'run-{mode}',300)
              for mode,image in enumerate(images)]
        measured=check_pair(*logs,vector.read_text());write_json(OUT/'measured.json',measured)
        verify();result.update(state=measured['state'],phase='COMPLETE',post_pins_match=True,
                               normal_per_image=66,recovery_per_image=5,faults_per_image=5,
                               fp_sequence_operands_equal=True)
    except Exception as exc:
        result.update(error=repr(exc),first_failure_preserved=True)
    verify();write_json(OUT/'commands.json',commands);write_json(OUT/'source-pins.json',pins)
    result['source_pins_sha256']=digest(OUT/'source-pins.json')
    result['artifacts']={str(p):digest(p) for p in OUT.iterdir() if p.is_file()}
    write_json(OUT/'result.json',result)
    print(json.dumps(dict(state=result['state'],phase=result['phase'],output=str(OUT),
                          result_sha256=digest(OUT/'result.json'),error=result.get('error'))))
    return 0 if result['state']=='WIDE_WEIGHT_COMPUTE_PAIR_PASS' else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-frozen',action='store_true')
    parser.add_argument('--preflight',action='store_true')
    args=parser.parse_args()
    if args.preflight:print(json.dumps(preflight(),indent=2))
    else:sys.exit(run(args.execute_frozen))
