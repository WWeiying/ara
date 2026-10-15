# Actual e16/mf2 Full4095 Reference Result

READY SHA02e348a7f370f32ab686c908f36bbbfb8a7fe21e9392a9613fc6d8dbcd753d17.
Reference result SHA85bcf618dd61f134ccefc80d50712c83a29ca6518b46eb9fd9425e21bb0fff39.
Status REFERENCE_FULL4095_PASS_SOFTWARE_ONLY_NOT_DUT. No new DUT permission or launch.

Original contiguous4095 calls,131040 uint16 results,8190 typed guards,
4095 returned-zero vstart checks,53235 helper instructions and36855 output reads.
CAP32/vtype15/mf2; one physical128B vector register, original low64B defined operand/result scope.
Each call fresh68B output:8SD plus actualSW4,8LD plus actualLW4;
sentinel and guards0x005b, original128B predicate with only4B vlm consumed.
All1575 mask groups and276 original typed seed scalar writes checked.
Flat ROM295224B includes full4095 expected9word rows and3x128 physical masks.
Original helper bytes,three-seed RNG/state/history and failure fallback preserved.

Actual producer wait0/12.145002164s,20 original-vs-packed Host logs paired equal.
UB trap negative actualSIGILL; all source negative/guard/boundary cases passed.
Observer boundary Host19tests actualwait0/0.869151393s. No reference raw reads in those Host tests.
Independent source REVIEW02 and exact reference entry accepted by Hilbert.
Sole Spike pid3117337 wait0/1.772060468s, no timeout/retry.
Full audit pid3117383 wait0/25.530246268s, no timeout/retry, one closed parse.
Firmware throughHTIF572522; to replay_exit572516; full raw575000 rows including5boot and2473purepark rows.
Raw59423809B, below768MiB; exact HTIF/EOF lifecycle validated, pins pre/post unchanged.
Cost margin projection1700.686685s is a proxy, not a DUT runtime guarantee or historical Linux closure.

## Unconsumed Future Worker Eligibility

future_owner_contract01 is a separate static proposal, not a deployed or accepted DUT worker.
Its6 focused tests actualwait0/0.316739713s derive actual SoC helper opcodes and frozenM9 dispatcher.
VSLIDEUP.VI0x38813c57 has unsignedoffset2; VL1/2 allow a local no-owner completion (18 source calls).
VL3+ remains required; slidedown and other nonempty targets are not waived; mask is not a no-op exemption.
Expected required owner set becomes20475 helper-memory owners plus2592 targets, including117 op24.
No total uop count is fixed. Full result/guard/vstart/ordering oracles remain unchanged.
No sealed running e8/e16 worker was modified, stopped, relaunched or polled by this preparation.
Future integration still needs exact worker entry review and its own DUT authorization.
