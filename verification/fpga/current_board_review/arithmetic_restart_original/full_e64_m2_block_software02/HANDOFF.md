# e64/m2 Software02 Actual Artifacts

Authoritative successful artifact result: audit_artifacts02/RESULT.json.
Status HOST_COMPILED_FULL_CFG_ELIGIBLE_REFERENCE_NOT_AUTHORIZED.
No Spike, VCS, RTL build/change, reference acceptance or Linux closure.
Original software01 COST_HOLD and all sealed inputs remain unchanged.

## Lifecycle and Actual Numeric Outcomes

The first software02 wrapper exited1/42.129382926s after35 Host outcomes and
the SoC GCC0. The exact cause was an overstrict symbol-name check requiring
refresh_fp_period; GCC actually emitted refresh_fp_period.constprop.0.
prepare.py, execution_receipt.json, execution_terminal.json and logs are retained.
No Host or completed compiler invocation was rerun to correct that observer.

finish_artifacts01 compiled only the previously undispatched reference-artifact
ELF. Its GCC exited0; completion wrapper exited1/2.070385154s because the old
assembly text reader swallowed the next stripped instruction after a ret.
The source report and receipts for this second observer failure remain intact.
It is not a firmware/DUT failure. No optimization was disabled as a workaround.

audit_artifacts02 is a readonly closed-artifact successor, with a horizontal-
whitespace, line-by-line parser. It explicitly retains ret10898 and the next
helper's first instruction1089a, requiring all original unique helper windows.
Actual audit wait0/1.419058743s,444 pre/post pins unchanged. It does not compile
or run Host/reference/DUT. Both GCC artifacts were compiled exactly once:
SoC0/1.269350397s and reference artifact0/1.319745250s.

## Host and Source

35 actual Host outcomes: original and new each13 (positive,11 full result
negative histories, one explicit UB trap), plus nine source-state negatives.
All12 original/new complete non-UB transcripts match byte for byte.
Every complete result run covers5985calls/191520results/11970guards,
1890FPcalls and verified120960 destination-write receipts.
The added receipt checks each a[i],b[i] ordering, not only final values.
Nine negatives all return90: omit equal-value a/b stores, swap, duplicate,
missing VL0 refresh, missing next-seed RNG, stale FP seed, missing fresh
output and mask upper-byte clear. Exact witnesses are in host_*/case0.log.
Prior per-position result/prestart/mask/tail/guard/vstart/NaN/signzero negatives,
UBSan, full272B output/128B mask PROT_NONE and exterior guard checks remain.
Host helpers are mocks with independent original C vs bit-model comparisons;
they do not establish vector architectural correctness.

Source delta is only the independently reviewed FP8 period helper and its call.
Mask128B per-group clear, original seed/RNG/trial order, dictionary/fifth16B
block, fresh272B output, fallback and original CSR history are unchanged.
Original scope35ops/5985, CAP32/physical2full256B, u64guards0x5b is retained.
No fflags acceptance/reset is introduced; no original CSR scope is expanded.

## Actual ELF and Clone Semantics

Audit accepts exactly the observed refresh_fp_period.constprop.0 symbol,
rejects any other/extra clone and binds its complete extent and sole main JAL.
The actual seed argument is a0 loaded from seed's stack32 slot. The call is
guarded by op>24, not VL/vstart/equal-value, and all later trials revisit it.
Symbolic source-address analysis of each actual path proves fresh eight table
LDs then64 ordered SDs to exact a/b offsets0..248 with original bit-index mapping.
Seed0/1/2 leaf counts are83/81/83; actual caller argument/spill/return path7.
The cache is within every call. All1890 FP calls preserve120960 writes.

Both artifacts preserve458 exact unique original helper instructions, no
extraRVV, original640FP64 bits/5120B matched uniquely, exact dictionary and all
5985x5 indices. Actual34 SD fresh and34 LD compare cover all272B; last block
reads only16B. Mask16 zero-SD decoded addresses0,8,...,120 have no branch/call/
hardware fence/RVV. Main frame288B, stack gap868448B SoC/860056B reference.
All explicit frame allocations fit the64KiB reserve.

SoC ELF SHA4d99a658c744e1cf9d6ab193cc34c6de73bd268505585759ad7038b8f7abc897.
Reference-artifact SHA dc746ebf6b5978f7901d923cc741747e7ce35bb1693fab3b70df0a5a11a7127c.

## Full Actual Linked CFG Cost

Actual per-PC regions and source multiplicities give mandatory core2159325
and conservative successful-path upper2330297. Original upper3074202:
net saving743905, meeting>=75000 and<=3000000. Includes all actual FP caller
spills, changed main/prologue, mask predicates, RNG, loop control, BSS zeroing
and unchanged20000 terminal/runtime allowance. This is not constructive686070
subtraction and is not a retired-firmware measurement; actual firmware count
remains unknown. Failing fallback execution timing is not guaranteed.

RESULT SHA072c572423903b64cc71cb2d34b3f2200bf32fc570deeb3e906b0ad34f751f09.
Pins SHA18ea993c5e0c6f8c1fccca6ae8cf51954eddee9ecc64ee96bd798755bd66b04a.
Audit numeric receipt SHA8caf4afdd557f62df6af0f49f6dabfe12d012363c64d362e96f439c4771341e6.
Hilbert exact-artifact independent review requested. No simulator authorization
is implied; do not overwrite either historical ERROR or software01 HOLD.
