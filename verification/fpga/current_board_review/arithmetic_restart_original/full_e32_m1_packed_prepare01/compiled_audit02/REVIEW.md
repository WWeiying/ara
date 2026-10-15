# Single Mask-Clear Candidate: Host/Compile And Cost

Status: actual mask lowering and static cost gate PASS; independent artifact
review requested. No reference or DUT is authorized or executed. Old
software01 HOLD, scripts, logs, pins and accepted historical inputs unchanged.

## Source And Actual Host Outcome

Independent SOURCE NO_BLOCKER:
e32_m1_packed_source_review01/SOFTWARE02_SOURCE_REVIEW.md,
SHA3f73028df84a0a2b8e9bc6c38c751bf2d36c7930a2fae26c47dc60836ab765fe.
The sole source delta replaces the128-byte mask zero loop with16 exact8-byte
builtin memcpy writes plus empty compiler memory barriers. Inverting that
delta reproduces software01/case.c byte for byte. No compiler flag changes.
No target hardware fence/delay, alias cast or assumed pointer alignment.

Host/compile PID3255657 actual numeric0,12.396689195s, no timeout.
New14 runs all had expected numeric outcomes: packed positive plus11 full
negative histories match the previously accepted original12 logs byte for
byte; deleted equal-old-value FP a/b stores each reject at call1367 with90.
Old original12 binaries were NOT rerun. UBSan remains enabled. Every new Host
run also checks dirty128B clearing at an unaligned address with exterior
sentinels, and exactly128B ending at a PROT_NONE boundary. Existing complete
136B output, typed32bit guards, signedzero/NaN-bit mutations and fallback
checks remain; selected32-position mask construction is unchanged.

All5985 calls/35 ops/191520 results/11970 guards/full three-seed order remain.
Every1890 FP call retains both32-word input refreshes, including VL0 and
start>=VL. Next-seed RNG, original640 FP golden words, fallback and helpers
remain unchanged. No fflags result oracle is added or claimed.

## Actual Machine Code

Both ELFs decode to exactly16 SD-zero accesses at mask+0,8,...,120.
The decoder resolves each AUIPC/GP-relative effective address from actual
instruction bits and linked symbols. There is no clear-path branch, call,
memset, byte loop, hardware fence or RVV. Both mask symbols are8B aligned.
Spike uses7 AUIPC+16 SD=23 instructions/group; SoC uses8+16=24.
This is not the optimistic16-instruction store-only estimate.

Both preserve458 original helper instructions, extraRVV0,17 output SD and
17 output LD at byte offsets0..128, and the15-instruction FP loop with two SW
for each of32 iterations per FP call. Full linked813960B expected ROM and
2560B original FP table are byte-identical to software01/source gold.

| Artifact | SoC | Spike |
| --- | ---: | ---: |
| text bytes | 5664 | 5748 |
| rodata bytes | 818192 | 818200 |
| BSS bytes | 12488 | 20688 |
| stack gap bytes | 212136 | 203744 |
| main frame bytes | 304 | 304 |

SoC ELF SHA8b6c67293ad57aff6ddeaf478aa4c94bd07d44421f3c6eb901378fe4cf23db5c.
Spike ELF SHAb4fba0b73d4fbd656f54769f7ea8047b3af6fec848de53d685fb209a89651d4f.
All static C-frame allocation sizes sum to480/528B respectively, with no
recursion/dynamic allocation; the64KiB reserved stack gate remains satisfied.

## Actual CFG Cost, Not Retired Measurement

Spike mask clear becomes23*2205=50715 instructions, versus846720 previously:
clear-region saving796005. New register allocation and outer loop/setup
costs are included, not assumed unchanged. Static mandatory core2355885;
successful-path conservative upper2550519, down770159 from3320678.
Margin below3M:449481 instructions. Existing original error fallback remains;
this is a successful-path bound, not a promise to finish a failing path.

Full per-PC regions/multiplicities and overhead bounds are in RESULT.json.
inspect.py completed actual exit0 (receipt tool chunk3fb843).280 pins checked
before/after unchanged. There was one candidate Host/compile and one static
inspection, no retries, parameter changes, reference execution or DUT launch.

RESULT SHA0e3da5d2df3de13f8014f89bf1064559f29bd1be4c39b93fbc4160daab40d144.
software02/proof SHAaf3c787838efa61761dd19dd0b443c107abd185894ec0c57d00cf90001d25c7e.
Reference requires separate exact entry review and parent authorization;
this software-only result is neither architectural PASS nor Linux closure.
