# Dispatcher store-response FSM 结构候选

## 镜像和源码绑定

旧镜像编译源码的Dispatcher SHA256为
`9af95c3eee6c63ecd9e60bf6d7c6474bdaaf1c5f96cef1bd653a6d51c6a2dd43`。
当前integration工作区该文件已有后续修改，第一次绑定检查正确
拒绝了它。`/home/wangwy/openproject/ara_dsa/hardware/src/ara_dispatcher.sv`
与旧编译哈希逐字节一致，后续分析只使用这个经哈希绑定的副本。
若副本变化，检查必须停止，不能改用不匹配的当前源码。

## 结构推导

1. `decode_blocked`组合默认值为0，仅有一处其他赋值，位于
   `if (arch_decode)`内部；它没有其他过程或寄存器驱动。
2. `arch_decode`仅可能在NORMAL_OPERATION、OVERLAP_ISSUE_ORIGINAL、
   WAIT_IDLE和WAIT_IDLE_FLUSH四个主状态为1；后两者还受额外条件
   约束。这是主FSM的`state_q`，不是LSU子FSM的`lsu_ex_state_q`。
3. 唯一的`state_d = WAIT_STORE_RESPONSE`赋值要求
   `ara_store_accepted_i && decode_blocked`及有效非segment store。
4. 因此，其他主状态中decode_blocked恒为0，无论backend ready、
   响应或输入请求如何，都不能通过该赋值进入WAIT_STORE_RESPONSE。

700项原始FSM诊断中，以下11个状态到WAIT_STORE_RESPONSE的边
全部未命中，符合上述结构条件：

- OVERLAP_CAPTURE、OVERLAP_FIXUP、OVERLAP_PREFIX_FIXUP、OVERLAP_RESPOND。
- OVERLAP_WAIT_CAPTURE、OVERLAP_WAIT_FIXUP、OVERLAP_WAIT_ORIGINAL、OVERLAP_WAIT_PREFIX_FIXUP。
- RESHUFFLE、SOURCE_SNAPSHOT_CAPTURE、SOURCE_SNAPSHOT_WAIT。

`test_dispatcher_store_fsm_scope.py`三项源码绑定检查通过。测试使用
字边界区别`state_q`与`lsu_ex_state_q`，避免子状态名称污染候选集。

## 不扩大排除范围

这不是整个FSM的不可达结论。其他未命中边，例如四个可译码状态
之间的控制交互、prefix fixup到capture的条件边，均需另行分析。
不因“没软件能触发”而排除错误恢复、异常、reset或有效stall路径。

当前只是结构候选：尚未绑定DVE的精确FSM原生edge标识、checksum
及向量，也未做export/reset/import/邻点保护验证。因此没有生成
可自动应用的exclusion，没有修改VDB或正式FSM百分比。

## 701项原始坐标复核

`inventory_dispatcher_store_fsm.py`重新核对已准入701项的bitmap、
原生FSM shape哈希和Dispatcher定义，确认总体checksum
`1099616778`、宽度92。主FSM名state_q，机器checksum
`4130774747`。结构候选精确11个，其他81个状态/边记录全部保留。
目标全部未命中，任何未来命中都必须否决相应结构推论。

证据为`verification/out/dispatcher-store-fsm-candidates-701-20261006-01.json`，
保存完整state/transition属性、from/to ID、原始诊断坐标及证据哈希。
原始坐标不是DVE exclusion编号；当前`native_binding_verified=false`、
`exclusions_applied=false`，不能将这个JSON直接作为豁免文件。
