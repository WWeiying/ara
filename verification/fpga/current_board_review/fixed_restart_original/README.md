# Original Fixed Restart:777-Call Prefix Prepared

**Status: host and Spike PASS; no DUT execution or launch plan.** FP08 was
not inspected or polled. No RTL, shared helper or existing sealed input was
modified. All new files are owned by this directory.

## Original Identity

Archive: `/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_fixed_restart01`.
Original program: `rvv_fixed_restart_e8_m4`, four fixed-point operators,
10752 total calls in its full original source configuration.

- Original ELF SHA256:
  `ca6937f7969cb2664becfe53fac5e49111415929e96220874568964b293b85cc`.
- Required historical C SHA256:
  `b50d3298db2c10f35a5a286f4db01d8b32603afdfc0a0ad1a5b0d3df087e56bc`.
- Surviving C SHA256:
  `ab82b4891f9e926e37ef4d9f10fc44b0f953136deef2173b84427c0447e81006`.

Old C bytes were **not** recovered. Instead, the unmodified surviving C,
original S/header and original fixed.py compiler flags rebuilt the complete
original Linux ELF byte-for-byte on the first attempt. No optimizer or
source-tuning search was used. This establishes binary-equivalent source
for this exact original configuration, not for other suites/macros.

Proof: [recovery01/report.json](recovery01/report.json), original/rebuilt
disassemblies and build command alongside it. The archive copy and delivered
`rvv_additions33/binaries` copy both match the required ELF hash. The selected
historical report hash is checked against `stall_family_triage02/triage.json`.

## Correct Boundary

The historical printed record is:

```text
RVV_TRIAL seed=0 vl=512 mask=0 vstart=256 completed=776
```

`checks` counts **completed** full-oracle calls and the print occurs before
the next operation. Thus the requested contiguous prefix includes calls
0..776,777 calls, not776. The index is:

```text
6 preceding VL positions * 4 predicates * 4 starts * 8 controls
+ 1 preceding start * 8 controls = 776
```

Last tuple: seed0/op0 `vsmul.vv v24,v8,v16,v0.t`, e8/m4, VL512,
mask mode0, vstart256, vxrm0, initial sticky vxsat0. Every predecessor is
retained, including duplicate no-op start/VL combinations and all original
input/RNG/setup effects. Prefix controls include195/194/194/194 calls for
vxrm0/1/2/3 and389/388 with initial vxsat0/1.480 calls have vstart>=VL.
All777 are seed0/op0; this prefix does not execute the other three operators
or seeds1/2. The original summary's `seeds=3` is retained unchanged and is
not a claim that the bounded prefix executed three seeds.

## Faithful Port and Checks

Only the Linux wrapper and the after-oracle prefix stop are adapted.
Write/exit/startup use the existing bare-metal runtime; Linux tty drain is
an explicit no-op, so Linux scheduling/tty timing is not reproduced. The
host-only vlenb replacement is excluded from both vector ELFs.
The original full-capacity data, prestart, masked-off, tail, guard, returned
vstart and sticky vxsat oracle is retained without weakening.

`prepared01/prepared/runtime_adaptation.diff` and `bound.diff` record these
changes. Original S/header bytes are unchanged. All24 instructions of op0,
including operand loads, CSR save/setup/read/restore and final store, match
the original Linux helper's instruction bytes in the SoC ELF.

- Host: bounded prefix and unbounded-source first777 calls match every
  input hash, order, VL/start and vxrm/vxsat control against independent
  enumeration. Both scalar-oracle runs PASS.
- Nine injected errors are rejected: active, prestart, masked-off, tail,
  both guards, vstart, lost sticky vxsat and spurious vxsat.
- Spike: original777-call oracle PASS,397824 elements checked, zero errors;
  raw failure veto and all four completion markers checked. The completed776
  boundary is present in the reference log.
- Software reference cost:16249331 retired instructions to replay_exit,
 16249331 Spike cycles,2.575 seconds host wall time. These are not DUT
  throughput or an authorized DUT timeout.

## Prepared Artifacts

- [Scope and historical record](prepared01/scope.json).
- [Host evidence](prepared01/host/status.json).
- [Spike reference](prepared01/reference/status.json) and raw `spike.log`.
- [SoC ELF manifest](prepared01/soc/programs.json).
- [Final self-audit](audit01.json):83 pins unchanged, helper instruction-byte
  identity, exact scope and address mapping.

Original target PC: `0x1094e`; SoC target PC: `0x800008d2`;
opcode `9c880c57`. SoC ELF SHA256:
`ff8fddb67699469c774e1e55f389e6df52b82f5fbe910d634e72bd139cb13260`.
Spike ELF SHA256:
`62717595c4443e097ed15a6211293d20a5a43c0bc7daaa6dd7fd5aaf20a0fdd5`.
Input pin-ledger SHA256:
`e6588bcee4dbbc55772acf3e9f591c3683b72a368026af1c9cac9c4e19648d09`.

There is no remaining source-equivalence blocker for this selected prefix.
There is still no current-DUT acceptance, no full10752-call acceptance, no
execution of the unmodified original Linux ELF, and no proven stall root
cause. A future DUT run requires separate parent review and authorization.
