# NaN single reference: CSR write-log contract

Status: **STOPPED; reference not accepted; no DUT admission.** Successor
observer review is pending Zeno's notification. Original reference is preserved;
this review did not run Spike, Host tests, a compiler, DUT, or an observer, and
did not read any raw reference or CSV. Only source and small metadata were read.

## Concrete checker mismatch

Producer directory: `../nan_minmax_soc_prepare01/`.

- `check_reference.py:78-81` requires an explicit `fflags` field at helper
  index 11. For a no-exception instruction, absence gives `None`, so the
  correct result with no flag-write event fails. The second identical
  assumption at `check_reference.py:274` must also be addressed in a successor.
- `test_raw.py:36-40` requires a preexisting CSR field before corrupting it.
  Its index-11 `raw_result_flags` negative therefore cannot mutate the actual
  no-fflags-event case. A successor negative must insert an explicit NV event
  when absent, not silently skip this negative or count failure before mutation.
- `STOPPED.json` reports `raw bitwise result/flags/vstart`, no completed cases,
  and call1234 not dispatched. `call1294/reference01/actual_exit_unvalidated.json`
  records numeric returncode 0, timed_out false, elapsed 2.974907114636153 s,
  validated false. These are process facts, not a full oracle PASS.

Parent reports the one inspected target commit has v24 canonical `7fc00000`
plus unchanged `5b` tail, vstart 0, and no fflags field. This report does not
claim an independent raw observation of that row.

## Source contract

Spike root: `/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart`.

1. `riscv/execute.cc:10-15` clears the commit write maps per instruction;
   `execute.cc:119-135` prints recorded CSR writes, not a CSR-state snapshot.
2. `riscv/decode_macros.h:214-219`: `raise_fp_exceptions(flags)` calls
   `fflags->write(read() | flags)` only if flags is nonzero. Zero exceptions
   therefore produce no fflags event. `set_fp_exceptions` then clears the
   SoftFloat accumulator.
3. `riscv/csrs.cc:53-67` logs successful CSR writes.
   `masked_csr_t::unlogged_write` at :965 and `float_csr_t::unlogged_write`
   at :1436 do not suppress writes merely because the value is unchanged.
   Thus explicit `csrw fflags,0` has evidence even when already zero.
4. `riscv/insns/vfredmax_vs.h:1-12` uses the FP reduction macro and
   `is_propagate=false`; `riscv/v_ext_macros.h:1630-1655` invokes
   `set_fp_exceptions` for active elements. Reduction end at :1509-1555
   explicitly writes vstart 0. With all elements masked off, it retains the
   seed; it does not invoke the active max operation.
5. `softfloat/fall_maxmin.c:46-60` canonicalizes two NaNs. The selected
   inputs are quiet NaNs: call1294 has only element 2 active at VL3 with mask
   0x24 and expects `7fc00000`, flags 0; call1234 is all off and expects seed
   payload `7fc12345`, flags 0. This is not a signaling-NaN NV test.

More precisely, this is a **write-event log**, not a universal value-delta
log: even a repeated nonzero sticky exception may emit the same CSR value.
Absence means no logged write for that instruction, never implicitly zero.
The source contract and pinned executable identity were checked separately;
this review does not newly establish a reproducible source-to-Spike build.

## Minimum successor obligations

The original op_2 assembly at `call1294/prepared/operations.S:55-75` fixes the
21-instruction sequence. Index 10 is explicit `csrw fflags,a7`; index 11 is
the reduction; index 12 reads vstart; index 13 reads fflags; indices 16/17
restore frm/fflags. Required checks:

- Begin tracked flags as unknown. Establish zero only from the actual index-10
  CSR write and zero source operand, with exact PC/code and contiguous helper
  order. Missing/malformed clear evidence must fail, not seed a default zero.
- Preserve the original per-row CSR dictionary. If index 11 omits fflags,
  carry only a previously proven state. If it includes fflags, validate the
  recorded value. Reject nonzero flags, unexpected writes between clear and
  readback, and unexpected fcsr aliases rather than ignoring them.
- Require exact index-13 readback x6=0 and index-12 vstart readback x10=0;
  retain the explicit index-11 vstart=0 check. The intervening exact instruction
  window must not permit a clear to hide an exception before readback.
- Keep the original 128-byte vector result, all 144 output-byte oracle reads,
  setup/mask/seed/fixture history, unused-helper exclusion, original flags
  and restore checks, normal exit, bounds, and source/ELF pins unchanged.
- Focused negatives: missing/wrong clear; absent target event without known
  predecessor state; inserted NV despite later zero readback; nonzero actual
  readback despite absent target event; unexpected intervening fflags/fcsr
  event; missing/reordered helper row. Mutations must reach their intended
  check and not pass by failing at an unrelated earlier assertion.

A local state-chain check over the exact helper is sufficient; no need to
invent full architectural CSR state. Merely changing `.get('fflags')` to
`.get('fflags', 0)` is not acceptable. No new reference or successor execution
is authorized by this report. Existing 3M / 256 MiB / 120 s bounds are unchanged.

## Scope still pending

No successor observer was available at inspection. No READY acceptance is
asserted. Full source-fidelity/21-helper/144-byte reference acceptance for both
singles still requires the producer's completed successor and sealed evidence;
numeric Spike rc0 alone does not satisfy that acceptance.

## SHA256 evidence snapshot

All paths below are relative to the roots named above. Raw hashes in execution
metadata were not independently recomputed because raw reads were prohibited.

| File | SHA256 |
| --- | --- |
| Producer check_reference.py | 72d276601b3e3d8723ebb0abaf677096e50b09c077f56ec8478d137d86b9539b |
| Producer test_raw.py | c023a31c632fb5b665deab39cf58fb95af4eaf52dfb520fea9a70184487444b2 |
| Producer STOPPED.json | c649139a4e25a079f7f632b3a884caed15025712bd09cb51d0797317d00126de |
| Producer call1294/reference01/actual_exit_unvalidated.json | afb62cf97fddb2cc88c86dbc850315e5646a55fc0cc051dcf32ca9e66da4ce30 |
| Producer call1294/reference01/execution.json | 587d141cd96ffa0a31165eb8ac9d8b51be5d3baf37115dcc185ec41b37663016 |
| Spike build/spike | c03c5a84f2313b2e0bb28be7aba496836b8d7b29e472c918457bca21f8abc7d2 |
| Spike riscv/decode_macros.h | 3d59de02867434c364d796e53c4b4ea7832cb21c7970bcab58c5f287aedafd7f |
| Spike riscv/csrs.cc | 8f22b4fc5f2b6b5d5b9d01ac9abd18fe9aed0f41b27cefd7e4531cfd342a5fdc |
| Spike riscv/execute.cc | b5339a8fed1eb74e22f882195930e845cd6f54e48755f9bd8697192f219acb04 |
| Spike riscv/v_ext_macros.h | 85120cf1bff1425251485545f738851aa28a38b4986ef33a006cfec69f1755f3 |
| Spike riscv/insns/vfredmax_vs.h | c6135f6c45f5c1306832b954a4e073d6c687258bc9afb9a1a81d52b154b53305 |
| Spike softfloat/fall_maxmin.c | d0e4361c28a63c821a63f4cf2d423d6a640dba9ecdc0801b23005fc5773cff5b |
