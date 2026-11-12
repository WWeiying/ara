# Resident Hardware Discovery

This successor suite does not edit or consume the old sealed Resident checkers.
Run from `ara_dsa`, with host VCS and the host C/C++ toolchain on PATH:

```sh
python3 -B verification/performance/resident_deployment/discovery/run.py \
  /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/resident_deployment_discovery_UNIQUE
```

The output must be a fresh direct child of signoff `verification/out`. The runner
archives SDK support sources from HEAD, overlays only the authorized discovery
files, and freezes inputs before testing. Uncommitted native assembly and native
C changes are not imported into this SDK test snapshot. `source-pins.json`,
`artifact-pins.json`, command logs and `SHA256SUMS` retain the evidence. No board,
synthesis, full SoC, Verilator, URG or ZCC is used.

## Wire Contract

`config/akv_abi.json` is the single source for the index-4 layout:

| Bits | Meaning |
| --- | --- |
| 7:0 | Discovery word version, exactly 1 |
| 8 | Actual Resident PV implementation supported |
| 9 | Actual Resident QK implementation supported |
| 23:16 | Lane count, exactly 4 |
| 47:32 | VLEN in bits, exactly 1024 |
| All other bits | Reserved, must be zero |

PV-only is `0x0000040000040101`; PV+QK is `0x0000040000040301`.
No implementation contributes any bits when disabled. The dispatcher ORs the
two contributions, including common metadata. Zero means absent/legacy hardware.
QK-only is malformed because QK uses the PV resources. Words 0..3 are unchanged.
The legacy compile-time `*_SUPPORTED` defaults remain false and are not discovery.

## SDK Consumer API

All SDK users must rebuild together: `akv_capabilities_t` and consequently
`akv_device_t` grew. There is no binary compatibility with prebuilt consumers.

`akv_device_query()` now reads indices 0..4 in order. It retains the original
0..3 decode status. An absent or malformed index 4 disables only Resident and
does not disable a valid native AKV implementation.

For a platform gate with captured words, first call
`akv_capabilities_decode_extended(info0, info1, info2, info3, &caps)`, then:

```c
akv_status_t status = akv_capabilities_decode_resident(info4, &caps);
/* status == OK and the relevant supported field permit compute selection only. */
```

This API changes only `resident_valid`, `resident_capability_version`,
`resident_pv_supported`, `resident_qk_supported`, `resident_nr_lanes` and
`resident_vlen_bits`. Every failure clears all six fields and preserves all
native fields. Zero returns `RUNTIME_UNAVAILABLE`, unknown version/geometry,
reserved bits or QK-only returns `ABI_MISMATCH`, missing native/v2/F16 support
returns `CAPABILITY`, and a null pointer returns `BAD_ARGUMENT`.

The reference device always leaves Resident off. These fields describe hardware
compute only. They grant no Linux whole-call portal authority, OS state/lease
ownership, single-worker admission or normal-memory eligibility. Those remain
independent platform gates.

## Gate Audit And Tests

The dispatcher requires AKV, v2, PV, four lanes, VLEN=1024 and RVVH; QK further
requires QK and RVVF. `ara.sv` forwards the same FPUSupport to dispatcher and
lanes. Lane/FUS/VMFPU gates add no unmet compile-time requirement; VLSU gates
are weaker (no FPU check). The shared reader and AKV engine are instantiated
without an additional QBS-enable requirement. FP extension support controls
reciprocal-related operations, not Resident FMA. Dynamic readiness, context
shape, legal rounding mode, faults and ownership are execution/admission checks,
not persistent compute capability bits.

The suite compiles the actual generated package with all 16 combinations of the
four enables. It extracts, rather than reimplements, dispatcher/lane/VLSU gates
and the actual FPU enum/RVVH/RVVF functions. Five lane counts, three VLEN values
and eight named FPU profiles produce 1,920 SV-to-SDK vectors. The actual SDK
decoder consumes those words. Host tests exhaust all 8-bit version/lane values,
all 16-bit VLEN values and every one-bit corruption; they check stale-field
clearing, old hardware, reference-off and native preservation. The existing
four SDK host tests run as regressions, plus C++ header compilation.

This is isolated capability discovery evidence, not a full-SoC, numerical,
performance, kernel integration or board acceptance result. Once shared with a
consumer, do not edit the frozen snapshot or any sealed consumer.
