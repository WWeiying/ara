# Bounded Static ELF Difference

Decision: code layout/control-transfer encoding differs; no changed oracle
condition was found in the inspected old/new control flow. This does NOT prove
historical C identity or authorize a guessed inverse edit. `NOT_RECOVERED`
and the sole rebuild's ELF mismatch remain unchanged.

## Evidence and Scope

One Linux `objdump -d` invocation decoded both existing ELFs (actual exit 0).
Output is preserved in `old_new.disassembly.txt`, SHA
`8ac711b1ddce664a831763a905ddbb5f9a740b7ad97fa6d0e1ad21829446c098`.
No compile, Host, reference, DUT, new source search, or C edit was performed.
Existing ELF sections were read as binary data for the small comparisons below.

Old ELF SHA: `bef54674b16fdeefdb37295d035b1b9a58cd446cd54662078aa24e83cced7b2d`.
New ELF SHA: `673d58fc8c83581bae8b5ee008a4c9a41403982c84c67dd830639aca6d4723bb`.

## Where the Eight Bytes Come From

- `.text` starts at PC `0x10120`, file offset `0x120`, in both ELFs.
  Old size 1792, new 1794: net **two code bytes**, not an eight-byte C branch.
- Old text ends at `0x10820`, already 8-byte aligned. New text ends at
  `0x10822`, followed by six zero padding bytes before `.rodata` at `0x10828`.
  Thus following file sections move by eight bytes without increasing size.
- There are 567 versus 568 decoded instructions. Main scalar code has 13
  versus 14 unconditional `j` instructions, all compressed. Other instruction
  count changes are equal-width substitutions/inverted conditions below.
- Capacity and all ten operation helpers, old `[0x10538,0x10820)` and new
  `[0x1053a,0x10822)`, are exactly identical 744-byte sequences, SHA
  `e1bee3371d4119f7c07f45cc56d14c86738124ba934463ec7d8108014a553a09`.
- `.rodata` has identical length 12648. Its only changed bytes are offsets
  280,288,...,352: the ten 64-bit function pointers each increase by two.
  All other bytes, including inputs, expected bit/flag tables and strings,
  are identical. `.bss` address/size/alignment and attributes/comment match.

## Concrete Control Flow and Source Conditions

PCs below are old -> new. C references are to the unchanged `parent.c` (03cc).

1. **Per-call setup moved**, C lines 49-63: old `0x10232..0x10242`
   saves prior errors, loads VL, initializes expected flags from sticky, and
   sets up mask initialization, then falls through to `0x10246`.
   The same setup is new `0x10430..0x10440`, followed by the additional
   `0x10444: b3fd j 0x10232` to its relocated mask loop. This is the net extra
   compressed jump, not an added mask/oracle predicate.
2. **Sticky-loop branch inverted**, C line 47: old
   `0x1045a: dce69ce3 bne a3,a4,0x10232` versus new
   `0x1042c: 04e68163 beq a3,a4,0x1046e`. Both compare sticky+1 against 2;
   new nonterminal execution falls through to relocated setup. Both first
   set `s8=1` (old `0x10458`, new `0x1042a`). Consequently mode increment
   old `0x1045e: 9a62 add s4,s4,s8` and new
   `0x1046e: 0a05 addi s4,s4,1` have the same value on that edge.
3. **Active oracle**, C lines 79-82: `a4=i`, `t0=VL`, `a3=actual`,
   `a6=wanted.bit`, `s5=flags`, `s0=errors`. Old `0x10354` / new `0x10340`
   branch on `i>=VL`. Otherwise both load wanted.flags and OR into flags;
   old `0x1035e` BEQ skips error increment, new `0x1034a` BNE branches to it.
   Old error increment `0x10362`; new `0x1046a`. Same acceptance condition.
4. **VL-zero versus tail**, C lines 83-91: old `0x1036e..0x10378` computes
   `old=(91>>(i&7))&1` and `0x10374: 10029063 bnez t0,0x10474` selects
   nonzero-VL tail handling. New computes the same old bit at
   `0x1044e..0x10452`, with inverse
   `0x10454: 00028963 beqz t0,0x10466`. Both require `actual==old` when
   VL=0 (start is fixed zero). For VL>0 tail, old `0x10474/78/7c` and new
   `0x10458/5c/60` accept respectively `actual==old`, `actual==1`, or
   `wanted.bit==0` when actual is already known zero. This is exactly
   acceptance of `{old,1,wanted.bit}`, not removal of the VL-zero safeguard.
5. **Flags/guards**, C lines 93-94: old `0x10384..0x103aa` and new
   `0x10356..0x1037c` compare returned high32 flags and both 0x5b guards;
   no changed predicate or error increment was found. Returned low32 vstart
   checking is likewise old `0x102fa..0x10308`, new `0x102e6..0x102f4`.

These are real changes to instruction addresses/branch directions and dynamic
jump counts, not byte-identical code. They do not establish changed oracle
semantics. This is a bounded manual CFG/data comparison, not a formal
whole-program equivalence proof or a runtime/performance measurement.

## 03cc Versus 3652 and Recovery Limit

The existing 3652 template SHA is
`3652ca2d4f3f7b63995234bf624514dfb318db9cd781aeee0a7533d6c564491c`.
Its diff against 03cc contains only the three-line UNBOXED default definition
and the comment/`if(UNBOXED_COMPARISONS && op>=4)bi=14` addition. Under the
fixed `UNBOXED_COMPARISONS=0`, the latter does not change the selected `bi`.
Both templates already contain `start>=vl || i<start` (3652:77, 03cc:83),
and old ELF itself implements the resulting VL-zero check. Removing that
condition to chase identity is therefore not supported by this evidence.

No unique source change can be inferred from basic-block ordering or jump
inversion, and no separate 3652 rebuild was performed. Recovering the exact
historical C SHA `9060f293...` still requires external source/history evidence;
this analysis does not justify marking any candidate C recovered. No further
compile or source reconstruction is proposed by this bounded result.
