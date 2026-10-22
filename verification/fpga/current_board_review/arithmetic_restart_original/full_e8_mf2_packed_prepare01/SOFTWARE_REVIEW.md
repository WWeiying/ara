# Full e8/mf2 Software Preparation

Software preparation completed, actual command `python3 -B prepare.py` exit0
(session54883, completion chunk2a75cc). No DUT has been authorized or run.
`PLAN.md` preserves the initial planning state; current software status is
`software_status.json`, not that historical status line.

## Original Scope And Identity

No accepted full original e8/mf2 execution was found in the current arithmetic
inventories. Prior prefix/other-shape evidence does not substitute for it.
Original source family: `rvv_extended04`, reconstructed C backed by identical
Linux ELF rebuilding, not byte-recovered original C or Linux replay.

| Input | SHA256 |
|---|---|
| Archived/rebuilt Linux ELF | `2e16fe0a09238c14efb89b28326190c15225b10680138e7339f07c8541f38093` |
| Original mf2 assembly | `49e955479c7c53ffd5b58e94552afd2abf17f23572c36ee7cb810b68a5bd795b` |
| Original e8 operations.h | `7686eb17f96d500c82711d09bbaa74c965352b4257b0b7db3510d3fbbd9bf48c` |
| Reconstructed C | `7483f9dfde7012f7b800314fe1765f8cee9836fbcfbdc16fc641554397884e91` |

Derived scope:3 seeds *7 lengths *3 masks *(20 normal ops *3 starts +
5 special ops)=4095 calls. All duplicates and predecessors remain.
CAP64 yields262080 result bytes,8190 guard bytes and4095 returned-vstart
checks;25 original13-instruction helpers yield53235 dynamic helper slots,
plus one3-instruction capacity helper. These are expected coverage counts,
not a reference/DUT result yet.

The model recomputes CAP64 RNG inputs and expected values, including gather
index255 being out of range and slide-down's last2 source positions being
zero. It does not truncate another shape's expected output. Original RNG,
25-op order and per-byte error fallback remain in `case.c`; `source.diff`
shows only scalar output/mask work and the stricter capacity check.

## Measured Software Evidence

Original and packed Host each ran one full positive,8 error injections and
one deliberate UBSan shift64 trap:20 actual receipts. Valid rc0, injected
rc1 and deliberate trap rc-4 are kept distinct. Original/packed logs match
for every non-UB run. Checks include every result/input byte,128-byte mask,
prestart/inactive/tail/both guards, high returned-vstart bit, separate low
tail-byte mutation, unaligned memcpy, and a protected-page66-byte boundary.
No prior Host or firmware reference was rerun.

Both actual compiled ELFs retain all328 static original helper instructions
(capacity3 +25*13), matched against archived ELF bytes, and have zero extra
RVV instructions. SoC ELF SHA:
`5e901ae235792e40de311713125a7a37a480a3e266c3a7c8d8d4887bb8433839`.
Spike ELF SHA:
`c2c8b69433dc357004904b8ddd8192681aef5b48d90df41b97f77ae5dd2d58a3`.

Flat expected ROM294840B + mask384B fits without dictionary lookup. Actual
SoC `.text`4810B, `.rodata`296712B, `.bss`3272B. Main frame304B; no recursive
call path. BSS-to-stack gaps743656B SoC /735200B Spike exceed reserved64KiB.
Original a/b[1024],out[1026],mask[128] backing is unchanged. Byte memcpy
avoids alignment/alias UB; no rounded72-byte output access is introduced.

Actual SoC init is SH at`800004f8` BEFORE8 SD at`800004fc..80000518`.
Actual output oracle reads8 LD plus LHU, not9 full LD. Tail2 consists of
result63 and rear guard; front guard is in the first LD. Spike equivalents
are bound separately by `lifecycle.py`, including9 exact read sites, hence
36855 expected output reads. The output memory footprint is exactly66B.
Physical v24 is128B, but original fractional helpers observe only its low64B;
the high half is not a new oracle. Full mask buffer is128B; vlm reads8B.

## Cost And Next Gate

`compiled_review.json` is static inspection, actual exit0,129 pins unchanged.
Measured instruction-site counts: per-call setup21 + helper13 + initial
compare11 + remaining compares/counter updates37 =82 instructions, excluding
outer-loop work. Each original mask group executes94 copy-loop instructions;
there are1575 groups. A deliberately loose positive-path envelope is1.2M
firmware instructions (4095*200+1575*200+30000=1164000, rounded upward).
This is not a measured retirement count or a simulation liveness guarantee.

The old M6 e16/mf4 rate594.197 instructions/s would project about45 minutes
including20% and300s allowance at1.2M. Hardware/vector throughput may differ;
actual full reference cost is required before any DUT budget decision.
No DUT launch follows automatically from this software reference gate.

Reference successor02 preserves the initial draft that stopped parsing at
HTIF. The successor reads through EOF and rejects all post-HTIF activity
except exact `8000007e/a001` park with no side effects; reset ROM is also
exactly bounded.12 new lifecycle tests and7 boundary tests passed, without
repeating full original/packed Host or compilation. Final independent entry
review is required before the sole reference execution.

Per latest authorization, finite `rs 4000000; quit` bounds total execution;
acceptance additionally requires complete firmware-through-HTIF <=3M,
120s execution and768MiB raw limit. The earlier proof's3M hard-step proposal
is retained, not rewritten into a claimed execution. Exact successor entry
is `entry02.json`; only `reference02.py` consumes its reviewed SHA.
