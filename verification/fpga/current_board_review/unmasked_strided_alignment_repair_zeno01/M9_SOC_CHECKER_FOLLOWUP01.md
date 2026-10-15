# M9 SoC Checker Presence Follow-Up

Scope: quick static follow-up requested by Aquinas after source-contract review. No new reference traversal, Host campaign, simulation, launch query or production change.

Reviewed dut_check.py SHA0dd3f3f397f1eaed1970ea0722fba9161969910e15b4cb606caa61cbcdbedd59. Any successor is a separate version; this finding does not presume it remains unfixed.

## Concrete Protocol Coverage Gap

Current unmasked_strided_alignment_soc_m9_prepare01/dut_check.py only records arch_start/uop_alloc/uop_done when insn equals the target encoding. finish requires two target owners and one target CVX fault, but has no required per-owner completion gate for other real helper memory instructions.

Discriminating trace transformation: retain all retire, CVX and architecture events, both target allocations/completions, exact scalar oracle operands and successful data checks; delete one entire allocation/completion pair belonging to the VL16 seed load, full fault/result/next snapshot, or legal v8 successor. Custom checker state is unchanged because those events were never tracked. Frozen generic validation still has matching retire/CVX/arch sequences, balanced remaining uops and no pending owner. Thus combined protocol-presence evidence can omit that necessary helper owner. This is a static counterexample, not a claimed mutated full-run measurement or a DUT/RTL failure.

## Minimal Remedy

Track actual architectural memory owners and their completed allocations, not only target encodings. Require completion for each actual nonempty helper memory dispatch (including staging/snapshots/successor), with actual source context and generic sequence validation. Do not guess a fixed aggregate count or manufacture Spike CVX events. In this specific fixture the target's first attempt has a real valid prefix and retry has one remaining element, so both target owners are legitimately required; generic harmless CSR replay remains distinct.

Add one focused boundary negative removing a complete non-target helper-memory pair while retaining target owners and other uops. Data oracle and numerical counts must not substitute for lifecycle presence.

Tesla/Aquinas/main must preserve any already started valid simulation. This postchecker coverage gap alone is not a reason to cancel or retry DUT. Use a corrected independent successor and closed original CSV if execution has begun. Do not edit its sealed running inputs. Aquinas was notified immediately; no launch/cancel was performed by this reviewer.
