"""Bind actual independent terminal report and exact accepted reference."""
from pathlib import Path
import checker as c
def verify(binding,ready):
    p=Path(binding['path'])
    c.require(c.sha(p)==binding['sha256']=='a323f9dbc657b0d527b12f35001d2db0d52b5d6f1e7a504c2af24d852b26e34f','Actual independent terminal report')
    c.require('NO_BLOCKER_REFERENCE_TERMINAL_BINDING_NOT_DUT' in p.read_text(),'Actual report verdict')
    c.require(binding['READY_sha256']==c.READY_SHA and c.sha(c.REF/'READY.json')==c.READY_SHA,'Same accepted READY')
    report=c.read(c.REF/'reference01/result.json')
    c.require(c.sha(c.REF/'reference01/result.json')==ready['reference_sha256']=='042e258f88415d47802331438b1e73552a9537fab6e571195693b41dc2b038d5','Exact accepted full reference result')
    c.require(report['EOF_checked'] and report['pins_unchanged'] and report['closed_raw_parses']==1 and report['firmware_to_HTIF']==2804792,'Actual full reference complete')
