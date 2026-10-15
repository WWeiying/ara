# NF8 Selected Sv39 Reference: Measured Preparation

Status: **HOST_SPIKE_SELECTED4_PASS_NOT_DUT**. No VCS launch, no RTL changes,
no Linux execution, no NF7 status polling. Four separately selectable trial
ELFs are ready for parent image/budget review, not automatically scheduled.

## Results

| Original trial | Scalar comparisons | Retiring Spike commits | Checkpoints | Fault/retry access counts |
| --- | ---: | ---: | --- | --- |
| 19 | 3122 | 287851 | phase1, phase2 | 28, 40 |
| 17 | 3122 | 287862 | phase1, phase2 | 28, 40 |
| 67 | 3166 | 288945 | phase1, phase2 | 28, 40 |
| 31 | 2984 | 220774 | phase2 only | 0 |

All four software executions terminated successfully with zero firsterror,
zero unexpected traps, exact comparison count, one completed selected case,
all environment restoration checks, completion magic and tohost=1.
Total: **12394 comparisons / 1085432 retiring commits / seven checkpoints**.
Full memory/PTE arrays use mismatch-accumulating scans; comparison counts are
not a substitute for the full-array byte coverage.

Host C formulas matched 18948 independently generated Python rows.
The negative oracle rejected 65 distinct mutations and accepted six legal
partial-state examples (repeated against each ELF symbol layout).
Thirty-eight pinned inputs were unchanged after all execution and again at
the independent post-run audit. Per-case Spike plus trace-validation time was
12.115 / 12.092 / 12.319 / 9.213 seconds, excluding software build and host
negative checks. These times are not VCS runtime estimates.

## Actual Fault Evidence

Trials19/17 faulted with cause13; trial67 with cause15. All had
tval=0x40001000, saved VL8/vtype23/vstart3, fcsr117/vcsr5, and younger marker0.
Trace records independently confirm MXR/SUM/MPRV=0 and the denied second-page
PTE flags c9. The addressed SFENCE followed repair to flags c7; the unchanged
target PC retried at vstart3. Post-readback state was returned-vstart0, VL16,
vtype23, vstart0, fcsr117, vcsr5.

Spike committed 24 completed-prefix field accesses plus four accessible
fault-element fields before each page fault, then 40 accesses on retry.
**This observed four-field partial commit is not an oracle requirement.**
The oracle allows each accessible fault-segment store field independently
old or correctly stored; a third value is rejected. Load fault-segment state
is unconstrained as in the original prefix oracle. Any protected field tval
of element3 (offset4096/4100/4104/4108) is accepted; f4 is the measured Spike
outcome, not a required DUT implementation order.

Tuple31 issued its original alloff target with no memory access and no page
fault. Only the expected S-mode completion ecall occurred; denied PTE c9,
old destinations, whole-register sentinels and complete backing memory
remained unchanged. This is a reference observation, not proof about DUT MMU
request/AXI activity.

Trial19's saved/final v31[2]=37603 and trial67's prefix store poison
330 XOR 0x5b = 273 are included in the independently checked state. All eight
fields include cap16 words, original output guards0/129, full8192-byte memory
and gaps; physical fractional tails and v16/v23 guards add coverage beyond
the original manifest. No tail/prefix oracle was relaxed to obtain PASS.

## Artifacts And Binding

- Sources: `fixture.c`, `fixture.h`, `fixture.S`, `reference.py`.
- Exact archived assembly copy: `reference01/prepared/original.S`.
- Sources and original ELF binding: `reference01/source_provenance.json`.
- Input/tool/runtime hashes: `reference01/input_pins.json`.
- Aggregate result: `reference01/status.json`.
- Independent final trap/CSR extraction and per-ELF hashes:
  `reference01/postrun_audit.json`.
- Each `reference01/trial{19,17,67,31}/` holds `soc.elf`, `spike.elf`,
  disassembly, symbols, exact cases, Spike trace, checkpoints/actions/accesses
  in `status.json`, and `negative_oracle.json`.

| Trial | SoC target PC | SoC ELF SHA256 |
| --- | --- | --- |
| 19 | 0x80001566 | 40cee4a9a59850e09187c15f9db5be4f4e831a4d006bb0ab85c594fed8e09b4d |
| 17 | 0x80001566 | ef75b1db13ac62e47f35dadf274080170faea8ff87480c943364bf0d57a37aa9 |
| 67 | 0x800015f4 | 392a01bd5c6d07f8b416ce091bbb0cca5065ad3f7d0c2741c037f94127a6caed |
| 31 | 0x80001566 | a605432cd14730bc65a9114f80ebc22e2e429d30cf071b533ae35f6b34a01ce9 |

Spike PCs differ by eight bytes from SoC PCs due to backend-specific startup.
Any future CSV adapter must use the selected SoC symbol file, not the Spike
PCs. Load/store encodings remain exactly e9c56c07/e9c56c27 in both backends.

The source manifest/identity57 rebuilt-ELF ledger binds the archived original
Linux ELF hash c90e2ac2... and current C/generator; the target assembly is
byte-identical to the archived source. S-mode page-table/trap adaptation
does not exercise Linux signal ABI or replay the Linux ELF. These four
representative original tuples do not locate the original169/later128 error
difference and do not replace the full192 original scope.

No VCS runner or image acceptance is implied. Future execution requires
parent-selected frozen image and bounded per-trial budget; all prior sealed
inputs and ongoing jobs were left unchanged.
