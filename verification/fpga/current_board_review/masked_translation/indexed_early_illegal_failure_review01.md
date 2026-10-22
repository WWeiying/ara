# 索引 Store 不对齐异常后的整机停滞

## 已测事实

镜像为封存 M7，源码没有因本次测试再修改。
程序及独立参考见 `indexed_early_illegal_sv39_prepare01/PLAN.md`。
e64/m1、VL3、mask=0x06 的有序索引 store 依次跳过元素0、写入合法元素1，
然后在元素2的地址 `0x40000011` 触发不对齐异常。
参考模型已通过完整输入、前缀、同 PC 重试及后继访存检查。

`vcs_m7_indexed01/complete.json` 为 NOT_PASS/TIMEOUT，仿真用时
900.107秒；真实子进程凭据为 returncode255、timed_out=true，没有软件
失败标记。这个结果不能称为通过，也不因没有失败标记而排除硬件停滞。

关闭后的 `commit_trace.csv` 表明：

- 第79705周期，目标 uop18完成，CVX返回异常。
- 陷阱处理函数已经进入，最后两条退休为 `0x80000bf8` 的 AUIPC 和
  `0x80000bfc` 的 ADDI，形成 `mt_trap_count` 地址 `0x80008078`。
- 下一条 `0x80000c00` 是 `ld t1,0(t0)`，没有退休；尚未执行 CSR 读取。

因此首先调查标量 load 的阻塞路径。原先“SLDU 未完成导致全局等待”
只是候选，当前证据不支持：索引访存的 target_vfus 不包含 SLDU，索引源
经 lane 的 SlideAddrGenA 队列直接供给 AddrGen，而且目标 uop 已完成。

## 周期测量确认的根因

AddrGen 的 indexed_data 在地址不对齐时设置 `idx_op_error_d`，结束
AXI 地址生成并准备异常；其后的 translation_req 条件仍可能对同一地址
置位 `mmu_req_d`。外部请求是 `mmu_req_d & ~mmu_valid_i`。

CVA6 的 load_store_unit MMU 仲裁在 CVA6 状态收到 accelerator 请求后
进入 ACC；只有 `translation_valid` 才返回 CVA6。若本地不对齐异常在
仲裁切换前撤销了请求，可能出现 ACC 已占用而实际 translation_req 为0，
没有回应可释放仲裁。此时 `lsu_ctrl.valid` 被门控为0，标量 load 无法推进。

同镜像、同 ELF 的一次有界 FSDB 观测已经确认该链路，文件位于
`indexed_early_illegal_sv39_prepare01/diagnostic01`。该观测运行至85000ns
按计划退出0，没有等待宿主超时；其 scalar retirement CSV 与原失败
CSV逐字节一致，避免把探针改变执行行为的结果当作原反例。

| 周期 | 实际观察 |
| --- | --- |
| 79692 | 索引地址为0x40000011，idx_op_error=1；MMU req=1、valid=0；仲裁当前为CVA6，下一状态为ACC，此时实际translation_req尚为0 |
| 79693 | AddrGen已回IDLE、req=0；仲裁为ACC，translation_req/valid均为0 |
| 79705 | Store pending清零，向量异常响应及目标完成已经产生，MMU仍为ACC |
| 79713 | Ara已idle，异常flush完成；MMU仍为ACC |
| 79736 | handler的0x80008078标量load进入bypass，count=1；load valid仍被门控为0 |
| 82984 | 同一标量load仍滞留，MMU仲裁、请求及响应保持上述停滞状态 |

窗口内 Ara AW/W/B完整配对为1/1/1。正常索引翻译之后，新的不对齐请求
明确触发了这次仲裁转移；不能归因于合法前缀的B未返回或Ara未flush。
浅层dump没有直接导出完整lsu_ctrl结构，门控依据实际bypass占用、load
地址/valid和已核对的仲裁源码；不把未导出的结构字段写成实测信号。

## 修复候选

当前 AddrGen 的 translation_req 仅允许有效且对齐的 indexed 地址。
非indexed条件保持原样，合法indexed路径不增加流水级或等待周期；本地
不对齐异常仍按原cause/vstart路径完成，只是不再误占MMU。
没有在CVA6侧按请求撤销强制释放仲裁，以免错误归属在途的翻译回应。

当前候选 AddrGen SHA256：
`1cc40e2669e310ae25e23f5c9ee1f7ee493dc1ac990d70d8b8122f47e93742b2`。
M8 已用同一 ELF、同一checker完成966项整机检查；完整20项回归也已
通过，最终终态为 `PASS_M8_RECOVERY3_CONTROLS16_RESIDENT1`。

## 修后同程序验收

结果位于 `memory_candidate08_recovery19/prepared01/indexed1/tests/`
`indexed_prefix_vl3`。实际子进程退出0，用时262.724秒，没有超时、软件
失败或中止；checker实际退出0，发布 `INDEXED_PREFIX_CSV_PASS`。
完整CSV为162118行、161805条退休记录，最终周期203634。

原M7停在handler第一条标量load之后；M8继续完成实际vstart读取（79830）、
前缀内存检查（92136）、前缀poison（92182）、索引修复（92229）、
恢复vstart2（92260）及同PC重试（92328）。后继不同源的索引store、
masked load/add和较新的scalar store均执行，966项完整检查及14项原CSR
恢复读取通过，输出软件PASS与正常tohost结束。

这次介入只更改翻译请求资格。M7实测反例、独立源码审查和M8同输入恢复
共同支持根因与修复；不需要通过另一次全量波形运行替代已完成的验收。
16项正常控制全部通过，310350行完整周期记录与M7一致。完整50轮
resident indexed load通过5215检查，836502行记录与已接受M6基线一致。
合计1146852行的周期和非周期字段均无变化。两个VL9缺页恢复程序也
各完成914检查，未中止、未超时，输入哈希校验通过。

这些结果支持当前请求资格修复的功能正确性及上述正常控制的周期不退化。
它们不替代其余原始Linux程序或尚未定位的历史Gather停滞。

## Indexed Load 补充验收

同一M8另有 `indexed_load_misaligned_sv39_prepare01` 的load方向补测：
e64/m1、VL5、初始vstart1、mask0x17，在活动元素2触发cause4/vstart2。
元素0属于prestart，元素1已完成，元素3 inactive，元素4尚未完成，
尾元素5至15需保持。故障快照仅放宽元素2/4的16字节，其他状态严格；
修复索引、保存vstart并同PC重试之后，最终结果没有未定义豁免。

实际子进程退出0，用时303.542秒，`M8_INDEXED_LOAD_MISALIGNED_PASS`。
962项检查、168631行完整CSV、实际CSR恢复和不同源后继访存通过；
最终周期214393，输入哈希不变、无超时或中止。该测试补齐load方向及
非零重启起点的真实队列/异常恢复边界，不冒充原Linux失败程序。

## 一次聚焦观测需要的信号

复用同一个 M7、同一个 ELF，用 UCLI 抓取约79000至83000ns的有限窗口；
TB时钟周期为1ns，需同时记录 wall_cycle 校准复位偏移。

1. AddrGen两级FSM、idx_vaddr_valid/ready、idx_final_vaddr、idx_op_error、
   mmu_req_d/o、MMU valid/exception、ack与early-store异常。
2. CVA6 MMU仲裁状态、acc请求/响应、translation_req/valid、
   cva6_translation_req、lsu_ctrl_byp.valid和lsu_ctrl.valid。
3. Store完成、pending-B、Ara在飞/idle、dispatcher异常flush状态。
4. AXI AW/W/B配对、标量load请求/返回及缓存invalidation valid/ready。

上述信号集合用于同一反例的前后对照。修复后必须看到本地不对齐周期
没有额外MMU请求、仲裁可服务标量load，并完成原程序全部结果检查。

旧900秒失败记录保留。聚焦观测到指定窗口末即停止，不等待同样的长超时。
