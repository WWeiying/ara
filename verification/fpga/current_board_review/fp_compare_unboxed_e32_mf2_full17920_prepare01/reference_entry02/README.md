# Pure Source Setup Cache Successor

Entry01 is sealed, unchanged and not executed. Its `setup_store` reconstructs
49 expected tuples for each of49 actual stores:878080 constructions,43025920
tuples for17920 calls. No cache exists in entry01. Averroes confirmed the same
static result and suspended its final entry01 admission.

Entry02 inherits the hash-bound entry01 checker. It overrides only construction
state and `setup_store`. The original pure `expected_setup(g)` is unchanged.
On a new `self.calls` ordinal it builds one tuple of49 immutable integer triples
from `self.current()` and pinned symbol addresses. Neither actual store data,
shadow memory nor prior observed values are used. On later stores in that
call it reuses only these expectations. The ordinal equality guard makes old
expectations unusable after the original oracle advances `self.calls`, even
when all expected values repeat. The first store of the next call replaces
the entire cache. State is instance-local, not shared across checkers/backends.

The unchanged source gold/spec are read-only inputs by contract, checked by
pre/post file pins. No checker method mutates those objects. Actual vector,
scalar and memory state lives separately. This successor does not support
changing a source row in place mid-call; no production or test path does so.

Each actual event still passes the same phase, exact PC/index, sequential
fresh-count, address, full value and width comparisons and increments both
original counters. Missing/duplicate/same-value writes are not elided. There
is no cached actual data, oracle result, helper progress or acceptance state.
The complete reader/CSR/FPR/helper/owner qualification/EOF checks are inherited.

The short suite runs all31 predecessor checker tests against entry02 plus
small old/new differential tests. These cover source call/seed/mode changes,
repeated identical setups, FP32 high bits, missing/duplicate events, wrong
PC/address/width/value, successful-oracle ordinal transition, immutable tuples
and instance isolation. A six-call instrumented profile expects294 old
constructions vs6 new constructions, with294 actual store events delivered to
both. It measures constructor count, not a fabricated full raw audit speedup.

No original full Host, target compilation, linked CFG, raw parse or reference
is repeated. One checker-only child is bounded120s. Preparation preserves all
receipts and is exclusive/no-retry. Spec, executor and audit wrapper are
byte-identical to entry01; only their private directory and exact pin binding
change. Parent approval and Averroes final exact entry review remain required
before the sole future reference. Budgets remain rs4M/120s/768MiB/audit600s,
firmware-to-HTIF3M. No DUT is authorized.
