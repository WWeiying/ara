# e64/m2 Full5985 M9 Entry Review

Verdict: NO_BLOCKER_ENTRY_REVIEW for exact plan25fd2b8fd4523771d3ebfa61581f7c960ef26ff009e99ed3176f027a33f96b14. Parent's conditional one-launch authority may be consumed by Zeno after the actual resource/service gates pass. This is entry admission, not DUT acceptance or Linux closure. Reviewer performed static reads/hash checks only, without tests, reference rerun, compilation, live queries or launch.

All1126 frozen plan pins freshly match. ENTRY01.json carries the full identical pin map and exact scope/image/reference fields required by core.reviews. Frozen M9 image48d9e4d2acb1fa239e05549fe695caad36af34c1f02aaffe041bb8261e302b5a, actual SoC ELF4d99a658c744e1cf9d6ab193cc34c6de73bd268505585759ad7038b8f7abc897 and accepted reference READY e6fb21e24903c5c3acc6519d946ebd69a757f070e841c41d067fc89347c8c181 are exact. Independent terminal4036aa11044c2e07f19435b6d84b27bb8c843f1b16ed72f5ff8fcc6a68a2ae0d is checked using its actual schema, counts and artifact hashes.

## Complete Source And Protocol

Strict model retains35ops/3seeds/5985 original ordered calls,191520 results,11970 guards,77805 helper instructions and203490 eight-byte reads. The output is272B,34 LDs with full u64 guards0x5b; it is not a typed16/tail4 shape. SoC-specific lifecycle binds the real FP clone and seed argument, eight input table reads and64 ordered SDs per each of1890 FP calls, including empty/equal-value cases. Original276 seed stores,16-SD physical128B mask clearing plus bitsets, per-call34-SD initialization, full fallback veto and returned vstart remain checked. No extra RVV or fflags result oracle is introduced.

Reset GPR initialization is restricted to the separately bound frozen M9 FpgaEn0 authority and RTL/config/image identities, not unknown-register defaults. The real prologue, decoded scalar store register/address/enables and actual CTRL0 exit are checked; failure.part.0 is a veto. This is the SoC ELF, not Spike HTIF1.

The actual generic lossless six-event observer is combined with Strict on the same CSV stream. OwnerObserver matches retired offloads to architectural owners and requires each necessary owner to allocate and complete matching backend work. Required scope is29925 setup-memory owners plus3762 targets, including117 nonempty op24 targets. Exactly18 legal VI2 no-op targets may elide backend work; ordinary active/slidedown targets are not waived.33687 is a minimum necessary owner count, not a fixed total uop count. Optional owners still must obey actual token pairing.

## Actual Host And Failure History

Host02 receipt actual rc0/233.05183464335278s,28 tests/0 errors/0 failures; all11 Host input pins are identically included in plan. It consumes a full5985 constructed stream and actual-machine ABI sites, not a captured DUT trace. Reviewed negatives cover each required helper pair, active target/op24 pair deletion, generic dropped events, legal empty/VI2 versus active VL3, fresh init, full last guard, vstart, failure PC, unknown source register and incorrect byte enables/data. Added snapshots cover a/b stores for all three FP seeds and reject skip/reorder/duplicate/wrong bank; missing whole refresh rejects. Snapshot tests do not claim independent execution of preceding ISA history.

Original Host preflight missing filename, asset parser empty contract and Host01 literal-newline failure remain historical evidence, not accepted outcomes. Host02 uses its separate fixture/source snapshot; the accepted owner contract is owner_contract02, not the failed empty contract. No full Host or reference was rerun by the reviewer.

## Execution And Terminal Boundary

Dryrun SHA a09bea62a4f0efe4501386181fa2db57ad047884b3b9f5cdd36fecb10c05dd03 binds the same plan and exact private ELF/trace paths, frozen M9 simv, seed1 and NO_FSDB. Jobs1/case10800/worker12000/service13200 are fixed, no build/retry/FSDB. The6724.6043s estimate is only a projection, not a runtime guarantee. Runtime resource gate and direct systemd owner identity remain required; reserved_slots0 does not ignore actual live jobs.

The reused worker records numeric monitor exit before generic/strict postchecks, keeps abort sticky, checks disk plan/source/image/review pins at terminal, cancels/joins its deadline timer and invokes the mature guarded terminal publisher. Nonzero/timeout/cancel/postcheck failure cannot become PASS. Unique service launch and one CPU/trace-size observation are owned by Zeno; no repeated polling. ExecStopPost captures actual service outcome and invokes the metadata collector. Later DUT acceptance requires whole full5985 PASS, actual child0, unchanged identities, matching service/collector terminal and the complete checker evidence.

Key current hashes: checker.py5dad9f2d8cdbc60d2f99aebac21dbbc5667959cc0e6eecf07a882717f5df6b7f; worker_lifecycle.py ea3d52bce7f159d8b6e1dd5c84c811243a544dec8f5ac3c9fdef690754a6f506; replay.py cd5b9a369a5788986830fa1a65d64c278acad1e4ce1e2111ffb11466417f4136; Host02 report14dc553dde9edec5f5ec17ad1fa0f204e289001c6ca819a2054b479357eea323; Host02 process receipt a432ef25f8e00f91835af64c28c8dca9b6fcc9817afa64651b8b12fb9b605a48.
