extern void replay_text(const char *);
extern int rvv_small_masks_cmp_alias_restart_e64_m2_main(void);
int main(void) { unsigned long vb; __asm__ volatile("csrr %0,vlenb":"=r"(vb));
if(vb!=128){replay_text("BOARD_REPLAY_VLEN_FAIL\n");return 90;}
if(rvv_small_masks_cmp_alias_restart_e64_m2_main()){replay_text("BOARD_CASE_FAIL rvv_small_masks_cmp_alias_restart_e64_m2\n");return 1;}
replay_text("BOARD_CASE_PASS rvv_small_masks_cmp_alias_restart_e64_m2\nBOARD_REPLAY_PASS\n");return 0;}
