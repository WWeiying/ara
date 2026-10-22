# Full E8 MF4 O2 on Frozen M9

One continuous original4095-call source-port: cap32, three seeds,25 operations,
131040 results,8190 guards,4095 vstart returns,53235 helper instructions.
C/main/runtime/model and original helper bytes are unchanged; only -Os to -O2.
Reference READY f3eba77f2abd2fd1a9ad43eca00f26216ad1ad6c9cdbeceabd9a77d9f2751fe0:
4447579 actual firmware instructions; conservative measured-rate projection
9282.033s includes20percent plus300s check margin. This is not measured M9 time.
Case10800s, worker12000s, service13200s, jobs1, no retry/build/FSDB.

Checker is a cap32 specialization of full_small2's full RVFI checks, with
the mature O2 failure.part.* entry handling and exact M9 reset profile bound
to the ten unchanged reviewed reset/trace RTL files. It checks actual memory
address/BE/register value, original initialization/call order/whole oracle,
CSR bootstrap, actual CTRL raw0 exit (not Spike HTIF), UART and failure veto.
The generic trace checker remains enabled by the unchanged frozen runner.
An added lossless observer requires matching architecture and backend owners
for all20475 nonempty setup/result memory helpers; complete removal of one
alloc/done pair must fail. Target memory operations remain separately matched.

Independent entry JSON schema: status=NO_BLOCKER_ENTRY_REVIEW, plan_sha256,
image_sha256, reference_ready_sha256, scope=[arithmetic_full_e8_mf4], pins equal
the exact plan pins. Supply --entry-review and --entry-review-sha256 at run.
No borrowed approval. Terminal systemd environment is recorded by ExecStopPost;
missing service facts cannot be interpreted as exit0. Reference is source-port
history, not original Linux execution or closure of all22 original shapes.
