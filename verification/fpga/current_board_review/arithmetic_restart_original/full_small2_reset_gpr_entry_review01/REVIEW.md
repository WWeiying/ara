# Full Small2 Reset GPR Successor Entry Review01

Decision: APPROVED_STATIC_E8_RESET_PROFILE_SUCCESSOR_ONLY. No blockers.
This supersedes the pending-successor state in the earlier memory-contract note
without editing that note or any sealed old worker/checker/terminal record.
Main authorization is still required for any full offline audit. No full CSV
has been read here, no Host/reference/DUT/build was run, and no producer was edited.

## Frozen Identity

Producer `arithmetic_restart_original/full_small2_reset_gpr_recovery01`:

| Artifact | SHA256 |
| --- | --- |
| READY.json | 7d2dfe7a3fd630befa53c487749a477a6aae26ea28011215653b7c65d66e3af9 |
| checker.py | 95f811703a8f13b75fc176cdc599ee30c7ead3007d54ed9ccf872c87b431478f |
| reset_profile.json | 308784d27eaf81e2a608cd7cd37a9ac61a22a58ce9eda994715cec58dcd682a4 |
| pins.json | f7c81ea3f40aa2ccb059dce38579463cd151fb93321710d6b588efc648f8e1eb |
| host01.json | 90d770f4ef290929bdf60087d1851884367bd886d3972aab3d165e9755420991 |
| host_exit.json | ea032187ed256f5c0ea404dc47376d84f635b1aad066170afe558bbdf142d4d7 |

All12 successor pins and Host-reported pins were independently hashed, without
opening CSV/raw. Original plan SHA7ec58e3f... matches the exact profile. All10
profile RTL pins, all66 M6 image file pins, compiled manifest/configuration/
snapshot identities, and50 original project Python dependency pins match.
The original e8 model4095 entries and SoC ELF were independently hash-checked
against the plan; READY remained unchanged across the checks.

## Reset State Is A Hardware Profile

The independently read frozen source proves FpgaEn=0 in the configured package,
no override by ara_soc adaptation, and selection of ariane_regfile_ff. Reset
clears all32 GPRs, and the frozen testbench asserts reset before clocks/run;
the SoC boots DRAMBase. This is not an ISA-wide zero-register initialization
rule, a Linux ABI assumption, or permission to seed a midstream/warm trace.

The new gate pins the profile itself, old plan/checker, image.json, actual
compiled manifest/configuration/snapshot and image files. It checks exact e8
specification, source model and ELF before constructing state. e32 is excluded.
The inherited first retirement must be original _start/order0, followed by
contiguous retirement and ordered full BSS initialization; no startup bypass
was added. Future offline admission must also bind the actual original command,
artifacts/numeric outcome and fresh-run context to this profile, not just load
this class on an unrelated trace.

## Only Initial Knowledge Changes

Static AST inspection confirms the subclass defines only __init__. It uses the
exact legacy checker SHA18c9b86ab1a13b05d0f69823299d761a1f54a8d7c20c8b1ca30afd867ec8bf0f,
calls its initializer, then seeds32 integers from the proven profile. It does
not overwrite legacy methods/globals or infer any value from observed wdata.

Original consume/finish remain inherited unchanged: scalar address/enable/value
equality, signed-load rules, every source/RNG/setup byte, original13-instruction
continuous helpers, argument/op/seed/history order,16 results plus2 guards per
call, prestart/inactive/tail, returned vstart0, capacity16/vlenb128, final counters,
failure vetoes, CTRL raw0 and original park. All4095 e8 calls/65520 results/
8190 guards/53235 helper instructions still have to pass a full audit. The old
unshifted RVFI store-data contract and decoder are unchanged.

## Actual Small Host Evidence

Read-only Host evidence reports8 methods PASS, numeric subprocess wait0,
timeoutfalse,9.437740874 seconds within60s, one attempt. run_host.py persists
the actual child wait result; this reviewer did not rerun or wait that process.
The captured diagnostic JSON is pinned and contains only the prior bounded
first-error evidence, not a new raw read by this reviewer or this Host fixture.

The Host fixture feeds the real jal-main/sp decrement/ra save/s0 save sequence
at its documented pre-main boundary, with captured known registers plus the
proven reset state. It is explicitly not a full from-reset replay. It checks:

- the corrected exact prologue passes and the old checker still fails;
- wrong value, write/read mask and address remain rejected;
- removing source x8 still fails, and known7 versus observed0 fails without
  learning0 from wdata; matching known7/store7 remains a real equality check;
- mismatched profile/regfile/image/initial values/origin/shape fail closed;
- missing original startup remains rejected;
- consume/finish identity with legacy remains intact.

The Host tests do not prove all later e8 calls. Their bounded purpose is to
cover the genuine first-error checker defect which the old synthetic fixtures
missed. No further test matrix or DUT run is needed to review this narrow change.

## Scope And Next Boundary

Static approval is for this sealed **e8-only initial-state successor**. It is
not full-CSV architectural acceptance, acceptance of the original whole2 batch,
recovery of canceled e32, or DUT launch permission. Preserve original e8 ERROR,
e32 CANCELLED and whole2 NOT_PASS. A separately authorized one-pass offline
recovery must still verify actual command/image/source/pins/rc0/noabort, generic
trace validity and the entire inherited oracle, with its actual process exit
and first new error preserved. No automatic parse retry or state relaxation
is justified by this entry review.
