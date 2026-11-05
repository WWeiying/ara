# 操作数整数扩展网络共享

## 1. 范围与实现

这是 lane 队列/数据通路静态审计中的 A2，接在已通过 62 项 SoC 回归的 VRF
返回路由精简之后。主工作区改动仅涉及
`hardware/src/lane/operand_queue.sv` 的六个整数扩展分支。

同一扩展倍数下，符号扩展与零扩展读取相同的源元素，只是扩展位填充值不同。
将两种分支合并为一个源元素选择，再用 `sign_extend & element[MSB]` 决定高位。

| 扩展倍数 | 有效输入/输出位宽 | 共用内容 |
|---|---|---|
| 2 | 8→16、16→32、32→64 | 同一个源元素切片，区别仅在高位填充 |
| 4 | 8→32、16→64 | 同上 |
| 8 | 8→64 | 同上 |

不跨倍数强制共享，不跨队列合并，不增加流水级。不修改 FIFO 容量、信用计数、
元素计数、select 更新、pop/valid/ready、复位或 flush。浮点转换、归约中性值
以及原有尾部填充代码保持原样。FPGA 副本尚未迁移。

| 身份 | SHA256 |
|---|---|
| 修改前 operand_queue | `eafc82bfe3bd7413aa549015a2145e977d1ce01a9bd52c369993e5dac10e453d` |
| 本轮候选 operand_queue | `170e8c102d86a8edf9e2eb7a24bec8c368954f07db5e21f0fbf001afcb333df2` |

源码更短并不等于网表更小：DC 可能原本就合并了一部分重复逻辑。因此保留候选
的决定必须依据同条件综合，而不是仅根据 RTL 表达式数量。

## 2. 局部验证结果

使用宿主机 VCS，完整实例化新旧 `operand_queue` 和真实 `fifo_v3`，不使用
Verilator。旧实现来自冻结的 Git HEAD 原文件，重命名后作为参考实例。

证据根目录：
`/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/`。

正式局部结果在 `operand_ext_20261104_03/test.status.json`，结果为 PASS。

| 项目 | 实测数量/范围 |
|---|---|
| 整数扩展支持配置 | 8 种：×2/×4/×8 三个参数的全部组合 |
| 数据 FIFO 深度 | 1、2、5 |
| 组合新旧对照 | 327,680 组 |
| 组合输入覆盖 | 10 种转换、4 种 EEW、8 个 select、每组合 128 个数据点 |
| 队列事务 | 2,800 次，其中 80 次中途 flush 取消 |
| 实际输出握手 | 29,108 次，包含随后被取消事务中已经发生的握手 |
| 正常事务长度 | 1～33 元素，另有 flush 后 17 元素恢复测试 |
| 数据模式 | 零、全一、符号边界、随机字、局部 X |
| 时序模式 | 一拍返回流水、连续输入、信用限制、输出背压、两个接收端选择 |

组合阶段强制内部输入，只用于覆盖转换组合；随后解除 force，使用真实命令
FIFO、数据 FIFO 和握手完成时序测试。不能把组合阶段视为完整程序或合法指令
覆盖。有效 SRAM 数据的 Z 不属于本次测试契约。

独立参考模型采用逐 bit 源元素索引和固定 byte 排列计算，不调用生产 RTL 的
转换/排列函数。时序阶段还逐拍比较 valid、credit、cmd_pop、input pop、select、
元素计数，以及所有有效输出数据，不能只凭最终数值相同判通过。

### 首次参考模型问题的处理

`operand_ext_20261104_01` 和 `_02` 原始 FAIL 保留，不覆盖或改判。
两次均在普通传递 `None`、EW8、长度 1 的首个事务出现独立模型不一致；新旧
RTL 一致，补充探针显示输入命令、内部命令、源数据、select 和元素计数一致。

原因是参考模型漏掉原有 `SupportNtrVal` 行为：这类队列即使不是归约，普通
传递的最后一个不完整 word 也会把无效尾部 byte 填零。03 根据逻辑元素数判断
尾部，再映射到物理 byte 位置，补上该行为，仍比较完整 64 位，不屏蔽尾部。
此次没有因此改变生产 RTL。

## 3. 面积/时序与系统验收安排

后台主任务：`operand-ext-acceptance-20261104-01.service`。
状态目录：`operand_ext_soc_20261104_01`。

流程按顺序执行：

1. 检查局部 PASS、历史 SoC 源码与参考队列一致，递归核验继承的冻结文件。
2. 在 `synopsys_workspace` 容器内做新旧完整 operand queue 部件 DC 综合。
3. 使用实际 ALU-B 的主要参数：命令深度 4、数据深度 5、全整数扩展、无 FPU、
   支持归约和中性值。测试顶层额外观察 cmd_pop，不是 SoC 面积报告。
4. 同库、同脚本、同 1 ns 时钟与 setup uncertainty 0.15 ns；在两版综合前固定
   目标 `.db` 内容，并在结束后核查，不只固定库路径配置。
5. 自动门槛为面积降低、寄存器组 setup slack 非负、该组最差到达时间不变长。
   不满足则停止并等待审查，不继续消耗长 SoC 仿真时间。该门槛不代替 hold、
   所有路径组或物理 signoff。
6. 通过门槛后，基于已通过的 VRF 优化 SoC 源码，仅替换 operand_queue，构建
   新镜像，并六路并行执行原 62 项。使用相同 ELF，复用冻结的已检查基线运行。
7. 在全部 36 个真实 operand queue 中绑定旧队列实例，检查每拍有效数据与握手；
   同时要求应用结果、结束周期、区域周期和已有 lane 活动计数与基线完全一致。
   任一批失败停止后续派发。

局部综合位于 `operand_ext_20261104_03/ppa/`。其 `report.json` 的 `MEASURED`
仅表示测量完成，不是“优化成功”的同义词。SoC 验收通过后才可讨论系统周期
不退化；本记录编写时后台还在局部综合阶段，尚无面积收益数字。

## 4. 查看状态

```bash
BASE=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out
cat "$BASE/operand_ext_soc_20261104_01/status.json"
cat "$BASE/operand_ext_20261104_03/ppa.status.json"
journalctl --user -u operand-ext-acceptance-20261104-01 -n 15 --no-pager
```

主任务由 systemd 直接托管，完成后保存结果。无需持续轮询，也不需要手动衔接
综合与回归。没有自动提交、迁移 FPGA 或启动全 SoC 综合。
