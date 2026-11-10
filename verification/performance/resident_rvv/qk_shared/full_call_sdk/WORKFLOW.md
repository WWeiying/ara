# Current SDK Functional Workflow

The current functional gate uses BUILD02 and the corrected sources in
[`flags_v2/USAGE.md`](flags_v2/USAGE.md). The six original helpers beside this
file are preserved predecessor inputs, not the current PV flag attribution.
Do not rebuild or launch their historical example in place of BUILD02.

## Frozen Inputs

| Role | Identity |
|---|---|
| SoC | `stage3_soc_20261110_02`, RTL `9af19508d` plus registered CPU retirement patch |
| Firmware | `stage3_attention_sdk_build_20261110_02/attention_sdk.elf` |
| ELF SHA256 | `d8c413799646ddf3286347d0c18a76eaaadce27a2840fc3bf4f46f3d7d1de17c` |
| SDK | Archived `8dc915db8` plus reviewed native-C/executor-header overlays matching `ca772ef90` |
| Checker | Frozen BUILD02 `check.py` and corrected `fixture.py`; no live fixture import |
| Output root | `/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out` |

The live dirty `akv_v2_attention_rvv.S` is not a build input. Neither this
functional firmware nor its OFF call replaces the stronger performance
baseline in `../full_call/`.

## Execution

`run.py prepare` creates a fresh directory, copies the reviewed checker and
protocol package, verifies firmware/image identities and runs 11 bounded host
checks. It does not execute the simulator.

```sh
python3 -B verification/performance/resident_rvv/qk_shared/full_call_sdk/run.py prepare \
  --soc-build /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/stage3_soc_20261110_02 \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/stage3_attention_sdk_vcs_NEW
```

Review `selection.json`, `prepare-report.json` and `source-pins.json`. Then use
`run.py service-command --output OUTPUT --review-sha256 HASH` to obtain the
direct systemd launch command. Do not run the worker from the live source or
retry an attempted directory. The worker runs the image contract, VCS, SDK
numerical/work checker and independent protocol checker in order. Simulation
is bounded at 5,400 seconds; no FSDB or automatic retry is enabled.

The reviewed attempt is `stage3_attention_sdk_vcs_20261110_01`, with source-pin
SHA256 `d532da52c58a5742c294cab8a7148397a08e4e2ec13cb1a568e3f7c0582da3c2`.
It is terminal PASS; its service exited successfully and is now inactive:
`stage3-attention-sdk-stage3_attention_sdk_vcs_20261110_01.service`.

```sh
systemctl --user status stage3-attention-sdk-stage3_attention_sdk_vcs_20261110_01.service
cat /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/stage3_attention_sdk_vcs_20261110_01/result.json
```

A live process or `state=SIMULATION` is not PASS. The terminal result must have
numerical, actual-entry, work, independent-protocol, post-source and post-image
checks all passing. Three calls require 1,088 exact FP32 outputs, FCSR 3/11/3,
247 context/native commands, eleven QK and eleven PV commands, six retired
Decode entries and four experimental executor entries. The derived D96/GQA
fixture is explicitly distinguished from independently captured model heads.

Keep `performance_acceptance=false` in this functional worker: retention uses
the separate equal-work ABBA measurement. Neither receipt promotes capability,
GGML selection, a new bitstream or whole-model performance.

The accepted result SHA256 is
`70ccad29ade83850f3c6a94276b8f60d7258513c4091939267641f550bbd3fb1`.
It checks all 1,088 outputs, flags, actual entries, work and protocol above,
including post-run identities. Diagnostic full-call cycles are 41,908/37,984/
58,285; these are not a new paired performance comparison.
