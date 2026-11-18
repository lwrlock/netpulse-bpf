from __future__ import annotations

import os
import threading
from collections import deque

os.environ.setdefault("GSK_RENDERER", "gl")

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk

from .monitor import sample_network

NET_CSS = b"""
window, window.background, AdwApplicationWindow {
    background-color: #080a16;
    background-image: radial-gradient(circle at 20% 15%, rgba(99, 102, 241, 0.16), transparent 48%),
                      radial-gradient(circle at 82% 85%, rgba(251, 191, 36, 0.11), transparent 46%);
    color: #eef2ff;
}
headerbar, AdwHeaderBar {
    background: rgba(11, 14, 30, 0.92);
    border-bottom: 1px solid rgba(129, 140, 248, 0.25);
    color: #eef2ff;
}
.n-card {
    background: rgba(14, 17, 36, 0.94);
    border: 1px solid rgba(129, 140, 248, 0.22);
    border-radius: 16px;
    padding: 15px 18px;
}
.n-hero {
    background: rgba(17, 21, 44, 0.95);
    border: 1px solid rgba(165, 180, 252, 0.28);
    border-radius: 15px;
    padding: 14px 16px;
}
.hk { font-size: 10.5px; font-weight: 700; color: #818cf8; letter-spacing: 0.7px; }
.hv { font-size: 24px; font-weight: 800; color: #f8fafc; }
.hs { font-size: 11.5px; color: #94a3b8; }
.st { font-size: 14px; font-weight: 700; color: #eef2ff; }
.ss { font-size: 11.5px; color: #94a3b8; }
.row { padding: 6px 0; border-bottom: 1px solid rgba(255, 255, 255, 0.06); }
"""


class ThroughputChart(Gtk.DrawingArea):
    """Dual RX (Indigo) / TX (Gold) live network waveform."""

    def __init__(self) -> None:
        super().__init__()
        self.set_size_request(-1, 175)
        self.set_hexpand(True)
        self._rx: deque[float] = deque(maxlen=50)
        self._tx: deque[float] = deque(maxlen=50)
        self.set_draw_func(self._draw)

    def push(self, rx_kbps: float, tx_kbps: float) -> None:
        self._rx.append(rx_kbps)
        self._tx.append(tx_kbps)
        self.queue_draw()

    def _draw(self, _a, cr: cairo.Context, w: int, h: int) -> None:
        pad_l, pad_r, pad_t, pad_b = 46.0, 14.0, 14.0, 24.0
        cw = max(20.0, w - pad_l - pad_r)
        ch = max(20.0, h - pad_t - pad_b)
        cr.set_source_rgba(0.04, 0.05, 0.11, 0.90)
        cr.rectangle(0, 0, w, h)
        cr.fill()

        peak = max(16.0, max(max(self._rx, default=0.0), max(self._tx, default=0.0)) * 1.2)
        for f in (0.0, 0.5, 1.0):
            y = pad_t + ch * (1.0 - f)
            cr.set_source_rgba(0.51, 0.55, 0.97, 0.14)
            cr.set_line_width(1.0)
            cr.move_to(pad_l, y); cr.line_to(w - pad_r, y); cr.stroke()
            cr.set_source_rgba(0.65, 0.70, 0.86, 0.8)
            cr.set_font_size(9.5)
            cr.move_to(4, y + 3)
            cr.show_text(f"{peak * f:.0f} KB/s")

        if len(self._rx) >= 2:
            n = len(self._rx)
            pts = [(pad_l + (i / (n - 1)) * cw, pad_t + ch * (1.0 - min(1.0, v / peak))) for i, v in enumerate(self._rx)]
            grad = cairo.LinearGradient(0, pad_t, 0, pad_t + ch)
            grad.add_color_stop_rgba(0.0, 0.51, 0.55, 0.97, 0.38)
            grad.add_color_stop_rgba(1.0, 0.51, 0.55, 0.97, 0.02)
            cr.set_source(grad)
            cr.move_to(pts[0][0], pad_t + ch)
            for x, y in pts:
                cr.line_to(x, y)
            cr.line_to(pts[-1][0], pad_t + ch)
            cr.close_path(); cr.fill()

            cr.set_source_rgba(0.51, 0.55, 0.97, 0.96)
            cr.set_line_width(2.2)
            cr.move_to(pts[0][0], pts[0][1])
            for x, y in pts[1:]:
                cr.line_to(x, y)
            cr.stroke()

        if len(self._tx) >= 2:
            n = len(self._tx)
            cr.set_source_rgba(0.98, 0.75, 0.14, 0.90)
            cr.set_line_width(1.8)
            for i, v in enumerate(self._tx):
                x = pad_l + (i / (n - 1)) * cw
                y = pad_t + ch * (1.0 - min(1.0, v / peak))
                cr.move_to(x, y) if i == 0 else cr.line_to(x, y)
            cr.stroke()


class NetWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application) -> None:
        super().__init__(application=app, title="NetPulse BPF", default_width=1080, default_height=740)
        self._busy = False
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(root)
        root.append(Adw.HeaderBar(title_widget=Adw.WindowTitle(title="NetPulse BPF", subtitle="eBPF sock_ops RTT • TCP BBR Congestion & Socket Throughput")))

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, margin_top=14, margin_bottom=16, margin_start=18, margin_end=18)
        root.append(body)

        hero = Gtk.Grid(column_spacing=12, row_spacing=12, column_homogeneous=True)
        c1, self.h_rate, self.h_rate_s = self._hero("DOWNLINK RX", "-- KB/s", "TX: -- KB/s")
        c2, self.h_bbr, self.h_bbr_s = self._hero("TCP CONGESTION", "bbr", "qdisc: fq")
        c3, self.h_ret, self.h_ret_s = self._hero("RETRANSMIT RATE", "0.00%", "SNMP Estab: 0")
        c4, self.h_stat, self.h_stat_s = self._hero("LINK HEALTH", "OPTIMAL", "sock_ops eBPF Ready")
        for i, c in enumerate((c1, c2, c3, c4)):
            hero.attach(c, i, 0, 1, 1)
        body.append(hero)

        mid = Gtk.Grid(column_spacing=14, row_spacing=14, column_homogeneous=True)
        left = self._card("Live RX / TX Throughput Waveform", "Indigo: Downlink (RX) • Gold: Uplink (TX) over active interface")
        self.chart = ThroughputChart()
        left.append(self.chart)
        self.iface_lbl = Gtk.Label(label="Interface: probing...", xalign=0.0)
        self.iface_lbl.add_css_class("ss")
        left.append(self.iface_lbl)

        right = self._card("Top Active Socket Holders", "Per-process open network socket descriptors (/proc/[pid]/fd)")
        self.rows = []
        for i in range(6):
            r = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            r.add_css_class("row")
            nl = Gtk.Label(label=f"#{i + 1} Scanning...", xalign=0.0, hexpand=True)
            vl = Gtk.Label(label="—", xalign=1.0)
            vl.add_css_class("ss")
            r.append(nl); r.append(vl)
            right.append(r)
            self.rows.append((nl, vl))

        mid.attach(left, 0, 0, 1, 1)
        mid.attach(right, 1, 0, 1, 1)
        body.append(mid)

        GLib.timeout_add(1600, self._tick)
        self._refresh()

    def _hero(self, k: str, v: str, s: str):
        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        b.add_css_class("n-hero")
        kl = Gtk.Label(label=k, xalign=0.0); kl.add_css_class("hk")
        vl = Gtk.Label(label=v, xalign=0.0); vl.add_css_class("hv")
        sl = Gtk.Label(label=s, xalign=0.0, ellipsize=3); sl.add_css_class("hs")
        b.append(kl); b.append(vl); b.append(sl)
        return b, vl, sl

    def _card(self, t: str, s: str) -> Gtk.Box:
        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        b.add_css_class("n-card")
        tl = Gtk.Label(label=t, xalign=0.0); tl.add_css_class("st")
        sl = Gtk.Label(label=s, xalign=0.0); sl.add_css_class("ss")
        b.append(tl); b.append(sl)
        return b

    def _tick(self) -> bool:
        self._refresh()
        return GLib.SOURCE_CONTINUE

    def _refresh(self) -> None:
        if self._busy:
            return
        self._busy = True

        def _worker():
            try:
                data = sample_network(140)
            except Exception:
                data = None

            def _apply():
                self._busy = False
                if not data:
                    return GLib.SOURCE_REMOVE
                rx = float(data.get("rx_kbps", 0.0))
                tx = float(data.get("tx_kbps", 0.0))
                self.h_rate.set_label(f"{rx:.1f} KB/s")
                self.h_rate_s.set_label(f"Uplink TX: {tx:.1f} KB/s")
                self.h_bbr.set_label(str(data.get("tcp_cc", "bbr")).upper())
                self.h_bbr_s.set_label(f"qdisc: {data.get('qdisc', 'fq')} • {data.get('iface', 'lo')}")
                self.h_ret.set_label(f"{float(data.get('retrans_pct', 0.0)):.3f}%")
                self.h_ret_s.set_label(f"Estab: {data.get('tcp_estab', 0)} • Drop: {data.get('rx_dropped', 0)}")
                self.h_stat.set_label(str(data.get("health", "OPTIMAL")).replace("_", " ").title())
                self.h_stat_s.set_label("eBPF sock_ops compiled" if data.get("bpf_ready") else "Kernel SNMP mode")

                self.chart.push(rx, tx)
                self.iface_lbl.set_label(f"Active NIC: {data.get('iface', '?')} • TCP {data.get('tcp_cc', 'bbr')} / {data.get('qdisc', 'fq')}")
                socks = data.get("top_sockets", [])
                for idx, (nl, vl) in enumerate(self.rows):
                    if idx < len(socks):
                        sp = socks[idx]
                        nl.set_label(f"{sp['name']} (PID {sp['pid']})")
                        vl.set_label(f"{sp['sockets']} sockets")
                    else:
                        nl.set_label(f"#{idx + 1} Idle"); vl.set_label("—")
                return GLib.SOURCE_REMOVE

            GLib.idle_add(_apply)

        threading.Thread(target=_worker, daemon=True).start()


class NetApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="com.lwrlock.NetPulse")

    def do_activate(self):
        p = Gtk.CssProvider(); p.load_from_data(NET_CSS)
        d = Gdk.Display.get_default()
        if d:
            Gtk.StyleContext.add_provider_for_display(d, p, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        win = self.props.active_window or NetWindow(self)
        win.present()


def main() -> int:
    return NetApp().run(None)


if __name__ == "__main__":
    raise SystemExit(main())
