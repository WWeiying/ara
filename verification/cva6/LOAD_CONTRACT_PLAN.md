# FPGA Load 路径：一次捕获的定向验证

## 目标与边界

本项是完整 SoC/Linux 门禁前的局部验证，验证候选包内真实的 `lsu_bypass`、
`load_unit` 与 `wt_dcache_ctrl` 如何共同处理异常、旧返回、重试和取消。
它不替代 MMU/PTW、scoreboard/commit、实际 cache array、AXI 或板卡验证。
当前不修改 RTL，先验证 FPGA 特有等待态异常适配的实际行为。

当前输入是 `out/fpga-soc-candidate-20260922-04/package` 中的封装源文件。
runner 冻结源码、类型定义、激励、检查器和命令，输出必须是新目录。原导出、
共享依赖、当前用户工作区和已有证据不覆盖。配置保持 XLEN=64、MMU存在、
两项 load buffer；为隔离检查非幂等顺序规则，测试只配置一个低地址非幂等区域。
这不是完整 Cheshire `gen_cva6_cfg()` 的逐字段替代品。

### 为什么先用这个边界

- 使用真实 cache 控制器产生 `gnt/rvalid`，不独立强制不可能的 grant 或返回。
- cache array 只提供受控 hit/data，miss handler 只接受和归还已发出的 miss。
- 翻译模型在 `translation_req && head.valid` 后一拍提供异常；因此请求不持续时
  异常也不持续。它能验证 load unit 对“单拍”和“可再生”异常的处理，但不能证明
  真实 MMU 的所有异常时序、PMP 权限或 ACC 翻译所有权正确。
- 不把 `data_rvalid` 当架构完成。TLB/NI abort 和 flush kill 也会产生 cache 返回。
- `flush && valid_o` 允许出现内部结果，单独记录为取消边界，不称其已经提交。
  真正 scoreboard 的结果过滤与 ID 重用安全性仍要在后续系统级验证中检查。

## 仿真前的判别假设

| 假设 | 同一次捕获的判别信号 | 区分成功与失败 |
|---|---|---|
| 等待grant的异常依赖cache资源才能完成 | state、translation_req、fault、req/gnt、pop、result | 当前适配应在没有旧返回时零cache接受、一次pop、一次异常结果 |
| 异常覆盖旧load的正常结果 | 旧slot对应逻辑序号、rid、fault、结果ID和内容 | 旧返回先完成旧请求；新异常队头保留，下拍或重试后独立完成 |
| WAIT_PAGE_OFFSET丢失异常等于丢请求 | fault脉冲、conflict、head身份、pop、重新翻译 | 脉冲消失时仍保留队头；冲突解除后完成，不能把延期误判为丢失 |
| kill应答被当作额外指令完成 | 接受的cache尝试、kill、rvalid、pop、valid | 释放一次已分配slot，不额外完成未pop的逻辑请求 |
| flush与grant竞争泄漏slot | 同拍flush/gnt、下一拍kill/rvalid、buffer位图 | 新分配的cache尝试得到回收；被取消指令没有后续有效结果 |
| ID重用把旧结果给新请求 | 独立分配序号、epoch、architectural ID、slot代次 | 数字ID可以复用，但结果必须属于对应的新逻辑请求 |

这些是待验证假设，不是未经测量就宣称的新 bug。MMU=0/NI=0 的跨配置静态反例
记录在 `fpga/reports/LOAD_UNIT_HANDOFF_20260922.md`，不混入当前目标的通过率。

## 一次运行的场景

| 场景 | 关键条件 | 预期 |
|---|---|---|
| back_to_back_hit | 旧返回与新接受同拍 | 两个独立请求各完成一次 |
| wait_grant_misaligned | cache阻塞、未对齐异常 | 零cache接受，正确cause/tval |
| wait_grant_access_fault | cache阻塞、访问异常 | 同上 |
| wait_grant_page_fault | cache阻塞、页异常 | 同上 |
| page_conflict_fault | store地址冲突持续 | 异常不等待冲突解除 |
| wait_grant_return_collision | 旧miss返回撞上新异常 | 旧请求优先，新队头不丢 |
| page_conflict_pulse_collision | 异常脉冲撞旧返回，随后消失 | 记录实际延期，释放冲突后重新翻译完成 |
| tlb_miss_fault | 已接受尝试abort后翻译失败 | kill只回收尝试，异常只完成一次 |
| tlb_miss_retry | 已接受尝试abort后翻译成功 | 两次cache尝试对应一条逻辑请求 |
| nonidempotent_retry | 未清空store/write buffer | 等待清空后重试，非幂等访问走miss路径 |
| accepted_tag_fault | grant后一拍异常 | kill/tag返回与对应请求异常完成一致 |
| flush_old_miss_and_queued_head | 旧在途miss和新等待队头同时flush | 两条都取消，miss排空后复用ID |
| flush_same_accept | flush与新grant同拍 | 取消逻辑请求并回收cache尝试 |
| flush_same_fault | flush与异常结果同拍 | 不计作提交；后继同ID请求结果正常 |
| fault_then_same_id | 已完成异常后复用ID | 不串异常信息，不重复完成 |

预先规划22条逻辑请求、15次cache接受/返回，其中18条完成、4条取消。
这些计数是激励完整性检查，不是测出来的性能数据，也不是指令覆盖率。

## 探针与独立判定

在worktree根目录运行；输出目录必须不存在：

```sh
make -C verification cva6-load-contract \
  CVA6_LOAD_OUT="$PWD/verification/out/load-contract-new"
```

`CVA6_LOAD_PACKAGE` 可显式选择另一份封装，runner会记录其精确输入，不允许覆盖原包。

每拍记录 `pre` 和 `post` 两行 JSON。输入在下降沿后改变，`pre` 在上升沿、
NBA更新前读取，`post` 在该上升沿后1 ns读取寄存器结果，避免把两拍混成一拍。

- 逻辑身份：测试分配序号、flush epoch、请求ID、地址、预期异常类别。
- bypass：输入和队头身份、valid、ready、pop、当前及下一占用。
- load FSM：当前/下一状态、translation request、异常全部有效字段、DTLB hit。
- 顺序条件：page conflict、NI stall、store/write buffer状态、commit ID。
- cache：真实req/gnt、tag/kill、rvalid/rid/data、控制器当前/下一状态。
- buffer：valid/flushed位图及下一值、slot内ID、最后分配slot、读写事件。
- miss：req/ack/return及受控存储模型的在途数。
- 结果：valid、ID、data、exception/cause/tval；flush同拍单独解释。

SV检查器检查每组预期；Python检查器从原始输入和握手重新构造逻辑队列、
cache尝试和取消记录，不信任SV打印的PASS或事务归属。两套账本必须吻合。
截断、重复JSON字段、X/Z、缺失用例、缺失最终记录、未排空、非零退出或断言失败
均不能判PASS。负向host测试会故意破坏ID、返回、异常payload或flush行为。

仿真只有固定2000周期看门狗，设计实验规模远低于此；runner限制一次编译和一次
短运行的墙钟时间。若失败，首先离线检查同一捕获，不能修改超时来掩盖丢完成。

## 后续系统级验证

本项通过后仍须在真实MMU/PTW、WT cache、scoreboard和返回流水中重现关键交叉，
确认真实异常可达性、PMP/页表、flush后退休、ACC共享翻译所有权。

完整SoC仿真应围绕候选包的 `cheshire_soc`，保持板级核心配置，以稀疏AXI存储模型
替代外部DDR物理接口；沿原boot ROM/debug流程启动已匹配的OpenSBI/Linux材料。
不能使用把全部IRQ绑零的普通 `ara_tb` 作为外部中断/Linux整机通过的替代证据。
上板还需独立验证时钟、DDR、设备中断、Linux上下文隔离和真实模型运行。
