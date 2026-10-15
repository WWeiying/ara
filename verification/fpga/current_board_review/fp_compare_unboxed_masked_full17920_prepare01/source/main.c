extern void replay_text(const char *);
extern int fp_compare_unboxed_masked_e16_mf4_full17920_main(void);
int main(void) {
 unsigned long vb; __asm__ volatile("csrr %0,vlenb":"=r"(vb));
 if(vb!=128){replay_text("BOARD_REPLAY_VLEN_FAIL\n");return 90;}
 replay_text("BOARD_CASE_BEGIN fp_compare_unboxed_masked_e16_mf4_full17920\n");
 if(fp_compare_unboxed_masked_e16_mf4_full17920_main()){replay_text("BOARD_CASE_FAIL fp_compare_unboxed_masked_e16_mf4_full17920\n");return 1;}
 replay_text("BOARD_CASE_PASS fp_compare_unboxed_masked_e16_mf4_full17920\nBOARD_REPLAY_PASS\n");return 0;
}
