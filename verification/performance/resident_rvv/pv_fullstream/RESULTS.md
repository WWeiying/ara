# 源流、驻留 SRAM 和共享 VMFPU 的联合验收

## 结论与范围

`resident_pv_fullstream_20261109_02`：**PASS，69 次执行**，宿主机 VCS。
复用四个真实 StA operand_queue、AKV context SRAM 和四个 production VMFPU，
没有新增乘加器、总线宽度或 context 存储。共享源队列只保持现有队首，不另建系数数组。

这不是 SoC 指令验收：VRF requester/仲裁、CPU decode/CSR/异常/退休及真实 VID final grant
尚未接入。最终 grant 是独立测试激励；普通后续命令通过队列哨兵检查，而非真实 store 执行。
SharedFma=0；不能据此宣称 SharedFma=1 四 lane 或模型端到端已通过。

## 执行与独立核对

- 66 次正常执行：36,976 次 SIMD FMA 接受/返回，2,544 个结果 word 及最终确认。
- 3 次 T9 实际数据重复：1,728 次 FMA，128 个结果 word；中间取消项零结果写/确认/flags。
- 每次每 lane 消费 24 个源 word，源命令仅 pop 一次，随后普通命令的一个哨兵 word 保持完整。
  合计 6,624 个自有源 word、276 次源命令 pop、276 个后续命令哨兵。
- 每 lane 每次提供 25 次一周期返回（含哨兵），共 6,900 次；credit、乱齐和下游反压逐周期记账。
- 每 lane 345 个 native 完成、69 次 acquire/release；native FMA/mul/div/max 与旧 VMFPU 作周期精确对照。
- 14 项 host tests 通过，包括原始算术 body 不变、最小 cluster diff、日志删除/重复/篡改拒绝。
- 父级重新核对 1,414 个 source pins、45 个 image pins 和报告中全部 artifact 哈希，无差异。
  systemd worker 正常退出，`ExecMainStatus=0`。

66 次不是 66 个独立原始模型负载：沿用 context gate 的 63 个支持形状重组和 3 次无注入阻塞重放。
guard 三次使用同一真实 D128/H2/T9 的原始数值 body，仅重映射 ID 与取消后的架构提交预期。
完整特殊浮点/部分 lane 元素覆盖仍分别见前置部件测试，不由本批新增证明。

## 必须等源流排空，而非只等计算结束

父级提交许可为 import 成功完成且 reader 成功完成。cluster 的修改仅新增许可输入，
在 group **授权前**屏蔽 lane result valid；授权后不撤回已承诺的输出。
success/error 两路都保持 importer Done 和 cluster owner，直到 source/reader 完成及最终确认。

刻意停止每 lane 第 18 个源 word 后的供给，令 T9 计算先完成：

| 场景 | 最后 FP 返回 | 首次等待 | 取消 | error terminal | 释放源尾部 | import 完成 | 首写 | 总体退休 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 成功 | 653 | 655 | 无 | 无 | 667 | 698 | 699 | 876 |
| 取消 | 1536 | 1538 | 1550 | 1553 | 1565 | 1598 | 无 | 1599 |

取消后又将尾部冻结到 error terminal 后 12 周期；不能因 cluster 已报错就释放源队列。
第三次执行不 reset/flush，重新通过全部数值、流和哨兵检查。

## 无注入阻塞诊断，不是完整调用加速比

保留真实 native acquire probes；源返回模型为一周期，未模拟真实 VRF 仲裁。
区间从首次源 issue 到所列事件，含首尾周期。

| 实际 tile | T | import 完成 | 最后 FP 返回 | 最终写确认 | 总体退休 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0 | 64 | 1111 | 1133 | 1151 | 1154 |
| 1 | 64 | 1111 | 1133 | 1151 | 1154 |
| 2 | 9 | 185 | 198 | 216 | 219 |

总体退休区间合计 2,527 周期。尚不含实际软件 source 准备、完整 context 生命周期、
dispatcher 维护、真实 requester/写仲裁及 CPU 完成，不能直接和完整 PV helper 周期相除宣称收益。
下一步先量化准备成本，再按 `SOC_INTEGRATION_AUDIT.md` 接入实际架构路径。

## 失败记录保留与测试完善

首轮 `resident_pv_fullstream_agent_20261109_01` 保持 FAIL，不重标为 PASS。
正常 66 次检查通过；guard 原始仿真数值/协议未报错，但 adapter-visible `private_stalls=0`，
不满足继承检查器的覆盖要求。原测试在 adapter **之前**门控输入，不能证明 adapter 内部反压。

后继只在 guard 中增加每 lane 两个真实 valid/not-ready 返回阻塞周期，并精确核对其日志。
原 ownership checker 原样保留，最终每 lane `private_stalls=6`。算术 oracle、生产 RTL、
源流及提交规则均未修改。失败证据及其冻结输入仍保留，后继使用独立目录和独立镜像。

## 证据定位

目录位于唯一验证工作树 `verification/out/resident_pv_fullstream_20261109_02/`：
`report.json`、`work/normal.log`、`work/guard.log`、`work/commands.json`、`source-pins*.json`、
`work/image-pins.json` 和 `cluster.diff`。运行前后 source inventories 完全相同。

报告 SHA256：`8db66e64102125eff2a6dbb7052e7db16b931240a4c2e7f4cff80dbeca41545e`。
