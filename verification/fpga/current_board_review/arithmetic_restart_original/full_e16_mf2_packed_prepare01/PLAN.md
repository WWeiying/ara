# Original e16/mf2 Full4095 Software Preparation

Original22 inventory has no current original e16/mf2 full4095 acceptance; this is not a duplicate of accepted prefixes or mf4.
Specific original ELF SHA3c15efe93cf3a1cc23e76682afb4990ed23098410739f7b1be2dbc59ca9c1b7a and rebuilt recovery ELF match.
Source is binary-equivalent reconstructed C, not a claim of recovered original C bytes.
Original archived assembly e16/mf2/tu/mu and actual stripped ELF zimm derive vtype15.
Reference profile VLEN128B gives fractional capacity32 uint16 words in low64B of one physical128B register.
Physical input arrays remain1024 uint16 entries=2048B each; business seed initialization32 entries.
Original masks clear/initialize128B, onlylow4B consumed by vlm; upper124B remainzero.
Output retains1026 uint16 physical entries; each call checks34 words=68B with typed005b sentinel/guards.

Sole packed scalar candidate:8 aligned raw64-bit words and one exact4B tail via builtinmemcpy byte pointers;
flat expected4095x9 uint64 ROM294840B plus3x128 masks384B (total295224B).
No dictionary, checksum, call dedup, shorten, history reset, extra RVV, arbitrary neighbor snapshot, or flag sweep.
Originalthree seed RNG loops,25 operations,7 VLs,3 masks and3-or1 original vstarts retain4095 continuous calls;
131040 element comparisons,8190 typed guards,4095 returned-vstart checks,53235 original helper instructions.
Original failure fallback remains verbatim, including combined guard errorcount and diagnostic behavior.

Independent source NO_BLOCKER admits Host+compile only; actual Host pairs original-C and packed-C everyposition,
uses expected flat ROM as independent check against original scalar C, distinguishes mock helper from genuine execution.
Host covers active/prestart/masked/tail/leftguard/rightguard/highbyte/vstart/UB shift64 negatives,
misaligned byte memcpy, protected-page tail width, full128 physical mask and unused backing zeros.
Actual SoC/Spike ELF helper bytes must each match unique original stripped-ELF windows, no compiler-generated RVV.
Final exact independent reference entry then onlyone finite debug rs4000000/120s/768MiB reference and closed full audit,
through EOF including exact boot/HTIF/park. Costtarget<=3M elseHOLD; no DUT authorization.
