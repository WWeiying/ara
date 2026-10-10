"""One scalar radix16 native qualification, independent scalar DIV/SQRT evidence."""
import argparse
import csv
import gzip
import json
from pathlib import Path
import re
import shutil
import sys
import types
import xml.etree.ElementTree as ET
import capture_scalar_fma8 as launch
import run_scalar_divsqrt_finite as fixture

life,require,tools=launch.life,launch.require,launch.tools
HERE=Path(__file__).resolve().parent
SOURCE_REVIEW=fixture.QUAL/'arithmetic-source-review.json'
REVIEW_SHA='72a632ba4ff352a81a00350f79bba400a90f009386b14e0697e05a7002adc829'
QUAL_SHA='a5b6ebf7704f62f9190b53582e94a87f28f8831060e183d0d23432ac9f596cfd'
TCL=HERE/'capture_scalar_radix158.tcl'


def source_signals(review):
    require(review['physical_scalar_instances']==1 and review['scope']==fixture.CHILD and
        review['objects']==158 and review['protected_objects']==52 and review['upstream_bytes_equal'] and
        not review['vector_architecture_borrowed'] and not review['native_approval'],'Wrong approved scalar scope')
    result=[]
    for n in review['signals']:
        require(n['kind']=='vectornode' and n['portnode']=='0' and n['excluded']=='0' and n['file']=='375',
                'Port/preexcluded/foreign target')
        match=re.fullmatch(r'\s*(reg|wire)\s+\[[^]]+\]\s+'+re.escape(n['name'])+r'\s*;\s*',n['declaration'])
        require(match is not None,'Source whole-object type declaration differs')
        result.append(dict(n,left=int(n['left']),right=int(n['right']),source_type=match.group(1),
            native_name=n['name']+'[%s:%s]'%(n['left'],n['right'])))
    require(len(result)==len({n['name'] for n in result})==158 and sum(n['width'] for n in result)==9684,
        'Not exact158/9684 scalar source objects')
    return result


def candidate(c):
    i=c['instance']
    lines=['CHECKSUM: "'+i['design_module_checksum']+' '+i['toggle_checksum']+'"','INSTANCE: '+i['scope']]
    for s in i['signals']:
        kind='reg' if s['source_type']=='reg' else 'net'
        lines.append('Toggle '+s['name']+' "'+kind+' '+s['native_name']+'"')
    return '\n'.join(lines)+'\n'


def records(text,c):
    i=c['instance'];expected={s['name']:s for s in i['signals']};scope=None;checksum=None;blocks=0;found={}
    for raw in text.splitlines():
        line=raw.strip()
        if not line or line.startswith('//'):continue
        if line.startswith('ANNOTATION:'):
            require(re.fullmatch(r'ANNOTATION: "[^"\r\n]*"',line),'Malformed annotation')
        elif line.startswith('CHECKSUM:'):
            require(checksum is None,'Duplicate checksum block')
            m=re.fullmatch(r'CHECKSUM: "(\d+) (\d+)"',line)
            require(m is not None,'Malformed checksum');checksum=m.groups()
        elif line.startswith('INSTANCE:'):
            scope=line[len('INSTANCE:'):].strip();blocks+=1
            require(blocks==1 and scope==i['scope'] and checksum==(i['design_module_checksum'],i['toggle_checksum']),
                'Not exact scalar instance/checksum')
        else:
            m=re.fullmatch(r'Toggle (\w+) "(reg|wire|net|logic) (\w+)\[(\d+):(\d+)\]"',line)
            require(scope is not None and m is not None,'Unknown directive/type/direction')
            name,kind,decl,left,right=m.groups();s=expected.get(name)
            require(s is not None and decl==name and (int(left),int(right))==(s['left'],s['right']),
                'Unapproved field/full bounds differs')
            allowed=('reg','logic') if s['source_type']=='reg' else ('wire','net')
            require(kind in allowed,'Native/source type differs')
            require(name not in found,'Duplicate native object')
            found[name]=(scope,*checksum,s['source_type'],int(left),int(right))
    require(blocks==1 and len(expected)==len(found)==158 and set(expected)==set(found),'Not exact158 native objects')
    return sorted((name,*record) for name,record in found.items())


def inventory(out,c,stage):
    require(stage in ('before','selected','reset','reloaded','final'),'Unknown inventory stage')
    with (out/('native_'+stage+'_0.tsv')).open(newline='') as stream:
        reader=csv.DictReader(stream,delimiter='\t')
        require(reader.fieldnames==['handle','path','meta','name'],'Native header differs')
        rows=list(reader)
    require(len(rows)==210 and all(set(r)==set(reader.fieldnames) and all(r.values()) for r in rows),
        'Not complete158+52 native inventory')
    require(all(len({r[k] for r in rows})==210 for k in ('path','name')),'Ambiguous native identity')
    require({r['name'] for r in rows}==set(c['instance']['protected'])|
        {s['native_name'] for s in c['instance']['signals']},'Native target/protected identity union differs')
    return [(r['path'],r['meta'],r['name']) for r in rows]


def prepare(out):
    require(out.parent==life.OUT and out.resolve()==out and not out.exists(),'Fresh output required')
    r=life.read_bound(SOURCE_REVIEW,REVIEW_SHA)
    q=life.read_bound(fixture.QUAL/'qualification.json',QUAL_SHA)
    require(q['status']=='EXACT20_SCALAR_FP_RATIONAL_SPIKE_DUT_QUALIFIED' and
        (q['operations'],q['result_flags_checks'],q['guard_checks'])==(20,40,35),'Own scalar qualified20 required')
    pins=life.merge_pins(life.merge_pins(r['pins'],q['input_pins']),q['output_pins'])
    pins=life.merge_pins(pins,{str(SOURCE_REVIEW):REVIEW_SHA,str(fixture.QUAL/'qualification.json'):QUAL_SHA})
    life.check(pins)
    book=life.read_bound(fixture.old.BUILD/'build-source-pins.json',fixture.old.SOURCE_SHA)
    pins,actual=fixture.source_review(pins,book)
    for key in ('scope','signals','protected','wrapper','source_sha256','design_module_checksum','toggle_checksum'):
        require(r[key]==actual[key],'Actual compiled/source review differs: '+key)
    signals=source_signals(r)
    protected=[n['name']+('[%s:%s]'%(n['left'],n['right']) if n['kind']=='vectornode' else '') for n in r['protected']]
    require(len(protected)==len(set(protected))==52 and not set(protected)&{s['native_name'] for s in signals},
        'Protection partition differs')
    info=fixture.old.BUILD/'sim/simv.vdb/snps/coverage/db/shape/tgl.verilog.info.xml'
    descendants=[dict(n.attrib) for n in ET.fromstring(gzip.decompress(info.read_bytes())).iter('instance_data')
        if n.get('name','').startswith(r['scope']+'.')]
    require(descendants and any('.x_ct_vfdsu_srt_radix16_bound_table' in n['name'] for n in descendants),
        'Protected boundary descendant absent')
    instance=dict(scope=r['scope'],signals=signals,protected=protected,protected_typed_objects=r['protected'],
        design_module_checksum=r['design_module_checksum'],toggle_checksum=r['toggle_checksum'],
        all_descendants_protected=True,protected_descendants=descendants)
    identity=tools.prepare(shutil.which('dve'),'/usr/bin/xvfb-run')
    for p in (Path(__file__).resolve(),HERE/'test_capture_scalar_radix158.py',TCL,Path(launch.__file__).resolve(),
        HERE/'c910_srt_datapath_native_v3.tcl',HERE/'fma_datapath_native.tcl',Path(tools.__file__).resolve()):
        pins=life.merge_pins(pins,{str(p):life.digest(p)})
    pins=life.merge_pins(pins,{f['path']:f['sha256'] for f in identity['files']});life.check(pins)
    vdb=fixture.RUN/'code.vdb';tests=list((vdb/'snps/coverage/db/testdata').iterdir())
    require(len(tests)==1 and tests[0].name=='scalar_divsqrt_finite','Not sole own scalar DIV/SQRT test')
    values=dict(fma_design=str(fixture.old.BUILD/'sim/simv.vdb'),fma_vdb=str(vdb),
        fma_test=str(vdb.with_suffix('')/tests[0].name),fma_python=sys.executable,fma_helper=str(Path(__file__).resolve()),
        c910_fma_tcl=str(HERE/'fma_datapath_native.tcl'))
    require(all(not any(ch in v for ch in '{}\\\n\r') for v in values.values()),'Unsafe Tcl value')
    selection=''.join('set '+k+' {'+v+'}\n' for k,v in values.items())
    selection+='set fma_instances [list [list {'+instance['scope']+'} {'+' '.join(s['native_name'] for s in signals)+'} {'+' '.join(protected)+'} 0]]\n'
    c=dict(output=str(out),pins=pins,identity=identity,instance=instance,objects=158,logical_bits=9684,
        scalar_qualification_sha256=QUAL_SHA,source_review_sha256=REVIEW_SHA,timeout_seconds=600,
        input_VDB_count=1,native_test=values['fma_test'],automatic_retry=False,population_application=False)
    text=candidate(c);records(text,c);out.mkdir()
    for name,value in (('selection.tcl',selection),('candidate.el',text),('capture.tcl',TCL.read_text())):
        launch.primitive.one.common.save(out/name,value);pins[str(out/name)]=life.digest(out/name)
    life.save(out/'config.json',c)
    print(json.dumps(dict(output=str(out),seal=life.digest(out/'config.json'),pins=len(pins),objects=158)),flush=True)


def verify(out,seal):
    c=life.read_bound(out/'config.json',seal);life.check(c['pins']);tools.revalidate(c['identity'])
    terminal=json.loads((out/'terminal.json').read_bytes())
    require(terminal['returncode']==0 and not terminal['timeout'] and len(terminal['actual_dve'])==1,'Terminal identity failed')
    gui=(out/'DVEfiles/dve_gui.log').read_text()
    require(gui.splitlines().count('SCALAR_RADIX158_NATIVE_DONE')==1 and
        'C910_SRT_NATIVE_CAPTURE_FAILED' not in gui,'Native session failed')
    require(records((out/'first.el').read_text(),c)==records((out/'second.el').read_text(),c),'Full typed native reload differs')
    for name in ('initial-empty.el','reset-empty.el','final-empty.el'):
        require((out/name).read_bytes()==b'','Not global empty')
    before=inventory(out,c,'before')
    for stage in ('selected','reset','reloaded','final'):
        require(inventory(out,c,stage)==before,'Native target/protection metadata drift')
    life.check(c['pins'])
    result=dict(status='SCALAR_RADIX158_NATIVE_ROUNDTRIP_QUALIFIED_NOT_POPULATION_APPLICATION',
        config_seal=seal,scalar_qualification_sha256=QUAL_SHA,source_review_sha256=REVIEW_SHA,
        objects=158,logical_bits=9684,protected_local_objects=52,all_descendants_protected=True,
        both_directions=True,semantic_reload=True,finalreset=True,non_target_exclusions=0,
        vector_architecture_borrowed=False,population_application=False,official_denominator=False,
        pins=life.merge_pins(c['pins'],{str(p):life.digest(p) for p in out.rglob('*') if p.is_file()}))
    life.check(result['pins']);life.save(out/'capture-result.json',result)
    print('QUALIFIED '+life.digest(out/'capture-result.json'),flush=True)


def run(out,seal):
    worker=types.FunctionType(launch.run.__code__,dict(launch.run.__globals__,verify=verify),launch.run.__name__)
    worker(out,seal)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=('prepare','run','verify','el','inventory'))
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--seal');parser.add_argument('--file',choices=('first.el','second.el'))
    parser.add_argument('--stage');parser.add_argument('--index',type=int)
    a=parser.parse_args();out=a.output.absolute()
    if a.mode=='prepare':prepare(out)
    elif a.mode in ('el','inventory'):
        c=json.loads((out/'config.json').read_bytes())
        if a.mode=='el':
            require(a.file is not None,'EL file required');print(json.dumps(dict(objects=len(records((out/a.file).read_text(),c)))))
        else:
            require(a.index==0,'Only scalar index0');print(json.dumps(dict(native_rows=len(inventory(out,c,a.stage)))))
    else:
        require(a.seal,'Config seal required');(run if a.mode=='run' else verify)(out,a.seal)
