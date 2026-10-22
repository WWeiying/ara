# e32/m2 Exact Reference Entry Review

2026-10-14: NO_BLOCKER_SOURCE_SOFTWARE_FOR_ONE_BOUNDED_REFERENCE_NOT_DUT.

Exact entry: `../full_e32_m2_block_prepare01/reference_entry01/entry.json`, SHA256 `3d0fba95fad58da26cc1cd5b49a8c0f85e4a9522479da4a3dda19d45e6a0bff3`.

This satisfies the parent's conditional permission for Aquinas to execute this one reference attempt. It does not authorize VCS, another reference attempt, a larger budget, or changes to the source/ELFs/oracle. This report does not claim the reference has run or passed.

## Independent Checks

- All 244 entry pins independently rehashed and matched. Exact reference ELF remains `cbe657411501c8cf974d3c6830caea39847563cfa5f6451ef335eca6e5e809e7`; companion unexecuted SoC ELF remains `b9a09a69f9ae8d93b38f5a3f8de1049967a79127ebb473da7f321e73143039f6`. Prior source/artifact/cost reviews remain inputs, not overwritten.
- Focused observer Host receipt has actual integer returncode 0, PID 3326725, elapsed 15.20701659284532 seconds, no timeout, one attempt. All 18 named tests are recorded ok, with final unittest OK. Receipt SHA `58d07d20747d501e8556606926093350b8c3c87698c432d6eda06fb93077f82f`. These are constructed observer tests, not Spike/DUT evidence; no suite was rerun by this reviewer.
- `reference01` did not exist at review. The executor uses exclusive directory creation, pins the independent review and entry, persists actual child returncodes before semantic checks, and has no retry path. Its command is finite `rs 4000000` followed by `quit`, ISA `rv64gcv_zvl1024b`, 2MiB memory, 120s wall limit and 768MiB output-file limit. Offline audit is separately limited to 600s. Firmware through HTIF above 3M produces HOLD, not READY or an automatic budget increase.
- Real main is a tail jump at 0x80001e90 to arithmetic_main, so no hidden wrapper frame invalidates the hashbound 336-byte frame/cache address. The parser requires the actual arithmetic_main SP update. Cache seed preparation checks each original seed's eight source loads and eight cache stores, including exact original source addresses, signed LW values, seed phase and order.
- Every FP call requires the actual 128 cache LW/SW pairs with exact PC, bank, index, width and values before output initialization. Old-equal data cannot excuse a missing store or load. All 1890 calls retain 241920 source SW and 241920 cache LW. The original 552 RNG/override stores remain independently scheduled.
- Mask lifecycle follows the actual compiled paths, including mode1 shared-tail PCs. It requires all sixteen SD clears before the first selected LBU, then matching same-byte LBU and cumulative SB in original index order. It retains 35280 clears and 77175 updates, owned by the original si0 mask groups.
- Full output setup and reads are ordered 33-word events over precisely 264 bytes; both halves of the last word are checked, element63 and uint32 rear guard. Missing initializations, missing reads, wrong widths and equal-value omissions are rejected. No padding or short-tail exemption is used.
- All 5985 calls and their 13 original helper instructions remain ordered, with exact arguments, capacity64, vtype17, target vstart, physical two-register input/old-vd/result groups, actual mask bytes, returned-vstart0, full stores and scalar data/guard checks. Interior helper PCs cannot start an unowned helper window. Capacity has its own exact three-instruction single-use window. VI2 short-VL no-ops retain all helper/setup/oracle requirements.
- Every firmware PC/code must match the pinned ELF. The parser consumes EOF, not just the success marker. It requires the exact five-reset-instruction prefix and single HTIF success store at 0x8000007a. Thereafter only actual parking PC 0x8000007e, instruction 0xa001 and no side effects are accepted. Extra helper, CSR/store activity, changed parking encoding, malformed/trap rows, nonzero exit and incomplete EOF are rejected.
- Full counters, console marker, raw failure veto, helper totals, per-call oracle reads and final lifecycle counts must agree. Original FP bit gold is retained; initial fcsr/RNE is checked but no original fflags oracle is invented.

## Host Coverage And Limits

Inspected focused negatives cover all 128 missing FP stores/loads, wrong bank/value/width/cache slot/order, missing/reordered cache accesses, missing mask clears/bitsets/loads and early bitset activity, every missing output store/read, last-word element/guard corruption, missing/wrong helper ownership, physical group truncation, code drift, malformed/partial raw and exact reset/EOF/parking behavior. The full lifecycle positive is explicitly constructed rather than an ISA run. No additional Host test was necessary for this entry.

Spike provides helper/source lifecycle evidence, not DUT CVX/uop allocation/completion tokens. Those generic DUT transport and owner gates remain a future separate requirement. Approval here is full source-port reference readiness, not Linux historical closure or DUT acceptance.

No compile, Host rerun, Spike, VCS, raw trace parse or live process query was performed by this reviewer. Only existing code, metadata, receipts and hashes were read; only new independent review files were written.
