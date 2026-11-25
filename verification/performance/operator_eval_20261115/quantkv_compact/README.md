# QuantKV Compact Successor

Only quantkv_compact/ and operator_quantkv_compact_prepare_20261115_* outputs
are owned here. Existing extensions, ELFs, FNV logs and running tasks are untouched.
No simulator, probe, hardware build, production edit or task cancellation.

```sh
env -u LD_LIBRARY_PATH python3 -B verification/performance/operator_eval_20261115/quantkv_compact/prepare.py --kind q4_0 --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/operator_quantkv_compact_prepare_20261115_q4_02
```

Repeat for q8_0 in a fresh q8 output. The parent consumes manifest.json, with
run-source-pins.json sealing the build. Only two successor ELF cases are needed.

The diagnosis retains pinned old disassembly: FNV loops at 0x800018e8,
0x80001c2c and 0x80002024 are outside the old ROI markers 0x800019de/0x80001bfe.
The 19,551,101-cycle user sample shows byte/hash progress, not a compute stall.
Earlier printf PCs were a transient reverse-format stage; s7 is its stack byte
pointer. There is no evidence here establishing an integer/division/ABI defect.
Q4 has 763904 full fixture bytes; nine serial FNV passes project to 50.6M cycles
using the observed 795 cycles/108 bytes. This is not a new timing measurement.

The successor replaces FNV with pure integer RVV u8m8 strip-mined byte comparison
against a separate, immutable, complete expected copy. Expected bytes come from
the independently pinned original capture and must equal the entire ancestor ELF
fixture region, including inactive heads/KV, mask and gold. Every byte is compared
even after a mismatch; report checked count and first mismatch. Five full passes
are made: initial plus one per trial, not duplicated for printf and error checks.
The helper rejects nonzero entry VSTART without executing a vector instruction,
and verifies FCSR/VCSR/VSTART snapshots are unchanged. It writes none of those
CSRs and contains no FP/saturating operations or fence. VL/VTYPE may change
outside ROI; the exact original pre-ROI initialization remains unchanged.

Original arithmetic, ROI source, drains, ABBA order, real gold, 2e-5 tolerance,
cross-arm full-bit/flag equality, four QBS commands, 74/20/20/74 value decodes,
all1024 target numerical comparisons and all384 guard bytes are retained.
Only64 raw output values are printed. Whole-output numerical/repeat checks are
not replaced by hashes or the printed prefix. Existing printf library is reused.

Host checking audits the complete actual and expected bytes in disjoint ELF
regions against the real capture, shape/type/scale/tolerance constants, all byte
and numerical counts, raw prefix, native work, and commit-trace ROI/helper/CSR
snapshots. Parent image/protocol gates remain mandatory. SDK slice only, not
GGML production dispatch or whole-model performance.

```sh
python3 -B -m unittest discover -s verification/performance/operator_eval_20261115/quantkv_compact -p 'test_*.py' -v
```

Host mutation fixtures are tests, never performance evidence. Freeze all helper
files after release; subsequent changes need another successor.
