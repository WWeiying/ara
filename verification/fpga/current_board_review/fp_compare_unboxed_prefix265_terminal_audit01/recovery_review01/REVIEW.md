# Command Provenance Failure Diagnosis

The sole argv mismatch is element5, +TESTCASE. Both seeds are1; cwd, private
ELF, image, log, NO_FSDB and CSV destination match exactly. The scope adapter
replay.py:27 stores original_name=rvv_fp_compare_unboxed_unmasked_e16_mf4,
whereas the legacy runner constructs TestCase with the port NAME. The shared
gather_repair05/regression.py:211 incorrectly expects case.original_name here.
Actual +TESTCASE=fp_compare_unboxed_e16_mf4_prefix265 matches the pinned case.id.
The frozen TB uses this label for performance/dump output naming, not ELF choice.

The worker's wrapper invokes strict checking only after a PASS TestResult;
check_artifacts:198 additionally checks numeric returncode0 before reaching the
command mismatch. Frozen runner.py:513 emits trace_summary only after rc0 and
no monitored failure, but runner.py:629 replaces the wrapper exception with
ERROR/None/0.0. Thus rc0 has code-path inference, NOT a preserved numeric wait
record. The generic summary is producer evidence only, not independent oracle
acceptance. No exact subprocess wall elapsed survives;1225.070s is VCS CPU time.

Old complete remains NOT_PASS/aborted=true/pins_unchanged=false; run INTERRUPTED;
summary ERROR/returncode=null. The later pin flag does not by itself prove drift:
all733 original plan pins currently match and the private ELF matches. The
specialized strict_prefix.json is absent because its checker was never reached.
The wait failed closed before audit invocation; terminal01 does not exist.

Evidence and current metadata hashes are in evidence.json. No CSV was opened,
hashed or parsed during this diagnosis. CSV size was stat-only84138571 bytes.
Producer summary reports741981 rows/730922 retirements/lastcycle925939; these
counts are not independently accepted here.

The parent subsequently authorized one separate recovery01 full-CSV audit.
That audit must preserve this ERROR, check actual command against exact port id,
verify source/image/privateELF/raw artifacts before and after, and deliver all
rows unchanged to sealed dut_strict plus lossless observer. It must retain all
265 calls/264 predecessors,4240 bits/530 guards,265 flags/vstart,4587 helper
instructions, initialization/capacity/unused full ranges/PC/exit checks. It may
accept architectural data only, never relabel process metadata or full17920/
Linux closure. A real data failure stops with its first cause and no retry.
