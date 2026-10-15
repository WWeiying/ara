# Prepared, Not Admitted

Software reference READY (already sent to Confucius):
`ee10a401774a5cb474be69c317edad4ea052c147a42b5fd03aa4cc4b1f5db731`.
Actual SoC ELF: `03e24bc51c28b705ae3cd373a51c38e04c39ab0eb26443d29ca7d36277741058`.

Host02 PASS:5 methods,2 positive protocol fixtures,13 case-specific negative
subtests; zero failures/errors,16.858s. Includes real partial-line DETAIL
monitor cancellation and inherited late-abort/fresh-plan behavior.
Host01 FAIL is preserved: missing Spike-only replay_log in the actual SoC spec,
and Host Python dependency initialization. No synthetic symbol was fabricated.
The owned dut_strict.py differs from sealed reference strict.py by exactly one
condition: `if s['spike'] and wmask ...` before Spike console reconstruction.
Rows, original oracle, PC, CSR and helper-window checks are unchanged.

Fresh `prepared01/plan.json` SHA:
`e3bbb288f69f8f0cc0a24491125e0bb327e04d3edbaa3eb46837bb2c153e0940`.
733 input pins; exact M6 image, one job,5400sec case/6600sec service.
`prepared01/dryrun_check.json` is `PASS_DRYRUN_NO_SIMULATOR`, SHA
`54d5bda0715a2d6e102d5cdcdba912984d2177922ac9042b143603bf862c2491`.
Dryrun printed the existing M6 simv invocation with +NO_FSDB/+COMMIT_TRACE;
it did not execute simv. No build, DUT, resource/live-service query or reference
retry was performed.

Worker SHA: `f760f4a69190b29886f4fa70de289b992e052a46c0a6b6010dcc166792ea422a`.
CSV adapter SHA: `48c233a86c5b26ef5196a26c845ec1374d8589f409a389193e1cdd53f2726cd8`.
Owned strict SHA: `b657f3606c9f0c0d64992ad3bc92c56e7646d81ed203d36d15cd8040d1052bfb`.
Host02 JSON SHA: `add04b1e985610c3f7e6b52af9fa110c32111470e03cd9db9c18b616df907491`.

Independent reference acceptance remains pending in this plan. Launch requires
the actual independently written audit.json and REVIEW hashes supplied by a new
pinned parent authorization, their accepted status and matching READY, the exact
plan SHA, service name, and explicit budget acceptance. No placeholder acceptance
or hash is stored. Actual schema mismatch must remain fail-closed and be resolved
in a fresh plan before admission, not by altering this prepared plan.

The full future service command is in `prepared01/ready.json`; placeholders
PARENT_REVIEW_JSON/PARENT_REVIEW_SHA256 deliberately prevent accidental launch.
No launch is authorized by this record. Preserve prepared01, host01/02 and all
software reference artifacts unchanged for independent review.
