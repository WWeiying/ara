# Independent M6 Unboxed265 Data Recovery

Status: **ARCHITECTURAL_RESULT_ACCEPTED_PROCESS_METADATA_ERROR**.
One authorized offline audit, actual PID1435758, actual audit command exit0.
Audit elapsed84.71279346942902s. Command/invocation and exit observation are
recorded separately; no simulation, reference or retry was run.

## Actual Data

- One complete CSV parse,741981 original rows delivered unchanged and in order;
  730922 retired instructions, firstcycle82, lastcycle925939.
- All265 original natural calls and264 predecessors;4240 result-bit checks,
  530 guard checks,265 actual fflags reads,265 returned-vstart reads all0.
- Exact4587 helper instructions: op0..3 each56 complete17-instruction windows,
  op4 has41 complete19-instruction windows. Five entire unused helper ranges
  have zero retirements. Every retired PC/encoding matches actual pinned ELF.
- Actual initialization stores76850: mask33920, a4240, b4240, output34450;
  original values/address/BE/order checked. Capacity16 via all3 instructions;
  all6 legal bootstrap/CSR prelude instructions and operands checked.
- Historical first-failure call265 is op4/VL15/mode0/sticky0. Actual target
  PC0x80000602, encoding62805c57, cycle922695, retired ordinal729316;
  all16 bit reads plus2 guards passed, actual flags0 and vstart0.
- All41 fmv.d.x f0,t2 instructions and integer source0 checked. This is not
  direct FPR payload evidence.265 saved-zero flags restoration writes checked;
  final post-restore CSR state has no additional readback and is not claimed.
- Actual CTRL exit0 at PC0x80000072, order730915, cycle925930; only6 original
  parking retirements afterward. Firmware retirement to exit730916.
- CVX2653 requests/responses, architecture2653;1550 uop allocations/completions;
  no replay, exception or outstanding IDs. Recomputed generic dictionary equals
  the saved producer summary. Strict original oracle was independently rebuilt
  through sealed dut_strict, not a missing producer strict_prefix.json label.
- Raw console and run.vcs.log retain exact265-case original PASS/finish markers;
  firsterror/failure vetoes pass. VCS CPU1225.070s is not subprocess wall elapsed.

## Identity And Metadata

761 unique pins match before/after, including733 original plan pins and19
recovery evidence paths (overlap counted once),539 frozen source files and66
image files. Image/configuration/manifest/privateELF identities match frozen M6.
The actual command matches the exact port case.id including seed1, cwd and all
paths. Only the legacy expected TESTCASE used historical original_name instead
of the port id; no other command-schema discrepancy was waived.

Old complete remains NOT_PASS, aborted=true, pins_unchanged=false; run remains
INTERRUPTED; summary remains ERROR/returncode=null/elapsed0.0 with Command
provenance mismatch. All are unchanged and included in recovery pins.
The earlier numeric0 gate and producer trace-summary creation imply rc0 along
the sealed code path, but no persistent numeric wait result survives. Therefore
simulator child rc and outer service rc remain UNKNOWN/null. This report does
not rehabilitate the batch/process contract or invent a TestResult0.

## Hashes

- Result: `0d468b20b1117c596023594be63c5abe7174e29045a14a53bbbea2b47850b479`
- Verified pins: `b68228f17b8988e28076674abdbea21ef56ae2e1b3494b025b33c047c5e1d9ac`
- CSV: `87b7e5b970b36b0f9aa129cb7456822ac189955a306d4efc621dbf720daff93d`
- Before/after row digest: `a6b8613eb4e1a3e7350a497ba8a13aa8f1920a57957c829ca25b5639657a6897`
- Old complete: `54d4d1a6b91e5de466a777a9d02fc12e2bb3180288ebfc64ec3bcbca448d3b04`
- Plan: `e3bbb288f69f8f0cc0a24491125e0bb327e04d3edbaa3eb46837bb2c153e0940`
- M6 image: `a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0`
- ELF: `03e24bc51c28b705ae3cd373a51c38e04c39ab0eb26443d29ca7d36277741058`
- Recovery script: `be40689e59def4045da5713315832583658e19e34bd67e5aab78c2be93afb7fd`

Acceptance covers original natural prefix265 only, preserving original tail
allowances and full oracle. It is not full17920 parent or Linux closure, not
reference substituted for DUT, and not validation of newer workspace RTL.
