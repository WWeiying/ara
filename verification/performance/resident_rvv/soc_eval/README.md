# Resident PV SoC Evaluation

Experimental direct-wrapper software for the new resident-PV SoC image. This
does not advertise a runtime capability, modify the SDK, or establish FPGA or
performance acceptance. The first execution is smoke only. ABBA requires separate
explicit smoke acceptance; there is no automatic run or ABBA action here.

## Build And Identity

`experiment.py` supports `--kind smoke|abba`. Both use the accepted
`akv_pair_integration_build_20261107_01` SDK archive, data, GNU flags, and 15
unchanged objects. Only the entry, `pv.S`, sealed `pv_prepare/prepare.S`, and
sealed `rotation/pv_rotation.S` are compiled. The latter is renamed to
`resident_pv_rotation_body`, with `resident_pv_rotation_always` selecting the
strong rotating-register baseline. The candidate prepares six source registers
and issues `0x0485705b`.

The explicit input inventory includes these three build files, Bacon's four
wrapper files, and the parent's two resident checker files. Compiler dependencies
must already be pinned; live SDK, dirty assembly, RTL, and dependency trees are
not imported. Build receipts inventory all software artifacts. Compilation alone
leaves the SoC binding pending until an explicitly selected successful image is
checked. No build01 success is assumed.

```sh
python3 -B verification/performance/resident_rvv/soc_eval/test_experiment.py -v
python3 -B verification/performance/resident_rvv/soc_eval/experiment.py recipes --kind smoke --output /tmp/pv-recipes
# After parent review, use a fresh direct signoff output child:
python3 -B verification/performance/resident_rvv/soc_eval/experiment.py build --kind smoke --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/resident_pv_soc_eval_smoke_20261109_01 --parent-reviewed
python3 -B verification/performance/resident_rvv/soc_eval/experiment.py verify --build /path/to/software-build --soc-build /path/to/reviewed-soc-build
```

The new, separate `checked_soc(directory)` accepts only
`RESIDENT_PV_SOC_BUILT_NOT_EXECUTED`, matching 4 lanes / VLEN1024 / shared integer
multiply / no shared FMA / 16 MiB / pure CVA6 / PV enabled / capability zero.
It checks the frozen predecessor, exact filelist/recipe, 13 replacements plus six
new modules (including `operand_requester.sv`), include closure, baseline TB,
prepared receipt, standard manifest, and complete `simv`/`simv.daidir` inventory.
Live service stdout/stderr/status are excluded. It never relaxes old accepted
`checked_soc` or other global checkers.

## Later Execution

Smoke performs one complete D128/H2/T137 candidate call, tiles 64/64/9. Its
firmware checks 256 outputs against `native_golden` bitwise, FCSR exactly 3,
VCSR/VSTART, query, guards, and source-data hashes. Independent host numerical
and CPU/AXI checks are still required before accepting the run.

Future execution must include `+RESIDENT_PV_PERF +RESIDENT_PV_WATCHDOG` (32768-cycle
lease guard), and be separately owned and bounded. No simulator is launched by
this script. `check_resident_work(vector_path, log_text, kind)` reserves the
parent's `check_successful_pv` API and preserves its partial scope:
`numerical_checked=False`, `protocol_checked=False`.

For ABBA, expected legacy AKV PERF records are 674, resident PV records six,
vector AKV allocations 664, and exact `0x0485705b` allocations six. Each candidate
call has 2192 FMAs per lane. Each PV command drains 96 source words (24/lane),
writes 64 results and receives 64 final acknowledgements (16/lane). Smoke has
100 legacy records, three PV records, and 99 vector AKV allocations. The parent's
checker validates PV allocation/write/done geometry, lane work, and flags union;
the old `uvm_coverage` `akv_column` classification includes f7=2 and is **not new
PV semantic acceptance**. No old column-count acceptance is reused.
