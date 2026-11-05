# -*- coding: utf-8 -*-
import sys
import os
import re
import shutil
import traceback
import winreg
from datetime import datetime
from ctypes import windll, c_int, byref, sizeof, Structure, POINTER, wintypes
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QTextEdit, QPushButton, QLabel, QSystemTrayIcon,
                             QMenu, QAction, QFrame, QDesktopWidget,
                             QGraphicsDropShadowEffect, QStyle,
                             QTabBar, QInputDialog, QMessageBox, QShortcut,
                             QLineEdit, QListWidget, QListWidgetItem, QSlider,
                             QWidgetAction, QDialog)
from PyQt5.QtCore import (Qt, QTimer, QSize, QSettings, QPoint, QUrl, QRect,
                          QEvent, pyqtSignal, QPropertyAnimation, QEasingCurve)
from PyQt5.QtNetwork import QLocalServer, QLocalSocket
from PyQt5.QtGui import (QColor, QFont, QPainter, QBrush, QIcon, QCursor, QPen,
                          QTextCursor, QTextCharFormat, QTextFormat, QKeySequence,
                          QTextDocument)

# --- Windows Acrylic (毛玻璃) API 封装 ---
class WindowEffect:
    def __init__(self):
        self.user32 = windll.user32
        self.dwmapi = windll.dwmapi

    def setAcrylicEffect(self, hWnd, gradientColor="99000000", enableShadow=True, animationId=0):
        class ACCENT_POLICY(Structure):
            _fields_ = [
                ("AccentState", c_int),
                ("AccentFlags", c_int),
                ("GradientColor", c_int),
                ("AnimationId", c_int)
            ]

        class WINDOWCOMPOSITIONATTRIBDATA(Structure):
            _fields_ = [
                ("Attribute", c_int),
                ("Data", POINTER(ACCENT_POLICY)),
                ("SizeOfData", c_int)
            ]

        ACCENT_ENABLE_ACRYLICBLURBEHIND = 4
        accent = ACCENT_POLICY()
        accent.AccentState = ACCENT_ENABLE_ACRYLICBLURBEHIND
        accent.AccentFlags = 2
        accent.GradientColor = 0x4DFFFFFF
        accent.AnimationId = animationId

        data = WINDOWCOMPOSITIONATTRIBDATA()
        data.Attribute = 19
        data.Data = byref(accent)
        data.SizeOfData = sizeof(accent)

        self.user32.SetWindowCompositionAttribute(int(hWnd), byref(data))

# --- 全局配置 ---
WM_NCHITTEST = 0x0084
WM_HOTKEY = 0x0312
HOTKEY_ID = 0xB001          # RegisterHotKey 的 id，只要和其它程序不撞就行
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN = 0x0001, 0x0002, 0x0004, 0x0008
DEFAULT_HOTKEY = "Ctrl+G"
FALLBACK_HOTKEY = "Ctrl+Alt+G"   # 默认热键被别的程序占用时自动退到这个
HTCLIENT = 1
HTLEFT, HTRIGHT, HTTOP, HTBOTTOM = 10, 11, 12, 15
HTTOPLEFT, HTTOPRIGHT, HTBOTTOMLEFT, HTBOTTOMRIGHT = 13, 14, 16, 17
BORDER_WIDTH = 15

BG_COLOR_TRANSLUCENT = "rgba(255, 255, 255, 88)"
BORDER_COLOR = "rgba(184, 143, 86, 130)"
ACCENT_COLOR = "rgba(116, 28, 36, 210)"
ACCENT_COLOR_HOVER = "rgba(116, 28, 36, 235)"
MUTED_TEXT_COLOR = "rgba(92, 86, 78, 180)"
SCROLLBAR_COLOR = "rgba(116, 28, 36, 58)"
SCROLLBAR_COLOR_HOVER = "rgba(116, 28, 36, 96)"

# 笔记内容的颜色 (左/右)
TEXT_COLOR_LEFT = "rgba(49, 56, 66, 1)"
TEXT_COLOR_RIGHT = "rgba(91, 74, 60, 1)"

# 选区颜色
SELECTION_COLOR = "rgba(116, 28, 36, 170)"

# 插入光标（自绘）：QSS 没有 caret-color，只能自己画，见 ZoomableTextEdit.paintEvent
CARET_WIDTH = 2
CARET_COLOR = (116, 28, 36, 200)
CARET_BLINK_MS = 530

BULLET_SOLID = "•"
BULLET_HOLLOW = "◦"
B = BULLET_SOLID
C = BULLET_HOLLOW

TITLE_FONT = "Comic Sans MS"
CONTENT_FONT = "Comic Sans MS"
DEFAULT_FONT_SIZE = 12
APP_TITLE = "Gryffindor"
ICON_NAME = "Gryffindor_icon.ico"

# Markdown 保存标记
MD_FORMAT_HEADER = "<!--GRYFFINDOR_RICH_V1-->\n"

# 单实例互斥：第二个实例不弹窗，而是召唤第一个实例到前台
SINGLE_INSTANCE_KEY = "GryffindorSingleInstance_v2"

# --- 路径逻辑 ---
NOTE_MARKERS = ("Gryffindor_note_p1.md", "Gryffindor_note_left.md", "Gryffindor_note_right.md")
if getattr(sys, 'frozen', False):
    EXE_DIR = os.path.dirname(sys.executable)
    # 从 exe 目录向上查找，直到找到笔记文件或到达项目根目录
    candidate = EXE_DIR
    found = False
    for _ in range(5):
        if any(os.path.exists(os.path.join(candidate, m)) for m in NOTE_MARKERS):
            found = True
            break
        parent = os.path.dirname(candidate)
        if parent == candidate:
            break
        candidate = parent
    BASE_DIR = candidate if found else EXE_DIR
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SAVE_FILE_LEFT = os.path.join(BASE_DIR, "Gryffindor_note_left.md")
SAVE_FILE_RIGHT = os.path.join(BASE_DIR, "Gryffindor_note_right.md")

def to_roman(n):
    """整数 → 罗马数字（页签默认编号用，支持无限页）"""
    vals = [(1000, 'M'), (900, 'CM'), (500, 'D'), (400, 'CD'), (100, 'C'),
            (90, 'XC'), (50, 'L'), (40, 'XL'), (10, 'X'), (9, 'IX'),
            (5, 'V'), (4, 'IV'), (1, 'I')]
    out = ""
    for v, s in vals:
        while n >= v:
            out += s
            n -= v
    return out

def page_file_path(index):
    """第 index 页(0-based)的笔记文件路径"""
    return os.path.join(BASE_DIR, f"Gryffindor_note_p{index + 1}.md")

def parse_hotkey(spec):
    """'Ctrl+Alt+G' → (mods, vk)；非法组合返回 None（全局热键注册用）"""
    if not spec:
        return None
    mods, key = 0, None
    for part in str(spec).replace(" ", "").split("+"):
        p = part.lower()
        if p in ("ctrl", "control"):
            mods |= MOD_CONTROL
        elif p == "alt":
            mods |= MOD_ALT
        elif p == "shift":
            mods |= MOD_SHIFT
        elif p in ("win", "meta", "super"):
            mods |= MOD_WIN
        elif len(p) == 1 and (p.isalpha() or p.isdigit()):
            key = ord(p.upper())
        elif re.fullmatch(r"f([1-9]|1[0-2])", p):
            key = 0x70 + int(p[1:]) - 1   # VK_F1 == 0x70
        else:
            return None
    # 必须带修饰键，否则会把普通字母变成全局热键，打字全废
    if key is None or mods == 0:
        return None
    return mods, key

def hotkey_spec_from_event(event):
    """QKeyEvent → 'Ctrl+Shift+G'；只按了修饰键或按键不受支持时返回 None"""
    key = event.key()
    if key in (Qt.Key_Control, Qt.Key_Alt, Qt.Key_Shift, Qt.Key_Meta, Qt.Key_Escape):
        return None
    mods = event.modifiers()
    parts = []
    if mods & Qt.ControlModifier: parts.append("Ctrl")
    if mods & Qt.AltModifier: parts.append("Alt")
    if mods & Qt.ShiftModifier: parts.append("Shift")
    if mods & Qt.MetaModifier: parts.append("Win")
    if Qt.Key_A <= key <= Qt.Key_Z or Qt.Key_0 <= key <= Qt.Key_9:
        parts.append(chr(key))
    elif Qt.Key_F1 <= key <= Qt.Key_F12:
        parts.append(f"F{key - Qt.Key_F1 + 1}")
    else:
        return None
    return "+".join(parts) if len(parts) > 1 else None

def atomic_write_text(path, text):
    """原子写：先写 .tmp 再 os.replace 覆盖，避免断电/崩溃留下半截文件"""
    tmp = path + ".tmp"
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        return True
    except Exception as e:
        log_error(f"atomic_write {os.path.basename(path)}: {e}")
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return False

def text_stats(text):
    """返回 (字符数, 单词数)
    字符数：不含空白字符的字符个数
    单词数：英文单词（含撇号/连字符连接，如 don't、well-known）+ 每个中文字符算 1 词"""
    chars = len(re.sub(r'\s', '', text))
    en_words = len(re.findall(r"[A-Za-z0-9]+(?:['\u2019\-][A-Za-z0-9]+)*", text))
    cjk_chars = len(re.findall(r'[\u3400-\u4dbf\u4e00-\u9fff]', text))
    return chars, en_words + cjk_chars

def log_dir():
    """日志统一放系统目录（%LOCALAPPDATA%\\Gryffindor），程序目录保持干净，
    只留 exe / 源码 / 笔记这些该在的东西"""
    d = os.path.join(os.environ.get("LOCALAPPDATA") or BASE_DIR, "Gryffindor")
    try:
        os.makedirs(d, exist_ok=True)
        return d
    except Exception:
        return BASE_DIR


def log_error(msg):
    """轻量错误日志：静默异常统一写入 error.log，方便排查。
    超过 512KB 自动截断，只保留最近 200 行，防止无限膨胀"""
    path = os.path.join(log_dir(), "error.log")
    try:
        if os.path.exists(path) and os.path.getsize(path) > 512 * 1024:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                tail = f.readlines()[-200:]
            with open(path, 'w', encoding='utf-8') as f:
                f.writelines(tail)
        with open(path, 'a', encoding='utf-8') as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")
    except Exception:
        pass

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = BASE_DIR
    return os.path.join(base_path, relative_path)

# --- Markdown 工具函数 ---

def markdown_to_html(md_text):
    """将 Markdown 纯文本转换为 HTML（用于加载旧的纯文本文件）"""
    lines = md_text.split('\n')
    html_parts = []
    in_code_block = False
    code_lang = ""

    for line in lines:
        # 代码块
        if line.strip().startswith("```"):
            if in_code_block:
                html_parts.append("</code></pre>")
                in_code_block = False
            else:
                code_lang = line.strip()[3:].strip()
                html_parts.append(f'<pre style="background:#f5f5f0;padding:12px;border-radius:8px;font-family:Consolas,monospace;font-size:13px;"><code>')
                in_code_block = True
            continue
        if in_code_block:
            html_parts.append(line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") + "<br>")
            continue

        # 标题
        if line.startswith("###### "):
            html_parts.append(f'<h6>{_inline_md(line[7:])}</h6>')
        elif line.startswith("##### "):
            html_parts.append(f'<h5>{_inline_md(line[6:])}</h5>')
        elif line.startswith("#### "):
            html_parts.append(f'<h4>{_inline_md(line[5:])}</h4>')
        elif line.startswith("### "):
            html_parts.append(f'<h3 style="font-size:16pt;margin:12px 0 4px;">{_inline_md(line[4:])}</h3>')
        elif line.startswith("## "):
            html_parts.append(f'<h2 style="font-size:18pt;margin:14px 0 6px;">{_inline_md(line[3:])}</h2>')
        elif line.startswith("# "):
            html_parts.append(f'<h1 style="font-size:22pt;margin:16px 0 8px;">{_inline_md(line[2:])}</h1>')
        # 分割线
        elif line.strip() in ("---", "***", "___"):
            html_parts.append('<hr style="border:1px solid #ddd;margin:12px 0;">')
        # 引用
        elif line.startswith("> "):
            html_parts.append(f'<blockquote style="border-left:4px solid #ccc;padding-left:12px;color:#666;margin:8px 0;">{_inline_md(line[2:])}</blockquote>')
        # 无序列表
        elif line.startswith("- ") or line.startswith("* "):
            text = line[2:]
            indent = len(line) - len(line.lstrip())
            margin = 4 + (indent // 2) * 16
            html_parts.append(f'<div style="margin-left:{margin}px;">• {_inline_md(text)}</div>')
        # 有序列表
        elif re.match(r'^(\d+)\. ', line):
            m = re.match(r'^(\d+)\. (.*)', line)
            html_parts.append(f'<div style="margin-left:4px;">{m.group(1)}. {_inline_md(m.group(2))}</div>')
        # 普通段落
        elif line.strip():
            html_parts.append(f'<p style="margin:4px 0;">{_inline_md(line)}</p>')
        else:
            html_parts.append('<br>')

    if in_code_block:
        html_parts.append("</code></pre>")

    return "<br>".join(html_parts) if html_parts else ""


def _inline_md(text):
    """处理 Markdown 行内格式 -> HTML"""
    # 先处理转义
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # 行内代码
    text = re.sub(r'`([^`]+)`', r'<code style="background:#f0ede8;padding:2px 5px;border-radius:4px;font-family:Consolas,monospace;">\1</code>', text)

    # 加粗+斜体
    text = re.sub(r'\*\*\*(.+?)\*\*\*', r'<b><i>\1</i></b>', text)
    # 加粗
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.+?)__', r'<b>\1</b>', text)
    # 斜体
    text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)
    text = re.sub(r'_(.+?)_', r'<i>\1</i>', text)
    # 删除线
    text = re.sub(r'~~(.+?)~~', r'<s>\1</s>', text)
    # 高亮
    text = re.sub(r'==(.+?)==', r'<span style="background:#fff3a8;padding:1px 2px;border-radius:3px;">\1</span>', text)

    return text


def rich_to_markdown(document):
    """将 QTextDocument (富文本) 转换为 Markdown 纯文本（用于保存）"""
    md_lines = []
    block = document.begin()

    while block.isValid():
        block_text = block.text()
        block_format = block.blockFormat()
        heading_level = block_format.headingLevel()
        indent = block_format.indent()
        # 检测标题
        if heading_level > 0:
            prefix = "#" * heading_level + " "
            md_lines.append(prefix + _fragments_to_md(block))
        # 检测列表
        elif block_text.strip().startswith("•") or block_text.strip().startswith("·"):
            clean = block_text.strip().lstrip("•·").strip()
            md_lines.append("  " * int(indent) + "- " + _fragments_to_md_simple(block, clean))
        elif re.match(r'^\d+[\.\)]\s', block_text.strip()):
            m = re.match(r'^(\d+[\.\)])\s(.*)', block_text.strip())
            md_lines.append("  " * int(indent) + m.group(1) + " " + _fragments_to_md_simple(block, m.group(2)))
        # 引用
        elif block_text.startswith(">"):
            md_lines.append("> " + _fragments_to_md(block).lstrip("> "))
        # 分割线
        elif block_text.strip() in ("---", "***", "___"):
            md_lines.append("---")
        # 普通段落
        else:
            md_lines.append(_fragments_to_md(block))

        block = block.next()

    return "\n".join(md_lines)


def _fragments_to_md(block):
    """从 block 的文本片段提取行内 Markdown 格式"""
    it = block.begin()
    parts = []
    while not it.atEnd():
        fragment = it.fragment()
        if fragment.isValid():
            text = fragment.text()
            fmt = fragment.charFormat()
            md_text = text

            # 检测格式并包裹 Markdown 语法
            font_weight = fmt.fontWeight()
            italic = fmt.fontItalic()
            strike = fmt.fontStrikeOut()
            bg = fmt.background().color()
            is_highlight = bg.isValid() and bg.name() == "#fff3a8"

            has_bold = font_weight >= QFont.Bold
            has_italic = italic

            if has_bold and has_italic:
                md_text = f"***{text}***"
            elif has_bold:
                md_text = f"**{text}**"
            elif has_italic:
                md_text = f"*{text}*"

            if strike:
                md_text = f"~~{md_text}~~"
            if is_highlight:
                md_text = f"=={md_text}=="

            # 检测行内代码 (等宽字体)
            family = fmt.fontFamily().lower()
            if "consolas" in family or "courier" in family or "monospace" in family:
                md_text = f"`{text}`"

            parts.append(md_text)
        it += 1
    return "".join(parts)


def _fragments_to_md_simple(block, fallback_text):
    """简化的片段提取（列表项用）"""
    result = _fragments_to_md(block)
    # 如果提取的结果以 bullet 开头，去掉
    result = result.lstrip("•·").strip()
    return result if result else fallback_text


# --- 自定义UI组件 ---

class ZoomButton(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setFixedSize(24, 24)
        self.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: rgba(49, 44, 39, 230);
                font-family: Arial;
                font-size: 18px;
                font-weight: bold;
                border: none;
                border-radius: 12px;
            }
            QPushButton:hover {
                background-color: rgba(116, 28, 36, 28);
            }
        """)
        self.setCursor(Qt.PointingHandCursor)

class PinButton(QPushButton):
    toggled_state = pyqtSignal(bool)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(20, 20)
        self.is_pinned = True
        self.hovered = False
        self.setStyleSheet("border: none; background: transparent;")
        self.setToolTip("Toggle Always on Top")

    def enterEvent(self, event): self.hovered = True; self.update()
    def leaveEvent(self, event): self.hovered = False; self.update()
    def mousePressEvent(self, event):
        self.is_pinned = not self.is_pinned
        self.toggled_state.emit(self.is_pinned)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if self.hovered: painter.setBrush(QBrush(QColor(0, 0, 0, 20)))
        else: painter.setBrush(Qt.NoBrush)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(0, 0, 20, 20)
        if self.is_pinned: painter.setBrush(QBrush(QColor(116, 28, 36)))
        else: painter.setBrush(QBrush(QColor(100, 100, 100)))
        painter.drawEllipse(6, 6, 8, 8)

class CloseButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(20, 20)
        self.hovered = False
        self.setStyleSheet("border: none; background: transparent;")

    def enterEvent(self, event): self.hovered = True; self.update()
    def leaveEvent(self, event): self.hovered = False; self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if self.hovered: painter.setBrush(QBrush(QColor(116, 28, 36)))
        else: painter.setBrush(QBrush(QColor(92, 86, 78)))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(0, 0, 20, 20)


# --- 全局热键录制对话框 ---
class HotkeyDialog(QDialog):
    """点开托盘菜单后按组合键即记录；Esc 取消，Backspace 恢复默认"""

    def __init__(self, spec, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Global Hotkey")
        self.setFixedWidth(320)
        self.result_spec = spec or DEFAULT_HOTKEY
        lay = QVBoxLayout(self)
        lay.setSpacing(8)
        tip = QLabel("Press the combination you want.\nEsc = cancel, Backspace = reset to default.")
        tip.setStyleSheet("color: rgba(60, 55, 50, 220); font-size: 11px;")
        self.preview = QLabel(self.result_spec)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setStyleSheet(
            "background: rgba(255, 255, 255, 150);"
            "border: 1px solid rgba(184, 143, 86, 90); border-radius: 9px;"
            "padding: 12px; font-size: 14pt; color: rgba(116, 28, 36, 230);")
        btns = QHBoxLayout()
        btn_ok = QPushButton("Save")
        btn_cancel = QPushButton("Cancel")
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_ok)
        btns.addWidget(btn_cancel)
        lay.addWidget(tip)
        lay.addWidget(self.preview)
        lay.addLayout(btns)
        self.setFocusPolicy(Qt.StrongFocus)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.reject()
            return
        if event.key() == Qt.Key_Backspace:
            self.result_spec = DEFAULT_HOTKEY
            self.preview.setText(self.result_spec)
            return
        spec = hotkey_spec_from_event(event)
        if spec:
            self.result_spec = spec
            self.preview.setText(spec)

    def accept(self):
        if parse_hotkey(self.result_spec) is None:
            QMessageBox.warning(self, "Invalid Hotkey",
                                "Need at least one modifier (Ctrl / Alt / Shift / Win) plus a letter, digit or F1-F12.")
            return
        super().accept()


# --- Markdown 编辑器 ---
class MarkdownEditor(QTextEdit):
    """支持 Markdown 快捷键和自动转换的编辑器"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(True)
        self._converting = False
        self._note_pane = None  # set by NotePane after construction

    # --- 拖文件进窗口：.md/.txt 导入为新页，图片插入正文 ---
    def _dropped_local_files(self, event):
        md = event.mimeData()
        if not md.hasUrls():
            return []
        return [u.toLocalFile() for u in md.urls() if u.isLocalFile()]

    def dragEnterEvent(self, event):
        if self._dropped_local_files(event):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if self._dropped_local_files(event):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event):
        files = self._dropped_local_files(event)
        pane = self._note_pane
        main_win = getattr(pane, "main_win", None) if pane is not None else None
        if files and main_win is not None:
            for path in files:
                main_win.handle_dropped_file(path)
            event.acceptProposedAction()
            return
        super().dropEvent(event)

    def keyPressEvent(self, event):
        # Ctrl+B → 加粗切换
        if event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_B:
            self._toggle_bold()
            return

        # Ctrl+Shift+H → 高亮切换
        if (event.modifiers() == (Qt.ControlModifier | Qt.ShiftModifier) and
                event.key() == Qt.Key_H):
            self._toggle_highlight()
            return

        # Ctrl+I → 斜体切换
        if event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_I:
            self._toggle_italic()
            return

        # Ctrl+Shift+] → 激活当前行实心点模式
        if (event.modifiers() == (Qt.ControlModifier | Qt.ShiftModifier) and
                event.key() == Qt.Key_BracketRight):
            self._insert_bullet_point()
            return

        # Tab → 在 •/◦ 行加深级别
        if event.key() == Qt.Key_Tab:
            if self._handle_bullet_tab():
                return

        # Shift+Tab → 在 bullet 行退级
        if event.key() == Qt.Key_Backtab:
            if self._handle_bullet_shift_tab():
                return

        # Backspace → 在 bullet 行行首退级：◦→•→无前缀
        if event.key() == Qt.Key_Backspace:
            if self._handle_bullet_backspace():
                return

        # Enter → 若在 •/◦ 行续行，否则正常换行
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self._handle_bullet_enter():
                return
            super().keyPressEvent(event)
            QTimer.singleShot(0, self._convert_current_line)
            return

        # Space → 尝试转换行首模式（标题、列表）
        if event.key() == Qt.Key_Space:
            super().keyPressEvent(event)
            QTimer.singleShot(0, self._convert_on_space)
            return

        super().keyPressEvent(event)

    def _insert_bullet_point(self):
        """Ctrl+Shift+] : 激活/取消当前行实心点模式"""
        cursor = self.textCursor()
        block = cursor.block()
        text = block.text()
        stripped = text.strip()
        char_fmt = QTextCharFormat()
        if self._note_pane is not None:
            char_fmt.setFontPointSize(self._note_pane.current_font_size)
        # toggle off: 已是 bullet 就移除
        if stripped.startswith(B) or stripped.startswith(C):
            bullet_char = stripped[0]
            bullet_pos = text.index(bullet_char)
            cursor.setPosition(block.position() + bullet_pos)
            cursor.setPosition(block.position() + bullet_pos + 2, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()
            block_fmt = cursor.blockFormat()
            block_fmt.setIndent(0)
            cursor.setBlockFormat(block_fmt)
            self.setTextCursor(cursor)
            return
        # 在行首插入 bullet，光标保持相对位置
        saved_pos = cursor.position()
        cursor.movePosition(QTextCursor.StartOfBlock)
        cursor.insertText(B + " ", char_fmt)
        new_cursor = self.textCursor()
        new_cursor.setPosition(saved_pos + 2)
        self.setTextCursor(new_cursor)

    def _handle_bullet_enter(self):
        """Enter 在 •/◦ 行续行，返回 True 已处理。"""
        cursor = self.textCursor()
        block = cursor.block()
        stripped = block.text().strip()
        is_solid = stripped.startswith('•')
        is_hollow = stripped.startswith('◦')
        if not (is_solid or is_hollow):
            return False
        content_after = stripped[1:].strip()
        if not content_after:
            cursor.movePosition(QTextCursor.StartOfBlock)
            cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()
            block_fmt = cursor.blockFormat()
            block_fmt.setIndent(0)
            cursor.setBlockFormat(block_fmt)
            self.setTextCursor(cursor)
            return True
        bullet = '• ' if is_solid else '◦ '
        indent_level = cursor.blockFormat().indent()
        char_fmt = QTextCharFormat()
        if self._note_pane is not None:
            char_fmt.setFontPointSize(self._note_pane.current_font_size)
        cursor.movePosition(QTextCursor.EndOfBlock)
        cursor.insertBlock()
        block_fmt = cursor.blockFormat()
        block_fmt.setIndent(indent_level)
        cursor.setBlockFormat(block_fmt)
        cursor.insertText(bullet, char_fmt)
        self.setTextCursor(cursor)
        return True

    def _handle_bullet_tab(self):
        """Tab: bullet行加深级别 / 数字列表行增加缩进，返回True已处理。"""
        cursor = self.textCursor()
        block = cursor.block()
        text = block.text().strip()
        # bullet 行
        if text.startswith("•"):
            self._replace_bullet_char(cursor, block, "•", "◦", delta_indent=1)
            return True
        elif text.startswith("◦"):
            self._replace_bullet_char(cursor, block, "◦", "◦", delta_indent=1)
            return True
        # 数字列表行：Tab 增加 leftMargin 缩进
        elif re.match(r"^\d+\. ", text):
            block_fmt = block.blockFormat()
            block_fmt.setLeftMargin(block_fmt.leftMargin() + 20)
            cursor.setBlockFormat(block_fmt)
            return True
        return False

    def _handle_bullet_backspace(self):
        """Backspace 在 bullet 行行首处退级，返回 True 已处理。"""
        cursor = self.textCursor()
        block = cursor.block()
        text = block.text()
        stripped = text.strip()
        is_solid = stripped.startswith(B)
        is_hollow = stripped.startswith(C)
        if not (is_solid or is_hollow):
            return False
        bullet_char = B if is_solid else C
        bullet_pos = text.index(bullet_char)
        # 光标在 bullet 区域内才拦截
        if cursor.positionInBlock() > bullet_pos + 2:
            return False
        if is_hollow:
            self._replace_bullet_char(cursor, block, C, B, delta_indent=-1)
        else:
            cursor.setPosition(block.position() + bullet_pos)
            cursor.setPosition(block.position() + bullet_pos + 2, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()
            block_fmt = cursor.blockFormat()
            block_fmt.setIndent(0)
            cursor.setBlockFormat(block_fmt)
            self.setTextCursor(cursor)
        return True

    def _handle_bullet_shift_tab(self):
        """Shift+Tab: bullet行退级 / 数字列表行减少缩进，返回True已处理。"""
        cursor = self.textCursor()
        block = cursor.block()
        text = block.text().strip()
        if text.startswith("◦"):
            self._replace_bullet_char(cursor, block, "◦", "•", delta_indent=-1)
            return True
        elif text.startswith("•"):
            full_text = block.text()
            bullet_pos = full_text.index("•")
            cursor.setPosition(block.position() + bullet_pos)
            cursor.setPosition(block.position() + bullet_pos + 2, cursor.KeepAnchor)
            cursor.removeSelectedText()
            block_fmt = cursor.blockFormat()
            block_fmt.setIndent(0)
            cursor.setBlockFormat(block_fmt)
            self.setTextCursor(cursor)
            return True
        elif re.match(r"^\d+\. ", text):
            block_fmt = block.blockFormat()
            new_margin = max(0, block_fmt.leftMargin() - 20)
            block_fmt.setLeftMargin(new_margin)
            cursor.setBlockFormat(block_fmt)
            return True
        return False

    def _replace_bullet_char(self, cursor, block, old_char, new_char, delta_indent):
        """替换行首 bullet 字符并调整缩进"""
        text = block.text()
        pos_in_block = text.index(old_char)
        cursor.setPosition(block.position() + pos_in_block)
        cursor.setPosition(block.position() + pos_in_block + 1, QTextCursor.KeepAnchor)
        char_fmt = QTextCharFormat()
        if self._note_pane is not None:
            char_fmt.setFontPointSize(self._note_pane.current_font_size)
        cursor.insertText(new_char, char_fmt)
        block_fmt = cursor.blockFormat()
        new_indent = max(0, block_fmt.indent() + delta_indent)
        block_fmt.setIndent(new_indent)
        cursor.setBlockFormat(block_fmt)
        self.setTextCursor(cursor)

    def _toggle_bold(self):
        cursor = self.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.WordUnderCursor)
        if not cursor.hasSelection():
            return
        fmt = cursor.charFormat()
        new_fmt = QTextCharFormat(fmt)
        new_fmt.setFontWeight(QFont.Normal if fmt.fontWeight() >= QFont.Bold else QFont.Bold)
        cursor.mergeCharFormat(new_fmt)

    def _toggle_italic(self):
        cursor = self.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.WordUnderCursor)
        if not cursor.hasSelection():
            return
        fmt = cursor.charFormat()
        new_fmt = QTextCharFormat(fmt)
        new_fmt.setFontItalic(not fmt.fontItalic())
        cursor.mergeCharFormat(new_fmt)

    def _toggle_highlight(self):
        cursor = self.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.WordUnderCursor)
        if not cursor.hasSelection():
            return

        # 检测选区内所有 fragment 是否全部都已高亮：全部高亮 → 取消，否则 → 添加
        doc = self.document()
        sel_start = cursor.selectionStart()
        sel_end = cursor.selectionEnd()
        all_highlighted = True
        block = doc.findBlock(sel_start)
        while block.isValid() and block.position() <= sel_end:
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid():
                    frag_start = frag.position()
                    frag_end = frag_start + frag.length()
                    # 只检查与选区有重叠的 fragment
                    if frag_end > sel_start and frag_start < sel_end:
                        bg = frag.charFormat().background()
                        if not (bg.style() != 0 and bg.color().name() == "#fff3a8"):
                            all_highlighted = False
                            break
                it += 1
            if not all_highlighted:
                break
            block = block.next()

        # 根据检测结果应用格式
        # 注意：必须用 mergeCharFormat 而非 setCharFormat，否则会清除已有粗体/斜体等格式
        new_fmt = QTextCharFormat()
        if all_highlighted:
            # 取消高亮：用全透明背景色覆盖（clearBackground() 在 PyQt5 中无效）
            new_fmt.setBackground(QColor(0, 0, 0, 0))
        else:
            new_fmt.setBackground(QColor("#fff3a8"))
        cursor.mergeCharFormat(new_fmt)

    def _convert_on_space(self):
        """在空格后转换：标题(# )、列表(- / * / 1. )、引用(> )、分割线(--- )"""
        if self._converting:
            return
        cursor = self.textCursor()
        block = cursor.block()
        text = block.text()

        # 标题：# , ## , ### , #### , ##### , ######
        # 容许行首有空格，末尾一个空格即触发
        m = re.match(r'^\s*(#{1,6})\s$', text)
        if m:
            self._apply_heading(block, len(m.group(1)))
            return

        # 无序列表：- 或 * 后跟空格
        if text.strip() in ("-", "*"):
            self._apply_bullet(block)
            return

        # 有序列表：数字. 后跟空格
        m = re.match(r'^(\d+)[\.\)]\s$', text)
        if m:
            self._apply_numbered_list(block, m.group(1))
            return

        # 引用：> 后跟空格
        if text.strip() == ">":
            self._apply_blockquote(block)
            return

        # 分割线：--- 或 *** 或 ___ 后跟空格
        if text.strip() in ("---", "***", "___"):
            self._apply_hr(block)
            return

    def _convert_current_line(self):
        """在 Enter 后转换上一行的内联 Markdown"""
        if self._converting:
            return
        cursor = self.textCursor()
        # 获取上一行（Enter 后光标在新行，上一行 = block.previous）
        prev_block = cursor.block().previous()
        if not prev_block.isValid():
            return

        text = prev_block.text()
        if not text.strip():
            return

        self._converting = True
        try:
            self._apply_inline_formatting(prev_block)
        finally:
            self._converting = False

    def _apply_heading(self, block, level):
        """应用标题格式"""
        self._converting = True
        try:
            cursor = QTextCursor(block)
            cursor.movePosition(QTextCursor.StartOfBlock)
            cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)

            # 去掉 # 前缀
            text = block.text()
            m = re.match(r'^#{1,6}\s*(.*)', text)
            clean_text = m.group(1) if m else text

            # 设置标题格式
            block_fmt = block.blockFormat()
            block_fmt.setHeadingLevel(level)
            cursor.setBlockFormat(block_fmt)

            # 设置字体大小（相对 current_font_size 缩放，保持层级意义）
            base = self._note_pane.current_font_size if self._note_pane is not None else DEFAULT_FONT_SIZE
            ratios = {1: 1.8, 2: 1.5, 3: 1.3, 4: 1.15, 5: 1.05, 6: 1.0}
            char_fmt = QTextCharFormat()
            char_fmt.setFontPointSize(max(base * ratios.get(level, 1.0), float(base)))
            char_fmt.setFontWeight(QFont.Bold)
            cursor.insertText(clean_text, char_fmt)

            # 重置段落格式（避免后续输入也变标题）
            cursor.movePosition(QTextCursor.EndOfBlock)
            reset_fmt = QTextCharFormat()
            reset_fmt.setFontPointSize(self._note_pane.current_font_size if self._note_pane is not None else DEFAULT_FONT_SIZE)
            reset_fmt.setFontWeight(QFont.Normal)
            cursor.setCharFormat(reset_fmt)
            self.setTextCursor(cursor)
        finally:
            self._converting = False

    def _apply_bullet(self, block):
        """应用无序列表格式"""
        self._converting = True
        try:
            cursor = QTextCursor(block)
            cursor.movePosition(QTextCursor.StartOfBlock)
            cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)

            # 插入 bullet 符号
            char_fmt = QTextCharFormat()
            if self._note_pane is not None:
                char_fmt.setFontPointSize(self._note_pane.current_font_size)

            cursor.insertText("• ", char_fmt)
        finally:
            self._converting = False

    def _apply_numbered_list(self, block, num):
        """应用有序列表格式（无缩进，正常排列）"""
        self._converting = True
        try:
            cursor = QTextCursor(block)
            # 先清除缩进
            block_fmt = block.blockFormat()
            block_fmt.setIndent(0)
            block_fmt.setLeftMargin(0)
            cursor.setBlockFormat(block_fmt)
            cursor.movePosition(QTextCursor.StartOfBlock)
            cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
            char_fmt = QTextCharFormat()
            if self._note_pane is not None:
                char_fmt.setFontPointSize(self._note_pane.current_font_size)
            cursor.insertText(f"{num}. ", char_fmt)
        finally:
            self._converting = False

    def _apply_blockquote(self, block):
        """应用引用格式"""
        self._converting = True
        try:
            cursor = QTextCursor(block)
            cursor.movePosition(QTextCursor.StartOfBlock)
            cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)

            text = block.text().lstrip("> ").strip()
            char_fmt = QTextCharFormat()
            if self._note_pane is not None:
                char_fmt.setFontPointSize(self._note_pane.current_font_size)

            char_fmt.setForeground(QColor("#666666"))
            char_fmt.setFontItalic(True)
            cursor.insertText(text, char_fmt)

            block_fmt = block.blockFormat()
            left_margin = block_fmt.leftMargin()
            block_fmt.setLeftMargin(left_margin + 20)
            cursor.setBlockFormat(block_fmt)
        finally:
            self._converting = False

    def _apply_hr(self, block):
        """应用分割线"""
        self._converting = True
        try:
            cursor = QTextCursor(block)
            cursor.movePosition(QTextCursor.StartOfBlock)
            cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
            cursor.insertText("─" * 40)

            char_fmt = QTextCharFormat()
            char_fmt.setForeground(QColor("#bbbbbb"))
            cursor.select(QTextCursor.BlockUnderCursor)
            cursor.mergeCharFormat(char_fmt)
        finally:
            self._converting = False

    def _apply_inline_formatting(self, block):
        """转换行内 Markdown 格式：**粗体**、*斜体*、~~删除线~~、==高亮==、`代码`
        每处理一个匹配后重新扫描文本：删除标记字符会使后续偏移失效，不能复用一次 finditer 的位置"""
        patterns = [
            (r'`([^`]+)`', "code"),
            (r'\*\*(.+?)\*\*', "bold"),
            (r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', "italic"),
            (r'~~(.+?)~~', "strike"),
            (r'==(.+?)==', "highlight"),
        ]
        for pattern, fmt_type in patterns:
            while True:
                text = block.text()
                m = re.search(pattern, text)
                if not m:
                    break
                self._apply_span_format(block, m.start(1), m.end(1), fmt_type)

    def _apply_span_format(self, block, start, end, fmt_type):
        """对指定范围内（相对 block 的偏移）应用格式并移除 Markdown 标记"""
        cursor = QTextCursor(block)

        cursor.setPosition(block.position() + start)
        cursor.setPosition(block.position() + end, QTextCursor.KeepAnchor)

        char_fmt = QTextCharFormat()
        if fmt_type == "bold":
            char_fmt.setFontWeight(QFont.Bold)
        elif fmt_type == "italic":
            char_fmt.setFontItalic(True)
        elif fmt_type == "strike":
            char_fmt.setFontStrikeOut(True)
        elif fmt_type == "highlight":
            char_fmt.setBackground(QColor("#fff3a8"))
        elif fmt_type == "code":
            char_fmt.setFontFamily("Consolas")
            char_fmt.setBackground(QColor("#f0ede8"))
            _sz = self._note_pane.current_font_size if self._note_pane else 11
            char_fmt.setFontPointSize(_sz)

        cursor.mergeCharFormat(char_fmt)

        # 移除标记符号（从后往前删，避免偏移）
        if fmt_type == "bold":
            # 移除 ** 前缀和 ** 后缀
            self._remove_markers(cursor, block, start, 2, end, 2)
        elif fmt_type == "italic":
            self._remove_markers(cursor, block, start, 1, end, 1)
        elif fmt_type in ("strike", "highlight"):
            self._remove_markers(cursor, block, start, 2, end, 2)
        elif fmt_type == "code":
            self._remove_markers(cursor, block, start, 1, end, 1)

    def _remove_markers(self, cursor, block, content_start, prefix_len, content_end, suffix_len):
        """移除 Markdown 标记符号（前缀和后缀），保留内容"""
        # 先删后缀
        cursor.setPosition(block.position() + content_end)
        cursor.setPosition(block.position() + content_end + suffix_len, QTextCursor.KeepAnchor)
        cursor.removeSelectedText()

        # 再删前缀
        cursor.setPosition(block.position() + content_start - prefix_len)
        cursor.setPosition(block.position() + content_start, QTextCursor.KeepAnchor)
        cursor.removeSelectedText()


class CustomTitleBar(QWidget):
    zoom_signal = pyqtSignal(int)

    def __init__(self, parent):
        super().__init__(parent)
        self.main_win = parent  # 主窗口引用（不覆盖 Qt 内建的 parent() 方法）
        self.setFixedHeight(50)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(25, 0, 20, 0)
        self.layout.setSpacing(8)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.title_label = QLabel(APP_TITLE)
        font = QFont(TITLE_FONT, 18, QFont.Bold)
        self.title_label.setFont(font)

        self.title_label.setStyleSheet(f"""
            QLabel {{
                color: rgba(49, 44, 39, 235);
                background: transparent;
                font-family: '{TITLE_FONT}', 'Microsoft YaHei';
                font-weight: bold;
            }}
        """)

        self.btn_zoom_out = ZoomButton("-", self)
        self.btn_zoom_out.setToolTip("Zoom Out Font")
        self.btn_zoom_out.clicked.connect(lambda: self.zoom_signal.emit(-1))

        self.btn_zoom_in = ZoomButton("+", self)
        self.btn_zoom_in.setToolTip("Zoom In Font")
        self.btn_zoom_in.clicked.connect(lambda: self.zoom_signal.emit(1))

        self.pin_btn = PinButton(self)
        self.pin_btn.toggled_state.connect(self.main_win.toggle_always_on_top)
        self.close_btn = CloseButton(self)
        self.close_btn.clicked.connect(self.main_win.minimize_window)

        self.layout.addWidget(self.title_label)
        self.layout.addStretch()
        self.layout.addWidget(self.btn_zoom_out)
        self.layout.addWidget(self.btn_zoom_in)
        self.layout.addWidget(self.pin_btn)
        self.layout.addWidget(self.close_btn)

        self.start_pos = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.main_win.stop_dock_animation()
            self.start_pos = event.globalPos() - self.main_win.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self.start_pos:
            self.main_win.move(event.globalPos() - self.start_pos)
            event.accept()


class ZoomableTextEdit(MarkdownEditor):
    """继承 MarkdownEditor 的缩放功能 + 自绘插入光标"""

    def __init__(self, parent=None):
        super().__init__(parent)
        # Qt 的 QSS 没有 caret-color，原生光标颜色只能取自 QPalette::Text，
        # 而 update_styles() 里的 color 正好覆盖它 → 想换个显眼的颜色只能自绘。
        # 原生光标置 0 宽（不绘制），改用 accent 圆角竖条，见 paintEvent。
        self.setCursorWidth(0)
        self._caret_on = True
        self._caret_timer = QTimer(self)
        self._caret_timer.setInterval(CARET_BLINK_MS)
        self._caret_timer.timeout.connect(self._blink_caret)
        self._caret_timer.start()

    def _blink_caret(self):
        self._caret_on = not self._caret_on
        if self.hasFocus():
            self.viewport().update()

    def _kick_caret(self):
        """输入/点击后光标立刻显示，并重置闪烁节拍（和系统光标手感一致）"""
        self._caret_on = True
        self._caret_timer.start()
        self.viewport().update()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._kick_caret()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.viewport().update()

    def keyPressEvent(self, event):
        super().keyPressEvent(event)
        self._kick_caret()

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self._kick_caret()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.hasFocus() or not self._caret_on or self.isReadOnly():
            return
        if self.textCursor().hasSelection():
            return  # 选中状态不画插入点，和系统行为一致
        r = self.cursorRect()
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(*CARET_COLOR))
        painter.drawRoundedRect(
            QRect(r.left(), r.top() + 1, CARET_WIDTH, max(r.height() - 2, 6)), 1, 1)
        painter.end()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0: self.parent().change_font_size(1)
            elif delta < 0: self.parent().change_font_size(-1)
            event.accept()
        else:
            super().wheelEvent(event)


class NotePane(QWidget):
    text_changed = pyqtSignal()

    def __init__(self, parent=None, is_left=False):
        super().__init__(parent)
        self.is_left = is_left
        self.current_font_size = DEFAULT_FONT_SIZE

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.editor = ZoomableTextEdit(self)
        self.editor._note_pane = self  # allow MarkdownEditor to access font size
        self.editor.setPlaceholderText("")
        self.editor.setLineWrapMode(QTextEdit.WidgetWidth)
        self.editor.setAcceptRichText(True)
        self.editor.textChanged.connect(self.on_text_change)
        self.editor.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.editor.setFrameShape(QFrame.NoFrame)
        self.editor.setAcceptDrops(True)
        # 让文档内相对图片路径（images/xxx.png）按程序目录解析
        self.editor.document().setBaseUrl(QUrl.fromLocalFile(BASE_DIR + os.sep))

        stats_color = TEXT_COLOR_LEFT if is_left else TEXT_COLOR_RIGHT
        self.stats_label = QLabel("Chars 0 · Words 0")
        self.stats_label.setAlignment(Qt.AlignRight)
        self.stats_label.setStyleSheet(f"background-color: transparent; color: {MUTED_TEXT_COLOR}; font-size: 10px; padding: 2px 8px 5px 8px;")

        # 统计节流：连续输入时只在停顿 150ms 后统计一次，避免每次按键全量跑正则
        self.stats_timer = QTimer(self)
        self.stats_timer.setSingleShot(True)
        self.stats_timer.timeout.connect(self._update_stats)

        self.layout.addWidget(self.editor)
        self.layout.addWidget(self.stats_label)

        self.update_styles()

    def on_text_change(self):
        self.text_changed.emit()
        self.stats_timer.start(150)

    def _update_stats(self):
        chars, words = text_stats(self.editor.toPlainText())
        self.stats_label.setText(f"Chars {chars} · Words {words}")

    def set_content(self, text):
        """加载内容：判断是富文本还是纯文本"""
        if text.startswith(MD_FORMAT_HEADER):
            # 富文本 HTML
            html = text[len(MD_FORMAT_HEADER):]
            self.editor.setHtml(html)
        elif text.strip():
            # 纯 Markdown → 转换为富文本
            html = markdown_to_html(text)
            self.editor.setHtml(html)
        else:
            self.editor.setPlainText("")
        # 加载完成后，把所有 fragment 字号归一到 current_font_size
        self._normalize_font_sizes()
        self._update_stats()  # 切页/加载后统计立即可见

    def get_html_content(self):
        """获取内容为 HTML（用于带格式保存）"""
        return self.editor.toHtml()

    def _collect_format_runs(self):
        """只读一遍文档，收集 [(position, length, headingLevel, charFormat)]。

        ⚠ 必须"先收集、后修改"：QTextBlock::iterator 指向文档内部结构，
        遍历过程中调 mergeCharFormat 会让它失效，随后 it += 1 / it.fragment()
        会读到已释放的结构 —— 原生崩溃（0xC0000005，崩在 Qt5Gui，Python 层抓不到）。
        mergeCharFormat 只改字符格式、不改文本，所以收集到的 position/length 在
        第二遍里依然有效。"""
        doc = self.editor.document()
        runs = []
        block = doc.begin()
        while block.isValid():
            heading = block.blockFormat().headingLevel()
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid():
                    runs.append((frag.position(), frag.length(), heading, frag.charFormat()))
                it += 1
            block = block.next()
        return runs

    def _apply_format_runs(self, runs, pick_point_size):
        """第二遍：按 runs 批量套字号。pick_point_size(heading, old_pt) -> 新的磅值"""
        self.editor.blockSignals(True)
        try:
            cur = QTextCursor(self.editor.document())
            cur.beginEditBlock()   # 合并成一次撤销步骤
            for pos, length, heading, old_fmt in runs:
                nfmt = QTextCharFormat(old_fmt)
                nfmt.setFontPointSize(pick_point_size(heading, old_fmt.fontPointSize()))
                cur.setPosition(pos)
                cur.setPosition(pos + length, QTextCursor.KeepAnchor)
                cur.mergeCharFormat(nfmt)
            cur.endEditBlock()
        finally:
            self.editor.blockSignals(False)

    def change_font_size(self, delta):
        new_size = self.current_font_size + delta
        if not (8 <= new_size <= 72):
            return
        ratio = new_size / self.current_font_size
        self.current_font_size = new_size
        self.update_styles()
        h_ratios = {1: 1.8, 2: 1.5, 3: 1.3, 4: 1.15, 5: 1.05, 6: 1.0}
        runs = self._collect_format_runs()

        def pick(heading, old_pt):
            # old_pt==0 表示该 fragment 用的是继承字体，也要设置到目标字号
            if old_pt > 0:
                if heading > 0:
                    return max(new_size * h_ratios.get(heading, 1.0), float(new_size))
                return max(8.0, min(72.0, round(old_pt * ratio, 1)))
            if heading == 0:
                return float(new_size)
            return max(new_size * h_ratios.get(heading, 1.0), float(new_size))

        self._apply_format_runs(runs, pick)

    def _normalize_font_sizes(self):
        """将文档内所有 fragment 的字号统一到 current_font_size（标题按倍率，正文统一）"""
        base = self.current_font_size
        h_ratios = {1: 1.8, 2: 1.5, 3: 1.3, 4: 1.15, 5: 1.05, 6: 1.0}
        runs = self._collect_format_runs()

        def pick(heading, old_pt):
            if heading > 0:
                return max(base * h_ratios.get(heading, 1.0), float(base))
            return float(base)

        self._apply_format_runs(runs, pick)

    def update_styles(self):
        text_color = TEXT_COLOR_LEFT if self.is_left else TEXT_COLOR_RIGHT

        self.editor.setStyleSheet(f"""
            QTextEdit {{
                background: transparent;
                border: none;
                color: {text_color};
                padding: 12px 14px;
                font-family: '{CONTENT_FONT}', sans-serif;
                font-size: {self.current_font_size}pt;
                selection-background-color: {SELECTION_COLOR};
                selection-color: #FFFFFF;
            }}
            QScrollBar:vertical {{ border: none; background: transparent; width: 6px; }}
            QScrollBar::handle:vertical {{ background: {SCROLLBAR_COLOR}; border-radius: 3px; }}
            QScrollBar::handle:vertical:hover {{ background: {SCROLLBAR_COLOR_HOVER}; }}
        """)


class GryffindorNote(QWidget):
    def __init__(self):
        super().__init__()
        self._duplicate_exit = False
        # 防多开：已有实例在跑时，向它发"show"后本实例直接退出
        if not self.try_single_instance():
            self._duplicate_exit = True
            return
        self.settings = QSettings("GryffindorSoft", APP_TITLE)
        self.ignore_docking = False
        self.dock_armed = False   # 鼠标进过窗口才允许吸附，避免叫出来的窗口被反复推走
        self.dock_animation = None
        self.dock_animation_target = None
        self.window_effect = WindowEffect()
        self.bg_alpha = 88

        # 图标只加载一次，init_ui / init_tray 共用
        icon_path = resource_path(ICON_NAME)
        self.app_icon = QIcon(icon_path) if os.path.exists(icon_path) else self.style().standardIcon(QStyle.SP_ComputerIcon)

        self.auto_save_timer = QTimer(self)
        self.auto_save_timer.setSingleShot(True)
        self.auto_save_timer.timeout.connect(self.save_window_state)

        # 笔记内容落盘防抖：500ms 内无新输入才写文件，避免每个按键都全量写盘
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.timeout.connect(self.flush_notes)

        # 吸附功能定时器
        self.dock_timer = QTimer(self)
        self.dock_timer.timeout.connect(self.check_docking)

        # 多页状态：页名列表 + 当前页（无旧配置时默认一页，罗马数字编号）
        saved_names = self.settings.value("page_names")
        if isinstance(saved_names, str):
            saved_names = [saved_names] if saved_names else None
        self.page_names = list(saved_names) if saved_names else ["I"]
        saved_cur = self.settings.value("current_page", 0, type=int)
        self.current_page = saved_cur if 0 <= saved_cur < len(self.page_names) else 0
        self._loading_pages = False
        self._tab_drag_pending = False   # 鼠标按在页签上：拖拽期间禁止切页逻辑插手
        self._tab_armed = False          # 刚点过页签（F2/Del 作用于页签而非正文）
        self._tab_drag_moved = False     # 本次按下是否真的拖动了页签
        self.hotkey_spec = self.settings.value("hotkey", DEFAULT_HOTKEY) or DEFAULT_HOTKEY
        self.hotkey_ok = False
        self._toggle_pending = False     # 热键已排队但还没执行（防连按触发两次）
        self._page_text_cache = {}  # 搜索用页面纯文本缓存：idx -> (mtime, text)

        # 旧版左右栏内容一次性迁移为第 I / II 页（须在 init_ui 建页签前执行）
        self.migrate_legacy_notes()

        self.init_ui()
        self.init_tray()
        self.register_global_hotkey()
        self.load_window_state()
        self.set_auto_start()
        self.load_notes()
        self._arm_tab_keys()      # 一启动就是页签上下文：选中的页签按 Del 就能删

        QApplication.instance().aboutToQuit.connect(self.save_window_state)
        QApplication.instance().aboutToQuit.connect(self.flush_notes)
        QApplication.instance().aboutToQuit.connect(self.unregister_global_hotkey)
        self.dock_timer.start(80)

    def moveEvent(self, event): super().moveEvent(event); self.auto_save_timer.start(500)
    def resizeEvent(self, event): super().resizeEvent(event); self.auto_save_timer.start(500)
    def showEvent(self, event): self.enable_blur(); super().showEvent(event)

    def enterEvent(self, event):
        """鼠标进过窗口，才允许「鼠标移开后自动吸附」"""
        self.dock_armed = True
        super().enterEvent(event)

    # --- 单实例防多开 ---
    def try_single_instance(self):
        """已有实例在跑 → 给它发 show 并返回 False（本实例退出）；
        否则注册监听服务并返回 True。崩溃残留的管道也会先清掉"""
        sock = QLocalSocket()
        sock.connectToServer(SINGLE_INSTANCE_KEY)
        if sock.waitForConnected(300):
            sock.write(b"show")
            sock.flush()
            sock.waitForBytesWritten(300)
            sock.disconnectFromServer()
            return False
        QLocalServer.removeServer(SINGLE_INSTANCE_KEY)  # 清理上次崩溃残留
        self._single_server = QLocalServer()
        self._single_server.listen(SINGLE_INSTANCE_KEY)
        self._single_server.newConnection.connect(self._on_single_connection)
        return True

    def _on_single_connection(self):
        """第二个实例发来 show → 把自己召唤到前台"""
        sock = self._single_server.nextPendingConnection()
        if sock is None:
            return
        sock.waitForReadyRead(300)
        data = bytes(sock.readAll()).strip()
        sock.disconnectFromServer()
        if data == b"show":
            self.show_normal()
        elif data == b"quit":
            # 外部（升级脚本/换 exe 前）可以让它优雅退出：先落盘再退，不留数据风险
            try:
                self.flush_notes()
                self.save_window_state()
            finally:
                self.unregister_global_hotkey()
                QApplication.quit()

    def enable_blur(self):
        try: self.window_effect.setAcrylicEffect(self.winId())
        except: pass

    def init_ui(self):
        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(self.app_icon)
        self.resize(850, 550)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.bg_widget = QFrame()
        self.bg_widget.setObjectName("BgFrame")
        self.bg_widget.setStyleSheet(f"""
            QFrame#BgFrame {{
                background-color: {BG_COLOR_TRANSLUCENT};
                border-radius: 10px;
                border: 1px solid {BORDER_COLOR};
            }}
        """)

        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(20)
        self.shadow.setColor(QColor(0, 0, 0, 50))
        self.bg_widget.setGraphicsEffect(self.shadow)

        self.bg_layout = QVBoxLayout(self.bg_widget)
        self.bg_layout.setContentsMargins(4, 4, 4, 4)
        self.bg_layout.setSpacing(0)

        self.title_bar = CustomTitleBar(self)
        self.title_bar.zoom_signal.connect(self.handle_zoom)
        self.bg_layout.addWidget(self.title_bar)

        # --- 页签栏（标题栏正下方，罗马数字编号） ---
        self.sheet_bar = QWidget()
        self.sheet_bar.setAttribute(Qt.WA_TranslucentBackground)
        bar = QHBoxLayout(self.sheet_bar)
        bar.setContentsMargins(12, 2, 12, 4)
        bar.setSpacing(4)

        self.tab_bar = QTabBar()
        self.tab_bar.setExpanding(False)
        self.tab_bar.setDrawBase(False)
        self.tab_bar.setUsesScrollButtons(True)
        # 关键：字号设在控件本体而非仅样式表，否则 sizeHint 用默认字体测量，
        # 实际渲染字更宽 → 长名字被硬截断（"Daily Task" 显示成 "Daily Tas"）
        tab_font = QFont(TITLE_FONT, 10)
        self.tab_bar.setFont(tab_font)
        self.tab_bar.setStyleSheet(f"""
            QTabBar {{ background: transparent; }}
            QTabBar::tab {{
                background: rgba(255, 255, 255, 95);
                color: {MUTED_TEXT_COLOR};
                border-radius: 9px;
                padding: 3px 16px;
                margin: 2px 3px 1px 3px;
                border: 1px solid rgba(184, 143, 86, 60);
            }}
            QTabBar::tab:selected {{ background: {ACCENT_COLOR}; color: #FFFFFF; border-color: transparent; }}
            QTabBar::tab:hover:!selected {{ background: rgba(116, 28, 36, 40); }}
        """)
        for name in self.page_names:
            self.tab_bar.addTab(name)
        self.tab_bar.setCurrentIndex(self.current_page)
        self.tab_bar.currentChanged.connect(self.on_tab_changed)
        self.tab_bar.tabBarDoubleClicked.connect(self.rename_page)
        self.tab_bar.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tab_bar.customContextMenuRequested.connect(self.show_page_menu)
        # 拖拽排序：用 Qt 原生 movable（自带位移动画），位移后自己搬文件 + 重排页名
        self.tab_bar.setMovable(True)
        self.tab_bar.tabMoved.connect(self.on_tab_moved)
        self.tab_bar.installEventFilter(self)

        self.btn_add_page = ZoomButton("+")
        self.btn_add_page.setToolTip("New Page")
        self.btn_add_page.clicked.connect(self.add_page)

        bar.addWidget(self.tab_bar)
        bar.addWidget(self.btn_add_page)
        bar.addStretch()

        # --- 全局跨页搜索面板（默认隐藏，Ctrl+F 呼出） ---
        self.search_panel = QWidget()
        self.search_panel.setAttribute(Qt.WA_TranslucentBackground)
        sp = QVBoxLayout(self.search_panel)
        sp.setContentsMargins(12, 0, 12, 2)
        sp.setSpacing(2)

        row = QHBoxLayout()
        row.setSpacing(4)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search all pages...")
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(255, 255, 255, 130);
                border: 1px solid rgba(184, 143, 86, 90);
                border-radius: 9px;
                padding: 4px 10px;
                color: rgba(49, 44, 39, 235);
                font-family: '{TITLE_FONT}', 'Microsoft YaHei';
                font-size: 10pt;
                selection-background-color: {SELECTION_COLOR};
                selection-color: #FFFFFF;
            }}
            QLineEdit:focus {{ border-color: {ACCENT_COLOR}; }}
        """)
        self.search_input.textChanged.connect(self.run_search)
        self.btn_close_search = ZoomButton("x")
        self.btn_close_search.setToolTip("Close search (Esc)")
        self.btn_close_search.clicked.connect(self.hide_search)
        row.addWidget(self.search_input)
        row.addWidget(self.btn_close_search)

        self.search_results = QListWidget()
        self.search_results.setMaximumHeight(150)
        self.search_results.setStyleSheet(f"""
            QListWidget {{
                background: rgba(255, 255, 255, 120);
                border: 1px solid rgba(184, 143, 86, 70);
                border-radius: 9px;
                color: rgba(49, 44, 39, 230);
                font-family: '{CONTENT_FONT}', 'Microsoft YaHei';
                font-size: 9pt;
                padding: 2px;
            }}
            QListWidget::item {{ padding: 3px 6px; border-radius: 6px; }}
            QListWidget::item:selected {{ background: {ACCENT_COLOR}; color: #FFFFFF; }}
            QScrollBar:vertical {{ border: none; background: transparent; width: 6px; }}
            QScrollBar::handle:vertical {{ background: {SCROLLBAR_COLOR}; border-radius: 3px; }}
        """)
        self.search_results.itemClicked.connect(self.jump_to_result)
        self.search_results.hide()
        self.search_panel.hide()

        sp.addLayout(row)
        sp.addWidget(self.search_results)

        # --- 单栏全宽编辑区 ---
        self.pane = NotePane(is_left=True)
        self.pane.main_win = self
        self.pane.text_changed.connect(self.schedule_save)
        # 监听正文的按键/点击：离开页签上下文后 Del 要还给正文
        self.pane.editor.installEventFilter(self)

        self.bg_layout.addWidget(self.sheet_bar)
        self.bg_layout.addWidget(self.search_panel)
        self.bg_layout.addWidget(self.pane)
        self.main_layout.addWidget(self.bg_widget)

        # Ctrl+Tab / Ctrl+Shift+Tab 快速换页；Ctrl+F 搜索；Esc 关闭搜索
        sc_next = QShortcut(QKeySequence("Ctrl+Tab"), self)
        sc_next.setContext(Qt.ApplicationShortcut)
        sc_next.activated.connect(self.next_page)
        sc_prev = QShortcut(QKeySequence("Ctrl+Shift+Tab"), self)
        sc_prev.setContext(Qt.ApplicationShortcut)
        sc_prev.activated.connect(self.prev_page)
        sc_find = QShortcut(QKeySequence("Ctrl+F"), self)
        sc_find.setContext(Qt.ApplicationShortcut)
        sc_find.activated.connect(self.toggle_search)
        sc_esc = QShortcut(QKeySequence("Esc"), self)
        sc_esc.setContext(Qt.WidgetWithChildrenShortcut)
        sc_esc.activated.connect(self.on_esc_pressed)

        # 页签快捷键：F2 改名、Del 删除。
        # Del 会和正文删字符冲突，所以默认按"页签上下文"切换，见 _arm/_disarm_tab_keys。
        sc_rename = QShortcut(QKeySequence(Qt.Key_F2), self)
        sc_rename.setContext(Qt.ApplicationShortcut)
        sc_rename.activated.connect(self.rename_current_page)
        self.sc_delete_page = QShortcut(QKeySequence(Qt.Key_Delete), self)
        self.sc_delete_page.setContext(Qt.ApplicationShortcut)
        self.sc_delete_page.activated.connect(self.delete_current_page)
        self.sc_delete_page.setEnabled(False)

    # --- 多页管理 ---
    def eventFilter(self, obj, event):
        """页签拖拽守卫：按下时挂起切页逻辑（Qt 可能在 tabMoved 之前先改下标），
        松开后如果没发生位移，就补跑一次普通点击换页"""
        if obj is self.tab_bar:
            et = event.type()
            if et == QEvent.MouseButtonPress:
                self._tab_drag_pending = True
                self._tab_drag_moved = False
                self._arm_tab_keys()      # 点页签 = 进入"页签上下文"，Del 可删页
                # 防呆：万一 release 事件被系统吞掉（拖到窗口外失焦等），
                # 10 秒后自动解除挂起，避免点击换页永久失效
                QTimer.singleShot(10000, self._release_tab_drag_guard)
            elif et == QEvent.MouseButtonRelease:
                self._tab_drag_pending = False
                if self._tab_drag_moved:
                    self._tab_drag_moved = False
                    # Qt 的 mouseReleaseEvent 会把选中项改成松手位置的页签，
                    # 等它处理完再把高亮纠正回"原来选中的那页"（现在换了位置）
                    QTimer.singleShot(0, self._sync_tab_index)
                else:
                    idx = self.tab_bar.currentIndex()
                    if idx != self.current_page:
                        self.on_tab_changed(idx)
            elif et == QEvent.MouseButtonDblClick:
                self._tab_drag_pending = False
        elif obj is getattr(self.pane, "editor", None):
            et = event.type()
            if et == QEvent.KeyPress and self._tab_armed and event.key() == Qt.Key_Delete:
                # QTextEdit 会把 Del 声明成自己的按键（ShortcutOverride），
                # 走 QShortcut 根本收不到，必须在事件过滤器里抢在正文前面截住
                self.delete_current_page()
                return True
            # 碰正文（打字/点击/滚轮缩放）就退出页签上下文，Del 恢复成删字符
            if et in (QEvent.KeyPress, QEvent.MouseButtonPress, QEvent.Wheel):
                self._disarm_tab_keys()
        return super().eventFilter(obj, event)

    def on_tab_changed(self, idx):
        """切页：先把当前页落盘（用的还是旧 current_page 路径），再加载新页"""
        if self._loading_pages or self._tab_drag_pending or idx == self.current_page:
            return
        self._loading_pages = True
        try:
            self.flush_notes()
            self.current_page = idx
            self.load_notes()
        finally:
            self._loading_pages = False
        self._arm_tab_keys()      # 切过页签就是"页签上下文"，Del 删页

    def _release_tab_drag_guard(self):
        self._tab_drag_pending = False
        self._tab_drag_moved = False

    def _sync_tab_index(self):
        """把页签高亮对齐到 current_page（拖拽松手后 Qt 会擅自改选中项）"""
        if self.tab_bar.currentIndex() == self.current_page:
            return
        self.tab_bar.blockSignals(True)
        try:
            self.tab_bar.setCurrentIndex(self.current_page)
        finally:
            self.tab_bar.blockSignals(False)

    def on_tab_moved(self, frm, to):
        """页签被拖到新位置：搬文件 + 重排页名，维持「下标 = 文件编号」这个前提"""
        self._tab_drag_moved = True
        n = len(self.page_names)
        if frm == to or self._loading_pages or not (0 <= frm < n and 0 <= to < n):
            return
        old_cur = self.current_page
        self.save_timer.stop()
        self._loading_pages = True
        try:
            self.flush_notes()      # 此刻文件还没搬，先按旧下标落盘，不会写错地方
            # 新顺序用旧下标表达：order[new_i] = old_i
            order = list(range(n))
            order.insert(to, order.pop(frm))
            self._move_page_files(order)
            self.page_names.insert(to, self.page_names.pop(frm))
            # 当前页跟着被拖的那页走
            if old_cur == frm:
                new_cur = to
            elif frm < old_cur <= to:
                new_cur = old_cur - 1
            elif to <= old_cur < frm:
                new_cur = old_cur + 1
            else:
                new_cur = old_cur
            self.current_page = max(0, min(new_cur, n - 1))
            self._page_text_cache.clear()   # 搜索缓存按 mtime，下标变了必须清
            self.tab_bar.blockSignals(True)
            try:
                self.tab_bar.setCurrentIndex(self.current_page)
            finally:
                self.tab_bar.blockSignals(False)
            self.load_notes()
        except Exception as e:
            log_error(f"on_tab_moved {frm}->{to}: {e}")
        finally:
            self._loading_pages = False
        self._arm_tab_keys()
        self.save_window_state()

    def _move_page_files(self, order):
        """按 order 重排页面文件；全部先挪到临时名再放回，避免 os.replace 互相覆盖"""
        n = len(order)
        tmps = [page_file_path(i) + ".reorder_tmp" for i in range(n)]
        for i in range(n):
            src = page_file_path(i)
            if os.path.exists(src):
                os.replace(src, tmps[i])
        for new_i, old_i in enumerate(order):
            if os.path.exists(tmps[old_i]):
                os.replace(tmps[old_i], page_file_path(new_i))

    def add_page(self):
        used = {n.lower() for n in self.page_names}
        i = 1
        while to_roman(i).lower() in used:
            i += 1
        self._loading_pages = True
        try:
            self.flush_notes()  # 当前页先落盘
            self.page_names.append(to_roman(i))
            self.tab_bar.addTab(to_roman(i))
            self.current_page = self.tab_bar.count() - 1
            self.tab_bar.setCurrentIndex(self.current_page)
            self.pane.set_content("")
            self.pane.editor.setFocus()
        finally:
            self._loading_pages = False
        self._arm_tab_keys()
        self.save_window_state()

    def rename_page(self, idx):
        name, ok = QInputDialog.getText(self, "Rename Page", "Page name:",
                                        text=self.page_names[idx])
        if ok and name.strip():
            self.page_names[idx] = name.strip()
            self.tab_bar.setTabText(idx, name.strip())
            self.save_window_state()

    # --- 页签快捷键（F2 改名 / Del 删除） ---
    def _arm_tab_keys(self):
        """进入"页签上下文"：Del 当删除页用。
        启动后、切页后、点页签后都算——页签选中的时候按 Del 就该删页，
        不能让用户去猜"我到底点没点过"（这是看不见的状态）。"""
        self._tab_armed = True
        if hasattr(self, "sc_delete_page"):
            self.sc_delete_page.setEnabled(True)

    def _disarm_tab_keys(self):
        """碰正文（打字/点击/滚轮）：Del 交还给正文删字符"""
        self._tab_armed = False
        if hasattr(self, "sc_delete_page"):
            self.sc_delete_page.setEnabled(False)

    def rename_current_page(self):
        if QApplication.activeModalWidget() is not None:
            return
        self._disarm_tab_keys()
        self.rename_page(self.current_page)

    def delete_current_page(self):
        """Del：删当前页（仍弹确认框，误删不可逆）"""
        if not self._tab_armed or QApplication.activeModalWidget() is not None:
            return
        self._disarm_tab_keys()
        self.delete_page(self.current_page)

    def show_page_menu(self, pos):
        idx = self.tab_bar.tabAt(pos)
        if idx < 0:
            return
        menu = QMenu()
        menu.addAction("Rename", lambda: self.rename_page(idx))
        menu.addAction("Copy Page Text", lambda: self.copy_page_text(idx))
        del_act = menu.addAction("Delete", lambda: self.delete_page(idx))
        if len(self.page_names) <= 1:
            del_act.setEnabled(False)  # 至少保留一页
        menu.exec_(self.tab_bar.mapToGlobal(pos))

    def delete_page(self, idx):
        """确认后真删：删除该页文件，后面的页文件整体前移一位，并清理该页图片"""
        if len(self.page_names) <= 1:
            return
        ret = QMessageBox.question(
            self, "Delete Page",
            f"Delete page '{self.page_names[idx]}' permanently?",
            QMessageBox.Yes | QMessageBox.No)
        if ret != QMessageBox.Yes:
            return
        # 防抖中的未落盘输入会写回已删文件，先停掉
        self.save_timer.stop()
        if idx != self.current_page:
            self.flush_notes()
        # 图片引用必须在搬文件之前解析：搬完 page_file_path(idx) 已经是下一页的文件了
        page_images = self._page_image_names(idx)
        try:
            p = page_file_path(idx)
            if os.path.exists(p):
                os.remove(p)
            # 文件名按下标命名：删中间页后必须把后面的文件整体前移，
            # 否则后续页签会读到已删/错位的文件（内容看起来整组跑偏）
            for i in range(idx, len(self.page_names) - 1):
                src, dst = page_file_path(i + 1), page_file_path(i)
                if os.path.exists(src):
                    os.replace(src, dst)
            self._delete_image_files(page_images)
            self._page_text_cache.clear()
        except Exception as e:
            log_error(f"delete_page {idx + 1}: {e}")
        self._loading_pages = True
        try:
            self.tab_bar.removeTab(idx)
            del self.page_names[idx]
            self.current_page = min(idx, len(self.page_names) - 1)
            self.tab_bar.setCurrentIndex(self.current_page)
            self.load_notes()
        finally:
            self._loading_pages = False
        self._arm_tab_keys()
        self.save_window_state()

    def _page_image_names(self, idx):
        """解析某页 HTML 里引用的图片文件名（images/xxx）。
        不依赖 p{页码}_ 前缀 —— 页签拖拽排序后前缀会失准，靠前缀删会误删别人的图"""
        names = set()
        p = page_file_path(idx)
        if not os.path.isfile(p):
            return names
        try:
            with open(p, 'r', encoding='utf-8', errors='ignore') as fh:
                html = fh.read()
            names = set(re.findall(r'images/([^"\'\s<>/]+)', html))
        except Exception as e:
            log_error(f"page images p{idx + 1}: {e}")
        return names

    def _delete_image_files(self, names):
        """按文件名删 images/ 下的图片（只删确实存在的）"""
        img_dir = os.path.join(BASE_DIR, "images")
        if not names or not os.path.isdir(img_dir):
            return
        for name in names:
            fp = os.path.join(img_dir, name)
            try:
                if os.path.isfile(fp):
                    os.remove(fp)
            except Exception as e:
                log_error(f"remove image {name}: {e}")

    def next_page(self):
        count = self.tab_bar.count()
        if count > 1:
            self.tab_bar.setCurrentIndex((self.current_page + 1) % count)

    def prev_page(self):
        count = self.tab_bar.count()
        if count > 1:
            self.tab_bar.setCurrentIndex((self.current_page - 1) % count)

    def migrate_legacy_notes(self):
        """一次性迁移：旧版左栏 → 第 I 页，右栏 → 第 II 页。旧文件保留不动，可随时回退"""
        if os.path.exists(page_file_path(0)):
            return  # 新版文件已存在，跳过
        pages = []
        for f in (SAVE_FILE_LEFT, SAVE_FILE_RIGHT):
            if os.path.exists(f):
                try:
                    with open(f, 'r', encoding='utf-8') as fh:
                        c = fh.read()
                    if c.strip():
                        pages.append(c)
                except Exception as e:
                    log_error(f"migrate read {os.path.basename(f)}: {e}")
        if not pages:
            return
        for i, content in enumerate(pages):
            atomic_write_text(page_file_path(i), content)
        # 页数多于已登记页名时补齐罗马数字名
        if len(pages) > len(self.page_names):
            self.page_names = [to_roman(i + 1) for i in range(len(pages))]
        self.current_page = min(self.current_page, len(self.page_names) - 1)

    def handle_zoom(self, delta):
        self.pane.change_font_size(delta)

    # --- 全局跨页搜索 (Ctrl+F) ---
    def on_esc_pressed(self):
        if self.search_panel.isVisible():
            self.hide_search()

    def toggle_search(self):
        if self.search_panel.isVisible():
            self.hide_search()
        else:
            self.show_search()

    def show_search(self):
        self.search_panel.show()
        self.search_results.show()
        self.search_input.setFocus()
        self.search_input.selectAll()
        self.run_search(self.search_input.text())

    def hide_search(self):
        self.search_panel.hide()
        self.search_results.hide()
        self.search_results.clear()
        self.pane.editor.setFocus()

    def page_plain_text(self, idx):
        """取某页纯文本：当前页直接读编辑器，其余页读文件后去 HTML（带 mtime 缓存）"""
        if idx == self.current_page:
            return self.pane.editor.toPlainText()
        path = page_file_path(idx)
        if not os.path.exists(path):
            return ""
        try:
            mtime = os.path.getmtime(path)
        except Exception:
            mtime = 0
        cached = self._page_text_cache.get(idx)
        if cached and cached[0] == mtime:
            return cached[1]
        try:
            with open(path, 'r', encoding='utf-8') as f:
                raw = f.read()
        except Exception as e:
            log_error(f"page_plain_text {idx + 1}: {e}")
            return ""
        if raw.startswith(MD_FORMAT_HEADER):
            doc = QTextDocument()
            doc.setHtml(raw[len(MD_FORMAT_HEADER):])
            text = doc.toPlainText()
        else:
            text = raw
        self._page_text_cache[idx] = (mtime, text)
        return text

    def search_pages(self, query):
        """跨页搜索，返回 [(页序号, 命中行文本), ...]"""
        q = query.strip().lower()
        if not q:
            return []
        hits = []
        for idx in range(len(self.page_names)):
            for line in self.page_plain_text(idx).splitlines():
                if q in line.lower():
                    hits.append((idx, line.strip()))
                    if len(hits) >= 200:
                        return hits
        return hits

    def run_search(self, query):
        self.search_results.clear()
        q = (query or "").strip()
        if not q:
            return
        hits = self.search_pages(q)
        if not hits:
            item = QListWidgetItem("No matches")
            item.setFlags(Qt.NoItemFlags)
            self.search_results.addItem(item)
            return
        for idx, line in hits:
            snippet = line if len(line) <= 90 else line[:90] + "..."
            item = QListWidgetItem(f"{self.page_names[idx]}  ·  {snippet}")
            item.setData(Qt.UserRole, (idx, q))
            self.search_results.addItem(item)

    def jump_to_result(self, item):
        data = item.data(Qt.UserRole)
        if not data:
            return
        idx, query = data
        if idx != self.current_page:
            self.tab_bar.setCurrentIndex(idx)  # 触发切页落盘+加载
        editor = self.pane.editor
        cursor = editor.document().find(query, 0, QTextDocument.FindFlags())  # 默认即不区分大小写
        if not cursor.isNull():
            editor.setTextCursor(cursor)
            editor.ensureCursorVisible()
        editor.setFocus()

    def copy_page_text(self, idx):
        """整页复制为纯文本到剪贴板"""
        QApplication.clipboard().setText(self.page_plain_text(idx))

    # --- 拖文件导入 / 图片插入 ---
    IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")

    def handle_dropped_file(self, path):
        ext = os.path.splitext(path)[1].lower()
        try:
            if ext in (".md", ".markdown", ".txt"):
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                name = os.path.splitext(os.path.basename(path))[0] or to_roman(len(self.page_names) + 1)
                self.import_as_new_page(name, content)
            elif ext in self.IMAGE_EXTS:
                self.insert_image(path)
            else:
                log_error(f"drop unsupported file: {path}")
        except Exception as e:
            log_error(f"handle_dropped_file {path}: {e}")

    def import_as_new_page(self, name, content):
        """把一段文本作为新页导入（拖 .md 进来用），重名自动加序号"""
        base = name or to_roman(len(self.page_names) + 1)
        name = base
        n = 2
        while name in self.page_names:
            name = f"{base} ({n})"
            n += 1
        self._loading_pages = True
        try:
            self.flush_notes()  # 当前页先落盘
            self.page_names.append(name)
            self.tab_bar.addTab(name)
            self.current_page = self.tab_bar.count() - 1
            self.tab_bar.setCurrentIndex(self.current_page)
            self.pane.set_content(content)
            self.flush_notes()  # 导入内容立即落盘
            self._page_text_cache.clear()
        finally:
            self._loading_pages = False
        self.save_window_state()

    def insert_image(self, path):
        """复制图片到程序目录 images/，插入正文（相对路径，随文件夹一起搬）"""
        ext = os.path.splitext(path)[1].lower()
        img_dir = os.path.join(BASE_DIR, "images")
        os.makedirs(img_dir, exist_ok=True)
        fname = f"p{self.current_page + 1}_{datetime.now():%Y%m%d_%H%M%S_%f}{ext}"
        shutil.copy2(path, os.path.join(img_dir, fname))
        cursor = self.pane.editor.textCursor()
        cursor.insertHtml(f'<img src="images/{fname}" width="340" /><br>')
        self.pane.editor.setTextCursor(cursor)

    # --- 窗口透明度 ---
    def apply_bg_alpha(self, alpha):
        """调整毛玻璃底板的不透明度（只影响底色，不影响文字清晰度）"""
        self.bg_alpha = int(alpha)
        self.bg_widget.setStyleSheet(f"""
            QFrame#BgFrame {{
                background-color: rgba(255, 255, 255, {self.bg_alpha});
                border-radius: 10px;
                border: 1px solid {BORDER_COLOR};
            }}
        """)
        self.settings.setValue("bg_alpha", self.bg_alpha)

    def toggle_always_on_top(self, checked):
        self.setWindowFlag(Qt.WindowStaysOnTopHint, checked)
        self.show(); self.enable_blur()
        # 改窗口 flag 会让 Qt 重建原生窗口句柄，热键绑定在旧 hwnd 上就失效了，重挂一次
        self.register_global_hotkey()

    def nativeEvent(self, eventType, message):
        from ctypes.wintypes import MSG
        if eventType in ["windows_generic_MSG", "windows_dispatcher_MSG"]:
            msg = MSG.from_address(message.__int__())
            if msg.message == WM_HOTKEY and int(msg.wParam) == HOTKEY_ID:
                # 关键：不能在消息派发过程中直接 hide()/move()/重设毛玻璃，
                # 那会在 Qt 处理窗口消息时重入并改窗口状态，可能直接崩在 Qt5Gui。
                # 只排一个事件，等这条消息派发完再动手。
                if not self._toggle_pending:
                    self._toggle_pending = True
                    QTimer.singleShot(0, self._run_toggle)
                return True, 0
            if msg.message == WM_NCHITTEST:
                x = (msg.lParam & 0xffff); y = (msg.lParam >> 16) & 0xffff
                if x > 32767: x -= 65536
                if y > 32767: y -= 65536
                p = self.mapFromGlobal(QPoint(x, y))
                bx, by = p.x(), p.y()
                w, h = self.width(), self.height()
                if bx < BORDER_WIDTH and by < BORDER_WIDTH: return True, HTTOPLEFT
                if bx > w - BORDER_WIDTH and by < BORDER_WIDTH: return True, HTTOPRIGHT
                if bx < BORDER_WIDTH and by > h - BORDER_WIDTH: return True, HTBOTTOMLEFT
                if bx > w - BORDER_WIDTH and by > h - BORDER_WIDTH: return True, HTBOTTOMRIGHT
                if bx < BORDER_WIDTH: return True, HTLEFT
                if bx > w - BORDER_WIDTH: return True, HTRIGHT
                if by < BORDER_WIDTH: return True, HTTOP
                if by > h - BORDER_WIDTH: return True, HTBOTTOM
        return super().nativeEvent(eventType, message)

    def load_window_state(self):
        pos = self.settings.value("pos")
        size = self.settings.value("size")
        if size: self.resize(size)
        if pos:
            # 防止窗口跑到屏幕外面
            screen = QApplication.desktop().availableGeometry()
            px, py = pos.x(), pos.y()
            w, h = self.width(), self.height()
            if px + w < 50 or px > screen.width() - 50 or py + h < 50 or py > screen.height() - 50:
                self.center_window()
            else:
                self.move(pos)
        else: self.center_window()
        font_size = self.settings.value("font_size", DEFAULT_FONT_SIZE, type=int)
        self.pane.current_font_size = font_size
        self.pane.update_styles()
        # 底板透明度
        self.apply_bg_alpha(self.settings.value("bg_alpha", 88, type=int))

    def save_window_state(self):
        self.settings.setValue("pos", self.pos())
        self.settings.setValue("size", self.size())
        self.settings.setValue("font_size", self.pane.current_font_size)
        self.settings.setValue("page_names", self.page_names)
        self.settings.setValue("current_page", self.current_page)
        self.settings.sync()  # 立即刷盘，防止强杀进程丢设置

    def center_window(self):
        qr = self.frameGeometry()
        cp = QDesktopWidget().availableGeometry().center()
        qr.moveCenter(cp); self.move(qr.topLeft())

    def stop_dock_animation(self):
        if self.dock_animation and self.dock_animation.state() == QPropertyAnimation.Running:
            self.dock_animation.stop()
        self.dock_animation = None
        self.dock_animation_target = None

    def animate_dock_to(self, target_pos):
        if self.pos() == target_pos:
            return
        if self.dock_animation_target == target_pos and self.dock_animation and self.dock_animation.state() == QPropertyAnimation.Running:
            return

        self.stop_dock_animation()
        self.dock_animation_target = target_pos
        self.dock_animation = QPropertyAnimation(self, b"pos", self)
        self.dock_animation.setDuration(180)
        self.dock_animation.setStartValue(self.pos())
        self.dock_animation.setEndValue(target_pos)
        self.dock_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.dock_animation.finished.connect(lambda: setattr(self, "dock_animation_target", None))
        self.dock_animation.start()

    # --- 四边吸附逻辑 ---
    def visible_ratio(self):
        """窗口落在屏幕内的面积占比。贴边藏起来时只剩一条缝，占比接近 0"""
        screen = QApplication.desktop().availableGeometry(self)
        g = self.geometry()
        area = g.width() * g.height()
        if area <= 0:
            return 0.0
        inter = screen.intersected(g)
        return (inter.width() * inter.height()) / float(area)

    def docked_edge(self):
        """窗口藏在哪条边：返回 'left'/'right'/'top'/'bottom'，完整可见时返回 None"""
        screen = QApplication.desktop().availableGeometry(self)
        g = self.geometry()
        overflow = {
            'left': screen.left() - g.left(),
            'right': g.right() - screen.right(),
            'top': screen.top() - g.top(),
            'bottom': g.bottom() - screen.bottom(),
        }
        edge = max(overflow, key=overflow.get)
        return edge if overflow[edge] > 4 else None

    def reveal_window(self):
        """把贴边藏起来的窗口沿着那条边滑回完整可见，并抢到前台"""
        edge = self.docked_edge()
        if edge:
            screen = QApplication.desktop().availableGeometry(self)
            g = self.geometry()
            w, h = g.width(), g.height()
            target = {
                'left': QPoint(screen.left(), g.y()),
                'right': QPoint(screen.right() - w + 1, g.y()),
                'top': QPoint(g.x(), screen.top()),
                'bottom': QPoint(g.x(), screen.bottom() - h + 1),
            }.get(edge)
            if target is not None:
                self.stop_dock_animation()
                self.move(target)          # 直接到位，热键唤出要立刻看见，不做动画
        self.raise_(); self.activateWindow()
        # 这里不再重复调 enable_blur：只有在重新 show 时才需要（showEvent 已经处理），
        # 反复对同一个 hwnd 调 SetWindowCompositionAttribute 没必要且有风险
        self.dock_armed = False            # 已经完整可见，鼠标没进来之前别再缩回去

    def check_docking(self):
        if not self.isVisible() or self.isMinimized() or self.ignore_docking:
            return

        if QApplication.mouseButtons() == Qt.LeftButton:
            return

        desktop = QApplication.desktop()
        screen_rect = desktop.availableGeometry(self)

        s_left = screen_rect.left()
        s_top = screen_rect.top()
        s_right = screen_rect.right()
        s_bottom = screen_rect.bottom()

        w_rect = self.geometry()
        w_x, w_y = w_rect.x(), w_rect.y()
        w_w, w_h = w_rect.width(), w_rect.height()

        SNAP_MARGIN = 20
        HIDE_PROTRUSION = 2

        cursor_pos = QCursor.pos()
        is_hovered = w_rect.contains(cursor_pos)

        # 吸附只在"窗口拖到边上→鼠标移开"时发生一次：
        # 鼠标进过窗口才布防，吸完就解除，避免叫出来的窗口被反复推回屏外
        if is_hovered:
            self.dock_armed = True
        elif not self.dock_armed:
            return

        # --- A. 上边缘 ---
        if w_y < s_top + SNAP_MARGIN:
            if is_hovered:
                target_y = s_top
            else:
                target_y = s_top - w_h + HIDE_PROTRUSION
                self.dock_armed = False

            if w_y != target_y:
                self.animate_dock_to(QPoint(w_x, target_y))

        # --- B. 左边缘 ---
        elif w_x < s_left + SNAP_MARGIN:
            if is_hovered:
                target_x = s_left
            else:
                target_x = s_left - w_w + HIDE_PROTRUSION
                self.dock_armed = False

            if w_x != target_x:
                self.animate_dock_to(QPoint(target_x, w_y))

        # --- C. 右边缘 (直接用 s_right，避免多显示器坐标偏移) ---
        elif w_x + w_w > s_right - SNAP_MARGIN:
            target_x = s_right - w_w if is_hovered else s_right - HIDE_PROTRUSION
            if not is_hovered:
                self.dock_armed = False
            if w_x != target_x:
                self.animate_dock_to(QPoint(target_x, w_y))

        # --- D. 下边缘 (直接用 s_bottom，避免多显示器坐标偏移) ---
        elif w_y + w_h > s_bottom - SNAP_MARGIN:
            target_y = s_bottom - w_h if is_hovered else s_bottom - HIDE_PROTRUSION
            if not is_hovered:
                self.dock_armed = False
            if w_y != target_y:
                self.animate_dock_to(QPoint(w_x, target_y))

    def init_tray(self):
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(self.app_icon)
        menu = QMenu()
        auto_act = QAction("Auto Start", menu, checkable=True)
        auto_act.setChecked(self.settings.value("auto_start", True, type=bool))
        auto_act.toggled.connect(self.toggle_auto_start)
        menu.addAction(auto_act)
        menu.addSeparator()

        # 全局热键：点一下可以重录组合键
        self.hotkey_action = QAction("Global Hotkey", menu)
        self.hotkey_action.triggered.connect(self.ask_hotkey)
        menu.addAction(self.hotkey_action)
        self.refresh_hotkey_action()
        menu.addSeparator()

        # 透明度滑块（只调底板底色，文字始终清晰）
        opacity_holder = QWidget()
        oh = QHBoxLayout(opacity_holder)
        oh.setContentsMargins(12, 4, 12, 4)
        oh.setSpacing(8)
        lab = QLabel("Opacity")
        lab.setStyleSheet("color: rgba(60, 55, 50, 220); font-size: 11px;")
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(30, 215)
        self.opacity_slider.setValue(self.settings.value("bg_alpha", 88, type=int))
        self.opacity_slider.setFixedWidth(130)
        self.opacity_slider.valueChanged.connect(self.apply_bg_alpha)
        oh.addWidget(lab)
        oh.addWidget(self.opacity_slider)
        opacity_action = QWidgetAction(menu)
        opacity_action.setDefaultWidget(opacity_holder)
        menu.addAction(opacity_action)

        menu.addSeparator()
        menu.addAction("Show", self.show_normal)
        menu.addAction("Quit", self.close_application)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda r: self.show_normal() if r == QSystemTrayIcon.Trigger else None)
        self.tray.show()

    def minimize_window(self): self.hide()

    # --- 全局热键（Ctrl+G 唤起 / 收起） ---
    def register_global_hotkey(self):
        """把热键注册到本窗口的 hwnd；被别的程序占用时自动退到 Ctrl+Alt+G"""
        spec = self.hotkey_spec or DEFAULT_HOTKEY
        self.unregister_global_hotkey()
        self.hotkey_ok = False
        user32 = windll.user32
        user32.RegisterHotKey.argtypes = [wintypes.HWND, c_int, wintypes.UINT, wintypes.UINT]
        user32.RegisterHotKey.restype = wintypes.BOOL
        hwnd = int(self.winId())      # 强制创建原生窗口句柄
        tried = []
        for cand in (spec, FALLBACK_HOTKEY):
            if cand in tried:
                continue
            tried.append(cand)
            parsed = parse_hotkey(cand)
            if not parsed:
                log_error(f"hotkey parse fail: {cand!r}")
                continue
            mods, vk = parsed
            if user32.RegisterHotKey(hwnd, HOTKEY_ID, mods, vk):
                self.hotkey_ok = True
                if cand != spec:
                    log_error(f"hotkey {spec} taken, fallback to {cand}")
                    self.hotkey_spec = cand
                    self.settings.setValue("hotkey", cand)
                    self.settings.sync()
                break
            log_error(f"RegisterHotKey failed: {cand} (err={windll.kernel32.GetLastError()})")
        self.refresh_hotkey_action()
        return self.hotkey_ok

    def unregister_global_hotkey(self):
        try:
            user32 = windll.user32
            user32.UnregisterHotKey.argtypes = [wintypes.HWND, c_int]
            user32.UnregisterHotKey(int(self.winId()), HOTKEY_ID)
        except Exception:
            pass

    def _run_toggle(self):
        """热键排到这里才真正执行，此时已脱离 Windows 消息派发过程"""
        self._toggle_pending = False
        self.toggle_window()

    def toggle_window(self):
        """全局热键的语义：叫出来 / 收起来，而不是简单开关
        - 在托盘里        → 弹回来并展开
        - 贴边只剩一条缝  → 滑出来完整显示（不收起！）
        - 开着但不在前台  → 只叫到前面，不收掉
        - 开着且就在眼前  → 收进托盘
        """
        try:
            if not self.isVisible():
                self.show_normal()
                self.pane.editor.setFocus()
                return
            if self.visible_ratio() < 0.5:
                self.reveal_window()
                self.pane.editor.setFocus()
                return
            if not self.isActiveWindow():
                self.raise_(); self.activateWindow()
                self.dock_armed = False
                self.pane.editor.setFocus()
                return
            self.flush_notes()
            self.hide()
        except Exception as e:
            log_error(f"toggle_window: {e}")

    def refresh_hotkey_action(self):
        if not hasattr(self, "hotkey_action"):
            return
        if self.hotkey_ok:
            self.hotkey_action.setText(f"Global Hotkey: {self.hotkey_spec}")
        else:
            self.hotkey_action.setText("Global Hotkey: unavailable")

    def ask_hotkey(self):
        """托盘菜单点开：录制一个新组合键并立即生效"""
        dlg = HotkeyDialog(self.hotkey_spec, self)
        if dlg.exec_() != QDialog.Accepted:
            return
        self.settings.setValue("hotkey", dlg.result_spec)
        self.settings.sync()
        self.hotkey_spec = dlg.result_spec
        ok = self.register_global_hotkey()
        if ok and self.hotkey_spec != dlg.result_spec:
            QMessageBox.information(
                self, "Global Hotkey",
                f"{dlg.result_spec} is already used by another app.\n"
                f"Falling back to {self.hotkey_spec}.")
        elif not ok:
            QMessageBox.warning(
                self, "Global Hotkey",
                "Could not register any hotkey. See Gryffindor_error.log.")

    def show_normal(self):
        self.showNormal()
        # 从托盘恢复时，如果它在边缘只剩一条缝，直接滑出来完整显示
        if self.visible_ratio() < 0.5:
            self.reveal_window()
        self.raise_(); self.activateWindow(); self.enable_blur()
        self.dock_armed = False        # 刚叫出来的窗口别立刻自己缩回去
        self.ignore_docking = True
        QTimer.singleShot(1500, lambda: setattr(self, 'ignore_docking', False))

    def schedule_save(self):
        """输入防抖：500ms 内没有新输入才真正落盘"""
        self.save_timer.start(500)

    def flush_notes(self):
        """立即落盘（防抖定时器触发或退出/切页时调用），保证不丢最后 500ms 的输入"""
        self.save_timer.stop()
        self.save_current_page()

    def save_current_page(self):
        """保存当前页：带格式标记的 HTML（原子写入，避免半截文件）"""
        atomic_write_text(page_file_path(self.current_page),
                          MD_FORMAT_HEADER + self.pane.get_html_content())

    def load_notes(self):
        path = page_file_path(self.current_page)
        try:
            if not os.path.exists(path):
                self.pane.set_content("")
                return
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            try:
                self.pane.set_content(content)
            except Exception as e:
                # 内容解析失败：先备份原文件，再显示空页，避免后续保存把原文覆盖掉
                backup = path + f".corrupt_{datetime.now():%Y%m%d_%H%M%S}"
                try:
                    shutil.copy2(path, backup)
                except Exception:
                    pass
                log_error(f"load corrupt p{self.current_page + 1}: {e} (backup: {backup})")
                self.pane.set_content("")
        except Exception as e:
            log_error(f"load_notes p{self.current_page + 1}: {e}")

    def closeEvent(self, event):
        """Alt+F4 或系统关闭时保存数据再退出"""
        self.save_window_state()
        self.flush_notes()
        event.accept()

    def close_application(self):
        self.save_window_state(); self.flush_notes(); QApplication.quit()

    def set_auto_start(self):
        """按 QSettings 里的 auto_start 开关注册/注销开机自启（仅 exe 模式生效）"""
        if not getattr(sys, 'frozen', False):
            return  # skip when running as .py script
        enabled = self.settings.value("auto_start", True, type=bool)
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE
            )
            if enabled:
                winreg.SetValueEx(key, APP_TITLE, 0, winreg.REG_SZ, f'"{sys.executable}"')
            else:
                try:
                    winreg.DeleteValue(key, APP_TITLE)
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception as e:
            log_error(f"set_auto_start: {e}")

    def toggle_auto_start(self, checked):
        """托盘菜单开关：保存设置并立即生效"""
        self.settings.setValue("auto_start", checked)
        self.set_auto_start()

def install_excepthook():
    """打包后 console=False，未捕获异常默认无声消失；这里统一写进 error.log 便于排查"""
    def hook(exc_type, exc_value, exc_tb):
        try:
            log_error("UNCAUGHT:\n" + "".join(
                traceback.format_exception(exc_type, exc_value, exc_tb)))
        except Exception:
            pass
        sys.__excepthook__(exc_type, exc_value, exc_tb)
    sys.excepthook = hook


def install_fatal_handler():
    """原生崩溃（访问越界等）Python 的 excepthook 抓不到，
    faulthandler 能抓，并把当时的 Python 调用栈写进日志。
    日志写到系统目录（%LOCALAPPDATA%\\Gryffindor\\fatal.log），不往程序目录里丢文件。"""
    import faulthandler
    try:
        fh = open(os.path.join(log_dir(), "fatal.log"), "a", encoding="utf-8", buffering=1)
        fh.write(f"\n===== session {datetime.now():%Y-%m-%d %H:%M:%S} =====\n")
        faulthandler.enable(file=fh, all_threads=True)
    except Exception as e:
        log_error(f"faulthandler: {e}")


if __name__ == "__main__":
    install_excepthook()
    install_fatal_handler()
    app = QApplication(sys.argv)
    window = GryffindorNote()
    if window._duplicate_exit:
        # 已有实例在跑：它已被召唤到前台，本进程安静退出
        sys.exit(0)
    window.show()
    sys.exit(app.exec_())










