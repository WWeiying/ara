# Original MIN Source Singles

Software/Spike preparation only. No DUT, RTL build, image build or full-parent
acceptance. Fresh call1292/call1232 select original scenario1, length index3,
VL3, frm0, op1 MIN, sticky0; bank1 fixture646/616. Active mask0x24 selects
element2; all-off mask0 preserves seed. Input/seed quiet NaN is7fc12345.

Local successors reuse the sealed MAX preparation/checker structure, without
editing it. The helper selector is explicitly op1/14881c57; both unused op0
and op2 windows are forbidden. All21 helper encodings match the original
Linux ELF. The independent MIN oracle tests numeric order and signed zero,
not just the common quiet-NaN result. Unknown GPR state is not assumed zero.

Original scenario input/seed/mask/fixture traversal and full144B output,
128B vector writeback, guards, tail, fflags/vstart/frm restoration are retained.
Absent unchanged fflags deltas require the actual explicit preceding clear,
continuous known CSR state and returned flag read; fcsr alias conflicts and
unknown deltas reject. No default-zero substitution.

Each reference runs once, sequentially, with3M step/120s/256MiB raw bounds
after compiled static admission and Host gates. Actual Popen.wait numeric
outcome is persisted before log closure, metadata or checking. First failure
stops the batch without retry. Raw witnesses are captured during the sole
full extraction; mutations are decoded and checked without another full scan.
READY remains pending independent/main review; it is not DUT or parent closure.
