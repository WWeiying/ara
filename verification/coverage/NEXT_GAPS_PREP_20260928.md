# Next coverage batch: preparation only

## Evidence base

The audited original-image collection has 473 PASS and 12 TIMEOUT results.
Only PASS VDBs contribute to its DVE report at
`verification/out/vcs-memory-gap-20260928-01/dve/summary_waived.csv`.
The in-flight 36-case `vqueue_gap28` batch reuses that exact VCS image. Its
coverage delta is unknown until the batch completes and DVE exports the new
PASS-only report. Do not count Spike preflight as RTL coverage.

## Prepared follow-up

`verification/tests/next_gap29_ready.json` pins seven new ELFs and their
sources. Six `vrvv_gap29_fp16_*_m4` programs passed Spike selfchecks and cover
rounding modes, masked/tail behavior, VL 0/1 and exact FP16 conversion bits
and flags. The `akv_d96_gap29` program uses a legal V2 descriptor with D=96,
three query rows and three KV rows; its host reference checked 864 elements
and guards. Its custom instructions have not yet been checked by RTL.

The existing QBS M8 application has a NaN-permissive comparator and no bounded
RTL runtime measurement, so it is not in this frozen selection. Its candidate
work remains a separate future gap.

Run `python3 verification/tests/prepare_next_gap29.py` to recheck all pinned
inputs. This command prepares metadata only; it does not launch VCS. The
selection file is `verification/tests/next_gap29_selection.json`.

## Candidate gaps after the queue batch

| Area | 473-PASS observation | Next directed evidence |
| --- | --- | --- |
| Ordinary RVV | Instruction forms are present, but SEW/LMUL, mask, policy and vstart combinations are sparse. Random tests rarely use FP16. | Short self-checking FP16, reduction and boundary combinations with legal RVV configuration and an independent reference. |
| QBS | Engine condition 71.08%, FSM 54.33%, toggle 55.24%; earlier audit did not select dedicated wide-M or small-N cases. | Legal wider-M, interleaved and small-N cases; check full output and command completion against the software reference. |
| AKV | Engine condition 69.31%, FSM 63.64%; existing D64/D128 and software-grouped D256 do not establish native D96. | A legal D96 case with view/lifetime transitions and complete result checks. |
| System | PTW line 55.24%, branch 40.23%; a large Linux boot is not required to target specific state transitions. | Small MMU/trap cases only after verifying the checker, address map and existing coverage bins. |

The operand queues are currently addressed by `vqueue_gap28`; measure their
actual coverage delta before spending another batch on those paths. Disabled
parameter branches and physically tied-off inputs require reachability review,
not more random seeds or blanket waivers.

## Launch gate

Prepare source, ELF, test oracle, Spike/reference preflight, unique names and
SHA-256 pins now. Do not launch VCS or DVE for this next batch until the
user explicitly says to start after the in-flight queue finishes. On launch,
append to the completed original-image collection, use at most eight VCS
workers, continue independent cases after ordinary FAIL/TIMEOUT, and admit
only independently checked PASS VDBs to the verified DVE report.
