/* Experimental ABBA caller only; this does not enable a runtime capability.
 * Link pv.S, sealed pv_prepare/prepare.S, and a separate rotation/pv_rotation.S:
 *   -D__wrap_akv_experimental_pv_f16_pair=resident_pv_rotation_body
 *   -Dresident_pv_rotation_selected=resident_pv_rotation_always
 * Keep --wrap=akv_experimental_pv_f16_pair. Both arms use native_auto;
 * arm 0 always executes strong rotation, arm 1 prepares and executes PV.
 */
int resident_pv_rotation_always = 1;
#include "../rotation/main.c"
