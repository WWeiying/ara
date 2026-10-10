# 主线 RTL 同步与逐项验收

## 验证对象与边界

主线为 `/home/wangwy/openproject/ara_dsa`，唯一验证工作区为
`/home/wangwy/openproject/ara_dsa_signoff_integration`。本轮同步七份文件，
首次同步保留同步前副本及 SHA-256，未修改主线，也未覆盖 FPGA 导出包。
随后 MVP 根因修复同步修改了两边的两份依赖文件，未修改 FPGA 导出包。
`hardware/src` 和 `hardware/include` 两侧逐文件一致。
验证 TB 保留指定内部状态和指定第几笔读事务触发复位的测试能力；
主线 TB 的门级网表适配属于测试平台差异，不属于处理器功能差异。

不能把代码较新、历史回归通过或仿真成功解释为所有修改均有价值。
首次同步的 MVP 候选在独立审计中失败；随后已针对根因修正并通过178项
FP32/FP64 模块级回归，详见 `verification/fpu/MVP_REPAIR_20260930.md`。
两侧修正文件已再次同步。下面的逐项表和首次审计保留为修复前记录，
不能把历史失败描述当作修复后的结果，也不能把有限专项通过当作完整浮点验收。
两侧 RTL 一致与两侧 RTL 全部正确是两个不同目标。

## 首次同步的逐项评估（修复前）

| 文件 | 修改意图 | 验收方式 | 当前判断 |
| --- | --- | --- | --- |
| `hardware/src/lane/valu.sv` | 用临时 payload 和固定索引整项写入，避免 FPGA 工具对动态字段写与整项清除的处理问题 | 检查窄化半字保持、规约累加、同周期读写清除优先级；新镜像定向/随机回归；同 ELF 周期比较 | 静态优先级一致，主线代表点已通过；全量回归待完成，未重新验证 Vivado 网表 |
| `hardware/src/lane/vmfpu.sv` | 对 FP/MUL 结果队列采用同样写法，保留分次窄化结果 | 检查 `be` 合并、结果及异常标志保持、规约与结果握手；转换/除法定向测试和随机回归 | 静态优先级一致，主线代表点已通过；全量回归待完成 |
| `hardware/deps/fpu_div_sqrt_mvp/hdl/control_mvp.sv` | 用原始部分余数非零判断额外 sticky | 精确 FP64 `1/1`，观察 raw remainder、sticky、结果、NX | 失败：原始非恢复余数非零不等于精确结果存在舍入余数；RUP 得到下一可表示数，RNE 误置 NX |
| `hardware/deps/fpu_div_sqrt_mvp/hdl/nrbd_nrsc_mvp.sv` | 传递余数非零信号 | 检查信号连接及消费含义 | 连接本身存在，但传递的是有缺陷的 exactness 判定，不能独立称为正确性收益 |
| `hardware/deps/fpu_div_sqrt_mvp/hdl/div_sqrt_top_mvp.sv` | 接入余数信号到归一化/舍入路径 | 直接模块级 DIV 测试，检查结果和所有异常标志 | 路径有执行证据；精确除法/溢出失败，不能验收整条路径 |
| `hardware/deps/fpu_div_sqrt_mvp/hdl/norm_div_sqrt_mvp.sv` | sticky 补充、按舍入模式选择 infinity/maxfinite、补充 RMM | 正负溢出、精确值、逐周期进位链；后续完整舍入矩阵 | 部分意图合理，但溢出 infinity 会再次舍入成 NaN；RMM 尚未专项闭环，不能声称整个修改通过 |
| `hardware/deps/fpu_div_sqrt_mvp/hdl/defs_div_sqrt_mvp.sv` | 增加 RMM 编码定义 | 与解码和舍入行为配对验证 | 常量定义不是性能收益；需要 RMM tie/non-tie 定向测试才可验收 |

VALU/VMFPU 的两个写法改动属于一组实现方式调整，不预期产生指令级加速。
其价值应来自综合兼容性且功能/周期不退化，不能用新镜像 PASS 推断面积或时序改善。
本轮不运行 DC、Vivado，不给出新的面积、时序或板卡正确性结论。

## MVP 实测发现

独立输出：`verification/out/main-mvp-evaluation-20260930-01/`。
八笔事务中五笔不满足架构结果/flags，三笔控制测试匹配。
审计工具退出成功表示复现预先声明的问题，不表示 DUT PASS。

1. FP64 `1/1`，RUP：期望 `0x3ff0000000000000`、flags=0，
   实际 `0x3ff0000000000001`、NX=1。
2. FP64 `1/1`，RNE：值相同，但错误置 NX。
3. FP64 正最大有限数除以 0.5，RUP：期望正 infinity，实际 infinity 尾数被进位为1。
4. FP64 负最大有限数除以 0.5，RDN：期望负 infinity，同样发生错误二次舍入。
5. FP32 正最大有限数除以 0.5，RNE：结果是 infinity，但 flags 缺少 NX。
   第五项是既有残留问题，不能归因于本轮候选补丁。

前四项证明候选修改有正确性问题。第五项说明即使撤掉候选修改，
也不能直接宣称 PULP/MVP 替代配置已符合完整浮点语义。
当前 `vmfpu.sv` 与 CVA6 `fpu_wrap.sv` 明确选择 THMULTI；
MVP 代码被编译不等于 MVP 单元被实例化。这些问题不作为 THMULTI 整机失败，
也不能通过排除 MVP 来隐瞒它的专项失败。后续切换到 PULP/MVP 前必须修复并独立验收。

## 新镜像整机回归

入口：`verification/coverage/run_main_alignment_20260930.py`。
构建目录：`verification/out/main-aligned-build-20260930-01/`。
回归目录：`verification/out/main-aligned-600-20260930-01/`。

- 独立构建 VCS 覆盖率镜像；保留源码、参数、镜像和刺激哈希。
- 沿用完整600项刺激和各自原有 checker；随机使用 Spike 标量/向量对比，
  定向使用 selfcheck、trace 审计，接口场景使用 UVM 独立检查。
- 先执行60项前置门禁，包含 FP 转换、存储错误、访存矩阵、相邻请求和 AXPY。
  门禁失败不投放后续540项。
- 门禁通过后最多八路并行；源码/配置漂移停止调度，保留普通测试失败证据。
- 所有 VDB 来自本轮新镜像；只将独立检查通过的案例纳入验证覆盖率。
- 汇总通过案例覆盖率，保留失败/超时清单，不把历史600项覆盖率当作本轮覆盖率。
- 结束后 `finish_main_alignment_20260930.py` 比较相同 ELF 的任务周期，
  生成 `cycle-comparison.csv` 和 `evaluation.json`。缺少明确 task cycle 的案例不比较墙钟时间。

本轮是已有600项的新镜像重跑，不意味着 Linux 启动、所有 ISA 参数、
所有浮点舍入模式、所有量化形状或 FPGA 环境均已穷尽验证。

## 查看进度

```sh
cd /home/wangwy/openproject/ara_dsa_signoff_integration
cat verification/out/main-aligned-build-20260930-01/pipeline-status.json
cat verification/out/main-aligned-600-20260930-01/checkpoint.json
tail -n 30 verification/out/main-aligned-build-20260930-01/compile.log
```

编译阶段尚无回归 `checkpoint.json`；以 `pipeline-status.json` 为准。
发现失败先查看现有 trace/flags/握手证据，不通过更改期望值或盲目重试掩盖问题。

## 门禁超时的证据与处理

新镜像首轮门禁为59项 PASS、1项宿主机墙钟超时；不是600项全部失败。
`vfdiv_mask_flags` 在600秒时被 `timeout` 截断。对照同一 ELF 的旧通过记录，
新运行已产生的481条接口事件（包含周期号）完全一致，36项完整子测试的
结果/flags也完全一致；末尾仍在输出第37项测试信息，没有证据证明死锁。
AXPY新旧均为2810 task cycles。

入口 `close_main_aligned_gate_20260930.py` 用同一镜像、ELF和检查器，
仅将该测试的宿主机墙钟预算从600秒改为1200秒；不改变RTL、周期看门狗、
测试期望或其余案例预算。第一次超时的原始证据保留。
补跑必须通过独立结果与完整VDB审计，才会归档超时、合并门禁并恢复八路540项；
失败则停止，不能将未完成的VDB计入PASS覆盖率。
这一处理不修复、也不豁免前面列出的MVP舍入问题。
