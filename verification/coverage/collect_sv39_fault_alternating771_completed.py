"""Reuse exact CSR/prefix proof; resolve design VDB from sealed771 ledger."""
import argparse
import inspect
from pathlib import Path
from types import FunctionType,SimpleNamespace
import collect_sv39_fault_alternating771_csr_return as csr

life,require=csr.life,csr.require

def design_vdb():
    base=life.read_bound(csr.old.p.BASE/'admission-manifest.json',csr.old.p.BASE_SHA)
    path=csr.old.p.BASE/'combined-inputs.txt'
    require(life.digest(path)==base['output_pins'][str(path)],'Exact771 ledger hash')
    ledger=path.read_text().splitlines()
    require(len(ledger)==len(set(ledger))==772,'Exact771 population')
    design=Path(ledger[0]);require((design/'snps/coverage/db/design/verilog.design.xml').is_file(),'Compiled design VDB')
    return str(design)

def collect(output):
    raw=inspect.getsource(csr.old.raw_gain);needle="before['tests'][0]"
    require(raw.count(needle)==1,'Unique wrong design-source expression')
    namespace=dict(csr.old.raw_gain.__globals__,design_vdb=design_vdb)
    exec(compile(raw.replace(needle,'design_vdb()'),str(Path(__file__).resolve())+':raw','exec'),namespace)
    inherited=FunctionType(csr.old.collect.__code__,dict(csr.old.collect.__globals__,raw_gain=namespace['raw_gain']),
      csr.old.collect.__name__,csr.old.collect.__defaults__)
    proxy=SimpleNamespace(**dict(vars(csr.old),collect=inherited))
    source=inspect.getsource(csr.collect)
    needle='source=inspect.getsource(old.collect)'
    require(source.count(needle)==1,'Exact CSR successor dependency gate')
    source=source.replace(needle,"manifest['pins']=life.merge_pins(manifest['pins'],{str(CSR_PATH):life.digest(CSR_PATH),str(TEST_PATH):life.digest(TEST_PATH)})\n    "+needle)
    namespace=dict(csr.collect.__globals__,old=proxy,__file__=__file__,
      CSR_PATH=Path(csr.__file__).resolve(),TEST_PATH=Path(__file__).with_name('test_collect_sv39_fault_completed.py'))
    exec(compile(source,str(Path(__file__).resolve())+':preserved-csr','exec'),namespace)
    namespace['collect'](output)

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--output',type=Path,required=True)
    collect(a.parse_args().output.resolve())
