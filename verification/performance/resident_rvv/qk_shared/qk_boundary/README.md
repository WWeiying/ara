# Architectural QK Boundary

This is a new, bounded architectural gate, not component or performance
acceptance. It never modifies production RTL, dependencies, SDK, parent-owned
`resident_attention/qk.S`, or the old PV boundary/checkers. No SoC execution is
authorized merely by building this firmware or preparing its recipes.

## Contract

The current experimental ABI is custom2 `0x5b`, funct3 7, funct7 3:
`0x0605705b` for vd0/rs1=a0/rs2=0. Control is T-1[5:0], H-1[6], D code[8:7]
(64=0, 128=1, 96=2), query base[11:9]; higher bits must be zero. Destinations
reserve four aligned registers, EW32, VL128, LMUL4; QK has no VRF source.
The suite also uses legal vd28. Dynamic VL/VTYPE do not select QK geometry.
Capability remains default unsupported; this gate directly tests enabled RTL.

23 discriminating scenarios produce 35 direct attempts: six shape points
cover T1/2/3/9/17/64, D64/96/128, H1/2, bases3/5/6/7 and rm0..4; five special
points distinguish 0*Inf, qNaN/Inf, sNaN, inactive poison with exact subnormal
arithmetic, and NX/cancellation. Twelve rejection points cover FS/VS Off,
vstart, reserved frm, rs2, rd alignment, high control, bad D code, missing
context, D/T context mismatches and a valid base6/H2 command against seven
loaded queries (8 <= ABI maximum 8, but 8 > runtime context 7). Its same-context
recovery selects base5/H2, exactly reaching runtime row7 without a refill.
Each rejection is followed by a successful command without context reset or
reload, except the deliberately released context, which requires one refill.

One additional call uses the unmodified parent helper, with its FCSR read bound
to an exact ELF PC. Two real PV calls surround the first QK/helper calls in the
same context. A frozen QBS/ordinary-RVV postlude checks raw data and flags.
Expected totals are 24 successful QK retirements, 12 real CSR trap groups,
34 actual QK accelerator requests and ten accelerator exceptions. FS/VS Off
must not reach the accelerator. Illegal instructions must not be invented as
RVFI retirements. The CPU retirement fix is a mandatory image identity.

QK results and command-local flags come from independent ordered Spike
SoftFloat, never from the DUT. Frozen Qwen3 data contain only two Q rows;
eight distinguishable rows are explicitly derived by dimension rotations, not
presented as an eight-head model capture. Special patches are identified by
case kind. The firmware's expected arrays are not trusted as host evidence.

The checker binds named ELF CSR PCs/words and the complete frozen trap path,
before/after VL/VTYPE, raw FCSR/vstart, exact mepc/cause, and destination
atomicity including adjacent v0-v7 and high v28-v31 registers. It independently
checks allocation geometry and actual source4 VRF write bytes, including
partial 4-byte tails, result/final-ack counts, no QK VRF source requests and PV
source96 drain. Inactive destination tails are clobberable, not expected to
retain old bits after success. An independent unmodified UVM protocol checker
remains mandatory; its legacy AKV-column label is not QK semantic acceptance.

## Preparation

`build.py --output OUT/resident_qk_boundary_build_...` builds once from the
hash-pinned old SDK/common archive, frozen trap/postlude/linker, fixed parent
QK helper and this new directory. It does not need a SoC image. Outputs include
full source/toolchain pins, independent vectors, exact ELF and disassembly.

After Gauss's image is ready:
`run.py prepare --soc-build SOC --software-build BUILD --output RUN` checks the
fresh stage3 receipt, CPU overlay and all source/image/software identities,
then freezes the complete protocol checker inventory and execution recipes.
It does not run simv. Actual execution additionally requires the reviewed
source-pins hash, frozen worker and direct systemd MainPID ownership:

```text
systemd unit: resident-qk-boundary-<RUN.name>.service
worker: RUN/inputs/qk_boundary/run.py run --output RUN --parent-reviewed --review-sha256 SHA
working directory: RUN/work
RuntimeMaxSec=7200, KillMode=control-group
StandardOutput/StandardError: independent RUN files
```

Simulation is bounded to 5400 seconds, protocol checking to 900 seconds and
architectural checking to 300 seconds. No retries, automatic next experiment,
FSDB, EDA compilation, synthesis, FPGA activity or timing/speedup claims.

Standalone host tests: `python3 -B test_boundary.py`. With `--build BUILD` they
also use the real GNU ELF for synthetic retirement/trap mutation checks. No
synthetic trace is counted as hardware acceptance.
