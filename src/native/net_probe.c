/*
 * net_probe.c - Native C Linux TCP BBR, qdisc, /proc/net/snmp & Socket Profiler
 */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include <ctype.h>
#include <dirent.h>
#include <fcntl.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static bool read_line(const char *path, char *out, size_t sz) {
    int fd = open(path, O_RDONLY);
    if (fd < 0) return false;
    ssize_t n = read(fd, out, sz - 1);
    close(fd);
    if (n <= 0) return false;
    out[n] = '\0';
    while (n > 0 && (out[n - 1] == '\n' || out[n - 1] == ' ')) out[--n] = '\0';
    return true;
}

static uint64_t read_u64(const char *path) {
    char b[64];
    if (!read_line(path, b, sizeof(b))) return 0;
    return strtoull(b, NULL, 10);
}

static void find_primary_iface(char *out, size_t sz) {
    snprintf(out, sz, "lo");
    DIR *d = opendir("/sys/class/net");
    if (!d) return;
    struct dirent *de;
    while ((de = readdir(d)) != NULL) {
        if (de->d_name[0] == '.' || strcmp(de->d_name, "lo") == 0) continue;
        char op[256], st[32] = "";
        snprintf(op, sizeof(op), "/sys/class/net/%.32s/operstate", de->d_name);
        if (read_line(op, st, sizeof(st)) && strcmp(st, "up") == 0) {
            snprintf(out, sz, "%.31s", de->d_name);
            break;
        }
    }
    closedir(d);
}

static void read_snmp_tcp(uint64_t *estab, uint64_t *out_segs, uint64_t *retrans) {
    *estab = *out_segs = *retrans = 0;
    FILE *f = fopen("/proc/net/snmp", "r");
    if (!f) return;
    char hdr[1024], val[1024];
    while (fgets(hdr, sizeof(hdr), f)) {
        if (strncmp(hdr, "Tcp:", 4) == 0 && fgets(val, sizeof(val), f)) {
            if (strncmp(val, "Tcp:", 4) == 0) {
                /* Column order in Linux /proc/net/snmp Tcp: 9=CurrEstab, 11=OutSegs, 12=RetransSegs (1-indexed after Tcp:) */
                uint64_t cols[20] = {0};
                int idx = 0;
                char *p = val + 4;
                while (*p && idx < 20) {
                    while (*p && isspace((unsigned char)*p)) p++;
                    if (!isdigit((unsigned char)*p)) break;
                    cols[idx++] = strtoull(p, &p, 10);
                }
                if (idx >= 12) {
                    *estab = cols[8];
                    *out_segs = cols[10];
                    *retrans = cols[11];
                }
                break;
            }
        }
    }
    fclose(f);
}

typedef struct {
    int pid;
    char name[32];
    int sockets;
} SockProc;

static int cmp_sp_desc(const void *a, const void *b) {
    return ((const SockProc *)b)->sockets - ((const SockProc *)a)->sockets;
}

int main(int argc, char *argv[]) {
    bool as_json = false;
    int sample_ms = 120;
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--json") == 0 || strcmp(argv[i], "-j") == 0) as_json = true;
        else if (strcmp(argv[i], "--sample-ms") == 0 && i + 1 < argc) {
            sample_ms = atoi(argv[++i]);
            if (sample_ms < 40) sample_ms = 40;
            if (sample_ms > 1500) sample_ms = 1500;
        }
    }

    char iface[32];
    find_primary_iface(iface, sizeof(iface));
    char rxp[128], txp[128], drp[128];
    snprintf(rxp, sizeof(rxp), "/sys/class/net/%s/statistics/rx_bytes", iface);
    snprintf(txp, sizeof(txp), "/sys/class/net/%s/statistics/tx_bytes", iface);
    snprintf(drp, sizeof(drp), "/sys/class/net/%s/statistics/rx_dropped", iface);

    uint64_t rx0 = read_u64(rxp), tx0 = read_u64(txp);
    usleep((useconds_t)sample_ms * 1000U);
    uint64_t rx1 = read_u64(rxp), tx1 = read_u64(txp), rxd = read_u64(drp);

    double sec = (double)sample_ms / 1000.0;
    double rx_kbps = (rx1 >= rx0) ? ((double)(rx1 - rx0) / 1024.0) / sec : 0.0;
    double tx_kbps = (tx1 >= tx0) ? ((double)(tx1 - tx0) / 1024.0) / sec : 0.0;

    char cc[32] = "cubic", qdisc[32] = "pfifo_fast";
    read_line("/proc/sys/net/ipv4/tcp_congestion_control", cc, sizeof(cc));
    read_line("/proc/sys/net/core/default_qdisc", qdisc, sizeof(qdisc));

    uint64_t estab = 0, out_s = 0, ret_s = 0;
    read_snmp_tcp(&estab, &out_s, &ret_s);
    double retr_pct = (out_s > 0) ? ((double)ret_s / (double)out_s) * 100.0 : 0.0;

    SockProc sps[512];
    size_t nsp = 0;
    DIR *pd = opendir("/proc");
    if (pd) {
        struct dirent *de;
        while ((de = readdir(pd)) != NULL && nsp < 512) {
            if (!isdigit((unsigned char)de->d_name[0])) continue;
            int pid = atoi(de->d_name);
            char fp[128], cp[128], cname[32] = "";
            snprintf(fp, sizeof(fp), "/proc/%d/fd", pid);
            DIR *fd = opendir(fp);
            if (!fd) continue;
            int sc = 0;
            struct dirent *fe;
            while ((fe = readdir(fd)) != NULL) {
                char lp[256], tgt[128];
                snprintf(lp, sizeof(lp), "/proc/%d/fd/%.64s", pid, fe->d_name);
                ssize_t rl = readlink(lp, tgt, sizeof(tgt) - 1);
                if (rl > 0) {
                    tgt[rl] = '\0';
                    if (strncmp(tgt, "socket:[", 8) == 0) sc++;
                }
            }
            closedir(fd);
            if (sc <= 0) continue;
            snprintf(cp, sizeof(cp), "/proc/%d/comm", pid);
            read_line(cp, cname, sizeof(cname));
            sps[nsp].pid = pid;
            snprintf(sps[nsp].name, sizeof(sps[nsp].name), "%.31s", cname[0] ? cname : "proc");
            sps[nsp].sockets = sc;
            nsp++;
        }
        closedir(pd);
    }
    qsort(sps, nsp, sizeof(SockProc), cmp_sp_desc);
    bool bpf_ready = (access("bpf/sock_rtt.bpf.o", F_OK) == 0);

    if (as_json) {
        printf("{\n"
               "  \"iface\": \"%s\",\n"
               "  \"bpf_ready\": %s,\n"
               "  \"tcp_cc\": \"%s\",\n"
               "  \"qdisc\": \"%s\",\n"
               "  \"rx_kbps\": %.1f,\n"
               "  \"tx_kbps\": %.1f,\n"
               "  \"rx_dropped\": %llu,\n"
               "  \"tcp_estab\": %llu,\n"
               "  \"retrans_pct\": %.3f,\n"
               "  \"top_sockets\": [",
               iface, bpf_ready ? "true" : "false", cc, qdisc, rx_kbps, tx_kbps,
               (unsigned long long)rxd, (unsigned long long)estab, retr_pct);
        size_t tp = nsp < 6 ? nsp : 6;
        for (size_t i = 0; i < tp; i++) {
            printf("%s\n    {\"pid\": %d, \"name\": \"%s\", \"sockets\": %d}",
                   i == 0 ? "" : ",", sps[i].pid, sps[i].name, sps[i].sockets);
        }
        printf("\n  ]\n}\n");
    } else {
        printf("=== NetPulse BPF (%s) ===\n", iface);
        printf("  Stack : TCP %s / qdisc %s | Estab: %llu | Retrans: %.3f%%\n",
               cc, qdisc, (unsigned long long)estab, retr_pct);
        printf("  Rate  : RX %.1f KB/s | TX %.1f KB/s | Dropped: %llu\n",
               rx_kbps, tx_kbps, (unsigned long long)rxd);
    }
    return 0;
}
