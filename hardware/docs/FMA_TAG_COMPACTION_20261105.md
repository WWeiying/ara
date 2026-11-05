# ADDMUL 专用 tag 精简

## 范围与依据

承接 `AREA_OPTIMIZATION_REVIEW_20261105.md`，本轮只精简共享 ADDMUL 的事务
标签，不修改浮点运算、流水级数、SIMD 并行度、异常规则、队列或 FPGA 副本。
`EnableSharedFma` 仍默认为零。上一紧凑流水候选固定在 `cad2e4950`，
其 32,175.023623 平方微米结果仍属于旧 tag 宽度，不能作为本轮实测面积。

静态检查 `vmfpu.sv` 的 tag 构造和全部返回消费者：

- `operand_a` 的 64 位由 VFREC7/VFRSQRT7 用作原操作数，比较指令用其中
  低位携带逐元素 NV 信息。这些均走 NONCOMP，不能全局删除。
- ADDMUL 的数据来自 FPU result，不消费返回的 operand_a。
- `flag_mask` 和 `control` 用于异常标志及归约中性值处理，继续保留。
- `debug_id`、`debug_ara_op` 只存在于仿真，继续保留，返回顺序断言不削弱。

旧 ADDMUL 映射报告保留了 tag 存储。尚无包含最新共享 FPU 的全 VMFPU/SoC
映射可用于证明整机多省多少；即使本轮部件压缩有效，也必须单独核对集成后
是否已经被常量传播裁剪。这里只批准有界候选和部件比较，不预先宣称整机收益。

## 实现

1. VMFPU 用具名结构体常量 `AddmulTagKeepMask` 指明只省略 operand_a。
2. `simd_fpnew` 的 `SharedFmaTagKeepMask` 仅传给 ADDMUL；DIVSQRT、CONV、
   NONCOMP 的 TagType、输入 tag 和输出仲裁不变。
3. `simd_fma_shared` 的 `TagKeepMask` 默认为全一，原调用者仍获得完整 tag。
   显式选择精简时，generate 常量索引把保留位映射到紧凑内部类型。
4. 核心及两级公共输出寄存器只保存紧凑 tag；外部类型不变，省略位返回零。
   排列依据编译期 `$countones`，没有运行时移位或可变宽 mux。

综合 tag 为 64+8+8=80 位，本轮内部为 8+8=16 位。仿真额外保留调试字段，
因此仿真探针不应硬性要求内部恰好为 16 位，而应检查比外部少 64 位。
`shared_fma_tagpack_soc_monitor.sv` 对四个实际 lane 检查这一点。

默认完整 tag 的行为仍逐位对照冻结旧版；省略语义是显式调用者契约，不是
允许通用 FMA 模块丢弃任意输入。零保留位的泛型配置提供一个常零占位位，
但生产配置保留 16 位，不依赖零宽向量行为。

## 已完成部件验证

证据位于验证工作树 `verification/out/`：

| 项目 | 目录 | 结果 |
|---|---|---|
| 完整 FPU 三方逐周期对照 | shared_fma_tagpack_20261105_03 | PASS |
| 独立 SoftFloat 算术参考 | shared_fma_tagpack_softfloat_20261105_01 | 7,200 组 PASS |

三方对照分别是冻结旧 RTL、新 RTL 默认完整 tag、新 RTL 显式精简 tag。
四种运算组均实际退休：ADDMUL 976、DIVSQRT 475、NONCOMP 496、CONV 496。
总计 12,273 个检查周期，接收 2,492、检查完成 2,443、reset/flush 取消 49；
2,864 次输出阻塞观察，3,192 个多个 opgroup 同时有效的周期。

ready/valid/busy、有效结果及 fflags 必须逐拍相同；默认 tag 与旧版完整
一致，精简 tag 只允许 ADDMUL 的声明省略位为零。独立输入身份表检查重复、
丢失及返回身份，不仅把两份 RTL 相等当作正确。激励含混合精度、随机数据、
特殊浮点值、每元素掩码、标量 boxing、背压及无用 payload 的局部 X。
独立 SoftFloat 检查使用默认完整 tag；tag 精简的精确数据通路保持由三方
逐周期对照补充，不将这两项合称为形式证明。

### 初始测试的范围问题

`_01`、`_02` 失败记录保留。`_02` 周期 196 接收 DIV 请求 id=108，
周期 203 又接收不同格式的 SQRT 请求 id=109。旧版及两个新版均在周期
226、228 重复返回 id=108，独立身份表在第二次返回时报错。

VMFPU 的 `queue_latency_conflict_d`、`latency_transition_stall` 明确阻止
不同指令在任一方为 DIV/SQRT 时重叠。这段直接 FPU 激励绕过了该约束，
不能据此判断 tag 精简失败，也不能说任意直接使用 fpnew 都正确。
第三轮恢复这个发射前提：DIV/SQRT 独占在途指令区间；其他运算组仍交错并
保留多组同时返回和背压压力，检查器未放宽。未修改 DIV/SQRT RTL。
此处仍是部件输入约束说明，不替代真实 VMFPU 集成验收。

## 后台系统验收与综合门槛

入口：`verification/timing/run_shared_fma_tagpack_acceptance.py`。
执行目录：`verification/out/shared_fma_tagpack_acceptance_20261105_02/`。
首轮 `_01` 在 VCS 构建阶段因 bind 参数中的 `$bits(TagType)` 类型引用不能
解析而停止，未运行程序。探针改为读取同宽的常量 `KeepMask`，没有修改 DUT
或放宽位宽检查，首轮日志保留。

保持先验证后综合：

1. 复用已验收旧共享镜像，冻结同一批 ELF；新镜像只替换三个本轮 RTL 文件。
2. 旧有 31 程序加 VFREC7、VFRSQRT7 和六种浮点比较，共 39 个程序、78 次
   运行，最多六路并行。新增八个消费者测试优先运行。
3. 两边必须数值 PASS、正常 EOC、四 lane 请求完整退休。完成时刻、内部
   周期、微内核输出和 lane 活动逐项完全一致，任何差异停止后续批次。
4. 通过后启动一次新旧同库、1 ns / 0.15 ns setup uncertainty 的部件 DC，
   保存两个独立目录。只对候选使能 `SHARED_FMA_COMPACT_TAG`。
5. 报告整个 ADDMUL 面积和所有时序组；没有整机证据不外推 SoC 降幅。

当前只完成部件验证，系统结果和面积结果待后台任务收齐。没有因此启用
生产默认共享开关，也没有触及用户工作区里的其他未提交修改。
