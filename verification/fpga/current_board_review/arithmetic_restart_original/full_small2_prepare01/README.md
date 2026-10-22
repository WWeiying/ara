# Full Small2 Software Reference

Status: complete source-faithful Host/Spike preparation; both full references
accepted by recovery01, pending independent review. No DUT acceptance or launch.

## Measured Completion

The authorized single offline child returned actual wait rc0 in153.626305s,
without timeout (600s ceiling). See `recovery01/execution01/outcome.json` and
`output.log`. It parsed each immutable raw once; no new Spike invocation,
compilation, simulation, retry or bound change occurred.

| Original program | Calls / vstart checks | Results | Guards | Helper instructions | Firmware through HTIF | Raw retire records |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| rvv_matrix_e8_mf8 |4095|65520|8190|53235|4406446|4410000|
| rvv_matrix_e32_mf2 |5985|95760|11970|77805|5922051|5925000|

Each capacity helper executes once. Totals:10080 calls,161280 result elements,
20160 guards,10080 returned-vstart checks. The original three seeds, RNG,
full ordering, integer/FP transition, all25/35 operation helpers and every
13-instruction call window remain continuous, not reset partitions. Original
checks/elements/errors0 and final HTIF success are required. All scalar result
and guard reads are checked against the independent model. The source has no
explicit fflags oracle; this report does not invent flag acceptance.

Spike's already-persisted actual child rc is0 for each run: e8 elapsed7.737235s,
raw293505471 bytes; e32 elapsed10.543294s, raw396412404 bytes. Full-parse times
were57.172414s and78.894272s, distinct from Spike runtime and total audit time.
Raw includes five boot records per case and3549/2944 permitted post-HTIF parking
records, explaining the difference from firmware-through-HTIF counts.

`recovery01/fullparse01/status.json` records229 input pins unchanged pre/post,
including original bound/source/model/ELFs, both raw logs and execution records,
approved recovery checker and external `scoped_rv64c_memory.py` decoder.

## Preserved Checker Failure

The initial checker rejected startup `sd zero,0(t0)` at PC0x80000046 when BSS
clearing reached replay_log: e8 raw line1640/address0x80002160; e32 line6248/
address0x800053a0. Both are eight-byte zero stores, not runtime console output.
The original reference01/not_completed.json errors remain untouched. Interrupted
offline02 is also preserved and is not an accepted audit.

Recovery permits only the exact ELF-backed startup instruction, full ordered
aligned BSS range and actual t0/t1 context before main/printing. It verifies all
1434/2586 startup doubleword stores. Runtime console remains byte-store-only.
Host positive and11 negative gates passed before the authorized full parse.
No arbitrary wide console writes or source/oracle relaxation were introduced.

## Provenance And Scope

`prerequisites.json` verifies existing candidate04 prefix5 terminal evidence and
recovery22 byte-equivalence evidence. Original C text is unavailable; the
reconstructed C reproduces all22 archived Linux ELFs byte-for-byte. These new
bare-metal SoC/Spike ELFs adapt runtime only and are not byte-identical Linux
executables. Per-shape `sourceproof.json` binds original Linux ELF/helper code
and actual compiled helper windows; `model.json` binds complete call order.
These two shapes are original controls, not proof of closure for other stalled
shapes, all22 matrices or Linux timing. No existing prefix was rerun.

## Limited DUT Cost Proxy

Source: `../TERMINAL_AUDIT01.md`, actual candidate04 prefix5 wall times and
firmware retires (large-shape op0). Measured rates619.182818..686.494927/s give:

| Shape | Actual new firmware | Proxy seconds | Slow-rate proxy +20% |
| --- | ---: | ---: | ---: |
| e8_mf8 |4406446|6418.76..7116.55|8539.86 (2.37h)|
| e32_mf2 |5922051|8626.50..9564.30|11477.16 (3.19h)|

These are estimates, not measured DUT times or a proposed timeout increase.
Different LMUL, full arithmetic/FP mix and image version can change throughput.
In particular e32 is not demonstrated to fit a three-hour DUT budget with20%
margin. Any DUT admission/budget decision remains separate; no DUT was launched.

`READY.json` binds the exact terminal evidence and executable identities for
independent review. Original failed checker outcomes remain historical errors,
not rewritten reference successes.
