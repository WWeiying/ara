# FPGA Source Origins - 2026-09-22

## Scope and conclusion

Measured at 2026-09-22T23:07:28.475677+00:00; resolver metadata inspected at 2026-09-22T23:08:41.031244+00:00.

Scope is exactly the 226 `missing_source` records in `/home/wangwy/openproject/ara_dsa_verification/verification/out/fpga-rtl-handoff-20260922/source-audit.json`. This is an origins supplement, not a new acceptance result, source export, waiver, functional-equivalence review, or EDA signoff.

- Located: 226/226 actual source files and 226/226 blobs at the manifest-pinned commits.
- Actual source bytes equal pinned blob bytes: 226/226. All 16 checkout HEADs equal their declared pins.
- Direct source/blob-to-export byte matches: 221. Exactly reproduced adaptations: 5, from both disk files and pinned blobs independently. Unexplained exports: 0.
- Truly missing within this scope: 0, meaning neither the explicitly mapped source file nor its pinned blob is available. This does not say the verification worktree has been populated: all 226 original audit source paths remain absent.
- Pre-integration SHA256 declarations: 224 present, all independently confirmed against both source files and pinned blobs. Two board records have no such declaration; they are NOT counted as declaration matches.
- 214 records are marked compiled in the audit; 12 are packaged non-compilation entries. No compilation or elaboration was performed.
- The original `accepted: false` is unchanged. Its 429 `matched`, 12 `differing`, 5 `adapted_unreviewed`, and 226 `missing_source` counts are historical audit results, not rewritten by this report. The 17 non-missing discrepancies are outside this task and remain unresolved here.

Only this report is written. No source, cache, checkout, export, manifest, checksum file, checker, exception file, or candidate artifact is changed. No prepare/export/build/EDA command, checkout, fetch, reset, or full-disk search is performed.

## Evidence semantics

Every subject path comes directly from the audit inventory. Non-board source locations use the exact package root in the main checkout's `hardware/fpga/vcu118/.cache/roots.json` plus the path after `rtl/<package>/`. Board files use the explicit `export.py` mapping to `.cache/cheshire_board/target/xilinx/src/`; their pin is `manifest.cheshire_board_port_commit`, not `board_definition_tree` (the latter identifies Xilinx board definitions and is not the origin of these two RTL files). No alternate checkout is guessed or searched.

Revisions and source hashes in metadata are declarations. The actual checks separately read each file, resolve `<pin>:<relative-path>`, read its Git blob with `git cat-file blob`, compute SHA256 from both byte strings, verify their full byte equality, and compare against the actual export bytes. Each Git object ID is additionally recomputed as SHA1 of the Git blob header plus contents. The 40-hex Git OID is NOT a SHA256 file hash.

The current manifest revisions equal `source-audit.json.export_recorded_revisions`. All 226 current export SHA256 values equal the audit's recorded export hashes; all 226 audit declaration values, including the two nulls, equal the current manifest lookup. Inputs read in the main audit were rehashed after measurement with no changes observed. This is a bounded evidence check, not a whole-filesystem integrity assertion.

Git queries disable optional locks and fsmonitor; the audit process also sets `GIT_NO_LAZY_FETCH=1`. Python uses `-B`. Only already-inspected pure function/constant AST nodes are evaluated in memory, so importing the exporter, executing its entrypoint, and creating bytecode are avoided.

## Package counts

`Direct` and `Adapted` are disjoint and sum to `Total`; `Located file/blob` and `Source=blob` overlap them. `Declared verified` counts only existing pre-integration declarations. `Dirty RTL` refers only to these subject files, not the whole repository.

| Package | Total | Located file/blob | Source=blob | Direct | Adapted | Declared verified | Truly missing | Dirty RTL |
| --- | ---: | --- | ---: | ---: | ---: | --- | ---: | ---: |
| `apb_uart` | 14 | 14/14 | 14 | 14 | 0 | 14/14 | 0 | 0 |
| `axi_llc` | 26 | 26/26 | 26 | 26 | 0 | 26/26 | 0 | 0 |
| `axi_riscv_atomics` | 9 | 9/9 | 9 | 9 | 0 | 9/9 | 0 | 0 |
| `axi_rt` | 16 | 16/16 | 16 | 16 | 0 | 16/16 | 0 | 0 |
| `axi_vga` | 5 | 5/5 | 5 | 5 | 0 | 5/5 | 0 | 0 |
| `board` | 2 | 2/2 | 2 | 1 | 1 | 0/0 (no declarations) | 0 | 0 |
| `cheshire` | 8 | 8/8 | 8 | 6 | 2 | 8/8 | 0 | 0 |
| `clic` | 9 | 9/9 | 9 | 9 | 0 | 9/9 | 0 | 0 |
| `clint` | 3 | 3/3 | 3 | 3 | 0 | 3/3 | 0 | 0 |
| `idma` | 34 | 34/34 | 34 | 34 | 0 | 34/34 | 0 | 0 |
| `irq_router` | 3 | 3/3 | 3 | 3 | 0 | 3/3 | 0 | 0 |
| `opentitan_peripherals` | 39 | 39/39 | 39 | 39 | 0 | 39/39 | 0 | 0 |
| `register_interface` | 23 | 23/23 | 23 | 23 | 0 | 23/23 | 0 | 0 |
| `riscv-dbg` | 11 | 11/11 | 11 | 9 | 2 | 11/11 | 0 | 0 |
| `serial_link` | 18 | 18/18 | 18 | 18 | 0 | 18/18 | 0 | 0 |
| `unbent` | 6 | 6/6 | 6 | 6 | 0 | 6/6 | 0 | 0 |
| **Total** | **226** | **226/226** | **226** | **221** | **5** | **224/224; 2 absent** | **0** | **0** |

## Checkout pins and actual paths

All listed repository roots were checked with `git rev-parse --show-toplevel`; all measured HEADs equal the full pins below. These are existing local checkouts, not newly materialized copies. For the 14 peripheral packages, the pin also equals the revision read from the pinned Cheshire `Bender.lock` blob. Upstream URLs below are declarations from that lock blob (or the Cheshire checkout configuration), not claims of a remote fetch or signature authentication.

| Package | Manifest pin = measured HEAD | Exact actual checkout root | Declared upstream | Tracked changes now |
| --- | --- | --- | --- | --- |
| `apb_uart` | `6c7dde3d749ac8274377745c105da8c8b8cd27c6` | `/home/wangwy/openproject/ara_dsa/hardware/fpga/vcu118/.cache/cheshire_ara/.bender/git/checkouts/apb_uart-38dcfab592cbc1a1` | `https://github.com/pulp-platform/apb_uart.git` | none |
| `axi_llc` | `559bcbd09a5a884dbe31e2d72fd95d024e357f39` | `/home/wangwy/openproject/ara_dsa/hardware/fpga/vcu118/.cache/cheshire_ara/.bender/git/checkouts/axi_llc-5fb8850caad4fcfa` | `https://github.com/pulp-platform/axi_llc.git` | none |
| `axi_riscv_atomics` | `0ac3a78fe342c5a5b9b10bff49d58897f773059e` | `/home/wangwy/openproject/ara_dsa/hardware/fpga/vcu118/.cache/cheshire_ara/.bender/git/checkouts/axi_riscv_atomics-40ad8d2d0e0daa8b` | `https://github.com/pulp-platform/axi_riscv_atomics.git` | none |
| `axi_rt` | `56074a195b1c8b05f4bdd73674e437bbcb35f2cd` | `/home/wangwy/openproject/ara_dsa/hardware/fpga/vcu118/.cache/cheshire_ara/.bender/git/checkouts/axi_rt-7cef46f372eaf0fb` | `https://github.com/pulp-platform/axi_rt.git` | none |
| `axi_vga` | `3718b9930f94a9eaad8ee50b4bccc71df0403084` | `/home/wangwy/openproject/ara_dsa/hardware/fpga/vcu118/.cache/cheshire_ara/.bender/git/checkouts/axi_vga-74c838b44ce780d5` | `https://github.com/pulp-platform/axi_vga.git` | none |
| `board` | `a315a828abb61cf3cb9f4419b910ebe6739b90bf` | `/home/wangwy/openproject/ara_dsa/hardware/fpga/vcu118/.cache/cheshire_board` | `https://github.com/pulp-platform/cheshire.git` | none |
| `cheshire` | `cd73fd892a09da8aa9ae03171c0338bd3873007c` | `/home/wangwy/openproject/ara_dsa/hardware/fpga/vcu118/.cache/cheshire_ara` | `https://github.com/pulp-platform/cheshire.git` | ` M Bender.lock` |
| `clic` | `8ed76ffc779a435d0ed034f3068e4c3334fe2ecf` | `/home/wangwy/openproject/ara_dsa/hardware/fpga/vcu118/.cache/cheshire_ara/.bender/git/checkouts/clic-360fff7ce2d41116` | `https://github.com/pulp-platform/clic.git` | none |
| `clint` | `d5390a805c20f9226758a152ba1645f61da73349` | `/home/wangwy/openproject/ara_dsa/hardware/fpga/vcu118/.cache/cheshire_ara/.bender/git/checkouts/clint-de4a234303f657d0` | `https://github.com/pulp-platform/clint.git` | none |
| `idma` | `ca1b28816a3706be0bf9ce01378246d5346384f0` | `/home/wangwy/openproject/ara_dsa/hardware/fpga/vcu118/.cache/cheshire_ara/.bender/git/checkouts/idma-77bf7fa56d324e6a` | `https://github.com/pulp-platform/iDMA.git` | none |
| `irq_router` | `d1d31350b24f3965b3a51e1bc96c71eb34e94db3` | `/home/wangwy/openproject/ara_dsa/hardware/fpga/vcu118/.cache/cheshire_ara/.bender/git/checkouts/irq_router-376b3d113c15d0ef` | `https://github.com/pulp-platform/irq_router.git` | none |
| `opentitan_peripherals` | `cd3153de2783abd3d03d0595e6c4b32413c62f14` | `/home/wangwy/openproject/ara_dsa/hardware/fpga/vcu118/.cache/cheshire_ara/.bender/git/checkouts/opentitan_peripherals-7b624fb57f78de9a` | `https://github.com/pulp-platform/opentitan_peripherals.git` | none |
| `register_interface` | `ae616e5a1ec2b41e72d200e5ab09c65e94aebd3d` | `/home/wangwy/openproject/ara_dsa/hardware/fpga/vcu118/.cache/cheshire_ara/.bender/git/checkouts/register_interface-902ad5bfde7bb98c` | `https://github.com/pulp-platform/register_interface.git` | none |
| `riscv-dbg` | `358f90110220adf7a083f8b65d157e836d706236` | `/home/wangwy/openproject/ara_dsa/hardware/fpga/vcu118/.cache/cheshire_ara/.bender/git/checkouts/riscv-dbg-1a98531d53bb4602` | `https://github.com/pulp-platform/riscv-dbg.git` | none |
| `serial_link` | `5a25f5a71074f1ebb6de7b5280f2b16924bcc666` | `/home/wangwy/openproject/ara_dsa/hardware/fpga/vcu118/.cache/cheshire_ara/.bender/git/checkouts/serial_link-6e09ea4800bad616` | `https://github.com/pulp-platform/serial_link.git` | none |
| `unbent` | `e9c9d5cfb635f2d4668c816ce9235798cfecb297` | `/home/wangwy/openproject/ara_dsa/hardware/fpga/vcu118/.cache/cheshire_ara/.bender/git/checkouts/unbent-a93c32aef5b319fd` | `https://github.com/pulp-platform/unbent.git` | none |

## Adaptation replay

Both the on-disk source and the pinned Git blob were separately passed through the same pure function. All five results are byte-for-byte equal to the actual current export. This establishes exact generation reproducibility, NOT approval of the adaptation's hardware behavior. `patch_dram` already calls `patch_ready` internally; applying `patch_ready` a second time would not reproduce the exporter.

| Export path | Pure function | Actual source/blob SHA256 | Actual replay/export SHA256 |
| --- | --- | --- | --- |
| `rtl/board/dram_wrapper_xilinx.sv` | `patch_dram (includes patch_ready)` | `68b78ae54ee70a7d67e16fd471c8d6f455bc25b2778a631e87481fa03bd61981` | `c3eea7cfad7a93192b09aa4ae326746ce7bb8c675a9e838e8bd1b502840604a6` |
| `rtl/cheshire/hw/cheshire_pkg.sv` | `patch_soc_pkg` | `ff19556a3a8eef32e72e1a6d7595407585a2544330c74070f54063cc763b505d` | `47c422aebb106973a50b845f3fce1a51541efcb001270bd8b901033cf8a3aca8` |
| `rtl/cheshire/hw/cheshire_soc.sv` | `patch_soc` | `afabcf5fd40b15c897ea8e36a8df17fc2e7c40a62b819a2759b1358b8f3067ad` | `d92a0b504d7da8857d7e4903fae84910c748646ef7ca1b9a122fe6edd124992a` |
| `rtl/riscv-dbg/src/dmi_jtag.sv` | `patch_jtag` | `a3dbcd4190586d11821b798853a17da4a5276a4d9c56b8007340b7919dc58d0b` | `424019b9b1ce656ad810f2135d808f31db6c582344aa5ab26f37fc2401f0153f` |
| `rtl/riscv-dbg/src/dmi_jtag_tap.sv` | `patch_tap` | `7fe8d372125983237b6dd6c76137f10958b2e1222471f82105fe5f8fea935a8a` | `4a893c776f25c27661cd9157eb9ec3ef30ca81ca92541d2d485d57f9189cb975` |

Adapter files were also read from the Ara commit declared by this export and compared with the actual main-worktree files. Both whole files are byte-identical to those blobs and have no path-specific Git status changes. Only the listed helpers/constants are executed; unrelated dispatcher functions are not imported or exercised.

| Actual adapter file | Ara manifest pin | Actual SHA256 = pinned-file SHA256 |
| --- | --- | --- |
| `/home/wangwy/openproject/ara_dsa/hardware/fpga/vcu118/jtag_fpga.py` | `3e494a0781fcd4e888edeade0338b8778965b5a4` | `dd4038fa13a69483f9c7328daa9a6c34867e81b075c4e52bce4fa47d6f4c5315` |
| `/home/wangwy/openproject/ara_dsa/hardware/fpga/vcu118/export.py` | `3e494a0781fcd4e888edeade0338b8778965b5a4` | `0854505b702130f13f8632bbcda5244af9049e4f3df28523d2e8025a2c71f808` |

## Dirty source and handoff risks

1. No dirty subject RTL is required to explain these 226 exports: all source bytes equal their pinned blobs, and path-specific status is empty for every subject. The 15 non-Cheshire repositories have no tracked changes in the measured status; this does not inventory arbitrary untracked or ignored files.
2. Cheshire is NOT a clean resolver checkout. Its manifest declares `tracked_changes: ["Bender.lock"]`, and the actual status confirms that path is modified. Its eight subject RTL/header files nevertheless equal their pinned blobs. The dirty lock replaces nine Git sources with absolute local `Path` sources and null revisions/versions; Ara's dependency list also differs. The untracked `Bender.local` separately repeats those nine path overrides. Consequently a clean checkout of the Cheshire commit alone does not reproduce this resolver environment or certify the overridden Ara/CVA6/FPnew/MVP contents.

   Actual lock: `/home/wangwy/openproject/ara_dsa/hardware/fpga/vcu118/.cache/cheshire_ara/Bender.lock`.
   Actual lock SHA256: `ccb1c60ead581b7dfd47683acb46dc5cafcd419ca85e91e9bb963d81f840b8f9`.
   Pinned lock SHA256: `a58c5ed773d66acbb4df22f3e9f2cc979da04a6df85b5979ab0e9446e2804a61`; Git blob OID: `7dc65b1067ebd50be0a8cde58db117e5424c3ad4`.
   Actual local overrides: `/home/wangwy/openproject/ara_dsa/hardware/fpga/vcu118/.cache/cheshire_ara/Bender.local`; status `?? Bender.local`; SHA256 `1efd2219d2056682d717f5f916e0f047d854e76fa6119586b4b003812a28bda3`.

| Overridden package | Actual lock and Bender.local path |
| --- | --- |
| `apb` | `/home/wangwy/openproject/ara_dsa/hardware/deps/apb` |
| `ara` | `/home/wangwy/openproject/ara_dsa` |
| `axi` | `/home/wangwy/openproject/ara_dsa/hardware/deps/axi` |
| `common_cells` | `/home/wangwy/openproject/ara_dsa/hardware/deps/common_cells` |
| `common_verification` | `/home/wangwy/openproject/ara_dsa/hardware/deps/common_verification` |
| `cva6` | `/home/wangwy/openproject/ara_dsa/hardware/deps/cva6` |
| `fpnew` | `/home/wangwy/openproject/ara_dsa/hardware/deps/fpnew` |
| `fpu_div_sqrt_mvp` | `/home/wangwy/openproject/ara_dsa/hardware/deps/fpu_div_sqrt_mvp` |
| `tech_cells_generic` | `/home/wangwy/openproject/ara_dsa/hardware/deps/tech_cells_generic` |

3. All 14 Bender peripheral checkouts have `remote.origin.url` pointing to an old absolute local database path that currently does not exist. Existing pinned objects are readable and were verified, so this does not invalidate the file/blob matches. It is a portability and future fetch risk: do not hand off these origin strings as usable upstream locations. No remote or database was repaired.

| Package | Actual configured origin (path currently absent) |
| --- | --- |
| `apb_uart` | `/home/wangwy/openproject/ara_dsa/fpga/vcu118/.cache/cheshire_ara/.bender/git/db/apb_uart-ab8518fbd3eed755` |
| `axi_llc` | `/home/wangwy/openproject/ara_dsa/fpga/vcu118/.cache/cheshire_ara/.bender/git/db/axi_llc-add2aeee0a7800d7` |
| `axi_riscv_atomics` | `/home/wangwy/openproject/ara_dsa/fpga/vcu118/.cache/cheshire_ara/.bender/git/db/axi_riscv_atomics-3862d36749027355` |
| `axi_rt` | `/home/wangwy/openproject/ara_dsa/fpga/vcu118/.cache/cheshire_ara/.bender/git/db/axi_rt-ff3fd19237251a75` |
| `axi_vga` | `/home/wangwy/openproject/ara_dsa/fpga/vcu118/.cache/cheshire_ara/.bender/git/db/axi_vga-2fb152bf92b50a06` |
| `clic` | `/home/wangwy/openproject/ara_dsa/fpga/vcu118/.cache/cheshire_ara/.bender/git/db/clic-6fc7a4283ec855b0` |
| `clint` | `/home/wangwy/openproject/ara_dsa/fpga/vcu118/.cache/cheshire_ara/.bender/git/db/clint-902eb855f0cbcc1e` |
| `idma` | `/home/wangwy/openproject/ara_dsa/fpga/vcu118/.cache/cheshire_ara/.bender/git/db/idma-a664d81973407c92` |
| `irq_router` | `/home/wangwy/openproject/ara_dsa/fpga/vcu118/.cache/cheshire_ara/.bender/git/db/irq_router-ce0e9c2cbbcfb646` |
| `opentitan_peripherals` | `/home/wangwy/openproject/ara_dsa/fpga/vcu118/.cache/cheshire_ara/.bender/git/db/opentitan_peripherals-c1ba51498c96de97` |
| `register_interface` | `/home/wangwy/openproject/ara_dsa/fpga/vcu118/.cache/cheshire_ara/.bender/git/db/register_interface-e986c31a854fb554` |
| `riscv-dbg` | `/home/wangwy/openproject/ara_dsa/fpga/vcu118/.cache/cheshire_ara/.bender/git/db/riscv-dbg-cd6c0f590eb678e5` |
| `serial_link` | `/home/wangwy/openproject/ara_dsa/fpga/vcu118/.cache/cheshire_ara/.bender/git/db/serial_link-011faf3bc9d35d5d` |
| `unbent` | `/home/wangwy/openproject/ara_dsa/fpga/vcu118/.cache/cheshire_ara/.bender/git/db/unbent-6cf8a90aa756c6e3` |

4. The two board source hashes are absent from `source_hashes_before_integration` because the inspected board copy loop does not append `source_records`. Their source bytes, pinned blobs, board commit and actual export have now been checked independently. This supplements their origins but does not retroactively add a historical declaration to the manifest.
5. Dirty declarations outside the 226-file scope remain declarations only. The manifest reports Ara, CVA6, FPnew and MVP changes. Except for the two adapter files explicitly checked above, this investigation does not certify those packages' current contents or local patch completeness. These risks cannot be cleared by the 226-file result.

| Out-of-scope package | Number of manifest-declared tracked changes | Verification in this report |
| --- | ---: | --- |
| `ara` | 28 | declaration only; only the two adapter files checked separately |
| `cva6` | 4 | declaration only |
| `fpnew` | 3 | declaration only |
| `fpu_div_sqrt_mvp` | 5 | declaration only |

6. Origins are now located on this machine, not physically delivered into the verification worktree. All original missing paths remain missing there. A later authorized handoff still needs to preserve/materialize the exact pins and required local resolver metadata, explicitly review adaptations, and resolve the other 17 source discrepancies. No checker override or exemption is proposed or used here.

## Input fingerprints

The manifest timestamp is a declaration (`2026-09-09T06:20:43.843298+00:00`), not this verification's timestamp. These SHA256 values were measured from actual bytes; they identify which evidence was inspected.

| Actual input path | Measured SHA256 |
| --- | --- |
| `/home/wangwy/openproject/ara_dsa_verification/verification/out/fpga-rtl-handoff-20260922/source-audit.json` | `c26d7ebeda8bb7f33e8ae2a2f14744ee71bc069020bb52a8cb92e5cf1a95189b` |
| `/home/wangwy/openproject/ara_dsa/hardware/fpga/vcu118/.cache/roots.json` | `1561eef4489444e434ef4a1d82df5209adf488686aa58349c0e4af2f8f53558d` |
| `/home/wangwy/openproject/ara_dsa_verification/hardware/fpga/ara_dsa_vcu118/manifest.json` | `0157af3a60db3eb82ea56d234b252715285e27faa2c133b6eccd15d796262eae` |
| `/home/wangwy/openproject/ara_dsa_verification/hardware/fpga/ara_dsa_vcu118/SHA256SUMS` | `f3423352c61efa2764ebbcdef8ba6beb001d1bed6e3d328b2af091cf616cb4bf` |
| `/home/wangwy/openproject/ara_dsa_verification/verification/fpga/check_sources.py` | `89220c1d83adfc4491f29ed4b215bc35c53d4af0b255f90acaadafae5cf0473b` |
| `/home/wangwy/openproject/ara_dsa/hardware/fpga/vcu118/prepare.py` | `a9b8410b8a85fd27eec15571ac35ec2e3233c7eb7745f0c8fc29e15f6bf0e933` |

## Per-file evidence

These tables enumerate exactly the original 226 records, once each. `Actual source SHA256 (=blob)` is measured independently from disk and Git, with full byte equality checked. `Declared SHA256` is copied from the manifest only after checking it against those measurements; `ABSENT` is not a verified declaration. `Export SHA256` is independently measured from the existing export. `direct` means source=blob=export bytes; `adapted:<function>` means both source and blob replay exactly to export bytes. `Compiled` repeats the audit's designation and is not a build result.

Export root: `/home/wangwy/openproject/ara_dsa_verification/hardware/fpga/ara_dsa_vcu118`.

For every row, the full actual source path is the package's exact checkout root below plus `Source relative path`. The full export path is the export root plus `Export path`. No symbolic-link redirection was observed: every measured resolved source path equals its printed absolute construction.

### apb_uart

Actual checkout root: `/home/wangwy/openproject/ara_dsa/hardware/fpga/vcu118/.cache/cheshire_ara/.bender/git/checkouts/apb_uart-38dcfab592cbc1a1`
Pinned commit: `6c7dde3d749ac8274377745c105da8c8b8cd27c6`

| Source relative path | Export path | Declared SHA256 | Actual source SHA256 (=blob) | Verified Git blob OID | Actual export SHA256 | Result | Compiled |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `src/apb_uart.sv` | `rtl/apb_uart/src/apb_uart.sv` | `95a020ecfd87d028db2f9aa0c958bc3bd300e8a45a4f3446d20a3ee9cddf51cc` | `95a020ecfd87d028db2f9aa0c958bc3bd300e8a45a4f3446d20a3ee9cddf51cc` | `6e7d2b95c6965bd15fa52e08c2a3bbb76093ae39` | `95a020ecfd87d028db2f9aa0c958bc3bd300e8a45a4f3446d20a3ee9cddf51cc` | direct | yes |
| `src/apb_uart_wrap.sv` | `rtl/apb_uart/src/apb_uart_wrap.sv` | `efe5708ff6b2f5a0aed56239818ee792114392f2d304232d2ed6cee585350c41` | `efe5708ff6b2f5a0aed56239818ee792114392f2d304232d2ed6cee585350c41` | `2076d59a8acf8c5cb678b0c06c0a78cd8ed1718e` | `efe5708ff6b2f5a0aed56239818ee792114392f2d304232d2ed6cee585350c41` | direct | yes |
| `src/reg_uart_wrap.sv` | `rtl/apb_uart/src/reg_uart_wrap.sv` | `49e4f5c48e76c23242fe0714089446b8f5334b91c468c8f49f8eda9992f18c2e` | `49e4f5c48e76c23242fe0714089446b8f5334b91c468c8f49f8eda9992f18c2e` | `8b955310cd8e0a8614b9a052809de49dcb3af92e` | `49e4f5c48e76c23242fe0714089446b8f5334b91c468c8f49f8eda9992f18c2e` | direct | yes |
| `src/slib_clock_div.sv` | `rtl/apb_uart/src/slib_clock_div.sv` | `f17383c52bc93953c253cc14f5a5846af81a0fbdf62aaf778303828e6fbcbfcf` | `f17383c52bc93953c253cc14f5a5846af81a0fbdf62aaf778303828e6fbcbfcf` | `c5222429f3cd54aa3e2b2f4fdf325aec5ffd2620` | `f17383c52bc93953c253cc14f5a5846af81a0fbdf62aaf778303828e6fbcbfcf` | direct | yes |
| `src/slib_counter.sv` | `rtl/apb_uart/src/slib_counter.sv` | `b34d5171b24c00740042618901ff30c5b67a5dbbab926e81c10370f49926196a` | `b34d5171b24c00740042618901ff30c5b67a5dbbab926e81c10370f49926196a` | `59cdd5a607b5abb7818746e7ed5149072bfd1991` | `b34d5171b24c00740042618901ff30c5b67a5dbbab926e81c10370f49926196a` | direct | yes |
| `src/slib_edge_detect.sv` | `rtl/apb_uart/src/slib_edge_detect.sv` | `375472cefc07ec46559952f5952a81577856281a143486f1ee4cd923dd70f1bb` | `375472cefc07ec46559952f5952a81577856281a143486f1ee4cd923dd70f1bb` | `768b2a0e7c218d5903c17da890d323d4a5c1e6e2` | `375472cefc07ec46559952f5952a81577856281a143486f1ee4cd923dd70f1bb` | direct | yes |
| `src/slib_fifo.sv` | `rtl/apb_uart/src/slib_fifo.sv` | `0772cd7d4dd2f2681f74b909ca27e9314407ac3479c0c05871e2a051980d1b59` | `0772cd7d4dd2f2681f74b909ca27e9314407ac3479c0c05871e2a051980d1b59` | `255b7a93d7d3cde82f19baf3c2bddee12c2c6959` | `0772cd7d4dd2f2681f74b909ca27e9314407ac3479c0c05871e2a051980d1b59` | direct | yes |
| `src/slib_input_filter.sv` | `rtl/apb_uart/src/slib_input_filter.sv` | `d3ee29af3f976b889f0c1c2f8065880e8418cad15d6237a4e04a69376c611954` | `d3ee29af3f976b889f0c1c2f8065880e8418cad15d6237a4e04a69376c611954` | `3ddab477bdcc0da520dda6cc417341d72aea8186` | `d3ee29af3f976b889f0c1c2f8065880e8418cad15d6237a4e04a69376c611954` | direct | yes |
| `src/slib_input_sync.sv` | `rtl/apb_uart/src/slib_input_sync.sv` | `107b3fca99c4b9cbf670e6ee143f1f3f06996b65b7a6ba336c59087be8dca9ea` | `107b3fca99c4b9cbf670e6ee143f1f3f06996b65b7a6ba336c59087be8dca9ea` | `e2eb76f04ab935307da48a6131156623e20f8a47` | `107b3fca99c4b9cbf670e6ee143f1f3f06996b65b7a6ba336c59087be8dca9ea` | direct | yes |
| `src/slib_mv_filter.sv` | `rtl/apb_uart/src/slib_mv_filter.sv` | `9c13d01ac0cbe95d908910dad096dd8db354bf43e2ee45757f0491d1d44827b3` | `9c13d01ac0cbe95d908910dad096dd8db354bf43e2ee45757f0491d1d44827b3` | `d5b50a9e47ebfa2da161ecec03760198f7dc904e` | `9c13d01ac0cbe95d908910dad096dd8db354bf43e2ee45757f0491d1d44827b3` | direct | yes |
| `src/uart_baudgen.sv` | `rtl/apb_uart/src/uart_baudgen.sv` | `4619ad56bf2e4aa8f458bf0231523c9505ac3a956842fda6c3f3a5c4c9ff7d82` | `4619ad56bf2e4aa8f458bf0231523c9505ac3a956842fda6c3f3a5c4c9ff7d82` | `47904accfea31398345296fc69a227e3c9cd3ca9` | `4619ad56bf2e4aa8f458bf0231523c9505ac3a956842fda6c3f3a5c4c9ff7d82` | direct | yes |
| `src/uart_interrupt.sv` | `rtl/apb_uart/src/uart_interrupt.sv` | `46970823797dc973770154497d975fd2915dbe6c05bb4cb6aaf57cdd398fd41e` | `46970823797dc973770154497d975fd2915dbe6c05bb4cb6aaf57cdd398fd41e` | `98b33247b4988b917ad7e6bd16373770190ac125` | `46970823797dc973770154497d975fd2915dbe6c05bb4cb6aaf57cdd398fd41e` | direct | yes |
| `src/uart_receiver.sv` | `rtl/apb_uart/src/uart_receiver.sv` | `978a7fa8b91e8bcb8b29b3886cadc8a19ede1d1510781b7801d26bf6c881c3a4` | `978a7fa8b91e8bcb8b29b3886cadc8a19ede1d1510781b7801d26bf6c881c3a4` | `0cf79596158b7d2cad021504d02cd578bcc692dc` | `978a7fa8b91e8bcb8b29b3886cadc8a19ede1d1510781b7801d26bf6c881c3a4` | direct | yes |
| `src/uart_transmitter.sv` | `rtl/apb_uart/src/uart_transmitter.sv` | `269f165140d84aa635312b53763e50c706d4ac3c476c1cc69d15babeaf1c721d` | `269f165140d84aa635312b53763e50c706d4ac3c476c1cc69d15babeaf1c721d` | `8d57a6b7e78da992742328b6923cce9d45579c13` | `269f165140d84aa635312b53763e50c706d4ac3c476c1cc69d15babeaf1c721d` | direct | yes |

### axi_llc

Actual checkout root: `/home/wangwy/openproject/ara_dsa/hardware/fpga/vcu118/.cache/cheshire_ara/.bender/git/checkouts/axi_llc-5fb8850caad4fcfa`
Pinned commit: `559bcbd09a5a884dbe31e2d72fd95d024e357f39`

| Source relative path | Export path | Declared SHA256 | Actual source SHA256 (=blob) | Verified Git blob OID | Actual export SHA256 | Result | Compiled |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `include/axi_llc/assign.svh` | `rtl/axi_llc/include/axi_llc/assign.svh` | `887be2f98473c5960bf95c500d87c2d520b58613b1dd547137d5732c6020afc3` | `887be2f98473c5960bf95c500d87c2d520b58613b1dd547137d5732c6020afc3` | `de20ed6405fb03a55d57b6b5cfc0ee6f9a697680` | `887be2f98473c5960bf95c500d87c2d520b58613b1dd547137d5732c6020afc3` | direct | no |
| `include/axi_llc/typedef.svh` | `rtl/axi_llc/include/axi_llc/typedef.svh` | `782b7a639672beaa6d1de6df859e3b4972f785e829f1bfb994b4135d343962f8` | `782b7a639672beaa6d1de6df859e3b4972f785e829f1bfb994b4135d343962f8` | `2200d48dd1a7f8ac2d3d249523868ecc5f0a59ce` | `782b7a639672beaa6d1de6df859e3b4972f785e829f1bfb994b4135d343962f8` | direct | no |
| `src/axi_llc_burst_cutter.sv` | `rtl/axi_llc/src/axi_llc_burst_cutter.sv` | `34f2652a0031e008e94844de2abfdfd32eb5515e6865efd65affee4bbed1833f` | `34f2652a0031e008e94844de2abfdfd32eb5515e6865efd65affee4bbed1833f` | `b89d152c89d4b67bd7e3555ea58e98fdbde1ccec` | `34f2652a0031e008e94844de2abfdfd32eb5515e6865efd65affee4bbed1833f` | direct | yes |
| `src/axi_llc_chan_splitter.sv` | `rtl/axi_llc/src/axi_llc_chan_splitter.sv` | `968fba08b9f3daeafe455bf4fcddf9318e95c14605083198b5a25471eb45cc89` | `968fba08b9f3daeafe455bf4fcddf9318e95c14605083198b5a25471eb45cc89` | `c1bde5bba968d533de934a4b0d2426082cd5c491` | `968fba08b9f3daeafe455bf4fcddf9318e95c14605083198b5a25471eb45cc89` | direct | yes |
| `src/axi_llc_config.sv` | `rtl/axi_llc/src/axi_llc_config.sv` | `60691d56d923e0784a2094a80ea6e423cfc88ac0b4e9daf33db435eb61435138` | `60691d56d923e0784a2094a80ea6e423cfc88ac0b4e9daf33db435eb61435138` | `da0421ee581d03c810905377d118da0344ac618c` | `60691d56d923e0784a2094a80ea6e423cfc88ac0b4e9daf33db435eb61435138` | direct | yes |
| `src/axi_llc_data_way.sv` | `rtl/axi_llc/src/axi_llc_data_way.sv` | `ec86ec51325498389b108d41479da38044afd500f58bf63cce8c5afe2a3590e3` | `ec86ec51325498389b108d41479da38044afd500f58bf63cce8c5afe2a3590e3` | `a0fd18297ddb4cee61866203f587189a27aff7a0` | `ec86ec51325498389b108d41479da38044afd500f58bf63cce8c5afe2a3590e3` | direct | yes |
| `src/axi_llc_evict_unit.sv` | `rtl/axi_llc/src/axi_llc_evict_unit.sv` | `1e990bd3fc305896b78125843a727f3fe54cbd1a4d0dba45810a11eed979d519` | `1e990bd3fc305896b78125843a727f3fe54cbd1a4d0dba45810a11eed979d519` | `b2c1e7d85d7be1cc478efc893b124e506e9121cb` | `1e990bd3fc305896b78125843a727f3fe54cbd1a4d0dba45810a11eed979d519` | direct | yes |
| `src/axi_llc_hit_miss.sv` | `rtl/axi_llc/src/axi_llc_hit_miss.sv` | `cf7d95aca77faa5a90dcd4b3fe34bc8d20f08914e0c9dbf67191c387f0607077` | `cf7d95aca77faa5a90dcd4b3fe34bc8d20f08914e0c9dbf67191c387f0607077` | `7ae2424c703d5b9c9088747ccd70e837fa20c2c9` | `cf7d95aca77faa5a90dcd4b3fe34bc8d20f08914e0c9dbf67191c387f0607077` | direct | yes |
| `src/axi_llc_merge_unit.sv` | `rtl/axi_llc/src/axi_llc_merge_unit.sv` | `29749bfc23302264f425bb51de1d8328d56e8be817de10420026cbf821db52b7` | `29749bfc23302264f425bb51de1d8328d56e8be817de10420026cbf821db52b7` | `231d215c71fdf7df625a648579f67652f287ab7d` | `29749bfc23302264f425bb51de1d8328d56e8be817de10420026cbf821db52b7` | direct | yes |
| `src/axi_llc_pkg.sv` | `rtl/axi_llc/src/axi_llc_pkg.sv` | `4f23669394df059929916272f3dd3d09af30fd4211ea87cbda4d99eb17a0a5eb` | `4f23669394df059929916272f3dd3d09af30fd4211ea87cbda4d99eb17a0a5eb` | `7e5c0964f6ef6c7c1c9089d76dad93cbc962abf8` | `4f23669394df059929916272f3dd3d09af30fd4211ea87cbda4d99eb17a0a5eb` | direct | yes |
| `src/axi_llc_read_unit.sv` | `rtl/axi_llc/src/axi_llc_read_unit.sv` | `00443f72109a59423ea9189c2fde95151c78edf733111d6e6b0944741aa05473` | `00443f72109a59423ea9189c2fde95151c78edf733111d6e6b0944741aa05473` | `c5c7bce9d0ff45b3b811cb8d4a5ef06933290564` | `00443f72109a59423ea9189c2fde95151c78edf733111d6e6b0944741aa05473` | direct | yes |
| `src/axi_llc_refill_unit.sv` | `rtl/axi_llc/src/axi_llc_refill_unit.sv` | `3b4ce5be3ad45aae7c74e383a9d8543327092c16ad4b16fe579639f3b10bf13e` | `3b4ce5be3ad45aae7c74e383a9d8543327092c16ad4b16fe579639f3b10bf13e` | `16b6bcccce3b1a829a0c2e2b4f196f05698a2f95` | `3b4ce5be3ad45aae7c74e383a9d8543327092c16ad4b16fe579639f3b10bf13e` | direct | yes |
| `src/axi_llc_reg_pkg.sv` | `rtl/axi_llc/src/axi_llc_reg_pkg.sv` | `0b129f58e898e5c864e2f52e4ebc6451a0d23bb1cc94b98346fa56d4617eee72` | `0b129f58e898e5c864e2f52e4ebc6451a0d23bb1cc94b98346fa56d4617eee72` | `49b8d75bf3ac5e1a44f213c2c53ba8125c76cafd` | `0b129f58e898e5c864e2f52e4ebc6451a0d23bb1cc94b98346fa56d4617eee72` | direct | yes |
| `src/axi_llc_reg_top.sv` | `rtl/axi_llc/src/axi_llc_reg_top.sv` | `0e58a7552411f5f368e7f84a958fbea17915577ed70f3e055a570e25f43536c1` | `0e58a7552411f5f368e7f84a958fbea17915577ed70f3e055a570e25f43536c1` | `e320217523b0ff64d2185d4269df779de94d9691` | `0e58a7552411f5f368e7f84a958fbea17915577ed70f3e055a570e25f43536c1` | direct | yes |
| `src/axi_llc_reg_wrap.sv` | `rtl/axi_llc/src/axi_llc_reg_wrap.sv` | `df67486ef5b91940f301ab340d53337f53b2b93317b06874ad287f44b88c4e10` | `df67486ef5b91940f301ab340d53337f53b2b93317b06874ad287f44b88c4e10` | `f5de663fc86dc18a47f8f85d655b601c9e41457f` | `df67486ef5b91940f301ab340d53337f53b2b93317b06874ad287f44b88c4e10` | direct | yes |
| `src/axi_llc_top.sv` | `rtl/axi_llc/src/axi_llc_top.sv` | `40ad5d3c0ec3817662815514d28f1a9190ae1b24af4976c6359502f0a851bd1c` | `40ad5d3c0ec3817662815514d28f1a9190ae1b24af4976c6359502f0a851bd1c` | `443b5ed4778f3388198340776a85b381d75d66f9` | `40ad5d3c0ec3817662815514d28f1a9190ae1b24af4976c6359502f0a851bd1c` | direct | yes |
| `src/axi_llc_ways.sv` | `rtl/axi_llc/src/axi_llc_ways.sv` | `b84f2bdf8b5712d17d26aecb9b0e758cdfc6095e87e61fb72950b206208dd9ae` | `b84f2bdf8b5712d17d26aecb9b0e758cdfc6095e87e61fb72950b206208dd9ae` | `c217401cdde9d2c66b94593144d61877c3b57f14` | `b84f2bdf8b5712d17d26aecb9b0e758cdfc6095e87e61fb72950b206208dd9ae` | direct | yes |
| `src/axi_llc_write_unit.sv` | `rtl/axi_llc/src/axi_llc_write_unit.sv` | `2a264b35ba5f567f15d40f63af29fed4a140e73d27971990328de4610ad35778` | `2a264b35ba5f567f15d40f63af29fed4a140e73d27971990328de4610ad35778` | `2640e94443cdb54ac8ca6af3605a7176ef247944` | `2a264b35ba5f567f15d40f63af29fed4a140e73d27971990328de4610ad35778` | direct | yes |
| `src/eviction_refill/axi_llc_ax_master.sv` | `rtl/axi_llc/src/eviction_refill/axi_llc_ax_master.sv` | `ca70badc3d628fd70d1aae6f683f3b28376ab7a3c1cd6916fe8afa3fe23e23ca` | `ca70badc3d628fd70d1aae6f683f3b28376ab7a3c1cd6916fe8afa3fe23e23ca` | `5c4ffac004b7a5a39fab5a37e6484d2279b23407` | `ca70badc3d628fd70d1aae6f683f3b28376ab7a3c1cd6916fe8afa3fe23e23ca` | direct | yes |
| `src/eviction_refill/axi_llc_r_master.sv` | `rtl/axi_llc/src/eviction_refill/axi_llc_r_master.sv` | `2bad2b1a9cf5c6a2bcb17750d95ac76403ed3e3e2e911aa21e3577ffa56b1c44` | `2bad2b1a9cf5c6a2bcb17750d95ac76403ed3e3e2e911aa21e3577ffa56b1c44` | `d46633c50a1ad60f34e36220870bcd5735cfd5d1` | `2bad2b1a9cf5c6a2bcb17750d95ac76403ed3e3e2e911aa21e3577ffa56b1c44` | direct | yes |
| `src/eviction_refill/axi_llc_w_master.sv` | `rtl/axi_llc/src/eviction_refill/axi_llc_w_master.sv` | `49ef7db50216d1d91901ca4d1992503d8fdafb888202d8568c3d5b9eabc0a3d1` | `49ef7db50216d1d91901ca4d1992503d8fdafb888202d8568c3d5b9eabc0a3d1` | `2dce5f7f80c029f29b82f75292a0a10286329255` | `49ef7db50216d1d91901ca4d1992503d8fdafb888202d8568c3d5b9eabc0a3d1` | direct | yes |
| `src/hit_miss_detect/axi_llc_evict_box.sv` | `rtl/axi_llc/src/hit_miss_detect/axi_llc_evict_box.sv` | `18f66f1186ab326247de0318bba21688d47176354adb98c484ad0291840619e8` | `18f66f1186ab326247de0318bba21688d47176354adb98c484ad0291840619e8` | `bfe2eaaa6fad6a759a13319580da3511c15ca6c0` | `18f66f1186ab326247de0318bba21688d47176354adb98c484ad0291840619e8` | direct | yes |
| `src/hit_miss_detect/axi_llc_lock_box_bloom.sv` | `rtl/axi_llc/src/hit_miss_detect/axi_llc_lock_box_bloom.sv` | `2655812e119b2a48bd646d689fcfcb861038b4f2936cdadb4a9a4f9a932cb258` | `2655812e119b2a48bd646d689fcfcb861038b4f2936cdadb4a9a4f9a932cb258` | `130be54d479752ea16fde0a60294ce640b88a0cb` | `2655812e119b2a48bd646d689fcfcb861038b4f2936cdadb4a9a4f9a932cb258` | direct | yes |
| `src/hit_miss_detect/axi_llc_miss_counters.sv` | `rtl/axi_llc/src/hit_miss_detect/axi_llc_miss_counters.sv` | `ad09bddaa4884c59aab07eab82d6b5dbfbd8ea8127a9197fa0dde1bed44837a1` | `ad09bddaa4884c59aab07eab82d6b5dbfbd8ea8127a9197fa0dde1bed44837a1` | `262c683d5761bd8adc361d69e3b8100660033eee` | `ad09bddaa4884c59aab07eab82d6b5dbfbd8ea8127a9197fa0dde1bed44837a1` | direct | yes |
| `src/hit_miss_detect/axi_llc_tag_pattern_gen.sv` | `rtl/axi_llc/src/hit_miss_detect/axi_llc_tag_pattern_gen.sv` | `c611fe03ff6c0f8576b421e8e6c8c750bbdb7c5a817f5384dfabfe34d975ec43` | `c611fe03ff6c0f8576b421e8e6c8c750bbdb7c5a817f5384dfabfe34d975ec43` | `2d9b2f8fb45612b03e694c38c22e509676de719d` | `c611fe03ff6c0f8576b421e8e6c8c750bbdb7c5a817f5384dfabfe34d975ec43` | direct | yes |
| `src/hit_miss_detect/axi_llc_tag_store.sv` | `rtl/axi_llc/src/hit_miss_detect/axi_llc_tag_store.sv` | `4781fee27b31bd4b12a64fc4323bdf864ec625ac820a1da434b5e4388149d588` | `4781fee27b31bd4b12a64fc4323bdf864ec625ac820a1da434b5e4388149d588` | `d15691aa3f38efd511a6bb75159a7fc064512a59` | `4781fee27b31bd4b12a64fc4323bdf864ec625ac820a1da434b5e4388149d588` | direct | yes |

### axi_riscv_atomics

Actual checkout root: `/home/wangwy/openproject/ara_dsa/hardware/fpga/vcu118/.cache/cheshire_ara/.bender/git/checkouts/axi_riscv_atomics-40ad8d2d0e0daa8b`
Pinned commit: `0ac3a78fe342c5a5b9b10bff49d58897f773059e`

| Source relative path | Export path | Declared SHA256 | Actual source SHA256 (=blob) | Verified Git blob OID | Actual export SHA256 | Result | Compiled |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `src/axi_res_tbl.sv` | `rtl/axi_riscv_atomics/src/axi_res_tbl.sv` | `5c2b2d81f57ecac5f732a07e740a5d27916a1e371eb32ec5f705d95e5280907c` | `5c2b2d81f57ecac5f732a07e740a5d27916a1e371eb32ec5f705d95e5280907c` | `657e6f5dd60fc2d939e3cbb6677e62470255dc27` | `5c2b2d81f57ecac5f732a07e740a5d27916a1e371eb32ec5f705d95e5280907c` | direct | yes |
| `src/axi_riscv_amos.sv` | `rtl/axi_riscv_atomics/src/axi_riscv_amos.sv` | `cd8515daf716fe61fdd600e001c19e9bfba6639d68945d08e976ada46969e99e` | `cd8515daf716fe61fdd600e001c19e9bfba6639d68945d08e976ada46969e99e` | `0996e8214a7d177a22d685a50d4256e8329d9809` | `cd8515daf716fe61fdd600e001c19e9bfba6639d68945d08e976ada46969e99e` | direct | yes |
| `src/axi_riscv_amos_alu.sv` | `rtl/axi_riscv_atomics/src/axi_riscv_amos_alu.sv` | `7913f1ec1a2d21b38c90a9f93e12214b5a63536bd7cf2fee70fcfa6c2eafaa29` | `7913f1ec1a2d21b38c90a9f93e12214b5a63536bd7cf2fee70fcfa6c2eafaa29` | `40a52b0ec66d1947c63099b0f15a968b3c1b4be5` | `7913f1ec1a2d21b38c90a9f93e12214b5a63536bd7cf2fee70fcfa6c2eafaa29` | direct | yes |
| `src/axi_riscv_amos_wrap.sv` | `rtl/axi_riscv_atomics/src/axi_riscv_amos_wrap.sv` | `f28a06eac7a4fae17a95977f9ff8262792b9c7687e0dbe22a1c2615d1356c56d` | `f28a06eac7a4fae17a95977f9ff8262792b9c7687e0dbe22a1c2615d1356c56d` | `a76acc9c2ad682887b274a2b3b524c7ae3a26001` | `f28a06eac7a4fae17a95977f9ff8262792b9c7687e0dbe22a1c2615d1356c56d` | direct | yes |
| `src/axi_riscv_atomics.sv` | `rtl/axi_riscv_atomics/src/axi_riscv_atomics.sv` | `6581b4ee92f33261114f534ecd0ef0df9801485a18a51b51ed5acc52eb1b302a` | `6581b4ee92f33261114f534ecd0ef0df9801485a18a51b51ed5acc52eb1b302a` | `12ad0fb63075786892e629dca8046bc498075990` | `6581b4ee92f33261114f534ecd0ef0df9801485a18a51b51ed5acc52eb1b302a` | direct | yes |
| `src/axi_riscv_atomics_structs.sv` | `rtl/axi_riscv_atomics/src/axi_riscv_atomics_structs.sv` | `69d91d4ae30026975f9aa9c0b93700953c776ddb7f00461c83e3e9c43b50eced` | `69d91d4ae30026975f9aa9c0b93700953c776ddb7f00461c83e3e9c43b50eced` | `24afec4f4bfe03ee6c56f8ce2d886deca5ec2fad` | `69d91d4ae30026975f9aa9c0b93700953c776ddb7f00461c83e3e9c43b50eced` | direct | yes |
| `src/axi_riscv_atomics_wrap.sv` | `rtl/axi_riscv_atomics/src/axi_riscv_atomics_wrap.sv` | `0b6d830f31ef90f9be4b4fbb6feb14076bed3ca893a05c8de6bf6385fd299737` | `0b6d830f31ef90f9be4b4fbb6feb14076bed3ca893a05c8de6bf6385fd299737` | `f63af612bc1cb9363ab3b59e542cdcb5e1175ae6` | `0b6d830f31ef90f9be4b4fbb6feb14076bed3ca893a05c8de6bf6385fd299737` | direct | yes |
| `src/axi_riscv_lrsc.sv` | `rtl/axi_riscv_atomics/src/axi_riscv_lrsc.sv` | `7a596399dd5568248ef7b61434d2b87ee1bc1f0dce2dea0eee25b978ea8bf9a4` | `7a596399dd5568248ef7b61434d2b87ee1bc1f0dce2dea0eee25b978ea8bf9a4` | `eb75593bf5b0218fa6d55c4c0dbdcf9b202667f9` | `7a596399dd5568248ef7b61434d2b87ee1bc1f0dce2dea0eee25b978ea8bf9a4` | direct | yes |
| `src/axi_riscv_lrsc_wrap.sv` | `rtl/axi_riscv_atomics/src/axi_riscv_lrsc_wrap.sv` | `0a20fc917e4e3977fd1efe2d5f40e420d7d92b1734c1d82cfa06586d84581fea` | `0a20fc917e4e3977fd1efe2d5f40e420d7d92b1734c1d82cfa06586d84581fea` | `bf2e5c1bf4595251f336f30da1263bf4c881957b` | `0a20fc917e4e3977fd1efe2d5f40e420d7d92b1734c1d82cfa06586d84581fea` | direct | yes |

### axi_rt

Actual checkout root: `/home/wangwy/openproject/ara_dsa/hardware/fpga/vcu118/.cache/cheshire_ara/.bender/git/checkouts/axi_rt-7cef46f372eaf0fb`
Pinned commit: `56074a195b1c8b05f4bdd73674e437bbcb35f2cd`

| Source relative path | Export path | Declared SHA256 | Actual source SHA256 (=blob) | Verified Git blob OID | Actual export SHA256 | Result | Compiled |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `include/axi-rt/assign.svh` | `rtl/axi_rt/include/axi-rt/assign.svh` | `d8d3afab16cf6cb27b4dabbf345c515ab78123b84f3e314949ef3af76742943c` | `d8d3afab16cf6cb27b4dabbf345c515ab78123b84f3e314949ef3af76742943c` | `87cb0ff3c134815784caa5499066eb063bfcd371` | `d8d3afab16cf6cb27b4dabbf345c515ab78123b84f3e314949ef3af76742943c` | direct | no |
| `include/axi-rt/port.svh` | `rtl/axi_rt/include/axi-rt/port.svh` | `2f79e7127d5cfe87a5301416877896af13c4868c56fcbb1978e935d704b344bf` | `2f79e7127d5cfe87a5301416877896af13c4868c56fcbb1978e935d704b344bf` | `74510a8814a6d2bfb71c30d424ff0bff8ea18bd8` | `2f79e7127d5cfe87a5301416877896af13c4868c56fcbb1978e935d704b344bf` | direct | no |
| `src/axi_gran_burst_splitter.sv` | `rtl/axi_rt/src/axi_gran_burst_splitter.sv` | `9a8544a8a4082dafba10757ae0774f12f5658954af216c5a932ba5c7e0fe9379` | `9a8544a8a4082dafba10757ae0774f12f5658954af216c5a932ba5c7e0fe9379` | `b0944766ca962517e710781bc1c2011b2526b3b5` | `9a8544a8a4082dafba10757ae0774f12f5658954af216c5a932ba5c7e0fe9379` | direct | yes |
| `src/axi_gran_burst_splitter_ax_chan.sv` | `rtl/axi_rt/src/axi_gran_burst_splitter_ax_chan.sv` | `23b12f87469cd1bd7493b542625ba4975e5814f231d7b6071419d925403d9f38` | `23b12f87469cd1bd7493b542625ba4975e5814f231d7b6071419d925403d9f38` | `b11a3266082d324998fee5edfffac79af1d69802` | `23b12f87469cd1bd7493b542625ba4975e5814f231d7b6071419d925403d9f38` | direct | yes |
| `src/axi_gran_burst_splitter_counters.sv` | `rtl/axi_rt/src/axi_gran_burst_splitter_counters.sv` | `6e97b07f5a4d3bf8d03d7c911bdec5e8306656e1d27ca692fc179d7bd9a5f28c` | `6e97b07f5a4d3bf8d03d7c911bdec5e8306656e1d27ca692fc179d7bd9a5f28c` | `82ed66d053d8bafdba2bb116e889376bf2d02e45` | `6e97b07f5a4d3bf8d03d7c911bdec5e8306656e1d27ca692fc179d7bd9a5f28c` | direct | yes |
| `src/axi_rt_err_slv.sv` | `rtl/axi_rt/src/axi_rt_err_slv.sv` | `2d376b1cc22e5d6c78d5166af8dba068733f1c151e33aaddf071dc328fb01c57` | `2d376b1cc22e5d6c78d5166af8dba068733f1c151e33aaddf071dc328fb01c57` | `ed4a4cbe46f8c39369023610121ceb1137e7bcf3` | `2d376b1cc22e5d6c78d5166af8dba068733f1c151e33aaddf071dc328fb01c57` | direct | yes |
| `src/axi_rt_regbus_guard.sv` | `rtl/axi_rt/src/axi_rt_regbus_guard.sv` | `950010df43fe231997a75bcf03e28a466e7fb2f0887c1657c913e164bb53cfee` | `950010df43fe231997a75bcf03e28a466e7fb2f0887c1657c913e164bb53cfee` | `148c727a8523ceabbec96352e00f04c7959e0d43` | `950010df43fe231997a75bcf03e28a466e7fb2f0887c1657c913e164bb53cfee` | direct | yes |
| `src/axi_rt_unit.sv` | `rtl/axi_rt/src/axi_rt_unit.sv` | `2c0b90ee67aa3f1cab09253f7f33ecbb13bbc39812ae916ff02f43259e50eed3` | `2c0b90ee67aa3f1cab09253f7f33ecbb13bbc39812ae916ff02f43259e50eed3` | `49c8420e96ec768c16b5cacaa6f721fcd9a42f63` | `2c0b90ee67aa3f1cab09253f7f33ecbb13bbc39812ae916ff02f43259e50eed3` | direct | yes |
| `src/axi_rt_unit_counter.sv` | `rtl/axi_rt/src/axi_rt_unit_counter.sv` | `37eb94dde4cabd3c99a42444f757fe42d292eca948ba1524f7d2cc7ec400ca67` | `37eb94dde4cabd3c99a42444f757fe42d292eca948ba1524f7d2cc7ec400ca67` | `8b0c8f75018626e127bd939ca98a90564702c9d6` | `37eb94dde4cabd3c99a42444f757fe42d292eca948ba1524f7d2cc7ec400ca67` | direct | yes |
| `src/axi_rt_unit_top.sv` | `rtl/axi_rt/src/axi_rt_unit_top.sv` | `74277848d38fd34e0f89b188e7b34e342ce23040831cc4257a077507313b1ab5` | `74277848d38fd34e0f89b188e7b34e342ce23040831cc4257a077507313b1ab5` | `9172e60b47a12ee7115fd96133576c684cc712b2` | `74277848d38fd34e0f89b188e7b34e342ce23040831cc4257a077507313b1ab5` | direct | yes |
| `src/axi_rt_unit_top_synth.sv` | `rtl/axi_rt/src/axi_rt_unit_top_synth.sv` | `66358bd21911d736ef3e7c4a6d8b1af21cd26cec93915a58f5e15f01ca9fe16d` | `66358bd21911d736ef3e7c4a6d8b1af21cd26cec93915a58f5e15f01ca9fe16d` | `de16598fb5d1b47a4d50529293bcd7ab041eb834` | `66358bd21911d736ef3e7c4a6d8b1af21cd26cec93915a58f5e15f01ca9fe16d` | direct | yes |
| `src/axi_write_buffer.sv` | `rtl/axi_rt/src/axi_write_buffer.sv` | `26bfb61ec78eb10280b3be189f6123b0c1eda2f8fdac8040aad548548e849671` | `26bfb61ec78eb10280b3be189f6123b0c1eda2f8fdac8040aad548548e849671` | `18e004b4c7aaadc990fc7828d791e95182a5407b` | `26bfb61ec78eb10280b3be189f6123b0c1eda2f8fdac8040aad548548e849671` | direct | yes |
| `src/regs/axi_rt_reg_pkg.sv` | `rtl/axi_rt/src/regs/axi_rt_reg_pkg.sv` | `1da6b3315682d08f660ec708caa77def22a275b0f1a3c58f45fbff280fa035b4` | `1da6b3315682d08f660ec708caa77def22a275b0f1a3c58f45fbff280fa035b4` | `6fcc04fdb6a926ddbfa4628f3349b11ddd143dc2` | `1da6b3315682d08f660ec708caa77def22a275b0f1a3c58f45fbff280fa035b4` | direct | yes |
| `src/regs/axi_rt_reg_top.sv` | `rtl/axi_rt/src/regs/axi_rt_reg_top.sv` | `e36525d2d53ce87d74cb6dfb5c8813c5c106875d673c6c00118b833d67ebe253` | `e36525d2d53ce87d74cb6dfb5c8813c5c106875d673c6c00118b833d67ebe253` | `73658eecab81b3ec0ff4918b3246a5d44639caf5` | `e36525d2d53ce87d74cb6dfb5c8813c5c106875d673c6c00118b833d67ebe253` | direct | yes |
| `target/xilinx/src/axi_rt_unit_top_xilinx.sv` | `rtl/axi_rt/target/xilinx/src/axi_rt_unit_top_xilinx.sv` | `92d56c1210603842dbdbcf2324b230562ecb17a32b132e4f827a6cd151779a9f` | `92d56c1210603842dbdbcf2324b230562ecb17a32b132e4f827a6cd151779a9f` | `5c1410c4964caa1c85cef156c1cca53f8b313971` | `92d56c1210603842dbdbcf2324b230562ecb17a32b132e4f827a6cd151779a9f` | direct | yes |
| `target/xilinx/src/axi_rt_unit_top_xilinx_ip.v` | `rtl/axi_rt/target/xilinx/src/axi_rt_unit_top_xilinx_ip.v` | `ff6d7c7c34e6735ac3950de36f1cd9136189cd1e44f5749939d70c5f72193011` | `ff6d7c7c34e6735ac3950de36f1cd9136189cd1e44f5749939d70c5f72193011` | `56ea8923e952687a1ea8a2bc5ba4dd84bb3a92cb` | `ff6d7c7c34e6735ac3950de36f1cd9136189cd1e44f5749939d70c5f72193011` | direct | yes |

### axi_vga

Actual checkout root: `/home/wangwy/openproject/ara_dsa/hardware/fpga/vcu118/.cache/cheshire_ara/.bender/git/checkouts/axi_vga-74c838b44ce780d5`
Pinned commit: `3718b9930f94a9eaad8ee50b4bccc71df0403084`

| Source relative path | Export path | Declared SHA256 | Actual source SHA256 (=blob) | Verified Git blob OID | Actual export SHA256 | Result | Compiled |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `src/axi_vga.sv` | `rtl/axi_vga/src/axi_vga.sv` | `880ef76a0f53af411b6e27a3542e27749ee63c6b3501a639094a1f113603032e` | `880ef76a0f53af411b6e27a3542e27749ee63c6b3501a639094a1f113603032e` | `b44cc72710ec2646df7bb2ddcf73190062eb0bd4` | `880ef76a0f53af411b6e27a3542e27749ee63c6b3501a639094a1f113603032e` | direct | yes |
| `src/axi_vga_fetcher.sv` | `rtl/axi_vga/src/axi_vga_fetcher.sv` | `1d0af37f6f66a524d68dbb179fc1068a17411abc9aa25ddeceef115acbced83f` | `1d0af37f6f66a524d68dbb179fc1068a17411abc9aa25ddeceef115acbced83f` | `f412a8dfdc9da64202085856a6596c45e931858b` | `1d0af37f6f66a524d68dbb179fc1068a17411abc9aa25ddeceef115acbced83f` | direct | yes |
| `src/axi_vga_reg_pkg.sv` | `rtl/axi_vga/src/axi_vga_reg_pkg.sv` | `b9e4747edf175a69ea93ff16a977fd4de71d3f3057400b44dd97d51988f7ccdc` | `b9e4747edf175a69ea93ff16a977fd4de71d3f3057400b44dd97d51988f7ccdc` | `eff5217a65a353fd89639a316f7bcf91a5acad70` | `b9e4747edf175a69ea93ff16a977fd4de71d3f3057400b44dd97d51988f7ccdc` | direct | yes |
| `src/axi_vga_reg_top.sv` | `rtl/axi_vga/src/axi_vga_reg_top.sv` | `a8a5ac2b637410c0bff21172b6d7cd5e80ad31e0cf540d762af6ebc0580a665a` | `a8a5ac2b637410c0bff21172b6d7cd5e80ad31e0cf540d762af6ebc0580a665a` | `0b306c97261cd9755d7a65737cad5853dd71ee97` | `a8a5ac2b637410c0bff21172b6d7cd5e80ad31e0cf540d762af6ebc0580a665a` | direct | yes |
| `src/axi_vga_timing_fsm.sv` | `rtl/axi_vga/src/axi_vga_timing_fsm.sv` | `9b1147235912603c8b3e853b5adb0fb12121587ace400a0f13a577a10a4c6689` | `9b1147235912603c8b3e853b5adb0fb12121587ace400a0f13a577a10a4c6689` | `126a48a27fe57b76bf79a2b307e75c870e0fc03e` | `9b1147235912603c8b3e853b5adb0fb12121587ace400a0f13a577a10a4c6689` | direct | yes |

### board

Actual checkout root: `/home/wangwy/openproject/ara_dsa/hardware/fpga/vcu118/.cache/cheshire_board`
Pinned commit: `a315a828abb61cf3cb9f4419b910ebe6739b90bf`

| Source relative path | Export path | Declared SHA256 | Actual source SHA256 (=blob) | Verified Git blob OID | Actual export SHA256 | Result | Compiled |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `target/xilinx/src/dram_wrapper_xilinx.sv` | `rtl/board/dram_wrapper_xilinx.sv` | ABSENT | `68b78ae54ee70a7d67e16fd471c8d6f455bc25b2778a631e87481fa03bd61981` | `1329c2f3667c2ed508ca49bb6ce8a3dd2c8efa23` | `c3eea7cfad7a93192b09aa4ae326746ce7bb8c675a9e838e8bd1b502840604a6` | adapted:patch_dram | yes |
| `target/xilinx/src/phy_definitions.svh` | `rtl/board/phy_definitions.svh` | ABSENT | `b84567c288c7525fee0bf5096c16ec0a17fbc08e292e0b02047996c62c7e3006` | `8ecf7c368b393c65ab27aca54e891163d9c8b07e` | `b84567c288c7525fee0bf5096c16ec0a17fbc08e292e0b02047996c62c7e3006` | direct | no |

### cheshire

Actual checkout root: `/home/wangwy/openproject/ara_dsa/hardware/fpga/vcu118/.cache/cheshire_ara`
Pinned commit: `cd73fd892a09da8aa9ae03171c0338bd3873007c`

| Source relative path | Export path | Declared SHA256 | Actual source SHA256 (=blob) | Verified Git blob OID | Actual export SHA256 | Result | Compiled |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `hw/bootrom/cheshire_bootrom.sv` | `rtl/cheshire/hw/bootrom/cheshire_bootrom.sv` | `9368e60cf5de3de84ecf277ef99fc5b194657c013622d555c8a8a9dc4aa31116` | `9368e60cf5de3de84ecf277ef99fc5b194657c013622d555c8a8a9dc4aa31116` | `072d4ee437268d2678df071a0b226964d2b8d954` | `9368e60cf5de3de84ecf277ef99fc5b194657c013622d555c8a8a9dc4aa31116` | direct | yes |
| `hw/cheshire_pkg.sv` | `rtl/cheshire/hw/cheshire_pkg.sv` | `ff19556a3a8eef32e72e1a6d7595407585a2544330c74070f54063cc763b505d` | `ff19556a3a8eef32e72e1a6d7595407585a2544330c74070f54063cc763b505d` | `2e3873b4d8d87c4a61aa9201c8044c92ffc5d758` | `47c422aebb106973a50b845f3fce1a51541efcb001270bd8b901033cf8a3aca8` | adapted:patch_soc_pkg | yes |
| `hw/cheshire_soc.sv` | `rtl/cheshire/hw/cheshire_soc.sv` | `afabcf5fd40b15c897ea8e36a8df17fc2e7c40a62b819a2759b1358b8f3067ad` | `afabcf5fd40b15c897ea8e36a8df17fc2e7c40a62b819a2759b1358b8f3067ad` | `586f6ddaa53ecad6ebee3c2f80e91f3b89853c06` | `d92a0b504d7da8857d7e4903fae84910c748646ef7ca1b9a122fe6edd124992a` | adapted:patch_soc | yes |
| `hw/future/UsbOhciAxi4.v` | `rtl/cheshire/hw/future/UsbOhciAxi4.v` | `f98258803336f1c285b331729a3abf1f1fc6d0424ac19947fde9dd21411fdf2f` | `f98258803336f1c285b331729a3abf1f1fc6d0424ac19947fde9dd21411fdf2f` | `5ea9e43894c1c4cb1e86655dae5c45afc533076b` | `f98258803336f1c285b331729a3abf1f1fc6d0424ac19947fde9dd21411fdf2f` | direct | yes |
| `hw/future/spinal_usb_ohci.sv` | `rtl/cheshire/hw/future/spinal_usb_ohci.sv` | `09507ee03a1e998ef5b81b058d0ff286a04677eaaa67dde957d426cb73cc1436` | `09507ee03a1e998ef5b81b058d0ff286a04677eaaa67dde957d426cb73cc1436` | `4a0d9763b9bb359b963271b9926f8b908e2f3424` | `09507ee03a1e998ef5b81b058d0ff286a04677eaaa67dde957d426cb73cc1436` | direct | yes |
| `hw/include/cheshire/typedef.svh` | `rtl/cheshire/hw/include/cheshire/typedef.svh` | `ed500e4eea0a512afcdcf12cd85ec4cf7bc10ba35f516f72fbea363dce751c76` | `ed500e4eea0a512afcdcf12cd85ec4cf7bc10ba35f516f72fbea363dce751c76` | `dde2b1bf0687b8be90e94d7fdcc1ff3e168e8e21` | `ed500e4eea0a512afcdcf12cd85ec4cf7bc10ba35f516f72fbea363dce751c76` | direct | no |
| `hw/regs/cheshire_reg_pkg.sv` | `rtl/cheshire/hw/regs/cheshire_reg_pkg.sv` | `9b6c8c0df01ed56b18f2843992d5e0dfe70363083879182568918df6deec180e` | `9b6c8c0df01ed56b18f2843992d5e0dfe70363083879182568918df6deec180e` | `e2711e3dcc0c867a3dd0b718ba3b825c9bb66871` | `9b6c8c0df01ed56b18f2843992d5e0dfe70363083879182568918df6deec180e` | direct | yes |
| `hw/regs/cheshire_reg_top.sv` | `rtl/cheshire/hw/regs/cheshire_reg_top.sv` | `8e872dabe2ac5a78eb0f7921310251bd2335a80ac465fb428dcbd834f9ddc4ea` | `8e872dabe2ac5a78eb0f7921310251bd2335a80ac465fb428dcbd834f9ddc4ea` | `9e55b807cb3f5efeda92740b12a180fb8e464308` | `8e872dabe2ac5a78eb0f7921310251bd2335a80ac465fb428dcbd834f9ddc4ea` | direct | yes |

### clic

Actual checkout root: `/home/wangwy/openproject/ara_dsa/hardware/fpga/vcu118/.cache/cheshire_ara/.bender/git/checkouts/clic-360fff7ce2d41116`
Pinned commit: `8ed76ffc779a435d0ed034f3068e4c3334fe2ecf`

| Source relative path | Export path | Declared SHA256 | Actual source SHA256 (=blob) | Verified Git blob OID | Actual export SHA256 | Result | Compiled |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `src/clic.sv` | `rtl/clic/src/clic.sv` | `613937107adcb31d6a2987149e404aa1fcc3a6b0035ca032a749a23c642f8030` | `613937107adcb31d6a2987149e404aa1fcc3a6b0035ca032a749a23c642f8030` | `044da344c32f1360caa3ada5884bbe558073ae31` | `613937107adcb31d6a2987149e404aa1fcc3a6b0035ca032a749a23c642f8030` | direct | yes |
| `src/clic_apb.sv` | `rtl/clic/src/clic_apb.sv` | `e4449edfee65f7703677bd343063b7856fbd742b7359e2c5311621c8957f3594` | `e4449edfee65f7703677bd343063b7856fbd742b7359e2c5311621c8957f3594` | `5e345c6ffe68aeab83fb2db708a40a9665ff7e9d` | `e4449edfee65f7703677bd343063b7856fbd742b7359e2c5311621c8957f3594` | direct | yes |
| `src/clic_gateway.sv` | `rtl/clic/src/clic_gateway.sv` | `b69ff086106db93574cd1dd1cb22e827d96a659f7d99c5f60c967feb8b31265d` | `b69ff086106db93574cd1dd1cb22e827d96a659f7d99c5f60c967feb8b31265d` | `af034f776e9d7bd3d41f057f91a97b9f3aeb4eed` | `b69ff086106db93574cd1dd1cb22e827d96a659f7d99c5f60c967feb8b31265d` | direct | yes |
| `src/clic_reg_adapter.sv` | `rtl/clic/src/clic_reg_adapter.sv` | `f631dea52f031e90543d71aacf897e70adb2445d02fb9240996ebe060f4844c6` | `f631dea52f031e90543d71aacf897e70adb2445d02fb9240996ebe060f4844c6` | `70008f42932e9ae891555928329512b6d9147200` | `f631dea52f031e90543d71aacf897e70adb2445d02fb9240996ebe060f4844c6` | direct | yes |
| `src/clic_target.sv` | `rtl/clic/src/clic_target.sv` | `9c9e8d328f3b0c63084a4bb6f3d65e0838f847917a61c1bf1afc884c384e795c` | `9c9e8d328f3b0c63084a4bb6f3d65e0838f847917a61c1bf1afc884c384e795c` | `e6800493c1df254f9e5aa1704f33f720d608dee7` | `9c9e8d328f3b0c63084a4bb6f3d65e0838f847917a61c1bf1afc884c384e795c` | direct | yes |
| `src/clicint_reg_pkg.sv` | `rtl/clic/src/clicint_reg_pkg.sv` | `c363bb2dbbd1a0f280ed47ddb2d0b1629bbbe87d6e2e645409424f1eca938f71` | `c363bb2dbbd1a0f280ed47ddb2d0b1629bbbe87d6e2e645409424f1eca938f71` | `b88579b4529cdc313aaddb7b319e56efae33b217` | `c363bb2dbbd1a0f280ed47ddb2d0b1629bbbe87d6e2e645409424f1eca938f71` | direct | yes |
| `src/clicint_reg_top.sv` | `rtl/clic/src/clicint_reg_top.sv` | `47a0b912885da3555a907b03c788305b478e161c248a2f6681edaa7b4bbc6cce` | `47a0b912885da3555a907b03c788305b478e161c248a2f6681edaa7b4bbc6cce` | `6552ea0c0ada54a8f1ff6526aafa1fe6d1d4f4c6` | `47a0b912885da3555a907b03c788305b478e161c248a2f6681edaa7b4bbc6cce` | direct | yes |
| `src/mclic_reg_pkg.sv` | `rtl/clic/src/mclic_reg_pkg.sv` | `158bc2cbe7d59179bae10fa7bbd3a1eefcb5a815f1efdadbc48878e8d49b9338` | `158bc2cbe7d59179bae10fa7bbd3a1eefcb5a815f1efdadbc48878e8d49b9338` | `a194e30e62020f40e1e0780e1de82e95bf681116` | `158bc2cbe7d59179bae10fa7bbd3a1eefcb5a815f1efdadbc48878e8d49b9338` | direct | yes |
| `src/mclic_reg_top.sv` | `rtl/clic/src/mclic_reg_top.sv` | `a0349e2546a54c34e398afb411be66f481c186ccc432959d4d31c8d5051070cc` | `a0349e2546a54c34e398afb411be66f481c186ccc432959d4d31c8d5051070cc` | `93560ed07ea8845e884ae75f41ef65f8cdf49b14` | `a0349e2546a54c34e398afb411be66f481c186ccc432959d4d31c8d5051070cc` | direct | yes |

### clint

Actual checkout root: `/home/wangwy/openproject/ara_dsa/hardware/fpga/vcu118/.cache/cheshire_ara/.bender/git/checkouts/clint-de4a234303f657d0`
Pinned commit: `d5390a805c20f9226758a152ba1645f61da73349`

| Source relative path | Export path | Declared SHA256 | Actual source SHA256 (=blob) | Verified Git blob OID | Actual export SHA256 | Result | Compiled |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `src/clint.sv` | `rtl/clint/src/clint.sv` | `7c5b5b530ed5b4cdda0e81dab8ca390e7f8d0a2f22dc98134ead6d985cf28caf` | `7c5b5b530ed5b4cdda0e81dab8ca390e7f8d0a2f22dc98134ead6d985cf28caf` | `b124a05c5d445642fbcca2a97a484bea6fb08852` | `7c5b5b530ed5b4cdda0e81dab8ca390e7f8d0a2f22dc98134ead6d985cf28caf` | direct | yes |
| `src/clint_reg_pkg.sv` | `rtl/clint/src/clint_reg_pkg.sv` | `a3ac42ca85fd268370e9e9b1e7df04151484c1a66269e94ca713df326e127960` | `a3ac42ca85fd268370e9e9b1e7df04151484c1a66269e94ca713df326e127960` | `3b482936b542b7595b88bdd0e650895761704c0f` | `a3ac42ca85fd268370e9e9b1e7df04151484c1a66269e94ca713df326e127960` | direct | yes |
| `src/clint_reg_top.sv` | `rtl/clint/src/clint_reg_top.sv` | `f94b67ae79518f12a2579203523acf3cc4043011edf76c9c7d115403ab9be5a5` | `f94b67ae79518f12a2579203523acf3cc4043011edf76c9c7d115403ab9be5a5` | `1161b4f9e7a3f984d1f2ced0039a6e0e9b4d1b78` | `f94b67ae79518f12a2579203523acf3cc4043011edf76c9c7d115403ab9be5a5` | direct | yes |

### idma

Actual checkout root: `/home/wangwy/openproject/ara_dsa/hardware/fpga/vcu118/.cache/cheshire_ara/.bender/git/checkouts/idma-77bf7fa56d324e6a`
Pinned commit: `ca1b28816a3706be0bf9ce01378246d5346384f0`

| Source relative path | Export path | Declared SHA256 | Actual source SHA256 (=blob) | Verified Git blob OID | Actual export SHA256 | Result | Compiled |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `src/frontends/desc64/idma_desc64_reg_pkg.sv` | `rtl/idma/src/frontends/desc64/idma_desc64_reg_pkg.sv` | `73667b1474df72d6e282a675aefe6911b0188bd945810d0a6c57173234dba7e2` | `73667b1474df72d6e282a675aefe6911b0188bd945810d0a6c57173234dba7e2` | `cb0408b01aca6b9ee543204f4854b1c6995ea13b` | `73667b1474df72d6e282a675aefe6911b0188bd945810d0a6c57173234dba7e2` | direct | yes |
| `src/frontends/desc64/idma_desc64_reg_top.sv` | `rtl/idma/src/frontends/desc64/idma_desc64_reg_top.sv` | `a1bc816a3b6d8b3b15d6dae6dcd5cb3ae69eafadfb4c5641a5ce92067be7ba0f` | `a1bc816a3b6d8b3b15d6dae6dcd5cb3ae69eafadfb4c5641a5ce92067be7ba0f` | `9461431bcfa67bf3341c5acd36afe727c6435fa8` | `a1bc816a3b6d8b3b15d6dae6dcd5cb3ae69eafadfb4c5641a5ce92067be7ba0f` | direct | yes |
| `src/frontends/desc64/idma_desc64_reg_wrapper.sv` | `rtl/idma/src/frontends/desc64/idma_desc64_reg_wrapper.sv` | `11859640ded55521eb334ae77141267f5008559d24ea1277684802a7463d0155` | `11859640ded55521eb334ae77141267f5008559d24ea1277684802a7463d0155` | `24457b241e681c081b76f092d1a15534c097c653` | `11859640ded55521eb334ae77141267f5008559d24ea1277684802a7463d0155` | direct | yes |
| `src/frontends/desc64/idma_desc64_shared_counter.sv` | `rtl/idma/src/frontends/desc64/idma_desc64_shared_counter.sv` | `0659d3d735714f15326ba2a226f2c1d23c4c1a029396ffb30d02d8e276b3d923` | `0659d3d735714f15326ba2a226f2c1d23c4c1a029396ffb30d02d8e276b3d923` | `52da6481a7ae0f16a9331a6ec6002a40321d85b8` | `0659d3d735714f15326ba2a226f2c1d23c4c1a029396ffb30d02d8e276b3d923` | direct | yes |
| `src/frontends/desc64/idma_desc64_top.sv` | `rtl/idma/src/frontends/desc64/idma_desc64_top.sv` | `3aa29bd26527dd17b381e9c1e6f4af73c54e61decc3aef5cb8fda8d0dcaca025` | `3aa29bd26527dd17b381e9c1e6f4af73c54e61decc3aef5cb8fda8d0dcaca025` | `fdda4570012d4a28682b0a5fdde906441b271e53` | `3aa29bd26527dd17b381e9c1e6f4af73c54e61decc3aef5cb8fda8d0dcaca025` | direct | yes |
| `src/frontends/idma_transfer_id_gen.sv` | `rtl/idma/src/frontends/idma_transfer_id_gen.sv` | `bbdd21973d50c2f5367f6696032f9db688c3c243e283420f948e13a8adaaaa1d` | `bbdd21973d50c2f5367f6696032f9db688c3c243e283420f948e13a8adaaaa1d` | `5a801dd3d6830d02d0ec0c0700ea38b587d7deef` | `bbdd21973d50c2f5367f6696032f9db688c3c243e283420f948e13a8adaaaa1d` | direct | yes |
| `src/frontends/register_32bit_2d/idma_reg32_2d_frontend.sv` | `rtl/idma/src/frontends/register_32bit_2d/idma_reg32_2d_frontend.sv` | `4cf02dde1410afd9ecdfe4dbdb82787bbab568d3094cf4c85f18c5503dd1ec13` | `4cf02dde1410afd9ecdfe4dbdb82787bbab568d3094cf4c85f18c5503dd1ec13` | `dc8403dfefe321e9bb0d8a1a23fcc9c3e3bd1ecc` | `4cf02dde1410afd9ecdfe4dbdb82787bbab568d3094cf4c85f18c5503dd1ec13` | direct | yes |
| `src/frontends/register_32bit_2d/idma_reg32_2d_frontend_reg_pkg.sv` | `rtl/idma/src/frontends/register_32bit_2d/idma_reg32_2d_frontend_reg_pkg.sv` | `cf71b18103b230d7b3179db190e1e76c1247de6bfaf575b0b51f0a4bef7c10ff` | `cf71b18103b230d7b3179db190e1e76c1247de6bfaf575b0b51f0a4bef7c10ff` | `c4b436136cd97aeee54587369f7f887c6ad683d4` | `cf71b18103b230d7b3179db190e1e76c1247de6bfaf575b0b51f0a4bef7c10ff` | direct | yes |
| `src/frontends/register_32bit_2d/idma_reg32_2d_frontend_reg_top.sv` | `rtl/idma/src/frontends/register_32bit_2d/idma_reg32_2d_frontend_reg_top.sv` | `a40ea423443398fabbe5e6a3e44a790c70ffa39855158ff5f85fc186ad6a177b` | `a40ea423443398fabbe5e6a3e44a790c70ffa39855158ff5f85fc186ad6a177b` | `c83af9c07a23a12ffd487c901e76d3eef09e898e` | `a40ea423443398fabbe5e6a3e44a790c70ffa39855158ff5f85fc186ad6a177b` | direct | yes |
| `src/frontends/register_64bit/idma_reg64_frontend.sv` | `rtl/idma/src/frontends/register_64bit/idma_reg64_frontend.sv` | `cc8a274a1dee4a97c434cf1799bf2994beaed72b91d5d3793a38ae6d4f33a4fa` | `cc8a274a1dee4a97c434cf1799bf2994beaed72b91d5d3793a38ae6d4f33a4fa` | `a9a7f3eee66c6e62225f6cd545749c41400f52f1` | `cc8a274a1dee4a97c434cf1799bf2994beaed72b91d5d3793a38ae6d4f33a4fa` | direct | yes |
| `src/frontends/register_64bit/idma_reg64_frontend_reg_pkg.sv` | `rtl/idma/src/frontends/register_64bit/idma_reg64_frontend_reg_pkg.sv` | `75ef0edefabb50c40e9621885f5f21bf4d91e51b799fa18f229eaf5f255331e9` | `75ef0edefabb50c40e9621885f5f21bf4d91e51b799fa18f229eaf5f255331e9` | `e1ada5a2c0c5b0aff716f697cd5bd87e68f52262` | `75ef0edefabb50c40e9621885f5f21bf4d91e51b799fa18f229eaf5f255331e9` | direct | yes |
| `src/frontends/register_64bit/idma_reg64_frontend_reg_top.sv` | `rtl/idma/src/frontends/register_64bit/idma_reg64_frontend_reg_top.sv` | `c03f7f2065b1a23920e2d1d49064475a6df9a2262266c2429e8402c241e490ff` | `c03f7f2065b1a23920e2d1d49064475a6df9a2262266c2429e8402c241e490ff` | `c01b4aea3664c8fd5d0076f086a49bdc9d0e8157` | `c03f7f2065b1a23920e2d1d49064475a6df9a2262266c2429e8402c241e490ff` | direct | yes |
| `src/frontends/register_64bit_2d/idma_reg64_2d_frontend.sv` | `rtl/idma/src/frontends/register_64bit_2d/idma_reg64_2d_frontend.sv` | `f5818f4c55f4ada89a967839d794b350335ebe8ac69318af296d49a6c7f96990` | `f5818f4c55f4ada89a967839d794b350335ebe8ac69318af296d49a6c7f96990` | `9b78ba569b34a967075c2071bb46814f27cc6c14` | `f5818f4c55f4ada89a967839d794b350335ebe8ac69318af296d49a6c7f96990` | direct | yes |
| `src/frontends/register_64bit_2d/idma_reg64_2d_frontend_reg_pkg.sv` | `rtl/idma/src/frontends/register_64bit_2d/idma_reg64_2d_frontend_reg_pkg.sv` | `bba8803bf6957d83eaf9daaf1a7dd36a296eedffeab7d5275fba451255fe6f2d` | `bba8803bf6957d83eaf9daaf1a7dd36a296eedffeab7d5275fba451255fe6f2d` | `7131af8ec48558518bfa546ee95d42d545bf089f` | `bba8803bf6957d83eaf9daaf1a7dd36a296eedffeab7d5275fba451255fe6f2d` | direct | yes |
| `src/frontends/register_64bit_2d/idma_reg64_2d_frontend_reg_top.sv` | `rtl/idma/src/frontends/register_64bit_2d/idma_reg64_2d_frontend_reg_top.sv` | `372a56e0075dfbd8223604a07608fb4d18ed2fd714d2f77fc4de947ef1d5ff14` | `372a56e0075dfbd8223604a07608fb4d18ed2fd714d2f77fc4de947ef1d5ff14` | `f19a37eaca3796a66124f143d5aacad1e392a6dd` | `372a56e0075dfbd8223604a07608fb4d18ed2fd714d2f77fc4de947ef1d5ff14` | direct | yes |
| `src/idma_axi_lite_transport_layer.sv` | `rtl/idma/src/idma_axi_lite_transport_layer.sv` | `b7d0365cfd34e35f8dcb160200a24fe17436caf8304ff1b76d4aa561cc4e356c` | `b7d0365cfd34e35f8dcb160200a24fe17436caf8304ff1b76d4aa561cc4e356c` | `1951ceb5bab46a5ef0b153b5a68255eecf38202d` | `b7d0365cfd34e35f8dcb160200a24fe17436caf8304ff1b76d4aa561cc4e356c` | direct | yes |
| `src/idma_axi_transport_layer.sv` | `rtl/idma/src/idma_axi_transport_layer.sv` | `cb54ade81f7bbebbbe999a61d2529d7cdcffb89dbfa5fe5d593b06d013113b2a` | `cb54ade81f7bbebbbe999a61d2529d7cdcffb89dbfa5fe5d593b06d013113b2a` | `0e02f7e8b3d5ba47d8b8e7dfd273fe5438ae271a` | `cb54ade81f7bbebbbe999a61d2529d7cdcffb89dbfa5fe5d593b06d013113b2a` | direct | yes |
| `src/idma_backend.sv` | `rtl/idma/src/idma_backend.sv` | `c3eb5f5668789716e263cbc436dbf8ba0accca6cd2184a1f71b89241dc5a10d3` | `c3eb5f5668789716e263cbc436dbf8ba0accca6cd2184a1f71b89241dc5a10d3` | `2962e340f5893c5b88acd606d9bdf05522e5b517` | `c3eb5f5668789716e263cbc436dbf8ba0accca6cd2184a1f71b89241dc5a10d3` | direct | yes |
| `src/idma_buffer.sv` | `rtl/idma/src/idma_buffer.sv` | `f45d36d77b0ace2b8aeda659c52099e83e17238f5c2d51bd0ed57e4570969f57` | `f45d36d77b0ace2b8aeda659c52099e83e17238f5c2d51bd0ed57e4570969f57` | `c3eadeea72e88121cb0be7d42140060df75a8f88` | `f45d36d77b0ace2b8aeda659c52099e83e17238f5c2d51bd0ed57e4570969f57` | direct | yes |
| `src/idma_channel_coupler.sv` | `rtl/idma/src/idma_channel_coupler.sv` | `06f744341f2badf77805c3763ed13c0d2cdb9cfb7ddc8397752839e495a9909c` | `06f744341f2badf77805c3763ed13c0d2cdb9cfb7ddc8397752839e495a9909c` | `b4a38269df1a2b61aa9752c1238e9a872d0d68a3` | `06f744341f2badf77805c3763ed13c0d2cdb9cfb7ddc8397752839e495a9909c` | direct | yes |
| `src/idma_error_handler.sv` | `rtl/idma/src/idma_error_handler.sv` | `f08a19708ed69c4494e958c32927ff0560953a84e677652e65173e86ee8b1b0d` | `f08a19708ed69c4494e958c32927ff0560953a84e677652e65173e86ee8b1b0d` | `4cbe888077fa5b009d4a139efe47f649a9ef7710` | `f08a19708ed69c4494e958c32927ff0560953a84e677652e65173e86ee8b1b0d` | direct | yes |
| `src/idma_legalizer.sv` | `rtl/idma/src/idma_legalizer.sv` | `6dba196d72453443a87956c897e98dd37caea7905579e40425c7e79a96e3c884` | `6dba196d72453443a87956c897e98dd37caea7905579e40425c7e79a96e3c884` | `d925dd32a9bb6aface203f9e590096bae18bc606` | `6dba196d72453443a87956c897e98dd37caea7905579e40425c7e79a96e3c884` | direct | yes |
| `src/idma_obi_transport_layer.sv` | `rtl/idma/src/idma_obi_transport_layer.sv` | `c350730c3dfd9045bd4be5338effb89fd386df2d7c6e0b4b5632bfe96455729d` | `c350730c3dfd9045bd4be5338effb89fd386df2d7c6e0b4b5632bfe96455729d` | `8c54a4215e5eb9b1ba1f9ffe8909f847390e1fda` | `c350730c3dfd9045bd4be5338effb89fd386df2d7c6e0b4b5632bfe96455729d` | direct | yes |
| `src/idma_pkg.sv` | `rtl/idma/src/idma_pkg.sv` | `9c655f69469e37ddf4a6199d0192f8497b24de2488226fba6d85f605324b705d` | `9c655f69469e37ddf4a6199d0192f8497b24de2488226fba6d85f605324b705d` | `e283f0db37e94757b79114c5cc2a28168720f094` | `9c655f69469e37ddf4a6199d0192f8497b24de2488226fba6d85f605324b705d` | direct | yes |
| `src/idma_stream_fifo.sv` | `rtl/idma/src/idma_stream_fifo.sv` | `21da9f45eae6a975407dcfc58c5dab5589576bf51f0b6fee185bae4804c1a9dd` | `21da9f45eae6a975407dcfc58c5dab5589576bf51f0b6fee185bae4804c1a9dd` | `73f7d33593d8c247a4f14d763860b2aa791b43d6` | `21da9f45eae6a975407dcfc58c5dab5589576bf51f0b6fee185bae4804c1a9dd` | direct | yes |
| `src/include/idma/guard.svh` | `rtl/idma/src/include/idma/guard.svh` | `db37363a14bcc57fff529e8100c10372535ae9e264da71e51816f0f71e0846a0` | `db37363a14bcc57fff529e8100c10372535ae9e264da71e51816f0f71e0846a0` | `cddea6ad510049f589466bd76bfa2907f7261ffb` | `db37363a14bcc57fff529e8100c10372535ae9e264da71e51816f0f71e0846a0` | direct | no |
| `src/include/idma/typedef.svh` | `rtl/idma/src/include/idma/typedef.svh` | `2ef0f27221abd6de4ed9ea8240954c44c23f0431cb35461bbba52ca7d4291588` | `2ef0f27221abd6de4ed9ea8240954c44c23f0431cb35461bbba52ca7d4291588` | `51bb8906b1a84e0f215207ec212bc33569ab703d` | `2ef0f27221abd6de4ed9ea8240954c44c23f0431cb35461bbba52ca7d4291588` | direct | no |
| `src/legacy/axi_dma_backend.sv` | `rtl/idma/src/legacy/axi_dma_backend.sv` | `231837c90c58afb784d03eae6ad5e6a7ef24e84a636fd803f71823cfee6206a1` | `231837c90c58afb784d03eae6ad5e6a7ef24e84a636fd803f71823cfee6206a1` | `20cce510128606b33a5e4a6255decca3c3fdb68c` | `231837c90c58afb784d03eae6ad5e6a7ef24e84a636fd803f71823cfee6206a1` | direct | yes |
| `src/legacy/midends/idma_2D_midend.sv` | `rtl/idma/src/legacy/midends/idma_2D_midend.sv` | `58c77aa0c7e55cadb6e0cbf6ec0ee27c4aa5ea69760564809e8273ccd614822e` | `58c77aa0c7e55cadb6e0cbf6ec0ee27c4aa5ea69760564809e8273ccd614822e` | `46f8bd3c669c18fec4b0bc84f37604b652fb34dd` | `58c77aa0c7e55cadb6e0cbf6ec0ee27c4aa5ea69760564809e8273ccd614822e` | direct | yes |
| `src/midends/idma_nd_midend.sv` | `rtl/idma/src/midends/idma_nd_midend.sv` | `17f65a898fd340944cc8da00f189e5cd6348048293fe6452e203b1f381023a51` | `17f65a898fd340944cc8da00f189e5cd6348048293fe6452e203b1f381023a51` | `c7b47956a755c34b8a555607ce4c1c6bba38b613` | `17f65a898fd340944cc8da00f189e5cd6348048293fe6452e203b1f381023a51` | direct | yes |
| `src/synth_wrapper/idma_backend_synth.sv` | `rtl/idma/src/synth_wrapper/idma_backend_synth.sv` | `da391dbc8cf30d899e6d530a49ec06894c2836867565e8dcde38787171fa920c` | `da391dbc8cf30d899e6d530a49ec06894c2836867565e8dcde38787171fa920c` | `cccc51cf8f7d7e2de0760aa575fd65703cd2a2b4` | `da391dbc8cf30d899e6d530a49ec06894c2836867565e8dcde38787171fa920c` | direct | yes |
| `src/synth_wrapper/idma_lite_backend_synth.sv` | `rtl/idma/src/synth_wrapper/idma_lite_backend_synth.sv` | `d2bbb424a16da4d0b77148ebb507787b64c5c99bf299bb0086bfd2c35bca8bc9` | `d2bbb424a16da4d0b77148ebb507787b64c5c99bf299bb0086bfd2c35bca8bc9` | `dfd91a28a9a54d069dd4b84a2ab9f21285a9030e` | `d2bbb424a16da4d0b77148ebb507787b64c5c99bf299bb0086bfd2c35bca8bc9` | direct | yes |
| `src/synth_wrapper/idma_nd_backend_synth.sv` | `rtl/idma/src/synth_wrapper/idma_nd_backend_synth.sv` | `a999fb88f39d6e1710b51fa128f0a94ccb13d1be57b4c73b350fe068f8f324a7` | `a999fb88f39d6e1710b51fa128f0a94ccb13d1be57b4c73b350fe068f8f324a7` | `4fdc40b467ce3dfcef6e149f28e8fac0b1935a8e` | `a999fb88f39d6e1710b51fa128f0a94ccb13d1be57b4c73b350fe068f8f324a7` | direct | yes |
| `src/synth_wrapper/idma_obi_backend_synth.sv` | `rtl/idma/src/synth_wrapper/idma_obi_backend_synth.sv` | `b3ceeeaf247eb2d74aecdbb4d4f8618ef574c132605f7d255d3ff46496421f98` | `b3ceeeaf247eb2d74aecdbb4d4f8618ef574c132605f7d255d3ff46496421f98` | `618e39080cb2f7d2eda223594ce841fc70f314f2` | `b3ceeeaf247eb2d74aecdbb4d4f8618ef574c132605f7d255d3ff46496421f98` | direct | yes |

### irq_router

Actual checkout root: `/home/wangwy/openproject/ara_dsa/hardware/fpga/vcu118/.cache/cheshire_ara/.bender/git/checkouts/irq_router-376b3d113c15d0ef`
Pinned commit: `d1d31350b24f3965b3a51e1bc96c71eb34e94db3`

| Source relative path | Export path | Declared SHA256 | Actual source SHA256 (=blob) | Verified Git blob OID | Actual export SHA256 | Result | Compiled |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `rtl/irq_router.sv` | `rtl/irq_router/rtl/irq_router.sv` | `51579e33bf2b95d9d586ad72d3f94ea8bcd11442c651c75fe9c191909b082d38` | `51579e33bf2b95d9d586ad72d3f94ea8bcd11442c651c75fe9c191909b082d38` | `3a2d8d5cc92bcefcca16561df719426978287551` | `51579e33bf2b95d9d586ad72d3f94ea8bcd11442c651c75fe9c191909b082d38` | direct | yes |
| `rtl/irq_router_reg_pkg.sv` | `rtl/irq_router/rtl/irq_router_reg_pkg.sv` | `1d53b0b29b492e79adc79803ca543ef16767563165285e4739bc5b81c1bf3736` | `1d53b0b29b492e79adc79803ca543ef16767563165285e4739bc5b81c1bf3736` | `72de1533705e736b777935178beaccd08f26bda3` | `1d53b0b29b492e79adc79803ca543ef16767563165285e4739bc5b81c1bf3736` | direct | yes |
| `rtl/irq_router_reg_top.sv` | `rtl/irq_router/rtl/irq_router_reg_top.sv` | `afefe55f3f82b6adb136d312a162ca5330e143df542d8f6853c48e872c450a42` | `afefe55f3f82b6adb136d312a162ca5330e143df542d8f6853c48e872c450a42` | `ec064fab2192489a8607175b6a220bfe9dd59a48` | `afefe55f3f82b6adb136d312a162ca5330e143df542d8f6853c48e872c450a42` | direct | yes |

### opentitan_peripherals

Actual checkout root: `/home/wangwy/openproject/ara_dsa/hardware/fpga/vcu118/.cache/cheshire_ara/.bender/git/checkouts/opentitan_peripherals-7b624fb57f78de9a`
Pinned commit: `cd3153de2783abd3d03d0595e6c4b32413c62f14`

| Source relative path | Export path | Declared SHA256 | Actual source SHA256 (=blob) | Verified Git blob OID | Actual export SHA256 | Result | Compiled |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `src/gpio/rtl/gpio.sv` | `rtl/opentitan_peripherals/src/gpio/rtl/gpio.sv` | `978072a85fdaeeb72bd6112bb1f3b2d7555c342d72033b3e1cc3e6d85dd24129` | `978072a85fdaeeb72bd6112bb1f3b2d7555c342d72033b3e1cc3e6d85dd24129` | `3c2b948b5b50ac13b87bba148e59a904e417ea34` | `978072a85fdaeeb72bd6112bb1f3b2d7555c342d72033b3e1cc3e6d85dd24129` | direct | yes |
| `src/gpio/rtl/gpio_reg_pkg.sv` | `rtl/opentitan_peripherals/src/gpio/rtl/gpio_reg_pkg.sv` | `0377ad543658f8f13e5f0db78514f2d932c07d3cab5a589ab5fc7926d72c1dff` | `0377ad543658f8f13e5f0db78514f2d932c07d3cab5a589ab5fc7926d72c1dff` | `399dbd39715c83f7d0bfd26111f219b13420b41e` | `0377ad543658f8f13e5f0db78514f2d932c07d3cab5a589ab5fc7926d72c1dff` | direct | yes |
| `src/gpio/rtl/gpio_reg_top.sv` | `rtl/opentitan_peripherals/src/gpio/rtl/gpio_reg_top.sv` | `97517c1c1a57377fd68e5fba66387a529321335e509a81819910bdb2becde214` | `97517c1c1a57377fd68e5fba66387a529321335e509a81819910bdb2becde214` | `2038041aa38a66332e0f7cc7ae4cef693a31b0ca` | `97517c1c1a57377fd68e5fba66387a529321335e509a81819910bdb2becde214` | direct | yes |
| `src/i2c/rtl/i2c.sv` | `rtl/opentitan_peripherals/src/i2c/rtl/i2c.sv` | `187c5c4f143cc0beebf95b8dd27e10de44f3c85a1ceb869841e8634e41380ede` | `187c5c4f143cc0beebf95b8dd27e10de44f3c85a1ceb869841e8634e41380ede` | `df051006f16c6baf52f3254609a778d68aaac831` | `187c5c4f143cc0beebf95b8dd27e10de44f3c85a1ceb869841e8634e41380ede` | direct | yes |
| `src/i2c/rtl/i2c_core.sv` | `rtl/opentitan_peripherals/src/i2c/rtl/i2c_core.sv` | `12a5e6e4585ad82c5b86f4475719c781ed4632ffa2556eea67a548be4e8c4adb` | `12a5e6e4585ad82c5b86f4475719c781ed4632ffa2556eea67a548be4e8c4adb` | `6f740b622eb3a5a7e447fe075915d072d851d390` | `12a5e6e4585ad82c5b86f4475719c781ed4632ffa2556eea67a548be4e8c4adb` | direct | yes |
| `src/i2c/rtl/i2c_fsm.sv` | `rtl/opentitan_peripherals/src/i2c/rtl/i2c_fsm.sv` | `acbb23ec8bb7983fb47332342e4bc9bad15b68bd513e800a6ce034b9164f39aa` | `acbb23ec8bb7983fb47332342e4bc9bad15b68bd513e800a6ce034b9164f39aa` | `ff019408fd44ae39d9f2d11d6439ee7cc18e3f37` | `acbb23ec8bb7983fb47332342e4bc9bad15b68bd513e800a6ce034b9164f39aa` | direct | yes |
| `src/i2c/rtl/i2c_pkg.sv` | `rtl/opentitan_peripherals/src/i2c/rtl/i2c_pkg.sv` | `bc9a02cb51a2d1ef2dfbe8ab83f5387f796e657c88d8b0572d6dfe5e4e96ca16` | `bc9a02cb51a2d1ef2dfbe8ab83f5387f796e657c88d8b0572d6dfe5e4e96ca16` | `f8bb905246184ee233dc0527eaf6f20681df61cc` | `bc9a02cb51a2d1ef2dfbe8ab83f5387f796e657c88d8b0572d6dfe5e4e96ca16` | direct | yes |
| `src/i2c/rtl/i2c_reg_pkg.sv` | `rtl/opentitan_peripherals/src/i2c/rtl/i2c_reg_pkg.sv` | `8cbb6226047f77bbbd3deb3d44354498db256267c7f27ea038e25f645293acf7` | `8cbb6226047f77bbbd3deb3d44354498db256267c7f27ea038e25f645293acf7` | `133af129210f1f8b7031e0c0289132beddf9b8be` | `8cbb6226047f77bbbd3deb3d44354498db256267c7f27ea038e25f645293acf7` | direct | yes |
| `src/i2c/rtl/i2c_reg_top.sv` | `rtl/opentitan_peripherals/src/i2c/rtl/i2c_reg_top.sv` | `6559fb77901a64c713608d6130b35202ec3f26c7de83303f43a13a95070049d3` | `6559fb77901a64c713608d6130b35202ec3f26c7de83303f43a13a95070049d3` | `f57c1d8c90d0aeabe90ae1eb94d9c3f437ef03c2` | `6559fb77901a64c713608d6130b35202ec3f26c7de83303f43a13a95070049d3` | direct | yes |
| `src/prim/prim_pulp_platform/prim_flop_2sync.sv` | `rtl/opentitan_peripherals/src/prim/prim_pulp_platform/prim_flop_2sync.sv` | `8599babd479ad54b1afede6858ba7dbe8736937b4fe4ee7cfc26fd4f4f5991ba` | `8599babd479ad54b1afede6858ba7dbe8736937b4fe4ee7cfc26fd4f4f5991ba` | `72f8de792ee8d1dd7fbb17f2a19f52c43af7bcfc` | `8599babd479ad54b1afede6858ba7dbe8736937b4fe4ee7cfc26fd4f4f5991ba` | direct | yes |
| `src/prim/prim_pulp_platform/prim_flop_en.sv` | `rtl/opentitan_peripherals/src/prim/prim_pulp_platform/prim_flop_en.sv` | `d145fb30c5f3c9f8aa33d8e63415e1db610d959aa191c468cbbb247a6a881da9` | `d145fb30c5f3c9f8aa33d8e63415e1db610d959aa191c468cbbb247a6a881da9` | `2711663412beb1553405c809e45d4e8f5f0c4088` | `d145fb30c5f3c9f8aa33d8e63415e1db610d959aa191c468cbbb247a6a881da9` | direct | yes |
| `src/prim/rtl/prim_fifo_async.sv` | `rtl/opentitan_peripherals/src/prim/rtl/prim_fifo_async.sv` | `c4ab9a3a2d24bb67df3876315c1c7e11397925d337c5931c9f87356e693868f1` | `c4ab9a3a2d24bb67df3876315c1c7e11397925d337c5931c9f87356e693868f1` | `df90ccdcc4656241c46310413334972905a1ba06` | `c4ab9a3a2d24bb67df3876315c1c7e11397925d337c5931c9f87356e693868f1` | direct | yes |
| `src/prim/rtl/prim_fifo_sync.sv` | `rtl/opentitan_peripherals/src/prim/rtl/prim_fifo_sync.sv` | `7dc7b04fb9fee8c608f0b5af7e2fef82422693ba112509d8fca4f2637f425f55` | `7dc7b04fb9fee8c608f0b5af7e2fef82422693ba112509d8fca4f2637f425f55` | `1d786830d2b15a0f1be358314ed570f07de00075` | `7dc7b04fb9fee8c608f0b5af7e2fef82422693ba112509d8fca4f2637f425f55` | direct | yes |
| `src/prim/rtl/prim_fifo_sync_cnt.sv` | `rtl/opentitan_peripherals/src/prim/rtl/prim_fifo_sync_cnt.sv` | `0fb5a3e321091b4c8dedbf43b330dc5cc9d7a98d868d405d0fa49adf7210de65` | `0fb5a3e321091b4c8dedbf43b330dc5cc9d7a98d868d405d0fa49adf7210de65` | `b8f6fba829324ac2c79efdba6be5eb7fda5284e7` | `0fb5a3e321091b4c8dedbf43b330dc5cc9d7a98d868d405d0fa49adf7210de65` | direct | yes |
| `src/prim/rtl/prim_filter_ctr.sv` | `rtl/opentitan_peripherals/src/prim/rtl/prim_filter_ctr.sv` | `9ee08314ca37b1b3c17d42f220ef6feb1ea3071a7dcca69cd01c5246d45eda1f` | `9ee08314ca37b1b3c17d42f220ef6feb1ea3071a7dcca69cd01c5246d45eda1f` | `435b16155eb0e6c94edb3934314268ffecf35c42` | `9ee08314ca37b1b3c17d42f220ef6feb1ea3071a7dcca69cd01c5246d45eda1f` | direct | yes |
| `src/prim/rtl/prim_intr_hw.sv` | `rtl/opentitan_peripherals/src/prim/rtl/prim_intr_hw.sv` | `87a8b62373aa27e70490cdf165d2ced13659578ad92ee1a46c451837cf93d404` | `87a8b62373aa27e70490cdf165d2ced13659578ad92ee1a46c451837cf93d404` | `1e87f6c6b2e8af4442123a44a6f04162ca31a5c8` | `87a8b62373aa27e70490cdf165d2ced13659578ad92ee1a46c451837cf93d404` | direct | yes |
| `src/prim/rtl/prim_max_tree.sv` | `rtl/opentitan_peripherals/src/prim/rtl/prim_max_tree.sv` | `ef0bc1d7e8f9ad2b410570cc4a13f98e504474eff281ca1946f5c5ab2a4accc1` | `ef0bc1d7e8f9ad2b410570cc4a13f98e504474eff281ca1946f5c5ab2a4accc1` | `58b7d05fe66e2288c88c97e789d421397f9c7b70` | `ef0bc1d7e8f9ad2b410570cc4a13f98e504474eff281ca1946f5c5ab2a4accc1` | direct | yes |
| `src/prim/rtl/prim_packer_fifo.sv` | `rtl/opentitan_peripherals/src/prim/rtl/prim_packer_fifo.sv` | `d95549a3bc6e86dc5b2071edd4709ab50ce931d58505ce73cdd0ed2c271b1afd` | `d95549a3bc6e86dc5b2071edd4709ab50ce931d58505ce73cdd0ed2c271b1afd` | `57781d41d17739fb8a2442860a2481c6c1ce7972` | `d95549a3bc6e86dc5b2071edd4709ab50ce931d58505ce73cdd0ed2c271b1afd` | direct | yes |
| `src/prim/rtl/prim_pulse_sync.sv` | `rtl/opentitan_peripherals/src/prim/rtl/prim_pulse_sync.sv` | `c28f37f796c07646b3950bb5d29e405334adf558a53e68c1bd3765950621155f` | `c28f37f796c07646b3950bb5d29e405334adf558a53e68c1bd3765950621155f` | `f37bca91c056fabdc9a3c510dc212ca9783948b8` | `c28f37f796c07646b3950bb5d29e405334adf558a53e68c1bd3765950621155f` | direct | yes |
| `src/prim/rtl/prim_sync_reqack.sv` | `rtl/opentitan_peripherals/src/prim/rtl/prim_sync_reqack.sv` | `2ad21119507f3d1752f534cf335a02401b37662899a008845571363fcd8511db` | `2ad21119507f3d1752f534cf335a02401b37662899a008845571363fcd8511db` | `33c679f85e633fb443aff55bfc7650d447eee4eb` | `2ad21119507f3d1752f534cf335a02401b37662899a008845571363fcd8511db` | direct | yes |
| `src/prim/rtl/prim_sync_reqack_data.sv` | `rtl/opentitan_peripherals/src/prim/rtl/prim_sync_reqack_data.sv` | `a8029a61db1edcd018a12c9117af6ed1611510350d395200298d7acc2c536ae4` | `a8029a61db1edcd018a12c9117af6ed1611510350d395200298d7acc2c536ae4` | `ba1ce5a4c61ef7127aa34bc9831aff45ecbbbe45` | `a8029a61db1edcd018a12c9117af6ed1611510350d395200298d7acc2c536ae4` | direct | yes |
| `src/prim/rtl/prim_util_pkg.sv` | `rtl/opentitan_peripherals/src/prim/rtl/prim_util_pkg.sv` | `352542203218a11c12ff29e00075193190ad35c7ce82748571b998c7bb3d739d` | `352542203218a11c12ff29e00075193190ad35c7ce82748571b998c7bb3d739d` | `f5e3c92af522acd15577dcf0c39d25071156020e` | `352542203218a11c12ff29e00075193190ad35c7ce82748571b998c7bb3d739d` | direct | yes |
| `src/rv_plic/rtl/rv_plic.sv` | `rtl/opentitan_peripherals/src/rv_plic/rtl/rv_plic.sv` | `16636ef1a144fc614d255c6e91d12b5a9898df895ceaf0e1292ed211a42af24c` | `16636ef1a144fc614d255c6e91d12b5a9898df895ceaf0e1292ed211a42af24c` | `fae82be3a5b6ea8a4fc061231ad0db86849f41c6` | `16636ef1a144fc614d255c6e91d12b5a9898df895ceaf0e1292ed211a42af24c` | direct | yes |
| `src/rv_plic/rtl/rv_plic_gateway.sv` | `rtl/opentitan_peripherals/src/rv_plic/rtl/rv_plic_gateway.sv` | `c9d86f32bd218d3641cdac73656e6ac776b01e72041b98b5f509d3c4956078ff` | `c9d86f32bd218d3641cdac73656e6ac776b01e72041b98b5f509d3c4956078ff` | `c81810b24b64e2ccc2cf33134cd8b9050e684906` | `c9d86f32bd218d3641cdac73656e6ac776b01e72041b98b5f509d3c4956078ff` | direct | yes |
| `src/rv_plic/rtl/rv_plic_reg_pkg.sv` | `rtl/opentitan_peripherals/src/rv_plic/rtl/rv_plic_reg_pkg.sv` | `6e01bcc602506f3d0c5581b25f6bcc2d9800a84ba82488d4004c7bc071510f60` | `6e01bcc602506f3d0c5581b25f6bcc2d9800a84ba82488d4004c7bc071510f60` | `5710c38c040f436e6c92e7a3e65721af1bd64ee8` | `6e01bcc602506f3d0c5581b25f6bcc2d9800a84ba82488d4004c7bc071510f60` | direct | yes |
| `src/rv_plic/rtl/rv_plic_reg_top.sv` | `rtl/opentitan_peripherals/src/rv_plic/rtl/rv_plic_reg_top.sv` | `c57f256c00f09aa02a6483ec2f7fc5dd3ba1badf65225aeefc4ed822f902ed2f` | `c57f256c00f09aa02a6483ec2f7fc5dd3ba1badf65225aeefc4ed822f902ed2f` | `a6f00a358f1d4c4b91016ebfee9c578abaf8b882` | `c57f256c00f09aa02a6483ec2f7fc5dd3ba1badf65225aeefc4ed822f902ed2f` | direct | yes |
| `src/rv_plic/rtl/rv_plic_target.sv` | `rtl/opentitan_peripherals/src/rv_plic/rtl/rv_plic_target.sv` | `b108ec9304c49e966e7de30e6fada6035cf6e498860157f2428b77b0a1c69153` | `b108ec9304c49e966e7de30e6fada6035cf6e498860157f2428b77b0a1c69153` | `d02a4fb02c3df4b71a05ef108f528704d46bb297` | `b108ec9304c49e966e7de30e6fada6035cf6e498860157f2428b77b0a1c69153` | direct | yes |
| `src/spi_host/rtl/spi_host.sv` | `rtl/opentitan_peripherals/src/spi_host/rtl/spi_host.sv` | `ffd2ebecc5c53acdc409f1daa2f7c683bbc9028cce8da1d4bcf7b2b5e50518c9` | `ffd2ebecc5c53acdc409f1daa2f7c683bbc9028cce8da1d4bcf7b2b5e50518c9` | `ca205d54b4ee3b4c31b46964a148bb3c39a979ee` | `ffd2ebecc5c53acdc409f1daa2f7c683bbc9028cce8da1d4bcf7b2b5e50518c9` | direct | yes |
| `src/spi_host/rtl/spi_host_byte_merge.sv` | `rtl/opentitan_peripherals/src/spi_host/rtl/spi_host_byte_merge.sv` | `96bb589eee80f18559de063438dc424ae55365ced336310d4b65ec3cf0deb521` | `96bb589eee80f18559de063438dc424ae55365ced336310d4b65ec3cf0deb521` | `faa425bdd5debb440110e808786fa85b17af90c0` | `96bb589eee80f18559de063438dc424ae55365ced336310d4b65ec3cf0deb521` | direct | yes |
| `src/spi_host/rtl/spi_host_byte_select.sv` | `rtl/opentitan_peripherals/src/spi_host/rtl/spi_host_byte_select.sv` | `f82438e32271603545a821d2a8bd6b37020408b88e0c9395e598b3040ae4fe2f` | `f82438e32271603545a821d2a8bd6b37020408b88e0c9395e598b3040ae4fe2f` | `78f288ed077deeb38a3c498c3b48cb939a04e5ae` | `f82438e32271603545a821d2a8bd6b37020408b88e0c9395e598b3040ae4fe2f` | direct | yes |
| `src/spi_host/rtl/spi_host_cmd_pkg.sv` | `rtl/opentitan_peripherals/src/spi_host/rtl/spi_host_cmd_pkg.sv` | `7b347b675f82a8d8174d294e1c3e52a4f790919866488f81dbe7fb9628f0a9d9` | `7b347b675f82a8d8174d294e1c3e52a4f790919866488f81dbe7fb9628f0a9d9` | `45abc0223fda4218de5121e667d08576a9ee8ecd` | `7b347b675f82a8d8174d294e1c3e52a4f790919866488f81dbe7fb9628f0a9d9` | direct | yes |
| `src/spi_host/rtl/spi_host_command_queue.sv` | `rtl/opentitan_peripherals/src/spi_host/rtl/spi_host_command_queue.sv` | `d48d46787273f066961b7bd3ee01b566f97b4ea6afa41313f96f38800d6b7786` | `d48d46787273f066961b7bd3ee01b566f97b4ea6afa41313f96f38800d6b7786` | `fbca9e49022f5873dce2d7a1ec9bff9993b2d6d5` | `d48d46787273f066961b7bd3ee01b566f97b4ea6afa41313f96f38800d6b7786` | direct | yes |
| `src/spi_host/rtl/spi_host_core.sv` | `rtl/opentitan_peripherals/src/spi_host/rtl/spi_host_core.sv` | `84a626b971ab587b8b911fa52c866a60bbf5ff09b5b6dab6effbe49bac836fa8` | `84a626b971ab587b8b911fa52c866a60bbf5ff09b5b6dab6effbe49bac836fa8` | `c3e7712f9233f7297cb0ec1d80560425079121d0` | `84a626b971ab587b8b911fa52c866a60bbf5ff09b5b6dab6effbe49bac836fa8` | direct | yes |
| `src/spi_host/rtl/spi_host_data_fifos.sv` | `rtl/opentitan_peripherals/src/spi_host/rtl/spi_host_data_fifos.sv` | `1d93e7e97ff59a78a54480eaead897303f74b9e28f091841f8ec891f06f8304f` | `1d93e7e97ff59a78a54480eaead897303f74b9e28f091841f8ec891f06f8304f` | `0f1e36ee5f4d021e3fa9f6109b4efb92a6760003` | `1d93e7e97ff59a78a54480eaead897303f74b9e28f091841f8ec891f06f8304f` | direct | yes |
| `src/spi_host/rtl/spi_host_fsm.sv` | `rtl/opentitan_peripherals/src/spi_host/rtl/spi_host_fsm.sv` | `27f2252ded2981ab9d0adf9fa5127978d42c8d197e9f50ad9a0e777511df9b22` | `27f2252ded2981ab9d0adf9fa5127978d42c8d197e9f50ad9a0e777511df9b22` | `842a7589716c2ce8fe639bef523e86eb4c5cbbcc` | `27f2252ded2981ab9d0adf9fa5127978d42c8d197e9f50ad9a0e777511df9b22` | direct | yes |
| `src/spi_host/rtl/spi_host_reg_pkg.sv` | `rtl/opentitan_peripherals/src/spi_host/rtl/spi_host_reg_pkg.sv` | `3bc59a1ea181e0a237b67420de900c0bfbc7f2f313520db3267d77103c0dc76f` | `3bc59a1ea181e0a237b67420de900c0bfbc7f2f313520db3267d77103c0dc76f` | `29ba1a27bc1a358ec985b97e05fb8f0590d25a1c` | `3bc59a1ea181e0a237b67420de900c0bfbc7f2f313520db3267d77103c0dc76f` | direct | yes |
| `src/spi_host/rtl/spi_host_reg_top.sv` | `rtl/opentitan_peripherals/src/spi_host/rtl/spi_host_reg_top.sv` | `df15f26a3391491bea81c840c2addefae7f305c05cb551a2978c6e6e84ae253e` | `df15f26a3391491bea81c840c2addefae7f305c05cb551a2978c6e6e84ae253e` | `7821cfd360a78806b48760b51aaa1c5eab6ffe88` | `df15f26a3391491bea81c840c2addefae7f305c05cb551a2978c6e6e84ae253e` | direct | yes |
| `src/spi_host/rtl/spi_host_shift_register.sv` | `rtl/opentitan_peripherals/src/spi_host/rtl/spi_host_shift_register.sv` | `5c472b260e3a90a716120e1185a5325b004bd96f80b82cef482de421b782159b` | `5c472b260e3a90a716120e1185a5325b004bd96f80b82cef482de421b782159b` | `00351e61b9b3544ed17ee69799966e11b0f6a0d6` | `5c472b260e3a90a716120e1185a5325b004bd96f80b82cef482de421b782159b` | direct | yes |
| `src/spi_host/rtl/spi_host_window.sv` | `rtl/opentitan_peripherals/src/spi_host/rtl/spi_host_window.sv` | `5847a927a7d7c7d285f36a480de5852541e966f23160e7119bb6380553fa2a62` | `5847a927a7d7c7d285f36a480de5852541e966f23160e7119bb6380553fa2a62` | `a10ff9328a0f65aefc2c3b97adaf92f73e748165` | `5847a927a7d7c7d285f36a480de5852541e966f23160e7119bb6380553fa2a62` | direct | yes |

### register_interface

Actual checkout root: `/home/wangwy/openproject/ara_dsa/hardware/fpga/vcu118/.cache/cheshire_ara/.bender/git/checkouts/register_interface-902ad5bfde7bb98c`
Pinned commit: `ae616e5a1ec2b41e72d200e5ab09c65e94aebd3d`

| Source relative path | Export path | Declared SHA256 | Actual source SHA256 (=blob) | Verified Git blob OID | Actual export SHA256 | Result | Compiled |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `include/register_interface/assign.svh` | `rtl/register_interface/include/register_interface/assign.svh` | `362408c8e4fe2d73be91b8ec7a753620bdd2734f25fd8d4851c66f38131b883c` | `362408c8e4fe2d73be91b8ec7a753620bdd2734f25fd8d4851c66f38131b883c` | `267dfabbf305b784db562b0761bb3b6afac7e4c1` | `362408c8e4fe2d73be91b8ec7a753620bdd2734f25fd8d4851c66f38131b883c` | direct | no |
| `include/register_interface/typedef.svh` | `rtl/register_interface/include/register_interface/typedef.svh` | `d78094f45d6e67b72d5ccfe998495dac562c301f03619d6a2a1a4b0c5cf27189` | `d78094f45d6e67b72d5ccfe998495dac562c301f03619d6a2a1a4b0c5cf27189` | `350d79e164096986d0c0229999d54ccf6a0a8a7e` | `d78094f45d6e67b72d5ccfe998495dac562c301f03619d6a2a1a4b0c5cf27189` | direct | no |
| `src/apb_to_reg.sv` | `rtl/register_interface/src/apb_to_reg.sv` | `eecefe6daba3a5a4ffd7df22198c778b8350d6983e1400f66bae17bcda6f47bc` | `eecefe6daba3a5a4ffd7df22198c778b8350d6983e1400f66bae17bcda6f47bc` | `6a9988653bcbdd1d8b979b7ca4b99c1c422cd155` | `eecefe6daba3a5a4ffd7df22198c778b8350d6983e1400f66bae17bcda6f47bc` | direct | yes |
| `src/axi_lite_to_reg.sv` | `rtl/register_interface/src/axi_lite_to_reg.sv` | `c497445d931b7a35e07d307921cf0d6aef5bcb3bc53ebade9378d0261f6776e0` | `c497445d931b7a35e07d307921cf0d6aef5bcb3bc53ebade9378d0261f6776e0` | `98eca25816b05200d7c3a0ed42aff9cb28678c74` | `c497445d931b7a35e07d307921cf0d6aef5bcb3bc53ebade9378d0261f6776e0` | direct | yes |
| `src/axi_to_reg_v2.sv` | `rtl/register_interface/src/axi_to_reg_v2.sv` | `df090ca44a38464c16cb88fb859e23e8dc192609a059e0c12f7325e7c87170cb` | `df090ca44a38464c16cb88fb859e23e8dc192609a059e0c12f7325e7c87170cb` | `90530cdc9f45c5d81b5bf8cd9981cc8d898626d3` | `df090ca44a38464c16cb88fb859e23e8dc192609a059e0c12f7325e7c87170cb` | direct | yes |
| `src/deprecated/axi_to_reg.sv` | `rtl/register_interface/src/deprecated/axi_to_reg.sv` | `f7232bb4e0f914b0ecbebc5f67e681b5c3bc7e1b8229fdf2c266f9025a94cca4` | `f7232bb4e0f914b0ecbebc5f67e681b5c3bc7e1b8229fdf2c266f9025a94cca4` | `a84392b13b115779ae1108f1854a069e6a0cf1b1` | `f7232bb4e0f914b0ecbebc5f67e681b5c3bc7e1b8229fdf2c266f9025a94cca4` | direct | yes |
| `src/periph_to_reg.sv` | `rtl/register_interface/src/periph_to_reg.sv` | `f6ff322cfea6a4c3413523df7534e313abb32215a3635a2500ee395edb060fef` | `f6ff322cfea6a4c3413523df7534e313abb32215a3635a2500ee395edb060fef` | `64c8f294d369792b680203c942194437faa9331c` | `f6ff322cfea6a4c3413523df7534e313abb32215a3635a2500ee395edb060fef` | direct | yes |
| `src/reg_cdc.sv` | `rtl/register_interface/src/reg_cdc.sv` | `825757fff4aa98d4c5c916e281a77fbbdb2eeacbba8b38307aab36f9f4f8338b` | `825757fff4aa98d4c5c916e281a77fbbdb2eeacbba8b38307aab36f9f4f8338b` | `6f30ad2c4927ba156e43bce6e702ff88a0c049f6` | `825757fff4aa98d4c5c916e281a77fbbdb2eeacbba8b38307aab36f9f4f8338b` | direct | yes |
| `src/reg_cut.sv` | `rtl/register_interface/src/reg_cut.sv` | `b527cd80851be3cf572f419cb62d7661f1435847d3d8aa3e158fbfd3d0ed2fe5` | `b527cd80851be3cf572f419cb62d7661f1435847d3d8aa3e158fbfd3d0ed2fe5` | `56c4c369cbb60075103fa129408bbb05d9ffdf06` | `b527cd80851be3cf572f419cb62d7661f1435847d3d8aa3e158fbfd3d0ed2fe5` | direct | yes |
| `src/reg_demux.sv` | `rtl/register_interface/src/reg_demux.sv` | `9dae9a736c17cae7d5f5aaa06c303e0e9185b43d4b38b3d386260d4ee6cf7814` | `9dae9a736c17cae7d5f5aaa06c303e0e9185b43d4b38b3d386260d4ee6cf7814` | `94404d5dc4d7d0235a2de3fd2ae8ad91b3f649b3` | `9dae9a736c17cae7d5f5aaa06c303e0e9185b43d4b38b3d386260d4ee6cf7814` | direct | yes |
| `src/reg_err_slv.sv` | `rtl/register_interface/src/reg_err_slv.sv` | `c1a82b143b11aca9396c2aa83c40d0cef612434713fb59b1afa626145cb7d64d` | `c1a82b143b11aca9396c2aa83c40d0cef612434713fb59b1afa626145cb7d64d` | `723625fd320dd8749ba036d3adbb3ab4748741eb` | `c1a82b143b11aca9396c2aa83c40d0cef612434713fb59b1afa626145cb7d64d` | direct | yes |
| `src/reg_filter_empty_writes.sv` | `rtl/register_interface/src/reg_filter_empty_writes.sv` | `1cd7f1805d06c59cba7b8ccc84f171acf6748758da775b2fa09a03f7ee53f2fe` | `1cd7f1805d06c59cba7b8ccc84f171acf6748758da775b2fa09a03f7ee53f2fe` | `f074a693deb22c0db9a57a006a24b8ecba195c56` | `1cd7f1805d06c59cba7b8ccc84f171acf6748758da775b2fa09a03f7ee53f2fe` | direct | yes |
| `src/reg_intf.sv` | `rtl/register_interface/src/reg_intf.sv` | `6d6fa7332215d4afe5a46316ed4ce6cb38abb95b9da7034df13ecc7feb597984` | `6d6fa7332215d4afe5a46316ed4ce6cb38abb95b9da7034df13ecc7feb597984` | `5923ae3a30c0232cdbb4ac1db32dd2ad87eccb9d` | `6d6fa7332215d4afe5a46316ed4ce6cb38abb95b9da7034df13ecc7feb597984` | direct | yes |
| `src/reg_mux.sv` | `rtl/register_interface/src/reg_mux.sv` | `a437ffda02b3bbb7369a81eadf91a9e2bb2c50f9901d51419c4aaed480f21b75` | `a437ffda02b3bbb7369a81eadf91a9e2bb2c50f9901d51419c4aaed480f21b75` | `74f9806efdeb073ab4fa999749a4ed7f2091367c` | `a437ffda02b3bbb7369a81eadf91a9e2bb2c50f9901d51419c4aaed480f21b75` | direct | yes |
| `src/reg_to_apb.sv` | `rtl/register_interface/src/reg_to_apb.sv` | `957b3046504ea7fd80deb7fbeb6be0d02a9925c843b15d8484b4e9f37783e1da` | `957b3046504ea7fd80deb7fbeb6be0d02a9925c843b15d8484b4e9f37783e1da` | `598b24e94c5cea5c6a88b907871fff8d32653f3a` | `957b3046504ea7fd80deb7fbeb6be0d02a9925c843b15d8484b4e9f37783e1da` | direct | yes |
| `src/reg_to_axi.sv` | `rtl/register_interface/src/reg_to_axi.sv` | `abccc74660cc948c36b0686b184514fd8a8b920c6fc702b89e22d14e0c386b8b` | `abccc74660cc948c36b0686b184514fd8a8b920c6fc702b89e22d14e0c386b8b` | `caf30f23d9a842c6d3be2911b09d3b492beecce3` | `abccc74660cc948c36b0686b184514fd8a8b920c6fc702b89e22d14e0c386b8b` | direct | yes |
| `src/reg_to_mem.sv` | `rtl/register_interface/src/reg_to_mem.sv` | `33773692ebd5f6264c7edbe5f42b27a0503ba0432787ba20e6545da699a44267` | `33773692ebd5f6264c7edbe5f42b27a0503ba0432787ba20e6545da699a44267` | `1079931fccdcfdb5aa93fee995657aca5554d8f7` | `33773692ebd5f6264c7edbe5f42b27a0503ba0432787ba20e6545da699a44267` | direct | yes |
| `src/reg_to_tlul.sv` | `rtl/register_interface/src/reg_to_tlul.sv` | `9057320f03ffe935ed4c6a76f676f4985cbf2a88b935b76567cb3f4debedd8dc` | `9057320f03ffe935ed4c6a76f676f4985cbf2a88b935b76567cb3f4debedd8dc` | `94bf2f1d20f3c999622ee7c2692aaece9a6d9a5d` | `9057320f03ffe935ed4c6a76f676f4985cbf2a88b935b76567cb3f4debedd8dc` | direct | yes |
| `src/reg_uniform.sv` | `rtl/register_interface/src/reg_uniform.sv` | `ccd00cbafbb35dbeb38f0fd2ce6dc61e797c1cca4ff91876bf51cf3df91d6890` | `ccd00cbafbb35dbeb38f0fd2ce6dc61e797c1cca4ff91876bf51cf3df91d6890` | `0046b877339f1b62dd35226fb669e2535c557a95` | `ccd00cbafbb35dbeb38f0fd2ce6dc61e797c1cca4ff91876bf51cf3df91d6890` | direct | yes |
| `vendor/lowrisc_opentitan/src/prim_subreg.sv` | `rtl/register_interface/vendor/lowrisc_opentitan/src/prim_subreg.sv` | `307ac44d6b36f09525a3b4bdf6d07086b668ca0e0343c7e83ae857b245dfd2d6` | `307ac44d6b36f09525a3b4bdf6d07086b668ca0e0343c7e83ae857b245dfd2d6` | `d1fab641921fccc4350bf02718ddb2d9f9d93df3` | `307ac44d6b36f09525a3b4bdf6d07086b668ca0e0343c7e83ae857b245dfd2d6` | direct | yes |
| `vendor/lowrisc_opentitan/src/prim_subreg_arb.sv` | `rtl/register_interface/vendor/lowrisc_opentitan/src/prim_subreg_arb.sv` | `4b8b6dc42d7c554e192f06b0f81b18a22ef101fa53a26931716997cbb1a6da08` | `4b8b6dc42d7c554e192f06b0f81b18a22ef101fa53a26931716997cbb1a6da08` | `410cf2d1d7d8277238ba69e6091a84696182a101` | `4b8b6dc42d7c554e192f06b0f81b18a22ef101fa53a26931716997cbb1a6da08` | direct | yes |
| `vendor/lowrisc_opentitan/src/prim_subreg_ext.sv` | `rtl/register_interface/vendor/lowrisc_opentitan/src/prim_subreg_ext.sv` | `852fef59bc568250360e3866a24a98e1d9884421bbbea57b74d52234c53f772e` | `852fef59bc568250360e3866a24a98e1d9884421bbbea57b74d52234c53f772e` | `6db975d8da6227ef365062c58e1a506b4d65afee` | `852fef59bc568250360e3866a24a98e1d9884421bbbea57b74d52234c53f772e` | direct | yes |
| `vendor/lowrisc_opentitan/src/prim_subreg_shadow.sv` | `rtl/register_interface/vendor/lowrisc_opentitan/src/prim_subreg_shadow.sv` | `a26b9981d94ba1b95a5bd5de10f810300e0a305288417d32b034229fdd4cfe5b` | `a26b9981d94ba1b95a5bd5de10f810300e0a305288417d32b034229fdd4cfe5b` | `347e57f88c8de7923f666cf733df24c05fd35379` | `a26b9981d94ba1b95a5bd5de10f810300e0a305288417d32b034229fdd4cfe5b` | direct | yes |

### riscv-dbg

Actual checkout root: `/home/wangwy/openproject/ara_dsa/hardware/fpga/vcu118/.cache/cheshire_ara/.bender/git/checkouts/riscv-dbg-1a98531d53bb4602`
Pinned commit: `358f90110220adf7a083f8b65d157e836d706236`

| Source relative path | Export path | Declared SHA256 | Actual source SHA256 (=blob) | Verified Git blob OID | Actual export SHA256 | Result | Compiled |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `debug_rom/debug_rom.sv` | `rtl/riscv-dbg/debug_rom/debug_rom.sv` | `3dfc5bce1021e5fcc07c31cfe2fa087eb6801d31160d7f47692880d2637e6ce6` | `3dfc5bce1021e5fcc07c31cfe2fa087eb6801d31160d7f47692880d2637e6ce6` | `ac10eeea87da1bcfc41d59d1288e0eb57f1e8ee8` | `3dfc5bce1021e5fcc07c31cfe2fa087eb6801d31160d7f47692880d2637e6ce6` | direct | yes |
| `debug_rom/debug_rom_one_scratch.sv` | `rtl/riscv-dbg/debug_rom/debug_rom_one_scratch.sv` | `ae30ed4821f5b1bc08e05c3c44db8deda5fbb7d9ec5991227d1bbccfa94e8bff` | `ae30ed4821f5b1bc08e05c3c44db8deda5fbb7d9ec5991227d1bbccfa94e8bff` | `3cd2d9e2fcdc9310f91c117ad1a597c233e221de` | `ae30ed4821f5b1bc08e05c3c44db8deda5fbb7d9ec5991227d1bbccfa94e8bff` | direct | yes |
| `src/dm_csrs.sv` | `rtl/riscv-dbg/src/dm_csrs.sv` | `7dd06f9da4f0f08f92a2185dcae8a3f391c7f7e9f9f1e8d4196c3e703a0fb05a` | `7dd06f9da4f0f08f92a2185dcae8a3f391c7f7e9f9f1e8d4196c3e703a0fb05a` | `59d1c90a144d574a9800f082b2e023e4a10696e5` | `7dd06f9da4f0f08f92a2185dcae8a3f391c7f7e9f9f1e8d4196c3e703a0fb05a` | direct | yes |
| `src/dm_mem.sv` | `rtl/riscv-dbg/src/dm_mem.sv` | `2e44921811623deda5ce489b245519be1727a4e98ddc5e0c6eb6bfa0aeaecc0e` | `2e44921811623deda5ce489b245519be1727a4e98ddc5e0c6eb6bfa0aeaecc0e` | `9ff3c86a70eda6ca522e0f0dd868125169384a7f` | `2e44921811623deda5ce489b245519be1727a4e98ddc5e0c6eb6bfa0aeaecc0e` | direct | yes |
| `src/dm_obi_top.sv` | `rtl/riscv-dbg/src/dm_obi_top.sv` | `80b5ef62b692100271f22c7a98b956807af2db43e8eb0b285b110700a0e10a65` | `80b5ef62b692100271f22c7a98b956807af2db43e8eb0b285b110700a0e10a65` | `aa0b4f0fa675fdf6d677d1ee4be61720be4dd5c6` | `80b5ef62b692100271f22c7a98b956807af2db43e8eb0b285b110700a0e10a65` | direct | yes |
| `src/dm_pkg.sv` | `rtl/riscv-dbg/src/dm_pkg.sv` | `ddd883331359926221f593a853b62a21537ecf7a9ffa7427e845ac1d03c32487` | `ddd883331359926221f593a853b62a21537ecf7a9ffa7427e845ac1d03c32487` | `cc2e1ebcfadf0980638919d11483bf94df4a0313` | `ddd883331359926221f593a853b62a21537ecf7a9ffa7427e845ac1d03c32487` | direct | yes |
| `src/dm_sba.sv` | `rtl/riscv-dbg/src/dm_sba.sv` | `4386f04de9145c6285948b72c404fb6a563830507ebc17c6e79620b35066cdd9` | `4386f04de9145c6285948b72c404fb6a563830507ebc17c6e79620b35066cdd9` | `1c31c52eb7c4cc2caaf150c123025b8d3292cb79` | `4386f04de9145c6285948b72c404fb6a563830507ebc17c6e79620b35066cdd9` | direct | yes |
| `src/dm_top.sv` | `rtl/riscv-dbg/src/dm_top.sv` | `89a1f707cc89ec984387fec61f73966e437dd2e399d387b18e2e8fa2232dc823` | `89a1f707cc89ec984387fec61f73966e437dd2e399d387b18e2e8fa2232dc823` | `c21e58d9cd8a1d5001b8460241fcda36cdae61b5` | `89a1f707cc89ec984387fec61f73966e437dd2e399d387b18e2e8fa2232dc823` | direct | yes |
| `src/dmi_cdc.sv` | `rtl/riscv-dbg/src/dmi_cdc.sv` | `85bff5443ad0e19aa5f7dcfcc3054901e6d2a4e364cde8c3ba3db329fa093c1d` | `85bff5443ad0e19aa5f7dcfcc3054901e6d2a4e364cde8c3ba3db329fa093c1d` | `f9d66fdd41baf9dcc69e039214355ab6abbe84e5` | `85bff5443ad0e19aa5f7dcfcc3054901e6d2a4e364cde8c3ba3db329fa093c1d` | direct | yes |
| `src/dmi_jtag.sv` | `rtl/riscv-dbg/src/dmi_jtag.sv` | `a3dbcd4190586d11821b798853a17da4a5276a4d9c56b8007340b7919dc58d0b` | `a3dbcd4190586d11821b798853a17da4a5276a4d9c56b8007340b7919dc58d0b` | `577c3fd071798eeb22e498383f16055913dde3b9` | `424019b9b1ce656ad810f2135d808f31db6c582344aa5ab26f37fc2401f0153f` | adapted:patch_jtag | yes |
| `src/dmi_jtag_tap.sv` | `rtl/riscv-dbg/src/dmi_jtag_tap.sv` | `7fe8d372125983237b6dd6c76137f10958b2e1222471f82105fe5f8fea935a8a` | `7fe8d372125983237b6dd6c76137f10958b2e1222471f82105fe5f8fea935a8a` | `53f0fa9d8d598bd014dd44f26a084c1133446526` | `4a893c776f25c27661cd9157eb9ec3ef30ca81ca92541d2d485d57f9189cb975` | adapted:patch_tap | yes |

### serial_link

Actual checkout root: `/home/wangwy/openproject/ara_dsa/hardware/fpga/vcu118/.cache/cheshire_ara/.bender/git/checkouts/serial_link-6e09ea4800bad616`
Pinned commit: `5a25f5a71074f1ebb6de7b5280f2b16924bcc666`

| Source relative path | Export path | Declared SHA256 | Actual source SHA256 (=blob) | Verified Git blob OID | Actual export SHA256 | Result | Compiled |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `src/axis/include/axis/assign.svh` | `rtl/serial_link/src/axis/include/axis/assign.svh` | `fffc7524545267187005a70240a0954b0bae980b0f5109abc88afa7a76dac87f` | `fffc7524545267187005a70240a0954b0bae980b0f5109abc88afa7a76dac87f` | `49a96bbc02ce0b8e2cbfed996260c8c2f594367c` | `fffc7524545267187005a70240a0954b0bae980b0f5109abc88afa7a76dac87f` | direct | no |
| `src/axis/include/axis/typedef.svh` | `rtl/serial_link/src/axis/include/axis/typedef.svh` | `dcc9e0128b7bffa52bb208b28bac81ec0e086be6d53fa6867fd00c16c982f9b8` | `dcc9e0128b7bffa52bb208b28bac81ec0e086be6d53fa6867fd00c16c982f9b8` | `9ab71fe513f8f1c8df9fb9ec240387bee772526f` | `dcc9e0128b7bffa52bb208b28bac81ec0e086be6d53fa6867fd00c16c982f9b8` | direct | no |
| `src/channel_allocator/channel_despread_sfr.sv` | `rtl/serial_link/src/channel_allocator/channel_despread_sfr.sv` | `faf896e721896860a32e1ca11e27766470336429d095ed58fed1cb3ba7f84d52` | `faf896e721896860a32e1ca11e27766470336429d095ed58fed1cb3ba7f84d52` | `89fd1578019808f5e24bf7bb5d86ad95575788e1` | `faf896e721896860a32e1ca11e27766470336429d095ed58fed1cb3ba7f84d52` | direct | yes |
| `src/channel_allocator/channel_spread_sfr.sv` | `rtl/serial_link/src/channel_allocator/channel_spread_sfr.sv` | `112605d9b2336b50ed4373454b65c506c930e61bccabd4071318a1fef34a1295` | `112605d9b2336b50ed4373454b65c506c930e61bccabd4071318a1fef34a1295` | `4a6a3904cb5cd213ea6b3f50be1bb90e1da8da48` | `112605d9b2336b50ed4373454b65c506c930e61bccabd4071318a1fef34a1295` | direct | yes |
| `src/channel_allocator/serial_link_channel_allocator.sv` | `rtl/serial_link/src/channel_allocator/serial_link_channel_allocator.sv` | `c13dd4cc6cad66231f87cbc4e00e6816e0d6906ff3a53e6e87eadbe4b4dc4dd8` | `c13dd4cc6cad66231f87cbc4e00e6816e0d6906ff3a53e6e87eadbe4b4dc4dd8` | `bd01a203c41167f9f60f021756c26769ff06deb7` | `c13dd4cc6cad66231f87cbc4e00e6816e0d6906ff3a53e6e87eadbe4b4dc4dd8` | direct | yes |
| `src/channel_allocator/stream_chopper.sv` | `rtl/serial_link/src/channel_allocator/stream_chopper.sv` | `dce286e37d889b247b734a209b5b3d6243aacee426a54d17a7b093542617955d` | `dce286e37d889b247b734a209b5b3d6243aacee426a54d17a7b093542617955d` | `bc30c266766b05a8276fe6c4abfdcc80d4237294` | `dce286e37d889b247b734a209b5b3d6243aacee426a54d17a7b093542617955d` | direct | yes |
| `src/channel_allocator/stream_dechopper.sv` | `rtl/serial_link/src/channel_allocator/stream_dechopper.sv` | `b8cddcada245ab8d14046188d7e9d09a3201f515cafe10b18f3d563b2c675417` | `b8cddcada245ab8d14046188d7e9d09a3201f515cafe10b18f3d563b2c675417` | `546b873187b22740113ab8a1f221f40c492029a0` | `b8cddcada245ab8d14046188d7e9d09a3201f515cafe10b18f3d563b2c675417` | direct | yes |
| `src/regs/serial_link_reg_pkg.sv` | `rtl/serial_link/src/regs/serial_link_reg_pkg.sv` | `3635d2d763b5af560d29cf1087ccb368966d80bedd37ce5b8e7fe60e1633b4ab` | `3635d2d763b5af560d29cf1087ccb368966d80bedd37ce5b8e7fe60e1633b4ab` | `5dc099c27b33f1528fcc10bf332613821ff66e97` | `3635d2d763b5af560d29cf1087ccb368966d80bedd37ce5b8e7fe60e1633b4ab` | direct | yes |
| `src/regs/serial_link_reg_top.sv` | `rtl/serial_link/src/regs/serial_link_reg_top.sv` | `90e12e5f4acdf49c41fe1cad5c25da441d703715d88edb4a930477798f64f1f7` | `90e12e5f4acdf49c41fe1cad5c25da441d703715d88edb4a930477798f64f1f7` | `587ba5d9ba8a14c5a722f8def4faf7fe6387d5c2` | `90e12e5f4acdf49c41fe1cad5c25da441d703715d88edb4a930477798f64f1f7` | direct | yes |
| `src/regs/serial_link_single_channel_reg_pkg.sv` | `rtl/serial_link/src/regs/serial_link_single_channel_reg_pkg.sv` | `22a60f2dc9729d71cc1936f215c98c56eca601b082d514936992a07cf4078ebf` | `22a60f2dc9729d71cc1936f215c98c56eca601b082d514936992a07cf4078ebf` | `fa0f2b155adb6db20238156c4bae4e835677c047` | `22a60f2dc9729d71cc1936f215c98c56eca601b082d514936992a07cf4078ebf` | direct | yes |
| `src/regs/serial_link_single_channel_reg_top.sv` | `rtl/serial_link/src/regs/serial_link_single_channel_reg_top.sv` | `93c7dd2b0bd712ecbcbd4297b7a741c56abb092cc7aa0b016b0665b462431317` | `93c7dd2b0bd712ecbcbd4297b7a741c56abb092cc7aa0b016b0665b462431317` | `9e5058a89ae803b515b2eb1da227b854c5e449c0` | `93c7dd2b0bd712ecbcbd4297b7a741c56abb092cc7aa0b016b0665b462431317` | direct | yes |
| `src/serial_link.sv` | `rtl/serial_link/src/serial_link.sv` | `b4a4a537349811c6e776c117f0401a3b2dae055ca6807e52f3121be8d58b4980` | `b4a4a537349811c6e776c117f0401a3b2dae055ca6807e52f3121be8d58b4980` | `1ea76d7aa79bd6a3fc79aa651907bb3a43d50502` | `b4a4a537349811c6e776c117f0401a3b2dae055ca6807e52f3121be8d58b4980` | direct | yes |
| `src/serial_link_data_link.sv` | `rtl/serial_link/src/serial_link_data_link.sv` | `34ffd50e5dce95c040a21713effe7c8c487585468de47d567caee802ca63c3aa` | `34ffd50e5dce95c040a21713effe7c8c487585468de47d567caee802ca63c3aa` | `2182eed1ecca4784128087e23858801c7fe56937` | `34ffd50e5dce95c040a21713effe7c8c487585468de47d567caee802ca63c3aa` | direct | yes |
| `src/serial_link_network.sv` | `rtl/serial_link/src/serial_link_network.sv` | `98f4b782597ada255cc94ffb5471f16169807a13cc189d4f1e6dc83f48690e9a` | `98f4b782597ada255cc94ffb5471f16169807a13cc189d4f1e6dc83f48690e9a` | `d480a2809d471c8c3468dfe4f71c63a7b4f9add2` | `98f4b782597ada255cc94ffb5471f16169807a13cc189d4f1e6dc83f48690e9a` | direct | yes |
| `src/serial_link_occamy_wrapper.sv` | `rtl/serial_link/src/serial_link_occamy_wrapper.sv` | `b40f023a0bad6353f2c493655e54caf32c1e9af16f348c3a8fc23b4389379f77` | `b40f023a0bad6353f2c493655e54caf32c1e9af16f348c3a8fc23b4389379f77` | `97c838ab8cab19c4ec04abb64936a8d58539becf` | `b40f023a0bad6353f2c493655e54caf32c1e9af16f348c3a8fc23b4389379f77` | direct | yes |
| `src/serial_link_physical.sv` | `rtl/serial_link/src/serial_link_physical.sv` | `f3dea5ced76a2c66e853066a3cc621a749be9ba1a56c68746cb9e7750fa1e609` | `f3dea5ced76a2c66e853066a3cc621a749be9ba1a56c68746cb9e7750fa1e609` | `840f19830e4b1376ddfc240a011fa3899aa0d0e3` | `f3dea5ced76a2c66e853066a3cc621a749be9ba1a56c68746cb9e7750fa1e609` | direct | yes |
| `src/serial_link_pkg.sv` | `rtl/serial_link/src/serial_link_pkg.sv` | `a675f095ed2c4afb5085a44a18f25777e680422ba9a19969419e4eae52d639e7` | `a675f095ed2c4afb5085a44a18f25777e680422ba9a19969419e4eae52d639e7` | `e3503557de3dde18cdb7b9616d46ec5ddeb96909` | `a675f095ed2c4afb5085a44a18f25777e680422ba9a19969419e4eae52d639e7` | direct | yes |
| `src/serial_link_synth_wrapper.sv` | `rtl/serial_link/src/serial_link_synth_wrapper.sv` | `6224b566d4a015b6a80387726bed7540229072525a33b4a48078e5ebd1cebad1` | `6224b566d4a015b6a80387726bed7540229072525a33b4a48078e5ebd1cebad1` | `8fed73d97e5ca668511014f50d5f5347390efb19` | `6224b566d4a015b6a80387726bed7540229072525a33b4a48078e5ebd1cebad1` | direct | yes |

### unbent

Actual checkout root: `/home/wangwy/openproject/ara_dsa/hardware/fpga/vcu118/.cache/cheshire_ara/.bender/git/checkouts/unbent-a93c32aef5b319fd`
Pinned commit: `e9c9d5cfb635f2d4668c816ce9235798cfecb297`

| Source relative path | Export path | Declared SHA256 | Actual source SHA256 (=blob) | Verified Git blob OID | Actual export SHA256 | Result | Compiled |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `src/axi_err_unit_wrap.sv` | `rtl/unbent/src/axi_err_unit_wrap.sv` | `ae9d5c14ed5658364769b9668b87f28f39b1e2af07e4b7eec820cdec9218ee36` | `ae9d5c14ed5658364769b9668b87f28f39b1e2af07e4b7eec820cdec9218ee36` | `e53b4a725c03cf586056c0b4878d2b419d29d893` | `ae9d5c14ed5658364769b9668b87f28f39b1e2af07e4b7eec820cdec9218ee36` | direct | yes |
| `src/bus_err_unit.sv` | `rtl/unbent/src/bus_err_unit.sv` | `32f1e85bef38dcf99383150dc74608f7699545b12a02d4c951efe125de0eb048` | `32f1e85bef38dcf99383150dc74608f7699545b12a02d4c951efe125de0eb048` | `26d15fd1e50fb2b69405d37790eb87b50026d196` | `32f1e85bef38dcf99383150dc74608f7699545b12a02d4c951efe125de0eb048` | direct | yes |
| `src/bus_err_unit_bare.sv` | `rtl/unbent/src/bus_err_unit_bare.sv` | `e6fd99c2ecfb3ddc02cce9724e0ba425ad1e8f119165bd63dcd8b8172611f0ad` | `e6fd99c2ecfb3ddc02cce9724e0ba425ad1e8f119165bd63dcd8b8172611f0ad` | `c8df1df7631cb74b34e8d1f481b168a3d73a536c` | `e6fd99c2ecfb3ddc02cce9724e0ba425ad1e8f119165bd63dcd8b8172611f0ad` | direct | yes |
| `src/bus_err_unit_reg_pkg.sv` | `rtl/unbent/src/bus_err_unit_reg_pkg.sv` | `512e6a452a8823b0ae87d180fe34afc18fbdbbc407fea8fe7eb6d1f9a8c2f6b6` | `512e6a452a8823b0ae87d180fe34afc18fbdbbc407fea8fe7eb6d1f9a8c2f6b6` | `c05d536adb7f830b78dc8e6a7413286f12a5e5c0` | `512e6a452a8823b0ae87d180fe34afc18fbdbbc407fea8fe7eb6d1f9a8c2f6b6` | direct | yes |
| `src/bus_err_unit_reg_top.sv` | `rtl/unbent/src/bus_err_unit_reg_top.sv` | `d8bb869b6a32a052e372b61088e71c74ebeaf46e9bf13715323bf921c4c8150b` | `d8bb869b6a32a052e372b61088e71c74ebeaf46e9bf13715323bf921c4c8150b` | `c35d7ffd712179333f446e367f0209aad94d792b` | `d8bb869b6a32a052e372b61088e71c74ebeaf46e9bf13715323bf921c4c8150b` | direct | yes |
| `src/obi_err_unit_wrap.sv` | `rtl/unbent/src/obi_err_unit_wrap.sv` | `1649ce58790d411f4a928bb11410efa1b72424052e171dc39530af77d6abcca6` | `1649ce58790d411f4a928bb11410efa1b72424052e171dc39530af77d6abcca6` | `8075aa2e0bd2f920da58b33abe0fcb5ac2438de4` | `1649ce58790d411f4a928bb11410efa1b72424052e171dc39530af77d6abcca6` | direct | yes |

## Read-only reproduction

The following is the exact bounded main audit used for file/blob/replay measurement. It prints JSON to stdout only and does not create a script, report, checkout, bytecode, or export. It intentionally fails instead of fetching a missing Git object. Resolver risks above were separately checked by reading only the explicit Cheshire `Bender.lock`, `Bender.local`, the pinned lock blob, and the 14 configured origin strings; no dependency search was used.

```bash
python3 -B - <<'PY'
import ast
from collections import Counter
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess

main = Path("/home/wangwy/openproject/ara_dsa")
verify = Path("/home/wangwy/openproject/ara_dsa_verification")
audit_path = verify / "verification/out/fpga-rtl-handoff-20260922/source-audit.json"
roots_path = main / "hardware/fpga/vcu118/.cache/roots.json"
audit = json.loads(audit_path.read_bytes())
export = Path(audit["export_root"])
manifest_path = export / "manifest.json"
manifest = json.loads(manifest_path.read_bytes())
roots = json.loads(roots_path.read_bytes())
roots["board"] = str(main / "hardware/fpga/vcu118/.cache/cheshire_board")
records = [r for r in audit["source_correspondence"]["files"] if r["status"] == "missing_source"]
assert len(records) == 226
claims = {r["file"]: r["source_sha256"] for r in manifest["source_hashes_before_integration"]}
assert len(claims) == len(manifest["source_hashes_before_integration"])
env = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_NO_LAZY_FETCH="1", PYTHONDONTWRITEBYTECODE="1")
def git(root, *args):
    r = subprocess.run(["git", "--no-optional-locks", "-c", "core.fsmonitor=false",
                        "-c", "gc.auto=0", "-c", "maintenance.auto=false",
                        "-C", str(root), *args], env=env, capture_output=True)
    if r.returncode:
        raise RuntimeError(r.stderr.decode(errors="replace").strip())
    return r.stdout
def sha(b):
    return hashlib.sha256(b).hexdigest()
snapshots = {}
def read(path):
    data = path.read_bytes()
    snapshots[str(path)] = sha(data)
    return data
for p in (audit_path, roots_path, manifest_path, export / "SHA256SUMS",
          verify / "verification/fpga/check_sources.py",
          main / "hardware/fpga/vcu118/prepare.py"):
    read(p)
# Extract only the already-inspected pure function definitions/constants.
ns = {"hashlib": hashlib}
adapter_sources = [
    ("jtag_fpga.py", {"replace", "patch_jtag", "patch_tap", "patch_ready"}, {"OLD_READY", "NEW_READY"}),
    ("export.py", {"replace_once", "patch_soc_pkg", "patch_soc", "patch_dram"}, set()),
]
adapters = []
for name, funcs, constants in adapter_sources:
    path = main / "hardware/fpga/vcu118" / name
    source = read(path)
    tree = ast.parse(source, filename=str(path))
    selected = [n for n in tree.body if
                (isinstance(n, ast.FunctionDef) and n.name in funcs) or
                (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in constants for t in n.targets))]
    assert {n.name for n in selected if isinstance(n, ast.FunctionDef)} == funcs
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), ns)
    rel = str(path.relative_to(main))
    pin = manifest["revisions"]["ara"]["commit"]
    blob = git(main, "cat-file", "blob", pin + ":" + rel)
    adapters.append({"path": str(path), "sha256": sha(source), "ara_pin": pin,
                     "pinned_blob_sha256": sha(blob), "equals_ara_pin": source == blob,
                     "status": git(main, "status", "--porcelain=v1", "--untracked-files=no", "--", rel).decode(),
                     "functions": sorted(funcs)})
transforms = {
    "rtl/cheshire/hw/cheshire_pkg.sv": "patch_soc_pkg",
    "rtl/cheshire/hw/cheshire_soc.sv": "patch_soc",
    "rtl/riscv-dbg/src/dmi_jtag.sv": "patch_jtag",
    "rtl/riscv-dbg/src/dmi_jtag_tap.sv": "patch_tap",
    "rtl/board/dram_wrapper_xilinx.sv": "patch_dram",
}
packages = {}
for package in sorted({r["export_path"].split("/")[1] for r in records}):
    root = Path(roots[package])
    pin = manifest["cheshire_board_port_commit"] if package == "board" else manifest["revisions"][package]["commit"]
    head = git(root, "rev-parse", "HEAD").decode().strip()
    toplevel = git(root, "rev-parse", "--show-toplevel").decode().strip()
    assert Path(toplevel).resolve() == root.resolve(), (package, toplevel, root)
    assert git(root, "cat-file", "-t", pin).strip() == b"commit"
    changes = git(root, "status", "--porcelain=v1", "-z", "--untracked-files=no").decode().split("\0")
    packages[package] = {"root": str(root), "resolved_root": str(root.resolve()),
                         "pin": pin, "head": head, "head_equals_pin": head == pin,
                         "tracked_status": [s for s in changes if s],
                         "manifest_tracked_changes": None if package == "board" else manifest["revisions"][package]["tracked_changes"],
                         "remote": git(root, "config", "--get", "remote.origin.url").decode().strip()}
results = []
for r in records:
    ep = r["export_path"]
    _, package, relative = ep.split("/", 2)
    p = packages[package]
    if package == "board":
        relative = "target/xilinx/src/" + relative
    path = Path(p["root"]) / relative
    out = read(export / ep)
    item = {"export_path": ep, "package": package, "relative": relative,
            "source_path": str(path), "resolved_source": str(path.resolve()),
            "audit_source_path": str(verify / r["source_path"]),
            "audit_source_still_missing": not (verify / r["source_path"]).is_file(),
            "compiled": r["compiled"], "manifest_source_sha256": claims.get(ep),
            "audit_claim_equals_manifest": r["manifest_source_sha256"] == claims.get(ep),
            "audit_export_sha256": r["export_sha256"], "export_sha256": sha(out),
            "export_matches_audit": sha(out) == r["export_sha256"],
            "source_exists": path.is_file(), "blob_exists": False}
    before = read(path) if path.is_file() else None
    item["source_sha256"] = sha(before) if before is not None else None
    item["source_matches_manifest"] = sha(before) == claims[ep] if before is not None and ep in claims else None
    item["source_equals_export"] = before == out if before is not None else False
    item["source_git_status"] = git(p["root"], "status", "--porcelain=v1", "--untracked-files=all", "--", relative).decode()
    try:
        oid = git(p["root"], "rev-parse", "--verify", p["pin"] + ":" + relative).decode().strip()
        blob = git(p["root"], "cat-file", "blob", oid)
        item.update(blob_exists=True, blob_oid=oid, blob_sha256=sha(blob),
                    blob_oid_verified=hashlib.sha1(b"blob " + str(len(blob)).encode() + b"\0" + blob).hexdigest() == oid,
                    source_equals_blob=before == blob,
                    blob_equals_export=blob == out,
                    blob_matches_manifest=sha(blob) == claims[ep] if ep in claims else None)
    except RuntimeError as e:
        blob = None
        item["blob_error"] = str(e)
    if ep in transforms:
        fn = transforms[ep]
        item["adaptation"] = fn
        for label, data in (("source", before), ("blob", blob)):
            if data is None:
                continue
            try:
                # Path.read_text() in export uses universal newline translation.
                text = data.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
                after = ns[fn](text).encode("utf-8")
                item[label + "_replay_sha256"] = sha(after)
                item[label + "_replay_equals_export"] = after == out
            except Exception as e:
                item[label + "_replay_error"] = str(e)
    results.append(item)
for package, p in packages.items():
    rows = [r for r in results if r["package"] == package]
    p["counts"] = {
        "total": len(rows),
        "compiled": sum(r["compiled"] for r in rows),
        "located_file": sum(r["source_exists"] for r in rows),
        "located_blob": sum(r["blob_exists"] for r in rows),
        "source_equals_export": sum(r["source_equals_export"] for r in rows),
        "blob_equals_export": sum(r.get("blob_equals_export", False) for r in rows),
        "source_equals_blob": sum(r.get("source_equals_blob", False) for r in rows),
        "claimed": sum(r["manifest_source_sha256"] is not None for r in rows),
        "source_matches_manifest": sum(r["source_matches_manifest"] is True for r in rows),
        "blob_matches_manifest": sum(r.get("blob_matches_manifest") is True for r in rows),
        "source_replay": sum(r.get("source_replay_equals_export", False) for r in rows),
        "blob_replay": sum(r.get("blob_replay_equals_export", False) for r in rows),
        "truly_missing": sum(not r["source_exists"] and not r["blob_exists"] for r in rows),
        "unexplained": sum(not (r["source_equals_export"] or r.get("source_replay_equals_export", False)) for r in rows),
    }
changed = [path for path, digest in snapshots.items() if sha(Path(path).read_bytes()) != digest]
print(json.dumps({"time_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  "scope": len(records), "audit_accepted": audit["accepted"],
                  "audit_counts": audit["source_correspondence"]["counts"],
                  "audit_revisions_equal_manifest": audit["export_recorded_revisions"] == manifest["revisions"],
                  "metadata": {str(p): snapshots[str(p)] for p in (audit_path, roots_path, manifest_path, export/"SHA256SUMS")},
                  "manifest_created_utc": manifest["created_utc"],
                  "packages": packages, "adapters": adapters, "files": results,
                  "snapshots": snapshots, "inputs_changed_during_read": changed}, indent=2))
PY
```

