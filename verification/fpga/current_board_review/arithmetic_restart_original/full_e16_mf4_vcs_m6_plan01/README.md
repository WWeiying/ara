# Full Original E16 MF4 M6 Preparation

Preparation only, no DUT authorization. Full4095 calls/65520 results/8190
guards/4095 vstarts/53235 original helper instructions,25 operations/3 seeds.
Source is the accepted binary-equivalent reconstruction of the original
rvv_extended04 matrix, not the unrelated ordered-reduction e16 single.
All original global RNG, setup,128-byte predicate,16-element oracle, guards,
source operation order and continuous history remain. No explicit fflags
oracle is invented. Original1024/1026-element static allocations remain.

Source/reference READY is ../full_e16_mf4_prepare01/READY.json,
SHA beac34d373d7dadaa1dda388417ec87905273b5541a654b793d42f16c493fd0a.
Original Linux ELF e538572b... was already byte-identically reconstructed;
original C text itself was not recovered. New runtime-only SoC ELF
509e072989f6e661ec1fcf899c9ea944b43f29f643960032928f9d723505a5b6;
Spike ELF a6c082ecbc312d33be27c9c5374023113c9d1c811ae681f1a62d3d50a9d02430.
The sole reference run exited0/6.933s, full audit exited0/57.052s; reference
producer PASS still requires independent source/reference admission.

New exact M6/e16 reset profile binds the proven FpgaEn0 FF register reset;
initial GPR zeros are not assumed for unknown images or midstream traces.
Legacy Strict.consume/finish stay unchanged. Unknown source/value/mask/address
rejection remains. The actual e16 main at80000cd6 and startup/BSS/ABI saves are
covered separately from the full constructed Host stream.

Standalone jobs1/unit ara-arithmetic-full-e16-mf4-m6-01.service.
Simulator10800s / worker12000s / service13200s; no automatic extension, retry,
RTL/image build or FSDB. Reference measured3,807,882 instructions projected
at the measured slower M6 rate590.725 retire/s plus20% gives7735.343s.
This is an estimate, not measured e16 DUT runtime or a completion guarantee.
Only runtime checks resource reservations/cap24/memory floor and direct service
MainPID/cgroup. Prepare/dryrun do not query live services or read active CSV.

Prepared ready.json contains the exact future direct-worker systemd command.
Independent entry JSON must use decision APPROVE_FULL_E16_MF4_M6_ENTRY and
bind plan_sha256,image_sha256,reference_ready_sha256,full_reference_scope_accepted,
checker_host_reviewed,evidence_pins including READY/checker/profile/host01.json.
Parent JSON must use AUTHORIZE_FULL_E16_MF4_M6_ONCE and bind plan SHA, entry SHA,
unit and budget_risk_accepted=true. These approvals are required before any DUT.
Monitor numeric exit/timeout is persisted before generic/strict checks; sticky
abort, late pins, exact full-oracle completion and terminal gates are retained.

Sealed e8/e32 workers/checkers/profiles/reference evidence are unchanged.
