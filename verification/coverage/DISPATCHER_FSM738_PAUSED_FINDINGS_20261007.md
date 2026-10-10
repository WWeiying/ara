# Dispatcher FSM738 Paused Findings

Static observation only. Work stopped at the parent's request before stimulus
selection. No new test, VCS run, DVE run, RTL edit, or waiver authorization.

Read baseline:
`verification/out/clip17-offline-admitted-738-parent-20261006-01/combined-bits.json`.
Scope: `ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher`.
FSM metric checksum `1099616778`, width92, raw bits
`0xffffefda435b6edaf480fff`.

Compiled shape SHA256:
`39eec846a15994d7e7e196025d5b215a11474af4e9b4de19afb2d25223c485fc`.
Matched the baseline's design pin before interpreting coordinates.
Coordinates are sequential states then transitions for each compiled machine;
hit is `(bits >> (width - raw_index - 1)) & 1`, not a source-line index.

Frozen source read:
`verification/out/old-image-source-evidence-20261006-01/ara_dispatcher.sv`,
SHA256 `9af95c3eee6c63ecd9e60bf6d7c6474bdaaf1c5f96cef1bd653a6d51c6a2dd43`.
Historical build-source-pins manifest SHA256:
`6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b`.
Live workspace RTL was not used to establish frozen behavior.

`state_q` compiled machine checksum4130774747, id0, width4, line539.
Raw zero transition indices observed:
19,26,29,31,32,34,35,36,37,40,42,45,48,51,55,58,61,63,
68,70,71,73,74,75,76,77,78,79.
No zero state or `lsu_ex_state_q` coordinate was printed by this traversal.

Selected observations, NOT reachable-stimulus recommendations:

| Raw | Compiled transition | Compiled line |
| --- | --- | --- |
|19|NORMAL_OPERATION -> OVERLAP_WAIT_ORIGINAL|5855|
|31|OVERLAP_ISSUE_ORIGINAL -> OVERLAP_CAPTURE|5850|
|32|OVERLAP_ISSUE_ORIGINAL -> OVERLAP_PREFIX_FIXUP|5848|
|68|WAIT_IDLE -> OVERLAP_WAIT_ORIGINAL|5855|
|70|WAIT_IDLE -> WAIT_IDLE_FLUSH|4348|

Source investigation reached the overlap-prepared/snapshot/reshuffle gates
and the masked load fault/FOF flush assignments. It did not finish proving
which compiled arcs survive all producer, pending-request, decode-blocked,
and state override conditions. Raw zeros alone do not prove reachability or
unreachability. Existing store-response structural review and known failures
must be deduplicated before any future proposal. No case was selected.

The successful v8 host audit/prepare/check belongs to the existing735 reader
work, not this static investigation, and is not a new DVE percentage report.
