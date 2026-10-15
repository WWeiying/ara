# Parent Conditional Authorization

The parent explicitly authorized a read-only file-event wait after preparation.
Only after the actual complete.json exists with exact PASS/full original scope,
numeric case rc0, aborted=false, retries=0, pins_unchanged=true and matching plan
SHA may the frozen terminal audit run once into terminal01, binding the actual
complete SHA and preserving the actual invocation/exit evidence. Any failure,
missing field or drift must stop, not be treated as PASS. No automatic retry.

This authorizes no simulator, reference, build, Host suite, sealed-file change,
RTL modification or termination of existing work. Waiting uses filesystem and
pidfd events, not periodic polling. A missing process is not evidence of rc0.
Real numeric child exit is required from the pinned terminal evidence. The
separate audit command return code will be collected by its actual parent.

Authorized plan: e3bbb288f69f8f0cc0a24491125e0bb327e04d3edbaa3eb46837bb2c153e0940
Frozen prepared: ff5f57910afda05b9eb34ca8551459523fffa952b0282cb4563d1f9a9a9af444
Parent's observed simulator PID: 1418946 (not a substitute for identity checks).

Local wait has a fixed7200s ceiling; audit subprocess has a fixed1200s ceiling.
These are offline scheduling bounds only, not changes to the DUT5400/service6600
budgets. At most one audit invocation. Timeout or cancellation cannot publish an
accepted review. No final service return code is fabricated after GC.
