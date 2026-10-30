# Decode 公共 selector 对齐候选的 RTL 周期实验

> 评测接线复核（2026-10-28）：本文既有 native 周期数据使用通用标量
> `dequantize_row_q8_0` 作为 V 回调；当前 llama.cpp 后端使用共享 RVV
> `akv_quant_q8_0_value`。这些历史配对数据在其配置下仍有效，但不能当成
> 当前后端回调配置下的周期或瓶颈占比。真实 GGML/模型功能回归不受此
> benchmark 差异影响。更正及补测见 `quantized_native_binding_audit_20261028.md`。


## 假设与隔离

共享 selector 在检查 query 和量化 KV 的有限值时，使用保留对象表示的
固定长度 memcpy。view 检查已经证明 query 为 4 字节对齐、KV scale 为
2 字节对齐。将这个已证明的事实传给编译器，可能减少逐字节装载和栈上
拼接，不改变准入范围、拒绝顺序、数值运算或硬件协议。

候选还未安装到生产软件；本次没有修改 RTL。旧 runtime 和候选 runtime
使用同一份 `runtime_strided.c`，分别编译到两个 translation unit。
编译参数完全相同，候选仅替换 selector 和导出函数名称。

## 输入与周期边界

- 真实 Qwen3 capture 的 query 19，选 KV head 0，对应两个 query head。
- D=128，可见前缀 20 token，K=Q4_0、V=Q8_0。
- 物理存储保留 8 个 KV head 的 token-major 排列；只选择一个 KV head
  不等于将物理 head stride 改成连续布局。
- 同一 ELF，原/候选/候选/原顺序，4 次完整调用。
- ROI 包括准入检查、query 量化、K panel 准备、QK、online softmax/PV、
  输出写入及最终 drain；不包括 UART 输出和检查程序。
- 每次应产生 1 个命令、1 个完成组、20 次 V 解码、1 个 K panel、
  1440 字节 K 拷贝，256 个输出。

## 身份与验收

`build_selector_native.py` 只读取历史构建的编译配方和封存的汇编/二进制
数据，不复用历史对象，也不声称当前 C 源码仍等于旧构建源码。所有 17 个
对象重新编译，当前依赖重新扫描并封存。执行前后核验当前源码和 canonical
VCS 镜像。原始历史结果保持不变。

新 checker 检查 ABBA 次序、唯一结束标记、输出位模式、capture golden、
FCSR/VCSR 和上述活动计数；另执行原有独立协议检查。
`test_selector_native_check.py` 已通过正例和故意破坏输出、次序、计数、
标志、结束标记的反例检查。

构建目录：`verification/out/selector-native-q4-build-20261028-01/`。
ELF SHA256：`24c763d3c8a14e64ce51e29e1cc19260c61e5299c282c71e4fb097b321643180`。
预检查：`verification/out/selector-native-q4-preflight-20261028-01/result.json`，
状态 `PREFLIGHT_NOT_RUN`、指纹一致，不是仿真通过记录。

正式任务：`selector-native-q4-20261028-01.service`。
结果目录：`verification/out/selector-native-q4-vcs-20261028-01/`。
最终周期和验收状态以该目录的 `result.json` 为准。任务已完成，状态 PASS：

| 顺序 | 入口 | 完整调用周期 |
|---|---|---:|
| A | 原 selector | 82870 |
| B | 对齐候选 | 71839 |
| B | 对齐候选 | 71463 |
| A | 原 selector | 82512 |

原版均值 82691，候选均值 71651，加速 1.1540801943×，周期减少约
13.3509%。四轮 256 个输出逐位一致，相对 capture golden 最大绝对误差
2.9988586903e-7，FCSR 均为 1、VCSR 均为 5。独立协议检查通过，运行
前后源码和镜像指纹一致。该收益是此 Decode 完整调用的局部测量，
不是模型端到端加速，也不能与其他不同分母的收益相乘。

已有主机四组完整执行 PASS 记录见
`quantized_kv_selector_real_execution_20261028.md`，不能替代本次 RTL 测量。
