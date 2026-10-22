# FP Scalar Insert: Before and After

## Latest Candidate03 Result

The parent's two scalar-insertion decode changes were frozen and built separately.
**Candidate03 passes11/11 focused tests**: the exact four original ELF inputs plus
seven integer/stored-EEW supplements. Integer same cause was first measured on
candidate02; four real after captures show the two-byte write enabled, and all
seven normal/no-op controls retain byte-identical full commit traces.
See [candidate03 review and measured hashes](CANDIDATE03_REVIEW.md) and
[independent audit](candidate03_audit01/finding.json). No additional RTL edits
were made by this agent. The candidate02 evidence below remains unchanged;
neither these11 nor candidate02's38 PASS count as a full candidate03 arithmetic
or original Linux partition regression.

The subsequent [representative16 replay](CONTROLS16.md) also passes on the same
candidate03 image: unchanged candidate02 ten smokes plus six singles, all full
oracles PASS and all16 complete cycle traces byte-identical. No rebuild or RTL
edit;1305 pins unchanged. This is representative acceptance, not all38 replay.

## Historical Candidate02 Result

Real candidate02 SoC replay reproduces the archived e16/m1/op6 numerical failure.
No production RTL, sealed helpers, or image were changed. Four ELFs ran serially,
with a 180-second bound each; the original ran with a bounded UCLI capture.

| Source-derived case | Architectural VL / vstart | Host oracle | Spike | Candidate02 | Wall seconds |
| --- | --- | --- | --- | --- | ---: |
| Original op6 | 2 / 1 | PASS | PASS | FAIL, element0 expected 0, actual 0x7bff | 35.26 |
| start0 | 2 / 0 | PASS | PASS | PASS | 22.55 |
| start==VL | 2 / 2 | PASS | PASS | PASS | 25.51 |
| VL0 | 0 / 1 | PASS | PASS | PASS | 23.01 |

The original returned vstart=0 and fflags=0, preserved the scalar-result sentinel
and both 0x5b guards, and reported exactly one numerical error. Simulator process
returncode was 0 even for this architectural FAIL; the oracle and tohost failure
remain authoritative. This is the genuine archived single-stimulus source port,
not execution of its full 21,504-configuration Linux partition.

- [Four terminal results](candidate02_before01/complete.json)
- [Original console](candidate02_before01/fp_move_original/console.log)
- [Spike references](port02/reference.json), [host oracle checks](port02/host.json)
- [Cycle finding](cycle01/finding.json), [pre-edge samples](cycle01/cycles.csv)
- [Original source selection and lineage](SELECTION.md)

## Cycle Evidence

The samples are taken immediately before rising edges using the commit monitor's
cycle convention, not values after sequential updates. Only the target opcode
42005c57 and its assigned VID0 are used to attribute execution and completion.

| Cycle | Target event | Relevant values |
| ---: | --- | --- |
| 6845 | Front request accepted | Architectural VL2, vstart1 |
| 6846 | Registered backend request accepted | VFMVSF, internal VL1, vstart1, boxed scalar 0xffffffffffff0000 |
| 6847 | Lane0 accepts | VID0; only lane0 has one result element |
| 6848 | VALU accepts | Local VL1, vstart1 |
| 6849 | VALU issues | Correct data0, result_write.be=0 |
| 6850 | Result request/grant and VALU done | VID0, data0, BE0; no bytes written |
| 6851 | Sequencer completion trace | One target uop_done |

The CVA6 target retirement at 6847 does not prove a data write. The recorded
result handshake has BE0, and the later original whole-capacity store and scalar
oracle observe unchanged element0=0x7bff. This discriminates write qualification
from scalar boxing/data generation, final readback layout, and completion stalls.

The frontend CSR has already reset to zero by backend cycle6846, but the accepted
request retains vstart1. The defect is not a lost CSR write: it is the incorrect
internal element interval retained for this scalar insertion. Changing CSR timing
would be unrelated and could break the architectural empty-operation check.

The three controls have one target retirement each. start0 allocates/completes
one uop; start==VL and VL0 allocate no backend uop and preserve the entire vector.
There is no maintenance-loop inference from these traces.

## Root and Scoped Repair Boundary

Static code and measurement agree:

- `ara_dispatcher.sv:3888` reduces VFMVSF's internal VL to1 without changing the
  internal vstart. The architectural gate at5962 correctly compares CSR vstart
  against CSR VL, allowing the original1<2 case and rejecting the two controls.
- `lane/lane_sequencer.sv:448` maps global start1 to lane0 local start1.
- `lane/valu.sv:943` intersects the one-element BE with the ordinary prestart
  mask, suppressing element0. `lane/simd_alu.sv:571` already supplies correct data.

The minimal repair candidate to review is scalar-insertion-specific internal
start0 for a nonempty operation, while retaining the existing CSR-based no-op
qualification. Do not clear csr_vstart early or weaken ordinary ALU/slide prefix
protection. Mixed stored-EEW handling must see the actual element0 write interval.
No repair was applied during this baseline measurement. The later parent patch
and independent candidate03 acceptance are recorded in the latest section above.

`ara_dispatcher.sv:3159` VMVSX has the same VL1/nonzero-vstart decode and shares
the exact lane/VALU/SIMD path. Reserve one e16/m1/VL2/start1 integer insertion
control for the subsequent focused regression. At this baseline checkpoint it
was a static same-cause prediction only; the later integer reproduction and A/B
results are now recorded in CANDIDATE03_REVIEW.md.

## Reproducibility and Scope

`focused.py` reuses the existing software compiler/runtime and image-validation
helpers without editing them. Original scenario.S, inputs.h and operations.h are
byte-identical copies, and the entire executable oracle block is unchanged.
The only driver changes are Linux output/exit/startup adaptation, the inactive
Linux drain wrapper, and the explicitly authorized VL/start control values.

The host fixture runs the unchanged oracle with a scalar model: four normal
checks plus eight omission/tail-corruption checks, all12 as expected. It is an
oracle sanity check, not evidence that hardware executes correctly. Spike4/4
uses `rv64gcv_zvfh_zvl1024b`. `port01` is retained as a failed reference setup:
the first command omitted Zvfh and all four trapped at vfmv.s.f; no RTL run used
that failed gate. `port02` corrects only the reference ISA parameter.

Original Linux target PC is0x106f0. The port's original SoC target is0x800006ec,
Spike target0x800006f4. Complete per-control mapping and ELF/disassembly hashes
are in [address_map.json](port02/address_map.json).

- Original SoC ELF SHA256: `0804702683213a3dbbf9b7ec412767e36f33d3c05910c3a21fffe88b0defb0f7`
- Candidate02 image ledger SHA256: `384515b7365200942d08fc7b34275d10eee676cf6ce0574935043020e87c7810`
- Prepared provenance SHA256: `8b254c420c7c6d4cccdc928ba55ca93d5957864a7fbcc52652bc78316aa501a7`
- Four-result complete SHA256: `c003679710a6daaa4e46da79c55389aca8c4cea5c4daa1872ea0c8467b246479`
- Cycle finding SHA256: `987e46a22e77729e4ee8cf837fef32c4ffc701c44a1d3c44c26035b7775157a5`

Before every launch, the runner checked the global24-simv cap and MemAvailable
>=32GiB, retaining NF7 two slots and alias one slot. Recorded existing simv counts
were19/19/23/23, so this serial addition stayed within24; available memory was
at least184391434240bytes. No other process was stopped or reconfigured.
All recorded image and input pins remained unchanged after the four runs.

Reproduction commands require fresh owned output directories and available slots:

```sh
python3 focused.py build --out /absolute/path/to/fp_moves/new_port
python3 focused.py replay --build /absolute/path/to/fp_moves/new_port --out /absolute/path/to/fp_moves/new_before
python3 analyze_capture.py /absolute/path/to/fp_moves/new_before/fp_move_original --out /absolute/path/to/fp_moves/new_cycles
```

No new simulation is implied by these commands. Full original partition coverage,
integer insertion, unboxed scalars and other SEW/LMUL configurations remain outside
this four-case measurement.
