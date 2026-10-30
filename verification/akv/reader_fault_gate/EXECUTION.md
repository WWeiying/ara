# Reviewed Execution Interface

This successor adds `executor_common.py`, `build.py`, `run.py` and
`test_executor.py`. Nothing launches automatically. No GNU/VCS invocation is
authorized merely by preparing or reviewing these files. `prepare-02` is retained
as a historical prepare-only record and no longer matches the strengthened
checker. Use a fresh `prepare-03` after the executor inventory is final.

The strengthened checker inspects every fault-pending/response-drain sample,
including no-RVALID HOLD_EMPTY cycles, for data/completion validity. It permits
an older unretired completion on the first error cycle, but never payload on
that error beat. No scenario or original program selfcheck is removed.

## Build, Then Review, Then Execute

From the signoff root, after approval (replace each SHA with the reviewed full
hash; the commands below are recipes, not launch receipts):

```sh
OUT="$PWD/verification/out/reader-held-ar-build-20261025-01"
systemd-run --user --unit=reader-held-ar-build-20261025-01 --service-type=exec \
  -p WorkingDirectory="$PWD" -p KillMode=control-group -p RuntimeMaxSec=5400 \
  -p StandardOutput="append:${OUT}.worker.log" \
  -p StandardError="append:${OUT}.worker.log" --setenv="PATH=$PATH" \
  /usr/bin/python3 -B verification/akv/reader_fault_gate/build.py \
  --prepared verification/out/reader-held-ar-prepare-20261025-03 \
  --expected-prepare-sha256 PREPARE_SHA --output "$OUT"
```

The service directly owns the worker; stdout is a sibling of the fresh output,
never an active file included in an evidence hash. Build returns
`READER_HELD_AR_BUILT_NOT_EXECUTED`, not functional PASS. Review `build.json`,
weights nm/section bounds, disassembly, both compile admissions and images first.

```sh
OUT="$PWD/verification/out/reader-held-ar-run-20261025-01"
systemd-run --user --unit=reader-held-ar-run-20261025-01 --service-type=exec \
  -p WorkingDirectory="$PWD" -p KillMode=control-group -p RuntimeMaxSec=6000 \
  -p StandardOutput="append:${OUT}.worker.log" \
  -p StandardError="append:${OUT}.worker.log" --setenv="PATH=$PATH" \
  /usr/bin/python3 -B verification/akv/reader_fault_gate/run.py \
  --build verification/out/reader-held-ar-build-20261025-01 \
  --expected-build-sha256 BUILD_SHA --output "$OUT" --timeout 900
```

Both commands support `--preflight-only` with a DIFFERENT fresh output; this
does not invoke GNU/VCS. No pidfd queue or automatic simulator follow-up is added.
Confirm the service MainPID and actual EDA child once, then wait for completion.

## Identity and Bounds

One freshly linked ELF is reused unchanged for baseline and candidate. Only the
successor main is recompiled; all original startup/libc/probe objects are explicit
hash-pinned reuse. GNU actual compiler/linker/multilib components and `-M` header
dependencies are recorded before compilation. `nm -S --defined-only --format=posix`
must report exactly one `weights`, size432, alignment64, in an allocated section
inside the reserved 16MiB layout; its first288B must not cross a4KiB page. The
exact nm address drives both the simulator plusarg and the UART/wave checker.

Each new image has its own full source/header graph manifest, original UVM
sources/flags, `simulator.conf`, simv and all image `.so` pins. `image_files`
explicitly includes BOTH config and manifest; each is pinned before and after
simulation. Only the exact inherited TLB genvar warning is admitted, using the
already-reviewed fixed-hash admission. No global IPDW/width-warning exception.

Run phases preserve raw console/VCS/vector logs, finite250000ns FSDB, raw exporter
CSV/metadata and strict combined log/wave checks. Actual `ara_verify.uvm_dut` is
run with events/backend/AXI/write checks, directly on unfiltered logs/traces and
the same ELF/image. Each mode stops on any failure. The final comparison retains
all71 command ledgers and every field delta; even offsetting cycle changes yield
REGRESSION rather than PASS. No active status/stdout/self-result is evidence-sealed.

Bounds: GNU phases180s (identity/nm30s), each SoC compile1800s, each simulation900s,
each UVM check600s, each export300s. The inherited accepted SoC compile reported
about208 CPU seconds, not wall time; provision roughly10-20 minutes for the two
fresh builds under shared load. The earlier71-command fixture took roughly3
minutes per simulation; budget roughly6-12 minutes for the pair plus hashes,
export and protocol audit. These are scheduling estimates, not measured new-run
performance or a promise to finish before a fixed wall time. Never widen bounds
automatically after a failure.
