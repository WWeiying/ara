# e16 mf4 reference instruction-budget review

Status: independent static review only. No Spike, host test, compilation, DUT,
or live-job query performed. No prepared/sealed input changed.

## Decision

The reported **1,612,800 mask-loop instructions is correct** for the existing
compiled Spike ELF. A single explicitly approved **3,000,000-step / 256 MiB /
120-second** reference attempt is reasonable without changing the ELF, source,
oracle, or DUT budget. The conservative finite-path instruction envelope below
is **2.2M**, not a measured retirement count or a reference PASS. Retain all
completion/error/CSR/full-output checks; a bound hit remains NOT_COMPLETED with
no automatic second increase.

## Exact mask cost

Input directory: `original_e16_mf4_prepare01/`, adjacent to this report.
`prepared/case.c` retains 8 scenarios, 7 lengths, 4 mask modes, 5 rounding
modes, 3 operations, and 2 sticky choices. Crucially, the 64-byte mask fill is
BEFORE the sticky loop and the single-case selector at line 40. Thus even
rejected cases, including those after the selected target, still fill the mask:

- 8 * 7 * 4 * 5 * 3 = 3,360 fills; 840 fills per mask mode.
- `spike/program.dis`, PC `0x8000051c..0x80000534`: mode 3 executes
  `li, beq, add, sb, addi, bne` (6 instructions/byte).
- Modes 0/1/2 also execute the `ld` and `lbu` at `0x80000524/526`
  (8 instructions/byte). Limit 64 is set at `0x80000512`.
- **840 * 64 * (6 + 8 + 8 + 8) = 1,612,800** instructions, excluding
  fill setup, fixture lookup, selector, and outer-loop control.

The ELF's actual objdump agrees with the saved disassembly for this loop.
This is scalar retirement cost, not vector element count or simulated cycles.
The original 1M cap cannot reach normal completion, even if FP behavior is correct.

## Remaining finite-path envelope

| Category | Instruction allowance | Compiled basis |
| --- | ---: | --- |
| Mask byte-loop bodies | 1,612,800 exact | Above |
| Fixture loads, mask setup, both sticky selectors, nested-loop transitions | 336,000 | Charge 100 per each of 3,360 fills; paths at `0x800004ce..51a`, `538..54e`, `684..6ba` fit within this charge, excluding separately counted target and scenario initialization |
| Seed initialization | 122,880 | 512 seed elements; each invokes a 32-byte memcpy at `0x8000042a`. Memcpy costs 7*32+3=227 instructions, callsite loop 12; exact combined body 512*(227+12)=122,368 |
| Input initialization | 8,192 | 8*16 elements, allowance 64 per element; bounded switch/table paths at `0x8000039a..400`, `46a..4b2` |
| Startup/BSS | 5,000 | BSS `0x8001afc0..0x8001d540`: 1,200 eight-byte iterations, 4 instructions each, plus startup |
| One selected helper, output initialization, full output/flags/vstart oracle | 6,000 | 21-instruction op_0; 144-byte fill and complete 144-byte comparison retained; no other selected helper calls |
| Text/number formatting, optional single error detail, summary and return/HTIF | 10,000 | Bounded strings/numbers; no per-byte error printing or software FP fixture computation |

Subtotal 2,100,872; round upward to **2,200,000** for remaining scalar setup
and accounting slack. This covers the post-target outer loops, not merely the
first target result. Fixtures are static data; there is no runtime SoftFloat
generation. The bound assumes normal instruction execution through the existing
finite control flow, not an illegal-instruction trap/park or corrupted state.
Completion means the existing successful HTIF/return checks, not counting the
post-exit park loop as useful execution.

The 3M step ceiling leaves at least 800k instructions above this envelope.
Wall time and log size are not proven by instruction counting: 256 MiB/120s
remain independent hard limits. A rough 70-100 trace bytes per scalar instruction
would put 2.2M instructions at 147-210 MiB, but this is a format-dependent estimate,
not a file-size guarantee. Preserve partial evidence and reject incomplete output.
Use the established `rv64gcv_zvfh_zvl1024b` Spike profile; missing Zvfh would
invalidate this normal-path estimate by trapping on the e16 reduction.

## Reviewed identity (SHA-256)

- `spike/program.elf`: `afa05463645a429d2467b226fda805f7c8a655189743339555d99adb2b6be1ba`
- `spike/program.dis`: `b064bcb4c10b5ca7601af14d3d892cfc471816b6e6995590103091b4e4b19840`
- `prepared/case.c`: `fb1f0a462fb1a3ec2911f2867bb2587ed68824228d5e76626773adc9e4fb8626`
- `prepared/operations.S`: `48a893837032d5e5affa5b5b649f935341e9800b3661cf38af2393d06505a9bf`
- `sourceproof.json`: `f6efe2b2b360e96d4caa69fef05764bf205040f6c7347033e01cbd19562185af`
- `soc/program.elf`: `eed20f08a98ac66766a66810b6f5f8fc829d0603477d37b3d59d48c32669f162`

The counted binary is the Spike ELF, not the distinct SoC ELF. The preparation
script still records the historical 1M/128MiB budget; any approved new budget
must be recorded separately rather than editing this preparation evidence.
