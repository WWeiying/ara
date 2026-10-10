# GAP102 Runner Prepared, Not Started

Runner: `run_gap102_simulation.py`; tests: `test_run_gap102_simulation.py`.
12 tests PASS. Frozen GAP95 lifecycle SHA remains
`1e8b9f269fefd86e095c01d08bcff0be0fc52dd567273de26aafdebe7233d3d8`.
No frozen preflight, old runner, RTL, or image files were modified.

Actual prepare completed with162 pins and the exact66-file old-image inventory.
Record: `gap102-widen-acc-cross-old-image-717-20261006-01.prepared.json`.
SHA256: `4deaed6729e6bf19f78498055b35ba8281102bbc9d004d2d183fa478544d1ea9`.
The future runtime directory does not exist, and no simv process was launched.

The command is fixed to the preflight02 ELF SHA
`ee65c0c43fd7a3e36168673a3403b7b2316e26c153098a7c237ec7f597eba3c1`,
the old simv SHA
`2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3`,
seed1, +NO_FSDB, commit/vector traces and independent code.vdb.
Timeout is600 seconds; no retry, collection, admission or DVE is automatic.
Only explicit `run --prepared-seal` can invoke the frozen lifecycle.

The strict offline collector must later establish723 checks, no illegal trap,
one architectural MAC, full4096 VRF snapshot,1536 source-array bytes, exact CSR
snapshots and64 recovery/guard bytes. The raw Spike reference contains35 vector
write instructions and48 physical-register writes (6144 bytes), not merely516
active MAC bytes. Internal backend uops must not be confused with these
architectural counts. A simulator exit alone is not functional PASS.

## Index Calibration Against Real Measured Evidence

Calibration: `gap102-branch-path-measured-calibration-20261006-01.json`.
SHA256: `9fbc480284de4e48d095db95c0465e24ae10834a02c59a7970f44f8bc1b78023`.
Tool/tests: `calibrate_gap102_branch_path.py` and its test;3 tests PASS.
The runner additionally verifies measured line raw1334 is native BB1326,
file547, source line4542 in the actual compiled line definition.

Three distinct coordinate spaces must not be mixed:

| Coordinate | Conversion | Actual value |
| --- | --- | --- |
| Raw bitmap offset345, width1215 | integer bit1215-1-345=869 | new hit in actual GAP101A VDB |
| Branch vector ID784 | select XML vector record784 | not a bit index |
| Expression index985, vector length1270 | character1270-985=285, equivalent to `v[-985]` | `1` |

Expression indices are one-based from the right. Raw bitmap offsets are
zero-based from the left. Thus `v[985]` is incorrectly left-based and returns0;
`v[-1-985]` introduces an incorrect extra offset and also returns0.

This is not only string self-consistency: the approved real GAP101A trace has
opcodee2050827, NF8, trap vtype1 (e8,m2), request37 rejected with no backend
activity. The frozen RTL computes `(nf+1)*lmul_register_count(emul)=16>8`.
Independent rereading of that terminal raw VDB finds both branch raw345 and
the corresponding body line raw1334 newly hit against715. The same frozen
branch/source/line shapes and the admitted716 external seal bind the witness.

For GAP102, raw127 maps to integer bitmap bit1087, while vector1002 is the
record ID. Its expression1259 maps to character11 (`0`); complementary false
arm1260 maps to character10 (`1`), under parent expression1254 at character16
(`1`). Source expression5843's parent is1254. The big spec's root line1656 is
not used for leaf attribution. No EL identity or coverage increment is claimed.

## Parent Reverification Without Launch

From the signoff repository:

```bash
python3 -m unittest discover -s verification/coverage -p 'test_run_gap102_simulation.py'
python3 - <<'PY'
import sys
sys.path.insert(0, 'verification/coverage')
import run_gap102_simulation as r
out = r.life.OUT / 'gap102-widen-acc-cross-old-image-717-20261006-01'
seal = '4deaed6729e6bf19f78498055b35ba8281102bbc9d004d2d183fa478544d1ea9'
_, fresh = r.prepare(out)
saved = r.life.read_bound(out.with_name(out.name + '.prepared.json'), seal)
assert fresh == saved
print('GAP102_PREPARED_REVERIFIED_NO_LAUNCH', len(fresh['pins']))
PY
```
