# Gap46 AKV Plan A

Only new files; no RTL, frozen helper, old test or app Makefile edits. Software
compilation and host execution only during preflight. No VCS, Spike, DVE, URG or
Verilator invocation. Runtime is a future single 600-second bounded case, with
no automatic retry, oracle relaxation, or assumption that the budget suffices.

## Composition

Import `run_gap46_akv_checked_extension` and call `install_hooks()` after parent
defaults and before `checked.main()`. Register case `akv_gap46_skew_context`
(`app:akv_gap46_skew_context` in selection). Installation is idempotent and
captures/delegates precheck, worker, summarize and directed hooks. Only standalone
`main()` assigns `checked.SCRIPT`; the parent owns its own SCRIPT and scheduler.

Use the standard `selection.json` `cases` array. Copy the case **exactly**, without
appending sources, evidence or metadata. `compose_gap48_selection.py` must bind
the draft, seal and composer at batch level, not mutate this case. The record
stores the exact case template; the sole deterministic extension is its own
record path/hash. `sealed-precheck.json` binds the draft hash, canonical complete
case hash, precheck result and checked files. The final selection binds that seal
and repeats its result. Parent batch preparation remains the parent's task.

The frozen VCS directed `_run_test` does not add `+AKV_PERF`; the Makefile
`akv_v2=1` automatic plusarg belongs to Verilator only. A gap46-only directed
hook temporarily wraps `_run_monitored`, adds exactly one `+AKV_PERF`, enforces
600 seconds and restores the prior function in `finally`. Original command.json
remains untouched; new work/gap46-command.json records the effective command.
Runtime requires agreement with the wrapper's actual coverage.command.json.
The existing runner uses a single case in each directed subprocess, not shared
in-process concurrent simulations.

## Data And Architecture

12 operations: V1 FULL, Q/K/V ROW64, V2 REFILL, V1 REFILL, ROW64 Q,
V2 FULL, Q/K/V ROW64, RELEASE. Exactly operations 5/6/7 trap cause2,
exact ELF-bound instruction PC and tval zero or opcode. Descriptor version1,
F16/D64/one query/one token/tile0. V1 source skews2/6/14, stride130; V2 aligned
stride128. All six padded sources occupy one page. Each successful FULL is
followed by external payload XOR0x5a5a before loads, which must return the
original epoch pattern, never the poisoned memory. Epoch B differs from A.

Before every command, all v8..v11 are seeded (256 halfwords). All 256 are checked
afterward: successful row updates exactly the first64; other commands preserve
all. Six complete 256-byte external buffers, both descriptors, seed buffer and
both frame guards are compared each phase. Checks are bit-exact integers;
there is no FP computation or tolerance. CSR seeds are fflags21/vstart0;
`csrr t0,fflags; csrr t1,vstart` immediately follows each custom opcode, before
stores and before the next vsetvli. ELF audit enforces the actual five words.

Common checks: 12*(256+1 seed+1 frame guards+6 sources+2 descriptors)=3192.
Host adds two ABI/context checks per phase:3216. DUT adds trapcount+two CSR
checks per phase and three details for each illegal:3237. Host uses existing
ABI validators and V2 reference full/row APIs. V1 is a bounded validated snapshot
copy, not an independent hardware/microarchitecture model. Host does not claim
CSR, illegal-instruction, protocol, timing or coverage execution.

## Independent Runtime Contract

Require generic checked independent PASS/trace audit, immutable ELF/image,
nonreused complete per-case VDB and exact selected precheck inputs. Replay UART
phase/check counts, ELF sites, all CSR/trap records, and twelve PERF terminals in
order. Commands are0,2,2,2,5,1,2,4,2,2,2,3. Faults have validation_error12,
read_fault0; only operation5 has v2_rejected1. Operation6/7 retain V1 mode and
must have rejected0. FULLs each read descriptor64+Q128+KV256 bytes in four
ranges; six successful loads replay128 bytes; fault/release have no reads/replay.
Counters are per command, not accumulated. All cycle fields are retained;
busy cycle totals must fit the trace. No fixed latency or bank conflict count
is guessed. Lifecycle is serial and contains no FENCE.T or microreset.

CSV replay independently pairs requests/responses by live ID, checks custom
opcode/outcome order, exact successful retirement PCs, and the values of all
24 immediate CSR retirements. The three negatives do not retire. Terminal
ARA_CONTRACT counters must agree with CSV, with exactly3 exceptions and no
pending request, stalled handshake or protocol error. PERF supplies exact
validation reason and context-ready state that architectural cause2 cannot.

Native proof rechecks structured XML definitions/checksums/source binding and
0/640 baseline positions. Line uses explicit linebb.index; branch reverses raw
within **each spec**, not the whole instance. Candidates: context Block6/raw7,
Branch2(0)/raw5; engine Blocks109/160/164/165 at112/163/167/168 and
Branches11(2)/12(7)/12(8) at90/138/137. No FSM IDs are inferred. Runtime records
all nine actual raw bits; missing hits remain GAPS_RETAINED, not invented gain.
Raw diagnostic gain is not a native DVE percentage or waiver authorization.
These candidates require legal mapped payload transactions and architecturally
specified negative context commands, not force/invalid internal state.

## Offline Verification

`build_gap46_akv.py --output NEW_DIRECTORY` builds host and RV64 ELFs with frozen
common CRT/helpers, checks RAM fit and ELF sites, runs the host oracle,20 direct
C bit-corruption negatives and Python fail-closed tests. It binds dependencies,
tool binaries, command exit statuses, source/RTL pins, native definitions and
negative reports. `prepare_gap46_akv_admission.py --build DIRECTORY` seals and
replays precheck twice, emits exact selection, and never prepares a batch.

Synthetic positive/negative runtime fixtures test checker behavior only; they
are explicitly labeled and cannot be submitted as DUT evidence. Timing and
native closure remain pending the parent's one authorized checked run.
