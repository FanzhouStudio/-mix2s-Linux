#!/usr/bin/python3
"""Show the phone's LAN-only 1Panel address without starting a browser."""

from ipaddress import ip_address, ip_network
from pathlib import Path
import subprocess

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gtk  # noqa: E402


LAN = ip_network("192.168.3.0/24")
ENTRANCE = Path.home() / ".config/polaris-1panel/entrance"


def panel_url():
    address = subprocess.check_output(
        ["ip", "-4", "-o", "addr", "show", "dev", "wlan0"], text=True
    ).split()[3].split("/")[0]
    if ip_address(address) not in LAN:
        raise ValueError("请先连接家里的 192.168.3.x Wi-Fi")
    path = ENTRANCE.read_text(encoding="utf-8").strip().strip("/")
    if not path or not path.isalnum():
        raise ValueError("1Panel 安全入口配置无效")
    return f"http://{address}:10086/{path}"


class PanelLauncher(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="local.polaris.panel_launcher")

    def do_activate(self):
        window = Gtk.ApplicationWindow(application=self, title="1Panel 内网访问")
        window.set_default_size(480, 230)
        layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        for side in ("top", "bottom", "start", "end"):
            getattr(layout, f"set_margin_{side}")(20)
        window.set_child(layout)

        try:
            url = panel_url()
            message = "面板正在手机上运行。可在同一 Wi-Fi 的电脑或平板浏览器打开："
        except (OSError, IndexError, ValueError, subprocess.CalledProcessError) as exc:
            url = ""
            message = f"暂时无法生成访问地址：{exc}"

        label = Gtk.Label(label=message, wrap=True, xalign=0)
        layout.append(label)
        if url:
            address = Gtk.Entry(text=url, editable=False, hexpand=True)
            layout.append(address)

            buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            layout.append(buttons)
            copy = Gtk.Button(label="复制地址")
            copy.connect(
                "clicked", lambda _button: Gdk.Display.get_default().get_clipboard().set(url)
            )
            buttons.append(copy)

            # Firefox has previously frozen this phone. Opening it is an explicit choice.
            open_here = Gtk.Button(label="在手机浏览器打开（可能卡住）")
            open_here.connect("clicked", lambda _button: subprocess.Popen(["xdg-open", url]))
            buttons.append(open_here)

        window.present()


PanelLauncher().run()
