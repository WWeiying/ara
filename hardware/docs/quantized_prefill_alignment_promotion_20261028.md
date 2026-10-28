# 将已验证对齐标注并入共享 Prefill 入口

## 本轮修改

共享 `admission.h` 仅在原有 view/mask 对齐检查成功后，显式传递二/四字节
对齐信息。字段读取仍使用 builtin memcpy，原拒绝顺序、数值域、NaN/范围
检查、alias、能力条件不变。共享 `execute.h` 在同步 scheduler 结束后清空
借用的局部 visible/selection 指针，包括失败返回路径。

`admission_baseline.h` 保存合入前的准入函数，供差分回归使用；对齐差分
测试现在比较该旧函数与实际共享函数，而非两个都已优化的实现。
实验规划没有合入；Prefill 的构建和运行时开关仍默认关闭。没有修改 RTL。

## 新代码的验收

- 11 项 unittest 方法通过：原准入、旧基线差分、未对齐拒绝、完整执行、
  GGML 映射及真实 allocator/view；包括 GCC、Clang UBSan。
- `prefill-promoted-real-20261028-01/result.json` PASS：真实 Qwen3 20-query
  输入，两种 K 格式、连续/strided 两种布局；每项 40960 个输出与旧逐 query
  入口逐位一致，浮点标志及命令/分组/V 解码活动不变。
- `prefill-aligned-ggml-build-20261028-01/result.json` PASS：正常 CMake
  OFF/ON 两套完整 llama 库成功，构建前后源码哈希一致。

这些结果均为本次共享入口修改后重新取得。旧 RTL 结果证明候选值得合入，
但不冒充此次正常构建的模型回归。当前仍需重新链接 graph、Qwen2.5 和
Qwen3 程序并运行功能对照，尤其保留 fallback 和 Decode 活动检查。

旧结果目录、库和失败记录没有覆盖。后续使用新构建必须核验该构建自己的
source pins；不能复用旧构建的过期源码核验结果。
