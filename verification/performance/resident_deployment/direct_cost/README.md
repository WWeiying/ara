# User-Direct SDK Attention Cost

This pair compares **native AKV** and **Resident**, directly in U-mode, in one
ELF using one SDK arithmetic implementation and the same immutable Qwen3 inputs.
Native includes AKV commands and RVV leaves; it is not a pure RVV baseline.
Scope is `complete-sdk-attention`, not a complete GGML graph, model inference,
or proof of a production direct-U integration speedup.

## Inputs And Build

Main-owned `build.py` freezes SDK commit
`4a7361f51ba5447a616217dad1c8e72e3ee2b45b` with `git archive software/akv`.
Never overlay the working tree's dirty AKV assembly. Compile the entire closure
with a consistent userspace LP64D ABI, RV64GCV/Zfh/Zvfh,
`AKV_EXPERIMENTAL_RESIDENT_ATTENTION=1`, `AKV_REFILL_OVERLAP=0`, no fast math,
`-ffp-contract=off`, and no LTO. Link original native and Resident QK/PV sources.
The already-qualified board/view fixtures supply `fixture.h`, F32 query,
F16 K/V/plain mask, independent SoftFloat/original-math golden bits and flags.
Only H2, KV1, D128, T65/128/137 are measured; no unbounded model/context run.

GNU ld interposition is required for all ten symbols:

```text
--wrap=akv_experimental_qk_f16_pair_panel4
--wrap=akv_experimental_pv_f16_pair
--wrap=akv_experimental_resident_qk
--wrap=akv_experimental_resident_pv
--wrap=akv_native_info
--wrap=akv_experimental_attention_execute_v2_native
--wrap=ara_akv_direct_open
--wrap=ara_akv_direct_acquire
--wrap=ara_akv_direct_release
--wrap=ara_akv_direct_close
```

Pass each as `-Wl,--wrap=SYMBOL`. SDK entry/INFO and native/Resident leaf
witnesses are symmetric and their overhead is included in timing. Direct-client
wrappers prohibit client calls in the measured interval. Static linking avoids
lazy binding after acquisition. Missing wrappers must not be treated as usable
evidence: the benchmark requires exactly one SDK entry and five INFO reads per
sample, and 2/2/3 QK/PV pairs on the selected arm with zero opposite-arm calls.
An SDK OK result alone is insufficient: Resident admission can retain native.

## Ownership And Setup

An old board image is incompatible. Deploy a separately reviewed new kernel
with the built-in direct lease (including `!SMP` if required by that driver) and
a rebuilt hardware gate bitstream. This directory does not perform deployment.
No U-mode access to the S-privileged gate CSR is attempted. The real scalar
client validates Linux/ISA admission and ABI1 info: features 7, gate signature
`0x414b5601`, one online CPU. Acquisition returns the checked owner/generation.
Actual SDK capability INFO including index 4 and VLEN1024 is then checked
under ownership, before any arithmetic. Failure is terminal, without replay.

Each invocation acquires once, after storage initialization, finite-domain
validation of immutable inputs, input hashing/prefaulting, clock initialization,
unbuffered stdio setup, standard F/V first-use and RNE/zero vector-state setup.
It touches a bounded 256 KiB stack region and requires
`mlockall(MCL_CURRENT|MCL_FUTURE)` success before acquire; insufficient locking
privilege/limit is a setup failure. All workspace/output storage is static,
aligned and guarded. No allocation is requested in the leased loop. These are
reported setup actions, not a guarantee that an entire process can never fault;
the current kernel's owner-user-fault fail-closed policy remains authoritative.
Any fault/error stops this point without retry. Exactly one release occurs
after the entire point. No per-call ioctl, kernel input copy, or kernel compute
is involved. Options asserting whole-call ownership are set only after a real
successful lease. There is no emulation or substitute lease callback.

The once-only finite scan is excluded from timing because the fixture is
immutable. It rejects nonfinite Q/K/V and masks other than finite or -Inf, and
rejects an all-masked point. The fixed scale is `1/sqrt(128)` and inputs are
the bounded checked captures. This does not authorize removing validation for
arbitrary or mutable production tensors.

## Timed Scope

Both arms enter the same experimental SDK executor with automatic native
policy; only `options.requested` differs. Timing includes query F32-to-F16
conversion, a fresh SDK device query, Decode problem construction/validation,
plan preparation, shared SDK workspace initialization, FULL/refill, QK,
scale/mask/online softmax/PV preparation, PV, RELEASE, output normalization and
the completion drain. Shared original SDK C/assembly performs all arithmetic.
The benchmark neither implements attention nor bypasses SDK numerical work.

The call framing is derived from
`resident_rvv/qk_shared/full_call_sdk/main.c`, with one explicit cost change:
the harness-only geometry/route preflight occurs once per arm after acquiring
the lease, before the first measured call, instead of repeating a second Decode
walk every time. Resident checks its tile maps there; native does not perform
gratuitous Resident tile-map checks. This validates fixed immutable fixture
spans/workspace nonaliasing, not arbitrary mutable KV. Each timed call still
performs exactly one standard `akv_decode_execute`, preparing/validating its
plan and entering the shared SDK. The SDK internally revalidates its own
admission/preparation as before. No per-call SDK plan/check is cached or removed.
This framing difference precludes equating timings with the original VCS ROI.

Timing uses `CLOCK_MONOTONIC_RAW` and includes witness increments plus CSR
completion checks. It excludes lease setup/teardown, finite scanning, canary
resets, fixture-only preflight, output/golden checks, input rehashing, and logging. These excluded checks
also affect cache state identically between arms; this is not a cache-cold
microbenchmark. The SDK's existing FULL/refill transfers remain inside timing.
No repeated full user-buffer staging/copy is added.

Each point has native and Resident first-arm calls labeled `cold`, followed by
three `native, Resident, Resident, native` blocks: six warm samples per arm,
14 samples total. Cold means first call for that arm in the process; Resident
follows native and is not guaranteed cold in hardware caches/context. Each
sample seeds FFLAGS with 8 and checks the exact golden accrued flags OR 8,
RNE, VCSR0, VSTART0, all 256 output bits, input immutability and workspace
guards. A bad VSTART is terminal; it is cleared only for teardown, never replay.

## Collect And Analyze

The frozen `board/` package contains `resident-direct-pair`, `run_board.sh`,
`analyze.py`, `README.md`, the unchanged flat `source-pins.json`, original
`goldens.json`, and `SHA256SUMS` covering all six other files. Source pins retain
original absolute paths; analysis compares shipped artifact identities without
requiring those paths to exist on the board/analysis host. Retain the builder's
archive/compiler receipts alongside the board output. Hash inventories detect
drift; they are not signatures or a defense against forged evidence.

Operator example, after deploying and independently identifying the new image:

```sh
ARA_DIRECT_PLATFORM_ACCEPTED=yes BOARD_ID=vcu118-identified \
BITSTREAM_SHA256=<actual-64-lowercase-hex> KERNEL_SHA256=<actual-64-lowercase-hex> \
sh ./run_board.sh /tmp/resident-direct-new-output
```

Use the actual rebuilt identities, not historical image hashes. The script
checks machine/online CPU/device and package identity, runs a capability/lease
probe, then each bounded point once; failures stop without retries. It never
installs software, reboots, programs the FPGA, or changes the production image.
It copies its own executable/package into the new receipt directory and records
operator image attestations, Linux identity, return codes and original logs.
Attestation plus the runtime gate/SDK checks is not bitstream readback proof.

Off-board: `python3 analyze.py /path/to/copied/output`. The strict analyzer
requires a passing probe, balanced lease, 42 ordered samples, actual leaf
witnesses, exact flags/hash, unchanged packaged inputs, and correct setup
receipts. It reports cold separately, six-sample warm medians/ranges, three
ABBA paired ratios and temporal drift. It never grants whole-model or automatic
performance acceptance. Ratios alone do not promise a speedup.

Host checker: `python3 -B -m unittest discover -s . -p test_analyze.py -v`.
Its synthetic receipts test validation only and are not hardware/numerical
evidence. Target compilation/linking likewise proves no board admission or
performance result.
