# Full482 Plan03 Entry Review

**APPROVED_M8_FULL482_ENTRY_NOT_DUT_PASS. No blocking findings in the terminal-only successor.**

Exact plan: `7ff93716f73ad92ccaf3327f44de076909944b4cf7091709141feeabdfc78ece`.
Source READY unchanged: `06197d69f8e3767e358b0dacdb6020147f8b1dcf7c9961fd20f5929436a0941a`.

- All858 plan pins and bound Host evidence freshly verified. Read/hash review process actually waited, exit0, 1.567810s. No new tests, reference parsing, Spike, compiler or DUT.
- Worker remains byte-identical to02 (`bcdb7357e55131e61ef345f1260799d878cab98c44b5a5eca3e0ba3c92a89741`); checker unchanged (`ad52594870b9cbae5e20eb29e11f7e8feb5e8b952d507af24941546b872d0cc6`). Actual spec/profile/ELF/budget match02. Old21 tests inherited, not rerun.
- New terminal helper SHA `495a2f91dde233c040eea231531d414b734184100b7c33a88dda98b6070ec718`. Host SHA `eb7571fc452e62547530ab2d56861197711fe1ee559cd8e4325e578042a1682e`: actual10 tests, waited child0/4.218216s. Separate real SIGTERM children during fsync and rename both assert final NOT_ACCEPTED and exit1. Started timer cancel/join, write-time expiry, prepublication fsync failure, no overwrite and postdecision cancellation covered.
- Expensive checker/hashes remain outside the terminal lock. Timer is cancelled and joined; absolute expiry still checked. Restore signal mask before the single locked closure decision. Previously triggered abort cannot be silently cleared. Required NOT_ACCEPTED correction completes before nonzero return; failed correction removes candidate PASS and raises.
- **Linearization:** locked `abort.closed=True` after signal-mask restoration freezes cancellation; check frozen abort and absolute expiry once. Later cancellation does not reopen that decision. No infinite next-instruction signal rechecking.
- **Acceptance:** final record alone while worker is alive is only a candidate. Require actual worker numeric exit0 plus final PASS. Do not infer worker0 from collected service state. File fsync + atomic visibility is claimed; directory power-loss durability is not.
- Previously reviewed owner scope remains2410 CAP-memory +182 active targets (including45 actual all-off), individually matched, not a fixed uop count. Full482/246784 results/964 guards/original6266 helper instructions, final-read high6-byte permission, reset-known profile, numeric-monitor-before-postcheck and exact direct service gates unchanged.
- Exact same jobs1,10800 case/12000 worker/13200 service, no retry;5551.74s remains a proxy, not measured M8 duration.

Confucius may perform the once-only authorized launch using this report's actual path/hash and runtime gates. Reviewer has not launched. Prior plan01/02 and HOLD remain unchanged. Scope is requested natural first482/481 predecessors, not full22400 or original Linux history.
