"""Measured singleton-view compatibility; exact cast168 scope remains unchanged."""
import argparse
import csv
import importlib.util
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('cast168_private_original', HERE/'capture_cast168_native.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
life, require = base.life, base.require
ORIGIN = life.OUT/'fpnew-cast-fp-shared168-native745-agent-20261007-01'
ORIGIN_SHA = 'e76cb738bb5ec015e607842f5c52bf0ad03f9733159d36ef6bdd81ee247a6196'
DIAG = life.OUT/'fpnew-cast168-native745-schema-hold-review-agent-20261007-01.json'
DIAG_SHA = '3f45932e2bc10a2f863b537c19d64847921d24fb0b9b3f5921d557f856e59eec'
ALIASES = {
    'out_pipe_result_q[0:0][63:0]': 'out_pipe_result_q[0][63:0]',
    'out_pipe_aux_q[0:0][7:0]': 'out_pipe_aux_q[0][7:0]',
    'out_pipe_ext_bit_q[0:0]': 'out_pipe_ext_bit_q',
    'out_pipe_mask_q[0:0]': 'out_pipe_mask_q',
    'out_pipe_valid_q[0:0]': 'out_pipe_valid_q',
    'out_pipe_ready[0:0]': 'out_pipe_ready',
}
origin = life.read_bound(ORIGIN/'config.json', ORIGIN_SHA)
review = life.read_bound(base.REVIEW, base.REVIEW_SHA)
source = life.read_bound(Path(review['inventory400']), review['pins'][review['inventory400']])
original_contract, original_parse, original_inspect = base.contract, base.parse_el, base.inspect


def contract(c):
    for i in c['instances']:
        src = next(x for x in source['instances'] if x['scope']==i['scope'])
        require(i['toggle_checksum']==src['toggle_checksum']=='400336858' and
                re.search(r'(?:,| )NUM_OUT_REGS=0(?:,|\s)', src['compiled_definition']),
                'Exact zero-output-stage specialization required')
        objects={x['native_name']:x for x in src['protected']}
        for old,new in ALIASES.items():
            node=objects.get(old)
            expected=[[0,0],[63,0]] if old.startswith('out_pipe_result_q') else \
                     [[0,0],[7,0]] if old.startswith('out_pipe_aux_q') else [[0,0]]
            require(node is not None and node['dimensions']==expected and node['portnode']=='0',
                    'Singleton compiled declaration/bounds differs')
            require(old not in [t['native_name'] for t in i['targets']], 'Alias may not target output/control')
        compiled=i.get('protected_compiled',i['protected'])
        wanted=([x['native_name']for x in src['protected']]+
                [x['native_name']for x in src['targets']if x['name'] not in {t['name']for t in i['targets']}])
        require(sorted(compiled)==sorted(wanted) and all(compiled.count(k)==1 for k in ALIASES),
                'Protected compiled complement differs')
        native=[ALIASES.get(n,n)for n in compiled]
        if 'protected_compiled'in i:require(i['protected']==native,'Unauthorized alias/protection drift')
        i['protected_compiled']=list(compiled);i['protected']=native
    original_contract(c)


def inventory(out,c,stage,index):
    contract(c);require(stage in base.STAGES and 0<=index<8,'Inventory stage/index')
    with (out/('native_%s_%d.tsv'%(stage,index))).open(newline='') as stream:
        table=list(csv.reader(stream,delimiter='\t'))
    require(table and table[0]==['handle','path','meta','name'] and len(table)==280 and
            all(len(r)==4 and all(r) and r[1]==r[2]==r[3]for r in table[1:]),
            'Exact279 unique native name/path/meta identities required')
    require(len({r[0]for r in table[1:]})==279,'Duplicate native handles')
    rows=[tuple(r[1:])for r in table[1:]];names=[r[2]for r in rows];i=c['instances'][index]
    expected=[t['native_name']for t in i['targets']]+i['protected']
    require(len(set(names))==279 and sorted(names)==sorted(expected),
            'Target/protection missing/extra/duplicate or unauthorized alias')
    return sorted(rows)


def parse_el(text,c,native_meta=None):
    contract(c)
    if native_meta is not None:
        expected={(i['scope'],t['name']):t['native_name']for i in c['instances']for t in i['targets']}
        require(native_meta==expected,'Bare native identity unbound; not an EL type signature')
    # The original parser independently validates legal typed Toggle declarations,
    # exact full vector/array bounds, checksum, scope, duplicates and all168 objects.
    return original_parse(text,c,None)


def inspect(out,seal):
    original_inspect(out,seal)


class Route:
    def __truediv__(self,name):
        return HERE/({'capture_cast168_native.tcl':'capture_cast168_native_v2.tcl',
                      'test_capture_cast168_native.py':'test_capture_cast168_native_v2.py'}.get(name,name))


def prepare(out):
    life.check(origin['pins'])
    diag=life.read_bound(DIAG,DIAG_SHA);life.check(diag['pins'])
    require(diag['five_stages_complete'] is False and diag['no_target_exclusions_executed'] is True,
            'Original failure must remain HOLD, never a qualified predecessor')
    recorded={x['compiled_name']:x['actual_native']['name']for x in diag['singleton_output_dimension_aliases']}
    require(recorded==ALIASES,'Aliases not exactly observed six')
    inventory(ORIGIN,origin,'before',0)
    dependencies={str(ORIGIN/'config.json'):ORIGIN_SHA,str(DIAG):DIAG_SHA,
                  str(ORIGIN/'native_before_0.tsv'):diag['pins'][str(ORIGIN/'native_before_0.tsv')]}
    for p in (HERE/'capture_cast168_native.py',HERE/'capture_cast168_native.tcl',
              HERE/'test_capture_cast168_native.py'):
        dependencies[str(p)]=origin['pins'][str(p)]
    save=life.save
    def bound_save(path,data):
        if path==out/'config.json':
            data=dict(data);data['pins']=life.merge_pins(data['pins'],dependencies)
            data['compatibility_profile']='EXACT_SIX_NUM_OUT_REGS0_ALIASES_WITH_BARE_NATIVE_IDENTITY'
            data['aliases']=ALIASES;data['original_HOLD']=str(ORIGIN)
            life.check(data['pins'])
        save(path,data)
    life.save=bound_save
    try:base.prepare(out)
    finally:life.save=save


base.contract=contract;base.inventory=inventory;base.parse_el=parse_el;base.inspect=inspect
base.__file__=str(Path(__file__).resolve());base.HERE=Route()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','run','inspect','el','inventory'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal');p.add_argument('--file')
    p.add_argument('--stage');p.add_argument('--index',type=int);a=p.parse_args();out=a.output.resolve()
    if a.mode=='prepare':prepare(out)
    elif a.mode in ('el','inventory'):
        c=json.loads((out/'config.json').read_bytes())
        if a.mode=='el':
            require(a.file in ('first.el','second.el'),'EL filename');print(len(parse_el((out/a.file).read_text(),c)))
        else:print(len(inventory(out,c,a.stage,a.index)))
    else:
        require(a.seal,'Exact seal');(base.run if a.mode=='run'else inspect)(out,a.seal)
