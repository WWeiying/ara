# Work05 Independent Software Review

Verdict: **NO BLOCKER for work05 software conversion and recorded reference evidence.** This is not dynamic checker/worker entry approval or DUT acceptance.

## Exact Binding
- READY SHA256: `06197d69f8e3767e358b0dacdb6020147f8b1dcf7c9961fd20f5929436a0941a`.
- Reference status SHA256: `348017eedaff3f98b8fd7b9eb52506a3c73e7c269ac015b737ccc5860dc018c5`.
- Independent static review actual waited exit0, 2.793405s; 227 distinct pins verified across READY(126), PRE_REFERENCE(185), original inputs(27), identity report(8).
- Scope: all requested original first482/481 predecessors, not full22400 or original Linux history. Original C text recovery is explicitly false; retained reconstructed source has complete original Linux ELF byte identity `608e941760443563f055058d60f18ce466a06d016fb277989fc332ed9cdb347d`.

## Checked
- Exact original RNG source slice and all512 input bytes; seed0/op0 order: six VL groups0/1/2/3/256/511, each80 calls, followed by VL512/mode0/accumulator0 starts1 and256. Five accumulator patterns, four masks, physical128-byte predicates with upper64 zero retained.
- Independent static reconstruction matches every saved model row, archived expected input/output hashes, actual Host capture and ROM words. Original/optimized captures each1077752 bytes, SHA256 `89f6f8a1eee5ca8d8dc5a8bd549df94024b612954b42faa41ebfd2f20ab20044`.
- All482 calls retain512 result bytes plus two guards:246784 results/964 guards. Positive oracle is65 aligned64-bit reads per call; final read checks only low16 bits. High six bytes out514..519 are outside the original oracle and remain permitted. Host evidence has10 rejecting mutation pairs and one permitted-extra-byte pair, plus original/optimized positive executions.
- Both SoC/Spike ELFs contain exactly the same original13 helper bytes as the retained original Linux ELF (unique byte sequence):6266 helper retirements recorded. All original assembly helpers remain; no added vector validation instructions.
- Low returned vstart zero and original high-word zero/status-container check remain. Do not label the high word as independently sampled fflags/vxrm/vxsat.
- Tables257668 bytes, physical a/b1024/out1026/mask128 retained; aligned scalar setup adds redundant fresh a/b/mask copies without changing values/order of helper calls. SoC BSS ends0x80040f10, stack0x800ffff0; both backend metadata reserve64KiB and conservative C-frame sum496 bytes. This is scalar scheduling/alignment change, not Linux ABI or exact microstate preservation.
- Producer reference actual child0/2.123902s, full482/13 ledgers,31330 output reads, actual HTIF1 and original pass markers. Minstret835145 includes boot5; firmware to replay_exit entry835140, through HTIF835146. Cost is not measured M8 time.
- Original16,438,522 to835145 reduction94.92%. Work05 legacy estimate2266s remains historical. Main reports successor independent proxy about5552s; final worker budget must use its current sealed evidence, not silently inherit the earlier proxy.

## Boundaries
- No repeated Spike, Host executable, compiler, DUT, or raw parser; raw files only hashed as pinned immutable inputs. FP682/background jobs untouched.
- Failed preparation attempts retained and are not RTL failures. The historical optimization.diff includes the already-corrected message-escaping draft; actual final case.c, syntax receipt, compiled ELF and Host code were reviewed, not that stale diff as final authority.
- Confucius may proceed with checker/worker sealing. Review of that successor should focus on real RVFI data/masks, full65-read low16 final-word rule, exact13 windows/unused helpers, justified M8 reset profile, six-event lifecycle, durable numeric exit/abort/pins and exact final plan binding. No need to repeat this software/reference review.

Review script SHA256: `c89534b3f4fb418159feabe377d067a8fa213d408c57eac404db89755cd56000`.
