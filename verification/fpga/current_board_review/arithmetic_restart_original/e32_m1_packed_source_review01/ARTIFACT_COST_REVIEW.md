# e32/m1 Actual Artifact and Compiled Cost Review

Verdict: **HOST/COMPILE ARTIFACTS ACCEPTED; REFERENCE COST HOLD**.
This is an independent read-only review of `full_e32_m1_packed_prepare01/software01`
and `compiled_audit01`, not a Spike or DUT acceptance. No producer scripts,
Host tests, build, reference, or DUT execution were repeated for this review.
No production RTL or sealed input was changed.

## Bound Identities

| Artifact | SHA256 |
|---|---|
| Original and binary-identical reconstructed ELF | `0c11f7a2d6bcf0fa0ee27e5f4eb3f9d1fc567d29ad638c5e2c9675d0dc2785e4` |
| software01/proof.json | `e68e6df558fbf427940930750a5738a0c8e46ab88e26b222d78914f938b0431d` |
| software01/pins.json | `67cd7dbbbedc572167a85b7db4db8eadce9e30ef141a7acd4c5015ac7dc68371` |
| software01/execution_receipt.json | `49cca909eed82e74717200d99443eb298a4a1ff507b2b891a5f5f0a3c2f195d4` |
| SoC program.elf | `82e0395a504f7583f5f1baa02426ca1f583947e93776c84e149ab8bb9e0d2e02` |
| Spike program.elf | `cd9a75ba80d9fffac14a6640d1b1e21527bfc915aafa5eb3a2ee8435016950fc` |
| compiled_audit01/RESULT.json | `946b2d45dbd68ff59078091c17d2a80d3252ce5f5aaa49bc811b816ada1bc885` |

All 169 software pins were independently rehashed without mismatch. Original C
bytes remain unavailable: provenance is reconstructed C reproducing the original
ELF, not recovery of the original C file.

## Actual Artifacts

- Persisted Host/compile outer receipt is numeric returncode 0, timed_out false,
  elapsed 17.476429773960263 seconds. All 26 individual Host records have strict
  integer expected returncodes and matching log hashes. Twelve original/packed
  log pairs are byte-identical. Positive runs report full5985, results191520,
  guards11970, FPcalls1890 and FPstores120960. The two missing-equal-valued FP
  store negatives return90 with `HOST_BLOCK call=1367 every FP call fresh stores,
  even equal old value`; these are expected rejected mutations, not positive runs.
- Independent ledger transcription from original loop order/kinds checks every
  seed/op/VL/mask/start tuple: 5985 calls, 35 ops, no omitted duplicate starts.
  Every 128-byte mask was checked, including zero upper124 bytes. Actual `vlm`
  consumes four bytes at CAP32. Physical data group is one full128-byte register.
- All 1890 FP ledger entries were checked against original eight input patterns
  and exact original 10x64 expected-bit table. No host floating-point calculation
  supplies the golden result. The 2560-byte table occurs uniquely in original,
  SoC and Spike ELFs, SHA `b6ba4a7cb146e697a04723349b9e023e2210dc0714b717f70eb8bfb6c3a8438a`.
- Actual Spike op>24 gate at `0x80000510` enters FP setup `0x80000aba` on every
  call. Loop `0x80000ade..0x80000b00` has 15 instructions and two SW sites
  (`0x80000af4`, `0x80000af8`), runs32 iterations and exits to output setup.
  The next-start paths return through the op gate. There is no VL/start or
  unchanged-value shortcut. SoC equivalents: gate `0x80000508`, loop
  `0x80000ae2`, SW `0x80000af8`/`0x80000afc`. This preserves120960 input stores,
  not merely seed-first contents. Original next-seed RNG block remains intact.
- Both linked ELFs contain the complete813960-byte packed ROM obtained from
  every ledger result plus both original guards: 5985 *136 bytes. Actual code
  initializes and compares17 eight-byte words per call, covering all191520
  32-bit results and11970 32-bit guards. This is **136B, not a two-byte tail**;
  first/last packed words combine a guard with adjacent data. Full original
  scalar fallback remains present. Original has vstart but no fflags oracle;
  artifact acceptance is not exception-flag acceptance.
- Independently compared bytes at linked ELF addresses for capacity3 and all
  35 helpers13 each:458 static instructions, each unique original byte sequence.
  Scanned disassembled vector encodings outside those PCs: zero extra RVV.
- Actual linker maps assert64KiB stack reserve. SoC BSS end `0x800cc2c8` to
  stack `0x800ffff0` leaves212264B; Spike BSS end `0x800ce3d0` leaves203808B.
  Main frame320B; reported sums of explicit frames496B/544B do not threaten
  that reserve. Backing arrays are retained, not reduced to CAP-sized buffers.

## Cost Gate

Reviewed actual compiled branches/loops, not just the producer's initial estimate.
For an entirely correct execution, the disjoint mandatory core totals
**3,151,890 instructions**, already151890 above the3M gate. The producer's
conservative positive-path accounting including control/startup/tail allowance is
**3,320,678**. Neither number is a measured retirement count or wall-clock time.
Failure-path execution is not bounded by this positive-path estimate.

Key mandatory costs are bytewise mask clearing846720, mask construction676935,
per-FP-call setup20790 and input loop907200, per-call setup/first compare263340,
remaining packed compares/counters359100, and original helpers77805. Mask visits
are2205 groups,735 each mode; FP visits are1890*32, not three seed initializations.
Independent sum and original loop cardinalities match the compiled cost report.

Therefore **do not admit a reference for this exact artifact**, even though
Host/compile semantics and memory fit pass. No finite4M reference has been run
or authorized here. Any future scalar-only optimization requires a separately
identified successor and new actual artifact/cost review. The128-byte mask clear
is a concrete candidate; it must retain the entire mask contents and all original
calls, per-FP input writes, RNG/history, helpers and full data/guard oracle.

## Review Execution Evidence

Read-only tool completion `7eedd4` (numeric0,1.6696s) independently verified all
169 pins,26 Host receipts,12 matching log pairs, linked helper bytes, FP table,
noextraRVV and map gaps. Completion `4c3fee` (numeric0,1.6378s) independently
verified all5985 ordered ledger records/masks,1890 FP exact-table records, complete
linked136B-per-call ROM and compiled cost arithmetic. These are reviewer metadata
inspection exits, **not** Host reruns or architectural reference exits.

Producer's initial two static inspector failures and their receipts are retained;
successful `inspect03.py` inspection is not represented as a simulation result.
No Linux/board closure, current-image PASS, or dynamic freshness proof is claimed.
