# e32/m2 Host02 and Exact M9 Entry Review

Verdict: NO_BLOCKER_ENTRY_REVIEW for plan
`a5685d503e6f8a422b3e7938b9c86a0e155157d4ebbf2c7774c9c15e2f23de5e`.
This is entry approval only, not DUT PASS or historical Linux closure.
Aquinas remains the sole launcher under the parent's existing conditional authorization.

## Locator-only Successor

`test_host_successor02.py` performs three exact, occurrence-checked text substitutions:
hoist four snapshot PC lookups before the stream loop, use that tuple at the
unchanged snapshot site, and write host02 rather than host01. The 35 test
methods, generated full5985 stream, observer delivery, consume order, snapshot
conditions and deepcopy calls are unchanged.

The tuple contains only four (string, integer-PC) pairs. CACHE_LOAD_PC and
CACHE_STORE_PC are constants; FP_LOAD_PC[0] comes from the frozen SoC compiled
profile. mask_schedule(0) creates local events/mask lists from that same profile
without modifying it; only element [16][4], an integer load PC, is retained.
No Lifecycle, observer, counter, freshness set, mask event list or mutable
snapshot is newly cached/shared by this change. Existing per-snapshot mutable
state copying remains unchanged: counters/cursors are copied, calls/read sets,
registers/memory/fresh sets and observer dictionaries/lists/digests are isolated;
shared model/static schedules are read-only in these paths. The isolation
negative is among the actual 35 passing tests.

Host01 remains incomplete: PID3340823, SIGTERM, numeric rc=-15,
251.96901291282848s, pins unchanged. No Host01 PASS is inferred.
Host02 actual PID3344822, numeric rc=0, 474.6449758131057s,
timed_out=false, retries=0, pins_unchanged=true; unchanged 600s bound.
Log reports all original 35 named tests exactly once and terminal OK
(473.484s unittest time); host02.json reports zero failures/full5985 once.
Original nine command pins, successor sixteen pins and six result pins
independently matched. No Host/reference/compiler/DUT was rerun.

## Full Entry Contract

- Exact accepted SoC ELF b9a09a69f9ae8d93b38f5a3f8de1049967a79127ebb473da7f321e73143039f6.
  Original full5985/35ops, CAP64/physical2, full264B/33LD including element63
  and 32-bit rear guard: 383040 results,11970 guards,5985 vstart,77805 helper
  instructions,197505 output reads. No original fflags oracle is claimed.
- Every one of 1890 FP calls retains ordered128SW and matching cache LW:
  241920 each, with24 actual seed-cache reads/stores. Masks require16SD clears
  then original cumulative LBU/SB:35280 clear stores,77175 selected stores.
  ABI/reset and actual helper PC/code checks use this ELF, not copied offsets.
- Model-derived owners:29925 compulsory memory owners,3762 required targets,
  minimum33687,including117 op24 targets.2205 ordinary vstart>=VL targets are
  optional; only18 additional original op19/0x38813c57 offset2-empty targets.
  The27 short-VL VI2 tuples include9 VL0 already in ordinary no-ops.
  All actual allocations still require matched completion, even optional ones.
  Exact helper retirement/fulloracle is never waived.
- Generic and strict consume identical unfiltered rows; owner and six-event
  protocol coverage, full input/output data, original helper windows, CSR,
  CTRL0 exit and post-exit parking remain enforced. Host negatives include
  necessary-owner deletion, actual no-op qualification, missing fresh/cache
  writes/reads, swapped FP banks/sites, mask-phase deletion, final output word,
  failures/exit, numeric17/0 and late abort.
- Imported worker uses the current checker namespace. It persists actual
  unvalidated child outcome before postchecks, retains numeric failures,
  vetoes raw failure markers, cancels on first failure, checks late disk plan
  and all evidence pins before publishing. Source ID and runtime label are
  deliberately distinct; command validation uses the actual runtime label.
- Exact frozen M9 image, jobs1,case10800s,worker12000s,service13200s,
  TimeoutStopSec360,KillMode=control-group,Restart=no,no build/FSDB/retry.
  Fresh resource admission requires total live/reserved<=24 and >=32GiB.
  Direct MainPID/cgroup ownership is mandatory. No resource/live query was
  performed by this review.
- ExecStopPost persists actual systemd exit environment before a bounded
  metadata collector; collector requires success/exited/0 plus complete,
  numeric child0, strict/generic/owner summaries and unchanged pins. Internal
  receipts do not substitute for actual service exit. The collector hashes
  closed CSV but does not repeat semantic parsing.
- Ready/dryrun bind the exact plan, private ELF/trace paths and frozen simv.
  Dryrun artifact is preparation evidence only; no claim of an independently
  observed dryrun child wait receipt. Projection6721.123s is not a guarantee.

## Identity Verification and Limits

All902 non-raw plan pins independently rehashed and matched. The903rd pin is
the already accepted223479471-byte Spike commits.log, bound to its accepted
result raw SHA a41be31e078c54403159e8bc9b83bdd2f9a458cbedb692315e76bb1cc9fba1b4;
stat/receipt only, not reread or reparsed here. Final runner will enforce its
normal full pin checks. No sealed inputs changed.

Host02 receipt SHA:
fc27368fb38a8c825fa47a0cf3a76525e4283c2616a0b8dd7fff400105d83f13

Host02 result SHA:
d27d798d576f2ed020ed9fcc79106ef0d3f406d7233f2e5f6423dbb45305711c

Host02 log SHA:
b55ffd1cafeecddabe6e78aec60328ffcf0e68d07815bd3b7b80a9c361ab965a

Successor diff SHA:
5527caa907495788c9846f2b2214e2903b22384cf1208e5ea87e0b85ff7286a0

Ready SHA:
60fb636a74433d09048817288a28811c491773fa145fd6f3e1310519d2338361

Dryrun artifact SHA:
34f3c2eec08fa1c3690c3c850893f5897b9fe88977e4fc75282752140006320f

