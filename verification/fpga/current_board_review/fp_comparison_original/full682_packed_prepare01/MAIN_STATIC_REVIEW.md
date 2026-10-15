# Full682 Preparation: Independent Main Review

This review accepts the scalar transformation preparation, not DUT execution.
The original 17920-call parent and Linux ABI remain outside this acceptance.

## Reviewed Contracts

- Read the original `prepared02/prepared/alias_v8_e16m8_prefix682/case.c`,
  successor `run01/case.c`, `prepare.py`, `host.c`, `finalize02.py`, compiler
  command and the recorded Host receipts.
- The actual compiler defines SEW=16, unmasked comparisons, no restart and
  destination-kind=1. Therefore the specialized oracle must use source-a
  alias bits as old destination, start=0 and all elements below VL as active.
  It is not a general replacement for masked or restarted comparison tests.
- For VL=0, every destination bit must equal the original alias bit. For
  VL>0, active bits must equal the fixture result; tail bits retain the
  original allowed set `{old, 1, wanted}`. Packed must-zero/must-one masks
  preserve this predicate. Rejecting an entire byte rather than counting
  each wrong bit changes detailed error totals, not acceptance.
- All 512 halfwords of each input are reconstructed from original formulas.
  Five deduplicated rows are storage sharing, not five selected test inputs.
  Both original 1024-entry arrays retain zero-initialized unused upper halves.
- The original loop order, 682 calls, mask initialization, 130-byte output
  initialization, status/flags checks and both guards remain in the successor.
  No vector instruction is introduced into scalar verification code.

## Fresh Evidence Checks

The reviewer independently hashed all 126 entries in `pins.json`: no missing
or changed files. The manifest hash and SoC/Spike ELF hashes match `READY.json`.
The Host receipt reports 698368 input-halfword checks, 11173888 exhaustive
byte-alternative checks and 682 flags checks. The separate actual-source flow
receipt reports byte-identical original/transformed call records, one positive
pair and six negative pairs. These are Host proofs, not RTL measurements.

## Remaining Gate

Before a DUT acceptance claim, bind the frozen M8 image and relocated helper
PCs to a strict checker. It must validate actual dynamic calls, input writes,
all 64 result bytes, flags, returned vstart and guards, retaining original
predecessor order. A successful console marker or Spike cost run alone is
insufficient. Keep original failed/time-limited artifacts unchanged.
