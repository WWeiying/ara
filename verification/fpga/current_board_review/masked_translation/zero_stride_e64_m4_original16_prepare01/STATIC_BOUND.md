# Pre-execution reference bound

The software was compiled before this assessment. No reference has yet run.
`software01/spike.dis` SHA
`20413dd3115b5a7e04b5838d71af859d3ff46344efcf77527d159af43a8eef05`.

Successful-path conservative retired-instruction accounting:

| Region in actual Spike ELF | Bound |
| --- | ---: |
| Full original memory oracle, 0x80000bbe..0x80000c58 and side branches: 16 * 1024 words * 220 instructions, including eight logical-element iterations, active(), check() | 3,604,480 |
| Source/setup: 16 * (1024 memory + 512 offsets + 514 output + 64 input + 64 mask + 160 snapshot words) * 16 | 598,528 |
| Eight original unmapped page refills, 8 * 512 * 16 | 65,536 |
| Full output+result checks, 16 * 64 * 120 | 122,880 |
| Twelve fault handlers plus sixteen S ecalls, 28 * 4000 | 112,000 |
| Initial BSS, 1536 page-table entries, logs, CSR save/restore, bootstrap, 16 case boundaries, printing/exit: allowance | 300,000 |
| Total | 4,803,424 |

Round to **5,200,000** successful-path retired instructions. The full-memory
inner loop at 0x80000bd0..0x80000bec has nine instructions per ordinary
logical element, maximum eight iterations. The rare matching-word path calls
active(); its total is still within the per-word allowance. Division latency
is not a retired-instruction multiplier; it can affect later VCS walltime.
These bounds do not assume removing any oracle, predecessor, or initialization.
If the software takes an unexpected repeated-fault path, the finite reference
ceiling below applies rather than asserting completion.

One Spike invocation only: **8,000,000 steps / 120 s / 1 GiB trace-file cap**,
actual `rv64gcv_zfh_zvfh_zvl1024b`, `--priv=msu --pmpregions=0 -m2`.
Actual ELF hashes and these limits are in `software01/bound.json` before run.
All input pins, including the imported observer and compressed-memory decoder,
are checked before and after execution. Numeric child wait status is persisted
before any audit. Reaching any cap preserves the incomplete reference; no
automatic retry or limit increase.

The cap is a reference resource limit, not a proposed DUT timeout. Retired-count
and raw-size estimates are not pass evidence. Later VCS timing must use the
actual new reference count; the measured related M6 negative-stride STORE
rate (851704 firmware retires / 1111.624555705 s = 766.18/s) is only a proxy.
