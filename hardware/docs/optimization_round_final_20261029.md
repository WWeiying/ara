# 本轮软硬件优化结论

本轮按 `optimization_exit_criteria_20261029.md` 的有限验收标准结束。
交付位于 `ara_dsa_signoff_integration` 验证分支，未自动合入其他分支或推送。
本结论不是处理器全功能 signoff，也不表示已经穷尽所有优化空间。

## 保留的修改与效果

| 项目 | 原周期 | 优化后周期 | 加速比 | 统计范围 |
|---|---:|---:|---:|---|
| M4 激活准备 | 76060 | 44443 | 1.711406× | 准备阶段 |
| M4 parallel sums + QBS retirement | 582799.5 | 547856 | 1.063782× | 完整 Q/V/K 切片，原版已经启用 QBS |
| Register-PV Decode，当前 RTL | 47882.5 | 43072.5 | 1.111672× | 真实 Qwen3、D128、GQA2、20 个可见 token 的完整 C 调用 |
| Grouped Prefill，Q4_0 K | 174314.5 | 147469 | 1.182042× | 四个 query 的因果前缀切片 |
| Grouped Prefill，Q8_0 K | 179726 | 148884.5 | 1.207151× | 同上，K 格式不同 |

准备阶段收益已经包含在完整投影结果中，不能再次累乘。Attention 和投影
加速比也不能相乘形成整模型加速比。这些是本轮增量优化，不是最初 QBS
与普通 RVV 的差距。完整模型 RTL 吞吐未在本轮测得。

硬件只保留已验证的 final-dot retirement 改动；不增加计算阵列、不扩大
队列或缓存、不改变点积数值顺序。软件保留 parallel sums、Register-PV
与 grouped Prefill 的受控实现，均沿用运行时适用性选择与 fallback。
源码入口、构建开关和运行期开关见
`runtime_integration_current_20261029.md`；这些优化仍为显式选择，不是默认
覆盖全部模型、格式和上下文。

## 未采纳的候选

- Prepared-cache hint-first 查询：实测准备调用退化，不采纳。
- Prefill query guard 分支调整：完整调用退化，不采纳。
- 复制式 V 缓存：两路超时，不能判 PASS，不补跑。
- 直接读取 V 缓存：完整检查通过，但 Q4/Q8 分别退化 3.835733% 和
  4.269561%，不采纳。相关完整输出、协议与身份检查均通过。

所有候选均保留独立实验源码和原始记录；没有为了得到较好结果而修改
生产路径、降低检查标准或把失败改为通过。本轮不再追加这些方向的变体。

## 最后一项当前 RTL 回归

`verification/out/register-retirement-final-20261029-01/result.json` 为 PASS。
保持原始 guarded ELF，唯一显式接受的 RTL 差异是已审查的 retirement 更新。
每试次核对 256 个输出、20 个 V 行和一个 QBS 命令；配对输出逐位相同，
异常标志一致，独立协议检查 PASS 且无 issues。当前结果比旧 RTL 下的
对应两条路径各减少 3 个平均周期，未发现此次更新导致性能退化。

历史 Prefill 加速比来自原始已通过的旧 RTL 比较，未重标为新 RTL 结果。
当前 RTL 的两路 V-pointer 对照同时运行未修改的生产 Prefill 基线，验证了
真实 Q4/Q8 输入、八个 query、两个分组的生产路径输出。普通 RVV 与
Attention 的 retirement 代表性回归也已通过，具体范围见
`qbs_retirement_acceptance_20261029.md`。

## 结束清单核对

| 条件 | 结论与证据 |
|---|---|
| E1 任务终态 | 四路缓存实验及最后一项回归的服务 MainPID 均为 0；超时状态保留 |
| E2 候选决定 | 有效修改保留；hint、guard 和两种 V 缓存拒绝，决定文档及原始结果保留 |
| E3 正确性 | 定向/协议证据、普通 RVV 代表回归、当前 RTL Register-PV 回归已核验；没有因本轮候选引入未解决的生产错误 |
| E4 运行时集成 | 已审查的 CMake、后端分派和共享 SDK 实现仍与模型测试源码匹配；普通实现与 fallback 保留 |
| E5 模型数值 | Qwen2.5-1.5B 与 Qwen3-1.7B 的 Q4_K_M 模型、Q4_0/Q8_0 K-cache、Q8_0 V 配对证据通过，合计 1,823,232 个 logits 逐位一致；这是功能而非 RTL 吞吐证据 |
| E6 性能口径 | 完整调用 ABBA 与阶段计时区分，投影原分母复核，未用 QEMU 时间声称硬件性能 |
| E7 可复现 | 源码/ELF/镜像/报告哈希核验，外部运行时 814 份已测源码归档，版本提交及生成脚本保留 |
| E8 最终交付 | 本文汇总保留/淘汰决定、实际收益、适用范围与未测范围 |

最终无仿真重跑的证据审计：
`verification/out/optimization-final-evidence-20261029-01.json`，状态
`ROUND_EVIDENCE_REHASHED`，核验 3,546 个唯一证据文件。脚本为
`verification/qbs/tile_boundary/final_evidence_audit.py`。历史 RTL 差异仅以
明确的新旧哈希及旧源码归档处理，不忽略任意源码漂移。

外部运行时归档：
`verification/out/optimization-runtime-snapshot-20261029-02`。其中保存基准
提交、源码副本、哈希与工作区差异。未提交差异包含先前工作，不把全部差异
归功于本轮；没有擅自提交或清理外部仓库。归档和大体积原始实验文件在
本机，未声称它们已上传远端。

后续如需综合/PPA、FPGA、整模型吞吐、更多模型或更长上下文，应作为新的
明确任务。本轮不再以这些尚未要求的扩展延长优化过程。
