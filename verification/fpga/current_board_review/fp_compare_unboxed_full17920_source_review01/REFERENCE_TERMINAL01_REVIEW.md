# Full17920 Reference Terminal Review

Decision: **ACCEPTED_FULL17920_REFERENCE_NOT_DUT**. Metadata-only independent
terminal review of the single admitted reference and single closed audit.
No raw semantic parse or raw hash reread, no Host/compile/reference rerun, no
DUT and no e32 observer query/modification were performed by this reviewer.

Actual Spike child exit0/not timed out,7.236188s; actual closed-audit child
exit0/not timed out,218.384610s. Both durable receipts equal COMPLETE's outcomes
and their actual small log hashes match. COMPLETE/result hashes match the
producer's supplied identities;109 current input/approval pins independently
match identical before/after maps. No NOT_ACCEPTED or audit failure marker exists.

Full original source-port scope:17920 calls/286720 result bits/35840 guard values,
17920 returned flags and vstarts,326144 original op-helper instructions plus
capacity3. Lifecycle totals are734720 fresh stores,143360 input LDs,17920 full
LWU output reads and2240 hoisted record LDs. All32 raw scalar seed paths occur
336 times each. This uses fixed DK0 old5b5b and original allowed tails/flags, not
alias-m8 semantics. Caller ABI and actual saved/restored CSR operands are within
the previously admitted checker; no extra post-restore CSR readback is claimed.

Measured firmware through actual HTIF success is2653044,346956 below the3M gate.
The complete raw count2655000 equals5 bootstrap+2653044 firmware+1951 pure park.
The admitted one-pass checker reports EOF pure park and exact full success
console. The producer's pre/post-verified raw identity is
`f87f872f9fa87bb45eefdcaf9c1b60d9e618d1d3dd9f04288a56d01b7c82f8ae`,236711843B;
this terminal review relies on that admitted audit and does not reread raw.

COMPLETE SHA30b18a9051d31e73bc0cf786813c6849bcb87555c621a2554c23535ea0270657;
result SHA42147ec08005540cd6a5416bd1a2682dd8f403c125ffbe9e8f59e923d3464def.
Old source/Host failures and ENTRY01 HOLD remain preserved. This closes software
reference preparation for the full source port only: not DUT acceptance, original
Linux execution/stall closure, measured VCS budget or permission to launch DUT.
