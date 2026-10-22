# Current Gather Liveness Review

**Finding: none established in the current supported configuration.** In
particular, the two assignments to `vrgat_cmd_req_cnt_d` do not establish a
reachable current counter bug. No RTL edit, simulation, reference execution,
live-task query or proof framework was performed. This does not close the
11 archived stalls or turn source-prefix tests into original Linux acceptance.

## Counter Candidate And Reachability

References below are repository-relative. `hardware/include/ara_pkg.sv:163`
supports only `MaskuInsnQueueDepth=1`; at1093 `VrgatherOpQueueBufDepth=2`.
Consequently `lane/lane_sequencer.sv:258` blocks a data request at count1.
The two-bit count is not a count of outstanding result writes.

Define A as `masku_vrgat_req_ready_d && !masku_vrgat_req_q.no_data`, P as
`mask_b_cmd_pop_i`, and L as an accepted `is_last_req`. Before terminal reset,
the intended delta is A-P. If both A and P were one, lines264..268 would
incorrectly select `q-1` rather than q. **The missing step is reachability:**

| Current, nonterminal epoch | Inputs and actual next state |
| --- | --- |
| q0, new data accepted | A1/P0 -> q1; push one registered MaskB request |
| q1, response not yet popped | A0/P0 -> q1; following data request held |
| q1, registered command pop | A0/P1 -> q0; no simultaneous replacement |
| next cycle q0 | following data request may now be accepted |
| accepted last data or no-data | L1 -> IDLE/q0; terminal reset intentionally overrides accounting |

`operand_queue.sv:500..537` asserts cmd_pop only when a valid output is
accepted and its command's element count is exhausted. The ad-hoc command
has `vl=1`, conversionNone (`lane_sequencer.sv:1245`), so each real source
word has one pop. `operand_queues_stage.sv:279..309` connects this MaskB queue;
`lane.sv:264..265,305` registers its pop for one cycle before the sequencer.
While that pop is pending, count remains1 and still blocks A. A spill-input
handshake is not A: the lane spill may accept another request while the
internal data-command admission remains blocked. Counting that handshake
would falsely construct the proposed simultaneous event.

### Why An Old Pop Does Not Supply The Missing Event

- MaskB words enter non-bypassed per-lane spills before MASKU consumes them
  (`masku_operands.sv:136..149,262..267`). Thus the queue pop precedes the
  corresponding use; its registered notification is no later than the first
  cycle in which that newly received word can be used.
- Gather consumes every in-range index's source word, including masked and
  prestart destinations (`masku.sv:1483..1500,1566..1569`). An old instruction
  cannot publish its last result while an earlier required source is still
  missing. Commit additionally drains result writes/final grants
  (`masku.sv:1662..1741`). Instruction depth1 and broadcast admission prevent
  the next MASKU context from entering during this interval
  (`masku.sv:270,1112,1779`; `ara.sv:357`). Its first request then passes a
  request FIFO, lane spill and IDLE-to-REQUESTING transition.
- Last-data acceptance may clear q before that final word pops. This is
  deliberate: the FSM is IDLE, ignores the tail pop, and the above commit
  barrier prevents a new data epoch from borrowing that pop. A last no-data
  token may similarly end with an older in-range request outstanding; that
  older word must still be consumed before old result completion. An all-OOR
  instruction can leave a delayed terminal token, but has no data pop to
  inject. FIFO/spill ordering keeps that token before the next request.
- Ordinary old-vd consumers likewise consume their requested final word
  before completing. The scalar-extract exception is explicitly serialized:
  `ara_sequencer.sv:584..588` holds VMVXS/VFMVFS behind older vector work;
  its WAIT path consumes the scalar before issuing a successor (1060..1069).
  It cannot divert an older gather's MaskB tail or leave a scalar pop pending
  as the following gather reaches REQUESTING.

This rules out the proposed simultaneous A/P example for an otherwise legal,
uncorrupted current flow. A depth>=4 experiment or manually injecting a pop
without a matching eligible command would test another contract, not these
11 stalls. Existing `lane/lane_mask_tb.sv:71..74` ties both the pop and gather
request inputs inactive; it supplies no positive counter coverage. No such
test was repurposed into an impossible counter reproduction.

## Remaining Request-To-Done Path

- Arbitration: ad-hoc admission requires an empty registered MaskB request;
  the payload remains stable until requester acceptance (`lane_sequencer.sv:
  143..158,258,1245`). A simultaneously offered ordinary MASKU request is
  excluded in REQUESTING with valid ad-hoc data (363..369); a scalar request
  additionally requires IDLE/no spill entry (373). Bank grants, not valid
  alone, advance the actual source read (`operand_requester.sv:495..539`).
- Broadcast: each lane's FIFO-head acceptance is remembered, valid withdrawn
  only for that lane, and the shared head pops only after all have accepted
  (`masku.sv:623..640`). Subsequent requests cannot replace a stalled head.
- Predicate/OOR: each of VL scanned positions gets an index token; only
  in-range positions get data commands. Final OOR gets last+no_data
  (`masku.sv:1389..1428`). OOR processing explicitly needs no MaskB operand
  and does not consume a future in-range response. No-data bypasses count
  and requester capacity without allocating a command. All-off is not
  all-OOR: it still consumes the in-range source stream and emits BE0 writes.
- No predicate cycle: VALU forces gather preprocessing unmasked
  (`valu.sv:1300`); MASKU owns predicate consumption. AluA and MaskM start0
  and cover the full scan (`lane_sequencer.sv:968..987,1219..1230`), while
  destination BE preserves architectural vstart (`masku.sv:966..992`).
  VL0/vstart>=VL is suppressed by dispatcher5970; it does not owe a phantom
  last token. SEW/LMUL change lengths and VLMAX, not the count1 admission rule.
- Completion: BE0 still creates a write request and receives normal/final
  grants; there is no `|BE` completion gate (`operand_requester.sv:151..174,
  949..967`). MASKU decrements commit only for drained results and requires
  the final grants. This is separate from the earlier MaskB command credit.

No accepted request with a lost completion or self-sustaining wait cycle
was identified. This is a bounded static review, not a proof against arbitrary
external starvation: the VRF has high/low priority classes. It does not
establish a fixed completion latency under unbounded competing traffic.

## Existing Evidence And Identity

Reviewed measured prestart repair (`gather/README.md`, 12-case local result)
and M4 index-origin discrimination (`gather_original_review/gather_repair05/
focused01/MEASUREMENT.md`): start128 read the shifted index513 and produced0
instead of79; start0 control passed. Current AluA origin0 repair addresses
that measured numerical fault. Neither measurement proved the 11 stalls'
root cause. Existing no-data/broadcast handling was inspected, not newly run.

Fresh byte comparison found all12 inspected current files identical to
`/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources`:
ara_pkg, ara, ara_sequencer, ara_dispatcher, lane, lane_sequencer,
operand_requester, operand_queue, operand_queues_stage, valu, masku,
masku_operands. Key SHA256 values:

- lane_sequencer: `c11e2a871b91a7aaf940f9e4fb0ef79229a48a2a9b7e2db3fd1108e24dc01dcc`.
- ara_pkg: `49a4fd9879cad35c2c77241bd5114fb8d02ab520e833335fd916122854830971`.
- masku: `1bc71bbb732a842d59fdcc48d4f44aa79f830f2bb11444923b15910b8d875f3d`.
- ara_sequencer: `bf5d5a9be860340ca7a6f8d8c636da67cf9650f7b7b72d1123ce983e8eea5655`.

The full REQUESTING block, including the two count assignments and terminal
reset, is byte-identical to HEAD7d5d1829; both package depths are unchanged.
It is not an introduced M5/M6 credit repair regression.

Discriminator if a real stall occurs: sample pre-edge state/q, spilled
valid/ready/no_data/last/id, registered MaskB valid/ready/push, actual cmd_pop
and its registered copy, old/new MASKU issue/commit IDs, source-spill
valid/ready, index/request FIFO heads, and result req/gnt/final_gnt. A/P
overlap requires showing the matched prior command and how it survived the
commit boundary, not just asserting pop on a port. No new run is justified
by the assignment pattern alone.
