# 访存组合候选的整机验收

## 版本和范围

候选：`/home/wangwy/fpga_runs/current_board_memory_candidate02/campaign`。
对照：`/home/wangwy/fpga_runs/current_board_integration_final04/campaign`。
候选包含 AddrGen 的 masked 普通访存资格检查、VLDU 异常前缀排空及
sequencer 的 fault-only load 完成等待。冻结输入和镜像身份由各目录中的
snapshot/image/plan 文件保存；旧对照不含这三项修改。

候选构建成功。三项相同ELF的Sv39测试及十项smoke全部PASS/returncode0；
后台服务已退出，不再是运行中的计划。

**后续算术回归已在此candidate02镜像独立完成38/38 PASS**，并非沿用
final04的通过结论；原ELF、oracle与镜像身份的独立复核见下节。

| Sv39程序 | 结果 | 墙钟秒 |
| --- | --- | ---: |
| alloff_fault | PASS | 331.95 |
| active_fault_retry | PASS | 331.84 |
| alloff_valid | PASS | 294.37 |

三项控制台均为 `MT_SV39_PASS`，沿用原程序的完整结果、异常及重启检查。
墙钟时间受宿主机影响，不用作处理器性能比较。新增八项扩展和原始Linux
信号程序不在这次13项验收范围内。

## 算术回归实测

`../integration/memory_regression_plan02/complete.json` 已终止为
`PASS_38_CANDIDATE02`。八项Sv39扩展02完整PASS后，父进程审核并启动
四路、首错停止的封存计划；没有重建镜像，也没有修改原程序或oracle。
这38项排除上述十项已通过的smoke。

| 原程序组 | ELF数 | 实测结果 |
| --- | ---: | --- |
| 原VL127 extension、大偏移slide | 1 + 6 | 全部PASS |
| 原始来源单例、组合、扩展 | 6 + 1 + 5 | 全部PASS |
| gather、比较异常原始来源 | 2 + 5 | 全部PASS |
| flags sequence、连续规约epoch | 1 + 1 | 全部PASS |
| 比较矩阵含prefix控制 | 4 | 全部PASS；主矩阵102/100/100子例 |
| extension矩阵 | 6 | 全部PASS；每组24，共144子例 |

独立审计重新检查38项原oracle标记、`BOARD_REPLAY_PASS`、tohost=0与
returncode0；当前输入ELF与封存副本、final04原ELF逐项哈希一致。
六组extension各有严格递增的trial0..23和24次整寄存器读回退休，合计144次。
flags序列保留8次规约+8次普通VFADD；epoch保留first_only/same_vl/changed_vl，
非零m8扩宽保留10子例。组合程序存在重复覆盖，不把这些数量相加为独立bug数。

审计重算752项计划pin、162项门槛pin及539文件快照，去重共907个路径，
不匹配为0；每项运行记录的simv及共享库哈希均与candidate02镜像一致。

- 计划SHA256：`1410586ddc6e00f7c55239f807497d214c1802c5727dbfb1e0ec1d684841a3bd`
- 镜像清单SHA256：`384515b7365200942d08fc7b34275d10eee676cf6ce0574935043020e87c7810`
- 快照清单SHA256：`b185f9fd8cc4a75ce5ab5ef240fb621511affd673bbc8b43fb7a2e8d64bad8a9`
- [逐项审计、oracle和证据哈希](../integration/memory_regression_audit01/finding.json)
- [原始终态](../integration/memory_regression_plan02/complete.json)、[逐项结果](../integration/memory_regression_plan02/replay/summary.json)

最长项e64/m8/vf8实测1025.95秒，在预定1200秒预算内；e32/m4/vf4与
e64/m4/vf4分别640.90、609.09秒。这些是宿主机墙钟时间，不是性能结论。
旧final04的TIMEOUT/CANCELLED及补跑记录保持原样；本节只接受candidate02
新运行的这38个程序，不扩展为Linux ABI、全部历史矩阵或所有性能路径通过。

## 正常路径周期对照

逐文件执行 `cmp -s`，下面十项的 `input.elf` 以及完整
`commit_trace.csv` 在上述两镜像之间均逐字节相同，所有比较退出码为0。
CSV包含周期字段，因此不仅是最终结果相同，已记录的退休和内部请求/
完成事件及其周期也一致。该结论限于这些程序，不宣称任意程序性能不变。

| 程序 | 两边相同的commit_trace.csv SHA256 |
| --- | --- |
| rvv_vadd | `4f5efbd610136190f9d0a126a0a07ebb712f7d4da172088671ecf36f12397768` |
| rvv_vslideup | `05c01e9ead8ab112186f70bf578fff73648a21d3e3671fc48f0363ca9f66ba40` |
| rvv_vslidedown | `72b683c55b1885fcf4675f275b196faa3764587af7fd58ceabacdc85f27fcef5` |
| rvv_vrgather | `21b71449bc2543ef83a977e8595044bd7b1419b088586eb5a7bee7789cd12337` |
| rvv_vmseq | `7d90bfff0247345ca941e79f4382455ddb0373828b3258ba82121cf14e90bfbb` |
| rvv_vfredosum | `71a5eb0195335ed8939dbe4b298226488e69a2ff72300ffec06d1bc170073502` |
| rvv_vfwredosum | `a985f715e932a28e466648b9d3f6d672c632e638ad85d17fe4f62684ac41602d` |
| qbs_control_smoke | `8b497a24d005d5d9f8d6a510f1e11a5e66db13db87f1b47ec27331f559a0db90` |
| akv_context_smoke | `4c3b1f482554c71b6b50cb77e7803ac18f25901aed41c0b3b5f10e0e621a63cd` |
| qbs_akv_handoff_smoke | `d10360e71a1f02449e04f6352676de9e1048e61f31154b6c060dc049120b7749` |

复核路径为两侧 `smokes/tests/<程序名>/{input.elf,commit_trace.csv}`。
这些正常控制不掩盖 masked 普通访存采用逐元素事务的代价：全一掩码仍
可能增加AR/AW及翻译次数，见 `REPAIR_CONTRACT.md`。异常等待仅在故障
路径延迟响应；不能用正常控制推导故障处理周期不变。

## 八项扩展的中断分析

`sv39_extended/candidate02_extended8_01` 被systemd外层20分钟期限终止，
runner记录为CANCELLED，不是程序已经报错或模拟器确认卡死。
只读重建结果见该目录的 `terminal_analysis.json`：八个功能场景、
十三个检查点、五次故障重试和八次S-mode ECALL已观察且满足oracle；
已完成5072次比较与Spike前缀一致，`mx_errors=0`、`mx_unexpected=0`。
最后1000条指令在1304周期内继续退休，停止在公共seed/guard检查阶段。

尚余1155次检查和最终恢复/完成标志，故整套保持INCOMPLETE，不计为PASS。
基于实际速度估计总模拟约1253秒，原内层1200秒也不足。
授权 `candidate02_extended8_02` 保持原ELF/镜像/oracle，以内层1800秒、
外层2100秒独立补跑；这些是预先限定的宿主机墙钟预算，不是RTL周期，
也不修改原中断记录。完整通过是后续38项最新镜像算术回归的启动门槛；
该门槛现已满足，后续实测结果见上文，不更改旧01状态。

补跑02已完整通过：模拟1251.50秒，含分析总耗时1293.97秒。
`complete.json`为`CANDIDATE02_EXTENDED8_PASS`，独立CSV检查为
`EXTENDED8_CSV_ORACLE_PASS`，6227次比较全部完成，最后周期1055787。
运行前后输入及镜像全部哈希一致。旧01仍保持CANCELLED，不回填成功。
结果范围是这八个Sv39场景，不代表Linux ABI或整个访存族通过。

## NF2 字段故障和重启

`segment_review/sv39/vcs_preflight01/complete.json`已记录
`CANDIDATE02_NF2_FOUR_PASS`，独立CSV检查为`NF2_CSV_ORACLE_PASS`，
4133次检查，最后周期1446260。模拟1590.94秒，连同分析1640.46秒。
镜像仍为candidate02，没有为段访存新增RTL修改。

| 原始来源参数 | 覆盖行为 | 结果 |
| --- | --- | --- |
| NF2/e16/m1/b3/mask0x24/split1 load | 不能在被屏蔽元素3提前故障；应在有效元素5故障并重试 | PASS |
| 同上 store | 双字段前缀内存及重启后的精确结果 | PASS |
| NF2/e16/m1/b5/mask0x24/split1 load | 元素5第二字段跨页，允许第一字段部分完成；保持vstart5重启 | PASS |
| 同上 store | 部分字段写入、完成前缀poison不被重写、最终内存及guard | PASS |

b3两项来自归档失败single；b5两项是原序列中的正向控制，不能把它们
都称为旧失败。原始源码/ELF及适配差异见`segment_review/SELECTION.md`。
测试使用真实S-mode/Sv39与M-mode异常重启，不冒充Linux信号帧、sigreturn
或原Linux可执行文件验收。NF7 indexed仍单独待验收。
