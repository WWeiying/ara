# Offline Checker Adapter Review

`python3 -B checker_reference_bridge01.py` completed with actual command
exit0 (tool receipt c97b47). No simulator/reference process was started.
Both existing raw reference inputs were checked against READY pins before
and after this one-pass adaptation. The running DUT checker/worker and
source/ELF inputs were not modified.

| Member | Actual reference scalar commits | Check calls | Restore readbacks |
| --- | ---: | ---: | ---: |
| LOAD | 120321 | 914 | 14 |
| STORE | 125321 | 914 | 14 |

The same frozen `dut_check.Checker` accepted the full expected operand
sequence, captured actual nonzero saved CSRs, captured both complete
handler CSR records, checked repair/SFENCE/same-PC retry and the ordered
successor load/add/store. It checked fault cause13/15, ecall9, VL9,
vtype26, vstart0, fcsr117, vcsr5 and exact stored trap records.
Five focused negatives rejected retire gaps, duplicate retire order,
backward pseudo-cycles, a saved-CSR mismatch and duplicate handler CSR.
The prior `host_dut_check01.json` separately records 11 tests, including
wrong tail/guard expected operands and durable numeric child receipts.

This is **Host adapter PASS, not DUT acceptance**. The bridge deliberately
omits vector memory writes from the scalar row interface and excludes the
one nonretiring fault partial record. Row order supplies synthetic cycles,
not hardware timing. After checking the actual reference HTIF write equals
1 and that no DUT CTRL exit occurred, the Host-only finish test substitutes
the expected CTRL0 endpoint. It does not manufacture a DUT CSV or numeric
simulator return code. Real DUT acceptance still requires its own actual
CTRL0, raw console, private ELF, command/image pins and durable numeric rc0.

Result: `result.json`; checker SHA256
`62ece09471c5b318b7e34d99b462571c0f93bcef5762511fba44c60df8412842`.
Bridge SHA256
`cfcbb56bf223805780bef08050ea74dd464a0d27373ae33f5aae4ef131040a1e`.
The two already-launched M7 runs remain untouched. Any later checker-only
failure must preserve the old result and use the same closed CSV offline,
not rerun the RTL.
