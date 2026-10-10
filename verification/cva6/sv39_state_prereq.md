# S/Sv39 Actual-SoC Prerequisite

Status (2026-09-22): **116 checks PASS in actual VCS SoC simulation after R-90**.
The first diagnostic run found only the predicted ECALL tval error (#68).
Decoder-local correction was then verified using the identical frozen ELF;
the 165-check state prerequisite, `vle32` and `vsetvl` also passed in the same
new simulator image. These are directed prerequisites, not Linux boot signoff.

## 实测证据

- 原失败：`verification/out/sv39-prereq-vcs-20260922/`，102.42 秒，115/116 项通过。
- 修复后：`verification/out/sv39-prereq-fixed-vcs-20260922/`，本例 86.64 秒，116/116。
- 前后 ELF 相同；未调整刺激、期望、超时或配置。周期 39445 的 S ECALL tval
  从 `0x73` 改为零，两次向量缺页、补页重启和数据检查保持通过。
- 本例九路日志完整且未截断，33/33 ACC 请求/响应、两次预期向量缺页、零协议错误。
  整个四点回归的输入指纹、提交轨迹和捕获完整性审计 PASS。
- 不把少打印失败信息导致的墙钟减少算作性能收益；不声称完成了全部 Sv39、
  delegated traps、上下文切换或 Linux 验证。逐周期表和源码修复见
  [验证报告第 105 节](../RVV1_DIFFERENTIAL_VALIDATION.md#105-一次跨模块捕获定位-ecall-tval-错误)。

## Scope And Assumptions

- Default build: `cv64a6_imafdcv_sv39`, `MmuPresent=1`, `RVS=1`, WT data cache,
  `OSSupport=1`, four lanes, VLEN=1024. `ara_soc` overrides `NrPMPEntries=0`;
  this test neither configures nor tests PMP. It uses ordinary S, not RVH VS.
- `crt0.S` calls `rvtest_init` in M with a valid stack, VS/FS enabled and bare
  SATP. It later MRETs to U-mode `main`; all printing happens there after cleanup.
  No assumption that the default `mtvec` is a usable recovery vector is needed
  inside the test window: `enter_s` installs an aligned direct M handler.
- DRAM decodes `[0x80000000,0xc0000000)`, but the default backing memory is
  1 MiB. CTRL returns the decoded high end as the initial SP. The test permits
  this established high alias: the hook's stack is just below `0xc0000000`,
  not at CTRL MMIO `0xd0000010`. The 1 GiB identity leaf covers this stack and
  all code/globals. The linked image is well below the backing-memory stack.
- Single hart; no asynchronous interrupt/NMI/debug entry. The hook saves and
  zeros both delegations and `mie`; clearing MIE alone would not mask machine
  interrupts in S. MPRV/MPV/TVM/SUM/MXR/SIE are cleared for the test window.
- Scalar stores use the WT path; accelerator writes use the existing enabled
  `acc_cons`/AXI invalidation path. `fence rw,rw` orders data and PTE stores;
  vector CSR reads drain Ara before scalar observations. A fence is not being
  claimed as a portable cache flush. No cache or consistency CSR is changed.
- C is built with `-fno-vectorize`, scalable vectorization off and
  `-mno-implicit-float`; `vec`, Linux/FPGA/Spike and nondefault lane/VLEN builds
  are rejected. Non-ZCC LLVM is the reviewed compiler, not a portability claim.

This is not Linux boot, a page allocator, context switching, delegation,
interrupt handling, ASID switching, PMP/SUM/U-page permissions, A/D-bit update,
indexed/segmented/masked/fault-only-first RVV, arbitrary VLEN, or FPGA signoff.
It uses caller-clobbered `v8`; it restores every changed CSR, not vector data
register contents or TLB/cache microarchitectural contents.

## Mapping And Oracle

The rules used are the fixed-version ratified
[RVV 1.0 vector specification](https://docs.riscv.org/reference/isa/v20260120/unpriv/v-st-ext.html)
and [Supervisor/Sv39 specification](https://docs.riscv.org/reference/isa/v20260120/priv/supervisor.html).
No raw master v-spec draft is used as an RVV 1.0 reference. Sv39 has three levels
and 4 KiB base pages; a suitably aligned root leaf can cover 1 GiB. PTEs are
written with aligned 64-bit stores, followed by ordering and SFENCE.VMA.

`root_pt[1] -> mid_pt[0] -> leaf_pt` covers the four low VA pages. Non-leaf
flags are V only. All leaf mappings have U=G=0 and A=D=1; data flags are
`0xc7` (VRWAD), identity code/stack flags are `0xcf` (VRWXAD).
Other PTEs are explicitly zeroed, not dependent on BSS loader initialization.

| VA | PTE | Physical backing | Initial state |
|---|---|---|---|
| `0x80000000..0xbfffffff` | `root_pt[2]` | Identical 1 GiB decoded region | Valid RWX |
| `0x40000000` | `leaf_pt[0]` | `pages[0]` | Valid RW |
| `0x40001000` | `leaf_pt[1]` | `pages[2]` | Invalid (entire PTE zero) |
| `0x40002000` | `leaf_pt[2]` | `pages[3]` | Valid RW |
| `0x40003000` | `leaf_pt[3]` | `pages[5]` | Invalid (entire PTE zero) |

Each physical page and each table is 4096-byte aligned. `pages[1]` and
`pages[4]` are unmapped physical gaps filled with guard `0x6b6b6b6b`. A burst
that incorrectly continues into the next physical page cannot masquerade as
the second VA page. The code accesses no unbacked low VA as physical RAM.

| Phase | S-mode work | Required observation |
|---|---|---|
| 1 | Scalar LWU at VA+32, SW/LWU at VA+36 | `0x13579bdf`, then `0x2468ace0` |
| 1 | `e32,m1,tu,mu,VL=8`; same-page VLE32 at VA+64, VSE32 at VA+128 | Eight words `0x31415000 + i*0x107`; VL=8, vtype=0x10, vstart=0 |
| 2 | VLE32 at `0x40000ff0` | Load page fault 13, exact PC, mtval=`0x40001000`, vstart=4, VL=8 |
| 2 | M repairs `leaf_pt[1]`, fences, MRETs to unchanged PC | Eight words `0x11223040 + i*0x101` in `load_out[1..8]`; vstart=0 |
| 3 | VSE32 at `0x40002ff0`, separate source `0x55667080 + i*0x103` | Store page fault 15, exact PC, mtval=`0x40003000`, vstart=4, VL=8 |
| 3 | M snapshots first four stores, repairs `leaf_pt[3]`, fences, retries | Prefix snapshot and all eight destination words correct; vstart=0 |
| 4 | Fixed `sv39_s_ecall` label | Cause 9, mtval=0, vstart=0; return through fixed M label |

Here `(4096-4080)/4 = 4` elements fit before the page boundary; the two
independent invalid PTEs force the two fault sites. RVV records the instruction
PC and a resumable element index, and precise traps preserve committed prefix
results. Exact `vstart=4` is the frozen directed expectation for this Ara
page-split path, not a proof that every legal implementation must choose the
same restart point. No oracle assumes ordering between individual unit-stride
elements or requires inactive vector tails to remain untouched. The store
prefix is sampled only after the fault has drained, not at first MMU request.
Final values alone cannot prove there were no duplicate idempotent writes;
the main-thread lifecycle/AXI evidence must establish actual restart behavior.

## Trap And Restore Contract

The hand-written S body changes only `t0-t6` and `v8`, never callee-saved GPRs,
RA, GP, TP or SP. `enter_s` is a normal C ABI call with a saved RA/old-mtvec
frame. It publishes that frame before installing the handler. The M handler
swaps SP through `mscratch` onto a dedicated aligned stack and saves/restores
every GPR it uses (`t0-t6`); no printf, C call or vector data instruction.
It records up to four 64-byte records:
`mcause,mepc,mtval,vstart,mstatus,phase,invalid_pte,vl`.

Repair requires the exact cause/PC/VA/phase, S-origin MPP, VL=8, vstart=4,
an unused repair flag, and the corresponding PTE still zero. It sets the flag,
writes the precomputed PTE, executes `fence rw,rw; sfence.vma x0,x0`, and
returns without writing `mepc` or `vstart`. A duplicate fault cannot loop.
CSR reads do not reset `vstart`; the dispatcher explicitly excludes SYSTEM
instructions from its successful-vector-instruction vstart reset.

The known S ecall or **any other trap in this installed window** selects
`sv39_m_resume` and MPP=M, with MPIE/MIE/MPRV/MPV cleared. Unexpected traps set
FATAL and retain their raw record; there is no `mepc += 4` recovery. The resume
label reloads the published M frame, restores the original mtvec and returns
to C. MRET resets the MPP field to U even when returning to M, so check #34
expects MPP=0; M execution is established by the MRET destination and succeeding
privileged CSR instructions, not by misreading post-MRET MPP as current mode.

All comparisons run in M and accumulate failures without returning early.
The original SATP is restored with SFENCE before summary; then VL/vtype
(including VILL), vcsr/vstart, mtvec/mepc/mcause/mtval, mscratch, both
delegations, mie and finally mstatus are restored. Status is checked with MIE
still masked, then the full original mstatus is written last. `main` does not
use EXIT_CHECK's additional vector CSR read. Shared printf may use FP outside
the restored hook boundary; no print occurs inside it.

Recovery assumes functioning M fetch/RAM, the saved frame, and the already
validated M vector CSR access path. It does not promise recovery from a second
fault inside the M handler, corrupted physical memory, an unresponsive bus or
an accelerator deadlock. Preflight CSR/setup and final cleanup faults are
outside the installed S-test trap window. Such platform failures require the
main thread's bounded external capture, not guessed software PC advancement.

## Planned Checks

**116**, with a 128-entry failure log and explicit overflow failure. Counts
are unchanged on a comparison mismatch, preflight rejection or recoverable
return after a fatal S trap; unexecuted observations retain failure sentinels.

| IDs | Count | Checks |
|---|---:|---|
| 1-6 | 6 | Bare SATP, decoded SP range/alignment, object layout, delegations/mie zero |
| 20-34 | 15 | Fatal/count/fix/done/phase, S SATP, scalar control, VL/vtype/vstart and M return |
| 50-73 | 24 | Eight fields for each load/store/ecall trap; ecall PTE field is the defined zero placeholder |
| 100-107,110-117,120-127,130-137 | 32 | Same-page output, cross-page load output, store output, unchanged load source |
| 140-143 | 4 | Store prefix committed at the fault before PTE repair |
| 150-151 | 2 | Scalar control physical backing |
| 160-169 | 10 | Guards around control ranges, cross-page source/destination and load_out |
| 170-171 | 2 | Whole physical gap pages unchanged (mismatching-word counts) |
| 180-186 | 7 | Final identity/table/leaf PTE contents |
| 200-213 | 14 | Full saved CSR readbacks, mstatus last |

PASS additionally requires completed M hook, exact planned count, no fatal,
no overflow, no failed check and SoC exit=0. Guard sums are not extra checks;
the two gap scans each contribute one check. Missing expected traps or data
comparisons cannot silently reduce the count or produce PASS.

## Hypothesis And Signal Matrix

Use the [cross-module probe plan](sv39_probe_plan.md), with the
same frozen ELF and shared CSR/ACC boundary/lifecycle probes. No RTL fault is
presumed. Match epoch/PC/instruction/order/flush history, not a recycled ID
alone; sample all q/d evidence at the probes' pre-edge `#1step` phase.

| Candidate if a check fails | Discriminating evidence in the captured logs | Expected observation / decision |
|---|---|---|
| S entry or translation not enabled | CSR privilege/SATP plus `.mmu` enables/root and `.mmu_route` selected VA/store and both request sources | Ordinary S, SATP MODE=8; code high VA identity, data low VA translated. Cause 12/5/7 is not the planned 13/15 |
| Wrong PTE or scalar/PTW visibility | `.mmu` PTW raw PTE address/data_req/gnt/rvalid/rdata, TLB update; scalar repair PC/fence/SFENCE | Exact table chain/PTE values below; distinguish construction/visibility from decode before attributing a fault |
| MMU response routed to wrong owner | `.mmu_route` scalar/acc inputs, selected request and acc result, `.mmu` response/exception | Same VA/access type/ownership through acceptance and response; valid is not a handshake or retirement |
| Incorrect page split/vstart | `.addrgen` pe.vl/vstart/eew, original/current VA, remaining bytes, queue push/pop and exception q/d | Initial 32 bytes, 16 bytes left at second-page fault; `8-(16>>2)=4`; no successful AXI request for invalid page |
| Premature trap or data completion | `.vlsu` AXI AR/R/AW/W/B fire, byte enables, load VRF result req/gnt, completion; ACC pending/flush | First four committed when fault reaches M; correct byte coverage, no guard write; correlate response drain separately from exception |
| Repair invisible or restart wrong | Repair SD, fence/SFENCE, PTW/TLB refill, same fault PC accepted again with vstart=4 | Resume at second-page mapping, retain first four results; no second fault at the same site; flags allow only one repair |
| Scalar/RVV coherence or wrong physical continuation | WT stores/invalidation, `.vlsu` PA/data/BE and final physical buffers/gaps | Three nonidentity mapped transfers agree with literal data; gap pages and boundary guards unchanged |
| Inflight transaction lost / no ecall | ACC accept/spill/issue/complete/cancel/ID reuse, `.seq` lane/mask acceptance and running sets, `.dispatcher` flush/vstart, MMU/addrgen/VLSU last progress | Identify outstanding obligation and stalled ready/response; no arbitrary timeout increase or speculative RTL edit |

There are seven new state streams plus CSR/FPU. MMU responses must be related
to registered request fields, not merely the current VA. `.ptw` distinguishes
cache return, registered PTE and update phases. The route probe deliberately
does not claim to observe its anonymous-generate ownership state. ACC lifecycle
has a separate 65536-cycle window; check target-event coverage explicitly rather
than claiming it captures every initialization and printf cycle.

If waveforms are needed, preselect the fault-PC request through handler
SFENCE and first restarted completion, with a bounded window (initial budget:
128 pre-trigger and 2048 post-trigger cycles per fault, not a latency oracle).
The activity logs must retain the whole sequence, including setup and the
final ecall, with one END per stream and `truncated=0,dropped=0`. Reuse this
capture for alternative hypotheses; rerun only for missing discriminating
evidence or a justified fix. No polling of simulations expected over ten
minutes; the main thread owns independent background runs and completion.

## Build And Static Freeze

The test is registered as `sv39-prereq` in Makefrag/gitignore/suites.
The direct application build is:

```sh
make -C apps -o linker_script zcc=0 config=default \
  bin/rv64uv-ara-sv39_state_prereq
```

The non-ZCC build and additional `-fsyntax-only -Wall -Wextra -Werror` check
passed. Only linker diagnostic: ignored memory-region assignment for the
non-allocatable `.comment` section. This is compilation, not DUT PASS.
The static-review build did not regenerate the shared linker script.
Independent test and fault-drain/vstart probe reviews preceded the first run.

Frozen on 2026-09-22 after the final compile:

| Item | SHA-256 |
|---|---|
| Source | `2a9c11d40cb829ef9b363b55c64efc0aab43aad31c585a54051c9d214718500f` |
| ELF | `ee7fc5a54f68cf072a6b754df3467504b7fd2a6994e4b6f5e7a6de0327e17c0c` |
| Pre-strip dump | `4affcfd99958c85e71f1ea64e885e29769e0e0ee9fa0f7cac9920fb60ff52abf` |

| Symbol / action | Address / encoding |
|---|---|
| `sv39_m_handler` | `0x80000104`, 4-byte aligned |
| `enter_s` / `sv39_m_resume` / `sv39_s_entry` | `0x80000308` / `0x8000035a` / `0x80000384` |
| S configuration / same-page load / same-page store | `0x800003be` / `0x800003d2` / `0x800003da` |
| `sv39_load_fault` | `0x800003f8`, `020e6407` = `vle32.v v8,(t3)` |
| `sv39_store_fault` | `0x80000438`, `020e6427` = `vse32.v v8,(t3)` |
| `sv39_s_ecall` | `0x80000458`, `00000073` |
| Restore VL/vtype | `0x80001d20`, `8127f057` = `vsetvl zero,a5,s2` |
| Restore/check masked mstatus / final full mstatus | `0x8000224e` / `0x800022ae` |
| `main` | `0x800022d0` |

The `.text` audit finds exactly six explicit vector memory instructions, the
one S `vsetivli` and the M restore `vsetvl`; no implicit vector instructions.
No FP instruction occurs in the test/hook/handler; linked shared printf has
FP code outside that boundary. Only t0-t6/SP are written in the handler, with
matching saves/restores. Repair has no mepc/vstart write and no hidden call.
The C check bookkeeping is inlined but dynamically totals 116 as tabulated.

`leaf_pt/mid_pt/root_pt` are `0x80004000/0x80005000/0x80006000`.
`pages[0..5]` are `0x80007000..0x8000c000`; gap pages are `0x80008000` and
`0x8000b000`. `load_out/store_in/trap_stack` are
`0x8000d000/0x8000d040/0x8000d070`. The dedicated trap SP is `0x8000d170`,
with its 64-byte frame below that address. The image ends at `0x8000dd98`;
text/data/BSS sizes are 14348/8/40704 bytes. Review uses allocatable ELF
sections, not `objdump -D`'s accidental instruction decoding of symbol tables.

Exact SATP is `0x8000000000080006`. Initial root[1]/root[2]/mid[0] PTE values
are `0x20001401/0x200000cf/0x20001001`. Leaf[0..3] start as
`0x20001cc7,0,0x200028c7,0`; the repairs install `0x200024c7` and `0x200030c7`.
Thus cross-load PA spans `0x80007ff0..0x80007fff` then
`0x80009000..0x8000900f`, and cross-store spans
`0x8000aff0..0x8000afff` then `0x8000c000..0x8000c00f`.
These are expected values calculated from the linked layout, not observations
of a DUT run. Main-thread image/probe hashes and measured results must be
recorded separately. Rehash and re-review the layout if the source changes.
