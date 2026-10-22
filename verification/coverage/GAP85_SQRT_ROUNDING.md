# FP32平方根舍入激励

新增`apps/riscv-tests/isa/rv64uv/vgap85_sqrt32.c`，用于继续覆盖C910
div/sqrt功能单元中的sqrt及round路径，不修改RTL。

45次`vfsqrt.v`覆盖5种frm、3种mask、VL64/63/1，e32/m2及tu/mu。
操作数包括正负零、正负Inf、quiet/signaling NaN、负有限数、平方根
精确的normal/subnormal输入，以及sqrt(2)的舍入方向差异。
使用固定IEEE原始位oracle；检查2970项结果、fflags和vstart，验证
全关mask抑制异常及tail/mask原值保持。

独立Spike已正常退出，2970检查、0失败、tohost写1，trap保持0。
预检在`verification/out/gap85-sqrt32-preflight-20261006-01/`，ELF
SHA256为`3bc569c610e75b199485e866d1a5918089c6df79f62171abd3271ae6ebe7c9f5`。

旧镜像后台服务为`ara-gap85-sqrt32-old-image-20261006-01.service`，
输出`verification/out/gap85-sqrt32-old-image-20261006-01/`。
启动前核对Spike签名和旧镜像全部可执行文件pins，限时600秒，收集
完整提交/向量轨迹及line/condition/branch/FSM/toggle VDB。
最初启动时未准入691集合；随后已完成下面的独立验收。

## 实际验收

VCS正常退出，CPU时间194.830秒；contract为405个请求/405个响应，
协议错误、异常和outstanding均为0。完整scalar差分匹配52534条提交
指令、trap0；vector比较180个请求、27240字节，未知字节跳过和
非逐位比较均为0，无incomplete/unretired/trapped请求。DUT签名2970/0。

`admit_gap85_offline.py`验证封存输入及691项正式无豁免报告的成员清单
后，独立准入并合并同Design覆盖位。结果在
`verification/out/gap85-offline-admitted-692-20261006-01/`。
集合692项PASS，相对691新增line2、condition13、branch2、FSM0。
没有修改RTL或原有失败项，692项DVE百分比尚待汇总。
