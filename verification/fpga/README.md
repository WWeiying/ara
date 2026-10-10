# VCU118 验证入口

FPGA 负责扩大时间覆盖和系统软件覆盖，不能替代 VCS 的逐条差分和首错定位。每一次 VCU118 结果必须附带一个 manifest，至少包含：

```json
{
  "schema_version": 1,
  "board": "VCU118",
  "bitstream_tool": "Vivado",
  "vivado_version": "<version>",
  "rtl_commit": "<git commit>",
  "clock_mhz": 50,
  "flow_status": "COMPLETE",
  "bitstream_generated": true,
  "ddr_calibration": true,
  "reset_uart_smoke": true,
  "artifacts": {
    "bitstream": {"path": "ara_dsa.bit", "sha256": "<hash>"},
    "software": {"path": "Image", "sha256": "<hash>"}
  },
  "console_log": "uart.log",
  "console_markers": [
    "OpenSBI",
    "Linux version",
    "Ara DSA VCU118 Linux init reached",
    "Linux console, DDR and RVV handoff are alive"
  ],
  "tests": [
    {
      "name": "reset_uart_ddr", "status": "PASS",
      "command": ["board-test", "reset_uart_ddr"],
      "evidence": {
        "log": "evidence/reset_uart_ddr.log",
        "result": "evidence/reset_uart_ddr.json",
        "input_hashes": {"software": "<sha256>"}
      }
    },
    {"name": "baremetal_rvv_signature", "status": "PASS", "command": ["board-test", "baremetal_rvv_signature"], "evidence": {"log": "evidence/baremetal_rvv_signature.log", "result": "evidence/baremetal_rvv_signature.json", "input_hashes": {"software": "<sha256>"}}},
    {"name": "linux_boot", "status": "PASS", "command": ["board-test", "linux_boot"], "evidence": {"log": "evidence/linux_boot.log", "result": "evidence/linux_boot.json", "input_hashes": {"software": "<sha256>"}}},
    {"name": "rvv_fallback_userspace", "status": "PASS", "command": ["board-test", "rvv_fallback_userspace"], "evidence": {"log": "evidence/rvv_fallback_userspace.log", "result": "evidence/rvv_fallback_userspace.json", "input_hashes": {"software": "<sha256>"}}},
    {"name": "qbs_akv_userspace", "status": "PASS", "command": ["board-test", "qbs_akv_userspace"], "evidence": {"log": "evidence/qbs_akv_userspace.log", "result": "evidence/qbs_akv_userspace.json", "input_hashes": {"software": "<sha256>"}}},
    {"name": "context_switch_and_fault_return", "status": "PASS", "command": ["board-test", "context_switch_and_fault_return"], "evidence": {"log": "evidence/context_switch_and_fault_return.log", "result": "evidence/context_switch_and_fault_return.json", "input_hashes": {"software": "<sha256>"}}},
    {"name": "long_model_smoke", "status": "PASS", "command": ["board-test", "long_model_smoke"], "evidence": {"log": "evidence/long_model_smoke.log", "result": "evidence/long_model_smoke.json", "input_hashes": {"software": "<sha256>"}}}
  ]
}
```

每个 `tests` 条目都必须带有实际执行命令和
`evidence.log`/`evidence.result`，并记录非空的输入文件哈希。上面的路径是
结构示意，不能直接作为签核 manifest。签核检查还会要求 bitstream/software
的 SHA-256、四个固定启动 marker、`flow_status=COMPLETE`、
`bitstream_generated=true`，并拒绝控制台中的 panic/BUG/UVM_FATAL 等失败标记。

检查命令：

```bash
PYTHONPATH=verification python3 verification/fpga/check_run.py \
  --manifest verification/out/<run-id>/fpga/manifest.json \
  --output verification/out/<run-id>/fpga/check.json
```

`check_run.py` 的命令行入口始终使用严格检查。历史 manifest 若只有测试名称而
没有证据文件，只能作为历史记录，不能作为板卡签核依据。

签收前需要至少完成：裸机 DDR/复位/RVV signature、Linux 启动、RVV fallback、QBS/AKV 快速路径、非法/回退路径、上下文切换和长时间模型片段。bitstream、软件镜像、RTL commit、时钟、DDR 校准和控制台日志必须来自同一次板卡运行。

## 当前接入准备与待补项

2026-09-22 的只读检查确认 `hardware/fpga/ara_dsa_vcu118/` 已有 Vivado 工程、
约束、构建/烧录脚本，`linux/artifacts/` 有 OpenSBI、Linux Image、DTB 和 initramfs。
导出工程和四项启动载荷通过其现有哈希检查；这只说明工件完整，不证明当前功能
修复已进入导出 RTL，更不证明已上板通过。

| 项目 | 已有工件 | 下一步必要证据 |
| --- | --- | --- |
| 板卡连接 | UART 装载/读回/执行工具 | 板卡主机的串口、JTAG/hw_server、匹配的 bitstream；当前主机未发现板卡串口，本工作区没有 `.bit/.ltx` |
| 裸机快速路径 | `software/qwen_small_combined/qbs_akv.elf` 及脚本 | 当前修复版硬件运行相同输入，保留 RVV/QBS/AKV 校验结果 |
| Linux 启动 | 四项启动载荷、BusyBox rootfs | 实际启动日志、DDR 状态和用户态执行结果 |
| Linux 向量执行 | `verification/linux/userspace/` 短载荷已在 Linux/QEMU VLEN1024 通过 | 板卡运行同一载荷；QBS/AKV 小计算和隐藏状态隔离仍需验证 |
| 上下文切换 | 需独立核实 | 普通 RVV 状态及 QBS/AKV 隐藏上下文的隔离或保存恢复；不能假定 RVV 保存自动覆盖扩展状态 |
| 完整模型 | rootfs 不含 llama.cpp 和模型 | 匹配当前 ABI 的程序、GGUF 搬运/存储方案、2 GiB DDR 预算及数值检查 |

启动脚本中的 `RVV handoff are alive` 是固定输出，不能当成已经执行 RVV 指令的
证据。独立 rootfs 的小型用户态测试已补齐，仍须由板卡运行产生真实结果；不要
为了补齐签核字段生成模拟的 PASS 日志。

## 导出源码对应性检查

```bash
make -C verification fpga-source-check \
  FPGA_SOURCE_REPORT=/absolute/path/to/new-report.json
```

报告必须使用尚不存在的路径。`check_sources.py` 独立报告两类事实：

- `export_integrity`：文件是否符合导出包自身的 SHA256SUMS。
- `source_correspondence`：导出 RTL/header 是否对应当前源码；逐文件记录来源、
  两侧哈希、Git dirty/untracked 状态。没有源 checkout 时明确标为缺失，不能靠
  文件同名、历史 manifest 中的哈希或导出包自身内容证明来源一致。

已知 FPGA 适配也不自动豁免。若确实需要保留差异，必须提供带审阅人、理由和两侧
精确哈希的例外；更换任意一侧文件后例外失效。该检查不替代 elaboration、CDC、
时序或 bitstream 身份检查。

2026-09-22 的实际报告为
`verification/out/fpga-source-audit-20260922/report.json`：导出完整性有效，但源码
对应性未通过。672 个 RTL/header 中 427 个相同、14 个不同、5 个为待审阅适配，
226 个未找到当前工作树中的确定来源。这 226 项主要是尚未准备的 FPGA/Cheshire
依赖，并非声称导出文件本身缺失。

重点核查得到：VMFPU 文件与当前修复版逐字节一致；CVA6 的 `acc_dispatcher.sv`
和 `issue_read_operands.sv` 存在双向差异。验证工作区有新 fence barrier 和上游
stall 保留修改；原 `ara_dsa` 工作区及 FPGA 导出还包含 commit ID 匹配、第二提交
口授权、queue-pop 记账及 flush 清理等本地修改，未被当前依赖初始化过程带入。
因此不能把任一侧整文件覆盖另一侧。此后已在验证 worktree 合并并登记审核补丁，
完成相关短回归，但尚未部署到 FPGA 导出。最新待交接差异与保留项见
[CURRENT_RTL_HANDOFF.md](CURRENT_RTL_HANDOFF.md)。

## PLIC/Linux 配套门禁

完整隔离SoC候选现已生成，准备方法、输入核查、已带入修复和下一步load-unit
门禁见 [SOC_CANDIDATE.md](SOC_CANDIDATE.md)。状态为PREPARED_NOT_BUILT，
没有覆盖原导出或替代板卡验收。

进一步审核确认：旧导出为 32 槽/1 context、27-bit 寄存器地址，而实际 Cheshire
配置为 58 槽/2 contexts、26-bit 地址；旧 DTS 的 ndev51 也遗漏高位源。
这不属于向量算术错误，却会影响正常 PLIC MMIO 和 Linux 外部中断。
静态根因及源编号见 [PLIC_LINUX_GAP.md](PLIC_LINUX_GAP.md)，隔离生成、
真实物理地址的总线测试及配套软件流程见 [PLIC_BRINGUP.md](PLIC_BRINGUP.md)。
这些候选输入不自动覆盖旧导出；board manifest 仍需真实板卡执行证明。
