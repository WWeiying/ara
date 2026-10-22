# NF2 Final Four Independent Source/Reference Review

**Accepted source/reference only; no blocking finding. No DUT acceptance or
launch authorization.** The latest explicit parent tuple list, not the stale
batch03 heading, is the selection authority. No existing file was changed.

| Exact source single | Base | Mask | Required behavior | Actual reference |
| --- | --- | --- | --- | --- |
| u0_s0_b1_m2_f1 | P-6 | 24 | load fault/restart2 | cause13, mtval P+2, samePC0x80001180 retry2 |
| u1_s1_b3_m2_f0 | P-12 | 24 | store fault/restart5 | cause15, mtval P+8, samePC0x80001188 retry5 |
| u0_s1_b5_m3_f1 | P-22 | 00 | no page-fault/store access | target access list empty; only S-ecall |
| u1_s0_b1_m3_f0 | P-4 | 00 | no page-fault/load access | target access list empty; only S-ecall |

P=0x40001000. Active fault address allowances remain P+2/P+4 and P+8/P+10,
respectively; not an arbitrary protected-page address. All four target phases
are S-mode, VL8/e16m1/vtype8, initial vstart0. The nofault start8 is a source
sentinel, never a restart index. All terminal vstart values are0.

## Source And Field Ownership

The actual archived C selectors and manifest C/S/ELF/case identities match the
exact four; each is a failed independent single with exit1. They remain
single_current_oracle_trial derivatives, not byte-identical original-parent
Linux replay. Source formulas were independently evaluated for both64-element
fields and all4096 memory halfwords in all eight phases, matching the sealed
oracle. Actual SoC/Spike disassembly and symbols match ELF bytes directly;
load/store encodings20055c07/20055c27 and prior Sv39 assembly are retained.

Load b1 has no completed active prefix; its first attempt has no accesses,
and retry accesses both fields of elements2/5. The intermediate faulting load
segment2 retains the original partial-field allowance, not a requirement for
both fields to remain old. Final two-field/tail/guard checks are not relaxed.

Store b3 first commits element2 fields at P-4/P-2 with127/156, then faults at
element5. Repair/refill precedes same-PC retry5; both completed element2 fields
remain XOR5b poison in the final full-memory oracle. Retry accesses exactly
element5 fields P+8/P+10 with166/195. No faulting-store field can commit on the
denied second page before repair in this selected split0 geometry.

Each all-off case has a full precleanup phase3 checkpoint while leaf1 remains
invalid, then cleanup and a second full checkpoint. The u1 load refills only
after phase3; refill cannot hide a precleanup target side effect. Their unused
fault snapshots/second trap records remain initialized. No page-fault retry or
prefix poison is accepted for these two cases.

## Independent Raw Result

One full offline raw parse, no Host suite, Spike execution or simulator run.
Actual audit command exit0 (session55940, final tool chunkffbd0a),55.891347s.
Sealed reference execution itself records rc0,23.180048s,3M/120s/512MiB bounds,
actual ISA rv64gcv_zfh_zvfh_zvl1024b; no profile substitution.

- 1315037 parsed records, including5 reset-ROM records;1315032 firmware records.
  These include fault-attempt records, not DUT retirement counts.
- All actual PC/encodings checked;3567 scalar check arguments match; no default
  trap/mismatch path. Case counts756/758/474/474 match the full source oracle.
- Eight ordered checkpoints,184296 checked byte positions across memory, PTEs,
  snapshots/output/mask/guards, plus original permitted field-address choices.
  Full8KiB memory at every checkpoint; final128 halfwords and2 guards per case.
- Six handlers: causes13,9,15,9,9,9. Both fault CSR contexts and vstart writes
  checked; no mepc overwrite before retry. Two retries and six target records.
- Post-target CSR values8/8/0/117/5, final seed/neighbor guards, completion magic
  and HTIF1 verified. Reference restore readbacks are present and scalar checks
  pass; this does not substitute for future DUT CSR evidence.
- All producer checkpoint/action/access/trap/count fields independently rebuilt
  and equal after JSON key normalization. No unknown raw-line category.
- 78 pins verified before/after. Existing Host34816 rows/16 negative tests were
  reviewed as sealed evidence, not rerun. CSV adapter/runner are outside READY.

Limitations: both Linux protection and unmapping use an invalid Sv39 PTE here;
Linux signal-frame/SEGV subtype equivalence is not proved. Original mask allocation
is128B, fixture16B, helper consumes8B at capacity64; consumed values are preserved,
not all original mask storage. Acceptance covers these four exact source-derived
cases, not the full96 parent, all40 failures, a new DUT image, or Linux closure.

READY SHA: `d427f9c9846e0c59d9374efb6fbae020df08c8f6a4472ce740e05ddf4306aa2f`
Result SHA: `f7c60873358baeeea6d8a0798a6ec8e0bdf5ad0f9daeb2750784ec0f23c918e6`
Verified-pins SHA: `7544ab6c982a672afcf8611fad92b184e313c307d96720ebd705e4b8ebdb5c54`
SoC ELF SHA: `cd2aa14f5251bf32353bf256b5c64e9035dc0ed266688bece78f7c691ac234d2`
Spike ELF SHA: `d7bd752c8bce39872d761e8bc521406f48ab67f07c69a2640e740270a6098001`
Raw SHA: `f921f74412ff2fff9490f24330ca52a7ddf01ecc6a8d0354579bb7c689c9e438`
