# Canonical Build V2

Successor wrapper only. `canonical_soc/build.py` at commit `e3f75073`
(SHA-256 `99063bec061c3417cddb2a17555d5348822d05779c1c65406d668551017762fa`)
is loaded read-only and its `run` code is cloned with a private globals dictionary.
Only `expected_graph` and `auxiliary_inputs` are replaced. No module monkeypatch
is used; all other helper functions retain their original globals.

The parent-owned `canonical_graph_v2/graph.py` supplies `expected_graph(oldtext)`
and `inputs()` (path to SHA-256). The original exact-token `check_graph`, nineteen
after-hash promotion guard, source/image/configuration inventories, actual VCS
argv and lint gates remain unchanged. The new template is not a token-set waiver.
All graph inputs plus these three files are mandatory build inputs:
`build.py`, `test_build.py`, `README.md`. Graph input digests are verified before
merging; conflicting pins fail closed. Original auxiliary inputs are retained.

CLI matches the original: `python3 -B build.py --output FRESH_DIR
[--timeout 7200] [--execute]`. Without `--execute`, no compilation is requested.
This directory does not authorize EDA: parent root-cause/template review and
explicit approval are required first. No source promotion is performed here.
The receipt remains `canonical_soc_v1`, since this is the same actual-root
compile workflow. The old failed worker remains failed; no PASS is inferred.

Host tests: `python3 -B -m unittest discover -s
verification/akv/canonical_promotion/canonical_build_v2 -p 'test_*.py' -v`.
Tests use private clones and temporary fixtures, not EDA. Freeze these files
after parent approval; subsequent changes require a successor directory.
