# FP32 Host And Compile Receipt Review

Decision: **ACCEPT_HOST_NUMERICAL_EVIDENCE; LINKED_COST_PENDING**.
No reference/DUT admission. Independent read-only review of completed receipts,
short logs and pins; no repeated generation, Host or compilation.

Actual supervisor exit0, no timeout,11.845084737986326s. Generation exit0/5.580s.
All22 stage receipt command/log hashes match. Six original/packed C executions
exit0 and each complete17920 calls; five deliberate fixture failures exit90 at
the configured rejection gates, not generic arbitrary nonzero acceptance.
Both Host compiles exit0 with the configured UBSan trap flags.

Original/packed transcripts match for all three modes after excluding the Host
instrumentation line:

| Mode | Original and packed result | Details |
| --- | --- | --- |
| positive | cases17920/errors0 | 0 |
| details | cases17920/errors21 | 20 |
| all_errors | cases17920/errors87712 | 20 |

Each packed mode reports17920 aligned result/guard reads and430080 independent
original-C error/flag comparisons. Source review establishes actual32-bit input
checks,49 fresh events/call, complete upper4032B zeros per bank, all mask/output
initialization and argument order. These are C/fixture semantics, not RVV/FPR
execution or a reference firmware retirement measurement.

The two fixed target compiles each exit0, SoC0.519040401s and Spike0.518602731s.
Both resulting ELF hashes match RESULT.json:

- SoC: `520b652eb8a4d4dc634a17a36a9d5e71c382a4679afeb8aeb54746d18a37be73`
- Spike: `9b6f3e8fa391514816fc6731aeb8b9628d374fbe5f0e1ccb85fb6a2e929e1254`

All76 post-execution source/tool/generated artifact pins rehashed unchanged.
Compilation success does not establish helper/lowering/ABI/cost acceptance;
that remains pending the actual linked CFG ledger and independent review.
No retry or second flags compilation was requested by this reviewer.

## Receipt Bindings

- `software01/receipt01/supervisor.exit.json`:
  `e3de304565c0dffe036f68570d107b16e637b27b44a27711a9aab87620b86bfe`
- `software01/execution01/host/RESULT.json`:
  `fb6a94fc7a2bf7746b51bf3098c8fa18b80cbbce68f715c85a77fed5253f1695`
- `software01/execution01/RESULT.json`:
  `8be9b55f62a2a2c5a9775974848b1e18f23562bfa1445bc55438b085d6b1534e`
- `software01/execution01/inputs_after.json`:
  `3af366d8417ab1876391aac5e6c3386e72cf256b1b0ed50b92615174df9344cb`
