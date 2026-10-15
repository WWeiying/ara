# NF2 Four Archived Singles: Software Reference

Scope is the four exact failed singles in `source_manifest.json`, in the user-confirmed order:
`u0_s0_b1_m2_f1`, `u1_s1_b3_m2_f0`, `u0_s1_b5_m3_f1`, `u1_s0_b1_m3_f0`.
The source manifest binds each original C/S/ELF/case.json and measured board failure.
This is a source-derived real Sv39 M/S-mode fixture, not byte-identical Linux execution,
not the complete original parent matrix, and not an AddrGen mock.

The existing Sv39 assembly is unchanged. The original masked segment instruction
encodings are `20055c07` (load) and `20055c27` (store). The fixture retains VL8,
e16/m1, field seeds, mask bits, base/split offsets, full 128-halfword output,
two guards, and 8192-byte memory oracle for every case. Its additional neighbor
register/PTE/CSR checks are fixture evidence, not claims about Linux signal frames.

The original Linux mask array is 128 bytes. This fixture uses 16 bytes per case;
the actual capacity64 helper reads 8 bytes. Those consumed bytes retain the
original repeated mask pattern. Extra memory/guard coverage does not establish
that all 128 original mask bytes or the entire Linux environment were copied.

The two active cases fault at element2 (load) and element5 (store) and retry at
the same instruction PC. The unmapped store refills the restored page before
poisoning both already-completed element2 fields. Both all-off cases enter only
the S-ecall handler: no page fault, no fault retry, and no target memory accesses.
Their full memory/PTE/guard checks occur BEFORE cleanup/refill (phase3), then
again after cleanup. The all-off unmapped load's later refill cannot conceal an
earlier target side effect. `start=8` is a nofault sentinel, not a retry vstart;
the returned architectural vstart is zero.

One authorized Spike execution completed: 23.180048s, numeric rc0, 1,315,037
parsed instruction/commit records (includes fault attempts; not hardware retire
count), 3,567 firmware checks, eight full checkpoints, two page faults and four
S-ecalls. Actual ISA: `rv64gcv_zfh_zvfh_zvl1024b`. Bound: 3M instructions,
120 seconds, 512MiB raw-file ceiling. Raw trace is 161,343,303 bytes. See
`reference01/{bound,reference_attempt,status,host,source_proof}.json` and
`STATIC_COST.md`. Host oracle tests rejected 16 mutations; none are DUT results.

Only one reference was executed. No VCS simulation, RTL build, Linux run, or
live-simulator query was performed. `READY.json` seals the source/reference
artifacts; the separate CSV observer and future runner remain prepare-only work
and are not part of this source/reference acceptance.
