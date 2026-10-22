# Prepared Runner Handoff

Status: **PREPARED_NOT_RUN**, Host27 PASS in36.228s, zero failures/errors.
No DUT/Spike/build launch and no live-simulator/service-status query occurred.
The only launched monitor-test child was ordinary Python emitting a retained
first-error partial line. It was stopped within the asserted5s bound, without
newline/finalFAIL, and the checked-runner abort latch was verified.

Exact scope remains66 original calls/all65 predecessors/cap1024,67584 results,
132 guards, original setup/RNG/vstart and13asm. The existing reference SoC ELF
is reused. Source/ELF identity, original reference/independent review, M6 image,
snapshot/config, frozen runner and shared helpers are bound by785 plan pins.
Neither `prepared01/replay` nor `prepared01/launch.json` exists at handoff.

| Artifact | SHA256 |
| --- | --- |
| `prepared01/plan.json` | `3d487be3a65775b2fa99cceec10bf9a09d9e2564e09efed66e7485a7abfa8006` |
| `prepared01/ready.json` | `3bf1b35783c02b400a0a0371eb4ade1f65dd79f6bf84a5b1dcf4e8507868fd56` |
| `replay.py` | `c438af5ccff71eb31c5e08838817b4c86c0dc69fbac276ec4ddfe158fa9e6575` |
| `checker.py` | `4da8e2fd64f40eb07f61fc8dda485eb17e7bc8276cb8a3e1c739e4656f1d1508` |
| `test_host.py` | `4a1c54aae67a90004a4c313e35d0d29fb4c3d67716c31dd44c203244a75019ff` |
| `host01.json` | `47fabc876f42aa7add0ae8d344014b83cacb8611297061c6b28278a4995dd5f7` |
| `README.md` | `d59a0e0222818facdf3f345f48500d592ee79a1fa665aa304da2645a8a83fae2` |
| Existing M6 `image.json` | `a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0` |

The prepared service command contains explicit review placeholders, not a
launch approval. Jobs1/case9000s/service10200s remain unchanged. Nominal273/s
estimate10056.39s exceeds the case budget; +20%=12067.67s exceeds3h. No expected
guarantee of passing or timeout increase is implied.

Run requires pinned e16 terminal acceptance and a new parent review explicitly
accepting budget risk, then runtime capacity/memory admission. The e16 terminal
has not been queried for this preparation. Resource snapshot is deliberately
null/deferred; unused external reservation is0 in this plan, so a different
reservation requirement needs a separately prepared/reviewed plan, not edits
to this sealed one. Service-exit facts are not inferred from worker status.

README documents the approval schema and full commands. All old e16/reference
and sealed helpers remain untouched. This successor and its plan are ready for
read-only review; no further edits are intended after handoff.
