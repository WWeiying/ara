# Masked Load Drain: Independent Measurement Check

No blocker in the seven measured first-fault boundaries. Reviewed only existing `masked_translation/multiword_fault_liveness01/successor01/measurement01`; no new simulation/test/build or producer edits.

All35 frozen pins match. All pinned hardware files equal frozen M6 except `hardware/src/vlsu/vldu.sv`, whose candidate SHA is `92f9ebbeb136cd3ff11ae1a8ea92ce31b3aac077ae0667f79d82e919a3603401` (baseline `4e46a4733530b15edb05bbaded651899511af930e2caffe77b7482528c4fc8ab`). The diff adds masked DRAIN_EXCEPTION_MASK after final grants and moves owner-matched mask consumption out of HANDLE_EXCEPTION; other RTL is unchanged.

Pins JSON SHA: `186f0ef825a408fcff06e6c160c3681b904764dd5bbabb64317a0c142a69719e`.
Measurement result SHA: `0a7a762e35f453bffbf4ffa7310daa9aa5a4f4e99aee540354bec30b556b3b68`.

Each case has actual recorded integer returncode0, exact private command, one PASS marker and no assertion/fatal error. The frozen runner stores subprocess.run's returncode. All seven complete CSVs contain100 data rows plus header, cycles1..100. Sampling is on posedge before the RTL nonblocking updates, so `ld_mask_pop` denotes the handshake at that edge and `ld_done` is the observed registered response.

| VL | Words (W=4) | Local Pop Cycles | Last Pop | Load Done/Response | Global Idle |
| --- | --- | --- | --- | --- | --- |
| 1 | 1 | 14 | 14 | 16 | 17 |
| 4 | 1 | 14 | 14 | 16 | 17 |
| 5 | 2 | 14,15 | 15 | 17 | 18 |
| 8 | 2 | 14,15 | 15 | 17 | 18 |
| 9 | 3 | 14,15,16 | 16 | 18 | 19 |
| 12 | 3 | 14,15,16 | 16 | 18 | 19 |
| 16 | 4 | 14,15,16,17 | 17 | 19 | 20 |

Every acceptance/pop sequence covers first-element0,4,... in order, and its final first+4>=VL. Every pop occurs in drain state4 with issue_valid1 and a valid local mask. The frozen TB checks local owner against the accepted VID at every pop; the CSV lacks a separate local-owner column, so owner proof also uses that assertion and clean numeric0 log. Done is strictly after the last pop, with local valid0, spill A/B0 and MASKU commit0. All cycle80..100 rows have running0/idle1, issue_valid0/exception state0, MASKU commit/queue0 and both upstream/local mask-valid vectors0. One MMU response, AddrGen acknowledgement, MASKU done and sequencer response occur per case.

Scope: real AddrGen/VLDU/MASKU/sequencer, e64m4/vm0/vstart0/stride0, active first-element page fault cause13, one modeled packed predicate beat and modeled MMU. No forced internal signals. The TB holds LSU flush0; `flush_eligible_model` is not a real dispatcher flush observation. This is not a full SoC/Linux or prefix-data oracle acceptance.

Normal no-fault cycle equality, nonempty partial-prefix/final-grant behavior, restart/owner succession and VSTU remain unmeasured here; Aquinas owns the next normal/prefix checks. These seven PASS cases must not be generalized to those boundaries.
