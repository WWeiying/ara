# Typed16 Reference Entry Review

Decision: HOLD solely for reference-executor step-bound enforcement. No reference
or DUT has run. Source/software checks below do not authorize the current entry.
Entry SHA:2d6867d7575456f54d5089aadd2debd8ee0eb35c52104ac58a76c86c0f962c18.
All150 pins freshly checked. Existing sealed preparation remains untouched.

## Concrete Blocker

reference.py uses `-d`, `until pc ...` and `--instructions=4000000` together.
The local Spike implementation at riscv/sim.cc:429 selects interactive() in
debug mode; the instruction_limit decrement exists only in the other branch
(435-445). interactive_until at interactive.cc:790-805 directly calls step(1)
and does not consume that limit. Therefore this command does not implement the
claimed4M execution cap, although120s and768MiB protections still exist.

Use a new narrowly scoped executor/entry with the already-used finite
`rs 4000000` then `quit` command. Derive firmware count and actual software/HTIF
exit from the unchanged complete observer rather than requiring an unbounded
until-PC diagnostic. Preserve the old entry; no recompile or semantic Host rerun
is needed. Bound4M,120s,768MiB,one attempt; above3M full completion remains HOLD.

## Source And Software Checks Completed

- Original Linux identity is68fc999069ab1f830f6dc4c572f1ebe851c8511b412aa355cd5e0fabe9a4ef7d,
  with byte-equal reconstruction, not recovered original C bytes.
- Full4095 order/three seeds/CAP512 are retained:2096640 typed results,8190
  guards,4095 returned vstart and53235 helper instructions. No partition reset.
- Typed sentinel0x005b, not0x5b5b. Actual checked footprint1028 bytes; result
  offset2 and span1024. Physical a/b each2048 bytes; their unused upper1024
  bytes are checked zero. Physical output remains2052 bytes.
- vtype11; actual vector groups remain eight128-byte registers. Predicate
  initialization checks all128 bytes, upper64 zero. Active predicate compares
  low512 bits; upper predicate tail is not falsely treated as active.
- Actual ELF load bytes independently match all26 helper specifications and
  all129 initializer PCs. Decoded stores are128 SD plus1 SW, no duplicate or
  missing byte in0..1027. Lifecycle separates ordered zero-BSS from business
  initialization and requires the full actual schedule on each helper entry.
- Observer explicitly uses little-endian16-bit words, not bytes(uint16_list).
  Full output is expected[2:1026]; scalar oracle requires128 word reads plus
  one4-byte tail. Tail upper16 bits are the005b guard, so its RV64 signedness
  cannot silently truncate a meaningful high-bit value. Complete original
  fallback/error accounting is retained; constant memcpy avoids aliasing casts.
- Model keeps original512-word RNG, reduction bit0-masked seed semantics,
  compress and gather out-of-range behavior.3598 blocks/17 IDs per call do not
  deduplicate calls. Automatic vectorization disabled; no extra RVV in proof.
- All10 original/packed log pairs freshly compare byte-identical (20 actual
  processes, including expected corruption exits and intentional UB trap).
  Separate7 lifecycle/boundary Host tests have actual wait0,1.57037s. No Host
  was rerun during review.
- SoC SHA:f70831da5a87b07ff0c14852d4d38968226a35653a7568b775577b0a07948923.
  Spike SHA:da0aea1d62c81e9d9c9de8806c459ee1e17b4de96260c0a298082f378fa94eb2.
  Stack gaps663720/655328 bytes exceed64KiB in the1MiB load region.

Executor SHA858be9abe4a28ea81201157fac2fc5c145cb4a46b0d395195913db6bb946352c.
Unchanged typed observer SHA8f4837db87e47666bb1380b1b04c59d191ad2960c1796fd119ebda751ced1feb.
Only the executor correction remains before final exact-entry binding.
