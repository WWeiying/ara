# M5 prefix2 终态复核入口

本说明位于封存输入之外。未修改 worker、plan、ELF 或旧记录；不启动第二次，不轮询长任务。

## 已知启动状态

2026-10-11 父进程报告：`ara-gather-prefix2-candidate05-01.service` active，MainPID `513485`，cgroup 正确，RuntimeMax 9600 秒、KillMode control-group。真实 M5 simv：ops1 PID `513506`，ops20 PID `513507`，使用原两份 SoC ELF。父负责一次 3 秒 trace 增长确认；本文不将尚未收到的增长结果或运行中状态标为 PASS。

输入 SHA256（本说明落盘前只读核对）：

- `prefix_replay.py`: `aeaa04e3bf9ba11e7302c896066f6b144bb4ec590eb2d8fb01ee5d23328c377f`
- `prefix_plan.json`: `293f376e169cfd434e7988804990c58a6ae07981bf72cfd5e34b2c4eead25409`
- `focused01/acceptance.json`: `6c963d2b5c1e858acb853c4a3f50ecf2dced01091bc2cc77e2cd2f1e1b735d51`

focused 已闭环：same2ELF、每例完整 514 oracle、returned vstart=0、exit0；M5 source origin0、scan128 index511、BE=ff/data79。start0 完整 commit_trace.csv 与 M4 字节一致（含 cycle 与非退休事件），严格控制 performance PASS。

## 完成后只读复核

输出入口：`prefix_vcs_candidate05_01/complete.json`，明细 `prefix_vcs_candidate05_01/replay/summary.json`。逐例以 summary 给出的 artifact_dir 为准，读取 `console.log`、`run.vcs.log`、`commit_trace.csv`、`input.elf` 和 `fulloracle98_gate.json`；若外层终止导致 complete 缺失，保留现场，不推定 PASS。

仅在两个 case 均终态后进行一次离线复核：

1. 要求 complete 为 `PASS_TWO_AUTHENTIC98_PREFIXES_M5`、runner_returncode=0、两例严格 gate 齐全；核对 worker、plan、focus acceptance、M5 image 与私有 ELF 身份未变。
2. 每例原序列 98 calls，完整 50176 scalar oracle 加 196 guards（共 50372 输出读取），原 13 asm、call setup、vstart 返回与统计、encoded exit0 全部通过；逐条 CSV 数值证据不能由 summary PASS 替代。
3. console 与原 simulator log 不得有失败/abort/trap marker。若 FAIL/TIMEOUT/CANCELLED，仅保存并报告第一条原始错误、PC/cycle 与 peer 取消关系，不重跑、不增预算、不改 RTL。

同 ELF SHA256：ops1 `e3f79fd61e9d3d35ffc1773ba9599630ec69bdbc42b117c103f1b48a367941e5`；ops20 `be97b7369ae580019755ac4c5d6e331677050d110943e777142441594490c7f2`。

范围仍为两个 authentic child 98-call prefixes；原归档 stopped tuple 未知，不等同原 Linux ELF 重放、11 stalls 精确重现或 full parent closure。当前 prefix 尚未终态验收。
