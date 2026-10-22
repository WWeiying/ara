# Immediate Vector FP / CSR Ordering

Source: `apps/riscv-tests/isa/rv64uv/vec_fp_csr_order.c`.
Makefrag adds only `vec_fp_csr_order` next to `vfcvt`. No existing narrowing,
runtime, RTL, or runner source is changed. The existing .gitignore rule still
ignores this new C file; the owner must whitelist or force-add it when staging.

## Frozen inputs

Directory: `verification/out/vec-fp-csr-order-20260926-02/`.
The previous 20-case `-01` inputs remain unchanged.

- DUT: `inputs/vec_fp_csr_order.elf`
- Golden: `inputs/vec_fp_csr_order.spike.elf`
- Source SHA-256: `4b8da2ea9ec00b30da6440403638cac4c1f06ffd044dd20a50cea0c8ac730e4a`
- DUT SHA-256: `bd7885723a60c6f6e98b0ed7a55582803db591dfaad1c4cb39cd33fdab97b3f5`
- Golden SHA-256: `38e344537e2f6335b6691654743b5df882e796f911822a660ab8dc8d901c685f`

Adjacent DUT ELFs in the same inputs directory: `vfp_vstart_edges.elf`,
`vfredosum.elf`, and `vfwmacc.elf`. All were freshly built with the same repo
LLVM settings; no existing verified apps/bin images were available. Their
original sources were copied, not edited, and live-source hashes were checked
against the snapshots after compilation. Each corresponding golden also
passed. The `adjacent` manifest section records source and ELF provenance.

`manifest.json` records tool hashes, all input hashes, and each disassembled
critical FP/CSR pair in both ELFs. `commands.log` records exact build/run argv.
`SHA256SUMS` verifies all inputs, which are read-only. Repo LLVM 22, no ZCC;
Ara O3/lp64d, NR_LANES=4, VLEN=1024, existing 2 MiB linker script and privately
compiled runtime. No apps make or shared common object/linker regeneration.

## Cases

Each case initializes its operands, destination sentinels and FCSR before the
critical sequence. Operands are raw FP32 bits: +/-1.5, +/-2.5, quiet NaN, +0.
The fixed integer expectation table covers all five rounding modes without
scalar/host floating-point computation. VL=16 uses multiple execution beats.

| IDs | Critical sequence / check |
| --- | --- |
| 1 | Inexact conversion -> immediate fflags read, expecting NX |
| 2 | Invalid conversion -> immediate fflags write-zero; NV must stay cleared |
| 3 | Inexact conversion -> immediate fflags set-NV; retain NX |
| 4 | Inexact conversion -> immediate fflags clear-NX |
| 5 | Vector divide by zero -> fflags swap to NX; returned old value is DZ |
| 6 | Inexact conversion -> fflags read/set-NV; old NX, new NX\|NV |
| 7 | Invalid conversion -> fflags read/clear-NV; old NV, new zero |
| 8-12 | Conversion -> frm change -> conversion; old/new results for RNE->RTZ->RDN->RUP->RMM->RNE |
| 13 | Inexact conversion -> immediate combined fcsr read |
| 14 | Conversion -> fcsr swap (RDN to RUP plus DZ) -> conversion |
| 15 | Invalid conversion -> fcsr read/clear (RMM and NV) -> RNE conversion |
| 16 | Conversion -> fcsr read/set (RUP and NV) -> RUP conversion |
| 17 | Conversion -> immediate frm read, then fflags read |
| 18 | Legal VL=0 conversion -> fcsr swap; no destination/flag side effects |
| 19-20 | Illegal single-width SEW=8 conversion at VL=16/0 -> handler FCSR access -> return and CSR access |
| 21 | Consecutive independent NV-producing and NX-producing conversions -> one fflags read expecting NV\|NX |

The illegal instruction is `vfcvt.x.f.v` at SEW=8, NOT legal FP16->I8 narrowing.
Both raise mcause=2 in golden even at VL=0. The naked handler's first instruction
reads FCSR, then clears/reads FFLAGS before accessing any vector CSR or memory.
It records state and skips the known 4-byte illegal instruction. This exposes
a phantom pending-FP token that would deadlock handler-side CSR access.

Each tested FP instruction is immediately followed by a CSR instruction in
one asm block, except case 21's first conversion which is immediately followed
by the second conversion. Disassembly verifies all 22 static FP sites for
both ELFs: exactly one FP->FP pair and 21 immediate FP->CSR pairs. There is no
fence, vset, vector CSR read or helper call in those critical gaps.
The post-capture vset/stores/fence are intentional: a late FCSR check then
detects stale flag reassertion after a clear/overwrite, without hiding the
earlier immediate observations. Both destination vectors are checked, including
unchanged sentinels. Each non-trapping case also checks that no trap occurred.

## Validation

- Initial 20-case version: repo ISA make/O2/lp64 golden PASS.
- Current frozen O3/lp64d golden: PASS, 21 cases, 762 checks, 2 expected traps.
- 762 = 672 destination-word comparisons + 63 CSR observations + 27 trap checks.
- 30 dynamic FP instruction attempts: 27 active operations, one VL=0 operation,
  and two illegal attempts. Exactly two illegal-instruction traps, no others.
- Golden emitted 27,680 `-l` instruction records. This includes startup, printf
  and HTIF polling; final repeated-PC exit spinning may be suppressed. It is
  not an exact retired-instruction count or an Ara cycle measurement.
- No VCS run. A hang must be bounded by the caller's independent timeout;
  software cannot diagnose itself while the hart is stalled on a CSR.

Reproduce into a new directory:

```sh
bash verification/build_vec_fp_csr_order.sh \
  verification/out/vec-fp-csr-order-REBUILD
```
