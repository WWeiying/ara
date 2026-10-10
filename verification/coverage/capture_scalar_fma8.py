"""One scalar F/D whole-object native qualification; no population report."""
import argparse
import gzip
import json
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import fma_datapath_native as primitive
import run_scalar_fpu_finite as fixture

life, require, tools = primitive.life, primitive.require, primitive.tools
HERE = Path(__file__).resolve().parent
REVIEW = life.OUT/'scalar-fpu-arithmetic-review-agent-20261007-01.json'
REVIEW_SHA = '500ede40b60be2e217b270ad0d41cf2daf3a93c477a1ccab2efb030ed3f02f7f'


def records(text, c):
    expected = {i['scope']: i for i in c['instances']}
    found = {}; scope = None; checksum = None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('//'):
            continue
        if line.startswith('ANNOTATION:'):
            require(line == 'ANNOTATION: "Approved unchanged local FMA datapath integration scope; all other signals retained"', 'Unknown annotation')
        elif line.startswith('CHECKSUM:'):
            m = re.fullmatch(r'CHECKSUM: "(\d+) (\d+)"', line)
            require(m is not None, 'Malformed checksum')
            checksum = m.groups(); scope = None
        elif line.startswith('INSTANCE:'):
            scope = line[len('INSTANCE:'):].strip()
            require(scope in expected and checksum == (expected[scope]['design_module_checksum'],
                expected[scope]['toggle_checksum']), 'Scope/checksum differs')
        else:
            m = re.fullmatch(r'Toggle (\w+) "logic (\w+)\[(\d+):(\d+)\]"', line)
            require(scope is not None and m is not None, 'Unexpected native directive')
            name, signature, left, right = m.groups()
            wanted = {s['name']: s for s in expected[scope]['signals']}
            require(name in wanted and signature == name and (int(left),int(right)) ==
                (wanted[name]['left'],wanted[name]['right']), 'Signal/type/full bounds differ')
            require((scope,name) not in found, 'Duplicate object')
            found[scope,name] = (*checksum,int(left),int(right))
    wanted = {(i['scope'],s['name']) for i in c['instances'] for s in i['signals']}
    require(len(wanted)==8 and set(found)==wanted, 'Not exact eight complete objects')
    return sorted((scope,name,*v) for (scope,name),v in found.items())


def prepare(out):
    require(out.parent==life.OUT and out.resolve()==out and not out.exists(), 'Fresh output required')
    r = life.read_bound(REVIEW,REVIEW_SHA)
    life.check(r['pins'])
    require(r['initial_objects']==8 and r['initial_logical_bits']==871 and not r['native_exclusion_approved'],
        'Reviewed source scope differs')
    pins = life.merge_pins(r['pins'],{str(REVIEW):REVIEW_SHA})
    pins, rebuilt = fixture.compiled(pins)
    require([{k:i[k] for k in ('scope','checksum','compiled_parameters','targets')} for i in rebuilt] ==
        [{k:i[k] for k in ('scope','checksum','compiled_parameters','targets')} for i in r['instances']],
        'Actual compiled specialization differs from review')
    design = fixture.old.BUILD/'sim/simv.vdb/snps/coverage/db/design/verilog.design.xml'
    defs = ET.fromstring(gzip.decompress(design.read_bytes())).findall('srcdef')
    modules = [d for d in defs if d.get('name')=='fpnew_fma']
    require(len(modules)==1 and modules[0].get('chksum')=='2431620414', 'Module source checksum differs')
    instances = []
    for i in r['instances']:
        signals = [dict(s,name=s['name'],left=int(s['left']),right=int(s['right'])) for s in i['targets']]
        complements = i['field_partition']['extension_seven_source_candidates'] + i['field_partition']['protected_from_family51'] + i['other_protected']
        require(not ({s['name'] for s in signals} & {s['name'] for s in complements}), 'Protected overlap')
        instances.append(dict(scope=i['scope'],design_module_checksum='2431620414',toggle_checksum=i['checksum'],
            signals=signals,protected_typed_complement=complements,all_descendants_protected=True))
    # Reuse the established selection/session primitive, changing only exact cardinality and merge name.
    source = HERE/'fma_datapath_native.tcl'
    tcl = source.read_text()
    require(tcl.count('[llength $fma_rows] == 9')==1, 'Primitive cardinality contract differs')
    tcl = tcl.replace('[llength $fma_rows] == 9','[llength $fma_rows] == 4').replace('Not nine unique','Not four unique').replace('FMA108NativeOnly','ScalarFMA8NativeOnly')
    identity = tools.prepare(shutil.which('dve'),'/usr/bin/xvfb-run')
    for p in (Path(__file__).resolve(),HERE/'test_capture_scalar_fma8.py',source,Path(primitive.__file__).resolve(),
              Path(primitive.one.__file__).resolve(),Path(tools.__file__).resolve()):
        pins = life.merge_pins(pins,{str(p):life.digest(p)})
    pins = life.merge_pins(pins,{item['path']:item['sha256'] for item in identity['files']})
    life.check(pins)
    vdb = fixture.RUN/'code.vdb'
    tests = list((vdb/'snps/coverage/db/testdata').iterdir())
    require(len(tests)==1 and tests[0].name=='scalar_fpu_finite', 'Not exact qualified scalar test')
    values = dict(fma_design=str(fixture.old.BUILD/'sim/simv.vdb'),fma_vdb=str(vdb),
        fma_test=str(vdb.with_suffix('')/tests[0].name),fma_python=sys.executable,fma_helper=str(Path(__file__).resolve()))
    require(all(not any(ch in v for ch in '{}\\\n\r') for v in values.values()), 'Unsafe Tcl scalar')
    lines = ['set '+k+' {'+v+'}\n' for k,v in values.items()] + ['set fma_instances {}\n']
    for n,i in enumerate(instances):
        names = ' '.join(s['name']+'[%d:%d]'%(s['left'],s['right']) for s in i['signals'])
        lines.append('lappend fma_instances [list {'+i['scope']+'} {'+names+'} {} '+str(n)+']\n')
    candidate = primitive.candidate_text(instances)
    records(candidate,dict(instances=instances))
    out.mkdir()
    for name,text in (('selection.tcl',''.join(lines)),('capture.tcl',tcl),('candidate.el',candidate)):
        primitive.one.common.save(out/name,text)
        pins[str(out/name)] = life.digest(out/name)
    c = dict(output=str(out),pins=pins,identity=identity,instances=instances,logical_bits=871,
        timeout_seconds=600,input_VDB_count=1,selected_test=values['fma_test'],population_application=False,
        source_basis='Unchanged reused arithmetic integration scope, not unreachability',automatic_retry=False)
    life.save(out/'config.json',c)
    print(json.dumps(dict(output=str(out),seal=life.digest(out/'config.json'),objects=8,pins=len(pins))),flush=True)


def verify(out,seal):
    c = life.read_bound(out/'config.json',seal); life.check(c['pins']); tools.revalidate(c['identity'])
    t = json.loads((out/'terminal.json').read_bytes())
    require(t['returncode']==0 and not t['timeout'] and len(t['actual_dve'])==1, 'Terminal tool identity failed')
    gui = (out/'DVEfiles/dve_gui.log').read_text()
    require(gui.splitlines().count('FMA_DATAPATH_NATIVE_CAPTURE_DONE')==1 and
        'FMA_DATAPATH_NATIVE_CAPTURE_FAILED' not in gui and 'FMA_CLEANUP_FAILED' not in gui, 'Session failed')
    require(records((out/'first.el').read_text(),c)==records((out/'second.el').read_text(),c), 'Full identity reload differs')
    for name in ('initial-empty.el','reset-empty.el','final-empty.el'):
        require((out/name).read_bytes()==b'', 'Not global empty')
    for n in range(2):
        def rows(stage):
            return [tuple(line.split('\t')[1:]) for line in (out/('native_%s_%d.tsv'%(stage,n))).read_text().splitlines()[1:]]
        before = rows('before')
        require(before and len(before)==len(set(before)), 'Ambiguous full typed inventory')
        for stage in ('selected','reset','reloaded','final'):
            require(rows(stage)==before, 'Protected inventory/path/meta/type changed')
    life.save(out/'capture-result.json',dict(status='EXACT_SCALAR_FMA8_NATIVE_ROUNDTRIP_QUALIFIED',
        objects=8,logical_bits=871,config_seal=seal,semantic_reload=True,global_empty_resets=True,
        full_typed_complements_protected=True,all_other_scopes_protected=True,population_application=False,
        official_denominator=False,pins={**c['pins'],**{str(p):life.digest(p) for p in out.rglob('*') if p.is_file()}}))
    print('QUALIFIED '+life.digest(out/'capture-result.json'),flush=True)


def run(out,seal):
    c = life.read_bound(out/'config.json',seal); life.check(c['pins']); tools.revalidate(c['identity'])
    env = tools.controlled_environment(c['identity'],os.environ);env.pop('DVE',None);env['DVE_COVERAGE_OUTPUT']=str(out)
    cmd = ['/usr/bin/xvfb-run','-a','-e',str(out/'xvfb.log'),'-s','-screen 0 1280x1024x24',
        c['identity']['roles']['launcher'],'-full64','-cov','-script',str(out/'capture.tcl')]
    life.save(out/'execution.json',dict(command=cmd,automatic_retry=False))
    with (out/'launcher.log').open('x') as log:
        p = subprocess.Popen(cmd,cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        start = tools.process_info(p.pid)['starttime']
        time.sleep(10);live=[]
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit():continue
            try:
                if (proc/'exe').resolve()==Path(c['identity']['executable']) and (proc/'cwd').resolve()==out:
                    tools.verify_live_executable(int(proc.name),c['identity'],p.pid,start)
                    live.append(dict(pid=int(proc.name),exe=str((proc/'exe').resolve()),cwd=str(out)))
            except (OSError,ProcessLookupError):pass
        life.save(out/'live-identity.json',live);print(json.dumps(dict(actual_dve=live)),flush=True)
        timeout=False
        try:p.wait(timeout=600)
        except subprocess.TimeoutExpired:
            timeout=True;os.killpg(p.pid,signal.SIGTERM)
            try:p.wait(timeout=10)
            except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
    life.save(out/'terminal.json',dict(returncode=p.returncode,timeout=timeout,actual_dve=live))
    verify(out,seal)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','run','verify','el'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal');p.add_argument('--file',choices=('first.el','second.el'))
    a=p.parse_args();out=a.output.absolute()
    if a.mode=='prepare':prepare(out)
    elif a.mode=='el':
        require(a.file is not None,'EL file required');c=json.loads((out/'config.json').read_bytes())
        print(json.dumps(dict(objects=len(records((out/a.file).read_text(),c)))))
    else:
        require(a.seal,'Config seal required');(run if a.mode=='run' else verify)(out,a.seal)
