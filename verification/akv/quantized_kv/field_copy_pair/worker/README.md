# Matched Field-Copy Worker

Implementation/review only. No simulator, compiler or service launch is
authorized until the parent reviews frozen preparation and worker inputs.
Only worker/ belongs to this owner; prepare/, PLAN.md, software-path documents,
old helpers, RTL, historical results and external llama are read-only here.

Compare 839a03622130dba7299155f1ccd55c004a6b676a (baseline) against
083d4ed84f47905a675566cc4c459d2e70549ac0 (candidate), using TWO freshly built
programs on ONE reviewed actual canonical image. No historical run/cycle values
are admitted as either side. Each executable must perform all six original
H/S/B/B/S/H calls, 768 outputs per call and sixteen native commands. Original
model gold, per-output tolerance, H/S exactness, mirrored output/CSR consistency,
actual work and all four independent UVM requirements remain mandatory.

Each --side baseline/candidate invocation owns one foreground simulator and
one independent output/work directory. The services may run concurrently;
they do not launch each other. Each simulator is bounded to 10,800 seconds;
there is no retry or continuation after failure. Run the Python worker as the long-lived
systemd service process (KillMode=control-group), never a short-lived launcher.
The accepted Execution bookkeeping/process-group cleanup is retained with a
worker-local child-launch function that sets cwd to the private log directory.
This avoids shared ucli.key files in the repository root. Canonical image,
manifests, source and preparation directories are read-only inputs.
No systemd service is created by this module. The unrelated multicore campaign
is not inspected for control or modified.

No COMMIT_TRACE is requested. VECTOR_TRACE, QBS_PERF, NO_FSDB, NO_INSTR_TRACE
and original 2,000,000 event limits remain. Required UVM events, backend, AXI
and AXI-write checks must all pass. Limit exhaustion is a failure, not permission
to filter evidence or silently rerun with different flags.

The default command performs OFFLINE preflight only. Actual execution requires
an explicit --execute-reviewed-side argument and a parent-reviewed receipt/hash.
Preserve inherited LD_LIBRARY_PATH exactly, review its value, record it and
check it before/after each phase. All preparation, data, compiler, helper, ELF,
image and parent PLAN.md identities are pinned before/after. No doc or helper
that becomes a consumer pin may be edited during its run.

Outputs are organized as two independently fresh side directories and a third
fresh offline comparison directory; each has its own closed evidence receipts.
Each binary contributes 4,608 output words; the cross-binary comparison checks
4,608 corresponding pairs (9,216 values read). A successful
checked pair measures cycle deltas/ratios for both repeats and all modes, but
does not require a positive speedup to call functional checks complete. Any
regression is explicit. Independent parent review is still required before
performance acceptance; no default-on/backend/whole-model claim is made.

## Review Interface

The native prepare/build.json schema is consumed directly. No new API is
required from the preparation owner. admission.checked_pair verifies receipt
types, full workload, all input/artifact hashes, both source trees and exact
five-header-plus-new-helper delta, all seventeen dependency/compile proofs,
three affected rebuilds, common linker slots/scripts, linked layouts and original
payloads. Pure producer layout/recipe functions are replayed from reviewed helper
code; no producer build/Git/compiler action is called. The original gold file
must equal each linked attention_golden payload. Neither side is an old ELF.

Parent review schema `field_copy_pair_parent_review_v1` contains:
prepared_pair (absolute pair build.json), prepared_pair_sha256,
runtime_environment: {"LD_LIBRARY_PATH": <exact string or null>}, input_pins
(absolute input path -> SHA256), and four explicit static review flags:
preparation_reviewed=true, same_inputs_flags_schedule=true,
affected_objects_rebuilt=true, historical_timings_used=false.
input_pins must include every worker Python file, worker README, parent PLAN,
and all top-level preparation Python, README and .gitignore inputs. Additional
reviewed program/tool/data pins may be included. Freeze before hashing review.
The pair receipt itself closes generated sources, objects, build receipts,
compile/link/dependency evidence and data; the consumer verifies those hashes.

```
python3 -B verification/akv/quantized_kv/field_copy_pair/worker/run.py \
  --side baseline --review /absolute/review.json --review-sha256 REVIEW_SHA \
  --output /absolute/fresh-baseline
```

The candidate preflight uses --side candidate and a different fresh output.
After separate approval, the same invocations with --execute-reviewed-side own
their simulations directly. collect.py accepts --baseline, --candidate,
--review, --review-sha256 and --output; it never launches any child process.

Host tests: `python3 -B -m unittest discover -s verification/akv/quantized_kv/field_copy_pair/worker -p 'test_*.py' -v`.
