# Prefill harness initialization failure and repair

## Evidence

The initial `prefill-native-q4-vcs-20261028-01` experiment was stopped and its
FAIL record, ELF and logs retained. It did not produce performance results.
The console log reached `PREFILL_BEGIN trial=0 shared=0`, then reported:

- Cycle 12474: accepted instruction `0x42802057`, response exception asserted.
- Disassembly at `0x80000992`: `vmv.x.s zero,v8`, the first drain operation.
- The new test entry had not executed a preceding `vset*` instruction.
- `ara_dispatcher.sv` resets `csr_vtype_q` with `vill=1`.

The older grouped-PV test explicitly initialized e32/m1 and v8 before this
drain. That setup was omitted when creating the new test. This is a harness
initialization error, not evidence of a Prefill arithmetic or RTL fault.
The VCS log file was more heavily buffered than console stdout; looking only
at its tail initially hid the already printed trial marker and exception.

## Repair

The test now executes `vsetivli zero,1,e32,m1,ta,ma` and `vmv.v.i v8,0` before
resetting FCSR/VCSR and issuing the initial drain. Initialization is outside
the timed region and identical in both comparison modes. The GNU disassembly
of build `prefill-native-q4-build-20261028-02` confirms this exact order.
No RTL, quantizer, arithmetic kernel or acceptance tolerance was changed.

The failed source is also preserved as
`verification/out/prefill-native-q4-vcs-20261028-01/native_main_before_fix.c`.
The successor run uses a separate service and output directory with suffix
`-02`; it does not replace or relabel the first run's result.

## Avoiding wasted simulation

`early_guard.py` watches this no-fault benchmark's console log. An accepted
response with `exc=1`, or a nonzero contract-monitor error field, saves the
first failing line and signals the owned simulator process. Normal valid
responses and unaccepted exception fields do not trigger it. Parser tests
and an owned-child termination test pass. The ordinary end-of-run numerical
and protocol checks remain mandatory; the guard does not replace them.

The successor's actual execution result is recorded by its worker. Build
success and this static diagnosis alone do not establish numerical PASS or
performance improvement.
