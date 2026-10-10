# 唯一验证主线与历史归并

## 工作约定

唯一活动验证分支是 `ara_dsa_signoff_integration`，工作目录为
`/home/wangwy/openproject/ara_dsa_signoff_integration`。
本文件记录 2026-09-26 的归并，不是新的硬件验证通过声明。

- 新激励、比较器、覆盖率和验证报告统一在本分支维护。
- 发现新的失败后停止派发测试，保留首错和输入；区分 RTL、检查器和环境问题，
  向用户报告。未经用户指示，不自行修改 RTL。
- 用户同意修复后，可以创建临时修复分支；修复代码、回归激励和证据索引必须
  回到本分支，临时分支不能成为第二条长期验证主线。
- `ara_dsa` 是产品开发主线，不是并行维护的另一套验证环境。
- 本次归并没有修改 RTL，没有启动 VCS 仿真或 Linux 启动，也没有删除旧工作树。

## 如何理解“包含所有”

包含已有的有效验证能力、已确认修复和历史证据索引，不是把旧文件无条件覆盖
到新文件上。当前 dispatcher 已包含部分旧修复树没有的寄存器组、mask 重叠等
合法性检查，必须保留。不同版本的 RTL 和结果不能混合统计覆盖率。

| 原工作树 | 本次处理 | 之后用途 |
| --- | --- | --- |
| `ara_dsa_verification` | 核对早期平台、QBS 测试和工具；补齐有效缺项 | 历史结果归档 |
| `ara_dsa_masked_indexed_fix` | 核对访存异常修复、比较器、覆盖率和 Linux 工具 | 历史结果归档 |
| `ara_dsa_store_fault_fix_20260925` | 保留已合入的 Store/FP 修复，补充可复用验证用例 | 修复证据归档 |
| `ara_dsa_signoff_integration` | 保留最新整合实现，接收有效补充 | 唯一活动验证主线 |

旧目录中的 `verification/out/` 暂保留原位。历史 JSON 和文件清单使用绝对路径，
随意搬动会破坏重放和审计。归档保留不意味着继续在旧分支运行新的验证。

## 本次补齐的有效能力

| 类别 | 补齐内容 | 验证边界 |
| --- | --- | --- |
| 模型切片 | 12 个入口，覆盖 IQ4_NL、Q4_0、Q5_0、Q2_K 及 N33 的六组 RVV/QBS 配对；补齐共享 kernel、格式分派和生成器依赖 | 真实 capture 生成检查，不是新增 RTL 数值 PASS |
| AKV | column coverage 和 minimal 两个有界测试入口 | 源码收齐，待当前镜像运行 |
| DIV/SQRT | 多格式流水、mask 和 backpressure 的子模块测试，拒绝将历史 bug 复现模式当作 signoff PASS | runner 离线检查；未编译或运行 DUT |
| 验证框架 | 恢复配对调度单元测试，修正两个覆盖率审计测试的导入路径 | host 单元测试 |
| Linux | 恢复 single-hart-fast 选项，以及 minimal-boot 下关闭 RAID6 启动测速 | shell 语法通过；没有新编译内核，不代表 SMP/完整 Linux 验证 |
| 证据审计 | 恢复配对结果 `--source-root` 重定位，保留输入哈希和冻结镜像校验，拒绝相对路径越界 | 独立 host 用例验证 |

应用文件清单、共享依赖和生成检查见
[SOURCE_UNION.md](../apps/llama_qwen25_real/SOURCE_UNION.md)。
本次没有导入旧 RTL 覆盖当前实现，也没有把新测试的“可生成”误记为“硬件已通过”。

## 环境与版本管理

以下输入已经改为本地副本，不再通过软链接依赖旧验证工作树：

- `apps/bin`：复制后逐文件 SHA-256 核对；旧 ELF 不是新 RTL 的通过证据。
- `hardware/bender`：复制后 SHA-256 核对。
- `verification/tools`：保留 riscv-dv 仓库和 Python 环境，并迁移虚拟环境启动脚本路径。
- `hardware/deps`：继续使用当前独立依赖及经过审核的补丁，不导入旧依赖目录。

共享工具链 `install` 和 `apps/third-party` 指向基础 `ara` 目录，这是明确保留的
外部依赖，不指向旧验证工作树。工具版本由 `toolchain.lock.json`、补丁注册表和
环境检查约束。不要把已安装工具或生成的 ELF 全部提交到 Git。

修正了 20 个定向 C 测试被忽略的问题，覆盖 Linux 状态/MMU/上下文、异常、
mask/policy、非法寄存器组、indexed fault 和 Store 多 burst 等；源码可纳入版本
管理，但生成文件仍保持忽略。

## 不作为活动入口导入的历史文件

| 文件类别 | 原因与保留方式 |
| --- | --- |
| `finish_combined_17case.sh`、`finish_no_raid6_bench.sh` | 写死旧服务名和结果目录，属于已结束任务的收尾脚本 |
| `check_single_hart_fast_qemu.sh`、`run_single_hart_fast_soc.sh`、`finish_fulltrace_campaign.sh` | 同上；可复用能力应在通用脚本中保留，而不是重启旧任务 |
| `verification/patches/patches/` | 重复嵌套的历史补丁副本，不能替代当前经过哈希审核的注册表 |
| 旧 FPGA dispatcher 哈希测试 | 绑定旧 RTL 精确哈希，不适合作为当前 RTL 测试；FPGA 不在本轮范围 |
| `novas.conf`、旧 build/filelist | 本机波形或构建残留，不是缺失的验证能力 |

这些内容没有从源目录删除。不同和独有的历史源码另存于：
`/home/wangwy/openproject/ara_verification_archive/consolidation-20260926/historical_sources_final.tar.gz`。
解包文件只用于追溯，不作为自动应用到当前 RTL 的补丁。
最终清单 `consolidation_inventory_20260926.json` 记录每项历史文件哈希和整个归档哈希；
归档的 190 个历史源码文件已逐项核对。

四组原来位于旧验证树中的模型 capture 已复制到
`/home/wangwy/openproject/ara_verification_archive/captures/`，应用配置引用新位置，
原数据仍保留。`out/consolidation-20260926/captures.json` 记录逐文件哈希。
这些是真实模型输入，不是重新生成的合成数据；仍不纳入源码 Git 仓库。

## 证据位置与复查方法

本轮日志和哈希记录：`verification/out/consolidation-20260926/`。

- `source_inventory*.json`：各来源的文件差异和哈希；差异不等于遗漏。
- `local_inputs*.json`：本地输入迁移记录和旧链接去向。
- `copied_inputs_audit.json`：ELF 目录和 Bender 内容一致性。
- `worktree_inputs.before.json`：迁移前环境记录，当前记录在 `verification/worktree_inputs.json`。
- `validation.json`、`host-tests.log`、`doctor.log`：离线回归与环境检查。
- `rtl-source-check.log`：已有 VCS 镜像的 457 个输入文件核对，无改动。

本轮离线检查：框架 625 项中 600 项通过、25 项跳过；配对结果重审 7/7 通过；
真实 capture 生成检查 11/11 通过。四份 capture 的 380 对文件 SHA-256 一致。
新增测试尚未进行目标编译和 VCS 执行，本轮没有新增 RTL 覆盖率数值。

环境检查保留了一个既有警告：`4_lanes.mk` 文件名与其 `nr_lanes=8` 内容不一致。
当前使用 `default.mk` 的 4-lane、VLEN=1024 配置；本轮没有为了消除警告擅自改变
硬件配置。后续每次构建都应记录实际配置，不能从文件名推断 lane 数。

源码清单可以重新生成：

```bash
python3 verification/audit_consolidation.py \
  --source ../ara_dsa_verification \
  --source ../ara_dsa_masked_indexed_fix \
  --source ../ara_dsa_store_fault_fix_20260925 \
  --output verification/out/consolidation-review.json
```

当前硬件验证状态仍以 [CURRENT_SIGNOFF_STATUS.md](CURRENT_SIGNOFF_STATUS.md)
为准。新补入的激励必须在当前冻结镜像上运行并完成对应审计后，才可进入通过统计；
离线脚本单元测试不能替代 VCS/Spike 对比或 RTL 覆盖率回放。
