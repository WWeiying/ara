# Execution index

Output root: `/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out`.
This is an execution index, not an all-tests-passed or power-completion claim.

| Output | Scope |
|---|---|
| `power_rtl_20261117_host02` | VCS build of exact DC-frozen 870cadb9 design/dependencies with behavioral 1 MiB SRAM; compile passed |
| `power_program_inputs_20261117_projection_01` | Real Qwen3 M1/M4 projection and original Qwen2.5 Q8_0 ELF selection, native/RVV manifests |
| `power_legacy_q8_prepare_20261117_01` | Frozen original Q8_0 ELF/data; matching activation, row-weight and golden hashes on both sides |
| `power_attention_prepare_20261117_{rvv,akv}_01` | Separate same-data KV137 two-call ELFs, 1 MiB linker and bounded stack; seven host tests passed |
| `power_precheck_20261117_native_projection_01` | Three native projection RTL cases, maximum three concurrent |
| `power_precheck_20261117_native_attention_02` | One native AKV RTL case; total VCS concurrency no more than four |
| `power_protocol_audit_20261117_q4_m1_01` | Independent PASS: exact numerical checks plus recovered protocol audit, no RTL rerun |
| `power_protocol_audit_20261117_attention_01` | Independent protocol PASS after exact 512-value/flags/guard numerical PASS; no RTL rerun |
| `power_legacy_q8_successor_20261117_01` | Same Qwen2.5 blobs/shape; reviewed SDK descriptor-v2 rebuild; original timing identity not claimed |
| `power_precheck_20261117_native_q8_successor_01` | RTL, all-output numerical and independent protocol PASS; 43,033 complete compute cycles |
| `power_rtl_20261117_baseline_01` | Reconstructed no-QBS source/dependency closure; VCS compile PASS; historical byte identity unproven |
| `power_precheck_20261117_baseline_02` | Four RVV programs, maximum three workers while native M4 occupies one slot |
| `power_gate_build_20261117_all_on_01` | Shared gate simulator compilation authorized only after the two-case RTL evidence admission |

## Original failures retained

- Legacy Q8_0 native firmware issues `0x00b5045b`; a vector response exception
  occurs at cycle 6410, then the legacy CRT's invalid trap vector causes repeated
  invalid instruction fetches. Only that process was stopped after about two
  minutes. Descriptor bytes prove v1 (header `0x37f12261`), while the frozen
  hardware requires v2. The separately rebuilt SDK successor uses v2 and passes;
  the original legacy ELF/failure remains unchanged and is not counted as PASS.
- Real Q4_K M1 finishes successfully and passes the independent exhaustive
  numerical/flags/guard checker. Its worker's subsequent Python protocol stage
  failed because `ara_verify` was absent from the frozen support tree. An
  independently frozen checker from commit dbe2b788 verified the existing
  traces: no exceptions, protocol errors or outstanding requests, with matching
  image/ELF/log/trace identities. The original worker remains FAIL; the separate
  audit is PASS. No repeated RTL run was needed for this tooling error.
- `power_precheck_20261117_native_attention_01` is preparation-only failure:
  original run-plan lacked the campaign `scope` field. No simulator was launched
  there; `_02` uses an explicit wrapper manifest. Firmware/checker are unchanged.

## Baseline qualification

The historical no-QBS power netlist is in `ara_dsa_no_qbs_pulp_eval`, not the
unqualified similarly named worktree. Its synthesis incorporated uncommitted
experimental RTL; source reconstruction is still being audited. Current HEAD or
an earlier b73af277 passing test is not automatically synthesis-matched evidence.
Historical clipped SAIFs are references only, not new verified activity.

The baseline frozen inventory now preserves 703 files, the dirty RTL patch,
netlist/DDC identities and include closure. It compiled successfully, but that
does not retroactively prove synthesis-time source byte identity. The earlier
idle `_baseline_queue_01` controller was stopped before any case dispatch and
retained with `disposition.json`; `_baseline_02` uses the available three slots.

## Conversion infrastructure

`convert.py` requires a completed bounded capture, an initial `$dumpvars`
snapshot, exact cycle/time duration and a known, toggling root clock. It rejects
old tail files without initial state. A synthetic 1-ps converter probe established
that this `vcd2saif -time` takes VCD ticks, not nanoseconds. Probe SAIFs are named
`power_converter_probe_*`; they are infrastructure tests, never processor data.

## One-shot status

```sh
python3 -B verification/performance/power_eval_20261117/status.py
```

No gate simulation or power measurement has been accepted at this stage.
