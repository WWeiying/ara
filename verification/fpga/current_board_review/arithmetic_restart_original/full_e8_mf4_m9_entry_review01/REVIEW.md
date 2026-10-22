# M9 full e8 mf4 entry review

Decision: HOLD for one concrete owner-evidence gap; no DUT authorization receipt
issued. Reviewed plan SHA256:
`db1fc1c9bda5c9aabede944179c1e39b9a9c493efe535178e0a56fcc940eaecc`.
All 896 plan pins freshly matched. No Host/reference/DUT was run.

## Blocking finding

`full_e8_mf4_o2_vcs_m9_plan01/checker.py:133` marks a memory owner required only
for indices (1,2,3,4,11). These correctly identify the three CAP32 loads,
mask load and CAP32 store in each original op helper. They do not cover
op_24's target load at index8 when vstart < vl. Actual unchanged model has
189 op_24 calls, including 117 with vstart < vl.

Static counterexample: remove every uop_alloc/uop_done belonging to one such
active target, retaining its arch_start, CVX pair and retirement. Its owner
then has allocs=dones=0; it is not required. The 20664 memory retirement/arch
count, 20475 fixed-helper requirement, positive aggregate allocation count and
empty live map still hold. Shared trace.validate_trace also allows an arch
request with no backend allocation and only checks extant allocation pairs.
Thus this omission is not caught by composition. This is a missing-evidence
acceptance gap, not evidence that original arithmetic results are incorrect.
No mutated trace or Host was executed for this static counterexample.

Narrow correction: derive target-load requiredness from its ordered original
call (op24, index8, vstart < vl); preserve permitted VL0/start>=VL elision.
Require per-owner completion, not a fixed total uop count. Add one complete
active-target-pair deletion negative; preserve the existing Host evidence.
Aquinas was notified to hold launch and prepare a successor.

## Other requested checks

- Reset authority is genuinely M9 image-bound, not a guessed unknown-register
  default: image.json points at the frozen snapshot and compiled manifest;
  actual simulator.conf and vcs_source_manifest.json hashes match image.json.
  All ten reset/encoder RTL pins appear with matching hashes in that manifest
  and freshly match actual files. Configuration package sets FpgaEn=0 at85;
  ara_soc gen_usr_cva6_config does not override it; build_config_pkg copies it.
  issue_read_operands:864-900 selects ariane_regfile, whose compiled FF source
  resets mem to all zero at63-64. Testbench asserts reset at776 before release
  at784. Trace monitor resets retirement/owner state on reset. Strict requires
  first retirement _start and full ordered BSS initialization before main.
  Register lookup rejects absent bases/sources rather than defaulting them0.
- Profile's inherited plan_sha256 names the old reset-authority plan, not the
  current entry plan; current binding comes from the exact profile hash,
  M9 image hashes, allowed_shape and exact SoC ELF hash. No current-plan claim
  is made from that inherited field.
- Helper windows and setup: exact original PCs/opcodes, all13 instructions,
  capacity once32, initial vlenb128, ordered CSR prelude, ABI arguments,
  original input/RNG/mask/sentinel bytes and all34 scalar result/guard reads
  per call are enforced. This is not a general scalar branch re-execution
  checker; acceptance checks the original ordered call/data obligations and
  actual oracle outcomes, not every scalar ALU/branch semantic independently.
- Actual SoC has one failure symbol, failure.part.0; Strict maps and vetoes
  its entry. It rejects trap_entry, bad console/detail markers, missing oracle
  bytes, extra/interior helpers and wrong final error/check/element ledgers.
  Multiple future compiler clones would need renewed review; this ELF has one.
- Actual SoC exit is an eight-byte CTRL write at 0xd0000000 with raw0 and a0=0,
  not Spike's HTIF1. Only exact original park PC/encoding is allowed afterward.
- Full scope stays4095/131040/8190/4095 and53235 helper instructions. Existing
  reference and audit actual exits0 are retained; no fflags oracle invented.
  Host15 actual0/49.44049s includes synthetic full stream and constructed
  actual-ABI fixture; it is not captured DUT evidence.
- Fixed jobs1/case10800/worker12000/service13200; no build/retry/FSDB, direct
  service ownership/resource admission, numeric simulator outcome before
  postchecks, late plan/pin checks and sticky abort remain. Projection9282s
  is not measured M9 runtime. Exit hook records actual service result, and
  metadata collector requires success/exited/0 before accepting the terminal.

After a narrow owner correction and new frozen plan, review that delta only;
do not repeat software conversion, full reference parsing or all Host layers.
