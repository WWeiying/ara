# Actual linked candidate: cost HOLD

This report completes inspection of the one existing `software01` candidate.
No second compiler invocation, Spike reference, VCS, or RTL edit was performed.
`RESULT.json` and `execution_receipt.json` record the read-only linked-code
inspection, actual tool wait exit 0, and unchanged software input pins.
Inspector success is not cost admission or independent reviewer acceptance.

## Actual products

- SoC ELF: `../software01/soc/program.elf`, SHA256
  `81d32bc48391b57c5dd0ea53d8ca10dd85040a6fd1ff89d092bb4f3cbad752dd`.
- Spike ELF: `../software01/spike/program.elf`, SHA256
  `3c37c694c180fada587e034c2a513f6c0ed146fd2af658086d73d13c5e015f6c`.
- Original Host/GCC wrapper: actual wait 0, 31.998270575422794 seconds;
  all 41 expected Host outcomes matched, including intentional nonzero negatives.
  There were 26 complete-history Host runs, two deliberate UB trap runs, and
  13 setup/order/deletion negatives. Host helpers are emulations, not DUT RVV.
- `software01/proof.json`: SHA256
  `e1a81989b65c159ebfc1467e93606401894451471c897bc99855c9871a3ce1f8`.
- `software01/pins.json`: SHA256
  `ae027a8decac535668989fc2fa99f845ac0e228b656f10d919a326fe81f90a92`.
- Actual linked bytes match this shape's dictionary, IDs, original FP tables,
  and 458 helper instructions; no extra RVV. Both backends were checked using
  their own linked addresses, not a shared hardcoded PC map.
- Spike `.text` 9,028 B, `.rodata` 241,672 B, `.bss` 32,984 B.
  Main frame 320 B; conservative sum of all static frames 552 B;
  BSS-end to stack-top 764,632 B. Dictionary payload 127,104 B plus
  107,730 B IDs, 5,120 B FP expected table, and 64 B FP input table.

Scope remains all 5,985 calls / 35 ops / 3 seeds, 383,040 result words,
11,970 guard words, 5,985 returned-vstart checks, and all original history.
Output is 528 B / 66 words, including the ninth block's **16 valid bytes**.
The sentinel is uint64 `0x5b`, not byte replication.
The archival e64/m4 resume03 was board PASS; this work is an uncompleted
current-image full regression, not a newly identified RTL bug.

## Count convention

Numbers below are linked-instruction CFG counts, **not measured retirement**.
Compressed and full-width instructions each count once. Costs describe the
successful path; diagnostic fallback cost is not bounded here. Full fallback
is unchanged and its wrong-data/guard/vstart behavior was exercised on Host.
The eight-block loop and finite seed/mask paths were reconstructed from the
actual instructions. Source multiplicities are 5,985 calls, 2,205 mask groups
(735 per mode), and 1,890 FP calls (630 per seed).

| Mandatory repeated component | Instructions | Full-scope contribution |
| --- | ---: | ---: |
| Output sentinel LI + 66 SD | 67/call | 400,995 |
| Helper arguments, JALR and returned-vstart branch | 14/call | 83,790 |
| Original helper | 13/call | 77,805 |
| Comparator including entry bookkeeping and final mismatch branch | 366/call | 2,190,510 |
| Result/check/trial counters and end decision | 12/call | 71,820 |
| FP refresh paths seed0/1/2 | 143/142/143 | 269,640 |
| Mask paths mode0/1/2 | 280/155/63 | 366,030 |
| **Mandatory subtotal** | | **3,460,590** |

The output fill is already unrolled. There is **no output-init loop** to remove.
The 400,995 includes all 395,010 required output SDs and one LI per call.
The comparator performs all 395,010 actual and 395,010 expected volatile LDs.
Its OR-of-XOR tree includes all 66 words; it is not a cancellable checksum.

FP paths include eight table loads and 128 alternating `a[i], b[i]` SDs each
call: 241,920 required SDs plus 27,720 other path instructions. VL0, equal-value
repetitions, seed transitions and their original order are not removed.
Mask paths include all 35,280 zero SDs and 77,175 cumulative selected byte
updates. Each selected update retains actual LBU/ORI/SB, including repeat
updates to the same byte. Upper mask bytes remain cleared.

## Whole successful-path upper

`RESULT.json:terms` lists every instruction PC and multiplicity. Alternative
branches are deliberately union-counted; this is not an exact retired count.

| Remaining component | Conservative instructions |
| --- | ---: |
| Op gate, all calls | 17,955 |
| Later-trial start selection union | 52,920 |
| Mask-group trial setup/end | 35,280 |
| VL setup/end | 16,905 |
| Op setup/end | 3,045 |
| Seed setup/end | 102 |
| RNG including union of overrides | 6,720 |
| Main prologue + capacity | 48 |
| Startup BSS clearing | 16,493 |
| Success printing/startup/exit allowance | 20,000 |
| **Total including mandatory subtotal** | **3,630,058** |

The 20,000 allowance covers the bounded success text (<256 bytes), at most six
20-digit integer conversions, startup outside BSS, and exit. It excludes
post-completion parking and failing diagnostics. It is a conservative budget
term, not a measurement. Averroes is to independently check these same terms.

The earlier **3,066,840** is only `472 * 5985 + 241920`: it omitted mask costs,
FP loads/control, outer control, startup and exit. Therefore saving 66,841
alone does **not** establish a full-program upper below 3M. The full current
upper needs at least **630,058** removed; admission remains HOLD.

## Dominant loop and single proposal boundary

Spike comparator loop `0x80000a66..0x80000b04` has 42 instructions, eight
iterations per call. At `af2/af6/afa/afe/b00`, output-pointer increment,
loop-end AUIPC/ADDI, ID-pointer increment and branch account for five
loop-only instructions per block: **239,400** over the full program.
Dictionary-base AUIPC/ADDI is also repeated eight times and again for the
tail; the tail repeats five row-address instructions at `b04..b14`.
The sole source-static proposal in `../static_unroll01/PROPOSAL.md` targets
these costs. It does not change the comparator algorithm, initializer,
mask/FP events, original helper, or fallback. Its identified savings still
do not establish the 3M upper, so no new compile/reference is justified yet.

## Bound evidence

- `RESULT.json` SHA256
  `c55f35e5dbf1e5f16d06c16ab65137d138b061c28db6ff353e25851900229c83`.
- `inspect.py` SHA256
  `d14b44ba3ee28c509cb7e53807fdbe309900a8395d8b67382a85b0ffe3df5a34`.
- All original software pins were checked before and after inspection.
- This is the producing agent's static inspection, pending independent review.
- No reference/DUT acceptance, new RTL finding, or future GCC saving is claimed.
