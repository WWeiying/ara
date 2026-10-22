# e32/m8 Static Counterpart

Status: complete original identity/geometry identified; retained scalar
contract cannot fit3M. This is not an RTL failure or M9 acceptance.
No Host, compile, reference, DUT, live CPU/CSV query or sealed-file edit.
The e64 report/evidence were not rewritten or rerun. No6h authorization is
inferred from the user's pending budget choice.

## Actual Original Material

Archive C: /home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_extended04.
Review A: verification/fpga/current_board_review/arithmetic_restart_original.

- C/overlay/opt/ara-tests/rvv_matrix_e32_m8 and A/recovery22/rvv_matrix_e32_m8:
  SHAab307903f1da301801731456464a9358f5f85a0bb4cdcff1a7657f88a833f8f2.
- C/rvv_matrix_e32_m8.S:
  SHA562ee87b61684f0d53d2ca9ee85cd5e1c2fba9964c1f43ee335fdbf84be332dd.
- C/e32/operations.h:
  SHA2b3cce9dcdaaa6bc6e556ae4d2c013325ed48c473858c1984751c867a58f4b7b.
- A/recovery22/report.json records exact ELF/disassembly reconstruction;
  A/recovery22/reconstructed_oracle.c is binary-equivalent reconstructed C,
  not verbatim lost-source recovery.
- A/recovery22/rvv_matrix_e32_m8_decode/original.dis and actual ELF uniquely
  match all35 original48B/13-instruction helper sequences. Capacity3 plus
 35*13=458 static helper instructions. All106 vsetvli select actual0x13.
- The original FP expected table is640 uint32 bit patterns/2560B, uniquely
  matched inside this ELF LOAD; offset/VA/hash are in E32_M8_STATIC_EVIDENCE.json.
  Header constants use UINT64_C syntax but actual SEW32 word serialization
  is4 bytes, not the e64 table's8. No host-float computation.

C/resume03_report.json records historical board PASS/exit0/5.4763349001295865s,
CAP256/cases5985/elements1532160/errors0. This does not replace current M9
full regression or close the current all22-shape objective.

## Geometry and Complete History

At VLEN1024, actual e32/m8 vtype0x13 gives CAP256 and1024B physical groups
v8..15, v16..23, v24..31. No legal v32 upper-neighbor snapshot exists.
Original lengths0/1/2/3/128/255/256; three seeds,35 ops, three mask modes,
original kind-derived one/three starts give5985 continuous calls:
4095 integer and1890 FP. Results1532160, guards11970, vstart5985,
helper77805. Preserve seed RNG, nextseed restart, gather CAP256, fallback,
CSR/history and all13 helper instructions; no shortened scope.

Each call initializes/reads/checks258 uint32 values=1032B, legally packed
as129 whole64-bit words, total772065 SD/LD operations each.
Typed sentinel is0x0000005b; packed SD sentinel0x0000005b0000005b.
First word contains guard0 and first result4; final word1024 contains last
result1024 and guard1028. There is NO partial scalar tail or extra8B guard.
Every half-word's result/guard equality remains independently recoverable;
failure fallback counts original32-bit elements rather than packed words.

All128 mask bytes cleared in2205 groups, permitting16 ordered scalar SDs
perclear with no new RVV/fence. Actual vlm32B, upper96B zero.
Selected CAP256 counts are256/all,128/odd,37/i%7==2.
Original bitset SB count=(256+128+37)*(3*35*7)=309435.
Do not transplant e64 selection or upper-mask geometry.

EVERY FP call, including VL0, refreshes original
a[i]=inputs[(i+seed)%8], THEN b[i]=inputs[(3*i+seed)%8], i0..255:
512 original ordered32-bit writes/call,967680 SWs overall. Equal values
cannot eliminate fresh writes. Periodic scalar selection can remove modulo
overhead but not these stores. Widening adjacent a elements and adjacent b
elements would reorder the original alternating bank sequence and requires
separate equivalence/authorization; it is not silently assumed legal.
Preserve original context; no extra fflags oracle absent from source.

## Contract-specific Scalar Floor

| Required phase | Minimum instructions |
| --- | ---: |
| 129 fresh SD/call | 772065 |
| 129 complete LD/call | 772065 |
| 129 full64-bit compare/difference operations/call | 772065 |
| Original FP512 SW/call,1890 calls | 967680 |
| Mask16 SD clear/group | 35280 |
| Original mask bitset SBs | 309435 |
| Original13 helper instructions/call | 77805 |
| Total | 3706395 |

This exceeds3M by706395 before gold loads, RNG, loops/indexing, wrapper/ABI,
vstart checks, startup/return or diagnostics. Counts are source/ISA minima
for the stated retained contract, not actual GCC CFG or reference firmware.
Even granting a hypothetical optimistic halving of ALL FP stores to256 SDs
percall (NOT authorized/equivalence-proven) would still give3222555,
already222555 above3M. No added RVV or lossy checksum is proposed.

## Static ROM Direction and Next Decision

Flat gold5985*1032=6176520B exceeds1MiB. Dictionary has17 IDs/call:
16 full64B blocks and8 valid bytes in block17. IDs203490B; do not read
the final56 padding bytes from actual output. Exact unique count U is not
enumerated here; no capacity-fit claim.
With original12448B globals,2592B original FP tables/inputs,384B masks,
65536B code/RO,16384B runtime,65536B stack, envelope366370+64U fits1MiB
only if U<=10659 before alignment/extra metadata. Actual map/stack/lowering
and uint16 ID bound would need separately authorized software preparation.

Thus this second full FP m8 shape also cannot be admitted under3M.
User/main must explicitly choose a revised finite instruction/time budget
or leave it not admitted. Pending6h discussion is not execution permission.
No timer extension, new run, result reduction, historical-PASS substitution
or automatic retry was performed.
