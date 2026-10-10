# IEEE special-value and masked-exception coverage

This campaign uses the old frozen image, not the repaired live RTL.
Stimuli are new; processor RTL is unchanged. RTL failures are recorded and
excluded without automatic repair. Environment errors can be corrected.

## Missing behavior and source basis

The 673-PASS raw condition bitmap still has 512 unhit positions out of
5,684 vector FP classifier positions, and 82 out of 784 scalar classifier
positions (instances named i_class_inputs or i_fpnew_classifier).
These raw diagnostic counts are not official DVE percentages or promises
that every remaining position is reachable.

The previous exact-integer/subnormal tests do not systematically exercise
signaling NaNs, infinity arithmetic or exception suppression by mask/VL.
This batch targets those distinct mechanisms. The widening dispatcher
selects OpQueueConversionWideFP2 on both sources; conversion must retain
the architectural arithmetic and exception behavior for these inputs.

## Test matrix

Eight tests use `vfadd.vv` and `vfmul.vv` for SEW 16/32/64, plus
`vfwadd.vv` for SEW 16/32. LMUL 1/2 and VL zero/short/odd/near-full/full
are combined with zero, sparse and all-one masks. Inputs are integer
bit-pattern arrays, not compiler-generated floating-point values.

| Operand pair | Addition result | Multiplication result | Invalid flag |
| --- | --- | --- | --- |
| +0, -0 | +0 in RNE | -0 | No |
| -0, +1 | +1 | -0 | No |
| +Inf, +1 | +Inf | +Inf | No |
| -Inf, +1 | -Inf | -Inf | No |
| qNaN, +1 | Canonical qNaN | Canonical qNaN | No |
| sNaN, +1 | Canonical qNaN | Canonical qNaN | Yes |
| +Inf, +0 | +Inf | Canonical qNaN | Multiply only |
| +Inf, -Inf | Canonical qNaN | -Inf | Add only |

All expected output and flag values are formed using an integer oracle;
there is no dependence on the compiler's scalar FP NaN propagation.
Masked-off and tail elements preserve the initialized destination.
No active signaling/invalid pair means no NV flag, including VL=0 and
all-zero masks. Flags and vstart are sampled immediately after arithmetic.
The complete raw destination array, flags and vstart are checked.

The exact same ELF must first pass Spike, then full scalar/vector RTL
comparison, DUT self-check and contract checking. Only admitted PASS VDBs
are merged with the completed compatible baseline. Merely reaching an
exception path does not admit a failing VDB. Diagnostic LZC VDBs remain
outside this processor aggregate.

## Preparation validation

Representative normal-width `vgap79_add16` and widening
`vgap79_wide32` compile with the same LLVM target flags, startup and
aligned linker used by the frozen-image campaigns. Both pass Spike;
the terminal tohost and g75_result signature are independently read from
the commit logs to require success, nonzero checks and zero errors.
Evidence: `verification/out/gap79-preflight-20261006-01`.
This is stimulus/oracle validation, not an RTL PASS or coverage admission.
The full eight-case old-image campaign uses `run_gap79_old_image.py`.
The runner permits overlap with an upstream DVE export only after every
upstream new test has an independent PASS verdict and its VDB is present
in the sealed, compatible bitmap/input lists. It freezes the upstream
acceptance status before starting, so later GUI report status changes do
not invalidate test-source pins. No running/failed/timed-out baseline
test is admitted by this overlap policy. Its own native DVE export remains
mandatory for a COMPLETE coverage result.

Output: `verification/out/gap79-old-image-20261006-01`.
Progress: `./vstatus jobs gap79` from the verification worktree.

## Measured eight-case results

All eight cases passed independent Spike self-check, full scalar/vector
comparison, DUT self-check and contract checks. Check counts per case:
FP16 2,080, FP32 1,056, FP64 544 (widening uses its source SEW count).
Both widening special-value cases correctly preserve canonical NaN results
and required NV flags; no conversion exception bug is inferred.

The compatible PASS bitmap union has 685 test VDBs. Its increment over
677 is 45 line points, 121 condition points and 23 branch points, with
zero FSM increment. All 189 newly hit raw points are in vector-lane
hierarchies, unlike the primarily scalar gains in earlier batches.
Evidence: `raw-bitmap-delta.json` and per-case comparison/audit files.
These counts are diagnostic points, not percentage-point increases.

The 677-test upstream native DVE export finished successfully while this
batch ran. Its raw i_system metrics are line 80.40%, condition 81.16%,
branch 79.97%, FSM 60.46%, toggle 62.89%. The new 685-test native DVE
export subsequently completed successfully. Its raw i_system metrics are
line 80.44%, condition 81.22%, branch 79.99%, FSM 60.46%, toggle 62.90%.
Both status and coverage_status are COMPLETE, and aggregate_passed is 685.
The final input/bitmap lists have 685 unique test VDBs and exclude the
known reduction failure and all isolated diagnostic VDBs.
