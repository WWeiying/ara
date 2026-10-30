# Public Attention Result Acceptance

Six independent VCS runs cover two real K formats and three software
comparisons. They use the same accepted RTL image and captured six-head group;
none is a complete-model timing measurement.

| Canonical comparison | Ordinary V decode | Candidate V decode | Attribution |
| --- | --- | --- | --- |
| ORIGINAL_DECODERS | Production scalar | Production scalar | QBS plus sharing, including candidate admission |
| CANDIDATE_RVV_DECODE | Production scalar | RVV | Combined decoder vectorization, QBS and sharing |
| BOTH_RVV_DECODE | RVV | Same RVV | QBS plus sharing after equal software decode |

`common_variant.py` validates the sealed builder flags, exact decoder labels
and optional scope. `audit_common_attention.py` also verifies the final ELF's
sealed disassembly: original scalar conversion/multiply/store must be present
without vector instructions; the RVV helper must have the expected vector
load, extension, conversion, multiply and store. A symbol name alone does not
establish this distinction. All six actual builds pass this classification.

## Independent Acceptance

The auditor requires a terminal original-worker PASS, exit0, matching build/ELF,
complete source pins, independently checked backend/CVXIF/AXI evidence and the
original private experiment's fully replayed prerequisite. It then rechecks
the raw ABBA transcript, all output words, original gold, same-mode repeats,
QBS work, paired sums, reported numerical differences and protocol input hashes.

Each accepted result retains its variant annotation. The speedup is ordinary
two-trial cycle sum divided by candidate two-trial sum **within that ELF**.
Candidate cycles from different ELFs must not be subtracted and described as a
decoder-only effect: wrappers, code addresses and layouts also differ. Even the
matched-RVV comparison includes software cross-head sharing, so it is not a
hardware-only ablation. Model speedup and deployment approval are not inferred.

Mapping and runtime admission are timed. Actual GGML backend allocation-query
calls remain outside these standalone tests and require their own accounting.
A functionally valid result slower than its baseline is retained as such; the
auditor does not hide it or rerun until a favorable measurement appears.

## Background Collection

`queue_common_audit.py` seals its inputs and waits once on the real owning
worker's kernel process handle. When the owner finishes with a checked PASS,
the same transient service execs the auditor directly. It never launches a
simulator, rewrites an original result or modifies a sealed source. A missing
result, failed prerequisite, owner mismatch or identity drift stops collection.
An existing status file alone is not evidence of a live process or a PASS.

For each existing `akv-quantkv-<comparison>-<format>-20261024-01` run, independent
results use `akv-quantkv-<comparison>-<format>-audit-20261024-01`; queue state
uses the corresponding `-audit-control-20261024-01` directory. A dispatched
queue is not an accepted audit; inspect the audit's terminal `result.json`.

Fifteen unit tests cover variant ambiguity, linked implementation mismatch,
unchecked/nonterminal runs, failed owners and no-dispatch behavior. These are
checker tests, not additional RTL experiments or performance results.
