"""One closed CSV pass: unchanged six-event transport plus exact SoC source."""
from collections import Counter
import csv
import sys
from scope import *
from specification import specification,model,owner_contract
from strict import Strict

sys.path.insert(0,str(G/'gather_repair05'))
import regression as common
transport=load('unboxed17920_lossless_transport',G/'fp_comparison_original/fp_alias50_terminal_eventcheck01/observer.py')
VETO=__import__('re').compile(common.BAD.pattern+r'|RVV_FP_COMPARE_(?:DETAIL|FAIL|CAPACITY_FAIL)',__import__('re').I)

def console_gate(text):
    require(not VETO.search(text),'Raw original failure veto')
    lines=text.splitlines()
    for prefix,exact in [('BOARD_CASE_BEGIN','BOARD_CASE_BEGIN '+NAME),('RVV_FP_COMPARE_PASS',MARKER),
                         ('BOARD_CASE_PASS','BOARD_CASE_PASS '+NAME),('BOARD_REPLAY_PASS','BOARD_REPLAY_PASS'),
                         ('Core Test *** SUCCESS ***',common.SUCCESS)]:
        require([x for x in lines if x.startswith(prefix)]==[exact],'Exact console '+prefix)
    require('$finish' in text,'Actual simulator finish')

class Owners(transport.Observer):
    def __init__(self,protocol):
        super().__init__(protocol)
        self.alloc=Counter();self.done=Counter()
    def observe(self,row):
        super().observe(row)
        if row['event']=='uop_alloc': self.alloc[int(row['order'])]+=1
        if row['event']=='uop_done': self.done[int(row['order'])]+=1
    def coverage(self,ledger):
        require([r['insn'] for r in ledger]==self.retvec,'All actual retired offload instructions')
        index=0;covered=[];replays=[]
        for order,insn in enumerate(self.arch):
            if index<len(ledger) and insn==ledger[index]['insn']:
                item=dict(ledger[index],arch_order=order,alloc=self.alloc[order],done=self.done[order])
                require(item['alloc']==item['done'],'Every owner alloc/done balance')
                if item['required']: require(item['alloc']>0,'Missing necessary owner '+repr(item))
                if item['kind']=='configuration': require(item['alloc']==0,'Configuration backend data owner')
                covered.append(item);index+=1
            else:
                csr,funct,rs,rd=insn>>20,(insn>>12)&7,(insn>>15)&31,(insn>>7)&31
                harmless=(insn&127==0x73 and funct in (2,3) and rs==0 and csr in (8,9,10,15,0xc20,0xc21,0xc22)
                          and (rd==0 or order>0 and insn==self.arch[order-1]))
                require(harmless and self.alloc[order]==self.done[order]==0,'Only generic-qualified side-effect-free CSR replay')
                replays.append(order)
        require(index==len(ledger),'Missing architectural transaction')
        return covered,replays
    def full_coverage(self,ledger,spec,gold):
        covered,replays=self.coverage(ledger)
        actual=[(x['call'],x['helper_index'],x['kind'],x['required']) for x in covered if x['kind']!='configuration']
        from specification import helper_owner
        expected=[]
        for call,g in enumerate(gold):
            for i in range(len(spec['helpers'][g['op']])):
                q=helper_owner(spec,g['op'],i,g)
                if q and q[0]!='configuration': expected.append((call,i,*q))
        require(actual==expected,'All185 instruction types, per-call exact memory/target owner ledger')
        return dict(status='EVERY_NECESSARY_OWNER_COMPLETED',contract=owner_contract(),
                    total_actual_alloc=sum(self.alloc.values()),total_actual_done=sum(self.done.values()),
                    harmless_CSR_replays=replays,owner_ledger=covered)

def audit(path,spec,abort):
    common.image_context(IMAGE)
    protocol=sys.modules['ara_verify.trace']
    state=Strict(spec);observer=Owners(protocol)
    try:
        with Path(path).open(newline='') as f:
            for row in observer.rows(csv.DictReader(f)):
                if state.rows%4096==0: require(not abort.is_set(),'Sticky abort during closed audit')
                state.consume(row)
        generic=observer.finish()
        for k in ('cvx_request_count','cvx_response_count','architecture_request_count','backend_uop_alloc_count','backend_uop_done_count'):
            require(generic[k]>0,'Missing event family '+k)
        strict=state.finish();owners=observer.full_coverage(state.offloads,spec,state.gold)
        require((strict['rows'],strict['retired'],strict['last_cycle'])==
                (generic['rows'],generic['retire_count'],generic['last_cycle']),'Full strict/generic counts agree')
        require(not abort.is_set(),'Abort before audit publication')
        return dict(strict=strict,generic=generic,owners=owners,csv_sha256=sha(path),closed_semantic_passes=1)
    except BaseException as e:
        raise ValueError(str(e)+' context='+repr(state.current_context)) from e

def artifacts(result,case,ledger,spec,abort):
    require(result.status=='PASS' and type(result.returncode)is int and result.returncode==0 and not abort.is_set(),'Actual numeric child0')
    # Historical provenance name must not become +TESTCASE runtime identity.
    common.check_artifacts(result,dict(case,original_name=case['id']),ledger)
    for p in ('console.log','work/run.vcs.log'): console_gate((result.artifact_dir/p).read_text())
    return audit(result.artifact_dir/'commit_trace.csv',spec,abort)
