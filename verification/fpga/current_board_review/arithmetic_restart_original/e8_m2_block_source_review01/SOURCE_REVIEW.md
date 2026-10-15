# E8/M2 Source Gate

Verdict: NO_BLOCKER_HOST_COMPILE_ONLY. Static review only; no Host, compilation, reference, DUT, model generation or old raw traversal was run by this reviewer. Aquinas remains the sole software producer.

Reviewed full_e8_m2_block_prepare01 PLAN.md, model.py, packed.h, host.c and prepare.py against recovery22/reconstructed_oracle.c, the archived e8/m2 assembly and the inherited runtime adaptation/helper-byte validation functions.

Original archived ELF and actual recovery22 rebuilt ELF both hash to `fe193c889801184a3144895f4817f0e9e6a9dfffae3144f6bf5bbcd311a1c0c6`. Original assembly hash is `4e73c13c43d558cf7a4102590197abcd57db9a48e3cd15e373565207116f2237`. Original C bytes are unavailable: this is binary-equivalent reconstructed C, not recovered original C bytes.

The source retains all 4095 calls, original seed/op/VL/mask/start nesting, RNG updates for all 256 elements, and the original byte fallback and returned-vstart check. Only scalar representation and runtime services change. The model uses CAP, not VL, for gather and slidedown. In particular b[2]=255 selects a[255] at CAP256, including target VL3. The gather assertion is valid because original kind1 gather has only start0.

Block64 deduplicates expected values, never calls. Each row has five uint16 IDs: four complete blocks compare offsets 0..255 as 32 words; one halfword at offset256 covers result255 and the rear guard. The first word contains the front guard. Expected-ROM padding is never read from the output. Initialization and comparison use memcpy, avoiding alignment/aliasing UB. The original larger a/b/out backing is preserved and Host checks untouched suffixes remain zero. Mask initialization covers 128 software bytes, with only the first32 populated; original m2 helpers physically read32 bytes and use two registers per full data group at VLEN1024.

Host design compares the original C oracle against every dictionary-derived position and original/packed diagnostics. It includes active, prefix, masked, tail, both guards, high-vstart, last-result and legal-index255 mutations, all258 individual-byte participation, unaligned buffers, a protected-page exact footprint, and a deliberate UBSan trap. These are reviewed planned checks, not yet actual PASS results.

prepare.py preserves complete loops and fallback, pins original inputs, checks exact unique archived helper-byte windows, forbids extra RVV, and gates actual linked bss/stack separation. It does not dispatch reference or DUT. Full expected scope is 1048320 results, 8190 guards, 4095 returned-vstart checks, 53235 helper instructions and 135135 packed reads.

Next gate requires actual Host22 receipts, original/packed log equality, generated source diff/ROM bounds, both ELF helper identities and no-extra-RVV evidence, actual group2 and scalar load/store lowering, stack frame plus linker gap. The exact reference observer/runner remains unreviewed at this source gate. Reference requires a separate exact-entry decision: one finite 4000000-step run, 120 seconds, 768MiB raw bound and firmware-to-HTIF <=3000000. No DUT authorization.
