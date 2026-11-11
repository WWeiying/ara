# Actual Linux Model Execution

New successor only: models04, binding_v1, SDK, llama and QEMU inputs stay sealed.
This directory owns the linked test-platform provider, model frontend link,
minimal PID1 and single-attempt systemd worker. It does not build libraries or
emulators. No model has executed merely because compilation or host tests pass.

`link` consumes James's actual prepare-v2/build-v1 receipts and four archives.
It links the frozen model comparison program plus the real enabled provider,
so the SAME ELF contains native requested0 and resident requested1 paths. It
also builds the real static PID1 and initramfs. The result is
LINKED_PROVIDER_NOT_AUTHORIZED: there is no launch command and `run` rejects it.
This closes actual library/provider/static-link/packaging compatibility without
granting S3 acceptance. Historical link01/02 were default-denied checks only.

After all four S3 gates, `prepare` calls Dalton's independently reviewed frozen
`qemu/execution/run.py.checked_result(out, review_sha)` directly. That function
must validate directed AKV, original Stage4 performance and functional ELFs,
and native QBS on the SAME binary, returning `(report, pins)`. A directed-only
receipt is insufficient. The aggregate API/source closure is still owned by
Dalton; no local replacement PASS flags are accepted. Missing API/receipt denies
preparation. `prepare` then links the same libraries with a contract containing
the actual S3/image identities and creates the real initramfs/launch recipe.
This re-links only frontend/provider, never the libraries or dirty assembly.
Each job rechecks its selected model file and disk, kernel/BIOS, case inputs
and complete consumed library/S3/source closures. Unused model disks are not
rehashed on every Smol preparation; their frozen models04 inventory is retained.

## Provider

The provider's SHA binds source, libraries, model/disk/tokens, kernel/BIOS,
launcher policy and, for runnable preparation only, S3/image identities. The
ELF is externally bound by the preparation receipt, avoiding self-hashing.
Index4 and production default behavior are unchanged. The provider is an
explicit linked TEST_MODEL implementation, not an environment-based grant or
a general Linux/board eligibility assertion.

Before CSR access: actual auxv F/D/V, hwprobe F/D/V/Zfh/Zvfh, current per-thread
Vector policy ON, and main-thread identity are required. Unknown support denies.
No SET_CONTROL or privileged CSR is used. The existing scalar state reader
retains its VSTART-first behavior. All callback code is scalar and uses direct
syscalls, no libc memcpy/formatting or FP/vector instructions.
Only this bounded scalar provider is compiled with `-fno-stack-protector`:
the target toolchain otherwise inserts libc `__stack_chk_fail` calls into its
callbacks. GNU undefined-symbol checks allow only the sealed scalar CSR reader.
Frontend, init and all sealed libraries retain their existing protector policy.

Acquire checks one task, affinity CPU0, no active lease and all supplied spans,
including crossing contiguous mappings. /proc/self/maps is checked for complete
coverage and write permissions. Only anonymous/heap/stack, the static /test and
the pinned read-only model file are normal-RAM sources for this dedicated VM;
unknown/device mappings and holes decline. Kernel vDSO/vvar are never accepted
as spans. Static approved code, one task and the fixed RAM-only machine bind
future internal SDK stack/heap allocation lifetime. This is a trusted closed
test deployment, not a security boundary against arbitrary in-process code.
Legacy BASE/PREFILL/QUANT_KV have a separate matching contract. Lease lasts
through the original whole-call SDK completion/RELEASE, with no mid-call retry.

## Real Launch

The existing model_live initramfs flow is retained: static /init and /test,
read-only ext4 /model, writable /tmp. PID1 additionally mounts procfs for provider
checks, waits for /test and prints its real exit status before powering off.
The frozen harness still forks requested0 then requested1 in the SAME ELF;
all fixed QBS/native options, tokens, teacher forcing, whole-logit and CSR
comparisons remain. Only `tcdrain` after before/after snapshots is added to a
COPY, never to binding_v1. It fences serial phase records before compute.

QEMU uses one vCPU, guest4GiB and log-backend AKV events. stdout and stderr share
one host descriptor; qemu_log flushes each event. No guessed timestamp merge.
Scoped `exec,nochain,in_asm` covers only final-ELF QBS/PV_PREP function ranges;
no single-step whole-model trace. Entry-TB hits are compared to complete command
summaries and PV counts, explicitly NOT called instruction-retirement proof.
The old content checker remains unchanged and receives actual QK/PV ELF PCs.

The direct service owns the Python worker, which owns and waits for QEMU.
One attempt, 5400-second guest timeout, host MemoryMax8GiB, CPUQuota100%,
KillMode=control-group; no automatic retry. `attempt.json` prohibits reuse.
S3-unbound prelink never has an authorized launch command. Both preparation pins and
the final four-gate aggregate are revalidated before launch and pins afterward.
Actual execution remains subject to parent review and approval.

```
python3 -B run.py identity
python3 -B run.py link --output OUT/stage5_models_execution_link_ID \
  --source-sha256 REVIEW --case smol_f16 \
  --library-prepare OUT/stage5_libraries_prepare_20261110_02 \
  --library-build OUT/stage5_libraries_build_20261110_01 --library-sha256 REVIEW
```

For actual preparation, replace `link` with `prepare` and supply the reviewed
`--s3-reader`, `--s3-reader-sha256`, `--s3-result`, `--s3-sha256`. Nothing launches
automatically. The parent-reviewed service runs the frozen `inputs/run.py run`
with `--output PREP` and `--review-sha256 SHA_OF_SOURCE_PINS`.
It also requires `--review-prepare-sha256 SHA_OF_PREPARE_JSON`. The
`service-command` action only prints the exact reviewed systemd argv; it never
launches it. The worker verifies actual MainPID, memory cap, CPU quota and
KillMode before running QEMU.
This is QEMU functional evidence only; no model/RTL speedup claim is supported.
