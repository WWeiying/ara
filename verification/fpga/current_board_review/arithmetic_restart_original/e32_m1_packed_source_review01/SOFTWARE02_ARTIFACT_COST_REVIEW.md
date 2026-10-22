# Software02 Actual Artifact and Cost Gate

Verdict: **NO_BLOCKER: authorized single Host/compile artifact and <=3M static
positive-path cost gates pass. Reference and DUT remain unauthorized.**
This supersedes the cost HOLD only for the new software02 ELFs; software01 and
its original HOLD evidence are unchanged. No producer script, Host, build,
reference or DUT was rerun by this review.

## Exact Bindings

All paths below are relative to `full_e32_m1_packed_prepare01/`.

| Artifact | SHA256 |
|---|---|
| software02/proof.json | `af3c787838efa61761dd19dd0b443c107abd185894ec0c57d00cf90001d25c7e` |
| software02/pins.json | `31d456377fea09041ea5984f1303e6e8ebc235e5eae8f2e4ea5d7b5ebe90d493` |
| software02/execution_receipt.json | `60018777d95fb0c168c3b5dd1b6eeec32c8ac8c2a0b6c5edef76f135b768b1c8` |
| software02/soc/program.elf | `8b6c67293ad57aff6ddeaf478aa4c94bd07d44421f3c6eb901378fe4cf23db5c` |
| software02/spike/program.elf | `b4fba0b73d4fbd656f54769f7ea8047b3af6fec848de53d685fb209a89651d4f` |
| compiled_audit02/RESULT.json | `0e3da5d2df3de13f8014f89bf1064559f29bd1be4c39b93fbc4160daab40d144` |

## Actual Evidence

- Independently rehashed all280 software pins, unchanged. Persisted Host/compile
  receipt is numeric0, timed_out false,12.396689194720238s. Fourteen new Host
  outcomes and twelve explicitly reused original outcomes match their expected
  numeric statuses and log hashes. New packed logs match all12 old original logs
  byte-for-byte. Both equal-old-value missing-FP-write mutations remain rejected
  with90, not reported as successful unmutated tests.
- New Host code includes dirty128-byte clear at an unaligned address with both
  adjacent guards, and a clear ending at a protected-page boundary. No old Host
  run was repeated. This is Host evidence, not actual architectural execution.
- Independently checked software02 sequence, seed inputs, expected header,
  packed header, original_case.c and operations.h byte-identical to software01.
  Reverse-diff of case.c still yields exactly the previously reviewed case:
  only mask-clear replacement and include. All5985/35ops,1890 FP calls,
  191520 data/11970 guards, original fallback/RNG and table bits remain.
- Reconstructed the actual clear-store addresses directly from linked
  instruction encodings and symbol bases, not just disassembler comments.
  SoC mask=`0x800c9298`, Spike mask=`0x800c9358`; both aligned8. Each has exactly
  sixteen SD zero stores covering offsets0..120. Spike region
  `0x800004b2..0x8000050a` has7 AUIPC plus16 SD; SoC region
  `0x800004aa..0x80000506` has8 AUIPC plus16 SD. No call, byte loop, vector
  instruction or hardware fence occurs there. Original selected-bit loop follows.
- Actual Spike op>24 gate=`0x80000568`, FP loop=`0x800009b2`, SW sites
  `0x800009c8`/`0x800009cc`; the15-instruction loop writes32 pairs each call.
  Its exit returns to normal output setup and the nonfinal start paths return
  through the FP gate. SoC gate=`0x80000564`, loop=`0x800009b6`. No seed-only,
  VL=0, empty-window or equal-value bypass was added:120960 input word stores
  remain required by compiled positive control flow, not dynamically measured yet.
- Both ELF helper windows independently match458 original instructions;
  vector encoding scan outside those windows finds zero extra RVV. Disassembled
  instruction bytes were also checked against loadable ELF addresses. Both
  contain the unchanged complete813960-byte expected ROM and original2560-byte
  FP table uniquely. Actual17 eight-byte output stores/reads retain all136 bytes,
  with two32-bit guards, not a two-byte tail. Original has no fflags oracle.
- Actual304-byte main frame; map gaps212136B SoC/203744B Spike, both exceeding
  the64KiB reserve. Physical source group remains one128-byte register and actual
  architectural mask load four bytes; full128-byte software mask is retained.

## Cost and Admission Boundary

Reviewed the actual new clear, mask selection, per-call gate, FP loop, trial and
outer-loop branches and the recomputed CFG accounting. Positive mandatory core
is **2,355,885**; conservative positive-path upper including loop/control,
BSS and success-tail allowance is **2,550,519**, leaving449481 below3M.

This is not simply old total minus the proposed store-only saving: it includes
23 instructions per Spike mask clear, changed register/control overhead and
actual newly located blocks. Old upper3,320,678 minus new upper2,550,519 yields
**770,159** net accounted reduction. These are static instruction counts, not
measured retirement, VCS duration or proof of architectural reference correctness.
Failure/fallback execution cost is not claimed by the positive-path bound.

There is no remaining source/artifact/cost blocker to the parent's consideration
of the unique finite reference. Reference execution still requires the explicit
parent entry authorization and a checker bound to these actual ELFs/PCs; neither
this report nor the producer's static RESULT grants reference or DUT execution.
No Linux/board closure or new current-image acceptance is claimed.

Independent read-only completion `d3be1f` returned numeric0 in1.586985s for pin,
receipt, reused-file, ELF byte/helper/ROM/table, encoded store address and cost
arithmetic checks. This receipt describes metadata inspection, not a new Host
test, compilation or reference.
