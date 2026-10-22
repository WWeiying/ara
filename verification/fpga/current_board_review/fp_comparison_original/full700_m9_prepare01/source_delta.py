#!/usr/bin/env python3
"""Narrow executable transformation proof, without reopening any raw trace."""
import ast
import difflib
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
from newscope import HERE, PACKED, CASE, NAME, PREVIOUS
from model import model, _old
from prepare import RUN, sha, save, replace_one


def array(text, label):
    start = text.index(label)
    body = re.search(r'=\s*(\{[\s\S]*?\});', text[start:]).group(1)
    body = re.sub(r'UINT64_C\((0x[0-9a-f]+)\)', lambda m:str(int(m[1],16)), body)
    return ast.literal_eval(body.replace('{','[').replace('}',']'))


def main():
    oldcase = (PACKED/'run01/case.c').read_text()
    original = (CASE/'case.c').read_text()
    oldname = 'alias_v8_e16m8_prefix682'
    assert oldcase.count(oldname)==original.count(oldname)==1
    assert oldcase.count('if(cases==682)')==original.count('if(cases==682)')==1
    for before, after in [(oldcase,RUN/'case.c'),(original,RUN/'original_source_port.c')]:
        assert before.replace(oldname,NAME).replace('if(cases==682)','if(cases==700)')==after.read_text()
    host = (PACKED/'host.c').read_text()
    assert [host.count(x) for x in ('682','698368','11173888')]==[2,1,1]
    assert host.replace('682','700').replace('698368','716800').replace('11173888','11468800')==(RUN/'host_exhaustive.c').read_text()
    oldflow = (PACKED/'host_flow.c').read_text()
    assert oldflow.count(oldname)==2 and oldflow.count('calls==682')==1 and oldflow.count('    ++calls;')==1
    added = '''    if(calls==699) {
        if(mutation==7)status^=1UL<<36;
        if(mutation==8)o[0]^=1;
        if(mutation==9)o[64]^=1;
        if(mutation==10)status|=1;
    }
    ++calls;'''
    assert oldflow.replace(oldname,NAME).replace('calls==682','calls==700').replace('    ++calls;',added)==(RUN/'host_flow.c').read_text()
    oldtable = (PACKED/'run01/tables.h').read_text()
    newtable = (RUN/'tables.h').read_text()
    assert array(oldtable,'input_rows')==array(newtable,'input_rows')
    assert array(oldtable,'packed_cases')==array(newtable,'packed_cases')[:682]
    assert len(array(newtable,'packed_cases'))==700
    assert _old.model()['rows']==model()['rows'][:682]
    files = [Path(__file__),PREVIOUS/'model.py',PREVIOUS/'strict.py',PACKED/'run01/case.c',
             PACKED/'run01/tables.h',PACKED/'host.c',PACKED/'host_flow.c',CASE/'case.c',
             RUN/'case.c',RUN/'original_source_port.c',RUN/'host_exhaustive.c',RUN/'host_flow.c',RUN/'tables.h']
    save(HERE/'source_delta.json',dict(status='EXACT_SOURCE_DELTA700_PASS_NOT_DUT',
         first682_rows_a_b_mask_allowed_flags_identical=True,first682_packed_records_identical=True,
         original_input_ROM_rows_identical=True,host_replacement_occurrences=[2,1,1],
         source_only_name_and_single_stop_change=True,flow_only_name_bound_and_four_endpoint_negatives=True,
         immutable_original_comparator=True,immutable_original_audit_logic=True,pins={str(p):sha(p) for p in files}))
    print('SOURCE_DELTA700_PASS',flush=True)


if __name__=='__main__':main()
