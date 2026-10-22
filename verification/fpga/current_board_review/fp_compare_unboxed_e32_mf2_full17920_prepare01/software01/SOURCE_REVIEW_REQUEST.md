# Single FP32 Source Candidate

Static admission is `../static_review01/review.json`. This directory contains
one generator, not a generated/compiled/reference/DUT result. No original
Linux rebuild is proposed. `generate.py` executes only after exact source
review, once into exclusive `generated01`; partial outputs are never reused.

## Narrow Reuse

The pinned e16 generator is imported without its main. Only its SEW-independent
source port, CAP16 allowed-set function and ELF byte reader are used. Neither
its FP16 classifier nor its e16 helper locator/model/generator runs. Original
FP32 fixtures and `.S` are copied byte-for-byte. Source substitutions change
the port's compile guard to SEW32 and its entry name. The scalar header changes
only `fresh_inputs`: four additional A/B LD-SD pairs at 32/40/48/56 bytes.
All casts, packed error counting, combined guards, details20/21, output LWU,
16 output SD plus final SH, and all 16 mask SD remain the established logic.

FP32 values are unsigned integers; each ROM word is `lo | (hi << 32)` in
Python, emitted as uint64 constants. C never shifts a 32-bit value by 32.
Each uint32 bank retains its complete 4096-byte backing. All 64 input bytes
are fresh per call; bytes64..4095 remain BSS. Scalar inline-asm stores use
memory clobbers and aligned bases, not type-punning loads. The output wide
read is exactly four bytes at aligned `output`, never at `output+1`.

The source loops and all 17920 invocations are unchanged. Value deduplication
affects immutable input periods only, not calls or fresh writes. 2240 records
retain both admissible outcomes where the source allows agnostic tails.
Generation performs representation checks, explicitly NOT independent numeric
acceptance. Host must execute the original C oracle/fixture interpretation,
compare all bits/flags and malformed outcomes, and preserve its actual first20
diagnostic behavior before either compiler is allowed.

## Source Review Receipt Contract

Please publish a new `../source_review01/review.json` with
`status: SOURCE_GENERATOR_NO_BLOCKER` and `generator_sha256` binding this
exact generator only if the source review passes. Additional evidence fields
are welcome. The generator verifies both before making any output directory.

Next stages retain parent limits: each Host child <=120s; fixed flags and one
SoC/Spike build each only after numerical acceptance; complete linked positive
CFG <=600s. Cost >=3,000,000 is HOLD. No reference or DUT authorization.
