// Separate callback pass: preserve original arithmetic, isolate active suffix flags.
#include "qbs_ref.h"
#include <fenv.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void need(int ok) { if (!ok) { fputs("LOCAL_FLAGS_FAIL\n",stderr); exit(1); } }
struct flag_scope { unsigned n, prefix, completed, flags; };
static unsigned host_flags(void) {
  int f = fetestexcept(FE_ALL_EXCEPT);
  return ((f&FE_INEXACT)?1u:0u)|((f&FE_UNDERFLOW)?2u:0u)|((f&FE_OVERFLOW)?4u:0u)|
         ((f&FE_DIVBYZERO)?8u:0u)|((f&FE_INVALID)?16u:0u);
}
static void block_boundary(const qbs_trace_event_t *e, void *opaque) {
  struct flag_scope *s = opaque;
  if (e->kind != QBS_TRACE_BLOCK || e->output != s->n-1 || e->context != 7) return;
  need(e->k_block == s->completed);
  unsigned flags = host_flags();
  if (e->k_block >= s->prefix) s->flags |= flags;
  need(feclearexcept(FE_ALL_EXCEPT) == 0);
  s->completed++;
}
int main(int argc, char **argv) {
  need(argc == 3);
  unsigned char *memory = calloc(0x250000,1); need(memory != NULL);
  uint64_t wb[5]={0}, ab[5]={0}; unsigned depths[5]={0}; uint32_t gold[4][128]={{0}};
  FILE *f = fopen(argv[1],"r"); need(f != NULL);
  char token[32]; need(fscanf(f,"%31s",token)==1 && !strcmp(token,"S2SEED1"));
  unsigned outputs=0, regions=0;
  while (1) {
    need(fscanf(f,"%31s",token)==1);
    if (!strcmp(token,"END")) break;
    if (!strcmp(token,"B")) {
      uint64_t address; unsigned strobe; char hex[33];
      need(fscanf(f,"%" SCNx64 " %x %32s",&address,&strobe,hex)==3 &&
           address+16<=0x250000 && address%16==0 && strobe==0xffff && strlen(hex)==32);
      for(unsigned b=0;b<16;b++) {
        char byte[3]={hex[30-2*b],hex[31-2*b],0}; char *end;
        memory[address+b]=(unsigned char)strtoul(byte,&end,16); need(*end==0);
      }
    } else if (!strcmp(token,"O")) {
      unsigned model,index; uint32_t bits;
      need(fscanf(f,"%u %u %" SCNx32,&model,&index,&bits)==3 && model==outputs/128 && index==outputs%128);
      gold[model][index]=bits; outputs++;
    } else if (!strcmp(token,"F")) {
      unsigned model,flags; need(fscanf(f,"%u %u",&model,&flags)==2 && model<4);
    } else if (!strcmp(token,"R")) {
      unsigned index; need(fscanf(f,"%u",&index)==1 && index==regions && index<5);
      need(fscanf(f,"%" SCNx64 " %" SCNx64 " %u",&wb[index],&ab[index],&depths[index])==3);
      regions++;
    } else need(0);
  }
  need(outputs==512 && regions==5 && !fclose(f));
  FILE *out=fopen(argv[2],"wx"); need(out != NULL); fputs("S2LOCAL1\n",out);
  const unsigned prefixes[4]={0,1,3,5};
  for(unsigned model=0;model<4;model++) {
    unsigned blocks=1+2*model, n=model==3?5:16, base=0;
    unsigned char w[16*7*144], a[8*7*292];
    for(unsigned region=0;region<=model;region++) {
      unsigned kb=depths[region];
      for(unsigned r=0;r<16;r++) for(unsigned k=0;k<kb;k++)
        memcpy(w+((r/4*blocks+base+k)*4+r%4)*144,
               memory+wb[region]+((r/4*kb+k)*4+r%4)*144,144);
      memcpy(a+base*8*292,memory+ab[region],kb*8*292); base+=kb;
    }
    need(base==blocks);
    qbs_descriptor_fields_t fields={.descriptor_version=QBS_DESCRIPTOR_VERSION,
      .weight_profile=QBS_WEIGHT_PROFILE_Q4_K,.activation_profile=QBS_ACTIVATION_PROFILE_Q8_K,
      .weight_layout=QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
      .activation_layout=QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED,.n=n,.k_blocks=blocks};
    qbs_descriptor_t d={.header=qbs_pack_descriptor_header(&fields),.weight_base=0x100000};
    float result[8*32]={0}; qbs_ref_result_t info;
    struct flag_scope scope={.n=n,.prefix=prefixes[model]};
    need(qbs_ref_execute(&d,8,8,1024,0x200000,w,16*blocks*144,a,8*blocks*292,
         result,8*32,block_boundary,&scope,&info)==QBS_REF_OK);
    need(scope.completed==blocks && scope.flags==(model?1u:0u));
    for(unsigned r=0;r<8;r++) for(unsigned c=0;c<n;c++) {
      uint32_t bits; memcpy(&bits,&result[r*32+c],4); need(bits==gold[model][r*16+c]);
    }
    fprintf(out,"%u %u %u\n",model,n,scope.flags);
  }
  fputs("END\n",out); need(!fclose(out)); free(memory);
  puts("LOCAL_FLAGS_PASS models=4 suffix_cuts=0,1,3,5 active_n=16,16,16,5 callback_outputs_bitexact=1");
  return 0;
}
