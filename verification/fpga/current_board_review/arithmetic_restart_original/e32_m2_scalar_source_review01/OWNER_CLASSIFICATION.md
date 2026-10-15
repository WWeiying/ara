# e32/m2 Reference Scope And Future Owner Classification

2026-10-14: NO_BLOCKER in reference terminal metadata. See REFERENCE_TERMINAL.md, SHA256 `00d64beab506cfdb4abed168acf92e84b51b123ae55cc5e4d58bcc2acec5f222`, for the independently verified READY/result/actual numeric returncodes/EOF/246 pins. This addendum clarifies owner classification only; it is not a future M9 worker entry approval or an actual DUT owner result.

## Derived From This Exact Original Sequence

Input `full_e32_m2_block_prepare01/software01/sequence.json` SHA256 `076c752e9171a6f8ab2e9be4e385bcbf1a3228f3f5839cfd3fe479341f59f966`, and its own SoC proof/helper encoding. Actual op19 target instruction is `0x38813c57`, VSLIDEUP.VI with unsigned immediate 2. The counts below were independently derived by reading this sequence and decoding that target, not copied from another shape or the 25-operation integer family.

- Original op19 calls with VL<=2: 27, comprising VL0, VL1 and VL2 with nine calls each. All have start0, three seeds and three mask modes.
- Of those 27, the nine VL0 calls already satisfy the ordinary vstart>=VL optional-target condition. They are not additional exceptions.
- Only the eighteen VL1/VL2 calls introduce the additional exact offset2 empty-target exception despite start<VL. No other slide encoding, scalar offset, opcode or wider VL may inherit it.
- Across all 5985 original calls, 2205 satisfy vstart>=VL. Adding only the disjoint eighteen offset2 cases yields 2223 optional target owners, leaving 3762 required target owners. Required FP targets: 1170. Required op24 memory targets: 117.
- Five full-capacity memory helpers per call remain compulsory: 29925. Together with 3762 required targets, minimum required owners are 33687. The 117 op24 targets are already within 3762 and must not be added twice.

The reference report's `VI2_short_noop_calls=27` is a descriptive source count, NOT a grant of 27 new waivers. All 27 still passed full helper windows, setup, input/output oracle and vstart checking. Reference has no CVX/uop tokens. A future M9 checker must derive classification from its pinned sequence and exact target encoding, require every actual allocated token to complete even when the target was optional, and retain all memory-helper and generic protocol gates. No helper retirement, full-call sequence or scalar oracle may be omitted for a no-op.

## Review Boundary

The e32/m2 raw reference was not reread or reparsed. During this addendum a mistakenly unrestricted recursive rg search of the older e32/m1 worker directory also scanned its CSV text. That search was stopped without semantic reanalysis; no CSV output from it is used as acceptance evidence. Subsequent inspection was restricted to the named checker source and e32/m2 sequence/proof JSON. No artifact was modified and no Host/reference/DUT job was run.
