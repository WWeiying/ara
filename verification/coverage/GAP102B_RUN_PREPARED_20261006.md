# GAP102B runner prepared only

No simv PID, runtime directory, simulation, retry, collector or admission was
started by this preparation. Parent independently reverified the preflight;
the runner deliberately binds the original03 manifest rather than replacing it
with the parent-check directory.

Runner: `verification/coverage/run_gap102b_simulation.py`.
Tests: `verification/coverage/test_run_gap102b_simulation.py`,13 PASS.

Prepared record:

`verification/out/gap102b-widen-acc-vstart-old-image-717-20261006-01.prepared.json`

SHA256:
`767835e44c1c2f952645f2e12045defad1ce20d77e6fa346d593acdd5cfcbd59`

The150 pins include runner/tests, frozen lifecycle helper and its tests,03
manifest and all79 preflight pins, image plan and all66 old image files.
Conflicting expected hashes reject, and inputs are checked before/after the
read-only prepare validation. No source redirection, compilation or host/Spike
execution occurs. Raw Spike is parsed for an independent full oracle replay;
the target is freshly rebound against the fixed717 design/source context.

- Preflight03 manifest seal:
  `9658afe68b674bb25fb849b4fcab9b46c1778ee4c4051562d0a162e73df72552`.
- Actual GAP102B02 ELF SHA256:
  `5f27f7052c5805c46f80c859713350d15d5037754a2784a75039e245f7a593bd`.
- Frozen lifecycle SHA256:
  `1e8b9f269fefd86e095c01d08bcff0be0fc52dd567273de26aafdebe7233d3d8`.
- Old simv SHA256:
  `2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3`.

Future explicitly authorized run uses600s wall timeout, fixed seed1, +NO_FSDB,
fixed ELF/tohost, commit/vector traces and independent five-metric code.vdb.
No automatic retry or admission is provided. Successful simulator exit alone
does not qualify software correctness or coverage gain.

Software expectations are723 checks, zero traps, VL129/vstart128 for the exact
one MAC,4 active MAC bytes,2 active source-load bytes, full4096 VRF bytes,
1536 source guard bytes and64 recovery guard bytes. Spike35 instructions/43
register declarations/5504 declared bytes are NOT DUT physical traffic counts.
Raw127 hit and snapshot routing remain predictions, not prepared evidence.

Parent revalidation only, from the integration repository:

```bash
python3 -m unittest discover -s verification/coverage -p test_run_gap102b_simulation.py
python3 - <<'PY'
import sys
sys.path.insert(0, 'verification/coverage')
import run_gap102b_simulation as r
out = r.life.OUT / 'gap102b-widen-acc-vstart-old-image-717-20261006-01'
seal = '767835e44c1c2f952645f2e12045defad1ce20d77e6fa346d593acdd5cfcbd59'
_, fresh = r.prepare(out)
saved = r.life.read_bound(out.with_name(out.name + '.prepared.json'), seal)
assert fresh == saved
assert not out.exists()
print('GAP102B_PREPARED_REVERIFIED_NO_LAUNCH', len(fresh['pins']))
PY
```

The CLI exposes an explicit `run` requiring the external prepared seal, but it
has not been invoked and still requires parent authorization. Do not invoke
`prepare` again into the same record: creation is exclusive; compare the
in-memory fresh contract as above. All prior GAP102 and GAP102B failures remain.
