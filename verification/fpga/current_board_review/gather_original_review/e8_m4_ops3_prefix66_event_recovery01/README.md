# Gather 已完成仿真的事件检查器修正

## 实测原因

原 M6 仿真实际运行 1639.143087 秒，monitor 返回 0，未超时。
控制台报告全部 66 次调用无错误，冻结的通用检查器报告 VALID、
1317045 行及零 CVX 异常。但严格数值检查器在 CSV 第 14 行遇到
`arch_start` 后报 `Cycle reversal/unknown event/exception`。

原检查器仅允许 retire、cvx_req、cvx_resp；冻结的 trace 协议还定义
arch_start、uop_alloc、uop_done。这是检查器事件白名单不匹配的直接
证据，不是新的 RTL 故障证据，也不是仅凭固件 PASS 即可验收的理由。

## 修正与验收约束

新 checker.py 仅调整模块路径和上述六种事件的白名单。协议观察器
继续检查请求、响应、架构请求和后端微操作的配对及完整性，未知事件
仍拒绝。原数值模型、源程序、私有 ELF 和封存的 RTL/镜像不变。

7 项 Host 测试已通过，包括旧检查器拒绝合法元数据的复现、未知事件、
周期倒退、协议配对错误，以及 prestart/tail/inactive/guard/vstart
数值错误的拒绝。Host 结果不等价于 DUT 验收。

recover.py 要求独立审核后显式绑定 checker 与 Host 哈希，只离线遍历
原 CSV 一次，同时重新核查通用协议与全部 66 次调用的数值：33792
结果、132 guard、66 次 vstart 和 858 条 helper 指令。必须确认输入
前后不变、真实 monitor 返回值为 0，才生成新的架构验收结果。

原 worker 的 ERROR、NOT_PASS 和 aborted 记录不修改，不补造退出码，
不重新运行 VCS。即使离线验收通过，也不关闭未知的 11 项历史卡死、
完整 2688 次父程序或 Linux 信号/上下文问题。

## 入口复核的实际拒绝与后继

首次 recover.py 调用实际退出1，在创建 offline01 和打开 CSV 之前拒绝。
原因是入口预期 replay/run.json 为 COMPLETE，但原 worker 的 cancel_event
在 POSTCHECK_EXCEPTION 后置位，runner.py 将其如实记为 INTERRUPTED、
status_counts 为 ERROR1。admission_attempt01.json 保留本次实际结果；
原始状态没有改写。

recover02.py 只将该入口要求改为精确的 INTERRUPTED + ERROR1，并绑定
自己的代码与前次拒绝记录。其他门槛仍包括准确的 POSTCHECK_EXCEPTION
原因、整数 monitor0、未超时、无失败标记及原数值模型。仅入口检查已
实际退出0，确认744 pins、原NOT_PASS、monitor0、generic VALID；未读取CSV。
完整数据验收必须等待后继代码独立审核及实际离线检查退出0。

## 实际离线验收

独立 REVIEW02 批准后，recover02 唯一一次原 CSV 遍历实际退出0，耗时
94.335351 秒。1317045 行、1314151 条退休记录、730 对 CVX 请求/响应、
352 对后端微操作均通过；33792 个完整容量结果、132 guards、66 次
vstart0 及858条 helper 退休记录全部符合原判据。输入pins前后不变。

结果SHA：`c86bf85d2b4f6215675b8cccd41f3545b1f2ad79b0873c0470a13dc2f81b6d6e`。
offline01/actual_exit.json 保存工具实际返回0的证据，不从结果文件或
进程消失推断退出状态。原worker失败记录保留，范围仅为66调用数值前缀。
