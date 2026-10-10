# Seed509fix Bounded Exploration

Status: planned, not run. `batch_exploration_plan.json` contains 200 new random
cases and 48 existing directed ELFs. No RTL or simulator image is modified.
The frozen VCS launcher is `out/seed509-fix-20260926-01/sim/simv`, SHA-256
`1f9c4f3cf4735a503eeecc692f734fbe3ae4bd9cdee1d44f07ed1965130f6205`.
Its full runtime map, source manifest and PASS validation are pinned in JSON.

## Random Profiles

All names below have prefix `ara_dsa_rvv1_` and suffix `_coverage300`.
Aliases preserve the original `gen_test`, `rtl_test`, iteration default and
every generation option except `instr_cnt=300`. Each job uses iterations=1.
These are real entries in `riscv_dv/testlist.yaml`, not hypothetical overrides.

| Profile stem | Original instr_cnt | New seeds (20 each) | Main target |
| --- | ---: | --- | --- |
| short_memory_cross | 300 | 601-620 | Segment, restart, indexed memory |
| short_control_cross | 300 | 701-720 | Dispatcher, CSR, dependencies |
| arithmetic | 2000 | 801-820 | Operand queue and mixed arithmetic |
| load_store | 2000 | 901-920 | Masked memory and vstart |
| integer_stress | 5000 | 1001-1020 | Masks, permutations, integer dependencies |
| fp32 | 3000 | 1101-1120 | FP conversion, rounding, reduction |
| fp64 | 3000 | 1201-1220 | Widening/narrowing and FP reduction |
| vtype_churn | 3000 | 1301-1320 | Vtype/LMUL and dispatcher state |
| load_store_slide | 3000 | 1401-1420 | Slide-built indices and restart |
| smoke | 200 | 1501-1520 | Bounded vector-only dependencies |

300 means generator body instructions, not total ELF instructions or DUT cycles.
The existing generic `riscv_instr_base_test` generator can be reused; no SV
generator configuration changes are required. The JSON pins the existing
short-memory-preflight generator; pass that path explicitly if the driver
defaults to the separate short-control-preflight executable.

Strict random flags: `--vector-signature --defined-scalar-sources
--vector-commit-compare --spike-isa rv64gcv_zvfh_zvl1024b`; independent audit
requires trace, vector and full match. Do not add intrusive per-instruction
checkpoints to the whole batch. Preserve generated assembly and rewrite records.

## Directed Selection

The JSON uses exact `verify.py` catalog IDs and pins every available `apps/bin`
ELF, its size and hash, source oracle files, and matching historical PASS where
available. All 48 are ELF64 RISC-V and their PT_LOAD ranges fit below 0x80100000.
37 have an exact-ELF historical PASS in the inspected local summaries; the other
11 have existing self-checking sources but are NOT claimed previously passed.
This is not a claim that current source was used to build an older ELF.

- 8 segment cases: EMUL, illegal recovery, unit/strided/indexed load/store.
- 8 restart/memory cases: masked indexed faults, vstart, whole-register,
  store mask/tail and load/store hazards.
- 8 VMFPU cases: FP restart, reduction boundaries, narrow/wide conversion,
  ordered widening reduction, reverse-subtract pipeline and widening FMA.
- 8 mask/dependency cases: carry/tail, comparison, memory EMUL, scalar handoff,
  policy matrix, ID queue and pending-source WAR.
- 8 dispatcher/operand-queue cases: illegal groups/overlap/vstart, widening
  LMUL4, reductions, narrowing clip and compression.
- 8 bounded apps: `app:qbs_control_smoke`, `app:qbs_akv_handoff_smoke`,
  `app:akv_context_smoke`, `app:akv_column_coverage_smoke`,
  `app:akv_coverage_minimal`, and `app:llama_qwen25_` plus
  `shape_decode_n32_qbs`, `shape_decode_n32_rvv`, `shape_prefill_n33_qbs`.

Directed oracle: program self-check, zero exit, Core SUCCESS, no failure
diagnostics, valid trace and provenance. Custom QBS/AKV instructions are not
silently sent to ordinary Spike. No large FFN/full-model cases or unconfigured
AXI-fault-injection tests are included. Do not rebuild these pinned ELFs.

## Scheduling And Handoff

- Canonical schema: `schema_version:1,cases:[{name,kind,test,seed?}]`.
  Equivalent `random/directed` compatibility views remain because the inspected
  driver still consumes those. They describe the SAME 248 cases, not extra work.
- At most five VCS processes total, including generator processes; at most
  twelve compiler processes. Only random ELF compilation, never RTL compilation.
- RTL timeout 300 s for random/RVV, 600 s for QBS/AKV; random Spike timeout
  60 s, watchdog 100000 cycles. Requested whole-case hard limit: 600 s.
- Planning memory budget: 5x16 + 12x4 + 50 = 178 GB on the 250 GB host.
  This is an allocation estimate, not measured RSS; back off before 200 GB.
- Rough expected duration 1-3 h, unmeasured. Pessimistic 248 jobs at 600 s
  over five whole-job slots is about 8.3 h plus setup. No waveform campaign.
- Continue independent cases after ordinary RTL failures, mismatches and bounded
  DUT timeouts. Retain first-failure evidence per case and group repeated failures.
  Stop the shared queue only for infrastructure, hash/integrity or checker
  failures. No automatic retry, RTL repair or timeout changes.
- Coverage replay is already authorized, without another approval gate. Report
  exploration coverage including failed prefixes separately from independently
  checked PASS coverage. A failed prefix is not correctness evidence.

**Main/Hilbert coordination before launch:** continuing ordinary test failures
matches the authorized exploration policy. The inspected driver's outer
`timeout_s+1500` limit differs from the requested 600 s whole-case bound; align
that bound and child cleanup, normalize the two schema views, and compare
plan-pinned ELF/image hashes before preparing inputs. This sidecar did not modify
the driver.

The priorities come from historical 18-case coverage: dispatcher 910/2613,
operand queue 430/1664, VMFPU 540/1267, mask unit 405/700. They are not current
coverage numbers. Bind coverage replays to their own coverage image/source hashes,
distinct from the functional VCS image. Merge only compatible measured coverage
and keep failed-prefix exploration and independently checked PASS sets separate.
