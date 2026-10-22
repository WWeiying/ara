# GAP102B nonzero-vstart preflight

No VCS launch, RTL change, old-image rebuild, coverage gain or admission.
The parent-approved next hypothesis is intentionally different from GAP102:
the active source and wide destination do not share a physical register before
MAC, even though their complete architectural groups legally overlap.

## Frozen usable inputs

- App: `apps/riscv-tests/isa/rv64uv/vgap102b_widen_acc_vstart.c`.
- Software reference: `verification/tests/gap102b_reference.h`.
- Independent host oracle: `verification/tests/gap102b_host_reference_v2.c`.
- Compile/Spike builder: `verification/coverage/build_gap102b_preflight_v2.py`.
- Strict actual-log qualification: `verification/coverage/qualify_gap102b_preflight_v3.py`.
- Final preflight directory:
  `verification/out/gap102b-widen-acc-vstart-preflight-717-20261006-03`.
- Manifest SHA256:
  `9658afe68b674bb25fb849b4fcab9b46c1778ee4c4051562d0a162e73df72552`.
- ELF: `verification/out/gap102b-widen-acc-vstart-preflight-717-20261006-02/input.elf`.
- ELF SHA256:
  `5f27f7052c5805c46f80c859713350d15d5037754a2784a75039e245f7a593bd`.

The final03 manifest binds79 pins, including its own successor validation and
the actual GAP102B02 ELF/host/Spike artifacts. It does not reuse the earlier
GAP102 execution or preflight artifacts as this case's results. Qualified03 is
a strict offline successor audit of GAP102B02, not a second Spike execution.

## Static routing audit

Old dispatcher SHA256:
`9af95c3eee6c63ecd9e60bf6d7c6474bdaaf1c5f96cef1bd653a6d51c6a2dd43`.
The target-before file binds the old build/source owner, compiled branch shape
and exact717 population. Raw127 remains zero in this baseline; spec25/vector1002
is the path through5829 and the false arm of5843, not a guessed source offset.

1. Seed all v8-v15 with e32,m8,VL256. This is a complete unmasked overwrite.
2. Set e16,m4,VL129, then vstart128 before the narrow load. Only source element128
   at v14 bytes0-1 changes. Active-only destination metadata updates at5892-5906
   affect v14, not v12. The preserved portion of v14 may be normalized to EW16
   before the load; this still does not modify architectural v12.
3. Reload vstart128 immediately after the load, which clears vstart on completion.
   Before MAC, independent CSR checks require `[129,10,128,0]`.
4. MAC is `vwmaccu.vx v8,a0,v12`, opcode `0xf2c56457`, scalar7. With wide destination
   e32,m8 and narrow source e16,m4, its active destination is only v12; active vs2
   is only v14. The source mask and wide destination mask are distinct.
5. At5330/5348, active-only reshape requests are predicted zero from the resulting
   EW32(v12)/EW16(v14) metadata.5435 requires destination reshape, so accumulator
   snapshot conflict is predicted false. No vector vs1 means dual-source
   serialization/conflict cannot apply. vm=1 disables masked-widen conflict;
   this is not an indexed load, gather, narrow operation or reduction.
6. Full-source normalization at5281 is limited to gather instructions, not this
   MAC. Same-base dedup at5555-5575 is inapplicable: vs2=v12 differs from vd=v8,
   and there is no vector vs1. The subsequent duplicate mask does not inject a
   new reshape request. Whole-register seed and later snapshot stores are not
   interposed between source load and MAC.
7. Legal high-group widening overlap still holds. No matching source snapshot
   is predicted;5753 can enter overlap preparation.5829 computes
   `(12-8)*(128/4)=128`; VL129 makes5843 false. The boundary old vd register is v12,
   predicted already EW32, so capture is not expected to be needed.

All metadata and branch values above are falsifiable source predictions, NOT
measured DUT state or native eligibility. Future VCS must verify architecture
first, then actual raw127, without accepting gain based on these calculations.

## Independent oracle and actual preflight

- Before-image starts from all32 initialized registers and the full wide seed.
  It replaces only offsets1792-1793 in v14 with source128=`0x2280`.
- The MAC reads wide old accumulator128=`0x51004180`; exact result is `0x51013300`.
  It modifies only offsets1536-1539 in v12. All prestart/tail/other VRF bytes are
  checked against an immutable before-image.
- All4096 VRF bytes, both untouched input arrays1536 bytes, two CSR snapshots,
 64-byte recovery buffer, zero trap ledger and723 software checks are verified.
  Post-MAC CSR is `[129,10,0,0]`. Recovery stores v12 element0 to a guarded buffer.
- Actual Spike reports35 vector-write instructions and43 register declarations
  (5504 declared bytes), not4 bytes of declarations. MAC reports v10 and v12:
  v10's entire128 bytes are strictly checked equal to the preimage; v12's entire
  register is checked, allowing only the expected four changed bytes. No declared
  byte is skipped. These declarations are not DUT physical write traffic counts.
- Host oracle independently constructs the full byte image and checks all512
  word results as well; it is not merely a hardcoded PASS/check count.

## Preserved preflight failures

The initial pre-output setup filename rejection is recorded separately.
GAP102B01 failed host `-Werror` for an unused word helper before Spike. A fresh
host v2 added independent checks of every word; old host/builder/tests remain.
GAP102B02 host and Spike executed successfully, but its validator expected only
v12 in the MAC declaration. The original02 FAIL and pins remain. Successor03
strictly audits actual v10 preservation plus v12 output from the sealed02 trace;
it does not mutate old manifests, weaken unknown-byte checks or rerun software.

Review commands, from the integration repository:

```bash
PYTHONPATH=verification/coverage python3 -m unittest \
  test_build_gap102b_preflight_v2 test_qualify_gap102b_preflight_v3
python3 verification/coverage/qualify_gap102b_preflight_v3.py \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/gap102b-widen-acc-vstart-parent-check-20261006-01
```

No runner is launched or new718 membership proposed. Later old-image runtime
budget remains600 seconds; prior GAP102 took299.020 CPU seconds, so plan roughly
five minutes without promising duration or raw coverage increment.
