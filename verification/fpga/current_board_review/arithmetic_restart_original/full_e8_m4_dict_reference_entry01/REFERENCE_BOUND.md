# One Reference Entry

The actual executor was read after the source-only review. Its exact hash and
the software pin-set identity are bound in reference_entry.json, using the
executor's real NO_BLOCKER/software_pins_sha256 schema. The original review
is retained unchanged.

The declared limits are120 seconds,6000000 executed instructions,768MiB per
raw file, one attempt, profile rv64gcv_zvl1024b. The3000000 firmware-instruction
threshold is a cost target, not the reference step ceiling. A complete result
over that threshold is HOLD, not automatic DUT approval. These bounds are
declared before execution; no failure-driven extension is authorized.

Executor saves actual Popen.wait returncode before its sole raw audit. The
observer requires4095 ordered13-instruction helper windows, exact initialized
source/mask/sentinel bytes, original CSR/arguments, full physical vector
results and65 scalar oracle reads (64 words plus final halfword) per call,
returned vstart zero, original complete console and HTIF success1. It verifies
actual counter agreement and source pins again. No reference was run here.

The declared executor must remain unchanged. Owner retains its pre-execution
hash/command and post-execution identity; all old Host failures remain intact.
This permits the single software reference, not a simulator or RTL build.
