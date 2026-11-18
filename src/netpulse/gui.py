from __future__ import annotations

import os
import pathlib
import threading
from collections import deque

os.environ.setdefault("GSK_RENDERER", "gl")

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk

from .monitor import sample_network

ROOT = pathlib.Path(__file__).resolve().parents[2]

NET_CSS = b"""
window, window.background, AdwApplicationWindow {
    background-color: #050712;
    background-image: radial-gradient(circle at 18% 12%, rgba(99, 102, 241, 0.14), transparent 46%),
                      radial-gradient(circle at 86% 85%, rgba(34, 211, 238, 0.10), transparent 46%);
    color: #eef2ff;
}
headerbar, AdwHeaderBar {
    background: #0a0d1e;
    border-bottom: 1px solid rgba(129, 140, 248, 0.25);
    color: #eef2ff;
    min-height: 42px;
}
.pipe-wrap {
    background: #0b0f22;
    border: 1px solid rgba(129, 140, 248, 0.25);
    border-radius: 10px;
    padding: 10px 14px;
}
.n-card {
    background: #0c1024;
    border: 1px solid rgba(129, 140, 248, 0.22);
    border-radius: 10px;
    padding: 13px 16px;
}
.stat-pill {
    background: #090c1b;
    border: 1px solid rgba(34, 211, 238, 0.22);
    border-radius: 7px;
    padding: 7px 10px;
}
.win-btn {
    border-radius: 6px; padding: 4px 10px; font-size: 11px; font-weight: 700;
    background: rgba(129, 140, 248, 0.14); border: 1px solid rgba(129, 140, 248, 0.30);
}
.win-active {
    background: rgba(34, 211, 238, 0.25);
    border: 1px solid #22d3ee;
    color: #cffafe;
}
.st { font-size: 13.5px; font-weight: 700; color: #eef2ff; }
.ss { font-size: 11px; color: #94a3b8; }
.sk { font-size: 10px; font-weight: 700; color: #818cf8; letter-spacing: 0.7px; }
.sv { font-family: monospace; font-size: 16px; font-weight: 800; color: #f8fafc; }
.mono { font-family: monospace; font-size: 12px; color: #e2e8f0; }
.row { padding: 6px 0; border-bottom: 1px solid rgba(255, 255, 255, 0.06); }
progressbar trough { background: rgba(255, 255, 255, 0.08); border-radius: 4px; min-height: 6px; }
progressbar progress { background: #22d3ee; border-radius: 4px; min-height: 6px; }
"""


class KernelPipelineBanner(Gtk.DrawingArea):
    """Draws 5 kernel networking pipeline stages horizontally across the top."""

    def __init__(self) -> None:
        super().__init__()
        self.set_size_request(-1, 74)
        self.set_hexpand(True)
        self._iface = "wlp1s0f0"
        self._qdisc = "fq"
        self._cc = "bbr"
        self._bpf = "sock_rtt.bpf.o"
        self._health = "OPTIMAL"
        self.set_draw_func(self._draw)

    def update(self, iface: str, qdisc: str, cc: str, bpf_ok: bool, health: str) -> None:
        self._iface = iface
        self._qdisc = qdisc
        self._cc = cc.upper()
        self._bpf = "sock_rtt.bpf.o OK" if bpf_ok else "SNMP fallback"
        self._health = health.replace("_", " ")
        self.queue_draw()

    def _draw(self, _a, cr: cairo.Context, w: int, h: int) -> None:
        cr.set_source_rgba(0.03, 0.04, 0.10, 0.0)
        cr.rectangle(0, 0, w, h)
        cr.fill()

        stages = [
            ("1. NIC LINK", self._iface, (0.13, 0.83, 0.93)),
            ("2. QUEUING DISC", self._qdisc, (0.51, 0.55, 0.97)),
            ("3. TCP CONGESTION", self._cc, (0.38, 0.72, 0.98)),
            ("4. eBPF HOOK ELF", self._bpf, (0.65, 0.55, 0.98)),
            ("5. LINK VERDICT", self._health, (0.06, 0.72, 0.51) if "OPTIMAL" in self._health else (0.98, 0.75, 0.14)),
        ]
        n = len(stages)
        gap = 18.0
        box_w = max(90.0, (w - gap * (n - 1) - 4.0) / n)
        bh = h - 10.0
        y0 = 5.0

        for i, (title, val, rgb) in enumerate(stages):
            bx = 2.0 + i * (box_w + gap)
            cr.set_source_rgba(0.06, 0.08, 0.17, 0.95)
            cr.rectangle(bx, y0, box_w, bh)
            cr.fill()
            cr.set_source_rgba(rgb[0], rgb[1], rgb[2], 0.45)
            cr.set_line_width(1.2)
            cr.rectangle(bx, y0, box_w, bh)
            cr.stroke()

            cr.set_source_rgba(rgb[0], rgb[1], rgb[2], 0.95)
            cr.set_font_size(9.5)
            cr.move_to(bx + 10, y0 + 21)
            cr.show_text(title)

            cr.set_source_rgba(0.95, 0.97, 1.0, 0.98)
            cr.set_font_size(11.5)
            cr.move_to(bx + 10, y0 + 44)
            cr.show_text(val[:22])

            if i < n - 1:
                ax0 = bx + box_w + 3
                ax1 = bx + box_w + gap - 3
                ay = y0 + bh * 0.5
                cr.set_source_rgba(0.51, 0.55, 0.97, 0.65)
                cr.set_line_width(1.6)
                cr.move_to(ax0, ay)
                cr.line_to(ax1, ay)
                cr.stroke()


class ButterflyThroughputChart(Gtk.DrawingArea):
    """Mirrored bidirectional butterfly waveform: RX upward (cyan), TX downward (gold)."""

    def __init__(self) -> None:
        super().__init__()
        self.set_size_request(-1, 240)
        self.set_hexpand(True)
        self.set_vexpand(True)
        self._rx: deque[float] = deque(maxlen=55)
        self._tx: deque[float] = deque(maxlen=55)
        self.set_draw_func(self._draw)

    def push(self, rx_kbps: float, tx_kbps: float) -> None:
        self._rx.append(rx_kbps)
        self._tx.append(tx_kbps)
        self.queue_draw()

    def _draw(self, _a, cr: cairo.Context, w: int, h: int) -> None:
        cr.set_source_rgba(0.03, 0.04, 0.10, 0.96)
        cr.rectangle(0, 0, w, h)
        cr.fill()

        pad_l, pad_r, pad_t, pad_b = 56.0, 14.0, 16.0, 16.0
        cw = max(30.0, w - pad_l - pad_r)
        ch = max(40.0, h - pad_t - pad_b)
        mid_y = pad_t + ch * 0.5
        half_h = ch * 0.48
        peak = max(16.0, max(max(self._rx, default=0.0), max(self._tx, default=0.0)) * 1.2)

        # Center 0 KB/s datum axis
        cr.set_source_rgba(0.55, 0.60, 0.90, 0.45)
        cr.set_line_width(1.2)
        cr.move_to(pad_l, mid_y)
        cr.line_to(w - pad_r, mid_y)
        cr.stroke()

        for sign, tag in ((-1.0, f"+{peak:.0f}"), (1.0, f"-{peak:.0f}")):
            y = mid_y + sign * half_h
            cr.set_source_rgba(0.51, 0.55, 0.97, 0.16)
            cr.set_line_width(1.0)
            cr.move_to(pad_l, y); cr.line_to(w - pad_r, y); cr.stroke()
            cr.set_source_rgba(0.70, 0.78, 0.92, 0.80)
            cr.set_font_size(9.5)
            cr.move_to(4, y + 3)
            cr.show_text(f"{tag} KB/s")

        cr.set_source_rgba(0.13, 0.83, 0.93, 0.90)
        cr.set_font_size(10.0)
        cr.move_to(pad_l + 6, pad_t + 12)
        cr.show_text("RX DOWNLINK (UPWARD)")
        cr.set_source_rgba(0.98, 0.75, 0.14, 0.90)
        cr.move_to(pad_l + 6, h - pad_b - 4)
        cr.show_text("TX UPLINK (DOWNWARD)")

        # RX upward
        if len(self._rx) >= 2:
            n = len(self._rx)
            pts = [(pad_l + (i / (n - 1)) * cw, mid_y - half_h * min(1.0, v / peak)) for i, v in enumerate(self._rx)]
            grad = cairo.LinearGradient(0, mid_y - half_h, 0, mid_y)
            grad.add_color_stop_rgba(0.0, 0.13, 0.83, 0.93, 0.42)
            grad.add_color_stop_rgba(1.0, 0.13, 0.83, 0.93, 0.04)
            cr.set_source(grad)
            cr.move_to(pts[0][0], mid_y)
            for x, y in pts:
                cr.line_to(x, y)
            cr.line_to(pts[-1][0], mid_y)
            cr.close_path(); cr.fill()

            cr.set_source_rgba(0.13, 0.83, 0.93, 0.98)
            cr.set_line_width(2.2)
            cr.move_to(pts[0][0], pts[0][1])
            for x, y in pts[1:]:
                cr.line_to(x, y)
            cr.stroke()

        # TX downward
        if len(self._tx) >= 2:
            n = len(self._tx)
            pts = [(pad_l + (i / (n - 1)) * cw, mid_y + half_h * min(1.0, v / peak)) for i, v in enumerate(self._tx)]
            grad = cairo.LinearGradient(0, mid_y, 0, mid_y + half_h)
            grad.add_color_stop_rgba(0.0, 0.98, 0.75, 0.14, 0.04)
            grad.add_color_stop_rgba(1.0, 0.98, 0.75, 0.14, 0.40)
            cr.set_source(grad)
            cr.move_to(pts[0][0], mid_y)
            for x, y in pts:
                cr.line_to(x, y)
            cr.line_to(pts[-1][0], mid_y)
            cr.close_path(); cr.fill()

            cr.set_source_rgba(0.98, 0.75, 0.14, 0.96)
            cr.set_line_width(2.0)
            cr.move_to(pts[0][0], pts[0][1])
            for x, y in pts[1:]:
                cr.line_to(x, y)
            cr.stroke()


class NetWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application) -> None:
        super().__init__(application=app, title="NetPulse BPF", default_width=1120, default_height=730)
        self._busy = False
        self._sample_ms = 140
        self._peak_rx = 0.0
        self._peak_tx = 0.0

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(root)

        hb = Adw.HeaderBar(title_widget=Adw.WindowTitle(title="NetPulse BPF", subtitle="Packet Pipeline • Mirrored RX/TX • Process Sockets"))
        win_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._wbtns: dict[int, Gtk.Button] = {}
        for ms in (80, 140, 320):
            b = Gtk.Button(label=f"{ms}ms")
            b.add_css_class("win-btn")
            if ms == self._sample_ms:
                b.add_css_class("win-active")
            b.connect("clicked", self._set_window, ms)
            win_box.append(b)
            self._wbtns[ms] = b
        hb.pack_end(win_box)
        root.append(hb)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=12, margin_bottom=14, margin_start=16, margin_end=16)
        root.append(body)

        # Top Kernel Packet Pipeline Banner (replaces 4 hero cards)
        pw = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        pw.add_css_class("pipe-wrap")
        self.pipeline = KernelPipelineBanner()
        pw.append(self.pipeline)
        body.append(pw)

        # Asymmetric Split: Left (7 cols) Mirrored Waveform + Counters | Right (5 cols) SNMP & Sockets
        split = Gtk.Grid(column_spacing=12, row_spacing=12, column_homogeneous=True, vexpand=True)

        left = self._card("Mirrored RX / TX Throughput Waveform", "Cyan (Top): Downlink RX KB/s  •  Gold (Bottom): Uplink TX KB/s")
        self.chart = ButterflyThroughputChart()
        left.append(self.chart)

        strip = Gtk.Grid(column_spacing=8, column_homogeneous=True, margin_top=6)
        self.live_kv: dict[str, Gtk.Label] = {}
        for idx, (k, title) in enumerate([
            ("rx", "LIVE RX"),
            ("rx_pk", "PEAK RX"),
            ("tx", "LIVE TX"),
            ("tx_pk", "PEAK TX"),
            ("drop", "RX DROPPED"),
        ]):
            sp = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            sp.add_css_class("stat-pill")
            kl = Gtk.Label(label=title, xalign=0.0); kl.add_css_class("sk")
            vl = Gtk.Label(label="--", xalign=0.0); vl.add_css_class("sv")
            sp.append(kl); sp.append(vl)
            strip.attach(sp, idx, 0, 1, 1)
            self.live_kv[k] = vl
        left.append(strip)

        right = self._card("SNMP Counters & Active Socket Holders", "From /proc/net/snmp and /proc/[pid]/fd descriptors")
        snmp_bar = Gtk.Grid(column_spacing=8, column_homogeneous=True)
        self.snmp_kv: dict[str, Gtk.Label] = {}
        for idx, (k, title) in enumerate([
            ("estab", "TCP ESTAB"),
            ("retrans", "RETRANS RATE"),
            ("bpf", "BPF OBJECT"),
        ]):
            sp = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            sp.add_css_class("stat-pill")
            kl = Gtk.Label(label=title, xalign=0.0); kl.add_css_class("sk")
            vl = Gtk.Label(label="—", xalign=0.0); vl.add_css_class("mono")
            sp.append(kl); sp.append(vl)
            snmp_bar.attach(sp, idx, 0, 1, 1)
            self.snmp_kv[k] = vl
        right.append(snmp_bar)

        self.rows = []
        for i in range(6):
            r = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            r.add_css_class("row")
            h = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            nl = Gtk.Label(label=f"#{i + 1} Scanning...", xalign=0.0, hexpand=True); nl.add_css_class("mono")
            vl = Gtk.Label(label="0 sockets", xalign=1.0); vl.add_css_class("ss")
            pb = Gtk.ProgressBar()
            h.append(nl); h.append(vl)
            r.append(h); r.append(pb)
            right.append(r)
            self.rows.append((nl, vl, pb))

        split.attach(left, 0, 0, 7, 1)
        split.attach(right, 7, 0, 5, 1)
        body.append(split)

        GLib.timeout_add(140, self._warmup_tick)
        GLib.timeout_add(450, self._warmup_tick)
        GLib.timeout_add(850, self._warmup_tick)
        GLib.timeout_add(1500, self._tick)

    def _set_window(self, _btn, ms: int) -> None:
        self._sample_ms = ms
        for k, b in self._wbtns.items():
            b.remove_css_class("win-active")
            if k == ms:
                b.add_css_class("win-active")
        self._refresh()

    def _card(self, t: str, s: str) -> Gtk.Box:
        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        b.add_css_class("n-card")
        tl = Gtk.Label(label=t, xalign=0.0); tl.add_css_class("st")
        sl = Gtk.Label(label=s, xalign=0.0); sl.add_css_class("ss")
        b.append(tl); b.append(sl)
        return b

    def _warmup_tick(self) -> bool:
        self._refresh()
        return GLib.SOURCE_REMOVE

    def _tick(self) -> bool:
        self._refresh()
        return GLib.SOURCE_CONTINUE

    def _refresh(self) -> None:
        if self._busy:
            return
        self._busy = True
        ms = self._sample_ms

        def _worker():
            try:
                data = sample_network(ms)
            except Exception:
                data = None

            def _apply():
                self._busy = False
                if not data:
                    return GLib.SOURCE_REMOVE

                rx = float(data.get("rx_kbps", 0.0))
                tx = float(data.get("tx_kbps", 0.0))
                self._peak_rx = max(self._peak_rx, rx)
                self._peak_tx = max(self._peak_tx, tx)

                self.pipeline.update(
                    str(data.get("iface", "lo")),
                    str(data.get("qdisc", "fq")),
                    str(data.get("tcp_cc", "bbr")),
                    bool(data.get("bpf_ready", False)),
                    str(data.get("health", "LOW_LATENCY_OPTIMAL")),
                )
                self.chart.push(rx, tx)

                self.live_kv["rx"].set_label(f"{rx:.1f} KB/s")
                self.live_kv["rx_pk"].set_label(f"{self._peak_rx:.1f} KB/s")
                self.live_kv["tx"].set_label(f"{tx:.1f} KB/s")
                self.live_kv["tx_pk"].set_label(f"{self._peak_tx:.1f} KB/s")
                self.live_kv["drop"].set_label(str(data.get("rx_dropped", 0)))

                self.snmp_kv["estab"].set_label(str(data.get("tcp_estab", 0)))
                self.snmp_kv["retrans"].set_label(f"{float(data.get('retrans_pct', 0.0)):.3f}%")
                bpf_obj = ROOT / "bpf" / "sock_rtt.bpf.o"
                self.snmp_kv["bpf"].set_label(f"Ready ({bpf_obj.stat().st_size // 1024} KB)" if bpf_obj.exists() else "Missing")

                socks = data.get("top_sockets", [])
                top_s = max(1, max((int(x.get("sockets", 0)) for x in socks), default=1))
                for idx, (nl, vl, pb) in enumerate(self.rows):
                    if idx < len(socks):
                        sp = socks[idx]
                        sc = int(sp.get("sockets", 0))
                        nl.set_label(f"#{idx + 1} {sp['name']} (PID {sp['pid']})")
                        vl.set_label(f"{sc} sockets")
                        pb.set_fraction(min(1.0, max(0.04, sc / top_s)))
                    else:
                        nl.set_label(f"#{idx + 1} Idle")
                        vl.set_label("—")
                        pb.set_fraction(0.0)
                return GLib.SOURCE_REMOVE

            GLib.idle_add(_apply)

        threading.Thread(target=_worker, daemon=True).start()


class NetApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="com.lwrlock.NetPulse")

    def do_activate(self):
        p = Gtk.CssProvider()
        p.load_from_data(NET_CSS)
        d = Gdk.Display.get_default()
        if d:
            Gtk.StyleContext.add_provider_for_display(d, p, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        win = self.props.active_window or NetWindow(self)
        win.present()


def main() -> int:
    return NetApp().run(None)


if __name__ == "__main__":
    raise SystemExit(main())
