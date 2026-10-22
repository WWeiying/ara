# Full Original E32 MF2 Standalone M6

Preparation only. No DUT launch authorization is implied.
One original unchanged SoC ELF, all5985 calls/95760 results/11970 guards/
5985 vstart checks/77805 original helper instructions,35 operations,3 original
seeds/global RNG in original continuous order. No partitioning or reduced case.
Old e32 CANCELLED and whole2 NOT_PASS records remain untouched.

Same frozen M6 image. New exact e32 reset profile derives all32 zero GPR values
from the reviewed M6 FpgaEn0 FF regfile proof, not an ISA reset assumption.
The unchanged legacy consume/finish methods retain the complete original oracle.
No register is learned from store data. No explicit fflags oracle is invented.

Standalone unit ara-arithmetic-full-e32-mf2-m6-01.service owns the worker directly,
jobs1, independent abort event/cgroup. Simulator10800s, worker12000s, service13200s;
no extension, retry, build or FSDB. E32 nominal slow proxy9564s plus20%=11477s
exceeds simulator10800s; completion is not guaranteed. Parent must accept this
fixed-budget risk and resource admission. Preparation/dryrun do not query live
services/resources. Trusted explicit user-bus environment is used at runtime.

Host includes one complete5985-call constructed stream and exact e32 ELF
_start/BSS/main ABI stack-save sequence, plus actual saved numeric monitor outcome
gates, wrong memory value/address/masks, unknown source, profile/spec mismatch,
final result/guard rejection, incomplete completion, late abort and owner/budgets.
The ABI fixture is derived from real compiled source, not a claimed DUT capture.

Prepare:
`python3 -B replay.py prepare --image /home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image --out OWN_DIR/prepared01 --reserved-slots 0 --authorize-prepare`

Dryrun:
`python3 -B replay.py dryrun --image /home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image --out OWN_DIR/prepared01 --plan-sha256 PLAN_SHA`

prepared01/ready.json contains the exact future direct-worker systemd command.
Replace review placeholders only after independent entry review and explicit
parent authorization. Entry JSON decision APPROVE_FULL_E32_MF2_M6_ENTRY must
bind plan_sha256, image_sha256, reference_ready_sha256, full_reference_scope_accepted,
checker_host_reviewed and evidence_pins including source READY, checker, profile,
host01.json. Parent decision AUTHORIZE_FULL_E32_MF2_M6_ONCE must bind plan SHA,
entry review SHA, unit and budget_risk_accepted=true. No launch occurs in prepare.
