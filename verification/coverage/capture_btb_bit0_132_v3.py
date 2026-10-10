"""BTB132 exact compiled btb_gen.i_btb display alias; no EL or scope changes."""
import argparse
import csv
import json
from pathlib import Path
from types import FunctionType, SimpleNamespace

import capture_btb_bit0_132_v2 as prior

original,plan,require,digest=prior.original,prior.plan,prior.require,prior.digest
HERE=Path(__file__).resolve().parent
HOOK=HERE/'capture_btb_bit0_132_v3.tcl'
V2=plan.OUT/'btb-bit0-132-native-v2-prepared779-agent-20261008-01'
V2_SHA='6fe2ed0cd06c933a08ac3cb2286087fcb44603fa98ab6df312b84d93af7e1243'
ALIASES=['i_btb','btb','btb_gen.i_btb']


def compiled_binding(c):
    matches=[Path(p) for p in c['pins'] if p.endswith('/design/verilog.design.xml')]
    require(len(matches)==1,'One bound compiled design')
    path=matches[0];data=path.read_bytes()
    require(plan.hashlib.sha256(data).hexdigest()==c['pins'][str(path)],'Compiled design drift')
    design=plan.native.base.ET.fromstring(plan.gzip.decompress(data) if data[:2]==b'\x1f\x8b' else data)
    nodes={}
    for module in design.findall('srcdef'):
        for node in module.findall('srcinst'):
            require(node.get('id') not in nodes,'Duplicate compiled instance')
            nodes[node.get('id')]=(node,module)
    def full(key,seen=()):
        require(key not in seen,'Compiled cycle')
        node,_=nodes[key];parent=node.get('pid')
        return (full(parent,seen+(key,))+'.' if parent in nodes else '')+node.get('name')
    selected=[(node,module) for key,(node,module) in nodes.items() if full(key)==plan.SCOPE]
    require(len(selected)==1,'Exact unique compiled BTB scope')
    node,module=selected[0];parent,parent_module=nodes[node.get('pid')]
    require(dict(module.attrib)==c['inventory']['module'] and dict(node.attrib)==
        dict(id='-1968',name='btb_gen.i_btb',pid='-466') and
        dict(parent.attrib)==dict(id='-466',name='i_frontend',pid='-1712') and
        parent_module.get('name')=='frontend','Exact compiled generated instance/parent')
    src=plan.ROOT/'hardware/deps/cva6/core/frontend/frontend.sv'
    text=src.read_bytes()
    require(str(src) in c['pins'] and plan.hashlib.sha256(text).hexdigest()==c['pins'][str(src)],
            'Frozen frontend source binding')
    compact=plan.compact(text.decode())
    require("if(CVA6Cfg.BTBEntries==0)beginassignbtb_prediction='0;endelsebegin:btb_genbtb#(" in compact and
        '.NR_ENTRIES(CVA6Cfg.BTBEntries))i_btb(' in compact,'Source generate/instance contract')
    return dict(scope=plan.SCOPE,instance=dict(node.attrib),parent=dict(parent.attrib),
                module=dict(module.attrib),frontend_source=str(src),source_sha=c['pins'][str(src)])


def contract(c):
    original.contract(c)
    require(c['protocol']==prior.PROTOCOL and c['origin_config_seal']==prior.ORIGIN_SHA and
        c['previous_config_seal']==V2_SHA and c['root_display_aliases']==ALIASES,
        'Exact compiled display-only successor contract')


def read_config(out,seal):
    c=original.bound(out/'config.json',seal);contract(c);original.check(c['pins'])
    require(c['output']==str(out) and c['display_binding']==compiled_binding(c) and
        original.bound(original.STATIC/'inventory.json',c['pins'][str(original.STATIC/'inventory.json')])==c['inventory'],
        'Bound compiled display/typed inventory/output')
    return c


def root_observations(out):
    with (out/'root-contract.tsv').open(newline='') as f:rows=list(csv.reader(f,delimiter='\t'))
    require(len(rows)==5 and all(len(r)==7 for r in rows),'Five exact actual root observations')
    for row,stage in zip(rows,original.STAGES):
        s,scope,token,handle,path,name,next_item=row
        require(s==stage and scope==token==plan.SCOPE and handle not in ('','0') and
            path==name and name in ALIASES and next_item in ('','0'),
            'Exact fullscope token/unique compiled display root')
    require(len({tuple(r[4:6]) for r in rows})==1,'Root display identity drift')
    return {r[0]:r for r in rows}


def metrics(out,stage):
    return FunctionType(prior.metrics.__code__,dict(vars(prior),root_observations=root_observations))(out,stage)


def verify(out,seal):
    return FunctionType(original.verify.__code__,dict(vars(original),read_config=read_config,metrics=metrics))(out,seal)


def prepare(out):
    previous=original.bound(V2/'config.json',V2_SHA)
    prior.contract(previous);original.check(previous['pins'])
    binding=compiled_binding(previous)
    with (V2/'root-contract.tsv').open(newline='') as f:rows=list(csv.reader(f,delimiter='\t'))
    require(len(rows)==1 and len(rows[0])==7 and rows[0][0]=='before' and
        rows[0][1]==rows[0][2]==plan.SCOPE and rows[0][4]==rows[0][5]=='btb_gen.i_btb' and
        rows[0][6]=='0','Measured exact generated display alias')
    terminal=json.loads((V2/'terminal.json').read_bytes())
    require(type(terminal['returncode']) is int and terminal['returncode']==0 and
        terminal['timeout'] is False and (V2/'cleanup-empty.el').read_bytes()==b'' and
        not (V2/'first.el').exists() and 'Nonunique/foreign BTB root' in (V2/'error.txt').read_text(),
        'Preserved pre-candidate v2 display failure/normal exit/empty cleanup')
    extras=[Path(__file__).resolve(),HERE/'test_capture_btb_bit0_132_v3.py',
        Path(prior.__file__).resolve(),prior.HOOK,V2/'config.json',V2/'root-contract.tsv',
        V2/'terminal.json',V2/'error.txt',V2/'cleanup-empty.el',V2/'DVEfiles/dve_gui.log']
    extra_pins={str(p):digest(p) for p in extras}
    def save(path,value):
        if Path(path)==out/'config.json':
            value=dict(value,previous_config_seal=V2_SHA,root_display_aliases=ALIASES,display_binding=binding)
            value['pins']=dict(value['pins'])
            for name,sha in extra_pins.items():
                require(name not in value['pins'] or value['pins'][name]==sha,'Dependency conflict')
                value['pins'][name]=sha
            contract(value);original.check(value['pins'])
        original.save(path,value)
    # Existing prepare/write contract unchanged; only the fresh config and helper route differ.
    proxy=SimpleNamespace(**dict(vars(original),save=save))
    return FunctionType(prior.prepare.__code__,dict(vars(prior),original=proxy,
        __file__=str(Path(__file__).resolve()),HOOK=HOOK))(out)


def run(out,seal):
    return FunctionType(original.run.__code__,dict(vars(original),read_config=read_config,HOOK=HOOK,verify=verify))(out,seal)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','check','stage','run','verify'))
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--seal')
    parser.add_argument('--stage',choices=original.STAGES)
    args=parser.parse_args();out=args.output.absolute()
    if args.mode=='prepare':print(prepare(out))
    else:
        require(args.seal,'Exact successor config seal')
        if args.mode=='stage':print(len(original.check_stage(out,read_config(out,args.seal),args.stage)))
        elif args.mode=='check':read_config(out,args.seal);print('BTB132_GENERATE_ALIAS_PREPARED_NO_EDA')
        else:print((run if args.mode=='run' else verify)(out,args.seal))
