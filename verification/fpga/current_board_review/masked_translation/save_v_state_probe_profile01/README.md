# save_v_state CSR 等待：未来聚焦探针配置

状态：**静态配置完成；未采集、未elaborate、根因未关闭。**
仅新增本目录。未访问现板，未运行仿真、编译或任何后台任务查询。

## 范围与版本

- `profile.json` 是自描述信号清单及触发契约，不是现有runner可直接执行的profile。未来collector须显式适配，不可将未知字段静默忽略。
- 已检索到的indexed Sv39 diagnostic profile面向另一个裸机故障，使用固定绝对时间和较宽LSU范围，不覆盖H0–H4，因此没有复制其触发时间或递归scope。
- 逐项采用源代码中的实例/端口/struct成员，82个叶信号共954bit。16个相关源文件当前工作树与M9冻结副本哈希均一致，具体SHA和声明位置在JSON中。
- 源级路径根为 `ara_tb.dut.i_ara_soc.i_system`。这是VCS testbench层级，不是原FPGA的综合网名。未检查优化后信号可见性；未来采集前必须逐信号解析路径与宽度，缺失/不符直接拒绝，不猜别名。
- 当前CPU请求缓冲实际实例是 `i_accelerator_req_register`（两槽fall-through），不是假定的spill实例名。本配置只探其两侧已核实的接口，不依赖错误内部路径。
- M9源绑定与原campaign的dispatcher/sequencer/ara哈希不同；历史源可解释候选路径，不能拿M9状态枚举或新增memory完成锁存直接解释旧位流。原板LTX/ILA仍缺失。本配置不能证明现板版本或复现原Linux环境。
- CVA6的VLEN=64是地址位宽；Ara向量VLEN=1024，对应vlen_t=11bit，二者不可混用。ID=3bit，两个commit槽，8个PE，每PE8个owner位。

## 触发与窗口

仅在未来另行授权且同ABI环境具备时使用。每次最多8192个时钟样本：触发前6144，触发样本1，后续2047。954bit纯数据约954KiB；不包含文件/时间戳开销，不承诺FSDB大小。有限arm上限1,000,000周期，未触发即结束，不自动重试或扩大。

两个候选触发并列：真实占用的head在原PC `ffffffff80013a18` 连续64周期未退休；或者观察到指令 `00802573` 后64周期没有匹配响应。后者须用同时记录的head PC/ID验证属于本次save_v_state，其他同编码CSR不算原症状。64只是取证阈值，不是架构规定响应时限。

按同一时钟边沿记录握手值，并保留后一拍寄存状态；不要用NBA后状态配上前一拍ready拼接出虚假握手。若未来跨时钟/ILA采集须单独解决同步，不可默认为同域。

## 判别链与注意点

|假设|本profile可提供的判别|不能越界推断|
|---|---|---|
|H0：未到Ara|head真实占用、队首ID/指令、pending/ready、flush、CPU缓冲输入握手、Ara端present|head PC不等于CSR接受；present也不等于ready握手|
|H1：旧owner使idle低|每PE/owner运行位、done位、广播/ready、op/VL/vstart、memory接受/完成历史|没看到owner分配就不能确定原前序；仅idle低不能证明循环依赖flush|
|H2：flush开始但未完成|start、实际flush输出、原始done、寄存done和FSM|窗口前已发生的start不可凭空补齐；有界未完成不是永久丢失证明|
|H3：decode资格受阻|state_q与state_qq、idle、backend ready、arch_decode、decode_blocked、请求/响应|当前状态WAIT_IDLE不代表前拍也符合；DDR无活动不等于Ara idle|
|H4：响应后未退休|响应ID/值/异常、CPU写回ID、head完成位、commit ACK、GPR写|没有匹配响应不能指认后端CPU退休问题；异常退出与正常GPR写须区分|

`commit_instr_id_commit.valid` 表示结果完成，不是槽存在。
实际占用取 `still_issued[commit_pointer_q[slot]]`。
请求ID只有3bit会复用，必须用复位/占用/握手顺序建立epoch；CPU flush不会抹掉已经进入非flushable缓冲的所有权。请求与响应同拍时须先匹配，不得制造虚假64周期等待。

不采VRF内容、整个DDR、所有队列或完整Linux波形。若本窗口没有更早的PE分配或异常来源，只能报告“上游/owner历史不足”；后续是否针对某个PE取更早窗口需另有证据和授权。

## 现有证据与最小下一步

原Image恢复的PC窗口包含 `csrr a0,vstart`，但归档停机记录缺请求接受、owner和flush波形，也缺实际运行时替代指令修补后的文本。已有三条停机记录不足以在H0–H4中选根因，源派生Sv39已通过场景也不关闭这个Linux症状。

未来安全下一步仅是：在获准的精确环境中绑定实际Image/RTL/config及运行时目标PC，核对全部信号路径/宽度/可见性，再按本有限窗口一次采集。当前没有该执行授权，本目录没有启动脚本。
