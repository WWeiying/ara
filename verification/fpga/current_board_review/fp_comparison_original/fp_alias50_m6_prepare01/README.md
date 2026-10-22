# Original FP Alias First50: Software Ready

**READY for independent review, not DUT acceptance or launch authorization.**
This is the named current-M6 first-data-failure regression for original
`rvv_fp_compare_unmasked_alias_v8_e16_m8`, preserving all49 predecessors.
It does not replace the held682 prefix, full17920-call parent, or Linux/board
history. The historical diagnostic50 PASS is not used as current-M6 evidence.
No RTL edit, image build, VCS launch, or change to old prepared inputs occurred.

## Entry Points

- [READY.json](READY.json): machine-readable identities and reference counts.
- [SoC manifest](prepared01/soc/programs.json): one ELF for the mature integration runner.
- [Source/provenance](prepared01/prepared/provenance.json),
  [prefix diff](prepared01/prepared/alias_v8_e16m8_prefix50/prefix.diff),
  [runtime diff](prepared01/prepared/alias_v8_e16m8_prefix50/wrapper.diff),
  [ordered call ledger](prepared01/prepared/alias_v8_e16m8_prefix50/call_sequence.json).
- [Host checks](prepared01/host.json), [Spike result](prepared01/reference.json),
  [actual per-call checkpoints](prepared01/reference_calls.json),
  [PC/encoding map](prepared01/address_map.json).
- [Input pins](prepared01/input_pins.json), [artifact pins](prepared01/artifact_pins.json).

READY SHA256: `feae4a0dc86ea2e5222655469f574634eaae03741d777bb015f71af6644ee004`.
SoC manifest SHA256:
`272107a89c43a6a7797df6638c85c7f99ce4474f2708bc87ce72c8b4f72c7cc6`.

## Source And Call Number

The recovered original C SHA is
`3652ca2d4f3f7b63995234bf624514dfb318db9cd781aeee0a7533d6c564491c`.
The existing full Linux rebuild and original archived ELF were rehashed equal:
`266467e6d61dc7334a83e62ce6ee8d2d0cfac5050811be026329c46eb3816754`.
This reuses the established byte-identical full-parent rebuild; no new Linux
rebuild or historical diagnostic-source substitution was needed.
The parent path is recorded verbatim in the provenance record.

Only two lines are added to the original C: stop when `++cases` reaches50,
after all original data/CSR/flags/guard checks, and the summary label.
The minimal Linux-to-SoC adaptation is exactly the mature682 adapter: source
matches its port after replacing the entry name and682 stop with50.
Startup/runtime/linker files and assembly are copied byte-identically from
the proved prepared02 sources. No diagnostic printing or software hints were
added. Original failure reporting remains intact; it was not removed to
reduce cost. Input-generation functions, initialization and oracle are unchanged.

The independently enumerated50-entry ledger equals the old682 ledger's first50:

| Calls, one-based | Original sequence |
| --- | --- |
| 1..48 | seed0/op0, VL0/1/2/3/256/511; each four mask modes and sticky0/1 |
| 49 | seed0/op0, VL512, mask0, sticky0, start0 |
| 50 | seed0/op0, VL512, mask0, sticky1, start0 |

Call50 matches the actual original board detail with expected/actual flags17
and errors64, not an inferred off-by-one boundary. The pinned source report is
`rvv_compare_uncovered01/original_board_report.json`, SHA256
`7ed11ee7257c8571d8d5d4bf87780231d82fd5373173343598d21d47ed5aa00f`.
The original aggregate64 errors does not identify exact wrong bit positions.

All ten assembled helper byte sequences occur uniquely and exactly in the
original Linux ELF. Only op0 is selected by this prefix:16 instructions,
target `vmfeq.vv v8,v8,v16`, PC `0x80000508`, encoding `0x62881457` in both
new backends. Capacity512, e16/m8, unmasked and source-alias-v8 are unchanged.
Other vv helpers have16 instructions; vf helpers21. This is not a13-instruction
gather helper. The function remains loaded with full source groups before
each call; no prior vector operation or scalar state update is skipped.

## Actual Software Validation

Host uses the existing independent integer FP16 emulator/classifier, checking
all1536 archived fixture entries against the original table. Two positive
executions pass: ordinary output and permitted all-one tail alternatives.
Eight mutations return1 with original FAIL: call50 bit0, bit511, NV, returned
vstart, left/right guards, first-call VL0 preservation, and predecessor49 bit11.
Five marker negatives reject contradictory PASS+DETAIL/FAIL/trap and missing
runtime completion. This is software oracle testing, not hardware validation.

One Spike execution used `rv64gcv_zvfh_zvl1024b`, `-m2`, timeout120s, the same
compiled source/assembly with the established HTIF runtime define. Original
firmware reports exactly `RVV_FP_COMPARE_PASS sew=16 cases=50 errors=0`, the
one case PASS and BOARD_REPLAY_PASS; saved firmware exit is0. The subprocess
helper completed successfully. No Spike rerun was used.

Read-only debugger checkpoints, with no added firmware instructions, independently
check each call's actual PC/opcode, VL/vtype/vstart/fflags and a0..a7 setup;
both complete512-element input arrays,128 predicate bytes, full stored mask,
guards, and returned status. The checker admits the original tail alternatives,
not a fixed preferred tail. These are50 explicit helper checkpoints, not a
claim to have independently classified every retired PC in a full trace.

| Actual reference check | Count/result |
| --- | --- |
| Complete calls / preserved predecessors | 50 / 49 |
| Result bits / original guard checks | 25600 / 100 |
| Returned-vstart / exact flags checks | 50 / 50 |
| Input FP16 values / predicate bytes | 51200 / 6400 |
| Last output | All64 result bytes `01`, flags17, vstart0, both guards91 |
| Start / replay_exit minstret | 5 / 1579534 |
| Retired interval | 1579529 instructions |
| Spike ELF SHA256 | `65e729caedfd94c64f8131e78ef9a2f0d4103fc9918eac75c2fb2f1e00437d49` |
| SoC ELF SHA256 | `4496c2b3644420634d48c0552b62a5126344271ea62fd2baac3c93205cf27983` |
| Original raw reference SHA256 | `544bbd4aac4dfc4e30145a54811fa03c480d2c9a4b5ffb62e68ae7c980e86d79` |

The initial outer preparation returned1 because its offline Python mask-byte
constructor was wrong, after successful Host/build/Spike. It is retained as
[ATTEMPT01.md](ATTEMPT01.md) and `prepare_attempt01.py`, SHA256
`d358ebb2796013f1acad0ff3878f229c36fe650ae9987ea91855268da11ba556`.
The corrected offline-only finalization returned0, consuming the same raw log
and unchanged ELFs. No software oracle was changed. Spike elapsed wall time
was not saved before that parser failure and remains null, not fabricated.

Final read-only rehash verified33 input pins and88 artifact pins. The regenerated
input ledger's unchanged claim covers the offline finalization/recheck; it is
not an invented persisted pre/post-run ledger from the failed first preparation.
Original source/ELF/runtime identities were also checked against their sealed
predecessor records. Source/provenance SHA256:
`9feb97224ccfca6cd45324ae26f4f60a2ed8916808099da534ea0e517dd7b8d3`.

## Cost And Future Admission

At the measured M4 authentic130-prefix rates696.46..702.00 retired/s, the
new actual Spike count projects2250..2268s (37.5..37.8min). At a hypothetical
slow273/s it projects5786s (96.4min); that is a sensitivity bound, not measured
FP50 performance. Neither assumes Spike instructions equal RTL cycles.

`budget.json` preserves the initial5400s proposed case ceiling, which would
not cover that slow sensitivity case. Parent review may choose a fixed7200s
case budget with7800s outer teardown/check allowance, both below three hours;
this is only a proposal, not automatic escalation or execution authorization.
The estimate supports a bounded M6 first50 run, not a runtime guarantee.

The prospective image is the existing frozen M6 ledger SHA256
`a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0`.
No replay driver/service was launched or added. Parent admission must still
bind actual image/private ELF, exact50 calls/full oracle, current resource
capacity, strict COMPLETE/child exit0, no abort/retry, and raw DETAIL/FAIL/trap
veto regardless of any PASS text. The supplied one-program manifest is ready
for the mature integration runner; future trace validation must retain the
explicit FP16-capable ISA where required.

The remaining632 calls through682, later excess-NV cases, full parent and Linux
history are explicitly outside this regression. The682 HOLD is unchanged.
