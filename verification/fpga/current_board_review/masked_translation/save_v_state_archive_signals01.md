# Historical CSR-wait signal availability

Verdict: ARCHIVE_SIGNAL_GAP. No new discrimination between H0-H4.
This follows `save_v_state_csr_static01.md`; it does not change its hypotheses
or close the original Linux symptoms. No board/network connection, simulation,
Linux execution, symbol recovery rerun or original artifact modification.

## Search boundary and actual artifacts

Only `/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01` (C) and its recovery
subdirectories were searched. This is not a claim about remote archives or all
possible files on the host.

Recursive `find` found no regular files matching `*ila*`, `*capture*`, `*.ltx`,
`*.vcd`, `*.wdb`, `*.zip`, or `*.tar*`. No archived `host_transport.py`,
`host_vivado.tcl`, `fpga_debug.h`, `*debug*.sv` or `*telemetry*.sv` was found.
The only three symlinks found were unrelated simulation csrc shared libraries;
they were not followed. Source/text search over py/tcl/sv/md found no
`get_hw_ilas|write_hw_ila|probe[0-9]|probes_file|head_pc_i|debug-v1` matches.
CSV filename inventory is dominated by `snapshot.csv`; the target six CSVs
were parsed explicitly rather than assuming they were waveform captures.

Target artifacts are:
`C/rvv_recovery08_{12,41,76}/terminal_scene/batch_progress_{0001,0002}/`
with `snapshot.json`, `snapshot.csv`, `report.json` in each directory.
The scene also retains report/state/console/UART/ELF/identity evidence, but no
additional capture/probe path was found in its console.log or state.json.

All six collection reports explicitly say command `snapshot`, state
`snapshot_collected_not_execution_verification`, passed=false. They identify
JTAG debug cell `gen_host.i_host_bridge.i_jtag_debug` and reference:

`D:\fpga_runs\ara_dual_bitgen_20261006_01\bitstream\ara_dsa_vcu118.ltx`

That is evidence of a configured external probe-file path, NOT evidence that
an ILA trace was captured or that the LTX contains these internal signals.
The file itself is absent from the searched local archive. No remote access
was attempted. Reports pin host_vivado.tcl as
`8a8af0c2c994d6acc20570dc3f3087f6ebfb7bd890dcac2634d6f585ddc5e8c9`
and fpga_debug.h as
`eb12cfc1d9790f247cc1cdfe6c86acb908a503f479b3071256f9b2dfdb6e6054`;
hash references are not the missing implementation or probe definitions.

## Minimum signal availability

| Required evidence | Actually present | Missing / consequence |
|---|---|---|
| CPU head and retirement | head_pc, last_pc, retired, cycles | Head presence/completion/FU/ID and commit ACK absent; H0 remains open |
| Trap context | last_trap_pc/cause/tval, cumulative trap_count | No event timeline, task/frame or correlation to a pending owner |
| CPU accelerator queue and spill | None | Queue head/empty, ready/pending authorization, flush-unissued, spill handshake absent |
| CSR request and response | None | Instruction/ID/valid/ready/result/exception absent; cannot separate H0 from H4 |
| Dispatcher gates | None | state_q/state_qq, backend valid/ready, idle absent; H1 versus H3 unresolved |
| PE ownership/completion | None | PE-by-ID running/done, original owner/op, address ACK and consumer acceptance absent |
| Exception flush | None | FSM state/start/output/done absent; H1 versus H2 unresolved |
| External memory monitor | Both DDR counters, outstanding, stalls, last addresses and errors | Not a substitute for internal PE ownership or translation/flush state |
| Software mailbox/watchdog | 16 mailbox words all zero; live.flags=0, watchdog_snapshot=false | No encoded internal-state dump; no watchdog-triggered capture |
| Probe definitions | Snapshot semantic descriptions and historical LTX/host hashes | No actual LTX or debug implementation in this search scope |

The six CSVs each contain exactly one data row and 75 fields. A Python
csv.DictReader/json comparison asserted every CSV field equals its JSON
counterpart (including mailbox words); actual command exit0. CSVs add no
unexposed signals. Snapshot schema is `ara-fpga-debug-v1`, ABI1, caps3.
The capability number is not decoded into an invented ILA capability.

## New bounded observations

| Recovery | Cycle increase | Retired/trap-count increase | Both DDR records |
|---|---:|---:|---|
| 12 | 572408693 | 0 / 0 | Every field unchanged |
| 41 | 583474970 | 0 / 0 | Every field unchanged |
| 76 | 554341885 | 0 / 0 | Every field unchanged |

All six report last_pc=ffffffff80013a16, head_pc=ffffffff80013a18.
DDR read/write outstanding and errors are zero at both endpoints. This
supports a persistent no-retirement interval without observed monitor progress;
it does not establish that no internal activity occurred between samples or
prove which CSR gate blocked. Counter wrap/monitor coverage are not expanded
into stronger claims. No H0-H4 branch can be selected from these fields.
The prior static response-ready=1 exclusion remains a source result, not a
new measured CSR-response event.

Snapshot JSON SHA256, in recovery/sequence order:

```text
12/1 8c5c501e25d820212097e25966a9eacb34beea3467389ef23a5c2e9d206889d9
12/2 c5eb5c7711ff09f45347b6d9c22da51b9c2994c828e53687ce9d548e33684eb0
41/1 c7a81a2c2ba23cbf535047a78a18520248144b637323c0c1eec1aa25958680d2
41/2 bb50aea3de54b042ed30cf48c266cdda4c12949af89521429d295a3779db6a88
76/1 32a1b13737f949e2e8ce05c5c95947a9eb26a5a4c36f4c0b5b0a8db3e87e5cdf
76/2 bf4f79248d19551419050d1852dece6a852c5680f8fa0f7d3ff6df32c3684013
```

## Safe disposition

The authorized local archive search is complete. The useful next input would
be an already existing remote capture export plus its exact LTX and capture
metadata, if the archive owner has one. Retrieving an old file is distinct
from taking a new capture; neither was attempted here. LTX alone would resolve
probe definitions, not historical values. If no such capture exists, the
original episodes remain causally unresolved, and repeating these telemetry
snapshots or the already accepted Sv39 tests would not fill the signal gap.
