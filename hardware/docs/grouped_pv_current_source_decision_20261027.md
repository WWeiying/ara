# Current-source grouped-PV decision

The complete-call experiment is finished. Keep the grouped-PV opt-in OFF:
the current implementation is correct for this accepted real-data case but
still slower than the ordinary shared-V schedule in the same ELF.

| ABBA trial | Schedule | Complete call cycles | QBS busy cycles |
| ---: | --- | ---: | ---: |
| 0 | Ordinary shared V | 480814 | 8805 |
| 1 | Grouped PV | 485698 | 8805 |
| 2 | Grouped PV | 484920 | 8805 |
| 3 | Ordinary shared V | 480503 | 8805 |
| Paired sum | Ordinary shared V | 961317 | 17610 |
| Paired sum | Grouped PV | 970618 | 17610 |

Grouped PV takes 0.96752684% more cycles, speedup 0.99041745x. This compares
two software schedules on the same existing QBS hardware, not RVV versus QBS
and not complete model inference.

## What this closes

All seventeen objects were rebuilt from current sources. No stale quantizer
object was accepted after its source changed. The GNU build retained the
original real Q4_0 K / Q8_0 V inputs, six query heads, D128 and 128 visible
tokens. Every call produces 768 output values and uses eight native commands,
128 V decodes, four key panels, 9216 copied key bytes and six Q quantizations.

All four trials match the full golden-output tolerances on target and have
bitwise identical outputs across schedules, identical FCSR=3 and VCSR=5, and
intact guards. Independent UVM checking passes with no issues: 26983 interface
requests/responses, 22988 backend allocations/completions, 12228 completed AXI
reads and 5956 matched AXI writes. No transaction remains pending or aborted.

Parent review independently reran the raw transcript/work checker, revalidated
source pins and replayed the protocol-identity gate. The compact printed output
digest is not an independent host reconstruction of every numerical output;
the full comparison executes in the pinned target program.

Receipt: `verification/akv/results/grouped-pv-fresh-pair-review-20261027.json`.
Original worker output:
`verification/out/grouped-pv-fresh-vcs-20261027-01`.

## Interpretation

The old measured binary repeatedly divided to validate the per-token output
stride. Current code uses the checked equivalent multiplication-overflow
predicate. The complete linked disassembly confirms that this specific divide
is absent, and the boundary/code-generation tests pass. However, the remaining
complete-call regression rejects the claim that this change alone makes the
grouped schedule beneficial. New code placement and other current-source
changes also prevent attributing the difference between old and new binaries
solely to this one instruction.

The original shared schedule already decodes V once per token. Grouped PV
therefore only reuses V loads and combines some output scaling/MAD work; it
does not eliminate another round of full V dequantization. Coefficient arrays,
public-leaf validation, scalar head scheduling and changed dependency behavior
remain plausible costs. They are not an exclusive measured stall breakdown.
Unchanged QBS busy time also does not prove every residual cycle is software.

Do not add compute resources or remove safety checks based on this result.
Retain the correct original schedule as the default. Before further work on
this candidate, obtain bounded retired-PC/cycle attribution that distinguishes
validation, coefficient setup, exponential evaluation, vector arithmetic and
necessary command-front synchronization. Avoid another hint or LMUL sweep
without that evidence. The separately running Q/V/K preparation-reuse test is
independent and must be evaluated using its own complete-call timing.
