# M9 STORE/SoC Contract Follow-Up

Decision: no evidenced production defect; no blocking issue found in the inspected directed SoC source contract. This is not reference, dynamic-checker or worker admission. Preserve earlier M9_BOUNDARY_REVIEW01 as its review-time snapshot.

## Newly Available Evidence

Read completed STORE REVIEW.md, not CSV or live process state: four successor cases report actual0,1004 rows, unchanged251-row M8 normal control. Late fault has only one prefix AW, WREADY until40, actual W40/B50/marker-pop50/done-response51. This observed response is after B, not a pending-bit inference. Initial fault has zero AW/W/B. Original ERROR remains preserved. Local e64/nontranslated results do not close SoC/MMU coverage.

## Actual SoC Source

Inspected unmasked_strided_alignment_soc_m9_prepare01/fixture.c SHA41e75c4797de31e84edde4659342c6759025c7dd8942286bb6f09cf3390d2f0a and fixture.S SHA290d7eab341aa976f949a4b6b82ccf713dbcf4e7fb8ed140d8690f4e6e6cb795. Source was still in preparation; no sealed/reference result is inferred.

- Load/store compile variants and M/Sv39 variants retain e64/m1/VL2/start0 target stride4. Actual target PC is checked on the first trap; cause4/6, mtval=target virtual address+4, absolute vstart1, VL2/vtype24, privilege/SATP and fcsr117/vcsr5 are independently saved and checked. Unexpected page/access/phase/PC traps reach mt_bad_trap, not an alignment waiver.
- Real Sv39 root entries1 and2 map a 1GiB supervisor RWX leaf with A/D preset to physical0x80000000. Code/stack use identity region2; target memory uses the region1 virtual alias. Handler executes in M mode, preserves the actual mepc for same-PC retry, and restores S/M return context rather than skipping the target.
- After the first fault, handler snapshots all16 vector words and all16 backing words before poisoning memory prefix0. It changes stride4 to8 and restores vstart1 after snapshot vset changes. Same-PC retry must preserve the completed prefix: load result0 retains original data0 rather than poison; store memory0 stays poison rather than being rewritten from seed0. Complete retry output, prestart/tail and two-word guards are checked.
- Only the load fault snapshot's incomplete active element1 is exempt. Prefix0, all inactive/tail words and guards remain checked; after retry element1 is checked too. No global output or CSR unknown-value exemption is introduced. Store source snapshot remains fully checked.
- A separate legal v8 load/store successor and full snapshot verify continued progress and stale-owner isolation. Both trap records, post/tail CSR reads,512 root PTEs and saved CSR restoration are checked. Source counts are697 for load and698 for store; the difference is exactly the single intermediate load-word exemption.
- The frozen M8 configuration uses WT D-cache (cv64a6_imafdcv_sv39_config_pkg.sv:76). Existing fences order the handler's poison and snapshot operations; this source contract is not claiming that a fence alone establishes arbitrary write-back-cache coherence.

## Scope To Keep Precise

This SoC source adds real translated fault/retry and architectural forward progress if it later passes; it does not by itself measure zero MMU req/grants or AXI B timing. Exact no-orphan microinterface evidence and delayed-B timing belong to direct probes; a later successful scalar/vector operation establishes no lasting orphan, not absence of all MMU activity.

It does not add EEW16/32, unsafe negative stride, or nonzero-original-start late fault. Those remain the small discriminators listed in M9_BOUNDARY_REVIEW01, not new demonstrated bugs. It also does not provide many-good-prefix alignment coverage: with vm1 constant unsafe stride, the second active element necessarily faults.

Reference/checker must bind the actual source/ELF helper and trap/retry sequence, reconstruct fresh data/guards and exact CSR readbacks, keep actual numeric execution separately, and reject unexpected traps or event omissions. No reference/worker approval is given before those artifacts exist. Reviewer did not build, simulate, reparse CSV, modify author files or query background tasks.
