# e64/m4 Software02 Actual Artifact Review

Verdict: **NO_BLOCKER_HOST_COMPILE_CFG_ONLY**. The actual linked successful-path
upper is2863981, below3M by136019. This is not measured firmware retirement,
reference PASS, or DUT admission. No compiler, Host suite, Spike or VCS was
run by this review. software01 and its COST_HOLD remain unchanged.

## Receipts and Source Boundary

Software02 wrapper: PID3365121, actual numeric rc0,39.01125316694379s,
timed_out=false. All41 original Host outcomes and their log hashes match;
13 original/packed full-history transcript pairs match byte for byte.
The new1072 C-arm probes per completed invocation observe intended132
comparator reads, including byte/guard/two-error cases. They do NOT prove
RV64 inline assembly; instrumentation itself also reads values for checking.

Independent rehash:416 software pins and241 source-entry pins all match.
case.c,original_case.c,dictionary,mask,FP-period,Host fixture and original
S/header remain byte-identical to software01. Only the comparator changes in
firmware. The full original scalar fallback remains unchanged, after the
complete comparator. Original5985/35ops/history,383040 results,11970 guards,
1890 FP calls and no explicit original fflags oracle remain the scope.

Producer audit02 is preserved as actual rc1/0.36708344984799623s, not PASS.
Its KeyError(a5) arose from starting at SoC's checks ADDI without the preceding
AUIPC. audit03 changes only that boundary inclusion and records actual rc0,
1.0180219081230462s. The same ELFs/Host outputs were used, not rebuilt.

## Independent Linked Assembly Proof

This review separately read ELF segment bytes and disassembly, not merely
the producer's C-arm result or transition arrays. A read-only symbolic walk
tracked a generic ordinal, nine symbolic dictionary IDs, addresses, loaded
word identities and the sticky flag. Actual instruction bytes matched ELF;
BEQ opcode/register/immediate fields and compressed LI encodings were checked.

| Backend | Comparator range (end exclusive) | Equal-path instructions | First / last BEQ |
| --- | --- | ---: | --- |
| Spike | 80000a44..80000d8a | 237 | 80000a72 / 80000d80 |
| SoC | 80000a4c..80000d96 | 238 | 80000a7e / 80000d8c |

Each backend has exactly66 comparisons and264 local state transitions:

| Incoming flag | Equal | Unequal |
| --- | ---: | ---: |
| 0 | 0 | 1 |
| 1 | 1 | 1 |

At every site BEQ consumes the matching actual/expected word registers;
its encoded target skips only C.LI a5,1 (0x4785). Both paths immediately
rejoin. The single C.LI a5,0 (0x4781) occurs before the first comparison;
no address arithmetic, load or later update clears/overwrites that flag.
Induction over these66 joins proves arbitrary mismatch patterns, not only
all-equal or selected numeric samples. Later matches cannot erase a failure,
and two equal differences cannot cancel.

The walk derives row address block_ids+18*ordinal, ordered ID offsets0..16,
and each expected address dictionary+64*ID[word/8]+8*(word%8). It verifies
exactly66 actual LD and66 expected LD, ordered actual then expected, each
natural8B access. Actual offsets0..520 cover guard/data/guard; the final
expected offsets0/8 cover only16 valid bytes. No mismatch branch can skip
later loads. The only flag-dependent decision is after all132 loads.
No stores/spills/calls/CSR/RVV occur in the comparator. The two incoming
comparison registers are consumed before the possible flag write, validating
this linked realization of the reviewed +r constraints.

Independent read-only proof completed with actual command exit0, tool chunk
b2bed3. This is static symbolic analysis of linked scalar instructions, not
execution of firmware or a new Host equivalence run.

## Full Artifacts and Cost

All458 helper instructions independently match unique contiguous archived
ELF windows in both backends; zero extra RVV. Linked dictionary,IDs,FP inputs
and640-entry FP expected table match the previously reviewed binary sources.
The original ELF is stripped: an initial independent mnemonic parser crossed
lines after no-operand instructions and caused a comparison assertion. The
reader was corrected to horizontal whitespace, recovering all1145 archived
instructions. Corrected static check exited0 (chunk f60961); no producer
file, expected data, compiler or execution was changed.

The output initializer still has LI91 and66 SD at offsets0..520. FP paths
retain eight table LD and128 ordered alternating a/b SD per call, including
all restart paths:241920 FP stores. Mask paths retain16 clear SD then
64/32/9 cumulative LBU/ORI/SB:35280 clear stores and77175 selected stores.
Recorded finite paths were checked against linked instruction adjacency,
branches and counts; the producer's value/order interpreter was reviewed,
not executed again. Main frame remains320B. Static-frame sums are552B Spike,
504B SoC; stack gaps764056B/772576B remain above64KiB.

Spike actual core344/call consists of67 initializer +14 helper setup/return
test +13 original helper +237 comparator +13 counter/end instructions.
This includes the extra counter load introduced by the changed allocation;
it is not just the old cost minus presumed compiler savings.

| Successful-path component | Instructions |
| --- | ---: |
| Core344*5985 | 2058840 |
| FP refresh paths | 269640 |
| Mask paths | 366030 |
| Mandatory subtotal | **2694510** |
| Outer control/RNG/prologue/capacity union | 132978 |
| BSS clear | 16493 |
| Success-runtime allowance | 20000 |
| Full conservative upper | **2863981** |

All linked comparator address setup/rematerialization and final branch are
counted; no comparator spill is omitted. Outer PCs/multiplicities and BSS
arithmetic were independently reconciled. The seed-setup union includes its
new3 total instructions. The runtime allowance remains unchanged. SoC is
separate:core346/call,mandatory2715300,not a Spike cost or measured DUT time.
Failure paths may execute extra LI and original diagnostics and are not
bounded by the all-equal successful-path upper. Post-completion parking is
excluded. There is no current reference/DUT result to claim.

## Identities

- SoC ELF:7ad99ec2e99b1eab9183e82934f09f29b3322a9c82093935dea3771f6d7d1620
- Spike ELF:42e53dc666391e88db7c2d436f7972cda362b575ca9e26806110841fecce51ae
- software02/proof.json:412e63afa9d3d20efc443ba586d912fef67ebb8c61d4f159c88b61a2daf72796
- software02/pins.json:4d6830229483e372e41f4ac3151e6ad45fb0e0be1ca2c16d7ee2e60781600fcd
- software02/execution_receipt.json:dd68d306a3e67ed78ff8be944325a1c0ad855bd4d719cc109b4bf9b712d5300d
- compiled_audit02/execution_receipt.json:0e5434629030578e24746111ad36a271e16c77af021ad9dcf6bf06b9fd8a482f
- compiled_audit03/execution_receipt.json:54178e8779f40f33df743b2e3eb9dae47cc29563a7de9ac1e7ba81d4a9e5d80a
- compiled_audit03/RESULT.json:95430da11698b00be8f080a0624f70a36576399549214cfb436345b04790805c
- software02/packed_output.h:56e53d4d64a8a3366757b76cafbdc917fea116795a83ebcb98e2e3ceef864679
