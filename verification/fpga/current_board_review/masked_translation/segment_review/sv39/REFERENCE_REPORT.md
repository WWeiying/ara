# NF2 Reference Ready For Parent Review

`reference01/status.json`: **HOST_SPIKE_PASS_NOT_DUT** on the first build/run.
No fixture repair/retry iterations, RTL edits, VCS execution, or Linux execution.
No sealed extended8/helper/runtime files were modified. All pinned input hashes
were rechecked after reference completion.

## Measured Acceptance

| Item | Result |
| --- | --- |
| Host C versus independent Python expected rows | 34,816 matched |
| RISC-V GCC SoC / Spike ELF builds | Both PASS, warnings treated as errors |
| Real-Sv39 Spike cases | 4/4 PASS |
| Independently reconstructed memory checkpoints | 8/8 PASS, over 23 KB per checkpoint |
| Firmware checks | 4,133; case-local counts 756,758,756,758 |
| Negative checker mutations | 16/16 rejected |
| Deliberate legal partial-state checks | 2/2 accepted |
| Spike committed instructions | 1,189,205 |
| Spike plus trace validation elapsed | 45.86 seconds |
| ISA | rv64gcv_zfh_zvfh_zvl1024b |

Each case has exactly one load/store page fault, an unchanged-PC retry with
vstart5, and the expected terminal supervisor ecall. Target execution is
verified as S-mode. The younger marker occurs only after successful retry.

Observed target accesses (P=0x40001000; store values in field order):

| Case | Successful accesses before fault | Retry accesses |
| --- | --- | --- |
| b3 sparse load | element2: P-6, P-4 | element5: P+6, P+8 |
| b3 sparse store | P-6=127, P-4=156 | P+6=166, P+8=195 |
| b5 later-field load | element2: P-14, P-12; element5 field0: P-2 | element5: P-2, P |
| b5 later-field store | P-14=127, P-12=156; P-2=166 | P-2=166, P=195 |

Thus Spike actually exercises partial field0 completion for b5, not merely a
checker allowance. Retry accesses exclude completed element2. Full final
register/memory checks independently confirm prefix poison was not replayed.
Neither this access trace nor firmware PASS constitutes RTL acceptance.

## Deliverable Identities

All paths below are relative to this directory.

| Artifact | SHA256 |
| --- | --- |
| reference01/soc.elf | 2ddce29de6d035fb02616f7924235b03e8863a74dfad161c3b2a4219ced61a67 |
| reference01/spike.elf | 9b3621b2952cbd16509d5574bd1afdc7bbe48ba10d3df414d0794c3d8ac102eb |
| reference01/prepared/fixture.c | d124c676780349b2e152f3a981ce4d0d413b0f824b6a26ddd66c2a9e9aae6097 |
| reference01/prepared/fixture.S | c776abe7c78614fbc53a28437fe2bfb203d5d87a25804eba5c83a6696dc01b3e |
| reference01/prepared/fixture.h | 16f55840eba9e5fb0c3b04b39b64bb30bff4d106733fe1e7ae5e476b36b7d587 |
| reference01/status.json | e5bf33440d88134588f1ed2c2f2c8bb009ebb80a5893010deb9a59aac5c9f62a |

Use `reference01/input_pins.json`, `linux_provenance.json`, and
`prepared/provenance.json` for full source/ELF/tool/runtime identities.
Original full Linux ELF SHA256 remains
`3fb155679a00980cc07e34a858e7eea84c1c390e6af054f8f868ee03ba6c7054`;
it is not the adapter binary. The b3 load/store sources are archived failing
singles; b5 load/store are passing trials selected from full original-sequence
trace source. The adapter does not relabel all four as original failures.

SoC ELF sites, distinct from the Spike ELF addresses:

| Symbol | SoC address |
| --- | --- |
| mx_segment_load | 0x800010bc |
| mx_segment_store | 0x800010c4 |
| mx_checkpoint | 0x80000278 |
| mx_repair_sfence | 0x800006e6 |
| mx_trap_mret | 0x80001010 |
| mx_ecall | 0x80001168 |
| __bss_end | 0x8000a708 |

## Boundaries

Ready for parent reference review and subsequent separately authorized DUT
integration. No VCS runner or DUT acceptance has been added. Four cases are in
one bounded ELF; there is no 96-trial Linux loop, NF7/NF8 or indexed expansion.
PROT_NONE/Linux signal handling is represented by an invalid Sv39 PTE and
M-mode snapshot/retry, explicitly not Linux ABI equivalence.

Negative checker tests mutate synthetic expected-state fixtures, not production
RTL. They cover PC/vstart, inactive prefix, second-field final data/tail,
neighbors, output/page guards, PTEs, mask, partial store corruption, replayed
prefix and premature younger marker. The original fault-segment load snapshot
omissions and allowed b5 store field0 partial value remain localized to the
fault checkpoint; final data/guard/memory expectations are exact.
