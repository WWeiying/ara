# Projection integer-throughput budget and next candidate

## Current measured hardware work

The accepted complete M4/K1536 Q/V/K benchmark executes 64 native commands per
trial. All four trials use identical logical weight/activation byte counts,
12582912 useful multiplication pairs and 393216 integer issue cycles. In the
two cache-enabled trials the exclusive command-busy totals are 447408 and
447414 cycles. SDK/native execution totals are 478271 and 478195 cycles;
complete projection totals, including preparation, are 621885 and 621203.

The strict weight-wait probes are all zero. This does not mean every read
finishes immediately, but it rejects claiming a large strict WAIT_WEIGHT
bottleneck in this workload. First-trial phase totals partition 447411 busy
cycles as follows:

| Exclusive controller phase | Cycles |
| --- | ---: |
| Setup | 960 |
| Activation | 5440 |
| Weight | 18483 |
| Compute without reader overlap | 257667 |
| Compute with reader overlap | 153981 |
| Drain | 5184 |
| Scheduler | 3520 |
| Commit | 2112 |
| Terminal | 64 |
| Fault | 0 |

The compute labels classify controller/reader states, not multiplier or FPU
utilization. In particular overlap is not a second additive memory-stall term.

## Counter and RTL audit

`qbs_profile_engine_int.sv` increments `dot_active_cycles_o` when
`compute_active_q && issue_active_q`, and advances K by eight, four or two
elements/context for M1, M2 or M3/M4. It increments useful pairs by
`row_count * M * k_per` and capacity by `row_count * 8`. These are issue-side
logical arithmetic counts, not power/activity measurements. The synchronous
payload read and registered decoder/dot stages follow that valid pipeline.

`qbs_dot_array.sv` retains 32 signed byte multiplications/cycle, organized as
four rows of eight product slots. M4 uses four contexts and two K elements per
context. This full-row M4 benchmark therefore issues 32 useful pairs each
integer issue cycle. `qbs_compute_engine.sv` accumulates the tile counters only
when the integer tile completes, not when a tile is merely requested.

Here useful pairs equal capacity because M4 and full four-row tiles use all
slots. The counter's capacity denominator shrinks with `row_count`; it must
not be used to claim full physical-array utilization for short row tails.
Similarly, 393216 issue cycles divided by command-busy is issue duty, not
whole-processor utilization or a claim about switching when operands are zero.

The FP table reaches capacity in many cycles, but slot/accumulator/input
blocking probes are zero for this run. Table-full time cannot be directly
subtracted from total latency. Integer issue already overlaps the correction
and FP pipeline; any new scheduling hypothesis needs discriminating signals.

## Conditional savings ceiling

For the two optimized complete calls:

```text
complete cycles            = 1243088
native command busy        =  894822
integer issue cycles       =  786432
native non-issue difference = 108390
integer issue / native busy = 87.8870%
native busy / complete      = 71.9838%
```

If the arithmetic mapping stays at 32 pairs/cycle, the same logical work is
retained and only native non-issue cycles change, even deleting every such
cycle would save at most 8.7194% of these complete calls, speedup 1.09552x.
This is an unattainable optimistic budget, not a forecast. It does not bound
an algorithm that reduces work, a wider unit, preparation changes or frequency
changes. It argues against enlarging readers, SRAM or FP queues blindly for
this case. It is not a general bound for every profile or decode shape.

## Verification-only software candidate

The remaining cold M4 producer still prepares four rows in small 16-element
groups and emits strided byte stores. A separate candidate batches up to 128
elements with e32/m4, preserves the same bias/FMA/narrowing and signed-max
policy, computes exact 16-element integer block sums using slides/reductions,
then uses `vsseg4e8` to emit the existing four-row byte layout directly.
It is VLA: smaller VLENs use smaller chunks, with the same format and fallback.

The hypothesis is fewer front-end vector commands and less fragmented store
organization, not more multipliers or different quantization. The candidate
uses the same integer-only domain check and generic fallback; no new scale,
rounding, clipping or approximate arithmetic is introduced. It remains outside
the production backend and does not replace any installed source.

QEMU functional comparisons pass at VLEN128/256/512/1024: 808 cases per VLEN,
including three real four-row groups, all 32 incoming FFLAGS patterns and eight
VCSR states, generated zero/tie/signed-zero/finite inputs, non-RNE fallback,
full prepared bytes and guards. These checks are not RTL performance evidence.
`verification/out/m4-tiled-reference-20261027-02` retains the checked logs.

The next VCS pair uses one fresh ELF, original/tiled/tiled/original ordering,
three real-data preparations per trial, fixed K1536 and full exact byte/CSR/
input/guard checks. It uses only ordinary RVV, including the segment store,
and independent protocol checking. The benchmark excludes cache and native
matrix work to isolate producer cost. Any successful gain must subsequently
pass complete-call timing and actual GGML/model integration before promotion.

Sources: `verification/qbs/m4_prepared_reuse/tiled_candidate.h`,
`tiled_producer.cpp`, `tiled_test.cpp`, `run_tiled_reference.py`, and `tiled/`.
No RTL, synthesis or physical implementation is changed in this candidate.
