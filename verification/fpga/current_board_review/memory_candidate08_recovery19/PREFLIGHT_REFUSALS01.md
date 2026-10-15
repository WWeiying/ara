# Preparation Refusals Before Any Launch

Both attempts stopped before creating prepared01 or starting a DUT.

1. A command mistakenly supplied literal PLACEHOLDER as the build handoff hash;
   the exact-hash gate rejected it (command completion chunk 8f6088, exit1).
2. The initial delta gate expected exactly one changed snapshot hash. It rejected
   the real M8 snapshot (chunk fe5cb0, exit1): in addition to AddrGen, generated
   frozen.filelist and hardware/bender embed the relocated M8 root. Direct byte
   comparison showed only that root relocation in those two files.

The corrected gate permits only those two named generated files, and requires
their bytes to equal the old bytes after the exact old-root/new-root replacement.
All other source hashes remain identical except the fixed reviewed AddrGen SHA.
host01.json is retained; host02.json adds a real relocation/corruption negative.
No build, simulation, software oracle, delay, or per-case timeout was changed.
