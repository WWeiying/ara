# Independent Top-Level Plan Review

Status: **PASS_STATIC_PREFLIGHT_REVIEW**, no launch-blocking mismatch found.
Review timestamp:2026-10-11T10:43:28.757737+00:00.
One read-only verification pass using structured JSON and SHA256, independent
of the replay driver's preparation routine. No tests, simulations, service
launch, live inventory or predecessor-progress polling were performed.

## Identity

| Artifact | SHA256 |
| --- | --- |
| candidate04_plan01/plan.json | `34b4caf0f0810a3194449e58bc337b9cadb93d4a31847f70dc871b16c209e0b4` |
| candidate04_plan01/preflight.json | `078d8645c97e217e76db9bada3d0c16646e2e76906fcc67f06a048828447f203` |
| prepared02/soc/programs.json | `165c5c4d7dc83da93480b5389eda711aebd0af9928560f0aa5e0c0ea57e0da08` |
| replay_candidate04.py | `809f1ebf12eada714bcc6ede4600f9bf90ef04812e8edae6969d987d080cdf98` |
| Frozen candidate04 image.json | `e26b4a68939946d104c37917cf688a40ea6e1f963f048a586a5662d58c368673` |

## Checks

- **992/992 plan pins match** actual files; zero missing or changed inputs.
- Preflight plan SHA matches both actual plan bytes and the parent-reviewed
  hash. Dry-run summary and host-test log hashes match preflight exactly.
- Exact five names, order, counts56/38/56/56/56, jobs2, limits4000/4000/4000/
  1800/1800s, sum15600s and outer10000s agree with the reviewed contract.
- All copied ELFs and original port ELFs match the unchanged programs manifest;
  each plan case retains the complete original pass-marker list exactly.
- Programs provenance SHA matches; all43 prepared source/runtime files match
  their provenance. No source, oracle or ELF regeneration occurred.
- M4 image ledger, actual simv path and snapshot SHA agree across the plan and
  image ledger. All66 image-file pins and all539 frozen-source pins are present
  in the plan and match disk. Compiled source manifest and simulator config
  match their ledger hashes.
- Admission parameters retain cap24, minimum available RAM32GiB, predecessor
  release4, own slots2 and continuing reservations20. The predecessor **plan**
  hash matches; its terminal result was deliberately not read in this review.
- Dry-run metadata/summary contain exactly five DRY_RUN outcomes, and preflight
  records `VCS_started=false`. No `attempt.json`, `launch.json`, `replay/` or
  `complete.json` existed in the new plan output at review time.
- README is not a pinned input; its appended successor-plan explanation does
  not alter the approved plan hash or any sealed input.

## Launch Conditions Still Pending

Parent review and accepted38 terminal evidence remain mandatory. This review
does not grant capacity or claim that the38 jobs have finished. The actual
one-shot admission check is deferred to the explicitly authorized work call.

The10000s outer deadline is a **parent systemd launch obligation**: require
`RuntimeMaxSec=10000` and `KillMode=control-group`, with no automatic restart.
The driver itself does not install or enforce this service wrapper. This is
an explicit deployment requirement, not a claim that a bounded service already
exists. No worker was started by this review.

The prior17 host acceptance checks and5 dry runs are hash-verified evidence,
not rerun here and not DUT acceptance. Source recovery still means22 exact
reconstructed Linux ELF identities, not recovery of the lost original C text
or completion of22 original matrices.
