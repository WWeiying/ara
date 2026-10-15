# Same-Source Extension Matrix: Ready for Parent Image

## Status

Six standalone software ELFs passed Spike: 24 trials each, 144 unique trials.
The combined non-reset ELF also passed all144 trials. **No matrix RTL replay
or RTL build was launched.** The parent's dispatcher candidate awaits its
combined image; these references do not validate that candidate.

Evidence: `matrix01/reference.json`, individual `matrix01/*.log`,
`matrix01/prepared/provenance.json`, and `matrix01/{soc,spike}/programs.json`.
Every ELF, original assembly, generated assembly, driver, runtime and helper
is hashed in those manifests. SoC programs are ready in `matrix01/soc/`.
`measurement01/` and the original VL127 program remain unchanged.

## Coverage and Derivation

| Program | Destination | Source | Factor | Trials |
|---|---|---|---|---|
| extension_e16_m2_vf2 | e16/m2, v24..v25 | e8/m1, v25 | 2 | 24 |
| extension_e32_m2_vf2 | e32/m2, v24..v25 | e16/m1, v25 | 2 | 24 |
| extension_e64_m2_vf2 | e64/m2, v24..v25 | e32/m1, v25 | 2 | 24 |
| extension_e32_m4_vf4 | e32/m4, v24..v27 | e8/m1, v27 | 4 | 24 |
| extension_e64_m4_vf4 | e64/m4, v24..v27 | e16/m1, v27 | 4 | 24 |
| extension_e64_m8_vf8 | e64/m8, v24..v31 | e8/m1, v31 | 8 | 24 |

The original campaign assembly for each shape is retained as `original/source.S`
and is a byte-identical prefix of generated `scenario.S`. The four original
functions are unchanged. Eight separately named derivatives retain all setup
loads/configuration/readback, adding only `csrw vstart,a5` immediately before
the extension; the unmasked derivatives additionally omit `,v0.t`.

`matrix.c` is a direct-trial derivative of the pinned oracle, not a claim of
byte-identical original C. It retains `(i*73 + seed*19)^0x85` input generation,
0x5b output initialization, the source-overwrites-high-destination adjustment,
signed/unsigned scalar extension oracle, complete physical destination checks,
vstart0 return requirement, `output+1`, and both guards. Prefix and inactive
bytes retain the setup image. No scalar search, policy relaxation, hint, or
extra fence is introduced. Original-source shape hashes and exact numeric
trial tuples are in each `original/cases.json` and the provenance manifest.

Trial layout, identical across shapes with shape-relative boundaries:

- 0..7: unsigned/signed overlap, all-one/all-zero/0xaa/0x24 masks, VL=cap-1.
- 8..15: masked/unmasked prefix, within a word, register boundary, and inside
  the overlapping source register. All use exact tu/mu preservation.
- 16..19: vstart=VL, VL0, full-VLMAX unmasked unsigned, full-VLMAX sparse signed
  with seed1 instead of seed0.
- 20..21: non-overlap v8 source controls with masked/unmasked prefix.
- 22..23: VL immediately before and after the destination reaches the source's
  high-overlap register.

This matrix does not cover every LMUL pair, fractional-source negative legality,
mixed source EEW within a multiregister source, ta/ma alternatives, or controlled
capture backpressure. All six sources here have LMUL1. Broader signoff remains
separate from the focused three-domain repair and the original VL127 acceptance.

## Commands

From the integration worktree, reproduce software/reference only into a new path:

```sh
python3 -B verification/fpga/current_board_review/extension_overlap/matrix.py --out verification/fpga/current_board_review/extension_overlap/matrix02
python3 -B -m unittest discover -s verification/fpga/current_board_review/extension_overlap -p 'test_*.py' -v
```

For the parent's future image, use the unchanged `integration/run.py run` with
`--programs <absolute-extension_overlap>/matrix01/soc`, a new `--out`, and
`--case <program-name>` or `--case all`. Do not use final03 to claim candidate
acceptance: its original VL127 livelock is confirmed in
`MEASURED_FINAL03_20261010.md` / `cycle_review02/finding.json`.

## Independent Final03 Completion Service

Separately authorized parent work uses `final03_successor01/` and service
`ara-final03-successor01.service`. It replays unchanged sealed programs/image,
serially: flags_sequence, reduction epoch/all, comparison matrix_e32, matrix_e16.
Each ELF has a600-second wall limit; no build or oracle edit is involved.

The extension investigation established why this timeout extension is justified:
the old comparison e32 trace enters trial81/100, e16 enters54/102, and both
continue retiring ordinary input-setup instructions at cancellation. Completed
e64 took285 seconds for100 trials. There was no MATRIX_DETAIL/MATRIX_FAIL in
the stopped e16/e32 consoles. `progress_evidence.json` records exact last trials,
retired PCs/cycles and trace hashes. This is unlike the extension's held request
with repeated maintenance and no scalar retirement.

The service was confirmed active at launch (Nice10) with its first VCS process
started. It is not polled afterward, per parent instruction. Inspect its own
`status.json` after completion; original final03 status/artifacts are preserved.
