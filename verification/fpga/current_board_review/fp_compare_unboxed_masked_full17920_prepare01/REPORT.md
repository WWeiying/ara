# Masked Unboxed E16/MF4 Full17920 Software Result

完整masked父程序已单一实现，原顺序17920/286720bits/35840guards/17920flags/vstarts不减。新目录独立于已接受unmasked和其他在跑任务；没有读取大trace、修改RTL、启动Spike参考或VCS。

## 关键变化

仅把原框架配置改为UNMASKED0/UNBOXED1/DK0，并使用归档原masked.S和本父82d90319... ELF身份。185条实际helper编码全部匹配原masked字节，没有额外RVV/FP。oracle变为8960个mode-sensitive 8B records；flags只累加实际active元素。VL>0但mask=0的inactive结果位严格保留old，tail仍是原{old,1,wanted}允许集，VL0全old；不扩充原C不存在的约束。raw FMV.D.X、32seed、原flags保存恢复、每call完整输入/mask128/output130及原错误计数/前20DETAIL保持。

## 独立原C Host与失败证据

Host不只拿新模型互比：`source/original_host.c`保留完整原C循环、原逐bit oracle和原flag/error/DETAIL正文，仅替换Linux syscall和入口（longjmp截获原exit），与packed程序在同一组真实原fixture/helper-C-stub响应下分别运行完整17920调用，并精确比较最终exit/完整文本。另逐call验证全部输入、实际mask字节、原old输出和完整41次fresh写序列；packed读取17920次LWU。C helper stub不是RVV硬件，也不宣称实际FPR/CSR执行。

六组完整原C/packed对照实际退出0：positive、合法tail全1、21次逐位错误并原前20DETAIL截断、all-off spuriousNV、active漏NV、inactive位改写。每组824320次逐bit/多bit/guard/status错误计数比较。注入旧板首错call39的all-off NV16，两程序均准确输出expected_flags0/actual16/errors1，完整总错1；不是把错误当PASS，也不是忽略flags。

五项故意坏输入/结构均由Host assertion拒绝（actual -6）：缺输入写、缺高mask写、缺output尾SH、错误原scalar输入、错mode record。全部原失败receipt/log保留。

可选动态UBSan最初链接actual1：宿主缺`/usr/lib64/libubsan.so.1.0.0`，不是模型/数值错误，未执行任何RISC-V编译。原失败保留在`build01/host/compile_ubsan.*`；窄后继`finish_build01.py`不重复已过Host，使用GCC undefined instrumentation+trap-on-error（不依赖缺失runtime），完整positive和all-off NV对照均actual0。此后才各一次固定flags SoC/Spike编译，未修改编译优化参数试验。

## 实际机器码与完整成本

| 后端 | 编译actual exit / 秒 | 完整成功CFG上界 | 距3M |
| --- | --- | ---: | ---: |
| SoC | 0 / 0.569047 | 2810222 | 189778 |
| Spike | 0 / 0.568876 | 2796402 | 203598 |

SoC ELF SHA256 `18294ae7aa7a2a503e0ab82d532f6c7dcc6f92ad752e3972e50038a7c03173ea`。
Spike ELF SHA256 `09c4eaf6033b25922a57e1c7223616e6a849d30b6393a67fd64d91da097a7634`。
`linked01/{soc,spike}.json`分区覆盖实际source函数每条指令，列明所有成功边权与失败路径，并校验CFG流量守恒，不是按预想指令数构造总数。额外call spills、常量/地址/循环/分支均计入。

actual fresh734720 stores（每call8输入SD+16maskSD+16outputSD+SH）、143360输入LD、17920完整结果LWU、8960 mode-record LD已由实际位置和执行次数核验。record保留在s6，sticky与caller临时量按实际stack spill/reload；helper不写任何callee-saved s寄存器。所有机器码也逐字节与实际ELF映射核对。输入backing各2048B、mask128B、output130B，8960records=71680B，periods1536B。SoC BSS4400B，镜像用至BSS仅80560B，独立保留64KiB栈；普通嵌套frame288B，保守需求512B，满足1MiB布局。

成本为全正确、正常终止路径的静态条件上界，不是实测firmware、不覆盖任意失败路径时间或挂起。相对已接受unmasked SoC静态upper2682862多127360（约4.75%）；6687s仅同形实测参考，不能据此保证masked相同墙时。还需一次获准的完整有界参考确认真实firmware<=3M及raw全oracle/EOF，当前未执行。

## 可证伪硬件预期与后续边界

本轮只读核对当前RTL：`hardware/src/lane/vmfpu.sv:1585`对比较禁用lane fflags；`hardware/src/masku/masku.sv:451`仅完整operand valid&ready接受beat时，对`fp_compare_nv_seq & result_queue_active_mask_seq & (masku_operand_m_seq | vm)`归并NV。因此预期all-off只返回原sticky，mode1/2仅active sNaN/NaN按原操作贡献NV。若实际完整父程序失败，首错应保留call/mode/VL/raw flags/bit及owner位置，再检查实际mask坐标、跨lane对齐、beat接受与owner顺序；不能凭旧5816错误提前改RTL，也不能认为静态机制等于已测PASS。后续必须绑定实际镜像与这些源代码的身份。

五个helper-memory owner/call仍89600必需，15360个VL>0 target必需（含all-off）；2560 VL0 target单列，所有实际token必须配对。新reference/worker只能继承判据，不能继承unmasked成功结果或PC。`SOFTWARE_READY.json`封存本次实际成品和失败链，仅供完整参考准入；无VCS/新镜像/自动重试授权。
