# Historical Ordinary Baseline Consumer

This offline interface retains the frozen ordinary resource baseline's same
ELF, real input crop, image acceptance, raw 3864 command records, independent
UVM association and six call cycles. It does not execute EDA or accept a new
canonical image. Resource baseline means original dual readers plus legacy/v2
storage, not an ordinary-RVV-only performance baseline.

`baseline.checked_baseline()` returns `(build_report, parsed, records, pins)`.
Only the reviewed original build/run directories are accepted. The final pins
are ready for merging into a future current-canonical worker, with exactly five
historical hardware/build keys mapped through `historical_inputs.Archive` and
two software keys through the unchanged `HistoricalSources.translate`. Other
pins, including existing headers, still require their exact old bytes.

The archive manifest must have SHA256
`d958c77b3e6e966b7e2b22920d6cbc3358466defc65abcef71a8299a3b4c1674`.
There is no caller-supplied replacement allowlist or hash bypass. Archive payload,
manifest, old software bindings and consumer dependencies are pinned pre/post.

Private FunctionType clones retain identical frozen code for checked_build,
checked_image, context.checked_prerequisite, consumed_evidence and
contract.checked_baseline. Only private globals/namespaces route pin verification
through the combined translation. No imported module is monkeypatched. Original
keys remain intact during raw receipt containment checks; translation occurs at
verification boundaries and on the final returned map.

```sh
python3 -B -m unittest discover \
  -s verification/akv/canonical_promotion/ordinary_baseline -p 'test_*.py' -v
python3 -B verification/akv/canonical_promotion/ordinary_baseline/preflight.py \
  --output verification/akv/canonical_promotion/ordinary_baseline/preflight-01
```

Preflight verifies the existing isolated actual promotion after-tree against the
fixed plan, then audits the complete real old baseline under a Python audit read
guard. Reads of the five live replaced paths, two replaced software paths and
three new live headers fail immediately; scanning live hardware/include also
fails. Unchanged pinned live headers are still individually verified. The guard
forbids subprocess launches. This is a host isolation proof, not simulation or
proof that the promoted canonical image works. No old output is rewritten.
