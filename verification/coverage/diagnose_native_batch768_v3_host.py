"""Read-only reproduction of a host audit rejection; not native qualification."""
import argparse
import copy
import json
from pathlib import Path
from unittest.mock import patch

import report_native_batch768_v3 as r


def differences(expected, actual):
    return [dict(index=n, expected=expected[n] if n<len(expected) else None,
                 actual=actual[n] if n<len(actual) else None)
            for n in range(max(len(expected),len(actual)))
            if (expected[n] if n<len(expected) else None) != (actual[n] if n<len(actual) else None)]


def diagnose(selection):
    c=copy.deepcopy(r.life.read_bound(r.base.BASE/'config.json',r.base.BASE_SHA))
    read=r.life.OUT/'requester-read108-native767-agent-20261007-01/capture-result.json'
    extra=r.base.additions(False,read,'a31abca542924c82f51f53e4e2c5ed17b22c3476eae035ecdccd5f355dbe749b')
    extra.update({key:r.source_family(key) for key in sorted(r.FIRST)})
    extra['fixed120']=r.fixed_family();c['new_families']=extra
    original=r.base.prior.old.audit_six
    failures=[]
    scopes={'native':c['queue_config']['instances'],
            'diagnostic':c['diagnostic_config']['instances'],
            'child':c['child_config']['instances'],
            'batch_scale':c['batch_captures']['scale120']['config']['instances']}
    def audit(out,prefix,references):
        for index,reference in enumerate(references):
            for stage in r.base.prior.STAGES:
                table=out/('%s_%s_%d.tsv'%(prefix,stage,index))
                actual=r.base.prior.old.table(table,['handle','path','meta','name','column1','column2'])
                diff=differences(reference,actual)
                if diff:
                    scope=scopes[prefix][index]['scope']
                    failures.append(dict(prefix=prefix,scope=scope,stage=stage,
                        expected_count=len(reference),actual_count=len(actual),
                        differing_rows=len(diff),rows=diff[:12],
                        overlapping_families=[k for k,item in extra.items() if scope in item['reference']]))
        original(out,prefix,references)
    failure=None
    with patch.object(r.base.prior.old,'audit_six',audit):
        try:r.private_namespace()['host_hook'](selection,c)
        except ValueError as exc:failure=str(exc)
    r.require(failure and failures,'Expected exact audit rejection was not reproduced')
    return dict(status='HOST_REJECTION_REPRODUCED_NOT_NATIVE',reason=failure,
                failures=failures,EDA_launched=False,frozen_files_modified=False,
                pins={str(selection):r.life.digest(selection),str(Path(r.__file__)):r.life.digest(r.__file__),
                      str(Path(__file__).resolve()):r.life.digest(__file__)})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--selection',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=diagnose(a.selection.resolve())
    r.life.save(a.output.resolve(),result)
    print(json.dumps(result,indent=2))
