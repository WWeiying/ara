# Independent Original Unboxed Prefix265 Reference Review

Verdict: **ACCEPTED_SOURCE_REFERENCE_ONLY_NOT_DUT**. No current blocking discrepancy was found in the sealed source/ELFs and the one already generated reference. This is not DUT acceptance or launch permission.

## Exact Binding

- Prepared directory: `../fp_compare_unboxed_prefix265_prepare01`.
- READY SHA `ee10a401774a5cb474be69c317edad4ea052c147a42b5fd03aa4cc4b1f5db731`, independently verified before and after the raw audit.
- Program: `fp_compare_unboxed_e16_mf4_prefix265`.
- SoC ELF SHA `03e24bc51c28b705ae3cd373a51c38e04c39ab0eb26443d29ca7d36277741058`.
- Spike ELF SHA `ac415ac17c597a4fb420965679572c36fb9dfd971fb920478d6027c5c7849ee3`.
- Original Linux ELF SHA `404b2c0bb8f9224dc5e281ad1ef83faee238dec1989b26b36d7dbc12e4c3b152`; archived and rebuilt binaries independently match byte identity. All ten helpers and capacity were freshly disassembled and checked against actual archived encodings, not only producer proof text.
- Full sealed baseline/owned/reference-input pins verified before and after. `audit.json` has114 combined source/evidence/auditor pins; `admission.json` adds the exact audit JSON, for115. No original artifact changed.

## Original Scope and Oracle

**265 natural calls /264 predecessors /mf4 cap16**, seed0, op0..3 each56 calls and op4 first41; endpoint op4/VL15/mode0/sticky0/start0. Original17/19-instruction helpers account for4587 retirements; op5..9 remain present but unexecuted. All original eight arguments, capacity/VL returns, caller flags save/restore and ordered helper windows are checked.

Fresh source reconstruction confirms only an after-oracle call265 stop plus the existing Linux write/entry/exit adapter. Full original oracle text and hash remain intact. Original fixture tables independently regenerate all265 source-model rows, including unmasked-mode repetitions, sticky flags, VL0 exact-old preservation and per-bit tail set `{old,1,wanted.bit}`. No fixed-tail-byte or active-only replacement.

Single complete offline strict reconstruction verifies **4240 result bits,530 guard values,265 returned-vstart0,265 returned-flags**, all76850 original setup scalar stores, actual reference vector inputs/results, both packed mask-store bytes and subsequent ordered scalar bit/guard reads. Right guard is output3, not output129. Actual analysis equals stored full analysis structurally, excluding only its separately checked execution/profile/hash fields. No second full raw parse was performed.

## Measured Scalar / Tail Discriminators

The frozen checker was reused unchanged. Its permissive missing-FP-field branch was supplemented for this raw evidence: all **41 real `fmv.d.x`/f2038053 retirements** have explicit actual `f0=0`; no scalar boxing or half-load replacement. First such move is call225/raw line599108, last call265/raw line699561, relocated PC0x800005f6.

Final target op4 is PC0x80000602/opcode62805c57, raw line699564: actual raw ft0=0 (not boxed half zero), active a14=qNaN7e55, tail a15=sNaN7c55. Actual low16 result bits=0000; low15 active bits mustzero and tail bit15 legitimately allows0/1 under the original oracle. Immediate vstart read PC0x80000606/raw line699565 is0; flags read PC0x8000060a/raw line699566 is0/NV0. This validates the reference's unboxed-qNaN and tail exclusion semantics; it does not measure DUT canonicalization or prove an RTL repair.

## Execution / Limits

Actual reference command is pinned: `rv64gcv_zfh_zvfh_zvl1024b`, Spike `-m2`, debugger cap2M steps,120s,256MiB per-output-file RLIMIT. Actual process numeric rc0, elapsed1.2702796938829124s. No memory-RSS bound is inferred from the file-size limit.

Raw SHA `814ccf91567ecefd4d2d63a03ad21cb3ec16268af37be195622a106de3614445`,45935822bytes. Exactly705000 records:5 checked reset-ROM instructions +701895 firmware through normal HTIF exit +3100 original a001 park retirements. No trap, unused helper, extra CSR phase or post-exit side effect. The reference trace's instruction ordinals are **not measured DUT cycles**. Full raw offline audit took27.581s including postchecks; there was one original reference attempt and zero retries. Existing Host2positive/7negative records were inspected/pinned, not rerun.

## Admission and Boundary

- `audit.json`: status `ACCEPTED_SOURCE_REFERENCE_ONLY_NOT_DUT`, key `ready_sha256`, exact `scope` with `calls/predecessors/capacity/result_bits/guards/vstart/flags`; SHA `ae6159a4edb0d0dc2e534f341c40f3467fae2d13b43a7e6ac25895539c934339`.
- `admission.json`: same status/scope, exact source/ELFs/READY/raw/audit identity and115 pins; SHA `764d364333edb66f558e2301012898ae49f19abdfd8f09fb4fe90354fc1472f7`. `launch_authorized=false`; requires separate frozen-image/worker review and parent authorization. This JSON is a source/reference prerequisite, not a command to run DUT.
- `recomputed_reference.json` SHA `f7e5269981503dccd180ca4018f79f950a076c792ed8b1f22563996d998e8969`; `actual_evidence.json` SHA `d3155aa206ca450688ab0496968a43f6ca28acdedc9398d81d9cf072377c695d`.
- Not full17920 parent (17655 calls remain outside scope), not all RVV09/unboxed records, Linux execution/scheduling, cross-process history or proof of a currently failing RTL bug. The byte-identical original Linux rebuild establishes provenance, not Linux execution of this SoC port.

Only this owned review directory was written. No DUT/Host/Spike/reference rerun, compiler/build, producer edit or live-process query. `WAITING_FOR_SEAL.md` is preserved as the historical preseal note; this review/admission supersedes that pending state.
