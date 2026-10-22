# Full4095 Reference Metadata Acceptance

Decision: **ACCEPTED_SOFTWARE_REFERENCE_NOT_DUT**. The sole reference consumed
the exact independently cleared entry02. No rerun, reference retry, compiler,
Host test, DUT or raw semantic reparse was performed by this reviewer.

Fresh metadata/pin audit actually exited0 (session38529, completion2bcf54):
all152 preflight identities match; READY/result/entry hashes and actual numeric
receipts agree. Raw file size matches71709283 bytes; its contents were not read
or rehashed here. Full raw semantics and digest remain backed by the one
previously reviewed parser execution, not a claimed second independent parse.

- Spike PID3087560 actual wait0,1.972304471s, timeoutfalse/retries0.
- Parser PID3087575 actual wait0,24.226088080s, timeoutfalse/retries0.
- Full4095 calls,262080 results,8190 guards,4095 returned-vstart zeros,
  all13 helper positions4095 times,53235 helper instructions.
- 36855 complete packed output reads,1575 mask setups,552 source input stores;
  one physical register per fractional group,64 observed bytes,8 vlm bytes.
- Firmware through HTIF561831, plus5 boot and3164 side-effect-free park records
  =565000 total parsed records. EOF checked. The finite4M command is a ceiling,
  not an expectation of exactly4M observed retirements. Firmware is below3M.

The driver's1668.929s VCS projection includes20% margin at the reused403.97
retire/s comparison rate. It is an estimate, not observed DUT performance,
new launch permission or full arithmetic22/Linux acceptance.

| Evidence | SHA256 |
| --- | --- |
| READY.json | 7327fc1457c47dc44f16c9d9f556251e3184058084486293d494d54d423f3f18 |
| reference01/result.json | 73d17b49dae9051e870752d3b70a2d72ec03c203db3fa8a22e47dab33aa94cf9 |
| execution.json | 5707291ba3fac4f99ff0f507bdbc97ee3e868056a5f551655b008971bd751ba8 |
| audit_execution.json | 4259195eb760fd44c6f671b88c4cb084b722883d1337d6209db35290121b8546 |
| command.json | 53e4a014794c409a9142fc1008236b19ddcdea98fbd01d2713a85099fe3fa0a8 |

Original sealed draft, source files and all execution evidence remain unchanged.
