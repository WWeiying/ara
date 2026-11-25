# 1 GHz 全设计综合：寄存器时序复核（2026-11-22）

对照为 `ara_main_870cadb9_all_on_20261111_01/attempt_03` 与
`ara_request_lane_timing_nofrontreg_20261121_02`，均在 `/home/wangwy/dc_runs`。
基于各自的 `backend/syn/ara_soc/v1-dc/reports`。时钟 1.000 ns，
setup/hold uncertainty 为 0.150/0.075 ns，TT 0.9 V、25 °C；是布局前报告。
两次之间除了运算单元改动还有 Direct-U 等设计差异，不是单因素对照。

| clk_i | 11 月 11 日 | 11 月 22 日完成的综合 |
|---|---:|---:|
| Setup WNS / TNS (ns) | -0.242 / -3219.841 | -0.278 / -4738.377 |
| Setup 违例端点 | 36914 | 48105 |
| 其中 slack ≤ -0.200 ns（报告精度 1 ps） | 4646 | 9628 |
| 最差路径逻辑级数 / 到达时间 (ns) | 101 / 1.077 | 91 / 1.113 |
| Hold WNS / TNS (ns) | -0.155 / -1699.962 | -0.150 / -1811.353 |
| 单元面积，含宏 (mm²) | 3.59915 | 3.59980 |

## 最差路径与累计负裕量不是一回事

按 `clk_i_max.tim` 的 Startpoint/Endpoint/沿途引脚逐条统计，新报告前
1000 条中，807 条从 CVA6 `alu_valid_q_reg_0_` 发出，并经过授权请求
FIFO 的 **data_o**，不是仅仅穿过 **valid_o**。旧报告同类为 650 条。
807 条中 738 条经 `data_o[165]`；696 条经过 Ara 的 `acc_resp_o[345]`
返回，另外 111 条直接落在 Dispatcher 内。其余路径仍有
QBS 借用乘法器到 Lane VMFPU 的 -0.276 ns；单独消除第一组不可能收敛。

| 最差路径观测点，累计到达时间 (ns) | 旧 | 新 |
|---|---:|---:|
| 标量 ALU 分支比较 | 0.333 | 0.327 |
| 分支解析 | 0.355 | 0.341 |
| FIFO 指令字段到达 Ara 接口 | 0.443 | 0.436 |
| Ara 响应返回 CVA6 | 0.909 | 0.945 |
| 记分牌数据端 | 1.077 | 1.113 |

虽然新 FIFO 输出早了 7 ps，Ara 入口到出口增至 509 ps（原 466 ps），
返回 CVA6 后到记分牌均为 168 ps。所比较的是同族各次最差路径，
终点寄存器位不同。这能定位差异落在哪一段，不能单凭两次编译证明是哪一行 RTL
造成 43 ps 差异。少了 10 级逻辑也没有补偿每级延时和负载的变化。

下表按 **终点归属** 汇总 `violation.rpt` 中 clk_i setup 的所有行，
包括四舍五入为 0.000 但被 DC 标记为 VIOLATED 的端点。累计值来自逐条
显示值求和，略有舍入。终点所在模块不一定是延时起源。

| 终点组 | 当前数量 | 当前 TNS (ns) | 当前 WNS (ns) |
|---|---:|---:|---:|
| Lane（含 Resident Lane） | 21007 | -2317.24 | -0.276 |
| QBS engine（不含 Lane） | 11639 | -627.24 | -0.273 |
| CVA6 issue | 2422 | -596.53 | -0.278 |
| CVA6 EX | 2951 | -343.79 | -0.278 |
| Ara Dispatcher | 817 | -179.17 | -0.276 |
| AKV engine（不含 Resident Lane） | 271 | -29.62 | -0.219 |

* Resident Lane 的 `accum_q` 有 4096 个违例端点，TNS 从 -665.65 增至
  -847.47 ns，占本轮全设计 clk_i TNS 的 17.9%。这里不是 AKV descriptor。
* 标量记分牌 `mem_q` 两轮均为 2120 个端点，TNS 从 -442.80 到
  -520.69 ns。不能将 2120 个端点解释为 2120 个独立的 RTL 缺陷。
* QBS FP 累加数组有 4096 个端点、-210.89 ns TNS，单点最差只有
  -0.074 ns。权重更新计数只有 64 个端点，却达到 -0.273 ns。
  两者要用不同的方法优化。
* 上次改过的 AKV K/V 地址端点最差分别由 -0.235/-0.234 改善到
  -0.215/-0.219 ns，仍未收敛。QBS activation 原累计计数端点是
  -0.231 ns，新分组 credit 寄存器最差 -0.072 ns；这不是整个 adapter 的 WNS。
* Lane VMFPU result queue 的 512 个端点两次均违例，最差
  -0.238 → -0.276 ns。不能凭共享乘法器/FMA 的逐周期测试通过宣称时序改善。

## 修复范围与验收

1. 授权请求 FIFO 保留原来的两项容量、满时背压和空队列同周期发送。
   空时仅根据寄存的占用选择 payload，授权仍控制 valid；
   无效周期的 payload 不是指令。此前的整级请求寄存器方案保持关闭。
2. QBS 的 weight grant 仿照 activation，四个字节一组寄存计数，将前拍
   credit 与历史累计相加。向完成判断转发尚未折入累计的 credit，避免
   延后 ready。每个 adapter 新增 96 位局部权重 credit；不是零面积优化。
3. 不改 SDC、不加 false/multicycle path、不关闭 QBS、AKV 或 Resident。
   对 Resident、VMFPU、AKV 地址、QBS 累加器从已有 DDC 提取指定端点的
   完整路径；在确认反馈、数据选择或写使能哪一段限制时序之前，不给它们加拍。
4. 新一轮 DC 以 11 月 22 日已完成任务为父本，仅替换通过 VCS 的两个
   活动源文件。应对比 WNS、TNS、深违例端点、各终点组和面积，不能以旧的
   最差路径从前 1000 条消失作为收敛证据。

独立看 hold：最差为 CVA6 I-cache 适配器寄存器至 cache SRAM。布局前 TT 的
结果用于定位，不能替代布线、时钟树和快角后的 hold 签核；也不能据此放宽约束。

## 从同一份已映射 DDC 重取的四条路径

原 DDC 未修改；独立报告目录为
`/home/wangwy/dc_runs/ara_nofrontreg_scoped_reports_20261122_01`。
以下分别取对应端点最差路径，其 slack 与原综合报告相符，但不代表同组所有位的起点相同。

| 文件 | 实际 launch → capture | 识别出的组合逻辑 / 建议 |
|---|---|---|
| `resident.tim` | Lane FP cast 的 `mid_pipe_int_fmt_q` → Resident `accum_q[1][60]`，-0.2426 ns | cast slice 结果 0.9587 ns，公共输出 1.0056 ns，Resident 数据输入 1.0286 ns，D 端 1.1037 ns。主要延时已在数据到达累加器之前。Resident 在拥有 FPU 时只发 FMADD；候选是让其直接取得被接受的 FMA 数据，保持仲裁、tag、flags、反压与 ownership 同步，并测独立的 FMA → Resident 路径。不应给整个累加反馈加一拍，或单凭软件不发 cast 就设例外。 |
| `vmfpu.tim` | QBS 借用权重 `weight_q[3]` → 原生 VMFPU 结果队列，-0.2759 ns | 共享乘法器输入 0.1266 ns，Dadda 树分片和 0.9787 ns，乘法器输出 1.0559 ns，队列 D 端 1.1127 ns。不能把主要延迟归给队列。应区分 QBS→QBS、RVV→RVV、跨所有者三类，先对前两类从网表定向取时序，才决定分割乘法树还是拆开结果路由。 |
| `qbs_acc.tim` | QBS FP FMA 的 `mid_pipe_exp_prod_q` → 累加数组，-0.0738 ns | 路径经过舍入，FMA 输出 0.7800 ns，公共结果 0.8367 ns，数组 D 端 0.9233 ns。可预译码目的槽与独立的 seed 写入选择；改写回级需覆盖同槽连续更新、clear 和 pending release。 |
| `akv.tim` | `descriptor_q[40]` → `v_read_address_q[63]`，-0.2194 ns | 到达 1.0755 ns。此前预计算没有切断所有 descriptor → cursor 路径。该段综合网表被扁平优化，不能仅凭引脚名判定是哪一条地址公式；先对首次读取、refill、fault 三种更新使能分开取证，保持 64 位地址与越界行为。 |

原生 VMUL 也有独立证据：全芯片前 1000 条中，`vmul_simd_op_a_q` 到
`result_queue_q` 最差 -0.267 ns，`vmul_simd_op_q` 到同队列最差
-0.270 ns。因此即便彻底隔离 QBS 借用者的输出，也不能解决原生乘法器的时序。

验收证据位于 `verification/out/payload-credit-20261122-01/`。
SoC 的 7 个相同 ELF 均通过，四类可用的计时字段与上轮逐项相同。
AXPY task 1543 周期；Qwen Q4_K 投影 15634 周期。FIFO 参考模型比较
20000 周期；只在 valid 时要求 payload 相等，包括不能握手的停顿周期。
QBS SRAM adapter 通过 81 项配置、完整 65536 种写 strobe 和 81 项零停顿
流式用例；并行参考比对执行到第 246372 个时钟。完整 DC 新目录：
`/home/wangwy/dc_runs/ara_payload_credit_20261122_01`，以
`backend/syn/ara_soc/v1-dc/run/dc.status` 标识工具实际阶段。
这不是 Linux 全模型回归，也不代表新 WNS 或 TNS 已经改善。
