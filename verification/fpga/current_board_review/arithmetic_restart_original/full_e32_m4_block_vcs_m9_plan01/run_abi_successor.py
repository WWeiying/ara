"""Explicit composite acceptance; old full Host rc1 is never rewritten."""
import ast
from pathlib import Path
import subprocess
import sys
import time
import checker as c
import context

def main():
    old=c.read(c.HERE/'host01.json');receipt=c.read(c.HERE/'host01_process_exit.json')
    c.require(old['status']=='FAIL_HOST_ONLY' and old['tests']==32 and old['failures']==1 and old['full5985_streams']==1,'Exact old completed Host scope')
    c.require(type(receipt['returncode']) is int and receipt['returncode']==1 and receipt['timed_out'] is False and receipt['pins_unchanged'] is True,'Actual old1, no timeout')
    pins=dict(c.read(c.HERE/'host01_command.json')['pins']);pins.update(old['pins']);c.common.base.verify_pins(pins)
    log=(c.HERE/'host01.log').read_text();lines=log.splitlines()
    c.require(lines.count('ok')==31 and lines.count('ERROR')==1 and log.count('ERROR: test_actual_elf_abi (__main__.Host)')==1 and
        'FAILED (errors=1)' in log and 'Ran 32 tests' in log and all('HOST_STAGE '+x in log for x in ('strict_finish','generic_finish','owner_finish')),
        'Exactly one failed test after completed full positive/generic/owners')
    c.require('self.assertEqual(state.value(0x800ffff8,8),0x80000052)' in log and 'Missing actual initialized byte' in log,
        'Exact isolated wrong test address, no other failure')
    tree=ast.parse((c.HERE/'test_host.py').read_text())
    node=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='test_actual_elf_abi')
    c.require(sum(isinstance(n,ast.Constant) and n.value==0x800ffff8 for n in ast.walk(node))==1,'Original wrong assertion pinned unchanged')
    for n in ('host01.json','host01_process_exit.json','host01.log','host01_command.json',
        'test_abi_successor.py','run_abi_successor.py','prepare_successor.py','HOST_ABI_SUCCESSOR.md'):
        pins[str(c.HERE/n)]=c.sha(c.HERE/n)
    command=[sys.executable,'-B','test_abi_successor.py'];start=time.monotonic();timeout=False
    context.save(c.HERE/'host_abi_command.json',dict(command=command,timeout_s=90,pins=pins,full_stream_rerun=False))
    with (c.HERE/'host_abi.log').open('x') as log:
        child=subprocess.Popen(command,cwd=c.HERE,stdout=log,stderr=subprocess.STDOUT)
        try:rc=child.wait(timeout=90)
        except subprocess.TimeoutExpired:timeout=True;child.kill();rc=child.wait()
    unchanged=all(c.sha(p)==h for p,h in pins.items())
    context.save(c.HERE/'host_abi_process_exit.json',dict(returncode=rc,pid=child.pid,timeout=timeout,
        elapsed_s=time.monotonic()-start,pins_unchanged=unchanged,retries=0))
    c.require(type(rc) is int and rc==0 and not timeout and unchanged,'Actual short ABI successor must pass')
    for n in ('host_abi_command.json','host_abi.log','host_abi_process_exit.json'):pins[str(c.HERE/n)]=c.sha(c.HERE/n)
    context.save(c.HERE/'host_composite.json',dict(status='PASS_COMPOSITE_HOST_ONLY_ORIGINAL_RC1_PRESERVED',
        original_full_Host_rc=1,original_tests=32,original_passed_tests=31,isolated_test_error='hardcoded ABI address800ffff8',
        actual_short_ABI_rc=rc,short_ABI_tests=4,full5985_streams=1,full_positive_shapes=[c.SHAPE],
        actual_abi_entry_checked=True,source_checker_builder_unchanged=True,pins=pins,
        full_Host_reruns=0,reference_DUT_runs=0))
    print('COMPOSITE_HOST_PASS_OLD1_PRESERVED_NEW_ABI0',flush=True)

if __name__=='__main__':main()
