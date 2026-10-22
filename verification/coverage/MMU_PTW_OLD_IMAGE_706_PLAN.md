# Old-Image MMU/PTW Plan Correction

This supersedes the PMP-deny proposal in GAP97_CSR_LARGE_AVL.md. That file is
historical/frozen; it must not be treated as permission to launch that proposal.
No RTL edit, simulator run, coverage exclusion, or admission is authorized here.

## Final Configuration: Zero PMP

`hardware/src/ara_soc.sv:545` sets `cfg.NrPMPEntries = 0` in
gen_usr_cva6_config. The SoC override is authoritative, not a base package's
default of eight entries. `hardware/deps/cva6/core/pmp/src/pmp.sv:73` consequently
assigns allow_o=1. The PTW checks this allow signal for its S-mode READ accesses.

Current copies were individually compared with the historical build manifest:

| Source | Matching frozen SHA256 |
| --- | --- |
| hardware/src/ara_soc.sv | 41268269246a564bec870bab1a45bdb260786ffa95d2f50cb912cc61792d3e62 |
| hardware/deps/cva6/core/pmp/src/pmp.sv | 9c2dce5d4bd2390a617882c282080dbf191c54f016b36b5e719672382c15c7b6 |
| hardware/deps/cva6/core/cva6_mmu/cva6_ptw.sv | 82dab3584098056cff37c18e3070875b0b71ba185e90fd878151fc197c0d9505 |
| hardware/deps/cva6/core/cva6_mmu/cva6_mmu.sv | 4859d957d56541c27928e347cee7ef800486cf3b1ad91aa53a9e3e044344c480 |

Independent existing audit: `verification/tests/build_gap47_sv39_indexed_pmp0.py`,
baseline_audit and the config-audit generation at lines183..198. It also records
that the DUT's zero-valued implemented PMP CSR behavior differs from Spike's
absent PMP CSR accessors. Neither model supplies operative deny regions.

Therefore DO NOT execute a PMP-deny case on this image. It would not produce
the planned fault. PTW PROPAGATE_ACCESS_ERROR state/entry/exit and bad_paddr
true selection are configuration-proof review candidates, not software targets.
No native exclusion is inferred or approved by this note.

## Small Legal Condition Case for Review

Use latest admitted706 bitmap:
`verification/out/gap97-offline-admitted-706-20261006-01/combined-bits.json`, SHA
`9aef93246352ac70f4df1446e17580497832c26f51d3099608bcd2470f9fa626`.

Propose a separate bounded S/Sv39 fixture with a normal successful translated
load as control, followed by an aligned load and instruction jump to the
noncanonical VA `1 << 39`. Mixed bits63:38 fail Sv39 canonicality. Use a
private M-mode handler, explicitly recorded expected fault sites, and a bounded
recovery path. This uses legal instruction encodings with intentional checked
page faults, not illegal requests or injected bus errors.

In scope `ara_tb.dut.i_ara_soc.i_system.i_ariane.ex_stage_i.lsu_i.gen_mmu.i_cva6_mmu`:

| Action | Source | Candidate raw condition offsets still zero on706 |
| --- | --- | --- |
| Translated noncanonical data load | cva6_mmu.sv:524 | 57 (canonical OR vector00), 60 (req/translation/invalid vector111) |
| Noncanonical translated fetch | cva6_mmu.sv:382 | 30 (canonical OR vector00), 33 (fetch_req/invalid vector11) |

Expected data fault is mcause13 with mepc at the load and mtval=bad VA. Expected
fetch fault is mcause12 with mepc/mtval at the bad target; recovery must replace
mepc with a known executable continuation. These expectations require review of
the complete exception-priority path, frontend VA propagation, and the existing
Sv39 setup/handler before implementation. Restore SATP/status/trap/vector state,
verify exact control data and exactly the planned two traps. Ordinary zero-trap
GAP97 admission cannot be reused unchanged for this intentional-fault fixture.

These are predictions, not measured hits. Do not target idle/noncanonical
MC/DC combinations by unsafe untranslated physical accesses. Unary monitored
condition rows need their own semantic mapping rather than assuming output bits.

## FSM Boundary

No new PTW FSM gain is promised. Normal PTE/page-permission faults already have
historical coverage. The source flush override at cva6_ptw.sv:604..610 selects
WAIT_RVALID or LATENCY, not direct IDLE. A future cold-walk/legitimate-pipeline-
flush case must first reconstruct the core flush producer and show a reachable
overlap; it cannot be justified by merely issuing more sfence instructions.
Keep such timing hypotheses HOLD until that path is established. Never change
AXI delay, RTL, configuration, or timeout to manufacture a state transition.
