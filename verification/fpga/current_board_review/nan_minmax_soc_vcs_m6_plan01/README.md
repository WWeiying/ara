# Two NaN Max Source Singles On Frozen M6

Preparation only; no DUT launch, source/ELF/reference rebuild or image/RTL edit.
Use the two sealed SoC ELFs directly. call1294 active element2 expects7fc00000;
call1234 alloff expects seed7fc12345. Both e32/m1/VL3/CAP32/frm0/op2/sticky0,
flags0/vstart0, original21 helper and144B output oracle. No min/full-parent claim.
Actual reference firmware:1857110 instructions each. At600 retired/s the
planning proxy is3095.2s per case, not a guarantee.

Two independent private case directories, jobs2, fixed5400s simulation and
7200s owning-worker service bounds. Direct systemd worker, group-owned children,
Restart=no; no retries, FSDB, coverage, UCLI or diagnostic simulation.
Resource gate runs only after actual parent authorization: live+jobs+unused
reservation<=24 and MemAvailable>=32GiB.

Mature gather_repair05 image/provenance/resource/signal gates and frozen M6
RegressionRunner are reused. The strict scalar checker derives PCs from each
actual SoC ELF independently of Spike. It validates every source input/seed/
mask store, fixture bank/address/value/order, one-shot capacity and full21
contiguous helper including vset retirements, returned flags/vstart, actual CSR
save/request/restore operands, full144 LBU oracle and original CTRL exit0.
Scalar CSV cannot expose vector port payload or CSR delta writes; these are
not assumed. Restoration evidence is retired writes with saved operands, not
an extra post-restore readback.

Only the frozen generic six normal event types are accepted; generic verifies
all CVX/architecture/uop protocol. Unknown events/exceptions fail. Raw PASS plus
any failure/DETAIL is vetoed. Exact COMPLETE/PASS metadata and both actual
numeric child outcomes are mandatory.

One immutable _run_monitored routing hook is installed before threads start.
It fsyncs each actual code/elapsed/timeout/failure tuple immediately after the
real monitor returns, before command metadata or generic/checker postprocessing.
Runner classification is saved separately. First cause is create-only; abort
is shared/sticky through late source/image/pin checks and final publication.

Host synthetic scalar/protocol fixtures, real frozen-parent early-postcheck
exceptions, rc0/17/timeout preservation and concurrent routing tests are not
architectural runs. Dryrun uses the actual frozen command builder but an
explicit no-build override. It requires two DRY_RUN results and no DUT files.

Prepare: replay.py prepare --out prepared01 --authorize-prepare --reserved-slots0
Dryrun: replay.py dryrun --out prepared01 --plan-sha256 ACTUAL_PLAN_SHA
Parent run approval remains unresolved. The service command contains explicit
unresolved approval placeholders, never an invented accepted pin.
