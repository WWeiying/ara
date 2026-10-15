# M4 focused01：索引源起点错误已测实

单轮、两路、180s/项，unit `ara-gather-focused-candidate04-01.service`。
真实原输出保留在 `../vcs_candidate04_01`，没有重启或搬移；本目录仅离线波形提取。
M4既有封存镜像未改、生产RTL未改、旧helper未改；未force/deposit。

| 单例 | 实测终态 | 耗时 | 原完整oracle |
| --- | --- | --- | --- |
| start128 | 原数值FAIL | 137.38s | cases1/errors128，512元素及两guards均实际读到，CSR vstart0 |
| start0明确控制 | PASS/exit0 | 74.87s | cases1/errors0，514项读取，CSR vstart0 |

失败首读 `PC=0x80000416 / 001d4783`、cycle45098、地址`0x800014e9`：
元素128 expected79/actual0。完整原失败日志在
`../vcs_candidate04_01/replay/tests/gather_probe_e8_m4_ops20_start128/work/run.vcs.log:575`。
退出日志明确 `Core Test *** FAILED *** (tohost = 1)`；simulator OS rc0不意味着架构PASS，runner正确判FAIL。
失败项534次output scalar读取包括打印20条DETAIL时的重复读取；
`finding.json.numeric_mismatches=148`是失配读取次数，不是原errors计数，原计数为128。

## 实际cycle链条（均为时钟上升沿前采样）

- start128四lane AluA接受cycle39075：vs16、vstart32、eew1=16bit、vl64、scale_vl0。
  首次grant cycle39076：metadata地址72、remaining64；bank地址9（72>>3），不是直接把9当全VRF地址。
- start0对应接受cycle38538、grant38539：vstart0、其余相同；metadata地址64，bank地址8。
- start128 scan0在cycle39080入idxfifo：idx511、oor0；scan128在cycle39624入队：idx513、oor1。
  原xorshift indices16[128]=511、indices16[256]=513，input[511]=79。
- 失败项cycle39631消费 idx513/oor1时 issue_cnt128，对应绝对目的元素256-128=128。
  控制cycle39099在同一目的元素消费idx511/oor0。
- lane0失败项地址96–99的accepted writes BE均0，保护元素0–127；
  地址100的accepted write cycle39768、BE255，data低字节0，确实覆盖活动元素128。
  控制地址100在cycle39226、BE255，data低字节79。
  四lane完整grant/payload/write样本见各子目录 `signal_samples.json`。

结论：lane将EI16 index source-origin提前128项，但MASKU仍从scan0遍历全前缀。
因此目的128使用源索引256=513并按VLMAX512生成0；目的BE正确，没有掩盖源错误。
局部修复候选唯一定位在 vector gather的AluA源请求vstart归零；
必须保留架构vstart、目的BE、VLMAX及source/no_data/token协议。当前没有实施修复。

FSDB原捕获限0–90000ns，两份原文件在各原work目录；离线VCD另限目标附近窗口。
一个块内临时变量vrgat_res不可直接dump，已明确记录此profile缺口；
实际idxfifo、source grant/payload、alu_result及accepted结果write/BE足以闭合上述链条。

保留原cap512 xorshift/setup、512完整oracle、guards和13条原asm编码；两项Spike也完整通过。
独立源码/provenance/diff/ELF在 `../prepared`、`../source.diff`、`../soc01`，身份在 `../plan.json`。
此single不能关闭失败prefix、原11个stalls或完整parent；后续修复仍须回归原prefix。
