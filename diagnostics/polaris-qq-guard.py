#!/usr/bin/python3
"""Prevent accidental QQ launches while this kernel hard-locks in QQ."""

import os
import subprocess

os.environ["GSK_RENDERER"] = "cairo"

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402


class Guard(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="local.polaris.qq_guard")

    def do_activate(self):
        window = Gtk.ApplicationWindow(application=self, title="QQ 启动提示")
        window.set_default_size(440, 220)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(20)
        window.set_child(box)

        box.append(
            Gtk.Label(
                label="QQ 已安装，但在当前 6.1 内核上启动两次都造成整机卡死。"
                "软件渲染也没有解决。请等内核问题修复后再使用。",
                wrap=True,
                xalign=0,
            )
        )
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.append(buttons)
        close = Gtk.Button(label="关闭")
        close.connect("clicked", lambda _button: window.close())
        buttons.append(close)
        launch = Gtk.Button(label="仍要启动（可能整机卡死）")
        launch.connect("clicked", self._launch)
        buttons.append(launch)
        window.present()

    def _launch(self, _button):
        subprocess.Popen(["/usr/local/bin/polaris-qq-safe"])
        self.quit()


Guard().run()
