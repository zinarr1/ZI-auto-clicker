# Original author: zinarr1

import sys
import os
import subprocess
import threading
import time
import psutil
import win32process
import pygetwindow as gw
import win32api
import win32con

from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import Qt, QEvent
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton, QComboBox,
    QCheckBox, QGridLayout
)
from pynput import keyboard, mouse
from pynput.keyboard import Key, Controller as KeyboardController
from pynput.mouse import Button, Controller as MouseController

class AutoClicker(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ZI Auto Clicker")
        self.setFixedSize(500, 600)

        # Pynput controllers
        self.keyboard_controller = KeyboardController()
        self.mouse_controller = MouseController()

        # State variables
        self.listening_for = None
        self.trigger_key = None
        self.affected_key = None
        self.running = False
        self.click_threads = []
        self.clicker_count = 1
        self.trigger_lock = False

        self.start_mode = "Hold"
        self.effect_mode = "Oto-click"
        self.clicks_per_second = 20
        self.gizli_katsayi = 1.00

        self.selected_pid = None
        self.window_dict = {}

        self.use_timer = False
        self.hold_time = 2.0
        self.release_time = 1.0

        # Build UI
        self.init_ui()

        # Start global listeners
        self.keyboard_listener = keyboard.Listener(
            on_press=self.on_key_event_press,
            on_release=self.on_key_event_release
        )
        self.keyboard_listener.daemon = True
        self.keyboard_listener.start()

        self.mouse_listener = mouse.Listener(
            on_click=self.on_mouse_click
        )
        self.mouse_listener.daemon = True
        self.mouse_listener.start()

        # Populate window list initially
        self.refresh_window_list()

        self.setStyleSheet("""
            /* === Genel Ayarlar === */
            QWidget {
                background-color: #202225;
                color: #f5f5f5;
                font-family: "Segoe UI", "Inter", sans-serif;
                font-size: 13px;
            }

            QLabel {
                color: #f5f5f5;
            }

            /* === Giriş Alanları === */
            QLineEdit, QTextEdit, QPlainTextEdit, QComboBox {
                background-color: #2f3136;
                border: 1px solid #3e4147;
                border-radius: 6px;
                padding: 6px 8px;
                color: #ffffff;
                selection-background-color: #5865f2; /* Discord mavisi */
                selection-color: #ffffff;
            }

            QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus {
                border: 1px solid #7289da;
                background-color: #35383d;
            }

            /* === Butonlar === */
            QPushButton {
                background-color: #5865f2;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 6px 14px;
                font-weight: 500;
                transition: 0.2s;
            }

            QPushButton:hover {
                background-color: #4752c4;
            }

            QPushButton:pressed {
                background-color: #3a3f9f;
            }

            /* === Checkbox === */
            QCheckBox {
                color: #f5f5f5;
                spacing: 6px;
            }

            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 2px solid #72767d;
                border-radius: 4px;
                background: #2f3136;
            }

            QCheckBox::indicator:checked {
                background-color: #5865f2;
                border-color: #5865f2;
            }

            /* === ComboBox Listesi === */
            QComboBox QAbstractItemView {
                background-color: #2f3136;
                color: #ffffff;
                border: 1px solid #3e4147;
                selection-background-color: #5865f2;
                selection-color: #ffffff;
                border-radius: 6px;
            }

            /* === Scrollbar === */
            QScrollBar:vertical, QScrollBar:horizontal {
                background: #2f3136;
                width: 10px;
                height: 10px;
                border-radius: 5px;
            }

            QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
                background: #5865f2;
                border-radius: 5px;
            }

            /* === Tooltip === */
            QToolTip {
                background-color: #2f3136;
                color: #ffffff;
                border: 1px solid #3e4147;
                padding: 4px 8px;
                border-radius: 6px;
            }

            /* === Sekmeler === */
            QTabWidget::pane {
                border: 1px solid #3e4147;
                background-color: #202225;
                border-radius: 8px;
            }

            QTabBar::tab {
                background: #2f3136;
                color: #b9bbbe;
                padding: 6px 12px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 2px;
            }

            QTabBar::tab:selected {
                background: #5865f2;
                color: #ffffff;
            }
        """)


    def init_ui(self):
        layout = QGridLayout()

    def init_ui(self):
        layout = QGridLayout()

        layout.addWidget(QLabel("Trigger Key:"), 0, 0)
        self.trigger_entry = QLineEdit()
        self.trigger_entry.setReadOnly(True)
        layout.addWidget(self.trigger_entry, 0, 1)
        self.trigger_btn = QPushButton("Select")
        self.trigger_btn.clicked.connect(lambda: self.listen_for_key("trigger"))
        layout.addWidget(self.trigger_btn, 0, 2)

        layout.addWidget(QLabel("Affected Key:"), 1, 0)
        self.affected_entry = QLineEdit()
        self.affected_entry.setReadOnly(True)
        layout.addWidget(self.affected_entry, 1, 1)
        self.affected_btn = QPushButton("Select")
        self.affected_btn.clicked.connect(lambda: self.listen_for_key("affected"))
        layout.addWidget(self.affected_btn, 1, 2)

        layout.addWidget(QLabel("Start Type:"), 2, 0)
        self.start_mode_combo = QComboBox()
        self.start_mode_combo.addItems(["Hold", "Toggle"])
        self.start_mode_combo.setCurrentText(self.start_mode)
        self.start_mode_combo.currentTextChanged.connect(self.update_settings)
        layout.addWidget(self.start_mode_combo, 2, 1, 1, 2)

        layout.addWidget(QLabel("Affected Key Mode:"), 3, 0)
        self.effect_mode_combo = QComboBox()
        self.effect_mode_combo.addItems(["Auto-click", "Hold Down"])
        self.effect_mode_combo.setCurrentText(self.effect_mode)
        self.effect_mode_combo.currentTextChanged.connect(self.update_settings)
        layout.addWidget(self.effect_mode_combo, 3, 1, 1, 2)

        layout.addWidget(QLabel("Clicks Per Second (CPS):"), 4, 0)
        self.cps_entry = QLineEdit(str(self.clicks_per_second))
        self.cps_entry.textChanged.connect(self.update_settings)
        layout.addWidget(self.cps_entry, 4, 1, 1, 2)

        layout.addWidget(QLabel("Number of Clickers:"), 5, 0)
        self.clicker_entry = QLineEdit(str(self.clicker_count))
        self.clicker_entry.textChanged.connect(self.update_settings)
        layout.addWidget(self.clicker_entry, 5, 1, 1, 2)

        layout.addWidget(QLabel("Select Application (EXE):"), 6, 0)
        self.window_combo = QComboBox()
        self.window_combo.currentTextChanged.connect(self.select_window)
        layout.addWidget(self.window_combo, 6, 1)
        self.window_refresh_btn = QPushButton("refresh")
        self.window_refresh_btn.setFixedWidth(80)
        self.window_refresh_btn.clicked.connect(self.refresh_window_list)
        layout.addWidget(self.window_refresh_btn, 6, 2)

        self.only_target_chk = QCheckBox("Work only in selected window")
        layout.addWidget(self.only_target_chk, 7, 0, 1, 3)
        
        self.timer_warning = QLabel("\n\n\nWARNING!! Set clicker count max 10 or system will sound alert")
        layout.addWidget(self.timer_warning, 13, 0, 1, 3, alignment=QtCore.Qt.AlignCenter)

        self.disable_chk = QCheckBox("Disable Clicker")
        layout.addWidget(self.disable_chk, 8, 0, 1, 3)

        self.timer_chk = QCheckBox("Activate Timer")
        self.timer_chk.stateChanged.connect(self.toggle_timer_options)
        layout.addWidget(self.timer_chk, 9, 0, 1, 3)

        self.hold_label = QLabel("Hold Duration (sec):")
        layout.addWidget(self.hold_label, 10, 0)
        self.hold_entry = QLineEdit(str(self.hold_time))
        self.hold_entry.textChanged.connect(self.update_settings)
        layout.addWidget(self.hold_entry, 10, 1, 1, 2)

        self.release_label = QLabel("Release Duration (sec):")
        layout.addWidget(self.release_label, 11, 0)
        self.release_entry = QLineEdit(str(self.release_time))
        self.release_entry.textChanged.connect(self.update_settings)
        layout.addWidget(self.release_entry, 11, 1, 1, 2)

        self.reverse_chk = QCheckBox("Reverse timer duration order")
        layout.addWidget(self.reverse_chk, 12, 0, 1, 3)

        self.status_label = QLabel("Ready")
        layout.addWidget(self.status_label, 13, 0, 1, 3, alignment=QtCore.Qt.AlignCenter)

        self.restart_btn = QPushButton("Restart")
        self.restart_btn.clicked.connect(self.restart_program)
        layout.addWidget(self.restart_btn, 14, 0, 1, 3)

        # Hide timer-related widgets initially
        self.hold_label.hide()
        self.hold_entry.hide()
        self.release_label.hide()
        self.release_entry.hide()
        self.reverse_chk.hide()

        self.setLayout(layout)

    def listen_for_key(self, which):
        self.listening_for = which
        self.status_label.setText(f"{which.capitalize()}: Select a button...")

    def on_key_event_press(self, key):
        self.handle_key_event(key, True)

    def on_key_event_release(self, key):
        self.handle_key_event(key, False)

    def on_mouse_click(self, x, y, button, pressed):
        key_name = f"mouse.{button.name}"
        self.handle_key_event(key_name, pressed, is_mouse=True)

    def handle_key_event(self, key, is_press, is_mouse=False):
        if is_mouse:
            key_name = key
        else:
            if isinstance(key, mouse.Button):
                key_name = f"mouse.{key.name}"
            elif hasattr(key, 'char') and key.char:
                key_name = key.char
            elif hasattr(key, 'name') and key.name:
                key_name = key.name
            else:
                key_name = str(key)

        # If waiting for user to press a key to set trigger or affected
        if self.listening_for:
            if self.listening_for == 'trigger':
                self.set_trigger_key(key_name)
            elif self.listening_for == 'affected':
                self.set_affected_key(key_name)
            self.listening_for = None
            self.status_label.setText("Button selected.")
            return

        if self.disable_chk.isChecked():
            return

        if self.only_target_chk.isChecked():
            try:
                hwnd = gw.getActiveWindow()._hWnd
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if pid != self.selected_pid:
                    return
            except:
                return

        if key_name == self.trigger_key:
            if self.start_mode == "Hold":
                if is_press and not self.running:
                    self.start_clicking()
                elif not is_press and self.running:
                    self.stop_clicking()
            elif self.start_mode == "Toggle":
                if is_press and not self.trigger_lock:
                    self.trigger_lock = True
                    if not self.running:
                        self.start_clicking()
                    else:
                        self.stop_clicking()
                elif not is_press:
                    self.trigger_lock = False

    def set_trigger_key(self, key_name):
        self.trigger_key = key_name
        self.trigger_entry.setText(key_name)

    def set_affected_key(self, key_name):
        self.affected_key = key_name
        self.affected_entry.setText(key_name)

    def update_settings(self):
        self.start_mode = self.start_mode_combo.currentText()
        self.effect_mode = self.effect_mode_combo.currentText()
        try:
            cps = int(self.cps_entry.text())
            self.clicks_per_second = max(1, cps)
        except:
            pass
        try:
            count = int(self.clicker_entry.text())
            self.clicker_count = max(1, count)
        except:
            self.clicker_count = 1
        try:
            self.hold_time = float(self.hold_entry.text())
            self.release_time = float(self.release_entry.text())
        except:
            pass

    def toggle_timer_options(self, state):
        active = self.timer_chk.isChecked()
        if active:
            self.hold_label.show()
            self.hold_entry.show()
            self.release_label.show()
            self.release_entry.show()
            self.reverse_chk.show()
        else:
            self.hold_label.hide()
            self.hold_entry.hide()
            self.release_label.hide()
            self.release_entry.hide()
            self.reverse_chk.hide()

    def perform_action(self):
        # Each thread uses individual CPS × gizli_katsayi
        hedef_cps = self.clicks_per_second * self.gizli_katsayi
        interval = 1.0 / hedef_cps
        next_click_time = time.perf_counter()

        if self.timer_chk.isChecked():
            try:
                hold_time_local = float(self.hold_entry.text())
                release_time_local = float(self.release_entry.text())
            except ValueError:
                self.status_label.setText("Geçerli süreler girin.")
                return

            while self.running:
                if self.reverse_chk.isChecked():
                    self.release_key(self.affected_key)
                    for _ in range(int(release_time_local * 100)):
                        if not self.running:
                            return
                        time.sleep(0.01)
                    self.press_key(self.affected_key)
                    for _ in range(int(hold_time_local * 100)):
                        if not self.running:
                            self.release_key(self.affected_key)
                            return
                        time.sleep(0.01)
                else:
                    self.press_key(self.affected_key)
                    for _ in range(int(hold_time_local * 100)):
                        if not self.running:
                            self.release_key(self.affected_key)
                            return
                        time.sleep(0.01)
                    self.release_key(self.affected_key)
                    for _ in range(int(release_time_local * 100)):
                        if not self.running:
                            return
                        time.sleep(0.01)

        elif self.effect_mode == "Basılı Tutma":
            self.press_key(self.affected_key)
            while self.running:
                time.sleep(0.01)
            self.release_key(self.affected_key)

        else:  # Oto-click
            while self.running:
                now = time.perf_counter()
                if now >= next_click_time:
                    self.press_key(self.affected_key)
                    self.release_key(self.affected_key)
                    next_click_time += interval
                else:
                    sleep_time = max(0.0005, next_click_time - now)
                    time.sleep(sleep_time)

    def start_clicking(self):
        # Stop any existing threads
        self.running = False
        time.sleep(0.01)


        try:
            count = int(self.clicker_entry.text())
            self.clicker_count = max(1, count)
        except:
            self.clicker_count = 1

        self.running = True
        self.click_threads = []

        # Birden fazla thread başlat
        for i in range(self.clicker_count):
            t = threading.Thread(target=self.perform_action, daemon=True)
            t.start()
            self.click_threads.append(t)

        self.status_label.setText(f"Started with {self.clicker_count} clickers")

    def stop_clicking(self):
        self.running = False
        self.status_label.setText("Tıklama Durduruldu")

    def press_key(self, key_name):
        try:
            if key_name and key_name.startswith("mouse."):
                btn = key_name.split(".")[1]
                if btn == "left":
                    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                elif btn == "right":
                    win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
                elif btn == "middle":
                    win32api.mouse_event(win32con.MOUSEEVENTF_MIDDLEDOWN, 0, 0, 0, 0)
            elif key_name and len(key_name) == 1:
                self.keyboard_controller.press(key_name)
            elif key_name:
                self.keyboard_controller.press(getattr(Key, key_name))
        except Exception as e:
            print(f"Hata (press): {e}")

    def release_key(self, key_name):
        try:
            if key_name and key_name.startswith("mouse."):
                btn = key_name.split(".")[1]
                if btn == "left":
                    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                elif btn == "right":
                    win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
                elif btn == "middle":
                    win32api.mouse_event(win32con.MOUSEEVENTF_MIDDLEUP, 0, 0, 0, 0)
            elif key_name and len(key_name) == 1:
                self.keyboard_controller.release(key_name)
            elif key_name:
                self.keyboard_controller.release(getattr(Key, key_name))
        except Exception as e:
            print(f"Hata (release): {e}")

    def refresh_window_list(self):
        self.window_combo.clear()
        self.window_dict.clear()
        exe_names = set()
        for w in gw.getWindowsWithTitle(""):
            try:
                hwnd = w._hWnd
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                proc = psutil.Process(pid)
                exe_name = proc.name()
                if exe_name and exe_name not in exe_names:
                    exe_names.add(exe_name)
                    self.window_dict[exe_name] = pid
                    self.window_combo.addItem(exe_name)
            except:
                continue

    def select_window(self, exe_name):
        self.selected_pid = self.window_dict.get(exe_name, None)

    def restart_program(self):
        python = sys.executable
        subprocess.Popen([python] + sys.argv)
        os._exit(0)

    def eventFilter(self, obj, event):
        # Tab, Shift+Tab, Space, Enter, Escape, Arrow keys, PageUp, PageDown, Home, End
        if event.type() == QEvent.KeyPress:
            forbidden_keys = {
                Qt.Key_Tab, Qt.Key_Backtab, Qt.Key_Space, Qt.Key_Return,
                Qt.Key_Enter, Qt.Key_Escape, Qt.Key_Up, Qt.Key_Down,
                Qt.Key_Left, Qt.Key_Right, Qt.Key_PageUp, Qt.Key_PageDown,
                Qt.Key_Home, Qt.Key_End
            }
            if event.key() in forbidden_keys:
                return True  # Ignore the event
        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        try:
            self.keyboard_listener.stop()
        except:
            pass
        try:
            self.mouse_listener.stop()
        except:
            pass
        os._exit(0)

def main():
    app = QApplication(sys.argv)
    window = AutoClicker()
    app.installEventFilter(window)
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
