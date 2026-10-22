# Prepared, Not Launched

The nine-case shared checker/runner and `prepared01` are now frozen for Hilbert
entrance review. No DUT, reference, build or live query was performed here.
`prepared01/launch.json` and `prepared01/replay` do not exist.

- Exact9 original SoC ELFs, same frozen M6,1352 pinned files.
- jobs3 / seed1, per-case5400s, unit19800s, worker18900s, noFSDB/no retry/no build.
- Parent-reported mf4 pilot3470.2s is only a limited budget proxy; no additional
  LMUL success or independent mf4 acceptance is claimed by this preparation.
- Launch still requires actual pinned independent mf4 DUT acceptance and a new
  pinned parent authorization. The generated command contains unresolved gate
  placeholders and is not launch authorization.

## Host Evidence

Host01:17 methods/548 recorded checks, original status **HOST_FAIL**, preserved.
All9 complete shape positives, four-shape data/control negative matrices and
all378 unused-helper PC negatives passed. Two duplicated-op0-entry tests were
correctly rejected by the checker but failed their diagnostic-text assertions.
Host01 is not relabeled PASS. It also did not cover the subsequently discovered
RunOptions positional inversion or asynchronous Timer publication race.

Host02:15 delta methods/44 checks **PASS_HOST_ONLY**,37.363s. It binds unchanged
checker, original Host01/script/worker hashes and constrained AST changes;
corrects both diagnostic assertions; validates actual frozen RunOptions jobs3/
seed1 and a process-free dry-run command; reproduces the old real Timer/Event
race; verifies cancel/join and deadline latching; and retests terminal, fresh
disk plan, failure cancellation and the strengthened independent-mf4 proof gate.
The long matrix was inherited with explicit provenance, not claimed rerun.

## SHA256

| Artifact | SHA256 |
| --- | --- |
| prepared01/plan.json | 10807a26d22d6beb48acdd075e3e1ccea37e5ca69f38c783ce2ed9027375891a |
| prepared01/ready.json | c4237b3972fe28b808ce3c2b2cb941ce26462f518a2552cfa1bbbe590d8d5bb1 |
| host02.json | 7d2a76d8ccced172d1de3ceb6aa0606c111db71ec716974b03490eea99d46b68 |
| host02_timer_before.json | e9350d0fbfb50640fa5895caa5b2e5c800e3b71498170e795a8b2751d14793f8 |
| checker.py | 2e92159b44879c96e2faca67cec3744d08c2633d507abd3d0afc91cf6f65ee15 |
| replay.py | ca22d0134b40d53fb14534b853128d1ae20362c8cdd2b289566ab4b44536bab8 |
| test_host02.py | 2e0b987d3736a40b870a25f3e17fe959b6443d30d08eaf7809fef12193408385 |

Independent entrance review is pending. No architectural acceptance is added.
