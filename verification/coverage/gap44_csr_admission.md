# Gap44 CSR Admission

This is a new M-mode case. No frozen case, harness, checker, RTL or scheduler
is modified. Runtime budget is 300 seconds, not yet measured on VCS.

## Evidence

- `verification/out/gap44-csr-preflight-20261004-01/evidence.json` is the
  original SHA256-anchored preflight: 52 probes, 50 illegal, 2 legal, 1290 checks.
- Its 60 artifact hashes cover compiler logs, objects, dependency files, dual
  ELFs, nm/disassembly/readelf, exact commands, Spike logs and source/tool maps.
- Source audit binds the compiled RTL manifest and 50 missing native vectors
  against the completed 640-test corpus. No coverage gain is claimed yet.
- `csr_gap35_body.h` supplies exact trap/cause/EPC/TVAL/MPP/GPR/SP/RA checks.
  Sixteen stable architectural CSR fields are compared after each illegal
  probe; trap CSRs with intentional effects are checked by the harness instead.
- Reads use CSRRS with rs1=x0; writes use CSRRW with nonzero rs1, data and rd.
  Read-only HGEIP has only a read probe. There is no six-op/three-privilege matrix.

## HPM Limitation

The independent capability executable writes two nonzero patterns to HPM3.
The installed Spike reads zero for both machine/user aliases: RAZ/WI.
This is sealed as a limitation, never evidence of nonzero write preservation.
Spike nevertheless independently checks every probe opcode/cause/EPC/TVAL/rd.

The DUT executable has an explicit different capability requirement: HPM3
must read back BOTH full-width nonzero patterns and remain stable with event
selector zero. Every high-half illegal probe must preserve the second pattern
in both aliases and leave the event selector zero. No mcountinhibit assumption
or adaptive acceptance of an unimplemented zero counter is permitted. The
runtime checker rejects the Spike profile/zero seeds even with a PASS summary.

## Parent Integration

Import `gap44_csr_admission`, then call `install_hooks()` in every parent,
worker, and summary process, after installing parent defaults and before
`checked.main()`. It wraps the current `evidence.precheck`, `full.worker` and
`checked.summarize`, preserving delegation; it does not change `checked.SCRIPT`.
The parent owns that variable. Repeated installation is idempotent.

Direct interfaces:

- `handles(item)` selects the exact case name or explicit gap44 format.
- `precheck(item, evidence)` replays sealed Spike evidence into the caller's
  hash set. A case-local proof avoids interference from other batch cases.
- `runtime_proof(output, plan, row)` is read-only; use after the existing strict
  directed audit. Requires original-row hashes for every artifact before read.
- `install_hooks()` returns installed precheck/worker/summarize plus
  runtime_proof callables. Hooks affect only gap44's extra checks.

Selections use the standard `cases` array, with `gap44-csr-spike-v1` precheck
and `gap44-csr-uart-generic-trace-v1` runtime contract. Compose the case unchanged;
the parent can rebase top-level baseline paths through its existing admission.
Standalone entry is `run_gap44_csr_checked_extension.py`; no launch was run.

Runtime proof is saved as `results/csr_gap44_absent/csr_gap44_runtime_audit.json`
and pinned into the original outcome. Summary reconstructs the entire proof
and requires equality, not just PASS/counts. Objects use string keys and arrays;
worker asserts JSON round-trip equality. No integer-key normalization is used.

Prepare metadata without compiling or simulating:

```sh
python3 -B verification/tests/prepare_gap44_csr_admission.py \
  --output verification/out/gap44-csr-admission-20261004-01
```
