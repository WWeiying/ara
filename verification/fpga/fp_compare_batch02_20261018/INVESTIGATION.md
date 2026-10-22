# 批次 02：FP compare 原始失败复核

**最新：已扩展核查前七批中的全部六个 FP compare 失败 ELF，确认源布局转换去重
遗漏并修复，14/14 SoC/VCS 通过。完整根因、旧/新代码和证据见 [FIX_REPORT.md](FIX_REPORT.md)。
下文保留最初两项调查及运行预算记录，不代表修复后的最新状态。**

## 原始证据与当前结论

证据入口：`/home/wangwy/fpga_runs/ara_va_rvv_explore_20261018_02/summary.json`。
同批 64 个 ELF，旧 FPGA 镜像 62 PASS、2 FAIL，QEMU 64 PASS。
本目录的工作针对这两个失败程序，不把两个程序直接计为两个 RTL 根因。

| 原程序 | 首条保留的失败参数 | 原程序调用序号（从 1 开始） | 原板测表现 |
| --- | --- | ---: | --- |
| `rvv_fp_compare_unmasked_alias_v8_e32_m4` | op5、seed0、VL64、mode3、sticky0 | 319 | expected fflags16、actual0，errors9 |
| `rvv_fp_compare_unboxed_unmasked_alias_v16_e32_m1` | op2、seed27、VL32、mode2、sticky1 | 15286 | expected fflags17、actual17，errors2 |

`errors` 是原 oracle 的检查失败累计值，包含结果位、vstart、fflags、输出哨兵，
不是错误元素数。第一项缺失 NV 是确定的；第二项 fflags 相等，不能因此断言恰好
两个向量结果位错误。

批次 03 的 `collector_status.json` 已记录最终 64 PASS、0 FAIL。
这些结果来自旧板卡镜像，不验证当前验证分支的修复。

## 指令与检查器核查

- op5 是 `vmfne.vf v8,v8,ft0`；op2 是 `vmflt.vv v16,v8,v16`。
- 两条均无 `v0.t`，所以 mode3 的全零 v0 不会关闭 op5 的计算。
- 源组 v8/v16 满足 m4/m1 对齐；掩码目的与源组低寄存器重叠是测试有意覆盖的情形，
  不能按普通不允许重叠的算术指令处理。
- 第二项名字含 unboxed，但其失败指令是 vv，不读取标量浮点操作数。
  不能仅凭程序名字归因于 NaN boxing。
- op5/seed0 的标量是 +0，源元素15、31、47、63 为 sNaN `0x7f812345`，
  且都在 VL64 活动范围内，因此应置 NV。当前原检查器并非误把未活动元素算入 flags。
- 两个原始 Linux ELF 均已从原 C/汇编/fixtures 重建并逐字节匹配原 SHA256；
  记录见 `prepared02/*/original_rebuilt.elf` 和编译命令/日志。

## 复现设计

`run.py prepare` 生成四项：两个首错参数单点，以及分别保留319/15286次原调用顺序
的前缀。原汇编 helper 和原 oracle 不变，仅增加单点筛选/前缀停止，并把 Linux
启动、输出、退出封装适配为裸机 SoC 运行。diff、源文件哈希、ELF 哈希和参考日志
全部保存。**这不等于在 RTL 上运行原 Linux ELF，也不保持 Linux 调度/虚拟地址历史。**

四项 Spike 参考均通过，标记为 `PREPARED_SPIKE_4_PASS_NOT_DUT`，不能据此判 RTL PASS。

VCS 使用已有封存镜像：
`/home/wangwy/fpga_runs/indexed_fault_overlap_fix_20261018_02/image`。
启动前核查镜像、冻结记录及当前源 RTL 哈希。先双路运行单点，全部通过后才运行
两项原序列前缀。长项上限10800秒，超时不算通过；不修改 RTL、不重烧板卡。
结果入口为 `vcs_current01/*/result.json`，全部结束后生成 `vcs_current01/results.json`。

当前已完成两个单点，均为 SoC/VCS PASS：m4/op5 为175.16秒，m1/op2为186.19秒，
均返回原 oracle `cases=1 errors=0` 和固件成功。单点没有保留前序向量调用，不能关闭
完整原程序失败。

**运行预算修正：**查阅已有 `fp_comparison_original/fp682_cost_feasibility01.md` 和
`full17920_static_feasibility01.md` 后，不能合理预期原样15286调用前缀在三小时内
完成。该长项在刚进入前缀阶段后由父进程管理操作 SIGTERM 停止（PID3885002），
不是 DUT 自发失败、看门狗超时或测试通过。driver 将其保守记为 NOT_PASS，须结合
本条解释为 `HOLD_COST_BUDGET`，不可纳入 RTL 故障计数。319调用前缀继续在后台运行。
后续需要保留向量 helper 历史且经独立核对的标量 oracle 加速方案，不能盲目放大时限。

独立复核确认：原ELF重建SHA一致；四份Spike日志的实际完成调用数分别为1、319、1、
15286；当前image的编译清单、配置、镜像和冻结源均无漂移。本轮runner本身未自动
复核编译清单/配置哈希，此处由独立只读检查补齐。runner未启用`--long-prefix`时会
只统计所选项并可返回0，不能将其进程退出0理解为四项全部通过；本次实际传入该选项，
但长项因成本被主动停止，最终整批仍不能判PASS。运行期间不修改封存runner。

准备阶段 `prepared01` 因新 main 封装的缩进警告被 `-Werror` 拒绝，未执行 DUT；
修正封装后在独立 `prepared02` 中完成，不改变原 oracle 或关闭警告。

## 根因假设与区分信号

现有 indexed-overlap 修改不涉及 FP compare 的执行与掩码压缩，不能据此认定这两项
已修复。历史比较修复包括源坐标、NV 活动范围资格和 MASKU 满队列保护，但是否
覆盖本次失败必须用这两个原始序列验证。

特别核查：批次协议登记板卡 source commit 为 `adbc41505`，与当前 `1a951504`
比较，`lane/vmfpu.sv`、`lane/lane_sequencer.sv`、`masku/masku.sv`、
`masku/masku_operands.sv` 无差异，dispatcher 差异仅为 indexed load 重启布局。
因此不能声称已有比较修复是板卡之后新增、可以自然关闭本次失败。该结论是 Git
登记版本对照，不冒充逐文件核对实际 Vivado 导出源的证明。

若当前 VCS 复现，按同一 VID 追踪以下边界，再决定 RTL 修改：

| 边界 | 关键信号 | 可以排除/确认什么 |
| --- | --- | --- |
| 请求和布局 | op/id、VL/vstart、vm、源/目的 EEW、寄存器布局元数据 | 错误请求或重排，还是正确请求下游出错 |
| 实际 FPU 输入握手 | `vinsn_issue_q`、operand_a/b、input valid/ready | sNaN 是否真实进入 FPU，是否读错元素/旧数据 |
| FPU 返回 | tag id/op、processing id/op、processed result bit0/bit2、valid/ready | 结果和逐元素 NV 是否对应同一拍/指令 |
| MASKU 接收 | `fp_compare_nv_seq`、active mask、vm、`vrf_pnt_q`、operand valid/ready | NV/结果压缩错位或错误活动资格 |
| 提交 | MASKU fflags valid、acc_resp fflags、CSR busy/提交、VRF 写回与 mask store | 内部正确但 flags/结果提交或读回错误 |

op5 的 errors9 与“8个应为0的活动结果位被置1，再缺失1次 NV 检查”在数目上相容，
但原输出没有打印逐位结果，因此这只是需探针检验的预测，不是已观测到的根因。
旧 vd 合并问题能解释数据差异，却不能单独解释缺失 NV。

## 验收边界

单点通过而前缀失败，说明前序状态/时序需要追踪，不直接证明某个 hazard 根因。
前缀通过也不能关闭完整17920调用的 Linux 程序，更不能替代新位流板上复测。
已有 indexed-overlap 原始34项的修复后板测仍单独待验收。

查看后台状态：

```sh
systemctl --user status ara-fpcompare-batch02-20261018-01 --no-pager
tail -n 10 verification/fpga/fp_compare_batch02_20261018/vcs_current01-service.log
```
