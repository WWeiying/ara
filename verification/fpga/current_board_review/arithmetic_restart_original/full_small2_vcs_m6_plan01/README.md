# Full Small2 M6 Replay Preparation

Preparation only. No simulation, reference invocation, compilation, RTL edit,
service start or live-DUT query is authorized/performed here. Independent entry
audit and a new pinned parent authorization are mandatory at `run`.

## Exact Scope

Reuse the frozen `../full_small2_prepare01` SoC ELFs, unchanged:

| Original program | SoC SHA256 | Calls | Results | Guards |
| --- | --- | ---: | ---: | ---: |
| rvv_matrix_e8_mf8 |181e24f087437f76519128e3a5cfab0e931b1d2df643fce41035d6bfd618f55b|4095|65520|8190|
| rvv_matrix_e32_mf2 |54931771b1ba6ade43ae776af14f52163323670ec8881dc2fc1f70fe1c6c994f|5985|95760|11970|

Full original25/35 operations, three seeds, contiguous RNG/state/history, FP
input transition and all10080 returned-vstart checks. No reset partition,
shortened oracle or added warmup. Original source lacks an explicit fflags
oracle; the source CSR behavior is retained without inventing flag acceptance.
These are two complete source-derived small-shape programs, not all22 matrices
or original Linux execution. Historical source names remain distinct from the
runtime test ids `arithmetic_full_e8_mf8` and `arithmetic_full_e32_mf2`.

Reference READY SHA256:
`db878aa262c882af8cf32dfa803426382b3869c1a0f47662c4a434bd8b6439b6`.
It binds actual offline wait rc0/153.626305s, the two previously completed
Spike children, full results and229 pre/post pins. Recovery-checker acceptance
is not an independent agent acceptance. Original errors/interrupted offline02
remain untouched. Prepare binds reference raw hashes, fixed checker, model,
full reports, original source/helper proofs, image/snapshot/config and imported
project helpers. No reference raw is parsed again by this preparation.

## Strict RVFI Adaptation

`checker.py` derives each backend's PCs/code/symbols from its actual sourceproof
and unchanged ELF hash, not a constant Spike-to-SoC PC offset. In particular
the e8 SoC BSS store differs from Spike; the unique startup `sd zero,0(t0)` is
located in the actual SoC code. BSS must clear the entire aligned range in order
with correct t0/t1, before main. Spike-only replay_log is absent and never read.

Every firmware retirement must match actual ELF PC/code; scalar addresses are
checked against decoded base+offset, width, byte enables and store source.
Output loads use actual integer RVFI rd_wdata and signed/unsigned load semantics,
not a fabricated vector-state stream. All16 results plus both guards are read
exactly once per call, including prestart/inactive/tail. Every helper entry
verifies the full original a/b/mask/sentinel setup and arguments against the
independent model, including RNG and FP transition. Capacity is exactly once;
each original13-instruction helper is contiguous and in exact operation/seed
order. Interior entry, duplicate windows, extra vector PCs and out-of-phase
CSRs are rejected. Original checks/elements/errors ledger must match exactly.

Console is reconstructed from actual SoC UART byte stores and checked alongside
raw console/VCS logs. CTRL requires its exact store PC, eight-byte write, raw0
and a0=0; Spike's HTIF1 is explicitly rejected. Only the original park is legal
after exit. Immediate partial `RVV_MATRIX_DETAIL` is a failure veto even without
a newline/final FAIL marker. Timeout is an incomplete run, not RTL-bug proof.

The unchanged frozen runner performs its generic CVX/retirement/uop validator
once; the new strict checker then streams the CSV once. No repeated full audits
or raw-to-synthetic conversion are performed on DUT data. Validation shares the
fixed worker deadline; the strict pass observes cancellation every4096 rows.

## Worker And Budgets

- Same existing M6 image, no build path. Private ELF copies and seed1 commands.
- jobs2; each case10800s; worker including observers12000s; service13200s.
- No retry or automatic budget extension. Dispatch requires enough remaining
  worker time for the unchanged case plus900s observer reserve.
- Direct systemd MainPID/cgroup owner, KillMode=control-group and Restart=no.
  Trusted explicit user-bus environment; query errors fail closed.
- Resource admission only at authorized run: cap24, available memory>=32GiB;
  `--reserved-slots` counts unused external reservations, not live jobs twice.
- Actual `_run_monitored` numeric wait outcome/command/timeout/failure is fsynced
  before generic or strict postchecks. A checker exception cannot erase it or
  convert it into architectural PASS. Failures latch cancellation and stop new
  dispatch; late abort/disk-plan drift preclude terminal PASS.
- Independent and parent reviews, all pins/image and fresh on-disk plan SHA
  are checked again at terminal. No GC service defaults are evidence.

Actual reference firmware counts are4406446/5922051. The measured candidate04
prefix5 proxy is619.18..686.49 instructions/s, giving6419..7117s and8627..9564s.
The planning upper rate740/s is not an additional measured rate here. The slow
proxy plus20% gives8539.86/11477.16s: e32 exceeds the fixed10800s case budget
under that margin. Different operation/image mixes can differ; completion is
not guaranteed, scope will not be shortened, and budgets will not be raised
automatically. The parent authorization must explicitly accept this risk.

## Commands And Admission

From this directory (M6 is read-only; prepare/dryrun do not query live jobs):

```sh
python3 -B replay.py prepare --image /home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image --out "$PWD/prepared01" --reserved-slots 0 --authorize-prepare
python3 -B replay.py dryrun --image /home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image --out "$PWD/prepared01" --plan-sha256 ACTUAL_PLAN_SHA
```

`prepared01/ready.json` contains the exact future direct-service command with
review placeholders. This is not a launch authorization. Independent entry
JSON must contain decision `APPROVE_FULL_SMALL2_M6_ENTRY`, exact plan/image/
reference-READY hashes, `full_reference_scope_accepted=true`,
`checker_host_reviewed=true` and actual `evidence_pins` binding READY/checker/
Host report. Parent JSON must use decision `AUTHORIZE_FULL_SMALL2_M6_ONCE`,
the same plan SHA, entry-review SHA, exact unit and `budget_risk_accepted=true`.
Neither review is fabricated or supplied by this preparation.

## Host Evidence

Host synthetic rows use actual SoC instruction/specification metadata and the
complete original model, not labels on a shortened positive. Both full scopes
must finish; negatives cover missing tail/full call, guards (including the last
e32 guard), active/inactive/prestart, actual arguments, wrong instruction/window,
FP setup, vstart, scalar read enables/sign behavior and HTIF1 misuse. Additional
tests exercise a real scalar Host subprocess with partial DETAIL (not a DUT),
durable child outcome on postcheck error, sticky abort, late disk drift, owner
bounds and missing admission.

The initial `host01` failure is retained: synthetic assignment selection omitted
startup t1, causing fixture KeyError before architectural testing. A subsequent
static preflight found the Spike-PC assumption for BSS, now replaced with actual
SoC-PC discovery. These are adapter/fixture defects, not measured DUT failures.
The `host02` fixture also selected an ra store without an assignment site and
was interrupted explicitly (actual wait130); its partial log is retained and is
not PASS. The successor filters to usable real scalar sites and caches identical
Host setup writes, without skipping any call/input/oracle check. `host03` is the
successor full Host run. Its exact result and final helper pins must pass before
any plan can be prepared.
