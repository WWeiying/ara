# 当前 RTL 到 VCU118 导出交接（2026-09-22）

**后续完整候选：** 已另建 [SOC_CANDIDATE.md](SOC_CANDIDATE.md) 所述隔离包，
带入decoder、PLIC/MMIO及配套Linux，并显式去除被隔离的旧除法补丁。
本页保留早期六文件交接的原始范围和证据，不把它追改为新的整机验收结果。

**结论：六文件最小增量可以保留现有 FPGA 适配，已生成可审阅补丁；尚未应用，不是 FPGA/Linux/llama 签核。**
本次仅在 `ara_dsa_verification` 新增交接文件、运行 host 检查；未修改 RTL、依赖、checker、适配器或导出元数据，未运行仿真、Vivado、板卡或串口。

**后续基线变化：** 本快照生成之后，Sv39 实际 SoC 实验发现 ECALL 的 tval 错误
（R-90），后续异常矩阵又定位并修复 breakpoint/SSIP tval（R-91/R-92）；
验证分支已修改 CVA6 `decoder.sv`。下面六文件候选未包含这些修复，
不能再被称为“包含当前全部 RTL 修改”；后续导出需另行审核追加，并重新生成
输入指纹和验证证据。此处保留旧交接原始数据，不追改成未实际测试的新快照。

## 交付与边界

- [candidate.patch](../out/fpga-rtl-handoff-20260922/candidate.patch)：相对于导出根目录的 **6 文件、7 hunks、+23/-6**；不是完整文件覆盖。
- [candidate-manifest.json](../out/fpga-rtl-handoff-20260922/candidate-manifest.json)：精确 source/export/candidate SHA-256、路径映射、原子变更组、已有修复与保留项；`approved_for_apply=false`。
- [source-audit.json](../out/fpga-rtl-handoff-20260922/source-audit.json)：重新调用现有 `check_sources.py`，无 exception。封装完整性 `valid`（761 条校验），但 `accepted=false`：429 matched、12 differing、5 adapted_unreviewed、226 missing_source。旧报告不能替代此快照。
- [host-checks.json](../out/fpga-rtl-handoff-20260922/host-checks.json)：`git apply --check --whitespace=error` 通过；source 漂移、export 漂移、重复应用前像均被指纹门禁拒绝；1236 个已记录输入前后不变。
- [checker-tests.txt](../out/fpga-rtl-handoff-20260922/checker-tests.txt)：现有 source checker 的 **33/33 host 单测通过**，临时夹具仅在新交接目录生成并已清理。

## 逐文件策略

下表路径相对于导出 `rtl/`；Ara 对应当前 `hardware/src/`，CVA6/FPnew 对应隔离 `hardware/deps/`。证据编号见下节。

| 导出文件 | 变更策略与精确差异 | 已有证据 / 缺失验证 |
|---|---|---|
| `ara/hardware/src/ara_dispatcher.sv` | **候选，2 hunks**：检查 XLEN 高位含 VILL；`vsetvl` 不截断 rs2；非法配置归一化。export 与本 worktree HEAD 全字节相同，除这两处外与当前 source 相同；保留 VL slice、slide/layout、maintenance/backend 选择与 segment sideband。 | E1：11 个非法 vtype 及恢复、vsetvl 回归；缺 FPGA 配置执行、任意 SEW/LMUL/VLEN/RV32 组合。 |
| `cva6/core/acc_dispatcher.sv` | **候选，1 hunk**：仅补五类 fence 等待 accelerator L/S pending；现有 commit-ID、flush、queue-pop、port1 older-ack/SVA 保持不动。 | E2：50/50 fence、20/20 scalar consistency；E1 有整 SoC 代表回归。缺 FPGA FIFO、完整核心 fence/异常/flush 组合；response 不是 vector execution-done。 |
| `cva6/core/issue_read_operands.sv` | **候选，1 hunk**：CVXIF RAW 路径保留 `stall_i`；与上行组成不可拆的 `fence_issue` 组。 | E1/E3 代表回归；E2 不直接编译此模块。缺 rejected transaction、RAW、fence 叠加的完整核心定向覆盖。 |
| `cva6/core/csr_regfile.sv` | **候选，1 hunk**：仅 SSTATUS 写掩码按 RVV 门控加入 VS；既有 next-state VS/SD 汇总已在 export。 | E1：8 步 SSTATUS RMW、32 项状态/哨兵检查；缺 S-mode 权限、RVV=0 与 RVH/VSSTATUS 回归。 |
| `cva6/core/include/ariane_pkg.sv` | **候选，1 hunk**：SSTATUS 读掩码按 `Cfg.RVV` 加 VS。 | E1：读回与旧失败闭环；缺非默认配置。 |
| `cva6/core/include/riscv_pkg.sv` | **候选，1 hunk**：定义 `SSTATUS_VS=0x600`；与以上两个 CSR 文件构成不可拆的 `sstatus_vs` 组，不放宽共享 VSSTATUS 写掩码。 | E1；缺包配置矩阵。 |
| `ara/hardware/src/lane/vmfpu.sv` | **不改**：export/source SHA 均为 `2f7b2de426a5f7c89710eec96ff3b6af05635641d1b4fb808d1f7290f4958a41`，reduction 排除 narrowing、所有调用点及 THMULTI 已存在。 | E1/E3：vfredmax_boundary 与真正 vfncvt 配对、vstart/div/sqrt 代表点；缺全面 mask/背压/舍入/flags 与 FPGA 实例。 |
| `cva6/core/fpu_wrap.sv` | **不改**：当前 NaN-box canonicalization 和 THMULTI 选择全字节已匹配。 | E1：H/S/D 27 个算术事务、54 项结果/FCSR 检查；缺非 RNE、任意 flush/背压及 FP8/FP16ALT。 |
| `cva6/common/local/util/instr_tracer.sv` | **不改**：`NO_INSTR_TRACE` 日志门控已匹配；不是硬件功能修复。 | 字节一致；不能据此关闭差分 oracle 所需日志。 |
| `fpnew/src/fpnew_cast_multi.sv`、`fpnew/src/fpnew_divsqrt_multi.sv`、`fpnew/vendor/openc910/C910_RTL_FACTORY/gen_rtl/vfdsu/rtl/ct_vfdsu_round.v` | **均不改**：批准补丁的三个 postimage 已全字节匹配，不能再次叠加 C910 round 补丁。 | E3：cast/THMULTI 代表点；vfwcvt 未逐项核对 flags，PULP HOLD 强制反压仍缺。 |

## 必须保留的导出差异

- **dispatcher 适配器门禁未更新。** `dispatcher_fpga.py`/`dispatcher_control_fpga.py` 仅对旧 `e28714d0...` 整文件走快捷接受；主线已用 `slide_bound`、`active_register_mask`、`backend_req/layout_req` 吸收适配。当前 VILL source 为 `59afd489...`，VL-cast 检查不变，但 layout 报 `Upstream dispatcher function changed: slidedown_source_start`，control 单独调用也拒绝。补丁可按精确前像局部迁移，**不能据此声称 exporter 已兼容，更不能放松哈希门禁**。
- `ara/.../segment_sequencer.sv` 已与 source 一致。`ara/.../vlsu/{qbs/qbs_engine,akv/akv_engine}.sv`、`cva6/common/local/util/sram_cache.sv`、`common_cells/src/{cdc_fifo_gray,rstgen_bypass}.sv` 的现有适配器在内存重放后均精确等于 export。全部保留；这只是可复现对应关系，不是等价证明或 review exception，详见 [adapter-evidence.json](../out/fpga-rtl-handoff-20260922/adapter-evidence.json)。
- **`cva6/core/load_unit.sv` 不覆盖。** export 独有 WAIT_PAGE_OFFSET/WAIT_GNT 的异常退休、保持 translation request、防 data_rvalid 冲突及异常返回状态扩展；当前批准依赖补丁不含它。需独立检查 exception/data_gnt/data_rvalid/flush、pop 与响应唯一性、MMU 组合环；现有源码回归不能为此导出差异背书。
- **`fpu_div_sqrt_mvp/hdl/{control_mvp,defs_div_sqrt_mvp,div_sqrt_top_mvp,norm_div_sqrt_mvp,nrbd_nrsc_mvp}.sv` 不纳入候选，也不默默回退。** 五个 export 的 Git blob 均精确等于 quarantine 补丁 postimage，当前依赖则等于其干净 preimage。E4 已复现错误；默认标量/向量 THMULTI 不代表封装中的 PULP 代码获准。后续必须显式处理隔离/禁选与配置验证。
- Cheshire、DRAM、JTAG 等共 **226 个映射源缺失**，不可用 manifest 历史 hash 或同名文件冒充源码。此次不下载、不回查原 worktree、不做映射豁免；缺失清单在 manifest 中，交由系统依赖负责人处理。

## 证据与验收

[evidence-links.json](../out/fpga-rtl-handoff-20260922/evidence-links.json) 固定以下证据文件指纹；本次没有重跑 RTL：

- **E1**：[linux-state-prereq-fixed-20260922](../out/linux-state-prereq-fixed-20260922/summary.json) 四点 PASS（165 checks、vfredmax_boundary、vle32、vsetvl），同镜像冻结旧 87 项亦 PASS。归档 dispatcher/VMFPU/segment 及两份依赖补丁与当前输入逐字节匹配。它是 baremetal SoC，不是 Linux boot。
- **E2**：[CVA6 实测](../cva6/MEASURED_20260922.md)：132-cycle 实模块 contract；冻结 acc_dispatcher SHA 与当前相同。旧补丁 bundle `74a49bd0...` **不是**当前 `c11a2e6c...`，不把旧 CSR/package 输入算作新 SSTATUS 验证。
- **E3**：[dependency-baseline 六点](../out/dependency-baseline-vcs-20260922/summary.json) PASS；冻结 top-level patch 的 VMFPU postimage blob 与当前匹配。旧整机 baseline 不为后加 VILL/SSTATUS 背书。
- **E4**：[MVP 实测](../fpu/MEASURED_20260922.md)：八输入中五项架构错误、三项控制匹配，不是 DUT PASS。

只读复核命令（从验证 worktree 根目录执行，不会应用补丁）：

```sh
python3 -B verification/out/fpga-rtl-handoff-20260922/prepare_handoff.py --verify
```

接收方须先审阅六文件 diff/原子组与保留项，再在另建隔离导出中迁移；任一 source/export 指纹漂移均停止，不使用 fuzz/三方自动合并。后续单独审阅适配器兼容性、补全依赖对应关系并按导出流程重封装元数据；不得复用旧 SHA256SUMS、旧 bitstream 或本 host PASS 作为新硬件签核。实际 FPGA 配置回归、Linux VS/context/异常保存恢复及真实 llama.cpp 模型路径仍未验证，本轮不执行这些操作。
