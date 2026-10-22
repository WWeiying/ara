# 全 lane 低尾数模式定向覆盖

## 假设与测试设计

gap78 的双源输入仍随元素位置变化，部分 FP16 子分量的可达 LZC 条件
可能因输入位置和 lane 分配相关而未被命中。本批在整个源数组中使用
相同模式，确保每个 lane 和子分量均接收到零、低两位、尾数最高两位、
最高两位组合及全一模式；双源均变动，并增加第二个源单独变化的情况。

`vgap80_uniform16/32` 使用 `vfwadd.vv`，测试 LMUL=1/2、VL=1、
满长度减一、满长度、交错 mask。独立标量 oracle 检查所有目的元素，
包括未激活、masked-off 和 tail；同时要求 fflags=0、vstart=0。
正的 subnormal 输入之和可精确表示为扩宽格式，不需要误差容限。

有效性标准不是简单 PASS：需要完成后比较同一 LZC condition 坐标的
新增命中。若无新增，不宣称提升；无法命中也不自动获得豁免资格。

## 执行和验收

基线：gap79 的 685 项 PASS，原始覆盖报告已完成。
镜像：`repaired-aligned-build-20260930-01/sim/simv`，未改 RTL 或重建。
两项已通过 Spike 自检、VCS 完整标量/向量比较和 DUT 检查。
runner 固定输入源码/镜像哈希，执行完整标量、向量对比和 DUT contract
检查，只有 PASS VDB 能合入；之后自动导出无新增豁免的 DVE 报告。

```bash
./vstatus jobs gap80
systemctl --user status ara-coverage-gap80-old-image-20261006-01.service --no-pager
```

输出：`verification/out/gap80-old-image-20261006-01/`。
最初普通后台启动被 service 身份检查拒绝，未启动仿真、未生成该输出；
随后通过受管理的 systemd 服务启动，保留失败启动日志，不绕过检查。

## 实测结果

两项全部 PASS。FP16 有 16640 次自检、146944 个对比向量字节；
FP32 有 8448 次自检、146176 个对比向量字节。
已合并到原 685 项集合，当前为 687 项 PASS，原始 DVE 导出完成。
成员核查确认原有前缀、唯一性及 bitmap 清单一致，失败归约和诊断
VDB 均未计入；两项无 unknown-byte 跳过或 non-bit-exact 比较。

实际新增两个条件点，分别在 lane1/lane3 MFPU C 的首个 FP16 LZC；
新增行、分支、FSM 点均为零。证明 uniform 模式确实补到两个目标点，
但不能据此宣称大幅提升。原始 `i_system` 报告为：行 80.44%、条件
81.22%、分支 79.99%、FSM 60.46%、Toggle 62.90%，两位小数未改变。
