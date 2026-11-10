# 第二阶段：QBS 与 RVV 整数乘法器协同

目标是用现有 Lane 乘法器参与 Prefill 的量化矩阵计算，不增大 SRAM、不修改外部
总线、不再复制一套大型乘法阵列。起点提交为 `b0156f8ab`。设计和验收标准见
`hardware/docs/INFERENCE_STAGE2_RVV_COOPERATIVE_MATRIX_20261109.md`。

## 当前实现范围

- `simd_mul` 和 `simd_mul_shared` 导出与原 valid/ready 对齐的完整128位乘积。
  原有低位、高位、定点舍入和饱和结果接口保留，不通过新乘法器重算。
- `qbs_lane_mul_borrow` 仅增加寄存、所有权控制和四个二乘积求和，不包含乘法器。
  一条 Lane 处理一个权重输出行，与另外四个输入行的两个连续K元素相乘。
- 入口、完整乘积和局部求和分为三拍，与 QBS 原点积阵列对齐。输入在发射前
  等待 ready；一经接收，三拍后结果必须可直接写入私有整数部分和，不允许在
  返回时再施加反压。外层必须保留所有在途结果，故障和释放也要排空这些结果。
- VMFPU 借出前等待本地普通指令及结果队列排空，并拒绝与 AKV 的 FPU 借用重叠。
  执行期间不把借用结果送入普通VRF写回，也不产生普通指令完成或异常标志。
- 首个并行矩阵候选只选择 Q4_K/M8，其余格式及行数沿用原调度。Q4_K 的32元素
  分组能匹配现有两路修正；不能直接将这一吞吐结论外推给16元素分组格式。
- 顶层 `ARA_QBS_LANE_MUL_ENABLE` 默认未定义，显式开启后也仅支持当前四Lane、
  VLEN1024的组合。尚未验收的新路径不能自动替换板上正式交付。

## 已完成的实际 VMFPU 检查

输出目录：
`/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/stage2_vmfpu_borrow_20261109_02/`。
原始 `report.json`、两套 `run.log`、编译命令及输入SHA256均保留。

| 配置 | 普通整数指令 | 借用接收 | 借用返回 | 复位取消 | 获取/正常释放 | 准入冲突检查 |
|---|---:|---:|---:|---:|---:|---:|
| 原分位宽乘法器 | 10 | 270 | 269 | 1 | 3/2 | 9 |
| 共享乘法器 | 10 | 270 | 269 | 1 | 3/2 | 9 |

普通指令包括8/16/32/64位的 VMUL、VMULH，借用覆盖连续发射、气泡、符号边界、
获取冲突、释放排空和在途复位。每组均满足接收=返回+取消。
本测试实例化真实 VMFPU，但关闭浮点支持以单独核查整数借用；它不是浮点共存、
整个SoC或性能验收，也不证明完整矩阵已经提速。

另有独立的完整乘积/原接口对照门和借用传输门。仅以各自最终回执判定结果，不
把“已编译”“正在仿真”或部分配置完成视为整批通过。

## 已完成的乘积及矩阵级检查

独立乘积门 `stage2_mul_product_vcs_20261110_03/report.json` 已通过，比较基线固定为
`b0156f8ab`，不使用变化中的 HEAD。覆盖24种位宽/流水配置及3种共享EW8配置，
接收152,093项，退休152,050项，复位取消43项，共214,604次检查。每配置包含6,000
个随机周期及定向边界；未将它表述为全部字节对的穷举验证。

独立借用门 `stage2_mul_borrow_vcs_20261110_01/report.json` 通过，接收6,935项、
返回6,923项、复位取消12项，包含80次入口阻塞、4次复位和6次租借撤回。

矩阵级结果来自 `stage2_matrix_vcs_20261109_02/report.json`。原01 worker因日志
解析器不认识多词前缀失败，原FAIL回执保留；02通过严格离线审计复用原两份镜像，
没有重新编译RTL或改变结果/异常检查。两侧各完成36项合成功能用例、12项context
功能用例及其故障/复位检查。context套件每侧372条命令和12次在途复位；非加速
格式仍走原路径。

以下为旧Qwen2.5真实样本的首组结果，K=1536，八个不同输入行，32个输出通道。
M4以两次N32、M8以两次N16覆盖相同的256个输出。表中周期包含各命令的数据读取、
计算、排空和提交，不包含CPU量化/描述符构造等完整软件调用开销。

| 调度 | 原路径周期 | 协同开启周期 | 周期变化 |
|---|---:|---:|---:|
| 两个M4/N32 | 13,756 | 13,756 | 不变，未使用新路径 |
| 两个M8/N16 | 15,362 | 12,238 | 减少20.34% |
| 最快原调度与协同M8比较 | 13,756 | 12,238 | 减少11.04% |

不能只用较慢的原M8来宣称完整收益。单条M8的dot发射周期从6,144降到3,072，
但FP请求阻塞从0增到1,296周期；浮点运算数量不变。因此乘积吞吐翻倍不等于
矩阵性能翻倍，当前也没有据此声称达到完整投影减少20%的目标。

上述样本来自Qwen2.5，新的Qwen3 Attention/FFN输入仍需独立配对；引擎fixture
使用四个真实整数乘法器，但尚不代替完整SoC资源所有权及软件调用验收。

## 运行方法

所有结果写入唯一主验证工作树的 `verification/out`，每次使用新目录名。
禁止覆盖旧失败目录，禁止在worker运行时修改其 `source-pins.json` 所列文件。

实际 VMFPU 小测试分为准备与执行：

```bash
python3 -B verification/performance/next_mechanism/stage2/run_vmfpu.py \
  /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/stage2_vmfpu_NEW

python3 -B /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/stage2_vmfpu_NEW/inputs/run_vmfpu.py \
  /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/stage2_vmfpu_NEW --execute
```

长任务必须用 `systemd-run --user` 直接托管第二条命令，不能让短启动器退出时
连带终止仿真子进程。VCS在宿主机运行，不调用 Verilator、URG 或综合工具。

## 模型数据与后续性能比较

`capture_qwen3.cpp` 和 `run_capture.py` 使用已封存、核验过的 llama.cpp 库及
Qwen3-1.7B-Q4_K_M 模型。在真实GGML图的第一层 Attention 和 FFN 投影输入处，
各收集八个不同token的归一化激活；只截取输出通道，不截短K维。

QEMU仅产生这些功能输入，不提供硬件性能数据。捕获首四行Attention激活必须
与旧四行样本逐位相同。新数据仍需在VCS中与原路径完成配对后，才能报告周期收益。

完整矩阵比较必须同时包含原M8和等工作量的原M4对照，覆盖全部输入装载、整数
修正、FP累加、排空和结果提交。原有M8权重复用不是新收益；阵列乘积率也不能
冒充整个矩阵或整模型的加速比。
