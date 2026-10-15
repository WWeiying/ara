# Original Mask-Logical Alias Restart Programs

Successor: [BOUNDED.md](BOUNDED.md) records the six original-prefix/exact-tuple
partitions, their host/Spike PASS and authorized candidate02 service launch.
The full-matrix preparation below is retained history, not a launch request.

Status: **3/3 full original-source matrices PASS on host and Spike; prepared for
SoC replay, NOT DUT PASS.** No VCS launched and no production RTL changed.
The complete loops are retained, not tiny replacement VFU cases. Their scalar
instruction cost is substantial; VCS scheduling/budget requires separate review.

## Original Identity And Observed Stall

Campaign root `C` is
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01`.
Archive `A` is `C/rvv_mask_logic_restart01`. Original generator/C are under
`/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix`.
The current files match the archived source manifest. Calling
`masks.assembly(sew, lmul, aliases=True, restart=True)` reproduces all three
archived `A/<name>.S` byte for byte. Original ELF copies in both
`A/overlay/opt/ara-tests/<name>` and `C/rvv_additions36/binaries/<name>` agree
with the release manifest and historical triage ELF hashes.

Common source SHA256:

| File | SHA256 |
| --- | --- |
| masks.py | dc7fa06cbf35900cb4178eddd933f8497647c4191e2544c8fcf38b93bef439ca |
| mask_oracle.c | fa837fa916fa40fa526c542d5be4de64b3f90150990ec9cf5a96e949e1ed422e |
| operations.h | d75b84985efb54ad3ea7564dee83d1b5abbf88a80f44fc8225f6d3c3be0e3c50 |

Names below have prefix `rvv_masks_alias_restart_`:

| Suffix | Original Linux ELF SHA256 | Archived assembly SHA256 |
| --- | --- | --- |
| e8_m4 | d12585c094241b3b591fd115e3a51568edce5e3aece92f4914dbb41b35dcf300 | 7ec1516211568e744971f9c8227f54f6c167b36124a8ed2838febf88a4784d05 |
| e8_m8 | c0248bf088a20f66c141bc31d0029936cec655823f06a3460154e02502656998 | 11e7ba74889c495b72b753aec6f88ae0bee50ea86e75215f752303552ff7c1dd |
| e16_m8 | b81d1aa69ad7041f46657eefa39f45a6099bb1ea9d19da1890b074982844783e | b33eb0998b64d148b444678d9d9048d4929eb5f914ff5807359adf91479e7bd1 |

The three `mask_logic_source_stream` records in
`C/stall_family_triage02/triage.json` identify these measured scenes:

| Suffix | Report path relative to C | Last/head PC | Observed cycle delta |
| --- | --- | --- | ---: |
| e8_m4 | rvv_failure_retest01/supervisor44/terminal_recovery239.json | 0x105b8 / 0x105bc | 523307822 |
| e8_m8 | rvv_recovery08_74/terminal_scene/report.json | 0x105b8 / 0x105bc | 537064574 |
| e16_m8 | rvv_failure_retest01/supervisor44/latest_report.json | 0x105c4 / 0x105c8 | 529342422 |

All last printed `RVV_MASK_TRIAL vl=512 vstart=256`. The original print
condition uniquely identifies seed=0, raw_op=0, mode=0, start-choice=1:
zero-based overall trial 97 for e8_m4/e16_m8 and 65 for e8_m8. This tuple is
source-derived, not a captured internal acceptance. The archived opcode at
the last PC is `66882457`, `vmand.mm v8,v8,v16`; head opcode is `00802573`,
`csrr a0,vstart`. Last-retired PC does not prove the mask operation never
retired; the head probe has no valid bit. Both DDR channels report zero
outstanding/errors. Internal queue/root-cause attribution remains unproven.

These are measured **no-retirement stalls**, not completed numerical FAILs.
The e8_m8 latest retest says `not_started`, but its earlier measured stalled
scene above exists. Historical QEMU reference_512/1024 PASS is not FPGA
acceptance. Full paths, report hashes, ELF hashes, manifest bindings and
measurement fields are retained in [original_provenance.json](prepared01/original_provenance.json).

## Preserved Program And Oracle

Each ELF runs 3 seeds x 16 operations x 7 VLs x 4 setup masks x 4 starts =
5376 configurations, in original order. Capacities at VLEN=1024 are 512,
1024 and 512 respectively. VLs are `[0,1,2,3,cap/2,cap-1,cap]`; starts are
`[1,vl/2,vl (capped at 1023),cap-1]`. Setup mask bytes are ff/00/aa/24.
The original xorshift data generator and full scalar oracle are unchanged.

The archived assembly loads v8/v16 at full capacity with the original
SEW/LMUL, loads v0, selects VL with `tu,mu`, writes vstart, executes one of
vmand/vmnand/vmandn/vmxor/vmor/vmnor/vmorn/vmxnor with destination alias v8
or v16, reads vstart, restores full capacity and uses vsm.v to store the
destination. Target mask-logical instructions are **unmasked**: setup v0 is
not their predicate. No added hints or changed register assignments.

The original oracle checks all cap bits: exact active logical results,
preserved prestart/no-body bits, and the original allowed tail alternatives
(old, one, or full-width logical result). It checks returned vstart=0 and
the two original output guards. Old destination is the aliased source, not
the output-buffer 0x5b poison. This does not claim checks on every unused
buffer byte beyond the original oracle.

`port.py` reuses `integration/prepare.py` adaptation and the unchanged
startup/runtime/linker from `/tmp/current-board-integration-fast01/prepared`.
Only Linux entry/exit/write and TIOCOUTQ plumbing are adapted; each exact
diff is saved in `prepared01/prepared/<name>/adaptation.diff`. This is full
original-source math execution, not execution of the original Linux ELF
or preservation of Linux UART-drain timing.

## Measured Reference Results And Cost

| Suffix | Configurations | Spike result | Instructions to replay_exit | Spike wall time | SoC ELF bytes |
| --- | ---: | --- | ---: | ---: | ---: |
| e8_m4 | 5376 | PASS | 126731252 | 19.48 s | 9968 |
| e8_m8 | 5376 | PASS | 230149840 | 35.17 s | 9968 |
| e16_m8 | 5376 | PASS | 129147584 | 19.87 s | 9976 |

ISA is `rv64gcv_zvl1024b`; the existing nonzero-vstart Spike probe also
passed. Counters are Spike instructions/cycles, **not RTL cycle estimates**.
Each run requires the original 5376-case/zero-error marker, wrapper markers,
the historical printed tuple and successful exit. Full results, commands,
ELF/log hashes and counter output are in [reference](prepared01/reference/)
and [status.json](prepared01/status.json).

Host checking used an independent truth-table mock and independently
regenerated input/call-order digests. All three complete matrices passed
under each of three allowed tail policies (9 full host runs, not additional
unique architectural configurations). Six negative runs were rejected by
the original oracle: wrong active, prestart, no-body, forbidden tail, guard
and returned-vstart values. The mock is never linked into either target
ELF. See [host/status.json](prepared01/host/status.json).

Final read-only rehash found no mismatch in all 33 original/tool/helper pins,
prepared files, or three SoC ELFs. Initial identity-path preflight rejection
and its correction are preserved in [PREPARATION_HISTORY.md](PREPARATION_HISTORY.md).

## SoC Handoff

[soc/programs.json](prepared01/soc/programs.json) is the existing integration
runner interface; it pins the prepared provenance and these SoC ELFs:

| Suffix | SoC ELF SHA256 |
| --- | --- |
| e8_m4 | 81e5615ea0bca14d4693a5aa514a6ddd536db5f5c5c1601ab119cd419c092111 |
| e8_m8 | f87f57d13cdc4b1870614f31aedbbb1bc0a8a39bfe7b3c7364f1b6607be17cc5 |
| e16_m8 | 1165416578b586d60df56130874b03563b48685de7abcacccf0a659b27e00bd4 |

Preparation adapter (requires a fresh output directory):

```sh
python3 -B verification/fpga/current_board_review/mask_alias_original/port.py --out NEW_PREPARED_DIR
```

Future runner planning interface below deliberately omits `--execute`.
Choose the reviewed image and timeout separately; do not use the default
300-second budget for these full scalar-heavy matrices. Use an independent
service with an outer deadline greater than the inner budget for an authorized
long run. This command has **not** been run; no image was selected or pinned
by this software-only preparation task.

```sh
python3 -B verification/fpga/current_board_review/integration/run.py run \
  --image "$REVIEWED_IMAGE" \
  --programs verification/fpga/current_board_review/mask_alias_original/prepared01/soc \
  --out "$FRESH_OUTPUT" --jobs 1 --timeout "$REVIEWED_INNER_SECONDS" \
  --case rvv_masks_alias_restart_e8_m4 \
  --case rvv_masks_alias_restart_e8_m8 \
  --case rvv_masks_alias_restart_e16_m8
```

Explicit case names are required: these manifests intentionally have no
synthetic `all` program. The shared runner checks snapshot/image/compiled
sources, prepared provenance, ELF hashes and full oracle completion markers.
The next gap is actual DUT execution and its cost/disposition, not further
software reference generation. No claim closes the original board stalls.
