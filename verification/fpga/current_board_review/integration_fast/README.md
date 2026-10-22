# Fast Single-case Ports

Successor of the sealed `../integration` package. No sealed helper, current
campaign, RTL, snapshot or image is modified. Read [PROOF.md](PROOF.md) for
the per-bound argument and required preservation of the reduction cursor.

Prepared output: `/tmp/current-board-integration-fast01`.

| Artifact | Relative to prepared output |
| --- | --- |
| Run-compatible SoC ledger, 14 ELFs | `soc/programs.json` |
| HTIF ledger, 14 ELFs | `spike/programs.json` |
| Spike 14/14 PASS | `reference/reference.json` |
| New provenance with unchanged original case records | `prepared/provenance.json` |
| Exact C source differences | `prepared/sources.diff` |
| Complete output hash ledger | `result.json` |

Host tests: 3 PASS, including six original/derived differential comparisons
(12 host compilations) across three cases and VLEN512/VLEN1024. Scalar mocks
capture exactly one operation boundary, not architectural RVV execution.
Only `maskslide`, `reduction_fflags`, `gather_original` and `all` ELF hashes
changed; the other ten SoC ELFs are byte-identical to the sealed package.

Reproduce into a fresh directory (software/Spike only):

```sh
F=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review/integration_fast
python3 -m unittest discover -s "$F" -p 'test_*.py' -v
python3 "$F/prepare_fast.py" --out /tmp/current-board-integration-fast02
```

Parent-authorized example using the existing image, no rebuild:

```sh
I=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review/integration
O=/home/wangwy/fpga_runs/current_board_integration_final01
P=/tmp/current-board-integration-fast01/soc
if python3 "$I/run.py" run --image "$O/campaign/image" --programs "$P" \
  --out "$O/fast01-singles" --jobs 4 --timeout 300 \
  --case maskslide --case restart_compare --case reduction_fflags \
  --case m8widen --case wholemove --case slide1up_prestart --execute
then
  python3 "$I/run.py" run --image "$O/campaign/image" --programs "$P" \
    --out "$O/fast01-combined" --case all --timeout 300 --execute
fi
```

The same ledger supports the existing extended and separate gather commands.
The old pipeline pins the old artifacts: do not edit its receipts or pass this
package off as its original input. Parent decides any successor execution.
No VCS timing/speedup or RTL PASS is claimed by software/Spike preparation.
Original Linux program acceptance remains separate.
