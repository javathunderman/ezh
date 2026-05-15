
#include <gem5/m5ops.h>
#include <stdint.h>

#define MAX_NODES 10000
#define MAX_EDGES 40000
#define MAX_LEVELS 20
#define MIN_COARSE_SIZE 8

typedef struct {
    int num_nodes;
    int num_edges;
    int row_ptr[MAX_NODES + 1];
    int col_idx[MAX_EDGES];
} Graph;

static uint32_t seed = 123456789;

uint32_t lcg_rand() {
    seed = (1103515245 * seed + 12345);
    return seed;
}

void generate_graph(Graph* g, int n, int avg_degree) {
    g->num_nodes = n;

    int edge_counter = 0;

    for (int i = 0; i < n; i++) {
        g->row_ptr[i] = edge_counter;

        for (int j = 0; j < avg_degree; j++) {
            int neighbor = lcg_rand() % n;

            if (neighbor == i) continue;

            if (edge_counter < MAX_EDGES) {
                g->col_idx[edge_counter++] = neighbor;
            }
        }
    }

    g->row_ptr[n] = edge_counter;
    g->num_edges = edge_counter;
}


void greedy_matching(Graph* g, int* match) {
    for (int i = 0; i < g->num_nodes; i++) {
        match[i] = -1;
    }

    for (int u = 0; u < g->num_nodes; u++) {
        if (match[u] != -1) continue;

        int start = g->row_ptr[u];
        int end   = g->row_ptr[u + 1];

        for (int e = start; e < end; e++) {
            int v = g->col_idx[e];

            if (match[v] == -1) {
                match[u] = v;
                match[v] = u;
                break;
            }
        }

        if (match[u] == -1) {
            match[u] = u;
        }
    }
}


int coarsen_once(Graph* fine, Graph* coarse) {
    int match[MAX_NODES];
    int coarse_id[MAX_NODES];

    greedy_matching(fine, match);

    int c = 0;
    for (int i = 0; i < fine->num_nodes; i++) {
        if (match[i] == i || i < match[i]) {
            coarse_id[i] = c;
            if (match[i] != i)
                coarse_id[match[i]] = c;
            c++;
        }
    }

    coarse->num_nodes = c;

    int edge_counter = 0;

    for (int i = 0; i < c; i++) {
        coarse->row_ptr[i] = edge_counter;

        for (int u = 0; u < fine->num_nodes; u++) {
            if (coarse_id[u] != i) continue;

            int start = fine->row_ptr[u];
            int end   = fine->row_ptr[u + 1];

            for (int e = start; e < end; e++) {
                int v = fine->col_idx[e];

                int cu = coarse_id[u];
                int cv = coarse_id[v];

                if (cu != cv && edge_counter < MAX_EDGES) {
                    coarse->col_idx[edge_counter++] = cv;
                }
            }
        }
    }

    coarse->row_ptr[c] = edge_counter;
    coarse->num_edges = edge_counter;

    return c; // return new node count
}


int multilevel_coarsen(Graph levels[MAX_LEVELS]) {
    int level = 0;

    while (level < MAX_LEVELS - 1) {
        m5_work_begin(level, 0);
        Graph* fine   = &levels[level];
        Graph* coarse = &levels[level + 1];

        int prev_nodes = fine->num_nodes;
        m5_dram_opt_enter(level, 0, &levels[level], sizeof(Graph) * 2);
        int new_nodes = coarsen_once(fine, coarse);
        m5_dram_opt_exit(level, 0, &levels[level], sizeof(Graph) * 2);
        // Stopping conditions
        if (new_nodes >= prev_nodes) break;
        if (new_nodes <= MIN_COARSE_SIZE) break;
        m5_work_end(level, 0);
        level++;
    }
    m5_work_end(level, 0);
    return level; // last level index
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

extern "C" void _start(void) {
    int num_nodes = 100000;
    int num_edges = 400000;

    Graph levels[MAX_LEVELS];

    int N = 256;
    int DEG = 10;

    generate_graph(&levels[0], N, DEG);

    int last_level = multilevel_coarsen(levels);
    
    sys_exit(0);
}
