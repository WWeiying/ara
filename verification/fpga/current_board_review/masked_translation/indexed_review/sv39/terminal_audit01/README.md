# NF7 Candidate02 Terminal Audit

This new directory audits sealed `../vcs_plan06` without editing it or launching
any simulator. `audit.py` checks all plan pins, frozen 539-source M2 image,
private inputs, exact 24-group/96-trial membership, return codes, completion logs,
strict group <2700s / runner <2400s bounds, and absence of abort/firstfailure.
It then recomputes all complete CSVs with the unchanged accepted checker, using
JSON-normalized dictionaries to distinguish integer-key serialization from
actual oracle changes. Trace row/retirement/cycle counters are independently
checked. Evidence and input pins are rehashed after replay.

The parent reported terminal service success before transient-unit GC. A fresh
read sees `LoadState=not-found`, not independently retrievable historical exit
status. The audit records this limitation explicitly rather than interpreting
systemd's missing-unit defaults as proof of success. It also checks absence of
remaining NF7-owned processes. No other simulation is inspected or controlled.

Run once: `python3 -B audit.py`. New evidence is exclusive-created in `results/`;
an existing output is not overwritten. Until `results/complete.json` exists,
no full24 offline acceptance is claimed. This is CPU-only postprocessing, not
a DUT rerun. Scope is the source-derived original96 on candidate02, not Linux
replay, candidate04, current workspace, or complete architectural coverage.
