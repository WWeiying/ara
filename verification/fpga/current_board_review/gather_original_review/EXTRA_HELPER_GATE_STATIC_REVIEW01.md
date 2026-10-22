# VI0 prefix112 extra-helper gate: independent static review

## Conclusion

**A same-category checker coverage gap exists.** The selected VI0 helper's
13 instruction PCs, order, counts and full scalar data oracle are checked,
but the checker does not reject every other RVV retirement or every interior
PC of an uncalled helper. A protocol-consistent extra instruction with a
different encoding can escape that selected-helper accounting.

This is a static acceptance-coverage finding, **not a measured DUT failure**,
not evidence that the running program took such a path, and not a withdrawal
of previous data/reference acceptance. No VI0 synthetic counterexample was
executed. The reduction review's existing synthetic evidence is corroborating
evidence about the same class of gate, not a VI0 DUT observation.

Only this new report was written. No consumed script, RTL, input, reference
or original report was changed. No DUT/Spike/Host test, reference reparse,
service/process query or simulation launch was performed. Static ELF
disassembly and selected source/ELF hashes were checked.

## Actual Import And Acceptance Path

Paths below are relative to `verification/fpga/current_board_review/` unless
stated otherwise. Let `P` denote
`gather_original_review/e8_m8_ops2_prefix112_vcs_m6_plan01`.

- `P/checker.py:10-16` imports the successor `reference_check` as `source`
  and `gather_repair05/regression.py` as `common`.
- `P/replay.py:234,243,251` establishes the frozen image framework, imports
  `ara_verify.trace.validate_trace`, and calls this checker's `artifacts`.
- `P/checker.py:148-160` calls `common.check_artifacts`, the console gates,
  generic `validate_trace`, then local `retirement`; row count, last cycle
  and retirement totals must agree between the two CSV checks.
- `gather_repair05/regression.py:197-217` checks private ELF, command/image
  provenance, exit/budget, logs and trace-summary validity. It does not
  classify retirement PCs. Its `image_context` delegates to
  `integration/replay_memory_regression.py:48-65`, then
  `integration/run.py:122-127` selects the frozen verification framework.

**Import-name correction:** this VI0 entry does not call or import an
attribute named `common.strictprefix`. Its strict gate is the local
`checker.retirement`, saved as `strict_prefix.json`. Older checker/audit files
appearing in the plan's pins do not imply their validation functions execute
on this CSV. The actual common helper and frozen generic validator above
do not provide the missing closed-set PC policy.

## Concrete Static Evidence

`P/checker.py:23-38` builds the specification from only the selected op2
routine, data addresses and exit/park instructions. There is no complete
helper-range table or program-wide allowed RVV PC inventory.

`P/checker.py:53,87-125` has two relevant gates:

1. Any retirement with exact selected target encoding `30803c57` must be at
   selected target PC `0x8000071a`.
2. Retirements whose PCs are among the selected 13 must have the expected
   encoding and next helper step. Only these advance the 13 counters.

Before CTRL exit, other PCs fall through. They can still affect generic
order/trap checks, scalar setup tracking or full-output reads, but there is
no `else` rejecting an unselected RVV opcode/helper interior. The final
`counts == [112]*13` and 112 calls at line141 consequently do not count those
extras. Even helper-step ordering allows unrelated outside-lookup retirements
between counted instructions; it is not an all-retirements adjacency check.

Static disassembly of the exact pinned SoC ELF shows:

| Role | PC | Encoding | Instruction |
| --- | --- | --- | --- |
| Selected op2 entry | `0x800006fc` | `003772d7` | `vsetvli t0,a4,e8,m8,tu,mu` |
| Selected target | `0x8000071a` | `30803c57` | `vrgather.vi v24,v8,0,v0.t` |
| Unselected op3 entry | `0x8000072c` | `003772d7` | `vsetvli t0,a4,e8,m8,tu,mu` |
| Unselected op3 interior | `0x8000074a` | `308fbc57` | `vrgather.vi v24,v8,31,v0.t` |
| Capacity query | `0x80000696` | `0032f557` | `vsetvli a0,t0,e8,m8,tu,mu` |

The op3 interior is outside the selected lookup and its encoding is not
`30803c57`. In particular, an extra such retirement after the last scalar
oracle read and before CTRL exit need not change any already-read output or
selected-helper counter. This is a falsifiable static bypass scenario, not
an executed mutation or a claim that the ELF normally branches there.
Unlike the reduction checker, this VI0 checker has no explicit alternate
helper-entry exclusion either.

The frozen generic validator is
`/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources/verification/ara_verify/trace.py`:

- Lines12-35 recognize OP-V, vector memory, custom offloads and vector CSRs.
- Lines149-182 collect vector retirement encodings and coherent CVX
  requests/responses; they do not inspect retirement PCs against an ELF.
- Lines183-219 validate architecture/uop records when present.
- Lines243-253 compare the **observed** request and retirement encoding
  sequences, with narrowly defined harmless CSR-read transport replay.

Thus one cannot simply insert a lone vector retirement and call it accepted:
the matching transport and, if present, architecture/uop evidence must remain
consistent. However, this generic consistency check is not an independent
expected-program sequence. Balanced extra activity is not excluded by it.
The comparison of aggregate CSV totals in `artifacts` is also between two
parsers of the same observed CSV, not against an exact source RVV count.

Existing protections remain meaningful: wrong-PC exact VI0 target is
rejected, selected 13 instructions/counts are required, all112 setup/call
arguments and 114688 result elements plus224 guards are checked, vstart
returns must be zero, console failure markers veto acceptance, and after
CTRL exit only the exact original side-effect-free park is allowed. The
finding is a missing **additional execution-scope constraint**, not removal
or weakening of those checks.

## Proposed Independent Terminal Supplement

Do not edit or replace the live/sealed checker. After actual terminal evidence
is available and the parent authorizes the supplement, produce a separate
read-only acceptance artifact over the terminal CSV:

1. Bind the original plan, private input ELF, image/command/provenance, raw
   logs and complete CSV by hash. Retain original terminal status and gates;
   a supplementary pass cannot override missing completion, abort, failed
   data oracle, bad exit or input drift.
2. Derive instruction boundaries and encodings from the pinned SoC ELF,
   not a fixed offset into the Spike ELF. Identify every helper's complete
   instruction window, not only entry/target PCs. Reject retirement anywhere
   inside a nonselected helper, including its scalar/CSR interior instructions.
3. Independently enumerate all vector/configuration/vector-CSR instruction
   PCs in the ELF. Admit only the source-required capacity query and selected
   op2 sequence. Cover OP-V, vector load/store encodings and relevant CSR
   accesses; do not misclassify scalar FP load/store as vector memory. Reject
   unknown/extra RVV PCs or mismatching encodings even outside helper ranges.
   For this helper, 11 of its13 instructions are classified by the frozen
   CVX recognizer (the other two are `mv` and `ret`). The source predicts one
   capacity query plus112 ordered groups of11: **1233 architectural
   vector/configuration/CSR retirements**, not a blanket1233 CVX-request cap.
   Confirm the complete static ELF inventory before hardening that expected
   sequence; any other legitimate runtime instruction requires explicit
   source justification, never allowance merely because it appeared in CSV.
4. Stream the terminal CSV once for a closed-set ordered PC/encoding census,
   selected-helper counts and every unexpected PC with its first row/cycle.
   Preserve the generic protocol checks separately: harmless transport CSR
   replay is not permission for an extra architectural retirement. Do not
   demand equal full scalar retirement totals between Spike and SoC runtimes.
5. Report the original full-data gate and supplemental execution-scope result
   separately, with hashes, counts and explicit limitations. Zero unexpected
   retirements would close this hole for that actual terminal trace; a static
   possibility alone does not invalidate it. Nonzero unexpected retirements
   require evidence review, not automatic attribution to a new RTL defect.

Before implementing/running that supplement, parent-authorized small Host
negatives should cover an uncalled helper's interior target, vector load,
vset and vstart write; an unknown RVV PC; and balanced protocol extras before
CTRL exit. Positive coverage must retain the capacity query, all original
112 calls and legitimate transport-only CSR replay. **These are proposed
tests only; none was executed in this review.** No new reference parse is
necessary for this terminal PC-classification audit.

## Reviewed Identities

Selected source/ELF hashes below matched their stored plan pins; the plan
hash and external reduction evidence hash are independently recorded.
This is not a claim of revalidating every image/source pin or live module.

| Artifact | SHA256 |
| --- | --- |
| `P/prepared01/plan.json` | `bb3b5302ce2c65ec91874c22ed85705488aae4ba2043ad32b285ba60c6d81c11` |
| `P/checker.py` | `77683517a53ff02666068b6176eebe3df7eb2f74daaefa914d3ad1536e93cff7` |
| `P/replay.py` | `0409776216fe0eae514ffe715540663b31414d68ef10e8ec7cc5983cd95631e5` |
| `gather_repair05/regression.py` | `10358143c0b18f62bb4772aa9b0a117676eb9121d35bebbd80be7bd5e26c9966` |
| `integration/replay_memory_regression.py` | `4c317b218d8558c09035f2b5b728f936df1b9dcb33783803ff8d736f24b868e2` |
| `integration/run.py` | `c1c3804dbe36fa981ea7b6cbcfa5d7b69fb793b2a14c37831fb96e866f2d2a78` |
| Successor `reference_check.py` | `44b71fc3cec0cfbf3f0b4d8a95062f4996410671ae43f8f77abc91b33556008a` |
| Frozen M6 `ara_verify/trace.py` | `b5751d25426ba78893c52359519d3b6f1df6bc9c77eb341c91cdca1ff75b506a` |
| SoC `gather_prefix_e8_m8_ops2.elf` | `a0445bcb877799d488e40f37d7bcbc038d9f0e36a7a60e147ed8baf3c5ea5f74` |
| Reduction `independent_entry_review01/extra_helper_evidence.json` | `ce3238d28c3a653983a71a580b069cfdf6435824533230b6356062f9e473ac9e` |

The supplied reduction evidence reports two synthetic interior targets
accepted by both generic and full artifact gates, and an entry control
rejected. It was read, not rerun. No conclusion about current VI0 actual
retirement membership is made until terminal evidence is independently
classified.
