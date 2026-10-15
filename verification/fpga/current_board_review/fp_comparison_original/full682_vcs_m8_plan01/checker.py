"""Composition of frozen six-event lifecycle validator and ordered682 oracle."""
import csv
import re
import sys
from pathlib import Path
sys.dont_write_bytecode=True
from newscope import *
from model import require,model,compare,INPUT
import strict as source
sys.path.insert(0,str(BASE/'gather_repair05'))
import regression as common
read,sha=common.read,common.sha
VETO=re.compile(source.VETO.pattern+r'|\b(?:FAIL|DETAIL|ABORT|ABORTED)\b',re.I)

def specification(elf):
    require(sha(READY)==READY_SHA,'Source READY identity')
    r=read(READY);require(sha(elf)==r['soc_elf_sha256'],'Exact packed SoC ELF')
    s=source.specification(elf)
    old=HERE.parent/'prepared02/prepared'/NAME
    ledger=read(old/'call_sequence.json')
    require(ledger==[dict(seed=g['seed'],op=g['op'],vl=g['vl'],mask=g['mode'],sticky=g['sticky'],vstart=0)
                     for g in model()['rows']],'All682 predecessor sequence')
    text=(old/'original/fixtures.h').read_text()
    import json
    wanted=json.loads(text.split('expected[6][16][16]=')[1].split(';')[0].replace('{','[').replace('}',']'))
    require(wanted==[[[list(compare(op,a,b)) for b in INPUT] for a in INPUT] for op in range(6)],'Independent full FP16 fixture model')
    return s

def convert(rows,protocol=None):
    for r in rows:
        require(r['event'] in EVENTS,'Six-event whitelist')
        if protocol is not None and r['event']!='retire':protocol.append(dict(r))
        yield dict(event=r['event'],cycle=int(r['cycle']),order=int(r['order']),trap=int(r['trap']),
            pc=int(r['pc'],16),insn=int(r['insn'],16),rd=int(r['rd']),value=int(r['rd_wdata'],16),
            address=int(r['mem_addr'],16),rmask=int(r['mem_rmask'],16),wmask=int(r['mem_wmask'],16),wdata=int(r['mem_wdata'],16))

def protocol_gate(events,result,generic):
    expected=[r['insn'] for r in result['retired_offloads']]
    for event in ('cvx_req','arch_start'):
        require([int(r['insn'],16) for r in events if r['event']==event]==expected,
                'Exact original offload sequence '+event)
    require(generic['cvx_request_count']==generic['cvx_response_count']==
            generic['architecture_request_count']==generic['vector_retire_count']==len(expected) and
            generic['cvx_replay_count']==generic['arch_request_replay_count']==generic['cvx_exception_count']==0,
            'Exact transport counts/no replay/exception')
    allocations={}
    for r in events:
        if r['event']=='uop_alloc':
            index=int(r['order']);allocations[index]=allocations.get(index,0)+1
    for i,r in enumerate(result['retired_offloads']):
        require(not r['backend_required'] or allocations.get(i,0)>0,'Missing entire backend transaction')
    return dict(offloads=len(expected),backend_arches=len(allocations),no_replay=True)

def console_gate(text,name=NAME):
    require(name==NAME and not VETO.search(text),'Original scope/raw failure veto')
    lines=text.splitlines()
    for prefix,exact in [('RVV_FP_COMPARE_PASS',MARKER),('BOARD_CASE_PASS','BOARD_CASE_PASS '+NAME),
                        ('BOARD_REPLAY_PASS','BOARD_REPLAY_PASS'),('Core Test *** SUCCESS ***',common.SUCCESS)]:
        require([l for l in lines if l.startswith(prefix)]==[exact],'Missing/ambiguous marker '+prefix)
    require('$finish' in text,'Simulator completion')

def artifacts(result,case,ledger,spec,validator):
    require(result.status=='PASS' and result.name==NAME and not result.reason,'Exact case PASS')
    common.check_artifacts(result,case,ledger)
    for name in ('console.log','work/run.vcs.log'):console_gate((result.artifact_dir/name).read_text())
    path=result.artifact_dir/'commit_trace.csv'
    generic=validator(path)
    require(generic['cvx_exception_count']==0,'Full lifecycle validator')
    protocol=[]
    with path.open() as f:strict=source.audit(convert(csv.DictReader(f),protocol),spec)
    require(generic['retire_count']==strict['retired'],'Full trace counter agreement')
    binding=protocol_gate(protocol,strict,generic)
    return dict(strict=strict,generic=generic,protocol=binding,csv_sha256=sha(path),
        scope='Full682,349184 result bits,1364guards,682flags/vstarts; scalar RVFI, not direct vector payload')
