# Remaining34 Independent Source / Reference Review

Decision: **ACCEPTED_REFERENCE34_NOT_DUT**, no blocking finding. This binds
producer READY `47d7e85317fdd848ce1cfb7094920019588cde0f92183667602e6dd7b54ed3ca`.
No Host/Spike execution, compilation, DUT launch, or live-pilot query occurred.

## Binding And Exit

- `audit.json`: schema `nf2_remaining34_independent_reference_audit_v1`;
  SHA `e5db50970a48445a7ff8f65c6ca3a457fc47dbdc7216cd65ec1202e691c7e478`.
  Required scope fields: `reference_only=true`, `DUT_started=false`,
  `pilot_queried=false`, `PASS40=false`, `blockers=[]`.
- `source_audit.json`: status `SOURCE34_VERIFIED`, `count=34`;
  SHA `fd9b7e4d5830e8587014846d8a0df00d650082332ae4860c320a845d1116e4e7`.
  Contains every exact original case path/hash, C/S hashes, ELF hash, parameters,
  measured failure text, and six exclusions.
- Each `audit.json.groups` entry binds `id`, `status=REFERENCE_ACCEPTED`,
  `audit_sha256` (the corresponding group JSON), `commits`, `checks`, and
  `soc_elf_sha256`. Full raw identities/results/dimensions are in each group JSON.
- `pins_pre.json` SHA
  `229857a9d5eac2bb40a85ce600fdfb0b728be4508e296fb1bc9b4494ed16fe79`.
  482 producer pins plus READY; all nonraw files rehashed before/after.
  Each raw SHA was computed during its sole complete traversal, with unchanged
  inode/size/mtime/ctime before/after and a final all-nine stat recheck.
- Actual audit PID1487474, tool session34480 completed with **exit_code0**;
  completion output reported group09 accepted and the above final audit SHA.
  This is observed process completion, not an inference from a missing PID/unit.
  The initial preparse error (stripped original ELF lacks a `mask` symbol)
  is retained in `preparse_attempt01.json`; it opened **zero raw files**.

## Source And Oracle

Exactly archived40 minus old-M2 J2 and the actual sealed pilot4 identities,
in archive order: eight groups of4 plus one group of2. The34 comprise
17 loads/17 stores, 12 sparse-fault cases and22 all-off cases. Original
`case.json` and manifest agree; each has its own measured standalone failure.
These are `single_current_oracle_trial` derivatives, not byte-identical original
parent Linux ELFs or proof of Linux signal-frame behavior. Context/fault-count
errors are not relabeled as independent historical numeric failures.

Independent parameters were transcribed from original `selected_trial` and
source selectors, then compared against every generated group configuration.
Original and adapter target encodings are `20055c07` / `20055c27` (masked NF2
e16 v24/v25); VL8, e16m1, cap64 per field, mask0x24 or0 are retained.

The mature read-only reference observer was reused, with an additional
independent original-formula check of all128 final halfwords, two output
guards, all8KiB memory, all1536 PTE words, physical guards, mask and post-CSRs
at the relevant checkpoints. Its full seed/fault/result neighbor snapshots
and exact exception/action ledger also passed. There are4352 final halfword
outputs plus68 guards across34 cases, not merely active-lane spot checks.

All12 faults restart the same target PC with vstart2 or5. Poison touches only
completed active-prefix elements, both fields. The faulting segment's vector
fields remain unconstrained at the partial checkpoint; this is not rollback
validation. In this selected34, the first active faulting segment has both
fields beyond the page boundary: do not claim observed active split-field
partial completion. Full-memory/PTE checks precede all-off cleanup/refill;
unmapped-page refill follows PTE repair/SFENCE and precedes retry/poison.

All46 target-attempt records independently match exact PC/code, S-mode,
address, VL8/vtype8, initial vstart0 or retry2/5, fflags21/frm3 and
vxsat1/vxrm2. Every firmware PC/code matches the actual reference ELF;
all vector-PC counts match setup/target/snapshot/retry/restore roles, with
no extra vector sites. Five boot instructions per ELF are accounted separately;
post-HTIF records are only ELF-backed side-effect-free parking loops.

Group09 actual compiled dimensions are2, including output520B, mask32B,
records384B and each snapshot array1280B, in both SoC and Spike ELFs.
Reference jobs use separate subprocesses; `observer_cli.py` configures one
group per process. Future concurrent replay must preserve that isolation,
not invoke mutable shared model configuration in multiple threads.

## Actual Profile

| Group | Cases | Raw commit records | Firmware records through HTIF, excluding boot | Checks | Traps | Stored reference seconds |
|---|---:|---:|---:|---:|---:|---:|
| 01 | 4 | 1261953 | 1257174 | 3565 | 6 | 47.878 |
| 02 | 4 | 1177976 | 1175050 | 3001 | 4 | 43.829 |
| 03 | 4 | 1318302 | 1317416 | 3569 | 6 | 49.552 |
| 04 | 4 | 1256185 | 1255299 | 3285 | 5 | 51.433 |
| 05 | 4 | 1352171 | 1347392 | 3847 | 7 | 61.873 |
| 06 | 4 | 1265954 | 1265324 | 3283 | 5 | 56.516 |
| 07 | 4 | 1366991 | 1362121 | 3569 | 6 | 61.486 |
| 08 | 4 | 1308073 | 1304483 | 3285 | 5 | 54.706 |
| 09 | 2 | 650445 | 645571 | 1509 | 2 | 28.586 |

Totals: 10,958,050 commit-style records =10,929,830 firmware-through-HTIF
records +45 boot +28,175 parking. These are parsed Spike records, including
fault-attempt logging, not independently measured DUT retirement counts.
All9 references report process return0 and exactly one HTIF success.
46 traps =12 page faults +34 supervisor ecalls; 68 checkpoints; 28,913 firmware
checks; 1,566,656 checkpoint bytes checked by the mature observer.
Raw bytes total1,344,425,696, each file traversed once.

Recorded commands retain ISA `rv64gcv_zfh_zvfh_zvl1024b`, msu, pmpregions0,
3M instructions/120s/512MiB per ELF, one attempt/no retry. The seconds above
include producer child/reference validation context, not measured VCS time.
Stored Host evidence is295,936 oracle rows/34 cases,68 positive checkpoints,
258 mutations rejected, and2/4-case observer controls; it was inspected, not
rerun. A three-hour DUT budget for the largest raw record count would require
at least126.6 records/s (151.9 with20% headroom); this is a planning threshold,
not evidence or a guarantee of DUT throughput.

## Nonblocking Correction And Limits

Sealed metadata says original mask128B. Actual original C declares
`mask[CAPACITY_LIMIT/8]`, `CAPACITY_LIMIT=128*LMUL_NUM`, m1: **16B**.
Fixture16B and helper consumption8B are correct. Original ELF is stripped,
so no original mask-symbol-size claim is made. Tesla reports this wording is
corrected in the new runner README; no sealed preparation file was changed.

No remaining34 DUT acceptance or PASS40 is inferred. Parent-reported pilot4
terminal acceptance was not independently re-audited here. J2 exclusions remain
old-M2 evidence; the proposed unchanged J4 current-image replay is outside this
review. Linux signal delivery/mmap batching and the full original parent remain
outside this source-faithful Sv39 reference scope. No launch authorization.
