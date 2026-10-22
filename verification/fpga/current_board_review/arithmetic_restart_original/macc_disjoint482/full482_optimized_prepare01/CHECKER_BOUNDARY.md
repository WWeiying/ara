# Full482 Future DUT Checker Boundary

Preparation/reference only. No DUT worker, campaign acceptance or M8 identity is established here. The old full482 reference, accepted single481/pair480-481, and all failed preparation records remain separate and unchanged.

## Numerical Scope

Exactly482 ordered original calls0..481, with481 predecessors: seed0/op0, VL0/1/2/3/256/511 all80 combinations each, then VL512/all-on/accumulator0 starts1 and256. Require actual vlenb128/cap512,6266 helper instructions (each original13 exactly482),246784 result bytes,964 guards,482 low returned-vstart and482 high-word zero/status checks. The high word is the original zero-container check, not an independently sampled fflags/vxrm/vxsat claim.

Scalar optimization retains the original RNG interval byte-for-byte and executes/checks it before first-call fresh copies. All five accumulator patterns, physical128-byte masks and every output byte/guard remain. It additionally rewrites identical a/b and mask values per call for auditable freshness; this is an explicit scalar-scheduling difference, not original Linux timing/ELF equivalence or exact historical microstate replay.

## Real Memory Contract

- Decode the actual frozen RV64/C memory instruction, including C.LD/C.SD and stack variants. Unknown code or unknown required GPR is fail-closed. Do not replace actual memory evidence with a presumed shadow-register address/data.
- Every scalar setup write must have the correct RVFI `mem_addr`, `mem_wmask`, `mem_wdata` under the frozen TB/CVA6 data-lane convention. Check actual read masks and prohibit contradictory read/write enables. A source-register reconstruction can cross-check reported data, not substitute for it. Byte-store unused high bits must not become a nonarchitectural oracle.
- At each helper entry require fresh complete writes to a512, b512, mask128 and out514 bytes since the preceding call. Enforce the actual per-call208 aligned64-bit stores plus the two final output bytes (or a correctly decoded equivalent16-bit final store); repeated identical values do not excuse missing initialization. Do not count vector stores, startup BSS clearing or prior-call values as fresh scalar setup.
- Preserve physical a/b1024/out1026 storage. Target output is still `out+1` with original relative byte offset. Physical predicate128 is distinct from its64-byte logical window; upper64 setup bytes are checked as zero.
- The positive path performs65 actual aligned64-bit output reads, covering out0..519. Require actual RVFI addresses/read-mask255/write-mask0 and exact returned data for all512 results and two guards. The final read's high six bytes out514..519 are outside the original oracle and **must not be compared**. Host explicitly verifies that corruption there remains permitted in both implementations. Fallback error reporting must not replace or truncate the complete positive oracle.
- Require original helper arguments, operation opcode `b5042c57`, original13 instruction order, VL/start/rm values, actual vstart CSR return0, source summary counts, unique runtime markers, numeric monitor exit0, no timeout/abort/retry, and original CTRL0/park. Actual monitor result must be durable before any generic/postcheck exception.

## Frozen State And Protocol

Bind the actual M8 image/config/snapshot and an independently justified **M8 reset-known GPR profile**. Reset-zero knowledge must come from the frozen enabled FF register-file implementation and configuration, not an ISA default or an inferred uninitialized value. Maintain x0 and each actual retired write; fail if an instruction requires a register without justified initial or retired provenance.

Compose the strict source/memory observer with real CVX request/response, arch-start and uop allocation/completion ownership checks. `validate_trace` has no `status` field: returning without exception means its generic checks passed, but does not prove that every expected event family exists. The campaign must additionally require actual nonzero counts for each of `cvx_req`, `cvx_resp`, `arch_start`, `uop_alloc`, `uop_done`, and bind target/owner/order ledgers to the retired original helper. Missing an entire event family must reject; no fabricated generic status or fallback attestation.

Before a formal run, bind the actual full482 reference readiness, Host byte-equivalence/mutations, original source/ELF identity chain, compiled helper proof, source diff, exact new ELF, memory/stack proof and producer pins. No accepted single/pair substitutes for this482-call execution. Case rc0 and architectural evidence are distinct from an outer service exit; GC is not positive exit0 evidence.
