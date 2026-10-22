# Original zero-stride e64/m4, continuous16

**Software and reference complete; no VCS/DUT acceptance.** One uninterrupted
Sv39 program runs all sixteen original configurations. There was one software
build per backend and one Spike invocation, no retries or partition resets.

## Actual result

- Spike numeric child wait rc **0**, 39.1051603 s, no timeout.
- Full raw trace: **270381207 bytes**, SHA
  `b26941b031b25aa6e5be2d03b95e296d299293f647d7733136d049d11ec4a2ad`.
- Full retired-code/data observer: **2165648 firmware instructions**,
  **19212 scalar comparisons**, **72 full-byte checkpoints**.
- **16 helper calls**, **12 page faults**, **12 same-PC retries**, **16 S ecalls**.
  The four all-off cases have no vector fault. Load cause13/store cause15;
  all fault tval values are `0x40001000`, starts are 0/1/2 by mask.
- Original final oracle: **1024 output elements, 32 guards, 16384 uint64 memory
  words (8 KiB per case), 16 returned-vstart checks**. All returned starts are0.
  Eight upper-page refills include the two unmapped all-off configurations.
- Host: 17424 independent C/Python oracle rows; 72 checkpoint positives and
  25 rejecting mutations. Undefined fault suffix remains unconstrained.
- `reference01/execution.json` was persisted before raw analysis;
  `reference01/status.json` is this executor's complete strict reference result,
  not a second agent's independent acceptance. Pre/post input pins unchanged.

The scalar check total is independently accounted as 20 initial/final checks +
16*1164 case checks + 28*13 trap-context checks + 12*16 snapshot-guard checks +
12 prestart checks = 19212. The full observer also checks the complete unused
allocation tails, mask, offsets, page-table neighbors, prior-case records and
initial/fault/repaired/pre-cleanup/final physical memory.

## Source identity and exact scope

Canonical source:
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_zero_stride_reference57/source_nf1_m4/`.
The original ELF `rvv_fault_replay_strided_zero_stride_e64_m4`, SHA
`f9ef7eecca757fe9f006a325e73fcd814afc89ea6b615afbd20fc357846b30ec`,
matches both additions57 and the actual recovery08_41 terminal-scene ELF.
Original `fault_replay_oracle.c`, generator, manifest, archived assembly and
all three ELF identities are pinned in `software01/source_proof.json`.

Order is protected LOAD masks ff/aa/24/00, protected STORE the same masks,
unmapped LOAD, then unmapped STORE. No guessed inner failing trial is claimed.
The historical last trap is load PC0x10846 / `09c57c07`, cause13,
tval0x3f87fed000; kernel head was a vstart CSR read. Head visibility alone is
not an accepted CSR handshake or proof of a new M6 root cause.

The original 3 capacity + 10 load + 10 store instructions match byte for byte
after relocation. All three compiler-generated sigaction RVV initialization
instructions also match. Source64/mask64B/output514/offset512 allocations,
cap64, VL8, vtype26, zero t3 (not architectural x0), uniform source101 and
typed uint64 seed0x5b are retained. Original guard is output65, not output513.
Actual full allocation is additionally checked, without weakening these guards.
No random initialization exists in this source.

Linux mmap/mprotect/munmap/signal-frame transport is replaced by real Sv39
S-mode access and M-mode handling. Relative page geometry is unchanged; a fixed
VA replaces the Linux allocator's chosen VA. The handler reads vstart/type/vl
before diagnostic RVV, observes only the original defined prestart fault
prefix, repairs the page, and restores the original PC/base/t3/start. Snapshot
stores do not modify v24-v27. The original poison loop is retained and naturally
does no writes because no active element precedes the first active fault.
No fabricated warmup or physical reset separates cases. Unused offset setup is
retained explicitly even where the archived compiler could remove it.

This is **not** Linux signalframe/sigreturn equivalence, physical MMU/AXI-count
proof, closure of all three old Linux stalls, or the separate VL9 mask-drain
candidate. No DUT, live simulation query, RTL edit, or SoC build was performed.

## Handoff

SoC ELF: `software01/soc.elf`
SHA `d719042343a32e41c31442bb77d4464bce3b09bb7aa3104e03726068a2d29c46`.
Spike ELF: `software01/spike.elf`
SHA `2042734d6765f7258c9593ca20c78621c93cdaef070587db24a4d0fa58bbc1b8`.
SoC load/store target PCs: **0x80000f44 / 0x80000f6a**.
Spike load/store target PCs: **0x80000f4c / 0x80000f72**.
ISA actually used: `rv64gcv_zfh_zvfh_zvl1024b`, Sv39 with `--priv=msu`, no PMP.
Exact command and numeric outcome are in `reference01/execution.json`.

The reusable no-build DUT target is explicitly frozen
`/home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image`,
not the current worktree. The parent subsequently added a VLDU
`DRAIN_EXCEPTION_MASK` candidate; **M6 does not include that change**.
Any later M7 comparison must reuse this ELF and separately pin its image.
The Spike observer must be connected to the existing RVFI adapter before a
strict VCS run; this directory does not launch or claim a prepared DUT service.

Using the related measured M6 negative-STORE rate (851704 instructions /
1111.624555705 s), the actual new instruction count projects **47.1 minutes**,
or **56.5 minutes with20% margin**. A slower273/s proxy with20% margin gives
**158.7 minutes**. Both are estimates, not guarantees: zero-stride transactions
and scalar division can change the rate. This supports a bounded under3h
single-program proposal without shrinking the original scope. No DUT timeout
has been changed or simulator started.

`READY.json` and `evidence_pins.json` bind the completed software/reference.
Do not rerun `prepare.py run`: the existing reference directory enforces the
one-attempt contract. Any correction must retain this original evidence.
