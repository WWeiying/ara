# Seed 509 分段 Store 停滞定位

## 范围与证据

验证主线为 `ara_dsa_signoff_integration`，本次不修改产品主工作树。
原始失败保留在 `out/coverage-checkpoint-20260926-02/functional/short-memory-509/`。
前 283 条提交指令与 Spike 一致，下一条是 PC `0x80000412`、编码
`0xea525a27` 的八字段跨步分段 store。其架构配置为 SEW=64、LMUL=1、
VL=3、vstart=1；访存 EEW 为 16，不能把 SEW 当成此次存储的数据宽度。

## 可证伪的根因假设

普通 store 的提前接收逻辑错误地接受分段 store 的第一个内部请求，
让 CVA6 撤走原指令并让 dispatcher 进入 `WAIT_STORE_RESPONSE`。
但 segment sequencer 还需要原指令继续产生后续字段。两者相互等待，
因此并非增加 watchdog 或等待内存返回就能解决。

区分信号为 CVXIF 请求/响应握手、dispatcher 状态、segment 状态与字段计数、
后端地址确认、W.last、B 响应和 store_complete。若 B 一直未返回，或者
segment 仍持续派发字段，就不符合该假设。

## 原镜像逐周期实测

复用原镜像的现有探针，不修改 RTL，不重新生成随机程序。
`out/seed509-store-probe-20260926-01/probe.csv` 记录周期 1300--1700：

| 周期 | 实际行为 |
| --- | --- |
| 1468 | 原分段指令在 CVXIF 被接收，后端 ready 仍为 0 |
| 1469 | dispatcher 进入状态 15 (`WAIT_STORE_RESPONSE`)，原输入指令已撤走 |
| 1473 | 后端地址请求已确认 |
| 1479 | W.last 握手 |
| 1484 | B 响应到达 |
| 1485 | store_complete 有效 |
| 1486 | 第一个内部 store 完成，后端 ready 恢复 |
| 1487 后 | 后端空闲，但 dispatcher 仍等待完整架构指令的响应 |

`out/seed509-segment-probe-20260926-01/run.vcs.log` 的 segment 探针进一步确认：
状态停留 `SEGMENT_MICRO_OPS`，字段计数为 1，nf=7，输入 valid=0、ready=1。
因此只完成了第一个字段，后续字段没有继续派发。两个短复现使用相同 ELF、
同一 seed；缩短的是无进展 watchdog，不是修改功能输入。

## 修复边界与验证要求

提前接收必须排除尚在分段派发中的 store；不能依赖 blocked-decode 清理后
已恢复默认值的组合译码标志。普通 store 的提前接收必须保留，whole-register
store 也不能仅因为编码中的 nf 非零就被误当成分段 store。

修复后应先重放原 seed509，要求严格比较完整通过，再检查分段 load/store、
非零 vstart、whole-register store 和非法分段指令恢复。AXPY 使用同一 ELF
比较修复前后周期，不能将本次局部修复与历史其他 RTL 修改混为一谈。

本文记录的是已测得的故障根因；修复验证结果以独立新运行目录中的报告为准。

## 已实施的 RTL 修改

`hardware/src/ara_dispatcher.sv` 的提前接收条件新增
`!pending_seg_mem_op_q`。该状态位在分段派发前建立，最后一个字段完成后释放，
不会被 blocked-decode 的组合默认值清理掉。它比检查 `nf == 0` 更准确：
whole-register store 可以具有非零 nf，但并不通过分段状态机派发。

本次没有改变 VSTU 的 B 响应规则、普通 store 的提前接收时刻或增加流水级。
另在 `FOR_VERIFY` 范围加入断言：分段内部 store 接收时，不允许提前置位
CVXIF request-ready 或进入 `WAIT_STORE_RESPONSE`。
普通 store 的性能不变是待实测检查的预期，不能据此提前宣称回归通过。

## 独立验证任务

服务 `ara-seed509-fix-20260926-01.service` 已启动，结果目录为
`out/seed509-fix-20260926-01/`。启动时处于 VCS 编译阶段。
先重放冻结的 seed509 ELF 并进行完整标量/向量对比及独立审计；通过后，
至多五路并行检查 vlseg、vssseg、vsseg、vsuxseg、vsegment_emul_edges、
vwhole_vstart_edges、villegal_segment_recovery 和 AXPY。
任何失败都会停止，不自动调整 RTL 或重试。

编译前对原镜像的 457 个输入逐一核验，只有 dispatcher 文件不同。
任务还会比较新旧编译选项、配置和文件列表。AXPY 使用原 2810-cycle
记录的同一 ELF；新周期大于 2810 即判性能检查失败。后台任务状态以
`validation.json` 为准，此处的启动记录不代表上述测试已经通过。
