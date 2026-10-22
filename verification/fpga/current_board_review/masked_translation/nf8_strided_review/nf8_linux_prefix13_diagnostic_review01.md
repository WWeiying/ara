# NF8 Prefix13 Diagnostic Review

2026-10-12. One read-only static pass over diagnostic.h and build03 source,
diff, compile command, existing disassembly and proof. No compile/test/run.

## Blocking Finding

P2: build03 drops fatal diagnostic evidence. diagnostic.c:81 buffers text while
diag_in_handler is set; quit at line83 immediately calls exit_group. Repeat
fault (122), invalid frame (144), and handler repair failures (110/114) therefore
exit2 without reaching the only diag_emit at314. Buffered fatal_message and
captured PC/context/first-error records are lost. This is not false PASS, but
blocks delivery as a diagnostic for those failure classes. Tesla was notified.

Minimal repair: only on fatal handler exit, serialize the already captured
record(s) into fixed-size storage with scalar bounded formatting, then issue
raw write syscall(s) through the existing call wrapper before the unchanged
exit_group(2). Include fatal identity and incomplete state; retain earlier
sticky records. Bound bytes and write attempts; short/error writes must not
turn failure into success or an unbounded retry. Do not dereference ctx/datap
again, use libc/allocator/locks, execute vector/FP instructions, longjmp,
return through a bad frame, or change repair/poison/oracle behavior. Ordinary
handler returns remain buffer-only. A blocking output descriptor can still
block a raw write: bounded bytes/attempts are not a wall-clock guarantee.
Do not merely clear diag_in_handler and invoke the many-call general emitter.

## Other Requested Checks

- No added normal-handler allocation, libc formatting, locks or output calls.
  Diagnostic capture uses scalar loads/stores to preallocated volatile records.
  Existing disassembly has46 RVV instructions, all in original helper sequences
  or the preserved three-instruction probe_main bootstrap. No added handler
  vector/FP instruction was found; no claim of a new execution measurement.
- Frame capture reads fixed state fields only after the original minimum
  vector-header size test. Original vlenb/datap/full32-register containment
  checks remain before saved-register reads; frame_valid is set only after
  those checks. frame_found alone is not validation. The original header walk
  assumes readable kernel-provided context; its16-record/size bounds are not
  proof that arbitrary malformed pointers are mapped. No new hardening or
  broader context-safety claim is inferred from this diagnostic.
- Original metadata-error counting, prefix comparisons, restore_page,
  active-prefix poison and unchanged saved PC/vstart/data are retained.
  Diagnostic check is sticky per trial; later trial records do not overwrite
  earlier records. Earliest failing trial plus its check identifies the first
  recorded error; this is not a separate global first-error latch.
- Original natural loops and trials0..12 are retained. The cut at311 follows
  complete output,8192-byte memory and guard oracles, original unmap and cases
  increment. All12 predecessors remain; no errors are cleared. Trial12 is
  load/ACCERR/boundary1/mode3/gap1/split0, expected prefix13/12/0.

## Reviewed Identity And Disposition

All9 proof input pins matched at read time. Original rebuilt ELF matches the
archived original SHA c90e2ac2ab90fba392ca887842ce07c78244405ef41428f7e8f760373e658282.

- diagnostic.h: `553c1c6848a225ee3e37a0b3d2a3a1e2cdd946d82caaa0d37d985fd9bbd5897f`
- build03/diagnostic.c: `d946c772243aa5dc89d50a81aa23adbf833938fb32382e2d9747b8b1900b68a6`
- build03/source.diff: `a0a7ffde0ac1c37cc25e44740d0f6abd4518c9092db06dc122032c51d13a0bc5`
- build03/proof.json: `016882f5b3a57f6bc8dc5be9910b4aa647f9ebadd2f37cff31fc2c4c35c54b28`
- Diagnostic ELF: `c6af42f4b1fc5a992d7f60b3ac078fe3accb29f034f8645abbc6ee5f0b18698f`

HOLD build03 diagnostic completeness pending the narrow fatal-output repair,
or explicitly limit delivery to nonfatal paths and acknowledge lost fatal
evidence. No successor is approved by this report; no launch authorization.
