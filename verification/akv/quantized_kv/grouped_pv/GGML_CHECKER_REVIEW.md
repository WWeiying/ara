# First actual-GGML run: unresolved checker assumption

The original run at `verification/out/grouped-pv-ggml-20261026-01` is FAIL and
must remain FAIL. Its complete fixture sources are preserved under
`fixture-source/`; logs and input pins are unchanged. No production calculation
or RTL fix is justified by this observation alone.

All 32 native call records reached their checked END markers: Q4_0/Q8_0 keys,
contiguous/token-major layouts, visible prefixes 128/5, old/grouped modes and
two repeats. Those calls checked complete output, pairwise exact bits, captured
gold where applicable, reference outputs, CSR and unchanged inputs. This is
partial evidence within a failed suite, not a complete-suite acceptance.

Failure occurred in the Q4_0 token-major two-thread fallback, grouped option
enabled: output equality passed before `baseline_csr_mismatch`. There was no
quant-KV execution record for this call. The preceding option-disabled call
reported parent FCSR 11, matching its reference. The fixture did not print the
failing actual FCSR, so it must not be invented or inferred as a measured value.

Static inspection identifies a questionable test assumption. GGML distributes
Attention head chunks dynamically across its OS threads; its completion barrier
does not reduce per-thread floating-point flags into the caller. The fixture
resets and samples only the calling thread's FCSR. Comparing that register
across two independent multi-thread schedules is not automatically equivalent
to comparing the aggregate arithmetic exception behavior.

A discriminating follow-up in `thread_flags/` runs the same two-thread ordinary
GGML computation repeatedly, with quant-KV disabled throughout. It must retain
all output bits, unchanged inputs, rounding mode, preexisting sticky flags and
VCSR checks, while recording actual caller flags. A varying caller flag set
would demonstrate the original equality assumption failing without any grouped
execution. A constant observation is inconclusive; it is not evidence that the
original failure was repaired. Native and single-thread exact-CSR checks must
not be weakened. The diagnostic result is pending at this document revision.

Separately, the grouped SDK runtime passed the existing 288-case panel/lifetime
fixture against its original contiguous reference with GCC and Clang
ASan/UBSan. This covers multi-group panel reuse, repeated-call invalidation,
padded layout, pre-admission fallback and terminal executor errors. It does not
close the failed actual-GGML suite or provide RTL performance evidence.
