# Unboxed265 M6 Independent Terminal Audit

Preparation is static only. No active CSV, service log or terminal artifact is
read. The frozen plan is e3bbb288f69f8f0cc0a24491125e0bb327e04d3edbaa3eb46837bb2c153e0940.
The audit imports the unchanged sealed dut_strict and mature lossless transport;
no disassembler, compiler, Host suite, Spike, simulator or service query is run.

After terminal authorization:

```sh
python -B audit.py terminal --authorize-terminal-audit --prepared-sha256 PREPARED_SHA --complete-sha256 COMPLETE_SHA --out terminal01
```

Both hashes are mandatory. Output must be a fresh direct child of this directory.
No automatic retry. Failures leave not_accepted.json, never an accepted result.
Static preparation: `python -B audit.py prepare` (exclusive prepared.json).

One complete CSV parse passes every original row unchanged, unfiltered, in order
through the independent observer to the sealed converter and strict checker.
Matching before/after row digests prove delivery, not a second CSV parse.
All actual PC/encodings, 265 calls/264 natural predecessors, exact 4587 helper
instructions, 5 entire unused helper ranges, legal bootstrap/capacity, original
setup order/values/BE, 4240 result bits, 530 guards, 265 flags/vstart reads, rawft0
instruction source, original CTRL exit0 and only subsequent parking are checked.
Full generic and strict dictionaries must match saved producer evidence.

Terminal checks include actual child numeric rc0, elapsed <=5400, COMPLETE,
no abort/retry/firsterror, both raw logs, private ELF, exact command, approval,
image/configuration/539 frozen sources/66 image files and all plan/evidence pins
before/after. Historical launch ownership is not outer service exit evidence.
No absent/GC service is ever assigned exit0.

Scope: original natural prefix265, not full17920 parent or Linux execution.
The unchanged original oracle allows architecturally permitted tail results.
Rawft0 evidence on DUT is the retired fmv.d.x f0,t2 encoding and prior integer
source0, not direct FPR payload observation. Saved flags0/restoration writes are
observed; post-restore CSR state is not directly read back. Raw reference vector
or CSR logs are not substituted for DUT payload/state measurements.
