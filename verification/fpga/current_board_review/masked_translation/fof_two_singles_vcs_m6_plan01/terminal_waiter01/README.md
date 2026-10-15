# Prepared Conditional FOF2 Terminal Check

No launch is authorized by preparation. No active CSV, reference raw, running
service or process is inspected. Existing worker, plan, helpers and outputs
stay unchanged. This reuses the accepted negative-stride waiter's inotify,
single-stream CSV/hash bridge and generic CVX/architecture/uop validator.

After Main explicitly authorizes, use a new independent service (4300s outer):

```sh
python3 -B waiter.py wait --authorize-wait --ready-sha256 ACTUAL_READY_SHA \
  --out "$PWD/terminal01"
```

The directory must be fresh. inotify registration precedes checking terminal
file existence, avoiding missed atomic-rename events. Wait bound3600s; offline
bound600s across both CSVs. No retries, resume, DUT control, or repeated CSV pass.
Missing terminal or any failure is NOT_ACCEPTED, not an RTL diagnosis.

Before either CSV opens, require whole2 clean PASS, exact COMPLETE membership,
both persisted actual monitor numeric0 and child0, unchanged elapsed values
within1800s, no abort/failure/timeout, all744 original plan pins (including118
reference pins), parent approval, M6/privateELF/commands, and complete evidence
membership. Hash the two CSVs within their one full parsing pass, not a separate
prepass. Check file identity before/after and all non-CSV evidence/pins again.

Each pass independently reconstructs actual scalar read addresses/BE/sign
extension and defined values: two complete20KiB maps (8192data+12288tables),
both page guards, 130 initial output elements and126/130 defined final elements,
32mask-byte reads, original guards0/9, selected contiguous11-helper/capacity3,
original four arguments, actual scalar checks5477/5481, original saved/restored
CSRs, S-ECALL context and raw CTRL0. e8 final5..8 are omitted, not constrained;
business VL4 is distinct from restored/store/completion VL8. e64 old-vd is
uint64 value0x5b. Compare independent checkpoint coordinates/protocol totals
with the worker's bound strict result. Full source maps and initialization
checks also remain bound by strict_csv/strict_original and original evidence.
The worker's source-oracle executor and reference are not rerun.

Durable simulator monitor0 is actual process evidence. Original systemd exit
is NOT_QUERIED_NOT_PROVEN unless Main separately captures it; do not infer it
from garbage-collected unit defaults. This is two selected source-derived Sv39
singles, not Linux signal equivalence/all eight failures. Architectural target
exception0 is required; zero physical MMU activity is not proved.

Only four focused Host test methods are used: whole2/actual-exit gate negatives,
both complete synthetic numerical scopes with corruptions/undefined-range
checks, single-stream generic/hash bridge, and atomic-rename event waiting.
