# Build Execution Review

These seven host-only tests complement the fourteen policy tests in
`../canonical_soc/`. They run the actual builder's execution/finalization code
with an in-memory tool interface and temporary synthetic build artifacts. No
compiler, Bender or simulator is launched. Production helpers remain unchanged.

The tests verify that a successful build records one compile and zero simulator
runs; a preflight launches nothing. Compiler failure, source drift, a missing
executable, a wrong-root manifest or an unplanned compiled input must instead
produce a failed receipt. Temporary process state is cleared on both paths.

```sh
python3 -B -m unittest discover \
  -s verification/akv/canonical_promotion/canonical_soc_review -p 'test_*.py' -v
```

Graph ordering, promotion hashes, configuration and command-policy checks remain
covered by the original policy suite. This review replaces those interfaces
only in its private test module to reach the later execution paths. Synthetic
artifacts are not functional RTL evidence and do not authorize promotion.
