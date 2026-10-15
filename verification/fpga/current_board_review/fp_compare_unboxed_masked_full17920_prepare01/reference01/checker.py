"""Masked successor of sealed full17920 checker; unchanged raw/helper semantics."""
import ast
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import sys
import textwrap

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
OLD=ROOT.parent/'fp_compare_unboxed_full17920_prepare01/reference_entry02/checker.py'
sp=importlib.util.spec_from_file_location('sealed_unboxed17920_reference',OLD)
base=importlib.util.module_from_spec(sp);sp.loader.exec_module(base)
require,parse_line,word,MASK=base.require,base.parse_line,base.word,base.MASK
NAME='fp_compare_unboxed_masked_e16_mf4_full17920'


def full_config():
    spec=json.loads((HERE/'spec.json').read_text());spec['code']={int(k):v for k,v in spec['code'].items()}
    gold=json.loads((ROOT/'model.json').read_text())['rows']
    require(len(gold)==17920 and gold[38]['flags']==0 and gold[-1]['flags']==1,'Full masked source identity')
    return spec,gold


def completion_successor():
    tree=ast.parse(textwrap.dedent(inspect.getsource(base.Checker.validate_complete)))
    counts=[0,0]
    class Change(ast.NodeTransformer):
        def visit_Constant(self,node):
            if node.value==2240:
                counts[0]+=1
                return ast.copy_location(ast.Constant(value=8960),node)
            if node.value=='fp_compare_unboxed_e16_mf4_full17920':
                counts[1]+=1
                return ast.copy_location(ast.Constant(value=NAME),node)
            return node
    tree=Change().visit(tree);require(counts==[1,1],'Narrow sealed completion sites')
    ast.fix_missing_locations(tree);namespace=dict(base.__dict__)
    exec(compile(tree,str(HERE/'derived_completion.py'),'exec'),namespace)
    return namespace['validate_complete']


class Checker(base.Checker):
    validate_complete=completion_successor()

    def consume(self,r):
        super().consume(r)
        if r['pc'] in self.capmap:
            i=self.capmap[r['pc']]
            if i==1:
                require((self.csr.get('vl'),self.csr.get('vtype'),self.csr.get('vstart'))==(16,14,0),
                        'Actual capacity VL16/vtype14/vstart0 state')
            elif i in (0,2):
                require(not(r['v'] or r['f'] or r['csr'] or r['mem'] or r['cfg']), 'Capacity scalar side effects')
                if i==2:require(not r['x'],'Capacity ret side effects')

    def record_load(self,address,value,width):
        g=self.current()
        require(self.calls%2==0 and self.fresh==0 and self.active is None,'Masked two-sticky record phase')
        require(self.record_loads==g['record_index'],'8960 mode-record LD exact order')
        require(width==8 and address==self.a['oracle_records']+8*g['record_index'],'Actual oracle record address')
        require(value==word(self.memory,address,8),'Actual oracle record contents')
        self.record_index=g['record_index'];self.record_loads+=1


def audit(path):
    spec,gold=full_config();check=Checker(spec,gold)
    before=path.stat();digest=hashlib.sha256();count=0
    try:
        with path.open('rb') as stream:
            for raw in stream:
                digest.update(raw);count+=len(raw)
                require(raw.endswith(b'\n'),'Truncated final raw row')
                check.consume(parse_line(raw.decode('ascii')))
        result=check.finish()
        after=path.stat()
        require((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)==
                (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns) and count==before.st_size,
                'Closed raw stat/bytes drift')
        result.update(raw_sha256=digest.hexdigest(),raw_bytes=count,hash_in_semantic_pass=True,
            raw_stat_before=dict(dev=before.st_dev,inode=before.st_ino,size=before.st_size,mtime_ns=before.st_mtime_ns),
            raw_stat_after=dict(dev=after.st_dev,inode=after.st_ino,size=after.st_size,mtime_ns=after.st_mtime_ns),
            masked=True,records_expected=8960,alloff_expected_sticky_only=True)
        return result
    except BaseException as error:
        raise ValueError(str(error)+' context='+repr(check.current_context)) from error
