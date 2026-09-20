/*
 * Keep the measured implementation in llama_q4km_operator and provide a
 * separate target whose data.S can be regenerated for each attention mode.
 */
#include "../llama_q4km_operator/main.c"
