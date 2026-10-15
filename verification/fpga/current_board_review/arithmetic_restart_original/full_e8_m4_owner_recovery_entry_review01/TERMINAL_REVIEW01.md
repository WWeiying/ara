# e8m4 离线恢复终态验收

接受架构层离线恢复，不将原service标PASS。实际唯一audit wait0/367.662512s，无timeout/retry，result/strict/wait/terminal哈希闭合且无failure.json。

完整4095调用、2096640结果、8190guards、4095vstart、53235helper、266175读回均通过；strict/generic一致2831332行。45047条CVX请求/响应/架构请求，23067 alloc/done；20475 memory+2592 required target，op24 117。

逐项读既有owner ledger，18个合法VI offset2>=VL目标全部alloc=done=0；原首错call1200/ordinal1201、arch13209/retire771538准确对应，当前required=false。不是吞掉其他owner或缩减oracle。

此次仅读终态JSON/ledger并核文件哈希，未再读CSV。813 pins已于入口fresh验证，实际成功auditor记录pre/post一致。原NOT_PASS、service exit1及sim0/10573s证据保持；无新VCS，不关闭原Linux历史症状。
