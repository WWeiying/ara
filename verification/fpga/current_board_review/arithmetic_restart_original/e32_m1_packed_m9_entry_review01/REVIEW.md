# e32/m1 Full5985 M9 Exact Entry

Verdict: **NO_BLOCKER_ENTRY_REVIEW**. Under the parent's explicit conditional
authorization, Aquinas is the sole launcher of this exact prepared plan. No
additional approval round is required; live resource admission remains mandatory.
This review neither launches a process nor claims a DUT result.

Producer: `full_e32_m1_packed_vcs_m9_plan01/prepared01/`.

| Artifact | SHA256 |
|---|---|
| plan.json | `fca9ceb8502f806b939e473030e3cbf3c92d00d55fca04d2087bc948c260ae2c` |
| ready.json | `5207d4f6a37d962eded6cd242037ba7bf0d9b3d927bd816f21c579a11b937647` |
| dryrun.json | `dca3d2ee0a7bc5322cb214fe0d8445a81cec130c858f1d32f609d2152747a8f5` |
| host_reconciled.json | `98bdd6aa78cf00bb5c73fcb18152f929344b3c59ea3a8e8cbf0096c048add5e4` |
| prepare_successor.py | `209bf2000f77976b3e71099b4044822448751772fd6b16c43e3dbd9d1a0c520b` |

## Exact Scope

Single `arithmetic_original_e32_m1_full5985_packed`, frozen M9 image.json
`48d9e4d2acb1fa239e05549fe695caad36af34c1f02aaffe041bb8261e302b5a`,
software02 SoC ELF
`8b6c67293ad57aff6ddeaf478aa4c94bd07d44421f3c6eb901378fe4cf23db5c`.
Reference READY `d1f70125ab071283390749323120204356e07da6a3a420f450e46c58e5859691`
already has independently accepted actual firmware2472244 and complete raw audit.
No reference raw or previous accepted CSV was reread by this entry review.

This is35 ops/full5985, not25 ops/4095:191520 results,11970 uint32 guards,
136B output/17 whole64-bit reads per call,101745 reads and77805 helper
instructions. Guard words remain0000005b. Original integer oracle and exact
640 FP table entries remain bound; no new fflags oracle is asserted.

## Checker and Host Gates

- SoC lifecycle explicitly binds actual SoC seed, FP, mask, init/read PCs; it
  does not use a universal offset from Spike. It enforces1890*64 fresh FP SW,
  even equal-valued writes;2205 mask groups each16 SD clear followed by exact
  original selected-bit SB phases; no si1/si2 reinitialization. Full136B init,
  result/guards, returned vstart, original call order/counters and scalar source
  GPR/address/byte-enable checks remain strict.
- Full helper PC membership/13-step windows and unexpected CSR/RVV rejection
  remain. Actual SoC opaque ABI/reset profile and CTRL0 exit are bound; no
  Spike tohost symbol is assumed. No shortened or partitioned original history.
- Independent derivation from the frozen ledger/target encodings yields29925
  compulsory memory owners +3762 required targets =33687 minimum. FP accounts
  for1170 required targets; op24 has117. Only the exact original VI2 opcode has
  the18 nonempty VL<=2 no-op exemptions. Generic observes all actual tokens,
  requires alloc/done pairing even for optional owners, and every necessary
  retired owner must have a pair. Minimum counts are not a filter on actual events.
- Host01 stays **FAIL/rc1**,33 tests,32 `ok` plus one exact regex mismatch;
  actual elapsed278.16455376008525s. Full5985 strict/generic/owner and actual ABI
  tests passed. The sole test expected `Deleted fresh`, but the unchanged checker
  correctly raised earlier `Complete output fresh/prior reads`.
- Host02 is a real6678-row short-prefix reconstruction: after only the first SD,
  shadow is filled with91 but remaining16 initialization writes are missing.
  Same helper entry is rejected with the exact earlier ValueError. Numeric0,
  1.377650988753885s, no timeout/retry/checker change/full-history replay.
  Composite gate verifies all33 original named outcomes, original rc1 and exact
  corrected-negative receipt/result. It does not rewrite or relabel Host01.

## Worker and Resource Gates

One job/reserved0, case10800s, worker12000s, direct systemd service13200s,
KillMode=control-group, Restart=no, no build/retry/FSDB. Numeric child outcome
is persisted before postcheck; strict plus lossless generic validation and raw
failure veto remain. First failure cancels; late abort or disk-plan/pin drift
prevents PASS. ExecStopPost preserves actual service exit and runs one bounded
metadata collector. Startup performs one pair of executable/private-ELF/cgroup,
CPU and CSV-size samples; no long polling is authorized.

Fresh run-time resource admission enforces24 live/reserved simv and32GiB
available memory; this review did not query live jobs or preclaim capacity.
Estimated7343.844s including20% margin is below10800, not a duration guarantee.
Dryrun names the exact private ELF/CSV/work directory and frozen executable.

Plan contains955 pins. Independently rehashed954 nonraw inputs including all
consumed worker/lifecycle/imports, actual ELF/image, Host receipts and correction
gate. The one accepted reference commits.log pin was compared with its completed
reference result rather than rereading raw. Verification completion `0badde`
returned numeric0 in2.81239866s. No Host/reference/build/DUT was rerun here.

No original Linux/board closure, aggregate shape increment, or DUT PASS is
claimed before terminal strict/generic/exit/collector acceptance.
