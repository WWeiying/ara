# Canonical promotion live-pin inventory

Process snapshot: 2026-10-25T01:13:44.159485+00:00.
Root: `/home/wangwy/openproject/ara_dsa_signoff_integration`.

One process/service inventory, followed by read-only receipt and source inspection; no subsequent process refresh. This is an as-of observation, not a claim that processes remain live when this note is read. Service and /proc enumeration is not atomic. No services launched, stopped, or polled repeatedly; no existing files modified. This note is the only new artifact.

## Summary

Nine actual running simv processes, plus one waiting coordinator. Five requested jobs already terminal PASS. No active canonical-standalone build remains in this snapshot.

All nine simulation workers AND the coordinator pin the same 66 canonical files: 2 Bender files, 7 include files, 57 hardware/src files. The ten pin maps match exactly; their 66 current file hashes were read and verified with zero mismatches. This verification covers this canonical subset, not every transitive tool/software/artifact pin.

Canonical promotion remains blocked by all ten consumers, including overlay-image workers: their postchecks still verify canonical inputs. Completed standalone tests are not live blockers. Do not infer permission to change source inventory or add headers from this file-key inventory.

## Live owners

| Service | Owner PID | simv PID | Output |
|---|---:|---:|---|
| shared-reader-real-prefill-20261025-01.service | 1108886 | 1109285 | /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared-reader-real-prefill-20261025-01 |
| shared-reader-real-quant-q8-20261025-02.service | 1112334 | 1112606 | /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared-reader-real-quant-q8-20261025-02 |
| shared-storage-real-decode-20261025-01.service | 1126258 | 1126479 | /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared-storage-real-decode-20261025-01 |
| akv-quantkv-tail-split-coordinate-20261024-01.service | 1121062 | none | /home/wangwy/openproject/ara_dsa_signoff_integration/verification/akv/quantized_kv/tail_split/out/coordinator-01 |
| shared-reader-real-quant-q4-20261025-02.service | 1112326 | 1112641 | /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared-reader-real-quant-q4-20261025-02 |
| akv-timed-decode-unified-20261025-01.service | 1138861 | 1139013 | /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/akv-timed-decode-unified-20261025-01 |
| akv-timed-decode-baseline-20261025-01.service | 1138856 | 1138904 | /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/akv-timed-decode-baseline-20261025-01 |
| akv-quantkv-tail-split-q8-v33-20261024-01.service | 1109910 | 1110443 | /home/wangwy/openproject/ara_dsa_signoff_integration/verification/akv/quantized_kv/tail_split/out/run-q8-v33-01 |
| shared-storage-real-prefill-20261025-01.service | 1126261 | 1126591 | /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared-storage-real-prefill-20261025-01 |
| akv-quantkv-tail-split-q4-v33-20261024-01.service | 1109905 | 1110464 | /home/wangwy/openproject/ara_dsa_signoff_integration/verification/akv/quantized_kv/tail_split/out/run-q4-v33-01 |

All listed simulator processes were state R; Python owners state S. Each observed owner/simulator belongs to its named service cgroup. Full argv, cwd, parent PID, and start ticks follow below.

## Terminal requested jobs

Both status.json and result.json reported PASS, with post_pins_match=true and no child PID. No corresponding live owner was found in the process snapshot. These are receipt observations, not a fresh raw numerical/protocol re-audit.

| Job | Former owner | Output |
|---|---:|---|
| tail q4 v5 | 1109903 | /home/wangwy/openproject/ara_dsa_signoff_integration/verification/akv/quantized_kv/tail_split/out/run-q4-v5-01 |
| tail q8 v5 | 1109908 | /home/wangwy/openproject/ara_dsa_signoff_integration/verification/akv/quantized_kv/tail_split/out/run-q8-v5-01 |
| shared-reader decode | 1108879 | /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared-reader-real-decode-20261025-01 |
| canonical standalone QBS | 1142065 | /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/canonical-standalone-qbs-20261025-01 |
| canonical standalone AKV | 1142070 | /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/canonical-standalone-akv-20261025-01 |

Superseded shared-reader-real-quant-q4-0-20261025-01 and q8-0-20261025-01 are terminal failed attempts, not the live q4/q8 -02 successors. They are not counted as PASS or live blockers.

## Coordinator is a source-pin blocker

The live coordinator (PID 1121062) was WAITING_OWNERS with no child process. Its pins are in pre-wait-pins.json, not yet source-pins.json. It merges all four tail source-pin maps plus target build/prerequisite pins (tail_split/coordinate.py:159-204), writes and verifies the pre-wait receipt (lines 261-267), waits using pidfds, and verifies again before combine/preflights (lines 284-308). On success it starts two directly owned services (lines 309-311 and start_services at lines 210-236):

- akv-quantkv-threeway-split-20261024-01-q4.service
- akv-quantkv-threeway-split-20261024-01-q8.service

Their output directories are coordinator-01/threeway-q4 and coordinator-01/threeway-q8. These are planned future consumers, NOT observed running simulators in this snapshot. Waiting only for the nine current simulators is insufficient: the coordinator may create successor consumers. This inventory neither stops nor authorizes changing that pipeline.

## Why pins block promotion

- tail_split/run.py:83-85 defines identity verification; line 119 checks it after the run.
- shared_reader_integration/run_real_runtime.py:92-94 verifies the full pinned map; line 119 repeats it after evidence checking. run_real_quantized.py delegates to that same run() and only changes counter flags.
- paired_heads/timed_decode/run.py:60-62 verifies the map; line 97 checks it before terminal PASS.
- tail_split/coordinate.py verifies the pre-wait map before and after dependency completion and before downstream launches.

## Manifest identities

| Pin manifest | SHA256 | Canonical keys |
|---|---|---:|
| /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared-reader-real-prefill-20261025-01/source-pins.json | c6fa3f4179df562f783463f3ffcce2d0d16cf9d1fb45abf9f56bc094528d54fe | 66 |
| /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared-reader-real-quant-q8-20261025-02/source-pins.json | 044c947b4259a4404b311996e63c063b748c3da327e66214fbe6bd23b5f0eb6e | 66 |
| /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared-storage-real-decode-20261025-01/source-pins.json | ca2d48fba9180601533398b346ea32bd7ccfae61cc9b6b8752c43e72d776aff3 | 66 |
| /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared-reader-real-quant-q4-20261025-02/source-pins.json | 5f6ae7d5233b44e1d00f34cf5b51098b5057181f7719d56e3f49526a05f7c3e2 | 66 |
| /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/akv-timed-decode-unified-20261025-01/source-pins.json | 1f9b5d21da8f5a3ab1c16f1474df29813d4f03c61549ec8dfa077e9e6478d26f | 66 |
| /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/akv-timed-decode-baseline-20261025-01/source-pins.json | f6706d956456b52f34ddb927d252ce722af9a970a55653da0876a6aa07f6293c | 66 |
| /home/wangwy/openproject/ara_dsa_signoff_integration/verification/akv/quantized_kv/tail_split/out/run-q8-v33-01/source-pins.json | 8563e772a213b980632742dcb6f8b232f5e536f11ac88243e57df3c3d28aab19 | 66 |
| /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared-storage-real-prefill-20261025-01/source-pins.json | 15aa9826c018ad020a90aa8166d2684ac6233c1dadf2200c5b3a774e7065ca5b | 66 |
| /home/wangwy/openproject/ara_dsa_signoff_integration/verification/akv/quantized_kv/tail_split/out/run-q4-v33-01/source-pins.json | 7e93d802655331b8189fae61538593cf9428fc0bbebc03b522c58e32609604e6 | 66 |
| /home/wangwy/openproject/ara_dsa_signoff_integration/verification/akv/quantized_kv/tail_split/out/coordinator-01/pre-wait-pins.json | 557bb3df7a73ef1f0abf832ef6346834deb4e0371b48beb2069668f59a273655 | 66 |

## Exact canonical blocker set

Each path below is pinned by ALL ten live owners above. Paths are relative to root. In particular, promotion replacements hardware/src/vlsu/vlsu.sv, hardware/src/vlsu/qbs/qbs_engine.sv, hardware/src/vlsu/akv/akv_engine.sv and edits to Bender.yml cannot occur while these consumers still require their current identities.

```text
Bender.lock
Bender.yml
hardware/include/akv_pkg.sv
hardware/include/ara/ara.svh
hardware/include/ara/ara_typedef.svh
hardware/include/ara/intf_typedef.svh
hardware/include/ara_pkg.sv
hardware/include/qbs_pkg.sv
hardware/include/rvv_pkg.sv
hardware/src/accel_dispatcher_ideal.sv
hardware/src/ara.sv
hardware/src/ara_dispatcher.sv
hardware/src/ara_sequencer.sv
hardware/src/ara_soc.sv
hardware/src/ara_system.sv
hardware/src/axi_inval_filter.sv
hardware/src/common_cells_compat/fall_through_register_v1.sv
hardware/src/ctrl_registers.sv
hardware/src/cva6_accel_first_pass_decoder.sv
hardware/src/lane/fixed_p_rounding.sv
hardware/src/lane/lane.sv
hardware/src/lane/lane_sequencer.sv
hardware/src/lane/operand_queue.sv
hardware/src/lane/operand_queues_stage.sv
hardware/src/lane/operand_requester.sv
hardware/src/lane/power_gating_generic.sv
hardware/src/lane/simd_alu.sv
hardware/src/lane/simd_div.sv
hardware/src/lane/simd_mul.sv
hardware/src/lane/valu.sv
hardware/src/lane/vector_fus_stage.sv
hardware/src/lane/vector_regfile.sv
hardware/src/lane/vmfpu.sv
hardware/src/masku/masku.sv
hardware/src/masku/masku_operands.sv
hardware/src/segment_sequencer.sv
hardware/src/sldu/p2_stride_gen.sv
hardware/src/sldu/sldu.sv
hardware/src/sldu/sldu_op_dp.sv
hardware/src/vlsu/addrgen.sv
hardware/src/vlsu/akv/akv_context.sv
hardware/src/vlsu/akv/akv_engine.sv
hardware/src/vlsu/akv/akv_refill_order_guard.sv
hardware/src/vlsu/akv/akv_v2_context.sv
hardware/src/vlsu/qbs/qbs_activation_context.sv
hardware/src/vlsu/qbs/qbs_block_adapter.sv
hardware/src/vlsu/qbs/qbs_commit.sv
hardware/src/vlsu/qbs/qbs_compute_engine.sv
hardware/src/vlsu/qbs/qbs_descriptor_decoder.sv
hardware/src/vlsu/qbs/qbs_dot_array.sv
hardware/src/vlsu/qbs/qbs_engine.sv
hardware/src/vlsu/qbs/qbs_fp_accumulator.sv
hardware/src/vlsu/qbs/qbs_half_scale.sv
hardware/src/vlsu/qbs/qbs_payload_buffer.sv
hardware/src/vlsu/qbs/qbs_payload_sram.sv
hardware/src/vlsu/qbs/qbs_profile_decoder.sv
hardware/src/vlsu/qbs/qbs_profile_engine_int.sv
hardware/src/vlsu/qbs/qbs_read_engine.sv
hardware/src/vlsu/qbs/qbs_seed_stream_router.sv
hardware/src/vlsu/qbs/qbs_vrf_seed_mapper.sv
hardware/src/vlsu/store_load_lookahead.sv
hardware/src/vlsu/store_load_lookahead_pair.sv
hardware/src/vlsu/vldu.sv
hardware/src/vlsu/vlsu.sv
hardware/src/vlsu/vstu.sv
hardware/src/vsetvl_preview.sv
```

## Exact observed process commands

### shared-reader-real-prefill-20261025-01.service

PID 1108886; PPID 624596; state S; start_ticks 384568465.
cwd: `/home/wangwy/openproject/ara_dsa_signoff_integration`
cgroup: `0::/user.slice/user-1002.slice/user@1002.service/app.slice/shared-reader-real-prefill-20261025-01.service`

```sh
'/usr/bin/python3' '-B' 'verification/akv/shared_reader_integration/run_real_runtime.py' '--soc-build' 'verification/out/shared-reader-integration-soc-build-20261024-01' '--kind' 'prefill' '--build' 'verification/out/akv-live-prefill-build-20261024-01' '--prior' 'verification/out/akv-live-prefill-20261024-01' '--output' 'verification/out/shared-reader-real-prefill-20261025-01'
```

PID 1109285; PPID 1108886; state R; start_ticks 384570753.
cwd: `/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared-reader-real-prefill-20261025-01/work`
cgroup: `0::/user.slice/user-1002.slice/user@1002.service/app.slice/shared-reader-real-prefill-20261025-01.service`

```sh
'/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared-reader-integration-soc-build-20261024-01/sim/simv' '-no_save' '-l' '/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared-reader-real-prefill-20261025-01/work/run.vcs.log' '+PRELOAD=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/akv-live-prefill-build-20261024-01/akv_live_prefill.elf' '+TESTCASE=shared_real_prefill' '+NO_FSDB' '+NO_INSTR_TRACE' '+AKV_PERF' '+AKV_SUMMARY' '+VECTOR_TRACE=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared-reader-real-prefill-20261025-01/work/vector_trace.csv' '+ARA_CONTRACT_TRACE_LIMIT=2000000' '+ARA_UVM_TRACE_LIMIT=2000000'
```

### shared-reader-real-quant-q8-20261025-02.service

PID 1112334; PPID 624596; state S; start_ticks 384596055.
cwd: `/home/wangwy/openproject/ara_dsa_signoff_integration`
cgroup: `0::/user.slice/user-1002.slice/user@1002.service/app.slice/shared-reader-real-quant-q8-20261025-02.service`

```sh
'/usr/bin/python3' '-B' 'verification/akv/shared_reader_integration/run_real_quantized.py' '--soc-build' 'verification/out/shared-reader-integration-soc-build-20261024-01' '--kind' 'quant_q8_0' '--build' 'verification/out/akv-quantkv-strided-attention-q8-build-20261024-01' '--prior' 'verification/out/akv-quantkv-strided-attention-q8-20261024-01' '--output' 'verification/out/shared-reader-real-quant-q8-20261025-02'
```

PID 1112606; PPID 1112334; state R; start_ticks 384600151.
cwd: `/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared-reader-real-quant-q8-20261025-02/work`
cgroup: `0::/user.slice/user-1002.slice/user@1002.service/app.slice/shared-reader-real-quant-q8-20261025-02.service`

```sh
'/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared-reader-integration-soc-build-20261024-01/sim/simv' '-no_save' '-l' '/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared-reader-real-quant-q8-20261025-02/work/run.vcs.log' '+PRELOAD=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/akv-quantkv-strided-attention-q8-build-20261024-01/strided_attention.elf' '+TESTCASE=shared_real_quant_q8_0' '+NO_FSDB' '+NO_INSTR_TRACE' '+VECTOR_TRACE=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared-reader-real-quant-q8-20261025-02/work/vector_trace.csv' '+ARA_CONTRACT_TRACE_LIMIT=2000000' '+ARA_UVM_TRACE_LIMIT=2000000' '+QBS_PERF'
```

### shared-storage-real-decode-20261025-01.service

PID 1126258; PPID 624596; state S; start_ticks 384739156.
cwd: `/home/wangwy/openproject/ara_dsa_signoff_integration`
cgroup: `0::/user.slice/user-1002.slice/user@1002.service/app.slice/shared-storage-real-decode-20261025-01.service`

```sh
'/usr/bin/python3' '-B' 'verification/akv/shared_reader_integration/run_real_runtime.py' '--soc-build' 'verification/out/shared-storage-integration-soc-build-20261025-01' '--kind' 'decode' '--build' 'verification/out/akv-live-decode-build-20261024-01' '--prior' 'verification/out/akv-live-decode-20261024-01' '--output' 'verification/out/shared-storage-real-decode-20261025-01'
```

PID 1126479; PPID 1126258; state R; start_ticks 384740635.
cwd: `/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared-storage-real-decode-20261025-01/work`
cgroup: `0::/user.slice/user-1002.slice/user@1002.service/app.slice/shared-storage-real-decode-20261025-01.service`

```sh
'/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared-storage-integration-soc-build-20261025-01/sim/simv' '-no_save' '-l' '/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared-storage-real-decode-20261025-01/work/run.vcs.log' '+PRELOAD=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/akv-live-decode-build-20261024-01/akv_live_decode.elf' '+TESTCASE=shared_real_decode' '+NO_FSDB' '+NO_INSTR_TRACE' '+AKV_PERF' '+AKV_SUMMARY' '+VECTOR_TRACE=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared-storage-real-decode-20261025-01/work/vector_trace.csv' '+ARA_CONTRACT_TRACE_LIMIT=2000000' '+ARA_UVM_TRACE_LIMIT=2000000'
```

### akv-quantkv-tail-split-coordinate-20261024-01.service

PID 1121062; PPID 624596; state S; start_ticks 384689416.
cwd: `/home/wangwy/openproject/ara_dsa_signoff_integration`
cgroup: `0::/user.slice/user-1002.slice/user@1002.service/app.slice/akv-quantkv-tail-split-coordinate-20261024-01.service`

```sh
'/usr/bin/python3' '-B' '/home/wangwy/openproject/ara_dsa_signoff_integration/verification/akv/quantized_kv/tail_split/coordinate.py' '--launch' '/home/wangwy/openproject/ara_dsa_signoff_integration/verification/akv/quantized_kv/tail_split/out/launch-01.json' '--output' '/home/wangwy/openproject/ara_dsa_signoff_integration/verification/akv/quantized_kv/tail_split/out/coordinator-01' '--unit-prefix' 'akv-quantkv-threeway-split-20261024-01' '--wait-timeout' '10800'
```

### shared-reader-real-quant-q4-20261025-02.service

PID 1112326; PPID 624596; state S; start_ticks 384596046.
cwd: `/home/wangwy/openproject/ara_dsa_signoff_integration`
cgroup: `0::/user.slice/user-1002.slice/user@1002.service/app.slice/shared-reader-real-quant-q4-20261025-02.service`

```sh
'/usr/bin/python3' '-B' 'verification/akv/shared_reader_integration/run_real_quantized.py' '--soc-build' 'verification/out/shared-reader-integration-soc-build-20261024-01' '--kind' 'quant_q4_0' '--build' 'verification/out/akv-quantkv-strided-attention-q4-build-20261024-01' '--prior' 'verification/out/akv-quantkv-strided-attention-q4-20261024-01' '--output' 'verification/out/shared-reader-real-quant-q4-20261025-02'
```

PID 1112641; PPID 1112326; state R; start_ticks 384600555.
cwd: `/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared-reader-real-quant-q4-20261025-02/work`
cgroup: `0::/user.slice/user-1002.slice/user@1002.service/app.slice/shared-reader-real-quant-q4-20261025-02.service`

```sh
'/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared-reader-integration-soc-build-20261024-01/sim/simv' '-no_save' '-l' '/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared-reader-real-quant-q4-20261025-02/work/run.vcs.log' '+PRELOAD=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/akv-quantkv-strided-attention-q4-build-20261024-01/strided_attention.elf' '+TESTCASE=shared_real_quant_q4_0' '+NO_FSDB' '+NO_INSTR_TRACE' '+VECTOR_TRACE=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared-reader-real-quant-q4-20261025-02/work/vector_trace.csv' '+ARA_CONTRACT_TRACE_LIMIT=2000000' '+ARA_UVM_TRACE_LIMIT=2000000' '+QBS_PERF'
```

### akv-timed-decode-unified-20261025-01.service

PID 1138861; PPID 624596; state S; start_ticks 384845607.
cwd: `/home/wangwy/openproject/ara_dsa_signoff_integration`
cgroup: `0::/user.slice/user-1002.slice/user@1002.service/app.slice/akv-timed-decode-unified-20261025-01.service`

```sh
'/usr/bin/python3' '-B' 'verification/akv/paired_heads/timed_decode/run.py' '--build' 'verification/out/akv-timed-decode-build-20261025-01' '--variant' 'unified' '--soc-build' 'verification/out/shared-storage-integration-soc-build-20261025-01' '--output' 'verification/out/akv-timed-decode-unified-20261025-01'
```

PID 1139013; PPID 1138861; state R; start_ticks 384847379.
cwd: `/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/akv-timed-decode-unified-20261025-01/work`
cgroup: `0::/user.slice/user-1002.slice/user@1002.service/app.slice/akv-timed-decode-unified-20261025-01.service`

```sh
'/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared-storage-integration-soc-build-20261025-01/sim/simv' '-no_save' '-l' '/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/akv-timed-decode-unified-20261025-01/work/run.vcs.log' '+PRELOAD=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/akv-timed-decode-build-20261025-01/timed_decode.elf' '+TESTCASE=akv_timed_decode_unified' '+NO_FSDB' '+NO_INSTR_TRACE' '+AKV_PERF' '+AKV_SUMMARY' '+VECTOR_TRACE=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/akv-timed-decode-unified-20261025-01/work/vector_trace.csv' '+ARA_CONTRACT_TRACE_LIMIT=2000000' '+ARA_UVM_TRACE_LIMIT=2000000'
```

### akv-timed-decode-baseline-20261025-01.service

PID 1138856; PPID 624596; state S; start_ticks 384845598.
cwd: `/home/wangwy/openproject/ara_dsa_signoff_integration`
cgroup: `0::/user.slice/user-1002.slice/user@1002.service/app.slice/akv-timed-decode-baseline-20261025-01.service`

```sh
'/usr/bin/python3' '-B' 'verification/akv/paired_heads/timed_decode/run.py' '--build' 'verification/out/akv-timed-decode-build-20261025-01' '--variant' 'baseline' '--output' 'verification/out/akv-timed-decode-baseline-20261025-01'
```

PID 1138904; PPID 1138856; state R; start_ticks 384846680.
cwd: `/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/akv-timed-decode-baseline-20261025-01/work`
cgroup: `0::/user.slice/user-1002.slice/user@1002.service/app.slice/akv-timed-decode-baseline-20261025-01.service`

```sh
'/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/qbacc-soc-20261023-02/build/sim/simv' '-no_save' '-l' '/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/akv-timed-decode-baseline-20261025-01/work/run.vcs.log' '+PRELOAD=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/akv-timed-decode-build-20261025-01/timed_decode.elf' '+TESTCASE=akv_timed_decode_baseline' '+NO_FSDB' '+NO_INSTR_TRACE' '+AKV_PERF' '+AKV_SUMMARY' '+VECTOR_TRACE=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/akv-timed-decode-baseline-20261025-01/work/vector_trace.csv' '+ARA_CONTRACT_TRACE_LIMIT=2000000' '+ARA_UVM_TRACE_LIMIT=2000000'
```

### akv-quantkv-tail-split-q8-v33-20261024-01.service

PID 1109910; PPID 624596; state S; start_ticks 384574568.
cwd: `/home/wangwy/openproject/ara_dsa_signoff_integration`
cgroup: `0::/user.slice/user-1002.slice/user@1002.service/app.slice/akv-quantkv-tail-split-q8-v33-20261024-01.service`

```sh
'/usr/bin/python3' '-B' '/home/wangwy/openproject/ara_dsa_signoff_integration/verification/akv/quantized_kv/tail_split/run.py' '--build' '/home/wangwy/openproject/ara_dsa_signoff_integration/verification/akv/quantized_kv/tail_split/out/build-q8-v33-02' '--prerequisite' '/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/akv-quantkv-model-strided-20261024-01-control' '--output' '/home/wangwy/openproject/ara_dsa_signoff_integration/verification/akv/quantized_kv/tail_split/out/run-q8-v33-01' '--timeout' '7200'
```

PID 1110443; PPID 1109910; state R; start_ticks 384578782.
cwd: `/home/wangwy/openproject/ara_dsa_signoff_integration/verification/akv/quantized_kv/tail_split/out/run-q8-v33-01/work`
cgroup: `0::/user.slice/user-1002.slice/user@1002.service/app.slice/akv-quantkv-tail-split-q8-v33-20261024-01.service`

```sh
'/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/qbacc-soc-20261023-02/build/sim/simv' '-no_save' '-l' '/home/wangwy/openproject/ara_dsa_signoff_integration/verification/akv/quantized_kv/tail_split/out/run-q8-v33-01/work/run.vcs.log' '+PRELOAD=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/akv/quantized_kv/tail_split/out/build-q8-v33-02/tail_attention.elf' '+TESTCASE=quant_tail_split' '+NO_FSDB' '+NO_INSTR_TRACE' '+QBS_PERF' '+VECTOR_TRACE=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/akv/quantized_kv/tail_split/out/run-q8-v33-01/work/vector_trace.csv' '+ARA_CONTRACT_TRACE_LIMIT=2000000' '+ARA_UVM_TRACE_LIMIT=2000000'
```

### shared-storage-real-prefill-20261025-01.service

PID 1126261; PPID 624596; state S; start_ticks 384739164.
cwd: `/home/wangwy/openproject/ara_dsa_signoff_integration`
cgroup: `0::/user.slice/user-1002.slice/user@1002.service/app.slice/shared-storage-real-prefill-20261025-01.service`

```sh
'/usr/bin/python3' '-B' 'verification/akv/shared_reader_integration/run_real_runtime.py' '--soc-build' 'verification/out/shared-storage-integration-soc-build-20261025-01' '--kind' 'prefill' '--build' 'verification/out/akv-live-prefill-build-20261024-01' '--prior' 'verification/out/akv-live-prefill-20261024-01' '--output' 'verification/out/shared-storage-real-prefill-20261025-01'
```

PID 1126591; PPID 1126261; state R; start_ticks 384741710.
cwd: `/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared-storage-real-prefill-20261025-01/work`
cgroup: `0::/user.slice/user-1002.slice/user@1002.service/app.slice/shared-storage-real-prefill-20261025-01.service`

```sh
'/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared-storage-integration-soc-build-20261025-01/sim/simv' '-no_save' '-l' '/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared-storage-real-prefill-20261025-01/work/run.vcs.log' '+PRELOAD=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/akv-live-prefill-build-20261024-01/akv_live_prefill.elf' '+TESTCASE=shared_real_prefill' '+NO_FSDB' '+NO_INSTR_TRACE' '+AKV_PERF' '+AKV_SUMMARY' '+VECTOR_TRACE=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/shared-storage-real-prefill-20261025-01/work/vector_trace.csv' '+ARA_CONTRACT_TRACE_LIMIT=2000000' '+ARA_UVM_TRACE_LIMIT=2000000'
```

### akv-quantkv-tail-split-q4-v33-20261024-01.service

PID 1109905; PPID 624596; state S; start_ticks 384574562.
cwd: `/home/wangwy/openproject/ara_dsa_signoff_integration`
cgroup: `0::/user.slice/user-1002.slice/user@1002.service/app.slice/akv-quantkv-tail-split-q4-v33-20261024-01.service`

```sh
'/usr/bin/python3' '-B' '/home/wangwy/openproject/ara_dsa_signoff_integration/verification/akv/quantized_kv/tail_split/run.py' '--build' '/home/wangwy/openproject/ara_dsa_signoff_integration/verification/akv/quantized_kv/tail_split/out/build-q4-v33-02' '--prerequisite' '/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/akv-quantkv-model-strided-20261024-01-control' '--output' '/home/wangwy/openproject/ara_dsa_signoff_integration/verification/akv/quantized_kv/tail_split/out/run-q4-v33-01' '--timeout' '7200'
```

PID 1110464; PPID 1109905; state R; start_ticks 384578883.
cwd: `/home/wangwy/openproject/ara_dsa_signoff_integration/verification/akv/quantized_kv/tail_split/out/run-q4-v33-01/work`
cgroup: `0::/user.slice/user-1002.slice/user@1002.service/app.slice/akv-quantkv-tail-split-q4-v33-20261024-01.service`

```sh
'/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/qbacc-soc-20261023-02/build/sim/simv' '-no_save' '-l' '/home/wangwy/openproject/ara_dsa_signoff_integration/verification/akv/quantized_kv/tail_split/out/run-q4-v33-01/work/run.vcs.log' '+PRELOAD=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/akv/quantized_kv/tail_split/out/build-q4-v33-02/tail_attention.elf' '+TESTCASE=quant_tail_split' '+NO_FSDB' '+NO_INSTR_TRACE' '+QBS_PERF' '+VECTOR_TRACE=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/akv/quantized_kv/tail_split/out/run-q4-v33-01/work/vector_trace.csv' '+ARA_CONTRACT_TRACE_LIMIT=2000000' '+ARA_UVM_TRACE_LIMIT=2000000'
```
