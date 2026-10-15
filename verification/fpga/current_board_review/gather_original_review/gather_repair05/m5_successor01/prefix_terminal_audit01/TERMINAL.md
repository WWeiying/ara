# M5 两个 authentic98 子前缀独立终审

结论：`PASS_INDEPENDENT_RAW_TWO_AUTHENTIC98_PREFIXES_M5`。本次仅离线读取，不启动仿真、不改 RTL、ELF、sealed worker/plan 或旧结果。

## 原始证据复算

`audit.py` 从原 C 的 uint64 xorshift、六层循环顺序、mask 和 scalar oracle 独立重建 98 个 tuple，逐条读取两份原始 commit_trace.csv。没有使用已有 `fulloracle98_gate.json` 或 complete.checked 的 PASS 作为验收依据。通用 trace validator 另核对退休顺序及 CVX/uop 完成配对。

| case | 完整 calls | 数值/guards | 退休条数 | 最后 cycle | elapsed 秒 |
| --- | ---: | --- | ---: | ---: | ---: |
| ops1 | 98 | 50176 / 196 | 2092785 | 3021740 | 3046.564879 |
| ops20 | 98 | 50176 / 196 | 2225267 | 3350943 | 3257.146007 |

两例均有 50372 次唯一、逐值正确的 scalar 输出读取；13 条原 asm 各退休 98 次、顺序和编码无差异；实际 call 指针/cap/VL/scalar/vstart、三次 vsetvli 返回 VL、98 次 returned vstart=0、CTRL raw exit0 均通过。每 call 还从 scalar store 重建并核对 512 输入、512 索引、128 mask 字节及 514 初始输出/guards，共 1666 个 setup 值。exit 后仅允许原 `a001` 无副作用 parking。原 console.log 和 work/run.vcs.log 均有完整唯一统计/成功标记，无 failure/abort/trap veto；两例 rc0，未超 9000 秒。

## 原第 66 call 修复

ops20 tuple `[0,20,0,4,0,1]`，VL256、vstart128、scalar0：

- 实际目标 `0x80000a9c / 38880c57`，cycle2233716，CSV 第1489882行（含 header）。
- 原 xorshift 索引 `indices16[128]=511`，`input[511]=79`，错误移位对应 `indices16[256]=513` 越界；实际 setup 内存全部匹配。
- M5 oracle 元素128：`0x8000050e / 001cc683`，地址 `0x80001629`，cycle2239878、retire order1488310，CSV 第1491206行，原 rd_wdata=`0x4f`，expected79/actual79。
- M4 同元素旧证据是 cycle2239883、expected79/actual0。M5 returned vstart=0，且该 call 的全部 512 数值和两侧 guards 通过，并继续完成后续 32 calls。

本次 prefix 没有重新捕获波形；origin0/scan128 idx511/BEff data79 的周期级证据来自已独立通过的 `../focused01/acceptance.json`。start0 完整 CSV 含 cycle/non-retire 字节一致的严格 performance PASS 保持不变，不用 prefix elapsed 推断性能。

## 身份与封存

已核对 110 个 baseline/prepared pins（含 authentic archived C、原 Linux ELF、报告、映射、asm、source diff、reference 及原 SoC ELF）、539 个冻结 source 文件、66 个 image 文件和 453 个 compiled source 文件；private ELF、command/cwd、simv、config、manifest、provenance、worker/plan/focus SHA 均匹配。终审另外绑定 131 个输入/artifact pins，完成复算后再次逐个 hash 核对，`FINAL_PIN_RECHECK_PASS 131`；明细与逐 call 结果见 `audit.json`。

- 原 C SHA：`b6e5fa032dfdc58ec621d0377f93cf824f27ad460d6bd102e173e244a65ec5ca`。
- audit.json SHA：`e368d848ba691608b3349af5b7af73bd51c135b475dc756e5c04766ac43e23f8`。
- audit.py SHA：`40a2c0994e2391e13ebf95dadd6b1736e7b152b9b7cdf9c7dc7c0b5fdfd80f7a`。
- M5 image ledger SHA：`9349bdae91e72706ffbb22ad20a7f62795215a5263b1ec0cc4e4837fc21d1500`。

## 边界

验收仅为两个 genuine archived child 的原先序列各前 98 calls（每个原 child 是 2688 configurations），保留原 RNG/setup、asm 和完整 oracle。两个 SoC ELF 与 M4 prefix ELF 相同，但不是原 Linux ELF；归档 manifest/source hash 与 13 asm 可对应，现有 GCC 的整份 Linux rebuild 不等于归档 binary，不能声称逐字节整程序 rebuild 证明。原归档 stopped tuple 仍未知，M4 数值第66call失败不是已定位的原 11 stalls 停止点；本结果不关闭 11 stalls、Linux 执行或 full parent histories。
