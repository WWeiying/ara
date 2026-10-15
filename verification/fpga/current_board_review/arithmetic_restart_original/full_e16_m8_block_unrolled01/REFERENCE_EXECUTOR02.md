# Finite Reference Executor Successor

No reference was launched against the original entry. Tesla found its proposed
debug-until plus --instructions combination did not enforce the declared4M
step limit: installed sim.cc idle only decrements instruction_limit outside
debug, while interactive_until repeatedly calls step without that decrement.
The original reference.py, entry.json, Host results, model, raw observer and
both compiled ELFs remain unchanged; this is not an actual reference failure.

The sole successor command uses finite debug script `rs 4000000`, then `quit`.
Installed interactive.cc:409-419 processes min(INTERLEAVE,remaining), then
reschedules only steps-actual_steps, with done checked each step. There is no
until loop or instruction-limit flag whose debug semantics are assumed.
The actual same Spike binary is pinned along with the inspected source.
The independently accepted e8/m8 predecessor uses this same finite approach.

The one complete reference retains120s and768MiB hard limits, exact original
typed16 full4095 oracle,128SD+SW4 initialization,128 full-word+tail4 reads,
allphysical8-register values, mask128/upper64zero, CSR11/vstart and raw original
exit/console checks. All150 prior pins remain, with only successor evidence
added. No compile, Host semantic rerun, DUT or old-run polling is needed.

Cost comes from the complete actual commit retirement ledger at replay_exit,
not a nonexistent debugger minstret receipt. Numeric Spike and offline child
waits are durable before checks. At firmware<=3M the result is software-only
READY; over-target is HOLD. Truncated scope, timeout, observer failure or any
new error stops without retry. The original Linux historical stall remains
outside this source-port acceptance.
