# Gather launch02 只读归因

本分析只读原记录；未改旧 helper、镜像、RTL 或终态。原 `complete.json`
继续 NOT_ACCEPTED。数值83 singles 的既有验收不受此记录影响；prefix尚未通过，
更不代表11个 archived stall 或完整 parent 已关闭。

## 首错与退休证据

- `stall_prefix2_launch02/vcs_candidate04_01/replay/tests/gather_prefix_e8_m4_ops20/work/run.vcs.log:17`：
  `RVV_PERMUTE_DETAIL op=20 seed=0 scalar=0 vl=256 mask=0 element=128 vstart=128 expected=79 actual=0`。
- 原第66次调用 tuple `[seed,op,s,l,mode,trial]=[0,20,0,4,0,1]`，
  cap512、VL256、vstart128。目标 `PC=0x80000a9c / insn=38880c57`，
  cycle2233716、retire order1486997。13条原 asm 完整退休，随后 CSR 返回 vstart0。
- 首个不符的 scalar oracle load：`PC=0x8000050e / 001cc683`，
  cycle2239883、order1488310，地址 `0x80001629`，rd13=0；对应 output[129]，
  即向量元素128。详细前后退休窗口见 `evidence.json`。
- 第65次同 VL256、vstart1 调用，514个 scalar checks（512元素及两 guards）全部匹配。
  前65次均完整匹配。第66次在 runner 停止前仅记录131次 output读取，不能声称完成fulloracle。
- CSV scalar store重建证明第66次之前 input512、indices16全部512项、predicate128字节、
  output初始化514字节均与独立原 stimulus模型一致，无 missing/mismatch。
- ops20最后 cycle2243268，累计1490159条退休；最后仍在打印 oracle 文本，无 trap。
  ops1累计1511321条退休、到第73次目标，没有数值不符；它是首错联动 CANCELLED，不能算PASS。

## 分类

ops20在2063.83s遇到原 oracle失败 marker，远早于9000s单项/9600s外层预算。
runner遇 marker主动停止私有 simulator process group，因此rc255不是自发launcher崩溃证据。
worker的非0/abort随后使独立terminal checker报 `Worker nonexit0/error/abort`，
这是二级汇总错误，不是导致数值反例的首错。02 actualstartup已经确认两个真实simv前进。
结论：已证实 DUT架构数值错误；不是startup race、预算不足或持续卡死。

## 可证伪根因假设

冻结M4 `lane_sequencer.sv:951-979` 给 AluA 使用 lane vstart，EI16 EEW16；
source-origin归零条件只有整数比较，不包含 gather。
架构vstart128 / NrLanes4 = lane vstart32。`operand_requester.sv` 的地址公式
`vaddr(vs)+ (vstart >> (EW64-eew))` 因EEW16偏移8个lane-local64bit字，
对应全局索引128项。VALU计数从vl初始化且gather透传operand_a；
`masku.sv` 的 vrgat_cnt从0初始化，仍按全流扫描。

预测：scan0收到原indices16[128]=511；scan128收到原indices16[256]=513。
512的VLMAX使后者oor并生成0。正确元素128应读取indices16[128]=511、input[511]=79。
这与日志 expected79/actual0精确吻合。既有MASKU目的写BE按绝对目的元素和架构vstart过滤，
不应把源请求的截断与写BE保护混为一谈。

本run没有FSDB，尚无内部地址/idxfifo/BE波形，不能把静态预测冒充实测。
局部反例需要同时观察：AluA请求vstart32、EEW16、length；requester实际VRF地址及payload；
MASKU vrgat_cnt、req_idx、idx_oor、idxfifo入队、source request/no_data；
issue_cnt对应目的元素128时的BE、result及实际VRF写入。

若波形证实该完整链条，唯一局部修复候选是 vector gather的AluA index source-origin归零，
保留架构vstart和MASKU目的BE，不改VL/VLMAX、vs2随机源读或末尾token协议。
当前未实施修复。聚焦single只用于辨别根因，不替代失败prefix及修复后的prefix回归。

## 身份与可重算入口

原C SHA256 `b6e5fa032dfdc58ec621d0377f93cf824f27ad460d6bd102e173e244a65ec5ca`。
ops20原LinuxELF SHA256 `15469ee7ca24fd7a7dac6e282358872a5d9c3dfc836e5de363661925fac70c18`。
本SoCELF SHA256 `be97b7369ae580019755ac4c5d6e331677050d110943e777142441594490c7f2`。
13原asm编码相同，但compiler/入口不同，不能称原LinuxELF重放。
原archived停止tuple仍未知。

`extract_evidence.py`只读取completed CSV及既有host模型，不运行任何测试或simulator；
`evidence.json`含完整来源路径/hash、每次调用setup/asm、fullcap读取、首错窗口和末尾退休。
