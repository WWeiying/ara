# Software02 actual linked inspection

Status: producing-agent Host/linked-symbolic/cost checks complete; independent
artifact review pending at report creation. No Spike reference, DUT, RTL edit,
or second software candidate compile was executed.

## Durable outcomes and identity

- `../software02/execution_receipt.json`: actual child wait0, no timeout,
  39.01125316694379s, PID3365121. All41 previous expected Host outcomes match,
  including intentional nonzero negatives. Original-versus-packed diagnostic
  transcripts match for all13 non-UB mutation variants.
- `execution_receipt.json`: actual static-inspection wait0, no timeout,
  1.0180219081230462s, PID3366640. This is not firmware execution time.
- SoC ELF SHA256:
  `7ad99ec2e99b1eab9183e82934f09f29b3322a9c82093935dea3771f6d7d1620`.
- Spike ELF SHA256:
  `42e53dc666391e88db7c2d436f7972cda362b575ca9e26806110841fecce51ae`.
- `RESULT.json` SHA256:
  `95430da11698b00be8f080a0624f70a36576399549214cfb436345b04790805c`.
- `inspect.py` SHA256:
  `5411fd5f2155d5b79ee735910a458fda0c6a3c8a711d7f21a9e030fd7c667850`.
- `../software02/proof.json` SHA256:
  `412e63afa9d3d20efc443ba586d912fef67ebb8c61d4f159c88b61a2daf72796`.
- `../software02/pins.json` SHA256:
  `4d6830229483e372e41f4ac3151e6ad45fb0e0be1ca2c16d7ee2e60781600fcd`.
  All416 input/artifact pins unchanged before and after linked inspection.

Only the approved comparator changed in firmware source. Case C, original C,
dictionary, mask/FP headers, original operations header and helper assembly
are byte-identical to software01. The approved header is integrated with
only its function name mapped to the existing callsite, plus the unchanged
output initializer. Its original static-proposal comment is retained as
source provenance; the software02 derivative was actually compiled.

## Host scope, explicitly not RV64 asm execution

All5,985 source calls / three seeds /35ops are preserved, with383,040 result
words,11,970 guards,5,985 returned-vstart checks, and26 full-history Host runs.
The prior41 outcomes remain:28 original/packed mutation runs (including two
intentional UB traps) and13 setup/order/freshness deletion failures.

New observation callbacks bind actual and expected addresses, values and
per-call read counts. Packed full-history runs require395,010 actual reads
and395,010 expected dictionary reads. The prior setup13 duplicated final
read still rejects instead of being hidden by identical tail values.

Each non-UB Host invocation also executes1,072 comparator probes before the
full source: two original dictionary rows, every528 byte position plus
all-equal, first/middle/last high-bit differences, result63, two identical
differences, mismatch followed by matches, and both guards. Every probe
requires132 alternating actual/expected observations, including after the
first mismatch. These are source-C tests, not an RV64 asm execution claim.
The original guard-page, dirty128B mask, unsigned/signed corner, exact
fallback/error-count and FP equal-write/order negatives are retained.

## Actual RV64 proof separate from Host

Each disassembled instruction is checked against its own ELF file bytes;
SoC and Spike use independent symbols/addresses. Linked dictionary/IDs and
FP tables match their original shape-specific binary inputs. Original458
helper instructions match archive windows; no extra RVV. CSR/system, fence,
and scalar-FP instruction multisets match the previous backend binary.

The symbolic comparator proves an arbitrary ordinal via row address
`ids + 18*ordinal`, all nine LHU/shift/address paths, actual offsets0..520,
and expected block offsets0..56 (last block only0/8). Each of66 BEQ compares
the tagged actual/expected pair for the same word, after both real LDs.
Each unequal path is exactly `LI a5,1`; equal skips only that instruction.
Both paths rejoin immediately before subsequent reads. All four local
transitions (incoming flag0/1, equal/unequal) are recorded at every site.
Induction retains the union of earlier mismatch conditions until the final
BNEZ; no intermediate clear, data-dependent early exit, or skipped tail.

Ten short symbolic corruptions across the two linked backends reject:
LI0 instead ofLI1, omitted final expected load, midstream flag reset,
wrong tail expected offset, and early branch exit. No firmware is executed.

Comparator has no stack spill/reload, call, CSR or fence. The final conditional
branch directly consumes the sticky register; there is no extra boolean
normalization sequence. The original fallback is reached only after all66
word pairs, and source-C diagnostics remain byte-identical in tested runs.

## Actual compiled cost

All figures are linked-instruction CFG counts, not measured retired counts.
Success path only; the original failure diagnostics are not time-bounded by
this success upper. Both compressed and full-width instructions count once.

| Component | Spike | SoC |
| --- | ---: | ---: |
| Comparator all-equal instructions/call |237|238|
| Full repeated call core, including13 original helper instructions |344|346|
| Core across5,985 calls |2,058,840|2,070,810|
| FP path seed0/1/2 instructions/call |143/142/143|143/142/143|
| Mask path mode0/1/2 instructions/group |280/155/63|284/159/67|
| Mandatory subtotal |2,694,510|2,715,300|

Spike call core is67 initializer instructions (LI+66SD),14 argument/call/
vstart-gate instructions,237 comparator,13 counter/trial instructions and
13 helper instructions. Compared with software01, comparator366->237 saves
129/call, but the post-comparator checks counter now reloads once:12->13.
Net core saving128/call is precisely
**128 * 5,985 = 766,080** instructions. Outer seed setup adds three total,
so the whole-upper reduction is**766,077**. All rematerialization and
counter reloads in the new binary are counted, not assumed absent.

The full Spike upper retains the source-qualified outer unions:

| Remaining component | Instructions |
| --- | ---: |
| All-trial op gate |17,955|
| Later-trial selection union |52,920|
| Mask-group setup/end union |35,280|
| VL setup/end union |16,905|
| Op setup/end union |3,045|
| Seed setup/end union |105|
| RNG/overrides union |6,720|
| Main prologue + capacity |48|
| Actual BSS loop |16,493|
| Unchanged bounded success-runtime allowance |20,000|
| **Whole upper** |**2,863,981**|

Headroom is**136,019** below3M. The whole upper is for the actual Spike
candidate; the SoC table reports its independently checked core and finite
paths, not an invented identical full cost or a wall-time guarantee.

Main frame remains320B in both. Conservative sum of static frames is552B
Spike/504B SoC. Stack gaps are764,056B/772,576B. Spike text9,616B is+588B;
rodata241,672B and BSS32,984B remain unchanged. No1MiB/64KiB limit was relaxed.
All241,920 FP stores,35,280 mask clear stores and77,175 selected updates remain.

## Preserved failed inspector

`../compiled_audit02/` remains with actual wait1 and its original traceback.
It selected the SoC comparator start at the symbol-bearing ADDI but omitted
the preceding AUIPC establishing a5, causing `KeyError: 'a5'` before symbolic
analysis. Audit03 adds that preceding instruction only when it is the actual
same-destination AUIPC. This also counts its cost. No predicate, numerical
check or branch condition was relaxed; no source/ELF/Host rerun occurred.

Software01 COST_HOLD remains intact. Software02 now has producing-agent
Host/linked-proof/static-cost success, not reference or hardware acceptance.
