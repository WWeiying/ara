# Experimental F32 paired-head PV

Isolated leaf only. No canonical caller, environment selector, context ownership,
GGML admission, or GQA6-special dispatch is changed.

```c
void akv_experimental_pv_f32_pair(const float *score, float *output,
                                const float *old_scale,
                                uint32_t tokens, uint32_t head_dim);
```

The caller supplies exactly two real heads of the same query and resident KV
group, D64/96/128 and T1..64. Score head stride is 256 bytes, output head stride
is **4*D bytes** (256/384/512), and scale stride is 4 bytes. Output is FP32,
not the decode workspace's F16 accumulator. Validated non-overlapping input,
output and workspace extents and four-byte F32 alignment are prerequisites.

GNU integer ABI a0..a4 is used; D is saved before reusing a4 as the second
output pointer. No calls, stack or scalar callee-saved writes. Caller-saved
v0..3 and v4..7 hold FP32/m4 numerators, v8..9 receives FP16 V, and v12..15
holds the shared widened FP32 V. VLEN1024 and the existing RVV/Zvfh native
environment are assumed; this is not a generic-VLEN library entry.

Each output starts with the canonical separately rounded FP32 scale multiply,
then exactly T FP32 fused multiply-adds in increasing token order. Score and
scale remain FP32. Finite FP16 V widening is exact. The two heads interleave
independent FMA chains without changing either chain's arithmetic. No CSR is
written. RNE numerical/flag behavior is host-mapped below; actual hardware
FCSR/VCSR preservation still requires a native gate.

Per pair: T V commands, T widening conversions, 2*T vector FMAs, two scale
multiplies, two output loads and two stores. Logical resident replay is 2*D*T
bytes instead of 4*D*T. External KV reads and scalar FMA work are unchanged;
this is not a speedup measurement. Capability/shape selection and FULL/REFILL/
RELEASE remain the caller's responsibility, before any partial execution.
PV requires existing row view/tail/D capabilities, not a new PANEL4 instruction.

Future head iteration advances score by 512B, output by 8*D bytes and scales
by 8B per pair. An odd real head MUST call the existing generic F32 PV with
q_rows=1 at that head's actual pointers. Do not fabricate a second row or add
zero-weight FMAs. This leaf has no odd-tail entry; object checks cannot certify
an unimplemented caller. Preserve the existing D128/GQA6 six-head shared PV:
replacing it with three pairs would increase V replay.

The leaf does not make output fault-atomic: it stores both rows after the loop,
whereas head-major generic can store its first row earlier. A replay/trap must
follow existing failure/ownership rules, never silently retry through another
kernel. No cross-query pairing, mask reinterpretation, or RELEASE is introduced.

## Host-only object gate

```sh
python3 -B verification/akv/paired_heads/f32_pv/build.py \
  --output verification/out/akv-f32-pv-object-20261024-01
```

The fresh GNU object is linked without relaxation, and the function's actual
ELF machine words are decoded by a deliberately narrow mapper. Every D and
T1..64 is checked; directed exact/rounding/range/invalid profiles augment those
192 shapes. Exact integer RNE operations are compared against an independently
compiled head-major scalar C `fmaf`/`fenv` oracle, with guards, read extents,
register groups, scale order, token order, replay/conversion count and output
stride checks. Every case compares newly raised flags from zero; separate cases
check preexisting sticky flags so they cannot hide missing exceptions. Raw
instruction mutations test the checker. Host NaN outputs
are canonicalized for comparison with RISC-V; V inputs are finite F16.

This is not native execution, an ISA model, full IEEE validation, a trap/reset
test, an odd-tail integration test, actual CSR proof, or performance acceptance.
No VCS/QEMU/Spike is launched by the builder. Runtime integration must use this
same leaf only after independent native/RTL and complete-operator gates.
