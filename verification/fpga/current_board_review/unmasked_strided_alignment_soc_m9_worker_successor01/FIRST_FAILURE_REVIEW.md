# M9 首次整机执行的检查器阻断

首错是 `strided_alignment_store_m` 的后处理检查器错误，尚无本次RTL
数值错误证据。原终态 `NOT_ACCEPTED_LATE_ABORT`、firstfailure和原始CSV保留。

## 实际执行证据

- store_m的真实child退出0，52.208243秒，无timeout/failure/abort；
  控制台包含STRIDED_ALIGNMENT_PASS及正常tohost0/$finish。
- load_m的真实child退出0，52.666754秒，无timeout/failure/abort；
  worker在store检查器失败后拒绝其aggregate acceptance，不能仅凭
  child0计入完整架构验收。
- load_sv39和store_sv39未获调度，ERROR记录原因是首错后禁止dispatch，
  不是这两项发生了RTL错误。

## 根因与判别证据

store_m的checker.log显示 `check.py:142` 报 `KeyError: tohost`。
Observer对每个实际scalar store先执行
`a in (self.s['tohost'], 0xd0000000)`，因此在SoC的符号表不含tohost时，
即使当前store并非退出操作，也会在查找第一元组成员时中止。
Spike参考ELF有HTIF tohost；本次SoC ELF使用真实CTRL寄存器退出。
已有Spike bridge未覆盖这一SoC符号契约差别。

修复方向是独立后继的backend退出契约：按实际hash绑定ELF/spec检查
符号与控制寄存器store，Spike保留HTIF要求，SoC验证CTRL路径；不伪造
缺失符号，不关闭退出检查，不修改RTL或已有oracle。增加真实SoC
spec与scalar store行的Host反例，随后离线一次完整核验两份关闭CSV。
M-mode通过后，只对尚未运行的Sv39两项建立新计划。

以上不是两项DUT完整通过声明，也不允许重写旧NOT_ACCEPTED记录。
