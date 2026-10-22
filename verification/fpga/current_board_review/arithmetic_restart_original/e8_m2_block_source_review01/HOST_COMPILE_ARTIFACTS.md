# E8/M2 Actual Host and Compile Artifacts

Verdict: HOST_COMPILE_ARTIFACTS_ACCEPTED_REFERENCE_ENTRY_PENDING. No reference or DUT authorization is implied.

Independent read-only metadata audit session 90680 completed with actual exit0 (completion 7cb938). All139 preparation pins freshly matched; pins.json SHA256 is `b224ffb9708ae80b180fa925e5ae13fccbf9a45a7e2cdfb05d26492f11a40c8d`.

Both original and packed variants have eleven actual Host receipts. Mutation0 exits0; mutation8 deliberately traps UBSan with returncode -4; all other nine mutations exit1. Non-trap original/packed logs are byte-identical and include the complete4095/1048320/8190 scope marker. No Host execution was repeated by this reviewer.

Actual ROM has1260 blocks,80640 dictionary bytes,40950 index bytes and384 mask bytes:121974 bytes total. Maximum index1259 fits uint16. Original order, source diff and unchanged failure fallback were reviewed.

| Backend | ELF SHA256 | Actual stack gap |
| --- | --- | --- |
| SoC | `30eca586d305d0636c125c4ad4ebdf9acf267feb6163b6c460b75e3bb5d1354d` | 916520 bytes |
| Spike | `71b6f3e6ceabeddb37dd38782a23b2d0fe67e08eb313a9becdb49941afae3683` | 908064 bytes |

For both ELFs, independently checked all328 helper instructions against actual ELF PT_LOAD bytes and unique archived original byte sequences (capacity3 plus25 helpers*13); decoded disassembly has no RVV outside those helpers. Actual Spike capacity is e8,m2,tu,mu (vtype1); helper groups are v8-v9, v16-v17 and v24-v25, with vlm32 bytes at capacity256. Original gather instruction is0x30880c57, not a replacement helper.

Actual Spike arithmetic_main frame is304 bytes. Initializer at0x80000502..0x8000057e uses32 SD instructions to out+0..248; the tail is a separate SH. Output comparisons use32 LD plus the LHU at0x800009fe resolving to out+256. This observes exactly258 bytes, including both guards and result255. No group1/4/8 or rounded320-byte output contract is substituted.

The producer reports a preserved initial inspector rc1: a global SoC/Spike PC shift is invalid for this compiled m2 binary (initializer and comparison sections have different shifts). This is not evidence of firmware or RTL failure. Final reference-entry review must bind the successor inspector using actual per-backend instruction sites, lifecycle/checker, its negative receipts and finite-run limits. Those entry files are still being finalized and are not accepted by this artifact note. No reference/Host/compiler/DUT was run by the reviewer, and no old trace was read.
