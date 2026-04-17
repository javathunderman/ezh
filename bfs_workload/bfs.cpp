
#include <gem5/m5ops.h>
// -------- CONFIG --------
#define MAX_NODES 100000
#define MAX_EDGES 500000

// -------- GRAPH STORAGE (Adjacency List) --------
struct Edge {
    int to;
    int next;
};

Edge edges[MAX_EDGES];
int head[MAX_NODES];
int edge_count = 0;

// Add edge u -> v
void add_edge(int u, int v) {
    edges[edge_count].to = v;
    edges[edge_count].next = head[u];
    head[u] = edge_count;
    edge_count++;
}

// -------- SIMPLE QUEUE --------
struct Queue {
    int data[MAX_NODES];
    int front;
    int rear;
};

void init_queue(Queue* q) {
    q->front = 0;
    q->rear = 0;
}

int is_empty(Queue* q) {
    return q->front == q->rear;
}

void enqueue(Queue* q, int val) {
    q->data[q->rear++] = val;
}

int dequeue(Queue* q) {
    return q->data[q->front++];
}

// -------- BFS --------
int visited[MAX_NODES];

void bfs(int start, int num_nodes) {
    Queue q;
    init_queue(&q);

    // Initialize visited
    for (int i = 0; i < num_nodes; i++) {
        visited[i] = 0;
    }

    visited[start] = 1;
    enqueue(&q, start);

    while (!is_empty(&q)) {
        int u = dequeue(&q);

        // Process node (here we just print it)
        // Replace this with whatever work you need
        // printf("%d\n", u);

        int e = head[u];
        while (e != -1) {
            int v = edges[e].to;
            if (!visited[v]) {
                visited[v] = 1;
                enqueue(&q, v);
            }
            e = edges[e].next;
        }
    }
}

// -------- GRAPH GENERATION --------
// Simple deterministic generator (no rand())
void generate_graph(int num_nodes, int num_edges) {
    // Initialize heads
    for (int i = 0; i < num_nodes; i++) {
        head[i] = -1;
    }

    edge_count = 0;

    // Create a pseudo-random but deterministic pattern
    int u = 1;
    int v = 2;

    for (int i = 0; i < num_edges; i++) {
        u = (u * 1103515245 + 12345) % num_nodes;
        v = (v * 1103515245 + 67890) % num_nodes;

        if (u != v) {
            add_edge(u, v);
            // Optional: make it undirected
            // add_edge(v, u);
        }
    }
}

// -------- MAIN --------
// int main() {
//     int num_nodes = 100000;
//     int num_edges = 400000;

//     generate_graph(num_nodes, num_edges);

//     bfs(0, num_nodes);

//     return 0;
// }

// Raw Linux x86-64 exit syscall
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
    int num_nodes = 100000;
    int num_edges = 400000;

    
    m5_work_begin(0, 0);   // workid = t
    generate_graph(num_nodes, num_edges);
    bfs(0, num_nodes);
    m5_work_end(0, 0);

    bfs(0, num_nodes);
    // int rc = workload_main();
    sys_exit(0);
}