# Original-image coverage extension, 2026-09-28

This result applies only to the frozen pre-segment-VL0-repair VCS image at
`verification/out/repair-closure-coverage-20260927-01/sim/simv`. It is not
coverage signoff for the current repaired RTL.

| PASS-only set | Top score | Line | Toggle | FSM | Condition | Branch |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 473 baseline | 66.94% | 75.69% | 59.53% | 45.89% | 77.89% | 75.69% |
| 503 after 30 queue cases | 66.94% | 75.69% | 59.53% | 45.89% | 77.89% | 75.69% |
| 504 after AKV D96 | 66.94% | 75.69% | 59.53% | 45.89% | 77.89% | 75.69% |
| 505 after QBS descriptor fault | 66.97% | 75.70% | 59.54% | 46.02% | 77.90% | 75.70% |

The 503-case merge changed only toggle scores in six hierarchy rows. The
AKV D96 case then raised `i_akv_engine` condition coverage from 69.31% to
70.39% and `i_context` toggle from 71.14% to 74.41%; it did not move the
rounded top-level score. The six FP16 Gap29 cases failed on this image and
were excluded. Their passing Spike preflight is not an RTL PASS. The 18 older
timeouts were also excluded; the 505-case report contains only audited PASS
VDBs.

Point-level FSM inspection showed that the QBS normal sequence was already
covered, while `DESCRIPTOR_WAIT -> FAULT` was not. The new
`apps/qbs_descriptor_fault_cov/main.c` uses an inaccessible descriptor address,
checks one load-access trap and its address, and checks all 32 destination
elements for atomicity. The standalone VCS run and independent trace audit
passed. The coverage replay used the same ELF and frozen simulator, reported
one accelerator exception with zero protocol errors, and produced a complete
compatible five-metric VDB. This case raised `i_qbs_engine` FSM from 54.33%
to 55.12% and `i_read_engine` FSM from 71.43% to 85.71%; the read engine's line
coverage rose from 88.24% to 93.38%.

The accepted 505-case report is
`verification/out/vcs-original504-qbs-fault-20260928-03/dve/summary_waived.csv`;
its `collection.json` pins the result and identifies the original image.
Two earlier DVE-only attempts are retained but are **not accepted**: DVE's
hierarchy tree had not expanded before raw export and exclusions. The exporter
now expands the tree first, and the accepted merge requires complete raw and
waived hierarchy row counts plus applied reviewed exclusions. No RTL was
changed during this extension.

Remaining QBS/AKV FSM gaps are primarily fault and reset-abort edges.
Additional normal shape sweeps should not be counted as a strategy to close
those edges. PTW low coverage also includes paths compiled out when RVH is
disabled; reachability must be reviewed before writing tests or waivers.
