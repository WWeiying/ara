# Final04 Trial22 Store Review

## Conclusion

The observed tail is a finite three-uop maintenance sequence followed by a
real store acceptance, not evidence of an infinite reshuffle loop. The
same-source row22 single passes its entire oracle on the unchanged final04
image in 59.7588 seconds. Its measured `decode_blocked && |reshuffle_req_q`
is never true, excluding the proposed default-request helper reentry in this
single. The original full matrix remains TIMEOUT, not PASS.

## Exact Inputs

- Original run: `/home/wangwy/fpga_runs/current_board_integration_final04/campaign/extension-matrix/tests/extension_e32_m4_vf4/`.
- Original pinned software: `matrix01/prepared/extension_e32_m4_vf4/`.
- Row22: `last_nonoverlapping_destination_element`, op2 unsigned vf4,
  e32/m4, VL96, vstart0, mask bytes ff, seed0; capacity128.
- Setup retains full destination initialization, source load into v27, mask
  load, and vtype setup. Target `vzext.vf4 v24,v27,v0.t` is opcode49b22c57 at
  PC0x80000462. Readback `vs4r.v v24,(a1)` is 62858c27 at PC0x8000046a.
- Final04 dispatcher SHA256:
  `8ea44e035165be966bc80cea3abc31a8af85fde3e46470116854480a92171ab2`.
- Original SoC ELF SHA256:
  `6601d146b1367f513a527b86eda75ce00f5b7cd4775c1250ab48ff3e2f0c2512`.

## Full-Program Evidence

`console.log` reaches trial22; trial0 through21 passed their complete checks,
because the driver breaks on any error before printing the next trial. There
are 22 retired readback stores. Trial21's function returned at cycle517145.
Trial22's extension retires538528; the last scalar retirement is its vstart
read at538529/PC0x80000466. The store begins538528, maintenance allocates at
538550/538551/538575 and completes538565/538573/538590. A fourth allocation and
`cvx_req` both occur538592. The store has not retired in the recorded trace.

Frozen `hardware/tb/ara_commit_monitor.sv:202` labels uops with their owning
architectural instruction, not backend opcode; repeated62858c27 is not by
itself repeated VSE execution. `cvx_req` at line293 requires actual front
valid/ready. The trace contains no end-of-timeout cycle heartbeat and its
explicit flush is watchdog-dependent, so last-event time is not a measured
600-second terminal simulation time. Earlier22 stores took3087-3162 cycles
from arch_start to retirement; only64 cycles of this store are recorded.

## Static Discriminator

In the frozen dispatcher, whole-store decode at4579 overrides VL512/EW8/M4;
source tag selection is at4638. Mixed layouts request normalization at5358.
Active destination tracking at5943 must leave inactive v27 alone: row22
writes v24-v26, while v27 retains its byte layout. Three conversions to EW8
before readback are therefore expected.

The blocked fallback at5921 calls `init_decoder_outputs()` before optionally
calling `prepare_reshuffle(ara_req_idle)`. The init restores pending from
`reshuffle_req_q`, not speculative decoded pending. If that q were nonzero,
the idle request at1203/1227 would use CSR VL96/EW32/M4 and source base0;
the helper at1140 would calculate limit2 instead of whole-store limit3 and
could mix those fields with retained v24/EW8 buffers. EMUL is4 in both views.
This is conditional risk, not measured reachability: RESHUFFLE clears pending
before WAIT_IDLE at1576-1621. Registered `ara_req_o` also holds while backend
ready is low, rather than being unconditionally overwritten by defaults.

## Measured Single

`trial22.py` copies pinned driver and assembly unchanged; only the case table
selects original row22. The local printed trial is0. All512 result bytes,
undisturbed tail and guards remain checked. Spike PASS precedes the one RTL
run. Prior rows are omitted, so this is supplementary evidence only.

- Software/reference: `trial22_software01/`; SoC ELF SHA256
  `ab284296af11b23be7cea78b671f4493276ee5da09bad4413b25bec4b12a7841`.
- Run: `trial22_final04_01/status.json`, `selected.fsdb`, `commit_trace.csv`.
- Final cycle analysis: `trial22_review02/finding.json` and `cycles.csv`.
- Existing ARA_DEBUG_RESHUFFLE filters out both target opcodes in this frozen
  image; bounded UCLI signals supply the actual evidence. Capture is bounded
  to0-40000ns; normal simulation finishes29233.5ns before that bound.
- First extension PC is0x800003a8; store PC is0x800003b0 in the derivative.
- VSLIDEDOWN129 accepts at19228(v24),19229(v25),19253(v26), each VL128/EW8.
  Maintenance limit remains3. No v27 conversion occurs.
- Front/posted-store acceptance19270 has `decode_blocked=1`, pending0,
  registered VSE137/VL512/oldEEW8 and all four source tags EW8. The conventional
  registered request valid/ready completes22354; do not mistake that later
  handshake for initial store allocation. Store done22354, retirement22356.
- No simultaneous blocked+pending state exists anywhere in the capture.
- All22 extension/store trace events over the144-cycle prefix match the full
  program after subtracting519322 cycles. This directly matches the finite
  maintenance sequence seen at the full-program timeout, not just its opcode.

## Authorized Successor Bound

`final04_successor01/plan.json` pins the image, shared runner hashes, original
three ELF hashes and the fixed command. No input or RTL changes, no rebuild,
no combined144 program, no automatic retry. Three concurrent original ELFs,
1200 seconds each, new output directory only.

| Original shape | Reference instructions | Recorded cycles / retires | Retired readbacks | Estimated total seconds |
| --- | ---: | ---: | ---: | ---: |
| e32m4vf4 | 384936 | 538592 / 355972 | 22 | 649-655 |
| e64m4vf4 | 366233 | 127062 / 86741 | 5 | 686-780 |
| e64m8vf8 | 552465 | 144582 / 89088 | 4 | 971-1004 |

Reference minstret is freshly measured on each unchanged Spike sibling ELF;
its runtime differs from the SoC UART wrapper. Estimates compare instruction
and24/readback progress fractions, not exact cross-runtime instruction equality.
1200 provides roughly20% margin over the largest estimate;900 would be below
that estimate. Original e32 has trial22 completion and trial23 still pending,
roughly30-40k additional cycles from the recorded acceptance boundary. Only a
new full-oracle terminal PASS can close each full matrix. Original TIMEOUT and
CANCELLED records remain untouched.
