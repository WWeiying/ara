# 块内统一判定：最终功能与局部性能验收

## 结果

`verification/out/block-max-promotion-runtime-20261028-01/result.json` 为 PASS。
当前共享 selector 已包含块内统一 NaN/Inf 判定，没有修改 RTL 或增加硬件
资源。此前同 ELF、真实后端 RVV 回调的 VCS 对照为：

| 实现 | 平均完整调用 cycles |
|---|---:|
| 合入前共享 selector | 47972 |
| 块内统一判定候选 | 47182 |

候选加速 1.0167436734×，节约 790 cycles，周期减少约 1.65%。四轮输出
逐位一致，FCSR/VCSR 相同，独立协议及前后身份检查通过。此处为真实
Qwen3 query19、GQA2、D128、20 可见 token 的完整 Decode 调用，不是模型
端到端性能，也不与此前其他配对的加速比相乘。

## 合入后回归

| 检查 | 范围 | 结果 |
|---|---|---|
| 主机差分/边界 | 27 个 unittest；含 GCC/UBSan 各 2819 项块最大值差分与 972 项原 selector 差分 | PASS |
| 真实数据回放 | Decode/Prefill 各 4 组，两种 K 格式、连续/带间隔布局，每组 40960 输出 | PASS |
| 正常构建 | CMake Prefill OFF/ON 库，不替换对象 | PASS |
| 实际 GGML 图 | 16 次调用；正确快路径与带孔 mask 回退 | PASS |
| Qwen2.5-1.5B | Q4_K_M 权重，4-token prompt，两种 K 格式，各 3 步 | 6 组、911616 logits 逐位一致 |
| Qwen3-1.7B | Q4_K_M 权重，40-token prompt，跨 32-token tile，两种 K 格式，各 3 步 | 6 组、911616 logits 逐位一致 |

两种 KV 配置分别为 KQ8_0/VQ8_0 和 KQ4_0/VQ8_0。两模型累计比较
1823232 个 logits，greedy token、FCSR/VCSR 相同。每个模型启用模式有
56 次成功 Prefill，关闭模式不进入该路径；两种模式各有 112 次成功
Decode，完整活动字段一致。结果均包含运行前后源码/数据/库身份检查。
任务结束后另核验各阶段结果哈希及合并去重的 1037 个当前输入指纹，
全部匹配。

模型回归比较当前共享源码下 Prefill OFF/ON，不是旧/新 selector 的
模型级二进制 A/B。旧/新判定的直接一致性由冻结的合入前函数、定向
位模式差分和原始同 ELF VCS 配对证明。QEMU 只作功能验证。

## 结果入口

全部路径前缀为 `verification/out/block-max-promotion-runtime-20261028-01/`。

| 子目录 | result.json SHA256 |
|---|---|
| libraries | 9d13902b1c6a7dcb09d80c41a982e9b2d03ef0f5448b72559a335566acccb097 |
| graph-build | 14ae6effb077e0df004fa4abfa793b65de11494edceb525181bf3ced78372b08 |
| graph | 636c73e3061f3dfa34cb0e51ae29cb76524b9061a45fa463f3bdc7773723d3a5 |
| qwen25 | c9163b00072c179ef5bd8f0dc3e0e74e1d63c433902f960f5ed0c39e1e6b2c40 |
| qwen3 | e1839e4c4f990c65fe5dc23270262eb96a82ef7252f35a2c1214cce7dd0f723e |

graph-build 的状态为 BUILT_NOT_EXECUTED；实际图 PASS 位于 graph 目录。
原始 VCS 数据、ELF 和旧回调版本记录保持不变，不重写为当前软件身份。

## 后续优先级

当前局部热点已测量，应避免为约 1% 的局部收益反复改动整个硬件。
软件运行库仍通过显式目录接入 Prefill 验证目录下的八个已接受 C/H 文件，
而普通量化 KV kernel 已位于正式 `software` 目录。后续先将已接受的共享
实现收敛到软件目录，保持测试引用同一实现，消除运行库依赖验证目录的
部署问题；这属于集成完善，不宣称性能收益。进一步硬件改动仍需对应
真实占比大的执行路径和周期级证据。
