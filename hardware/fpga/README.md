# VCU118 FPGA 工程

| 目录 | 用途 |
|---|---|
| [ara_dsa_vcu118](ara_dsa_vcu118/README_WINDOWS.md) | 完整、自包含的 Vivado 工程输入；Windows 直接使用这个目录 |
| [vcu118](vcu118/README.md) | Linux 维护工具、板级模板、增量同步脚本和回归测试 |

工程名仍为 `ara_dsa_vcu118`。本目录不保存 ZIP，不提交 Vivado 生成的工程、
综合/实现产物、日志、缓存、临时仿真或历史备份。
完整快照包含开源 RTL、板卡定义、约束、脚本、UART 工具及 smoke ELF，
不需要在 Windows 初始化 RTL submodule、安装 Bender 或解析 Linux 软链接。
Xilinx IP 仍由用户安装的 Vivado 生成，不随仓库分发厂商工具或器件库。

## Windows

可以只检出完整工程目录，减少无关文件：

```powershell
git clone --branch ara_dsa --single-branch --sparse https://github.com/WWeiying/ara.git D:/project/ara_dsa
git -C D:/project/ara_dsa sparse-checkout set hardware/fpga/ara_dsa_vcu118
py D:/project/ara_dsa/hardware/fpga/ara_dsa_vcu118/scripts/verify_package.py
```

在 Vivado Tcl Console 中：

```tcl
cd D:/project/ara_dsa/hardware/fpga/ara_dsa_vcu118
source scripts/create_project.tcl
source scripts/synth.tcl
```

后续通过 `git pull --ff-only` 更新，先关闭正在运行的 Vivado 任务。
已有 XPR 在路径不变且编译清单未变时可以继续使用，但修改 RTL 后必须重新综合。
从旧 `D:/fpga/ara_dsa_vcu118` 切换到新路径时，应在新路径重新创建 XPR；
也可以继续使用旧工程，按 Windows 说明中的兼容流程从 Git 检出目录同步源码。
详细的复位、烧录、UART 启动和 Linux 边界见工程内 `README_WINDOWS.md`。

## Linux 维护

从仓库根目录运行：

```bash
python3 -B hardware/fpga/vcu118/sync.py
python3 -B hardware/fpga/vcu118/sync.py --apply
python3 -B hardware/fpga/ara_dsa_vcu118/scripts/verify_package.py
git add hardware/fpga
git commit -m "Update VCU118 FPGA source snapshot"
git push origin ara_dsa
```

`sync.py` 默认更新同目录下的 `ara_dsa_vcu118/`，不再写仓库旁边的旧目录。
它执行 FPGA 接口/语法兼容补丁、更新源码清单及校验值，并保留本地 Vivado 产物。
不要只修改主 RTL 后就认为 FPGA 快照也自动更新了；提交前应完成上述同步。
需要板级改动时先修改 `vcu118/` 模板，再同步快照，避免两个副本长期分叉。

快照中的 `.gitattributes` 禁止 Git 自动修改换行，确保 Windows 检出的文件
与 `SHA256SUMS` 一致。`.gitignore` 排除本机产物，并保证原仓库的
`cheshire/`、`debug/` 等忽略规则不会漏掉快照必需的依赖源码。
