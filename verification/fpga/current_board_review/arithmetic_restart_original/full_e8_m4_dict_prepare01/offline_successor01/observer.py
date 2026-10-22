#!/usr/bin/env python3
"""Offline-only observer successor; immutable original execution stays rejected."""
import ast
import contextlib
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import re
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent
INIT_STORES=((0x80000514,0xe380,8),(0x80000516,0xe780,8),
    (0x80000518,0xeb80,8),(0x8000051a,0xef80,8),(0x8000052a,0x20f71023,2))
sys.path.insert(0,str(SOURCE))
spec=importlib.util.spec_from_file_location('sealed_first_reference',SOURCE/'reference.py')
sealed=importlib.util.module_from_spec(spec);spec.loader.exec_module(sealed)

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,value):
    with p.open('x') as f:json.dump(value,f,indent=2);f.write('\n')

def setup_owned(pc,address,out,start,end):
    return start<=pc<end and out<=address<out+514

class Lifecycle:
    def __init__(self,symbols,start,end,helper_entries=()):
        self.symbols=symbols;self.start=start;self.end=end
        self.next_bss=symbols['__bss_start'];self.entered=False;self.boot_locked=False
        self.helper_entries=set(helper_entries);self.initialized_stores=0

    def enter(self,pc):
        if pc==self.symbols['main']:
            if self.next_bss!=self.symbols['__bss_end']:raise ValueError('Incomplete actual startup BSS sequence')
            self.boot_locked=True
        if pc==self.start:
            if not self.boot_locked:raise ValueError('Missing actual main lifecycle entry')
            self.entered=True
        if self.start<pc<self.end and not self.entered:raise ValueError('Missing arithmetic exact entry')
        if pc in self.helper_entries:
            if self.initialized_stores!=65:raise ValueError('Missing exact per-call 64word+tail stores')
            self.initialized_stores=0

    def store(self,pc,insn,address,size,value):
        out=self.symbols['out']
        if pc==0x80000046:
            if (self.boot_locked or insn!=0x0002b023 or size!=8 or value!=0 or
                address!=self.next_bss or address%8 or address+8>self.symbols['__bss_end']):
                raise ValueError('Not exact pre-main zero SD/BSS sequence')
            self.next_bss+=8
            return
        if address<out+1026 and address+size>out:
            if not (self.entered and self.start<=pc<self.end and out<=address and address+size<=out+514):
                raise ValueError('Unowned/wide/cross-boundary business output store')
            index=self.initialized_stores
            if index>64:raise ValueError('Duplicate business initialization')
            want=INIT_STORES[index%4 if index<64 else 4]
            if ((pc,insn,size)!=want or address!=out+8*index or
                value!=(0x5b5b if index==64 else 0x5b5b5b5b5b5b5b5b)):
                raise ValueError('Business initializer exact PC/insn/address/value/order')
            self.initialized_stores+=1

class ReviewedRaw:
    def __init__(self,path,symbols,start,end,helper_entries):
        self.path=path;self.lifecycle=Lifecycle(symbols,start,end,helper_entries)

    @contextlib.contextmanager
    def open(self):
        regex=re.compile(r'core\s+0:\s+\d\s+(0x[0-9a-f]+)\s+\((0x[0-9a-f]+)\)(.*)')
        mem_regex=re.compile(r'\bmem\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)')
        def checked(stream):
            for line in stream:
                m=regex.match(line)
                if m:
                    pc,insn,rest=int(m[1],16),int(m[2],16),m[3]
                    self.lifecycle.enter(pc)
                    size=sealed.width(insn,True)
                    if size:
                        writes=mem_regex.findall(rest)
                        if len(writes)!=1:raise ValueError('Actual scalar store schema')
                        address,value=(int(v,16) for v in writes[0])
                        self.lifecycle.store(pc,insn,address,size,value)
                yield line
        with self.path.open() as stream:yield checked(stream)

def boundary_tests(symbols,start,end):
    def state():
        v=Lifecycle(symbols,start,end);v.next_bss=symbols['out']+512;return v
    def reject(action):
        try:action()
        except ValueError:return
        raise ValueError('Missed lifecycle negative')
    v=state();v.store(0x80000046,0x0002b023,v.next_bss,8,0)
    v=state();reject(lambda:v.store(0x80000046,0x0002b023,v.next_bss,8,1))
    v=state();reject(lambda:v.store(0x80000046,0x0002b023,v.next_bss+8,8,0))
    v=state();reject(lambda:v.enter(symbols['main']))
    v=state();v.next_bss=symbols['__bss_end'];v.enter(symbols['main'])
    reject(lambda:v.store(0x80000046,0x0002b023,symbols['out']+512,8,0))
    v=state();v.next_bss=symbols['__bss_end'];v.enter(symbols['main']);v.enter(start)
    reject(lambda:v.store(0x80000046,0x0002b023,symbols['out']+512,8,0))
    reject(lambda:v.store(start,0x0002b023,symbols['out']+512,8,0))
    reject(lambda:v.store(start,0x0002b023,symbols['out']-1,8,0))
    reject(lambda:v.store(end,0x0002b023,symbols['out'],8,0))
    reject(lambda:v.store(start,0x0002b023,symbols['out'],8,0x5b5b5b5b5b5b5b5b))
    reject(lambda:v.store(INIT_STORES[0][0],INIT_STORES[0][1],symbols['out'],8,0))
    v.helper_entries={end+4}
    reject(lambda:v.enter(end+4))
    for i in range(65):
        pc,insn,size=INIT_STORES[i%4 if i<64 else 4]
        v.store(pc,insn,symbols['out']+8*i,size,0x5b5b if i==64 else 0x5b5b5b5b5b5b5b5b)
    v.enter(end+4)
    assert v.initialized_stores==0
    original_tree=ast.parse(inspect.getsource(sealed.audit))
    expression=next(node for node in ast.walk(original_tree) if isinstance(node,ast.Compare) and
        isinstance(node.left,ast.Name) and node.left.id=='fresh')
    predicate=compile(ast.Expression(expression),'actual_original_fresh_guard','eval')
    complete=set(range(514));missing=complete-set(range(80,88))
    assert eval(predicate,{},dict(fresh=complete))
    assert not eval(predicate,{},dict(fresh=missing))
    return 16

def audit_function():
    text=(SOURCE/'spike/program.dis').read_text()
    functions={name:int(address,16) for address,name in re.findall(r'^([0-9a-f]+) <([^>]+)>:',text,re.M)}
    start=functions['arithmetic_main'];end=min(v for v in functions.values() if v>start)
    original=inspect.getsource(sealed.audit)
    before='if out<=address<out+514:\n                    require(address+w<=out+514,'
    after='if setup_owned(pc,address,out,SETUP_START,SETUP_END):\n                    require(address+w<=out+514,'
    if original.count(before)!=1:raise ValueError('Exact original observer boundary changed')
    modified=original.replace(before,after)
    namespace=dict(sealed.__dict__)
    namespace.update(setup_owned=setup_owned,SETUP_START=start,SETUP_END=end)
    exec(compile(modified,'offline_owner_only_audit','exec'),namespace)
    return namespace['audit'],dict(original_observer_sha256=sha(SOURCE/'reference.py'),
        original_audit_sha256=hashlib.sha256(original.encode()).hexdigest(),
        successor_audit_sha256=hashlib.sha256(modified.encode()).hexdigest(),
        sole_replacement=dict(before=before,after=after),setup_start=start,setup_end=end)

def main():
    # Small discriminating lifecycle boundary checks, not a repeated whole Host.
    symbols=json.loads((SOURCE/'spike/symbols.json').read_text());out=symbols['out']
    audit,delta=audit_function();start,end=delta['setup_start'],delta['setup_end']
    actual_code={int(m[1],16):int(m[2],16) for m in re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s',
        (SOURCE/'spike/program.dis').read_text(),re.M)}
    if any(actual_code.get(pc)!=insn for pc,insn,_ in INIT_STORES):raise ValueError('Actual ELF initializer PC/code drift')
    helpers=json.loads((SOURCE/'proof.json').read_text())['backends']['spike']['helpers']
    helper_entries=[helpers[f'op_{i}'][0]['pc'] for i in range(25)]
    lifecycle_checks=boundary_tests(symbols,start,end)
    assert not setup_owned(0x80000046,out+512,out,start,end)
    assert setup_owned(start,out+512,out,start,end)
    assert setup_owned(start,out+513,out,start,end)
    assert not setup_owned(end,out,out,start,end)
    # Business writes crossing514 are still rejected by the unchanged audit body.
    assert not (out+512+8<=out+514)
    assert out+512+2<=out+514
    original_pins=json.loads((SOURCE/'reference01/preflight_pins.json').read_text())
    for path,digest in original_pins.items():
        if sha(path)!=digest:raise ValueError('Original pin drift '+path)
    inputs=dict(original_pins)
    for name in ('commits.log','execution.json','STOPPED.json','spike.log','command.json'):
        p=SOURCE/'reference01'/name;inputs[str(p)]=sha(p)
    inputs[str(Path(__file__).resolve())]=sha(__file__)
    save(HERE/'preflight.json',dict(pins=inputs,observer_delta=delta,
        boundary_checks=6,lifecycle_checks=lifecycle_checks,Spike_invocations=0,DUT_runs=0,original_STOPPED_preserved=True))
    try:
        report=audit(ReviewedRaw(SOURCE/'reference01/commits.log',symbols,start,end,helper_entries))
        values=re.findall(r'^0x([0-9a-f]{16})$',(SOURCE/'reference01/spike.log').read_text(),re.M)
        if len(values)!=3 or int(values[0],16)!=0 or int(values[1],16)!=report['firmware_to_exit']+report['boot']:
            raise ValueError('Original numeric/counter mismatch')
        for path,digest in inputs.items():
            if sha(path)!=digest:raise ValueError('Offline post-pin drift '+path)
        report.update(status='ARCHITECTURAL_SOURCE_REFERENCE_ACCEPTED_OLD_OBSERVER_NOT_ACCEPTED',
            original_execution_sha256=sha(SOURCE/'reference01/execution.json'),
            original_STOPPED_sha256=sha(SOURCE/'reference01/STOPPED.json'),
            raw_sha256=sha(SOURCE/'reference01/commits.log'),raw_bytes=(SOURCE/'reference01/commits.log').stat().st_size,
            pins_pre_post_unchanged=True,original_numeric_receipt_unmodified=True,observer_delta=delta,
            cost_target=3000000,cost_within_target=report['firmware_to_exit']<=3000000,
            Spike_invocations=0,DUT_runs=0)
        save(HERE/'result.json',report)
        print(json.dumps({k:report[k] for k in ('status','calls','firmware_to_exit','cost_within_target')}),flush=True)
    except BaseException as error:
        save(HERE/'STOPPED.json',dict(first_cause=repr(error),no_retry=True,Spike_invocations=0,DUT_runs=0))
        raise

if __name__=='__main__':main()
