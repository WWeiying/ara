# Actual CVA6 dispatcher contract

For the actual-SoC Linux-source extraction test, see
[linux_vector_context.md](linux_vector_context.md): six S-mode context rounds,
6415 exact comparisons, first VCS run PASS in 156.905 seconds. Its scope is
separate from the dispatcher unit contract below and does not establish Linux boot.

Additional load-path boundary verification is documented separately in
[LOAD_CONTRACT_PLAN.md](LOAD_CONTRACT_PLAN.md) and
[LOAD_CONTRACT_MEASURED_20260922.md](LOAD_CONTRACT_MEASURED_20260922.md).
Its PASS is not a full-MMU, CPU retirement or Linux signoff.

The actual-MMU early PPN migration and directed tests are documented in
[MMU_EARLY_PPN_20261009.md](MMU_EARLY_PPN_20261009.md). That fixture injects
legal DTLB refills and checks the real MMU/TLB and load-unit NI classification;
it is separate from the modeled translation used by the load contract above.

This is a bounded unit-level interface experiment, not a full-core, Ara execution,
Linux, MMU, ISA, or architectural retirement test. No dependency is modified.
The optional PULP patch stays quarantined and no divider is compiled.

## Source and harness review (before simulation)

Inputs are the reviewed local `hardware/deps/cva6/core/acc_dispatcher.sv`, its
`cva6_fifo_v3`, common-cells `spill_register`/`spill_register_flushable` and
`counter`/`delta_counter`. The runner validates the registered CVA6 patch and
freezes these inputs before compiling. There is no dispatcher behavioral stub.

The configuration is the actual `cv64a6_imafdcv_sv39_config_pkg` processed by
`build_config_pkg`: RV64, eight scoreboard IDs, two commit ports, ASIC FIFO.
SoC address-map/PMP/FPU overrides are not needed by these contracts and are not
claimed tested. Six complete packed types are extracted unchanged from `cva6.sv`
parameter declarations; accelerator/MMU types use `ara/intf_typedef.svh`.
The extraction rejects anything other than the inspected flat packed structs.

Lifecycle reconstructed from sources:

1. `acc_valid_d` accepts non-exception ACCEL issue handshakes unless unissued
   flush is asserted. `acc_valid_q` pushes the corresponding execution payload
   one cycle later. Speculative memory counters increment at **issue**.
2. FIFO depth is three; issue is stalled at usage >= two to reserve pipeline
   space. Fall-through changes `empty`, not registered `usage`.
3. Commit eligibility means an unfinished ACCEL at port 0, or an unfinished
   ACCEL at port 1 behind a valid port 0 that is **acknowledged**. This is not
   architectural retirement of the accelerator instruction.
4. Only a matching pending ID or the head's previously recorded ready bit can
   authorize a request. A pop clears that ready bit. Flush clears both maps.
5. `queue_pop = internal_valid && internal_ready` transfers ownership to the
   two-entry, non-flushable spill. External valid/ready is a separate handshake.
   Speculative memory count decrements and dispatched count increments at pop,
   classified by the **queue head operation**, not current `fu_data_i`.
6. Responses forward ID/result/flags/exception. Only load/store completion pulses
   decrement dispatched memory counts. Flush cancels queue residents, not spill
   entries, accepted accelerator requests, or dispatched memory counts.
7. Scalar memory stalls depend on consistency mode; all five fence opcodes
   wait for speculative and dispatched memory regardless of that mode.
   HFENCE tests cover this enum-level stall predicate, not RVH execution.

The controller pairs `flush_ex` with `flush_unissued`; this harness tests that
legal pairing. Standalone unpaired execute flush is outside its contract.
The commit-ID mismatch stimulus deliberately presents a younger pending ID
behind a different FIFO head. It is an adversarial dispatcher boundary test,
not a claim that an in-order full core produces that ordering.

## Hypothesis / Evidence Matrix

All rows are prepared before compile. Capture is the complete bounded run,
maximum 256 active rising edges, sampled **pre-NBA**. State on the next row is
the previous edge's updated state. A unique issue sequence, PC, instruction,
and operands distinguish reused IDs; reset epoch is explicitly one.

| Candidate regression | Discriminating probes | Trigger / expected observation | Acceptance |
|---|---|---|---|
| Commit authorizes wrong head | commit ports/acks, selected ID, pending/ready q/d, FIFO head ID/token, internal valid/ready/pop | pending younger ID at commit, different head | no pop; own later commit releases head; younger recorded readiness then releases |
| Younger port escapes older stalled instruction | port0 valid/ack, port1 FU/valid/ID, commit, pop | hold older ack low for three edges, then raise | zero early pop, exactly one subsequent transfer |
| Flush retains speculative ID authorization | flush pair, queue usage/head, pending/ready q/d, acceptance, cancellation tokens | full spill, one ready and one pending queue entry, then reuse canceled ID | queue/maps/spec counts clear; canceled tokens never emerge; reuse waits for fresh commit |
| Flush destroys issued work / duplicates stalled payload | spill A/B occupancy, external payload/valid/ready/fire, dispatched counts, response | flush with two issued spill entries and ready low | stable payload through flush and three held cycles; both emerge once, in order |
| Queue-pop bookkeeping uses execution payload or external handshake | issue/ex/head kind and token, pop, internal/external handshakes, four pending counts, completions | stale unrelated STORE execution payload during LOAD pop; pop with downstream blocked; pop coincident with completion | counts follow acceptance/pop/completion independently, never wrap; simultaneous transfer/completion preserves count |
| Reused issued ID inherits readiness | per-token states, ID map, pending/ready, response | reuse a responded ID without commit | no transfer before own commit, no duplicate completion |
| Fence/scalar stalls miss speculative or spilled memory | issue FU/op, consistency mode, four counts, issue stall | each of five fences with load-spec/load-disp/store-spec/store-disp/empty, both modes | all 50 combinations; scalar load/store checks in same five states and both modes |
| Response confused with memory completion | external request fire, response valid/ID/result/flags, memory completion bits | response without memory complete, later complete coincident with next pop | response forwarded once; memory remains outstanding until completion |

## Acceptance Scoreboard

The Python checker replays every edge, independently tracking accepted tokens,
one-cycle upstream payload, ordered FIFO/spill ownership, per-ID authorization,
backend responses, and separately ordered memory completion. It checks all four
pending counts against transaction sets, not modulo arithmetic, and compares
current/next pending/ready maps. It also checks payload stability and exact
delivery, issue capacity, response forwarding, cancellation and final drain.
Coverage is derived from observed state/events, not test labels or a PASS string.
Missing/duplicate/truncated/unknown-valued evidence, simulator errors, nonzero
return status, missing coverage, or remaining work fails closed.

## Run

```sh
PYTHONDONTWRITEBYTECODE=1 python3 verification/cva6/run_contract.py \
  --output verification/out/cva6-contract-20260922
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=verification python3 -m unittest \
  verification/tests/test_cva6_contract.py -v
```

The output directory must not exist, must be inside this worktree's
`verification/out`, and may not resolve through a symlink. There is exactly one
compile command (180-second limit) and one simulator command (30-second limit),
with process-group cleanup on timeout. Each command and input hash is recorded.
No FSDB is required: the bounded JSONL trace is the complete focused probe set.
