#!/usr/bin/env python3
"""Host-only lane-owner properties, including the repaired requester idle gate.

Requires node. The embedded checks preserve the previous inline owner checks,
replace the invalid ready-as-idle assumption, and bind that regression to the
real requester source. Assertion counts are not independent RTL test cases.
No EDA invocation, source modification, or output-file creation occurs here.
Run with: python3 -B verification/performance/resident_rvv/soc_admission/lane_owner_test.py
"""
import hashlib
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[4]
HOST_CHECKS = r"""
const fs=require('fs'), assert=require('assert'), crypto=require('crypto');
const read=p=>fs.readFileSync(p,'utf8');
const paths=['hardware/src/lane/lane.sv','hardware/src/lane/vector_fus_stage.sv',
             'hardware/src/lane/operand_requester.sv'];
const [lane,stage,requester]=paths.map(read), top=read('hardware/src/ara.sv');
const clean=s=>s.replace(/\/\*[\s\S]*?\*\/|\/\/[^\n]*/g,'');
const src=clean(lane);
function rhs(name){const m=src.match(new RegExp('assign\\s+'+name+'\\s*=\\s*([\\s\\S]*?);'));assert(m,'assign '+name);return m[1].replace(/1'b1/g,'1').replace(/1'b0/g,'0');}
function val(name,env){const expr=rhs(name);return Function(...Object.keys(env),'return ('+expr+');')(...Object.values(env));}
const common={lease:1,pv_owned_o:1,cmd_captured_q:1,started_q:1,release_seen_q:0,release_command:0,abort_command:0,commit_command:0,pv_acquire_i:1,upstream_empty:1,native_ldu_debt_q:0,private_ldu_debt_q:0,ldu_result_final_gnt:0,ctrl_cmd_ready:1,ctrl_result_valid:0,ctrl_done_valid:0,ctrl_done_error:0,ctrl_busy:1,pv_payload_seed_i:0,pv_payload_value_i:0,seed_payload:false,value_payload:false,ldu_result_req_i:1,ldu_result_gnt:1,VAKVPV:200,pe_req:{op:200,id:3},id_q:3};
let properties=0;function check(x,m){assert(x,m);properties++;}
function derived(e){e={...common,...e};e.pv_block_native=val('pv_block_native',e);e.mux_private=val('mux_private',e);e.payload_enable=val('payload_enable',e);e.commit_enable=val('commit_enable',e);e.ldu_result_req_mux=e.commit_enable&&e.ctrl_result_valid;return e;}

// This source-bound regression is new evidence; the old 2622 result missed it.
function bindRequesterIdle(laneText,requesterText){
 const l=clean(laneText), r=clean(requesterText);
 const normalize=s=>s.replace(/\s+/g,' ').trim();
 const a=r.indexOf('always_comb begin: operand_requester');
 const b=r.indexOf('end : operand_requester',a);
 assert(a>=0&&b>a,'real per-requester always_comb missing');
 const comb=r.slice(a,b);
 const ready=[...comb.matchAll(/operand_request_ready_o\[requester_index\]\s*=\s*([^;]+);/g)];
 assert.deepStrictEqual(ready.map(m=>normalize(m[1])),["1'b0","1'b1","1'b1"],
                        'ready is a valid-command acknowledgement, not an idle output');
 const named=(text,label)=>{
  const m=text.match(new RegExp('begin\\s*:\\s*'+label+'\\b([\\s\\S]*?)end\\s*:\\s*'+label+'\\b'));
  assert(m,'missing real requester block '+label);return m[1];
 };
 const idle=named(comb,'state_q_IDLE'), requesting=named(comb,'state_q_REQUESTING');
 assert(/IDLE\s*:\s*begin\s*:\s*state_q_IDLE/.test(comb),'real IDLE branch');
 assert(/REQUESTING\s*:\s*begin\s*:\s*state_q_REQUESTING/.test(comb),'real REQUESTING branch');
 const validGuard=/if\s*\(operand_request_valid_i\[requester_index\]\)\s*begin\s*:/;
 assert(validGuard.test(idle),'IDLE ready must be gated by real valid input');
 assert(validGuard.test(requesting),'finishing REQUESTING ready must be gated by real valid input');
 const idleAccept=named(idle,'op_req_valid'), nextAccept=named(requesting,'accept_a_new_inst');
 const high=/operand_request_ready_o\[requester_index\]\s*=\s*1'b1;/g;
 assert.equal((idle.match(high)||[]).length,1,'unique IDLE ready assignment');
 assert.equal((idleAccept.match(high)||[]).length,1,'IDLE ready assignment inside valid guard');
 assert.equal((requesting.match(high)||[]).length,1,'unique REQUESTING ready assignment');
 assert.equal((nextAccept.match(high)||[]).length,1,'REQUESTING ready assignment inside valid guard');
 assert(/if\s*\(operand_queue_ready_i\[requester_index\]\)\s*begin\s*:\s*operand_queue_ready/.test(requesting),
        'real finish path requires operand queue ready');
 assert(/if\s*\(requester_metadata_d\[requester_index\]\.len\s*==\s*'0\)\s*begin\s*:\s*finish_request/.test(requesting),
        'real finish path requires zero remaining length');
 assert(named(named(requesting,'operand_queue_ready'),'finish_request').includes(nextAccept),
        'next command acknowledgement belongs to the queue-ready finish path');
 assert(comb.indexOf(ready[0][0])<comb.indexOf('case (state_q[requester_index])'),
        'ready defaults low before the actual state cases');
 const idleAssignments=[...comb.matchAll(/operand_request_idle_o\[requester_index\]\s*=\s*([^;]+);/g)];
 assert.equal(idleAssignments.length,1,'one unconditional current-state idle observation per requester');
 const idleExpr=normalize(idleAssignments[0][1]);
 assert.equal(idleExpr,'state_q[requester_index] == IDLE','idle must observe state_q, not ready/state_d');
 assert(comb.indexOf(idleAssignments[0][0])<comb.indexOf('case (state_q[requester_index])'),
        'idle observation must not be inside a valid-command/state branch');
 assert(/output\s+logic\s*\[NrOperandQueues-1:0\]\s+operand_request_idle_o\b/.test(r),'idle output vector');
 assert(/logic\s*\[NrOperandQueues-1:0\]\s+operand_request_idle\s*;/.test(l),'lane idle vector');
 assert(/\.operand_request_idle_o\s*\(operand_request_idle\s*\)/.test(l),'lane/requester idle connection');
 const term=l.match(/upstream_empty\s*&=\s*([^;]+);/);
 assert(term,'real upstream per-queue predicate');
 assert.equal(normalize(term[1]),
  '!operand_request_valid[q] && operand_request_idle[q] && !operand_issued[q] && !vrf_operand_valid[q] && !operand_queue_input_valid[q] && !operand_queue_cmd_valid[q]',
  'drain predicate must use true idle and keep every pending/issued/return/cmd check');
 const evalTerm=(expression,signals)=>Function(...Object.keys(signals),
  'return !!('+expression.replace(/\[q\]/g,'')+');')(...Object.values(signals));
 return {
  idle:state=>Function('state','IDLE','return ('+idleExpr.replace('state_q[requester_index]','state')+');')(state,0),
  // These guards and literal assignments are established from the real blocks above.
  ready:(state,valid,queueReady,finish)=>state===0?!!valid:!!(queueReady&&finish&&valid),
  drained:signals=>evalTerm(term[1],signals),
  oldDrained:signals=>evalTerm(term[1].replace('operand_request_idle[q]','operand_request_ready[q]'),signals)
 };
}
const regressionStart=properties, idleBinding=bindRequesterIdle(lane,requester);
const quiet={operand_request_valid:0,operand_request_idle:idleBinding.idle(0),
             operand_request_ready:idleBinding.ready(0,0,1,0),operand_issued:0,
             vrf_operand_valid:0,operand_queue_input_valid:0,operand_queue_cmd_valid:0};
check(quiet.operand_request_ready===false&&quiet.operand_request_idle===true,'real idle-without-valid has ready=0, idle=1');
check(!idleBinding.oldDrained(quiet),'reproduce original permanent-Acquire predicate');
check(idleBinding.drained(quiet),'repaired predicate admits truly idle requester');
for(const state of [0,1])for(const valid of [0,1])for(const queueReady of [0,1])for(const finish of [0,1])for(let busy=0;busy<16;busy++){
 const signals={...quiet,operand_request_valid:valid,operand_request_idle:idleBinding.idle(state),
  operand_request_ready:idleBinding.ready(state,valid,queueReady,finish),
  operand_issued:busy&1,vrf_operand_valid:busy&2,operand_queue_input_valid:busy&4,operand_queue_cmd_valid:busy&8};
 check(idleBinding.drained(signals)===(state===0&&!valid&&busy===0),'real current-state drain predicate');
 if(state===1&&finish&&!valid)check(!signals.operand_request_idle,'finishing state_d=IDLE is not current state_q=IDLE');
}
for(const [owner,oldText,newText] of [
 ['lane','!operand_request_valid[q] && operand_request_idle[q]','!operand_request_valid[q] && operand_request_ready[q]'],
 ['lane','.operand_request_idle_o   (operand_request_idle    )','.operand_request_idle_o   (operand_request_ready   )'],
 ['lane','!operand_issued[q] && !vrf_operand_valid[q]','!vrf_operand_valid[q]'],
 ['requester','operand_request_idle_o[requester_index] = state_q[requester_index] == IDLE;',
              'operand_request_idle_o[requester_index] = state_d[requester_index] == IDLE;'],
 ['requester','operand_request_idle_o[requester_index] = state_q[requester_index] == IDLE;',
              'operand_request_idle_o[requester_index] = operand_request_ready_o[requester_index];'],
 ['requester',"operand_request_ready_o[requester_index] = 1'b0;","operand_request_ready_o[requester_index] = 1'b1;"]]){
 const text=owner==='lane'?lane:requester;assert(text.includes(oldText),'mutation target');
 assert.throws(()=>bindRequesterIdle(owner==='lane'?text.replace(oldText,newText):lane,
                                    owner==='requester'?text.replace(oldText,newText):requester));
 check(true,'reject requester-idle regression mutation');
}
const idleRegressionAssertions=properties-regressionStart;
console.log('PROPERTY_GROUP requester_idle_fix assertions='+idleRegressionAssertions+
            ' source_bound=true old_2622_result_is_not_fix_evidence=true');

// Registered LDU path, not a fall-through or latency assumption.
const reg=read('hardware/deps/common_cells/src/stream_register.sv'), macros=read('hardware/deps/common_cells/include/common_cells/registers.svh');
const ldu=requester.slice(requester.indexOf('stream_register #(.T(stream_register_payload_t)) i_ldu_stream_register'),requester.indexOf('// Slide unit',requester.indexOf('i_ldu_stream_register')));
check(/\.valid_i\s*\(ldu_result_req_i\s*\)/.test(ldu)&&/\.valid_o\s*\(ldu_result_req\s*\)/.test(ldu),'registered LDU wiring');
check(/`FFLARNC\(valid_o,\s*valid_i,\s*ready_o/.test(reg)&&/`define FFLARNC\([\s\S]*?always_ff\s*@\(posedge/.test(macros),'registered valid, including actual macro');
check(requester.includes('assign ldu_result_final_gnt_o   = ldu_result_gnt;'),'real final source');
// Actual combinational debt equations against the one-entry physical register.
for(const pending of ['', 'native','private'])for(const lease of [0,1])for(const owned of [0,1])for(const commit of [0,1])for(const req of [0,1])for(const result of [0,1])for(const arb of [0,1]){
 if(pending==='native'&&owned)continue;
 const final=!!pending&&!!arb, ready=!pending||final;
 const e=derived({lease,pv_owned_o:owned,commit_command:commit,ldu_result_req_i:req,ctrl_result_valid:result,native_ldu_debt_q:Number(pending==='native'),private_ldu_debt_q:Number(pending==='private'),ldu_result_final_gnt:final,ldu_result_gnt:ready});
 const na=!!val('native_accept',e), nf=!!val('native_final',e), pa=!!val('private_accept',e), pf=!!val('private_final',e);
 check(!(na&&pa),'no shared accept');check(!(nf&&pf),'no shared final');
 check(nf===(final&&pending==='native')&&pf===(final&&pending==='private'),'final ownership');
 const n=e.native_ldu_debt_q+Number(na)-Number(nf), p=e.private_ldu_debt_q+Number(pa)-Number(pf);
 check(n>=0&&p>=0&&n+p<=1,'debt conservation');
 const after=(na?'native':pa?'private':final?'':pending);
 check(n===Number(after==='native')&&p===Number(after==='private'),'physical slot/accounting equality');
 if(e.lease&&!commit)check(!pa&&!e.ldu_result_req_mux,'payload never writes VRF');
 if(pending==='native'&&lease&&final)check(!pf,'old native final never credited to PV');
}
// Acquire cannot use a guessed delay or ignore any of its actual drain gates.
const acquire=derived({started_q:0,pv_owned_o:0,ctrl_busy:0});
check(!!val('pv_fpu_acquire',acquire),'clean acquire');
for(const patch of [{lease:0},{cmd_captured_q:0},{started_q:1},{release_seen_q:1},{release_command:1},{abort_command:1},{pv_acquire_i:0},{pv_acquire_i:'X'},{upstream_empty:0},{upstream_empty:'X'},{native_ldu_debt_q:1},{private_ldu_debt_q:1},{ldu_result_final_gnt:1}])check(!val('pv_fpu_acquire',{...acquire,...patch}),'blocked acquire '+JSON.stringify(patch));
const watched=src.match(/if \(q inside \{([^}]+)\}\)/)[1];
check(!/\bStA\b/.test(watched)&&['MulFPUA','MulFPUB','MulFPUC','MaskM','SlideAddrGenA'].every(q=>watched.includes(q)),'upstream drain excludes new StA');
for(const name of ['vfu_operation_valid','vfu_operation_valid_q','operand_request_valid','operand_request_idle','operand_issued','vrf_operand_valid','operand_queue_input_valid','operand_queue_cmd_valid'])check(src.includes(name),'drain '+name);
// Same-ID replay is allowed; a new command cannot overwrite retained metadata.
for(const lease of [0,1])for(const owned of [0,1])for(const captured of [0,1])for(const op of [0,200])for(const id of [3,4]){
 const e=derived({lease,pv_owned_o:owned,cmd_captured_q:captured,pe_req:{op,id}});
 check(!!val('pv_pe_req_allowed',e)===(!e.pv_block_native||(op===200&&(!captured||id===3))),'PE command admission');
}
check(/else if \(lease_seen_q && !lease && !pv_owned_o && !ctrl_busy &&\s*private_ldu_debt_q == 0\)/.test(src),'captured before lease is not cleared by idle');
// Abort/payload selector unknowns cannot produce architectural acceptance.
for(const seed of [0,1,'X'])for(const value of [0,1,'X']){
 const e=derived({pv_payload_seed_i:seed,pv_payload_value_i:value,seed_payload:seed===1,value_payload:value===1});
 check(!e.ldu_result_req_mux,'noncommit no VRF request');
 if(seed==='X'||(seed===0&&value==='X'))check(!e.payload_enable,'unknown selector blocks publication');
}
for(const done of [0,1])for(const debt of [0,1])for(const lease of [0,1])check(!!val('pv_done_valid_o',derived({lease,ctrl_done_valid:done,private_ldu_debt_q:debt}))===!!(lease&&done&&!debt),'done waits real final');
check(lane.includes("2'd0: elements = 6'd16;")&&lane.includes("2'd1: elements = 6'd32;")&&lane.includes("2'd2: elements = 6'd24;"),'D mapping');
check(lane.includes(".cmd_tokens_i({1'b0, control_q[5:0]} + 7'd1)"),'T64 widening');
check(lane.includes("vaddr_t'(vaddr(vd_q, NrLanes, VLEN)) + vaddr_t'(result_slot)"),'slot already has head stride');
// Bounded arithmetic properties of the fixed shape contract, not new RTL cases.
for(const elements of [16,24,32])for(const heads of [1,2])for(let tokens=1;tokens<=64;tokens++){
 const words=Math.ceil(elements/4), expected=words*heads*tokens,writes=words*heads;
 check(expected<=1024&&writes<=16,'bounded work');
 for(const issued of [0,1,expected]){const returned=issued;check(returned===issued,'cancel drains accepted work');}
}
function header(s){return s.slice(0,s.indexOf('\n  );'));}
function instance(s,name){const i=s.indexOf(' '+name+' (');assert(i>=0,name);return s.slice(i,s.indexOf('\n  );',i)+6);}
for(const [body,decl] of [[instance(lane,'i_vfus'),header(stage)],[instance(stage,'i_vmfpu'),header(read('hardware/src/lane/vmfpu.sv'))],[instance(lane,'i_resident_pv'),header(read('hardware/src/lane/akv_resident_pv_lane.sv'))]]){
 const ports=[...body.matchAll(/\.([A-Za-z_]\w*)\s*(?:\(|[,\n])/g)].map(m=>m[1]);check(ports.length===new Set(ports).size,'unique named ports');for(const p of ports)check(new RegExp('\\b'+p+'\\b').test(decl),'declared port '+p);
}
const pvPorts=[...header(lane).matchAll(/\b(pv_\w+_[io])\b/g)].map(m=>m[1]);
for(const p of pvPorts)check(new RegExp('\\.'+p+'\\s*\\(').test(top),'top connects '+p);
for(const p of ['lease','acquire','start','abort','release','commit','payload_seed','payload_value','done_ready'])check(new RegExp('input\\s+logic\\s+pv_'+p+'_i\\s*=\\s*1\'b0').test(header(lane)),'default '+p);
const off=lane.slice(lane.indexOf('end else begin : gen_no_resident_pv'));
for(const field of ['req','id','addr','wdata','be'])check(off.includes('assign ldu_result_'+field+'_mux = ldu_result_'+field+'_i;'),'disabled native LDU '+field);
check(off.includes("assign pv_pe_req_allowed = 1'b1;")&&off.includes("assign pv_ready_o = 1'b0;"),'disabled native PE path');
const synth=lane.replace(/\/\/ synthesis translate_off[\s\S]*?\/\/ synthesis translate_on/g,'');check(!synth.includes('perf_')&&!synth.includes('RESIDENT_PV_LANE'),'all perf probes sim-only');
check(lane.includes('if (pv_fpu_valid && pv_fpu_ready) perf_issued_q')&&lane.includes('if (pv_fpu_result_valid && pv_fpu_result_ready) perf_returned_q')&&lane.includes('if (private_accept) perf_writes_q'),'counters use handshakes');
check(lane.includes('if (!pv_done_error_o) begin')&&lane.includes('perf_active_q && perf_returned_q == perf_issued_q'),'cancel does not require full issue');
for(const path of paths)console.log(crypto.createHash('sha256').update(read(path)).digest('hex')+'  '+path);
console.log('PASS host_property_assertions='+properties+' requester_idle_regression_assertions='+idleRegressionAssertions+
            ' assertion_counts_are_not_independent_cases=true rtl_execution=false eda_invoked=false');
"""


def main():
    print("SCRIPT_SHA256 " + hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), flush=True)
    return subprocess.run(["node"], input=HOST_CHECKS, text=True, cwd=ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())
