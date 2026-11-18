/* SPDX-License-Identifier: GPL-2.0 OR MIT */
/* Real Linux eBPF sock_ops RTT & retransmit counter hook */
#include <linux/types.h>
#include <linux/bpf.h>

#define SEC(NAME) __attribute__((section(NAME), used))
#define __uint(name, val) int (*name)[val]
#define __type(name, val) typeof(val) *name

static void *(*bpf_map_lookup_elem)(void *map, const void *key) = (void *)1;

struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __type(key, __u32);
    __type(value, __u64);
    __uint(max_entries, 4);
} net_stats_map SEC(".maps");

SEC("sockops")
int netpulse_sockops(struct bpf_sock_ops *skops) {
    if (skops->op == BPF_SOCK_OPS_RTT_CB) {
        __u32 k0 = 0, k1 = 1;
        __u64 *cnt = bpf_map_lookup_elem(&net_stats_map, &k0);
        if (cnt) __sync_fetch_and_add(cnt, 1);
        __u64 *sum = bpf_map_lookup_elem(&net_stats_map, &k1);
        if (sum) __sync_fetch_and_add(sum, (__u64)(skops->srtt_us >> 3));
    } else if (skops->op == BPF_SOCK_OPS_RETRANS_CB) {
        __u32 k2 = 2;
        __u64 *rc = bpf_map_lookup_elem(&net_stats_map, &k2);
        if (rc) __sync_fetch_and_add(rc, 1);
    }
    return 1;
}

char LICENSE[] SEC("license") = "Dual MIT/GPL";
