# e16/mf2 参考终态metadata验收

结论：ACCEPTED_REFERENCE_TERMINAL_METADATA_ONLY_NOT_DUT。READY SHA02e348a7f370f32ab686c908f36bbbfb8a7fe21e9392a9613fc6d8dbcd753d17。

实际Spike wait0/1.772060s，actual audit wait0/25.530246s，无timeout/retry；READY/result/两numeric receipt哈希相互匹配，154输入pins新鲜一致。完整4095calls/131040results/8190guards/4095vstart/13*4095helper/36855reads；1575 maskgroups、276 seedSH均对应已审observer范围。

572522 firmware +5boot +2473park =575000完整记录，EOF已由实际一次auditor验证。raw仅stat核59423809B，未重读、未重新哈希或语义解析；消费既有完整observer结果及numeric exit，不冒充第二次fullraw独审。

可作为新worker的真实reference acceptance绑定。不是worker入口准入、DUT验收或Linux症状关闭。DUT预算仍需实际计划约束，fw估算不保证实测时长。
