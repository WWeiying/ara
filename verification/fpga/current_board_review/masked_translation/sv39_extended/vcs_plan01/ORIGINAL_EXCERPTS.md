# Read-Only Original Source Excerpts

Original Linux source is retained and hash verified, not run bare metal.
Fixture C/S is a semantic adapter, not byte-identical original source.

## unit_load_retry

/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_fault_handoff_e16m1_01/singles/rvv_small_fault_e16_m1_u0_s0_b3_m2

scenario.S SHA256 `91f002471d8bcdb4e9e94b88c89a7d1f108f93b34b01c39979e0d83a64a53f6b`

```text
   1: .text
   2: .global capacity
   3: capacity:
   4: li t0,-1
   5: vsetvli a0,t0,e16,m1,tu,mu
   6: ret
   7: .global replay_0
   8: replay_0:
   9: vsetvli t0,a4,e16,m1,tu,mu
  10: vle16.v v24,(a2)
  11: vlm.v v0,(a3)
  12: vsetivli t0,8,e16,m1,tu,mu
  13: .global fault_0_pc
  14: fault_0_pc:
  15: vle16.v v24,(a0),v0.t
  16: csrr a0,vstart
  17: vsetvli t0,a4,e16,m1,tu,mu
  18: vse16.v v24,(a2)
  19: ret
  20: .global replay_1
  21: replay_1:
  22: vsetvli t0,a4,e16,m1,tu,mu
  23: vle16.v v24,(a1)
  24: vlm.v v0,(a3)
  25: vsetivli t0,8,e16,m1,tu,mu
  26: .global fault_1_pc
  27: fault_1_pc:
  28: vse16.v v24,(a0),v0.t
  29: csrr a0,vstart
  30: vsetvli t0,a4,e16,m1,tu,mu
  31: vse16.v v24,(a2)
  32: ret
```

scenario.c SHA256 `8212db821a270a21fe2c925e5dcde0b3c2339ab06cfe617a5afd2c2533f64f39`

```text
 158:        uc->uc_mcontext.sc_regs.pc!=(uintptr_t)(store_case ? fault_1_pc:fault_0_pc) ||
 159:        state->vstart!=expected_start || state->vl!=REPLAY_ELEMENTS ||
 160:        state->vtype!=((SEW==8 ? 0:SEW==16 ? 8:SEW==32 ? 16:24)|LMUL_CODE))++handler_errors;
 161:     for(unsigned f=0;f<REPLAY_FIELDS;++f){
 162:     const word *saved=(const void *)((uintptr_t)state->datap+(24+f*FIELD_REGISTER_STRIDE)*state->vlenb);
 174: #endif
 175:     /* Changing completed elements detects an incorrect restart from element0. */
 176:     for(unsigned i=0;i<expected_start && i<REPLAY_ELEMENTS;++i)for(unsigned f=0;f<REPLAY_FIELDS;++f)
 177:         if(active(i))*(word *)field_address(i,f)=store_case ? poison(f*cap+i):(word)(original(field_address(i,f))^0x5b);
 178:     /* Keep the saved PC, vstart and vector register data unchanged. */
 179: #if NEGATIVE_RESTART
 180:     state->vstart=0;
 181: #endif
 219: #if ZERO_STRIDE
 220:         stride=0;
 221:         target=mapping+4096-accessible_fields*sizeof(word);
 222: #else
 223:         stride=(REPLAY_FIELDS+gap)*sizeof(word);
 224: #if NEGATIVE_STRIDE
 225:         target=mapping+4096+boundary*stride-(REPLAY_FIELDS-accessible_fields)*sizeof(word);
 226:         stride=-stride;
 227: #else
 228:         target=mapping+4096-boundary*stride-accessible_fields*sizeof(word);
 229: #endif
 230: #endif
 231: #else
 232:         target=mapping+4096-(boundary*REPLAY_FIELDS+accessible_fields)*sizeof(word);
 233: #endif
 234:         for(unsigned f=0;f<REPLAY_FIELDS;++f)for(unsigned i=0;i<cap;++i)
 235:             input[f*cap+i]=(word)(101+(ZERO_STRIDE ? 0:i*13)+f*29);
 248:         for(unsigned i=0;i<CAPACITY_LIMIT*REPLAY_FIELDS+2;++i)output[i]=(word)0x5b;
 249:         for(unsigned i=0;i<CAPACITY_LIMIT/8;++i)mask[i]=mode==0 ? 255:mode==1 ? 0xaa:mode==2 ? 0x24:0;
 250:         expected_start=REPLAY_ELEMENTS;
 251:         for(unsigned i=boundary;i<REPLAY_ELEMENTS;++i)if(active(i)){expected_start=i;break;}
 252:         expected_address=element_address(expected_start);faults=0;handler_errors=0;
 272:         for(unsigned f=0;f<REPLAY_FIELDS;++f)for(unsigned i=0;i<cap;++i){
 273:             word wanted=store_case ? input[f*cap+i]:i<REPLAY_ELEMENTS && active(i) ? original(field_address(i,f)):(word)0x5b;
 274:             if(output[f*cap+i+1]!=wanted)++errors;
 275:         }
 276:         for(unsigned i=0;i<8192/sizeof(word);++i){
 277:             uintptr_t at=mapping+i*sizeof(word);word wanted=original(at);
 278:             unsigned slot=logical_element(at),j=slot/REPLAY_FIELDS,f=slot%REPLAY_FIELDS;
 279:             if(store_case && j<REPLAY_ELEMENTS){
 280:                 if(active(j))wanted=faults && j<expected_start ? poison(f*cap+j):input[f*cap+j];
 281:             }else if(!store_case && faults && j<expected_start){
 282:                 if(active(j))wanted^=0x5b;
 283:             }
```

## unit_store_retry

/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_fault_handoff_e16m1_01/singles/rvv_small_fault_e16_m1_u0_s1_b3_m2

scenario.S SHA256 `91f002471d8bcdb4e9e94b88c89a7d1f108f93b34b01c39979e0d83a64a53f6b`

```text
   1: .text
   2: .global capacity
   3: capacity:
   4: li t0,-1
   5: vsetvli a0,t0,e16,m1,tu,mu
   6: ret
   7: .global replay_0
   8: replay_0:
   9: vsetvli t0,a4,e16,m1,tu,mu
  10: vle16.v v24,(a2)
  11: vlm.v v0,(a3)
  12: vsetivli t0,8,e16,m1,tu,mu
  13: .global fault_0_pc
  14: fault_0_pc:
  15: vle16.v v24,(a0),v0.t
  16: csrr a0,vstart
  17: vsetvli t0,a4,e16,m1,tu,mu
  18: vse16.v v24,(a2)
  19: ret
  20: .global replay_1
  21: replay_1:
  22: vsetvli t0,a4,e16,m1,tu,mu
  23: vle16.v v24,(a1)
  24: vlm.v v0,(a3)
  25: vsetivli t0,8,e16,m1,tu,mu
  26: .global fault_1_pc
  27: fault_1_pc:
  28: vse16.v v24,(a0),v0.t
  29: csrr a0,vstart
  30: vsetvli t0,a4,e16,m1,tu,mu
  31: vse16.v v24,(a2)
  32: ret
```

scenario.c SHA256 `a9628f9d441eadf866177e222cb8690b126c2fefd6094d7f63bfdb6931947500`

```text
 158:        uc->uc_mcontext.sc_regs.pc!=(uintptr_t)(store_case ? fault_1_pc:fault_0_pc) ||
 159:        state->vstart!=expected_start || state->vl!=REPLAY_ELEMENTS ||
 160:        state->vtype!=((SEW==8 ? 0:SEW==16 ? 8:SEW==32 ? 16:24)|LMUL_CODE))++handler_errors;
 161:     for(unsigned f=0;f<REPLAY_FIELDS;++f){
 162:     const word *saved=(const void *)((uintptr_t)state->datap+(24+f*FIELD_REGISTER_STRIDE)*state->vlenb);
 174: #endif
 175:     /* Changing completed elements detects an incorrect restart from element0. */
 176:     for(unsigned i=0;i<expected_start && i<REPLAY_ELEMENTS;++i)for(unsigned f=0;f<REPLAY_FIELDS;++f)
 177:         if(active(i))*(word *)field_address(i,f)=store_case ? poison(f*cap+i):(word)(original(field_address(i,f))^0x5b);
 178:     /* Keep the saved PC, vstart and vector register data unchanged. */
 179: #if NEGATIVE_RESTART
 180:     state->vstart=0;
 181: #endif
 219: #if ZERO_STRIDE
 220:         stride=0;
 221:         target=mapping+4096-accessible_fields*sizeof(word);
 222: #else
 223:         stride=(REPLAY_FIELDS+gap)*sizeof(word);
 224: #if NEGATIVE_STRIDE
 225:         target=mapping+4096+boundary*stride-(REPLAY_FIELDS-accessible_fields)*sizeof(word);
 226:         stride=-stride;
 227: #else
 228:         target=mapping+4096-boundary*stride-accessible_fields*sizeof(word);
 229: #endif
 230: #endif
 231: #else
 232:         target=mapping+4096-(boundary*REPLAY_FIELDS+accessible_fields)*sizeof(word);
 233: #endif
 234:         for(unsigned f=0;f<REPLAY_FIELDS;++f)for(unsigned i=0;i<cap;++i)
 235:             input[f*cap+i]=(word)(101+(ZERO_STRIDE ? 0:i*13)+f*29);
 248:         for(unsigned i=0;i<CAPACITY_LIMIT*REPLAY_FIELDS+2;++i)output[i]=(word)0x5b;
 249:         for(unsigned i=0;i<CAPACITY_LIMIT/8;++i)mask[i]=mode==0 ? 255:mode==1 ? 0xaa:mode==2 ? 0x24:0;
 250:         expected_start=REPLAY_ELEMENTS;
 251:         for(unsigned i=boundary;i<REPLAY_ELEMENTS;++i)if(active(i)){expected_start=i;break;}
 252:         expected_address=element_address(expected_start);faults=0;handler_errors=0;
 272:         for(unsigned f=0;f<REPLAY_FIELDS;++f)for(unsigned i=0;i<cap;++i){
 273:             word wanted=store_case ? input[f*cap+i]:i<REPLAY_ELEMENTS && active(i) ? original(field_address(i,f)):(word)0x5b;
 274:             if(output[f*cap+i+1]!=wanted)++errors;
 275:         }
 276:         for(unsigned i=0;i<8192/sizeof(word);++i){
 277:             uintptr_t at=mapping+i*sizeof(word);word wanted=original(at);
 278:             unsigned slot=logical_element(at),j=slot/REPLAY_FIELDS,f=slot%REPLAY_FIELDS;
 279:             if(store_case && j<REPLAY_ELEMENTS){
 280:                 if(active(j))wanted=faults && j<expected_start ? poison(f*cap+j):input[f*cap+j];
 281:             }else if(!store_case && faults && j<expected_start){
 282:                 if(active(j))wanted^=0x5b;
 283:             }
```

## positive_load_retry

/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_strided_fault_handoff01/singles/rvv_small_fault_strided_e16_m1_u0_s0_b3_m2_f0_g3

scenario.S SHA256 `597a58a41e73941a90e3ccc015676dca606d9f6f74436b2965dede15bfab3039`

```text
   1: .text
   2: .global capacity
   3: capacity:
   4: li t0,-1
   5: vsetvli a0,t0,e16,m1,tu,mu
   6: ret
   7: .global replay_0
   8: replay_0:
   9: vsetvli t0,a4,e16,m1,tu,mu
  10: vle16.v v24,(a2)
  11: ld t3,0(a5)
  12: vlm.v v0,(a3)
  13: vsetivli t0,8,e16,m1,tu,mu
  14: .global fault_0_pc
  15: fault_0_pc:
  16: vlse16.v v24,(a0),t3,v0.t
  17: csrr a0,vstart
  18: vsetvli t0,a4,e16,m1,tu,mu
  19: vse16.v v24,(a2)
  20: ret
  21: .global replay_1
  22: replay_1:
  23: vsetvli t0,a4,e16,m1,tu,mu
  24: vle16.v v24,(a1)
  25: ld t3,0(a5)
  26: vlm.v v0,(a3)
  27: vsetivli t0,8,e16,m1,tu,mu
  28: .global fault_1_pc
  29: fault_1_pc:
  30: vsse16.v v24,(a0),t3,v0.t
  31: csrr a0,vstart
  32: vsetvli t0,a4,e16,m1,tu,mu
  33: vse16.v v24,(a2)
  34: ret
```

scenario.c SHA256 `52fb44e99b956d1fc29e6f49a9113dd40b4c488911c4df7543b08ecf574d29c1`

```text
 158:        uc->uc_mcontext.sc_regs.pc!=(uintptr_t)(store_case ? fault_1_pc:fault_0_pc) ||
 159:        state->vstart!=expected_start || state->vl!=REPLAY_ELEMENTS ||
 160:        state->vtype!=((SEW==8 ? 0:SEW==16 ? 8:SEW==32 ? 16:24)|LMUL_CODE))++handler_errors;
 161:     for(unsigned f=0;f<REPLAY_FIELDS;++f){
 162:     const word *saved=(const void *)((uintptr_t)state->datap+(24+f*FIELD_REGISTER_STRIDE)*state->vlenb);
 174: #endif
 175:     /* Changing completed elements detects an incorrect restart from element0. */
 176:     for(unsigned i=0;i<expected_start && i<REPLAY_ELEMENTS;++i)for(unsigned f=0;f<REPLAY_FIELDS;++f)
 177:         if(active(i))*(word *)field_address(i,f)=store_case ? poison(f*cap+i):(word)(original(field_address(i,f))^0x5b);
 178:     /* Keep the saved PC, vstart and vector register data unchanged. */
 179: #if NEGATIVE_RESTART
 180:     state->vstart=0;
 181: #endif
 223: #if ZERO_STRIDE
 224:         stride=0;
 225:         target=mapping+4096-accessible_fields*sizeof(word);
 226: #else
 227:         stride=(REPLAY_FIELDS+gap)*sizeof(word);
 228: #if NEGATIVE_STRIDE
 229:         target=mapping+4096+boundary*stride-(REPLAY_FIELDS-accessible_fields)*sizeof(word);
 230:         stride=-stride;
 231: #else
 232:         target=mapping+4096-boundary*stride-accessible_fields*sizeof(word);
 233: #endif
 234: #endif
 235: #else
 236:         target=mapping+4096-(boundary*REPLAY_FIELDS+accessible_fields)*sizeof(word);
 237: #endif
 238:         for(unsigned f=0;f<REPLAY_FIELDS;++f)for(unsigned i=0;i<cap;++i)
 239:             input[f*cap+i]=(word)(101+(ZERO_STRIDE ? 0:i*13)+f*29);
 252:         for(unsigned i=0;i<CAPACITY_LIMIT*REPLAY_FIELDS+2;++i)output[i]=(word)0x5b;
 253:         for(unsigned i=0;i<CAPACITY_LIMIT/8;++i)mask[i]=mode==0 ? 255:mode==1 ? 0xaa:mode==2 ? 0x24:0;
 254:         expected_start=REPLAY_ELEMENTS;
 255:         for(unsigned i=boundary;i<REPLAY_ELEMENTS;++i)if(active(i)){expected_start=i;break;}
 256:         expected_address=element_address(expected_start);faults=0;handler_errors=0;
 276:         for(unsigned f=0;f<REPLAY_FIELDS;++f)for(unsigned i=0;i<cap;++i){
 277:             word wanted=store_case ? input[f*cap+i]:i<REPLAY_ELEMENTS && active(i) ? original(field_address(i,f)):(word)0x5b;
 278:             if(output[f*cap+i+1]!=wanted)++errors;
 279:         }
 280:         for(unsigned i=0;i<8192/sizeof(word);++i){
 281:             uintptr_t at=mapping+i*sizeof(word);word wanted=original(at);
 282:             unsigned slot=logical_element(at),j=slot/REPLAY_FIELDS,f=slot%REPLAY_FIELDS;
 283:             if(store_case && j<REPLAY_ELEMENTS){
 284:                 if(active(j))wanted=faults && j<expected_start ? poison(f*cap+j):input[f*cap+j];
 285:             }else if(!store_case && faults && j<expected_start){
 286:                 if(active(j))wanted^=0x5b;
 287:             }
```

## negative_store_retry

/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_negative_stride_handoff01/singles/rvv_small_fault_strided_negative_stride_e16_m1_u0_s1_b3_m2_f0_g1

scenario.S SHA256 `597a58a41e73941a90e3ccc015676dca606d9f6f74436b2965dede15bfab3039`

```text
   1: .text
   2: .global capacity
   3: capacity:
   4: li t0,-1
   5: vsetvli a0,t0,e16,m1,tu,mu
   6: ret
   7: .global replay_0
   8: replay_0:
   9: vsetvli t0,a4,e16,m1,tu,mu
  10: vle16.v v24,(a2)
  11: ld t3,0(a5)
  12: vlm.v v0,(a3)
  13: vsetivli t0,8,e16,m1,tu,mu
  14: .global fault_0_pc
  15: fault_0_pc:
  16: vlse16.v v24,(a0),t3,v0.t
  17: csrr a0,vstart
  18: vsetvli t0,a4,e16,m1,tu,mu
  19: vse16.v v24,(a2)
  20: ret
  21: .global replay_1
  22: replay_1:
  23: vsetvli t0,a4,e16,m1,tu,mu
  24: vle16.v v24,(a1)
  25: ld t3,0(a5)
  26: vlm.v v0,(a3)
  27: vsetivli t0,8,e16,m1,tu,mu
  28: .global fault_1_pc
  29: fault_1_pc:
  30: vsse16.v v24,(a0),t3,v0.t
  31: csrr a0,vstart
  32: vsetvli t0,a4,e16,m1,tu,mu
  33: vse16.v v24,(a2)
  34: ret
```

scenario.c SHA256 `55f8d781291b5b11bed6fe5a9632bbe9dc4050a7fcaa55185a399d096ac929b4`

```text
 158:        uc->uc_mcontext.sc_regs.pc!=(uintptr_t)(store_case ? fault_1_pc:fault_0_pc) ||
 159:        state->vstart!=expected_start || state->vl!=REPLAY_ELEMENTS ||
 160:        state->vtype!=((SEW==8 ? 0:SEW==16 ? 8:SEW==32 ? 16:24)|LMUL_CODE))++handler_errors;
 161:     for(unsigned f=0;f<REPLAY_FIELDS;++f){
 162:     const word *saved=(const void *)((uintptr_t)state->datap+(24+f*FIELD_REGISTER_STRIDE)*state->vlenb);
 174: #endif
 175:     /* Changing completed elements detects an incorrect restart from element0. */
 176:     for(unsigned i=0;i<expected_start && i<REPLAY_ELEMENTS;++i)for(unsigned f=0;f<REPLAY_FIELDS;++f)
 177:         if(active(i))*(word *)field_address(i,f)=store_case ? poison(f*cap+i):(word)(original(field_address(i,f))^0x5b);
 178:     /* Keep the saved PC, vstart and vector register data unchanged. */
 179: #if NEGATIVE_RESTART
 180:     state->vstart=0;
 181: #endif
 223: #if ZERO_STRIDE
 224:         stride=0;
 225:         target=mapping+4096-accessible_fields*sizeof(word);
 226: #else
 227:         stride=(REPLAY_FIELDS+gap)*sizeof(word);
 228: #if NEGATIVE_STRIDE
 229:         target=mapping+4096+boundary*stride-(REPLAY_FIELDS-accessible_fields)*sizeof(word);
 230:         stride=-stride;
 231: #else
 232:         target=mapping+4096-boundary*stride-accessible_fields*sizeof(word);
 233: #endif
 234: #endif
 235: #else
 236:         target=mapping+4096-(boundary*REPLAY_FIELDS+accessible_fields)*sizeof(word);
 237: #endif
 238:         for(unsigned f=0;f<REPLAY_FIELDS;++f)for(unsigned i=0;i<cap;++i)
 239:             input[f*cap+i]=(word)(101+(ZERO_STRIDE ? 0:i*13)+f*29);
 252:         for(unsigned i=0;i<CAPACITY_LIMIT*REPLAY_FIELDS+2;++i)output[i]=(word)0x5b;
 253:         for(unsigned i=0;i<CAPACITY_LIMIT/8;++i)mask[i]=mode==0 ? 255:mode==1 ? 0xaa:mode==2 ? 0x24:0;
 254:         expected_start=REPLAY_ELEMENTS;
 255:         for(unsigned i=boundary;i<REPLAY_ELEMENTS;++i)if(active(i)){expected_start=i;break;}
 256:         expected_address=element_address(expected_start);faults=0;handler_errors=0;
 276:         for(unsigned f=0;f<REPLAY_FIELDS;++f)for(unsigned i=0;i<cap;++i){
 277:             word wanted=store_case ? input[f*cap+i]:i<REPLAY_ELEMENTS && active(i) ? original(field_address(i,f)):(word)0x5b;
 278:             if(output[f*cap+i+1]!=wanted)++errors;
 279:         }
 280:         for(unsigned i=0;i<8192/sizeof(word);++i){
 281:             uintptr_t at=mapping+i*sizeof(word);word wanted=original(at);
 282:             unsigned slot=logical_element(at),j=slot/REPLAY_FIELDS,f=slot%REPLAY_FIELDS;
 283:             if(store_case && j<REPLAY_ELEMENTS){
 284:                 if(active(j))wanted=faults && j<expected_start ? poison(f*cap+j):input[f*cap+j];
 285:             }else if(!store_case && faults && j<expected_start){
 286:                 if(active(j))wanted^=0x5b;
 287:             }
```

## zero_load_retry

/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_zero_stride_handoff01/singles/rvv_small_fault_strided_zero_stride_e16_m1_u0_s0_b0_m2_f0

scenario.S SHA256 `597a58a41e73941a90e3ccc015676dca606d9f6f74436b2965dede15bfab3039`

```text
   1: .text
   2: .global capacity
   3: capacity:
   4: li t0,-1
   5: vsetvli a0,t0,e16,m1,tu,mu
   6: ret
   7: .global replay_0
   8: replay_0:
   9: vsetvli t0,a4,e16,m1,tu,mu
  10: vle16.v v24,(a2)
  11: ld t3,0(a5)
  12: vlm.v v0,(a3)
  13: vsetivli t0,8,e16,m1,tu,mu
  14: .global fault_0_pc
  15: fault_0_pc:
  16: vlse16.v v24,(a0),t3,v0.t
  17: csrr a0,vstart
  18: vsetvli t0,a4,e16,m1,tu,mu
  19: vse16.v v24,(a2)
  20: ret
  21: .global replay_1
  22: replay_1:
  23: vsetvli t0,a4,e16,m1,tu,mu
  24: vle16.v v24,(a1)
  25: ld t3,0(a5)
  26: vlm.v v0,(a3)
  27: vsetivli t0,8,e16,m1,tu,mu
  28: .global fault_1_pc
  29: fault_1_pc:
  30: vsse16.v v24,(a0),t3,v0.t
  31: csrr a0,vstart
  32: vsetvli t0,a4,e16,m1,tu,mu
  33: vse16.v v24,(a2)
  34: ret
```

scenario.c SHA256 `f2437b6927b5edc0e27edcc9b96651bb099c6e213eb98e25b91c85eb8e1de4e5`

```text
 158:        uc->uc_mcontext.sc_regs.pc!=(uintptr_t)(store_case ? fault_1_pc:fault_0_pc) ||
 159:        state->vstart!=expected_start || state->vl!=REPLAY_ELEMENTS ||
 160:        state->vtype!=((SEW==8 ? 0:SEW==16 ? 8:SEW==32 ? 16:24)|LMUL_CODE))++handler_errors;
 161:     for(unsigned f=0;f<REPLAY_FIELDS;++f){
 162:     const word *saved=(const void *)((uintptr_t)state->datap+(24+f*FIELD_REGISTER_STRIDE)*state->vlenb);
 174: #endif
 175:     /* Changing completed elements detects an incorrect restart from element0. */
 176:     for(unsigned i=0;i<expected_start && i<REPLAY_ELEMENTS;++i)for(unsigned f=0;f<REPLAY_FIELDS;++f)
 177:         if(active(i))*(word *)field_address(i,f)=store_case ? poison(f*cap+i):(word)(original(field_address(i,f))^0x5b);
 178:     /* Keep the saved PC, vstart and vector register data unchanged. */
 179: #if NEGATIVE_RESTART
 180:     state->vstart=0;
 181: #endif
 223: #if ZERO_STRIDE
 224:         stride=0;
 225:         target=mapping+4096-accessible_fields*sizeof(word);
 226: #else
 227:         stride=(REPLAY_FIELDS+gap)*sizeof(word);
 228: #if NEGATIVE_STRIDE
 229:         target=mapping+4096+boundary*stride-(REPLAY_FIELDS-accessible_fields)*sizeof(word);
 230:         stride=-stride;
 231: #else
 232:         target=mapping+4096-boundary*stride-accessible_fields*sizeof(word);
 233: #endif
 234: #endif
 235: #else
 236:         target=mapping+4096-(boundary*REPLAY_FIELDS+accessible_fields)*sizeof(word);
 237: #endif
 238:         for(unsigned f=0;f<REPLAY_FIELDS;++f)for(unsigned i=0;i<cap;++i)
 239:             input[f*cap+i]=(word)(101+(ZERO_STRIDE ? 0:i*13)+f*29);
 252:         for(unsigned i=0;i<CAPACITY_LIMIT*REPLAY_FIELDS+2;++i)output[i]=(word)0x5b;
 253:         for(unsigned i=0;i<CAPACITY_LIMIT/8;++i)mask[i]=mode==0 ? 255:mode==1 ? 0xaa:mode==2 ? 0x24:0;
 254:         expected_start=REPLAY_ELEMENTS;
 255:         for(unsigned i=boundary;i<REPLAY_ELEMENTS;++i)if(active(i)){expected_start=i;break;}
 256:         expected_address=element_address(expected_start);faults=0;handler_errors=0;
 276:         for(unsigned f=0;f<REPLAY_FIELDS;++f)for(unsigned i=0;i<cap;++i){
 277:             word wanted=store_case ? input[f*cap+i]:i<REPLAY_ELEMENTS && active(i) ? original(field_address(i,f)):(word)0x5b;
 278:             if(output[f*cap+i+1]!=wanted)++errors;
 279:         }
 280:         for(unsigned i=0;i<8192/sizeof(word);++i){
 281:             uintptr_t at=mapping+i*sizeof(word);word wanted=original(at);
 282:             unsigned slot=logical_element(at),j=slot/REPLAY_FIELDS,f=slot%REPLAY_FIELDS;
 283:             if(store_case && j<REPLAY_ELEMENTS){
 284:                 if(active(j))wanted=faults && j<expected_start ? poison(f*cap+j):input[f*cap+j];
 285:             }else if(!store_case && faults && j<expected_start){
 286:                 if(active(j))wanted^=0x5b;
 287:             }
```

## zero_store_alloff

/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_zero_stride_handoff01/singles/rvv_small_fault_strided_zero_stride_e16_m1_u0_s1_b0_m3_f0

scenario.S SHA256 `597a58a41e73941a90e3ccc015676dca606d9f6f74436b2965dede15bfab3039`

```text
   1: .text
   2: .global capacity
   3: capacity:
   4: li t0,-1
   5: vsetvli a0,t0,e16,m1,tu,mu
   6: ret
   7: .global replay_0
   8: replay_0:
   9: vsetvli t0,a4,e16,m1,tu,mu
  10: vle16.v v24,(a2)
  11: ld t3,0(a5)
  12: vlm.v v0,(a3)
  13: vsetivli t0,8,e16,m1,tu,mu
  14: .global fault_0_pc
  15: fault_0_pc:
  16: vlse16.v v24,(a0),t3,v0.t
  17: csrr a0,vstart
  18: vsetvli t0,a4,e16,m1,tu,mu
  19: vse16.v v24,(a2)
  20: ret
  21: .global replay_1
  22: replay_1:
  23: vsetvli t0,a4,e16,m1,tu,mu
  24: vle16.v v24,(a1)
  25: ld t3,0(a5)
  26: vlm.v v0,(a3)
  27: vsetivli t0,8,e16,m1,tu,mu
  28: .global fault_1_pc
  29: fault_1_pc:
  30: vsse16.v v24,(a0),t3,v0.t
  31: csrr a0,vstart
  32: vsetvli t0,a4,e16,m1,tu,mu
  33: vse16.v v24,(a2)
  34: ret
```

scenario.c SHA256 `a45bfe83616fdb82d9653971bdb134246b178f207aa3496feea2e8f8c6a1450d`

```text
 158:        uc->uc_mcontext.sc_regs.pc!=(uintptr_t)(store_case ? fault_1_pc:fault_0_pc) ||
 159:        state->vstart!=expected_start || state->vl!=REPLAY_ELEMENTS ||
 160:        state->vtype!=((SEW==8 ? 0:SEW==16 ? 8:SEW==32 ? 16:24)|LMUL_CODE))++handler_errors;
 161:     for(unsigned f=0;f<REPLAY_FIELDS;++f){
 162:     const word *saved=(const void *)((uintptr_t)state->datap+(24+f*FIELD_REGISTER_STRIDE)*state->vlenb);
 174: #endif
 175:     /* Changing completed elements detects an incorrect restart from element0. */
 176:     for(unsigned i=0;i<expected_start && i<REPLAY_ELEMENTS;++i)for(unsigned f=0;f<REPLAY_FIELDS;++f)
 177:         if(active(i))*(word *)field_address(i,f)=store_case ? poison(f*cap+i):(word)(original(field_address(i,f))^0x5b);
 178:     /* Keep the saved PC, vstart and vector register data unchanged. */
 179: #if NEGATIVE_RESTART
 180:     state->vstart=0;
 181: #endif
 223: #if ZERO_STRIDE
 224:         stride=0;
 225:         target=mapping+4096-accessible_fields*sizeof(word);
 226: #else
 227:         stride=(REPLAY_FIELDS+gap)*sizeof(word);
 228: #if NEGATIVE_STRIDE
 229:         target=mapping+4096+boundary*stride-(REPLAY_FIELDS-accessible_fields)*sizeof(word);
 230:         stride=-stride;
 231: #else
 232:         target=mapping+4096-boundary*stride-accessible_fields*sizeof(word);
 233: #endif
 234: #endif
 235: #else
 236:         target=mapping+4096-(boundary*REPLAY_FIELDS+accessible_fields)*sizeof(word);
 237: #endif
 238:         for(unsigned f=0;f<REPLAY_FIELDS;++f)for(unsigned i=0;i<cap;++i)
 239:             input[f*cap+i]=(word)(101+(ZERO_STRIDE ? 0:i*13)+f*29);
 252:         for(unsigned i=0;i<CAPACITY_LIMIT*REPLAY_FIELDS+2;++i)output[i]=(word)0x5b;
 253:         for(unsigned i=0;i<CAPACITY_LIMIT/8;++i)mask[i]=mode==0 ? 255:mode==1 ? 0xaa:mode==2 ? 0x24:0;
 254:         expected_start=REPLAY_ELEMENTS;
 255:         for(unsigned i=boundary;i<REPLAY_ELEMENTS;++i)if(active(i)){expected_start=i;break;}
 256:         expected_address=element_address(expected_start);faults=0;handler_errors=0;
 276:         for(unsigned f=0;f<REPLAY_FIELDS;++f)for(unsigned i=0;i<cap;++i){
 277:             word wanted=store_case ? input[f*cap+i]:i<REPLAY_ELEMENTS && active(i) ? original(field_address(i,f)):(word)0x5b;
 278:             if(output[f*cap+i+1]!=wanted)++errors;
 279:         }
 280:         for(unsigned i=0;i<8192/sizeof(word);++i){
 281:             uintptr_t at=mapping+i*sizeof(word);word wanted=original(at);
 282:             unsigned slot=logical_element(at),j=slot/REPLAY_FIELDS,f=slot%REPLAY_FIELDS;
 283:             if(store_case && j<REPLAY_ELEMENTS){
 284:                 if(active(j))wanted=faults && j<expected_start ? poison(f*cap+j):input[f*cap+j];
 285:             }else if(!store_case && faults && j<expected_start){
 286:                 if(active(j))wanted^=0x5b;
 287:             }
```

## fof_shorten

/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_small_exceptions01/rvv_small_exceptions_e16_scenario0

scenario.S SHA256 `2d75fc09a289e319c2e58fc812748f9030e6ccd2f864753b10d874535d489376`

```text
   1: .text
   2: .global capacity
   3: capacity:
   4: li t0,-1
   5: vsetvli a0,t0,e16,m1,tu,mu
   6: ret
   7: .global load_0
   8: load_0:
   9: vsetvli t0,a3,e16,m1,tu,mu
  10: vle16.v v24,(a1)
  11: vlm.v v0,(a2)
  12: vle16.v v24,(a0),v0.t
  13: csrr a0,vl
  14: csrr t1,vstart
  15: slli t1,t1,32
  16: or a0,a0,t1
  17: vsetvli t0,a3,e16,m1,tu,mu
  18: vse16.v v24,(a1)
  19: ret
  20: .global load_1
  21: load_1:
  22: vsetvli t0,a3,e16,m1,tu,mu
  23: vle16.v v24,(a1)
  24: vlm.v v0,(a2)
  25: vle16ff.v v24,(a0),v0.t
  26: csrr a0,vl
  27: csrr t1,vstart
  28: slli t1,t1,32
  29: or a0,a0,t1
  30: vsetvli t0,a3,e16,m1,tu,mu
  31: vse16.v v24,(a1)
  32: ret
```

scenario.c SHA256 `9883b8afe63695b104ca0915da15f565885b99310803fefcb1baef24e67cc07b`

```text
  35:         for(unsigned i=0;i<130;++i)out[i]=(word)0x5b;
  36:         for(unsigned i=0;i<16;++i)mask[i]=0;
  37:         mask[0]=scenario==0 || scenario==4 ? 255:scenario==1 || scenario==2 ? 15:0;
  38:         unsigned ff=scenario==0 || scenario==2 || scenario==4 || scenario==5;
  39:         unsigned fault=scenario==4;
  48:             for(unsigned i=0;i<8;++i){
  49:                 if(scenario==0 && i>=4)continue;
  50:                 word wanted=scenario<3 && i<4 ? start[i]:(word)0x5b;
  51:                 if(out[i+1]!=wanted)++bad;
  52:             }
  53:             if(out[0]!=(word)0x5b || out[9]!=(word)0x5b)++bad;
```

## fof_masked_suffix

/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_small_exceptions01/rvv_small_exceptions_e16_scenario2

scenario.S SHA256 `2d75fc09a289e319c2e58fc812748f9030e6ccd2f864753b10d874535d489376`

```text
   1: .text
   2: .global capacity
   3: capacity:
   4: li t0,-1
   5: vsetvli a0,t0,e16,m1,tu,mu
   6: ret
   7: .global load_0
   8: load_0:
   9: vsetvli t0,a3,e16,m1,tu,mu
  10: vle16.v v24,(a1)
  11: vlm.v v0,(a2)
  12: vle16.v v24,(a0),v0.t
  13: csrr a0,vl
  14: csrr t1,vstart
  15: slli t1,t1,32
  16: or a0,a0,t1
  17: vsetvli t0,a3,e16,m1,tu,mu
  18: vse16.v v24,(a1)
  19: ret
  20: .global load_1
  21: load_1:
  22: vsetvli t0,a3,e16,m1,tu,mu
  23: vle16.v v24,(a1)
  24: vlm.v v0,(a2)
  25: vle16ff.v v24,(a0),v0.t
  26: csrr a0,vl
  27: csrr t1,vstart
  28: slli t1,t1,32
  29: or a0,a0,t1
  30: vsetvli t0,a3,e16,m1,tu,mu
  31: vse16.v v24,(a1)
  32: ret
```

scenario.c SHA256 `683457c8b49cf416525e86ad25e37dcfc45bd9acb869a5b61f4d39a2156a184e`

```text
  35:         for(unsigned i=0;i<130;++i)out[i]=(word)0x5b;
  36:         for(unsigned i=0;i<16;++i)mask[i]=0;
  37:         mask[0]=scenario==0 || scenario==4 ? 255:scenario==1 || scenario==2 ? 15:0;
  38:         unsigned ff=scenario==0 || scenario==2 || scenario==4 || scenario==5;
  39:         unsigned fault=scenario==4;
  48:             for(unsigned i=0;i<8;++i){
  49:                 if(scenario==0 && i>=4)continue;
  50:                 word wanted=scenario<3 && i<4 ? start[i]:(word)0x5b;
  51:                 if(out[i+1]!=wanted)++bad;
  52:             }
  53:             if(out[0]!=(word)0x5b || out[9]!=(word)0x5b)++bad;
```

