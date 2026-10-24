# Experimental two-tile M4 VRF panel

Not part of the production runtime. No ISA execution or performance acceptance
is implied by the host/object gate. The resident entry is
`qbs_vrf_panel_run(records, stripe_count, out0, out1, stride_elements, n0, n1)`;
the full-K baseline is
`qbs_vrf_panel_direct_run(record, out0, out1, stride_elements, n0, n1)`.
Both use the standard scalar RV64 lp64d calling convention, not the vector
calling-convention variant. Compile the wrapper with vectorization disabled.

## Contract

- Exactly four input rows and two output-column tiles, each N=1..32; 1..256
  stripes for the resident API, exactly one record for DIRECT. Each 24-byte
  record holds two pointers to separate 16-byte aligned
  descriptors, then one four-byte-aligned activation pointer. Descriptor data
  is not inline. The two weight bases must differ. The caller supplies the
  correct local tile/stripe weight layout and a compact M4 activation slab.
- In the resident API, every stripe's first descriptor is FILL. Its second is REUSE except for the
  last stripe, where it is RELEASE. Count=1 therefore uses QBEXEC FILL followed
  by QBEXEC RELEASE. There is no standalone release instruction or extra
  descriptor, and no inter-stripe RELEASE: the next FILL replaces the context.
- The pair must agree on profile, layout, K, context ID zero, and generation.
  Profiles and weight layout stay fixed across stripes; K may vary. Generations
  may vary between pairs and are caller-owned; the driver does not invent or
  increment them. M4 interleaved Q8_K and Q8_0 must satisfy
  `4 * activation_block_bytes * k_blocks <= 4672` and `k_blocks <= 32`
  for the resident API. DIRECT requires both access fields DIRECT, both context
  IDs and generations zero, and matching K=1..256. It has no resident-capacity
  limit; the caller supplies the complete M4 interleaved full-K activation slab.
  DIRECT does not FILL or RELEASE an activation context. Both APIs require the
  same compatible profiles, layouts, two distinct weight bases, and N metadata.
  The packed K field encodes K-1 in eight bits; malformed pre-pack values such
  as K=0/257 cannot be recovered or rejected after a caller has truncated them
  into an otherwise valid encoded descriptor.
- All records and descriptors must be accessible, immutable for the whole
  call, and already backed by valid complete activation/weight storage. The
  wrapper checks metadata, pointer alignment and address overflow, not mapping,
  allocation sizes, packed contents, stripe coverage, or numerical validity.
  It validates the entire sequence before any native capability query/compute.
- The platform must first establish that RVV and QBINFO are legal and enabled
  for this hart. There is no illegal-instruction catcher. The wrapper reads
  VLENB and QBINFO words 0..4, requiring VLENB=128, exact current generated
  words 0..3, and word4=1. This deliberately rejects legacy or different ABI
  hardware instead of attempting a fallback. An old QEMU advertising word4=0
  returns UNSUPPORTED without QBEXEC/QBACC; a platform lacking QBINFO can trap.
- Output rows are contiguous float32 elements at the supplied common stride.
  Stride must be at least both tile widths. All eight active output row spans
  must be disjoint; two column tiles within one larger row-major matrix are
  supported. Outputs must have full writable extents. The caller must keep
  outputs disjoint from code, stack, records, descriptors, weights and
  activations. No concurrent writer may change any input during the call.
- The caller exclusively owns context zero and the hart's QBS execution for
  the entire call; no concurrent or interrupt-driven QBS/context user is safe.
  Interrupt/context-switch handlers must preserve vector state, or execution
  must occur in an environment which prevents such interference.

## Arithmetic and ownership

Both APIs call the identical assembly leaf. DIRECT sets count=1 and issues only
the first two QBEXEC commands, with full K from its descriptors. The resident
first stripe issues QBEXEC into v8-v11 then v16-v19. Each following stripe
issues QBACC into the same groups in the same order. Only integer loop/address
arithmetic runs between commands. No C call, vector spill, FP add, software
partial sum, or change of K order occurs while partial sums are live. Exactly
eight final `vse32.v` instructions write four rows of each tile at runtime N.
The assembly never touches scalar callee-saved registers or the stack. Vector
registers v8-v11/v16-v19 are caller-saved under the standard scalar convention.
VL/VTYPE are clobbered; FP exception flags accrue from QBS. FRM is not modified,
and QBS's fixed-RNE contract is unchanged. No VRF result remains caller-live
after return.

`fence rw,rw` precedes the first compute. After all eight output stores,
`vmv.x.s t2,v19` uses Ara's existing scalar-extract serialization behind all
older vector instructions (`ara_sequencer.sv`, scalar-extract admission gate),
then a final `fence rw,rw` precedes return. This explicitly depends on that Ara
behavior; changing LMUL alone is not a store-drain guarantee. The extract is
integer bit movement, not floating-point arithmetic.

Hardware faults trap; they are not returned as C status. Each QBS command's
atomic commit is not whole-panel atomicity. Earlier stripes and exception
flags/context changes may already have committed when a later command faults.
Compute faults occur before output stores, but a fault during the final stores
can leave partially written output. Resident RELEASE is performed by the last
compute, before these stores; DIRECT has no release lifecycle. Never skip a
trapping QBACC and continue: abort the panel,
re-establish context ownership, and restart from stripe zero after recovery.
This driver supplies no rollback or resumable checkpoint protocol.

## Fixed costs and intended baseline

For S stripes: 2 QBEXEC + 2*(S-1) QBACC, S FILL, S-1 REUSE, one RELEASE, and
32*S bytes of hardware descriptor payload. The leaf reads 24*S record bytes,
holds eight architectural vector registers (1024 physical bytes at VLEN1024),
and writes `16*(n0+n1)` output bytes once. It executes three VSETVLI, eight vector
stores, two fences and one scalar extract. Scalar setup/loop/store-pointer
arithmetic and the wrapper's O(S) validation are additional costs. Every call
also has one VLENB read and, on the supported path, five QBINFO instructions.
No cycle or memory-transaction reduction is claimed without measurements.

For a fair native comparison, time each public API call from entry through
return, with identically placed cycle markers. Both adapters tail-jump to one
compiled `noinline,noclone` preflight/dispatch core, with one assembly call site;
neither calls the other or adds a baseline-only validation layer. Descriptor
and pointer checks, capability queries (including optional word4), fences,
vector setup, final stores and store drain are shared. Only the mode-specific
access/K rules differ. DIRECT validates one record; resident validates S
records. This real O(S) overhead must remain in the measured resident time.
The DIRECT adapter needs scalar argument rearrangement to supply count=1;
neither adapter allocates a stack frame or makes an additional non-tail call.
Keep packing/preparation and independent numerical checking outside both timed
regions, or report them separately and symmetrically. Do not compare a timed
DIRECT wrapper against an unchecked resident leaf, or claim exact identical
software cycles: validation work and API argument setup naturally differ.

Q6_K K8960 is 35 K blocks: eight stripes of four plus a final stripe of three
(nine records, 18 commands). Full M4 Q8_K K4 residency consumes exactly 4672B;
the last K3 stripe consumes 3504B. The caller must explicitly provide these
stripe pointers; this driver neither packs nor slices the full-N weights.
Only two N<=32 tiles are handled per invocation, not an entire projection.
Cross-invocation context reuse, whole-model timing and automatic scheduling
remain outside this baseline.
The corresponding M4/N64 full-K baseline supplies one K35 record with two
N32 DIRECT descriptors: two commands versus the resident sequence's 18.
Both produce the same 256 output elements. The full-K activation slab is
40880 bytes, so this baseline must not be subjected to the 4672B resident
admission check. Whole-panel numerical equality remains a future native gate.

## Build and evidence

```sh
python3 software/qbs/experimental/vrf_panel/build.py \
  --output software/qbs/experimental/vrf_panel/build-gnu-02
```

The builder refuses output reuse; the historical `build-gnu-01` is unchanged.
It uses host GCC for 2130 mock-backed preflight cases: the original 1573 resident
cases plus 557 DIRECT/shared-core cases. These include all stripe counts and all N pairs, malformed final
descriptors, capacity overflow, alignment, output overlap, address overflow and
each capability rejection. DIRECT covers every K=1..256 for Q6_K/Q8_0,
including K35 and K256, incorrect access/context metadata and address arithmetic;
the resident API still rejects K35/K256 and capacity-overflow shapes.
These checks do not execute or numerically emulate
the panel. The default GNU cross compiler is
`/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc`.
It compiles RV64GCV/lp64d wrapper and assembly objects, links a relocatable
`vrf_panel.o`, and inspects encodings, stores, drain, and absence of calls or
callee-saved register use in the leaf, plus the single shared compiled C core
and its two stackless tail-jump adapters. It does not build a SoC ELF or launch
QEMU, Spike, VCS, Verilator, synthesis, or ZCC. Logs include exact commands,
disassembly and pre/post source hashes. Keep build output as evidence, not
source to be committed.
