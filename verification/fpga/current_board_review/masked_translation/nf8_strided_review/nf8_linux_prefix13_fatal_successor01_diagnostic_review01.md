# NF8 Fatal Successor Focused Review

2026-10-12. Read-only follow-up requested by Tesla; only fatal-output delta
reviewed. No compiler, native tests, DUT, QEMU or simulation executed.

NO BLOCKER for this narrow repair, with output limitations below. This does
not authorize execution or certify arbitrary malformed Linux signal frames.
The build03 review and its fatal-evidence finding remain historical evidence.

Compared with build03, diagnostic.c changes only quit(): fatal handler exits
invoke diag_fatal_emit(code,faults,handler_errors), then retain exit_group(code).
The separate header appends scalar fixed-buffer formatting. It reads only
already recorded scalar fields and literal strings, not ctx/datap or the
fatal_message pointer. Normal handler return, repair, poison, original checks
and prefix13 cut are unchanged. No longjmp or recovery diversion is added.

The full field list occupies841 bytes including newline, below1024. Each append
reserves the last byte for newline; there is exactly one write attempt and no
short-write retry. Existing disassembly shows write ecall at0x10500, followed
by exit_group at0x10518 with the original code restored. Formatter/quit use
scalar operations, not additional vector/FP work. A returned I/O failure does
not prevent exit2 or create a PASS path.

Limitations: a blocking descriptor can delay write; short/error writes can lose
output. Fatal output preserves the current trial's first captured signal and
sticky check only, not prior trials' records or a later repeated signal's PC.
It emits no fatal-message string; signals/frame_valid/check narrow the failure
class but do not replace an explicit reason string. Normal completed output
still contains all13 records. These are diagnostic scope limits, not full
history acceptance. Fatal context paths now attempt observable output rather
than silently discarding the current record as build03 did.

Reviewed identities under nf8_linux_prefix13_diagnostic01/fatal_successor01:

- diagnostic.h: `f4838b687afe5daa7f872515bf6969be934fe665a05a9ed491e6577aa59f72bf`
- build01/diagnostic.c: `05fd0fc4f8c223ac1c7bfdf6d194f3f5acba7f5edbeeffceef6f261d8a54329f`
- build01/proof.json: `dd0cfa4f3a656490d82560ad2d700c0f899e3ce2e266201b05f4f96455c764c8`
- ELF: `e7ce9267d6bdba32cdfe23af2f511bf50e7c0be662b19eebdf3a72438f283659`

Producer native formatter tests were not consumed or claimed in this review.
