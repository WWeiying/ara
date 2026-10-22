"""Shape-bound net/logic saved-EL normalization; no implicit native qualification."""
import argparse
import inspect
import json
import re
from pathlib import Path

import soc_constants61_native_v2 as previous

old=previous.old
RUN=old.life.OUT/'soc-constants61-native-parent-20261008-02'
SEAL='b5629d8a96e850e86f6dcab9f3f21fab9155d41746424ce6975362ee0be637f1'
V2_SHA='7976d17670b4ac3caa8bed4c025476bed86a1fe3c019fe9bda935d1e1eec6b6f'


def normalize(text,c):
    instances={i['scope']:i for i in c['instances']}
    proof=old.life.read_bound(old.SOURCE,old.SOURCE_SHA)
    authority={(r['scope'],r['name']):r['compiled_attributes'] for r in proof['candidates']}
    scope=None;lines=[]
    for line in text.splitlines():
        stripped=line.strip()
        if stripped.startswith('CHECKSUM:'):scope=None
        if stripped.startswith('INSTANCE:'):
            scope=stripped.split(':',1)[1].strip()
        if stripped.startswith('Toggle '):
            match=re.fullmatch(r'Toggle (?:(0to1|1to0) )?(\S+) "(logic|net) (\S+)\[(\d+):(\d+)\]"',stripped)
            old.need(match is not None and scope in instances,'Exact saved Toggle declaration')
            direction,name,kind,signature,left,right=match.groups()
            i=instances[scope]
            targets={s['name']:s for s in i['signals']}
            nodes=[n for n in i['typed_objects'] if n['name']==name]
            old.need(name in targets and len(nodes)==1 and nodes[0]['kind']=='vectornode'
                     and name==signature and (int(left),int(right))==
                     (targets[name]['left'],targets[name]['right']), 'Exact whole typed target')
            expected=authority.get((scope,name))
            old.need(expected is not None and all(expected.get(k)==value for k,value in nodes[0].items() if k!='kind'),
                     'Pinned compiled type/portnode/range/source attributes')
            old.need(nodes[0]['type'] in ('1','3') and
                     (kind!='net' or (nodes[0]['type']=='3' and nodes[0]['portnode']=='2')),
                     'Observed net declaration requires compiled type3 input port')
            line='Toggle '+((direction+' ') if direction else '')+name+' "logic '+signature+'['+left+':'+right+']"'
        lines.append(line)
    return '\n'.join(lines)+'\n'


def el_gate(text,c):return old.el_gate(normalize(text,c),c)


def context():
    old.need(old.life.digest(previous.__file__)==V2_SHA,'Frozen v2 source drift')
    env=previous.context()
    env.update(__file__=__file__,el_gate=el_gate,SCHEMA='SOC_CONSTANTS61_LOCAL_NATIVE_PREPARED_V3')
    body=inspect.getsource(old.prepare)
    anchor="test=HERE/'test_soc_constants61_native.py'"
    old.need(body.count(anchor)==1,'Exact predecessor test-pin anchor')
    exec(compile(body.replace(anchor,"test=HERE/'test_soc_constants61_native_v3.py'"),__file__,'exec'),env)
    return env


def replay():
    c=old.life.read_bound(RUN/'config.json',SEAL)
    old.need(c['instances']==old.instances(old.life.read_bound(old.SOURCE,old.SOURCE_SHA)),
             'Actual source/compiled registry')
    el=(RUN/'first.el').read_text();members=el_gate(el,c)
    rows=0;pins={str(RUN/'config.json'):SEAL,str(RUN/'first.el'):old.life.digest(RUN/'first.el')}
    for index,i in enumerate(c['instances']):
        paths=[RUN/('native_%s_%d.tsv'%(stage,index)) for stage in ('before','applied')]
        before,applied=[previous.bind(i,p.read_text()) for p in paths]
        old.stage_gate(i,before,applied,'applied');rows+=len(applied)
        pins.update({str(p):old.life.digest(p) for p in paths})
    return dict(status='EXACT_SAVED_EL_AND_ALL18_APPLIED_PROTECTION_PASS_NOT_FIVE_STAGE_QUALIFICATION',
                fields=len(members),rows_per_stage=rows,scopes=len(c['instances']),
                normalization='Only whole compiled type3 target net declarations to canonical logic',
                pins=pins,EDA_started=False,prepared=False,native_qualified=False)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',nargs='?',default='replay',choices=('replay','prepare','check','before','first','second','verify','run'))
    p.add_argument('--output',type=Path);p.add_argument('--seal');p.add_argument('--parent-reviewed-seal')
    a=p.parse_args()
    if a.mode=='replay':print(json.dumps(replay(),indent=2))
    else:
        old.need(a.output is not None,'Explicit output required');out=a.output.resolve();env=context()
        if a.mode=='prepare':env['prepare'](out)
        elif a.mode=='run':env['run'](out,a.seal,a.parent_reviewed_seal)
        else:
            c=env['check'](out,a.seal)
            if a.mode=='before':env['before_gate'](out,c)
            elif a.mode in ('first','second'):el_gate((out/(a.mode+'.el')).read_text(),c)
            elif a.mode=='verify':env['verify'](out,a.seal)
            print(a.mode+'_PASS')
