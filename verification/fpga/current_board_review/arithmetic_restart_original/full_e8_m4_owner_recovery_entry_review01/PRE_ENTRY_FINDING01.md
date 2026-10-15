# e8m4 closed recovery entry: pending narrow successor

阻断：recovery.py SHA4152afced7c712e9065c1c094ad8ac82418b232c3b7b166a26647f577f192df8 的audit在最后need(not abort)之后仍save(strict.json)并计算SHA。该昂贵阶段仍在abort_signals上下文中，SIGTERM仅置Event；其后未再检查便更新ACCEPTED并可return0。故已请求发布后继，不授予此版本入口准入。

窄修边界：strict保存/hash保持在信号锁外；完成后重查sticky abort；最终小result以信号屏蔽/pending检查定义发布线性化。仅补真实保存阶段abort及pending信号负例，不重原12Host或完整CSV。

已核checker当前delta：仅实际0x38813c57 VSLIDEUP.VI unsigned offset2>=VL额外允许无owner；原18个索引精确限定。VL3/slidedown/op24及五memory helper仍required，optional owner若存在仍必须alloc/done配对。原Strict数据/fresh/vstart/完整4095及generic保留。源级delta未见阻断，等待实际Host和最终runner/plan身份。

M9 dispatcher2329-2340及5970-5978支持该合法elide。原run的NOT_PASS/service exit1不改变；本审未运行VCS或完整CSV audit。此记录不是NO_BLOCKER或恢复验收。
