extern int fixed_full_main(void);
extern void replay_text(const char *);
extern volatile unsigned long replay_case;
int main(void) {
    replay_case=1;
    replay_text("BOARD_CASE_BEGIN fixed_e8_m4_full10752\n");
    int result=fixed_full_main();
    if(result) {
        replay_text("BOARD_CASE_FAIL fixed_e8_m4_full10752\n");
        return result;
    }
    replay_text("BOARD_CASE_PASS fixed_e8_m4_full10752\nBOARD_REPLAY_PASS\n");
    return 0;
}
