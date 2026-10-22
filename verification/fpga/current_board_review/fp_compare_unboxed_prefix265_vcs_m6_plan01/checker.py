"""M6 actual CSV adapter to sealed original265 instruction/setup/oracle checker."""
import csv
from pathlib import Path
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
REF=HERE.parent/'fp_compare_unboxed_prefix265_prepare01'
sys.path.insert(0,str(REF))
import dut_strict as source
from model import NAME,require
sys.path.insert(0,str(HERE.parent/'gather_repair05'))
import regression as common
read,sha=common.read,common.sha
READY_SHA='ee10a401774a5cb474be69c317edad4ea052c147a42b5fd03aa4cc4b1f5db731'
VETO=source.VETO
def specification(elf):
    require(sha(REF/'READY.json')==READY_SHA,'READY drift')
    ready=read(REF/'READY.json');require(sha(elf)==ready['soc_elf']['sha256'],'Actual SoC ELF drift')
    return source.specification(elf)
def convert(rows):
    for r in rows:
        yield dict(event=r['event'],cycle=int(r['cycle']),order=int(r['order']),trap=int(r['trap']),
            pc=int(r['pc'],16),insn=int(r['insn'],16),rd=int(r['rd']),value=int(r['rd_wdata'],16),
            address=int(r['mem_addr'],16),rmask=int(r['mem_rmask'],16),wmask=int(r['mem_wmask'],16),wdata=int(r['mem_wdata'],16))
def console_gate(text):
    require(not VETO.search(text),'Raw failure veto')
    lines=text.splitlines()
    for prefix,exact in [('RVV_FP_COMPARE_PASS','RVV_FP_COMPARE_PASS sew=16 cases=265 errors=0'),
        ('BOARD_CASE_BEGIN','BOARD_CASE_BEGIN '+NAME),('BOARD_CASE_PASS','BOARD_CASE_PASS '+NAME),
        ('BOARD_REPLAY_PASS','BOARD_REPLAY_PASS'),('Core Test *** SUCCESS ***',common.SUCCESS)]:
        require([l for l in lines if l.startswith(prefix)]==[exact],'Missing/ambiguous original oracle '+prefix)
    require('$finish' in text,'Simulator finish missing')
def artifacts(result,case,ledger,spec,validator):
    require(result.status=='PASS' and result.name==NAME and not result.reason,'Case not PASS')
    common.check_artifacts(result,case,ledger)
    for n in ('console.log','work/run.vcs.log'):console_gate((result.artifact_dir/n).read_text())
    path=result.artifact_dir/'commit_trace.csv';generic=validator(path)
    require(generic['cvx_exception_count']==0,'Unexpected CVX exception')
    with path.open() as stream:strict=source.audit(convert(csv.DictReader(stream)),spec)
    require(generic['retire_count']==strict['retired'],'Trace counters mismatch')
    return dict(strict=strict,generic=generic,csv_sha256=sha(path),scope='Scalar full oracle, no direct DUT vector payload claim')
