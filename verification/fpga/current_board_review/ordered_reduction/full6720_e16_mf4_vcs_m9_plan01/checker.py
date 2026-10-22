"""Reuse lossless generic transport, owner pairing and numeric-first artifacts."""
import re
from scope import *
from specification import specification,model,owner_contract
from strict import Strict
mature=load('full6720_mature_protocol',MATURE/'checker.py')
common=mature.common
VETO=re.compile(common.BAD.pattern+r'|RVV_FP_REDSPECIAL_(?:DETAIL|FAIL|CAPACITY_FAIL)',re.I)
def console_gate(text):
    require(not VETO.search(text),'Original raw failure veto')
    lines=text.splitlines()
    for pre,want in [('BOARD_CASE_BEGIN','BOARD_CASE_BEGIN '+NAME),('RVV_FP_REDSPECIAL_PASS',MARKER),('BOARD_CASE_PASS','BOARD_CASE_PASS '+NAME),('BOARD_REPLAY_PASS','BOARD_REPLAY_PASS'),('Core Test *** SUCCESS ***',common.SUCCESS)]:
        require([x for x in lines if x.startswith(pre)]==[want],'Exact console '+pre)
    require('$finish' in text,'Actual simulator finish')
mature.console_gate=console_gate
mature.VETO=VETO
Owners=mature.Owners
audit=mature.audit
artifacts=mature.artifacts
