# e16/m1 参考终态identity独审

接受reference metadata终态，不是DUT验收。READY b8faa1188136f9fffcad178dc9a6dd14a885ecfe775a6f25a856e82c50aea6ba与result、actual numeric receipts及已审entry相互匹配；154输入pins fresh一致。

实际Spike wait0/2.173068s，audit wait0/38.860843s，无timeout/retry。完整4095/262080results/8190guards/4095vstart/53235helper/69615reads，1575maskgroups及552seedSH均齐；704285firmware+5boot+710park=705000，实际observer EOF通过。

保留typed005b、132B输出/尾4B、单物理寄存器完整128B、mask128初始化/actualvlm8及原历史顺序。未重读、重hash或再解析raw，仅消费已有完整一次auditor证据。可作为新M9worker reference绑定；新worker还需actualHost/dryrun及exact入口。当前不宣称DUT或Linux closure。
