# RVV-19 Original Gather Selection

Sidecar only; all writes are below this directory. No RTL/image edits, VCS
launch/build, ZCC, Verilator, URG or board execution. **Eight source ports are
built and Spike self-oracle checked; candidate03 DUT acceptance is pending.**

## Authentic Evidence And Duplicates

`C=/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01`.
The main `hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix/repro/ALL_FAILURE_REVIEW.md`
under `/home/wangwy/openproject/ara_dsa` lists 83 RVV-19 numerical records,
separately from 11 gather stalls. Its SHA256 is
`c72e20fc1f85d6ca670c9b182dac85bf366c141dbe79d890e57f71282a54caaf`.

Use `C/rvv_verified_handoff03/rvv_small_gather02`, not the early pending
`rvv_gather_symptoms01` (0/83 confirmed). The export and final
`rvv_gather_symptoms04` say **83/83 board-confirmed single numerical matches**.
Every exported case includes `scenario.c`, unchanged `operations.S` and
`operations.h`, `scenario.elf`, byte-identically rebuilt `original.elf`, and
`case.json`. The reduced C differs from `C/rvv_small_gather02/<name>/original.c`
by exactly one selected-trial filter; no oracle/init/assembly change.

All source/ELF hashes and raw original/reduced outputs were rechecked in
[inventory83.json](inventory83.json). Original C paths/hashes and exact
parent ELF identities are in [lineage83.json](lineage83.json).
The source manifest SHA256 is
`d3240e001a55d0e29db8db126ae47d602e988c585c6e064dcdffb2d91a5ca238`;
original-report SHA256 is
`7ed11ee7257c8571d8d5d4bf87780231d82fd5373173343598d21d47ed5aa00f`;
reduced board-report SHA256 is
`085fa554c8622267da59e5dac92e1a42d0d5e25cbf9cb743a4d6bfedb5a9d509`.

The 83 records are **80 opcode partitions plus three unsplit fractional
parents** (e8/mf4, e8/mf8, e16/mf4). There are 83 distinct SEW/LMUL/op keys,
not 83 independent causes: 16 shapes have op0/1/2/3/20, three have only the
first measured op0 tuple. The 80 children overlap their 16 full restart
parents (56448 configurations each); child matrices have2688 configurations.
`C/rvv_permute_partitions01/parent_mapping.json` verifies every child original
ELF SHA. Do not add parent/partition counts as independent coverage. The
fractional parent single does not cover its other20 opcodes. `rvv_small_gather01`
and verified03 copies repeat identities, not additional tests. No exact final
unreturned tuple is recovered for the separate11 stalled programs here.

## Current Repair And Accepted Control

Archived deployed `C/rvv_stall_archived_rtl/masku.sv:943-959` enables gather
bytes using vm/predicate only. Its SHA matches the deployed manifest:
`9d41dc028967ed5b639072073b2ab07db87254419c30d0eae6b7a558b79f926f`.
Live and frozen candidate03 `hardware/src/masku/masku.sv` both hash to
`1bc71bbb732a842d59fdcc48d4f44aa79f830f2bb11444923b15910b8d875f3d`.
Candidate03 snapshot SHA256 is
`382af2912634002ceecbaa44b8e8f0fb8262ab6aeb30e52d66a9bb0268508a2f`.

Static path: VALU indices/scalar override -> index and request FIFOs -> lane
MaskB source read -> deshuffled source element -> result queue -> VRF grants
and completion. Admission initializes issue count to VL; gather delta is1.
`vl-issue_cnt_q` is absolute destination position; `out_valid_cnt_q` resets
at each result word. Lines972-992 guard every SEW BE with position>=vstart;
data selection and end-token/completion are separate contracts. Out-of-range
index synthesis and no-data last tokens must not be attributed to this BE fix.

Prediction for a focused future failure: positions below vstart may still
fetch source data, but their VRF enabled bytes must be zero. Compare target
VID/op/VL/start, issue count, predicate bit, index/request FIFO handshakes,
MaskB data, result BE/data/address, final grants and done. Correct fetched data
with enabled prefix bytes discriminates a BE failure; wrong active data or a
missing final token discriminates selection/stream/completion failures.

Existing `integration/gather_original` is genuine e16/m1/op0 vv: expected91,
historical actual61881 at element0. Its original Linux ELF SHA is
`9269579c92731b2afaf8bc9e1e31a171856c90a1af262a1afb7b8c4ef803767a`;
reduced ELF SHA is
`89282306e501acc09c2303500f118bbd9b55e0c463b55da348674dc9bbbb2537`.
Its accepted SoC ELF is
`bc01908559122bca514fd150feffb467ea27a587057d7e1e378aafbd38a0157f`:
F4 `C/../current_board_integration_final04/campaign/gather/summary.json`
PASS29.52s; candidate02 `../integration/memory_regression_plan02/replay/summary.json`
PASS30.81s. These are not candidate03 gather PASS. Generic `gather_prestart`
is separately labeled board_tested=false, source1000+i/vx index0; it cannot
substitute for any of the83 randomized source records.

## Recommended Minimal Candidate03 Batch

Each suffix below names original `rvv_permute_restart_<suffix>`, reduced
`rvv_small_gather_restart_<suffix>`, and local port `gather_<suffix>`.
Exact original/reduced ELF and C/asm/header hashes are indexed by those names
in [inventory83.json](inventory83.json); local sources are byte-for-byte under
`prepared01/gather_<suffix>/original/`. [soc01/programs.json](soc01/programs.json)
pins the eight runnable SoC ELFs and required markers; Spike ELFs are separate.

| Suffix | Target | Selection reason | Expected elements0,1 |
|---|---|---|---|
| e16_m1_ops0 | vrgather.vv | Accepted original identity, new-image control | 91,538 |
| e8_mf8 | vrgather.vv | Smallest archived fractional group; EW8 BE | 91,26 |
| e16_mf4 | vrgather.vv | Fractional e16 parent | 91,538 |
| e16_m1_ops1 | vrgather.vx index0 | Genuine scalar-index source | 91,61881 |
| e32_m1_ops2 | vrgather.vi index0 | Immediate form; EW32 BE | 91,1784607161 |
| e64_m1_ops3 | vrgather.vi index31 | Out-of-range, VLMAX16; no-data completion | 91,0 |
| e32_m8_ops20 | vrgatherei16.vv | Eight-register data; index EMUL4 | 91,2738160154 |
| e64_m8_ops0 | vrgather.vv | Eight-register e64 setup; EW64 BE | 91,2557299195215413786 |

All eight are **one original call**, VLEN1024, seed0/scalar0, VL2/vstart1,
mask mode0 (all-on), tu/mu, old destination91. Original xorshift seed
0xe736815b449aec21 and shifts13/7/17, truncated to SEW, are retained. Vector
indices start0,1; EI16 indices use the original separate uint16_t array.
Assembly loads full-capacity v8, indices v16, old v24 and v0, sets VL2,
writes vstart1, executes target, reads returned vstart, then stores full
capacity. The complete original oracle checks every capacity element,
prestart/tail91, both guard elements and returned vstart0. No SKIP is PASS.
Capacity is16/64/32/256/128 as appropriate; wide setup does not mean VL2
crosses a result word. Independent scalar tuple checks pass for all83.

## Prepared Status And Remaining Work

[prepare_batch.py](prepare_batch.py) uses the existing integration adapter,
runtime/startup/linker and installed GCC, with scalar auto-vectorization off.
Only Linux entry/write/exit and TIOCOUTQ are adapted; original scalar loop
bounds, asm and full oracle remain intact. [test_sources.py](test_sources.py)
passes3 host tests (83 filter-only lineages, independent83 tuple values,
source/runtime/ELF pins). [reference01/reference.json](reference01/reference.json)
records8/8 Spike HTIF exits0 after the required vstart probe, about0.035s each.
Spike diagnostics stay in RAM: these are self-oracle exit checks, not printed
marker evidence, same-ELF RTL differential checks, or Linux/board acceptance.

Parent may run the eight SoC ELFs on the already-built sealed candidate03
image with normal admission/pin checks, exact markers, failure-marker veto,
exit0 and complete commit CSV. No launch is authorized by this document.
Estimate30-120s/case, **4-16min serial**, extrapolated from the original control,
not measured for these new ports; retain existing300s/case wall bound
(40min maximum serial plus overhead). Preserve independent background output
and inspect after completion if a batch is expected to exceed10min; no polling.

Passing this batch covers eight exact singles (seven new versus F4/M2), not
all83. Another75 measured singles, other seeds/masks/VLs/restarts, in-range
index31, EI16 enlarged index EMUL, cross-result-word architectural tests,
full original parent/partition matrices, Linux ABI/board replay and11 stalls
remain separate. No repeated generic framework or full-matrix batch is needed
for this first admission.
