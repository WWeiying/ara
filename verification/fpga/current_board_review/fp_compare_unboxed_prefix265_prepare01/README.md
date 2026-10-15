# Original Unboxed FP Compare First265

Software reference only, pending independent review; no DUT execution/build.
Original parent: rvv_fp_compare_unboxed_unmasked_e16_mf4, ELF
404b2c0bb8f9224dc5e281ad1ef83faee238dec1989b26b36d7dbc12e4c3b152.
The rebuilt Linux ELF is byte-identical. All ten original helpers and capacity
match actual original machine-code bytes, including unboxed lhu/fmv.d.x.
Only Linux wrapper adaptation and an after-oracle stop at call265 were added.
Original first264 predecessors,128-byte masks,16-element a/b initialization,
130-byte output initialization, allowed tail alternatives, flags save/restore,
4240 result bits,530 guards,265 vstart and265 flags checks are retained.

The sole reference used rv64gcv_zfh_zvfh_zvl1024b,2M steps,256MiB raw/120sec.
Compiled static upper estimate was1,356,100; actual firmware through successful
HTIF was701,895, elapsed1.27028sec. Raw has5 reset-ROM instructions,701,895 firmware
instructions and3,100 original post-HTIF a001 parking instructions; no extra call
or code was allowed after exit. Raw size45,935,822bytes. Full reference source,
vector result/store, scalar bit oracle, CSR and instruction-window checks passed.
The exact original target is op4/seed0/VL15/mask0/sticky0 after264 predecessors.
This is not the original17,920-call parent or Linux runtime acceptance.

Host model independently checks1536 fixture entries: two positives (including
permitted all-one tails) and seven rejecting mutations (active bit, NV, two
guards, returned vstart, VL0 preservation, incorrectly treating unboxed zero
as boxed zero). See host01/result.json. These are software tests, not RTL evidence.

prepare.py was the executed compilation entry. software_prepare.py is an exact
copy for imports: naming an imported local module prepare shadowed the existing
integration prepare helper. The first Host import failed before any Host build;
the alias corrected that Python namespace collision without recompiling ELFs or
changing their source. No failed/reference attempt was deleted or retried.
strict.py was complete before the single reference run; later Host-only probes
may reuse its unchanged checker. Original files and shared helpers were not edited.

Reference reproduction is archival only, not permission to repeat:
python3 -B reference_once.py (refuses existing reference01).
Host: python3 -B host.py (refuses existing host01).
Static cost: static_cost.json. Proof/pins: source_elf_proof.json,baseline_pins.json,
reference01/input_pins.json,READY.json. The next DUT plan must separately bind an
actual independent reference acceptance and new parent authorization before run.
