# Static Physical-Flow Compatibility Proposal

Only new files in this directory. No canonical/old script modification, EDA,
container, real library inspection/measurement, simulation or PPA closure.
Parent-owned promotion files and the frozen reader-fault gate are untouched.

## Four Prospective Targets

1. `backend/syn/ara_soc/v1-dc/global_scripts/dc.tcl`: the actual integrated writer
   (there is no `backend/globaldc.tcl`). Select AKV-owned SRAMs under
   `*/i_akv_engine/`, then classify their reference and legacy/unified hierarchy.
2. `verification/akv/synthesis/akv_engine_dc.tcl`: same selection at standalone
   `i_akv_engine/`; add the Q64 DB path to its library existence/link list without
   reading or claiming availability of that library during this preparation.
3. `hardware/scripts/akv/check-synthesis-preflight.py`: explicit unified selection,
   required support-source order and Q64 blackbox/DB linkage; retain legacy
   defaults and QBS-only behavior. KV128 and existing macro/clock/flow checks stay.
4. `hardware/scripts/akv/collect-synthesis-results.py`: validate organization/Q
   metadata in raw reports AND stored JSON summaries; require both Q64 and KV128
   library identities for unified collection. Existing source/artifact freshness,
   hashes, area arithmetic and timing-field validation remain, not replaced by
   a static capacity calculation.

`render.py` makes exact reversible replacements. Mixed CRLF/LF outside the
integrated metric block is retained byte-for-byte. Fragments are generator inputs,
not new production runtime dependencies. `prospective/` contains four complete
candidate files, `physical_flow.patch`, and `manifest.json` with before/after and
helper hashes. Never execute the candidate Tcl to validate this proposal.

## Organization Contract

| `akv_sram_organization` | Total | Legacy V1 | Q | V2 / shared KV | Bits |
| --- | ---: | ---: | ---: | ---: | ---: |
| `legacy_v1_v2_64x256` | 20 | 4 | 0 | 16 | 327680 |
| `split_v1_96x256_v2_128x256` | 10 | 2 | 0 | 8 | 311296 |
| `unified_q64x256_kv128x256` | 9 | 0 | 1 | 8 | 278528 |

Unified hierarchy is exactly `i_unified_context/i_q_store/*` for Q64 and
`i_unified_context/i_kv_store/*` for KV128. The new Q counter is
`akv_q_sram_macro_count`. `akv_v1_sram_macro_count` remains zero for unified;
the existing V2 counter denotes its eight physical shared KV banks. Q is NOT V1.
Static unified capacity is `(1*64 + 8*128)*256 = 278528 bits = 34 KiB`.
This is logical macro capacity, not standard-cell area or measured PPA.

Both writers emit explicit organization and Q counter. Only the two exact old
count/capacity combinations may be read without both fields, for historical
report compatibility. Partial metadata, unknown/mismatched labels, unlabeled
unified data, boolean/floating counts, wrong totals, Q/V1 relabeling and wrong
capacities reject. Classification checks actual macro reference AND hierarchy;
mixed old/new storage, misplaced banks and unexpected SRAM widths/depths reject.
Unrelated CPU/QBS SRAMs are excluded. Integrated configurations with no AKV
remain synthesizable and emit `not_instantiated`/zero, which the AKV collector
deliberately does NOT accept as physical AKV evidence.

## Follow-Up Caller Requirement

The future unified preflight invocation must add:

```text
--akv-storage-organization unified_q64x256_kv128x256
```

It can explicitly override `--akv-q-sram-db` when the real reviewed library path
differs. A promoted unified graph with the legacy default is rejected, not silently
misclassified. This proposal does NOT edit the already frozen Makefile packaging;
parent must add the option in its coherent successor caller patch. Existing Bender
blackbox list and integrated setup already name64x256/128x256, so no speculative
changes to them are proposed. Their real availability/content remain unmeasured.

## Host-Only Checks

```sh
python3 -B -m unittest discover \
  -s verification/akv/canonical_promotion/physical_flow_compat \
  -p test_compat.py -v
python3 -B verification/akv/canonical_promotion/physical_flow_compat/render.py \
  --output verification/akv/canonical_promotion/physical_flow_compat/prospective
```

Tests reuse the unchanged historical collector/preflight host suites against
in-memory prospective modules. New tests exercise report/JSON roundtrip and
mutations with explicitly synthetic temporary area files and fake DB files.
Embedded host Tcl (`tkinter.Tcl`) evaluates only the classification fragment;
`get_cells`/`sizeof_collection` are Python mock collections, NOT DC, VCS or a
netlist/library measurement. Both hierarchy prefixes and all three organizations
are checked, including wrong path/reference/count/mixed-layout negatives.
No tool or container commands are launched by these tests. The generated patch
has not been applied to canonical files and proves no synthesis timing or area.
