# e16/m4 Corrected Source Review

NO_BLOCKER_SOURCE_FOR_HOST_AND_COMPILE for source_entry02 a2ed30e3...; all40 pins match. Old source_entry remains unaccepted. Actual changed prior pins are only model.py, dictionary.h and prepare.py: physical_masks is correctly [3][128], fixtures remain [3][256], software gate consumes source_entry02.

Original binary-equivalent source/archive e16,m4 vtype10 is retained. Full4095 calls/1048320 results/8190 guards, three-seed RNG, CAP256 gather bounds, helper calls and source loop order remain unchanged. Conversion retains original error fallback and vstart check. The8 full64B blocks plus final4B cover516B including result255 and trailing005b guard. memcpy uses legal byte pointers; no widened tail or uint64 alias cast. Full128B mask initialization has96 upperzero bytes; actual vlm32B. Dictionary2021 blocks/9indices/203438B ROM fits static reserve, not a substitute for actual linker map.

Host design extends every-position original-C/model comparison, all516-byte corruption coverage, protected-page tail, typed high-byte and original exact failure count checks. No Host or compiler run by reviewer. Actual helper machinebytes/no-extra-RVV/lowering/stack and subsequent reference group4 full512B remain later gates. No reference or DUT permission at this stage; old prefix56 is not full acceptance.
