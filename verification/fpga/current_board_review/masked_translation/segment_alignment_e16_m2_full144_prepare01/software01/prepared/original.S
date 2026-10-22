.text
.global capacity
capacity:
li t0,-1
vsetvli a0,t0,e16,m2,tu,mu
ret
.global op_0
op_0:
vsetvli t0,a4,e16,m2,tu,mu
slli t1,a4,1
mv t2,a1
vle16.v v24,(t2)
add t2,t2,t1
vle16.v v26,(t2)
add t2,t2,t1
vle16.v v28,(t2)
add t2,t2,t1
vlm.v v0,(a2)
vsetvli t0,a3,e16,m2,tu,mu
li t3,1
sd t3,0(a7)
.global target_0
target_0:
vlseg3e16.v v24,(a5),v0.t
csrr t4,vstart
li t3,2
sd t3,0(a7)
vsetvli t0,a4,e16,m2,tu,mu
mv t2,a1
vse16.v v24,(t2)
add t2,t2,t1
vse16.v v26,(t2)
add t2,t2,t1
vse16.v v28,(t2)
add t2,t2,t1
mv a0,t4
ret
.global op_1
op_1:
vsetvli t0,a4,e16,m2,tu,mu
slli t1,a4,1
mv t2,a0
vle16.v v8,(t2)
add t2,t2,t1
vle16.v v10,(t2)
add t2,t2,t1
vle16.v v12,(t2)
add t2,t2,t1
vlm.v v0,(a2)
vsetvli t0,a3,e16,m2,tu,mu
li t3,1
sd t3,0(a7)
.global target_1
target_1:
vsseg3e16.v v8,(a5),v0.t
csrr t4,vstart
li t3,2
sd t3,0(a7)
mv a0,t4
ret
.global op_2
op_2:
vsetvli t0,a4,e16,m2,tu,mu
slli t1,a4,1
mv t2,a1
vle16.v v24,(t2)
add t2,t2,t1
vle16.v v26,(t2)
add t2,t2,t1
vle16.v v28,(t2)
add t2,t2,t1
vlm.v v0,(a2)
vsetvli t0,a3,e16,m2,tu,mu
li t3,1
sd t3,0(a7)
.global target_2
target_2:
vlsseg3e16.v v24,(a5),a6,v0.t
csrr t4,vstart
li t3,2
sd t3,0(a7)
vsetvli t0,a4,e16,m2,tu,mu
mv t2,a1
vse16.v v24,(t2)
add t2,t2,t1
vse16.v v26,(t2)
add t2,t2,t1
vse16.v v28,(t2)
add t2,t2,t1
mv a0,t4
ret
.global op_3
op_3:
vsetvli t0,a4,e16,m2,tu,mu
slli t1,a4,1
mv t2,a0
vle16.v v8,(t2)
add t2,t2,t1
vle16.v v10,(t2)
add t2,t2,t1
vle16.v v12,(t2)
add t2,t2,t1
vlm.v v0,(a2)
vsetvli t0,a3,e16,m2,tu,mu
li t3,1
sd t3,0(a7)
.global target_3
target_3:
vssseg3e16.v v8,(a5),a6,v0.t
csrr t4,vstart
li t3,2
sd t3,0(a7)
mv a0,t4
ret
.global op_4
op_4:
vsetvli t0,a4,e16,m2,tu,mu
slli t1,a4,1
mv t2,a1
vle16.v v24,(t2)
add t2,t2,t1
vle16.v v26,(t2)
add t2,t2,t1
vle16.v v28,(t2)
add t2,t2,t1
vle16.v v30,(t2)
add t2,t2,t1
vlm.v v0,(a2)
vsetvli t0,a3,e16,m2,tu,mu
li t3,1
sd t3,0(a7)
.global target_4
target_4:
vlseg4e16.v v24,(a5),v0.t
csrr t4,vstart
li t3,2
sd t3,0(a7)
vsetvli t0,a4,e16,m2,tu,mu
mv t2,a1
vse16.v v24,(t2)
add t2,t2,t1
vse16.v v26,(t2)
add t2,t2,t1
vse16.v v28,(t2)
add t2,t2,t1
vse16.v v30,(t2)
add t2,t2,t1
mv a0,t4
ret
.global op_5
op_5:
vsetvli t0,a4,e16,m2,tu,mu
slli t1,a4,1
mv t2,a0
vle16.v v8,(t2)
add t2,t2,t1
vle16.v v10,(t2)
add t2,t2,t1
vle16.v v12,(t2)
add t2,t2,t1
vle16.v v14,(t2)
add t2,t2,t1
vlm.v v0,(a2)
vsetvli t0,a3,e16,m2,tu,mu
li t3,1
sd t3,0(a7)
.global target_5
target_5:
vsseg4e16.v v8,(a5),v0.t
csrr t4,vstart
li t3,2
sd t3,0(a7)
mv a0,t4
ret
.global op_6
op_6:
vsetvli t0,a4,e16,m2,tu,mu
slli t1,a4,1
mv t2,a1
vle16.v v24,(t2)
add t2,t2,t1
vle16.v v26,(t2)
add t2,t2,t1
vle16.v v28,(t2)
add t2,t2,t1
vle16.v v30,(t2)
add t2,t2,t1
vlm.v v0,(a2)
vsetvli t0,a3,e16,m2,tu,mu
li t3,1
sd t3,0(a7)
.global target_6
target_6:
vlsseg4e16.v v24,(a5),a6,v0.t
csrr t4,vstart
li t3,2
sd t3,0(a7)
vsetvli t0,a4,e16,m2,tu,mu
mv t2,a1
vse16.v v24,(t2)
add t2,t2,t1
vse16.v v26,(t2)
add t2,t2,t1
vse16.v v28,(t2)
add t2,t2,t1
vse16.v v30,(t2)
add t2,t2,t1
mv a0,t4
ret
.global op_7
op_7:
vsetvli t0,a4,e16,m2,tu,mu
slli t1,a4,1
mv t2,a0
vle16.v v8,(t2)
add t2,t2,t1
vle16.v v10,(t2)
add t2,t2,t1
vle16.v v12,(t2)
add t2,t2,t1
vle16.v v14,(t2)
add t2,t2,t1
vlm.v v0,(a2)
vsetvli t0,a3,e16,m2,tu,mu
li t3,1
sd t3,0(a7)
.global target_7
target_7:
vssseg4e16.v v8,(a5),a6,v0.t
csrr t4,vstart
li t3,2
sd t3,0(a7)
mv a0,t4
ret
