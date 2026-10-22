# Boxed mf4 Sole Identity Rebuild

Decision: `ELF_MISMATCH_FROM_LATER_TEMPLATE_STOP_NO_RETRY`.

Exactly one fixed Linux GCC compile was performed. Actual child PID 3780974,
`Popen.wait()` return code 0, elapsed 2.003841463010758 seconds; no timeout and
no retry. The orchestration command also exited 0: this means the experiment
and mismatch recording completed, not that identity passed. The numeric child
receipt was durably saved in `compile_execution.json` before ELF comparison.

## Inputs and Identity

- Unchanged later C: `03cc50313dee7cda6476658bbe025409617242c06cd06cdaff8d83d2812e9bad`.
- Original ELF: `bef54674b16fdeefdb37295d035b1b9a58cd446cd54662078aa24e83cced7b2d`.
- Rebuilt ELF: `673d58fc8c83581bae8b5ee008a4c9a41403982c84c67dd830639aca6d4723bb`.
- Original boxed mf4 assembly and e16 fixtures/operations were used, with
  SEW16, UNBOXED0, UNMASKED1, RESTART0, DK0. No source or compiler flags were
  adjusted after compilation.
- `command.json` preserves the full invocation and fixed baseline recipe;
  `compiler.json` pins the Linux GCC wrapper and real driver. All recorded
  input pins matched before and after the compile.

## Actual Difference

Original size 15648 bytes; rebuilt size 15656 bytes. There are 2749 differing
bytes in the common span; the first difference is at file offset 40. This
count includes shifted content and is not an instruction-change count.

The original `.text` is 1792 bytes, rebuilt `.text` 1794 bytes, at the same
file offset 288 and address 65824. Their payload hashes differ. Therefore the
failure is not confined to ELF headers or non-code metadata. `.comment`
payloads match and `.bss` address/size/alignment match. Full per-section
metadata/hashes and first byte differences are retained in
`section_comparison.json` and `byte_difference.json`.

The tested hypothesis that the later disabled branches fold to the exact
historical ELF is disproved for this fixed recipe. This experiment alone does
not identify the precise historical C change or prove a behavioral difference;
no new source/flag hypothesis was compiled.

## Scope and Receipts

Historical C remains `NOT_RECOVERED`, expected SHA
`9060f2931a5a2b6b51e3ff7be14ce420efaeb5c34800e496dad95dd78fc89dcf`.
Neither original provenance nor sealed artifacts were changed. No Host,
Spike, DUT, RTL change, or additional compile was performed. This experiment
does not close the boxed parent, replace alias17920, or change arithmetic
18/22 accounting.

- Command SHA: `2bc68f984d478fd0198a173224c0edddfadb484dcf19a711d17d8ce49f505b2e`.
- Input-pins SHA: `49af6f9394c2161e6003bd88a5a3bdaa6b108ceebf0febbf1d139bd0c4266899`.
- Actual compile receipt SHA: `531e0c06c9f2e3f8ac1944c78204a80104e4e545dba8f93a73c09067d0f20bd9`.
- Section comparison SHA: `ebb587a0b057828ca31f81196b66cc6801c3f86d66ba9221bb75d5b2743e2336`.
- Byte difference SHA: `d2904cda08f960892b2de2136efb4c69cd043945f0a05015e371a7937addffe5`.

Stopped after the sole authorized identity experiment.
