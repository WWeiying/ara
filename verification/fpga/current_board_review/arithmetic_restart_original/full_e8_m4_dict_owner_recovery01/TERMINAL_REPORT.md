# Full E8 M4 Architectural Recovery

Status: ACCEPTED_ARCHITECTURAL_RECOVERY_NOT_OLD_SERVICE_PASS.

Exactly one approved offline semantic pass of the original closed327166937-byte
CSV completed. Actual child PID3123875, OS wait0,367.662512071s, no timeout,
no retry, within the fixed600s budget. No VCS, Spike, build or RTL change.
The original producer NOT_PASS/aborted=true, actual service exit1 and collector
NOT_ACCEPTED remain unchanged. Original simulator child0/10573.338762348s is
preserved separately from this successful offline checker process.

## Root Cause and Measured Resolution

Original rejection was call1200/originalordinal1201, seed0/op19/li1/mode0,
VL1/start0, helper8, PC80000fd6/code38813c57, retire771538/arch13209,
alloc0/done0. Exact instruction is `vslideup.vi v24,v8,2,v0.t`.

Frozen M9 decodes unsigned offset2 and locally completes slide-up when
offset>=VL. Thus vstart<VL alone is insufficient to require a backend owner.
The successor uses actual source-helper encoding and original validated VL and
vstart, not an all-slide or mask waiver. Frozen RTL explains the local completion;
the CSV measures retired/architecture ownership, not internal null_vslideup wires.

Full saved owner ledger confirms all18 narrowly changed zero-based calls
1200..1205,2565..2570,3930..3935 have alloc=done=0. All are exact opcode38813c57,
offset2 and original VL1/2. The first matches the original rejected record.
All20475 helper memory owners and2592 necessary targets completed, including
117 op24 memory targets. Total actual backend alloc=done=23067. VL3 slide-up,
slidedown and missing helper pair negatives reject; no other required target
class was relaxed.

## Complete Source Scope

- Original contiguous4095 calls; no partition reset or reduced prefix.
-2096640 result bytes and8190 guards;4095 returned vstart values zero.
-53235 original helper instructions,4095 occurrences at each of13 positions.
-266175 packed oracle reads; every call fresh514-byte output initialization.
-2831332 CSV rows,2650057 retirements, firmware through CTRL2650051.
- Last cycle18820803;45047 CVX requests/responses and architecture requests.
- Zero CVX exceptions; full lossless generic protocol and strict counts agree.
- Original source initialization, RNG/order, exact PC/code, CSR/startup/reset,
  actual memory/address/BE/data and complete defined oracle remain enforced.
- Original integer source has no explicit fflags oracle; none is claimed here.

This accepts the complete source-faithful M9 software port under its original
oracle. It does not turn the old service into a success, establish a Linux
execution, or by itself close the historical Linux stall cause.

## Independent Entry and Preserved History

Hilbert exact entry is
`../full_e8_m4_owner_recovery_entry_review01/ENTRY02.json`,
SHA f7ab07af6d9751eb11037b14d8d4be7d3821d4dd8c13ca3673b05869bd5a7863.
Original recovery plan01 was never executed: its late-abort publication gap and
withdrawal are preserved in PLAN01_NOT_ADMITTED.md. The checker12 Host and
successor publication4 Host passed actual0 without rerunning the large Host.
Final runner02 performs expensive report save/hash before the terminal signal
decision; outer actual wait0 remains mandatory.

All813 bound input pins and the closed CSV identity/digest matched pre/post.
The final inspection read only saved reports and receipts, not the CSV again.

## Durable Evidence

All terminal files below are in `prepared02/fullparse01/`:

- wait.json: a7c89358adb937804caa3f0b4282863361e13b4d69b474a37acda445154d88a7
- result.json: c8be3bb4a2b4b5c23b69882f963bfaf6f9aa495fa85f8943a828a980652be03d
- strict.json: 69e3e12fda9ec6aebc3385f412b3e71db2719221d35b3cf6557d12f1ff1466d6
- terminal.json: 5167c38c7d2cbfdd9917508e99095672395159202ed6fc4c69165dfe161e6454
- attempt.json: ce7db41adce7adaf2627f464dd55349fa2b6b1bc5aea48b7cdde71762d36db7a

Final prepared02/plan.json SHA
38d90ad0213fbb7d1e9f7779d687ecbda32d07cc5623f6a478e142067e1d9b96.
Original CSV SHA
3aba5305e8d57c7f49abd93f103bd6b5ef5e912d6629c351e60193e2f44618ca.
Checker SHA7b5e4ae93cdd3b338dfd0d72b6ef36c3e7848f46d67a1cb5352a844ae07886fc;
runner02 SHA5b4ea2f7939aa7da2df175afef5968b206e82cb8e5cff4013ba805ebd4fa802d.
