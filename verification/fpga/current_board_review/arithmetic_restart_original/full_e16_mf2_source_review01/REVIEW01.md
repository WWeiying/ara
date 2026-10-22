# e16/mf2 source entry review

结论：BLOCKED_SOFTWARE_ENTRY；不是软件结果或RTL失败。

P1：prepare.py在20次Host后再次调用old.disassemble写original/program.dis。materialize已创建并pin该文件/command/exit；复用run使用独占创建，必在SoC/Spike编译前失败。应在software阶段只读解析已pin反汇编，并为修改后的prepare绑定后继source entry；旧证据保留。

已只读核38 pins全部一致。CAP32、mf2每操作数一个物理寄存器低64B、typed16输出68B、128B mask初始化及vlm实际4B、005b guards、三seed RNG与4095顺序、原13指令helper保持的源级方案未见阻断。memcpy避免uint64别名cast；八个8B加4B尾没有越界；失败回退保留原元素计数及双guard合并诊断。

Host源码覆盖逐位置原C/model比较、68字节损坏、未对齐memcpy、保护页尾界及返回vstart等，但尚无实际Host/编译验收。当前不授予参考入口或DUT准入。未运行任何Host、编译、参考或DUT；后续只审窄修和实际产物，不重复大trace。
