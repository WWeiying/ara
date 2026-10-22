# FP16中间尾数位定向补测

## 缺口与可证伪假设

689项历史PASS的编译shape绑定复查仍有3个可达internal-OR条件
未命中，详见`lzc-retained-689-20261006-01.json`及
`LZC_PADDING_REACHABILITY.md`。它们对应MFPU C队列的FP16分量，
树节点(1,0)的01及(2,1)的10，均可由尾数`0x20`构造。

旧镜像封存`ara_dispatcher.sv`的VFWADD解码设置
`swap_vs2_vd_op=1`及`conversion_vs2=OpQueueConversionWideFP2`。
封存`lane_sequencer.sv`的MulFPUC请求因此选择vs2、原始EEW及
该扩宽转换；不是将无关vf8/vf4输入错送到队列。
`operand_queue.sv`的FP16 LZC实例WIDTH=10、MODE=1，尾数反转
后`in_tmp=0x10`，恰为两种树组合的结构见证。

假设：在VL=64、e16,m1下给vs2的全部元素写入0x0020，能让各lane
两个FP16转换分量均观察到目标树组合。验证标准是仿真PASS之后，
三个精确scope/metric/raw_index覆盖位由0变1，不能仅凭输入推定。

## 已准备激励

源码：`apps/riscv-tests/isa/rv64uv/vgap83_midmant16.c`。
仅两次`vfwadd.vv`：vs2均为FP16 0x0020，vs1分别为0和0x0020。
FP16 0x0020表示2^-19，两个期望结果为FP32 0x36000000及
0x36800000；使用整数位模式检查，无浮点容差或标量浮点转换oracle。
每次目的组预装128个7.0，检查64个活动结果及64个尾部保留值，
并检查返回VL=64、fflags=0、vstart=0，总262项自检。

## 实际预检

`verification/out/gap83-midmant-preflight-20261006-01/`保存独立
ELF及Spike stdout/commit trace。非ZCC工具链编译成功；Spike实际
执行5000条提交指令，tohost=1，自检262项、失败0、trap记录0。
反汇编确认两个0xc2821857分别位于0x80002074与0x80002114。

旧VCS仿真已在独立托管服务启动：
`ara-gap83-midmant-old-image-20261006-01.service`。已核实真实simv
PID=2362752，父runner PID=2362751；控制台已输出VCS覆盖采集版本。
输出为`verification/out/gap83-midmant-old-image-20261006-01/`，
封存66份旧镜像文件及输入ELF、激励源码、Spike trace与驱动脚本。
ELF SHA256为`302adc8bc67502a9c4a94d52ef07afb89c914a2e4b26d7e11bf9a3e14d414c9f`。

该驱动只运行仿真，不批准覆盖准入；600秒运行预算，不重建RTL。
完成后必须另行核查完整标量/向量比较、262项DUT自检、contract和
输入身份，再提取新VDB核对目标位。尚未完成该验收或覆盖汇总。
Spike通过、服务启动或simv退出码均不能独自增加历史689项PASS集合。
任何失败保留但不合入覆盖率。

## 完整验收与实测增量

独立离线验收输出为
`verification/out/gap83-offline-admitted-690-20261006-02/`，状态
`PASS_RAW_UNION_HISTORICAL_ONLY`。标量比较到tohost完整匹配4058条，
无trap；向量8项目的请求、2048字节精确匹配，unknown跳过0、
non-bit-exact指令0、未完成请求0；DUT自检262项、失败0，contract无错。
旧镜像、源码、ELF、日志和VDB的封存pin在验收前后复核。

首次离线工具将失败计数地址0x8000220c的`sw`字节使能误写为0x0f，
因此拒绝签名。原始trace显示实际为0xf0，数据按旧镜像约定未左移；
已修正到精确地址/字节使能/值检查，六项单元测试包含错误计数、
失败结果、缺失签名、错误mask和地址的拒绝行为，没有重跑VCS。

对同一compiled shape和旧689项bitmap逐坐标核对，三个目标均为
0→1：lane2 MFPU C分量0的raw8、lane3分量1的raw8和raw28。
新增原始覆盖为条件3点，行/分支/FSM均为0；690项VDB唯一且保留
原689项成员。这是实际测得的增量，不是根据尾数模式估计。

690项官方DVE汇总尚未完成；本结果不提供新百分比，不证明新RTL
signoff，也未将RTL失败测试或其他镜像的VDB加入集合。
