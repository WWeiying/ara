# V9 Decoder and RAM Probe Repairs

V8 BUILD05 stopped generating decode-Xaraakv.c.inc: the five akvexec patterns
left top7 unspecified (`.......`) without an extracted field. V9 changes only
these five top7 patterns to ignored bits (`-------`). It does not constrain
funct7 to zero. The translator still forwards the complete original opcode;
the architecture helper retains all reserved-field validation.

The second approved copy-only repair adds RAM classification after the existing
TLB/host checks. Under an RCU read lock it resolves the host MemoryRegion,
requires RAM and not ROM, and checks offset/chunk against region size. It
unlocks before raising an access exception. Physical ROM/ROMD is rejected;
virtual read-only mappings backed by DRAM remain readable. The old flags/host
test alone cannot reject ROMD reads. Includes add system/memory.h and qemu/rcu.h.

The source is a new independent copy of variant02, retaining the full tracked
DTC restoration and CharFrontend repair. The original variant02, BUILD05,
frozen helper files and all guest ELFs remain unchanged. Only the exact empty
Meson subprojects/.wraplock is omitted when copying, and required separately
after the build. All other source bytes, topology and modes are checked.

Host checks use the pinned real scripts/decodetree.py: the old decoder must
fail with the reported missing-bit diagnostic; the repaired decoder must
generate successfully. A native C harness exercises all funct7/funct3 choices,
INFO reserved fields, resident opcodes, legacy opcodes and raw reserved-word
forwarding. A separate native harness executes the exact repaired probe body
with mock regions, covering ROM/ROMD/null/MMIO, DRAM, bounds/overflow, cross-page
reads and unlock-before-trap. These are host contract tests, not native guest
or arithmetic acceptance. Build receipt
mutations retain the previous identity, argv, timeout and ownership checks.

Preparation requires the frozen passing 12-test host receipt. James separately
probes the actual repaired QEMU helper with BUILD05 compile commands before
launch; his earlier four-TU probe covers the decoder-only repair.
Configure flags/environment remain V5/V4: Python3.11, offline wheels, explicit
internal FDT, downloads disabled; configure900s, Ninja1800s/-j4, direct systemd
Type=exec worker, 3000s/8GiB bound. No guest execution or timing claim here.

Host01 retained a generated-code unused-parameter warning failure; host02
decoder-only passed nine tests/65548 routing checks. Its three owner sources
are sealed in OUT/stage5_qemu_v9_decoder_only_sealed_20261110_01. Decoder-only
prepare was interrupted during read-only parent hash verification before any
variant/output creation, after the parent authorized combining the ROM fix.
Host03 and the actual variant03 contain both repairs. Existing helper sources,
host receipts and BUILD05 remain unchanged.

The first merged preparation stopped before copying: BUILD05 configure created
one additional empty tests/qemu-iotests/scratch directory. Its Meson log line
4888 records check -n; testenv.py:123-124 creates cwd/scratch. Existing source
pins passed; the complete name/type delta was exactly this directory, with no
missing paths, type changes or new files. This failure and its three owner files
are retained in OUT/stage5_qemu_v9_prepare_preflight_20261110_01. Host04 supersedes
host03 for preparation. The strict V9 parent adapter retains every original V8
receipt/artifact/content/tree/mode check, allowing only this exact empty,
non-symlink directory. It is copied, inventoried and recorded before/after the
new build. Any child, symlink or other addition still fails. No original source
or metadata is removed. PYTHONDONTWRITEBYTECODE=1 was already set and unchanged.
