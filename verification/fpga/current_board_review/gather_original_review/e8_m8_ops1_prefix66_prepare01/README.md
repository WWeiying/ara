# Authentic e8/m8/op1 Natural Prefix66

Prepare-only Host/Spike reference. No VCS build or DUT run, RTL changes, or
queries of ongoing M6/Gather jobs. This is a distinct cap1024 source boundary,
not a repeat of accepted cap512 prefixes and not an exact historical stall
reproduction. Final preparation identity and evidence pins are in `READY.json`.

## Scope and Source Proof

- Original child: `rvv_permute_restart_e8_m8_ops1`, 2688 original calls.
  Linux ELF SHA256:
  `7b6623f49a5aee9ae03a3365dc69e898b922ffc61a113c58aae71f96342c83cf`.
- Original complete C SHA256:
  `b6e5fa032dfdc58ec621d0377f93cf824f27ad460d6bd102e173e244a65ec5ca`.
  Source, original ELF, assembly/header, manifest and recovery171 report
  identities are checked in `baseline_pins.json` and `source_elf_proof.json`.
- Exact scope: first66 child calls, retaining all65 predecessors, original
  xorshift initialization, excluded-op loop iterations, masks, full-capacity
  setup and result/guard checks. The sole stop is after call66's full oracle.
- Endpoint tuple `[seed0, op1, scalar-index0, length-index4, mask0, trial1]`:
  cap1024, VL512, vstart256, scalar0. The 896 op0-excluded iterations remain
  in the original C control flow; no fabricated warmup or vector drain.
- Original target PC `0x105dc`, opcode `308e4c57`:
  `vrgather.vx v24,v8,t3,v0.t`. SoC target PC `0x800006fa`.
  All13 helper instructions match the original Linux helper and both prepared
  ELF variants byte for byte, including cap loads, mask load, vstart write,
  post-target CSR read and full-cap result store.
- `source_diffs/adapter.diff` contains only the established Linux wrapper
  adaptation; `prefix.diff` contains only the call66 stop and PREFIX summary.
  Original oracle is retained, including prestart, inactive and tail bytes.

The archived record has `last_trial=null`. Its last reported DETAIL VL3/start1
is not proof of the later unreturned tuple. This chosen natural endpoint is
justified by `../NEXT_GATHER_STALL_PLAN.md`, not invented historical precision.
No full2688 child, complete parent, original Linux timing, or DUT acceptance
is claimed. A byte-identical rebuild of the entire original Linux ELF is not
claimed; this is a proven source port with identical selected helper bytes.

## Host and Spike Evidence

`host/host_gate.json`: one positive and seven negative Host cases passed.
The actual original C oracle rejects active, prestart, masked, tail, both
guard, and returned-vstart corruptions. Vector operations are mocked only in
Host testing; the actual assembly executes on Spike.

`reference/reference.json` and raw `reference/commits.log` establish:

| Item | Measured |
| --- | ---: |
| Original target calls | 66 |
| Each of13 original helper instructions retired | 66 |
| Full-capacity scalar result checks | 67584 |
| Scalar guard checks | 132 |
| Returned vstart=0 checks | 66 |
| Source/setup values checked per call | 4226 |
| Firmware retired through successful HTIF store | 2745395 |
| Spike wall time / return code | 4.530458820s / 0 |
| Raw commit log size | 177751012 bytes |

The source model checks e8 truncation of data/indices separately from original
16-bit indices. Each actual call's arguments, all initialized source bytes,
mask bytes and old output/guards are verified from scalar stores in the raw
trace; missing bytes are rejected. Output checks must be actual scalar LBU
reads, with all1026 distinct output/guard positions per call. Raw console
reconstruction requires PREFIX66, BOARD_CASE_PASS, BOARD_REPLAY_PASS and no
failure/DETAIL text. HTIF store must encode exit0.

Bounds were unchanged: one Spike execution, 120 seconds, 5000000 instruction
debug ceiling, 768MiB per-output-file limit. The raw log is 169.52MiB.
No retry or limit increase occurred. `audit_reference02.py` is the successor
offline recheck with five corrupted-trace controls; it does not rerun Spike.
The first offline audit's diagnostic mismatch is preserved in
`audit01/FAILURE.md`: truncated oracle was rejected, but with a different
message than the inherited e16 fixture expected. No reference/checker/oracle
relaxation was made; only that negative's expected diagnostic changed.

Executable software inputs:

| ELF | SHA256 |
| --- | --- |
| `soc01/gather_prefix_e8_m8_ops1.elf` | `791d817193c9b46eec48e6feee8b1d9c8ecf289b588253b21c1f59a54314d2c6` |
| `spike01/gather_prefix_e8_m8_ops1.elf` | `b0c09970aa48d9c96951f5e724cacfcabbb25eb7a32c009ff35d5048b346298b` |

## Reference Cost, Not DUT Measurement

| Assumed retired/s | Estimated VCS seconds | Interpretation |
| --- | ---: | --- |
| 683..687, earlier accepted M5 prefixes | 3996..4020 | About67min, not measured for this case |
| 273, conservative historical rate | 10056.39 | 2h47m36s, under3h by743.61s |
| 273 plus20% time margin | 12067.67 | Exceeds3h; adequate margin is not established |

The nominal conservative estimate fits3h, but only with7.4% time margin.
Preparation does not choose or increase a DUT timeout, authorize a launch,
shrink the66 calls/oracle, or claim that any later timeout proves a stall.
Review actual admission/resource assumptions before considering a DUT plan.

Existing e16 reference files and shared helpers are included in baseline pins
and checked unchanged. All generated files are confined to this fresh owned
directory. Independent review, when available, is separate from this producer's
Host/Spike reference validation.
