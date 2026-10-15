"""Standalone synthetic env tests; never write prepared01/service_exit.json."""
import json
from pathlib import Path
import tempfile
import pinned_service_exit as hook
from checker import common,sha,HERE,require

cases=[]
good=dict(EXIT_CODE='exited',EXIT_STATUS='0',SERVICE_RESULT='success',SECRET='not recorded')
r=hook.payload(good,1)
require(set(r)=={'EXIT_CODE','EXIT_STATUS','SERVICE_RESULT','recorded_unix_s'},'Only allowed hook fields')
cases.append('success_fields_only')
for update in (dict(EXIT_STATUS='17',SERVICE_RESULT='exit-code'),
               dict(EXIT_CODE='killed',EXIT_STATUS='TERM',SERVICE_RESULT='timeout')):
    actual=hook.payload(dict(good,**update),1)
    require(all(actual[k]==v for k,v in update.items()),'Retain actual nonzero/signal fields')
    cases.append('nonzero_or_signal_retained')
for field in hook.FIELDS:
    bad=dict(good);del bad[field]
    try:hook.payload(bad,1)
    except ValueError:cases.append('missing_'+field)
    else:raise AssertionError(field)
for update in (dict(EXIT_STATUS=True),dict(EXIT_CODE='success'),dict(EXIT_STATUS='zero'),dict(SERVICE_RESULT='success\n')):
    try:hook.payload(dict(good,**update),1)
    except ValueError:cases.append('malformed_rejected')
    else:raise AssertionError(update)
with tempfile.TemporaryDirectory() as tmp:
    path=Path(tmp)/'synthetic.json';hook.write(path,r)
    try:hook.write(path,r)
    except FileExistsError:cases.append('exclusive_output')
    else:raise AssertionError('overwrite')
    require(json.loads(path.read_text())==r,'Original receipt retained')
common.save(HERE/'service_exit_host.json',dict(status='HOST_SERVICE_EXIT_PASS_NOT_SYSTEMD_EVIDENCE',
    tests=len(cases),cases=cases,helper_sha256=sha(HERE/'pinned_service_exit.py'),
    test_sha256=sha(Path(__file__)),actual_service_exit_written=False))
print('HOST_SERVICE_EXIT_PASS',len(cases))
