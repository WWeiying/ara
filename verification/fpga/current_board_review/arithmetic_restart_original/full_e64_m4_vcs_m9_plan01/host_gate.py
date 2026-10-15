"""Exact inherited 39 PASS + corrected single fixture test; old exit1 retained."""
import ast
from pathlib import Path
import re
import checker as c

def old_outcome(host,receipt,log):
    c.require(host['status']=='FAIL_HOST_ONLY' and (host['tests'],host['failures'],host['errors'])==(40,1,0) and
        type(receipt['returncode'])is int and receipt['returncode']==1 and not receipt['timed_out'] and
        0<receipt['elapsed_s']<=600,'Exact preserved Host02 outcome, not generic failure waiver')
    names=re.findall(r'^(test_\w+) \(([^\n]+)\) \.\.\. (ok|FAIL)$',log,re.M)
    # Numeric-monitor test prints its diagnostics between the name and "ok".
    c.require(len(names)==39 and sum(x[2]=='ok' for x in names)==38 and
        [(n,m) for n,m,s in names if s=='FAIL']==[('test_actual_u64_constant_setter','test_host.Host')] and
        log.count('FAIL: test_actual_u64_constant_setter (test_host.Host)')==1 and 'ERROR:' not in log and
        'Ran 40 tests' in log and log.rstrip().endswith('FAILED (failures=1)') and
        'AssertionError: 18 not found in' in log and
        re.search(r'test_numeric_first_0_17_timeout_and_first_record \(test_host.Host\) \.\.\..*?\nok\n',log,re.S),
        'Only exact wrong m2 GPR fixture assertion; all other39 tests passed')
    x=host['full_positive_summary'];o=host['owner_summary']
    c.require([x[k] for k in ('calls','results','guards','returned_vstart_zero','helper_instructions','packed_output_reads',
        'expected_dictionary_reads','dictionary_ID_reads','sticky_equal_BEQ','FP_input_stores','mask_bit_stores')]==
        [5985,383040,11970,5985,77805,395010,395010,53865,395010,241920,77175] and x['full_order'] and not x['partitioned'],
        'Full positive data/phase evidence persists despite fixture assertion')
    c.require((o['compulsory_memory_owners'],o['required_target_owners'],o['minimum_required_owners'])==(29925,3762,33687),
        'Full owner evidence, no partial replacement')

def verify_old():
    host=c.read(c.HERE/'host02.json');receipt=c.read(c.HERE/'host02_process_exit.json')
    old_outcome(host,receipt,(c.HERE/'host02.log').read_text())
    c.require(host['input_pins_pre_post_unchanged'] and host['pins']==c.read(c.HERE/'host02_command.json')['input_pins'],'Actual Host02 pins')
    for p,h in host['pins'].items():
        source=c.HERE/'host02_source/replay.py' if Path(p)==c.HERE/'replay.py' else Path(p)
        c.require(c.sha(source)==h,'Exact Host02 tested file '+p)
    old=ast.parse((c.HERE/'host02_source/replay.py').read_text());new=ast.parse((c.HERE/'replay.py').read_text())
    for tree in (old,new):tree.body=[n for n in tree.body if not isinstance(n,ast.FunctionDef) or n.name!='prepare']
    c.require(ast.dump(old,include_attributes=False)==ast.dump(new,include_attributes=False),'Only prepare Host admission changes; all runtime functions unchanged')
    return host

def verify():
    verify_old();now=c.read(c.HERE/'host03.json');exit=c.read(c.HERE/'host03_process_exit.json')
    c.require(now['status']=='PASS_NARROW_HOST_SUCCESSOR' and now['failures']==now['errors']==0 and now['tests']==5 and
        type(exit['returncode'])is int and exit['returncode']==0 and not exit['timed_out'],'Actual corrected short Host exit0')
    c.require(now['pins_unchanged'] and c.read(c.HERE/'host03_command.json')['input_pins']==now['pins'],'Actual short Host identity')
    c.common.base.verify_pins(now['pins'])
    pins=dict(now['pins'])
    for name in ('host03.json','host03_process_exit.json','host03_command.json','host03.log','host02_source/replay.py'):
        pins[str(c.HERE/name)]=c.sha(c.HERE/name)
    return pins
