.text
.global capacity
capacity:
li t0,-1
vsetvli a0,t0,e32,mf2,tu,mu
ret
.global replay_0
replay_0:
vsetvli t0,a4,e32,mf2,tu,mu
slli t2,a4,2
mv t1,a2
vle32.v v24,(t1)
add t1,t1,t2
vle32.v v25,(t1)
add t1,t1,t2
vle32.v v26,(t1)
add t1,t1,t2
vle32.v v27,(t1)
add t1,t1,t2
vle32.v v28,(t1)
add t1,t1,t2
vle32.v v29,(t1)
add t1,t1,t2
vle32.v v30,(t1)
add t1,t1,t2
vle32.v v16,(a5)
vlm.v v0,(a3)
vsetivli t0,8,e32,mf2,tu,mu
.global fault_0_pc
fault_0_pc:
vloxseg7ei32.v v24,(a0),v16,v0.t
csrr a0,vstart
vsetvli t0,a4,e32,mf2,tu,mu
slli t2,a4,2
mv t1,a2
vse32.v v24,(t1)
add t1,t1,t2
vse32.v v25,(t1)
add t1,t1,t2
vse32.v v26,(t1)
add t1,t1,t2
vse32.v v27,(t1)
add t1,t1,t2
vse32.v v28,(t1)
add t1,t1,t2
vse32.v v29,(t1)
add t1,t1,t2
vse32.v v30,(t1)
add t1,t1,t2
ret
.global replay_1
replay_1:
vsetvli t0,a4,e32,mf2,tu,mu
slli t2,a4,2
mv t1,a1
vle32.v v24,(t1)
add t1,t1,t2
vle32.v v25,(t1)
add t1,t1,t2
vle32.v v26,(t1)
add t1,t1,t2
vle32.v v27,(t1)
add t1,t1,t2
vle32.v v28,(t1)
add t1,t1,t2
vle32.v v29,(t1)
add t1,t1,t2
vle32.v v30,(t1)
add t1,t1,t2
vle32.v v16,(a5)
vlm.v v0,(a3)
vsetivli t0,8,e32,mf2,tu,mu
.global fault_1_pc
fault_1_pc:
vsoxseg7ei32.v v24,(a0),v16,v0.t
csrr a0,vstart
vsetvli t0,a4,e32,mf2,tu,mu
slli t2,a4,2
mv t1,a2
vse32.v v24,(t1)
add t1,t1,t2
vse32.v v25,(t1)
add t1,t1,t2
vse32.v v26,(t1)
add t1,t1,t2
vse32.v v27,(t1)
add t1,t1,t2
vse32.v v28,(t1)
add t1,t1,t2
vse32.v v29,(t1)
add t1,t1,t2
vse32.v v30,(t1)
add t1,t1,t2
ret
