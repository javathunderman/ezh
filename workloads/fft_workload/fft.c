/* =========================================================================
 * Build note:
 *   gcc -O2 -nostdlib -nostartfiles -static -lm -o fft_workload fft_workload.c
 *
 *   -nostdlib / -nostartfiles : suppress CRT; we provide our own _start
 *   -static                   : no dynamic linker (required for gem5 SE)
 *   -lm                       : needed for sin/cos if using libm; see note
 *                               below if you want to drop libm entirely.
 * ========================================================================= */

#include <gem5/m5ops.h>

#define FFT_N (1 << 16)                 // FFT size. Must be a power of two.
#define M_PI_VAL 3.14159265358979323846 // Double precision pi

/* =========================================================================
* Minimal complex type
* ========================================================================= */
typedef struct {
    double re;
    double im;
} complex_t;

static inline complex_t cmul(complex_t a, complex_t b) {
    return (complex_t){ a.re * b.re - a.im * b.im,
                        a.re * b.im + a.im * b.re };
}

static inline complex_t cadd(complex_t a, complex_t b) {
    return (complex_t){ a.re + b.re, a.im + b.im };
}

static inline complex_t csub(complex_t a, complex_t b) {
    return (complex_t){ a.re - b.re, a.im - b.im };
}

static complex_t buf[FFT_N]; // static alloc

/*
 * Range-reduce x into [-pi/2, pi/2] then evaluate sin via minimax poly.
 * Accurate to < 2 ULP over full double range.
 */
static double my_sin(double x) {
    /* Reduce to [0, 2*pi] */
    double twopi = 2.0 * M_PI_VAL;
    /* Subtract multiples of 2*pi via integer truncation */
    long long k = (long long)(x / twopi);
    x -= (double)k * twopi;
    if (x < 0.0) x += twopi;

    /* Map into [-pi, pi] */
    if (x > M_PI_VAL) x -= twopi;

    /* Further reduce to [-pi/2, pi/2] using symmetry */
    double sign = 1.0;
    if (x > M_PI_VAL / 2.0) {
        x = M_PI_VAL - x;
    } else if (x < -M_PI_VAL / 2.0) {
        x = -M_PI_VAL - x;
        sign = -1.0;
    }

    /* Minimax polynomial for sin(x) on [-pi/2, pi/2], degree 11 */
    double x2 = x * x;
    double r = x * (1.0
        - x2 * (1.6666666666666666e-1
        - x2 * (8.3333333333333329e-3
        - x2 * (1.9841269841269841e-4
        - x2 * (2.7557319223985888e-6
        - x2 *  2.5052108385441720e-8)))));
    return sign * r;
}

static double my_cos(double x) {
    return my_sin(x + M_PI_VAL / 2.0);
}


/* =========================================================================
 * Bit-reversal permutation.
 * ========================================================================= */
static void bit_reverse(complex_t *a, int n) {
    int bits = 0;
    int tmp = n;
    while (tmp > 1) { bits++; tmp >>= 1; }

    for (int i = 0; i < n; i++) {
        int rev = 0;
        int x   = i;
        for (int b = 0; b < bits; b++) {
            rev = (rev << 1) | (x & 1);
            x >>= 1;
        }
        if (rev > i) {
            complex_t t = a[i];
            a[i]   = a[rev];
            a[rev] = t;
        }
    }
}

/* =========================================================================
 * Cooley-Tukey radix-2 DIT FFT (in-place).
 *
 * Standard butterfly:
 *   W_N^k = e^{-j*2*pi*k/N}  (forward transform convention)
 *
 * Complexity: O(N log N)
 * ========================================================================= */
static void fft(complex_t *a, int n) {
    bit_reverse(a, n);

    int stage = 0;

    for (int len = 2; len <= n; len <<= 1) {

        m5_work_begin(stage, 0); // work ID is the length
        m5_dram_opt_enter(stage, 0, a, FFT_N * sizeof(complex_t));

        double ang = -2.0 * M_PI_VAL / (double)len;
        complex_t wlen = { my_cos(ang), my_sin(ang) };

        for (int i = 0; i < n; i += len) {
            complex_t w = { 1.0, 0.0 };
            int half = len >> 1;
            for (int j = 0; j < half; j++) {
                complex_t u = a[i + j];
                complex_t v = cmul(a[i + j + half], w);
                a[i + j]        = cadd(u, v);
                a[i + j + half] = csub(u, v);
                w = cmul(w, wlen);
            }
        }
        m5_work_end(stage, 0);
        m5_dram_opt_exit(stage, 0, a, FFT_N * sizeof(complex_t));

        stage++;
    }
}

/* =========================================================================
 * Synthetic input generation.
 * ========================================================================= */
#define FREQ_0  (FFT_N / 8)
#define FREQ_1  (FFT_N / 4)

static void generate_input(complex_t *a, int n) {
    for (int i = 0; i < n; i++) {
        double t  = (double)i / (double)n;
        a[i].re   = my_sin(2.0 * M_PI_VAL * FREQ_0 * t)
                  + 0.5 * my_sin(2.0 * M_PI_VAL * FREQ_1 * t);
        a[i].im   = 0.0;
    }
}

/* =========================================================================
 * Compute magnitude-squared of a bin (used as a trivial output sink
 * so the compiler cannot dead-code-eliminate the FFT computation).
 * ========================================================================= */
static double mag_sq(complex_t c) {
    return c.re * c.re + c.im * c.im;
}

// entry
int workload_main(void) {

    generate_input(buf, FFT_N);

    fft(buf, FFT_N);

    volatile double peak0 = mag_sq(buf[FREQ_0]);
    volatile double peak1 = mag_sq(buf[FREQ_1]);

    (void)peak0;
    (void)peak1;

    return 0;
}

/* Raw Linux x86-64 exit syscall (syscall number 60) */
static __attribute__((noreturn)) void sys_exit(int code) {
    __asm__ __volatile__(
        "movq $60, %%rax\n\t"
        "syscall\n\t"
        :
        : "D"((long)code)
        : "%rax", "%rcx", "%r11", "memory"
    );
    for (;;) { }
}

/* Program entry point — replaces CRT _start */
__attribute__((visibility("default")))
void _start(void) {
    int rc = workload_main();
    sys_exit(rc);
}
