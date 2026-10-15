# Original E8 M1 Full4095 M9

Single original continuous3seed/25op source port, not Linux replay. Reuse the
accepted full_e8_m1_packed_prepare01 SoC ELF and complete reference, no rebuild.
CAP128/physical1/vtype0, full130B output16words+tail2, mask128 software bytes,
vlm16 bytes. All524160 result bytes,8190 guards,4095 returned
vstart,53235 helper instructions and69615 output reads are mandatory.
Actual s6 initializer is SH FIRST then16 SD. Fresh output is checked each call;
fresh128B mask each source group and original a/b once per seed remain required.
No automatic RVV, source/helper/RNG/order/failure fallback or full oracle change.

Exact op19 target0x38813c57 is VSLIDEUP.VI offset2; VL1/2 can legally retire
without target backend uops. Required-owner qualification in both Strict and
OwnerObserver uses actual helper encoding and original VL/vstart. No gold
mutation, no all-slide or all-masked waiver. Nonempty op24, active VL3 slideup,
slidedown and five per-call memory helpers remain compulsory. All six generic
event families and pairing/replays/lossless hashes remain unchanged.

New-worker Host constructs one full4095 stream plus focused negatives; it
does not read any DUT/reference trace. Immutable gold/spec are shared safely
between isolated mutable snapshots, with stage timings. Software Host/reference
are not rerun. Numeric child outcome persists before postchecks; all error
vetoes, exact reset/ABI/ELF/private copies, image/config/source pins stay active.

Fixed jobs1 case10800s worker12000s service13200s. Fresh actual simv count plus
own1 and reserved0 <=24, available memory>=32GiB. Exact Averroes entry JSON
binds plan/image/READY/allpins. Direct worker service and ExecStopPost persist
real exits and perform bounded metadata collection without semantic CSV reread.
One actual startup CPU/CSV-size/identity and hook check, then no polling.
No other running tasks, sealed checker or original rejected results are touched.
