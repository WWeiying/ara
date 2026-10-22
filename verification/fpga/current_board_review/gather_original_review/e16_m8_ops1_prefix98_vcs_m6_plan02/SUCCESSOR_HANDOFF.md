# Plan02 Narrow Checker Repair

Prepared, not launched. Averroes review requested directly; this document is not
independent approval. The plan and pinned helpers are now fixed for that review.

- Plan: `prepared01/plan.json`, SHA256
  `e4476bec15fadab91251915d44bc156e24c9191abd0aea0359a32d372336f5c2`.
- Worker SHA256: `4c1a1e04805039c70482e3e0fb93c4565709fc72a6a98f07c881cd8ba61174d7`.
- Checker SHA256: `4b6c426a5938d597eb2b0fa01954a427d196fb991834055731ca8804b0e6b8cd`.
- Host: `host01.json`, 24 tests PASS, 28.488s. New test consumes the retained
  `RVV_PERMUTE_DETAIL op=1 seed=0 scalar=0 vl=1 mask=0 element=0 vstart=0 expected=61881 actual=61880`
  line, also truncated before `expected=`, with no final FAIL and no newline.
  Both the runtime VETO regex and terminal console gate reject it immediately.
- Checker diff is exactly the explicit `\bRVV_PERMUTE_DETAIL\b` alternative.
  Worker diffs are only host count23->24 and service name01->02.
- Old plan01 SHA remains
  `55e99bd7056dbfaaf6e1e5a71c1df55ddea66fddf68041071b8e2cf27d27dbd0`;
  all708 old pins rehashed unchanged. New708 pins validate; all701 pins outside
  the old owned directory have identical values in the successor.
- Source/SoC ELF, image/image SHA/snapshot SHA, case/spec, jobs1, timeout9000,
  outer10200, reservation, no-build/no-retry/no-FSDB and budget match plan01.
  Copied reference auditor and reference audit JSON are byte-identical.
- `prepared01/ready.json` contains the exact future direct service command for
  `ara-gather-e16m8-prefix98-m6-02.service`. No command was launched.

This repairs a launch-checker defect, not a DUT failure. No RTL, original source,
reference evidence, old sealed helper or old log was edited. Full natural98 scope
and full oracle remain mandatory; historical exact stopped tuple remains unknown.
