"""Read-only fresh MFPU272 typed binding, never an exclusion/application receipt."""
import argparse
import itertools
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time

import mfpu_constants272_sourcefirst770 as source
import c910_pack_literal_native770 as pack
from inventory_operand_debug import Design

life,require,tools=pack.life,pack.require,pack.tools
HERE=Path(__file__).resolve().parent
TCL=Path(__file__).with_suffix('.tcl')
SOURCE_SHA='c952ffb9e09569c219b0a0cc878478a5941c603f02a92eb9b55662d098cc3215'
TEMPLATE=life.OUT/'c910-pack-literal323-native770-agent-20261007-01/config.json'
TEMPLATE_SHA='907eb24fde860473d69c5a145a14dc757d5f400899869c3accb6ad03d6f3d3e6'
SCHEMA='MFPU272_READONLY_FRESH_TYPED_BINDING_V1'
ROOT_LIBRARY=HERE/'apply_points740_v4.tcl'
WALK_LIBRARY=HERE/'cva6_fixed_fields_native768.tcl'


def dimensions(n):
    if n['kind']=='node':return []
    if n['kind']=='vectornode':return [(int(n['left']),int(n['right']))]
    require(n['kind']=='arrays','Unknown compiled typed object')
    values=(n.get('unpackedrange','')+' '+n.get('packedrange','')).split()
    require(values and len(values)%2==0,'Exact ordered array dimensions required')
    return [(int(values[i]),int(values[i+1])) for i in range(0,len(values),2)]


def normalize_name(name):
    return re.sub(r'\[(-?\d+):\1\]',r'[\1]',name)


def match_label(n,label,row_type):
    """Accept only full declared ranges or complete indexed array elements."""
    name=n['name'];dims=dimensions(n)
    expected=name+''.join('[%d:%d]'%p for p in dims)
    if normalize_name(label)==normalize_name(expected):return ('aggregate',None)
    if n['kind']=='vectornode' and dims==[(0,0)] and n['portnode'] in ('2','3'):
        if label==name and row_type=='port':return ('aggregate',None)
    if n['kind']!='arrays' or not label.startswith(name):return None
    suffix=label[len(name):]
    parts=re.findall(r'\[(-?\d+)(?::(-?\d+))?\]',suffix)
    if ''.join('['+a+(':'+b if b else '')+']' for a,b in parts)!=suffix:return None
    if not parts or len(parts)>len(dims):return None
    indices=[]
    for index,(a,b) in enumerate(parts):
        hi,lo=dims[index];value=int(a)
        if b:
            if (value,int(b))!=(hi,lo):return None
            if any(pair!=dim for pair,dim in
                   zip([(int(x),int(y)) if y else None for x,y in parts[index:]],dims[index:])):return None
            if len(parts)!=len(dims):return None
            kind='aggregate' if index==0 else 'element' if index==len(dims)-1 else 'container'
            return (kind,tuple(indices))
        if not min(hi,lo)<=value<=max(hi,lo):return None
        indices.append(value)
    return ('container',tuple(indices)) if len(indices)<len(dims) else None


def bind_inventory(instance,text):
    rows=pack.native.native_rows(text)
    objects=instance['typed_objects'];names={n['name'] for n in objects}
    require(len(names)==len(objects),'Duplicate compiled names')
    owners={name:[] for name in names}
    for label,row in rows.items():
        matches=[(n,match_label(n,label,row['type'])) for n in objects]
        matches=[(n,m) for n,m in matches if m is not None]
        require(len(matches)==1,'Unknown/ambiguous native source object: '+label)
        n,match=matches[0]
        require(row['type'] and (n['portnode'] in ('2','3'))==(row['type']=='port'),
                'Native port/internal role differs: '+label)
        owners[n['name']].append((label,match))
    for n in objects:
        bound=owners[n['name']];require(bound,'Missing compiled object: '+n['name'])
        aggregate=[label for label,(kind,_) in bound if kind=='aggregate']
        require(len(aggregate)<=1,'Non-bijective aggregate alias: '+n['name'])
        if n['kind']!='arrays':require(len(bound)==1 and len(aggregate)==1,'Vector/scalar identity is not unique')
        elif not aggregate:
            dims=dimensions(n);leaves={index for _,(kind,index) in bound if kind=='element' and len(index)==len(dims)-1}
            expected=set(itertools.product(*(range(min(a,b),max(a,b)+1) for a,b in dims[:-1])))
            require(leaves==expected,'Incomplete ordered array element inventory: '+n['name'])
            require(all(len(index)<len(dims) for _,(_,index) in bound),'Bit-flattened array inventory not accepted')
    targets=[]
    for target in instance['targets']:
        source.target_guard(target['attributes'])
        values=owners[target['name']];require(len(values)==1,'Target native label not unique')
        label=values[0][0];row=rows[label]
        targets.append(dict(name=target['name'],native_label=label,native_path=row['path'],native_meta=row['meta'],
            native_type=row['type'],left=63,right=0,bits=list(range(64)),scalar=False,
            constant_hex=target['constant_hex'],shape=target['attributes']))
    return dict(scope=instance['scope'],design_module_checksum=instance['design_module_checksum'],
        toggle_checksum=instance['toggle_checksum'],signals=targets,
        reference=sorted([row['path'],row['meta'],name] for name,row in rows.items()),
        native_rows=rows,compiled_object_count=len(objects),actual_row_count=len(rows),
        array_bindings={n['name']:[label for label,_ in owners[n['name']]] for n in objects if n['kind']=='arrays'})


def compiled_instances(s):
    template=life.read_bound(TEMPLATE,TEMPLATE_SHA)
    design=Design(Path(template['design']))
    instances=[]
    for original in [*s['instances'],*s['protected_children']]:
        scope=original['scope'];definition=design.definition(scope,'tgl')
        require(design.hierarchy[scope].get('chksum')==original['design_module_checksum'] and
                definition.get('chksum')==original['toggle_checksum'] and
                definition.get('name').split(' (')[0]==original['module'],
                'Compiled scope/module/checksum drift: '+scope)
        typed=[dict(n.attrib,kind=n.tag,compiled_xml=source.ET.tostring(n,encoding='unicode'))
               for n in definition.find('tglshape')]
        if 'targets' in original:
            expected={n['name']:n for n in [*(t['attributes'] for t in original['targets']),*original['protected']]}
            require({n['name']:n for n in typed}==expected,'Full source inventory differs')
        instances.append(dict(scope=scope,design_module_checksum=original['design_module_checksum'],
            toggle_checksum=original['toggle_checksum'],typed_objects=typed,
            targets=original.get('targets',[]),protected_child='targets' not in original))
    require(len(instances)==788 and len({i['scope'] for i in instances})==788 and
            sum(len(i['targets']) for i in instances)==272,'Exact44/744/272 inventory')
    return instances,template


def source_gate():
    return source.verify(SOURCE_SHA)


def dependencies(s):
    files=[Path(__file__).resolve(),TCL,HERE/'test_mfpu_constants272_native_bind.py',ROOT_LIBRARY,WALK_LIBRARY,
           Path(source.__file__),Path(pack.__file__),Path(pack.native.__file__),Path(pack.native.primitive.__file__)]
    return life.merge_pins(life.merge_pins(s['pins'],{str(p):life.digest(p) for p in files}),
        {str(source.CONFIG):SOURCE_SHA,str(TEMPLATE):TEMPLATE_SHA})


def check(out,seal):
    c=life.read_bound(out/'config.json',seal);life.check(c['pins']);tools.revalidate(c['identity'])
    require(c['schema']==SCHEMA and c['output']==str(out) and c['timeout_seconds']==5400 and
            c['launch_authorized'] is False and c['exclusions_allowed'] is False and
            c['population_application'] is False,'Closed readonly capture contract')
    s=source_gate();instances,template=compiled_instances(s)
    require(c['instances']==instances and all(c[k]==template[k] for k in ('design','vdb','test','identity')),
            'Source/scope/sample binding differs')
    for path,sha in dependencies(s).items():require(c['pins'].get(path)==sha,'Dependency pin differs: '+path)
    return c


def prepare(out):
    require(out.parent==life.OUT and not out.exists(),'Fresh independent prepare only')
    s=source_gate();instances,template=compiled_instances(s)
    tools.revalidate(template['identity'])
    c=dict(schema=SCHEMA,output=str(out),timeout_seconds=5400,launch_authorized=False,exclusions_allowed=False,
        population_application=False,source_review_population=770,local_qualified=False,
        protected_child_scopes=744,instances=instances,source_config_seal=SOURCE_SHA,
        **{k:template[k] for k in ('design','vdb','test','identity')})
    c['pins']=life.merge_pins(template['pins'],dependencies(s))
    selection=''.join('set mfb_'+k+' {'+c[k]+'}\n' for k in ('design','vdb','test'))
    selection+='set mfb_scopes [list '+' '.join('{'+i['scope']+'}' for i in instances)+']\n'
    import check_generated_tcl
    c['pins'][str(Path(check_generated_tcl.__file__).resolve())]=life.digest(check_generated_tcl.__file__)
    life.check(c['pins']);out.mkdir()
    for name,text in [('selection.tcl',selection),('native-bind.tcl',TCL.read_text())]:
        pack.native.primitive.common.common.save(out/name,text)
        check_generated_tcl.check(out/name);c['pins'][str(out/name)]=life.digest(out/name)
    life.save(out/'config.json',c)
    print(json.dumps(dict(output=str(out),seal=life.digest(out/'config.json'),scopes=788,targets=272,
        compiled_objects=sum(len(i['typed_objects']) for i in instances),EDA_launched=False)),flush=True)


def verify(out,seal):
    c=check(out,seal);terminal=json.loads((out/'terminal.json').read_bytes())
    require(terminal['returncode']==0 and not terminal['timeout'] and len(terminal['actual_dve'])==1,'Actual native terminal0 required')
    gui=(out/'DVEfiles/dve_gui.log').read_text();launcher=(out/'launcher.log').read_text()
    require(gui.splitlines().count('MFPU272_READONLY_BIND_DONE')==1 and
            not re.search(r'(?:MFPU272_BIND_FAILED|Error-|Fatal-|Warning-|\bError:)',gui+launcher),'Incomplete/failed readonly capture')
    for name in ('initial-empty.el','final-empty.el'):require((out/name).read_bytes()==b'','Fresh global EL not empty')
    with (out/'scopes.tsv').open() as stream:
        import csv
        reader=csv.DictReader(stream,delimiter='\t');require(reader.fieldnames==['index','scope','token'],'Scope schema')
        tokens=list(reader)
    require(tokens==[dict(index=str(index),scope=i['scope'],token=i['scope']) for index,i in enumerate(c['instances'])],
            'Actual full token selection differs')
    bound=[bind_inventory(i,(out/('native_before_%d.tsv'%index)).read_text()) for index,i in enumerate(c['instances'])]
    require(sum(len(i['signals']) for i in bound)==272,'Binding lost targets')
    target_config=dict(instances=[i for i in bound if i['signals']])
    proposed=pack.native.primitive.candidate(target_config)
    require(len(pack.native.parse_el(proposed,target_config))==34816,'Proposed paired direction set differs')
    if (out/'candidate.el').exists():
        require((out/'candidate.el').read_text()==proposed,'Existing candidate differs; never overwrite')
    else:pack.native.primitive.common.common.save(out/'candidate.el',proposed)
    # Only completed native outputs are authority. Parent lifecycle stdout may
    # receive its final CLI line after this verifier, so it is not self-pinned.
    files=['execution.json','terminal.json','live-identity.json','launcher.log','DVEfiles/dve_gui.log',
           'scopes.tsv','initial-empty.el','final-empty.el','candidate.el',
           *('native_before_%d.tsv'%index for index in range(len(c['instances'])))]
    pins=life.merge_pins(life.merge_pins(c['pins'],{str(out/'config.json'):seal}),
        {str(out/name):life.digest(out/name) for name in files})
    life.check(pins)
    result=dict(status='MFPU272_COMPLETE_FRESH_BEFORE_BINDING_NOT_EXCLUSION_QUALIFICATION',
        config_seal=seal,source_config_seal=SOURCE_SHA,instances=bound,pins=pins,
        targets=272,directions=34816,protected_child_scopes=744,local_qualified=False,
        ready_for_union=False,population_application=False,exclusions_applied=False,
        proposed_EL=str(out/'candidate.el'),EL_origin='GENERATED_FROM_ACTUAL_BEFORE_BINDING_NOT_NATIVE_SAVED',
        required_next='Explicitly reviewed five-stage exact global EL/save-reload-reset/full complement; no initial-X waiver')
    if (out/'native-binding.json').exists():
        require(json.loads((out/'native-binding.json').read_bytes())==result,'Sealed binding replay differs')
    else:life.save(out/'native-binding.json',result)
    return result


def run(out,seal,reviewed):
    require(seal and reviewed==seal,'Exact explicit parent reviewed seal required')
    c=check(out,seal);require(not (out/'execution.json').exists(),'No repeat/retry')
    env=tools.controlled_environment(c['identity'],os.environ)
    env.pop('DVE',None);env['DVE_COVERAGE_OUTPUT']=str(out)
    command=[shutil.which('xvfb-run'),'-a','-e',str(out/'xvfb.log'),'-s','-screen 0 1280x1024x24',
        c['identity']['roles']['launcher'],'-full64','-cov','-script',str(out/'native-bind.tcl')]
    with (out/'execution.json').open('x') as f:json.dump(dict(command=command,cwd=str(out),config_seal=seal,timeout_seconds=5400),f)
    with (out/'launcher.log').open('x') as log:
        process=subprocess.Popen(command,cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        time.sleep(10);actual=[]
        for p in Path('/proc').iterdir():
            if not p.name.isdigit():continue
            try:
                if (p/'exe').resolve()==Path(c['identity']['executable']) and (p/'cwd').resolve()==out:
                    actual.append(dict(pid=int(p.name),exe=str((p/'exe').resolve()),cwd=str(out)))
            except OSError:continue
        life.save(out/'live-identity.json',actual);print(json.dumps(dict(actual_dve=actual,output=str(out))),flush=True)
        timeout=False
        try:process.wait(timeout=5390)
        except subprocess.TimeoutExpired:
            timeout=True;os.killpg(process.pid,signal.SIGTERM)
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
    life.save(out/'terminal.json',dict(returncode=process.returncode,timeout=timeout,actual_dve=actual))
    verify(out,seal)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','check','verify','run'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal');p.add_argument('--parent-reviewed-seal')
    a=p.parse_args();out=a.output.resolve()
    if a.mode=='prepare':prepare(out)
    else:
        require(a.seal,'Exact sealed config required')
        if a.mode=='run':run(out,a.seal,a.parent_reviewed_seal)
        else:
            result=check(out,a.seal) if a.mode=='check' else verify(out,a.seal)
            print(json.dumps(dict(status=a.mode+'_PASS',schema=result.get('schema'),
                native_qualification=False,population_application=False)))
