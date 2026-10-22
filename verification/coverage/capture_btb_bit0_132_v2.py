"""Protocol-only BTB132 successor; preserve original failed capture and exact targets."""
import argparse
import csv
import json
from pathlib import Path
from types import FunctionType

import capture_btb_bit0_132 as original

plan,require,digest=original.plan,original.require,original.digest
HERE=Path(__file__).resolve().parent
HOOK=HERE/'capture_btb_bit0_132_v2.tcl'
ROOT_HELPER=HERE/'apply_points740_v4.tcl'
ORIGIN=plan.OUT/'btb-bit0-132-native-prepared779-agent-20261008-01'
ORIGIN_SHA='1746a93256d81fd91ef49c5ace2e6a3bd1dfae42a71a7a4f841328dbd16a1ca5'
INSTALL=Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/gui/dve/auxx/gui/dve')
PROTOCOL='Qualified full-root restore -> exact selected fullscope readback -> setroot token; sole root display must be compiled i_btb/btb.'


def contract(c):
    original.contract(c)
    require(c['protocol']==PROTOCOL and c['origin_config_seal']==ORIGIN_SHA and
            c['root_display_aliases']==['i_btb','btb'] and c['inventory']['module']['name']=='btb',
            'Exact selected token/compiled display alias contract')


def read_config(out,seal):
    c=original.bound(out/'config.json',seal);contract(c)
    original.check(c['pins'])
    require(c['output']==str(out) and
        original.bound(original.STATIC/'inventory.json',c['pins'][str(original.STATIC/'inventory.json')])==c['inventory'],
        'Exact source inventory/output')
    return c


def root_observations(out):
    with (out/'root-contract.tsv').open(newline='') as f:
        rows=list(csv.reader(f,delimiter='\t'))
    require(len(rows)==5 and all(len(r)==7 for r in rows), 'Five complete actual root observations')
    for row,stage in zip(rows,original.STAGES):
        s,scope,token,handle,path,name,next_item=row
        require(s==stage and scope==token==plan.SCOPE and handle not in ('','0') and
                path==name and name in ('i_btb','btb') and next_item in ('','0'),
                'Exact fullscope token/unique compiled display root')
    require(len({tuple(r[4:6]) for r in rows})==1, 'Root display identity drift')
    return {r[0]:r for r in rows}


def metrics(out,stage):
    observations=root_observations(out)
    with (out/('rooted_'+stage+'.csv')).open(newline='') as f:
        reader=csv.DictReader(f);require(reader.fieldnames==original.HEADER,'Exact root schema')
        rows=list(reader)
    require(len(rows)==1,'One actual BTB root row')
    row=rows[0];observed=observations[stage]
    require(row['Stage']==stage and row['Scope']==plan.SCOPE and
            row['Path']==observed[4] and row['Name']==observed[5], 'Actual root observation/metrics mismatch')
    return {m:None if row[m]=='NA' and m not in ('Score','Toggle') else original.percent(row[m])
            for m in original.METRICS}


def verify(out,seal):
    return FunctionType(original.verify.__code__,dict(vars(original),read_config=read_config,metrics=metrics))(out,seal)


def prepare(out):
    c=original.bound(ORIGIN/'config.json',ORIGIN_SHA)
    original.contract(c);original.check(c['pins'])
    require((ORIGIN/'error.txt').is_file() and (ORIGIN/'cleanup-empty.el').read_bytes()==b'' and
        not (ORIGIN/'first.el').exists(), 'Preserved original pre-candidate failure and empty cleanup')
    error=(ORIGIN/'error.txt').read_text()
    require('Nonunique/foreign BTB root' in error and 'btb_stage before initial-empty.el' in error,
            'Exact measured original protocol failure')
    terminal=json.loads((ORIGIN/'terminal.json').read_bytes())
    require(type(terminal['returncode']) is int and terminal['returncode']!=0 and
            terminal['timeout'] is False, 'Original terminated failure preserved')
    extras=[Path(__file__).resolve(),HERE/'test_capture_btb_bit0_132_v2.py',
        Path(original.__file__).resolve(),original.HOOK,ROOT_HELPER,
        INSTALL/'ucliLoadCci.tcl',INSTALL/'cmenuprocs.tcl',
        ORIGIN/'config.json',ORIGIN/'error.txt',ORIGIN/'terminal.json',
        ORIGIN/'initial-empty.el',ORIGIN/'cleanup-empty.el',
        ORIGIN/'DVEfiles/dve_gui.log',ORIGIN/'DVEfiles/dve_history.log']
    extra_pins={str(p):digest(p) for p in extras}
    def save(path,value):
        if Path(path)==out/'config.json':
            value=dict(value,protocol=PROTOCOL,origin_config_seal=ORIGIN_SHA,
                       root_display_aliases=['i_btb','btb'])
            pins=dict(value['pins'])
            for name,sha in extra_pins.items():
                require(name not in pins or pins[name]==sha,'Successor dependency conflict')
                pins[name]=sha
            value['pins']=pins
            contract(value);original.check(pins)
        original.save(path,value)
    return FunctionType(original.prepare.__code__,dict(vars(original),
        __file__=str(Path(__file__).resolve()),HOOK=HOOK,save=save))(out)


def run(out,seal):
    return FunctionType(original.run.__code__,dict(vars(original),
        read_config=read_config,HOOK=HOOK,verify=verify))(out,seal)


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
        elif args.mode=='check':read_config(out,args.seal);print('BTB132_SUCCESSOR_PREPARED_NO_EDA')
        else:print((run if args.mode=='run' else verify)(out,args.seal))
