# Independent E16 MF4 Entry Review

Decision: **APPROVE_FULL_E16_MF4_M6_ENTRY**, no blocking findings for the
exact frozen plan `17fc37e50f5420488a62872513fa77ce28ea89814ee2d5d3401ddcef27c751e0`.
[ENTRY.json](ENTRY.json) is the binding independent-entry payload. This is not
parent launch authorization, resource admission, DUT PASS, or original Linux
closure. No Host/Spike/DUT/build, live-service query, or raw trace reparse was
performed. Only this new review directory was written.

## Source And Exact Scope

This is the original `rvv_extended04` arithmetic e16/mf4 matrix:25 operations,
3 seeds,4095 continuous calls,65520 16-bit results,8190 guards,4095 returned
vstart checks and53235 helper instructions. Capacity16, vlenb128, full128-byte
predicate setup and original1024/1026-element static arrays remain. It is not
the ordered-reduction e16 case, a prefix, or a source-history reset experiment.

The original C text is missing. The selected reconstructed C has SHA256
`7483f9dfde7012f7b800314fe1765f8cee9836fbcfbdc16fc641554397884e91`;
the existing reconstructed Linux ELF was independently rehashed equal to the
archived ELF `e538572bcf13bd7338647f5a7e5b7bfc8627f1ee04598d8fb0283a76926b998c`.
This supports binary-equivalent reconstruction, not original-text recovery.

The stored runtime diff was independently regenerated and compared exactly.
Only Linux entry/I/O/exit adaptation is present; no loop/tuple/oracle stop was
introduced. Source assembly and operations.h equal their archive counterparts.
The original C and separate SEW16 model agree on seeded xorshift initialization,
edge-value overrides, 7 VLs,3 predicates, per-kind restart counts, signed divide/
remainder corner cases, slide/gather source bounds, reduction seed, compress
packing, and sentinel checks. `rows(16)` rejects other widths; its unused FP
branches are not exercised or counted as FP16 arithmetic coverage.

Independent static ELF inspection verified every stored code-map instruction
against actual ELF loadable bytes. In both SoC and Spike, all26 helper windows
(capacity3 instructions plus25 operations of13 each) match uniquely in the
original stripped Linux ELF. No symbol-name assumption was made for that
stripped original. The 328 static instruction words are distinct from the
53235 dynamic operation-helper instructions across4095 calls.

SoC ELF: `509e072989f6e661ec1fcf899c9ea944b43f29f643960032928f9d723505a5b6`.
Spike ELF: `a6c082ecbc312d33be27c9c5374023113c9d1c811ae681f1a62d3d50a9d02430`.
Every model tuple and saved reference ledger row was compared against the
independently enumerated original loop order. All4095 ledger rows retain all18
result/guard reads, exact source arguments, returned vstart0 and the original
target PC/encoding at helper instruction8. The final tuple is seed2/op24,
VL16/mode2/start15; no truncated final operation is accepted.

## Reference Receipts

`full_e16_mf4_prepare01/READY.json` SHA256:
`beac34d373d7dadaa1dda388417ec87905273b5541a654b793d42f16c493fd0a`.
Its156 evidence pins are contained unchanged in the959-pin runner plan.
All959 files were strongly rehashed. Archived reference raw files were hashed,
not reparsed; there was no active CSV access.

Unlike an inferred subprocess success, this preparation has dedicated receipts:

| Saved receipt under rvv_matrix_e16_mf4/reference01 | Actual result |
| --- | --- |
| execution.json | Spike wait0, no timeout,6.933458621s, PID1808055 |
| audit_process_exit.json | Audit wait0, no timeout,57.052312153s, PID1808179, attempt1 |
| reference.json | Full4095 original oracle,65520 results,8190 guards,4095 vstarts, actual HTIF success |

The recorded reference code persists `proc.wait()` before requiring success,
and independently persists the parser child's wait result. READY, receipts,
reference report and ELF identities agree. The reference report SHA is
`b6ce6382cefaffe70a6c8d000b05033d4aa0a7143be973c3f515ab4468d3a17a`.
Raw SHA `1f329741d08d49838b15bb72db110425bbc441343a71d098b74ab774df11ef28`
matches253386956 actual bytes. Of3810000 recorded retirements,3807882 are
firmware through HTIF,5 boot and2113 post-HTIF park; these sum exactly.

Reference readiness is accepted here by reviewing that complete hash-bound
ledger, parser and actual receipts, not by claiming another independent raw
instruction traversal. The parser checks full contiguous helper windows,
actual setup memory, full results/guards, counters, original completion markers
and HTIF. The original has no explicit fflags oracle; none is invented.

## Checker And Reset Review

`full_e16_mf4_vcs_m6_plan01/checker.py` binds the exact e16 sourceproof, ELF,
model and reset profile, then inherits legacy `Strict.consume/finish` unchanged.
Important contracts in `full_small2_vcs_m6_plan01/checker.py` are retained:

- Every retired PC/code must match the actual ELF and retirement order starts
  at `_start`. Full helper windows reject internal-only entry, duplication,
  omission, interruption, wrong operation and excess calls. Other RVV and
  out-of-phase CSR instructions are rejected, not merely counted by entry PC.
- SEW16 derives width2. Actual scalar result/guard load width, alignment,
  read mask, destination and signed/unsigned value are checked independently.
  All16 result elements and both guards must be read once per original call.
- Scalar store address/base/enables/value require known GPR state; output data
  is never learned into a missing source register to excuse a mismatch.
- Startup BSS must be fully zeroed before main. Source arrays, full predicate
  and old destination are checked at each helper entry. End counters, exact
  console markers, CTRL address/store value0 and side-effect-free park are
  mandatory. SoC exit is not mistaken for Spike's HTIF encoded1.

The profile is exact frozen M6, not an architectural assumption that all RISC-V
registers reset zero. Its10 RTL pins bind FpgaEn0 configuration, FF regfile,
reset path and RVFI transport. Frozen `cv64a6_imafdcv_sv39_config_pkg.sv:85`
selects FpgaEn0; `issue_read_operands.sv:864` selects the implementation;
`ariane_regfile_ff.sv:62` resets the register array to zero. Fresh full-start
execution is required, not an arbitrary midstream trace.
The profile's old plan SHA identifies the inherited reset proof, while its
new allowed_shape/ELF/reference-bound fields are checked for this exact e16.

Stored Host15 passed with actual wait0 in33.402520046s. It exercises a full
constructed4095 stream and the actual e16 compiled ABI entry separately,
including main0x80000cd6, saved RA0x80000052 and reset s0. These are explicitly
constructed Host rows, not DUT captures. Negative checks cover wrong masks/
addresses/values, unknown source, missing startup, profile/spec/model drift,
last-result/guard corruption, incomplete final call, late abort/plan drift,
owner bounds and durable exit retention. No Host tests were rerun here.

## Worker And Launch Conditions

`replay.py:reviews` requires both this independent entry and a separate parent
authorization, hash-bound to the exact plan/image/reference and evidence files.
It does not treat PREPARED/dryrun/Host status as authorization.

The direct systemd MainPID and cgroup, fixed unit, RuntimeMaxSec13200,
KillMode=control-group and Restart=no are checked. The common resource gate
requires live+new+reserved <=24 and at least32GiB available. Only disappearing
processes are ignored; other process-inspection errors fail closed. No live
resource query was performed during this review. Frozen reserved_slots0 means
parent must coordinate not-yet-live reservations before authorizing this run.

The wrapper extends the actual frozen monitor's failure regex with strict
RVV/DETAIL/FAIL/trap vetoes, and captures its numeric outcome with fsync before
the generic or strict postchecks. A failing postcheck preserves that numeric
outcome and changes acceptance to ERROR/CANCELLED. First failure/timeout sets
sticky abort; no retry path is authorized. A monitor exception remains failure,
not an invented child exit result.

The strict full-CSV postcheck precedes COMPLETE acceptance; actual private ELF,
runtime label, simulator image, command/no-FSDB, markers, counters and exit are
checked. The historical source name remains distinct from the runtime test id.
Late disk-plan/input/image/review drift or abort prevents PASS; terminal
publication checks pending signals under the existing protected publish gate.

Estimated time7735.343s uses3807882 reference instructions and measured slower
M6 e32 throughput590.724701/s plus20%. It is not measured e16 duration or a
guarantee. Fixed limits are simulator10800s, worker12000s, service13200s. The
worker reserves900s for observation before admission; outer cleanup allowances
do not authorize a longer simulator run. Parent must explicitly accept this
budget risk and separately authorize the one fresh run.

## Scope Of This Acceptance

No evidence justifies claiming DUT4095 PASS now, all22-shape acceptance,
Linux/board closure or an fflags guarantee. There is no new blocking defect
found in this preparation/entry contract. Parent authorization and runtime
capacity admission remain unresolved by design. All old e8/e32 helpers,
profiles, plans and evidence remain unchanged.
