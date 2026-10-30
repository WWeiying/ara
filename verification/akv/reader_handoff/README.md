# Reader Handoff Fixture

Preparation only. Synthetic finite Q4_K/Q8_K M1/N3/Kb1 controls and distinct
F16 bit patterns, not a model capture or a timing benchmark. Requires actual
QBS context and AKV-v2 capabilities, four lanes and VLEN1024. Missing capability
is FAIL, never SKIP. No runtime library is needed: link main.c and probe.S with
the existing GNU baremetal common startup, printf/serial/util and linker script.
The default main exposes `rvtest_init` for the existing startup hook.

## Sequence and Raw Acceptance

1. Normal RVV load/add/store. AKV FULL epoch0, then poison all external Q/K/V.
2. Check all eight resident rows (Q2/K3/V3), each 128 bytes.
3. QBS DIRECT success -> AKV Q1, then check all eight resident rows.
4. QBS DIRECT with weight_base=0 -> AKV Q1, then check all resident rows.
5. QBS DIRECT retry with valid weights -> AKV Q1, then check all resident rows.
6. QBS FILL generation0x35 -> AKV Q1, then poison the external activation.
7. AKV FULL epoch1 with different Q/K/V payloads, then poison their external
   backing and check all eight rows. This FULL uses the real memory reader
   between QBS FILL and REUSE, not just the local replay path.
8. QBS REUSE -> AKV Q1, then check all resident rows; QBS RELEASE -> AKV Q1,
   then check all resident rows. Both receive activation_base=0 and must still
   return the original activation's exact result, not the poisoned input.
9. AKV RELEASE, normal RVV load/add/store and exact final accounting.

Exactly 6 QBS commands: accesses `[DIRECT,DIRECT,DIRECT,FILL,REUSE,RELEASE]`,
with only the second faulting. Exactly 65 AKV commands: 2 FULL, 62 LOAD and
1 RELEASE, all successful. No AKV REFILL/column or seeded-QBS instructions.
Guest checks all 32 QBS destination words per command (192 total), all 64 F16
elements per AKV load (62 rows), and 64-byte guards on both sides of outputs.
Each QBS command is followed by an AKV Q1 load into v16 with no intervening
normal vector memory request. QBS v8 is then stored without being overwritten
by the AKV load. t0/t1 sentinels must survive, including through the trap.

The expected single trap is cause5/tval0 at the exact `rh_qbs_site` instruction.
The trap handler preserves all registers it uses (t0/t1 and sp), leaves FP and
vector state untouched, and advances four bytes. All intentionally faultable
custom instructions are fixed-width `.word` instructions. This is a bounded
fixture trap handler, not a general handler for arbitrary compressed faults.
An unexpected custom-instruction trap fails the stage checks.

The guest cannot identify the reader's fault enum from mcause alone. The SoC
checker MUST require the second QBS record to have fault=1, success=0,
validation_fault=0, nonzero read_fault and no destination commit; all other
QBS records must succeed. Also check the exact access sequence, context
fill/reuse/release accounting, and zero activation AXI reads on REUSE/RELEASE.
Record the actual read_fault enum (weight address0 may be rejected by PMA);
do not label this an injected AXI RRESP error without raw evidence.

QBS's own fault precedes FILL. No claim is made that a QBS context survives its
own fault. AKV payload must survive QBS success/fault/retry; QBS activation
must survive successful AKV commands. The fixture does not inject an AKV fault.

`vmv.x.s` drains older vector work under the current sequencer rule in
hardware/src/ara_sequencer.sv (VMVXS waits for older running instructions and
mask completion), followed by a fence before C checks. The consuming builder
must pin this RTL, the ABI headers, common startup and these fixture sources
against the accepted image. UART PASS alone is not ownership/drain evidence:
retain the independent UVM/AXI/VRF checks and boundary wave profile.

## Host Checks Only

From this directory: `python3 -B -m unittest -v test_reader_handoff.py`.
The tests inspect source contracts, decode instruction fields, compile both
sources using GNU `rv64gcv` with `-Wall -Wextra -Werror`, and perform a relocatable
link/disassembly check in a temporary directory. They do not execute the fixture
or launch any simulator. Exact compile flags/tool path are in the test.

## Bounded SoC Execution

The fresh full ELF is built from the sealed GNU strided-attention build's
startup, link policy and accepted16 MiB simulator identity. Unused predecessor
workload sections are removed by linker garbage collection. The build receipt
is `READER_HANDOFF_BUILT_NOT_EXECUTED`, not a simulated PASS.

```bash
python3 -B verification/akv/reader_handoff/build.py \
  --base verification/out/akv-quantkv-strided-attention-q8-build-20261024-01 \
  --output verification/out/reader-handoff-build-20261024-01
python3 -B verification/akv/reader_handoff/run.py \
  --build verification/out/reader-handoff-build-20261024-01 \
  --output verification/out/reader-handoff-baseline-20261024-01 \
  --timeout 900
```

Output directories must be new. A long-running worker must be owned directly
by a user service, with separate stdout/stderr logs. The900-second bound applies
to simulation; extraction and independent checking follow afterward. No RTL,
testbench or simulator recompilation is performed by this worker.

The original image's UCLI FSDB support has been tested for20 ns. All134 required
control/metadata signals exported successfully, with10 negedge samples and
zero missing signals. The initial reset sequence deliberately pauses the
clock, so10 samples in20 ns do not imply a2 ns steady-state clock. The current
TB's running clock is1 ns; after the first command acquisition, the checker
requires consecutive samples10000 units apart at100 fs/unit.
Capability evidence: `../results/reader-handoff-wave-capability-20261024.json`.
This run executes no vector requests and proves no functional handoff.

`wave_profile.py` generates explicit signal dumps, not recursive SRAM dumps.
Capture is bounded to500 us and then disabled; normal execution continues.
If the program finishes earlier, the simulator closes the dump naturally.
An incomplete capture cannot pass: the wave checker requires every one of the
71 acquisitions and terminals plus the final owner exit.

The wave checker follows acquisition, uninterrupted ownership, terminal and
exit. It rejects missing samples, reset during the sequence, a nonempty reader
or registered AXI cut at acquisition, late counter/subrequest reset, incomplete
storage writes, or premature fault publication. Resident metadata is saved at
the original owner's terminal and checked across idle, acquisition and the
other owner's first and subsequent cycles. This is settled-negedge evidence,
not an assertion of equivalence with a pre-NBA posedge monitor.

For this fixture the expected reader fault is exactly `QBS_READ_FAULT_PMA=5`,
address0, on the second QBS command. The worker separately requires original
program checks, exact QBS/AKV hardware work, full wave checks and independent
UVM/AXI/trace identity checks, with source/image/tool pins before and after.
The tool inventory includes the `fsdbreport` entry, its wrapper and platform
exporter implementations; the basename-sensitive wrapper remains the invoked
entry. A failed prerequisite or checker must not be relabeled as PASS.

This fixture still does not exercise a fault while AR is stalled, an AXI error
response, or an AKV fault. Those remain distinct reader/handoff regression
requirements before accepting shared-reader hardware. The current test changes
no hardware organization and measures neither area nor performance.
