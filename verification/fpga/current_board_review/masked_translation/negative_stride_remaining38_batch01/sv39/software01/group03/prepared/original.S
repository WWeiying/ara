.text
.global capacity
capacity:
li t0,-1
vsetvli a0,t0,e16,m1,tu,mu
ret
.global replay_0
replay_0:
vsetvli t0,a4,e16,m1,tu,mu
vle16.v v24,(a2)
ld t3,0(a5)
vlm.v v0,(a3)
vsetivli t0,8,e16,m1,tu,mu
.global fault_0_pc
fault_0_pc:
vlse16.v v24,(a0),t3,v0.t
csrr a0,vstart
vsetvli t0,a4,e16,m1,tu,mu
vse16.v v24,(a2)
ret
.global replay_1
replay_1:
vsetvli t0,a4,e16,m1,tu,mu
vle16.v v24,(a1)
ld t3,0(a5)
vlm.v v0,(a3)
vsetivli t0,8,e16,m1,tu,mu
.global fault_1_pc
fault_1_pc:
vsse16.v v24,(a0),t3,v0.t
csrr a0,vstart
vsetvli t0,a4,e16,m1,tu,mu
vse16.v v24,(a2)
ret
