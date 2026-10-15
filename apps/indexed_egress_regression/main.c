#include <stdint.h>
#include "printf.h"
#define ALIGN __attribute__((aligned(128)))
static uint64_t indices[128] ALIGN;
static uint8_t input[1024] ALIGN, output[1024] ALIGN;
static unsigned cases;
static int case_8_8_0(unsigned avl, unsigned masked) {
 unsigned vl; uintptr_t sum;
 asm volatile("vsetvli %0,%1,e8,m1,tu,mu":"=r"(vl):"r"(avl):"memory");
 uint8_t *ix=(uint8_t *)indices;
 uint8_t *src=(uint8_t *)input,*dst=(uint8_t *)output;
 uint8_t expected=0;
 for(unsigned j=0;j<vl;j++) {src[j]=j+1;dst[j]=0;ix[j]=(vl-1-j)*1;}
 for(unsigned j=0;j<vl;j++) if(!masked || !(j&1)) expected+=(uint8_t)(vl-j);
 asm volatile("vid.v v4\nvand.vi v4,v4,1\nvmseq.vi v0,v4,0\nvle8.v v8,(%0)\nvmv.v.i v16,0"::"r"(ix):"memory","v0","v4","v8","v9","v10","v11","v12","v13","v14","v15","v16");
 if(!masked) asm volatile("vluxei8.v v16,(%1),v8\nvsuxei8.v v16,(%2),v8\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 if(masked) asm volatile("vluxei8.v v16,(%1),v8,v0.t\nvsuxei8.v v16,(%2),v8,v0.t\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 asm volatile("fence rw,rw\ncsrr zero,vstart":::"memory");
 if((uint8_t)sum!=expected){printf("FAIL sum sew=8 index=8 ordered=0 vl=%u mask=%u\n",vl,masked);return 1;}
 for(unsigned j=0;j<vl;j++){uint8_t exp=(!masked || !((vl-1-j)&1))?j+1:0;if(dst[j]!=exp){printf("FAIL store sew=8 index=8 ordered=0 vl=%u mask=%u j=%u\n",vl,masked,j);return 2;}}
 cases++;return 0;
}
static int case_8_8_1(unsigned avl, unsigned masked) {
 unsigned vl; uintptr_t sum;
 asm volatile("vsetvli %0,%1,e8,m1,tu,mu":"=r"(vl):"r"(avl):"memory");
 uint8_t *ix=(uint8_t *)indices;
 uint8_t *src=(uint8_t *)input,*dst=(uint8_t *)output;
 uint8_t expected=0;
 for(unsigned j=0;j<vl;j++) {src[j]=j+1;dst[j]=0;ix[j]=(vl-1-j)*1;}
 for(unsigned j=0;j<vl;j++) if(!masked || !(j&1)) expected+=(uint8_t)(vl-j);
 asm volatile("vid.v v4\nvand.vi v4,v4,1\nvmseq.vi v0,v4,0\nvle8.v v8,(%0)\nvmv.v.i v16,0"::"r"(ix):"memory","v0","v4","v8","v9","v10","v11","v12","v13","v14","v15","v16");
 if(!masked) asm volatile("vloxei8.v v16,(%1),v8\nvsoxei8.v v16,(%2),v8\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 if(masked) asm volatile("vloxei8.v v16,(%1),v8,v0.t\nvsoxei8.v v16,(%2),v8,v0.t\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 asm volatile("fence rw,rw\ncsrr zero,vstart":::"memory");
 if((uint8_t)sum!=expected){printf("FAIL sum sew=8 index=8 ordered=1 vl=%u mask=%u\n",vl,masked);return 1;}
 for(unsigned j=0;j<vl;j++){uint8_t exp=(!masked || !((vl-1-j)&1))?j+1:0;if(dst[j]!=exp){printf("FAIL store sew=8 index=8 ordered=1 vl=%u mask=%u j=%u\n",vl,masked,j);return 2;}}
 cases++;return 0;
}
static int case_8_16_0(unsigned avl, unsigned masked) {
 unsigned vl; uintptr_t sum;
 asm volatile("vsetvli %0,%1,e8,m1,tu,mu":"=r"(vl):"r"(avl):"memory");
 uint16_t *ix=(uint16_t *)indices;
 uint8_t *src=(uint8_t *)input,*dst=(uint8_t *)output;
 uint8_t expected=0;
 for(unsigned j=0;j<vl;j++) {src[j]=j+1;dst[j]=0;ix[j]=(vl-1-j)*1;}
 for(unsigned j=0;j<vl;j++) if(!masked || !(j&1)) expected+=(uint8_t)(vl-j);
 asm volatile("vid.v v4\nvand.vi v4,v4,1\nvmseq.vi v0,v4,0\nvle16.v v8,(%0)\nvmv.v.i v16,0"::"r"(ix):"memory","v0","v4","v8","v9","v10","v11","v12","v13","v14","v15","v16");
 if(!masked) asm volatile("vluxei16.v v16,(%1),v8\nvsuxei16.v v16,(%2),v8\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 if(masked) asm volatile("vluxei16.v v16,(%1),v8,v0.t\nvsuxei16.v v16,(%2),v8,v0.t\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 asm volatile("fence rw,rw\ncsrr zero,vstart":::"memory");
 if((uint8_t)sum!=expected){printf("FAIL sum sew=8 index=16 ordered=0 vl=%u mask=%u\n",vl,masked);return 1;}
 for(unsigned j=0;j<vl;j++){uint8_t exp=(!masked || !((vl-1-j)&1))?j+1:0;if(dst[j]!=exp){printf("FAIL store sew=8 index=16 ordered=0 vl=%u mask=%u j=%u\n",vl,masked,j);return 2;}}
 cases++;return 0;
}
static int case_8_16_1(unsigned avl, unsigned masked) {
 unsigned vl; uintptr_t sum;
 asm volatile("vsetvli %0,%1,e8,m1,tu,mu":"=r"(vl):"r"(avl):"memory");
 uint16_t *ix=(uint16_t *)indices;
 uint8_t *src=(uint8_t *)input,*dst=(uint8_t *)output;
 uint8_t expected=0;
 for(unsigned j=0;j<vl;j++) {src[j]=j+1;dst[j]=0;ix[j]=(vl-1-j)*1;}
 for(unsigned j=0;j<vl;j++) if(!masked || !(j&1)) expected+=(uint8_t)(vl-j);
 asm volatile("vid.v v4\nvand.vi v4,v4,1\nvmseq.vi v0,v4,0\nvle16.v v8,(%0)\nvmv.v.i v16,0"::"r"(ix):"memory","v0","v4","v8","v9","v10","v11","v12","v13","v14","v15","v16");
 if(!masked) asm volatile("vloxei16.v v16,(%1),v8\nvsoxei16.v v16,(%2),v8\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 if(masked) asm volatile("vloxei16.v v16,(%1),v8,v0.t\nvsoxei16.v v16,(%2),v8,v0.t\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 asm volatile("fence rw,rw\ncsrr zero,vstart":::"memory");
 if((uint8_t)sum!=expected){printf("FAIL sum sew=8 index=16 ordered=1 vl=%u mask=%u\n",vl,masked);return 1;}
 for(unsigned j=0;j<vl;j++){uint8_t exp=(!masked || !((vl-1-j)&1))?j+1:0;if(dst[j]!=exp){printf("FAIL store sew=8 index=16 ordered=1 vl=%u mask=%u j=%u\n",vl,masked,j);return 2;}}
 cases++;return 0;
}
static int case_8_32_0(unsigned avl, unsigned masked) {
 unsigned vl; uintptr_t sum;
 asm volatile("vsetvli %0,%1,e8,m1,tu,mu":"=r"(vl):"r"(avl):"memory");
 uint32_t *ix=(uint32_t *)indices;
 uint8_t *src=(uint8_t *)input,*dst=(uint8_t *)output;
 uint8_t expected=0;
 for(unsigned j=0;j<vl;j++) {src[j]=j+1;dst[j]=0;ix[j]=(vl-1-j)*1;}
 for(unsigned j=0;j<vl;j++) if(!masked || !(j&1)) expected+=(uint8_t)(vl-j);
 asm volatile("vid.v v4\nvand.vi v4,v4,1\nvmseq.vi v0,v4,0\nvle32.v v8,(%0)\nvmv.v.i v16,0"::"r"(ix):"memory","v0","v4","v8","v9","v10","v11","v12","v13","v14","v15","v16");
 if(!masked) asm volatile("vluxei32.v v16,(%1),v8\nvsuxei32.v v16,(%2),v8\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 if(masked) asm volatile("vluxei32.v v16,(%1),v8,v0.t\nvsuxei32.v v16,(%2),v8,v0.t\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 asm volatile("fence rw,rw\ncsrr zero,vstart":::"memory");
 if((uint8_t)sum!=expected){printf("FAIL sum sew=8 index=32 ordered=0 vl=%u mask=%u\n",vl,masked);return 1;}
 for(unsigned j=0;j<vl;j++){uint8_t exp=(!masked || !((vl-1-j)&1))?j+1:0;if(dst[j]!=exp){printf("FAIL store sew=8 index=32 ordered=0 vl=%u mask=%u j=%u\n",vl,masked,j);return 2;}}
 cases++;return 0;
}
static int case_8_32_1(unsigned avl, unsigned masked) {
 unsigned vl; uintptr_t sum;
 asm volatile("vsetvli %0,%1,e8,m1,tu,mu":"=r"(vl):"r"(avl):"memory");
 uint32_t *ix=(uint32_t *)indices;
 uint8_t *src=(uint8_t *)input,*dst=(uint8_t *)output;
 uint8_t expected=0;
 for(unsigned j=0;j<vl;j++) {src[j]=j+1;dst[j]=0;ix[j]=(vl-1-j)*1;}
 for(unsigned j=0;j<vl;j++) if(!masked || !(j&1)) expected+=(uint8_t)(vl-j);
 asm volatile("vid.v v4\nvand.vi v4,v4,1\nvmseq.vi v0,v4,0\nvle32.v v8,(%0)\nvmv.v.i v16,0"::"r"(ix):"memory","v0","v4","v8","v9","v10","v11","v12","v13","v14","v15","v16");
 if(!masked) asm volatile("vloxei32.v v16,(%1),v8\nvsoxei32.v v16,(%2),v8\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 if(masked) asm volatile("vloxei32.v v16,(%1),v8,v0.t\nvsoxei32.v v16,(%2),v8,v0.t\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 asm volatile("fence rw,rw\ncsrr zero,vstart":::"memory");
 if((uint8_t)sum!=expected){printf("FAIL sum sew=8 index=32 ordered=1 vl=%u mask=%u\n",vl,masked);return 1;}
 for(unsigned j=0;j<vl;j++){uint8_t exp=(!masked || !((vl-1-j)&1))?j+1:0;if(dst[j]!=exp){printf("FAIL store sew=8 index=32 ordered=1 vl=%u mask=%u j=%u\n",vl,masked,j);return 2;}}
 cases++;return 0;
}
static int case_8_64_0(unsigned avl, unsigned masked) {
 unsigned vl; uintptr_t sum;
 asm volatile("vsetvli %0,%1,e8,m1,tu,mu":"=r"(vl):"r"(avl):"memory");
 uint64_t *ix=(uint64_t *)indices;
 uint8_t *src=(uint8_t *)input,*dst=(uint8_t *)output;
 uint8_t expected=0;
 for(unsigned j=0;j<vl;j++) {src[j]=j+1;dst[j]=0;ix[j]=(vl-1-j)*1;}
 for(unsigned j=0;j<vl;j++) if(!masked || !(j&1)) expected+=(uint8_t)(vl-j);
 asm volatile("vid.v v4\nvand.vi v4,v4,1\nvmseq.vi v0,v4,0\nvle64.v v8,(%0)\nvmv.v.i v16,0"::"r"(ix):"memory","v0","v4","v8","v9","v10","v11","v12","v13","v14","v15","v16");
 if(!masked) asm volatile("vluxei64.v v16,(%1),v8\nvsuxei64.v v16,(%2),v8\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 if(masked) asm volatile("vluxei64.v v16,(%1),v8,v0.t\nvsuxei64.v v16,(%2),v8,v0.t\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 asm volatile("fence rw,rw\ncsrr zero,vstart":::"memory");
 if((uint8_t)sum!=expected){printf("FAIL sum sew=8 index=64 ordered=0 vl=%u mask=%u\n",vl,masked);return 1;}
 for(unsigned j=0;j<vl;j++){uint8_t exp=(!masked || !((vl-1-j)&1))?j+1:0;if(dst[j]!=exp){printf("FAIL store sew=8 index=64 ordered=0 vl=%u mask=%u j=%u\n",vl,masked,j);return 2;}}
 cases++;return 0;
}
static int case_8_64_1(unsigned avl, unsigned masked) {
 unsigned vl; uintptr_t sum;
 asm volatile("vsetvli %0,%1,e8,m1,tu,mu":"=r"(vl):"r"(avl):"memory");
 uint64_t *ix=(uint64_t *)indices;
 uint8_t *src=(uint8_t *)input,*dst=(uint8_t *)output;
 uint8_t expected=0;
 for(unsigned j=0;j<vl;j++) {src[j]=j+1;dst[j]=0;ix[j]=(vl-1-j)*1;}
 for(unsigned j=0;j<vl;j++) if(!masked || !(j&1)) expected+=(uint8_t)(vl-j);
 asm volatile("vid.v v4\nvand.vi v4,v4,1\nvmseq.vi v0,v4,0\nvle64.v v8,(%0)\nvmv.v.i v16,0"::"r"(ix):"memory","v0","v4","v8","v9","v10","v11","v12","v13","v14","v15","v16");
 if(!masked) asm volatile("vloxei64.v v16,(%1),v8\nvsoxei64.v v16,(%2),v8\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 if(masked) asm volatile("vloxei64.v v16,(%1),v8,v0.t\nvsoxei64.v v16,(%2),v8,v0.t\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 asm volatile("fence rw,rw\ncsrr zero,vstart":::"memory");
 if((uint8_t)sum!=expected){printf("FAIL sum sew=8 index=64 ordered=1 vl=%u mask=%u\n",vl,masked);return 1;}
 for(unsigned j=0;j<vl;j++){uint8_t exp=(!masked || !((vl-1-j)&1))?j+1:0;if(dst[j]!=exp){printf("FAIL store sew=8 index=64 ordered=1 vl=%u mask=%u j=%u\n",vl,masked,j);return 2;}}
 cases++;return 0;
}
static int case_16_8_0(unsigned avl, unsigned masked) {
 unsigned vl; uintptr_t sum;
 asm volatile("vsetvli %0,%1,e16,m1,tu,mu":"=r"(vl):"r"(avl):"memory");
 uint8_t *ix=(uint8_t *)indices;
 uint16_t *src=(uint16_t *)input,*dst=(uint16_t *)output;
 uint16_t expected=0;
 for(unsigned j=0;j<vl;j++) {src[j]=j+1;dst[j]=0;ix[j]=(vl-1-j)*2;}
 for(unsigned j=0;j<vl;j++) if(!masked || !(j&1)) expected+=(uint16_t)(vl-j);
 asm volatile("vid.v v4\nvand.vi v4,v4,1\nvmseq.vi v0,v4,0\nvle8.v v8,(%0)\nvmv.v.i v16,0"::"r"(ix):"memory","v0","v4","v8","v9","v10","v11","v12","v13","v14","v15","v16");
 if(!masked) asm volatile("vluxei8.v v16,(%1),v8\nvsuxei8.v v16,(%2),v8\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 if(masked) asm volatile("vluxei8.v v16,(%1),v8,v0.t\nvsuxei8.v v16,(%2),v8,v0.t\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 asm volatile("fence rw,rw\ncsrr zero,vstart":::"memory");
 if((uint16_t)sum!=expected){printf("FAIL sum sew=16 index=8 ordered=0 vl=%u mask=%u\n",vl,masked);return 1;}
 for(unsigned j=0;j<vl;j++){uint16_t exp=(!masked || !((vl-1-j)&1))?j+1:0;if(dst[j]!=exp){printf("FAIL store sew=16 index=8 ordered=0 vl=%u mask=%u j=%u\n",vl,masked,j);return 2;}}
 cases++;return 0;
}
static int case_16_8_1(unsigned avl, unsigned masked) {
 unsigned vl; uintptr_t sum;
 asm volatile("vsetvli %0,%1,e16,m1,tu,mu":"=r"(vl):"r"(avl):"memory");
 uint8_t *ix=(uint8_t *)indices;
 uint16_t *src=(uint16_t *)input,*dst=(uint16_t *)output;
 uint16_t expected=0;
 for(unsigned j=0;j<vl;j++) {src[j]=j+1;dst[j]=0;ix[j]=(vl-1-j)*2;}
 for(unsigned j=0;j<vl;j++) if(!masked || !(j&1)) expected+=(uint16_t)(vl-j);
 asm volatile("vid.v v4\nvand.vi v4,v4,1\nvmseq.vi v0,v4,0\nvle8.v v8,(%0)\nvmv.v.i v16,0"::"r"(ix):"memory","v0","v4","v8","v9","v10","v11","v12","v13","v14","v15","v16");
 if(!masked) asm volatile("vloxei8.v v16,(%1),v8\nvsoxei8.v v16,(%2),v8\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 if(masked) asm volatile("vloxei8.v v16,(%1),v8,v0.t\nvsoxei8.v v16,(%2),v8,v0.t\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 asm volatile("fence rw,rw\ncsrr zero,vstart":::"memory");
 if((uint16_t)sum!=expected){printf("FAIL sum sew=16 index=8 ordered=1 vl=%u mask=%u\n",vl,masked);return 1;}
 for(unsigned j=0;j<vl;j++){uint16_t exp=(!masked || !((vl-1-j)&1))?j+1:0;if(dst[j]!=exp){printf("FAIL store sew=16 index=8 ordered=1 vl=%u mask=%u j=%u\n",vl,masked,j);return 2;}}
 cases++;return 0;
}
static int case_16_16_0(unsigned avl, unsigned masked) {
 unsigned vl; uintptr_t sum;
 asm volatile("vsetvli %0,%1,e16,m1,tu,mu":"=r"(vl):"r"(avl):"memory");
 uint16_t *ix=(uint16_t *)indices;
 uint16_t *src=(uint16_t *)input,*dst=(uint16_t *)output;
 uint16_t expected=0;
 for(unsigned j=0;j<vl;j++) {src[j]=j+1;dst[j]=0;ix[j]=(vl-1-j)*2;}
 for(unsigned j=0;j<vl;j++) if(!masked || !(j&1)) expected+=(uint16_t)(vl-j);
 asm volatile("vid.v v4\nvand.vi v4,v4,1\nvmseq.vi v0,v4,0\nvle16.v v8,(%0)\nvmv.v.i v16,0"::"r"(ix):"memory","v0","v4","v8","v9","v10","v11","v12","v13","v14","v15","v16");
 if(!masked) asm volatile("vluxei16.v v16,(%1),v8\nvsuxei16.v v16,(%2),v8\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 if(masked) asm volatile("vluxei16.v v16,(%1),v8,v0.t\nvsuxei16.v v16,(%2),v8,v0.t\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 asm volatile("fence rw,rw\ncsrr zero,vstart":::"memory");
 if((uint16_t)sum!=expected){printf("FAIL sum sew=16 index=16 ordered=0 vl=%u mask=%u\n",vl,masked);return 1;}
 for(unsigned j=0;j<vl;j++){uint16_t exp=(!masked || !((vl-1-j)&1))?j+1:0;if(dst[j]!=exp){printf("FAIL store sew=16 index=16 ordered=0 vl=%u mask=%u j=%u\n",vl,masked,j);return 2;}}
 cases++;return 0;
}
static int case_16_16_1(unsigned avl, unsigned masked) {
 unsigned vl; uintptr_t sum;
 asm volatile("vsetvli %0,%1,e16,m1,tu,mu":"=r"(vl):"r"(avl):"memory");
 uint16_t *ix=(uint16_t *)indices;
 uint16_t *src=(uint16_t *)input,*dst=(uint16_t *)output;
 uint16_t expected=0;
 for(unsigned j=0;j<vl;j++) {src[j]=j+1;dst[j]=0;ix[j]=(vl-1-j)*2;}
 for(unsigned j=0;j<vl;j++) if(!masked || !(j&1)) expected+=(uint16_t)(vl-j);
 asm volatile("vid.v v4\nvand.vi v4,v4,1\nvmseq.vi v0,v4,0\nvle16.v v8,(%0)\nvmv.v.i v16,0"::"r"(ix):"memory","v0","v4","v8","v9","v10","v11","v12","v13","v14","v15","v16");
 if(!masked) asm volatile("vloxei16.v v16,(%1),v8\nvsoxei16.v v16,(%2),v8\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 if(masked) asm volatile("vloxei16.v v16,(%1),v8,v0.t\nvsoxei16.v v16,(%2),v8,v0.t\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 asm volatile("fence rw,rw\ncsrr zero,vstart":::"memory");
 if((uint16_t)sum!=expected){printf("FAIL sum sew=16 index=16 ordered=1 vl=%u mask=%u\n",vl,masked);return 1;}
 for(unsigned j=0;j<vl;j++){uint16_t exp=(!masked || !((vl-1-j)&1))?j+1:0;if(dst[j]!=exp){printf("FAIL store sew=16 index=16 ordered=1 vl=%u mask=%u j=%u\n",vl,masked,j);return 2;}}
 cases++;return 0;
}
static int case_16_32_0(unsigned avl, unsigned masked) {
 unsigned vl; uintptr_t sum;
 asm volatile("vsetvli %0,%1,e16,m1,tu,mu":"=r"(vl):"r"(avl):"memory");
 uint32_t *ix=(uint32_t *)indices;
 uint16_t *src=(uint16_t *)input,*dst=(uint16_t *)output;
 uint16_t expected=0;
 for(unsigned j=0;j<vl;j++) {src[j]=j+1;dst[j]=0;ix[j]=(vl-1-j)*2;}
 for(unsigned j=0;j<vl;j++) if(!masked || !(j&1)) expected+=(uint16_t)(vl-j);
 asm volatile("vid.v v4\nvand.vi v4,v4,1\nvmseq.vi v0,v4,0\nvle32.v v8,(%0)\nvmv.v.i v16,0"::"r"(ix):"memory","v0","v4","v8","v9","v10","v11","v12","v13","v14","v15","v16");
 if(!masked) asm volatile("vluxei32.v v16,(%1),v8\nvsuxei32.v v16,(%2),v8\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 if(masked) asm volatile("vluxei32.v v16,(%1),v8,v0.t\nvsuxei32.v v16,(%2),v8,v0.t\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 asm volatile("fence rw,rw\ncsrr zero,vstart":::"memory");
 if((uint16_t)sum!=expected){printf("FAIL sum sew=16 index=32 ordered=0 vl=%u mask=%u\n",vl,masked);return 1;}
 for(unsigned j=0;j<vl;j++){uint16_t exp=(!masked || !((vl-1-j)&1))?j+1:0;if(dst[j]!=exp){printf("FAIL store sew=16 index=32 ordered=0 vl=%u mask=%u j=%u\n",vl,masked,j);return 2;}}
 cases++;return 0;
}
static int case_16_32_1(unsigned avl, unsigned masked) {
 unsigned vl; uintptr_t sum;
 asm volatile("vsetvli %0,%1,e16,m1,tu,mu":"=r"(vl):"r"(avl):"memory");
 uint32_t *ix=(uint32_t *)indices;
 uint16_t *src=(uint16_t *)input,*dst=(uint16_t *)output;
 uint16_t expected=0;
 for(unsigned j=0;j<vl;j++) {src[j]=j+1;dst[j]=0;ix[j]=(vl-1-j)*2;}
 for(unsigned j=0;j<vl;j++) if(!masked || !(j&1)) expected+=(uint16_t)(vl-j);
 asm volatile("vid.v v4\nvand.vi v4,v4,1\nvmseq.vi v0,v4,0\nvle32.v v8,(%0)\nvmv.v.i v16,0"::"r"(ix):"memory","v0","v4","v8","v9","v10","v11","v12","v13","v14","v15","v16");
 if(!masked) asm volatile("vloxei32.v v16,(%1),v8\nvsoxei32.v v16,(%2),v8\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 if(masked) asm volatile("vloxei32.v v16,(%1),v8,v0.t\nvsoxei32.v v16,(%2),v8,v0.t\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 asm volatile("fence rw,rw\ncsrr zero,vstart":::"memory");
 if((uint16_t)sum!=expected){printf("FAIL sum sew=16 index=32 ordered=1 vl=%u mask=%u\n",vl,masked);return 1;}
 for(unsigned j=0;j<vl;j++){uint16_t exp=(!masked || !((vl-1-j)&1))?j+1:0;if(dst[j]!=exp){printf("FAIL store sew=16 index=32 ordered=1 vl=%u mask=%u j=%u\n",vl,masked,j);return 2;}}
 cases++;return 0;
}
static int case_16_64_0(unsigned avl, unsigned masked) {
 unsigned vl; uintptr_t sum;
 asm volatile("vsetvli %0,%1,e16,m1,tu,mu":"=r"(vl):"r"(avl):"memory");
 uint64_t *ix=(uint64_t *)indices;
 uint16_t *src=(uint16_t *)input,*dst=(uint16_t *)output;
 uint16_t expected=0;
 for(unsigned j=0;j<vl;j++) {src[j]=j+1;dst[j]=0;ix[j]=(vl-1-j)*2;}
 for(unsigned j=0;j<vl;j++) if(!masked || !(j&1)) expected+=(uint16_t)(vl-j);
 asm volatile("vid.v v4\nvand.vi v4,v4,1\nvmseq.vi v0,v4,0\nvle64.v v8,(%0)\nvmv.v.i v16,0"::"r"(ix):"memory","v0","v4","v8","v9","v10","v11","v12","v13","v14","v15","v16");
 if(!masked) asm volatile("vluxei64.v v16,(%1),v8\nvsuxei64.v v16,(%2),v8\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 if(masked) asm volatile("vluxei64.v v16,(%1),v8,v0.t\nvsuxei64.v v16,(%2),v8,v0.t\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 asm volatile("fence rw,rw\ncsrr zero,vstart":::"memory");
 if((uint16_t)sum!=expected){printf("FAIL sum sew=16 index=64 ordered=0 vl=%u mask=%u\n",vl,masked);return 1;}
 for(unsigned j=0;j<vl;j++){uint16_t exp=(!masked || !((vl-1-j)&1))?j+1:0;if(dst[j]!=exp){printf("FAIL store sew=16 index=64 ordered=0 vl=%u mask=%u j=%u\n",vl,masked,j);return 2;}}
 cases++;return 0;
}
static int case_16_64_1(unsigned avl, unsigned masked) {
 unsigned vl; uintptr_t sum;
 asm volatile("vsetvli %0,%1,e16,m1,tu,mu":"=r"(vl):"r"(avl):"memory");
 uint64_t *ix=(uint64_t *)indices;
 uint16_t *src=(uint16_t *)input,*dst=(uint16_t *)output;
 uint16_t expected=0;
 for(unsigned j=0;j<vl;j++) {src[j]=j+1;dst[j]=0;ix[j]=(vl-1-j)*2;}
 for(unsigned j=0;j<vl;j++) if(!masked || !(j&1)) expected+=(uint16_t)(vl-j);
 asm volatile("vid.v v4\nvand.vi v4,v4,1\nvmseq.vi v0,v4,0\nvle64.v v8,(%0)\nvmv.v.i v16,0"::"r"(ix):"memory","v0","v4","v8","v9","v10","v11","v12","v13","v14","v15","v16");
 if(!masked) asm volatile("vloxei64.v v16,(%1),v8\nvsoxei64.v v16,(%2),v8\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 if(masked) asm volatile("vloxei64.v v16,(%1),v8,v0.t\nvsoxei64.v v16,(%2),v8,v0.t\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 asm volatile("fence rw,rw\ncsrr zero,vstart":::"memory");
 if((uint16_t)sum!=expected){printf("FAIL sum sew=16 index=64 ordered=1 vl=%u mask=%u\n",vl,masked);return 1;}
 for(unsigned j=0;j<vl;j++){uint16_t exp=(!masked || !((vl-1-j)&1))?j+1:0;if(dst[j]!=exp){printf("FAIL store sew=16 index=64 ordered=1 vl=%u mask=%u j=%u\n",vl,masked,j);return 2;}}
 cases++;return 0;
}
static int case_32_8_0(unsigned avl, unsigned masked) {
 unsigned vl; uintptr_t sum;
 asm volatile("vsetvli %0,%1,e32,m1,tu,mu":"=r"(vl):"r"(avl):"memory");
 uint8_t *ix=(uint8_t *)indices;
 uint32_t *src=(uint32_t *)input,*dst=(uint32_t *)output;
 uint32_t expected=0;
 for(unsigned j=0;j<vl;j++) {src[j]=j+1;dst[j]=0;ix[j]=(vl-1-j)*4;}
 for(unsigned j=0;j<vl;j++) if(!masked || !(j&1)) expected+=(uint32_t)(vl-j);
 asm volatile("vid.v v4\nvand.vi v4,v4,1\nvmseq.vi v0,v4,0\nvle8.v v8,(%0)\nvmv.v.i v16,0"::"r"(ix):"memory","v0","v4","v8","v9","v10","v11","v12","v13","v14","v15","v16");
 if(!masked) asm volatile("vluxei8.v v16,(%1),v8\nvsuxei8.v v16,(%2),v8\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 if(masked) asm volatile("vluxei8.v v16,(%1),v8,v0.t\nvsuxei8.v v16,(%2),v8,v0.t\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 asm volatile("fence rw,rw\ncsrr zero,vstart":::"memory");
 if((uint32_t)sum!=expected){printf("FAIL sum sew=32 index=8 ordered=0 vl=%u mask=%u\n",vl,masked);return 1;}
 for(unsigned j=0;j<vl;j++){uint32_t exp=(!masked || !((vl-1-j)&1))?j+1:0;if(dst[j]!=exp){printf("FAIL store sew=32 index=8 ordered=0 vl=%u mask=%u j=%u\n",vl,masked,j);return 2;}}
 cases++;return 0;
}
static int case_32_8_1(unsigned avl, unsigned masked) {
 unsigned vl; uintptr_t sum;
 asm volatile("vsetvli %0,%1,e32,m1,tu,mu":"=r"(vl):"r"(avl):"memory");
 uint8_t *ix=(uint8_t *)indices;
 uint32_t *src=(uint32_t *)input,*dst=(uint32_t *)output;
 uint32_t expected=0;
 for(unsigned j=0;j<vl;j++) {src[j]=j+1;dst[j]=0;ix[j]=(vl-1-j)*4;}
 for(unsigned j=0;j<vl;j++) if(!masked || !(j&1)) expected+=(uint32_t)(vl-j);
 asm volatile("vid.v v4\nvand.vi v4,v4,1\nvmseq.vi v0,v4,0\nvle8.v v8,(%0)\nvmv.v.i v16,0"::"r"(ix):"memory","v0","v4","v8","v9","v10","v11","v12","v13","v14","v15","v16");
 if(!masked) asm volatile("vloxei8.v v16,(%1),v8\nvsoxei8.v v16,(%2),v8\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 if(masked) asm volatile("vloxei8.v v16,(%1),v8,v0.t\nvsoxei8.v v16,(%2),v8,v0.t\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 asm volatile("fence rw,rw\ncsrr zero,vstart":::"memory");
 if((uint32_t)sum!=expected){printf("FAIL sum sew=32 index=8 ordered=1 vl=%u mask=%u\n",vl,masked);return 1;}
 for(unsigned j=0;j<vl;j++){uint32_t exp=(!masked || !((vl-1-j)&1))?j+1:0;if(dst[j]!=exp){printf("FAIL store sew=32 index=8 ordered=1 vl=%u mask=%u j=%u\n",vl,masked,j);return 2;}}
 cases++;return 0;
}
static int case_32_16_0(unsigned avl, unsigned masked) {
 unsigned vl; uintptr_t sum;
 asm volatile("vsetvli %0,%1,e32,m1,tu,mu":"=r"(vl):"r"(avl):"memory");
 uint16_t *ix=(uint16_t *)indices;
 uint32_t *src=(uint32_t *)input,*dst=(uint32_t *)output;
 uint32_t expected=0;
 for(unsigned j=0;j<vl;j++) {src[j]=j+1;dst[j]=0;ix[j]=(vl-1-j)*4;}
 for(unsigned j=0;j<vl;j++) if(!masked || !(j&1)) expected+=(uint32_t)(vl-j);
 asm volatile("vid.v v4\nvand.vi v4,v4,1\nvmseq.vi v0,v4,0\nvle16.v v8,(%0)\nvmv.v.i v16,0"::"r"(ix):"memory","v0","v4","v8","v9","v10","v11","v12","v13","v14","v15","v16");
 if(!masked) asm volatile("vluxei16.v v16,(%1),v8\nvsuxei16.v v16,(%2),v8\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 if(masked) asm volatile("vluxei16.v v16,(%1),v8,v0.t\nvsuxei16.v v16,(%2),v8,v0.t\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 asm volatile("fence rw,rw\ncsrr zero,vstart":::"memory");
 if((uint32_t)sum!=expected){printf("FAIL sum sew=32 index=16 ordered=0 vl=%u mask=%u\n",vl,masked);return 1;}
 for(unsigned j=0;j<vl;j++){uint32_t exp=(!masked || !((vl-1-j)&1))?j+1:0;if(dst[j]!=exp){printf("FAIL store sew=32 index=16 ordered=0 vl=%u mask=%u j=%u\n",vl,masked,j);return 2;}}
 cases++;return 0;
}
static int case_32_16_1(unsigned avl, unsigned masked) {
 unsigned vl; uintptr_t sum;
 asm volatile("vsetvli %0,%1,e32,m1,tu,mu":"=r"(vl):"r"(avl):"memory");
 uint16_t *ix=(uint16_t *)indices;
 uint32_t *src=(uint32_t *)input,*dst=(uint32_t *)output;
 uint32_t expected=0;
 for(unsigned j=0;j<vl;j++) {src[j]=j+1;dst[j]=0;ix[j]=(vl-1-j)*4;}
 for(unsigned j=0;j<vl;j++) if(!masked || !(j&1)) expected+=(uint32_t)(vl-j);
 asm volatile("vid.v v4\nvand.vi v4,v4,1\nvmseq.vi v0,v4,0\nvle16.v v8,(%0)\nvmv.v.i v16,0"::"r"(ix):"memory","v0","v4","v8","v9","v10","v11","v12","v13","v14","v15","v16");
 if(!masked) asm volatile("vloxei16.v v16,(%1),v8\nvsoxei16.v v16,(%2),v8\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 if(masked) asm volatile("vloxei16.v v16,(%1),v8,v0.t\nvsoxei16.v v16,(%2),v8,v0.t\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 asm volatile("fence rw,rw\ncsrr zero,vstart":::"memory");
 if((uint32_t)sum!=expected){printf("FAIL sum sew=32 index=16 ordered=1 vl=%u mask=%u\n",vl,masked);return 1;}
 for(unsigned j=0;j<vl;j++){uint32_t exp=(!masked || !((vl-1-j)&1))?j+1:0;if(dst[j]!=exp){printf("FAIL store sew=32 index=16 ordered=1 vl=%u mask=%u j=%u\n",vl,masked,j);return 2;}}
 cases++;return 0;
}
static int case_32_32_0(unsigned avl, unsigned masked) {
 unsigned vl; uintptr_t sum;
 asm volatile("vsetvli %0,%1,e32,m1,tu,mu":"=r"(vl):"r"(avl):"memory");
 uint32_t *ix=(uint32_t *)indices;
 uint32_t *src=(uint32_t *)input,*dst=(uint32_t *)output;
 uint32_t expected=0;
 for(unsigned j=0;j<vl;j++) {src[j]=j+1;dst[j]=0;ix[j]=(vl-1-j)*4;}
 for(unsigned j=0;j<vl;j++) if(!masked || !(j&1)) expected+=(uint32_t)(vl-j);
 asm volatile("vid.v v4\nvand.vi v4,v4,1\nvmseq.vi v0,v4,0\nvle32.v v8,(%0)\nvmv.v.i v16,0"::"r"(ix):"memory","v0","v4","v8","v9","v10","v11","v12","v13","v14","v15","v16");
 if(!masked) asm volatile("vluxei32.v v16,(%1),v8\nvsuxei32.v v16,(%2),v8\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 if(masked) asm volatile("vluxei32.v v16,(%1),v8,v0.t\nvsuxei32.v v16,(%2),v8,v0.t\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 asm volatile("fence rw,rw\ncsrr zero,vstart":::"memory");
 if((uint32_t)sum!=expected){printf("FAIL sum sew=32 index=32 ordered=0 vl=%u mask=%u\n",vl,masked);return 1;}
 for(unsigned j=0;j<vl;j++){uint32_t exp=(!masked || !((vl-1-j)&1))?j+1:0;if(dst[j]!=exp){printf("FAIL store sew=32 index=32 ordered=0 vl=%u mask=%u j=%u\n",vl,masked,j);return 2;}}
 cases++;return 0;
}
static int case_32_32_1(unsigned avl, unsigned masked) {
 unsigned vl; uintptr_t sum;
 asm volatile("vsetvli %0,%1,e32,m1,tu,mu":"=r"(vl):"r"(avl):"memory");
 uint32_t *ix=(uint32_t *)indices;
 uint32_t *src=(uint32_t *)input,*dst=(uint32_t *)output;
 uint32_t expected=0;
 for(unsigned j=0;j<vl;j++) {src[j]=j+1;dst[j]=0;ix[j]=(vl-1-j)*4;}
 for(unsigned j=0;j<vl;j++) if(!masked || !(j&1)) expected+=(uint32_t)(vl-j);
 asm volatile("vid.v v4\nvand.vi v4,v4,1\nvmseq.vi v0,v4,0\nvle32.v v8,(%0)\nvmv.v.i v16,0"::"r"(ix):"memory","v0","v4","v8","v9","v10","v11","v12","v13","v14","v15","v16");
 if(!masked) asm volatile("vloxei32.v v16,(%1),v8\nvsoxei32.v v16,(%2),v8\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 if(masked) asm volatile("vloxei32.v v16,(%1),v8,v0.t\nvsoxei32.v v16,(%2),v8,v0.t\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 asm volatile("fence rw,rw\ncsrr zero,vstart":::"memory");
 if((uint32_t)sum!=expected){printf("FAIL sum sew=32 index=32 ordered=1 vl=%u mask=%u\n",vl,masked);return 1;}
 for(unsigned j=0;j<vl;j++){uint32_t exp=(!masked || !((vl-1-j)&1))?j+1:0;if(dst[j]!=exp){printf("FAIL store sew=32 index=32 ordered=1 vl=%u mask=%u j=%u\n",vl,masked,j);return 2;}}
 cases++;return 0;
}
static int case_32_64_0(unsigned avl, unsigned masked) {
 unsigned vl; uintptr_t sum;
 asm volatile("vsetvli %0,%1,e32,m1,tu,mu":"=r"(vl):"r"(avl):"memory");
 uint64_t *ix=(uint64_t *)indices;
 uint32_t *src=(uint32_t *)input,*dst=(uint32_t *)output;
 uint32_t expected=0;
 for(unsigned j=0;j<vl;j++) {src[j]=j+1;dst[j]=0;ix[j]=(vl-1-j)*4;}
 for(unsigned j=0;j<vl;j++) if(!masked || !(j&1)) expected+=(uint32_t)(vl-j);
 asm volatile("vid.v v4\nvand.vi v4,v4,1\nvmseq.vi v0,v4,0\nvle64.v v8,(%0)\nvmv.v.i v16,0"::"r"(ix):"memory","v0","v4","v8","v9","v10","v11","v12","v13","v14","v15","v16");
 if(!masked) asm volatile("vluxei64.v v16,(%1),v8\nvsuxei64.v v16,(%2),v8\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 if(masked) asm volatile("vluxei64.v v16,(%1),v8,v0.t\nvsuxei64.v v16,(%2),v8,v0.t\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 asm volatile("fence rw,rw\ncsrr zero,vstart":::"memory");
 if((uint32_t)sum!=expected){printf("FAIL sum sew=32 index=64 ordered=0 vl=%u mask=%u\n",vl,masked);return 1;}
 for(unsigned j=0;j<vl;j++){uint32_t exp=(!masked || !((vl-1-j)&1))?j+1:0;if(dst[j]!=exp){printf("FAIL store sew=32 index=64 ordered=0 vl=%u mask=%u j=%u\n",vl,masked,j);return 2;}}
 cases++;return 0;
}
static int case_32_64_1(unsigned avl, unsigned masked) {
 unsigned vl; uintptr_t sum;
 asm volatile("vsetvli %0,%1,e32,m1,tu,mu":"=r"(vl):"r"(avl):"memory");
 uint64_t *ix=(uint64_t *)indices;
 uint32_t *src=(uint32_t *)input,*dst=(uint32_t *)output;
 uint32_t expected=0;
 for(unsigned j=0;j<vl;j++) {src[j]=j+1;dst[j]=0;ix[j]=(vl-1-j)*4;}
 for(unsigned j=0;j<vl;j++) if(!masked || !(j&1)) expected+=(uint32_t)(vl-j);
 asm volatile("vid.v v4\nvand.vi v4,v4,1\nvmseq.vi v0,v4,0\nvle64.v v8,(%0)\nvmv.v.i v16,0"::"r"(ix):"memory","v0","v4","v8","v9","v10","v11","v12","v13","v14","v15","v16");
 if(!masked) asm volatile("vloxei64.v v16,(%1),v8\nvsoxei64.v v16,(%2),v8\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 if(masked) asm volatile("vloxei64.v v16,(%1),v8,v0.t\nvsoxei64.v v16,(%2),v8,v0.t\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 asm volatile("fence rw,rw\ncsrr zero,vstart":::"memory");
 if((uint32_t)sum!=expected){printf("FAIL sum sew=32 index=64 ordered=1 vl=%u mask=%u\n",vl,masked);return 1;}
 for(unsigned j=0;j<vl;j++){uint32_t exp=(!masked || !((vl-1-j)&1))?j+1:0;if(dst[j]!=exp){printf("FAIL store sew=32 index=64 ordered=1 vl=%u mask=%u j=%u\n",vl,masked,j);return 2;}}
 cases++;return 0;
}
static int case_64_8_0(unsigned avl, unsigned masked) {
 unsigned vl; uintptr_t sum;
 asm volatile("vsetvli %0,%1,e64,m1,tu,mu":"=r"(vl):"r"(avl):"memory");
 uint8_t *ix=(uint8_t *)indices;
 uint64_t *src=(uint64_t *)input,*dst=(uint64_t *)output;
 uint64_t expected=0;
 for(unsigned j=0;j<vl;j++) {src[j]=j+1;dst[j]=0;ix[j]=(vl-1-j)*8;}
 for(unsigned j=0;j<vl;j++) if(!masked || !(j&1)) expected+=(uint64_t)(vl-j);
 asm volatile("vid.v v4\nvand.vi v4,v4,1\nvmseq.vi v0,v4,0\nvle8.v v8,(%0)\nvmv.v.i v16,0"::"r"(ix):"memory","v0","v4","v8","v9","v10","v11","v12","v13","v14","v15","v16");
 if(!masked) asm volatile("vluxei8.v v16,(%1),v8\nvsuxei8.v v16,(%2),v8\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 if(masked) asm volatile("vluxei8.v v16,(%1),v8,v0.t\nvsuxei8.v v16,(%2),v8,v0.t\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 asm volatile("fence rw,rw\ncsrr zero,vstart":::"memory");
 if((uint64_t)sum!=expected){printf("FAIL sum sew=64 index=8 ordered=0 vl=%u mask=%u\n",vl,masked);return 1;}
 for(unsigned j=0;j<vl;j++){uint64_t exp=(!masked || !((vl-1-j)&1))?j+1:0;if(dst[j]!=exp){printf("FAIL store sew=64 index=8 ordered=0 vl=%u mask=%u j=%u\n",vl,masked,j);return 2;}}
 cases++;return 0;
}
static int case_64_8_1(unsigned avl, unsigned masked) {
 unsigned vl; uintptr_t sum;
 asm volatile("vsetvli %0,%1,e64,m1,tu,mu":"=r"(vl):"r"(avl):"memory");
 uint8_t *ix=(uint8_t *)indices;
 uint64_t *src=(uint64_t *)input,*dst=(uint64_t *)output;
 uint64_t expected=0;
 for(unsigned j=0;j<vl;j++) {src[j]=j+1;dst[j]=0;ix[j]=(vl-1-j)*8;}
 for(unsigned j=0;j<vl;j++) if(!masked || !(j&1)) expected+=(uint64_t)(vl-j);
 asm volatile("vid.v v4\nvand.vi v4,v4,1\nvmseq.vi v0,v4,0\nvle8.v v8,(%0)\nvmv.v.i v16,0"::"r"(ix):"memory","v0","v4","v8","v9","v10","v11","v12","v13","v14","v15","v16");
 if(!masked) asm volatile("vloxei8.v v16,(%1),v8\nvsoxei8.v v16,(%2),v8\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 if(masked) asm volatile("vloxei8.v v16,(%1),v8,v0.t\nvsoxei8.v v16,(%2),v8,v0.t\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 asm volatile("fence rw,rw\ncsrr zero,vstart":::"memory");
 if((uint64_t)sum!=expected){printf("FAIL sum sew=64 index=8 ordered=1 vl=%u mask=%u\n",vl,masked);return 1;}
 for(unsigned j=0;j<vl;j++){uint64_t exp=(!masked || !((vl-1-j)&1))?j+1:0;if(dst[j]!=exp){printf("FAIL store sew=64 index=8 ordered=1 vl=%u mask=%u j=%u\n",vl,masked,j);return 2;}}
 cases++;return 0;
}
static int case_64_16_0(unsigned avl, unsigned masked) {
 unsigned vl; uintptr_t sum;
 asm volatile("vsetvli %0,%1,e64,m1,tu,mu":"=r"(vl):"r"(avl):"memory");
 uint16_t *ix=(uint16_t *)indices;
 uint64_t *src=(uint64_t *)input,*dst=(uint64_t *)output;
 uint64_t expected=0;
 for(unsigned j=0;j<vl;j++) {src[j]=j+1;dst[j]=0;ix[j]=(vl-1-j)*8;}
 for(unsigned j=0;j<vl;j++) if(!masked || !(j&1)) expected+=(uint64_t)(vl-j);
 asm volatile("vid.v v4\nvand.vi v4,v4,1\nvmseq.vi v0,v4,0\nvle16.v v8,(%0)\nvmv.v.i v16,0"::"r"(ix):"memory","v0","v4","v8","v9","v10","v11","v12","v13","v14","v15","v16");
 if(!masked) asm volatile("vluxei16.v v16,(%1),v8\nvsuxei16.v v16,(%2),v8\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 if(masked) asm volatile("vluxei16.v v16,(%1),v8,v0.t\nvsuxei16.v v16,(%2),v8,v0.t\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 asm volatile("fence rw,rw\ncsrr zero,vstart":::"memory");
 if((uint64_t)sum!=expected){printf("FAIL sum sew=64 index=16 ordered=0 vl=%u mask=%u\n",vl,masked);return 1;}
 for(unsigned j=0;j<vl;j++){uint64_t exp=(!masked || !((vl-1-j)&1))?j+1:0;if(dst[j]!=exp){printf("FAIL store sew=64 index=16 ordered=0 vl=%u mask=%u j=%u\n",vl,masked,j);return 2;}}
 cases++;return 0;
}
static int case_64_16_1(unsigned avl, unsigned masked) {
 unsigned vl; uintptr_t sum;
 asm volatile("vsetvli %0,%1,e64,m1,tu,mu":"=r"(vl):"r"(avl):"memory");
 uint16_t *ix=(uint16_t *)indices;
 uint64_t *src=(uint64_t *)input,*dst=(uint64_t *)output;
 uint64_t expected=0;
 for(unsigned j=0;j<vl;j++) {src[j]=j+1;dst[j]=0;ix[j]=(vl-1-j)*8;}
 for(unsigned j=0;j<vl;j++) if(!masked || !(j&1)) expected+=(uint64_t)(vl-j);
 asm volatile("vid.v v4\nvand.vi v4,v4,1\nvmseq.vi v0,v4,0\nvle16.v v8,(%0)\nvmv.v.i v16,0"::"r"(ix):"memory","v0","v4","v8","v9","v10","v11","v12","v13","v14","v15","v16");
 if(!masked) asm volatile("vloxei16.v v16,(%1),v8\nvsoxei16.v v16,(%2),v8\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 if(masked) asm volatile("vloxei16.v v16,(%1),v8,v0.t\nvsoxei16.v v16,(%2),v8,v0.t\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 asm volatile("fence rw,rw\ncsrr zero,vstart":::"memory");
 if((uint64_t)sum!=expected){printf("FAIL sum sew=64 index=16 ordered=1 vl=%u mask=%u\n",vl,masked);return 1;}
 for(unsigned j=0;j<vl;j++){uint64_t exp=(!masked || !((vl-1-j)&1))?j+1:0;if(dst[j]!=exp){printf("FAIL store sew=64 index=16 ordered=1 vl=%u mask=%u j=%u\n",vl,masked,j);return 2;}}
 cases++;return 0;
}
static int case_64_32_0(unsigned avl, unsigned masked) {
 unsigned vl; uintptr_t sum;
 asm volatile("vsetvli %0,%1,e64,m1,tu,mu":"=r"(vl):"r"(avl):"memory");
 uint32_t *ix=(uint32_t *)indices;
 uint64_t *src=(uint64_t *)input,*dst=(uint64_t *)output;
 uint64_t expected=0;
 for(unsigned j=0;j<vl;j++) {src[j]=j+1;dst[j]=0;ix[j]=(vl-1-j)*8;}
 for(unsigned j=0;j<vl;j++) if(!masked || !(j&1)) expected+=(uint64_t)(vl-j);
 asm volatile("vid.v v4\nvand.vi v4,v4,1\nvmseq.vi v0,v4,0\nvle32.v v8,(%0)\nvmv.v.i v16,0"::"r"(ix):"memory","v0","v4","v8","v9","v10","v11","v12","v13","v14","v15","v16");
 if(!masked) asm volatile("vluxei32.v v16,(%1),v8\nvsuxei32.v v16,(%2),v8\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 if(masked) asm volatile("vluxei32.v v16,(%1),v8,v0.t\nvsuxei32.v v16,(%2),v8,v0.t\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 asm volatile("fence rw,rw\ncsrr zero,vstart":::"memory");
 if((uint64_t)sum!=expected){printf("FAIL sum sew=64 index=32 ordered=0 vl=%u mask=%u\n",vl,masked);return 1;}
 for(unsigned j=0;j<vl;j++){uint64_t exp=(!masked || !((vl-1-j)&1))?j+1:0;if(dst[j]!=exp){printf("FAIL store sew=64 index=32 ordered=0 vl=%u mask=%u j=%u\n",vl,masked,j);return 2;}}
 cases++;return 0;
}
static int case_64_32_1(unsigned avl, unsigned masked) {
 unsigned vl; uintptr_t sum;
 asm volatile("vsetvli %0,%1,e64,m1,tu,mu":"=r"(vl):"r"(avl):"memory");
 uint32_t *ix=(uint32_t *)indices;
 uint64_t *src=(uint64_t *)input,*dst=(uint64_t *)output;
 uint64_t expected=0;
 for(unsigned j=0;j<vl;j++) {src[j]=j+1;dst[j]=0;ix[j]=(vl-1-j)*8;}
 for(unsigned j=0;j<vl;j++) if(!masked || !(j&1)) expected+=(uint64_t)(vl-j);
 asm volatile("vid.v v4\nvand.vi v4,v4,1\nvmseq.vi v0,v4,0\nvle32.v v8,(%0)\nvmv.v.i v16,0"::"r"(ix):"memory","v0","v4","v8","v9","v10","v11","v12","v13","v14","v15","v16");
 if(!masked) asm volatile("vloxei32.v v16,(%1),v8\nvsoxei32.v v16,(%2),v8\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 if(masked) asm volatile("vloxei32.v v16,(%1),v8,v0.t\nvsoxei32.v v16,(%2),v8,v0.t\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 asm volatile("fence rw,rw\ncsrr zero,vstart":::"memory");
 if((uint64_t)sum!=expected){printf("FAIL sum sew=64 index=32 ordered=1 vl=%u mask=%u\n",vl,masked);return 1;}
 for(unsigned j=0;j<vl;j++){uint64_t exp=(!masked || !((vl-1-j)&1))?j+1:0;if(dst[j]!=exp){printf("FAIL store sew=64 index=32 ordered=1 vl=%u mask=%u j=%u\n",vl,masked,j);return 2;}}
 cases++;return 0;
}
static int case_64_64_0(unsigned avl, unsigned masked) {
 unsigned vl; uintptr_t sum;
 asm volatile("vsetvli %0,%1,e64,m1,tu,mu":"=r"(vl):"r"(avl):"memory");
 uint64_t *ix=(uint64_t *)indices;
 uint64_t *src=(uint64_t *)input,*dst=(uint64_t *)output;
 uint64_t expected=0;
 for(unsigned j=0;j<vl;j++) {src[j]=j+1;dst[j]=0;ix[j]=(vl-1-j)*8;}
 for(unsigned j=0;j<vl;j++) if(!masked || !(j&1)) expected+=(uint64_t)(vl-j);
 asm volatile("vid.v v4\nvand.vi v4,v4,1\nvmseq.vi v0,v4,0\nvle64.v v8,(%0)\nvmv.v.i v16,0"::"r"(ix):"memory","v0","v4","v8","v9","v10","v11","v12","v13","v14","v15","v16");
 if(!masked) asm volatile("vluxei64.v v16,(%1),v8\nvsuxei64.v v16,(%2),v8\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 if(masked) asm volatile("vluxei64.v v16,(%1),v8,v0.t\nvsuxei64.v v16,(%2),v8,v0.t\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 asm volatile("fence rw,rw\ncsrr zero,vstart":::"memory");
 if((uint64_t)sum!=expected){printf("FAIL sum sew=64 index=64 ordered=0 vl=%u mask=%u\n",vl,masked);return 1;}
 for(unsigned j=0;j<vl;j++){uint64_t exp=(!masked || !((vl-1-j)&1))?j+1:0;if(dst[j]!=exp){printf("FAIL store sew=64 index=64 ordered=0 vl=%u mask=%u j=%u\n",vl,masked,j);return 2;}}
 cases++;return 0;
}
static int case_64_64_1(unsigned avl, unsigned masked) {
 unsigned vl; uintptr_t sum;
 asm volatile("vsetvli %0,%1,e64,m1,tu,mu":"=r"(vl):"r"(avl):"memory");
 uint64_t *ix=(uint64_t *)indices;
 uint64_t *src=(uint64_t *)input,*dst=(uint64_t *)output;
 uint64_t expected=0;
 for(unsigned j=0;j<vl;j++) {src[j]=j+1;dst[j]=0;ix[j]=(vl-1-j)*8;}
 for(unsigned j=0;j<vl;j++) if(!masked || !(j&1)) expected+=(uint64_t)(vl-j);
 asm volatile("vid.v v4\nvand.vi v4,v4,1\nvmseq.vi v0,v4,0\nvle64.v v8,(%0)\nvmv.v.i v16,0"::"r"(ix):"memory","v0","v4","v8","v9","v10","v11","v12","v13","v14","v15","v16");
 if(!masked) asm volatile("vloxei64.v v16,(%1),v8\nvsoxei64.v v16,(%2),v8\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 if(masked) asm volatile("vloxei64.v v16,(%1),v8,v0.t\nvsoxei64.v v16,(%2),v8,v0.t\nvmv.s.x v2,zero\nvredsum.vs v3,v16,v2\nvmv.x.s %0,v3":"=r"(sum):"r"(src),"r"(dst):"memory","v2","v3","v16");
 asm volatile("fence rw,rw\ncsrr zero,vstart":::"memory");
 if((uint64_t)sum!=expected){printf("FAIL sum sew=64 index=64 ordered=1 vl=%u mask=%u\n",vl,masked);return 1;}
 for(unsigned j=0;j<vl;j++){uint64_t exp=(!masked || !((vl-1-j)&1))?j+1:0;if(dst[j]!=exp){printf("FAIL store sew=64 index=64 ordered=1 vl=%u mask=%u j=%u\n",vl,masked,j);return 2;}}
 cases++;return 0;
}
int main(void){ const unsigned sizes[]={1,3,5,7,9,16,17,31};
for(unsigned k=0;k<8;k++) for(unsigned m=0;m<2;m++) if(case_8_8_0(sizes[k],m))return 1;
for(unsigned k=0;k<8;k++) for(unsigned m=0;m<2;m++) if(case_8_8_1(sizes[k],m))return 1;
for(unsigned k=0;k<8;k++) for(unsigned m=0;m<2;m++) if(case_8_16_0(sizes[k],m))return 1;
for(unsigned k=0;k<8;k++) for(unsigned m=0;m<2;m++) if(case_8_16_1(sizes[k],m))return 1;
for(unsigned k=0;k<8;k++) for(unsigned m=0;m<2;m++) if(case_8_32_0(sizes[k],m))return 1;
for(unsigned k=0;k<8;k++) for(unsigned m=0;m<2;m++) if(case_8_32_1(sizes[k],m))return 1;
for(unsigned k=0;k<8;k++) for(unsigned m=0;m<2;m++) if(case_8_64_0(sizes[k],m))return 1;
for(unsigned k=0;k<8;k++) for(unsigned m=0;m<2;m++) if(case_8_64_1(sizes[k],m))return 1;
for(unsigned k=0;k<8;k++) for(unsigned m=0;m<2;m++) if(case_16_8_0(sizes[k],m))return 1;
for(unsigned k=0;k<8;k++) for(unsigned m=0;m<2;m++) if(case_16_8_1(sizes[k],m))return 1;
for(unsigned k=0;k<8;k++) for(unsigned m=0;m<2;m++) if(case_16_16_0(sizes[k],m))return 1;
for(unsigned k=0;k<8;k++) for(unsigned m=0;m<2;m++) if(case_16_16_1(sizes[k],m))return 1;
for(unsigned k=0;k<8;k++) for(unsigned m=0;m<2;m++) if(case_16_32_0(sizes[k],m))return 1;
for(unsigned k=0;k<8;k++) for(unsigned m=0;m<2;m++) if(case_16_32_1(sizes[k],m))return 1;
for(unsigned k=0;k<8;k++) for(unsigned m=0;m<2;m++) if(case_16_64_0(sizes[k],m))return 1;
for(unsigned k=0;k<8;k++) for(unsigned m=0;m<2;m++) if(case_16_64_1(sizes[k],m))return 1;
for(unsigned k=0;k<8;k++) for(unsigned m=0;m<2;m++) if(case_32_8_0(sizes[k],m))return 1;
for(unsigned k=0;k<8;k++) for(unsigned m=0;m<2;m++) if(case_32_8_1(sizes[k],m))return 1;
for(unsigned k=0;k<8;k++) for(unsigned m=0;m<2;m++) if(case_32_16_0(sizes[k],m))return 1;
for(unsigned k=0;k<8;k++) for(unsigned m=0;m<2;m++) if(case_32_16_1(sizes[k],m))return 1;
for(unsigned k=0;k<8;k++) for(unsigned m=0;m<2;m++) if(case_32_32_0(sizes[k],m))return 1;
for(unsigned k=0;k<8;k++) for(unsigned m=0;m<2;m++) if(case_32_32_1(sizes[k],m))return 1;
for(unsigned k=0;k<8;k++) for(unsigned m=0;m<2;m++) if(case_32_64_0(sizes[k],m))return 1;
for(unsigned k=0;k<8;k++) for(unsigned m=0;m<2;m++) if(case_32_64_1(sizes[k],m))return 1;
for(unsigned k=0;k<8;k++) for(unsigned m=0;m<2;m++) if(case_64_8_0(sizes[k],m))return 1;
for(unsigned k=0;k<8;k++) for(unsigned m=0;m<2;m++) if(case_64_8_1(sizes[k],m))return 1;
for(unsigned k=0;k<8;k++) for(unsigned m=0;m<2;m++) if(case_64_16_0(sizes[k],m))return 1;
for(unsigned k=0;k<8;k++) for(unsigned m=0;m<2;m++) if(case_64_16_1(sizes[k],m))return 1;
for(unsigned k=0;k<8;k++) for(unsigned m=0;m<2;m++) if(case_64_32_0(sizes[k],m))return 1;
for(unsigned k=0;k<8;k++) for(unsigned m=0;m<2;m++) if(case_64_32_1(sizes[k],m))return 1;
for(unsigned k=0;k<8;k++) for(unsigned m=0;m<2;m++) if(case_64_64_0(sizes[k],m))return 1;
for(unsigned k=0;k<8;k++) for(unsigned m=0;m<2;m++) if(case_64_64_1(sizes[k],m))return 1;
printf("PASS indexed load/store + reduction cases=%u\n",cases);return 0;}
