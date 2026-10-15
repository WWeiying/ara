# Software02: full5985 Host/linked checks complete, no reference

The one authorized new candidate changed only the reviewed fixed-block sticky
comparator. No compiler parameter experiment or retry occurred. Source inputs,
full scope, original helper, initializer, mask and FP events are unchanged.
Software01 remains COST_HOLD; its artifacts are not overwritten.

Actual Host/GCC supervisor wait0/39.01125316694379s, all41 previous expected
outcomes retained. New Host probes require66 actual+66 expected reads even
after first/middle/last mismatch. Host C does not establish RV64 asm behavior.
The separate actual linked proof checks all66 BEQ/LI sites and four state
transitions each, both backends' addresses, full reads and final fallback.

See `../compiled_audit03/REPORT.md` and `RESULT.json` for the complete cost,
lowering, original negative coverage, and preserved audit02 boundary error.
Audit03 actualwait0/1.0180219081230462s. Whole all-equal Spike CFG upper:
**2,863,981**, headroom**136,019**; static, not measured retirement.

| Artifact | SHA256 |
| --- | --- |
| `soc/program.elf` | `7ad99ec2e99b1eab9183e82934f09f29b3322a9c82093935dea3771f6d7d1620` |
| `spike/program.elf` | `42e53dc666391e88db7c2d436f7972cda362b575ca9e26806110841fecce51ae` |
| `proof.json` | `412e63afa9d3d20efc443ba586d912fef67ebb8c61d4f159c88b61a2daf72796` |
| `pins.json` | `4d6830229483e372e41f4ac3151e6ad45fb0e0be1ca2c16d7ee2e60781600fcd` |
| `packed_output.h` | `56e53d4d64a8a3366757b76cafbdc917fea116795a83ebcb98e2e3ceef864679` |
| audit03 `RESULT.json` | `95430da11698b00be8f080a0624f70a36576399549214cfb436345b04790805c` |

The original `software_status.json` retains its build-time pending-CFG status;
this append-only handoff supplies the later static inspection. Independent
artifact review has been requested from Averroes. No independent acceptance,
Spike execution, DUT result, or permission to run either is asserted here.
