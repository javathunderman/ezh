// Freestanding pull PageRank workload for gem5/DRAMSim3 trace experiments.
#include <gem5/m5ops.h>

#define NODES 2048
#define DEG 16
#define EDGES (NODES * DEG)
#define ITERS 8
#define SCALE 1000000
#define DAMP_NUM 85
#define DAMP_DEN 100

static int row_ptr[NODES + 1];
static int col_idx[EDGES];
static int out_deg[NODES];
static int rank_a[NODES];
static int rank_b[NODES];
static int checksum_sink = 0;

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

static int append_str(char* out, int p, const char* s) {
    for (int i = 0; s[i]; ++i) out[p++] = s[i];
    return p;
}

static int append_dec(char* out, int p, unsigned long long v) {
    char tmp[32];
    int n = 0;
    if (v == 0) {
        out[p++] = '0';
        return p;
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

static void print_region(const char* name, const void* base, unsigned long long bytes) {
    char buf[192];
    int p = 0;
    unsigned long long b = (unsigned long long)(unsigned long)base;
    p = append_str(buf, p, "PRREG name=");
    p = append_str(buf, p, name);
    p = append_str(buf, p, " base=");
    p = append_hex64(buf, p, b);
    p = append_str(buf, p, " end=");
    p = append_hex64(buf, p, b + bytes);
    p = append_str(buf, p, " bytes=");
    p = append_dec(buf, p, bytes);
    buf[p++] = '\n';
    sys_write(1, buf, (unsigned long)p);
}

static unsigned int lcg = 0x31415926u;
static unsigned int rng_u32() {
    lcg = lcg * 1664525u + 1013904223u;
    return lcg;
}

static void init_graph() {
    int edge = 0;
    for (int v = 0; v < NODES; ++v) {
        row_ptr[v] = edge;
        out_deg[v] = DEG;
        unsigned int seed = rng_u32() ^ (unsigned int)(v * 2654435761u);
        for (int j = 0; j < DEG; ++j) {
            seed = seed * 1103515245u + 12345u;
            int src = (int)((seed >> 8) & (NODES - 1));
            if (src == v) src = (src + 17) & (NODES - 1);
            col_idx[edge++] = src;
        }
    }
    row_ptr[NODES] = edge;

    int init = SCALE / NODES;
    for (int i = 0; i < NODES; ++i) {
        rank_a[i] = init;
        rank_b[i] = 0;
    }
}

static void pagerank_iter(int iter) {
    int* old_rank = (iter & 1) ? rank_b : rank_a;
    int* new_rank = (iter & 1) ? rank_a : rank_b;
    int base = ((DAMP_DEN - DAMP_NUM) * SCALE) / (DAMP_DEN * NODES);

    for (int v = 0; v < NODES; ++v) {
        int start = row_ptr[v];
        int end = row_ptr[v + 1];
        long long acc = 0;

        for (int e = start; e < end; ++e) {
            int src = col_idx[e];
            int deg = out_deg[src];
            if (deg > 0) {
                acc += old_rank[src] / deg;
            }
        }

        int next = base + (int)((DAMP_NUM * acc) / DAMP_DEN);
        new_rank[v] = next;
    }
}

static int workload_main() {
    print_region("rank_a", rank_a, sizeof(rank_a));
    print_region("rank_b", rank_b, sizeof(rank_b));
    print_region("row_ptr", row_ptr, sizeof(row_ptr));
    print_region("col_idx", col_idx, sizeof(col_idx));
    print_region("out_deg", out_deg, sizeof(out_deg));

    init_graph();

    for (int iter = 0; iter < ITERS; ++iter) {
        m5_work_begin(iter, 0);
        pagerank_iter(iter);
        m5_work_end(iter, 0);
    }

    int* final_rank = (ITERS & 1) ? rank_b : rank_a;
    int acc = 0;
    for (int i = 0; i < NODES; ++i) {
        acc ^= final_rank[i] + i * 17;
        acc = (acc << 3) | ((unsigned int)acc >> 29);
    }
    checksum_sink = acc;
    return acc & 255;
}

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

extern "C" void _start() {
    int rc = workload_main();
    (void)rc;
    sys_exit(0);
}
