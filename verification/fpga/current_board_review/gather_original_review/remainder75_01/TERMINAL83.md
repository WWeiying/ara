# Gather83 来源单点终态

结果为 **83/83 authentic source singles PASS**：独立保留的accepted8，加本批remaining75。
这关闭 RVV-19 numerical83 的所选原始 first-failing source records；不声明大parent矩阵、
原Linux ELF/ABI、板级复验、其它数值tuple或另外11个gather stall全部通过。

## 封存结果与独立复核

`vcs_candidate04_01/complete.json`：
`PASS_8_ACCEPTED_PLUS_75_SOURCE_SINGLES_CANDIDATE04`。
SHA256：`9b71c95ad9df4e32beb84d88407c40ff5368bfb311bdfa6ae4897de7afd551f6`。
plan SHA256：`116e89a3b9466ae910926653f1a84abb9c480c7dc12a9aca77ba81f5e76b2f83`。

first12和remaining63各自strict gate通过，worker returncode0/errorNone/retries0，
`accepted8_rerun=false`。75项target各一次，原asm/full-cap scalar oracle、guards、
VL2/vstart1与返回vstart0、完整markers和exit0均通过；3972个输入pins不变。
本批逐项raw CSV读到了7792个capacity输出元素与150个guard；accepted8原独立审计
为592个输出与16个guard，因此83来源合计8384个元素、166个guards。

Averroes先独立只读重验75项、3972pins、378prepared文件、150raw logs与75CSVs，
raw结果与complete.json完全一致。随后本目录owner也仅调用
`check_remainder75.validate(out, plan_sha)`，重验75结果并确认complete文件前后hash不变。
owner对返回results按JSON sort_keys=True、separators=(",",":")规范化的SHA256为：
`40421de116f903c2cb07131c9758e4c23aeec8d2a8a4678c729e3f2cd0388d2b`。
没有重跑test main、改写host gate/complete、轮询运行中的DUT或重新启动仿真。

## 正确计数与剩余边界

身份ledger输入仍是原封存的 `coverage83.json`，其中prepared状态代表启动前快照；
当前终态由75项complete和 `../acceptance_audit01/audit.json` 的accepted8共同绑定。
`check_remainder75.validate_plan()` 核验8+75不相交且精确等于83个manifest sourcekeys。
SEW/LMUL/op连同来源/ELF身份不能因首错标量字段相同而合并；parent/partition和重复
归档文件不能额外计数。19个shape、五种gather op均有来源覆盖，不等于所有parent配置。

原83身份由80个opcode-partition single和3个未拆分fractional-parent op0 single组成。
parent各56448配置，opcode partition各2688配置；本次每来源只验收归档准确trial。
其余VL/vstart/mask/seed/scalar、完整parent顺序、Linux signal/restart ABI、原Linux ELF
和板级环境仍须单独证明。六层空枚举缩界不改变被执行trial的完整RNG/setup和oracle。

原candidate03 TIMEOUT/CANCELLED、首次successor wrapper NOT_ACCEPTED、prepared12/75
和旧pins保持原样。没有新RTL修补、镜像改动、提高单项timeout或自动重试。
prefix/FP是否启动仍属父级资源协调；本报告不启动其它family。
