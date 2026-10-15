# Joint Load Regression, Baseline Versus Candidate

Freeze the same four real modules and dependencies as successor01. Only VLDU
differs: M6 versus parent candidate92f9ebbeb136cd3ff11ae1a8ea92ce31b3aac077ae0667f79d82e919a3603401.
One compile per version, one simulator invocation per version. Baseline runs
the two normal scenarios; candidate runs those plus five exception scenarios.
Compare the complete per-cycle normal traces byte-for-byte, including idle
cycles, AR/R, descriptors, mask owner/windows, requester/final grants, write
data/BE, completion and sequencer response. Do not change either RTL input.

All cases e64m4, base8-aligned, unit stride, real MASKU packed-predicate input:

| ID | VL/start | Predicate | MMU fault | Grant release |
| --- | --- | --- | --- | --- |
| 0 | 9/0 | alternate active, vm0 | none | immediate |
| 1 | 9/0 | vm1 | none | immediate |
| 2 | 9/3 | all-active, vm0 | element5 | cycle60 |
| 3 | 13/5 | all-active, vm0 | element7 | cycle60 |
| 4 | 9/0 | all-active, vm0 | element8, terminal word | cycle60 |
| 5 | 9/0 | all-active, vm0, FOF | element5 | cycle60 |
| 6 | 9/0 | all-active, vm0, FOF | element0 | immediate |

Fault bases put the specified element at the first address of a protected
4KiB page. MMU returns identity translation or cause13 only after real MMU
requests; it never directly injects an AddrGen descriptor. AXI model queues
actual AR handshakes, returns all declared beats in order, and fills bytes
with a deterministic address-dependent pattern. No invented R without AR.

Use the existing consumers/vldu_exception_tb.sv public stream_register per
lane: requester acceptance and delayed bank final grant are distinct. Full
512-byte destination groups at vd24 and vd28 begin poisoned. Verify every
enabled write's owner/address/BE/data, reject duplicates and any pre-vstart,
masked-off, fault/suffix or tail write, and check both entire groups after
each instruction. Exception response must follow full prefix bank writes.
For delayed cases explicitly observe a real pending bank write while
exception completion is withheld; grant delay must actually be exercised.

After each primary instruction, require real MASKU/VLDU/sequencer idle and
empty mask cuts before any external flush. Fault cases then apply only a
port-level flush after idle (dispatcher eligibility modeled, not a CPU).
Issue an ordinary masked VL5 load to vd28 without reset; recheck the preserved
vd24 group and the new group, mask windows, no duplicated old completion.
Reset only between independent primary scenarios. No forced internal state.

Each instruction has a fixed200-clock progress bound; 60-second host bound
is separate and includes proven ~11s startup overhead. Stop first failure,
preserve all output, no automatic retry. No SoC rebuild or Linux claim.
FOF checks backend exception/fof/element outputs and prefix ownership only;
dispatcher trap suppression and architectural VL CSR update are not measured.
