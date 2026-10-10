# FP32向量除法舍入缺口激励

新增`apps/riscv-tests/isa/rv64uv/vgap84_div32.c`，不修改处理器RTL。
目标是封存690集合中C910 div/sqrt round路径的未命中分支；是否提升
覆盖位必须以旧镜像VDB与690基线的实际差异为准，不能由操作数数量推算。

激励执行45次`vfdiv.vv`：5种合法frm乘3种mask乘3种VL。
VL为64、63、1，e32/m2、tu/mu；mask为全开、0xa5、全关。
涵盖正负零、Inf、quiet/signaling NaN、除零、最小subnormal除2、正负
overflow、正负1/3，以及精确subnormal结果。oracle使用固定IEEE结果
位和逐元素异常标志，不依赖宿主浮点计算。还检查tail/mask原值保持
及vstart归零；全关mask必须抑制所有算术异常。

编译使用项目riscv-llvm，不使用ZCC。独立Spike已退出成功，完整trace
在`verification/out/gap84-div32-preflight-20261006-01/spike.trace`：
结果签名`0x80002588`为2970个检查，`0x8000258c`失败数为0，
tohost `0x80001000`写1。ELF SHA256为
`af0f998f592249a6f42472c3a05c52554227c10dd89c1ddc61c72250da4a950c`。

最初只完成激励与Spike预检；随后已完成下述旧镜像验收并独立准入。
后续使用独立目录保留完整scalar/vector trace和VDB；只有自检、逐条
对比与contract检查通过才接纳。若暴露RTL错误，保存证据但不修RTL。

旧镜像单次后台仿真已启动，管理单元为
`ara-gap84-div32-old-image-20261006-01.service`，独立输出为
`verification/out/gap84-div32-old-image-20261006-01/`。
实际simv PID2394468及其旧镜像路径、PRELOAD和覆盖选项已核验。
runner在启动前复核Spike的2970/0签名、tohost和trap，并封存镜像及
激励哈希；这不是验收PASS。超时上限600秒，不改变镜像内看门狗。

## 实际旧镜像验收与新增覆盖

仿真正常退出，VCS CPU时间201.880秒，contract记录450个请求、
450个响应、exceptions/protocol_errors/outstanding均为0。
完整scalar差分匹配55987条提交指令，到tohost写1结束，trap为0。
vector比较225个目标请求、38760字节，未知跳过及非逐位比较均为0；
没有incomplete/unretired/trapped请求。DUT自检签名2970/0通过。

独立工具`admit_gap84_offline.py`核对690基线的正式无豁免报告输入，
封存本次日志、轨迹、VDB及checker，验收后才合并同Design的raw位图。
输出`verification/out/gap84-offline-admitted-691-20261006-01/`：
历史集合691项PASS，新增line15、condition83、branch29、FSM0。
这不是百分比推算；691项正式DVE报告尚待生成。原失败项、原始VDB
及RTL均未修改，不代表当前RTL的重新signoff。
