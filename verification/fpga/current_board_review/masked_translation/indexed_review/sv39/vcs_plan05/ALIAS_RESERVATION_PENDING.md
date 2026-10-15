# Not Authorized for Launch Under the New Alias Reservation

The two-worker offline preflight completed without a simulator or service
launch. Plan SHA256:
`622c4663714eb5d1deb638da18522f063473b6f77c079626679ab16a429f3f0f`.

The parent subsequently added an independently authorized one-slot alias job.
Plan05 counts current external simvs but does not reserve an alias slot before
that job starts. Consequently, do not launch plan05 as-is under the updated
coordination requirement. No actual admission gate for this successor has run.

The required admission formula is:

```
other_external_live_simv + max(alias_live_simv, 1) + 2 NF7 <= 8
```

Alias membership must use an exact parent-confirmed service unit or run directory,
not a generic substring. Its one-slot authorization must also be checked, and
NF2/arithmetic remain fully completed with no residual owned processes. All
external jobs remain read-only and must not be stopped or modified.

The available tools do not include `send_input`; direct contact with Averroes
was therefore unavailable. The parent was asked to relay the reservation and
provide the exact alias unit or output directory. Preserve this preflight and
all previous refusals. The per-group 2400/2700-second limits and 33600-second
two-worker service limit remain unchanged. No launch command is issued here.
