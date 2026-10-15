"""Scalar CSV adapter to mature FP checker, exact alias50 machine code/model."""
import csv
import re
import sys
from pathlib import Path
sys.dont_write_bytecode=True
from newscope import *
import dut_strict as source
from model import require,model,INPUT
sys.path.insert(0,str(BASE/'gather_repair05'))
import regression as common
read,sha=common.read,common.sha
VETO=re.compile(source.VETO.pattern+r'|\b(?:FAIL|DETAIL|ABORT|ABORTED)\b',re.I)


def specification(elf):
    require(sha(READY)==READY_SHA,'Actual source READY drift')
    require(sha(elf)==read(READY)['soc_elf_sha256'],'Actual alias50 SoC ELF')
    s=source.specification(elf)
    maps=read(REF/'address_map.json')['soc']
    for op in range(10):
        rr=s['routines'][op];proof=maps['helpers']['op_'+str(op)]
        require([(r['pc'],r['insn']) for r in rr]==[(int(pc,16),code) for pc,code,_ in proof],
                'Actual helper/original byte-equivalence provenance')
    require(maps['target'][1]=='62881457' and int(maps['target'][0],16)==s['routines'][0][7]['pc'],
            'Source target identity')
    original=REF/'prepared'/NAME/'original'
    text=(original/'fixtures.h').read_text()
    values=[int(x,16) for x in re.findall(r'UINT64_C\(0x([0-9a-f]+)\)',text.splitlines()[0])]
    require(values==INPUT,'Independent source FP16 inputs')
    from model import compare
    pairs=[(int(a),int(b)) for a,b in re.findall(r'\{(\d+),(\d+)\}',text)][0:256]
    require(pairs==[compare(0,a,b) for a in INPUT for b in INPUT],'Independent vmfeq/fixture truth table')
    rows=model()['rows']
    ledger=read(REF/'prepared'/NAME/'call_sequence.json')
    require(ledger==[dict(seed=g['seed'],op=g['op'],vl=g['vl'],mask=g['mode'],sticky=g['sticky'],vstart=0)
                     for g in rows],'All49 predecessors and original call50')
    return s


def convert(rows):
    for r in rows:
        require(r['event'] in EVENTS,'Exact six-event whitelist')
        yield dict(event=r['event'],cycle=int(r['cycle']),order=int(r['order']),trap=int(r['trap']),
            pc=int(r['pc'],16),insn=int(r['insn'],16),rd=int(r['rd']),value=int(r['rd_wdata'],16),
            address=int(r['mem_addr'],16),rmask=int(r['mem_rmask'],16),wmask=int(r['mem_wmask'],16),wdata=int(r['mem_wdata'],16))


def console_gate(text,name=NAME):
    require(name==NAME and not VETO.search(text),'Original prefix raw failure veto/runtime identity')
    lines=text.splitlines()
    for prefix,exact in [('RVV_FP_COMPARE_PASS',MARKER),('BOARD_CASE_BEGIN','BOARD_CASE_BEGIN '+NAME),
        ('BOARD_CASE_PASS','BOARD_CASE_PASS '+NAME),('BOARD_REPLAY_PASS','BOARD_REPLAY_PASS'),
        ('Core Test *** SUCCESS ***',common.SUCCESS)]:
        require([l for l in lines if l.startswith(prefix)]==[exact],'Missing/ambiguous original oracle '+prefix)
    require('$finish' in text,'Simulator finish missing')


def artifacts(result,case,ledger,spec,validator):
    require(result.status=='PASS' and result.name==NAME and not result.reason,'Exact original prefix PASS')
    common.check_artifacts(result,case,ledger)
    for name in ('console.log','work/run.vcs.log'):console_gate((result.artifact_dir/name).read_text())
    path=result.artifact_dir/'commit_trace.csv';generic=validator(path)
    require(generic['cvx_exception_count']==0,'CVX exception')
    with path.open() as stream:strict=source.audit(convert(csv.DictReader(stream)),spec)
    require(generic['retire_count']==strict['retired'],'Complete trace counter agreement')
    return dict(strict=strict,generic=generic,csv_sha256=sha(path),
                scope='All25600 source bits/100guards/50flags/vstarts; scalar CSV, not direct vector-port payload')
