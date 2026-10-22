# Independent Existing-Wave Boundary Review

Decision: **DUT mixed-EEW indexed-address failure, not fixture/runner/timeout**.
This adds measured evidence to PILOT_FAILURE.md's preliminary hypothesis.
No new DUT/host test, RTL or frozen-input change. Tesla's completed compact.vcd
was independently hashed and parsed, not merely its wave_fields.json read.

## What Is Measured

Raw CSV: attempt16 (17th target) arch_start cycle367643, request/exception
cycle367681, opcode0645f207. Its actual request starts at **vstart15**, not16;
16 is the subsequent fault's vstart CSR. Same target mepc0x80000d64.
Check160 at cycle368106 fails because real mtval read at cycle367806 is
0x400040017000 rather than0x40017000. Earlier faults0..15 and16 normal MRETs
are correct. Controls did not run.

Existing waveform independently shows:

| Time (ns) | Observation |
| --- | --- |
| 367660.5 | AddrGen pe_req_q: vstart15, eew_vs2=3(EW64), old_eew_vs2=2(EW32), vs2=v4, base0x40000000. Notebook v4=EW32/v5=EW64; dispatcher snapshot-valid0 and replay0. |
| 367663.5 | Four lane operand_queue_input[SlideAddrGenA=8] = [0x17000,0x4000,0x11000,0x1e000], exactly original indices16..19. Each input-valid vector=0x100 (queue8 valid); every snapshot-replay-valid vector=0. |
| 367664.5 | idx_final_vaddr_q and mmu_vaddr_o=0x4000a000, mmu_req_o=1: correct index15. Request vstart15/old_eew2 remain. |
| 367678.5 | idx_final_vaddr_q and mmu_vaddr_o=0x400040017000, mmu_req_o=1: bad index16 address, before MMU translation/CSR transport. Same request vstart15/old_eew2; replay remains0. |

At the bad MMU request, current lane input-valid is0; its stale current input
data is NOT substituted for the previously observed valid packet. Queue8's
valid original packet is observed separately at367663.5ns. Input-valid is not
claimed to be the AddrGen output-queue consume handshake.

## Causal Interpretation And Limit

The request starts in v4's EW32 physical layout, then crosses to v5's EW64
physical layout, while AddrGen keeps one old_eew_vs2=EW32. Frozen addrgen.sv:296
uses that field for the whole packet deshuffle. The four-lane EW32 byte mapping
combines lane0 low32 with lane1 low32, yielding
`(0x4000<<32)|0x17000 = 0x400000017000`; adding the correct base gives the
measured bad MMU VA exactly. This is not an active snapshot replay, a corrupted
initial index/RNG, a firmware compare-width problem or a downstream mtval-only
error. Pure snapshot-valid clearing alone was not used as evidence.

The captured profile lacks actual addrgen_operand_i/valid/ready, reduced_word,
deshuffled_word and word_lane_ptr. Therefore the precise internal FIFO consume
cycle and earliest bad combinational node are not directly observed. The
mixed-layout/single-old-EEW mechanism is strongly wave-supported; an exact
production repair still must preserve correct per-register physical layout
through this crossing, not just overwrite old_eew with a preferred constant.
No new run is needed to establish DUT versus fixture or pre-MMU localization.
If further measurement is later needed for a proposed repair, add only the
missing AddrGen queue/deshuffle/consume fields to a fresh delayed profile;
350000..375000ns includes this entire discriminating request history.

## Identity And Time

Compact VCD SHA256 `29a24efcf755398f675bac774addf6d565a4bb172748c1d8e03888058f9d6192`.
Original FSDB SHA256 `097b549514adaf71d680a96ce1b243eee115ebf8f62335587c59f39a6cb81fe8`.
Its100fs timescale makes3574300000 ticks =357430ns. Original first1Mns capture
was still active at failure and contains the target/17 faults; it did not
complete the planned32-fault round. No waveform-miss or full-round-coverage
claim is made. Full50-round/three-case acceptance remains NOT_PASS/NOT_RUN.

Exact sampled fields and raw hashes are retained in wave_boundary.json.
