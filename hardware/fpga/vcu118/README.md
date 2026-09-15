# VCU118 导出工具

本目录是版本管理用的导出工具、板级封装和模板。
**Windows 直接使用已纳入 Git 的 `hardware/fpga/ara_dsa_vcu118/`，不是此模板目录。**
完整工程与本工具都位于仓库 `hardware/fpga/` 下，通过 GitHub 同步，不再生成 ZIP。

当前 FPGA 专用 JTAG 使用 SoC 时钟采样，J53 外部 TCK 限制为 1 MHz，
高低电平各至少 400 ns；不能继续沿用旧版 10 MHz 设置。
`jtag_fpga.py` 保留原 TAP 状态逻辑并替换时钟/DMI 传输，另将板级复位就绪信号寄存后跨域。
边界、测试和 Windows 重跑步骤见快照的 `README_WINDOWS.md`、`docs/FPGA_ISSUES.md`。

宿主机首次准备依赖需要 Python 3、PyYAML、Git、仓库现有 Bender 和网络：

```sh
python3 hardware/fpga/vcu118/prepare.py
python3 hardware/fpga/vcu118/export.py /path/to/new/ara_dsa_vcu118 \
  --gcc /path/to/riscv64-linux-gcc \
  --objdump /path/to/riscv64-linux-objdump
```

导出不会覆盖已有文件夹，避免覆盖 Windows 回传的改动。编译器不要使用 ZCC。
`prepare.py` 固定 Cheshire SoC/板级来源版本，保留原工程 RTL 依赖的实际工作副本。

## 增量同步已有 FPGA 包

在本项目中修改 `.sv`/`.svh` 后，使用下面的入口。默认目标是仓库内的
`hardware/fpga/ara_dsa_vcu118/`，也可以在命令后指定其他已导出的目录。

```sh
# 仅预览，目标目录不写入任何文件
python3 hardware/fpga/vcu118/sync.py

# 确认差异后应用
python3 hardware/fpga/vcu118/sync.py --apply

# 指定目标目录
python3 hardware/fpga/vcu118/sync.py /path/to/ara_dsa_vcu118 --apply
```

脚本刷新 Bender 源码清单，并通过原 `export.py` 在临时目录生成完整快照。
因此 FPGA 专用 SRAM、接口补丁、宏定义及源码顺序仍按同一个导出流程处理。
新增模块必须先加入对应 `Bender.yml`；不参与 FPGA target 的模块不会被强行复制进来。
若当前代码不再适合某项集成补丁，导出失败，目标包不更新。

无需为了普通 RTL 修改重新编译 smoke：输入源码/ABI 未变且旧产物校验正确时复用 ELF。
需要重编译时默认使用 `~/llama/platforms/cva6-qemu/tools/bin/riscv64-linux-{gcc,objdump}`，
也可以传 `--gcc` 和 `--objdump` 指定非 ZCC 工具链。

| 输出 | 含义 |
|---|---|
| `ADD` / `UPDATE` / `DELETE` | 新增、更新或删除导出流程管理的文件 |
| `LOCAL` | 只有 FPGA 端改过，保留该修改，包括本地删除 |
| `ADOPT` | 双方内容已经相同，只更新上游校验基线 |
| `CONFLICT` | 双方都改过且内容不同，整个同步停止，不覆盖任何目标文件 |

同步以旧 `SHA256SUMS`、目标实际内容和新快照三方比较，不按时间戳判断。
`build/`、`reports/`、`output/`、原验证 `.log` 和未被导出清单管理的文件不修改。
备份在目标包的 `.fpga_sync_backups/<UTC时间>_<编号>/`：
`files/` 保存被更新/删除文件的旧内容及旧校验表，`record.json` 记录操作和状态。
普通写入异常会回滚已操作文件；进程被强制杀死或断电时，先检查该备份及锁文件，不要盲目重跑。

遇到冲突时先比较两端，将需要保留的 FPGA 修改整理回本项目，然后解决对应文件，再同步。
不要通过重新生成 `SHA256SUMS` 来隐藏 `LOCAL`，否则会失去后续冲突检测的基线。
保留本地改动后，`verify_package.py` 继续报告这些差异，这是预期行为，不表示同步丢失了文件。

**同步时应关闭该工程的 Vivado 运行及文件编辑。** 脚本不会启动或终止 Vivado，
也不会自动修改 `.xpr`。已有文件的正文变化会更新原路径；新增/删除源码、改变宏定义或 IP 配置时，
虽已更新 `scripts/sources.tcl`，仍需手动刷新工程配置，或归档旧 `build/` 后重新创建工程。
旧的综合结果、bitstream 和验证日志不会自动更新，不能当作新 RTL 的结果使用。
同步后提交本目录和快照中的修改，再 push；不要提交被忽略的缓存、备份和 Vivado 产物。

### Windows 端同步

推荐直接在 Git 检出的工程目录中使用 Vivado，之后 `git pull --ff-only` 更新。
快照含 `.gitattributes`，固定文件字节，避免 Windows 的 CRLF 自动转换破坏校验值。

若还需保留原 `D:/fpga/ara_dsa_vcu118` 工程，可从 Git 检出的目录增量同步：

```powershell
# 先 pull 仓库，再从新快照同步到旧工程
py D:/project/ara_dsa/hardware/fpga/ara_dsa_vcu118/scripts/sync.py D:/fpga/ara_dsa_vcu118 --from-package D:/project/ara_dsa/hardware/fpga/ara_dsa_vcu118
# 检查输出后，在同一命令末尾添加 --apply
```

这个模式只需要 Python 3.9+，不需要 GCC/Bender/PyYAML。
新包和目标包不能互相嵌套；同步前检查 Windows 端的本地修改。

## 环境与检查

UART 工具所用的两个纯 Python wheel 需要先下载到 `.cache/wheels`：

```sh
python3 -m pip download --only-binary=:all: --no-deps \
  --dest hardware/fpga/vcu118/.cache/wheels pyserial==3.5 pyelftools==0.32
```

静态检查：

```sh
python3 hardware/fpga/vcu118/tests/test_export.py
python3 hardware/fpga/vcu118/tests/test_sync.py
python3 hardware/fpga/vcu118/tests/test_package.py hardware/fpga/ara_dsa_vcu118
tclsh hardware/fpga/vcu118/tests/check_tcl.tcl hardware/fpga/ara_dsa_vcu118
tclsh hardware/fpga/vcu118/tests/test_clock_io.tcl /tmp/ara_clock_io_check
# 安装 VCS 后，使用尚不存在的临时目录运行板级状态采样测试：
python3 hardware/fpga/vcu118/tests/check_status_sync.py /tmp/ara_status_check --vcs /path/to/vcs
# FPGA 独立 dispatcher 补丁的区间运算及逐周期对照，不调用 Vivado：
python3 hardware/fpga/vcu118/tests/check_dispatcher_layout.py /tmp/ara_dispatcher_check --vcs /path/to/vcs
# 安装 pyslang 后执行：
python3 hardware/fpga/vcu118/check_rtl.py hardware/fpga/ara_dsa_vcu118 --allow-vendor-ip
```

这里的 Tcl mock 不是 Vivado，pyslang 也没有 Xilinx IP 内部实现。
不能据此声称已经生成过 bitstream。Windows 使用方法见 `README_WINDOWS.md`。
