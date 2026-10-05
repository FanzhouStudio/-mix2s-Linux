import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import * as Keyboard from 'resource:///org/gnome/shell/ui/keyboard.js';
import {Extension, InjectionManager} from 'resource:///org/gnome/shell/extensions/extension.js';

const XML = `<node><interface name="org.gnome.Mutter.DisplayConfig">
<property name="PowerSaveMode" type="i" access="readwrite"/>
</interface></node>`;
const DisplayProxy = Gio.DBusProxy.makeProxyWrapper(XML);
const TOUCH_NAME = 'org.polaris.TouchWake1';

export default class PolarisTouchControls extends Extension {
    enable() {
        this._alive = true;
        this._wakeTime = 0;
        this._wakeFromBlankTime = 0;
        this._blankPending = false;
        this._lastGesture = 0;
        this._moonLastPress = 0;
        this._moonTimer = 0;
        this._suppressWakeUntil = 0;
        this._transform = null;
        this._injections = new InjectionManager();
        this._injections.overrideMethod(Keyboard.KeyboardManager.prototype,
            'maybeHandleEvent', original => function (event) {
                if (!global.stage.get_event_actor(event))
                    return false;
                return original.call(this, event);
            });
        this._updateTransform();
        this._monitorsId = Main.layoutManager.connect('monitors-changed', () => this._updateTransform());
        this._proxy = new DisplayProxy(Gio.DBus.session,
            'org.gnome.Mutter.DisplayConfig', '/org/gnome/Mutter/DisplayConfig',
            (proxy, error) => {
                if (error || !this._alive)
                    return;
                this._propertiesId = proxy.connect('g-properties-changed', () => {
                    const now = GLib.get_monotonic_time() / 1000;
                    if (proxy.PowerSaveMode > 0) {
                        this._blankPending = true;
                    } else if (proxy.PowerSaveMode === 0) {
                        this._wakeTime = now;
                        if (this._blankPending)
                            this._wakeFromBlankTime = now;
                        this._blankPending = false;
                    }
                });
            });
        this._button = new PanelMenu.Button(0.0, '锁屏并息屏', false);
        this._button.add_child(new St.Icon({
            icon_name: 'weather-clear-night-symbolic', style_class: 'system-status-icon',
        }));
        const item = new PopupMenu.PopupMenuItem('锁屏并息屏（也可双击月亮）');
        item.connect('activate', () => this._blank());
        this._button.menu.addMenuItem(item);
        Main.panel.addToStatusArea(this.uuid, this._button);
        // Delay the single-tap menu until a second tap has had time to arrive.
        // Opening its modal menu on the first press can swallow the second tap.
        this._button._clickGesture.set_enabled(false);
        this._moonClickGesture = new Clutter.ClickGesture();
        this._moonClickGesture.connect('recognize', () => {
            const now = GLib.get_monotonic_time() / 1000;
            if (this._moonTimer && now - this._moonLastPress < 600) {
                GLib.Source.remove(this._moonTimer);
                this._moonTimer = 0;
                this._moonLastPress = 0;
                this._blank();
                console.log('Polaris native moon double tap recognized');
            } else {
                this._moonLastPress = now;
                if (this._moonTimer)
                    GLib.Source.remove(this._moonTimer);
                this._moonTimer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 600, () => {
                    this._moonTimer = 0;
                    if (this._alive && !Main.screenShield.locked)
                        this._button.menu.toggle();
                    return GLib.SOURCE_REMOVE;
                });
            }
        });
        this._button.add_action(this._moonClickGesture);
        this._touchId = Gio.DBus.session.signal_subscribe(TOUCH_NAME, TOUCH_NAME,
            'DoubleTap', '/org/polaris/TouchWake1', null, Gio.DBusSignalFlags.NONE,
            (_connection, _sender, _path, _interface, _signal, parameters) => {
                if (!this._alive)
                    return;
                try {
                    this._doubleTap(...parameters.deep_unpack());
                } catch (error) {
                    console.warn(`Polaris gesture: ${error.message}`);
                }
            });
        console.log('Polaris touch controls v4 enabled; raw S3330 gestures; suspend is not used');
    }

    _updateTransform() {
        Gio.DBus.session.call('org.gnome.Mutter.DisplayConfig',
            '/org/gnome/Mutter/DisplayConfig', 'org.gnome.Mutter.DisplayConfig',
            'GetCurrentState', null, null, Gio.DBusCallFlags.NONE, 3000, null,
            (connection, result) => {
                try {
                    const state = connection.call_finish(result).deep_unpack();
                    if (this._alive)
                        this._transform = state[2].find(monitor => monitor[4])?.[3] ?? null;
                } catch (error) {
                    console.warn(`Polaris monitor transform: ${error.message}`);
                }
            });
    }

    _power(mode) {
        // A failed DSI power transition can leave Mutter reporting "on" while
        // the CRTC is actually off. Reasserting mode 0 repairs that mismatch.
        if (mode !== 0 && this._proxy?.PowerSaveMode === mode)
            return;
        Gio.DBus.session.call('org.gnome.Mutter.DisplayConfig',
            '/org/gnome/Mutter/DisplayConfig', 'org.freedesktop.DBus.Properties',
            'Set', new GLib.Variant('(ssv)', ['org.gnome.Mutter.DisplayConfig',
                'PowerSaveMode', new GLib.Variant('i', mode)]),
            null, Gio.DBusCallFlags.NONE, 3000, null,
            (connection, result) => {
                try {
                    connection.call_finish(result);
                } catch (error) {
                    console.warn(`Polaris display control: ${error.message}`);
                }
            });
    }

    _blank() {
        if (this._moonTimer) {
            GLib.Source.remove(this._moonTimer);
            this._moonTimer = 0;
        }
        this._blankPending = true;
        this._suppressWakeUntil = GLib.get_monotonic_time() / 1000 + 1500;
        this._button.menu.close();
        Main.screenShield.lock(false);
        console.log('Polaris GNOME lock/blank requested');
    }

    _point(x, y) {
        const monitor = Main.layoutManager.primaryMonitor;
        if (!monitor || this._transform === null)
            return null;
        // wl_output_transform values; raw coordinates are in native portrait orientation.
        if (this._transform >= 4)
            x = 1 - x;
        switch (this._transform % 4) {
        case 1: [x, y] = [y, 1 - x]; break;
        case 2: [x, y] = [1 - x, 1 - y]; break;
        case 3: [x, y] = [1 - y, x]; break;
        }
        return [monitor.x + x * monitor.width, monitor.y + y * monitor.height];
    }

    _safeSleepPoint(x, y) {
        const actor = global.stage.get_actor_at_pos(Clutter.PickMode.ALL, x, y);
        if (!actor)
            return false;
        if (this._button.contains(actor))
            return true;
        if (!Main.overview.visible && Main.layoutManager._backgroundGroup.contains(actor))
            return true;
        const monitor = Main.layoutManager.primaryMonitor;
        if (y < monitor.y || y > monitor.y + Main.panel.height)
            return false;
        let current = actor;
        while (current && current !== Main.panel) {
            if (current instanceof St.Button || current.has_style_class_name?.('panel-button'))
                return false;
            current = current.get_parent();
        }
        return current === Main.panel;
    }

    _doubleTap(x1, y1, x2, y2, timestamp) {
        const now = GLib.get_monotonic_time() / 1000;
        if (now < this._suppressWakeUntil ||
            Math.abs(now - Number(timestamp)) > 1500 || now - this._lastGesture < 1000)
            return;
        this._lastGesture = now;
        const off = Main.screenShield.locked || this._proxy?.PowerSaveMode > 0 || this._blankPending ||
            now - this._wakeFromBlankTime < 1500;
        if (off) {
            this._blankPending = false;
            this._wakeFromBlankTime = 0;
            this._power(0);
            Main.screenShield._wakeUpScreen();
            // Open the normal password prompt without another curtain swipe.
            if (Main.screenShield.locked)
                Main.screenShield._dialog?.activate();
            console.log('Polaris raw double tap wake requested');
            return;
        }
        if (Main.screenShield.locked || now - this._wakeTime < 1500)
            return;
        const first = this._point(x1, y1);
        const second = this._point(x2, y2);
        if (first && second && this._safeSleepPoint(...first) && this._safeSleepPoint(...second))
            this._blank();
    }

    disable() {
        this._alive = false;
        if (this._moonTimer)
            GLib.Source.remove(this._moonTimer);
        this._moonTimer = 0;
        this._injections?.clear();
        this._injections = null;
        if (this._touchId)
            Gio.DBus.session.signal_unsubscribe(this._touchId);
        if (this._monitorsId)
            Main.layoutManager.disconnect(this._monitorsId);
        if (this._propertiesId)
            this._proxy.disconnect(this._propertiesId);
        this._button?.destroy();
        this._touchId = this._monitorsId = this._propertiesId = 0;
        this._proxy = this._button = null;
    }
}
