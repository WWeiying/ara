# MVP DIV/SQRT 候选核查与修复

## 修改属于哪里

这五份 MVP 候选文件此前已经同步到 `ara_dsa` 和
`ara_dsa_signoff_integration`，但尚未通过专项验收。
“尚未合入”实际应区分为代码同步、修复验收和 Git 提交三个状态。
本轮只修改两份文件的判断逻辑，保留三份接口/编码文件的合理修改。
两侧 MVP `hdl` 目录已逐文件核对一致；没有覆盖其他主线、验证或 FPGA 修改。

当前 Lane VMFPU 与 CVA6 FPU 均选择 THMULTI，MVP 是另一种可选实现。
下面的错误和通过记录属于 MVP 模块边界，不等于当前 THMULTI 整机失败或通过。

## 错误为什么发生

| 问题 | 实测证据 | 根因 | 本轮修复 |
| --- | --- | --- | --- |
| FP64 精确除法错误置 NX；RUP 还多加 1 ULP | `1/1` 的显式舍入位为零，原始余数等于 `-(denominator << 4)`，原候选仍置 sticky | 非恢复除法保存的是冗余形式的部分余数，负余数尚未恢复，不能直接判非零 | 精确余数允许两种表示：0 或负的缩放除数；其余情况才产生额外 sticky |
| 定向舍入的溢出 Infinity 变成 NaN | 正溢出 RUP、负溢出 RDN 均出现 OF=1、归一化尾数为0，之后尾数变成1 | 已依据 RM 选择 Infinity/maxfinite，后级又执行一次舍入 | 已选定溢出结果时禁止第二次尾数进位 |
| FP32 溢出缺 NX | maxfinite/0.5 返回 Infinity，但 flags=0x04 而不是0x05 | 只依据丢弃的尾数位生成 NX，而溢出分支已清空这些位 | 有限运算溢出明确置 NX；排除 Infinity、NaN 和除零输入，不把特殊值传播当成有限溢出 |
| FP32 RNE 的 `1/1.5`、`1/3` 少进位 | guard=1、显式 sticky=0、恢复余数非零，结果低1 ULP | 原实现未把 FP32 迭代尾部余数加入 sticky，误判成中点 | FP32 也消费修正后的除法余数信息 |

原候选把原始余数 sticky 同时用于平方根，没有证明其恢复含义。
本轮将新增余数信号限定于 DIV；平方根保留原本显式舍入位路径，
再用独立平方根结果和 flags 测试检查，没有将 DIV 的恢复公式套到 SQRT。

保留 RMM 编码、RMM guard-bit 舍入和按 RM/sign 选择溢出结果。
它们的设计意图合理；错误来自余数语义、重复舍入及 NX 的生成条件，
不是这些功能本身应该删除。

## 验证方法与结果

脚本：`verification/fpu/run_mvp_repair.py`。
结果：`verification/out/mvp-repair-20260930-03/summary.json`。

- 共178项，178项 PASS，无结果位或 flags 不一致。
- 前8项重放原始故障及控制点；120项为 FP32/FP64 的五种 RM、
  正负结果及六组精确/非精确/溢出输入；另50项为两种格式、五种 RM
  下的平方根1、4、9、2、3。
- DIV oracle 使用精确有理数和整数舍入，SQRT oracle 使用整数平方根及
  平方后的中点比较；不采用 DUT 输出作为期望值，不依赖宿主浮点舍入模式。
- 独立 oracle 的固定值单元测试4项通过，包括 `sqrt(2)`、`sqrt(9)`、
  `1/3`、精确结果和正负溢出。
- 每笔事务检查输入锁存、reset、一次接受/完成、未知值、输出稳定性，
  记录余数、除数、显式舍入位、sticky、进位、指数、结果及 flags 的逐周期 CSV。
- FP32 完成延迟9周期，FP64 19周期，与修复前这些控制点一致。
  没有修改状态机迭代次数或请求握手，也没有增加流水级。
- 保存独立源码快照、SHA-256、编译/运行命令、原始 CSV 和局部 VCD。
  原始失败目录保持不变；失败记录不改成 PASS，不计入通过覆盖率。

可复现命令，输出目录必须是新目录：

```sh
cd /home/wangwy/openproject/ara_dsa_signoff_integration
python3 verification/fpu/run_mvp_repair.py --output verification/out/mvp-repair-new
python3 -m unittest discover -s verification/tests -p test_mvp_repair.py
```

## 验收边界

本轮可以保留上述修正，原来已定位的故障全部闭环，
但178项不等于 MVP 的完整 IEEE 浮点或整机 signoff。
FP16/BF16、NaN/Infinity/零输入、subnormal、舍入后才溢出、
kill/连续事务及切换到 PULP/MVP 的整机集成仍不属于这份通过结论。
尤其已有归一化分支对特殊值的 OF、UF 处理需要另行专项核查，
不能仅凭本轮有限正常输入的 PASS 宣称替代实现已全面可用。

主路径选择保持 THMULTI，本轮不改变其性能。
这里“周期不变”来自 MVP 模块级完成延迟，不是新的综合时序或全模型性能数据。
没有启动 DC、FPGA 构建或新的600项全量回归。
新的源码哈希与此前封存镜像不同，后续覆盖率验收需重新核对镜像来源，
不能把旧 VDB 当成这一份新源码的完整覆盖率。
