#ifndef TREMOR_CORE_H
#define TREMOR_CORE_H

/*
 * tremor_core - portable, dependency-free hot-path math for TremorAssist.
 *
 * This is the per-event kernel: a One Euro Filter, a hold-steady dead-zone,
 * and a scroll-reversal stabilizer. It carries no platform dependencies so the
 * same object file links into the Swift event-tap engine on macOS and into a
 * Python ctypes binding for tests/benchmarks. All state is heap-allocated and
 * referenced by opaque handles; nothing here touches the Python runtime, so it
 * runs on the event-tap thread without taking the GIL.
 */

#ifdef __cplusplus
extern "C" {
#endif

typedef struct te_oneeuro2d te_oneeuro2d;
typedef struct te_deadzone te_deadzone;
typedef struct te_scroll te_scroll;

/* One Euro Filter, 2D (one filter per axis). */
te_oneeuro2d *te_oneeuro2d_new(double min_cutoff, double beta, double d_cutoff);
void te_oneeuro2d_update_params(te_oneeuro2d *f, double min_cutoff, double beta,
                                double d_cutoff);
void te_oneeuro2d_reset(te_oneeuro2d *f);
void te_oneeuro2d_filter(te_oneeuro2d *f, double x, double y, double ts,
                         double *out_x, double *out_y);
void te_oneeuro2d_free(te_oneeuro2d *f);

/* Hold-steady dead-zone. */
te_deadzone *te_deadzone_new(double radius);
void te_deadzone_set_radius(te_deadzone *d, double radius);
/* has_anchor == 0 clears the anchor; otherwise seeds it at (x, y). */
void te_deadzone_reset(te_deadzone *d, int has_anchor, double x, double y);
void te_deadzone_apply(te_deadzone *d, double x, double y, double *out_x,
                       double *out_y);
void te_deadzone_free(te_deadzone *d);

/* Scroll-reversal stabilizer. Returns the delta to emit (0 == swallow). */
te_scroll *te_scroll_new(double reversal_ms, double reversal_max);
void te_scroll_set_params(te_scroll *s, double reversal_ms, double reversal_max);
void te_scroll_reset(te_scroll *s);
double te_scroll_filter(te_scroll *s, double delta, double now);
void te_scroll_free(te_scroll *s);

const char *te_core_version(void);

#ifdef __cplusplus
}
#endif

#endif /* TREMOR_CORE_H */
