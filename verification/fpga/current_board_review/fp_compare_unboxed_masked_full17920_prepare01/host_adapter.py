"""Adapt immutable mature Host; also execute the literal original C body."""
from prepare import OLD, NAME, replace


def build():
    text = (OLD/'compile01/host.c').read_text()
    text = text.replace('#include <stdint.h>','#include <stdint.h>\n#include <setjmp.h>')
    text = replace(text,'static const char *negative_mode;', '''static const char *negative_mode;
static const char *variant;
static unsigned baseline, missing_nv_done;
static jmp_buf original_exit;
static int original_rc;
extern void original_probe_main(void);
extern void *original_area(unsigned);
long host_original_syscall3(long n,long x,long y,long z) {
    if(n==94){original_rc=(int)x;longjmp(original_exit,1);}
    return replay_write(n,x,y,z);
}''')
    text = replace(text,'unsigned bitvalue, unsigned *flags)', 'unsigned bitvalue, unsigned mode, unsigned *flags)')
    text = replace(text,'if (i < vl) { *flags |= w.flags; return bitvalue == w.bit; }',
        'if (i < vl && (((unsigned[]){255,170,36,0}[mode]>>(i%8))&1)) { *flags |= w.flags; return bitvalue == w.bit; }\n    if (i < vl) return bitvalue == old;')
    text = replace(text,'unsigned sticky, uint32_t value, uint64_t status)',
                   'unsigned mode, unsigned sticky, uint32_t value, uint64_t status)')
    text = text.replace('(value >> (i + 8)) & 1, &flags)', '(value >> (i + 8)) & 1, mode, &flags)')
    text = text.replace('original_errors(op, seed, vl, sticky,','original_errors(op, seed, vl, mode, sticky,')
    text = replace(text,'assert(pa == a && pb == b && pm == mask && pd == output + 1);', '''assert(pa == (baseline?original_area(0):(void *)a));
    assert(pb == (baseline?original_area(1):(void *)b));
    assert(pm == (baseline?original_area(2):(void *)mask));
    assert(pd == (unsigned char *)(baseline?original_area(3):(void *)output)+1);
    const word *aa=pa; word *bb=(word *)pb;
    const unsigned char *mm=pm; unsigned char *oo=(unsigned char *)pd-1;''')
    text = replace(text,'    assert(event_count == 41);','    if(!baseline) {\n    assert(event_count == 41);')
    text = replace(text,'    event_count = 0;','    event_count = 0;\n    }')
    begin,end=text.index('static unsigned long operate('),text.index('#define OP(N)')
    body=text[begin:end]
    for before,after in [('a[i]','aa[i]'),('b[i]','bb[i]'),('b[0]','bb[0]'),('mask[i]','mm[i]'),('output[i]','oo[i]')]:
        body=body.replace(before,after)
    body=replace(body,'value |= (i < vl ? w.bit : (91 >> (i%8)) & 1) << i;\n        if (i < vl) flags |= w.flags;', '''unsigned active=i<vl && ((masks[mode]>>(i%8))&1);
        unsigned chosen=active?w.bit:(91>>(i%8))&1;
        if(variant && !strcmp(variant,"legal_tailones") && vl && i>=vl) chosen=1;
        value |= chosen << i;
        if(active) flags |= w.flags;''')
    body=replace(body,'uint64_t record = oracle_records[(seed*10+op)*7+li];', '''uint64_t record = oracle_records[((seed*10+op)*7+li)*4+mode];
    if(negative_mode && !strcmp(negative_mode,"wrong_record_mode"))
        record=oracle_records[((seed*10+op)*7+li)*4+(mode+1)%4];''')
    body=replace(body,'    memcpy(output+1, &value, 2);', '''    if(variant && !strcmp(variant,"alloff_spurious_NV") && seed==0 && op==0 && vl==8 && mode==3 && sticky==0) status^=UINT64_C(16)<<32;
    if(variant && !strcmp(variant,"active_missing_NV") && !missing_nv_done && (flags&16)) {status^=UINT64_C(16)<<32;missing_nv_done=1;}
    if(variant && !strcmp(variant,"inactive_result") && seed==0 && op==0 && vl==1 && mode==1 && sticky==0) value^=1;
    memcpy(pd, &value, 2);''')
    text=text[:begin]+body+text[end:]
    text=text.replace('fp_compare_unboxed_e16_mf4_full17920',NAME)
    begin=text.index('int main(int argc, char **argv)')
    text=text[:begin]+r'''
int main(int argc,char **argv) {
    uint32_t endian=1;assert(*(unsigned char *)&endian==1 && argc==2);
    if(!strcmp(argv[1],"details")) inject_errors=1;
    else if(!strcmp(argv[1],"positive") || !strcmp(argv[1],"legal_tailones") ||
            !strcmp(argv[1],"alloff_spurious_NV") || !strcmp(argv[1],"active_missing_NV") ||
            !strcmp(argv[1],"inactive_result")) variant=argv[1];
    else negative_mode=argv[1];
    int rc=ENTRY();
    assert(call_number==17920 && lwu_count==17920 && event_count==0);
    if(negative_mode) {fprintf(stderr,"NEGATIVE_NOT_REJECTED\n");return 3;}
    unsigned details=0;
    for(char *s=transcript;(s=strstr(s,"RVV_FP_COMPARE_DETAIL "));++s) ++details;
    if(inject_errors) {
        assert(rc==1 && details==20);
        assert(strstr(transcript,"RVV_FP_COMPARE_FAIL sew=16 cases=17920 errors=21\n"));
    } else if(!strcmp(variant,"alloff_spurious_NV") || !strcmp(variant,"active_missing_NV") || !strcmp(variant,"inactive_result")) {
        assert(rc==1 && details==1);
        assert(strstr(transcript,"cases=17920 errors=1\n"));
        if(!strcmp(variant,"alloff_spurious_NV")) assert(strstr(transcript,"op=0 seed=0 vl=8 mask=3 sticky=0 expected_flags=0 actual_flags=16 errors=1\n"));
    } else assert(rc==0 && details==0);
    char packed_transcript[sizeof(transcript)];strcpy(packed_transcript,transcript);
    baseline=1;call_number=0;transcript_length=0;transcript[0]=0;missing_nv_done=0;
    if(!setjmp(original_exit)) {original_probe_main();assert(!"original exit not intercepted");}
    assert(original_rc==rc && call_number==17920 && !strcmp(packed_transcript,transcript));
    printf("HOST_ORIGINAL_C_EQ_PASS mode=%s calls=17920 lwu=%u comparisons=%lu details=%u\n",argv[1],lwu_count,equivalence_checks,details);
    return 0;
}
'''.replace('ENTRY()',NAME+'_main()')
    return text
