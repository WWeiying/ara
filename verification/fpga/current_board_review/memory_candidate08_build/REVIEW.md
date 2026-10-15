# M8 Static Review

NO BLOCKER for the exact AddrGen-only successor to frozen M7.
Approved addrgen.sv SHA256:
1cc40e2669e310ae25e23f5c9ee1f7ee493dc1ac990d70d8b8122f47e93742b2

The translation_req condition now rejects a valid indexed address already
known to be element-misaligned. It uses exactly the predicate used by the
existing local alignment fault. Existing active-predicate/queue/AXI readiness
eligibility remains outside this condition. Non-indexed requests and aligned
indexed requests are unchanged. The local error/vstart/tval path, no-translation
behavior, and same-cycle mmu_valid request suppression remain unchanged.
No CVA6 ownership release or response routing changes are introduced.

Main reports Aquinas cycle evidence confirming the orphan MMU request.
This review independently checks the static mechanism and exact patch, not
a new waveform audit. It does not assert DUT acceptance or eliminate unrelated
indexed translation hazards. Build acceptance is not functional acceptance.

build.py is derived from M7's existing script. It enforces the exact textual
replacement and reviewed SHA, all other537-live-input identities,539 frozen
files,453 compiled records and unchanged settings/simulator.conf (except
required output-root relocation). It rejects existing output: no build retry.
Output: /home/wangwy/fpga_runs/current_board_memory_candidate08.
Existing M6/M7 outputs and running services are not modified.
