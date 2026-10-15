# Static Inspector Correction

`python3 -B inspect_compiled.py` actual exit1, session60447/chunk e6e25f.
First failure line29: expected LD/LHU at inherited constant PC shift.
No firmware was run, and no compilation or original/packed Host is repeated.

Actual m2 SoC initializer is Spike PC minus12, but output compare sites
are Spike PC minus8: SoC first output LD800005c8 vs Spike800005d0.
The expected_dictionary address-materialization sequence accounts for the
four-byte difference. Original inspector remains intact; inspect_compiled02.py
checks actual initializer and read ranges separately, including exact rs1,
offset, instruction widths, all33 reads, tail address, and stack bound.

This is tooling scope only, not a reference or DUT failure.
