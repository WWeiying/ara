# QBS/AKV 配套源码检查点

本检查点固化当前主 RTL、SDK、llama.cpp 以及 FPGA 源码候选，供后续重新构建。
它不是新的位流验收或完整模型板测结果，不替换既有已验收标签。

## 固定版本

| 内容 | 仓库及分支 | 固定提交 |
|---|---|---|
| 主 RTL、QBS/AKV SDK、Linux 接入和配套测试 | `WWeiying/ara`，`ara_dsa` | `208ab0fef23721828aac579eff34a82585a3aaa3` |
| FPGA 完整源码包、锁定依赖及全开配置 | 同上，标签 `fpga-mainrtl-candidate-all-20261112` | `7b4eea960826d02a3da25d5f97542926f1e700c0` |
| GGML 优化选择、量化路径及 AKV Linux 入口 | `WWeiying/llama.cpp`，`qbs-activation-context` | `a2b7f30da9aadf88b0a068c447383ed2e26ee867` |

两个仓库的配套源码标签为 `qbs-akv-source-candidate-20261112`。
Ara 标签还包括本文及机器可读版本索引；计算源码以表中固定提交为准。
该标签只标识源码候选，不能替代部署验收。

主 RTL 提交已经收录 FPGA 同步时作为未提交补丁封存的修改。重新核对后，80 项
主 RTL/头文件与导出前像一致，824 项 FPGA 包校验通过；允许差异仅来自已登记
的 FPGA 适配。同步补丁 SHA256 仍为
`179473a6347a6b64faba74a898e89ce93dd9f0712d086ce7d9b10cc6b11308a3`。
因此不需要因这次源码提交本身再次覆盖 FPGA 包；若源码或配置后来改变，应重新检查。

## 构建输入

- 从表中固定提交用 `git archive` 提取 SDK、Linux 接入和 llama.cpp，写入新的构建目录。
- 不从当前脏工作区整体复制 SDK。未交付的 `akv_v2_attention_rvv.S` 修改仍留在工作区，未纳入提交。
- SDK 能力结构发生变化，应用、SDK 和静态库必须一起重新编译，不能混用旧对象。
- 主硬件全开配置使用 `config=llm`；FPGA 实际配置、宏定义及展开层级另由导出包记录约束。
- 软件选择 `cmake/ara-optimized.cmake`。AKV 驻留计算的 Linux 入口还需显式开启
  `GGML_RISCV_AKV_LINUX_PORTAL=ON`，并提供匹配的内核、驱动及可信平台描述。
- 不把旧 ELF、旧 `.ko`、测试 provider 或环境变量当作新硬件/操作系统准入证明。

## 已有检查与未完成工作

原验证索引保持原样，记录的是当时固定快照的身份，不因本次提交重写历史：

- `software/llama/integration_extension_manifest_20261111.json`：此前完整程序及 M4/M8 验证。
- `software/llama/resident_linux_manifest_20261112.json`：AKV 驻留计算能力、驱动、CSR、
  GGML 接入、真实 SoC/VCS 计算和 Linux 生命周期检查。
- `hardware/fpga/vcu118/migrations/mainrtl_candidate_all_20261112.json`：FPGA 同步、
  依赖重建、源清单与优化层级检查。

提交前另通过生成器一致性、`config=llm` 配置检查和 QBS/AKV 的 `make check` 宿主回归。
232 个 Ara 文件及对应软件实现被固化，不把新增提交本身算作重新执行 RTL 回归。
大体积 VCS、QEMU、模型捕获和 Linux 构建证据保留在各索引给出的本机目录，未纳入 Git。
历史验证脚本依赖这些冻结输入；仅拉取源码不等于已经取得完整证据或通用 CI 环境。

本检查点未启动 Vivado、综合或新板测。AKV Linux 接入已有模块加载/拒绝路径与
同一计算对象的正向 RTL 证据，尚未完成真实 Linux 中正向计算的板级验收。
下一步仍是重建位流、核对平台合同、编译匹配软件，再开展同条件端到端对照。

## 保留但未纳入本次提交

面积报告、门级 testbench 修改、其他验证工具修改、旧实验输出、未交付 AKV 汇编，
以及 llama.cpp 的既有 `tests/test-ara-q4k-repack.cpp` 差异均保留，不与本检查点混合。
旧 FPGA 同步标签和 `qbs-akv-validated-20261029` 验收标签不移动。
