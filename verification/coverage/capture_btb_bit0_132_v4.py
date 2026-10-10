"""Measured native annotation placement only; reuse frozen v3 Tcl and exact BTB bits."""
import argparse
import json
from pathlib import Path
import re
from types import FunctionType, SimpleNamespace

import capture_btb_bit0_132_v3 as prior

original,plan,require,digest=prior.original,prior.plan,prior.require,prior.digest
HERE=Path(__file__).resolve().parent
ORIGIN=plan.OUT/'btb-bit0-132-native-v3-prepared779-agent-20261008-01'
ORIGIN_SHA='bb6edb16befafd68567280865181e28ff09f094bfe3c5506539e3092cd836718'
FIRST_SHA='17508ab793c294b81981a6f9fe957bda1b9864fd036efeea45164e0241792691'
SEMANTICS='One exact provenance ANNOTATION may occur between native Toggle directives; no physical identity or declaration changes.'


def native_records(text):
    headers={};body=[];annotation=None;in_body=False
    for raw in text.splitlines():
        line=raw.strip()
        if not line:continue
        if line.startswith('ANNOTATION:'):
            require(annotation is None and line=='ANNOTATION: "'+plan.NOTE+'"',
                    'Duplicate/foreign native annotation')
            annotation=line
            continue
        match=re.fullmatch(r'(CHECKSUM|INSTANCE):\s*(.*)',line)
        if match:
            require(not in_body and match[1] not in headers,'Mixed/duplicate scope/checksum header')
            headers[match[1]]=match[2]
        else:
            require(set(headers)=={'CHECKSUM','INSTANCE'},'Native directive before complete scope/checksum')
            in_body=True;body.append(line)
    require(annotation is not None and headers==dict(CHECKSUM='"'+plan.CHECKSUM+'"',INSTANCE=plan.SCOPE),
            'Exact native scope/checksum/provenance required')
    # Physical membership is independent of provenance placement. The raw stream
    # stays pinned; only this semantic comparator uses a fixed header order.
    canonical='\n'.join(['CHECKSUM: '+headers['CHECKSUM'],'INSTANCE: '+headers['INSTANCE'],annotation]+body)
    return original.native_records(canonical)


def contract(c):
    prior.contract(c)
    require(c['native_parser_semantics']==SEMANTICS and c['native_export_origin_seal']==ORIGIN_SHA and
            c['native_export_first_sha']==FIRST_SHA,'Exact measured native export grammar')


def read_config(out,seal):
    c=prior.read_config(out,seal);contract(c)
    return c


def check_stage(out,c,stage):
    return FunctionType(original.check_stage.__code__,dict(vars(original),native_records=native_records))(out,c,stage)


def verify(out,seal):
    return FunctionType(original.verify.__code__,dict(vars(original),
        read_config=read_config,metrics=prior.metrics,check_stage=check_stage))(out,seal)


def mapping():
    c=prior.read_config(ORIGIN,ORIGIN_SHA)
    path=ORIGIN/'first.el';data=path.read_bytes()
    require(plan.hashlib.sha256(data).hexdigest()==FIRST_SHA,'Measured export drift')
    actual=native_records(data.decode());expected=plan.records(plan.el_text())
    require(actual==expected and len(actual)==132 and not actual & original.complement(c['inventory']),
            'Exact132 identities and complete8860 complement')
    terminal=json.loads((ORIGIN/'terminal.json').read_bytes())
    require(type(terminal['returncode']) is int and terminal['returncode']==0 and
        terminal['timeout'] is False and (ORIGIN/'cleanup-empty.el').read_bytes()==b'' and
        not (ORIGIN/'second.el').exists() and 'Mixed/duplicate native header' in (ORIGIN/'error.txt').read_text(),
        'Preserved applied-parser failure; no completed reload claim')
    lines=data.decode().splitlines()
    return dict(status='BTB132_FIRST_NATIVE_GRAMMAR_MAPPED_NOT_ROUNDTRIP_QUALIFIED',
        native_first=str(path),native_first_sha=FIRST_SHA,origin_config_seal=ORIGIN_SHA,
        directives=sum(line.startswith('Toggle ') for line in lines),direction_identities=len(actual),
        exact_approved_set=True,protected_direction_intersection=0,protected_directions=8860,
        annotation_text=plan.NOTE,annotation_line=next(i+1 for i,s in enumerate(lines) if s.startswith('ANNOTATION:')),
        semantic_authority='Explicit partial-bit physical identity, checksum, declaration and complete direction membership; no per-point annotation equivalence claim.',
        second_export_exists=False,population_application=False,
        canonical_direction_identities=[list(item) for item in sorted(actual)])


def prepare(out):
    evidence=mapping()
    extras=[Path(__file__).resolve(),HERE/'test_capture_btb_bit0_132_v4.py',
        Path(prior.__file__).resolve(),prior.HOOK,ORIGIN/'config.json',ORIGIN/'first.el',
        ORIGIN/'error.txt',ORIGIN/'terminal.json',ORIGIN/'cleanup-empty.el',
        ORIGIN/'root-contract.tsv',ORIGIN/'DVEfiles/dve_gui.log']
    extra_pins={str(p):digest(p) for p in extras}
    def save(path,value):
        if Path(path)==out/'config.json':
            value=dict(value,native_parser_semantics=SEMANTICS,native_export_origin_seal=ORIGIN_SHA,
                       native_export_first_sha=FIRST_SHA,pins=dict(value['pins']))
            for name,sha in extra_pins.items():
                require(name not in value['pins'] or value['pins'][name]==sha,'Dependency conflict')
                value['pins'][name]=sha
            original.save(out/'native-grammar-mapping.json',evidence)
            value['pins'][str(out/'native-grammar-mapping.json')]=digest(out/'native-grammar-mapping.json')
            contract(value);original.check(value['pins'])
        original.save(path,value)
    proxy=SimpleNamespace(**dict(vars(original),save=save))
    return FunctionType(prior.prepare.__code__,dict(vars(prior),original=proxy,
        __file__=str(Path(__file__).resolve())))(out)


def run(out,seal):
    return FunctionType(original.run.__code__,dict(vars(original),
        read_config=read_config,HOOK=prior.HOOK,verify=verify))(out,seal)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','check','stage','run','verify'))
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--seal')
    parser.add_argument('--stage',choices=original.STAGES)
    args=parser.parse_args();out=args.output.absolute()
    if args.mode=='prepare':print(prepare(out))
    else:
        require(args.seal,'Exact measured-grammar successor config seal')
        if args.mode=='stage':print(len(check_stage(out,read_config(out,args.seal),args.stage)))
        elif args.mode=='check':read_config(out,args.seal);print('BTB132_NATIVE_GRAMMAR_PREPARED_NO_EDA')
        else:print((run if args.mode=='run' else verify)(out,args.seal))
