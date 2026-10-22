# Remaining Nine Reference Results

Status: **ALL9_EXECUTOR_AND_PIN_CHECK_PASS_PENDING_INDEPENDENT_REVIEW**.
All nine unique reference attempts terminated normally. No retry, bound change,
reference recompilation, DUT simulation, RTL build or live-job query occurred.
e16/mf4 and e32/m1 were excluded. Aquinas has received the frozen reference set
for independent source/raw review; this report does not claim that review done.

| Shape | Firmware retired to HTIF1 | Spike seconds | Raw bytes | Static upper |
| --- | ---: | ---: | ---: | ---: |
| e16/mf2 | 1,860,457 | 3.024 | 121,092,946 | 2,143,584 |
| e16/m1 | 1,864,672 | 3.024 | 121,188,707 | 2,171,488 |
| e16/m2 | 1,873,154 | 3.024 | 121,782,179 | 2,227,296 |
| e16/m4 | 1,890,113 | 3.024 | 122,968,795 | 2,338,912 |
| e16/m8 | 1,924,035 | 3.124 | 124,942,133 | 2,562,144 |
| e32/mf2 | 1,858,929 | 3.075 | 120,860,143 | 2,129,632 |
| e32/m2 | 1,865,194 | 3.025 | 121,402,821 | 2,171,488 |
| e32/m4 | 1,873,578 | 3.074 | 121,794,079 | 2,227,296 |
| e32/m8 | 1,890,347 | 3.077 | 122,976,565 | 2,338,912 |

Times are actual Spike execution, excluding offline raw extraction/pin checks;
not VCS performance estimates. Every reference used the authorized actual ISA
`rv64gcv_zfh_zvfh_zvl1024b`, 3M steps, 256MiB raw-file bound, 120 seconds.

Each case passed its original144-byte oracle with canonical NaN, flags16,
vstart0 and frm/fflags restoration. The checker retained all21 helper retirements,
full register-group input and m1 seed/output footprints, original initialization
loops and6720 fixture-field reads. Total:9 target calls,189 helper retirements,
1296 original output-byte checks,60480 fixture-field reads. This accepts only
the nine archived reduced-single reference executions, not full6720-call Linux
children, all original parent failures, or any DUT execution.

Host results:117 native original-C oracle tests;180 shared ledger preflight
checks;558 illegal helper-PC negatives;27 boot negatives;180 checks against
the newly extracted raw ledgers. Preflight01/02 and both independently found
pre-reference checker issues remain recorded; no reference was spent discovering
those issues. The active mf4 plan02 and all older sources/helpers remained untouched.

Final no-run audit revalidated628 distinct input pins and730 total evidence pins,
all unchanged, including every raw/private ELF/command/ledger/admission.
`TERMINAL_CHECK.json` binds exact nine membership and all evidence. Original
inventory has150 historical pins; this batch freshly checks its132 archival pins
and binds the inventory itself, not mutable unrelated status documents as current
source provenance. Independent source/compiled-code review also checked525 pins.

Frozen identities:

- `READY.json`: `ad59b118f7b223b7deea74a04e43a63ff616705571748e01f0d18e1ce98d937c`
- `TERMINAL_CHECK.json`: `996e2ad07ecfcf3daadd52018791c590c129fa6e8610a999fa9310249ddba491`
- `check_reference.py`: `3379658485e42e616eaea432df67d43d1ed21729edaed63cfd6c2abacfa9bd8e`
- `reference.py`: `ea5ce182b5acac380c055b26b58e4c22cf372875949cd11322d75a7ad50cb923`

Independent static clear (not reference acceptance):
`../original_remaining9_static_review01/CODE_REVIEW02_SUPPLEMENT.md`,
SHA256 `91b15377e422bb5d697a0a87ac2a1d2d31e28efb4ca077aaf1680233b165c137`.
No VCS runner or launch is prepared by this batch.
