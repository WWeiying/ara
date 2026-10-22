# Unmasked Strided EEW64 Alignment Boundary

Status: concrete reachable static correctness/liveness finding; NOT a measured
DUT failure. Read-only source review, no test execution, RTL change, live-job
query or full777 polling. Scope is exactly an aligned base with a byte stride
that makes the next element unaligned, not a general misalignment campaign.

## Finding

**P1: vm=1 nonindexed strided requests can exhaust their descriptors after
delivering fewer bytes than VLDU/VSTU must consume.** Initial alignment checks
the raw base only; the later per-element local-fault branch excludes vm=1.
No inspected downstream path repairs the short transfer or raises its precise
element-alignment exception.

Example: `vlse64.v v24,(a0),a1`, vm=1, nf=0, legal e64/m1, VL2, vstart0,
`a0=B=0x80010000`, `a1=4`. Use accessible ordinary RAM, no concurrent vector
instruction, successful AXI responses, and either translation disabled or
valid resident mappings. B is aligned to both EEW8 bytes and the M8 AXI16-byte
bus. This does not rely on unsupported register alignment or an invalid vtype.

1. `hardware/src/ara_dispatcher.sv:4149` copies vm and raw rs1 base;
   `:4190` selects EW64 from memory EEW; `:4227` decodes VLSE and copies
   `acc_req_i.rs2` unchanged into stride. VSSE does the same at `:4495`.
   No stride-shift or stride-multiple-of-EEW rejection covers this instruction.
2. `hardware/src/vlsu/addrgen.sv:319` computes
   `start=base+vstart*stride`, `len=(VL-vstart)<<EEW`; here B and16.
   `:367` uses that effective start. `:382` makes only unit-strided vm1
   operations bursts, so VLSE uses per-element, nonburst requests.
3. `:388` tests `is_addr_error(pe_req_q.scalar_op,EW64)`: raw B passes.
   `:611` makes both predicate-valid and predicate-active true for vm1.
   `:948` requires `!pe_req_q.vm` for the later nonindexed alignment fault,
   so the B+4 element cannot enter that branch.
4. `:1065` emits each AR with len0/size3; `:1099` deducts8 bytes and
   `:1102` adds the raw stride4. Thus the two descriptors are
   `(B,len0,size3)` and `(B+4,len0,size3)`, neither an exception nor skip.
   The second request sets remaining length to0, and `:1245` finishes
   AddrGen; there is no compensating request for B+8..B+11.

## Why the Wider Bus Does Not Rescue It

`hardware/deps/axi/src/axi_pkg.sv:200` computes first-beat lower byte as
`addr % bus_bytes`; `:208` computes upper byte as
`align_down(addr,1<<size)+(1<<size)-1-align_down(addr,bus_bytes)`.

For the M8 128-bit bus and B+4,size3,len0, these are **lower4, upper7**,
not upper11. Even if the returned wide RAM word physically contains bytes
B+8..B+11, the real consumers deliberately exclude them. A legal unaligned
single AXI beat is not an automatic full8-byte cross-boundary element fetch.

VLDU `hardware/src/vlsu/vldu.sv:363` uses those bounds. At `:389` and `:398`
it advances by actual available bytes, not by the requested element width.
`vstart0/VL2` initializes issue and commit bytes to16 (`:718`, `:722`).
The first response accumulates8 bytes and the second4: `vrf_word_byte_cnt=12`.
Both descriptors pop on their len0 beat (`:480`, `:490`). For NrLanes4, the
aggregate VRF word is32 bytes: neither the full-word nor instruction-end test
at `:445` succeeds (12!=32 and12!=16). Result-valid is not published, issue
bytes remain16, commit bytes remain16, and `load_complete_o`/vinsn_done at
`:584` cannot assert. No exception marker/early-illegal input enters its
exception drain. The prediction is an incomplete operation/stall, **not a
claim that VL2 successfully retires with an incorrect 64-bit value**.

For `vsse64.v` with the same geometry, VSTU `:395`, `:412`, `:423` also
consumes8+4 bytes. The second W beat has only byte lanes4..7 strobed, WLAST=1,
and pops the descriptor at `:464`. After two successful B responses, pending-B
may be0, but `vrf_cnt=12`, issue bytes16 and the source operand is not drained:
`:480` never completes the payload, `:506` never advances the issue pointer,
and `:556` cannot complete the sole instruction. Partial memory side effects
are possible before this stall; this is not a measured store result.

The effective-AXI-width store machinery at AddrGen `:847` does not repair this:
the nonburst strided branch still explicitly emits `size=vew,len=0` rather than
using the narrowed burst geometry. No retry/extra beat exists in that branch.

## MMU and vstart Cross-Checks

- AddrGen `:102` hardwires `mmu_misaligned_ex_o=0` because Ara handles alignment.
  `hardware/deps/cva6/core/load_store_unit.sv:453` selects that accelerator
  exception in ACC state, not the scalar LSU's own alignment detector at `:704`.
- `hardware/deps/cva6/core/cva6_mmu/cva6_mmu.sv:52` takes a precomputed
  misalignment exception and a virtual address/store flag, not Ara's EEW.
  Its `:515` / `:518` pass through the supplied exception; permissions/PMP/page
  checks do not implement the missing per-element EEW alignment test.
  Valid same-page mappings therefore do not reject B+4 for this reason.
- With translation enabled, the nonindexed condition at AddrGen `:1174`
  still requests translation normally, and `:1245` / `:527` report final
  translation completion. This differs from the already-measured orphan
  indexed-MMU-request root: the request is not locally rejected and withdrawn.
- With vstart1, effective start is B+4 and length8, while the same initial
  check still examines aligned B. The first/only descriptor is short4.
  This follows from the source formula; it is not an additional measured case.
- Existing masked nonindexed alignment handling does cover the active B+4
  address through `!vm`, an ordered fault descriptor and element index1.
  Merely issuing an unaligned AXI request is not itself this finding: the
  defect is neither providing the complete element nor completing a precise
  exception. Correct full-element support would also refute the hypothesis.

## Minimal Falsification, Not Executed

Use one real AddrGen+VLDU path with its actual descriptor FIFO and legal PE
handshake; a normal bounded AXI responder must return one RLAST beat per len0
request, never force internal counters. Start with translation disabled and
distinct RAM bytes B..B+15. The only control needed is identical VL2/base with
stride8; it should produce16 bytes and complete. The stride4 case must either
complete both correct elements or report the implementation's precise
misalignment at B+4/element1; exhausting two normal descriptors with unfinished
VLDU falsifies the current completion contract. No test is launched here.

Focused signals, sampled around the two actual AR/R handshakes:

- request handshake/id/op/vm/vl/vstart/scalar_op/stride/vsew;
- AddrGen state/AXI state, current addr/len/vew/is_burst, predicate-valid/active,
  descriptor push/pop/full and descriptor addr/len/size/is_exception;
- ARVALID/ARREADY/address/len/size, RVALID/RREADY/RLAST/RRESP;
- `addrgen_ack_o`, exception valid/cause/tval/exception_vstart, early-illegal;
- VLDU issue/commit byte counts, VRF byte pointer/count, AXI byte pointer,
  result-valid/queue count, final grants, load_complete/vinsn_done/global idle.

Distinguishing signature: AR(B,len0,size3), AR(B+4,len0,size3), exactly two
successful R handshakes/descriptor pops, no exception, AddrGen length0, but
VLDU byte count12 against required16 and no completion. An actual extra
descriptor/full8-byte second payload, precise exception, or decoder rejection
would refute the analysis. If translation is enabled, additionally record
MMU req/vaddr/valid/exception and arbiter state to distinguish normal completed
translation from the previous indexed orphan-request failure. No historical
RVV failure family is attributed to this static finding.

## Identity

Read worktree: `/home/wangwy/openproject/ara_dsa_signoff_integration`.
HEAD `7d5d1829ff68baa223618a54807e6a2b4e2c9373` is not a claim of a clean tree.
Current AddrGen/VLDU/VSTU bytes individually match frozen M8 files. M8 static
configuration has NrLanes4/VLEN1024; `hardware/tb/ara_tb.sv:753` gives AXI128.

| Current file | SHA256 |
| --- | --- |
| hardware/src/ara_dispatcher.sv | c179ddd08b2bdb8648246f187aa892be5853fda38aeca850402d5e5b9b17ef7d |
| hardware/src/vlsu/addrgen.sv | 1cc40e2669e310ae25e23f5c9ee1f7ee493dc1ac990d70d8b8122f47e93742b2 |
| hardware/src/vlsu/vldu.sv | 92f9ebbeb136cd3ff11ae1a8ea92ce31b3aac077ae0667f79d82e919a3603401 |
| hardware/src/vlsu/vstu.sv | 37880822b8066fa13e66619dd335cb42db84cdc5730c6f4dff9a3f2fd0af46a0 |
| hardware/deps/axi/src/axi_pkg.sv | 244bd5cb3c5bc58d786f2ed2f5eeefd910c4fe03a175f4a2888c6a2ea1c430dc |
| hardware/deps/cva6/core/load_store_unit.sv | 88ceed6bd3794272145bda9a19c4e6844242a690cc539e36b7dc23a08163d8a8 |
| hardware/deps/cva6/core/cva6_mmu/cva6_mmu.sv | 3e3f19db1ef8d3526c2e5e751c89ce923244a4ae7be617144d523c6c6480d431 |
