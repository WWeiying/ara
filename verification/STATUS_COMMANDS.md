# 后台验证状态命令

在验证主工作树中运行：

```bash
cd /home/wangwy/openproject/ara_dsa_signoff_integration
./vstatus                 # 最新登记任务：阶段、服务状态、各阶段计数
./vstatus jobs            # 每个点的状态
./vstatus log             # 首错日志；无首错时显示当前一个运行点的日志尾部
./vstatus status --all    # 所有登记任务，包括已停止的历史任务
./vstatus jobs coverage   # 指定任务，可选 coverage / seed509
watch -n 10 ./vstatus     # 手动实时查看；Ctrl-C 只退出查看，不终止验证
```

命令只读，不启动、停止或修改验证结果。`log -n 60` 可增加显示行数。
在其他目录也可使用该工作树下 `vstatus` 的绝对路径。

| 状态 | 含义 |
| --- | --- |
| RUNNING | 报告仍在执行且对应服务存活；不代表所有测试已通过 |
| PASS | 对应任务已通过其检查；不代表整个处理器已完成 signoff |
| FAIL / STOPPED | 发生失败或任务停止，查看首错路径和日志 |
| PENDING | 尚未执行 |
| CANCELLED | 因停止策略取消，不能算通过，也不等于该点本身失败 |
| STOPPED/STALE | 报告仍写 RUNNING，但服务已不运行，不能当作成功 |
| UNKNOWN / CONFLICT | 状态无法确认或报告与服务冲突，需要检查 |

计数按调度阶段显示，可能含编译任务，因此不是全部都属于功能 case。
历史 coverage 任务的失败不会在新修复通过后被改写成成功。
命令不把旧镜像覆盖率当作当前 RTL 覆盖率，也不推算未经测量的进度百分比。

新建后台任务时，在 `verification/status_runs.json` 追加名称、输出子目录和
systemd 用户服务名。最后一项是默认任务；目录内读取 `validation.json` 或
`checkpoint.json` 及各 `*-scheduler/status.json`。本命令只展示登记的任务，
不声称自动识别本机全部进程。
