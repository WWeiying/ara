# Pre-Reference Store Bound

One original `e16_m1_u1_s1_b3_m2_f0_g3` source single. No reference execution
has occurred when this bound is written. Source/compiler/oracle inputs are
pinned in software01/input_pins.json. No DUT/RTL/image work is authorized.

Actual final software01/spike.dis, not the old load disassembly:

- `check` at80000082 has seven instructions on its success path.
- `check_memory` halfword loop800001e0..8000020a executes4096 times per phase.
  Phase0/1 allowance24 instructions includes check and phase1 prefix selection.
- Phase2/3 use the original logical-element search at80000334..80000342,
  five instructions per candidate, at most8. Allow86 total instructions per
  halfword including match, active/phase/poison branches, call and loop overhead.
- Page-table triple-loop80000246..800002ae has512 entries/phase; allow61
  instructions per entry across four phases, including special PTE branches.
- BSS is80002000..8000aad0:4442 doublewords. No synthesized BSS contents are
  supplied to the observer; startup writes must be present in the actual raw.

| Work | Instruction allowance |
| --- | ---: |
| Two initial/fault4096-word scans,24 each | 196608 |
| Two repaired/final4096-word scans,86 each | 704512 |
| Four512-entry triple page-table checks,61 each | 124928 |
| check_memory prologue, guards, checkpoint tails | 4000 |
| Startup BSS clear and setup | 18000 |
| Initial4096-word fill and2048-word refill | 40000 |
| Three snapshot checks and guards | 30000 |
| Other original input/offset/output/page-table initialization | 30000 |
| Handler saves/restores, scalar checks, CSR save/restore, runtime | 30000 |
| Subtotal | 1178048 |
| Additional allowance | 71952 |
| Correct-path admission estimate | **1250000** |

This is a conservative source/disassembly estimate for a correct terminating
path, not a termination proof for arbitrary errors. Fixed limits:
**1500000 instructions,120s child wall time,256MiB raw file,one invocation**.
Any failure or limit preserves actual wait status and raw; no automatic retry
or extension. The existing golden is non-ZCC Spike with
`rv64gcv_zfh_zvfh_zvl1024b --priv=msu --pmpregions=0 -m2`.

Raw sizing allowance190 bytes per ordinary instruction plus8MiB for vector
payload/CSR-rich/reset records gives245888608 bytes for the estimated path,
below268435456. This is a sizing estimate, not a guarantee on an abnormal
trace; RLIMIT_FSIZE enforces the independent hard bound. Previous adjacent
load actual raw was101219616 bytes for836971 firmware instructions,15.256s.

The new scalar prefix load at8000051a occurs before snapshot fences and page
repair and requires127. Original store memory then becomes36 at the poisoned
prefix and166 at the retry element. Four whole8KiB phases,64 result values,
two original guards, saved source/register neighbors, PTE neighbors and
same-PC MRET context remain checked. The extra prefix scalar comparison makes
17275 checks versus the load's17274; it does not replace any original oracle.

Spike has no AXI B channel. It establishes architectural prefix visibility and
retry semantics, not bus-response timing. A later DUT must preserve those
requirements; arbitrary delayed-B coverage cannot be claimed without probes.

For later planning only,1250000/(273 retired/s)*1.2=5495s (92min), below3h.
The measured adjacent M6 load was996.680s for its smaller836971-instruction
reference; neither proxy guarantees this store's runtime. No DUT admission
or timeout is established by the reference bound.
