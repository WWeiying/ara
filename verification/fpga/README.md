# VCU118 验证入口

FPGA 负责扩大时间覆盖和系统软件覆盖，不能替代 VCS 的逐条差分和首错定位。每一次 VCU118 结果必须附带一个 manifest，至少包含：

```json
{
  "schema_version": 1,
  "board": "VCU118",
  "bitstream_tool": "Vivado",
  "vivado_version": "<version>",
  "rtl_commit": "<git commit>",
  "clock_mhz": 100,
  "ddr_calibration": true,
  "reset_uart_smoke": true,
  "artifacts": {
    "bitstream": {"path": "ara_dsa.bit", "sha256": "<hash>"},
    "software": {"path": "Image", "sha256": "<hash>"}
  },
  "console_log": "uart.log",
  "console_markers": ["OpenSBI", "Linux version"],
  "tests": [
    {"name": "rvv_fallback", "status": "PASS"},
    {"name": "qbs_akv", "status": "PASS"}
  ]
}
```

检查命令：

```bash
PYTHONPATH=verification python3 verification/fpga/check_run.py \
  --manifest verification/out/<run-id>/fpga/manifest.json \
  --output verification/out/<run-id>/fpga/check.json
```

签收前需要至少完成：裸机 DDR/复位/RVV signature、Linux 启动、RVV fallback、QBS/AKV 快速路径、非法/回退路径、上下文切换和长时间模型片段。bitstream、软件镜像、RTL commit、时钟、DDR 校准和控制台日志必须来自同一次板卡运行。
