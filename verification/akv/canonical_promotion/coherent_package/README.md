# Coherent Resource Package Review

PREPARED NOT PROMOTED. This is a review artifact generator, not an application
tool. No existing canonical or sealed proposal file is modified. No Bender,
compiler, simulator, synthesis, container, or library measurement is invoked.
Live source pins and held-AR acceptance remain parent-owned promotion barriers.

## Exact Composition

Accepted receipts are bound by fixed SHA256 identities. Temporary application
order is:

1. `../shared_resources.patch`: three accepted snapshot03 engines/VLSU, seven
   support files, and Bender ordering (11 targets).
2. `../standalone_package/standalone_makefiles.patch`: original-suite preserving
   QBS and AKV Makefiles (2 targets).
3. `../physical_flow_compat_v2/prospective-02/physical_flow.patch`: physical
   metadata and hardware caller (5 targets).
4. Its `standalone_caller.patch`: second-stage AKV Makefile caller correction.
5. Byte-exact accepted `../akv_engine_synth_wrapper.sv` replacement at
   `verification/akv/synthesis/akv_engine_synth_wrapper.sv`.

The result has 19 distinct targets: seven additions and twelve replacements.
Every intermediate tree must have exactly its expected file inventory and
hashes. All five stages are reversed and original bytes/absence recovered.
The combined review patch is then independently applied to that restored
temporary fixture, checked against every final hash, and reversed again.
Git executable bits and mixed CRLF/LF bytes are preserved; no whitespace fixing.
The source's local permission bits (including 0660/0770) are inventoried, not
represented as Git changes or claimed restored by a content patch.
Tests also reject unexpected targets, wrong hashes, unsafe paths and symlinks.

## Host Contract

The generator reruns unchanged accepted host suites:

- physical-flow v2: 46 tests, including the legacy-only unified, QBS-only and
  explicit old-split caller matrix, selected libraries and malformed metadata;
- standalone packaging: 9 tests, original targets/vectors/flags, compositions,
  generic/macro/wrapper routing and archived interfaces;
- measurement wrapper: 5 static interface/owner/endpoint tests.

These suites use inert host fixtures and make dry-runs, not real Bender/DC
execution. Their logs/counts/hashes are saved. The package itself adds nine
host tests; run those before final generation. Inputs include the accepted
receipt/patch/helper/source identities and unchanged compatibility dependencies.
This is a package input inventory, not a newly generated complete EDA filelist.
Referenced historical wrapper elaboration remains elaboration evidence only.

```sh
python3 -B -m unittest discover -s verification/akv/canonical_promotion/coherent_package -p test_prepare.py
python3 -B verification/akv/canonical_promotion/coherent_package/prepare.py --output verification/akv/canonical_promotion/coherent_package/prepared-01
```

Only a fresh output below this directory is allowed. Patches are applied ONLY
inside independent `/tmp` fixtures. Output contains `coherent.patch`, `plan.json`,
`plan.sha256`, and host-suite logs. The plan binds every original/final target
hash, additions' prior absence, serial stages, helper/evidence pins and test logs.
All original inputs and canonical target bytes/absence are checked again after
the tests and composition. No auto-applier or canonical promotion command is
provided. Parent review, terminal source-pin audits and separate authorization
are still necessary; actual canonical graph verification has not occurred here.
