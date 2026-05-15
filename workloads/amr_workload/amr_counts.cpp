// amr_counts_freestanding.cpp
// x86-64 Linux freestanding entry for gem5-style runs
// No headers, no stdlib, no libc, no iostream, no printf.
#include <gem5/m5ops.h>

#define MAX_CELLS          4096
#define MAX_DEPTH          6
#define ROOT_GRID_X        64
#define ROOT_GRID_Y        64
#define NUM_STEPS          3

#define REFINE_THRESHOLD   180
#define COARSEN_THRESHOLD  70

static inline int iabs_i(int x) { return (x < 0) ? -x : x; }

static unsigned int g_rng = 0x12345678u;
static inline unsigned int rng_u32() {
    g_rng = g_rng * 1664525u + 1013904223u;
    return g_rng;
}

struct Cell {
    int alive;
    int leaf;
    int parent;
    int child[4];
    unsigned short x0, y0, x1, y1;
    unsigned char depth;
    int value;
    int init_tag;
};

static Cell g_cells[MAX_CELLS];
static int g_cell_count = 0;
static const unsigned int DOMAIN_SCALE = 1024u;

#ifndef RISCV
// Raw Linux x86-64 write syscall
static long sys_write(int fd, const char* buf, unsigned long len) {
    long ret;
    __asm__ __volatile__(
        "movq $1, %%rax\n\t"
        "syscall\n\t"
        : "=a"(ret)
        : "D"((long)fd), "S"(buf), "d"((long)len)
        : "%rcx", "%r11", "memory"
    );
    return ret;
}
#endif

#ifdef RISCV
// Raw Linux RISC-V write syscall
static long sys_write(int fd, const char* buf, unsigned long len) {
    long ret;
    __asm__ __volatile__(
        "li a7, 64\n\t"
        "mv a0, %1\n\t"
        "mv a1, %2\n\t"
        "mv a2, %3\n\t"
        "ecall\n\t"
        "mv %0, a0\n\t"
        : "=r"(ret)
        : "r"((long)fd), "r"(buf), "r"((long)len)
        : "a7", "a0", "a1", "a2", "memory"
    );
    return ret;
}
#endif

static int append_str(char* out, int p, const char* s) {
    for (int i = 0; s[i]; ++i) out[p++] = s[i];
    return p;
}

static int append_dec(char* out, int p, int v) {
    char tmp[16];
    int n = 0;

    if (v == 0) {
        out[p++] = '0';
        return p;
    }

    if (v < 0) {
        out[p++] = '-';
        v = -v;
    }

    while (v > 0) {
        tmp[n++] = (char)('0' + (v % 10));
        v /= 10;
    }

    while (n > 0) out[p++] = tmp[--n];
    return p;
}

static int append_hex64(char* out, int p, unsigned long long v) {
    static const char h[] = "0123456789abcdef";
    out[p++] = '0';
    out[p++] = 'x';
    for (int i = 15; i >= 0; --i) {
        out[p++] = h[(v >> (i * 4)) & 0xfULL];
    }
    return p;
}

static void print_cell_addr(int idx) {
    char buf[160];
    int p = 0;

    unsigned long long base =
        (unsigned long long)(unsigned long)&g_cells[0];
    unsigned long long addr =
        (unsigned long long)(unsigned long)&g_cells[idx];
    unsigned long long offset =
        (unsigned long long)((char*)&g_cells[idx] - (char*)&g_cells[0]);

    p = append_str(buf, p, "GCELL idx=");
    p = append_dec(buf, p, idx);
    p = append_str(buf, p, " base=");
    p = append_hex64(buf, p, base);
    p = append_str(buf, p, " addr=");
    p = append_hex64(buf, p, addr);
    p = append_str(buf, p, " offset=");
    p = append_hex64(buf, p, offset);
    p = append_str(buf, p, " sizeof_cell=");
    p = append_dec(buf, p, (int)sizeof(Cell));
    buf[p++] = '\n';

    sys_write(1, buf, (unsigned long)p);
}

static int alloc_cell() {
    if (g_cell_count >= MAX_CELLS) return -1;
    int idx = g_cell_count++;

    g_cells[idx].alive = 1;
    g_cells[idx].leaf = 1;
    g_cells[idx].parent = -1;
    g_cells[idx].child[0] = -1;
    g_cells[idx].child[1] = -1;
    g_cells[idx].child[2] = -1;
    g_cells[idx].child[3] = -1;
    g_cells[idx].x0 = g_cells[idx].y0 = g_cells[idx].x1 = g_cells[idx].y1 = 0;
    g_cells[idx].depth = 0;
    g_cells[idx].value = 0;
    g_cells[idx].init_tag = 0;

    print_cell_addr(idx);

    return idx;
}

static int sample_field(unsigned int x, unsigned int y, int t, int tag) {
    int xi = (int)x;
    int yi = (int)y;
    int cx = 200 + ((t * 37 + (tag & 31) * 9) & 511);
    int cy = 300 + ((t * 29 + ((tag >> 3) & 31) * 7) & 511);
    int dx = xi - cx;
    int dy = yi - cy;
    int cone = 700 - (iabs_i(dx) + iabs_i(dy));
    if (cone < 0) cone = 0;
    int stripes = ((xi >> 4) ^ (yi >> 5) ^ (t * 3)) & 31;
    int wobble  = ((xi * 3 + yi * 5 + t * 11 + tag * 13) >> 3) & 63;
    return cone + stripes * 3 + wobble;
}

static int estimate_variation(const Cell* c, int t) {
    unsigned int xmid = ((unsigned int)c->x0 + (unsigned int)c->x1) >> 1;
    unsigned int ymid = ((unsigned int)c->y0 + (unsigned int)c->y1) >> 1;

    int s00 = sample_field(c->x0, c->y0, t, c->init_tag);
    int s10 = sample_field(c->x1, c->y0, t, c->init_tag);
    int s01 = sample_field(c->x0, c->y1, t, c->init_tag);
    int s11 = sample_field(c->x1, c->y1, t, c->init_tag);
    int sm  = sample_field(xmid, ymid, t, c->init_tag);

    int avg4 = (s00 + s10 + s01 + s11) >> 2;
    int v = 0;
    v += iabs_i(s00 - avg4);
    v += iabs_i(s10 - avg4);
    v += iabs_i(s01 - avg4);
    v += iabs_i(s11 - avg4);
    v += iabs_i(sm  - avg4);

    int size_term = (int)(((unsigned int)(c->x1 - c->x0) + (unsigned int)(c->y1 - c->y0)) >> 4);
    return v + size_term;
}

static int compute_cell_value(const Cell* c, int t) {
    unsigned int xmid = ((unsigned int)c->x0 + (unsigned int)c->x1) >> 1;
    unsigned int ymid = ((unsigned int)c->y0 + (unsigned int)c->y1) >> 1;
    return sample_field(xmid, ymid, t, c->init_tag);
}

static int split_cell(int idx, int t) {
    Cell* c = &g_cells[idx];
    if (!c->alive || !c->leaf) return 0;
    if (c->depth >= MAX_DEPTH) return 0;

    unsigned int x0 = c->x0, y0 = c->y0, x1 = c->x1, y1 = c->y1;
    unsigned int xm = (x0 + x1) >> 1;
    unsigned int ym = (y0 + y1) >> 1;
    if (xm == x0 || xm == x1 || ym == y0 || ym == y1) return 0;

    int ch[4];
    for (int k = 0; k < 4; ++k) {
        ch[k] = alloc_cell();
        if (ch[k] < 0) return 0;
    }

    g_cells[ch[0]].parent = idx;
    g_cells[ch[0]].depth  = c->depth + 1;
    g_cells[ch[0]].x0 = (unsigned short)x0; g_cells[ch[0]].y0 = (unsigned short)ym;
    g_cells[ch[0]].x1 = (unsigned short)xm; g_cells[ch[0]].y1 = (unsigned short)y1;
    g_cells[ch[0]].init_tag = c->init_tag ^ 0x11;
    g_cells[ch[0]].value = compute_cell_value(&g_cells[ch[0]], t);

    g_cells[ch[1]].parent = idx;
    g_cells[ch[1]].depth  = c->depth + 1;
    g_cells[ch[1]].x0 = (unsigned short)xm; g_cells[ch[1]].y0 = (unsigned short)ym;
    g_cells[ch[1]].x1 = (unsigned short)x1; g_cells[ch[1]].y1 = (unsigned short)y1;
    g_cells[ch[1]].init_tag = c->init_tag ^ 0x22;
    g_cells[ch[1]].value = compute_cell_value(&g_cells[ch[1]], t);

    g_cells[ch[2]].parent = idx;
    g_cells[ch[2]].depth  = c->depth + 1;
    g_cells[ch[2]].x0 = (unsigned short)x0; g_cells[ch[2]].y0 = (unsigned short)y0;
    g_cells[ch[2]].x1 = (unsigned short)xm; g_cells[ch[2]].y1 = (unsigned short)ym;
    g_cells[ch[2]].init_tag = c->init_tag ^ 0x33;
    g_cells[ch[2]].value = compute_cell_value(&g_cells[ch[2]], t);

    g_cells[ch[3]].parent = idx;
    g_cells[ch[3]].depth  = c->depth + 1;
    g_cells[ch[3]].x0 = (unsigned short)xm; g_cells[ch[3]].y0 = (unsigned short)y0;
    g_cells[ch[3]].x1 = (unsigned short)x1; g_cells[ch[3]].y1 = (unsigned short)ym;
    g_cells[ch[3]].init_tag = c->init_tag ^ 0x44;
    g_cells[ch[3]].value = compute_cell_value(&g_cells[ch[3]], t);

    c->leaf = 0;
    c->child[0] = ch[0];
    c->child[1] = ch[1];
    c->child[2] = ch[2];
    c->child[3] = ch[3];
    return 1;
}

static int can_merge_children(int idx, int t) {
    Cell* p = &g_cells[idx];
    if (!p->alive || p->leaf) return 0;
    int ch0 = p->child[0], ch1 = p->child[1], ch2 = p->child[2], ch3 = p->child[3];
    if (ch0 < 0 || ch1 < 0 || ch2 < 0 || ch3 < 0) return 0;
    if (!g_cells[ch0].alive || !g_cells[ch1].alive || !g_cells[ch2].alive || !g_cells[ch3].alive) return 0;
    if (!g_cells[ch0].leaf || !g_cells[ch1].leaf || !g_cells[ch2].leaf || !g_cells[ch3].leaf) return 0;
    return estimate_variation(p, t) < COARSEN_THRESHOLD;
}

static void merge_children(int idx, int t) {
    Cell* p = &g_cells[idx];
    if (!p->alive || p->leaf) return;
    for (int k = 0; k < 4; ++k) {
        int ci = p->child[k];
        if (ci >= 0) {
            g_cells[ci].alive = 0;
            g_cells[ci].leaf = 0;
        }
        p->child[k] = -1;
    }
    p->leaf = 1;
    p->value = compute_cell_value(p, t);
}

static void init_roots() {
    g_cell_count = 0;
    unsigned int dx = DOMAIN_SCALE / (unsigned int)ROOT_GRID_X;
    unsigned int dy = DOMAIN_SCALE / (unsigned int)ROOT_GRID_Y;

    for (int j = 0; j < ROOT_GRID_Y; ++j) {
        for (int i = 0; i < ROOT_GRID_X; ++i) {
            int idx = alloc_cell();
            if (idx < 0) return;
            unsigned int x0 = (unsigned int)i * dx;
            unsigned int y0 = (unsigned int)j * dy;
            unsigned int x1 = (i == ROOT_GRID_X - 1) ? DOMAIN_SCALE : ((unsigned int)(i + 1) * dx);
            unsigned int y1 = (j == ROOT_GRID_Y - 1) ? DOMAIN_SCALE : ((unsigned int)(j + 1) * dy);

            g_cells[idx].parent = -1;
            g_cells[idx].depth = 0;
            g_cells[idx].x0 = (unsigned short)x0;
            g_cells[idx].y0 = (unsigned short)y0;
            g_cells[idx].x1 = (unsigned short)x1;
            g_cells[idx].y1 = (unsigned short)y1;
            g_cells[idx].init_tag = (int)(rng_u32() & 255u);
            g_cells[idx].value = compute_cell_value(&g_cells[idx], 0);
        }
    }
}

static void update_leaf_values(int t) {
    for (int i = 0; i < g_cell_count; ++i) {
        if (g_cells[i].alive && g_cells[i].leaf) {
            g_cells[i].value = compute_cell_value(&g_cells[i], t);
        }
    }
}

static void adapt_refine(int t) {
    int initial_count = g_cell_count;
    for (int i = 0; i < initial_count; ++i) {
        if (!g_cells[i].alive || !g_cells[i].leaf) continue;
        if (g_cells[i].depth >= MAX_DEPTH) continue;
        if (estimate_variation(&g_cells[i], t) > REFINE_THRESHOLD) {
            split_cell(i, t);
        }
    }
}

static void adapt_coarsen(int t) {
    for (int i = g_cell_count - 1; i >= 0; --i) {
        if (g_cells[i].alive && !g_cells[i].leaf && can_merge_children(i, t)) {
            merge_children(i, t);
        }
    }
}

static int compute_checksum() {
    unsigned int acc = 0u;
    for (int i = 0; i < g_cell_count; ++i) {
        if (!g_cells[i].alive || !g_cells[i].leaf) continue;
        acc ^= (unsigned int)(g_cells[i].value + 31 * (int)g_cells[i].depth);
        acc = (acc << 5) | (acc >> 27);
        acc += (unsigned int)g_cells[i].x0 + ((unsigned int)g_cells[i].y0 << 1);
    }
    return (int)(acc & 0x7fffffffU);
}

static int workload_main() {
    init_roots();
    int testAddr[1] = {1};
    for (int t = 0; t < NUM_STEPS; ++t) {
        m5_work_begin(t, 0);   // workid = t
        m5_dram_opt_enter(t, 0, g_cells, sizeof(Cell) * g_cell_count);
        update_leaf_values(t);
        adapt_refine(t);
        adapt_coarsen(t);
        m5_dram_opt_exit(t, 0, g_cells, sizeof(Cell) * g_cell_count);
        m5_work_end(t, 0);
    }
    return compute_checksum() & 255;
}

// Raw Linux x86-64 exit syscall
#ifndef RISCV
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
#endif

#ifdef RISCV
static __attribute__((noreturn)) void sys_exit(int code) {
    __asm__ __volatile__(
        "li a7, 93\n\t"       // syscall number for exit (93 on RISC-V Linux)
        "mv a0, %0\n\t"       // move exit code into a0
        "ecall\n\t"
        :
        : "r"((long)code)
        : "a7", "a0", "memory"
    );
    for (;;) { }
}
#endif

extern "C" void _start() {
    int rc = workload_main();
    sys_exit(rc);
}