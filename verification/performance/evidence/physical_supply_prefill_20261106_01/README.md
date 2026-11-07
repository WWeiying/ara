# Physical supply: completed Prefill decision

Both completed children, their source/image inventories, raw guest records and
independent protocol identities were replayed without rerunning VCS. The parent
receipt is also terminal and its 1634 source pins match. `result.json` binds these
external artifacts; this directory is a compact record, not their replacement.

| Complete measured SDK region | 128-bit physical RAM | 256-bit physical RAM | Speedup |
| --- | ---: | ---: | ---: |
| Decode: seven N128 prefixes, full K | 227810 | 194611 | 1.17059x |
| Prefill: M4, full QKV N, K2048 | 803294 | 759604 | 1.05752x |

These are different workloads. Both include activation preparation and admission,
but exclude cold weight repack. Matrix arithmetic is identical within each pair.
The Decode result is bound separately under `physical_supply_decode_20261106_01`.

## Consequence for resource selection

The wider path is a credible Decode supply optimization, not a general argument
for doubling compute resources or predicting model speedup from AXI width.
Prefill misses the preliminary 10% region-cycle-reduction screen. Its R beats
fall from 404608 to 240768, but the weight and activation payload byte counts and
524288 dot-issue cycles do not change. Only 37216 QBS busy cycles disappear.
The remaining measured weight-prefetch wait is 22231 cycles; even removing that
entire counter cannot save more than its magnitude in the 759604-cycle region,
and may save less because counter activity is not proof of criticality.

Do not further widen this path before comparing its physical resource cost with
data reuse and the remaining Attention/software costs. Ordinary RVV, translated
access and the SRAM macro mapping have separate acceptance gates. No synthesis,
area, power or complete-model speedup is claimed by these measurements.
