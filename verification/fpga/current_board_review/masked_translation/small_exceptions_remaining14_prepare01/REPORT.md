# Preparation Terminal

**READY: 14/14 original source references accepted, not DUT PASS.**
Host17 actual exit0; all14 Spike waits0, all14 separate parser waits0,
all14 preparation-child waits0; reference batch outer command actual exit0.
No reference retry, timeout, DUT, RTL edit or image build.

READY SHA256: `3e3b774785788916e41031ef652c63c8b6e0b9cc507dc9a0dc67e9746006824a`.
Input pins: **1253**, manifest SHA256
`af14d9e229da80413855ac779dd12e4d7c62618008f06797b2e93cfe16fb17a6`.
All reference inputs matched before/after. Exact per-member identities and
commands are in READY/source_proof/input_pins and the actual wait receipts.

| Original single | Actual raw records | Firmware through HTIF | Full scalar checks | Spike seconds | Parser process seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| e8 sc1 | 169855 | 165717 | 5481 | 3.075 | 5.679 |
| e8 sc2 | 169855 | 165717 | 5481 | 3.074 | 5.679 |
| e8 sc3 | 169546 | 164845 | 5481 | 2.924 | 5.779 |
| e8 sc5 | 169546 | 164845 | 5481 | 1.623 | 2.825 |
| e16 sc0 | 170082 | 166273 | 5477 | 2.924 | 5.880 |
| e16 sc1 | 170047 | 166042 | 5481 | 2.924 | 5.679 |
| e16 sc2 | 170047 | 166042 | 5481 | 2.975 | 5.679 |
| e16 sc3 | 169608 | 164906 | 5481 | 3.075 | 5.729 |
| e16 sc5 | 169608 | 164906 | 5481 | 2.924 | 5.679 |
| e32 sc0 | 173029 | 172024 | 5477 | 2.974 | 6.531 |
| e32 sc1 | 172994 | 171801 | 5481 | 2.974 | 5.829 |
| e32 sc2 | 172994 | 171801 | 5481 | 3.024 | 5.780 |
| e32 sc3 | 172555 | 170673 | 5481 | 3.076 | 5.930 |
| e32 sc5 | 172555 | 170673 | 5481 | 3.025 | 5.779 |

Batch elapsed195.889s includes pin checks/process overhead. Total2392321
raw records and76726 scalar checks. Each includes five Spike boot commits;
raw counts also contain original post-HTIF pure parking. Firmware-through-HTIF
is separately measured, not estimated by treating raw count as all business work.
Reference bounds800000 records/120s/256MiB were not enlarged.

All28 new ELFs preserve both original eleven-instruction helper encodings and
the three-instruction capacity encodings against their own archived Linux ELF.
Selected helper executes exactly once; unselected helper/vector PCs are vetoed.
Target actual reads are the original four mapped addresses for scenarios0/1/2,
none for3/5. Target returns VL4 only for0; helper restores VL8 and stores all
eight output elements in every case. Completion handler sees VL8, width-specific
vtype, vstart0/fcsr117/vcsr5. The only trap is the completion S-ecall. All130
outputs, sixteen mask bytes, data/pages/guards and CSR restoration are checked;
only original sc0 final slots5..8 are undefined.

Host17 includes independent C/Python width-packed gold, mutations to data,
guards/PTE/mask, sc0-only undefined scope, exact source opcode/owner checks,
orphan done/deleted lifecycle rejection, real SoC specs without tohost,
CTRL raw0 and error/premature/duplicate exit rejection, exact actual-ELF
main and handler spills with nonzero opaque values, bad SP/address/BE/order,
unknown business stores and missing completion-ecall rejection. These are
synthetic checker probes, not DUT execution. Existing sealed e64 recovery
scripts were read/pinned and not edited or rerun.

For later M9 admission, actual firmware164845..172024 at conservative273
retired/s gives604..630s; +20% gives725..757s. The accepted prior M9 e64 sc1/2
simulator times279.306/265.001s are measured comparators, not predictions for
eight concurrent workers. Fixed1800s/case remains a reasonable proposed bound,
not a guarantee. Parent-authorized future batch is jobs8/service7200s, with
fresh live-capacity gate and independent review before launch. This preparation
contains no launcher and claims neither fourteen DUT PASS nor Linux closure.
