# Prepared01 Not Launched

Plan d8e001aac8fe165f987e9fac9ded30e38c61233d240a5f4d439c7081b2a51d0d
is retained unchanged. Its actual dryrun exited1 at `Actual ELF specs drift`:
the targets mapping uses integer keys in memory and JSON string keys on disk.
No image or source drift occurred, and no DUT was launched.

Successor replay02 compares both spec objects through the same JSON
normalization. Runtime strict continues using fresh `specification()`; no
checker, oracle, profile, ELF or existing Host evidence is modified. The
successor copies lifecycle functions unchanged and retains their Host pins.
Only a matching-spec/wrong-spec subprocess check and AST equality are new.
ExecStopPost now has explicit TimeoutStopSec360 for its <=300s metadata
collector; case10800/worker12000/RuntimeMaxSec13200 remain unchanged.
