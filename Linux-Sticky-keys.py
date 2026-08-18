#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Linux 粘滞键 - 修正版（带调试）
- 正确映射所有字母数字键
- 特殊键映射（空格、回车、退格等）
- 调试输出所有事件和发送的命令
- 无 grab，无 uinput，使用 xdotool
- Shift 五次切换启用/禁用
- 退出：Ctrl+Shift+Q
用法：sudo python3 sticky_fixed.py
"""

import sys
import threading
import time
import os
import subprocess
from collections import deque

try:
    from evdev import InputDevice, categorize, ecodes, list_devices, KeyEvent
except ImportError:
    print("错误：请安装 evdev：pip install evdev")
    sys.exit(1)

try:
    import tkinter as tk
    from tkinter import messagebox
except ImportError:
    print("错误：请安装 tkinter")
    sys.exit(1)

# ==================== 映射 ====================
MOD_GROUPS = {
    'ctrl': (29, 97),
    'shift': (42, 54),
    'alt': (56, 100),
    'win': (125, 126),
}
CODE_TO_GROUP = {}
for g, codes in MOD_GROUPS.items():
    for c in codes:
        CODE_TO_GROUP[c] = g

XDOTOOL_MOD = {'ctrl': 'ctrl', 'shift': 'shift', 'alt': 'alt', 'win': 'super'}

# 特殊键（非字母数字）的 xdotool 名称
SPECIAL_KEYS = {
    28: 'Return',    # Enter
    57: 'space',     # Space
    15: 'Tab',
    14: 'BackSpace',
    111: 'Delete',
    1: 'Escape',
    102: 'Home',
    107: 'End',
    108: 'Page_Up',
    109: 'Page_Down',
    110: 'Insert',
    103: 'Up', 104: 'Down', 105: 'Left', 106: 'Right',
    59: 'F1', 60: 'F2', 61: 'F3', 62: 'F4',
    63: 'F5', 64: 'F6', 65: 'F7', 66: 'F8',
    67: 'F9', 68: 'F10', 87: 'F11', 88: 'F12',
}

# ==================== 引擎 ====================

class StickyEngine:
    def __init__(self):
        self.enabled = False
        self.mod_state = {g: 'off' for g in MOD_GROUPS}
        self.last_press_time = {}
        self.shift_times = deque(maxlen=5)
        self.shift_triggered = False

        self.running = True
        self.device = None

        self.ctrl_down = False
        self.shift_down = False

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.on_shift_quintuple = None

    def get_group(self, code):
        return CODE_TO_GROUP.get(code)

    def is_modifier(self, code):
        return code in CODE_TO_GROUP

    def get_active_mods(self):
        return [g for g, s in self.mod_state.items() if s in ('sticky', 'locked')]

    def toggle_mod_state(self, group):
        s = self.mod_state[group]
        if s == 'off':
            self.mod_state[group] = 'sticky'
        elif s == 'sticky':
            self.mod_state[group] = 'locked'
        else:
            self.mod_state[group] = 'off'

    def clear_sticky(self):
        for g in self.mod_state:
            if self.mod_state[g] == 'sticky':
                self.mod_state[g] = 'off'

    def get_key_name(self, key):
        """从 evdev Key 对象获取 xdotool 键名"""
        code = key.scancode
        # 检查特殊键
        if code in SPECIAL_KEYS:
            return SPECIAL_KEYS[code]
        # 尝试从 key.keycode 提取
        name = key.keycode
        if name.startswith('KEY_'):
            name = name[4:].lower()
            # 如果是单个字母或数字，直接使用
            if len(name) == 1 and name.isalnum():
                return name
            # 处理其他如 KEY_F1 等，但已经映射
        # 如果无法识别，返回 None
        return None

    def send_combo(self, mods, key_name):
        """发送组合键"""
        mod_str = '+'.join(XDOTOOL_MOD[m] for m in mods)
        cmd = f"xdotool key {mod_str}+{key_name}"
        print(f"   发送组合键: {mod_str}+{key_name}  (cmd: {cmd})")
        try:
            subprocess.run(cmd, shell=True, check=False, capture_output=True)
        except Exception as e:
            print(f"   xdotool 错误: {e}")

    def event_loop(self):
        devs = [InputDevice(p) for p in list_devices()]
        self.device = None
        for d in devs:
            if 'keyboard' in d.name.lower():
                self.device = d
                break
        if not self.device:
            for d in devs:
                if ecodes.EV_KEY in d.capabilities():
                    self.device = d
                    break
        if not self.device:
            print("错误：未找到键盘设备")
            self.root.after(0, self.quit)
            return
        print(f"[{time.time():.3f}] 使用设备: {self.device.path} - {self.device.name}")

        for event in self.device.read_loop():
            if not self.running:
                break
            if event.type != ecodes.EV_KEY:
                continue
            key = categorize(event)
            code = key.scancode
            pressed = (key.keystate == KeyEvent.key_down)
            group = self.get_group(code)

            # 物理状态
            if code in (29, 97):
                self.ctrl_down = pressed
            if code in (42, 54):
                self.shift_down = pressed

            # 退出热键（物理 Ctrl+Shift+Q）
            if pressed and self.ctrl_down and self.shift_down and code == 16:
                print(f"[{time.time():.3f}] !!! 退出热键触发 !!!")
                self.root.after(0, self.quit)
                break

            # Shift 五次检测（只针对 Shift 键）
            if code in (42, 54) and pressed:
                now = time.time()
                while self.shift_times and now - self.shift_times[0] > 2.5:
                    self.shift_times.popleft()
                self.shift_times.append(now)
                cnt = len(self.shift_times)
                if cnt >= 2:
                    interval = now - self.shift_times[-2]
                    print(f"[{time.time():.3f}]   Shift 计数: {cnt}/5 (间隔 {interval:.2f}s)")
                else:
                    print(f"[{time.time():.3f}]   Shift 计数: {cnt}/5")
                if cnt >= 5 and not self.shift_triggered:
                    self.shift_triggered = True
                    print(f"[{time.time():.3f}]   >>> 五次 Shift 触发！")
                    if self.on_shift_quintuple:
                        self.root.after(0, self.on_shift_quintuple)
                    self.shift_times.clear()
                    threading.Timer(2.0, lambda: setattr(self, 'shift_triggered', False)).start()

            # 调试输出
            key_name_dbg = key.keycode
            group_str = f" group={group}" if group else " group=None"
            print(f"[{time.time():.3f}] 事件: code={code:3d} {key_name_dbg:12s} {'按下' if pressed else '释放'}{group_str}")

            if not self.enabled:
                # 未启用时，只记录，不处理粘滞键
                continue

            # ----- 修饰键处理 -----
            if group:
                if pressed:
                    now = time.time()
                    last = self.last_press_time.get(group, 0)
                    self.last_press_time[group] = now
                    if now - last < 0.3 and self.mod_state[group] == 'sticky':
                        self.toggle_mod_state(group)
                        print(f"[{time.time():.3f}]   修饰键 {group} 状态变为: locked (双击锁定)")
                    else:
                        self.toggle_mod_state(group)
                        print(f"[{time.time():.3f}]   修饰键 {group} 状态变为: {self.mod_state[group]}")
                continue

            # ----- 普通键 -----
            if pressed:
                # 获取键名
                key_name = self.get_key_name(key)
                if not key_name:
                    print(f"[{time.time():.3f}]   无法识别键码 {code}，忽略")
                    continue

                active = self.get_active_mods()
                if active:
                    print(f"[{time.time():.3f}]   激活修饰键: {active}")
                    self.send_combo(active, key_name)
                    self.clear_sticky()
                    print(f"[{time.time():.3f}]   清除粘滞: {', '.join([g for g in self.mod_state if self.mod_state[g]=='off'])}")
                else:
                    print(f"[{time.time():.3f}]   普通键 {key_name} 无激活修饰键，透传")

        self.device.close()

    def toggle_enable(self, enable):
        self.enabled = enable
        print(f"[{time.time():.3f}] 粘滞键 {'启用' if enable else '禁用'}")
        print('\a', end='', flush=True)
        if not enable:
            for g in self.mod_state:
                self.mod_state[g] = 'off'

    def quit(self):
        self.running = False
        self.root.quit()
        self.root.destroy()

    def run(self):
        t = threading.Thread(target=self.event_loop, daemon=True)
        t.start()

        print("粘滞键已启动（默认禁用），调试日志已开启")
        print("快速按五次 Shift（2.5秒内）切换启用/禁用")
        print("启用后：单击修饰键粘滞，双击锁定")
        print("退出：按住 Ctrl+Shift，再按 Q")

        def on_shift_quintuple():
            if self.enabled:
                if messagebox.askyesno("粘滞键", "粘滞键当前已启用，是否禁用？"):
                    self.toggle_enable(False)
                    print("粘滞键已禁用")
            else:
                if messagebox.askyesno("粘滞键", "是否启用粘滞键？\n（单击修饰键粘滞，双击锁定）"):
                    self.toggle_enable(True)
                    print("粘滞键已启用")

        self.on_shift_quintuple = on_shift_quintuple

        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            pass
        finally:
            self.running = False
            if self.device:
                self.device.close()
            print("粘滞键已退出")

def main():
    if os.geteuid() != 0:
        print("错误：必须以 root 权限运行")
        sys.exit(1)
    engine = StickyEngine()
    engine.run()

if __name__ == '__main__':
    main()