# Recovery01 Terminal Metadata Review

Verdict: ACCEPTED_FULL5985_REFERENCE_TERMINAL_METADATA_NOT_DUT.

Exact recovery admission binds entry `b3c6347e7b21c9dd036fc5fabc7f9f699c6e643d9f2b6fb5a5f3b77be5e8a060` and independent review `8df46989c462ea6fa1832e56f2dc0b476dd85adeaa4b1329ea18bf227425c59b`. Freshly verified537 non-raw admission pins, zero mismatches. The existing raw pin was deliberately not reread; its identity matches the preserved firstfailure and recovered result. This is metadata acceptance of the reviewed observer's complete parse, not a second independent semantic parse.

Original Spike PID3424126 exited numeric0 /8.339230659s, no timeout/retry. Original audit numeric1 /78.480145270s and STOPPED are preserved unchanged. Recovery child PID3429196 exited numeric0 /139.632570052s, timeout=false, retries=0 under the600s bound. The durable child wait receipt is verified; no independent outer service/process exit claim is made. There was one original Spike run, no new Spike and no DUT.

Full scope:5985 calls,766080 results,11970 guards,5985 returned-vstart checks, each of13 helper positions5985 times (77805 total), capacity counts[1,1,1]. Fresh520-byte output per call and389025 complete64-bit output reads retained. Expected reads124041, ID reads53865, cache hits33123/fills14757 and389025 actual comparisons. Physical group4=512B; mask memory128B with16B actual predicate. FP1890 calls/483840 input SW/15120 fresh LW; seed writes1104; mask2205 groups/35280 clear SD/154350 cumulative SB. No fflags oracle or DUT backend-token claim.

Firmware to HTIF2,759,763 <3M;5 boot rows+firmware+232 pure-park rows=2,760,000 rows, EOF_checked=true. Raw305618403 bytes is below768MiB. Exact full-scope PASS console has errors0. No helper/oracle waiver for27 VI2 short no-op calls. This measured reference cost does not guarantee DUT walltime or authorize a DUT launch.

Verified identities:
- result.json: `0c889b678ab3a0df9925422139b9eb95f717ec49468d8114e27f91ddfefa9c6b`
- complete.json: `cf6fc263caf017c09303215b55bac810ea94bbf7ea735ea36879981470d7ae4b`
- audit_execution.json: `27a558d624492233a225ea8e209b91521f071097ab053449a1403851c2532d38`
- admission.json: `b7ffd790de650ed44d8e846495381ad07662b5d825041c013975e612d22f6f82`
- consumed raw identity: `4c570d9e9a24d3b0dd2a50dd865c999ac017a8d918efd17b190c30acc941ceee`

No blockers found in these terminal bindings. No Host, compilation, raw hashing/semantic parse, reference or DUT was repeated by this review. Old source/software01 cost HOLD and historical checker failures remain historical evidence, not relabeled successes.
