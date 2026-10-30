# Historical Canonical Inputs

Source/history archive only. No canonical promotion, EDA execution, image
acceptance, runtime PASS, automatic patch application or old-worker replacement.
All outputs and implementation live in this new directory. Existing proposals,
receipts, sources and images are untouched.

## Fixed Contract

`archive.py` admits exactly six original receipt SHA256 values and five changed
canonical path/SHA256 pairs. The archive copies, without symlinks:

- Those five files, plus unchanged `Bender.lock`.
- The complete historical `hardware/include` directory, including `.sv` packages.
- The six original manifests/receipts, unchanged byte for byte.
- Every `.f`/`bender_script*` file pinned by those receipts (four actual paths).

`manifest.json` uses relative payload paths, retaining the original absolute root
only as the identity namespace of the untouched receipts. Moving the archive
does not change its manifest hash. Consumers must supply an independently
reviewed manifest hash, not trust the adjacent hash file as an authentication
source. A changed receipt/hash, symlink, extra archive file/header or missing
file is rejected. The copies are physical bytes, not references to the live root.

The API is:

```python
old = Archive(archive_directory, reviewed_manifest_sha256)
pins = old.pins(exact_original_receipt_relative_path)
mapped = old.mapped_pins(pins)
verify_pins(mapped)
historical_include = old.historical_include()
```

Only the five allowlisted paths are relocated, and only at their exact original
hashes. Every other pin, including Bender.lock and existing live headers, still
requires its original hash. `mapped_pins` does not invent image acceptance or
make arbitrary new receipts historical. Use `pins()` to consume one of the six
bound receipts; the lower-level mapping method also supports checked subsets.

The two old software source bindings remain exclusively owned by the existing
`ordinary_resource/historical_sources.py` contract. Preflight composes its
unchanged `HistoricalSources.translate()` with this five-path mapping. It never
adds those software paths to the canonical allowlist, rewrites their receipt,
or copies current software as the source of the old ELF.

## Historical Compilegraph

The old include scan MUST use `historical_include()` / the sealed
`payload/hardware/include`, not current `hardware/include`. New canonical
admission/shared-reader include fragments must not enter the old graph. Existing
headers remain checked; they receive no implicit permission to change. Original
filelists are copied EXACTLY, with their original absolute path strings. They are
provenance records, NOT runnable rebased filelists. This helper does not yet rebase
the complete graph or replace the old `vcs_source_manifest --check` invocation.

After promotion a new canonical gate needs a new current-source/current-image
receipt consumer, with this archive for historical provenance. Old `checked_soc`
and `checked_image` cannot be called unchanged: they recheck the old current-root
hashes, and the former also expects an overlay-specific receipt. Do not modify
old receipts, update their hashes to current canonical bytes, or drop source pins.
Preserve old ELF/image/raw/UVM evidence independently; this archive does not
contain or establish all those execution artifacts.

## Host Validation

```sh
python3 -B -m unittest discover -s verification/akv/canonical_promotion/historical_inputs -p 'test_*.py' -v
python3 -B verification/akv/canonical_promotion/historical_inputs/archive.py \
  --output verification/akv/canonical_promotion/historical_inputs/archive-01
python3 -B verification/akv/canonical_promotion/historical_inputs/preflight.py \
  --archive verification/akv/canonical_promotion/historical_inputs/archive-01 \
  --reviewed-sha256 REVIEWED_MANIFEST_SHA256 \
  --output verification/akv/canonical_promotion/historical_inputs/preflight-01
```

Preflight verifies all six complete pin sets using the separate software-history
contract, then applies the pinned coherent patch ONLY to a fresh isolated partial
tree. All 19 promoted target hashes must match. It exercises consumption of the
five original hashes after those five live counterparts change, unchanged
lock/header checks, and the sealed seven-file include scan while the after-tree
contains three additional headers. This is not a complete old-worker invocation
or complete buildgraph relocation. Pre/post pins are rechecked; no compiler,
Bender, container, simulator or library measurement is invoked.

Only `git apply` is invoked by preflight, confined by its working directory and
`GIT_CEILING_DIRECTORIES` to the fresh tree. The real canonical tree is never a
patch target. Preparation requires the old before-state and fails after promotion;
reading an already reviewed archive is independent of the five live before-bytes.
