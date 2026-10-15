# e16/m2 Source Review

NO_BLOCKER_SOURCE_FOR_HOST_AND_COMPILE, bound to source_entry 8fd3c58191651666e081123fa42b308209618039360c3c1764485adc03f49175. All37 input pins match. No tests/compiler/reference/DUT run by this review.

Original archived ELF and reconstruction both b115b75e...; source is explicitly binary-equivalent reconstructed C, not recovered original C bytes. Original disassembly establishes vtype9/e16,m2,tu,mu and unchanged op19 VI2. Source conversion retains all original seed/op/VL/mask/start loops, input RNG, helper arguments, returned-vstart test and verbatim error fallback. It changes scalar initialization/comparison only, preserving typed005b rather than byte5b fill.

Four 64B blocks cover bytes0..255; the final4B covers result127 and trailing guard. memcpy avoids typed-alias/alignment UB, and neither initialization nor comparison accesses beyond byte259. Index range0..1227 fits uint16 and each of4095 ordered calls has five indices. Dictionary78592 + index40950 + masks384 =119926B. Actual linker stack/map remains a later artifact gate, not established by this static bound.

Model retains CAP128/three seeds and source operation semantics. Mask initialization covers128B with upper112B zero; actual vlm consumes16B. Reference must inspect exactly physical2/full256B, never inherited group4/8 or half-group data. Source register-history and original13-instruction helper preservation will be checked against actual compiled ELF.

Host design compares original C computation to model for every element/call, exact diagnostics/counters for mutations, all260 byte positions, both guards, high typed byte, vstart and protected-page tail boundary. These are planned tests, not claimed PASS. Compiler disables automatic vectorization and gates extra RVV, original helper windows and >=64KiB stack gap. Approval is only for the once software phase; finite reference entry and DUT admission remain separate and ungranted here.
