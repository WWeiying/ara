# 1 GHz：请求与 credit 优化后的寄存器时序

基线为全设计 DC 的 `ara_payload_credit_20261122_01`（不是工作区中的任意旧网表）。以下为布局前 TT、0.9 V、25 °C，`clk_i` 周期 1.000 ns、setup uncertainty 0.150 ns 的结果。

| DC 的 clk_i setup | 上一轮 nofrontreg | 本次修改前的 payload-credit |
|---|---:|---:|
| WNS (ns) | −0.278 | −0.133 |
| TNS (ns) | −4738.377 | −1235.585 |
| 违例端点 | 48105 | 18870 |

父报告在 `~/dc_runs/ara_payload_credit_20261122_01/backend/syn/ara_soc/v1-dc/reports/`；定向路径由同一个映射后 DDC 提取，在 `~/dc_runs/ara_after_credit_scoped_20261122_01/`。以下不是新候选的综合结果。

## 从路径定位修改

| 代表路径（起点 → 终点） | 基线 slack | 本轮如何处理 |
|---|---:|---|
| CVA6 单发射 FU valid → 分支解析 → 加速器请求有效 → Ara 响应 → scoreboard | −0.133 ns | 在原周期比较发射口操作数，EQ/NE 不再使用 ALU 减法零标志。保留分支有效、误预测、异常门控、正常 ALU 隔离及双发射选择。|
| Lane 3 FP 转换流水寄存器 → 两级仲裁 → Resident PV 累加位 | −0.0985 ns | Resident 的独占协议保证原生运算已排空，且这个所有者只发 FMADD。因此只直取 ADDMUL 的结果、标签和标志；仍由原仲裁器负责 valid、ready 和流控。没有移除原生 cast。|
| QBS 专用 I2F 流水寄存器 → 格式/组仲裁及分发 → dot 表项 | −0.0985 ns | 专用端口只有有符号 INT32 转 FP32 一种请求。保留 FPnew 的转换核、中间流水寄存器、RNE、异常标志和表项标签，省去两个没有其他生产者的选择器。未拆分 issue 的配置仍走原实现。|
| Lane 0 QBS 借用操作数 → 共享整数乘法器 → VMFPU 结果队列 | −0.1288 ns | 未改。本路径经过压缩树与 EW8 无寄存器旁路，不能仅凭“所有者不同”就把整个乘法器声明为假路径。|
| MMU 异常状态 → 物理范围检查 → reader 响应 → AKV V 地址更新 | −0.0844 ns | 未改。不能因终点名为地址寄存器就归因为一个加法器慢。|

* 标量最差路径：比较结果到达 0.327 ns，请求有效到达 Ara 约 0.389 ns，响应约 0.793 ns，scoreboard D 为 0.968 ns。修改针对前半段；不会凭空消除 Ara 请求到响应的 0.404 ns。
* Resident PV 的 4096 个累加位合计贡献约 −305.37 ns TNS，约占全组 24.7%。这是这些**终点**的负裕量，不代表每个终点都只从 cast 出发，也不代表能回收 305 ns。原生 ADDMUL 结果与写回选择仍是实在的路径。
* QBS dot/aux 两组各有 512 个违例终点，TNS 分别约 −36.38/−36.56 ns。所提取的 dot 代表路径在格式封装输出为 0.8432 ns，两级仲裁后为 0.8830 ns，表项 D 为 0.9394 ns。保留转换核也意味着其内部延时仍在。
* 共享整数乘法器代表路径：操作数到达 core 为 0.1210 ns，slice sum 为 0.7252 ns，乘法器输出为 0.9069 ns，队列 D 为 0.9666 ns。若新综合仍由它主导，优先比较保持 EW8 延迟的旁路重构与增加一级流水的代价；必须单独验证 QBS 借用和原生 RVV 的吞吐。

## 如何判断是否改善

对比同样约束下完整综合的 WNS、TNS、违例数和面积；分别重取以上代表终点的最差起点。除了确认不合理的数据连接消失，还要看是否由另一个真实源替代、是否变成更严重的违例。定向仿真只证明行为，不代替静态时序分析。不设置 false/multicycle path，不修改时钟约束。本轮针对 setup；父版 hold WNS 为 −0.150 ns，不能据此推断 hold 已收敛。

## 验证与本轮运行入口

* [单发射分支 VCS 对照](../out/cva6_single_branch_independent_20261122_03/report.json)：启用/禁用压缩指令各 51,208 次，含无效周期、误预测、跳转、比较边界；负对照能检出故意注入的错误。不是完整处理器的形式证明。
* [QBS 浮点转换对照](out_qbs_cast_equiv_20261122_03/report.json)：前后版完整累加器三种配置做周期对照；另以整数实现的 RNE 参考检查 3,657 个转换、异常标志和标签，含 2,382 次非精确舍入。
* [首轮整芯片运行状态](../out/ex-fp-credit-20261122-02/status.json) 与 [输入和配置](../out/ex-fp-credit-20261122-02/plan.json)：旧参考镜像在 Resident QK 的 FS-off 场景失败。该次未构建候选、未启动 DC；保留原始 FAIL，不能引用其预建目录为综合结果。
* [失败定位与短 VCS 对照](resident_fs_csr_20261123_01/REPORT.md)：旧参考的 `core/commit_stage.sv` 遗漏仓库已登记的退休限定补丁。异常本身正确；错误是未退休请求将 FS 置 Dirty，使陷阱处理程序走错了 CSR 采样分支。时序分支的四个改动均不是该失败的原因。
* 后续配对必须用“仅恢复退休限定”的参考与“同一修复＋四个时序文件”的候选，保留两个原始 Resident ELF 和七个代表程序。实际 VCS/DC 输入必须核对 `commit_stage.sv` 为 `ce293df18df94a81a0e4fe99ebc798a356c437219de79d79f900bf2362f93249`。不接受两份缺少同一补丁的镜像彼此对上。历史 DC 未含此正确性修复；与其比较面积、WNS 或 TNS 时，不应把差值全部归给时序优化。
* CVA6 的分支时序改动可用独立补丁 `hardware/patches/cva6/single-issue-branch-timing.patch` 重建；退休修复本身已在 `verification/patches/cva6-local-fixes.patch` 登记，不要重复应用整包。
