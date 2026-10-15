# Full Original E16 MF4 Preparation

Status: **FROZEN_PREPARED_NOT_ADMITTED_NO_DUT**. Preparation is complete; source
reference and DUT-entry review remain independent gates before main may launch.
No production RTL, sealed e8/e32 artifact, image build or DUT was changed/run.
All invoked preparation/Host/Spike/offline-audit/dryrun processes have exited.

## Exact Scope And Provenance

Original rvv_extended04 arithmetic e16/mf4, not ordered reduction:
25 operations,3 original seeds,4095 calls,65520 full result words,8190 guards,
4095 vstart checks,53235 original helper instructions; cap16/vlenb128.
All source setup/global RNG/history,128 physical predicate bytes,16 results
per call, both guards and original operation/seed/VL/mode/start order remain.
Original large static arrays/BSS remain. No prefix, per-call reset, synthetic
tuple substitution or invented fflags oracle. C text is binary-equivalent
reconstruction, not recovered original C text.

Existing recovery22 proves byte-identical complete Linux ELF; preparation
rehashes all22 archived/reconstructed ELFs and reconstructed C. Candidate:

| Input | SHA256 |
| --- | --- |
| Original/reconstructed Linux ELF | e538572bcf13bd7338647f5a7e5b7bfc8627f1ee04598d8fb0283a76926b998c |
| Reconstructed original C | 7483f9dfde7012f7b800314fe1765f8cee9836fbcfbdc16fc641554397884e91 |
| Original e16/mf4 assembly | dff1fdc271e574eb7206583a446fb0fd2cc99be20a406024280c955b51905c33 |
| Original operations.h | 7686eb17f96d500c82711d09bbaa74c965352b4257b0b7db3510d3fbbd9bf48c |
| Runtime-only SoC ELF | 509e072989f6e661ec1fcf899c9ea944b43f29f643960032928f9d723505a5b6 |
| Runtime-only Spike ELF | a6c082ecbc312d33be27c9c5374023113c9d1c811ae681f1a62d3d50a9d02430 |

New software ports only adapt runtime, preserving full loops. Every original
capacity/op helper window is matched uniquely against the archived stripped
ELF, unchanged3/13 instructions. SoC and Spike have distinct runtime identities.
The original-stripped-ELF nm diagnostic is expected; exact window byte matching
does not rely on nonexistent original symbol names. No original rebuild retry.

## Actual Preparation Results

- Software Host: full4095-call positive,8 injected active/prestart/inactive/tail/
  left/right-guard/vstart-low/high errors all rejected, with all original scalar
  checks retained. Independent model admits SEW16/25ops only; uint16_t Host data.
- BSS reference gate:1 positive and11 negatives PASS. Correct pre-main zero-sd
  initialization versus byte-only runtime console distinction retained.
- Spike: one invocation, actual wait exit0,6.933459s, no timeout; limit120s,
  24000000 steps and6GiB raw cap. Actual253386956-byte raw, SHA
  1f329741d08d49838b15bb72db110425bbc441343a71d098b74ab774df11ef28.
- Full reference audit: one parse, actual child wait exit0,57.052312s within600s.
  Full4095/65520/8190/4095/53235 accepted, original complete setup and counters,
  vlenb128 once/capacity16 once, actual HTIF zero-exit encoding1, original park.
  3810000 retired records,3807882 firmware instructions through HTIF,5 boot
  records and2113 parking records. No reference retry or tail-only shortcut.
- DUT checker Host15: actual exit0,33.402520s, timeoutfalse. One full4095 stream
  plus actual e16 compiled _start/fullBSS/main80000cd6/ra80000052/s0 save fixture;
  rows are source-derived constructed Host rows, not claimed DUT capture.
  Wrong masks/address/value, missing source/start, mismatched profile/spec/model,
  final result/guard, incomplete tail, late abort/plan and owner gates reject.
- Prepare and dryrun each actual exit0. Dryrun emits one private ELF command;
  it does not execute it or query live resources.

## Runtime Gate And Budget

Frozen M6 image.json SHA
a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0.
Separate e16 reset profile binds its exact SoC/spec/source bound to the reviewed
M6 FpgaEn0 FF regfile/10 RTL pins and fresh reset/full-start premise. Only this
proven profile initializes32 GPRs to zero. Unknown registers are still rejected;
no learning from observed wdata. Legacy Strict.consume/finish remain unchanged.

New unit ara-arithmetic-full-e16-mf4-m6-01.service; jobs1, direct MainPID/cgroup,
KillMode=control-group, Restart=no. Simulator10800s / worker12000s / service13200s,
no retry/extension/build/FSDB. Numeric monitor exit/timeout is durable before all
generic/strict checks. Full source oracle, raw failure veto, final ledgers,
sticky abort, late pins and independent/parent approval bindings remain required.

Measured reference3807882 instructions at measured slower M6 e32 throughput
590.724701 retire/s plus20% projects7735.343367s, about2.149h, below3h DUT cap.
This is not measured e16 DUT runtime or a guarantee. Main still accepts the
fixed-budget/resource risk; no service deadline extends simulator10800s.

## Frozen Handoff

| Artifact | SHA256 |
| --- | --- |
| ../full_e16_mf4_prepare01/READY.json (156pins) | beac34d373d7dadaa1dda388417ec87905273b5541a654b793d42f16c493fd0a |
| Reference report | b6ce6382cefaffe70a6c8d000b05033d4aa0a7143be973c3f515ab4468d3a17a |
| prepared01/plan.json (959pins) | 17fc37e50f5420488a62872513fa77ce28ea89814ee2d5d3401ddcef27c751e0 |
| checker.py | 01507d4a7e3ba873d3bf2f91aabe73d1f825c46166619ac5de000e0e07561204 |
| replay.py | 4c882bbd75ab4915c9a7160f493f1ff6be23881bb04b3b75a943f55cfc971944 |
| reset_profile.json | d9b51ce0d44c08fe96c72d921dbffb778346fa996dbd194fbfb08257502823c3 |
| host01.json | a283b319803d12cc60b6f8e00df6dcdf13f3b271884c728eb9fcf0e3fbf62386 |
| prepared01/dryrun.json | 3915ef0de2d48a19a7e17ab00b31323a7b181b191056435a5182e2631222d9d0 |

Exact future worker/systemd command is in prepared01/ready.json. README.md
documents required independent-entry and parent JSON schemas. Those paths/hashes
are placeholders until reviewed, not authorization already obtained. Source
READY is producer reference acceptance pending independent review, not DUT PASS.
