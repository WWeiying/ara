"""Replay failed-import capture's real before inventory; never exclusion qualification."""
import argparse
import json
from pathlib import Path
import fpnew_tied90_local as frozen

RUN = frozen.life.OUT/'fpnew-tied90-local-prepared781-agent-20261008-01'
SEAL = '60aa913eeb09637030ed08204c57b133a324c7cd4ffc5d3433d2afe839331f57'


def evaluate():
    c=frozen.check(RUN,SEAL)
    files=[RUN/('native_before_%d.tsv'%i) for i in range(70)]
    files += [RUN/n for n in ('error.txt','terminal.json','cleanup-empty.el','initial-empty.el',
                              'flags.tsv','execution.json','live-identity.json')]
    pins=frozen.life.merge_pins(c['pins'],{str(p):frozen.life.digest(p) for p in files})
    terminal=json.loads((RUN/'terminal.json').read_bytes())
    live=json.loads((RUN/'live-identity.json').read_bytes())
    frozen.primitive.terminal_gate(terminal,c,live)
    error=(RUN/'error.txt').read_text()
    frozen.need("ModuleNotFoundError: No module named 'elftools'" in error and
                'tied_gate before' in error,'Exact pre-application import failure required')
    frozen.need(all(not (RUN/('native_%s_0.tsv'%s)).exists() for s in ('applied','reset','reloaded','final'))
                and not (RUN/'first.el').exists() and not (RUN/'second.el').exists(),
                'Must not mislabel partially applied capture')
    frozen.need((RUN/'cleanup-empty.el').read_bytes()==b'' and
                (RUN/'initial-empty.el').read_bytes()==b'','Actual initial/cleanup empty')
    rows=frozen.before_gate(RUN,c)
    targets=[dict(scope=i['scope'],name=s['name'],native_label=label,native_row=r[label])
             for i,r in zip(c['instances'],rows) for s,label in zip(i['signals'],frozen.labels(i))]
    frozen.need(len(targets)==90 and sum(map(len,rows))==3286,'Exact actual rows/targets')
    for file in (Path(__file__).resolve(),Path(__file__).with_name('test_audit_fpnew90_before_offline.py')):
        pins[str(file)]=frozen.life.digest(file)
    frozen.life.check(pins)
    return dict(schema='FPNEW90_FAILED_IMPORT_BEFORE_BINDING_OFFLINE_V1',
                status='EXACT90_REAL_BEFORE_TYPED_BINDING_PASS_NOT_FIVE_STAGE_QUALIFICATION',
                original_run=str(RUN),config_seal=SEAL,native_returncode=0,timeout=False,
                root_cause='DVE exec Python import environment lacks elftools; binder was not reached',
                binder_changed=False,scopes=70,native_rows=3286,targets=targets,protected_objects=3196,
                directions=8520,local_qualified=False,population_application=False,EDA_launched=False,
                initial_and_cleanup_empty=True,pins=pins)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    out=p.parse_args().output.resolve()
    frozen.need(out.parent==frozen.life.OUT and not out.exists(),'Fresh independent evidence only')
    result=evaluate();frozen.life.save(out,result)
    print(json.dumps(dict(output=str(out),SHA=frozen.life.digest(out),status=result['status'])))
