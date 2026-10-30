# Prepared canonical RTL patch

Preparation only. Do not apply this patch while an old-source/image consumer
is still live or before the remaining interface and regression gates close.
No production file was changed by this preparation.

`plan.json` identifies every before/after hash. `shared_resources.patch` contains
the three byte-exact accepted snapshot03 RTL replacements, seven support files,
and only four dependency-ordered Bender source insertions. Existing old context
definitions remain available; they are not instantiated by the unified engine.
No package/ISA, Lane, sequencer, memory macro configuration or lockfile change
is included. FPGA vendored RTL is outside this patch.

The accepted snapshot manifest is
`verification/akv/shared_reader_integration/snapshot-03/manifest.json`, SHA256
`035ac16298960fafbe2de94a764af5ad80bf08e0c62fdd0d424369d800b3b72f`.
Support bytes come from its `support/`, not from regenerated candidate sources.
All ten HDL outputs match the accepted artifact pins. The Bender edit preserves
all existing lines and inserts the shared reader after `qbs_read_engine`, then
the repacker, Q store and unified context after `akv_v2_context`, before engines
that instantiate them. Include fragments are not standalone compilation units.

## Dry run

`dry-run.json` records a real isolated application, not just a prepared patch.
After checking the manifest/artifact pins and current canonical before hashes,
the four existing files were copied to a fresh temporary directory. Standard
`git apply --check` and `git apply` succeeded there. The resulting tree contained
exactly the eleven expected files, each matching its planned after hash. All
current canonical targets were rechecked as unchanged afterward.

The read-only applicability check can be repeated from the repository root:

```sh
git apply --check verification/akv/canonical_promotion/shared_resources.patch
```

This command is not permission to apply the patch. Applicability and matching
bytes do not prove functional integration, timing or production readiness.

## Before final application

Use `../results/shared-storage-canonical-promotion-checklist-20261025.md` for
the complete interface/source-graph obligations. In particular:

- Finish and audit live consumers before changing either canonical sources or
  include-directory contents; archived images may still check current sources.
- Complete the ordinary RVV Attention and integrated fault/drain gates.
- Adapt the standalone compile/check entries using the archived port contracts;
  preserve original TB stimulus, vectors, assertions and generic/macro modes.
- Adapt the measurement wrapper's external reader connection and old macro
  hierarchy assumptions without running synthesis in this stage.
- Include those packaging changes with this RTL patch as one coherent final
  promotion, then test the actual canonical Bender/source graph.

Do not present this prepared patch as already merged or as a new performance
result. Completed resource runtime and legacy-latency evidence is recorded in
the successor documents under `hardware/docs/`.
