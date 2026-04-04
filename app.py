#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
desktop_hud/app.py
Zorin OS 用 軽量デスクトップ監視HUD
CPU使用率・メモリ使用率・CPU温度・ストレージ使用率を
常に最前面に「文字だけ浮いている」HUD風で表示する。

依存ライブラリ:
    pip install PySide6 psutil
"""

import sys
import os
import psutil

from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout,
    QMenu, QDialog, QCheckBox, QPushButton,
    QHBoxLayout, QFrame, QSpinBox,
)
from PySide6.QtCore import Qt, QTimer, QPoint
from PySide6.QtGui import QFont, QFontDatabase

# ─── 定数 ────────────────────────────────────────────────────────────────────

# メトリクス更新間隔（ミリ秒）
UPDATE_INTERVAL_MS = 2000

# HUD の文字色（明るいシアン系グリーン）
HUD_COLOR_NORMAL  = "#00FF9C"   # 通常値
HUD_COLOR_WARNING = "#FFD700"   # 警告（70%以上）
HUD_COLOR_DANGER  = "#FF4444"   # 危険（90%以上）

# HUD 背景色（RGBA）
HUD_BG_COLOR = "rgba(0, 0, 0, 170)"

# HUD フォントサイズ初期値（pt）
FONT_SIZE_DEFAULT = 9
FONT_SIZE_MIN     = 8
FONT_SIZE_MAX     = 24

# CPU温度センサー優先キー（カーネルドライバー名順）
TEMP_SENSOR_KEYS = (
    "coretemp",     # Intel
    "k10temp",      # AMD Ryzen / K10
    "cpu_thermal",  # ARM系
    "cpu-thermal",  # ARM系（別名）
    "acpitz",       # ACPI 汎用
    "zenpower",     # AMD Zen (zenpower ドライバー)
)

# 外部ストレージとして検出しないファイルシステム種別
EXCLUDED_FSTYPES = frozenset({
    "tmpfs", "squashfs", "devtmpfs", "devfs",
    "proc", "sysfs", "cgroup", "cgroup2",
    "pstore", "efivarfs", "bpf", "tracefs",
    "securityfs", "fusectl", "hugetlbfs",
    "mqueue", "debugfs", "overlay", "ramfs",
    "autofs", "rpc_pipefs", "configfs", "nsfs",
    "iso9660",   # CD-ROM（光学メディアは除外したい場合）
})

# 外部ストレージとみなすマウントポイントのプレフィックス
EXTERNAL_PREFIXES = ("/media/", "/mnt/", "/run/media/")


# ─── ユーティリティ ───────────────────────────────────────────────────────────

def get_cpu_temperature() -> float | None:
    """
    CPU温度を取得する。
    psutil.sensors_temperatures() を優先順で走査し、
    取得できなければ None を返す（例外はすべて握り潰す）。
    """
    try:
        all_temps = psutil.sensors_temperatures()
        if not all_temps:
            return None

        # 優先キーで探す
        for key in TEMP_SENSOR_KEYS:
            if key in all_temps:
                entries = all_temps[key]
                if entries:
                    return entries[0].current

        # どのキーにも一致しなければ最初のセンサーの最初の値を使う
        for entries in all_temps.values():
            if entries:
                return entries[0].current

    except (AttributeError, OSError, Exception):
        pass

    return None


def bytes_to_gb(b: int) -> int:
    """バイト数を整数 GB に変換する（最小 1GB）"""
    return max(1, round(b / 1024 ** 3))


def get_external_mounts() -> list[str]:
    """
    現在マウント中の外部ストレージのマウントポイント一覧を返す。
    /media/*, /mnt/*, /run/media/* を優先的に対象にし、
    仮想・一時ファイルシステムはすべて除外する。
    """
    mounts: list[str] = []
    try:
        for part in psutil.disk_partitions(all=False):
            # 仮想FSは除外
            if part.fstype in EXCLUDED_FSTYPES:
                continue
            # ルートパーティションは除外（DISK ラベルで別表示）
            if part.mountpoint == "/":
                continue
            # 外部プレフィックスに一致するものだけ追加
            for prefix in EXTERNAL_PREFIXES:
                if part.mountpoint.startswith(prefix):
                    mounts.append(part.mountpoint)
                    break
    except Exception:
        pass
    return mounts


def pct_color(value: float) -> str:
    """使用率の数値に応じたHUD文字色を返す"""
    if value >= 90:
        return HUD_COLOR_DANGER
    if value >= 70:
        return HUD_COLOR_WARNING
    return HUD_COLOR_NORMAL


def short_name(mountpoint: str, max_len: int = 8) -> str:
    """
    マウントポイントのパスから表示用の短い名前を作る。
    例: /media/user/MyUSBDrive → MyUSBDri
    """
    name = os.path.basename(mountpoint.rstrip("/")) or mountpoint
    return name[:max_len]


# ─── 設定ウィンドウ ───────────────────────────────────────────────────────────

class SettingsWindow(QDialog):
    """
    表示項目 ON/OFF と文字サイズを管理する設定ダイアログ。
    各コントロール変更時に即座に HUD へ反映する。
    """

    def __init__(self, settings: dict, parent: "HUDWindow" = None):
        super().__init__(parent)
        self.settings = settings           # HUDWindow と共有する辞書
        self.setWindowTitle("HUD 設定")
        self.setWindowFlags(
            Qt.Dialog |
            Qt.WindowStaysOnTopHint |
            Qt.WindowCloseButtonHint
        )
        self.setFixedSize(240, 310)
        self.setStyleSheet("""
            QDialog {
                background-color: #1a1a1a;
                color: #cccccc;
            }
            QLabel {
                color: #aaaaaa;
                font-size: 11px;
            }
            QCheckBox {
                color: #dddddd;
                font-size: 12px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
            }
            QSpinBox {
                background-color: #2a2a2a;
                color: #eeeeee;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 2px 4px;
                font-size: 12px;
            }
            QPushButton {
                background-color: #333333;
                color: #eeeeee;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 4px 16px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #444444;
            }
        """)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(18, 16, 18, 16)

        # ── 表示項目セクション ──────────────────────────────────
        sec_items = QLabel("表示項目の ON / OFF")
        sec_items.setStyleSheet("color: #888888; font-size: 10px;")
        layout.addWidget(sec_items)

        line1 = QFrame()
        line1.setFrameShape(QFrame.HLine)
        line1.setStyleSheet("color: #333333;")
        layout.addWidget(line1)

        # チェックボックス（項目キーと表示名）
        cb_items = [
            ("cpu",  "CPU 使用率"),
            ("mem",  "メモリ使用率"),
            ("temp", "CPU 温度"),
            ("disk", "ストレージ使用率"),
            ("ext",  "外部ストレージ"),   # 新規追加
        ]
        self._checkboxes: dict[str, QCheckBox] = {}
        for key, label in cb_items:
            cb = QCheckBox(label)
            cb.setChecked(self.settings.get(key, True))
            cb.toggled.connect(lambda checked, k=key: self._on_toggle(k, checked))
            layout.addWidget(cb)
            self._checkboxes[key] = cb

        # ── 文字サイズセクション ────────────────────────────────
        layout.addSpacing(4)
        sec_font = QLabel("文字サイズ（pt）")
        sec_font.setStyleSheet("color: #888888; font-size: 10px;")
        layout.addWidget(sec_font)

        line2 = QFrame()
        line2.setFrameShape(QFrame.HLine)
        line2.setStyleSheet("color: #333333;")
        layout.addWidget(line2)

        # SpinBox 行
        font_row = QHBoxLayout()
        font_row.setSpacing(8)
        lbl_font = QLabel("サイズ:")
        lbl_font.setStyleSheet("color: #aaaaaa; font-size: 12px;")

        self.spin_font = QSpinBox()
        self.spin_font.setRange(FONT_SIZE_MIN, FONT_SIZE_MAX)
        self.spin_font.setValue(self.settings.get("font_size", FONT_SIZE_DEFAULT))
        self.spin_font.setSuffix(" pt")
        self.spin_font.setFixedWidth(80)
        self.spin_font.valueChanged.connect(self._on_font_size_change)

        font_row.addWidget(lbl_font)
        font_row.addWidget(self.spin_font)
        font_row.addStretch()
        layout.addLayout(font_row)

        layout.addStretch()

        # 閉じるボタン
        btn_close = QPushButton("閉じる")
        btn_close.clicked.connect(self.close)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def _on_toggle(self, key: str, value: bool):
        """チェック変更 → 設定更新 → HUD 即時反映"""
        self.settings[key] = value
        parent = self.parent()
        if parent is not None:
            parent.refresh_display()

    def _on_font_size_change(self, size: int):
        """文字サイズ変更 → 設定更新 → HUD 即時反映"""
        self.settings["font_size"] = size
        parent = self.parent()
        if parent is not None:
            parent.apply_font_size()


# ─── HUDウィンドウ ────────────────────────────────────────────────────────────

class HUDWindow(QWidget):
    """
    常に最前面・フレームなし・半透明背景の HUD ウィンドウ。
    左ドラッグで移動、右クリックでメニュー表示。
    """

    def __init__(self):
        super().__init__()

        # 表示項目の初期設定（全 ON）
        self.settings: dict = {
            "cpu":       True,
            "mem":       True,
            "temp":      True,
            "disk":      True,
            "ext":       True,          # 外部ストレージ
            "font_size": FONT_SIZE_DEFAULT,
        }

        self._settings_window: SettingsWindow | None = None
        self._drag_pos: QPoint | None = None   # ドラッグ開始のオフセット
        self._ext_labels: list[QLabel] = []    # 外部ストレージ用の動的ラベル群
        self.is_always_on_top: bool = True      # 最前面固定の現在状態

        self._setup_window()
        self._build_ui()
        self._start_timer()

        # 初回計測値を捨てて正確な値が出るようにする
        psutil.cpu_percent(interval=None)
        # 初回描画
        self.refresh_display()

    # ── ウィンドウ初期化 ──────────────────────────────────────────────────────

    def _setup_window(self):
        """ウィンドウフラグ・透明化・初期位置を設定する"""
        self.setWindowFlags(
            Qt.FramelessWindowHint      |   # タイトルバーなし
            Qt.WindowStaysOnTopHint     |   # 常に最前面
            Qt.Tool                         # タスクバーに表示しない
        )
        # 背景を完全透明にする（QSS の rgba() が機能するために必要）
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)

        # ウィンドウ自体に背景色を付けない（透明のまま）
        self.setStyleSheet("background: transparent;")

        # 初期位置：右上付近
        screen_rect = QApplication.primaryScreen().geometry()
        self.move(screen_rect.width() - 210, 40)

    # ── UI 構築 ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        """ラベルウィジェットを並べた縦レイアウトを構築する"""
        self._layout = QVBoxLayout(self)
        self._layout.setSpacing(3)
        self._layout.setContentsMargins(0, 0, 0, 0)

        # 現在のフォントを生成してインスタンス変数に保持
        self._font = self._build_font(self.settings["font_size"])

        # 固定メトリクスラベル（順序を保証するためタプルで管理）
        self.lbl_cpu  = self._make_label()
        self.lbl_mem  = self._make_label()
        self.lbl_temp = self._make_label()
        self.lbl_disk = self._make_label()

        for lbl in (self.lbl_cpu, self.lbl_mem, self.lbl_temp, self.lbl_disk):
            self._layout.addWidget(lbl)

        # 外部ストレージ用サブコンテナ
        # ボタン行より先に配置し、ext ラベルが常にボタンより上に来るようにする
        self._ext_container = QWidget()
        self._ext_container.setStyleSheet("background: transparent;")
        self._ext_inner = QVBoxLayout(self._ext_container)
        self._ext_inner.setSpacing(3)
        self._ext_inner.setContentsMargins(0, 0, 0, 0)
        self._layout.addWidget(self._ext_container)

        # レイヤー切替ボタン行（常に最下段）
        self._build_layer_buttons()

    def _build_font(self, size: int) -> QFont:
        """指定サイズの等幅フォントを返す"""
        preferred = ["DejaVu Sans Mono", "Monospace", "Liberation Mono", "Courier New"]
        available = QFontDatabase.families()
        for name in preferred:
            if name in available:
                f = QFont(name, size)
                f.setWeight(QFont.Light)
                return f
        # フォールバック
        f = QFont()
        f.setFixedPitch(True)
        f.setPointSize(size)
        return f

    def _build_layer_buttons(self):
        """「通常」「最前面」レイヤー切替ボタン行を構築する"""
        btn_widget = QWidget()
        btn_widget.setStyleSheet("background: transparent;")
        btn_layout = QHBoxLayout(btn_widget)
        btn_layout.setSpacing(2)
        btn_layout.setContentsMargins(0, 3, 0, 0)

        self._btn_normal = QPushButton("通常")
        self._btn_top    = QPushButton("最前面")

        for btn in (self._btn_normal, self._btn_top):
            btn.setFixedHeight(18)
            # ボタンのクリックがドラッグと混同しないよう明示的に矢印カーソル
            btn.setCursor(Qt.ArrowCursor)

        self._btn_normal.clicked.connect(lambda: self.set_always_on_top(False))
        self._btn_top.clicked.connect(lambda: self.set_always_on_top(True))

        btn_layout.addWidget(self._btn_normal)
        btn_layout.addWidget(self._btn_top)
        self._layout.addWidget(btn_widget)

        # 初期状態の外観を反映
        self._update_layer_buttons()

    def set_always_on_top(self, enabled: bool):
        """
        最前面固定を ON/OFF する。
        setWindowFlags() 変更後に show() を呼んで反映し、
        現在位置・透明化属性を再設定して見た目の乱れを防ぐ。
        """
        if self.is_always_on_top == enabled:
            return  # 状態変化なし

        self.is_always_on_top = enabled
        pos = self.pos()   # 位置を保存（setWindowFlags でリセットされる場合がある）

        flags = Qt.FramelessWindowHint | Qt.Tool
        if enabled:
            flags |= Qt.WindowStaysOnTopHint

        self.setWindowFlags(flags)
        # フラグ変更後も透明化を維持する
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.show()    # フラグを実際に反映するために必要
        self.move(pos) # 位置を復元

        if enabled:
            self.raise_()
            self.activateWindow()
        else:
            self.lower()   # 他ウィンドウの後ろに回りやすくする

        self._update_layer_buttons()

    def _update_layer_buttons(self):
        """is_always_on_top の状態に応じてボタンの外観を更新する"""
        # アクティブ側のスタイル（現在の状態を示す）
        style_top_active = """
            QPushButton {
                background-color: rgba(0, 255, 156, 35);
                color: #00FF9C;
                border: 1px solid #00FF9C;
                border-radius: 3px;
                font-size: 9px;
                padding: 0px 6px;
            }
        """
        style_normal_active = """
            QPushButton {
                background-color: rgba(255, 215, 0, 25);
                color: #FFD700;
                border: 1px solid #FFD700;
                border-radius: 3px;
                font-size: 9px;
                padding: 0px 6px;
            }
        """
        # 非アクティブ側のスタイル（薄く表示、ホバーで少し明るくなる）
        style_inactive = """
            QPushButton {
                background-color: rgba(0, 0, 0, 100);
                color: #444444;
                border: 1px solid #2a2a2a;
                border-radius: 3px;
                font-size: 9px;
                padding: 0px 6px;
            }
            QPushButton:hover {
                background-color: rgba(80, 80, 80, 120);
                color: #777777;
                border: 1px solid #555555;
            }
        """
        if self.is_always_on_top:
            self._btn_normal.setStyleSheet(style_inactive)
            self._btn_top.setStyleSheet(style_top_active)
        else:
            self._btn_normal.setStyleSheet(style_normal_active)
            self._btn_top.setStyleSheet(style_inactive)

    def _make_label(self) -> QLabel:
        """HUD 用ラベル（半透明黒背景）を生成してレイアウトに追加する前の状態で返す"""
        lbl = QLabel()
        lbl.setFont(self._font)
        lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        lbl.setStyleSheet(f"""
            QLabel {{
                color: {HUD_COLOR_NORMAL};
                background-color: {HUD_BG_COLOR};
                border-radius: 4px;
                padding: 2px 8px;
            }}
        """)
        return lbl

    # ── フォントサイズ適用 ────────────────────────────────────────────────────

    def apply_font_size(self):
        """設定の font_size を全ラベルに即時反映する"""
        self._font = self._build_font(self.settings["font_size"])
        # 固定ラベルに適用
        for lbl in (self.lbl_cpu, self.lbl_mem, self.lbl_temp, self.lbl_disk):
            lbl.setFont(self._font)
        # 外部ストレージラベルに適用
        for lbl in self._ext_labels:
            lbl.setFont(self._font)
        self.adjustSize()

    # ── タイマー ──────────────────────────────────────────────────────────────

    def _start_timer(self):
        """指定間隔で refresh_display を呼ぶタイマーを開始する"""
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh_display)
        self._timer.start(UPDATE_INTERVAL_MS)

    # ── メトリクス更新 ────────────────────────────────────────────────────────

    def refresh_display(self):
        """
        psutil でメトリクスを取得し、設定に応じてラベルを更新する。
        各メトリクスは独立して try/except で守られている。
        """
        self._update_cpu()
        self._update_mem()
        self._update_temp()
        self._update_disk()
        self._update_ext()
        # 表示項目の変化に合わせてウィンドウサイズを自動調整
        self.adjustSize()

    def _set_label_text(self, lbl: QLabel, text: str, color: str = HUD_COLOR_NORMAL):
        """ラベルのテキストと文字色をまとめてセットする（フォントは維持）"""
        lbl.setText(text)
        lbl.setStyleSheet(f"""
            QLabel {{
                color: {color};
                background-color: {HUD_BG_COLOR};
                border-radius: 4px;
                padding: 2px 8px;
            }}
        """)

    def _update_cpu(self):
        if not self.settings["cpu"]:
            self.lbl_cpu.hide()
            return
        try:
            val = psutil.cpu_percent(interval=None)
            # 小数なし整数表示（四捨五入）
            pct = round(val)
            self._set_label_text(
                self.lbl_cpu,
                f" CPU  {pct:3d}%",
                pct_color(val)
            )
        except Exception:
            self._set_label_text(self.lbl_cpu, " CPU   ERR")
        self.lbl_cpu.show()

    def _update_mem(self):
        if not self.settings["mem"]:
            self.lbl_mem.hide()
            return
        try:
            mem = psutil.virtual_memory()
            pct = round(mem.percent)
            total_gb = bytes_to_gb(mem.total)
            # 表示形式: MEM  41%  8GB
            self._set_label_text(
                self.lbl_mem,
                f" MEM  {pct:3d}%  {total_gb}GB",
                pct_color(mem.percent)
            )
        except Exception:
            self._set_label_text(self.lbl_mem, " MEM   ERR")
        self.lbl_mem.show()

    def _update_temp(self):
        if not self.settings["temp"]:
            self.lbl_temp.hide()
            return
        try:
            temp = get_cpu_temperature()
            if temp is not None:
                # 小数なし整数表示
                t = round(temp)
                # 70℃以上を警告、90℃以上を危険とする
                color = pct_color(temp) if temp >= 70 else HUD_COLOR_NORMAL
                self._set_label_text(
                    self.lbl_temp,
                    f" TEMP {t:3d}°C",
                    color
                )
            else:
                self._set_label_text(self.lbl_temp, " TEMP   N/A")
        except Exception:
            self._set_label_text(self.lbl_temp, " TEMP   ERR")
        self.lbl_temp.show()

    def _update_disk(self):
        if not self.settings["disk"]:
            self.lbl_disk.hide()
            return
        try:
            disk = psutil.disk_usage("/")
            pct = round(disk.percent)
            total_gb = bytes_to_gb(disk.total)
            # 表示形式: DISK  32%  240GB
            self._set_label_text(
                self.lbl_disk,
                f" DISK {pct:3d}%  {total_gb}GB",
                pct_color(disk.percent)
            )
        except Exception:
            self._set_label_text(self.lbl_disk, " DISK   ERR")
        self.lbl_disk.show()

    def _update_ext(self):
        """
        現在マウント中の外部ストレージを検出し、動的ラベルで表示する。
        設定が OFF の場合、または外部ストレージが存在しない場合はすべて非表示。
        """
        # 設定 OFF ならすべて隠して終了
        if not self.settings["ext"]:
            for lbl in self._ext_labels:
                lbl.hide()
            return

        mounts = get_external_mounts()

        # ラベルが足りなければ新しく生成してサブコンテナに追加する
        while len(self._ext_labels) < len(mounts):
            lbl = self._make_label()
            self._ext_inner.addWidget(lbl)
            self._ext_labels.append(lbl)

        # 各マウントポイントの情報を更新
        for i, mountpoint in enumerate(mounts):
            lbl = self._ext_labels[i]
            try:
                usage = psutil.disk_usage(mountpoint)
                pct = round(usage.percent)
                total_gb = bytes_to_gb(usage.total)
                name = short_name(mountpoint)
                # 表示形式: EXT1  58%  500GB
                self._set_label_text(
                    lbl,
                    f" {name:<8}  {pct:3d}%  {total_gb}GB",
                    pct_color(usage.percent)
                )
            except Exception:
                self._set_label_text(lbl, f" EXT{i + 1}   ERR")
            lbl.setFont(self._font)   # フォントを常に最新状態に保つ
            lbl.show()

        # 使われなくなったラベルは非表示にする
        for i in range(len(mounts), len(self._ext_labels)):
            self._ext_labels[i].hide()

    # ── ドラッグ移動 ──────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        """左クリック押下でドラッグ開始位置を記録する"""
        if event.button() == Qt.LeftButton:
            # グローバル座標 - ウィンドウの左上 = ウィンドウ内オフセット
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        event.accept()

    def mouseMoveEvent(self, event):
        """ドラッグ中はウィンドウを動かす（画面外に出ないよう制限）"""
        if self._drag_pos is not None and (event.buttons() & Qt.LeftButton):
            raw = event.globalPosition().toPoint() - self._drag_pos
            self.move(self._clamp_to_screen(raw))
        event.accept()

    def mouseReleaseEvent(self, event):
        """マウスリリースでドラッグ終了"""
        self._drag_pos = None
        event.accept()

    def _clamp_to_screen(self, pos: QPoint) -> QPoint:
        """
        ウィンドウが画面外に完全に出ないよう座標をクランプする。
        ウィンドウの幅・高さを考慮して右端・下端も制限する。
        """
        screen = QApplication.primaryScreen().geometry()
        x = max(screen.left(), min(pos.x(), screen.right()  - self.width()))
        y = max(screen.top(),  min(pos.y(), screen.bottom() - self.height()))
        return QPoint(x, y)

    # ── 右クリックメニュー ────────────────────────────────────────────────────

    def contextMenuEvent(self, event):
        """右クリックでコンテキストメニューを表示する"""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1a1a1a;
                color: #dddddd;
                border: 1px solid #444444;
                font-size: 12px;
            }
            QMenu::item:selected {
                background-color: #333333;
            }
        """)
        act_settings = menu.addAction("設定...")
        menu.addSeparator()
        # レイヤー切替（現在状態によってラベルを変える）
        if self.is_always_on_top:
            act_layer = menu.addAction("通常レイヤーへ")
            act_layer.triggered.connect(lambda: self.set_always_on_top(False))
        else:
            act_layer = menu.addAction("最前面に戻す")
            act_layer.triggered.connect(lambda: self.set_always_on_top(True))
        menu.addSeparator()
        act_quit = menu.addAction("終了")

        act_settings.triggered.connect(self.open_settings)
        act_quit.triggered.connect(QApplication.quit)

        menu.exec(event.globalPos())

    # ── 設定ウィンドウを開く ──────────────────────────────────────────────────

    def open_settings(self):
        """設定ウィンドウを開く。既に開いていれば前面に出すだけ。"""
        if self._settings_window is None or not self._settings_window.isVisible():
            self._settings_window = SettingsWindow(self.settings, parent=self)
        self._settings_window.show()
        self._settings_window.raise_()
        self._settings_window.activateWindow()


# ─── エントリポイント ─────────────────────────────────────────────────────────

def main():
    # Wayland 環境では XCB バックエンドを強制する
    # （Wayland は FramelessWindowHint / 最前面が不安定なため）
    if "WAYLAND_DISPLAY" in os.environ and "QT_QPA_PLATFORM" not in os.environ:
        os.environ["QT_QPA_PLATFORM"] = "xcb"

    # 高 DPI スケーリング
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")

    app = QApplication(sys.argv)
    app.setApplicationName("DesktopHUD")
    app.setQuitOnLastWindowClosed(False)   # 設定ウィンドウを閉じても終了しない

    hud = HUDWindow()
    hud.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
