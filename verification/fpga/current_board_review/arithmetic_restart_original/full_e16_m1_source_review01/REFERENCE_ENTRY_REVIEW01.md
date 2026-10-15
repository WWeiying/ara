# e16/m1 单次有界参考入口

NO_BLOCKER_SOURCE_SOFTWARE_FOR_ONE_BOUNDED_REFERENCE_NOT_DUT，绑定reference_entry87c4624676ed81aa4ceca081490edecf671ef9c4acfaf1c8e431160dc5f15b4b；152pins fresh一致。

actual software wait0/13.054s、20Host receipts/10paired logs、SoC/Spike实际ELF及stack478248/469792B已核；focused19Host actual0/1.219s。源helper/noextraRVV证据保持。

实际lowering为SW尾4+16SD；读回首LD588、后15个outputLD8b8+i*10、尾LW954，不是相邻ROM读。原seed每次184次SH共552；full128B物理寄存器、mask128初始化/实际8B，完整4095/262080/8190/69615reads与fresh/vstart/history不减。

一次4Msteps/120s/768MiB，audit600s；真实wait先保存，timeout kill+wait，无retry。HTIF后继续检查精确park直到EOF，不提前return。实测固件超过3M必须HOLD。compiled_review旧nineword备注不适用于当前17word，1.2M仅未经实测估算；不据此声称DUT时长保证，不改旧sealed证明。

只准入既定单次软件参考，不是动态PASS或DUT授权。本审只读来源/反汇编/metadata/hash，未重跑Host、编译或旧raw。
