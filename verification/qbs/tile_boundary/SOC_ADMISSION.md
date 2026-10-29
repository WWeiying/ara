# Retirement SoC image admission

The independent build is
`verification/out/qbs-retire-soc-build-20261029-01`.
VCS compiled and linked successfully, and its source manifest check passed.
The original worker then rejected the Bender filelist's option ordering.
Its `result.json` and `status.json` remain FAIL and are not rewritten.

The expected and actual lists contain the same 977 tokens and source order.
The macros and include-directory sets at each source are identical. A recursive
search found no same-relative-name include candidates with different content.
This is recorded separately in `order-audit.json`.

`admit_soc.py` rechecks the original pre-build source pins, build tools and
helpers, canonical graph, compile command, simulator configuration, generated
manifest, compiled-source inventory, VCS diagnostics and image inventory.
Only the two new review scripts are excluded from the historical imported-module
inventory: they were not compiler inputs and are pinned in the new receipt.
No RTL, compiled dependency or original build helper is exempted.

The resulting `reviewed-admission.json` has state
`ORDER_REVIEWED_SOC_BUILT_NOT_EXECUTED`. It admits the image for subsequent
testing; it does not establish ordinary RVV correctness, QBS/AKV coexistence,
projection performance or model-level speedup. Runtime consumers must validate
this separate receipt and its pins explicitly, not relabel the original build
as a clean canonical-worker PASS.

Next gates are an ordinary RVV/coexistence regression and the unchanged archived
M4 Q/V/K projection ELF. Compare each software variant against itself on the old
and new hardware. Keep preparation, execution and total cycles separate.
