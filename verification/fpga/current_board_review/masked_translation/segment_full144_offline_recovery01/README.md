# Segment Full144 Offline Recovery

## Actual Terminal Result

**FULL144_CAPABILITY_COMPLETE**, source exit77, actual simulator exit0.
The once-only offline observer actually exited0 in291.113008s, without timeout.
All746 input pins and all successor scripts remained unchanged. Host10 passed.

- Full144 original case order,288 checkpoints and96 no-active cases checked.
- 120 numerical cases:983040 actual result bytes checked through scalar RVFI.
- 24 observed capability exceptions: actual target/cause/phase/VL/mask/context
  eligibility checked, not inferred from the Spike counts. No numerical result
  is claimed for those faulting cases.
- 5204692 CSV rows,5163532 retired instructions, last cycle8294243.
- 2296 CVX requests/responses,24 exceptions;17136 backend allocations/completions.
- 1002 memory architecture owners,930 required completed owners individually
  checked. VL0 and eligible early-fault rules are unchanged.
- No data mismatch was found. Original NOT_PASS is preserved; this is new
  offline architectural capability acceptance, not144 numerical PASS, Linux
  clone/COW replay, new simulation, or an independent-agent terminal review.

Durable terminal identities:

- `audit01/result.json`: `e3376bfe01bdf259790163de595a88c1c2bae0475c0c63eca2190bb8263dbcab`
- `audit01/wait.json`: `e87930e38b469cd3cac77ed6ddfdce7a08ecd6a2c2ba879733af0c9d52c49778`
- `audit01/closure.json`: `54493c405ebc2a4e9f7625fff39991b01b97951000c3bf04513261e51eac450a`
- `audit01/input_pins.json`: `a1df4eaf0183caf2e939ce804bea2278ae5fa28a2dd039a097076ba30a4673d9`

This successor only checks the already closed M8 trace. No DUT, reference,
compiler, RTL or old sealed artifact is changed. Original `prepared02/complete.json`
remains NOT_PASS, including the original audit error and its numeric exit1.

## Proven Checker Defect

The actual SoC ELF and pinned spec have no `replay_mismatch` symbol. The runtime
source defines that function, but this fixture never calls it; function sections
and `--gc-sections` remove it. The fixture reports numerical/fatal errors through
`mx_errors`/`mx_fatal`, `SEGMENT144_FAIL` and its source return. The old observer
unconditionally indexed the absent symbol on every retired instruction, so the
original audit failed with KeyError before validating the program.

Actual mandatory fatal entries are `trap_entry=0x80000054` and
`replay_trap=0x80000b90` (size0x8e). `replay_exit=0x80000068` is a valid exit,
not a fatal entry. The legitimate `mx_handler`/`mx_trap` handle expected Sv39
exceptions and remain permitted under the unchanged context checks.

The successor checks all spec symbols and instruction encodings against actual
nm/objdump output of the hash-bound ELF. It rejects every instruction in the
real fatal functions/startup fatal path, rather than supplying a fake symbol or
ignoring arbitrary missing required keys. Only three checker locations differ:
the contract import, its initialization, and the fatal-PC test. All original
144-case source/data/CSR/guard/capability/owner checks remain unchanged.

## Focused Host Evidence

`host01/wait.json` records actual exit0; `host01/output.log` records10 passing
tests. Cases include the real optional absence, missing mandatory symbol,
fabricated alias, wrong fatal mapping, wrong instruction/hash, real fatal entry
and interior PCs, legitimate handler/exit, the original CSV first row, and
rejection of unexpected fatal/mismatch/exit text. No whole CSV was parsed by Host.

## Once-Only Offline Execution

Executed command: `python3 -B execute.py audit`.
`audit01/invocation.json` fixes the1800-second observer bound and script hashes.
`audit01/input_pins.json` binds original plan/source/reference/image/imports,
actual closed CSV/private ELF, previous error and durable simulator receipts.
The original simulator actual rc0/10179.499469s is process evidence only.

The observer performs one strict numerical traversal, then the unchanged generic
protocol validator traversal. A new mismatch stops immediately; no retries.
`audit01/wait.json` is the actual subprocess wait receipt, not an inference from
a missing PID. `result.json`, if produced, is valid only with exit0, no timeout,
unchanged script/input pins and successful `closure.json`. It distinguishes
source_exit77 capability completion from source_exit0 numerical completion.

No new independent-agent terminal review is claimed. Neither capability
completion nor a numerical result reproduces Linux clone/COW/signal history.

## Input Identity

- Original plan: `1c349adc821b8fb4d1076674e267baa16bdc128b32cc9338bb77ac259ecb616f`
- Original NOT_PASS: `4f6ac7785f9b92af6b8a66457c239ebf402d12f6fb5a7bc80dff4414e45df38f`
- Closed CSV: `6eced8082eefaf64d1e4fbf2a273803f07cb10aa810bcdcd967bb07a285a5e92`
- Actual ELF: `087f4490b3363f93b48a55f63a14cb90ea87bf9daea7244dc046c69814d9f4cb`
- Successor checker: `b97a09d27b4066cac8c46d0c8a10cddfd9328797b607dda270c7553d9a9a4bf6`
- Fatal contract: `e827f0f71a425e1867c4cb63a8412b3a3d7b0e40b349fa3c2cac4984b1739e34`
