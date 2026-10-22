# Prefix5 Independent Terminal Audit

**PASS: exact five original source prefixes,262 original trial positions, on
frozen candidate04.** This is not22 full matrices, the separate45 stalled records,
or original Linux/board closure. No DUT, host/Spike rerun, rebuild, service query,
duplicate launch, or simulation polling was performed for this audit. All old
records and sealed inputs remain unchanged.

## Terminal Identity

- Plan SHA256: `34b4caf0f0810a3194449e58bc337b9cadb93d4a31847f70dc871b16c209e0b4`.
- Image ledger SHA256: `e26b4a68939946d104c37917cf688a40ea6e1f963f048a586a5662d58c368673`.
- `candidate04_plan01/complete.json` status:
  `PASS_5_ARITHMETIC_PREFIXES_CANDIDATE04`, finished `1791722332.7901318`.
- Complete SHA256: `fbae6e7375e75ebd2fe6c098ab535514c7eb602181f30290f84676d078e81903`.
- Runner SHA256: `12a7a6468e1a218e3f064603529615ecf2f2333af40031139b80171a0e32d5e1`.
- Summary SHA256: `7296b13e74c1cb283e7be8e5ddd68f16a1413e3cc06b2086a6b358cf7dc0a111`.

The runner is COMPLETE, jobs2, exact five expected names and PASS counts. All
five summary rows and terminal rows agree, returncode0, empty failure reason.
Each private `input.elf` matches the frozen plan input, original prepared SoC
ELF and terminal-record hash. Actual `inputs.json` records match those paths/
hashes and the complete candidate04 simv image identity. Each actual command uses
the expected frozen simv and exactly one private `+PRELOAD` argument.

Independently rehashed: **992 plan pins**, **43 prepared files**, **4 launch-gate
pins**, plus the image ledger and all image files. Zero mismatch. Both raw logs
per case, `console.log` and `work/run.vcs.log`, were read: **10 logs** have exact
begin/original summary/prefix/board-pass markers, simulator success and `$finish`.
All original counts/elements/errors0 markers match. No RVV fail/failed,
unsupported, board failure/trap/mismatch, fatal/error/assertion, cancellation,
interruption or timeout token was found. Terminal console hashes match actual
files. The service log contains the same five PASS rows.

## Actual CSV and Full Results

All five CSVs were read in full without invoking a checker that rewrites old
outputs. Retirement order is contiguous, cycles monotonic, no retired trap;
row/retire/final-cycle counts agree with the stored VALID trace summaries, whose
CVX exception count is0. For every original call the audit checks all13 helper
instruction PCs and encodings in order, original a/b/out+1/mask addresses,
capacity/target VL, vstart and returned full vstart0. Target is original
`vadd.vv v24,v8,v16,v0.t`, encoding `00880c57`.

Call tuples were independently enumerated from original length/mask/start loop
order and compared with frozen host input records. The original seed0 xorshift,
special a/b inputs and predicate rules were reconstructed independently for
result checking. Every scalar load from the result/guard footprint after each
helper return was checked using actual CSV address, read mask and returned value:
active elements equal `(a[i]+b[i]) mod 2^SEW`; prestart/inactive/tail and both
guards equal original0x5b. Each expected address is read exactly once per call,
with no missing or duplicate output read. No agnostic allowance was added.
This verifies **124,928 actual result-element reads plus524 guard reads**, not
only source hashes or a firmware PASS string. All match.

| Program suffix | Calls | Result elements | Guards | Retired instructions | Last CSV cycle | Wall seconds / budget |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| e8_m4_prefix56 |56|28672|112|1174462|1678862|1776.948 /4000 |
| e8_m8_prefix38 |38|38912|76|1469207|2137945|2372.816 /4000 |
| e16_m8_prefix56 |56|28672|112|1098023|1483061|1679.200 /4000 |
| e8_m2_prefix56 |56|14336|112|596872|853244|956.510 /1800 |
| e16_m4_prefix56 |56|14336|112|559451|757477|814.938 /1800 |

All program names above have the `arithmetic_` prefix. Actual final target
retirement cycles and tuples:

| Shape | Original final trial | VL / vstart / mask | Target cycle | Helper return cycle |
| --- | ---: | --- | ---: | ---: |
| e8_m4 |55|512 /256 /0|1648341|1651458|
| e8_m8 |37|512 /256 /0|2089242|2095431|
| e16_m8 |55|512 /256 /0|1452932|1456064|
| e8_m2 |55|256 /128 /0|835586|837159|
| e16_m4 |55|256 /128 /0|739987|741567|

CSV SHA256s, in the same five-case order:

```text
94359c1dd92420c912b6de2f4ccea65589e702135348886abb363178a6b96557
60a78a567c853ce05f2573edd7e65f91cb17b28d2a4252d9f320a532a339b43f
8902646a533e0090d4be85ebe300d8dfab3c715f522bbe336c5ff822503a840c
4c4dc238b6e076b1fcd4c57a621c137ea41d7f6c4da638444df3262550b9dfe7
f3ba8138cf70ca4ca875bfff3bab0e4f8a24febcaf75753dc9d14eb021ac824e
```

Actual SoC ELF SHA256s, same order:

```text
22361e261aff163717e6ddf05f9f98c4d7d78cccd265691d3a280b45aab592d4
879d3445a0d89750968a1313e9294906a28593e78ee5f4f61f69f530e780ec8b
ab51f527a4d002ccae17cad5a01ea8cc888f6ef75b3de91930b883c3a1f11ba4
60026b6e884264bff244fdeb692da6c694a0e3e779bfb9b7d48e4fbd9923ded8
29cd8de03a412de10c1ed51c30c416dd4703d1d6c1fd6050f60f91ac48ba2413
```

## Time, Abort and Scope Limits

Runner start/end: `2026-10-11T04:29:04.561685-07:00` to
`2026-10-11T05:38:49.970995-07:00`,4185.409310s. Launch-record time to terminal
publication:4188.964321s, below the10000s outer budget; all individual cases are
below their sealed inner limits. Timestamp order is launch < runner start <
runner completion < terminal publication.

No recorded abort/cancel/timeout is present, and all262 calls and full data checks
completed. The parent separately reported the service inactive, MainPID0,
Result=success and ExecMainStatus0. Those service observations are attributed to
the parent; this agent did not repeat them or claim journal access. This older
prefix launcher does not emit the newer explicit sticky-abort terminal field, so
this audit does not claim an independent proof against every possible late-signal
race. Its observed functional completion and terminal/exit evidence are accepted.

Authenticity remains as documented in `README.md` and frozen provenance:
reconstructed C rebuilds all22 archived complete Linux ELFs byte-for-byte, but
the original C text itself was lost. Prefix0..55 for e8/m4 reaches the genuinely
recorded trace boundary; e8/m8 trial37 and e16/m8 trial55 were source-derived
boundary predictions for historically failed shapes, not original captured
tuples. The other two shapes are controls. These are contiguous original
prefixes retaining prior calls/RNG/state, unlike isolated tuple probes. The
bare-metal runtime does not reproduce Linux tty-drain timing. No claim is made
that all22 whole matrices, all arithmetic instructions, or45 distinct archived
stalled records are closed by this bounded acceptance.
