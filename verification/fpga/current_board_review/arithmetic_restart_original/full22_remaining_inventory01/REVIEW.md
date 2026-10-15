# Original22 Remaining Full-Program Inventory

Static source/metadata review only. No build, DUT, reference, Host or raw CSV
parse was run. Scope is the authentic rvv_extended04 basic arithmetic suite,
not integration arithmetic38, ordered reduction, or the separate45 stalled
ELF records. Existing related tests must not be substituted by name.

## Current Acceptance

**2/22 complete original SoC programs accepted on M6**, 10080 ordered calls:
e8/mf8 and e32/mf2. Full-model counts total161280 results and20160 guards.
E8's old checker-error record is preserved alongside its accepted reset-GPR
offline recovery; e32's old canceled run is preserved alongside its accepted
new standalone run. Neither original Small2 whole2 NOT_PASS nor old cancellations
are relabeled. Original Linux execution is not claimed.

**20 complete original programs remain open**, containing97020 full-program
call positions. Five of those have accepted M4 prefixes totaling262 calls;
15 have no current original-matrix DUT acceptance in the reviewed inventory.
Combining the two M6 full programs and five M4 prefixes leaves96758 original
positions outside either accepted scope. This mixed-image union is not a
current-M6 whole22 coverage claim.

| Original shape | VLMAX | Full calls | Full result elements | Existing acceptance |
| --- | ---: | ---: | ---: | --- |
| e8_mf8 | 16 | 4095 | 65520 | Full M6 accepted |
| e8_mf4 | 32 | 4095 | 131040 | No current original-matrix DUT acceptance |
| e8_mf2 | 64 | 4095 | 262080 | No current original-matrix DUT acceptance |
| e8_m1 | 128 | 4095 | 524160 | No current original-matrix DUT acceptance |
| e8_m2 | 256 | 4095 | 1048320 | M4 prefix56; full open |
| e8_m4 | 512 | 4095 | 2096640 | M4 prefix56; full open |
| e8_m8 | 1024 | 4095 | 4193280 | M4 prefix38; full open |
| e16_mf4 | 16 | 4095 | 65520 | No current original-matrix DUT acceptance |
| e16_mf2 | 32 | 4095 | 131040 | No current original-matrix DUT acceptance |
| e16_m1 | 64 | 4095 | 262080 | No current original-matrix DUT acceptance |
| e16_m2 | 128 | 4095 | 524160 | No current original-matrix DUT acceptance |
| e16_m4 | 256 | 4095 | 1048320 | M4 prefix56; full open |
| e16_m8 | 512 | 4095 | 2096640 | M4 prefix56; full open |
| e32_mf2 | 16 | 5985 | 95760 | Full M6 accepted |
| e32_m1 | 32 | 5985 | 191520 | No current original-matrix DUT acceptance |
| e32_m2 | 64 | 5985 | 383040 | No current original-matrix DUT acceptance |
| e32_m4 | 128 | 5985 | 766080 | No current original-matrix DUT acceptance |
| e32_m8 | 256 | 5985 | 1532160 | No current original-matrix DUT acceptance |
| e64_m1 | 16 | 5985 | 95760 | No current original-matrix DUT acceptance |
| e64_m2 | 32 | 5985 | 191520 | No current original-matrix DUT acceptance |
| e64_m4 | 64 | 5985 | 383040 | No current original-matrix DUT acceptance |
| e64_m8 | 128 | 5985 | 766080 | No current original-matrix DUT acceptance |

Every e8/e16 full program has25 operations/4095 calls/8190 guards/53235 helper
instructions; every e32/e64 program has35 operations/5985 calls/11970 guards/
77805 helper instructions. All retain3 seeds and original order. The complete
archive is107100 calls across22 shapes. Detailed Linux ELF and assembly hashes
and scope counts are in inventory.json.

Authorities: prepared02/original_identity.json, recovery22/report.json,
NEXT_ORIGINAL_SCOPE.md, TERMINAL_AUDIT01.md (accepted five M4 prefixes),
full_small2_e8_offline_recovery_audit01/run01/TERMINAL.json and the accepted
e8 metadata review; full_e32_mf2_terminal_metadata_review01/REVIEW.json.
No later full arithmetic shape acceptance was found in this family's records.
Historical board19-pass/3-stall and QEMU reference are not current M6 acceptance.
Three historically stalled full shapes e8/m4,e8/m8,e16/m8 remain full-program
gaps despite their now-accepted bounded M4 op0 prefixes.

## Best Next Full Candidate

**rvv_matrix_e16_mf4**, not the similarly named ordered-reduction single.
It is the remaining integer-only cap16 shape: original25 operations,3 seeds,
4095 calls,65520 result words,8190 guard words,4095 returned-vstart checks and
53235 helper instructions. Its original lengths are0,1,2,3,8,15,16; retain
all three predicate modes and source-defined starts, including duplicate zero
positions. Preserve per-seed xorshift/special values, all128 physical predicate
bytes, full16-lane setup/oracle, sentinel91 and both guards. Do not shrink the
original1024-element a/b,1026-element output allocations or startup BSS.
The per-call initialized footprint is32+32+128+36=228 bytes, not the unrelated
ordered-reduction144-byte oracle. Output oracle reads total147420 bytes.

Freshly hashed candidate identities match the existing manifest/recovery:
- Original and already-reconstructed Linux ELF:
  e538572bcf13bd7338647f5a7e5b7bfc8627f1ee04598d8fb0283a76926b998c.
- Original assembly:
  dff1fdc271e574eb7206583a446fb0fd2cc99be20a406024280c955b51905c33.
- Original e16 operations.h:
  7686eb17f96d500c82711d09bbaa74c965352b4257b0b7db3510d3fbbd9bf48c.
- Binary-equivalent reconstructed oracle.c:
  7483f9dfde7012f7b800314fe1765f8cee9836fbcfbdc16fc641554397884e91.
Original C text is not recovered; original manifest C hash is different.
The existing22 byte-identical Linux rebuilds prove provenance, not DUT execution.

Source paths: recovery22/reconstructed_oracle.c and recovery22/rvv_matrix_e16_mf4;
archive /home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_extended04/
rvv_matrix_e16_mf4.S and e16/operations.h. The original ELF is under that archive's
overlay/opt/ara-tests/. There is no newly prepared full e16/mf4 SoC ELF or current
full-reference cost in this task, and an archived Linux ELF cannot replace it.

## Measured Budget Basis, Not A Runtime Guarantee

| Accepted M6 full program | Actual simulator seconds | Retirements through CTRL | Effective retire/s |
| --- | ---: | ---: | ---: |
| e8/mf8 | 6279.050261 | 4405205 | 701.572 |
| e32/mf2 | 10026.130593 | 5922683 | 590.725 |

These are actual monitor durations, not offline audit time or wall-clock
service lifetime. Different host concurrency and instruction mix limit transfer.

For the proposed e16/mf4, all three transparent extrapolations fit10800s:
- Same-capacity e8 full runtime with20% margin:7534.860s (2.093h).
- Slower measured per-call rate,4095 calls,20% margin:8231.981s (2.287h).
- E8's4.405M instruction proxy at slower measured e32 retirement rate with20%
  margin:8948.747s (2.486h).

These are **projections**, not a measured e16 bound. No remaining shape currently
has a demonstrated own full-M6 runtime below3h. E16/mf4 is the best justified
next *preparation* candidate; launch admission still needs its exact runtime
port/source proof, full reference/oracle and measured reference instruction cost.
At590.725 retire/s and20% margin,10800s accommodates about5.3165M proxy
retirements, an explicit comparison threshold, not a hardware-time guarantee.
Keep any eventual simulator budget10800s, worker12000s/service13200s; no automatic
extension. E64/m1 shares cap16 but has5985 calls/FP operations: the measured e32
runtime plus20%=12031.357s already exceeds10800s, so it is not the preferred next
bounded candidate. Cap32+ shapes also lack adequate measured full-cost evidence.
The much larger historically stalled shapes are not justified as <3h full runs
by their short prefixes.

## Exact Reuse And Required Narrow Adaptation

Reuse the same frozen M6 image/reset-zero proof and mature numeric-outcome,
fail-stop, direct cgroup owner, pin and single-pass terminal mechanisms.
Reuse source runtime-only adaptation, not prefix insertion or loop truncation.
Retain original13-instruction helpers byte-for-byte against this e16 assembly,
and derive fresh actual SoC PCs/symbols/ABI startup from its own ELF.

The existing full-small2 model/prepare/checker wrappers are deliberately limited
to e8/e32 and are **not drop-in e16 acceptance**:
- model.rows rejects SEW16; its operation/count selection currently uses
  25 if sew==8 else35. A new owned successor must admit e16 as integer25,
  not accidentally enter FP or count5985.
- preparation helper enumeration also uses the e8-versus-other split and
  must select the original25 e16 helpers; preserve original e16 headers.
- specification/profile/ELF allowlists must bind the new exact e16 SoC image
  and cap16 shape, never borrow e8/e32 PCs or archived Linux addresses.
- Core Strict consume/finish already uses SEW-derived widths and full16+2
  oracle. Its original source/setup/CSR/window/unknown-register checks can be
  preserved rather than weakened; real e16 ABI entry and halfword load/store
  masks/sign rules must be covered in a bounded Host before admission.

This adds authentic complete-source coverage of one historically passing
control; it does not itself close the three historical stalled full programs,
separate45 records, or all previous bug families. No synthetic scope is proposed.
Main retains scheduling and CURRENT_SCOPE updates.
