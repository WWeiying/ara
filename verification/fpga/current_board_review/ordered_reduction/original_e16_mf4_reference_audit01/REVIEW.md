# Independent e16/mf4 Reference Acceptance

## Decision

**ACCEPT the single source-faithful reference under its actual ISA**, with the
explicit profile deviation below. No blocking numerical, source, raw-completion,
or oracle discrepancy found. This is NOT exact-profile contract PASS, NOT a run
under the narrower profile, NOT DUT acceptance, and NOT closure of the original
full 6,720-call Linux program or the remaining ten original width/LMUL records.

Frozen input: `../original_e16_mf4_prepare01/READY.json`, SHA-256
`f858249f61dc7b9c4e3507f78bb483543d0439ef74942e838fc1251931a661de`.
The 107 READY pins plus READY itself were independently hashed before and after
the complete offline audit; all 108 matched. `result.json` records recomputed
counts and `audit_raw.py` is this audit's independent reader, not an import or
rerun of the executor's checker. Only existing files were parsed; no Host test,
Spike, compiler, DUT, or live simulation query was executed for this review.

## Source And Oracle

- Canonical source is campaign `ara_hw_campaign_20261007_01`,
  `rvv_verified_handoff03/rvv_small_redspecial02/rvv_small_fp_redspecial_e16_mf4`.
  Source files, archived scenario ELF and original ELF match their case hashes.
  Removing only the archived inner selector reproduces `fp_reduction_oracle.c`.
  The port's entire main body matches that scenario after Linux exit-to-return
  adaptation; initialization, surrounding loops, selector and oracle remain.
- All 6,720 header fixture pairs equal the archived JSON. The selected 1024-bit
  bank row 1545 (flattened 4905) is `7e00/NV16`; the 512-bit bank's same row is
  `7c00/0` and is not substituted. Earlier default-QEMU FP16 SIGILL evidence is
  not treated as an RTL result; canonical redspecial02 used Zfh and Zvfh.
- All three 21-instruction helper windows match the archived scenario ELF and
  both compiled port ELFs byte-for-byte. The actual run calls only op_0 once.
  Every firmware retirement encoding was checked against the pinned Spike ELF;
  every saved disassembly instruction also matches its ELF bytes.
- Existing Host13 evidence contains one positive and twelve rejected injected
  failures, with full-setup marker and correct pass/fail console polarity.
  Existing raw-checker15 contains one positive and fourteen rejected witness
  mutations covering NV/NaN/vstart/guard/tail/bank/type/seed/mask/CSR/store/HTIF/
  truncation/encoding. Their code and outputs were read, not reexecuted. They
  support oracle sensitivity, not additional architectural executions.

## Independent Raw Results

The entire 120,844,625-byte raw was parsed, not sampled. Its SHA-256 is
`4f0723a9a59985cf5d25177ee9b0ba74c7dc23eccf1001294d7f4f8a4b312bf5`.

| Check | Independent result |
| --- | --- |
| Total / firmware-to-HTIF / boot / post-exit park | 1,860,000 / 1,858,335 / 5 / 1,660 |
| Mask-body instructions | 1,612,800, matching the static calculation |
| Initialization writes: input / seed / mask / output | 128 / 512 / 215,040 / 144 |
| Fixture traversal | All 3,360 bank-1 rows, both fields: 6,720 loads, exact order/value |
| Call | scenario3/l4/mode3/rm0/op0/sticky0; cap16, VL8 |
| Input / seed / mask / old output | 16 alternating +Inf/-Inf halves / 64 +Inf halves / 64 bytes 0x24 / 144 bytes 0x5b |
| Vector setup VL/vtype | 64/8, 16/14, 8/14; final full-register store setup 64/8 |
| Actual helper | 21 consecutive original instructions; reduction PC 0x80000764 |
| Result and output footprint | half 0x7e00, 126 unchanged tail bytes, eight unchanged guard bytes on each side |
| Original scalar byte checks | All 144 original LBU comparisons in exact address order |
| Flags / vstart / restore | NV16 only / 0; returned status 16<<32; frm and fflags restored to saved zero |
| Normal completion | Exact original cases=1/errors=0 marker, board PASS, HTIF=1 at 0x8000007a; only empty park afterward |

Mask 0x24 activates indices 2 and 5 within VL8: +Inf then -Inf with +Inf
seed, explaining canonical NaN plus NV. No alternate min/max helper or trap
entry retires. Final frm/fflags/vstart remain zero. This run validates zero-saved
frm restoration, not restoration of arbitrary nonzero frm; sticky=1 and other
rounding modes are outside this single case.

## Actual ISA Deviation

Actual: **rv64gcv_zfh_zvfh_zvl1024b**.
Cost-review minimum / later admission file: **rv64gcv_zvfh_zvl1024b**.
These are not equal. CONFIG_DELTA retains this fact and explicitly says the
later parent admission file was not a pre-execution file gate. Neither this
review nor numerical acceptance retroactively supplies that gate.

Independent encoding classification finds **zero scalar FP instructions of any
width** in the compiled disassembly or all 1,860,000 actual records, including
RV64 compressed FP loads/stores. The helper uses vector half arithmetic and
integer CSR operations, not scalar-half operations. In the inspected Spike
source, `isa_parser.cc:118` adds EXT_ZFH for Zfh, while Zvfh already supplies
Zfhmin. `v_ext_macros.h:1447` gates SEW16 vector FP on EXT_ZVFH, and its reduction
macro at line 1630 selects `f16_add` through `insns/vfredosum_vs.h`; that path
does not test EXT_ZFH. Thus the extra scalar-half capability has no consumer
or identified semantic effect in this concrete positive execution. This is a
bounded code-and-trace inference, not a measured narrower-profile run or a
general equivalence guarantee. Accept only with this deviation retained.

Spike binary SHA-256: `c03c5a84f2313b2e0bb28be7aba496836b8d7b29e472c918457bca21f8abc7d2`.
Supporting local-source hashes (source inspection is not a fresh build proof):

- `disasm/isa_parser.cc`: `68f02b81e58d19f5a87388e7cfb2e91f5bf7446f015adf03b66ef3ebb9307303`
- `riscv/v_ext_macros.h`: `85120cf1bff1425251485545f738851aa28a38b4986ef33a006cfec69f1755f3`
- `riscv/insns/vfredosum_vs.h`: `b0889e0b868e4664a41ef82489b7fe1f369220ef503c958eb5b6b5a11b8a3672`

## Consumption And Boundary

Recorded single reference elapsed **4.375200 s**, raw **115.2464 MiB**, complete
firmware **1.858335M**: within the unchanged approved ceilings of 120 s,
256 MiB and 3M debug steps, and within the earlier 2.2M static envelope. rc=0 is
corroborated by actual HTIF success and full oracle, not accepted alone.
The debug script requested 3M; normal exit was reached earlier. Initial 1M was
recorded NOT_RUN, and no further attempt is requested. Offline independent
parsing and pre/post pin checks took 48.952 s, not a new reference execution.
These timings do not predict or authorize a DUT timeout adjustment.

Spike ELF: `afa05463645a429d2467b226fda805f7c8a655189743339555d99adb2b6be1ba`.
Distinct SoC ELF: `eed20f08a98ac66766a66810b6f5f8fc829d0603477d37b3d59d48c32669f162`.
The former was independently accepted here; the latter remains untested by
this audit. No production RTL or original evidence was changed.
