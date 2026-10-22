# Pre-Execution Host Coverage Correction

Tesla's static review found that the initial injection positions covered only
all-sentinel outputs. Before any Host execution, retain the same scenarios and
move sat-only to call index768 and mixed to768..774 (zero based). These are the
original seed0/op0/VL512/mask0/start1/control0..6 positions. Element8 has original
a=b=0, hence result0 instead of0x5b, proving a non-sentinel row. No generated
source, tuple, expected table, comparator, original helper, or budget changes.

Mixed still produces35 counted errors and20 printed details in original order;
the vstart-only control stays at index0 to cover the sentinel fast path. Original
Host source SHA before this correction:
`f3948eac1e65e6c35094c67e6a82c80117dd15294283da706430253fc8522343`.
No Host failure/attempt is being replaced: Host had not yet executed.
