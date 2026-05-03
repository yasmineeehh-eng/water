import json
import os
import sys
import time
import traceback
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from typing import Callable

import pyautogui
import pyperclip
from PySide6.QtCore import QEvent, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


IMAGE_ACTIONS = {1.0, 2.0, 3.0, 8.0}
START_SHORTCUT_KEY = Qt.Key_F1
START_SHORTCUT_LABEL = "F1"
STOP_SHORTCUT_KEY = Qt.Key_Escape
STOP_SHORTCUT_LABEL = "Esc"


def get_autosave_path() -> str:
    base_dir = os.environ.get("APPDATA") or os.path.dirname(os.path.abspath(sys.argv[0]))
    config_dir = os.path.join(base_dir, "WaterRPA Studio")
    os.makedirs(config_dir, exist_ok=True)
    return os.path.join(config_dir, "last_tasks.json")


AUTOSAVE_PATH = get_autosave_path()

CMD_TYPES = {
    "左键单击": 1.0,
    "左键双击": 2.0,
    "右键单击": 3.0,
    "输入文本": 4.0,
    "等待(秒)": 5.0,
    "滚轮滑动": 6.0,
    "系统按键": 7.0,
    "鼠标悬停": 8.0,
    "截图保存": 9.0,
    "激活窗口": 10.0,
}

CMD_TYPES_REV = {value: key for key, value in CMD_TYPES.items()}

MODIFIER_KEYS = {
    int(Qt.Key_Control),
    int(Qt.Key_Shift),
    int(Qt.Key_Alt),
    int(Qt.Key_Meta),
}

SPECIAL_KEYS = {
    int(Qt.Key_Return): "enter",
    int(Qt.Key_Enter): "enter",
    int(Qt.Key_Escape): "esc",
    int(Qt.Key_Tab): "tab",
    int(Qt.Key_Backtab): "tab",
    int(Qt.Key_Backspace): "backspace",
    int(Qt.Key_Delete): "delete",
    int(Qt.Key_Insert): "insert",
    int(Qt.Key_Home): "home",
    int(Qt.Key_End): "end",
    int(Qt.Key_PageUp): "pageup",
    int(Qt.Key_PageDown): "pagedown",
    int(Qt.Key_Left): "left",
    int(Qt.Key_Right): "right",
    int(Qt.Key_Up): "up",
    int(Qt.Key_Down): "down",
    int(Qt.Key_Space): "space",
    int(Qt.Key_Print): "printscreen",
    int(Qt.Key_Pause): "pause",
    int(Qt.Key_CapsLock): "capslock",
    int(Qt.Key_NumLock): "numlock",
    int(Qt.Key_ScrollLock): "scrolllock",
}


@dataclass
class Task:
    type: float
    value: str
    retry: int = 1
    order: int = 1


def log_to_stdout(message: str) -> None:
    print(message, flush=True)


def qt_key_to_pyautogui_name(key: int, text: str) -> str:
    if int(Qt.Key_F1) <= key <= int(Qt.Key_F35):
        return f"f{key - int(Qt.Key_F1) + 1}"

    if int(Qt.Key_A) <= key <= int(Qt.Key_Z):
        return chr(ord("a") + key - int(Qt.Key_A))

    if int(Qt.Key_0) <= key <= int(Qt.Key_9):
        return chr(ord("0") + key - int(Qt.Key_0))

    if key in SPECIAL_KEYS:
        return SPECIAL_KEYS[key]

    if text and text.strip():
        return text.strip().lower()

    return ""


class ShortcutInput(QLineEdit):
    def __init__(self):
        super().__init__()
        self.capture_mode = False

    def start_capture(self):
        self.capture_mode = True
        self.setReadOnly(True)
        self.setText("")
        self.setPlaceholderText("请按下快捷键")
        self.setFocus()
        self.grabKeyboard()

    def finish_capture(self, shortcut: str):
        self.capture_mode = False
        self.releaseKeyboard()
        self.setReadOnly(False)
        if shortcut:
            self.setText(shortcut)

    def keyPressEvent(self, event):
        if not self.capture_mode:
            super().keyPressEvent(event)
            return

        key = event.key()
        modifiers = event.modifiers()
        parts = []

        if modifiers & Qt.ControlModifier:
            parts.append("ctrl")
        if modifiers & Qt.AltModifier:
            parts.append("alt")
        if modifiers & Qt.ShiftModifier:
            parts.append("shift")
        if modifiers & Qt.MetaModifier:
            parts.append("win")

        if key in MODIFIER_KEYS:
            self.setText("+".join(parts))
            event.accept()
            return

        key_name = qt_key_to_pyautogui_name(key, event.text())
        if key_name:
            parts.append(key_name)

        self.finish_capture("+".join(parts))
        event.accept()


class RPAEngine:
    def __init__(self):
        self.is_running = False
        self.stop_requested = False
        self.user32 = ctypes.windll.user32
        self.kernel32 = ctypes.windll.kernel32

    def stop(self):
        self.stop_requested = True
        self.is_running = False

    def should_stop(self) -> bool:
        return self.stop_requested

    def wait_until_image(self, img: str, timeout: float, callback_msg: Callable[[str], None] | None):
        start_time = time.time()

        while not self.should_stop():
            if timeout and time.time() - start_time > timeout:
                raise TimeoutError(f"等待图片超时：{img}，已等待 {timeout} 秒")

            try:
                location = pyautogui.locateCenterOnScreen(img, confidence=0.9)
                if location is not None:
                    return location
            except pyautogui.ImageNotFoundException:
                pass

            if callback_msg:
                callback_msg(f"未找到图片，继续查找：{img}")
            time.sleep(0.2)

        raise InterruptedError("任务已停止")

    def click_image(
        self,
        click_times: int,
        button: str,
        img: str,
        retry: int,
        timeout: float,
        callback_msg: Callable[[str], None] | None,
    ):
        total = 1 if retry <= 1 else retry
        count = 0

        while not self.should_stop():
            location = self.wait_until_image(img, timeout, callback_msg)
            pyautogui.click(
                location.x,
                location.y,
                clicks=click_times,
                interval=0.2,
                duration=0.2,
                button=button,
            )
            count += 1

            if retry == -1:
                time.sleep(0.2)
                continue

            if count >= total:
                return

    def move_to_image(self, img: str, retry: int, timeout: float, callback_msg: Callable[[str], None] | None):
        total = 1 if retry <= 1 else retry

        for _ in range(total):
            if self.should_stop():
                raise InterruptedError("任务已停止")
            location = self.wait_until_image(img, timeout, callback_msg)
            pyautogui.moveTo(location.x, location.y, duration=0.2)

    def activate_window(self, query: str, timeout: float, callback_msg: Callable[[str], None] | None):
        mode, keyword = self.parse_window_query(query)
        start_time = time.time()

        while not self.should_stop():
            window = self.find_window(mode, keyword)
            if window:
                hwnd, title, pid, process_name = window
                self.bring_window_to_front(hwnd)
                time.sleep(0.3)
                self.emit(callback_msg, f"已激活窗口：{title} / {process_name} / PID {pid}")
                return

            if timeout and time.time() - start_time > timeout:
                raise TimeoutError(f"等待窗口超时：{query}，已等待 {timeout} 秒")

            self.emit(callback_msg, f"未找到窗口，继续查找：{query}")
            time.sleep(0.2)

        raise InterruptedError("任务已停止")

    @staticmethod
    def parse_window_query(query: str) -> tuple[str, str]:
        text = str(query).strip()
        if not text:
            raise ValueError("激活窗口参数不能为空")

        if "=" in text:
            key, value = text.split("=", 1)
            key = key.strip().lower()
            value = value.strip()
            if key in {"title", "标题", "窗口"}:
                return "title", value.lower()
            if key in {"process", "进程", "程序", "exe"}:
                return "process", value.lower()

        return "title", text.lower()

    def find_window(self, mode: str, keyword: str):
        result = None
        enum_proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def enum_proc(hwnd, _):
            nonlocal result
            if result is not None:
                return False

            if not self.user32.IsWindowVisible(hwnd):
                return True

            title_len = self.user32.GetWindowTextLengthW(hwnd)
            if title_len <= 0:
                return True

            title_buffer = ctypes.create_unicode_buffer(title_len + 1)
            self.user32.GetWindowTextW(hwnd, title_buffer, title_len + 1)
            title = title_buffer.value

            pid = wintypes.DWORD()
            self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            process_name = self.get_process_name(pid.value)

            if mode == "title" and keyword in title.lower():
                result = (hwnd, title, pid.value, process_name)
                return False

            if mode == "process" and keyword in process_name.lower():
                result = (hwnd, title, pid.value, process_name)
                return False

            return True

        self.user32.EnumWindows(enum_proc_type(enum_proc), 0)
        return result

    def get_process_name(self, pid: int) -> str:
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = self.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return ""

        try:
            size = wintypes.DWORD(32768)
            buffer = ctypes.create_unicode_buffer(size.value)
            if self.kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                return os.path.basename(buffer.value)
            return ""
        finally:
            self.kernel32.CloseHandle(handle)

    def bring_window_to_front(self, hwnd):
        SW_RESTORE = 9
        SW_SHOW = 5
        if self.user32.IsIconic(hwnd):
            self.user32.ShowWindow(hwnd, SW_RESTORE)
        else:
            self.user32.ShowWindow(hwnd, SW_SHOW)
        self.user32.BringWindowToTop(hwnd)
        self.user32.SetForegroundWindow(hwnd)

    def run_tasks(
        self,
        tasks: list[Task],
        loop_forever: bool = False,
        timeout: float = 60,
        loop_interval_minutes: float = 0,
        callback_msg: Callable[[str], None] | None = None,
    ):
        self.is_running = True
        self.stop_requested = False

        try:
            while not self.should_stop():
                for idx, task in enumerate(tasks):
                    if self.should_stop():
                        raise InterruptedError("任务已停止")

                    if callback_msg:
                        callback_msg(f"执行步骤 {idx + 1}/{len(tasks)}：{CMD_TYPES_REV.get(task.type, task.type)}")

                    self.run_task(task, timeout, callback_msg)

                if not loop_forever:
                    break

                if callback_msg:
                    if loop_interval_minutes > 0:
                        callback_msg(f"本轮执行完成，等待 {loop_interval_minutes:g} 分钟后进入下一轮循环")
                    else:
                        callback_msg("本轮执行完成，准备进入下一轮循环")

                if loop_interval_minutes > 0:
                    self.sleep_with_stop(loop_interval_minutes * 60)
                else:
                    time.sleep(0.2)

        except InterruptedError as exc:
            if callback_msg:
                callback_msg(str(exc))
        except Exception as exc:
            if callback_msg:
                callback_msg(f"执行出错：{exc}")
            traceback.print_exc()
        finally:
            self.is_running = False
            if callback_msg:
                callback_msg("任务结束")

    def run_task(self, task: Task, timeout: float, callback_msg: Callable[[str], None] | None):
        cmd_type = task.type
        cmd_value = task.value
        retry = task.retry

        if cmd_type == 1.0:
            self.click_image(1, "left", cmd_value, retry, timeout, callback_msg)
            self.emit(callback_msg, f"左键单击：{cmd_value}")
        elif cmd_type == 2.0:
            self.click_image(2, "left", cmd_value, retry, timeout, callback_msg)
            self.emit(callback_msg, f"左键双击：{cmd_value}")
        elif cmd_type == 3.0:
            self.click_image(1, "right", cmd_value, retry, timeout, callback_msg)
            self.emit(callback_msg, f"右键单击：{cmd_value}")
        elif cmd_type == 4.0:
            pyperclip.copy(str(cmd_value))
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.5)
            self.emit(callback_msg, f"输入文本：{cmd_value}")
        elif cmd_type == 5.0:
            self.sleep_with_stop(float(cmd_value))
            self.emit(callback_msg, f"等待 {cmd_value} 秒")
        elif cmd_type == 6.0:
            pyautogui.scroll(int(cmd_value))
            self.emit(callback_msg, f"滚轮滑动：{cmd_value}")
        elif cmd_type == 7.0:
            keys = [key.strip().lower() for key in str(cmd_value).split("+") if key.strip()]
            if not keys:
                raise ValueError("系统按键不能为空")
            pyautogui.hotkey(*keys)
            self.emit(callback_msg, f"系统按键：{cmd_value}")
        elif cmd_type == 8.0:
            self.move_to_image(cmd_value, retry, timeout, callback_msg)
            self.emit(callback_msg, f"鼠标悬停：{cmd_value}")
        elif cmd_type == 9.0:
            filename = self.resolve_screenshot_path(cmd_value)
            pyautogui.screenshot(filename)
            self.emit(callback_msg, f"截图已保存：{filename}")
        elif cmd_type == 10.0:
            self.activate_window(cmd_value, timeout, callback_msg)
        else:
            raise ValueError(f"未知指令类型：{cmd_type}")

    def sleep_with_stop(self, seconds: float):
        end_time = time.time() + seconds
        while time.time() < end_time:
            if self.should_stop():
                raise InterruptedError("任务已停止")
            time.sleep(min(0.2, end_time - time.time()))

    @staticmethod
    def resolve_screenshot_path(path: str) -> str:
        path = str(path).strip()
        if os.path.isdir(path):
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            return os.path.join(path, f"screenshot_{timestamp}.png")

        root, ext = os.path.splitext(path)
        if ext.lower() not in {".png", ".jpg", ".jpeg", ".bmp"}:
            return f"{path}.png"
        return path

    @staticmethod
    def emit(callback_msg: Callable[[str], None] | None, message: str):
        if callback_msg:
            callback_msg(message)
        else:
            log_to_stdout(message)


class WorkerThread(QThread):
    log_signal = Signal(str)
    finished_signal = Signal()

    def __init__(
        self,
        engine: RPAEngine,
        tasks: list[Task],
        loop_forever: bool,
        timeout: float,
        loop_interval_minutes: float,
    ):
        super().__init__()
        self.engine = engine
        self.tasks = tasks
        self.loop_forever = loop_forever
        self.timeout = timeout
        self.loop_interval_minutes = loop_interval_minutes

    def run(self):
        self.engine.run_tasks(
            self.tasks,
            self.loop_forever,
            self.timeout,
            self.loop_interval_minutes,
            self.log_signal.emit,
        )
        self.finished_signal.emit()


class TaskRow(QFrame):
    def __init__(self, parent_layout, delete_callback, move_callback, index: int):
        super().__init__()
        self.delete_callback = delete_callback
        self.move_callback = move_callback
        self.index = index
        self.setFrameShape(QFrame.StyledPanel)
        self.setObjectName("taskRow")

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(12, 12, 12, 12)
        self.layout.setSpacing(14)

        self.index_label = QLabel()
        self.index_label.setObjectName("rowIndex")
        self.index_label.setFixedWidth(32)
        self.index_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.index_label)

        self.order_input = QLineEdit()
        self.order_input.setPlaceholderText("顺序")
        self.order_input.setFixedWidth(64)

        self.type_combo = QComboBox()
        self.type_combo.addItems(list(CMD_TYPES.keys()))
        self.type_combo.currentTextChanged.connect(self.on_type_changed)
        self.type_combo.setFixedWidth(140)

        self.value_input = ShortcutInput()

        self.file_btn = QPushButton("选择图片")
        self.file_btn.setObjectName("secondaryButton")
        self.file_btn.clicked.connect(self.select_file)

        self.shortcut_btn = QPushButton("按键加入")
        self.shortcut_btn.setObjectName("secondaryButton")
        self.shortcut_btn.clicked.connect(self.value_input.start_capture)

        self.retry_input = QLineEdit()
        self.retry_input.setPlaceholderText("重试")
        self.retry_input.setText("1")
        self.retry_input.setFixedWidth(56)

        self.value_group = QWidget()
        value_layout = QHBoxLayout(self.value_group)
        value_layout.setContentsMargins(0, 0, 0, 0)
        value_layout.setSpacing(8)
        value_layout.addWidget(self.value_input, 1)
        value_layout.addWidget(self.file_btn)
        value_layout.addWidget(self.shortcut_btn)

        self.layout.addWidget(self.create_field("顺序", self.order_input))
        self.layout.addWidget(self.create_field("动作类型", self.type_combo))
        self.layout.addWidget(self.create_field("识别目标 / 参数", self.value_group), 1)
        self.layout.addWidget(self.create_field("次数", self.retry_input))

        self.up_btn = QPushButton("上移")
        self.up_btn.setObjectName("iconButton")
        self.up_btn.clicked.connect(lambda: move_callback(self, -1))
        self.layout.addWidget(self.up_btn)

        self.down_btn = QPushButton("下移")
        self.down_btn.setObjectName("iconButton")
        self.down_btn.clicked.connect(lambda: move_callback(self, 1))
        self.layout.addWidget(self.down_btn)

        self.del_btn = QPushButton("删除")
        self.del_btn.setObjectName("dangerButton")
        self.del_btn.clicked.connect(lambda: delete_callback(self))
        self.layout.addWidget(self.del_btn)

        parent_layout.addWidget(self)
        self.set_index(index)
        self.on_type_changed(self.type_combo.currentText())

    def bind_change_callback(self, callback):
        self.order_input.textChanged.connect(lambda *_: callback())
        self.type_combo.currentTextChanged.connect(lambda *_: callback())
        self.value_input.textChanged.connect(lambda *_: callback())
        self.retry_input.textChanged.connect(lambda *_: callback())

    def create_field(self, title: str, widget: QWidget) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        label = QLabel(title)
        label.setObjectName("fieldLabel")
        layout.addWidget(label)
        layout.addWidget(widget)
        return container

    def set_index(self, index: int):
        self.index = index
        self.index_label.setText(f"#{index}")
        if not self.order_input.text().strip():
            self.order_input.setText(str(index))

    def set_order(self, order: int):
        self.order_input.setText(str(order))

    def set_move_buttons_enabled(self, can_move_up: bool, can_move_down: bool):
        self.up_btn.setEnabled(can_move_up)
        self.down_btn.setEnabled(can_move_down)

    def on_type_changed(self, text):
        cmd_type = CMD_TYPES[text]

        self.file_btn.setVisible(cmd_type in IMAGE_ACTIONS or cmd_type == 9.0)
        self.shortcut_btn.setVisible(cmd_type == 7.0)
        self.retry_input.setVisible(cmd_type in IMAGE_ACTIONS)

        if cmd_type in IMAGE_ACTIONS:
            self.file_btn.setText("选择图片")
            self.value_input.setPlaceholderText("图片路径")
        elif cmd_type == 4.0:
            self.value_input.setPlaceholderText("要输入的文本")
        elif cmd_type == 5.0:
            self.value_input.setPlaceholderText("等待秒数，例如 1.5")
        elif cmd_type == 6.0:
            self.value_input.setPlaceholderText("滚动距离，正数向上，负数向下")
        elif cmd_type == 7.0:
            self.value_input.setPlaceholderText("点击“按键加入”后按快捷键，也可手动输入")
        elif cmd_type == 9.0:
            self.file_btn.setText("选择目录")
            self.value_input.setPlaceholderText("截图保存目录或文件路径")
        elif cmd_type == 10.0:
            self.value_input.setPlaceholderText("title=窗口标题关键词 或 process=程序名.exe，例如 title=Chrome")

    def set_data(self, data):
        cmd_type = data.get("type")
        value = data.get("value", "")
        retry = data.get("retry", 1)
        order = data.get("order", self.index)

        if cmd_type in CMD_TYPES_REV:
            self.type_combo.setCurrentText(CMD_TYPES_REV[cmd_type])
        self.value_input.setText(str(value))
        self.retry_input.setText(str(retry))
        self.order_input.setText(str(order))

    def select_file(self):
        cmd_type = CMD_TYPES[self.type_combo.currentText()]

        if cmd_type == 9.0:
            folder = QFileDialog.getExistingDirectory(self, "选择截图保存目录", os.getcwd())
            if folder:
                self.value_input.setText(folder)
            return

        filename, _ = QFileDialog.getOpenFileName(
            self,
            "选择图片",
            os.getcwd(),
            "Image Files (*.png *.jpg *.jpeg *.bmp)",
        )
        if filename:
            self.value_input.setText(filename)

    def get_data(self) -> Task:
        cmd_type = CMD_TYPES[self.type_combo.currentText()]
        value = self.value_input.text().strip()
        retry = 1
        order_text = self.order_input.text().strip() or str(self.index)
        order = int(order_text)
        if order <= 0:
            raise ValueError("执行顺序必须是大于 0 的整数")

        if self.retry_input.isVisible():
            retry_text = self.retry_input.text().strip() or "1"
            retry = int(retry_text)
            if retry == 0 or retry < -1:
                raise ValueError("重试次数只能是 -1、1 或大于 1 的整数")

        return Task(type=cmd_type, value=value, retry=retry, order=order)

    def to_json(self) -> dict:
        task = self.get_data()
        return {"type": task.type, "value": task.value, "retry": task.retry, "order": task.order}


class RPAWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WaterRPA Studio")
        self.resize(1380, 840)

        self.engine = RPAEngine()
        self.worker = None
        self.rows = []
        self.autosave_suspended = False

        central_widget = QWidget()
        central_widget.setObjectName("appRoot")
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        main_layout.addWidget(self.create_header())
        main_layout.addWidget(self.create_toolbar())

        scroll = QScrollArea()
        scroll.setObjectName("taskScroll")
        scroll.setWidgetResizable(True)
        self.task_container = QWidget()
        self.task_container.setObjectName("taskCanvas")
        self.task_layout = QVBoxLayout(self.task_container)
        self.task_layout.setContentsMargins(24, 24, 24, 24)
        self.task_layout.setSpacing(12)
        self.task_layout.addStretch()
        scroll.setWidget(self.task_container)
        main_layout.addWidget(scroll, 1)

        main_layout.addWidget(self.create_log_panel())

        self.apply_styles()
        if not self.load_autosaved_config():
            self.add_row()
        QApplication.instance().installEventFilter(self)

    def create_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("header")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(22, 8, 24, 8)
        layout.setSpacing(14)

        logo = QLabel("↶")
        logo.setObjectName("logo")
        logo.setAlignment(Qt.AlignCenter)
        layout.addWidget(logo)

        title_block = QWidget()
        title_layout = QVBoxLayout(title_block)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(0)

        title = QLabel("WaterRPA <span style='color:#94a3b8'>Studio</span>")
        title.setObjectName("title")
        title.setTextFormat(Qt.RichText)
        subtitle = QLabel("CONFIG TOOL V2.0")
        subtitle.setObjectName("subtitle")
        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)
        layout.addWidget(title_block)

        layout.addStretch()

        self.add_btn = self.create_header_button("+  新增")
        self.add_btn.clicked.connect(self.add_row)
        layout.addWidget(self.add_btn)

        self.save_btn = self.create_header_button("▣  保存")
        self.save_btn.clicked.connect(self.save_config)
        layout.addWidget(self.save_btn)

        self.load_btn = self.create_header_button("↥  导入")
        self.load_btn.clicked.connect(self.load_config)
        layout.addWidget(self.load_btn)

        divider = QFrame()
        divider.setObjectName("headerDivider")
        divider.setFixedWidth(1)
        layout.addWidget(divider)

        self.start_btn = QPushButton(f"▶  开始运行 ({START_SHORTCUT_LABEL})")
        self.start_btn.setObjectName("primaryButton")
        self.start_btn.setToolTip(f"按 {START_SHORTCUT_LABEL} 开始运行")
        self.start_btn.clicked.connect(self.start_task)
        layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton(f"停止 ({STOP_SHORTCUT_LABEL})")
        self.stop_btn.setObjectName("stopButton")
        self.stop_btn.setToolTip(f"按 {STOP_SHORTCUT_LABEL} 停止")
        self.stop_btn.clicked.connect(self.stop_task)
        self.stop_btn.setEnabled(False)
        layout.addWidget(self.stop_btn)

        return header

    def create_header_button(self, text: str) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("headerButton")
        return button

    def create_toolbar(self) -> QWidget:
        toolbar = QFrame()
        toolbar.setObjectName("toolbar")
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(22, 10, 24, 10)
        layout.setSpacing(14)

        timeout_label = QLabel("◷  找图片最多等待（秒）")
        timeout_label.setObjectName("toolbarLabel")
        timeout_label.setToolTip("每一步需要找图片时，最多等待这么久；超过后仍没找到，就提示超时。")
        layout.addWidget(timeout_label)

        self.timeout_input = QLineEdit("60")
        self.timeout_input.setFixedWidth(64)
        self.timeout_input.setPlaceholderText("如 60")
        self.timeout_input.setToolTip("例如填 60：每次找图片最多等 60 秒，超时后不再继续等待。")
        layout.addWidget(self.timeout_input)

        mode_label = QLabel("↻  运行模式")
        mode_label.setObjectName("toolbarLabel")
        layout.addWidget(mode_label)

        self.loop_check = QComboBox()
        self.loop_check.addItems(["执行一次", "循环执行"])
        self.loop_check.setFixedWidth(120)
        layout.addWidget(self.loop_check)

        interval_label = QLabel("循环间隔（分钟）")
        interval_label.setObjectName("toolbarLabel")
        interval_label.setToolTip("选择循环执行时，每一轮执行完成后等待多少分钟再开始下一轮；填 0 表示立即循环。")
        layout.addWidget(interval_label)

        self.loop_interval_input = QLineEdit("0")
        self.loop_interval_input.setFixedWidth(64)
        self.loop_interval_input.setPlaceholderText("如 5")
        self.loop_interval_input.setToolTip("例如填 5：本轮完成后等待 5 分钟，再开始下一轮循环。")
        layout.addWidget(self.loop_interval_input)

        self.minimize_check = QCheckBox("运行时最小化")
        self.minimize_check.setChecked(True)
        layout.addWidget(self.minimize_check)
        layout.addStretch()

        return toolbar

    def create_log_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("logPanel")
        panel.setFixedHeight(194)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        log_header = QFrame()
        log_header.setObjectName("logHeader")
        header_layout = QHBoxLayout(log_header)
        header_layout.setContentsMargins(16, 8, 16, 8)
        header_layout.setSpacing(10)

        log_title = QLabel(">_  RUNTIME LOGS")
        log_title.setObjectName("logTitle")
        header_layout.addWidget(log_title)
        header_layout.addStretch()

        self.log_status = QLabel("● LIVE")
        self.log_status.setObjectName("liveStatus")
        header_layout.addWidget(self.log_status)

        self.command_count_label = QLabel("0 COMMANDS LOADED")
        self.command_count_label.setObjectName("commandCount")
        header_layout.addWidget(self.command_count_label)
        layout.addWidget(log_header)

        self.log_area = QTextEdit()
        self.log_area.setObjectName("logArea")
        self.log_area.setReadOnly(True)
        layout.addWidget(self.log_area, 1)

        return panel

    def apply_styles(self):
        self.setStyleSheet(
            """
            #appRoot {
                background: #f4f7fb;
                color: #10223f;
                font-family: "Microsoft YaHei UI", "Segoe UI";
            }
            #header {
                background: #ffffff;
                border-bottom: 1px solid #e4eaf2;
            }
            #logo {
                min-width: 40px;
                min-height: 40px;
                max-width: 40px;
                max-height: 40px;
                border-radius: 10px;
                background: #111c31;
                color: #dbeafe;
                font-size: 28px;
                font-weight: 700;
            }
            #title {
                font-size: 20px;
                font-weight: 800;
                color: #0b2545;
            }
            #subtitle {
                color: #8190ad;
                font-size: 11px;
                font-weight: 800;
                letter-spacing: 1.8px;
            }
            #headerButton {
                background: #f4f7fb;
                border: 1px solid #dce5f1;
                color: #2b4264;
                padding: 10px 14px;
                border-radius: 8px;
                font-weight: 600;
            }
            #headerButton:hover, #secondaryButton:hover {
                background: #edf3fb;
                border-color: #c9d8eb;
            }
            #primaryButton {
                background: #059669;
                color: #ffffff;
                border: none;
                padding: 12px 26px;
                border-radius: 8px;
                font-size: 15px;
                font-weight: 800;
            }
            #primaryButton:disabled {
                background: #89cbb6;
            }
            #stopButton {
                background: #fee2e2;
                color: #b91c1c;
                border: 1px solid #fecaca;
                padding: 10px 14px;
                border-radius: 8px;
                font-weight: 700;
            }
            #stopButton:disabled {
                color: #cbd5e1;
                background: #f8fafc;
                border-color: #edf2f7;
            }
            #headerDivider {
                background: #e5edf6;
                margin-left: 4px;
                margin-right: 2px;
            }
            #toolbar {
                background: #ffffff;
                border-bottom: 1px solid #dce5f1;
            }
            #toolbarLabel, #fieldLabel {
                color: #7588a8;
                font-size: 11px;
                font-weight: 700;
            }
            QLineEdit, QComboBox {
                background: #f7faff;
                border: 1px solid #e5edf6;
                border-radius: 8px;
                min-height: 34px;
                padding: 0 10px;
                color: #0f172a;
                font-size: 14px;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 1px solid #6aa2ff;
                background: #ffffff;
            }
            QCheckBox {
                color: #405575;
                font-weight: 600;
            }
            QCheckBox::indicator {
                width: 39px;
                height: 20px;
            }
            #taskScroll {
                border: none;
                background: #f4f7fb;
            }
            #taskCanvas {
                background: #f4f7fb;
            }
            #taskRow {
                background: #ffffff;
                border: 1px solid #dce5f1;
                border-left: 4px solid #5b8cff;
                border-radius: 10px;
            }
            #rowIndex {
                color: #8aa0c2;
                font-weight: 800;
                font-size: 12px;
            }
            #secondaryButton {
                background: #ffffff;
                border: 1px solid #dce5f1;
                color: #2f4668;
                border-radius: 7px;
                padding: 7px 10px;
                font-weight: 600;
            }
            #iconButton {
                background: transparent;
                border: none;
                color: #9eb0c9;
                padding: 8px 6px;
                font-weight: 700;
            }
            #iconButton:hover {
                color: #4078ff;
                background: #eef4ff;
                border-radius: 7px;
            }
            #iconButton:disabled {
                color: #d8e0ec;
            }
            #dangerButton {
                background: transparent;
                border: none;
                color: #fb7185;
                padding: 8px 8px;
                font-weight: 700;
            }
            #dangerButton:hover {
                background: #fff1f2;
                border-radius: 7px;
            }
            #logPanel {
                background: #15181d;
                border-top: 1px solid #0f1115;
            }
            #logHeader {
                background: #171a1f;
                border-bottom: 1px solid #262a31;
            }
            #logTitle {
                color: #9098a6;
                font-weight: 900;
                font-style: italic;
                letter-spacing: 1px;
            }
            #liveStatus {
                color: #10b981;
                font-weight: 800;
                font-size: 12px;
            }
            #commandCount {
                color: #8b95a5;
                font-size: 12px;
                font-weight: 800;
            }
            #logArea {
                background: #15181d;
                color: #58a6ff;
                border: none;
                padding: 12px;
                font-family: "Cascadia Mono", Consolas, monospace;
                font-size: 13px;
            }
            """
        )

    def add_row(self, data=None, autosave: bool = True):
        self.task_layout.takeAt(self.task_layout.count() - 1)

        row = TaskRow(self.task_layout, self.delete_row, self.move_row, len(self.rows) + 1)
        if data:
            row.set_data(data)
        row.bind_change_callback(self.save_last_config)
        self.rows.append(row)

        self.task_layout.addStretch()
        self.renumber_rows()
        self.update_command_count()
        if autosave:
            self.save_last_config()

    def delete_row(self, row_widget):
        if row_widget in self.rows:
            self.rows.remove(row_widget)
            row_widget.deleteLater()
            self.renumber_rows(sync_order=True)
            self.update_command_count()
            self.save_last_config()

    def move_row(self, row_widget, direction: int):
        if row_widget not in self.rows:
            return

        current_index = self.rows.index(row_widget)
        new_index = current_index + direction
        if new_index < 0 or new_index >= len(self.rows):
            return

        self.rows[current_index], self.rows[new_index] = self.rows[new_index], self.rows[current_index]
        self.rebuild_task_layout()
        self.renumber_rows(sync_order=True)
        self.save_last_config()

    def rebuild_task_layout(self):
        while self.task_layout.count():
            self.task_layout.takeAt(0)

        for row in self.rows:
            self.task_layout.addWidget(row)

        self.task_layout.addStretch()

    def renumber_rows(self, sync_order: bool = False):
        total = len(self.rows)
        for index, row in enumerate(self.rows, start=1):
            row.set_index(index)
            row.set_move_buttons_enabled(index > 1, index < total)
            if sync_order:
                row.set_order(index)

    def update_command_count(self):
        if hasattr(self, "command_count_label"):
            count = len(self.rows)
            suffix = "COMMAND" if count == 1 else "COMMANDS"
            self.command_count_label.setText(f"{count} {suffix} LOADED")

    def serialize_rows(self, allow_empty: bool = False) -> list[dict]:
        tasks = []
        for row in self.rows:
            task = row.get_data()
            if not allow_empty and not task.value:
                continue
            tasks.append({"type": task.type, "value": task.value, "retry": task.retry, "order": task.order})
        return tasks

    def save_last_config(self):
        if self.autosave_suspended:
            return

        try:
            tasks = self.serialize_rows(allow_empty=False)
            with open(AUTOSAVE_PATH, "w", encoding="utf-8") as file:
                json.dump(tasks, file, indent=4, ensure_ascii=False)
        except ValueError:
            return
        except Exception as exc:
            self.log(f"自动保存失败：{exc}")

    def load_autosaved_config(self) -> bool:
        if not os.path.exists(AUTOSAVE_PATH):
            return False

        try:
            with open(AUTOSAVE_PATH, "r", encoding="utf-8") as file:
                tasks = json.load(file)

            if not isinstance(tasks, list) or not tasks:
                return False

            self.autosave_suspended = True
            try:
                for task in tasks:
                    self.add_row(task, autosave=False)
            finally:
                self.autosave_suspended = False

            self.renumber_rows()
            self.update_command_count()
            self.log(f"已自动恢复 {len(tasks)} 条指令")
            return True
        except Exception as exc:
            self.log(f"自动恢复失败：{exc}")
            return False

    def collect_tasks(self) -> list[Task]:
        indexed_tasks = []
        for index, row in enumerate(self.rows, start=1):
            task = row.get_data()
            if not task.value:
                raise ValueError(f"第 {index} 条指令参数为空")
            indexed_tasks.append((index, task))

        indexed_tasks.sort(key=lambda item: (item[1].order, item[0]))
        return [task for _, task in indexed_tasks]

    def save_config(self):
        try:
            tasks = self.serialize_rows(allow_empty=True)
        except ValueError as exc:
            QMessageBox.warning(self, "无法保存", str(exc))
            return

        if not tasks:
            QMessageBox.warning(self, "提示", "没有可保存的配置")
            return

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "保存配置",
            os.getcwd(),
            "JSON Files (*.json);;Text Files (*.txt)",
        )
        if not filename:
            return

        try:
            with open(filename, "w", encoding="utf-8") as file:
                json.dump(tasks, file, indent=4, ensure_ascii=False)
            QMessageBox.information(self, "保存成功", "配置已保存")
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", str(exc))

    def load_config(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "导入配置",
            os.getcwd(),
            "JSON Files (*.json);;Text Files (*.txt)",
        )
        if not filename:
            return

        try:
            with open(filename, "r", encoding="utf-8") as file:
                tasks = json.load(file)

            if not isinstance(tasks, list):
                raise ValueError("配置文件格式不正确，应为指令数组")

            self.autosave_suspended = True
            try:
                for row in self.rows:
                    row.deleteLater()
                self.rows.clear()

                for task in tasks:
                    self.add_row(task, autosave=False)
                self.renumber_rows()
                self.update_command_count()
            finally:
                self.autosave_suspended = False

            self.save_last_config()

            QMessageBox.information(self, "导入成功", f"已导入 {len(tasks)} 条指令")
        except Exception as exc:
            QMessageBox.critical(self, "导入失败", str(exc))

    def start_task(self):
        try:
            tasks = self.collect_tasks()
            timeout = float(self.timeout_input.text().strip() or "60")
            if timeout <= 0:
                raise ValueError("图片等待超时必须大于 0")
            loop_interval = float(self.loop_interval_input.text().strip() or "0")
            if loop_interval < 0:
                raise ValueError("循环间隔分钟数不能小于 0")
        except ValueError as exc:
            QMessageBox.warning(self, "无法开始", str(exc))
            return

        if not tasks:
            QMessageBox.warning(self, "无法开始", "请至少添加一条指令")
            return

        self.log_area.clear()
        self.log("任务开始")

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.add_btn.setEnabled(False)
        self.save_btn.setEnabled(False)
        self.load_btn.setEnabled(False)
        self.log_status.setText("● RUNNING")

        loop = self.loop_check.currentText() == "循环执行"
        if not loop:
            loop_interval = 0

        self.worker = WorkerThread(self.engine, tasks, loop, timeout, loop_interval)
        self.worker.log_signal.connect(self.log)
        self.worker.finished_signal.connect(self.on_finished)
        self.worker.start()

        if self.minimize_check.isChecked():
            self.showMinimized()

    def eventFilter(self, watched, event):
        if event.type() != QEvent.KeyPress or event.modifiers() != Qt.NoModifier:
            return super().eventFilter(watched, event)

        if event.key() in (START_SHORTCUT_KEY, STOP_SHORTCUT_KEY):
            focus_widget = QApplication.focusWidget()
            if isinstance(focus_widget, ShortcutInput) and focus_widget.capture_mode:
                return False

        if event.key() == START_SHORTCUT_KEY:
            if self.start_btn.isEnabled():
                self.start_task()
                return True

        if event.key() == STOP_SHORTCUT_KEY:
            if self.stop_btn.isEnabled():
                self.stop_task()
                return True

        return super().eventFilter(watched, event)

    def stop_task(self):
        self.engine.stop()
        self.log("正在停止...")

    def on_finished(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.add_btn.setEnabled(True)
        self.save_btn.setEnabled(True)
        self.load_btn.setEnabled(True)
        self.log_status.setText("● LIVE")
        self.log("任务已结束")

        if self.minimize_check.isChecked() or self.isMinimized():
            self.showNormal()
            self.activateWindow()

    def log(self, msg):
        timestamp = time.strftime("%H:%M:%S")
        self.log_area.append(f"[{timestamp}]  >  {msg}")

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.engine.stop()
            self.worker.quit()
            self.worker.wait(3000)
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = RPAWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
