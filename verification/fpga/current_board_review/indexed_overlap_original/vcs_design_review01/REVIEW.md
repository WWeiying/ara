# Indexed overlap: reference03 到 VCS 的只读设计评审

2026-10-11。只写本目录；不修改 references、Tesla worker、RTL，不编译、不跑 Spike/VCS。采用 Averroes 最终 `reference03`、`REFERENCE_REPORT.md`、`REFERENCE_HANDOFF.json` 和 `VCS_CHECKER_BOUNDARY.md`。本文件是 checker/worker 契约评审，不是 DUT PASS，也不是尚未落盘 worker 的代码放行。

## Findings 与输入选择

1. **已修适配器问题，必须排除 reference02。** `reference02/fixture.c:115` 用 uint32 load 读取目标 opcode；ov0 target 仅 2-byte aligned，会产生与 indexed 故障无关的 scalar misaligned 异常。03 `fixture.c:115-118` 用四个 volatile byte load 修复。原 indexed 指令、原 ELF、oracle 均未改变。这不是 DUT/RTL bug，不允许混用 02 ELF 与 03 checker/symbols。
2. **reference gate 不足以当 VCS gate。** `check_reference.py:49-59,83-92` 只检查 target opcode 属于三个候选及总数，未独立验证全部 target 的 PC/opcode、完整 prologue、逐次 PTE/SFENCE/MRET/attempt 顺序。`io_retry_mret` 根本未检查。最终 rounds/minor/maps/unmaps/mask/checks 主要由固件保障，Python 未逐项独立重算。Averroes 确认此边界；新 VCS checker 必须补足，不能改封存 03 来掩盖。
3. **missing-byte 和 store-only shadow 风险。** `check_reference.py:37` 对未观察 byte 默认补零，可能把缺失 error/counter/PTE 证据当有效零；`regs.update` 也未验证 store 的 source/address/mask。VCS 要求 byte 已知，验证真实 RVFI scalar store。仅由 scalar stores 得到 pristine pages 的 shadow 不能排除未被 CSV 记录的非法 vector store，必须验证实际 scalar reload 与最终 checksum/check 比较。
4. **现有 negative coverage 只覆盖点值和 terminal。** `test_oracle.py:10-27` 的 126 负例没有验证 attempts/MRET/prologue/counter/missing-byte ledger；需在新 checker 自己的目录增加相关 fixture，不能把这些旧 negative PASS 当完整新 checker 验证。

最终 reference03 identity：identities SHA `4a5546cc452378cdbdd71a5f5d0fac9bb4cd60f5de8769c9dd6fa49c814f238b`；input pins SHA `43620fbe4885ca490a37cb1fee45afd63630d5a6f4805861ac470ffc0e4d12ea`。三原 Linux ELF 字节一致 rebuild、41 helper encodings 保持，是 reference 身份证据，不是 Linux 执行验收。SoC ELF 和 PC 必须采用同例 `.soc.symbols.json/.soc.dis`，不可用 Spike PC。

| case | SoC SHA256 | 成功 target PC/opcode | checkpoints / reloads | fault attempts / checks / Spike commits |
| --- | --- | --- | --- | --- |
| fault ov1 pilot | 5a73bf57dc9d9cef6136ec8daa53e409c77abd5e0e47645d403392df5310347f | 0x80000d64 / 0645f207 | 50 / 50 | 1650 / 21595 / 1595309 |
| resident ov1 | 85b1da567120fba1d04f2ec11ab6abc5d1898970c55550ed440b1ddc7cf276df | 0x80000cf0 / 0645f207 | 51 / 51 | 51 / 5215 / 840319 |
| fault ov0 | 1c1c653af2c745964b80b7bcc50a9d7c9fb06aaae8c90e6c1d50b57f43c810ad | 0x80000d56 / 0645f807 | 50 / 50 | 1650 / 21595 / 1595309 |

## 可复用部分与不能复制的部分

真实 Sv39 NF2 已验收 adapter：`masked_translation/segment_review/sv39/{csv_check.py,vcs_adapter.py,fixture.S,DUT_REPORT.md}`。可只读复用 `scalar_store(row,regs)`：RVFI BE 按 addr%8 左移、data 未移位；检查 compressed/scalar store source register、base+offset、宽度、mask，之后才更新 byte memory。其 `u64()` 的严格 missing-byte 和 handler CSR/record 相互比对模式也合适。

不能复用 NF2 的 case count、CSR期望、partial-field allowance、COUNTS、image SHA 或 handler vector snapshot/reconstruction：NF2 handler 会 snapshot 并重写 vset/vstart；indexed 03 handler 必须没有 vector data/config 操作，不写 vstart/vtype、不重载 indices、不改 fault mepc。允许纯 CSR read（这些也可能经 CVX transport），不能误禁它们。索引 ov1 的 v4-v5 destination 位于 e64m4 v4-v7 source 的低端，原 narrowing-overlap 合法；不强求已经消费的 prefix index bytes 在 destination 写入后仍不变。

M5 frozen monitor `hardware/tb/ara_commit_monitor.sv:247-300`：RVFI valid 才输出 retire；`cvx_req.pc=0`，只有 insn/trans_id；`cvx_resp` 的 rd_wdata 是 accelerator result，trap 是 exception.valid，**不是 cause/tval**。因此同 PC retry 的证据是 CSR mepc + 实际指令 byte reads + 未修改 mepc + exact MRET + 随后匹配请求，不是给 CVX 的零 PC 填上猜测。通用 `ara_verify.trace.validate_trace` 支持过滤 trapped requests，保留其事务/uop配对检查，不要要求 cvx_exception_count=0。

## 新 checker 的最低严格契约

1. **身份/CSV。** pin 03 21 inputs 与 handoff 58 artifacts，再 pin自己的程序目录/provenance、checker/worker/test/plan/capture TCL及所有 imported helpers。独立核对 ELF64/RISC-V/entry/load ranges、nm/symbols/dis 和原 41 helper instructions；每条 retire PC/encoding 对照实际 SoC ELF（非执行 data 区），order 连续、cycle 非降、字段完整、x0固定0。只允许原因明确的 target/ecall trap；trap 指令不更新 regs/memory。CTRL exit 后仅原 parking，不接受额外副作用。
2. **真实 setup/prologue。** 32768 个 backing uint32 `(i*7919)^0xa5a50f0f`、32 个 uint64 indices `((i*13+7)%32)*4096`、output guards `0x5b12` 要有初始化证据。每 round gather32 参数是 indices、VA0x40000000（fault）或 pages（resident）、output+1、原 overlap 参数；完整原 e64m4 index vset/VL32 -> `02057207` index load -> e32m2 tu/mu VL32 -> 正确分支 target。fault 恰50 prologues，不是1650；resident50+1。handler/retry中不允许 prologue/index reload、vector data/config、vstart/vtype write 或 fault mepc write。
3. **fault attempt ledger。** 按本轮/attempt和在途 trans_id 关联 accepted CVX req/resp，不能只用 opcode 或复用后的裸 trans_id。每 fault round恰32 cause13，vstart n=0..31；共1600 trap responses和1600真实 handler capture。handler读取 cause/mepc/mtval/vstart/vl/vtype/fcsr/vcsr，七项 record必须来自同次读取：[targetPC, VA+((n*13+7)%32)*4096, n,32,17,117,5]。检查 record地址/slot/完整写入及fault_count增量，不得仅检查最终1600条总表。
4. **repair/retry 有序证据。** 每 fault链是 accepted target request -> exception response -> io_handler/CSR -> 本页oldPTE实际读0 -> 单页正确PTE store（flags0xc3、对应physical pages）-> fence -> `io_repair_sfence` 的真实 addressed SFENCE（rs1=tval、rs2=x0）-> `io_retry_mret` exact `30200073` -> 下次同原target的accepted request。中间不能reload或写fault mepc；restore所有被handler保存的scalar regs后，重试参数应相同。next attempt要么下一fault，要么第33次请求成功、一次正确PC target退休、一次原result store，再进入post。不能要求1650 target retire；正常模型是50 success retire +1600 fault chains。如 monitor确实记录 trapping target retire，仅在同链内核验，不用它替代fault链。
5. **每轮完整 oracle。** checkpoint r=0..49顺序唯一；在 post实际 scalar output reload 与 `check(got,want)`参数上复核32完整uint32，不仅相信 io_result stores。idx[i]每次核对、五项最终 CSR `[32,17,0,117,5]`、helper返回32、两guards保持；io_result每行39项的 verified scalar stores必须匹配对应load/check来源和本轮，完整覆盖39项。每post72个check calls。原 C 后续自己的完整oracle/guards仍在原ELF，不截断、不只取低bits错过word；输出有重复load是正常的，不要求全程序仅1600次load。
6. **resident额外原控制。** 50 normal checkpoints全部32值；第51个masked helper独立prologue、VL17/start7/odd mask、v16=-7背景，target `0445f807` 的PC从实际dis定位。只i=7,9,11,13,15取原data，其他27个uint32为`0xfffffff9`；恢复VL32/vtype17/vstart0/CSR、检查完整32值及guards。零cause13、零repairs；51个target成功（normal50+masked1）。不把masked helper当作普通ov1 target。
7. **full memory/PTE/counters/exit。** 最终32768个backing words要按实际scalar reads复算，diff check=0；全部3x512 PTE的实际read/check核对，leaf最终清0，root/mid仅原slots有效。不可用store-only shadow假装vector没有改pages。fault最终 round50/mask0/minor1600/maps50/unmaps50、每round fault_count32、original faults accumulator1600；resident round50/mask1/minor/maps/unmaps均0。独立 check入口 a0==a1 和总calls/io_checks一致：fault21595，resident5215。exit_code0/errors0、done=0x525656303146494e；准确 VECTOR_PASS字符串、INDEXED_ORIGINAL_PASS各一次；原 console/run.vcs.log 中所有FAIL、BOARD_REPLAY_TRAP/MISMATCH、abort、异常exit/timeout均veto。SoC CTRL原返回码0（0xd0000000、原replay_exit SD），不能用Spike tohost=1替代，也不能要求本runtime不存在的 BOARD_CASE_PASS/BOARD_REPLAY_PASS。

新 host negatives至少覆盖：错PC/opcode/branch；missing/extra index reload；missing/duplicate/wrong trans_id response；CSR-record不一致；漏PTE/mask/错sfence地址；漏/错MRET、fault mepc写入；越轮/重复或漏checkpoint；第49轮第31值/guard损坏；residentmasked值错误；source实际load损坏但shadow仍正确；末counter/check count错；缺失零byte被误补0；truncated CSV；PASS后failure；无/重复CTRL。这里是测试设计，不运行旧owner test main。

## Pilot probe 与 bounded worker

先完整 fault ov1，strict CSV/source/image/exit gate通过才跑原resident ov1、fault ov0，最多后两例jobs2；任一首错仅cancel本scope，不重试、不改oracle。M5 image/config/source manifest需要fresh核对，Sv39 OSSupport/PMP0、NrLanes4/VLEN1024/L2与ELF布局匹配；不复制NF2旧candidate02身份。正式新adapter的程序manifest可放Tesla owned目录，引用03 ELF；不要为 integration.prepare.check 要求而改03来源/provenance。

首次pilot的**bounded profile**必须覆盖 initial index capture、partial-write后的再次capture、至少vstart1..5（含四lane word边界），建议直接覆盖round0全部32 fault repairs和首个完整checkpoint，然后关闭dump，剩余49rounds仍完整执行。用首次index prologue/accepted target handshake作触发，设review过的cycle/window硬上限；FSDB缺失/窗口未覆盖只报probe incomplete，不盲目第二轮。若只捕获首次vstart0 fault，尚无部分destination写入，不能区分 retry-corruption 假设。

profile依据PROBE_PLAN，选dispatcher indexed overlap/EEW/维护capture与tag、每lane snapshot valid/index/data和SlideAddrGenA req/ready/VRF operand、AddrGen decoded offset/vstart lane-word counter/accepted idx_final_vaddr、MMU req-vaddr/valid-paddr/exception、VLDU actual final grant+addr+BE+data、sequencer done与exception response，另保留clock/reset与CVX ID。按实际old EEW deshuffle，correlate round/attempt/arch_seq/PE id+generation；不force任何signal、不dump全SoC。M5已有 `+VECTOR_TRACE` 的write source4是真实VLDU VRF grant（`operand_requester.sv:179-184`），可辅助accepted-write证据，但不是内存访问trace，不能凭VRF addr当RAM addr。CVX scalar CSV同样不暴露partial VRF data。

cost仅参考：fault1595309、resident840319 Spike commits；parent rate723/s对应每fault约2207s、resident1162s；本Gather M5两prefix实测约683-687 retired/s，fault约2335s。三例serial估计93-98min，fault/PTW/FSDB与host争用可额外耗时，不能保证。7200s/fault、3600s/resident都是小于3h的**每例**上限，但pilot+controls分stage最坏14400s，不是3h整批保证；正式plan须明确3h是per-ELF还是whole-service。若整scope3h，使用共同10800s deadline和checker/teardown headroom，不改oracle；预算不足终态NOT_ACCEPTED/NOT_RUN，不自动加时。

资源fresh cap24/MemAvailable>=32GiB，按协同family max(actual,reserved)计数、不隐藏潜在simv读取错误。独立unit/cgroup/output；真实cancel进入monitor。启动确认60s内samePID generation两次positive trace/cycle+CPU增长；身份错立即fail，零baseline须rebase第一positive且不重置deadline；fast-finished只有独立完整PASS才可代替startup，不能用summary PASS。确认一次后停止观察长任务。

当前Tesla owns `vcs_candidate05_plan01`。首次读目录尚未可用，之后 `checker.py` 落盘，已只读审查其未封存初稿；其余 worker/negative/preflight/plan SHA仍待ready后审查，本文件不产生DUT授权。初稿发现如下，已发给Tesla，不修改其文件：

- **P1 启动必然 false-negative：** `checker.py:124-125` 在 capture/retry 中禁止所有非target CVX请求；真实handler读取 vstart/vl/vtype/vcsr本来走CVX，因此首次fault或syscall handler会被拒绝。需要允许确切纯 vector CSR reads/运输replay，仍禁止配置/写CSR/vector data/index reload；配对与计数不放松。negative必须带真实handler CSR CVX请求，不仅造scalar retire。
- **P2 完整原setup/output独立证据尚缺：** `checker.py:106-123,156-170` 目前计reload和读取io_result影子；未检查gather32真实args/prologue VL/e64m4配置、逐轮actual indices、32个actual output scalar reload及guards、post对应72个check增量。`self.ops.get(pc)`验证指令属于ELF，不等于验证执行了完整正确prologue。按上面最低契约补齐；不得声称当前已独立核了全部setup/load来源。
- **P2 syscall/终态绑定仍不完整：** `fault_values:145-154` cause9只核CSR集合，没有核合法ecall PC/原syscall寄存器与PC+4返回；`finish:284-291`已补大部分终counter，但尚未独立核原`faults` accumulator。CTRL目前仅地址/宽度/value检查，还需原replay_exit store PC和exit后parking约束。这些由封存固件保证的部分应与独立checker明确分开。

## 验收边界

完整3case支持合法overlap初始路径、真实Sv39 fault/retry路径及non-overlap控制的区分。逐页32 faults是明确adapter discriminator，不是Linux原150 minor faults、SIGSEGV停止round/start、Linux signal frame/context或父矩阵closure。snapshot-valid清除单点不能证明cause；以capture ->真实operand -> MMU exception -> partial VRF grant -> repair/retry的测量链作判别，测量前不主张RTL修复。
