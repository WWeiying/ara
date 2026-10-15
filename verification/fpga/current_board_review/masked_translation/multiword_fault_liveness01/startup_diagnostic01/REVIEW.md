# Startup Diagnosis and Baseline Counterexample

## Outcome

The unchanged `measurement01/simv` completes both authorized cases under the
fixed 60-second HOST bound. No recompilation, TB change, RTL change, startup
environment change or RTL-watchdog change was required. Original
`measurement01/result.json` remains ERROR, SHA256
`1d5350234182129fe27fbee581332a5af704121a41869f55db8b43e0666b67b1`.
Diagnostic command: `python3 ../startup_diagnostic.py` from this directory's
parent context, equivalently invoke that script by its absolute path.
The actual command arrays and environment are saved beside each run.

| Case | Actual simv PID | Host seconds | Simulator exit | CSV rows | Last cycle |
| --- | --- | --- | --- | --- | --- |
| VL8 | 1877044 | 11.184017 | 0 | 100 | 100 |
| VL9 | 1877136 | 11.180766 | 0 | 100 | 100 |

Both stop by the TB's intentional `$finish` at 1045000 ps, before the unchanged
2000ns watchdog. Direct `exit_group(0)` and `+++ exited with 0 +++` are recorded
in each simulator's strace, in addition to the tracer's numeric returncode0.

## Why the Original 10 Seconds Failed

In both runs the five-second process sample has no `cycles.csv`, and simv is
in `hrtimer_nanosleep`, not a busy RTL scheduler. Main-thread strace records
four approximately one-second sleeps followed by a 6.031256/6.029392-second
futex wait for a startup thread. The joined thread repeatedly attempts local
IPv4/IPv6 port80 connections and sleeps. License-server port27000/vendor-port
connections also occur earlier, but these traces do NOT establish license
pool starvation or name the private startup-thread function.

The first `cycles.csv` open occurs at host offsets 11.078747s and 11.088597s;
the simulator exits about 42/40ms later. This directly distinguishes startup
waiting from a zero-time delta loop. The old run has no strace, so its exact
blocked instruction cannot retrospectively be claimed; its ten-second bound
is shorter than the reproduced startup interval with identical inputs.

## Measured Cycles

Both cases: c3 real PE broadcast; c6/c7 MASKU-to-VLDU acceptance for predicate
windows first0/first4; c7 real MMU request, c10 cause13 response; c11 AddrGen
exception/descriptor; c12 VALID_RESULT_QUEUE, c13 WAIT_RESULT_QUEUE,
c14 HANDLE_EXCEPTION pops only first0 and accepts the fault descriptor;
c15 registered load-done and real sequencer exception response.

VL8: MASKU-done at c8; global idle at c16. The remaining first4 word in VLDU's
local cut is a later-flush responsibility, not a surviving MASKU completion.

VL9: c8 onward MASKU retains first8, valid0001 and commit1. At c14 both load
spill slots are full, so its pop does not admit first8 in that same cycle.
At c15 issue-valid becomes0, disabling `mask_input_valid`. c16..100 (85 rows)
have owner0 still running, global idle0, MASKU commit1, first8 unaccepted,
and one residual first4 word in the VLDU cut. The TB additionally asserts
empty result queue and all final-grant bits set throughout c80..100. Thus
this case is not waiting for any prefix VRF write.

Root chain in the baseline source: `vldu.sv:122` gates mask input by the issue
owner; `vldu.sv:669` pops one word while retiring that owner; the non-bypassed
spill's `ready_o` at `spill_register_flushable.sv:90` excludes pop lookahead.
MASKU commit decreases only on output consumption (`masku.sv:1273`) and its
done requires completion (`masku.sv:1715`). The real sequencer retains that
MASKU owner and drives idle low (`ara_sequencer.sv:88`). The uninstantiated
dispatcher's inspected WAIT_IDLE_FLUSH requires idle before starting flush
(`ara_dispatcher.sv:1240`), so a later production flush cannot release this
fixed point. This is a measured local liveness counterexample, not arch PASS.

## Modeling and Scope

All four modules are real frozen M6 modules. Packed all-one mask source beats
enter MASKU through its ordinary operand handshake; no internal force,
synthetic VLDU mask-valid or invented MASKU completion is used. The MMU is a
controlled three-cycle page-fault model. PE request output and both PE done
responses are registered in real RTL; the TB bus packing does not create an
unregistered response/request loop. Both measured clocks reach cycle100.
Other PE readiness is modeled true. No data requests, R traffic or result
writes occur, so tied-low result grants do not cause the measured blockage.
Pre-acceptance c1/c2 done probes show x because the TB's sampled owner is not
assigned until c3; these are not interpreted as an RTL unknown-state defect.

The dispatcher, CPU, kernel CSR, actual MMU page table and STORE are not
instantiated. `flush_eligible_model` is a static dispatcher precondition,
not a measured flush/CSR response. Original RVV16 configurations use VL8;
this new VL9 boundary does not identify their archived Linux root cause.

All 35 frozen input pins passed, including 32 RTL/include files equal to
current/M6 at the diagnostic post-check. Binary/data/input pre/post pins are
unchanged. Result SHA256:
`e9481d253b0f50c266e868a27995a298e915a9b02951b16c9761881d765b306a`.
Binary SHA256: `dc2890efdaab7ccc7ce5deec24a67e73b868bd554829f6e22f3d2b57c5720ea4`.
VL8 CSV SHA256: `a4236893f1865c95d1354fd68abea97f3cc6dad4a217dc767b5f6f3fbc3a1a83`.
VL9 CSV SHA256: `fce8fc333b13fa2313b68358cf7f29d3e8e1b7f07696ff1f259911406d9a1652`.
