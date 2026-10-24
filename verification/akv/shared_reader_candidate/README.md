# Shared Reader Candidate

Isolated extraction candidate, not integrated into VLSU. Production RTL and the
reader algorithm are unchanged. One `qbs_read_engine` instance, two queued ranges
and two outstanding bursts, no new functional state, arbitration or pipeline.
The second reader in the unit TB is the independent untouched reference instance,
not part of the synthesizable candidate.

## API

`qbs_akv_shared_reader` parameters: `AxiDataWidth=128`, `AxiAddrWidth=64`,
`VAddrWidth=64`, `PAddrWidth=56`; packed types `req_t`, `rsp_t`, `axi_ar_t`,
`axi_r_t`, `exception_t`. Types must satisfy the supplied typedef macros in
`shared_reader_types.svh`; type parameters default to `logic` only as placeholders.

`client_req_i[2]` / `client_rsp_o[2]` are **unpacked arrays of packed records**.
Index 0 is QBS, index 1 AKV. `owner_i[1:0]` is externally supplied onehot-or-zero.
Only its selected request is presented to the reader; all other responses are
bitwise zero, including statistics, ready, and sticky fault metadata. Owner zero
disconnects both clients. Invalid multi-owner selects neither and is asserted.

Request fields (nine): `range_valid`, `range_vaddr[VAddrWidth]`, `range_bytes[16]`,
`range_tag[16]`, `range_cache` (`axi_pkg::cache_t`), `range_prot`
(`axi_pkg::prot_t`), `data_ready`, `completion_ready`, `fault_ready`.

Response fields: `range_ready`, `data_valid`, `data[AxiDataWidth]`,
`data_strb[AxiDataWidth/8]`, `data_offset[16]`, `data_tag[16]`,
`completion_valid`, `completion_tag[16]`, `fault_valid`, `fault_kind`
(`qbs_pkg::qbs_read_fault_e`), `fault_vaddr[VAddrWidth]`, `fault_tag[16]`,
`fault_mmu_exception` (`exception_t`), `busy`. Statistics are nine unsigned
32-bit fields: `range_count`, `translation_count`, `ar_count`, `r_beat_count`,
`payload_byte_count`, `store_wait_cycles`, `r_backpressure_cycles`,
`outstanding_occupancy_sum`, `outstanding_full_cycles`; plus 2-bit `outstanding_max`.
The tag is opaque; AKV must zero-extend its 8-bit tag, QBS keeps all 16 bits.

`command_fire_i[1:0]` clears the reader counters on OR of accepted commands,
including when owner is still zero. Fire must be exclusive, reader fully idle,
and owner either zero or the firing client; do not offer a range on that edge.
Owner may become active on the following cycle. Keep it stable through all live
work, held AR, response drain, completion and fault consumption. Only release
when idle. Simulation-only admission assertions clear on owner release, with
simultaneous new fire taking priority; reacquisition requires a new fire.
These assertions strengthen external-controller contracts, not functional state.
Do not switch directly between owners without a new compatible acceptance.

Common ports exactly retain original reader naming and semantics:
`core_st_pending_i`, `en_ld_st_translation_i`; `mmu_req_o`, `mmu_vaddr_o`,
`mmu_is_store_o`, `mmu_valid_i`, `mmu_paddr_i`, `mmu_exception_valid_i`,
`mmu_exception_i`; `physical_check_valid_o`, `physical_check_addr_o`,
`physical_check_bytes_o[13]`, `physical_range_allowed_i`; `axi_ar_o`,
`axi_ar_valid_o`, `axi_ar_ready_i`, `axi_r_i`, `axi_r_valid_i`, `axi_r_ready_o`.
No clock gating is introduced: caller supplies `clk_i` and active-low `rst_ni`.
Future integration must keep that clock live for either owner, command acceptance,
and pending/draining transactions. No production probe paths are migrated here.

## Unit Evidence

Run from the signoff root, with VCS in PATH and a fresh output directory:

```sh
python3 verification/akv/shared_reader_candidate/run_unit.py \
  --output verification/out/qbs-akv-shared-reader-unit-20261024-01
```

The driver expands the existing QBS Makefile RTL source graph without building
its targets, compiles in the fresh directory, and pins sources/includes/tool,
commands, simulator and logs. Compilation is bounded to 600s, each unit to 120s.
All testbench waits have a 100us simulation watchdog. No SoC is built or run.

The TB compares every common output and the selected complete response at every
active clock edge, including invalid-cycle values, counters, busy and sticky
fault fields. Unselected endpoints are poisoned, responses must stay all-zero.
An independent byte/tag/offset/completion scoreboard checks payload contents.
Ten commands cover high QBS tags, zero-extended AKV tags, translation and bypass,
unaligned page crossing, two outstanding bursts, store/MMU/data/completion stalls,
AXI/MMU/PMA faults, held AR drain, alternating-client recovery without reader reset,
and ten owner-zero counter clears. Separate negative runs require exact rejection
of owner changes while busy, fire while busy, and readmission without new fire.

This is finite-stimulus cycle comparison, not formal equivalence, resident-context
proof, synthesis/PPA or whole-SoC validation. AXI memory and translation are mocks.
No claim is made about VLSU owner/drain integration or production clock enables.
