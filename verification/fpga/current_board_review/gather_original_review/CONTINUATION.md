# Candidate04 剩余七项独立续跑

## 旧终态与精确错误

`successor01/vcs_candidate04_01/complete.json` 保持 NOT_ACCEPTED。control simulator 实际 exit0，29.311663秒，完整 RVV_PERMUTE_PASS cases=1/errors=0、BOARD_CASE_PASS、BOARD_REPLAY_PASS 和 Core Test SUCCESS/tohost0；独立 gate 为 PASS_CONTROL。提交轨迹9548行、9491条退休、最终cycle16512，cycle16503在PC0x80000072向CTRL 0xd0000000写退出值0，最后PC0x80000076是合法退出自旋。

worker错误为 `ValueError('Startup confirmation missing')`。原启动线程在找到loader进程后立即取样，固定3秒后要求CPU、trace bytes、cycle、exe与cgroup同时满足；早期未进入可见退休区间就可能 NOT_CONFIRMED。异常分支丢弃采样，因此不能从旧记录声称哪个具体子条件失败。旧 actual_simv_confirmation.json 确实存在，内容是NOT_CONFIRMED/Real simv advancement not confirmed，而非文件不存在。随后worker额外require ADVANCING，覆盖原runner rc0为1。这是wrapper启动确认门禁失败，不是环境launcher缺失或RTL/oracle失败。旧服务不重启，旧脚本不修改。

## 续跑与门禁

新 `replay_continuation04.py`、`check_continuation.py` 仅执行未启动的七项。control固定锚定旧plan SHA256 `a132b635e168317e013cccbf1e6a4b938b54330923ae5f3abd98d86b85f7314b`；每次独立重验旧raw oracle、exit0、private ELF、trace、image与全部pins，不用启动监控文件代替终态检查，不重跑control。

新输出 `successor01/vcs_candidate04_remaining7_01`，新unit `ara-gather-tuple7-candidate04-cont01.service`。输入仍为同一candidate04镜像和同一successor01的八个SoC ELF；没有重新编译、没有提高300秒预算、没有修改RTL。cap24、NF7两路reserve、MemAvailable至少32GiB、不与Tesla comparison冲突。剩余七项jobs2、首错停、Restart=no、无自动重试。

worker内部启动观察只在60秒startup窗口内发现两个真实simv，先等待非零trace/cycle及正确exe/cgroup，再取两次相隔3秒的样本。无论成功失败都保存原始样本、每个增长/身份子条件及发现过程；没有长跑完成轮询。其最终PASS仍要求七项完整oracle/exit0、独立trace/ELF/pin检查，以及真实两路PID/CPU/trace/cycle增长记录。

`test_continuation.py` 使用host故障注入复现startup文件缺失、存在NOT_CONFIRMED、fast-finished的控制记录；只有独立raw control验收成立才允许继承。另有失败oracle/非零退出拒绝、进度不增长拒绝、所有输入pins与ELF不变检查。测试不启动DUT。

命令：`python3 -B verification/fpga/current_board_review/gather_original_review/replay_continuation04.py --launch`。终态由新目录complete.json记录，合并结果明确命名为一个继承control加七个新single，不是八项重跑、原Linux ELF、父矩阵或板级验收。
