# FPGA accelerated ELF and signature replay plan

This is an offline execution handoff, not a board runner. No ELF was executed
or rebuilt here. Runner completion/signature acceptance belongs to the main
runner owner; this document does not replace or relax those gates.

## Actual built verification artifact

Selected file: `apps/bin/rv64uv-ara-vfredmax_boundary`, 15,488 bytes, SHA-256
`98a007e64cb2187bc077b6798a0cc583b6340acf309fb90f451fcd9c400648a5`.
This is a real built RV64 little-endian executable, not a future filename.
The exact hash is also in
`verification/out/dependency-baseline-vcs-20260922/provenance/elf.sha256`;
that run's `summary.json` records the corresponding VCS case passing.

`reports/vfredmax-boundary-readelf.txt` captures the ELF metadata. Entry is
`0x80000000`; PT_LOAD physical ranges are:

| Start | Memory/file bytes | Permissions |
| --- | --- | --- |
| `0x80000000` | `0x11f4` | RX |
| `0x80001200` | `0x520` | R |
| `0x80001720` | `0x1078` | RW |

All segments fit DDR, but that is **not sufficient** for board execution.
The paired disassembly `apps/bin/rv64uv-ara-vfredmax_boundary.dump` has hash
`a5808f068dc276b19e877f24eca5715c4868cf2f8bd590bdf6733cf3609f49fa`:

- At `0x80000044..0x8000004c`, startup loads SP through the simulation
  `dram_end_address_reg` at `0xd0000010`.
- `_eoc` at `0x800000e4` writes its result to simulation EOC `0xd0000000`;
  the serial implementation targets simulation `fake_uart=0xc0000000`.
- VCU118 does not implement these locations as the simulation control block.
  They fall in its DDR address range, where the expected register behavior is
  absent. A successful UART load would not make these accesses meaningful.
- The executable is stripped: no symbol table or `begin_signature`/
  `end_signature` pair was reported. The dump labels `Ru32=0x80001780` and
  `num_failed=0x80002780`, but it is not a portable signature manifest.

The test source checks two FP32 max reductions (VL=4 then VL=1); both expected
scalar result words are `0x41700000`. The second overwrites the result buffer.
Reading that final word alone cannot prove the first comparison ran or passed,
and reading a zero failure count alone cannot prove completion.

### Necessary preparation, not performed

1. Preserve this exact ELF, source and dump identities as the simulation
   baseline. Do not relabel it as board-compatible or rebuild over `apps/bin`.
2. In a separate approved build directory, derive a board artifact from the
   same test and existing `ARA_FPGA` runtime. `apps/Makefile` selects this via
   `fpga=1`; `apps/common/crt0.S` supplies DDR SP, trap setup and M-mode entry,
   and `serial.c` supplies Cheshire UART. Force fresh runtime objects: changing
   a make variable alone is not evidence that cached objects were recompiled.
3. Add a bounded signature/completion record in that future harness: schema,
   unique run nonce, test identity, two separate actual/expected FP32 words,
   comparison count=2, failure count=0, trap/cause information and completion
   state published last after memory ordering. Record its address/size from the
   actual linked ELF, not the old stripped dump. Preserve an unstripped ELF/map,
   compiler flags and complete build inputs. Expected bytes and comparison
   policy must be fixed before the board run, never copied from board output.
4. Establish golden signatures in the applicable reference environment using
   that harness; if startup is board-specific, use a shared test body with
   explicit environment adapters and record both identities. Do not claim
   byte-identical ELFs across different runtimes or unchanged ISA coverage.
5. Only after board/bitstream approval, replay the built, hashed artifact with
   bounded elapsed time. The board bootloader supports READ/WRITE only while
   waiting for EXEC. `uart_load.py` reads back **load data before EXEC**, then
   merely collects UART. It has no post-execution memory-signature retrieval.
   Therefore choose and implement a framed signature-over-UART harness or an
   explicitly approved halt/read-debug path first. Resetting and hoping DDR
   survives is not an established result retrieval protocol.
6. Require one matching completion nonce, all signature bytes, zero traps and
   comparison failures, and matching ELF/reference/bitstream/export identities.
   Timeout, early EOF, duplicate/stale result or truncated data is incomplete,
   never PASS. Preserve raw serial/debug bytes and parsed results. Expand to
   a prebuilt ELF queue only once this single case closes the protocol gate.

These are concrete missing runtime/transport steps. This audit intentionally
does not produce a fake signature file or a command that would load the
simulation binary as though it already met the board contract.

## Existing board-targeted real-data replay

`hardware/fpga/ara_dsa_vcu118/software/qwen_small_combined/qbs_akv.elf` is
2,044,336 bytes, SHA-256
`ab3421bf6b3e422f64cd516dea40e64a138f0a4f72b68b8e281c1c36574c5b6e`.
The adjacent case hash is
`3d50792fc9825e9524716f93f1741ac72a0a97146a8c7686e9f0793fb1955aec`;
provenance hash is
`e3a7732ece6fc70c191a13333b16ac727c11f39a8aad2ffe55c8ee8b0da27a12`.
`reports/qbs-akv-readelf.txt` records its entry `0x80000000`, four DDR load
segments, and final load end `0x801f1618`. It too is stripped. These observations
identify a candidate artifact; they do not independently attest its build or
golden tensors. The original external capture directory was not accessed.

Its packaged case is a real llama.cpp Qwen2.5-1.5B Q4_K_M capture: layer-0
Q4_K projection, K=1536, 32 rows, one input; then AKV-v2 decode attention,
dim=128, one token, 12 query heads, two KV heads, physical KV capacity=256.
Inputs and golden tensors are embedded in the ELF and thereby covered by its
hash, though an independent tensor/source provenance chain remains necessary.

Future board replay should freeze that ELF/case/provenance together, establish
matching capabilities and boot baud, and record load readback or equivalent
transfer evidence. The packaged `run_qwen_small_combined.ps1` hardcodes 115200
and uses `--no-readback`; it is not a verified high-speed or signature protocol.
Do not run it until the owner confirms the board and artifact pairing.

Its existing `summarize_qwen_combined.py` consumes QBS, `LLAMA_OPERATOR`, native
dispatch and `QBS_AKV_COMBINED` records. Necessary numerical evidence includes
zero mismatches for both operators, both statuses zero, `native_v2=1`,
`attention_mode=akv_v2`, and consistent component/total cycles. Freeze the
expected case identities too; bind logs to this run instead of trusting the
last PASS line. Those records are self-check results, **not** a full vector
architectural signature. Full signature replay still needs the harness above.

This bare-metal numerical check is separate from Linux QBS/AKV compute and
hidden context isolation. First close the shared DDR/MMU/cache and OS ownership
gates in [READINESS.md](READINESS.md), then validate Linux real-data computation
and incorporate reproducible kernels into llama.cpp/GGML with shape/type/
capability selection and standard RVV fallback. No complete-model throughput
or Linux custom-runtime claim follows from this candidate ELF.
