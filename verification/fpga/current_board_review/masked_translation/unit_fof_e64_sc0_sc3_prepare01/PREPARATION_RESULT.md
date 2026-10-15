# e64 sc0/sc3 Preparation Result

Status: **Host + Spike accepted; no DUT run; independent entry review pending.**

READY SHA256: `8c2f89e677e1cf6148ad3d1013f1598a91ed77506a73266603d956ffe9672e1e`.
Input ledger: `input_pins.json`, SHA256
`7dd02dd132831300bf54e7f3310833b3bd2d8aa05cc180a043adb1f212a1d1b6`,
725 pins checked, including frozen M9 source/image, original archive source,
compiler/Spike, shared utilities, both new ELFs and actual reference evidence.

| Original single | Actual Spike rc | Firmware retired | Scalar checks | Spike time | Returned VL/start |
|---|---:|---:|---:|---:|---|
| e64/sc0 FOF active page crossing | 0 | 172761 | 5477 | 3.027 s | 4/0 |
| e64/sc3 ordinary alloff protected page | 0 | 172547 | 5481 | 3.027 s | 8/0 |

Each final ELF had exactly one Spike invocation with 800000 instructions,
120 seconds and 256MiB bounds. No timeout or retry. Both actual HTIF exits
are 1 (successful Spike endpoint), and neither target caused an architectural
trap; each has exactly one later completion S-ecall. The SoC ELFs use their
actual CTRL-address zero exit instead, never a fabricated `tohost` symbol.

Host: one 12-test suite, actual rc0, 23.420 s; both native C oracle outputs
matched 2836 independently computed rows each. Negatives cover defined output,
initial/final guards, mask, source and protected memory, page tables, returned
VL/vstart, exception context, helper-PC substitutions, endpoint, and all four
owner allocation/completion pairs, including deletion of an entire non-target
pair. Synthetic lifecycle tests are not DUT observations.

Original assembly and helper machine-code identities are preserved: selected
11-instruction helper once, capacity three instructions, and zero execution
through the unused helper. All130 output elements are initialized to scalar
0x5b. Both full checkpoints include 8KiB data, 12KiB page tables, surrounding
guards and16 mask bytes. sc0 final out[5..8] alone is undefined in the original
oracle; final126 allocation elements remain strict. sc3 checks all130 final
elements, including all eight original outputs. Source guards are out[0]/out[9].

The FOF target returns VL4, but the original helper restores VL8 before the
eight-element output store. Post-helper/completion context is therefore VL8;
it must not be substituted for the immediate returned VL4 check. The fixture
also checks returned start0, full handler context and14 CSR-restoration
readbacks. The DUT checker preserves those scalar observations and requires
four nonempty memory owners, three of them non-target helpers. Generic trace,
console veto, actual numeric child exit, and image/source pins remain required
for a future worker; preparation does not assert they were measured on DUT.

Evidence: `software01/scenario{0,3}/source_proof.json`, `host01.json`,
`reference_scenario{0,3}_01/{attempt,execution,status}.json`, and their pinned
raw traces. All preparation commands (build, host, each reference, finalize)
returned0. Tesla was sent the exact READY and owner-checker identities for
short review. Current sc1/2 PASS was reported by the parent; no prior scenario
was queried or rerun here. No production RTL or sealed predecessor was edited.

Scope remains two source-derived real-Sv39 singles, not Linux fork/wait/signal
closure or all parent scenarios. Architectural no-fault does not alone prove
zero MMU/AXI requests. Future DUT runtime is not measured for these ELFs; the
parent's sc1/2 measurements (265/279 s) suggest a similar order of magnitude,
not a guarantee and not justification for altering an existing budget.
