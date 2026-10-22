# Read-only VCU118 readiness audit

Scope: `/home/wangwy/openproject/ara_dsa_verification` only. This preparation
does not authorize programming, reset, serial/JTAG access, synthesis, or RTL
changes. Existing `check_sources.py` and `check_run.py` are unchanged. CVA6
integration and runner protocol acceptance remain with their respective owners.

## Repeatable inventory

From this worktree, choose a **new** result name:

```sh
python3 -B verification/fpga/readiness.py \
  --output verification/fpga/reports/readiness-next.json
python3 -B verification/fpga/check_sources.py \
  --output verification/fpga/reports/source-correspondence-next.json
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=verification python3 -m unittest \
  discover -s verification/tests -p test_fpga_readiness.py -v
```

`readiness.py` launches **no subprocesses**. It reads regular worktree files,
directory/stat/readlink metadata, and five USB sysfs text attributes. It never
opens UART/JTAG/USB device nodes or contacts a hardware server. SDK/PATH checks
are metadata only, not executions or license/version checks. Only the exclusive
JSON output is written, beneath `verification/fpga/`; symlink inputs and output
parents are rejected for worktree content. File inspection is bounded to 512 MiB
per file; discovery to 50,000 file entries. Special files are not opened.

Optional `--bitstream`, `--linux-dir`, `--replay-elf`, `--llama-elf`, and `--model`
select worktree-local inputs explicitly. `--sdk` selects metadata-only SDK
hints. `--dev-root` and `--sys-root` allow offline fixtures. The default discovery
roots are `hardware/fpga`, `hardware/build`, `verification/out`, and `apps/bin`;
symlink directories are listed but not traversed. This is not a host-wide search.

Inventory states have deliberately narrow meanings:

- `available`: regular, nonempty bytes were hashed, or metadata was observed.
  A file named `.bit` is not thereby a valid or programmed bitstream.
- `missing`: absent in the stated local scope, not absent on every host.
- `unknown`: not selected, unreadable, unsafe, beyond bounds, or not measured.
- Overall `BLOCKED`/`UNVERIFIED` never means signoff. Exit 1 means the inventory
  was written but cannot establish readiness; exit 2 means output/argument error.
  `ready_for_signoff` is always false. An all-files-present fixture remains
  unverified, even with `COMPLETE`, `PASS`, or console markers.

## Observed September 22, 2026

The machine-readable snapshots are in `reports/readiness-final-20260922.json`
and `reports/source-correspondence-20260922.json`. Earlier readiness JSONs are
retained, not overwritten. Reports are observations at their timestamps, not
permanent assertions while other agents continue working.

All 19 temporary-fixture tests passed (`reports/readiness-tests.txt`).
`reports/prep-sha256.txt` identifies the tool, tests, final JSON, source audit,
and unchanged existing checkers. No test uses live device or SDK paths.

1. **No local programming artifact.** No `.bit`, `.ltx`, or `.dcp` in the
   inspected trees. `/dev/serial` is absent; no `ttyUSB*`/`ttyACM*` nodes or sysfs
   tty candidates. Twelve USB device/root-hub entries were readable; none had
   Silicon Labs, FTDI, Digilent, or Xilinx vendor hints. Board power, physical
   location, cable identity, remote hw_server, and programmed design are unknown.
2. **Export is identified, not current-source-approved.** Manifest SHA-256
   `0157af3a60db3eb82ea56d234b252715285e27faa2c133b6eccd15d796262eae`;
   checksum-list SHA-256
   `f3423352c61efa2764ebbcdef8ba6beb001d1bed6e3d328b2af091cf616cb4bf`.
   Recorded Ara revision is `3e494a0781fcd4e888edeade0338b8778965b5a4`,
   CVA6 revision `b29fd3cf906e7f4c71da4c2f46451c4c60a4487f`, with recorded local
   changes. Recorded creation time is `2026-09-09T06:20:43.843298+00:00`.
   The export declares VCU118 `xcvu9p-flga2104-2L-e`, 50 MHz, four lanes,
   VLEN=1024, QBS/AKV/AKV-v2 enabled. These are source-package claims, not
   observations of a programmed board.
3. **Fresh source audit rejects correspondence.** All 761 listed checksums
   validate. Of 672 RTL/header files: 433 matched, 8 differed, 5 adaptations
   await review, and 226 lack mapped sources (primarily FPGA dependencies).
   Both `rtl/cva6/core/acc_dispatcher.sv` and `issue_read_operands.sv` differ.
   VMFPU is byte-equal. Do not overwrite either CVA6 version to close this gate.
4. **Historical route success is not a bitstream.** Exported
   `reports/audit_56a5c7fb455b/completed_audit.json` records a Windows routed
   checkpoint, 442,131,834 bytes, claimed SHA-256
   `b44d8c9507c696eb0d667309c183ea521a185d8ef4bc60f604c8751974551b7f`.
   Its timing report has WNS 0.023 ns, WHS 0.010 ns, zero failing endpoints;
   metadata says `BitstreamGenerated=false`, `ManualReviewRequired=true`.
   The referenced Windows DCP itself is unavailable here. No inference about
   the current export's timing is justified by these historical reports.
5. **Tools:** Vivado, hw_server, OpenOCD, QEMU, and generic RISC-V GCC names
   were not on PATH. `/usr/bin/dtc`, `cpio`, and `readelf` were available.
   The explicit CVA6 Buildroot SDK compiler/readelf/strip, OpenSBI 1.7 Makefile,
   kernel, BusyBox and three runtime libraries were present by metadata. This
   is not a claim that compilers work or that QEMU is absent outside PATH.

The one board-owner question needed before execution is:

> Which host owns the VCU118, what is its CP2105 Enhanced UART path/COM port
> and JTAG cable or hw_server endpoint, and where are the matching .bit/.ltx
> and export/build manifest (including boot baud)?

COM6/COM7 in historical instructions are examples, not discovered ports.
The loader defaults to 115200; 1562500 requires the matching fast-boot image
and Enhanced interface, then console switching to 115200. The external CPU
J53 JTAG path is distinct from FPGA programming USB-JTAG; the packaged docs
limit J53 TCK to 1 MHz. Neither path was exercised.

## Linux image gate

All four historical payloads exist under
`hardware/fpga/ara_dsa_vcu118/linux/artifacts/`; the readiness report records
their actual sizes and full hashes, matching the adjacent `SHA256SUMS`:

| Payload | SHA-256 |
| --- | --- |
| `fw_jump.elf` | `f82364b2b910bbb964f6bed1c7d76ce3cc9920e38be0ccda8ca43c829afef734` |
| `Image` | `716aef49389b25a0a3f4deac47de0bb69467a10f1057041cecd0f0621fbbf285` |
| `ara_vcu118.dtb` | `ff3024920cb210cc5bebd12e7950a183370653b19ecb50ba0098b023c5470845` |
| `initramfs.cpio` | `e98ae673a251ee2ddf362fb3f18fd2ac12b7625c7087d2af2842857230b6106a` |

The saved read-only cpio listing (`reports/historical-initramfs-list.txt`)
confirms `/lib` libraries but no `lib64 -> lib`. The prior isolated boot
failure is documented in `verification/linux/README.md`; the current builder
fix does not modify this historical binary. This exact image hash is a known
blocker in the preflight, not a heuristic applied to other cpio files.

The checked replacement at
`verification/out/linux-userspace-20260922/payload-checked/initramfs.cpio`
is 3,183,104 bytes, SHA-256
`6ef0ee1a3f279b59d628c5e1ba435125d0b0b0eaeb12b265db387948ccf26ef3`.
Its `rvv_linux_smoke` ELF hash is
`5792ed0a3fc5b5144a035423953eab5b07f828764c08266ef0180ab268c7ad5b`.
The decoded packaged DTB (`reports/historical-device-tree.dts`) advertises
initrd `[0x88000000,0x88251c00)`, for the old 2,432,000-byte cpio. The replacement
requires end `0x88309200`. Rebuild both the external DTB and OpenSBI with that
DTB embedded; retain the load map: firmware `0x80000000`, DTB `0x80100000`,
kernel `0x80200000`, initramfs `0x88000000`. Verify nonoverlap and all identities
before deployment. The original read-only audit did not rebuild or load images;
the separate software-only preparation below addresses the image-matching gap.

## Isolated Linux bundle

`prepare_linux_bundle.py` builds new OpenSBI firmware and a matching DTB around
the **existing checked cpio**. It does not extract/repack the rootfs, rebuild the
kernel, execute QEMU, access a board, or update the old export or SDK build.
The checked cpio's full SHA-256 is enforced, not merely recorded.

```sh
python3 -B verification/fpga/prepare_linux_bundle.py \
  --output verification/out/fpga-linux-userspace-bundle-20260922 --jobs 4
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=verification python3 -m unittest \
  discover -s verification/tests -p test_fpga_linux_bundle.py -v
```

The output must be new or empty, below this worktree's `verification/out`, and
independent of all inputs. It is reserved exclusively. Never reuse the command's
output name after a completed/failed preparation; choose a new directory.
Symlink input/output components, special input files, unsafe make-recipe paths,
missing inputs/tools, and a different cpio hash are refused. The SDK compiler
is invoked by its `riscv64-buildroot-linux-gnu-gcc` name, not its resolved
`toolchain-wrapper` name. Native commands are argv lists, never shell strings.
Build environment overrides are not inherited; host PATH is `/usr/bin:/bin`,
cross tools have explicit SDK paths, and `SOURCE_DATE_EPOCH=0`.

The preparer copies and hashes OpenSBI 1.7 sources under `inputs/opensbi-1.7`,
excluding the SDK's old top-level `build` and `.git`. It compiles **that snapshot**
using `O=<new-output>/opensbi-build`, `PLATFORM=generic`, RV64, `FW_JUMP=y`,
`FW_DYNAMIC=n`, `FW_PAYLOAD=n`, and the original builder's four load addresses.
The supplied DTS template, original builder and preparer are archived as inputs.
Kernel and cpio are independent byte-identical copies, not symlinks/hardlinks.
No `make` target executes in the SDK source directory.

Acceptance before publishing `manifest.json` requires:

- `fdtget -t x` returns `/chosen` initrd start `0 88000000` and end
  `0 88309200`, and DDR base/size `0 80000000 0 80000000`.
- `readelf -h -lW -sW` identifies an ELF64 little-endian RISC-V executable
  entering at `0x80000000`; file-backed/memory PT_LOAD sizes, alignment,
  executable entry, DDR bounds and pairwise nonoverlap are valid. Firmware
  stays below `0x80100000`; its BSS is included in the overlap check.
- The ELF's file-backed bytes at `fw_fdt_bin` match the entire external DTB,
  and the `_jump_addr` value is `0x80200000`. Build arguments alone do not
  establish embedded-DTB equality.
- The complete firmware/DTB/kernel/cpio load map does not overlap. Original
  inputs, copied kernel/cpio, DTB, deployed ELF, source snapshot, original source
  and recorded native tool identities still match their earlier hashes.

The manifest identifies source files/tree digest, original input hashes,
compiler wrapper/backend and helper identities, environment, exact commands,
DTB values, ELF segments, embedded-DTB bytes and generated files. `SHA256SUMS`
covers archived inputs, logs, build products/configuration and deployable files;
the manifest records its hash. Neither file claims to authenticate provenance
or capture every host OS/dynamic-library dependency. On error only `failure.json`
is published, with logs; partial outputs are not a usable bundle.

The deployment quartet is `fw_jump.elf`, `ara_vcu118.dtb`, `Image`, and
`initramfs.cpio` at the unchanged load addresses above. A successful preparation
has status **PREPARED_NOT_BOOTED**, `board_boot=NOT_RUN`, and
`custom_compute=NOT_VALIDATED`. It closes image consistency only, not bitstream,
DDR hardware, Linux board boot, or QBS/AKV computation/context isolation gates.
This checked cpio still shuts down after its userspace tests and contains no
full llama.cpp/GGUF. Its previously validated QEMU payload is not rerun here.

### Prepared September 22, 2026

The command above completed successfully in
`verification/out/fpga-linux-userspace-bundle-20260922`; OpenSBI compilation
took 15.05 seconds. The bundle contains these actual deployable files:

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `fw_jump.elf` | 253328 | `e83922577fa0ba66501d04b2a996716382c39aa1cbcd46baf2d90415058514c2` |
| `ara_vcu118.dtb` | 1770 | `ada7a97cab8458abb62ed00a530a2a8c14029ebbd8498d08bd91cd5ab7ee285d` |
| `Image` | 27412480 | `716aef49389b25a0a3f4deac47de0bb69467a10f1057041cecd0f0621fbbf285` |
| `initramfs.cpio` | 3183104 | `6ef0ee1a3f279b59d628c5e1ba435125d0b0b0eaeb12b265db387948ccf26ef3` |

The 458-file frozen OpenSBI source inventory has tree digest
`d4df71f740c1d164b1b8b0b8dab53c98ade52179036059b90512919c2ea7f473`.
The completed manifest has SHA-256
`0c44b8193cff2bd2c38a128cf56ee6899ca9da9dee9260b81e5f89fb3af561fb`.
It records `inputs_unchanged=true`. The original checked cpio, old exported
cpio/firmware/DTB, DTS template and SDK kernel retained their pre-build hashes.

Independent `sha256sum --check --quiet SHA256SUMS` passed. Independent `fdtget`
returned `0 88000000`, `0 88309200`, and `0 80000000 0 80000000` for the start,
end and DDR region. Firmware PT_LOAD memory intervals are
`[0x80000000,0x80028fe8)` and `[0x80040000,0x80043da8)`; the second includes
BSS. The embedded DTB at `fw_fdt_bin=0x80021000` (ELF file offset `0x22000`)
matches the external DTB hash above. All 17 bundle tests and 19 existing
readiness tests passed. No board boot, custom compute, or new QEMU run occurred.

## Separate runtime gates

`verification/out/linux-userspace-20260922/qemu-checked-vlen1024/console.log`
(SHA-256 `da16f93d6d285d5d63af14568597cbe8b55e2f6a5e4fb7a9b27ed1f11a28d9ff`)
reports vlenb=128, standard RVV arithmetic/load/store, reduction, two-process
preemption, signal return and scalar/illegal-instruction fault return. Its
userspace checker records stage **QEMU**, not FPGA. The same log explicitly has:

```text
[LINUX_CUSTOM_CAPS] QBS UNAVAILABLE signal=SIGILL
[LINUX_CUSTOM_CAPS] AKV UNAVAILABLE signal=SIGILL
CUSTOM_COMPUTE=NOT_VALIDATED
```

Keep these acceptance gates independent:

| Gate | Current evidence / missing evidence |
| --- | --- |
| Linux + ordinary RVV userspace | Existing QEMU evidence above; VCU118 execution still unknown |
| Custom capability query | QEMU SIGILL means unavailable there; board query result unknown; a successful query still proves no computation |
| QBS/AKV numerical computation | Needs Linux virtual-address inputs from real llama.cpp captures, golden comparison, and proof of native dispatch rather than RVV fallback |
| Shared DDR/MMU/cache | Needs page-crossing and permission/fault cases, scalar-to-accelerator and accelerator-to-scalar visibility, fence/order/completion checks, and no stale response crossing ownership changes |
| Hidden persistent context isolation | Needs OS task/address-space ownership plus save/restore or drain/invalidate/rebuild semantics; ordinary RVV state preservation is insufficient |
| Full llama.cpp | Needs an identified Linux executable, GGUF, ABI/capability/shape selection, fallback, storage/transfer plan, and a measured 2 GiB DDR budget including KV and scratch |

Static wiring is not runtime proof: exported `cheshire_soc.sv` sets
`OSSupport=1`; `hardware/src/vlsu/vlsu.sv` arbitrates MMU and AXI ownership for
normal/QBS/AKV traffic. That is **transaction** ownership, not Linux process
ownership. QBS activation data and AKV Q/K/V state reside outside the VRF;
their context interfaces do not establish task/ASID isolation. CPU affinity
and a process-local mutex do not protect against another process.

Before enabling persistent custom contexts in Linux, specify who owns each
context, how outstanding requests drain, and what happens on preemption,
signal/fault return, exit/exec, mapping changes and stale token reuse. Test
A/B processes using the same virtual addresses with different physical pages
and data, force switches and fault recovery, then require either preserved
owner-specific results or explicit invalidation and rebuild. AKV release and
QBS RELEASE are not interchangeable: QBS RELEASE is post-compute invalidation,
not a general standalone OS flush. No new hardware policy is implemented here.

The rootfs has no full llama.cpp/GGUF. The checked test init shuts down after
testing; it is not the final interactive model rootfs. Start with standard RVV
fallback, close the memory/context gates, then enable custom dispatch selected
by actual type/shape/capability and retain standard RVV fallback. A packaged
bare-metal operator replay is useful, but not Linux custom-runtime signoff.
See [REPLAY.md](REPLAY.md) for exact ELF identities and the replay gap.
