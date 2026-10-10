# 当前 RTL 修复与全量覆盖率重收集

## 目标和统计规则

本轮不在旧的 510 项覆盖率上继续拼接不同 RTL 的结果。先定位并修复
已确认的问题，再使用一个新建、冻结源码的 VCS 覆盖率镜像重跑全部清单。
使用宿主机 VCS 和 DVE，不使用 Verilator 或 URG。

`full_recollection_20260928.plan.json` 合并历史计划、访存扩展、FP16
边界、QBS/AKV 与 Dispatcher 状态复位测试，以及四项之前未纳入累计
计划的定向修复回归。按 ELF 内容、检查方式和复位配置去重，共 600 项。
历史 FAIL、TIMEOUT 和中断项均保留；历史结果只用于追溯，不作为新 PASS。
静态预处理未通过的 seed719 不作为合法 RTL 测试，保留替代 seed721。

## 本轮开始时的未闭环问题

| 项目 | 证据与状态 | 处理方式 |
| --- | --- | --- |
| Gap29 六种 FP16 舍入模式 | RNE 在当前镜像仍失败；已定位到异常标志，而非已比较的数值结果 | 用 CONV 子通道单元测试验证掩码假设，修复后六种模式全部重跑 |
| Gap28 六项 e32/e64 store 测试 | 历史 TIMEOUT，不能直接等同于 RTL 错误 | 检查提交轨迹及程序是否仍推进，再决定修复或合理时间预算 |
| 访存修复后的中断/取消项 | 不能算 PASS，也不能全部算新死锁 | 全量重跑，不复用中断结果 |
| NF7/e16 indexed | 当前镜像独立补跑已 PASS：`out/pre-recollection-nf7-e16-20260928-01/uvm_result.json` | 纳入新镜像回归，不能用本次补跑 VDB冒充修复后覆盖 |

FP16 现有首错和逐条证据见
`../diagnostics/gap29_fp16_rne_findings_20260928.md`。其中窄化实际
`fflags=0x07`、期望 `0x17`，缺少 NV；部分扩大转换尾部的标志还含 X。
不能通过放松异常标志比较来消除这个失败。

## FP16 修复的已测证据

逐周期单元探针复现了两个问题：

- 转换使用打包后的子通道编号，但输入异常掩码按物理最小浮点宽度编号。
  FP32/FP16 转换的第二个元素应取掩码位置 2，而不是位置 1；原来会漏掉
  有效 sNaN 的 NV，或者把无效尾部的异常加入最终标志。
- 不同宽度转换使用不同数量的子通道。子通道独立插入空泡后，在反压下
  可能超前于子通道 0。实测出现子通道 0/1 对应 tag444，而 2/3 已对应
  tag445，后一条转换的异常混入前一条。只改掩码不足以修复这一问题。

修复使 CONV 子通道携带同步的事务标记，并随流水线传递该子通道是否
实际参与运算的标志；结果和异常仅从本事务有效子通道选取。CPK 保留
独立操作数的掩码规则。没有增加转换流水级或串行等待条件。

| 测试 | 事务数 | 结果 | 输出目录（`verification/out/` 下） |
| --- | ---: | --- | --- |
| 修复后扩展转换、连续输入、反压 | 696 | PASS | `fp16-conv-mask-unit-lockstep-20260928-01` |
| 最小浮点宽度为 8 位的配置 | 712 | PASS | `fp16-conv-mask-unit-byte-20260928-01` |
| 纯标量配置 | 4 | PASS | `fp16-conv-mask-unit-scalar-20260928-01` |

这些是 fpnew CONV 单元证据，不是六个完整 RVV 程序已通过的声明。
全系统必须再通过下面的验收。构建接续脚本检查单元测试记录的 RTL
哈希与完整 VCS 编译输入一致，避免小单元测试与系统镜像错配。

## 执行顺序

1. 小型单元测试复现首错，记录子通道原始异常、掩码和合并后的异常。
2. 修复通过单元回归后，构建独立覆盖率镜像；校验编译参数、源码和运行库。
3. 先执行 60 项系统验收：六种 FP16 模式，三项转换指令回归，四项已有
   CSR/除法/store 修复回归，AXPY 周期检查，完整 40 项访存矩阵，以及
   六项历史 Gap28 store 超时测试。已知失败或超时不能留到正式队列才处理。
4. 验收全部通过后，以八路并发执行其余 540 项。验收结果属于这 600 项，
   不重复仿真。普通功能失败保留证据并继续独立项；环境或镜像漂移停止队列。
5. 只把新镜像下检查通过的 VDB交给 DVE，输出整体及模块层级覆盖率。
   新设计不匹配旧豁免时明确报告不适用，不自动移植旧豁免。

Gap28 store 的旧提交轨迹显示程序仍在有界的标量初始化与检查循环中推进，
不是停在同一个等待状态。依据实测周期推进速度和六轮程序结构，e32/e64
分别使用 900/1800 秒的墙钟预算。仅调整超时预算，不修改 ELF、检查器或
周期看门狗；这项分析不等于测试已经通过，仍必须通过前置验收。

## 入口和结果

- 构建与接续执行：`build_and_recollect_20260928.py`。
- 清单、验收与八路调度：`run_full_recollection_20260928.py`。
- 只读清单核查：`python3 verification/coverage/run_full_recollection_20260928.py --inventory`。
- 构建阶段：独立构建目录下 `pipeline-status.json`、`build-status.json`、`compile.log`。
- 运行阶段：独立收集目录下 `gate.json`、`checkpoint.json`、`outcomes/`。
- 完成后：`collection.json`、`dve/summary.csv`；适用的豁免另列于报告中。

上述是执行契约，不是 600 项已经通过的声明。以对应目录的实际状态及
独立检查结果为准；全量完成前不发布新的全量覆盖率百分比。

本次已启动的独立后台任务：

- systemd 服务：`ara-full-recollection-full-recollection-20260928-01.service`。
- 构建目录：`verification/out/fp16-repaired-coverage-20260928-01/`。
- 系统验收及正式收集目录：`verification/out/full-recollection-20260928-01/`。
- 启动时实际处于 BUILDING。构建通过后自动进入验收；60 项全部 PASS 才
  放行正式队列。未通过时保留 STOPPED/失败证据，不自动重试或绕过。

```sh
systemctl --user status ara-full-recollection-full-recollection-20260928-01.service --no-pager
cat verification/out/fp16-repaired-coverage-20260928-01/pipeline-status.json
# 下列文件在构建成功、开始系统验收后生成：
cat verification/out/full-recollection-20260928-01/gate.json
cat verification/out/full-recollection-20260928-01/checkpoint.json
```

## 系统启动错误与修复（02 轮）

01 轮完整镜像构建成功，但验收在 0 fs 调用 `int_width(X)` 时终止。
当时没有程序请求发出；8 项 FAIL 和 1 项检查设施错误不代表 8 个独立
数值错误。没有有效 VDB 被纳入覆盖率，后续 540 项没有放行。

根因是新增 CONV 掩码逻辑使用三目表达式选择整数或浮点宽度。当 `op_i`
尚为 X 时，SystemVerilog 会求值两个分支，触发整数格式函数内保留的
非法格式检查。此前单元测试在 0 时刻初始化全部输入，未覆盖系统启动的
未知输入窗口。

在单元测试输入初始化前增加 1 ns 延迟后，旧代码精确复现相同的 0 ps
fatal。将宽度选择改成 `if/else`，仅在明确的 I2F/F2I 操作时调用整数
格式函数后，扩展测试 696 个事务全部通过。没有删除 `int_width` 的
非法格式检查，也没有增加流水级或改变已知合法输入下的掩码映射。

- 复现证据：`out/fp16-conv-startup-before-20260928-02/`。
- 修复后扩展单元证据：`out/fp16-conv-startup-after-20260928-02/`。
- 新构建目标目录：`out/fp16-repaired-coverage-20260928-02/`。
- 新验收/收集目标目录：`out/full-recollection-20260928-02/`。

02 轮继续执行同一套 60 项全通过门槛，随后才运行其余 540 项。单元测试
通过不等于系统验收完成，实际阶段以新目录状态文件为准。
