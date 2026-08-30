# Attention/KV Streaming Context Contract

## 1. Scope

This document freezes architecture contract version 1 of the Attention/KV
streaming context (AKV). It is the design boundary between the measured
Decode-Attention bottleneck and the RTL implementation. The generated C and
SystemVerilog definitions come from `config/akv_abi.json`; this document
defines their behavior.

AKV is a bounded residency and replay mechanism, not a second vector compute
array. It has four responsibilities:

1. fetch one GQA group's F16 query vectors and one eight-token K/V tile through
   the existing MMU and AXI path;
2. retain those vectors in a non-architectural 6 KiB context;
3. replay a selected Q, K, or V vector through the existing load-result and VRF
   completion path; and
4. expose enough shape information for software to keep online-Softmax state
   and output accumulators in the VRF while ordinary RVV instructions perform
   all arithmetic.

AKV does not define a new dot-product, reduction, exponential, or FMA unit. It
does not change normal RVV register semantics, QBS semantics, the MMU, AXI, VRF
hazard tracking, or floating-point exception rules. When AKV is disabled or a
shape is unsupported, software uses the standard RVV implementation.

## 2. Why this boundary follows from the baseline

For the captured Qwen2.5-1.5B Decode Attention shape, `D=128`, there are 12
query heads and two KV heads. Six query heads therefore reuse each K/V stream.
The generic RVV loop executes one D-wide dot product at a time. At effective KV
lengths 16, 128, and 256, it exhibits all of the following invariants:

- one Q-vector reload per dot product;
- six external reads of each K and V vector because the GQA query heads are
  processed serially;
- one F16 output-accumulator load/store pair per dot product, plus a second pair
  when the running maximum changes;
- one FP reduction and one vector-to-scalar return per dot product; and
- only 6.7% to 8.4% strict compute-unit active cycles in the online phase.

Keeping Q, K/V, and online output state local reduces the targeted logical
traffic lower bound by 12.6x to 14.8x. The custom mechanism therefore targets
data lifetime and reuse. A dedicated arithmetic array would attack the wrong
first-order cause and duplicate the existing lane/MFPU datapath.

The local SpacemiT llama.cpp source also contains a stronger software baseline:
it packs K tiles in a TCM buffer, computes several query rows together, and
vectorizes scores across KV positions. AKV must ultimately be compared with an
equivalent portable tiled-RVV implementation, not only with the generic
one-dot-at-a-time loop. AKV's distinct role is to provide bounded on-path
residency and replay without external TCM packing traffic, while retaining the
standard RVV arithmetic path.

## 3. Execution model

Software operates on one KV head and its associated query-head group at a time.
The descriptor gives the first Q row, K stream, V stream, shape, and byte
strides. A full fill reads the descriptor, all Q rows, and the first K/V tile.
A refill preserves the descriptor and Q rows and replaces only the K/V tile.

The intended software schedule is:

```text
convert one GQA group's Q rows from F32 to F16
initialize one F16 output vector per Q row in VRF
initialize packed vector-domain M and S state for all Q rows

akvfill.full(descriptor, tile_start = 0)
for each KV tile:
    for each valid token in the tile:
        akvload K[token] once
        for each Q row in the GQA group:
            akvload Q[row]
            score = reduce(FP32(K * Q))
        akvload V[token] once
        update packed M/S and all output rows with RVV operations
    if another tile exists:
        akvfill.refill(tile_start += 8)

normalize and store output vectors
akvrelease
```

Each K/V vector is fetched from architectural memory only once per tile and is
loaded into the VRF once per token before it is shared by the GQA query rows. Q
is fetched once per full context and replayed locally for each dot product.
Output accumulators remain in vector registers across all tiles. Running maxima,
sums, and dot results are packed in vector registers, one element per query row,
so no score is returned to scalar control between dot products. The current
four-lane implementation extracts two per-row update factors into FP scalar
operands for `vfmul.vf` and `vfmacc.vf`; those values do not drive control flow
or return to memory. This avoids the much more expensive full-group `vrgather`
path while preserving ordinary RVV arithmetic semantics.

The v1 storage is row-major because the first implementation preserves the
current D-axis dot-product mapping. A future token-axis mode may add an on-fill
K transpose, but it requires a separate architecture version and must be
justified against the tiled-RVV baseline. It is not implicit in v1.

## 4. Bounded state and register feasibility

The maximum resident payload is:

```text
8 Q rows * 128 F16 elements = 2,048 B
8 K rows * 128 F16 elements = 2,048 B
8 V rows * 128 F16 elements = 2,048 B
                                  -------
                                    6,144 B
```

For the measured Qwen shape only six Q rows are used, so 512 B of the Q region
is inactive. Supporting eight rows costs little and covers common GQA group
sizes without hard-coding the mechanism to one model.

At `VLEN=1024`, one D=128 F16 vector occupies an LMUL=2 register group. A
Qwen group can retain six output vectors in 12 registers. Packed M/S and score
registers, one replayed Q row, K, V, one LMUL=2 FP32 dot accumulator, and the
temporary groups fit within 32 architectural vector registers when software
uses a fixed register plan. This is why v1 chooses an eight-token hidden
context and sequential Q replay instead of trying to retain every Q, K, V,
score, and output vector simultaneously.

The RTL may implement the 6 KiB payload as a banked register array or SRAM, but
the storage choice is not architectural. A 256-bit internal row corresponds to
192 rows at the maximum shape. Fill and replay do not require simultaneous
writes to the same context in v1, so a single logical write/read ownership
model is sufficient. Banking may still be used to meet 1 GHz timing.

## 5. Instruction encoding

All instructions use the standard 32-bit R-type layout under `custom-2`
opcode `0x5b`. QBS owns `funct3=0` and `funct3=1`; AKV uses the disjoint range
2 through 5.

| Mnemonic | `funct3` | `rd` meaning | `rs1` meaning | `rs2` meaning | `funct7` |
|---|---:|---|---|---|---|
| `akvfill` | 2 | must be `x0` | descriptor address for full fill; `x0` for refill | tile start index | bit 0 is fill mode; bits 6:1 zero |
| `akvload.v` | 3 | vector destination | selector value | must be `x0` | bit 0 is D code; bits 6:1 zero |
| `akvinfo` | 4 | scalar destination | query index | must be `x0` | zero |
| `akvrelease` | 5 | must be `x0` | must be `x0` | must be `x0` | zero |

The D code is zero for D=64 and one for D=128. It is encoded in the
instruction rather than read only from hidden context because the dispatcher
must reserve the destination register group before the command executes.
D=64 writes one aligned LMUL=1 group; D=128 writes an even-aligned LMUL=2
group. The instruction is illegal if the encoded D disagrees with the active
context.

### 5.1 `akvfill`

`AKV_FILL_FULL=0` requires a 64-byte-aligned descriptor address in `rs1` and a
tile start in `rs2`. It reads and validates the descriptor, then reads all Q
rows and `min(8, kv_length - tile_start)` K and V rows. `tile_start` must be
less than `kv_length`.

`AKV_FILL_REFILL=1` requires `rs1=x0` and a ready context. It reuses the retained
descriptor and Q payload, and reads only the K/V rows beginning at `rs2`.
Refill cannot change the shape, bases, or strides. A different GQA group starts
with another full fill.

Both modes are blocking accelerator loads. They complete only after every
required read is checked and the new context state is committed, or after a
terminal exception is ready for the scalar core.

### 5.2 `akvload.v`

The scalar selector in `rs1` is:

```text
bits 1:0  stream: Q=0, K=1, V=2; 3 is reserved
bits 4:2  row/token index, 0 through 7
bits 63:5 reserved and must be zero
```

For Q, the index must be below `q_rows`. For K/V, it must be below the valid
token count of the current tile. A valid operation writes exactly `head_dim`
F16 elements to `vd`. It is a vector destination, not a scalar `rd`; CVA6
first-pass decode must therefore record only the scalar selector dependency.

The load is allocated a normal vector instruction ID. Its result uses the LDU
lane-result address/data/byte-enable handshake, so existing VRF destination
hazards and completion gating apply. The local context introduces no memory
fault after validation; the implementation must validate the selector and
context before issuing the first VRF write.

Unlike fill and release, a local load need not drain unrelated MFPU work. It
may overlap with arithmetic, subject to explicit arbitration with normal VLDu
results. The architectural contract does not promise a fixed latency.

### 5.3 `akvinfo`

Query zero returns:

```text
bits  7:0   architecture version
bits 15:8   descriptor version
bits 23:16  descriptor bytes
bits 31:24  maximum Q rows
bits 39:32  tile tokens
bits 47:40  context count
bit  48     implementation enabled
bit  49     F16 payload supported
bit  50     D=64 supported
bit  51     D=128 supported
bits 63:52  zero
```

Query one returns the opcode, four `funct3` values, and descriptor alignment.
Other query indices return zero. `akvinfo` has no hidden-state side effects and
does not enter the vector sequencer.

Executing `akvinfo` on a processor that does not decode AKV still raises an
illegal-instruction exception. A production runtime must discover AKV through
an OS hardware-probe, device tree, platform contract, or a one-time trap-safe
probe before calling it. It must not execute `akvinfo` speculatively on an
unknown target.

### 5.4 `akvrelease`

Release waits until older AKV loads and vector work cannot reference the
context, then invalidates all descriptor, Q, K, and V state. Releasing an empty
context succeeds. All reserved instruction fields must be zero.

## 6. Descriptor v1

The descriptor is a naturally little-endian, 64-byte object aligned to 64
bytes. Its exact C layout is generated as `akv_descriptor_t`.

| Offset | Bytes | Field | Contract |
|---:|---:|---|---|
| 0 | 1 | `version` | must equal 1 |
| 1 | 1 | `element_format` | F16=1 |
| 2 | 1 | `q_rows` | 1 through 8 |
| 3 | 1 | `flags` | zero in v1 |
| 4 | 2 | `head_dim` | 64 or 128 |
| 6 | 2 | `kv_length` | nonzero total active KV rows |
| 8 | 4 | `q_row_stride_bytes` | even and at least `2*head_dim` |
| 12 | 4 | `k_token_stride_bytes` | even and at least `2*head_dim` |
| 16 | 4 | `v_token_stride_bytes` | even and at least `2*head_dim` |
| 20 | 4 | `reserved0` | zero |
| 24 | 8 | `q_base` | first F16 Q row |
| 32 | 8 | `k_base` | first F16 K token for this KV head |
| 40 | 8 | `v_base` | first F16 V token for this KV head |
| 48 | 8 | `reserved1` | zero |
| 56 | 8 | `reserved2` | zero |

All three base addresses must be F16-aligned. The last byte of every described
row range must be representable without 64-bit wraparound. Strides allow the
descriptor to reference native llama.cpp tensor views without requiring a
specific head stride; software passes bases already offset to one GQA group.

Mask, ALiBi/slope, softcap, sink, and scale data are deliberately not embedded
in the context. They remain software-visible operands to ordinary RVV
operations. This keeps AKV a reusable data-lifetime mechanism and avoids
hard-coding one model's Softmax policy. A runtime may still use AKV with an
arbitrary bias stream, although sparse masked tiles may reduce its benefit.

## 7. Context state and atomicity

The abstract state machine is:

```text
EMPTY --full accepted--> FILLING --all reads succeed--> READY
  ^                            |                         |
  |                            +--fault-----------------+
  |                                                      |
  +--release---------------- READY --refill--> REFILLING-+
                                      |          |
                                      +--fault---+--> EMPTY
```

At reset the context is empty. Full fill invalidates any old context at
acceptance. Refill makes the current tile unavailable while preserving Q only
as implementation-private temporary state; software cannot issue a load until
the refill commits. Any descriptor, translation, PMA, AXI, protocol, or payload
fault invalidates the complete context. Retrying after a fault therefore uses
a full fill, which avoids ambiguous mixtures of old Q and new K/V state.

Payload writes during fill are speculative hidden-state writes. The ready bit
is asserted only after all required bytes arrive and every range completes.
No architectural vector register is changed by a failed fill. A local load
checks context validity, D code, selector reserved bits, stream, and index
before its first lane-result request. It either writes the complete vector or
raises illegal instruction without a partial destination.

## 8. Memory ordering, protection, and faults

Full fill and refill use the existing VLSU translation and AXI read path. They
must acquire VLSU ownership only after older Ara memory activity and registered
responses drain. They also wait for older scalar stores using the same
store-pending rule as the current QBS read engine. Descriptor and payload
addresses undergo normal virtual translation, page-boundary splitting, PMA
checks, and AXI response checking.

Version 1 permits only cacheable, idempotent source ranges. MMIO and other
non-idempotent regions fail with load access fault. A translation exception
retains the MMU-provided cause and reports the detected faulting virtual address
in `tval`; PMA, AXI response, and protocol failures report load access fault.
Descriptor legality and hidden-context misuse report illegal instruction with
no destination write. As with the existing QBS back-end validation path,
software must accept either zero or the faulting instruction bits in `tval`;
the architectural contract does not require a nonzero illegal-instruction
`tval`.

The command has snapshot semantics. Successful completion means the hidden
context contains the bytes returned by its reads. Later stores to Q/K/V memory
do not update the context. Software that produces those buffers immediately
before fill must use the same platform coherence and fence discipline required
by ordinary Ara vector loads. AKV does not add coherence between CVA6 private
caches and the vector AXI master.

The scalar instruction remains unretired until a fill/release command completes
or faults, preserving precise scalar exceptions. AKV v1 is intended for the
current bare-metal execution environment. In a multi-process environment the
OS must release or invalidate the hidden context on protection-domain changes;
v1 does not define architectural save/restore state.

## 9. Numerical contract

AKV moves F16 payload bits and performs no floating-point arithmetic. Fill and
load therefore do not set `fflags`, do not depend on dynamic `frm`, and do not
canonicalize NaNs or flush subnormals. The values delivered by `akvload.v` must
be bit-identical to the selected bytes captured by the successful fill.

All dot products, reductions, comparisons, exp approximations, online-Softmax
updates, and output normalization remain ordinary RVV operations. Their
rounding, exception flags, NaN behavior, and element ordering are governed by
the existing RVV implementation and the software kernel. The optimized kernel
may legally differ from the generic one-dot loop because it removes scalar
materialization and may batch updates, so validation compares both paths with
the same real llama.cpp golden tensor and explicitly records maximum absolute
and relative errors. No looser tolerance may be hidden inside the AKV command.

A dedicated reduction or exponential pipeline is outside contract v1. It may
be proposed only after the post-residency RTL profile shows that existing MFPU
reduction/exp activity has become the critical limiter.

## 10. Coexistence and fallback

AKV and QBS share only the custom opcode and existing system interfaces. Their
`funct3` spaces are disjoint. Fill/refill obtain exclusive read-channel
ownership in the same manner as QBS; arbitration must ensure that at most one
special engine owns MMU/AXI or LDU result routing. `akvload.v` uses explicit
result arbitration and cannot consume a normal VLDu grant unless selected.

When `ARA_AKV_ENABLE` is absent, all four encodings are illegal and no AKV state is
clocked. Normal RVV and QBS behavior must be bit- and cycle-equivalent apart
from physically unavoidable decode fanout, which is checked in synthesis.

The llama.cpp/GGML dispatch policy is:

1. discover the architecture and descriptor versions through a platform-safe
   capability path;
2. require F16 Q/K/V, D=64 or 128, one to eight Q rows for a KV head, legal
   strides, and a kernel implementation with a verified register plan;
3. use AKV full fill/refill/load/release for supported shapes; and
4. use the standard RVV kernel for every unsupported type, shape, mask policy,
   capability, or command failure recoverable at software level.

For performance attribution, evaluation retains two RVV comparisons: the
existing generic path and a multi-row tiled path using software scratch. The
first measures end-to-end improvement over upstream behavior; the second
separates AKV's on-path residency benefit from a known software dataflow
transformation.

## 11. Implementation obligations

The RTL milestone is not complete until it proves all of the following:

- C and SystemVerilog ABI files regenerate identically from the JSON source;
- descriptor and instruction reserved bits fail before any payload or VRF
  side effect;
- address arithmetic checks overflow before issuing a read;
- fill is all-or-nothing with respect to context validity;
- local loads cannot observe a partial refill;
- D=128 destination alignment and register-span checks occur before issue;
- every accepted local load produces exactly the expected LDU result words and
  one sequencer completion;
- normal VLSU, QBS, and AKV ownership/grant paths are mutually exclusive;
- reset, release, and every terminal fault invalidate the required state;
- no AKV arithmetic path or hidden `fflags` update exists;
- disabled-AKV representative RVV and QBS regressions remain unchanged; and
- bounded assertions cover command acceptance, byte counts, range completion,
  context commit, result-word count, and terminal success/fault exclusivity.

The first functional test uses D=128, six Q rows, and tile lengths 8 and 5 to
exercise a full tile and tail. Fault tests cover descriptor alignment/version,
reserved fields, unsupported D, invalid selectors, destination alignment,
address overflow, page faults in descriptor/Q/K/V, PMA rejection, AXI error,
refill after release, and release during queued older vector work.

## 12. Generated contract files

The source of truth and generated consumers are:

```text
config/akv_abi.json
scripts/gen_akv_abi.py
apps/common/akv_abi.h
software/akv/include/akv/akv_abi.h
hardware/include/akv_pkg.sv
verification/akv/akv_contract_test.c
```

Run the architecture-only checks with:

```bash
verification/akv/run_contract_test.sh
```

Changing an encoding, descriptor field, capability bit, supported dimension,
or context limit requires changing the JSON source, regenerating both language
views, updating this contract, and extending the test vectors in the same
commit.
