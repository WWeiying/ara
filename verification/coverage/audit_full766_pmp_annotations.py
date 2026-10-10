"""Read-only strict PMP supplement; never modifies the running full766 consumer."""
import argparse
import csv
import json
from pathlib import Path
import report_native_batch766 as report

life,require=report.life,report.require
ANNOTATION='ANNOTATION: "PMP0 internal q/next constant after valid reset and settled evaluation; no initial-X waiver"'
CONFIG_SHA='ce709dbf1da6a16f16c8c10e7c2006c59429a3ff08c09237a3355a7267f53650'
OUTPUT=life.OUT/'native-batch-full766-agent-20261007-01'


def strict_records(text,c):
    blocks=[block for scope,block in report.old.blocks(text) if scope==c['instances'][0]['scope']]
    require(len(blocks)==1,'Exactly one PMP scope block required')
    annotation=None
    for line in blocks[0].splitlines():
        if line.startswith('ANNOTATION:'):
            require(line==ANNOTATION,'PMP annotation differs');annotation=line
        elif line.startswith('Toggle '):
            require(annotation==ANNOTATION,'Missing intended PMP annotation')
    return report.pmp.parse_el(blocks[0],c)


def audit(terminal=False):
    c=life.read_bound(OUTPUT/'config.json',CONFIG_SHA)
    q=life.read_bound(report.PMP/'capture-result.json',report.PMP_SHA)
    p=life.read_bound(report.PMP/'config.json',q['config_seal']);report.pmp.contract(p)
    pins={str(OUTPUT/'config.json'):CONFIG_SHA,str(report.PMP/'capture-result.json'):report.PMP_SHA,
          str(report.PMP/'config.json'):q['config_seal'],str(Path(__file__).resolve()):life.digest(Path(__file__))}
    expected=None
    for name in ('first.el','second.el'):
        path=report.PMP/name
        require(str(path) in q['pins'],'Native EL not sealed')
        require(life.digest(path)==q['pins'][str(path)],'Native EL bytes drift')
        text=path.read_text()
        value=strict_records(text,p)
        if expected is None:expected=value
        require(value==expected and len(value)==770,'Native exact770 parity differs')
        pins[str(path)]=q['pins'][str(path)]
    for stage in report.STAGES:
        path=report.PMP/('native_%s_0.tsv'%stage)
        require(str(path) in q['pins'] and life.digest(path)==q['pins'][str(path)],'Native inventory bytes drift')
        with path.open() as f:rows=list(csv.DictReader(f,delimiter='\t'))
        require(len(rows)==2077 and all(len({r[k] for r in rows})==2077 for k in ('handle','path','meta','name')),
                'Exact2077 unique metadata differs')
        report.pmp.inventory(report.PMP,p,stage,0)
        pins[str(path)]=q['pins'][str(path)]
    names=['combined.el']+(['applied.el','reloaded.el'] if terminal else [])
    for name in names:
        path=OUTPUT/name
        if name=='combined.el':
            require(life.digest(path)==c['pins'][str(path)],'Sealed combined bytes drift')
        require(strict_records(path.read_text(),p)==expected,'Full766 exact annotated PMP union differs')
        pins[str(path)]=life.digest(path)
    return dict(status='STRICT_PMP770_ANNOTATION_AND2077_NATIVE_METADATA_PASS',
        full766_config_seal=CONFIG_SHA,pmp_capture_seal=report.PMP_SHA,
        annotation=ANNOTATION,objects=770,complete_native_objects=2077,protected_objects=1307,
        terminal_full766_checked=terminal,initial_X_excluded=False,EDA_launched=False,pins=pins)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--terminal',action='store_true');args=parser.parse_args()
    require(args.output.resolve().parent==life.OUT and not args.output.exists(),'Fresh independent audit only')
    result=audit(args.terminal);life.save(args.output.resolve(),result)
    print(json.dumps(dict(status=result['status'],seal=life.digest(args.output.resolve()))))
