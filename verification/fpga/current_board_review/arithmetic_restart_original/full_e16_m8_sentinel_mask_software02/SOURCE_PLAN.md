# Single e16/m8 Sentinel and Mask Successor

Parent authorized short C tests, one GCC invocation per SoC/Spike backend,
and linked static CFG cost. No Spike/reference/VCS/fullstream checker Host.
Hilbert static strategy review SHA dd60d6f1f7bec6075a0468ec8932e82ec80f31f0e409d8760f211968c250fd97.
case.c is byte-identical to full_e16_m8_block_unrolled01/case.c.
Only packed.h changes: each full block ID0 uses one per-call typed u64
sentinel, other IDs retain exact eight original gold loads/equality early
return. Original4B tail expression stays untouched. Mask only expands the
original16 memcpy8 calls, maintaining128B full stores and group phase.
Original dictionary/header/sequence/helper/runtime are immutable include
or link inputs, never regenerated or modified. All4095 history, fresh
1028B, guards, original fallback/errors/CSR remain. No sticky or extraRVV.
Theory is not net compiled saving or less-than3h DUT admission.
