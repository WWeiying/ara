# Accepted Baseline Handoff Evidence

The current accepted receipt is
`verification/akv/results/reader-handoff-baseline-20261024.json`, backed by
`verification/out/reader-handoff-reexport-audit-20261024-01/result.json`.
This is unchanged production RTL and the original compiled fixture; no new VCS
run or source correction was needed to obtain this functional evidence.

| Check | Accepted Evidence |
| --- | --- |
| Commands | 6 QBS, 65 AKV; exact software and hardware order |
| QBS fault | Second command only, PMA enum5, cause5, address0; destination unchanged |
| QBS success | Five commands, each commits four aggregate words; fault commits zero |
| Resident payload | 62 AKV rows checked after external backing poisoning |
| QBS context | FILL, AKV FULL/loads, REUSE and RELEASE; 292 bytes reused without activation reads |
| Boundary wave | 118929 settled-negedge samples, all134 required signals |
| Metadata preservation | 328 QBS-context /747 AKV-context observations under the other owner |
| Independent protocol | UVM/CVXIF/backend/AXI, original log/trace and exact image/ELF hashes |
| Export derivation | Fresh pinned FSDB export reproduces the checked cycles.csv byte-for-byte |

These observation counts are evidence samples, not utilization or overlap
metrics. The synthetic fixture is neither a real-model benchmark nor an area
or performance result. It does not prove stalled-AR fault behavior inside the
SoC, AKV-fault switching, or physical sharing; those remain separate gates.

## Why the Original Worker Is Still FAIL

The original worker completed simulation successfully but its transcript
checker incorrectly expected one `commit_groups` per successful M1 command.
The field actually prints `qbs_commit_word_count`, which increments for each
completed aggregate lane word. Legacy M1 writes the whole register, including
zeroed output tails, even when N=3:

```text
aggregate word = 4 lanes * 64 bits = 256 bits
register       = 1024 bits
commit words   = 1024 / 256 = 4
```

This follows `qbs_commit.sv`'s `WordsPerRegister`, `total_words` and
`word_complete` logic, not an expectation fitted to observed values. The
payload fault occurs before commit, so its count is zero. Do not apply this
M1 fixture formula to wide M5..8 commands, which have a different active-N
commit rule.

The original worker/checker files and original FAIL reports are retained.
`check_reader_handoff_v2.py` is the corrected strict successor; it additionally
checks exact VLEN/lanes and context-reuse work. The original checker is run on
the same raw log to reproduce its known counter error. Its old unit tests
describe the retained historical checker and are not the current counter
contract.

`audit_completed_v2.py` first repeats all semantic, waveform and independent
protocol checks, then freezes source, FSDB, profile and exporter-tool hashes.
It actually reruns the exporter and requires identical cycles.csv bytes. Thus
the audit does not rely on metadata paths alone to establish wave provenance.
The independent protocol report uses absolute image paths, preserving the
strict image-inventory comparison. Earlier relative-path and intermediate
audit reports are retained but are not the accepted final receipt.

The final state is `REEXPORTED_FUNCTIONAL_AND_SETTLED_WAVE_AUDIT_PASS` with
`original_worker_state=FAIL`, `clean_original_worker_pass=false` and
`new_simulation=false`. It is not a retroactive clean worker PASS.

## Next Integration Gate

The isolated candidate in `verification/akv/shared_reader_candidate/` has
separate finite cycle-comparison evidence. Its one original-reader reference
proves mux transparency under the tested common history, not a full two-engine
system equivalence. Production VLSU and both engines still instantiate their
original readers. Preserve source seals of current campaigns; integrate the
candidate only with an independent image and repeat the boundary, fault,
resident-context and representative real-operator gates before promotion.
