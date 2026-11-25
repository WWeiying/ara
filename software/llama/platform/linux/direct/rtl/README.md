# CVA6 Direct AKV Gate Candidate

This source-only delivery preserves the four-file incremental RTL patch even
when `hardware/deps/cva6` changes are not tracked by the parent repository.
The gate patch is byte-identical to the immutable successor02 export; it is
not a complete CVA6 dependency snapshot or an FPGA migration.

## Contents and Contract

- `cva6-akv-direct-gate.patch`: task-initial to tested candidate; four files.
- `cva6-baseline-prerequisite.patch`: pre-existing three-file dirty delta
  needed to reconstruct the task baseline from the pinned CVA6 HEAD.
- `baseline-current-hashes.json`: exact HEAD, baseline/current file hashes,
  patch hashes, and validation-report hash.
- `focused-validation.json`: original pinned OUT final-review report.

SAKVCTL is supervisor RW CSR `0x5c0`: upper32 signature `0x414b5601`,
low bits STRICT=1, U_ALLOW=2, S_ALLOW=4, all other low32 bits read zero.
Reset low3=0 retains legacy access. Strict gating covers opcode `0x5b`,
funct3>=2, including INFO, using execution privilege, not MPRV. M bypasses;
QBS funct3 0/1 and ordinary RVV are unaffected. CSR writes flush younger work.
Permission flows CSR -> cva6 -> id_stage -> decoder; denial is illegal before
accelerator issue. Already authorized older requests are not asynchronously gated.

## Reconstruct the Four Files

Do not reapply to an already patched working tree. From the repository root,
reconstruct only in a fresh build-input directory, not a new development worktree:

```sh
bundle="$PWD/software/llama/platform/linux/direct/rtl"
work=$(mktemp -d)
git -C hardware/deps/cva6 archive b29fd3cf906e7f4c71da4c2f46451c4c60a4487f | tar -x -C "$work"
python3 - "$bundle" "$work" <<'PY'
import hashlib, json, pathlib, subprocess, sys
bundle, work = map(pathlib.Path, sys.argv[1:])
h = json.loads((bundle / 'baseline-current-hashes.json').read_text())
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
for name, record in h['artifacts'].items():
    assert digest(bundle / name) == record['sha256'], name
for stage, name in [('baseline', 'cva6-baseline-prerequisite.patch'),
                    ('current', 'cva6-akv-direct-gate.patch')]:
    cmd = ['git', '-C', '/tmp', 'apply', '--unsafe-paths', '--directory=' + str(work)]
    subprocess.run(cmd + ['--check', str(bundle / name)], check=True)
    subprocess.run(cmd + [str(bundle / name)], check=True)
    for relative, expected in h[stage].items():
        assert digest(work / relative) == expected, (stage, relative)
PY
```

## Evidence and Limits

Unit04 VCS PASS: 77,878 checks; 24,672 decode, 3,072 blocked, 25 no-issue,
150 CSR, two dispatcher flush/older-request cases, and nine ID-register cases.
The production `id_stage`, compressed decoder and decoder were really elaborated
and exercised; cva6 top wiring was checked against frozen production source.
Other unit support dependencies are pinned in the referenced unit04 inventory,
not reconstructed by this four-file patch. Failed unit01/02 and partial export01
remain preserved. Absolute evidence paths in the report refer to the original host.

This is RV64, no-H, single-issue focused module evidence, not whole-cva6
elaboration, whole-core/SoC PASS, Linux SAKVCTL probe validation, or board acceptance.
No FPGA copy, Vivado, synthesis, or migration manifest was changed.
