# Original Linux save_v_state CSR wait: static reconstruction

Status: STATIC_PATH_RECONSTRUCTED; historical root cause NOT established.
No Linux/board/simulation, symbol extraction rerun, RTL change or ledger edit.

## Evidence identity

Campaign C = `/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01`.
Original Image SHA256 `716aef49389b25a0a3f4deac47de0bb69467a10f1057041cecd0f0621fbbf285`.
Consume existing `original_image_kallsyms_recovery01/output01/pc_windows.txt`
(SHA256 `834060dae96a032fd75e0a482799adcdb72b7d7e31d75fdd5c4c4a7405ce2940`),
recovered map and result, not the mismatching local vmlinux.

Fresh `sha256sum` checks match C/rvv_stall_archived_rtl/manifest.json,
`source_hashes_before_integration`, for these actual files:

| File | SHA256 |
|---|---|
| C/rvv_verification_handoff02/deployed_rtl/ara_dispatcher.sv | 9af95c3eee6c63ecd9e60bf6d7c6474bdaaf1c5f96cef1bd653a6d51c6a2dd43 |
| mirror ara/hardware/src/ara_sequencer.sv | acf333e10d5b143cddb5bf037e55067bde4f3d644cb01ea4a8e82525c0f97454 |
| mirror ara/hardware/src/ara.sv | ab7af0adead3fbc3a78cba5029ab8fb3fe3066b6f954085dff27971343be1eac |
| mirror ara/hardware/src/vlsu/vldu.sv | 2661d1d5bd22ad95825c38be679622d7bae987deae743e12d1fadfe7c3b0af0d |
| mirror cva6/core/acc_dispatcher.sv | 6aa6fa74eaca4fd9981c4e9849bb4594df016ba4262d47295696aead82eeb117 |
| mirror ara/hardware/src/cva6_accel_first_pass_decoder.sv | 79dcb6c3c41b6ce0157f39b0f5d1ea42dcbc58a36b6f743b59b96b9d041594fc |

Mirror prefix is `/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/rtl/`.
This is archived manifest source binding, not a new bitstream readback proof.

## Original instruction boundary

All addresses below have prefix `ffffffff`.

```text
80013a00 ld a6,-1112(a5)
80013a04 nop
80013a08 li a5,1536
80013a0c csrs sstatus,a5
80013a10 lui a5,1
80013a12 addi a5,a5,-1152
80013a16 add a5,a5,a4           last-retired PC in all three scenes
80013a18 csrr a0,vstart         00802573; reported head PC, validity absent
80013a1c csrr a1,vtype
80013a20 csrr a2,vl
80013a24 sd a0,0(a5)
80013a26 sd a1,16(a5)
80013a28 sd a2,8(a5)
80013a2a sd a3,24(a5)
80013a2c nop
80013a30 csrr a3,vcsr
80013a34 lui a5,1
80013a36 add a5,a5,a4
80013a38 sd a3,-1128(a5)
80013a3c csrr a4,vlenb
```

These lie in recovered `save_v_state` starting 80013898. Later vector
configuration/stores occur at 80013a50/54/5a/60/66. They are younger than
the blocked boundary; there is no evidence they executed in this invocation.
Do not attribute the wait to those same-invocation younger vector stores.
Earlier state from previous instructions/invocations is not excluded.

The raw Image contains NOP/alternative sequences (including its function entry).
Runtime alternative-patched text was not captured. Thus this is a binary
instruction-window reconstruction, not proof of every executed branch or
GPR value. No matching DWARF/source-line assertion is made.

## Deployment-bound request and response path

1. First-pass decoder lines133-141 classifies vector CSR accesses as accelerator
   operations; vector enable checks also apply (line215). CSR 008 is not a
   scalar memory operation or a page-table request by itself.
2. CVA6 acc_dispatcher lines345-373 requires an instruction queue entry and
   commit authorization (`insn_ready_q`, or matching pending commit), with
   `!flush_unissued_instr_i`, before `acc_req_valid`. Lines278-299 pass through
   the ownership spill stage to Ara. A displayed head PC alone proves none of
   these handshakes. Its commit-entry `.valid` is a completion condition used
   by lines415-430, not a substitute for an independently captured head-present
   indication.
3. Ara dispatcher lines1196-1198 allows architectural decode in normal operation,
   eligible overlap state, WAIT_IDLE with `!ara_req_valid_o && ara_idle_i`, or
   WAIT_IDLE_FLUSH when LSU_FLUSH_DONE. Lines1659-1664 additionally require
   request-valid and response-ready. Backend not-ready sets `decode_blocked`;
   lines5871-5877 reset speculative outputs, suppressing the apparent response.
4. OpcodeSystem lines4624-4641 forces a WAIT_IDLE visit using **state_qq**, the
   previous state (registered at597), not simply current state. Once eligible,
   CSRRs VSTART lines4676-4679 returns `csr_vstart_q` directly, with
   `csr_vstart_d = csr_vstart_q | rs1`; x0 makes this a read. No CSR-specific
   multi-cycle arithmetic or DDR transaction is needed. All decode gates still
   apply; do not infer a fixed latency from this direct data path.
5. CVA6 acc_dispatcher lines384-396 directly forwards response ID/result/valid
   and exception; **response-ready is tied to 1**. Sustained backpressure from
   that endpoint is therefore not a supported explanation. Downstream
   scoreboard/ID/writeback/retirement loss remains a distinct unmeasured case.
6. Ara top lines275/368 connects dispatcher idle to sequencer idle. Sequencer
   line88 defines idle as `!(|vinsn_running_q)`; lines96-110 OR the PE running
   masks and register them. Line549 clears each PE's bits by its `vinsn_done`.
   DDR outstanding=0 is NOT this idle predicate.
7. A memory exception can set vstart and enter WAIT_IDLE_FLUSH (dispatcher
   1253-1255,4348-4354,4602-4604). Lines1237-1244 require idle BEFORE starting
   flush. The separate FSM (955-976) pulses flush, waits registered flush-done,
   then permits return. Sequencer1010-1030 can return address/exception response
   once address ACK and lane/mask acceptance conditions hold (plus optional
   store completion); that is not equivalent to every PE running bit cleared.

## Historical evidence and discrimination

Existing recovery08_12/41/76 `terminal_scene` snapshots have unchanged retired
count and trap count across advancing cycles, same last/head PCs, DDR outstanding
and errors zero, watch flags zero. Head validity, request handshake, dispatcher
state, PE ownership and flush state were not captured in those snapshot fields.

| Hypothesis | Supporting / limiting existing evidence | Falsifying observation |
|---|---|---|
| H0: CSR never reaches Ara (queue/authorization/flush hold) | Head address does not establish acceptance; CPU has these explicit gates | Matching 00802573 request appears at Ara with its ID |
| H1: older PE ownership keeps idle low, blocking CSR or pre-flush | Exact idle/flush dependency exists; preceding fault and DDR-zero are compatible, not proof | All PE bits zero with idle high throughout the stalled decode interval |
| H2: flush started but completion never returns | Explicit LSU_FLUSH_WAIT exists; no historical flush trace | No flush start, or observed DONE followed by decoded CSR |
| H3: backend-ready/decode or previous-state gate prevents response despite idle | `decode_blocked` and state_qq are real additional gates | Eligible state/history, backend-ready and same CSR request produce response |
| H4: CSR response reaches CPU but ID/writeback/retirement fails | Not ruled out by PC snapshots | No matching response at CPU; then failure is upstream instead |

An H1 circular wait is conditional: prove a remaining PE needs flush to finish
while dispatcher waits for its completion before flushing. The static dependency
alone does NOT establish that a PE actually requires flush in these episodes.
Do not select a mask-drain, FOF, or translation defect solely from later fixes.

Recovery12/76 last traps map to scalar usercopy stores, respectively
`fallback_scalar_usercopy_sum_enabled+0x66` (sd t3,48(a0)) and +0xb6
(sb a5,0(a0)); recovery41 last trap is user load PC10846. This rules out calling
all three *recorded last traps* the same vector instruction. It does not establish
trap-to-save invocation identity, nested-fault order, or the older pending owner.
Existing source-derived Sv39 passes do not close these original Linux episodes.

## Minimum discriminating historical signals

Use an existing trace if available, covering the last fault/response through
the first CSR wait, not just another final PC snapshot:

- CPU head presence/completion/FU/PC/transaction ID, commit ACK, exception event
  PC/cause/tval, accelerator queue head/empty, pending/ready bit for that ID,
  flush-unissued, spill valid/ready and instruction 00802573.
- Ara request-valid/ready/ID/instruction/rs1; response-valid/ID/result/exception.
  CPU response-ready is a constant, so need not spend a probe bit on it.
- Dispatcher state_q/state_qq, ara_req_valid_o/ara_req_ready_i, ara_idle_i;
  decode_blocked is derivable, not necessarily another probe.
- Sequencer PE-by-ID running masks plus PE done pulses and original owner ID/op;
  address ACK/exception and memory lane/mask acceptance for that owner. First
  identify the stuck PE; only then inspect its operand/mask/writeback counters.
- lsu_ex_state_q, flush-start/output, flush-done input/registered value.

Missing software context: runtime patched instruction bytes, task and saved
frame identity, exact trial/preceding sequence, page mapping/permissions and
exception-return timeline. These are required to claim the same Linux semantics,
not to decode the already recovered instructions.

## Safe next action

Static reconstruction is complete to the deployed accelerator boundary. First
look for already archived ILA/probe captures containing the above handshake and
ownership signals and their probe definitions. If absent, report historical
causality unresolved; do not manufacture a same-ABI reproducer from the passing
Sv39 tests. No new Linux run, short simulation, board access or RTL patch is
authorized or performed by this report.
