# J10 Ethernet-to-DDR loader: implementation status

## Scope guard

This work has one acceptance target: transfer an ELF's DDR1 segments and
additional binary data over J10, verify physical DDR readback, and stop
without launching Ara. MicroBlaze, AXI DMA, lwIP raw callbacks, timer/IRQ
and local BRAM are implementation dependencies, not additional products.
Do not add FreeRTOS, Linux services, PCIe, automatic boot, an Ara RTL
connection or a general-purpose network stack to this milestone. The
isolated image must pass a linked-memory-layout review, then routed
timing/DRC/CDC review, then controlled board transfer and throughput tests
before claiming success.

## Current CDMA fast-path checkpoint

Ara integration preparation is documented in `ARA_INTEGRATION.md`. The offline
`prepare_ara_integration.py` validates the proposed reserved ranges and creates
a source snapshot; it does not connect hardware or authorize launch.

### Large-file board acceptance (2026-09-26)

Two consecutive transfers of the same 256 MiB random file plus smoke ELF/BSS
passed, with full per-packet physical DDR readback and host byte comparison.
Each run transferred 268,440,256 payload bytes, targeting the raw data at
`0x90000FF8`. Run 1 took 26.926931 s (9.969211 MB/s); run 2 took 26.982833 s
(9.948557 MB/s). Both DATA and control retries were zero in both runs. The
combined transfer was 536,880,512 bytes; throughput stayed near 10 MB/s over
these approximately 54 seconds of transfer.

Evidence: `D:/fpga_host_runs/eth_large_20260926_223313_043`, containing
`manifest.json`, both `run*/report.json`, `profile_after.txt` and
`xsct_large_spotcheck.txt`. Payload SHA256:
`29d6f88d62fd1980d77754e73c1d840528ae39cb5e4e7e9039eb4cae37bf2182`.
Independent XSCT reads at `0x90000FF8`, `0x98000FF8`, and `0xA0000FF4` matched
source words 795951918, 2240494505 and 2045594196. Stage remained 8; CDMA
errors/timeouts, TX drops and bad frames remained zero. The rejection counter
stayed at its pre-test value 3 from the intentional earlier protocol tests.
The DDR byte counter increased by exactly 536,880,512. Cumulative callback
timer ticks wrap at 32 bits across this test and are not interpreted as a
nonwrapping elapsed-time total. No firmware or bitstream change was required.

### Board restart and BRAM control optimization (2026-09-26)

After the board power cycle, the matching `loader_cdma.bit/.ltx` was programmed
again and the standalone firmware downloaded with XSCT. A 16 MiB random
payload plus smoke ELF/BSS passed physical DDR readback in 1.969 s (8.521 MB/s).
The firmware now measures successful callback, transmit and CDMA time with
timer 1 at 100 MHz. Counters accumulate modulo 2^32; take deltas over bounded
transfers. Callback timing includes nested CDMA/transmit time and interrupt
preemption, so these counters are not mutually exclusive CPU profiles.

Static inspection showed repeated uncached DDR accesses to packet headers and
CPU-only control objects. The bounded Ethernet/IPv4/UDP/loader header is now
read into a 104-byte aligned local stack buffer, processed in BRAM, and the
reflected network header written back. Payload data stays in DMA-accessible
DDR. `cdma` and `load_state` use the linker's BRAM `.data` section; the build
checks their symbol addresses are below `0x80000`. This preserves range,
session, completion, duplicate and retransmission behavior.

| Same random image, window 8 | Seconds | MB/s |
| --- | ---: | ---: |
| Restarted image with profiling | 1.969 | 8.521 |
| Local packet-header processing | 1.802 | 9.314 |
| Local headers plus BRAM control objects | 1.668 | 10.063 |
| Final repeat after protocol guard tests | 1.667 | 10.066 |

The final run transferred 16,782,016 bytes with zero retransmissions, improving
about 15% over the previous 8.747 MB/s checkpoint. Successful CDMA calls total
24,326: their cumulative elapsed time fell from 0.2502 s to 0.1192 s.
Transmit time was 0.7251 s; callback time was 1.5256 s. Network driver and
packet processing remain substantial costs; this is not line-rate throughput.

Evidence is in `D:/fpga_host_runs/eth_profile_20260926_222334_222`,
`eth_header_bram_20260926_222520_321`, and
`eth_control_bram_20260926_222649_269` under the same parent directory.
The final repeat is `eth_control_repeat_20260926_222907_342`.
The last two include independent XSCT spot checks. Final stage is 8; CDMA
errors/timeouts, TX drops and bad frames were all zero. ELF first instruction,
BSS zero words and random payload first/middle/last words match the values
below. The board protocol guard test subsequently passed all five checks,
including an injected early packet loss requiring one retransmission.
The 18 existing Python sender regressions passed; the firmware compiled with
`-Wall -Wextra -Werror`. The routed bitstream is unchanged from the accepted
CDMA checkpoint, so its existing timing/DRC evidence applies.

`loader_fast_profile.tcl ELF tcp:localhost:3121` resolves counter addresses
from the matching ELF with `mb-nm` before read-only XSCT inspection. Use this
instead of old hard-coded addresses after changing firmware layout. The board
is left running the updated isolated Ethernet loader; Ara handoff remains a
separate integration milestone.

The board now runs the isolated CDMA loader, not Ara and not the older TCP
firmware. The new path reuses AXI Ethernet, scatter/gather AXI DMA, lwIP's
vendor driver and DDR4; AXI CDMA 4.1 replaces the CPU's DDR payload copies.
CDMA uses a 64-bit master, simple mode, burst length 32 and DRE enabled for
unaligned UDP buffers and destination addresses. The PC uses ordinary Python
UDP sockets; Npcap and Scapy are not dependencies of this loader.

Each DATA packet is copied from the received DDR buffer to its protected
destination, then copied back by CDMA and returned to the PC for an exact byte
comparison. A 20-byte session/sequence header and 1380-byte data chunks support
bounded retries, duplicates and a receive window. BEGIN/END validate segment
range and completeness. Destination writes exclude reserved DDR
`[0xFF000000, 0x100000000)`; the PC checks every segment before transmitting.
Source DMA buffers may use that reserved area. No command launches Ara.
Use this unauthenticated diagnostic service only on the controlled wired LAN.

Measured payload rates use decimal MB/s and include physical DDR readback:

| Transfer | Bytes | Seconds | MB/s |
| --- | ---: | ---: | ---: |
| Old CPU UDP DDR roundtrip, window 8 | 4,194,304 | 3.515 | 1.193 |
| CDMA UDP DDR roundtrip, window 8 | 4,194,304 | 0.493 | 8.511 |
| Actual smoke ELF/BSS + four 1 MiB segments | 4,199,104 | 0.489 | 8.589 |
| Actual smoke ELF/BSS + sixteen 1 MiB segments | 16,782,016 | 1.940 | 8.652 |
| Actual smoke ELF/BSS + random 16 MiB payload | 16,782,016 | 1.914 | 8.766 |
| Same random image after retry-window correction | 16,782,016 | 1.919 | 8.747 |

All these board transfers completed without retransmissions. The random-image
rate is about 10.3 times the previously measured 0.850 MB/s TCP loader, not a
gigabit line-rate result or a promised Ara-integrated speed. The Windows wired
NIC at `192.168.1.11` reports 1 Gbps. Increasing the old reflection-only window
from 8 to 32 did not help: the 16 MiB window-32 run measured 9.367 MB/s, versus
the earlier approximately 11.9 MB/s window-8 reflection result. Reflection
alone does not write DDR and must not be presented as loading throughput.

Acceptance evidence:

- Build: `D:/fpga_runs/ara_loader_bd_cdma_02`; programmed files are
  `loader_cdma.bit` and `loader_cdma.ltx`. Routed WNS +0.282 ns, WHS +0.010 ns,
  WPWS +0.005 ns; bad routes and DRC Errors are zero. All 22 detailed bus-skew
  checks are MET, with worst slack +3.209 ns. `loader_bd_route.tcl` now emits
  the skew report and bitgen rejects missing/nonpassing skew evidence.
- Firmware: `D:/fpga_runs/ara_loader_bsp_cdma_01/loader_app/fast_probe_cdma/fast_probe.elf`,
  built with `-Werror`. Text/data/stack/heap fit in local BRAM; BSS and DMA
  buffers remain in reserved top DDR. Stage 8, CDMA errors/timeouts, TX drops
  and bad-frame counters were independently read after the final test:
  stage 8 and all four error counters zero.
- Reports: `D:/fpga_runs/ara_probe_cpu_baseline_02`,
  `D:/fpga_runs/ara_probe_cdma_4m_01`,
  `D:/fpga_host_runs/eth_fast_cdma_elf_4m_01`,
  `D:/fpga_host_runs/eth_fast_cdma_elf_16m_01`, and
  `D:/fpga_host_runs/eth_fast_cdma_elf_random16m_01`, and
  `D:/fpga_host_runs/eth_fast_cdma_elf_random16m_02`. The 16 MiB runs include
  `xsct_spotcheck.txt` in addition to the sender's `report.json`.
- Independent XSCT reads matched smoke instruction `0x30401073` at
  `0x80000000`, zero BSS words, and payload endpoints. The random payload's
  first/middle/last words at `0x8C000FF8`, `0x8C800FF8`, `0x8D000FF4` matched
  `0xB49E7CF1`, `0x267FB293`, `0xD2C382DF`. Its SHA256 is
  `82e83798416309e211540ea02538883af737007fbcbd27a86093731cc52b5acc`.
- `check_eth_fast_load_board.py` passed reserved-range rejection (status 1),
  incomplete END rejection (4), reordered/duplicate/unaligned readback and
  post-END write rejection (2). Its second run deliberately drops an early
  DATA packet in an 80-packet transfer; one retransmission completes without
  exceeding the board's bounded receive window. Evidence:
  `D:/fpga_host_runs/eth_fast_protocol_02`. A normal full transfer subsequently
  succeeded. Native state/frame tests passed ASan/UBSan; five Python fast-load
  tests and thirteen existing TCP sender tests passed.

The sender window is anchored to the oldest unacknowledged sequence, not just
the count of outstanding replies. Limiting only that count allowed a lost
early packet to strand the receive cursor while later replies advanced beyond
the board's 64-packet window. The long-loss unit test and real loss-injection
test cover this software correction; no RTL change or new bitstream was needed.

Generated-IP CDC classifications and MDIO/reset IO-delay advisories remain
review caveats, not waived by board transfer. All routed Critical CDC paths
are inside vendor MAC/PHY or the vendor reset-to-SmartConnect synchronization
structures; no direct CDMA CDC path is reported. This is controlled isolated
board acceptance, not full production CDC sign-off or Ara handoff acceptance.

With the matching CDMA bitstream/ELF already running, repeat from the Windows
software directory, using a new output directory each time:

```powershell
$Out = 'D:\fpga_host_runs\eth_fast_' + (Get-Date -Format 'yyyyMMdd_HHmmss_fff')
py -3 .\eth_fast_load.py --elf .\host_smoke.elf --load '0x8c000ff8:D:\fpga_host_runs\ara_cdma_payload16m.bin' --out $Out
```

For rebuilding, `loader_bd_build.tcl` accepts mode `cdma`, and
`loader_fast_probe_build.tcl` accepts mode `cdma` with the matching exported
XSA/BSP workspace. Do not run the CDMA ELF against the baseline bitstream.

## Earlier TCP board checkpoint (2026-09-25)

- The isolated v7 design in `D:/fpga_runs/ara_loader_bd_build_07` completed
  route and bitstream generation with zero DRC errors, routed WNS +0.261 ns
  and WHS +0.010 ns. Its `loader_shared250.bit` is programmed on VCU118;
  this is **not** an Ara image. The linked standalone MicroBlaze ELF from
  `D:/fpga_runs/ara_loader_bsp_workspace_09` was downloaded separately with
  XSCT. Bitstream programming, DDR calibration and firmware stage 8 were
  observed on the board. Generated-IP CDC findings still require manual
  path review; bitgen and board transfer do not waive them.
- The Vitis 2020.1-generated `xtopology_g.c` assigned zero to the AXI INTC
  base despite the hardware mapping at `0x41200000`. DMA had received frames,
  but the interrupt enable register contained only timer bit `0x1`.
  `eth_loader_main.c` now validates the topology entry and corrects its
  mutable `intc_baseaddr` before `xemac_add`. On the board, the enable mask
  became `0xF` and a source-bound TCP connection succeeded. No RTL or
  bitstream change was needed for this fix.
- The generated linker puts lwIP `.bss`, DMA descriptors and packet buffers
  in reserved DDR `[0xFF000000, 0x100000000)`, accessible to the DMA but
  excluded from payload writes. Code, data, stack and heap remain in local
  BRAM. The BSP uses a 64 KiB lwIP heap, 80 packet buffers and a 16 KiB TCP
  receive window; Vitis's
  defaults had caused DMA initialization to return early without propagating
  an error.
- J10 transfer from Windows wired `192.168.1.11` to board
  `192.168.1.10:49200` passed for `host_smoke.elf`, then a 64 KiB extra
  payload, then a 1 MiB extra payload. The original 4 KiB-block test
  transferred 1,053,376 total bytes (ELF and BSS included) in 259 blocks
  in 4.329 s, about 243 kB/s including board DDR readback ACKs. With a
  16 KiB aligned scratch buffer, 16 KiB TCP window, 32-bit aligned DDR
  reads/writes and a byte-indexed CRC32 table, that intermediate firmware transferred
  the same bytes in 66 blocks in 2.112 s, **499 kB/s**. Evidence:
  `D:/fpga_host_runs/eth_loader_final_1m_01/report.json`. This is about
  2.0 times the initial measured rate, not an Ethernet line rate or an Ara
  execution speed. The sender spent 0.008 s in `sendall` and 2.098 s waiting
  for per-block ACKs; board profiling identified CRC and readback as major
  remaining CPU costs. The larger TCP window alone changed a 4 KiB-block
  run only from 2.845 to 2.806 s, so it did not explain the gain by itself.
- The latest software-only firmware keeps a 32 KiB scratch buffer wholly in
  local BRAM (`0x0001e6a8`, checked at link time), uses slicing-by-4 CRC32
  for aligned data and DDR readback, and advertises optional pipelined DATA
  records with capability bit 4 (not the existing DDR2 bit 2). With
  `--inflight 4`, 1,053,376 bytes passed peer readback in 34 blocks and
  1.241 s (**849 kB/s**). Four 1 MiB raw segments plus ELF transferred
  4,199,104 bytes in 130 blocks and 4.940 s (**850 kB/s sustained**).
  Evidence: `D:/fpga_host_runs/eth_loader_cap5_pipeline4_1m_01/report.json`
  and `D:/fpga_host_runs/eth_loader_pipeline4_4m_01/report.json`.
  The same 4 MiB image with the normal stop-and-wait mode took 5.194 s
  (809 kB/s), so pipelining itself helped only about 5%. A proposed fused
  TCP-copy/CRC pass did not improve the 1 MiB result and was reverted.
- Independent XSCT reads matched the first, middle and last pattern words in
  DDR. A write aimed at reserved `0xFF000000` was rejected with status 1;
  a deliberately corrupt record was rejected with status 2. A subsequent
  normal transfer succeeded after each rejection. An earlier raw-callback
  version could reset the TCP connection before delivering the status 1 ACK
  when rejected header and payload arrived together. The adapter now drains
  only the bounded declared payload before replying; a board retest returned
  `status=1` at `0xff000000`, then an unaligned 64 KiB transfer passed.
  Evidence: `D:/fpga_host_runs/eth_loader_guard_ack_01/report.json` and
  `D:/fpga_host_runs/eth_loader_final_unaligned_64k_01/report.json`.
  A pipelined run also rejected the reserved address with status 1 and
  recorded only the preceding legal ELF bytes, followed by a successful
  normal smoke run.
  `DONE` did **not** start
  the program. The sender report deliberately leaves `board_verified=false`
  because that field alone cannot distinguish a board from a test peer;
  board identity and independent XSCT reads are separate evidence.
- The board currently holds the isolated loader image and running standalone
  ELF, not the previous Ara or Ethernet echo image. No Ara memory arbitration,
  Linux boot, runtime handoff or execution has been tested through J10.

To repeat the small board transfer from Windows, keep J10 on the wired NIC,
give that NIC `192.168.1.11/24`, and use a new evidence directory:

```powershell
py -3 D:\project\ara\hardware\fpga\ara_dsa_vcu118\software\eth_load.py --elf D:\project\ara\hardware\fpga\ara_dsa_vcu118\software\host_smoke.elf --host 192.168.1.10 --source 192.168.1.11 --out D:\fpga_host_runs\eth_loader_next_run
```

The `--source` setting is important on a host that also has Wi-Fi: Windows
otherwise chose its Wi-Fi address even with a wired on-link route.
The sender defaults to `--inflight 1`; `--inflight 4` requires the current
loader firmware's pipeline capability and retains per-block ACK/readback.

## Earlier preflight checks

- `loader_preflight.tcl` ran in an isolated Vivado 2020.1 project on the
  Windows FPGA workstation. Its successful evidence is
  `D:/fpga_runs/ara_loader_preflight_20260925_05`.
- The local catalog contains AXI Ethernet 7.2, AXI DMA 7.1, MicroBlaze 11.0,
  SmartConnect and DDR4. The VCU118 board part was accepted.
- AXI Ethernet accepted SGMII/LVDS VCU118 settings with
  `CONFIG.processor_mode=true`. AXI DMA accepted scatter/gather, 32-bit
  receive/transmit streams, a 64-bit S2MM memory bus and 32-bit addresses.
  Both IP output targets were generated. The license-status report lists
  `tri_mode_eth_mac` Synthesis as `Bought`/`Bought`; bitstream license use has
  not been tested for this new configuration.
- The existing diagnostic image uses `processor_mode=false`. That mode has no
  processor driver support, so its PHY/PCS configuration can be reused but
  its MAC configuration cannot be connected to lwIP unchanged. See
  [PG138 processor mode](https://docs.amd.com/r/7.2-English/pg138-axi-ethernet/Functional-Description).
- The Python sender and hardware-independent C receiver passed native unit
  tests, including Python-to-C pipe and real localhost TCP exchanges with
  the actual `host_smoke.elf`. Fragmented handshake, bad payload CRC and
  mid-record disconnect were exercised. The older socket adapter was checked
  with a native shim; the standalone raw-callback adapter passed its own
  native tests and compiled against actual Vitis 2020.1 BSP headers. These
  tests used simulated memory, not the FPGA. At that checkpoint there was no
  linked firmware ELF or board-network result. The sender's `--plan-only`
  mode parsed the real `host_smoke.elf` into 448-byte and 4352-byte DDR1
  segments, with the latter including BSS zero fill.

## Wire contract

`ara_dsa_vcu118/software/eth_load.py` reuses `host_image.prepare_image` for
RV64 ELF and raw segment validation. After TCP connection the client sends
eight ASCII bytes `ARAETH01`. The receiver returns little-endian
`<8sII>`: the same magic, capability bits, and maximum block size (1..65536).
The isolated receiver advertises bit 0 for DDR1 host loading and bit 2 for
optional pipelined DATA records; bit 1 (DDR2) remains clear. The sender
defaults to one outstanding record and permits at most eight only when bit 2
is advertised. Each record still receives its own ordered readback ACK.

Each record is little-endian `<4sQII>`: `DATA` or `DONE`, DDR address or
entry, byte count, and payload CRC32. `DATA` is followed by payload bytes.
The receiver checks length, DDR1 bounds, monotonic non-overlap, received CRC,
then writes and reads back DDR before replying with `<QII>`: address,
readback CRC32, status. Any mismatch aborts the connection. `DONE` has zero
length/CRC and only acknowledges completed transfer; **it does not boot Ara**.
The host report's transfer rate includes per-block peer readback acknowledgments.

The implementation target is the Vitis 2020.1 **standalone** BSP with lwIP
raw callbacks, using the vendor `lwip_echo_server` platform/netif code as
a starting point. FreeRTOS is not required. The older
`firmware/eth_loader_tcp.c` socket adapter remains useful for native
protocol tests but is not the bare-metal board path.
`firmware/eth_loader_stream.c` accepts fragmented input without blocking,
and `firmware/eth_loader_raw.c` binds it to lwIP TCP callbacks. The raw
adapter and an initial 4 KiB scratch-buffer application entry point compiled with
the actual standalone BSP headers using Vitis 2020.1 `mb-gcc`; native
callback tests passed. A later isolated 512 KiB BRAM design also linked a
complete ELF, as detailed below. Those earlier results alone did not prove
network startup or FPGA operation; the current board results are above.

## Standalone hardware integration checkpoint

Vivado 2020.1 rebuilt an isolated `loader_bd_wrapper` in
`D:/fpga_runs/ara_loader_bd_build_01`, without opening Ara or accessing the
board. `loader_bd_build.tcl` generated and validated a MicroBlaze + AXI
Ethernet (processor mode) + scatter/gather DMA + DDR4 block design. The four
MAC/DMA stream interfaces are connected. MicroBlaze and the DMA descriptor,
MM2S, and S2MM address spaces each map the DDR4 segment at `0x80000000` for
2 GiB. Vivado's DDR connection automation initially left the DMA-side
interconnect outputs dangling; the script explicitly joins all four masters
through SmartConnect and rejects missing address segments.

`loader_bd_synth.tcl` completed top-level synthesis. The generated wrapper
was checked against `constraints/loader_pins.xdc`: all 14 non-DDR pin/IO
assignments matched, the 250/300 MHz clocks were present, and the vendor IP
defined the 625 MHz PHY reference clock. `loader_bd_opt.tcl` completed
`opt_design` with no unresolved black boxes. The post-opt DRC has zero Errors
and two DMA BRAM collision advisories. Source-based RTL and protocol tests
from the previous checkpoint remain the only loader functional tests.

This earlier checkpoint was **not** implementation or download acceptance. The post-opt timing
report has WNS `+1.055 ns`, WHS `-0.413 ns`, and WPWS `-0.029 ns` before
placement/routing; its IO report still lists two inputs and four outputs
without delay constraints. The post-opt CDC report includes 455 CDC-1, 2
CDC-4, 11 CDC-10, 4 CDC-11, and 3 CDC-13 Critical classifications, many in
generated MAC/PCS/AXI infrastructure. These need source/path review, not
blanket suppression. These post-opt reports belong to the earlier isolated
build, not a routed timing or CDC pass for the revised interrupt-connected
build. Ethernet automation also exposed the MAC's PHY reset
output directly, while the proven diagnostic image used an independent PHY
reset sequence; reset behavior must be resolved before board programming.
The initial BSP lacked MAC/DMA/timer interrupts. The interrupt-connected
design then failed to link the firmware within its 128 KiB local BRAM. The
link map identified about 115 KiB of code and 126 KiB of static data, mostly
lwIP pools and queues. Vivado's MicroBlaze automation rejected both 256 KiB
and 512 KiB `local_mem` settings. In the isolated
`D:/fpga_runs/ara_loader_bd_build_06` design, the generated dual-port BRAM
depth and both CPU address mappings were extended together to 512 KiB.
Block Design validation, top-level synthesis, no-bitstream XSA export and
the 14-pin/clock audit passed. This does not prove routed timing or operation.

The corresponding standalone lwIP BSP is in
`D:/fpga_runs/ara_loader_bsp_workspace_06`. Its `xparameters.h` reports
local BRAM through `0x0007ffff`, a 100 MHz CPU/timer clock, disabled caches
and four interrupt inputs. The C firmware and platform timer/interrupt glue
linked into `loader_app/direct/loader_app.elf`: `mb-size` reports 118080
text, 1548 data and 159636 BSS bytes (279264 total, including 16 KiB each
for stack and C heap). `readelf -l` shows all loadable sections in local
BRAM, ending at `0x44310`, below the `0x80000` limit. The writable DDR
window starts at `0x80000000` and excludes its top 16 MiB.

Vitis HSI still generates `TemacIntr=0xff` despite the MAC being wired to
interrupt vector 1. The application checks the generated DMA/MAC vectors
and corrects the mutable MAC configuration table before `xemac_add`; this
software workaround is linked but **not board-tested**. The vendor lwIP DMA
source also emits incompatible-pointer warnings in its checksum-offload
helper; the generated MAC has TX/RX checksum offload disabled, and the bad
RX helper call is behind the disabled offload path. The generated PHY reset
counter uses the independent 100 MHz management clock and releases after
about 3 ms. The application waits another complete 250 ms timer interval
before starting MDIO/netif setup. Actual PHY startup remains to be tested.
The 512 KiB v6 build passed `opt_design` but failed clock placement: Vivado
inserted a separate BUFG on the 250 MHz DDR reference path. Disabling that
automatic buffer still failed because a direct IO-to-DDR-MMCM path is not
dedicated on these sites. A read-only inspection of the previously routed Ara
checkpoint showed its E12/D12 250 MHz source feeding one shared BUFGCE at
`BUFGCE_X1Y288`, which then drives the DDR MMCM at `MMCM_X1Y13`. The isolated
v7 BD now feeds both its 100 MHz clock wizard and DDR from the same 250 MHz
IBUFDS output, matching that source topology. Its later route, bitstream
and board tests are reported in the current checkpoint above.

## Remaining work

1. Review generated-IP CDC paths and any remaining IO/timing advisories; do
   not waive them based solely on a functional transfer.
2. The CDMA fast path now reaches about 8.65-8.77 MB/s including readback,
   still below gigabit line rate and the approximately 12 MB/s reflection
   ceiling. Profile RX/TX driver, descriptor and per-packet CPU work before
   choosing the next optimization; the larger-window control experiment did
   not improve speed. Do not assume a cache, timeout or block-size change
   will help without measured evidence.
3. Decide later whether embedding the MicroBlaze ELF into the bitstream is
   useful; the current JTAG ELF download is sufficient for isolated tests.

Ara connection, passive-ROM handoff and launch/reset sequencing are a later,
separate milestone. They are not prerequisites for this isolated downloader
acceptance, and this checkpoint makes no Ara RTL changes. An integrated
design can be slower under DDR contention; standalone throughput does not
guarantee integrated throughput.

Local tests (no hardware):

```sh
python3 -m unittest hardware/fpga/vcu118/tests/test_eth_load.py -v
cc -std=c11 -Wall -Wextra -Werror -o /tmp/eth_loader_core_test hardware/fpga/vcu118/ethernet/firmware/eth_loader_core.c hardware/fpga/vcu118/tests/eth_loader_core_test.c
/tmp/eth_loader_core_test
cc -std=c11 -Wall -Wextra -Werror -o /tmp/eth_loader_stream_test hardware/fpga/vcu118/ethernet/firmware/eth_loader_core.c hardware/fpga/vcu118/ethernet/firmware/eth_loader_stream.c hardware/fpga/vcu118/tests/eth_loader_stream_test.c
/tmp/eth_loader_stream_test
cc -std=c11 -Wall -Wextra -Werror -Ihardware/fpga/vcu118/tests/lwip_raw_shim -o /tmp/eth_loader_raw_test hardware/fpga/vcu118/ethernet/firmware/eth_loader_core.c hardware/fpga/vcu118/ethernet/firmware/eth_loader_stream.c hardware/fpga/vcu118/ethernet/firmware/eth_loader_raw.c hardware/fpga/vcu118/tests/eth_loader_raw_test.c
/tmp/eth_loader_raw_test
```
