# Offline two-way Attention attribution

Only reads a completed, accepted **generic AKV / paired AKV** ABBA. No worker,
polling, simulation, canonical edit, or ordinary-RVV deployment claim. The input
is the derived Qwen2.5 KV128 subset (Q heads0,1,6,7), not a Qwen3 capture.

`analyze_attention.py` reuses sealed `attention_run.check_log`, `checked_build`,
accepted-image validation, UVM validation and hash validators. Both terminal
status/result must be PASS, child_pid null, and result SHA must match an explicit
independently supplied hash. All run evidence, source, build and image pins must
match before and after analysis. No partial-trial or in-progress output is used.

## Command busy and residual

Sum actual AKV_PERF busy_cycles separately for FULL, REFILL, KCOL, PV and RELEASE
within each checked trial. The sum must equal the sealed checker's trial total.
`hardware/src/vlsu/vlsu.sv:1557` and `:1643` report command_cycles+1.

**Measured cycles minus engine busy is NOT an exclusive stall breakdown.** It
does not identify scalar, FPU, memory or issue stalls. Command-active time can
overlap scalar/vector execution; the residual contains unassigned work, gaps and
synchronization. Do not add guessed FPU time to command busy or call the residual
CPU-only cost. The script reports actual command work and external traffic too.

## Retired-work proof

Pinned build03 disassembly contains exactly two cycle CSR reads in main:
start `0x800006c0`, end `0x8000086c`. The analyzer rediscovers them from instruction
bits, not hardcoded trial offsets. Require exactly eight matching architectural
retire records in alternating start/end order; each unsigned64 rd_wdata delta
must exactly equal that trial's application cycle count. Count only retire events
strictly between those boundaries, with contiguous retire order and instructions
matching pinned disassembly. Both boundary CSR instructions are excluded.
`arch_start`, `uop_alloc`, `uop_done` and reshuffle micro-ops are never counted as
architectural instructions. Classes distinguish scalar (including scalar FP),
standard RVV (including configuration), and AKV custom instructions/info reads.

Source expectations, **not measurements until proven from retire trace**:

* Generic QK `software/akv/src/akv_v2_attention_rvv.S:533`: four Q heads x128
  dimensions x two KV tiles =1024 retired vfwmacc.vf per complete call.
* Generic PV at `:667`: four Q heads x128 visible tokens =512 vfmacc.vf per call.
* Experimental `software/akv/experimental/paired_heads/attention_rvv.S` updates
  both heads for each shared load, preserving both arithmetic counts.
* The native softmax implementation also executes vector FMA. QK/PV counts are
  restricted to their exact function PC ranges; other vfmacc.vf is separate.
* K custom commands1024->128; PV loads512->256; logical K columns1024->512;
  replay262144->131072B. External Q/K/V/descriptor traffic stays unchanged.

If complete retire/CSR proof is unavailable or inconsistent, no partial counts
are published: `retired.state=NOT_AVAILABLE` includes the reason. Verified
command-busy analysis remains available. Even proven retire counts are not FPU
execution cycles, vector-element FLOPs, active-lane utilization or stall causes.

## Usage

```sh
python3 -B verification/akv/paired_heads/analyze_attention.py --self-test
python3 -B verification/akv/paired_heads/analyze_attention.py \
  --run verification/out/akv-paired-heads-attention-20261024-01 \
  --build verification/out/akv-paired-heads-attention-build-20261023-03 \
  --result-sha256 8d6b45a76f92ca37c704624534178a7230fd4565ef644c1eb50e5e123729925a \
  --output verification/out/akv-paired-heads-attention-analysis-20261024-01
```

Output must be a new directory outside the sealed run/build directories.
`analysis.json` contains attribution and its `pins.json` digest. Host self-test
uses the sealed synthetic log fixture and synthetic retire records, including
bad cycle data, missing final retirement and mismatched instruction mutations.
It does not inspect a running service or claim actual arithmetic coverage.
