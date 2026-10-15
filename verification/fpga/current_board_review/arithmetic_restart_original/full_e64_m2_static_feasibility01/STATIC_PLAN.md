# e64/m2 Full Original Static Feasibility

Status: STATIC ONLY; no Host, compile, reference or DUT admission.
ANALYSIS.json records actual primary hashes, source mapping and helper bytes.
Archive: /home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_extended04.
Use original overlay/opt/ara-tests/rvv_matrix_e64_m2, rvv_matrix_e64_m2.S
and e64/operations.h. recovery22/report.json proves reconstructed C's exact
ELF/disassembly identity. Original C bytes themselves are not recovered.

## Full Source Contract
Actual vtype0x19, SEW64/CAP32/LMUL2, physical groups v8..9/v16..17/v24..25
each256B. Preserve35ops/5985calls:4095 integer+1890 FP,191520results,
11970guards,5985vstart,77805helper instructions.
Checked output272B is34 whole uint64 words (203490 total reads).
Sentinel/guard bits000000000000005b, NOT repeated-byte/halfword005b.
Four64B blocks plus16 valid bytes: last result offset256, last guard264.
No4B tail/LW and no reading padded48B. Mask physical128B/actualvlm4B,
upper124B zero. Retain original mask reuse, RNG, seed/order, helper and
CAP32 gather boundary. Keep original per-element C fallback/failure policy.

## FP64 Oracle
640 original uint64 expected words match uniquely in ELF at file0x1560,
virtual0x11560. No host-float evaluation.
Input8-word sequence appears five times; actual input is virtual0x11520,
bound by original LUI/ADDI, stack120 and indexed+704 load instruction chain.
Do not claim global uniqueness of the input bytes.

Every FP call refreshes a[i] then b[i], i0..31 before output/helper:
64words/call,120960 stores/967680B; identical refreshes cannot be deduplicated.
Next seed restarts original RNG and integer initialization before op0.
Preserve original13-instruction helpers and vstart setup/readback.
Original source does not check fflags/frm. Preserve CSR history, do not invent
flags acceptance or clear sticky flags as an optimization.

Frozen M9 ara_testharness does not override ara_soc FPUSupport.
ara_soc defaults to HalfSingleDouble, ara_pkg111000/RVVD bit5 and cfg.RVD
demonstrate FP64 support path, not acceptance of this e64/m2 workload.

## ROM and Stack
One block64 dictionary,5 uint16 indices/call:
1282blocks/maxindex1281,82048dictionary+59850indices+384mask+5184original
FPtable/input =147466B. Flat1627920B exceeds1MiB.
No checksum, omitted result, input refresh, fresh init, guard or call.

Pre-link budget only:147466ROM+24744original globals+16384runtime+
65536code/other readonly+65536stack =319666B <1MiB.
Globals: a8192,b8192,out8208,mask128,counters24B.
Actual map/ABI frames/stack gap must be verified after separate authorization.
Use aligned uint64/raw memcpy, not unaligned cast or alias tricks.
This static inventory is not software-equivalence or linker/stack proof.

## Cost
Accepted full e64/m1 -O2:4528858 firmware instructions and M7
7544.534203s (~600retires/s), CAP16; -Os reference5908244.
Neither is the new packed CAP32/M9 measured cost.

Original e64/m2 FP-refresh loop10488..104bc has22 instructions/element:
32*1890*22=1330560 instructions for this phase alone.
Packed output alone requires203490stores+203490outputloads before
ROM loads/comparisons/control/helper/input refresh.
Illustrative assumptions:200..250instructions/call +2205maskgroups*200
+30000setup +1330560refresh =2998560..3297810.
NOT a bound: compiler lowering can differ. <=3M is not proven and may fail.
Source/ROM feasibility does not imply reference-cost feasibility or timing.

Next safe action requires separate authorization for original-C equivalence/UB
Host, actual compile/helper/no-extra-RVV/map/stack proof and cost review,
then independently reviewed bounded reference if budget permits.
No such stages executed or admitted here. Running/sealed artifacts untouched.

## Retained Failure
INITIAL_STATIC_CAUSE.json retains the initial overstrict uniqueness matcher
failure for the input8 table. Narrow successor binds actual input address;
unique640-word oracle requirement and all expected bits remain unchanged.
This is static observer failure, not Host/firmware/DUT failure.

