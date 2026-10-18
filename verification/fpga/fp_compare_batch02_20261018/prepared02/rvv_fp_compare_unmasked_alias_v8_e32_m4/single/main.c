extern void replay_text(const char*);
extern int rvv_fp_compare_unmasked_alias_v8_e32_m4_single_main(void);
int main(void){unsigned long vb;__asm__ volatile("csrr %0,vlenb":"=r"(vb));if(vb!=128){replay_text("BOARD_REPLAY_VLEN_FAIL\n");return 90;}
replay_text("BOARD_CASE_BEGIN rvv_fp_compare_unmasked_alias_v8_e32_m4_single\n");
if(rvv_fp_compare_unmasked_alias_v8_e32_m4_single_main()){return 1;}
replay_text("BOARD_REPLAY_PASS\n");return 0;}
