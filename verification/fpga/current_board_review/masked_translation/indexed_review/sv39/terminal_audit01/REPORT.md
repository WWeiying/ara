# NF7 M2 Full96 Independent Terminal Audit

Result: **NF7_M2_FULL96_INDEPENDENT_CSV_AUDIT_PASS**. No DUT correctness failure
or evidence of the legacy timeout/abort acceptance race was found in this run.
CPU-only audit completed in 293.52 seconds with exit code 0. No DUT was launched,
no existing input/result was overwritten, and no RTL was edited.

## Exact Evidence

- Sealed run: `../vcs_plan06`, exact groups 00..23, original trial IDs 0..95 once
  each, four per private ELF. Every private ELF matches its accepted SoC ELF,
  reference identity, program entry, input snapshot, and actual PRELOAD command.
- All 24 complete CSVs were independently replayed through the unchanged
  accepted oracle: 24,531,873 rows, 24,492,801 retirements, 284,816 comparisons,
  168 checkpoints. Every recomputed result equals its recorded result after
  `json.loads(json.dumps(fresh))` normalization. Integer/string dictionary keys
  explain the previous comparison assertion; no oracle value changed.
- Recomputed traps: 36 cause-13 load page faults, 36 cause-15 store page faults,
  and 96 cause-9 S-mode return ECALLs. The checker enforces precise fault state,
  same-PC repair/retry, prefix poison, permitted partial-field state, complete
  field tails/guards/memory, CSR restoration, firsterror zero, magic, and CTRL
  completion. All groups finish at retiring PC `0x80000076`; final trace cycles
  range from 1,197,392 to 1,454,774.
- Original group and runner return codes are all zero. All consoles contain
  the fixture PASS and simulator tohost-zero success, bind the private ELF and
  frozen M2 testbench, and contain no failure/cancellation/timeout marker.
- Group elapsed range: 1345.249924..1800.926507 seconds, strictly below 2700.
  Runner range: 1330.251239..1783.667245 seconds, strictly below 2400.
  Aggregate `firstfailure` is null; no `firstfailure.json` exists anywhere in
  this run; original post-hashes are unchanged. All group records agree with
  the aggregate. These checks do not rely solely on the legacy aggregate PASS.
- Verified 1491 plan pins, 539 frozen source inputs, 66 image files, compiled
  source manifest/configuration, exact reference membership and ledgers.
  Evidence, plan inputs, and image were rehashed after CSV replay: unchanged.

## Service Evidence Boundary

Parent observed `ara-indexed-nf7-candidate02-06.service` terminal inactive,
MainPID 0, Result success, exit status 0 before transient-unit garbage collection.
This audit's fresh query finds `LoadState=not-found`, inactive, MainPID 0, and no
NF7-owned process. Missing-unit default success fields are **not** treated as
independently recovered historical service exit status. That historical status
remains explicitly attributed to the parent's terminal observation. All 24
runner exits, time bounds, complete CSVs, and no-abort evidence were independently
verified here. The empty service log alone is not used as proof of successful exit.

## Identity And Scope

- Source plan SHA256:
  `edc7b0e20d0ef1cbf99b978421b8ca5df1eb9ce6505ec22e3bbc69db3e901839`
- Frozen candidate02 image.json SHA256:
  `384515b7365200942d08fc7b34275d10eee676cf6ce0574935043020e87c7810`
- simv SHA256:
  `6fcdf53ecf2df4526e9d35372ea6bf9d2c49fdd2fc7a6bc3b57044124aeb13b7`
- New audit script SHA256:
  `dac3c83be65880a76cc5ce1f94df638aaf9761ca853b4aba73f41d7a883c850f`
- New `results/complete.json` SHA256:
  `183b1bd1a268741f5c49dfa97b57ae9a8e239ff02bd5e478a3773f94bcf63a80`
- New `results/evidence_pins.json` SHA256:
  `adb3cd297087c1f3109a9358b51abb9cd144a013a1793229b6a27a68dfe97a07`

Acceptance is restricted to the source-derived original NF7 96-trial geometry
on frozen candidate02 (M2). It is not an original Linux ELF replay, proof of all
archived failure causes, validation of candidate04, or validation of mutable
workspace RTL. No NF8 or other ongoing simulation was queried or controlled.

Detailed artifacts: `results/preflight.json`, `results/service_observation.json`,
`results/evidence_pins.json`, `results/g00.json` through `results/g23.json`, and
`results/complete.json`. All are new outputs outside the sealed plan pins.
