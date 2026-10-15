# Full682 Packed 独立静态审核

结论：**标量软件转换/Host证明无阻断项；不构成DUT entry或DUT PASS。**

## 阻断项
无。READY明确仍缺新地址绑定的worker/oracle及动态helper/input/VRF/history核验；本审查不替代这些准入工作。

## 通过依据
- 实查READY SHA `64f82d0e893179b253b4cced76f6f73b7820f1427b865889bd127c7d9eee62e4`、其pins链接及126个真实文件，前后无漂移；未依赖HANDOFF作结论。
- 归档原Linux ELF与保留的original_rebuilt.elf均为`266467e6d61dc7334a83e62ce6ee8d2d0cfac5050811be026329c46eb3816754`。实际parent→prefix仅加入第682次完整oracle后的停止。
- 逐项独立核对全部682顺序/681前序；末项为seed1/op2/VL1/mask0/sticky1/vstart0。698,368个输入halfword匹配原式；原A/B各1024 halfword分配及未使用上半BSS保留，mask128 bytes和output130 bytes初始化保留。
- 实查七组original/packed Host二进制调用记录逐字节相同，每组682条；正例双方实际rc0，六个负例双方实际rc1，覆盖VL0 alias、活动结果、两guard、flags及返回vstart。
- 独立按原bit谓词的允许值集合构造Cartesian product，核对349,184 bits及11,173,888 byte候选：活动位按fixture，VL0严格保留alias旧位，普通尾部仍允许{old,1,wanted}。sticky flags仅OR活动元素，682项一致；不将Spike实测结果用作golden。
- 对实际SoC/Spike ELF逐段读取机器码：capacity3条、op0..3各16条、op4..9各21条完整匹配旧ELF，并在原归档ELF字节中各唯一匹配。helper的fflags保存/设置/读回/恢复、立即vstart读回及vsm均保留；helper外无新增vector/scalar-FP指令。
- 实际两ELF的5,120-byte输入ROM及98,208-byte判定ROM与独立解析的tables完全一致；A/B均8-byte对齐，栈顶0x800ffff0及64KiB保留区满足。
- 实查Host rc0和Spike debugger cost rc0、errors0/682calls，计数2,123,849。仅承认成本/端到端软件状态证据，不宣称新完整动态raw审计。

## 限定
仅CAP512/e16/m8、unmasked、destination-v8 alias、vstart0的原first682，非完整17920 parent，非原Linux ABI。
packed错误计数按失败byte而非失败bit；PASS/fail等价，但多bit错误时诊断总数可能不同。
只读核对现有证据；未重新执行Host二进制/Spike、未启动DUT、未修改RTL或源准备文件。

证据：`evidence.json`、`elf_rom.json`；复核脚本：`review_artifacts.py`、`elf_rom.py`。

