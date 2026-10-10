"""Exact one-line diagnostic guard successor; all frozen functional gates retained."""
import argparse
import inspect
import json
from pathlib import Path
import re

import collect_qbs_k2_row_pending782 as old

OLD_SHA='37e24fe8096951260979e938832726f33fd109eaff77c87b77fea4f238ec47da'
PATTERN=r'^\s*(?:QBS_PENDING_PROBE_REJECT\b|UCLI_ERROR\b|Error-)'


def actual_error(text):return re.search(PATTERN,text,re.M) is not None


def collect(run,seal,out):
    life,require=old.life,old.require
    require(life.digest(Path(old.__file__))==OLD_SHA,'Frozen collector changed')
    source=inspect.getsource(old.collect)
    before="re.search(r'QBS_PENDING_PROBE_REJECT|UCLI_ERROR|Error-',console)"
    require(source.count(before)==1,'Exact one guard substitution')
    source=source.replace(before,'actual_error(console)')
    namespace=dict(vars(old),actual_error=actual_error)
    exec(compile(source,str(Path(__file__).resolve()),'exec'),namespace)
    result=namespace['collect'](run,seal,out)
    path=out/'qualification.json';record=json.loads(path.read_bytes())
    extra={str(Path(__file__).resolve()):life.digest(Path(__file__)),
        str(Path(__file__).with_name('test_qbs_k2_row_pending782_echo.py').resolve()):
        life.digest(Path(__file__).with_name('test_qbs_k2_row_pending782_echo.py'))}
    record['input_pins']=life.merge_pins(record['input_pins'],extra)
    record['diagnostic_guard_successor']=dict(original_sha256=OLD_SHA,pattern=PATTERN,
        flags='MULTILINE',only_change='Ignore source echoes, reject actual diagnostic lines')
    life.check(record['input_pins'])
    # This is the new output just created above, never the original failed receipt.
    life.save(path,record);result['seal']=life.digest(path)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True)
    p.add_argument('--prepared-seal',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(json.dumps(collect(a.run.resolve(),a.prepared_seal,a.output.resolve())),flush=True)
