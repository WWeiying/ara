# Exact Canonical Bender Rendering

The first canonical build compiled successfully, but its original worker rejected
the generated filelist's formatting. Its FAIL receipt remains unchanged under
`verification/out/canonical-shared-resources-build-20261025-01/`.

`template.f` is the byte-exact generated artifact, SHA256
`e1670b96487792e24c296c831fbb894e8c14772fdf9f3df819ee3ced79a73644`.
It is not a filelist with substituted source paths or relaxed hashes.

Before admitting this one rendering, `graph.expected_graph()` compares it to the
original pinned dependency template plus the four reviewed source insertions:

- All 977 tokens and their multiplicities must match.
- All 439 source entries retain exact order, including inherited repetitions.
- Each source sees the same effective macro values and include-directory set.
- All seven global include directories remain present. Reordering is allowed
  only after checking that no relative header name has competing definitions.
- Dynamic and parent-relative include directives require separate review.

The new build still compares the actual generated list to this exact pinned
rendering. It does not accept arbitrary future permutations. Original promotion,
source/header hashes, duplicate-source, configuration, compiler argv and lint
checks remain active. `inputs()` adds the new helpers/template and full include
inventory to pre/post pins; no original source identity is translated or waived.

```sh
python3 -B -m unittest discover \
  -s verification/akv/canonical_promotion/canonical_graph_v2 -p 'test_*.py' -v
```

Host equivalence tests are not a functional RTL result. The successful compiler
exit in the preserved failed worker is not relabeled as a successful build gate.
A fresh guarded build and actual same-ELF regression are still required.
