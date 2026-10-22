# Same-Image Kallsyms Recovery

2026-10-14. Static binary recovery only; no OS, board, QEMU, simulation,
compilation, RTL edit, or access to the current board. Existing inputs and
earlier reports remain unchanged. No third-party tool was downloaded.

## Result

Recovered **52,248 symbols from the actual archived Image**. This resolves
the function-level symbol gap for the historical PCs, without substituting
the mismatching current vmlinux. It does not recover DWARF/source line numbers,
all data symbols, ELF section/debug metadata, or a runtime state dump.

Image:
/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/source/Image

SHA256: 716aef49389b25a0a3f4deac47de0bb69467a10f1057041cecd0f0621fbbf285.

| Historical PC | Recovered same-Image symbol | Actual instruction |
| --- | --- | --- |
| 0xffffffff80013a16 | save_v_state+0x17e | 97ba: add a5,a5,a4 |
| 0xffffffff80013a18 | save_v_state+0x180 | 00802573: csrr a0,vstart |
| 0xffffffff80b8754e | fallback_scalar_usercopy_sum_enabled+0x66 | 03c53823: sd t3,48(a0) |
| 0xffffffff80b8759e | fallback_scalar_usercopy_sum_enabled+0xb6 | 00f50023: sb a5,0(a0) |

save_v_state starts0xffffffff80013898; the next kallsyms symbol is
__riscv_sys_rt_sigreturn at0xffffffff80013b3c. The usercopy fallback starts
0xffffffff80b874e8; next is __clear_user at0xffffffff80b875b4.
These are actual sorted kallsyms address intervals, not invented ELF function
sizes. The save sequence reads vstart, vtype and vl before storing them.

The two kernel traps now have explicit scalar usercopy attribution. This does
not identify the copied task/frame, prove that the earlier trap caused the
stall, prove CSR acceptance, or establish which hardware owner failed to drain.
Head validity remains missing. NF8's extra41 errors remain unlocalized.

## Format and Primary Sources

Linux scripts/extract-ikconfig successfully extracted the original embedded
configuration. SHA5321c8c739fdb06a76db8ee6a8bdf0a2d31804ac63ae2421feb36acadba1faf5
matches the historical accepted_image.config identity:

- CONFIG_KALLSYMS=y.
- CONFIG_KALLSYMS_ALL is not set.
- CONFIG_64BIT=y; CONFIG_RELOCATABLE and CONFIG_RANDOMIZE_BASE are not set.

file reports a RISC-V PE32+ EFI application. The Linux RISC-V Image header
magic is independently present at offset48; EFI wrapping does not make it an
ELF with a recoverable original symtab. extract-vmlinux is not a raw-kallsyms
decoder, and scripts/kallsyms is a symbol-map encoder, not this inverse tool.

The narrow owned extractor follows only existing Linux primary implementation:
/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/build/linux-6.19.6/

- scripts/kallsyms.c: output layout, token index, 32-bit relative offsets,
  count, marker every256 symbols, big-endian three-byte lexical sequence index.
- kernel/kallsyms.c: one/two-byte compressed-name length and token expansion;
  the first expanded character is symbol type.
- kernel/kallsyms_internal.h: table types.
- scripts/extract-ikconfig: original embedded config extraction.

Those files are used as format specifications only, not proof that this local
tree built the archived Image. All are pinned in result.json. Disassembly uses
the existing Buildroot RISC-V objdump in raw-binary mode on the original Image,
with its archived fixed virtual base0xffffffff80000000. No mismatching
vmlinux symbol/address list is read by the extractor.

## Full Structural Validation

Discovery found one exact256-token string/index-table match among digit-token
anchor candidates. The final extractor is deliberately restricted to this
Image SHA and these offsets; it is not a generic heuristic recovery tool.

| Structure | File offset |
| --- | --- |
| kallsyms_num_syms | 0x11832b0 |
| kallsyms_names | 0x11832b8 |
| kallsyms_markers | 0x12274f0 |
| kallsyms_token_table | 0x1227828 |
| kallsyms_token_index | 0x1227ba0 |
| kallsyms_offsets | 0x1227da0 |
| kallsyms_relative_base | 0x125ae00 |
| kallsyms_seqs_of_names | 0x125ae08 |

All52,248 names decode, all205 markers equal recomputed name-stream offsets,
all256 token indexes match packed strings, alignment boundaries agree, and
all addresses sort correctly. The lexical sequence table is a full permutation
of0..52247 and sorts all decoded names exactly. Relative base is
0xffffffff80002000, matching recovered _text/_stext anchors. Historical PC
bytes are checked explicitly against the same Image before attribution.

CONFIG_KALLSYMS_ALL=n still retains __start_/__stop_ section boundaries in
scripts/kallsyms.c. An initial extractor attempt rejected these legitimate
R/D entries and exited1 before creating output01. The corrected rule accepts
R/D only for those explicit boundary names, rather than ignoring unknown types.
Final type counts observed during static inspection: t25997,T25935,W259,R31,D26.
The corrected final invocation exited0; this is a parser correction, not any
change to Image/config or target data. No kernel/reference run occurred.

## Artifacts and Execution

Executed from /home/wangwy/openproject/ara_dsa_signoff_integration:

```sh
python3 -B verification/fpga/current_board_review/masked_translation/original_image_kallsyms_recovery01/extract.py
```

Actual final tool process exit0, session46985. Output creation is exclusive;
do not rerun over output01. This report records observed tool execution, not
a fabricated independent child-wait receipt. Input hashes were checked before
and after final extraction. Focused objdump/config subprocesses exited0 with
30-second bounds. No full kernel execution was involved.

- extract.py SHA: a3dff95562395fa7a5b35b49ae10468cdc9e69e40f7e301c4c29d651da296320.
- output01/result.json SHA: 24e6887075a9f5306875879c18c2748b7805a2e5a3bdf69032837889a8c6bb05.
- output01/System.map.recovered SHA: 0de6ffa184888ea95ede077bbfa8aa26030466e99061e682f029306214ad9b0e.
- output01/pc_windows.txt SHA: 834060dae96a032fd75e0a482799adcdb72b7d7e31d75fdd5c4c4a7405ce2940.

The output is a reconstructed kallsyms map, not a byte-identical original
System.map or vmlinux. Function-level historical PC attribution is now
available. Matching source/DWARF and live task/PTE/frame/owner state remain
separate gaps. Nothing here authorizes or requires a new Linux/board run.
