# 分组规划完整周期实验

本实验对比固定分组与有界成本边界调整，不再以旧逐 query 路径作性能分母。
输入为真实 Qwen3 capture 的前五个 query、KV head 0、每 query 两个 GQA
head、D=128、K=Q4_0、V=Q8_0。共 1280 个输出，ABBA 四轮。

程序将完整准入、规划、量化、QK、softmax/PV、输出写回及 drain 计入 ROI。
预期 QBS 命令均为五，V 解码为 9/6/6/9，组数均为二。独立 checker 检查
规划计时范围标记、四轮输出、golden、CSR、命令及解码数；协议检查保留。
这些是待验证条件，不是已经取得的周期收益。

构建第三次目录 `verification/out/prefill-planned-native-build-20261028-03/`
已成功链接，15 对象全重编译，未复用对象。前两次失败分别为：

1. 候选 workspace 留存局部 visible/selection 指针，触发 dangling-pointer
   编译警告；在同步 scheduler 返回后、成功或失败分支之前清空这些指针。
   主机真实数据回放在 `prefill-planned-real-20261028-03` 四组继续通过。
2. 裸机无 newlib 的 `__assert_func`；提供报告上下文并调用现有 CRT `_fail(1)`
   的适配，不关闭断言、不修改 CRT。

服务为 `prefill-planned-native-vcs-20261028-01.service`，输出目录同名位于
`verification/out/`。实验不得据工作量减少自动判收益；若规划开销抵消节省，
保留原生产分组。当前未修改 RTL 或安装规划候选到 llama.cpp。
