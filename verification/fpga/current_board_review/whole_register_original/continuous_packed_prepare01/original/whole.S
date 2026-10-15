.text
.global op_0
op_0:
csrwi vstart,0
vl8re8.v v8,(a0)
vl8re8.v v24,(a1)
beqz a3,config0_0
li t0,1
beq a3,t0,config1_0
li t0,2
beq a3,t0,config2_0
li t0,3
beq a3,t0,config3_0
li t0,1
slli t0,t0,63
vsetvl zero,zero,t0
j configured_0
config0_0:
vsetivli zero,0,e8,m1,tu,mu
j configured_0
config1_0:
vsetivli zero,7,e16,m2,tu,mu
j configured_0
config2_0:
vsetivli zero,1,e32,m4,tu,mu
j configured_0
config3_0:
vsetivli zero,3,e64,m1,tu,mu
j configured_0
configured_0:
csrw vstart,a2
csrr t3,vstart
vl1re8.v v24,(a0)
csrr a0,vstart
slli t3,t3,32
or a0,a0,t3
csrwi vstart,0
vs1r.v v24,(a1)
ret
.global op_1
op_1:
csrwi vstart,0
vl8re8.v v8,(a0)
vl8re8.v v24,(a1)
beqz a3,config0_1
li t0,1
beq a3,t0,config1_1
li t0,2
beq a3,t0,config2_1
li t0,3
beq a3,t0,config3_1
li t0,1
slli t0,t0,63
vsetvl zero,zero,t0
j configured_1
config0_1:
vsetivli zero,0,e8,m1,tu,mu
j configured_1
config1_1:
vsetivli zero,7,e16,m2,tu,mu
j configured_1
config2_1:
vsetivli zero,1,e32,m4,tu,mu
j configured_1
config3_1:
vsetivli zero,3,e64,m1,tu,mu
j configured_1
configured_1:
csrw vstart,a2
csrr t3,vstart
vl1re16.v v24,(a0)
csrr a0,vstart
slli t3,t3,32
or a0,a0,t3
csrwi vstart,0
vs1r.v v24,(a1)
ret
.global op_2
op_2:
csrwi vstart,0
vl8re8.v v8,(a0)
vl8re8.v v24,(a1)
beqz a3,config0_2
li t0,1
beq a3,t0,config1_2
li t0,2
beq a3,t0,config2_2
li t0,3
beq a3,t0,config3_2
li t0,1
slli t0,t0,63
vsetvl zero,zero,t0
j configured_2
config0_2:
vsetivli zero,0,e8,m1,tu,mu
j configured_2
config1_2:
vsetivli zero,7,e16,m2,tu,mu
j configured_2
config2_2:
vsetivli zero,1,e32,m4,tu,mu
j configured_2
config3_2:
vsetivli zero,3,e64,m1,tu,mu
j configured_2
configured_2:
csrw vstart,a2
csrr t3,vstart
vl1re32.v v24,(a0)
csrr a0,vstart
slli t3,t3,32
or a0,a0,t3
csrwi vstart,0
vs1r.v v24,(a1)
ret
.global op_3
op_3:
csrwi vstart,0
vl8re8.v v8,(a0)
vl8re8.v v24,(a1)
beqz a3,config0_3
li t0,1
beq a3,t0,config1_3
li t0,2
beq a3,t0,config2_3
li t0,3
beq a3,t0,config3_3
li t0,1
slli t0,t0,63
vsetvl zero,zero,t0
j configured_3
config0_3:
vsetivli zero,0,e8,m1,tu,mu
j configured_3
config1_3:
vsetivli zero,7,e16,m2,tu,mu
j configured_3
config2_3:
vsetivli zero,1,e32,m4,tu,mu
j configured_3
config3_3:
vsetivli zero,3,e64,m1,tu,mu
j configured_3
configured_3:
csrw vstart,a2
csrr t3,vstart
vl1re64.v v24,(a0)
csrr a0,vstart
slli t3,t3,32
or a0,a0,t3
csrwi vstart,0
vs1r.v v24,(a1)
ret
.global op_4
op_4:
csrwi vstart,0
vl8re8.v v8,(a0)
vl8re8.v v24,(a1)
beqz a3,config0_4
li t0,1
beq a3,t0,config1_4
li t0,2
beq a3,t0,config2_4
li t0,3
beq a3,t0,config3_4
li t0,1
slli t0,t0,63
vsetvl zero,zero,t0
j configured_4
config0_4:
vsetivli zero,0,e8,m1,tu,mu
j configured_4
config1_4:
vsetivli zero,7,e16,m2,tu,mu
j configured_4
config2_4:
vsetivli zero,1,e32,m4,tu,mu
j configured_4
config3_4:
vsetivli zero,3,e64,m1,tu,mu
j configured_4
configured_4:
csrw vstart,a2
csrr t3,vstart
vl2re8.v v24,(a0)
csrr a0,vstart
slli t3,t3,32
or a0,a0,t3
csrwi vstart,0
vs2r.v v24,(a1)
ret
.global op_5
op_5:
csrwi vstart,0
vl8re8.v v8,(a0)
vl8re8.v v24,(a1)
beqz a3,config0_5
li t0,1
beq a3,t0,config1_5
li t0,2
beq a3,t0,config2_5
li t0,3
beq a3,t0,config3_5
li t0,1
slli t0,t0,63
vsetvl zero,zero,t0
j configured_5
config0_5:
vsetivli zero,0,e8,m1,tu,mu
j configured_5
config1_5:
vsetivli zero,7,e16,m2,tu,mu
j configured_5
config2_5:
vsetivli zero,1,e32,m4,tu,mu
j configured_5
config3_5:
vsetivli zero,3,e64,m1,tu,mu
j configured_5
configured_5:
csrw vstart,a2
csrr t3,vstart
vl2re16.v v24,(a0)
csrr a0,vstart
slli t3,t3,32
or a0,a0,t3
csrwi vstart,0
vs2r.v v24,(a1)
ret
.global op_6
op_6:
csrwi vstart,0
vl8re8.v v8,(a0)
vl8re8.v v24,(a1)
beqz a3,config0_6
li t0,1
beq a3,t0,config1_6
li t0,2
beq a3,t0,config2_6
li t0,3
beq a3,t0,config3_6
li t0,1
slli t0,t0,63
vsetvl zero,zero,t0
j configured_6
config0_6:
vsetivli zero,0,e8,m1,tu,mu
j configured_6
config1_6:
vsetivli zero,7,e16,m2,tu,mu
j configured_6
config2_6:
vsetivli zero,1,e32,m4,tu,mu
j configured_6
config3_6:
vsetivli zero,3,e64,m1,tu,mu
j configured_6
configured_6:
csrw vstart,a2
csrr t3,vstart
vl2re32.v v24,(a0)
csrr a0,vstart
slli t3,t3,32
or a0,a0,t3
csrwi vstart,0
vs2r.v v24,(a1)
ret
.global op_7
op_7:
csrwi vstart,0
vl8re8.v v8,(a0)
vl8re8.v v24,(a1)
beqz a3,config0_7
li t0,1
beq a3,t0,config1_7
li t0,2
beq a3,t0,config2_7
li t0,3
beq a3,t0,config3_7
li t0,1
slli t0,t0,63
vsetvl zero,zero,t0
j configured_7
config0_7:
vsetivli zero,0,e8,m1,tu,mu
j configured_7
config1_7:
vsetivli zero,7,e16,m2,tu,mu
j configured_7
config2_7:
vsetivli zero,1,e32,m4,tu,mu
j configured_7
config3_7:
vsetivli zero,3,e64,m1,tu,mu
j configured_7
configured_7:
csrw vstart,a2
csrr t3,vstart
vl2re64.v v24,(a0)
csrr a0,vstart
slli t3,t3,32
or a0,a0,t3
csrwi vstart,0
vs2r.v v24,(a1)
ret
.global op_8
op_8:
csrwi vstart,0
vl8re8.v v8,(a0)
vl8re8.v v24,(a1)
beqz a3,config0_8
li t0,1
beq a3,t0,config1_8
li t0,2
beq a3,t0,config2_8
li t0,3
beq a3,t0,config3_8
li t0,1
slli t0,t0,63
vsetvl zero,zero,t0
j configured_8
config0_8:
vsetivli zero,0,e8,m1,tu,mu
j configured_8
config1_8:
vsetivli zero,7,e16,m2,tu,mu
j configured_8
config2_8:
vsetivli zero,1,e32,m4,tu,mu
j configured_8
config3_8:
vsetivli zero,3,e64,m1,tu,mu
j configured_8
configured_8:
csrw vstart,a2
csrr t3,vstart
vl4re8.v v24,(a0)
csrr a0,vstart
slli t3,t3,32
or a0,a0,t3
csrwi vstart,0
vs4r.v v24,(a1)
ret
.global op_9
op_9:
csrwi vstart,0
vl8re8.v v8,(a0)
vl8re8.v v24,(a1)
beqz a3,config0_9
li t0,1
beq a3,t0,config1_9
li t0,2
beq a3,t0,config2_9
li t0,3
beq a3,t0,config3_9
li t0,1
slli t0,t0,63
vsetvl zero,zero,t0
j configured_9
config0_9:
vsetivli zero,0,e8,m1,tu,mu
j configured_9
config1_9:
vsetivli zero,7,e16,m2,tu,mu
j configured_9
config2_9:
vsetivli zero,1,e32,m4,tu,mu
j configured_9
config3_9:
vsetivli zero,3,e64,m1,tu,mu
j configured_9
configured_9:
csrw vstart,a2
csrr t3,vstart
vl4re16.v v24,(a0)
csrr a0,vstart
slli t3,t3,32
or a0,a0,t3
csrwi vstart,0
vs4r.v v24,(a1)
ret
.global op_10
op_10:
csrwi vstart,0
vl8re8.v v8,(a0)
vl8re8.v v24,(a1)
beqz a3,config0_10
li t0,1
beq a3,t0,config1_10
li t0,2
beq a3,t0,config2_10
li t0,3
beq a3,t0,config3_10
li t0,1
slli t0,t0,63
vsetvl zero,zero,t0
j configured_10
config0_10:
vsetivli zero,0,e8,m1,tu,mu
j configured_10
config1_10:
vsetivli zero,7,e16,m2,tu,mu
j configured_10
config2_10:
vsetivli zero,1,e32,m4,tu,mu
j configured_10
config3_10:
vsetivli zero,3,e64,m1,tu,mu
j configured_10
configured_10:
csrw vstart,a2
csrr t3,vstart
vl4re32.v v24,(a0)
csrr a0,vstart
slli t3,t3,32
or a0,a0,t3
csrwi vstart,0
vs4r.v v24,(a1)
ret
.global op_11
op_11:
csrwi vstart,0
vl8re8.v v8,(a0)
vl8re8.v v24,(a1)
beqz a3,config0_11
li t0,1
beq a3,t0,config1_11
li t0,2
beq a3,t0,config2_11
li t0,3
beq a3,t0,config3_11
li t0,1
slli t0,t0,63
vsetvl zero,zero,t0
j configured_11
config0_11:
vsetivli zero,0,e8,m1,tu,mu
j configured_11
config1_11:
vsetivli zero,7,e16,m2,tu,mu
j configured_11
config2_11:
vsetivli zero,1,e32,m4,tu,mu
j configured_11
config3_11:
vsetivli zero,3,e64,m1,tu,mu
j configured_11
configured_11:
csrw vstart,a2
csrr t3,vstart
vl4re64.v v24,(a0)
csrr a0,vstart
slli t3,t3,32
or a0,a0,t3
csrwi vstart,0
vs4r.v v24,(a1)
ret
.global op_12
op_12:
csrwi vstart,0
vl8re8.v v8,(a0)
vl8re8.v v24,(a1)
beqz a3,config0_12
li t0,1
beq a3,t0,config1_12
li t0,2
beq a3,t0,config2_12
li t0,3
beq a3,t0,config3_12
li t0,1
slli t0,t0,63
vsetvl zero,zero,t0
j configured_12
config0_12:
vsetivli zero,0,e8,m1,tu,mu
j configured_12
config1_12:
vsetivli zero,7,e16,m2,tu,mu
j configured_12
config2_12:
vsetivli zero,1,e32,m4,tu,mu
j configured_12
config3_12:
vsetivli zero,3,e64,m1,tu,mu
j configured_12
configured_12:
csrw vstart,a2
csrr t3,vstart
vl8re8.v v24,(a0)
csrr a0,vstart
slli t3,t3,32
or a0,a0,t3
csrwi vstart,0
vs8r.v v24,(a1)
ret
.global op_13
op_13:
csrwi vstart,0
vl8re8.v v8,(a0)
vl8re8.v v24,(a1)
beqz a3,config0_13
li t0,1
beq a3,t0,config1_13
li t0,2
beq a3,t0,config2_13
li t0,3
beq a3,t0,config3_13
li t0,1
slli t0,t0,63
vsetvl zero,zero,t0
j configured_13
config0_13:
vsetivli zero,0,e8,m1,tu,mu
j configured_13
config1_13:
vsetivli zero,7,e16,m2,tu,mu
j configured_13
config2_13:
vsetivli zero,1,e32,m4,tu,mu
j configured_13
config3_13:
vsetivli zero,3,e64,m1,tu,mu
j configured_13
configured_13:
csrw vstart,a2
csrr t3,vstart
vl8re16.v v24,(a0)
csrr a0,vstart
slli t3,t3,32
or a0,a0,t3
csrwi vstart,0
vs8r.v v24,(a1)
ret
.global op_14
op_14:
csrwi vstart,0
vl8re8.v v8,(a0)
vl8re8.v v24,(a1)
beqz a3,config0_14
li t0,1
beq a3,t0,config1_14
li t0,2
beq a3,t0,config2_14
li t0,3
beq a3,t0,config3_14
li t0,1
slli t0,t0,63
vsetvl zero,zero,t0
j configured_14
config0_14:
vsetivli zero,0,e8,m1,tu,mu
j configured_14
config1_14:
vsetivli zero,7,e16,m2,tu,mu
j configured_14
config2_14:
vsetivli zero,1,e32,m4,tu,mu
j configured_14
config3_14:
vsetivli zero,3,e64,m1,tu,mu
j configured_14
configured_14:
csrw vstart,a2
csrr t3,vstart
vl8re32.v v24,(a0)
csrr a0,vstart
slli t3,t3,32
or a0,a0,t3
csrwi vstart,0
vs8r.v v24,(a1)
ret
.global op_15
op_15:
csrwi vstart,0
vl8re8.v v8,(a0)
vl8re8.v v24,(a1)
beqz a3,config0_15
li t0,1
beq a3,t0,config1_15
li t0,2
beq a3,t0,config2_15
li t0,3
beq a3,t0,config3_15
li t0,1
slli t0,t0,63
vsetvl zero,zero,t0
j configured_15
config0_15:
vsetivli zero,0,e8,m1,tu,mu
j configured_15
config1_15:
vsetivli zero,7,e16,m2,tu,mu
j configured_15
config2_15:
vsetivli zero,1,e32,m4,tu,mu
j configured_15
config3_15:
vsetivli zero,3,e64,m1,tu,mu
j configured_15
configured_15:
csrw vstart,a2
csrr t3,vstart
vl8re64.v v24,(a0)
csrr a0,vstart
slli t3,t3,32
or a0,a0,t3
csrwi vstart,0
vs8r.v v24,(a1)
ret
.global op_16
op_16:
csrwi vstart,0
vl8re8.v v8,(a0)
vl8re8.v v24,(a1)
beqz a3,config0_16
li t0,1
beq a3,t0,config1_16
li t0,2
beq a3,t0,config2_16
li t0,3
beq a3,t0,config3_16
li t0,1
slli t0,t0,63
vsetvl zero,zero,t0
j configured_16
config0_16:
vsetivli zero,0,e8,m1,tu,mu
j configured_16
config1_16:
vsetivli zero,7,e16,m2,tu,mu
j configured_16
config2_16:
vsetivli zero,1,e32,m4,tu,mu
j configured_16
config3_16:
vsetivli zero,3,e64,m1,tu,mu
j configured_16
configured_16:
csrw vstart,a2
csrr t3,vstart
vmv1r.v v24,v8
csrr a0,vstart
slli t3,t3,32
or a0,a0,t3
csrwi vstart,0
vs1r.v v24,(a1)
ret
.global op_17
op_17:
csrwi vstart,0
vl8re8.v v8,(a0)
vl8re8.v v24,(a1)
beqz a3,config0_17
li t0,1
beq a3,t0,config1_17
li t0,2
beq a3,t0,config2_17
li t0,3
beq a3,t0,config3_17
li t0,1
slli t0,t0,63
vsetvl zero,zero,t0
j configured_17
config0_17:
vsetivli zero,0,e8,m1,tu,mu
j configured_17
config1_17:
vsetivli zero,7,e16,m2,tu,mu
j configured_17
config2_17:
vsetivli zero,1,e32,m4,tu,mu
j configured_17
config3_17:
vsetivli zero,3,e64,m1,tu,mu
j configured_17
configured_17:
csrw vstart,a2
csrr t3,vstart
vmv2r.v v24,v8
csrr a0,vstart
slli t3,t3,32
or a0,a0,t3
csrwi vstart,0
vs2r.v v24,(a1)
ret
.global op_18
op_18:
csrwi vstart,0
vl8re8.v v8,(a0)
vl8re8.v v24,(a1)
beqz a3,config0_18
li t0,1
beq a3,t0,config1_18
li t0,2
beq a3,t0,config2_18
li t0,3
beq a3,t0,config3_18
li t0,1
slli t0,t0,63
vsetvl zero,zero,t0
j configured_18
config0_18:
vsetivli zero,0,e8,m1,tu,mu
j configured_18
config1_18:
vsetivli zero,7,e16,m2,tu,mu
j configured_18
config2_18:
vsetivli zero,1,e32,m4,tu,mu
j configured_18
config3_18:
vsetivli zero,3,e64,m1,tu,mu
j configured_18
configured_18:
csrw vstart,a2
csrr t3,vstart
vmv4r.v v24,v8
csrr a0,vstart
slli t3,t3,32
or a0,a0,t3
csrwi vstart,0
vs4r.v v24,(a1)
ret
.global op_19
op_19:
csrwi vstart,0
vl8re8.v v8,(a0)
vl8re8.v v24,(a1)
beqz a3,config0_19
li t0,1
beq a3,t0,config1_19
li t0,2
beq a3,t0,config2_19
li t0,3
beq a3,t0,config3_19
li t0,1
slli t0,t0,63
vsetvl zero,zero,t0
j configured_19
config0_19:
vsetivli zero,0,e8,m1,tu,mu
j configured_19
config1_19:
vsetivli zero,7,e16,m2,tu,mu
j configured_19
config2_19:
vsetivli zero,1,e32,m4,tu,mu
j configured_19
config3_19:
vsetivli zero,3,e64,m1,tu,mu
j configured_19
configured_19:
csrw vstart,a2
csrr t3,vstart
vmv8r.v v24,v8
csrr a0,vstart
slli t3,t3,32
or a0,a0,t3
csrwi vstart,0
vs8r.v v24,(a1)
ret
