#include "tremor_core.h"

#include <math.h>
#include <stdlib.h>

#define TE_DEFAULT_DT (1.0 / 60.0)

typedef struct {
    int initialized;
    double prev_raw;
    double prev_filtered;
} lowpass;

static double lowpass_filter(lowpass *lp, double value, double alpha) {
    double filtered;
    if (lp->initialized) {
        filtered = alpha * value + (1.0 - alpha) * lp->prev_filtered;
    } else {
        filtered = value;
        lp->initialized = 1;
    }
    lp->prev_raw = value;
    lp->prev_filtered = filtered;
    return filtered;
}

static double smoothing_alpha(double cutoff, double dt) {
    if (cutoff <= 0.0) {
        return 1.0;
    }
    double tau = 1.0 / (2.0 * M_PI * cutoff);
    return 1.0 / (1.0 + tau / dt);
}

typedef struct {
    double min_cutoff;
    double beta;
    double d_cutoff;
    lowpass x;
    lowpass dx;
    int has_time;
    double last_time;
} oneeuro;

static double oneeuro_filter(oneeuro *f, double value, double ts) {
    double dt = TE_DEFAULT_DT;
    if (f->has_time && ts > f->last_time) {
        dt = ts - f->last_time;
    }
    f->has_time = 1;
    f->last_time = ts;

    double dvalue = 0.0;
    if (f->x.initialized) {
        dvalue = (value - f->x.prev_raw) / dt;
    }
    double edvalue = lowpass_filter(&f->dx, dvalue, smoothing_alpha(f->d_cutoff, dt));
    double cutoff = f->min_cutoff + f->beta * fabs(edvalue);
    return lowpass_filter(&f->x, value, smoothing_alpha(cutoff, dt));
}

struct te_oneeuro2d {
    oneeuro fx;
    oneeuro fy;
};

static void oneeuro_init(oneeuro *f, double min_cutoff, double beta, double d_cutoff) {
    f->min_cutoff = min_cutoff;
    f->beta = beta;
    f->d_cutoff = d_cutoff;
    f->x.initialized = 0;
    f->x.prev_raw = 0.0;
    f->x.prev_filtered = 0.0;
    f->dx.initialized = 0;
    f->dx.prev_raw = 0.0;
    f->dx.prev_filtered = 0.0;
    f->has_time = 0;
    f->last_time = 0.0;
}

te_oneeuro2d *te_oneeuro2d_new(double min_cutoff, double beta, double d_cutoff) {
    te_oneeuro2d *f = (te_oneeuro2d *)malloc(sizeof(te_oneeuro2d));
    if (!f) {
        return NULL;
    }
    oneeuro_init(&f->fx, min_cutoff, beta, d_cutoff);
    oneeuro_init(&f->fy, min_cutoff, beta, d_cutoff);
    return f;
}

void te_oneeuro2d_update_params(te_oneeuro2d *f, double min_cutoff, double beta,
                                double d_cutoff) {
    if (!f) {
        return;
    }
    f->fx.min_cutoff = min_cutoff;
    f->fx.beta = beta;
    f->fx.d_cutoff = d_cutoff;
    f->fy.min_cutoff = min_cutoff;
    f->fy.beta = beta;
    f->fy.d_cutoff = d_cutoff;
}

void te_oneeuro2d_reset(te_oneeuro2d *f) {
    if (!f) {
        return;
    }
    oneeuro_init(&f->fx, f->fx.min_cutoff, f->fx.beta, f->fx.d_cutoff);
    oneeuro_init(&f->fy, f->fy.min_cutoff, f->fy.beta, f->fy.d_cutoff);
}

void te_oneeuro2d_filter(te_oneeuro2d *f, double x, double y, double ts,
                         double *out_x, double *out_y) {
    if (!f) {
        return;
    }
    double rx = oneeuro_filter(&f->fx, x, ts);
    double ry = oneeuro_filter(&f->fy, y, ts);
    if (out_x) {
        *out_x = rx;
    }
    if (out_y) {
        *out_y = ry;
    }
}

void te_oneeuro2d_free(te_oneeuro2d *f) { free(f); }

struct te_deadzone {
    double radius;
    int has_anchor;
    double ax;
    double ay;
};

te_deadzone *te_deadzone_new(double radius) {
    te_deadzone *d = (te_deadzone *)malloc(sizeof(te_deadzone));
    if (!d) {
        return NULL;
    }
    d->radius = radius;
    d->has_anchor = 0;
    d->ax = 0.0;
    d->ay = 0.0;
    return d;
}

void te_deadzone_set_radius(te_deadzone *d, double radius) {
    if (d) {
        d->radius = radius;
    }
}

void te_deadzone_reset(te_deadzone *d, int has_anchor, double x, double y) {
    if (!d) {
        return;
    }
    d->has_anchor = has_anchor ? 1 : 0;
    d->ax = x;
    d->ay = y;
}

void te_deadzone_apply(te_deadzone *d, double x, double y, double *out_x,
                       double *out_y) {
    if (!d) {
        return;
    }
    if (!d->has_anchor) {
        d->has_anchor = 1;
        d->ax = x;
        d->ay = y;
    } else {
        double dx = x - d->ax;
        double dy = y - d->ay;
        double dist = hypot(dx, dy);
        if (dist > d->radius && dist != 0.0) {
            double k = (dist - d->radius) / dist;
            d->ax = d->ax + dx * k;
            d->ay = d->ay + dy * k;
        }
    }
    if (out_x) {
        *out_x = d->ax;
    }
    if (out_y) {
        *out_y = d->ay;
    }
}

void te_deadzone_free(te_deadzone *d) { free(d); }

struct te_scroll {
    double reversal_ms;
    double reversal_max;
    int last_dir;
    int has_time;
    double last_time;
};

te_scroll *te_scroll_new(double reversal_ms, double reversal_max) {
    te_scroll *s = (te_scroll *)malloc(sizeof(te_scroll));
    if (!s) {
        return NULL;
    }
    s->reversal_ms = reversal_ms;
    s->reversal_max = reversal_max;
    s->last_dir = 0;
    s->has_time = 0;
    s->last_time = 0.0;
    return s;
}

void te_scroll_set_params(te_scroll *s, double reversal_ms, double reversal_max) {
    if (!s) {
        return;
    }
    s->reversal_ms = reversal_ms;
    s->reversal_max = reversal_max;
}

void te_scroll_reset(te_scroll *s) {
    if (!s) {
        return;
    }
    s->last_dir = 0;
    s->has_time = 0;
    s->last_time = 0.0;
}

double te_scroll_filter(te_scroll *s, double delta, double now) {
    if (!s || delta == 0.0) {
        return 0.0;
    }
    int direction = delta > 0.0 ? 1 : -1;
    if (s->last_dir != 0 && direction != s->last_dir && s->has_time &&
        (now - s->last_time) * 1000.0 < s->reversal_ms &&
        fabs(delta) <= s->reversal_max) {
        s->has_time = 1;
        s->last_time = now;
        return 0.0;
    }
    s->last_dir = direction;
    s->has_time = 1;
    s->last_time = now;
    return delta;
}

void te_scroll_free(te_scroll *s) { free(s); }

const char *te_core_version(void) { return "tremor_core 1.0"; }
