# Directed Native AKV Gate

New firmware and checker only; the sealed model, adapter, QBS implementation and
QBS smoke gate are untouched. Building this directory never launches QEMU.

The finite synthetic fixtures cover v1/v2 lifecycle, query/descriptor snapshots,
REFILL retaining Q, row/K/V column/panel4 layout and byte tails, RELEASE, frontend
preservation versus backend poisoning, real M-mode traps, RAM-boundary and MMIO
read faults, same-context recovery, resident active heads, query bases, dimensions,
token tails, signaling/quiet NaNs, FRM0..4 midpoint rounding and sticky flags.
Representative geometry is D64/T1/H1, D96/T2/H2, D128/T3/H1, D64/T17/H2 and
D128/T64/H2, not a Cartesian sweep. No-context recovery alone reloads; frontend
errors and resident field/context errors reuse the already loaded context.

The numerical expectations are exact dyadic results and explicit IEEE midpoint
and canonical-NaN constants. They do not import `akv_model.c`, use a software
Attention implementation, or replace the unchanged Stage4 independent oracles.
Positive resident captures read only active destination elements. Negative
captures immediately read a nonuniform EW32 sentinel after recording/restoring
software CSR state. Source/unrelated registers receive independent byte guards.

Modes: 0 requires both AKV controls; 1 disables only resident AKV; 2 disables
AKV entirely. The two negative-control modes are separate ELF variants, not
adaptive skips. All use ordinary RVV and finish with a real vector-add check.
The existing QBS executable/trace smoke remains a separate required gate.

`start.S` installs a private scalar trap handler. It requires armed exact EPC,
cause and tval, records raw mstatus, restores FS/VS before returning, and advances
only the known 32-bit custom instruction. Unexpected traps fail EOC immediately.
No synthetic retires or architectural END events are invented. Memory callbacks
can throw with BEGIN/no-END; the checker accepts that only for the explicitly
matched guest access-fault cases followed by poisoned replay/recovery checks.

Build with the pinned GNU compiler using `build.py --output` and a fresh direct
signoff output. Each image retains sources, oracle, instructions/ELF addresses,
commands and logs. Review the build and the separate QEMU image/pins first.
There is no guest launcher in this directory. Parent owns any launch approval,
bounded service/exit checks and image/source pre/post identity. `check.py` only
accepts guest output and real `akv_arch_*` trace against the frozen firmware;
its result explicitly does not claim QEMU image or service-owner acceptance.

Runtime contract is the adapter README's opt-in Stage4 transport, entry
0x80000000, one hart, 16MiB RAM, UART byte writes at0xc0000000, and EOC raw0 at
0xd0000000. Test MMIO is the existing virt UART at0x10000000; no guest setup code
reads it. The RAM-end fault address is0x81000000. Reserved high RAM payloads do
not overlap the private stack at0x80fe0000. These are architecture tests, not
RTL timing, bus-drain, model-speedup, production-admission or FPGA evidence.
