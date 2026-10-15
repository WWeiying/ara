# Actual ISA And Approval Sequence

The retained command used **rv64gcv_zfh_zvfh_zvl1024b**. The subsequently
provided parent admission file specifies **rv64gcv_zvfh_zvl1024b**.
These strings are not identical. Neither the command, raw, approval, nor
parent review has been rewritten to suggest an exact match.

Execution followed the earlier explicit user request for the established
Zfh+Zvfh FP16 golden profile and the later explicit, pre-execution3M/256MiB/
120-second authorization. `reference03M/approval.json` was pinned before
the one execution. The separate parent `reference_admission01/review.json`
was read after that execution, and is bound afterward by CONFIG_DELTA.json;
it was not a pre-execution file gate. The user subsequently permitted this
accurately labeled delta and executor-PASS handoff for independent review.

Both actual ELF hashes and all four resource limits match the parent file.
The software, full original loops, fixtures, oracle, helper and both ELFs
are unchanged. No second reference was executed or authorized by this note.
The initial1M reference was never executed.

`config_delta.py` classifies every one of the1,860,000 retained commit
records. It finds **zero scalar FP instructions of any width**, including
zero scalar-half arithmetic/conversions/FMA/load/store. RV64 compressed FP
load/store forms are also included in the classification. There is exactly
one vector FP arithmetic encoding, `0c881c57` (original FP16 vfredosum).
The remaining vector instructions are the original loads/mask/store/vsets.
The retained21-instruction helper exactly matches the original Linux helper
machine code. Actual result, NV and CSR/full-byte checks are in audit.json.

Thus there is no observed scalar-half instruction consuming the extra Zfh
capability in this concrete execution. This is a bounded inference, not an
execution under the narrower profile or a claim that enabling Zfh can never
affect other software. Independent review must judge the concrete reference.

Final classification is **REFERENCE_EXECUTOR_PASS_PENDING_INDEPENDENT_REVIEW**,
not exact-profile contract PASS, not DUT acceptance, not full-parent/Linux
acceptance. CONFIG_DELTA.json binds the exact command, raw, ELF/resource
comparison, classifier, parent review and independent cost review hashes.
