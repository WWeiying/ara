# AddrGen Successor Local Validation

## Accepted Evidence

`after03`: **32/32 local PASS**, real AddrGen with modeled descriptor consumer,
mask windows, index operands, parent VID lifetime and three-cycle MMU response.
No RTL assertion errors. This is NOT real VLDU/VSTU, Sv39, ELF execution or
original Linux scenario acceptance. Production RTL was edited only by parent.

| Identity | SHA256 |
| --- | --- |
| Candidate AddrGen | 470c6c92d26cd2e540562302788f58d8d85ae6f147886fb949668e7728be41da |
| Baseline AddrGen | a339e5fe0c96728e4e97e21139b03649121a6c37ba765a4ee62f261c7e14f988 |
| Same TB, after03/before01 | 56bd5046f8102fae32bc20120253554a58911e37a0d9387e0edd6b03bdb2de7a |

`before01` uses `../measurement04/frozen`, not git HEAD. Its source manifest
differs from after03 ONLY in AddrGen. It runs controls21..25 before case0.
The five controls finish without assertion errors; every CONFIG/MMU/AXI/DESC/
ACK/LOCAL_PASS line, including cycles, is identical to after03. Original RTL
case0 fails at its first unexpected MMU request to 0x40001000: expected count0.
That is retained as a genuine local baseline FAIL, not relabeled expected PASS.

The frozen batch runner conservatively marked every before01 case FAIL because
the later case0 fatal applied to its whole-log filter. The raw five LOCAL_PASS
records and complete matching event logs establish the control outcomes.
No before01 status or log was rewritten. Current runner now parses each CONFIG
section independently and distinguishes NOT_RUN; this reporting-only correction
was checked against existing logs, without another RTL execution. Frozen runner
snapshots preserve the exact programs used for each historical run.

## Fixture Corrections, Not RTL Repairs

All old artifacts remain unchanged.

- **after01 is invalid evidence in full.** The modeled consumer kept ready high
  without a descriptor. AddrGen directly ORs consumer-ready into FIFO pop
  (`addrgen.sv:153`), so FIFO empty-read assertions fired. The local pass-marker
  parser also initially failed to reject nonfatal RTL assertion errors. Fixed
  consumer port to `descriptor_valid && sink_ready`, and rejected all assertion
  errors. Neither expected address nor predicate/exception oracle changed.
- **after02 partial input-layout error.** Four simple controls passed, but
  cases3/20/23 failed. The fixture's mask/index byte packing incorrectly used
  linear lane-local subelements. Existing Ara layout bit-reverses the lane-local
  subelement ordinal for e8/e16. For four lanes the independent mapping is:
  lane=(byte/E)%4; slot=bitreverse(byte/(4*E),log2(8/E)); offset=slot*E+byte%E.
  Formula checked statically against existing `ara_pkg.sv:534` tables at all128
  e8/e16/e32/e64 byte positions. The TB does not call RTL shuffle_index for this
  packing or derive expected results from DUT output.
- For case3/20, old input packing caused a request for element21 at 0x4000102a
  while the unchanged sparse oracle required element22 at 0x4000102c. For
  case23 element4 was skipped instead of active. Only input packing changed;
  active(i)=i%3==1, expected addresses, descriptors, cause/tval/vstart, FOF and
  counts were retained. after03 passes all three. after03 also batches independent
  reset-isolated cases in one simulator invocation to avoid repeated startups.

## Measured Matrix

VM here means address translation enable, distinct from instruction vm=1.
All cases except21/22 are masked (instruction vm=0).

| Cases | Coverage | Observed outcome |
| --- | --- | --- |
| 0,4 | All-off e16/VL8, translation on/off | 8 skips, zero translations/AXI, ack cycle11 |
| 1 | First active element faults | One translation, zero AXI, cause13/vstart0 |
| 2,3 | Sparse multiwindow, vstart0/15, VL35 | 35/20 descriptors, 12/7 active accesses |
| 5 | Sparse, translation disabled | 8 descriptors, 3 AXI, zero MMU |
| 6,7,8 | Store sparse/all-off/later active fault | 3/0/0 AW; later fault cause15/vstart3 |
| 9,10,11 | Positive/negative/zero stride | Correct three active addresses each |
| 12,13 | Odd base, all-off, translation on/off | 8 full-element skips, no access or exception |
| 14,15 | Odd base after three skips, VM on/off | Fourth descriptor exception, cause4/vstart3, no MMU |
| 16,17,18 | FOF first fault/later fault/all-off | FOF=0/1/0, later fault remains internally terminal |
| 19 | All-active VL49, FIFO/AXI backpressure | 49 descriptors/AR/translations, one ack |
| 20 | Sparse vstart17/VL50, delayed valid/wrong owner each window | 33 descriptors, 11 AR/translations, one ack |
| 21,22 | Instruction vm=1 unit burst, translation on/off | One descriptor and AR, size5/len0, ack7/4 |
| 23,24,25 | Indexed sparse/all-off/vstart3 controls | 8/8/5 descriptors; 3/0/2 AR |
| 26,27,28 | e8/e32/e64 word-interior start/window boundaries | 34/18/10 descriptors, exact element addresses |
| 29 | Store negative stride, vstart3/VL19 | 16 descriptors, 5 AW/translations |
| 30,31 | Store local misalignment / load FOF local misalignment | Cause6/4, vstart3; ordered marker, no early-illegal |

All cases check exact descriptor order/type/size/len, active physical address,
active descriptor VA/element metadata, skip synthetic addr0, MMU address and
response binding, exception cause/tval/vstart, FOF, exactly one ack and bounded
modeled retirement. A missing/extra transaction fails; timeout is not PASS.
Mask windows advance only after accepted consumer descriptors account for the
whole current word (or final partial word), never by looking at DUT progress.

## Scope and Remaining Obligations

The all-off/active-fault cases reconstruct the semantic core of measurement04's
historical e16 scenario3 but do not replay its original software or data oracle.
Original provenance stays in measurement04/linux_provenance.json and existing
review files. Other cases are explicitly new directed derivatives.

The MMU is a deterministic model, not a page walker or TLB. AXI readiness can
stall before translation and descriptor backpressure is independent; once a
translation is outstanding the model keeps AXI ready until its response. This
does not cover a one-cycle MMU response colliding with a newly withdrawn AXI
ready. No actual R/W/B or VRF data is modeled, and no genuine consumer completion
is claimed. Pure skips still need real consumer validation. Segments, actual
FOF VL update, trap/retry, late B errors, final VRF grants, adjacent instructions
without reset and full Linux signals remain owner/system-level obligations.

Consumer structural findings are in `../CONSUMER_REVIEW.md`, particularly
VLDU exception final-grant/accounting cleanup. AddrGen 32PASS does not resolve
those issues. All-active masked unit loads intentionally use one access per
element (case19:49), not the old unmasked burst; no performance-neutral claim.

Run into a new owned output directory:

```sh
python3 -B verification/fpga/current_board_review/masked_translation/successor/run.py --out verification/fpga/current_board_review/masked_translation/successor/NEW_RUN
```

Use `--cases 0,1,3,14,20,21,23` for the small discriminator set and `--rtl-root`
for a pinned source tree. Never overwrite a prior run directory. No baseline
runner, measurement04 artifact or Sv39 agent file was changed.
