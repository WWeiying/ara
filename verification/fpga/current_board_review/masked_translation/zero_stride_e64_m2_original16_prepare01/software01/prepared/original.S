.text
.global capacity
capacity:
li t0,-1
vsetvli a0,t0,e64,m2,tu,mu
ret
.global replay_0
replay_0:
vsetvli t0,a4,e64,m2,tu,mu
vle64.v v24,(a2)
ld t3,0(a5)
vlm.v v0,(a3)
vsetivli t0,8,e64,m2,tu,mu
.global fault_0_pc
fault_0_pc:
vlse64.v v24,(a0),t3,v0.t
csrr a0,vstart
vsetvli t0,a4,e64,m2,tu,mu
vse64.v v24,(a2)
ret
.global replay_1
replay_1:
vsetvli t0,a4,e64,m2,tu,mu
vle64.v v24,(a1)
ld t3,0(a5)
vlm.v v0,(a3)
vsetivli t0,8,e64,m2,tu,mu
.global fault_1_pc
fault_1_pc:
vsse64.v v24,(a0),t3,v0.t
csrr a0,vstart
vsetvli t0,a4,e64,m2,tu,mu
vse64.v v24,(a2)
ret
