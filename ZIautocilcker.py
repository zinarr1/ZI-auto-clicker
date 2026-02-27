# Original author: zinarr1

import sys
import time
import threading
import ctypes
from ctypes import wintypes
from PyQt5.QtCore import QEvent
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit,
    QPushButton, QComboBox, QGridLayout
)
from PyQt5.QtGui import QDoubleValidator
from PyQt5.QtGui import QIntValidator
from PyQt5.QtCore import pyqtSlot, Qt, Q_ARG, QMetaObject
from os import _exit
import win32gui
import win32process
import psutil
# ============================================
# WINDOWS / CTYPES SETUP
# ============================================

user32 = ctypes.windll.user32

WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208

WM_XBUTTONDOWN = 0x020B
WM_XBUTTONUP   = 0x020C

XBUTTON1 = 1
XBUTTON2 = 2

MOUSEEVENTF_LEFTDOWN   = 0x0002
MOUSEEVENTF_LEFTUP     = 0x0004
MOUSEEVENTF_RIGHTDOWN  = 0x0008
MOUSEEVENTF_RIGHTUP    = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP   = 0x0040
MOUSEEVENTF_XDOWN      = 0x0080
MOUSEEVENTF_XUP        = 0x0100

LLKHF_INJECTED = 0x10
LLMHF_INJECTED = 0x01

LRESULT = ctypes.c_int64 if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_int32

user32.CallNextHookEx.argtypes = (
    wintypes.HHOOK,
    ctypes.c_int,
    wintypes.WPARAM,
    ctypes.c_void_p
)
user32.CallNextHookEx.restype = LRESULT

# ============================================
# STRUCTS
# ============================================

class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]

class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", wintypes.POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]

# ============================================
# GLOBAL STATE
# ============================================

real_state = {}
listen_mode = None  # "trigger" | "affected"

# ============================================
# AUTOCLICKER
# ============================================

class AutoClicker(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Low-Level Hook ZIAutoClicker")
        self.setMinimumSize(420, 380)

        self.trigger_key = None
        self.affected_key = None
        self.running = False
        self.cps = 15

        self.work_one_window = False
        self.selected_pid = None

        self.timer_running = False
        self.use_timer = False
        self.hold_duration = 1.0
        self.release_duration = 1.0
        self.toggle_timer_running = False
        self.disable_key = None

        self.stop_event = threading.Event()
        self.wake_event = threading.Event()

        # UI
        self.build_ui()
     
        # Worker thread  
        threading.Thread(target=self.worker, daemon=True).start()

        threading.Thread(target=self.hook_thread, daemon=True).start()

    # ---------------- UI ----------------
    def build_ui(self):
        layout = QGridLayout(self)

        layout.addWidget(QLabel("Trigger Key"), 0, 0)
        self.trigger_entry = QLineEdit()
        self.trigger_entry.setReadOnly(True)
        layout.addWidget(self.trigger_entry, 0, 1)
        btn = QPushButton("Select")
        btn.clicked.connect(lambda: self.set_listen("trigger"))
        layout.addWidget(btn, 0, 2)

        layout.addWidget(QLabel("Affected Key"), 1, 0)
        self.affected_entry = QLineEdit()
        self.affected_entry.setReadOnly(True)
        layout.addWidget(self.affected_entry, 1, 1)
        btn = QPushButton("Select")
        btn.clicked.connect(lambda: self.set_listen("affected"))
        layout.addWidget(btn, 1, 2)


        layout.addWidget(QLabel("CPS"), 2, 0)

        self.cps_entry = QLineEdit()
        self.cps_entry.setPlaceholderText("CPS number")
        self.cps_entry.setFixedWidth(60)
        self.cps_entry.setText(str(self.cps))

        validator = QDoubleValidator()
        validator.setNotation(QDoubleValidator.StandardNotation)
        self.cps_entry.setValidator(validator)

        layout.addWidget(self.cps_entry, 2, 1, 1, 2)

        self.cps_entry.textChanged.connect(self.update_cps_from_entry)

        layout.addWidget(QLabel("Affected Mode"), 4, 0)
        self.affected_mode_box = QComboBox()
        self.affected_mode_box.addItems(["Auto-Click", "Hold"])
        self.affected_mode_box.setCurrentText("Auto-Click")
        layout.addWidget(self.affected_mode_box, 4, 1, 1, 2)

        layout.addWidget(QLabel("Trigger Mode"), 3, 0)
        self.trigger_mode_box = QComboBox()
        self.trigger_mode_box.addItems(["Hold", "Toggle"])
        self.trigger_mode_box.setCurrentText("Hold")
        layout.addWidget(self.trigger_mode_box, 3, 1, 1, 2)

        self.disable_checkbox = QtWidgets.QCheckBox("Disable.")
        self.disable_checkbox.setChecked(False)
        layout.addWidget(self.disable_checkbox, 5, 0, 1, 3)

        self.timer_checkbox = QtWidgets.QCheckBox("Enable Timer")
        layout.addWidget(self.timer_checkbox, 6, 0, 1, 3)
        self.timer_checkbox.stateChanged.connect(self.toggle_timer_fields)

        layout.addWidget(QLabel("Disable Key"), 13, 0)

        self.disable_entry = QLineEdit()
        self.disable_entry.setReadOnly(True)
        layout.addWidget(self.disable_entry, 13, 1)

        btn = QPushButton("Select")
        btn.clicked.connect(lambda: self.set_listen("disable"))
        layout.addWidget(btn, 13, 2)

        self.hold_label = QLabel("Hold duration (sec)")
        layout.addWidget(self.hold_label, 7, 0)
        self.hold_entry = QLineEdit("1.0")

        self.hold_entry.setValidator(QDoubleValidator())  
        layout.addWidget(self.hold_entry, 7, 1, 1, 2)

        self.release_label = QLabel("Release duration (sec)")
        layout.addWidget(self.release_label, 8, 0)
        self.release_entry = QLineEdit("1.0")
        self.release_entry.setValidator(QDoubleValidator())  
        layout.addWidget(self.release_entry, 8, 1, 1, 2)

        # ---------------- WORK ONE WINDOW ----------------

        self.work_checkbox = QtWidgets.QCheckBox("Work one window")
        layout.addWidget(self.work_checkbox, 10, 0, 1, 3)

        self.window_combo = QComboBox()
        layout.addWidget(self.window_combo, 11, 0, 1, 3)
        self.refresh_btn = QPushButton("Refresh Windows")
        layout.addWidget(self.refresh_btn, 12, 0, 1, 3)

        self.refresh_btn.clicked.connect(self.refresh_windows)
        self.refresh_windows()
        self.window_combo.currentIndexChanged.connect(self.update_selected_pid)
        self.work_checkbox.stateChanged.connect(self.toggle_window_mode)

        self.reverse_checkbox = QtWidgets.QCheckBox("Reverse time duration order")
        layout.addWidget(self.reverse_checkbox, 9, 0, 1, 3)

        self.hold_label.hide()
        self.hold_entry.hide()
        self.release_label.hide()
        self.release_entry.hide()
        self.reverse_checkbox.hide()

        self.status = QLabel("Ready")
        self.status.setAlignment(Qt.AlignCenter) 
        layout.addWidget(self.status, 99, 0, 1, 3)

        self.installEventFilter(self)
        for w in self.findChildren(QWidget):
            w.installEventFilter(self)

    def enum_handler(self, hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                try:
                    process = psutil.Process(pid)
                    name = process.name()
                    display = f"{name} - {title}"
                    self.window_combo.addItem(display, pid)
                except:
                    pass

    def refresh_windows(self):
        previous_pid = self.selected_pid

        self.window_combo.blockSignals(True)
        self.window_combo.clear()

        win32gui.EnumWindows(self.enum_handler, None)

        self.window_combo.blockSignals(False)

        if previous_pid:
            for i in range(self.window_combo.count()):
                if self.window_combo.itemData(i) == previous_pid:
                    self.window_combo.setCurrentIndex(i)
                    break
    def update_selected_pid(self):
        if self.work_one_window:
            index = self.window_combo.currentIndex()
            if index != -1:
                self.selected_pid = self.window_combo.itemData(index)

    def toggle_window_mode(self):
        self.work_one_window = self.work_checkbox.isChecked()

        if self.work_one_window:
            index = self.window_combo.currentIndex()
            if index != -1:
                self.selected_pid = self.window_combo.itemData(index)
        else:
            self.selected_pid = None

    def update_cps_from_entry(self, text):
        try:
            self.cps = float(text)
        except ValueError:
            self.cps = 0.0
    # ---------------- HOOKS ----------------
    def hook_thread(self):
        self.kb_proc = ctypes.WINFUNCTYPE(
            LRESULT, ctypes.c_int, wintypes.WPARAM, ctypes.c_void_p
        )(self.keyboard_proc)

        self.ms_proc = ctypes.WINFUNCTYPE(
            LRESULT, ctypes.c_int, wintypes.WPARAM, ctypes.c_void_p
        )(self.mouse_proc)

        user32.SetWindowsHookExW(WH_KEYBOARD_LL, self.kb_proc, None, 0)
        user32.SetWindowsHookExW(WH_MOUSE_LL, self.ms_proc, None, 0)

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    # ---------------- CALLBACKS ----------------
    def keyboard_proc(self, nCode, wParam, lParam):
        if nCode == 0:
            info = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents

            if info.flags & LLKHF_INJECTED:
                return user32.CallNextHookEx(0, nCode, wParam, lParam)

            key = f"key.{info.vkCode}"

            # ---- DISABLE HOTKEY ----
            if listen_mode is None and self.disable_key == key and wParam == WM_KEYDOWN:
                self.toggle_disable()
                return 1

            real_state[key] = (wParam == WM_KEYDOWN)
            self.wake_event.set()

            if listen_mode:
                QtCore.QMetaObject.invokeMethod(
                    self,
                    "assign_key",
                    Qt.QueuedConnection,
                    QtCore.Q_ARG(str, key)
                )
                return 0

        return user32.CallNextHookEx(0, nCode, wParam, lParam)

    def mouse_proc(self, nCode, wParam, lParam):
        if nCode == 0:
            info = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents

            if info.flags & LLMHF_INJECTED:
                return user32.CallNextHookEx(0, nCode, wParam, lParam)

            key = None

            down = {
                WM_LBUTTONDOWN: "mouse.left",
                WM_RBUTTONDOWN: "mouse.right",
                WM_MBUTTONDOWN: "mouse.middle",
            }

            up = {
                WM_LBUTTONUP: "mouse.left",
                WM_RBUTTONUP: "mouse.right",
                WM_MBUTTONUP: "mouse.middle",
            }

            # ---------------- NORMAL BUTTONS ----------------
            if wParam in down:
                key = down[wParam]

            elif wParam in up:
                key = up[wParam]

            # ---------------- XBUTTONS ----------------
            elif wParam in (WM_XBUTTONDOWN, WM_XBUTTONUP):

                xbtn = (info.mouseData >> 16) & 0xFFFF

                if xbtn == XBUTTON1:
                    key = "mouse.back"
                elif xbtn == XBUTTON2:
                    key = "mouse.forward"
                else:
                    return user32.CallNextHookEx(0, nCode, wParam, lParam)

            if key is None:
                return user32.CallNextHookEx(0, nCode, wParam, lParam)

            # ---- DISABLE HOTKEY CHECK ----
            if listen_mode is None and self.disable_key == key and wParam in (
                WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_MBUTTONDOWN, WM_XBUTTONDOWN
            ):
                self.toggle_disable()
                return 1

            # ---- LISTEN MODE ----
            if listen_mode:
                QtCore.QMetaObject.invokeMethod(
                    self,
                    "assign_key",
                    Qt.QueuedConnection,
                    QtCore.Q_ARG(str, key)
                )
                return 0

            # ---- STATE UPDATE ----
            if wParam in (WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_MBUTTONDOWN, WM_XBUTTONDOWN):
                real_state[key] = True
            else:
                real_state[key] = False

            self.wake_event.set()

        return user32.CallNextHookEx(0, nCode, wParam, lParam)
    # ---------------- SLOT ----------------
    @pyqtSlot(str)
    def assign_key(self, key):
        global listen_mode

        if listen_mode == "trigger":
            self.trigger_key = key
            self.trigger_entry.setText(key)

        elif listen_mode == "affected":
            self.affected_key = key
            self.affected_entry.setText(key)

        elif listen_mode == "disable":
            self.disable_key = key
            self.disable_entry.setText(key)

        listen_mode = None
        self.status.setText("Assigned")

    # ---------------- WORKER ----------------
    def worker(self):

        self.toggle_state = False
        self._last_pressed = False
        held_keys = set()
        timer_phase = None
        phase_end_time = 0

        next_click_time = 0
        interval = 0

        while not self.stop_event.is_set():

            self.wake_event.wait()
            self.wake_event.clear()

            if self.stop_event.is_set():
                break

            while not self.stop_event.is_set():
                # ---- DISABLE CHECK ----
                if self.disable_checkbox.isChecked():
                    self.release_key_set(held_keys)
                    time.sleep(0.01)
                    continue

                if not self.trigger_key:
                    break

                if self.disable_checkbox.isChecked():
                    self.release_key_set(held_keys)
                    break

                pressed = real_state.get(self.trigger_key, False)
                t_mode = self.trigger_mode_box.currentText()
                a_mode = self.affected_mode_box.currentText()

                # ---------------- HOLD MODE ----------------
                if t_mode == "Hold":
                    active = pressed

                # ---------------- TOGGLE MODE ----------------
                else:
                    if pressed and not self._last_pressed:
                        self.toggle_state = not self.toggle_state
                        self._last_pressed = True
                    elif not pressed:
                        self._last_pressed = False

                    active = self.toggle_state

                # ---------------- INACTIVE ----------------
                if not active:
                    self.release_key_set(held_keys)
                    timer_phase = None
                    phase_end_time = 0
                    next_click_time = 0
                    break

                # ---------------- WINDOW FILTER ----------------
                if self.work_one_window and self.selected_pid:
                    fg = user32.GetForegroundWindow()
                    if fg:
                        _, fg_pid = win32process.GetWindowThreadProcessId(fg)
                        if fg_pid != self.selected_pid:
                            self.release_key_set(held_keys)
                            time.sleep(0.01)
                            continue

                # ================= TIMER OFF (CPS MODE) =================
                if not self.use_timer:

                    if self.cps > 0:

                        if next_click_time == 0:
                            interval = 1.0 / self.cps
                            next_click_time = time.perf_counter()

                        now = time.perf_counter()

                        if now >= next_click_time:
                            self.send_action(mode=a_mode, held_keys=held_keys)
                            next_click_time += interval
                        else:
                            sleep_time = next_click_time - now
                            if sleep_time > 0:
                                time.sleep(min(0.002, sleep_time))
                    else:
                        time.sleep(0.01)

                    continue

                # ================= TIMER ON =================
                try:
                    hold_t = float(self.hold_entry.text())
                    release_t = float(self.release_entry.text())
                except ValueError:
                    break

                reverse = self.reverse_checkbox.isChecked()
                now = time.time()

                if timer_phase is None:

                    if reverse:
                        timer_phase = "release"
                        phase_end_time = now + release_t
                    else:
                        timer_phase = "hold"
                        phase_end_time = now + hold_t

                    if timer_phase == "hold":
                        self.send_action(mode="Hold", held_keys=held_keys)

                    continue

                if now >= phase_end_time:

                    if timer_phase == "hold":
                        self.release_key_set(held_keys)
                        timer_phase = "release"
                        phase_end_time = now + release_t
                    else:
                        timer_phase = "hold"
                        phase_end_time = now + hold_t
                        self.send_action(mode="Hold", held_keys=held_keys)

                if timer_phase == "hold":
                    self.send_action(mode="Hold", held_keys=held_keys)

                time.sleep(0.001)

    # ---------------- ACTION ----------------
    def send_action(self, mode="Auto-Click", held_keys=None):
        if not self.affected_key:
            return

        if held_keys is None:
            held_keys = set()

        # ---------------- MOUSE ----------------
        if self.affected_key.startswith("mouse"):

            # XBUTTONS
            if self.affected_key in ("mouse.back", "mouse.forward"):

                xbtn = 1 if self.affected_key == "mouse.back" else 2

                if mode == "Auto-Click":
                    user32.mouse_event(MOUSEEVENTF_XDOWN, 0, 0, xbtn, 0)
                    user32.mouse_event(MOUSEEVENTF_XUP,   0, 0, xbtn, 0)

                elif mode == "Hold":
                    if self.affected_key not in held_keys:
                        user32.mouse_event(MOUSEEVENTF_XDOWN, 0, 0, xbtn, 0)
                        held_keys.add(self.affected_key)

            # NORMAL BUTTONS
            else:
                flags = {
                    "mouse.left":   (MOUSEEVENTF_LEFTDOWN,   MOUSEEVENTF_LEFTUP),
                    "mouse.right":  (MOUSEEVENTF_RIGHTDOWN,  MOUSEEVENTF_RIGHTUP),
                    "mouse.middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
                }

                down, up = flags[self.affected_key]

                if mode == "Auto-Click":
                    user32.mouse_event(down, 0, 0, 0, 0)
                    user32.mouse_event(up,   0, 0, 0, 0)

                elif mode == "Hold":
                    if self.affected_key not in held_keys:
                        user32.mouse_event(down, 0, 0, 0, 0)
                        held_keys.add(self.affected_key)

        # ---------------- KEYBOARD ----------------
        else:
            vk = int(self.affected_key.split(".")[1])

            if mode == "Auto-Click":
                user32.keybd_event(vk, 0, 0, 0)
                user32.keybd_event(vk, 0, 2, 0)

            elif mode == "Hold":
                if self.affected_key not in held_keys:
                    user32.keybd_event(vk, 0, 0, 0)
                    held_keys.add(self.affected_key)

    def release_key_set(self, held_keys):
        for k in list(held_keys):
            self.release_key(k)
            held_keys.remove(k)

    def release_key(self, key):

        if key == "mouse.back":
            user32.mouse_event(MOUSEEVENTF_XUP, 0, 0, 1, 0)

        elif key == "mouse.forward":
            user32.mouse_event(MOUSEEVENTF_XUP, 0, 0, 2, 0)

        elif key.startswith("mouse"):
            flags = {
                "mouse.left":   MOUSEEVENTF_LEFTUP,
                "mouse.right":  MOUSEEVENTF_RIGHTUP,
                "mouse.middle": MOUSEEVENTF_MIDDLEUP,
            }
            user32.mouse_event(flags[key], 0, 0, 0, 0)

        else:
            vk = int(key.split(".")[1])
            user32.keybd_event(vk, 0, 2, 0)

    # ---------------- HELPERS ----------------

    def toggle_disable(self):
        current = self.disable_checkbox.isChecked()
        new_state = not current

        QtCore.QMetaObject.invokeMethod(
            self.disable_checkbox,
            "setChecked",
            Qt.QueuedConnection,
            QtCore.Q_ARG(bool, new_state)
        )

        if not new_state:
            for k in list(real_state.keys()):
                real_state[k] = False

            self.toggle_state = False
            self._last_pressed = False
            self.wake_event.set()

    def sleep_interruptible(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            if self.trigger_mode_box.currentText() == "Toggle":
                if not self.toggle_state:
                    return
            if self.disable_checkbox.isChecked():
                return
            time.sleep(0.01)

    def toggle_timer_fields(self):
        
        active = self.timer_checkbox.isChecked()
        self.use_timer = active

        for w in (
            self.hold_label,
            self.hold_entry,
            self.release_label,
            self.release_entry,
            self.reverse_checkbox,
        ):
            w.setVisible(active)

    def set_listen(self, mode):
        global listen_mode
        listen_mode = mode
        self.status.setText(f"Press {mode} key...")

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            forbidden_keys = {
                Qt.Key_Tab,
                Qt.Key_Backtab,
                Qt.Key_Space,
                Qt.Key_Return,
                Qt.Key_Enter,
                Qt.Key_Escape,
                Qt.Key_Up,
                Qt.Key_Down,
                Qt.Key_Left,
                Qt.Key_Right,
                Qt.Key_PageUp,
                Qt.Key_PageDown,
                Qt.Key_Home,
                Qt.Key_End
            }
            if event.key() in forbidden_keys:
                return True
        return QWidget.eventFilter(self, obj, event)
    
    def closeEvent(self, event):
        self.stop_event.set()
        self.wake_event.set()
        _exit(0)
# ============================================
# ENTRY
# ============================================

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = AutoClicker()
    w.show()
    sys.exit(app.exec_())
