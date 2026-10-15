# Whole-Store Reshuffle Context Review

Independent static review, no RTL edit or new simulation. Reviewed dispatcher:
`8ea44e035165be966bc80cea3abc31a8af85fde3e46470116854480a92171ab2`.
Line references below refer to `hardware/src/ara_dispatcher.sv` at that identity.

## Evidence Boundary

Parent reports final04 `extension_e32_m4_vf4` trial22 reaches VL96 and loops on
repair uops following vzext.vf4 and vs4r.v v24. Tesla owns the dynamic diagnosis.
This review has not independently decoded that trace and does not attribute
the observed loop to the blocked-decode tail as an established root cause.

The prepared source is
`matrix01/prepared/extension_e32_m4_vf4/original/scenario.S`: the overlapping
variants load the narrow source into v27, set e32/m4, execute vzext.vf4 v24,v27,
read vstart, then store with vs4r.v v24. `case.c` is a same-source derivative
with direct trials and bytewise oracle, not a claim of full original Linux
execution. Trial22/VL96 identification here comes from the parent's evidence.

## Confirmed Static Facts

At VLEN1024, e32 VL96 covers 384 bytes: v24-v26. Leaving the complete tail
register v27 in its old EW8 layout is consistent with active-register-only
metadata updates (:5944). Mixed EEW after the extension is not by itself an
extension correctness defect.

Whole-register store decoding (:4579-4647) replaces the CSR-derived geometry:

| Field | Decoded vs4r.v v24 request | ara_req_idle at CSR e32/m4 VL96, start0 |
| --- | --- | --- |
| op | VSE | default VADD |
| vs1 | 24 | 0 |
| eew_vs1 / vsew | EW8 / EW8 | EW32 / EW32 |
| vl | 512 bytes | 96 elements |
| emul | M4 | M4 |
| active register count / limit | 4 / 3 | 3 / 2 |

`ara_req_idle` is copied before architectural decode (:1202-1227). It is an
idle interface payload, not a saved whole-store request. `is_same_eew`
(:6083-6112) checks the decoded source group; the store layout check
(:5358-5370) legitimately requests source normalization for a mixed group.

## Latent Context Risk, Not Proven Loop Cause

The blocked tail (:5921-5927) calls `init_decoder_outputs()`, sets
NORMAL_OPERATION, then calls `prepare_reshuffle(ara_req_idle)` if a pending
reshuffle remains. Initialization restores `reshuffle_req_d = reshuffle_req_q`
(:1014), resets `is_vstore`/segment classification and working counters, and
retains the current buffered source/old/new EEW. It does not retain the
speculative decoded store geometry.

For an existing pending vs1 request (`reshuffle_req_q == 3'b100`), the helper
(:1140-1198) would replace the saved target with EW32, register limit with2,
and source base with0 instead of EW8/3/v24. Current `vs_buffer` and
`eew_new_buffer` remain from the old context, so the current register and
subsequent-register target/extent can disagree. This is a concrete conditional
context-integrity risk. Nonzero vstart and a CSR LMUL different from nf-derived
whole-store EMUL introduce further mismatches.

However, this branch requires `decode_blocked && |reshuffle_req_q`; a newly
computed speculative reshuffle alone is insufficient because initialization
restores q. The ordinary path calls `prepare_reshuffle(ara_req)` (:5802) with
correct whole-store geometry. RESHUFFLE is outside `arch_decode`, advances a
bounded register counter, clears the final pending bit and enters WAIT_IDLE
(:1572-1650). Under that path the mixed group should converge, not loop.
This review has not established reachability of the corrupting blocked-tail
call for the reported trial22 whole store. That distinction is essential.

## Discriminating Evidence for Tesla

At the first unexpected repeat, record `state_q`, `decode_blocked`,
`reshuffle_req_q/d`, `rs_lmul_cnt_q/d`, `rs_lmul_cnt_limit_q/d`,
`reshuffle_eew_vs1_q/d`, `reshuffle_vs1_base_q/d`, `vs_buffer_q/d`,
`eew_new_buffer_q/d`, and `eew_q[24:27]`, with the decoded request's
SEW/VL/EMUL and real backend handshakes.

- If `decode_blocked && |reshuffle_req_q` never occurs, exclude this tail call
  as the cause of that captured loop.
- If it occurs with a whole-store pending context and changes EW8 to EW32 or
  limit3 to2, it directly supports the context-corruption hypothesis. Follow
  subsequent accepted repairs and metadata to establish the actual recurrence.
- Separate a held uop from repeatedly accepted uops; a repeated display alone
  does not prove repeated execution.

Any repair should preserve a coherent registered repair context on blocked
decode. Blindly substituting an unaccepted speculative request is not reviewed
as safe. Expanding the extension's active interval to rewrite v27 is also not
a justified fix for a whole-store context problem. No implementation is made
or approved by this note.
