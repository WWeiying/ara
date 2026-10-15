# Single Reference Admission

Four exact source singles from source_manifest.json, one combined real-Sv39
ELF. No new historical predecessor sequence is invented. Latest parent tuple
selection takes precedence over the conflicting batch03 heading.

The compiled SoC disassembly has check_memory at0x80000284, its full-page loop
0x800002da..0x800003a0 and PTE loop0x800003e6..0x8000044e. Eight memory
checkpoints remain: fault/final for cases0/1 and precleanup/final for2/3.
Most halfwords take the outside-segment path; only16 per checkpoint enter
the detailed segment-address branch. The compiled seed/vector_gold/check
bodies have29/40/27 static instructions; refill_page has13. Successful-path
check() does not enter diagnostic formatting.

Conservative planning charges (not measured retire counts):

| Work | Charge |
| --- | ---: |
| 8*4096 memory iterations,45instructions outside segment | 1,474,560 |
| Additional128 in-segment iterations,150instructions | 19,200 |
| 8*512 PTE iterations,45instructions | 184,320 |
| Original4*4096 page initialization,12instructions | 196,608 |
| Two2048-halfword u1 refills,13instructions | 53,248 |
| Seed/snapshot/output oracle and init,4096*120 allowance | 491,520 |
| Remaining initialization, trap/CSR/markers/guards/runtime allowance | 200,000 |
| Total planning bound | 2,619,456 |

Authorize one reference invocation at3,000,000steps /120seconds /512MiB raw
file ceiling, actual profile rv64gcv_zfh_zvfh_zvl1024b, --priv=msu,
--pmpregions=0, -m2, no retry. This is a conservative successful-path estimate,
not a proof of termination under a software defect. Exceeding a bound or
missing the exit/oracle stops preparation; no oracle shrinking or automatic
extension. The existing same-family reference used1,189,205 commits and
143,989,993bytes (~121bytes/commit); 3M at that density is ~364MB below512MiB.

VCS is NOT authorized here. Existing NF2 four-case measurement1590.94seconds
for1.189M reference commits is the comparison source, not this ELF's timing.
Finalize a fixed <=3h VCS budget from this reference's actual count. Full
128 outputs,2 guards,8192memory bytes, PTE/neighbor/CSR checks remain intact.
