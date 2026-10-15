# Execution01 Host Review Entry

Parent admission: `../../full10752_numeric_admission01.json`; reviewed source
files remain unchanged. One `generated01` invocation completed with actual
numeric0/3.076510606s, recorded in generation.command/log/wait.json. No reference
or DUT entry point exists. Host stage below has not yet run at design handoff.

`original_wrapper.c` includes the complete generated runtime-only original C,
renaming only its entry. Its exported original_value/selected call the unchanged
static original extra_value/rounded/selected, which remain byte-identical to the
canonical C. The entire helper stub result and sat come from these C functions;
generated ROM is only read afterward for independent full514-byte comparison.
There is no Python model in the Host executable's helper path.

Original input and mask fragments execute in the original TU with after-store
recording. host_stage.py strips recording calls and checks source text identity;
mask braces are the only instrumentation syntax addition. Three C source arrays
and four C-built mask/event streams become independent expected histories.
packed_wrapper.c intercepts every actual __builtin_memcpy in packed.h, not a
forecasted event. host_copy checks address, width, value, bank, ordering, per-call
init/read indices, helper ordering and all mask epochs/source writes. Tail is
exactly2 bytes. Every helper sees complete a/b/mask/out and untouched upper backing.

Each original and packed full program runs once per mutation in the same process,
resetting its own globals and using the same unchanged C helper stubs. Entire UART,
return code, checks/elements/errors and28 boundary records must agree. Positive
compares10752*514 bytes and10752 sat values against ROM. Eight diagnostic controls
cover first/middle/last data, front/rear guards, full32 vstart, full32 saturation,
and seven mixed calls each producing vstart,data0,data511,sat,combined-both-guard
errors. Static review moved the existing sat-only fault to zero-based768 and the
existing mixed faults to768..774: seed0/op0/VL512/mode0/si0/start1, controls0..6.
Original element8 has a=b=0 and result0, proving these rows are not all0x5b;
the helper asserts this qualification. This covers the dictionary fallback while
vstart-only call0 still covers the row0 fast path. No additional test is added.
The mixed35 errors print exactly20 details; complete original/packed text
comparison covers errors19/20/21 and first20 suppression, not just returncode.

Four lifecycle rejection processes remove a same-value source write, one ordered
mask SB, a same-value second-call init store, or an actual output-read event.
They must exit90 at the next exact event/conservation check, not falsely accept
unchanged shadow bytes. Full positive UBSan is separate, with no recovery.
PROT_NONE end protection tests514-byte init and all65 reads on good and double-bad
buffers. The page-end fixture has intentionally unaligned start; memcpy semantics
allow this on Host. Production buffer alignment8 is a separate linked-image gate.

All children use run_bound.py with120s limits, exclusive logs/actual wait receipts,
no retry. host01 is exclusive. Any failure preserves FIRST_FAILURE and stops before
target compilation. Intended invocation after Tesla short review:

```sh
python3 host_stage.py
```

Host C does not prove RV64 assembly lowering. RV64 fixed_compare uses the unchanged
reviewed +r bad / two read-only uint64 inputs / memory clobber BEQ-LI template;
no vector/CSR/fence is added. Equal skips LI without changing bad, unequal sets1,
and no branch bypasses later reads. Compiler allocation and linked machine bytes
still require inspection; this Host stage cannot certify them.

README source line numbers are descriptive and partly offset; exact hash-bound
anchors/retained substrings govern this stage, as already noted by Tesla's review.
No original README, generator, packed/port header or old failure is rewritten.
