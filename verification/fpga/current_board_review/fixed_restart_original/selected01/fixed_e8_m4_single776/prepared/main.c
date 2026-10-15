extern int fixed_main(void);
extern void replay_text(const char *);
extern volatile unsigned long replay_case;
int main(void) {
    unsigned long vlenb;
    __asm__ volatile("csrr %0,vlenb":"=r"(vlenb));
    if(vlenb!=128) { replay_text("BOARD_REPLAY_VLEN_FAIL\n"); return 90; }
    replay_case=1;
    replay_text("BOARD_CASE_BEGIN fixed_e8_m4_single776\n");
    int result=fixed_main();
    if(result) { replay_text("BOARD_CASE_FAIL fixed_e8_m4_single776\n"); return result; }
    replay_text("FIXED_SELECTION_PASS fixed_e8_m4_single776 first=776 last=776 calls=1\nBOARD_CASE_PASS fixed_e8_m4_single776\nBOARD_REPLAY_PASS\n");
    return 0;
}
