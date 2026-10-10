# 剩余状态边激励补充记录（2026-09-28）

## 口径

本批仅统计同一 VCS 覆盖编译镜像
`verification/out/dispatcher-state-reset-20260928-01/sim/simv` 下独立检查
PASS 的 48 份 `code.vdb`。合并报告在
`verification/out/dispatcher-state-reset-20260928-01/dve_main_closed/summary.csv`，
输入清单在同目录 `inputs.txt`。这是针对状态边的局部批次，不是历史
510 项 PASS 的重跑，也不是全芯片 signoff 百分比；不同编译镜像的 VDB
不能直接合并。本批没有修改 DUT RTL。

| 实例 FSM | 本批覆盖 | 已补激励 |
| --- | ---: | --- |
| QBS 主 `state_q` | 30/30 | 主状态复位、描述符故障、读请求在途复位 |
| AKV 主 `state_q` | 36/36 | 主状态复位、描述符/负载故障、读请求在途复位 |
| QBS 计算 `state_q` | 38/43 | 两 K 块、多行、真实 Q6_K 延迟权重、M8、故障及 11 个阶段复位 |
| Dispatcher `lsu_ex_state_q` | 10/10 | `LSU_FLUSH` 与 `LSU_FLUSH_WAIT` 复位 |
| Dispatcher 主 `state_q` | 51/82 | 13 个 overlap/snapshot 阶段复位及正常重叠执行 |

可重复运行的定向矩阵分别是
`verification/uvm/run_qbs_compute_reset_matrix.sh`、
`verification/uvm/run_main_engine_reset_matrix.sh` 和
`verification/uvm/run_dispatcher_reset_matrix.sh`。QBS M8 激励使用合法的
`A_M8_INTERLEAVED` activation 布局；真实 Q6_K 激励使用 Qwen2.5 捕获数据，
`K=1536`。每次测试均保留应用自检、CVXIF/VID/AXI 检查和独立 VDB。
读在途复位分别使用第 1 次向量 AR 握手（QBS/AKV 描述符）和第 2 次
向量 AR 握手（AKV payload）；VDB 检查确认三个目标状态到 IDLE 的边
均被命中。没有使用超时或失败测试填充覆盖率。

## 尚未闭合的边及原因

1. QBS 计算 FSM 剩余 5 条都是 `QBS_COMPUTE_TILE`、`QBS_FINAL_DRAIN`、
   `QBS_START_CONTEXT_WAVE`、`QBS_START_WEIGHT`、`QBS_WAIT_WEIGHT` 各自
   到 `QBS_FAULT_DRAIN`。RTL 在这些状态下由 `fault_i` 决定转移；现有
   故障用例在更早的 weight read 阶段报错。下一批应使用可控的、协议
   合法的 read/MMU 故障注入，在指定阶段检查异常原因、地址、在途排空、
   目标寄存器未污染和恢复后下一条命令，再把 PASS VDB 计入。不能仅为
   命中覆盖率而强制内部 FSM 位或任意延长存储延迟。
2. Dispatcher 主 FSM 剩余 31 条边集中于 overlap 状态与
   `WAIT_STORE_RESPONSE`、`WAIT_IDLE_FLUSH` 的交叉组合。后者受
   `ara_store_accepted_i && decode_blocked && ara_req_valid_o &&
   is_store(ara_req_o.op) && !pending_seg_mem_op_q` 等条件约束。
   VCS 的 FSM 提取包含语法上可赋值但可能被互斥前提排除的边。
   应先逐条做接口可达性证明；可达者再构造并发 store/异常激励，
   不可达者提交点位级 waiver，而不是盲目增加随机 seed。
3. PTW 的虚拟化 stage 边在当前 `RVH=0` 配置下不可达，
   access-error 路径还受 SoC `NrPMPEntries=0` 约束。它们需要
   配置级排除/审阅，而不是当前配置下的激励。可达的 PTW flush、
   page-fault、权限边仍应由独立 MMU 定向集覆盖。
4. 已知 FP16 RNE 定向项存在 RTL 自检失败，不能以失败 VDB 填充
   PASS-only 报告；这是正确性缺口，应先定位首错并修复，再重跑覆盖。

本批 DVE 顶层 raw score 为 49.15%，仅反映上述 48 个局部测试，
不能和历史 510 项大集合的顶层数直接比较。下一次发布全设计覆盖率
时，应在一个冻结 RTL 镜像上重跑全部独立 PASS 激励，再执行同源合并。
