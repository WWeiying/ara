/* Host-only template: Python inserts the ACTUAL original/rendered check body. */
#include <fenv.h>
#include <float.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "verification/akv/quantized_kv/fast_hex/hex32.h"

_Static_assert(sizeof(float)==4 && FLT_RADIX==2 && FLT_MANT_DIG==24,
               "Require binary32 host float");
enum { HEADS=6, DIM=128, STRIDE=136, MODE_QBS=2 };
static struct { unsigned char before[64]; float data[HEADS][STRIDE];
                unsigned char after[64]; } output;
static float attention_golden[HEADS*DIM], baseline[HEADS][DIM];
static float mode_previous[3][HEADS][DIM];
static unsigned seen[3];
static const unsigned threeway_quantizations=6;

void _putchar(char character) { (void)putchar((unsigned char)character); }
static uint32_t bits(float value) {
  uint32_t result;
  memcpy(&result,&value,sizeof(result));
  return result;
}
static void put_word(float *destination, uint32_t word) {
  memcpy(destination,&word,sizeof(word));
}

static int verify(unsigned trial, unsigned mode, unsigned errors) {
  const unsigned long elapsed=123,fc=3,vc=5;
  const unsigned calls=mode==0?768:8,dots=mode==2?0:768,commands=mode==2?8:0;
  const unsigned values=mode==0?768:128;
  const unsigned long panels=mode==2?4:0,copied=mode==2?9216:0;
  const int map_status=0,status=0;
  const struct { struct { unsigned selection_reason,completed_groups,executor_status; } native; }
      report={{0,mode==2?1u:0u,0}};
/* INSERT_ACTUAL_CHECK_BODY */
  return 0;
}

static uint32_t state_hash(void) {
  uint32_t result=UINT32_C(2166136261);
  const unsigned char *b=(const unsigned char *)baseline;
  for (size_t i=0;i<sizeof(baseline);++i) result=(result^b[i])*UINT32_C(16777619);
  b=(const unsigned char *)mode_previous;
  for (size_t i=0;i<sizeof(mode_previous);++i) result=(result^b[i])*UINT32_C(16777619);
  for (unsigned i=0;i<3;++i) result=(result^seen[i])*UINT32_C(16777619);
  return result;
}

int main(void) {
  static const uint32_t special[]={
    0,UINT32_C(0x80000000),1,UINT32_C(0x80000001),UINT32_C(0x007fffff),
    UINT32_C(0x807fffff),UINT32_C(0x00800000),UINT32_C(0x80800000),
    UINT32_C(0x3f800000),UINT32_C(0xbf800000),UINT32_C(0x7f7fffff),
    UINT32_C(0xff7fffff),UINT32_C(0x7f800000),UINT32_C(0xff800000),
    UINT32_C(0x7fc00000),UINT32_C(0x7fc12345),UINT32_C(0xffc12345),
    UINT32_C(0x7f800001),UINT32_C(0x7fa12345),UINT32_C(0xff800001)};
  unsigned cases=0;
  uint32_t random=UINT32_C(0x6d2b79f5);
  for (unsigned variant=0;variant<96;++variant) {
    for (unsigned mode=0;mode<3;++mode) {
      for (unsigned repeat=0;repeat<2;++repeat) {
        memset(&output,0xa5,sizeof(output));
        memset(seen,0,sizeof(seen));
        seen[mode]=repeat;
        for (unsigned h=0;h<HEADS;++h) for (unsigned d=0;d<DIM;++d) {
          const uint32_t value=UINT32_C(0x3f000000)+(h*DIM+d)*127;
          put_word(&output.data[h][d],value);
          put_word(&attention_golden[h*DIM+d],value);
          put_word(&baseline[h][d],value);
          for (unsigned m=0;m<3;++m) put_word(&mode_previous[m][h][d],value);
        }
        unsigned expected=0,initial_errors=0;
        if (variant<20 || variant>=32) {
          uint32_t word;
          if (variant<20) word=special[variant];
          else {
            random^=random<<13; random^=random>>17; random^=random<<5;
            word=random;
          }
          put_word(&output.data[0][0],word); put_word(&attention_golden[0],word);
          put_word(&baseline[0][0],word); put_word(&mode_previous[mode][0][0],word);
          expected=(word&UINT32_C(0x7f800000))==UINT32_C(0x7f800000);
        } else switch (variant) {
          case 20: output.data[0][0]=1.0f; expected=1+(mode!=2)+repeat; break;
          case 21: put_word(&baseline[0][0],UINT32_C(0x3f000001)); expected=mode!=2; break;
          case 22: put_word(&mode_previous[mode][0][0],UINT32_C(0x3f000001)); expected=repeat; break;
          case 23: put_word(&output.data[2][DIM],0); expected=1; break;
          case 24: output.before[0]=0; expected=1; break;
          case 25: output.after[63]=0; expected=1; break;
          case 26: put_word(&attention_golden[0],UINT32_C(0x7f800001)); expected=1; break;
          case 27: initial_errors=3; expected=3; break;
          case 28:
            put_word(&output.data[0][0],UINT32_C(0x80000000));
            put_word(&attention_golden[0],0); put_word(&baseline[0][0],0);
            put_word(&mode_previous[mode][0][0],UINT32_C(0x80000000));
            expected=mode!=2; break;
          default: break;
        }
        /* Trial zero must initialize baseline before the bit comparison. */
        const unsigned trial=variant==29?0:mode+1;
        if (variant==29) { baseline[0][0]=2.0f; }
        if (fesetround(FE_TONEAREST) || feclearexcept(FE_ALL_EXCEPT)) return 2;
        if (repeat && feraiseexcept(FE_DIVBYZERO)) return 3;
        printf("CASE variant=%u mode=%u repeat=%u expected_errors=%u\n",variant,mode,repeat,expected);
        const int result=verify(trial,mode,initial_errors);
        const int flags=fetestexcept(FE_ALL_EXCEPT);
        if (result!=(expected!=0)) return 4;
        if (repeat && !(flags&FE_DIVBYZERO)) return 8;
        printf("STATE result=%d flags=%d hash=%08x seen=%u\n",result,flags,state_hash(),seen[mode]);
        if (fwrite(baseline,1,sizeof(baseline),stderr)!=sizeof(baseline) ||
            fwrite(mode_previous,1,sizeof(mode_previous),stderr)!=sizeof(mode_previous) ||
            fwrite(seen,1,sizeof(seen),stderr)!=sizeof(seen)) return 7;
        ++cases;
      }
    }
  }
  /* Check exact emitted payloads, including signaling NaNs, independently. */
  printf("PAYLOADS ");
  for (unsigned i=0;i<sizeof(special)/sizeof(special[0]);++i) {
    float value;
    put_word(&value,special[i]);
    if (bits(value)!=special[i]) return 5;
    fast_hex32(bits(value));
  }
  printf("\nHOST_VERIFY_PASS cases=%u\n",cases);
  return fflush(stdout)==0 && fflush(stderr)==0 && !ferror(stdout) && !ferror(stderr)?0:6;
}
