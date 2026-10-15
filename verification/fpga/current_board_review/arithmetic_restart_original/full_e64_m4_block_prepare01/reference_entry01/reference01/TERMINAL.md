# Full e64/m4 reference terminal

Status: approved-checker software reference PASS, not DUT acceptance and not
a claim of independent full-raw re-audit. No VCS or RTL change.

The sole reference used the approved unchanged Spike ELF
`42e53dc666391e88db7c2d436f7972cda362b575ca9e26806110841fecce51ae`,
profile `rv64gcv_zvl1024b`, rs4M/quit,120s/768MiB. Child actual wait0,
3.7283666720613837s, no timeout/retry. The single complete offline parse
returned actual0 in180.0131681766361s within600s. The outer executor's
actual exit0 is separately recorded in `executor_wait_receipt.json`.

Measured firmware to HTIF:2,804,792 (<3M); firmware to software exit:
2,804,786. Whole raw2,805,000 rows includes5 bootstrap and203 pure park rows.
The final HTIF1, software return0, complete exact marker and EOF were checked.
Raw277,359,345B SHA:
`906c03b17c1e142cd378f63438b2520753c877e4fe05ce0be1a1208e8facf51b`.
Raw identity and all entry/input pins remained unchanged across the audit.

Full scope checked, without partitions or history reset:

- 5985 original calls/35ops/3seeds,383040 result words,11970 guards,
  5985 returned-vstart0,77805 helper instructions, capacity3 once.
- Each call528B/66 actual and66 expected LD:395010 each;53865 dictionary
  ID reads including each final16B block;395010 equal sticky BEQ,
  5985 flag initializations. Original full oracle and fallback unchanged.
- 1890 FP calls,241920 ordered FP input SDs,552 original RNG stores.
- 2205 mask groups,35280 clear SDs,77175 cumulative selected SBs.
- Four physical128B registers per group,512B observed group,typed u64
  guard0x5b. Original source has no fflags oracle.

Bindings:

- Exact entry: `41b945d40245cbb661d0ff8b014250e155d80c790eb0e97b32a274c974de72a2`.
- Independent entry review: `7815c4f599d1b941a00494a33fa7c53164398b5b5ba96ab4fe90b7ad52d6241e`.
- READY: `156d039c5009f31b4ae4e6928ccf57e3284f2153926522aa01b84a02dd8e8737`.
- result.json: `042e258f88415d47802331438b1e73552a9537fab6e571195693b41dc2b038d5`.
- execution.json: `b4eba6fd27095d6caa752572f8f56cede39b24ce87b22c4b56893a371a3ac09f`.
- audit_execution.json: `24d3bc3f0962697194daf34cb091937e62b145b74e9e08a5588b830a9ec20896`.

The reviewed three omitted failure-path PCs remain fail-closed; no entry
patch or bypass was made. Their diagnostic/frame568/520 limitation remains
as documented by the independent review. Old software01 HOLD and Host01
failure are preserved. Reference instruction cost is not measured VCS time;
current-image full regression has not been executed by this task.
