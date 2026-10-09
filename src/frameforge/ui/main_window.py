from __future__ import annotations

import json
import csv
import os
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton,
    QMenu, QScrollArea, QStackedWidget, QTextEdit, QToolButton, QVBoxLayout, QWidget,
)

from .. import __version__
from ..catalog import GUIDE, GUIDE_CHECKLISTS, GUIDE_CHECKLIST_LABELS, GUIDE_GAMES, GUIDES, GAMES
from ..core.apply import apply_profile_setting, build_profile_bytes, make_diff, read_profile_setting
from ..core.benchmark import (
    Benchmark, FRAME_BUDGET_FPS_PRESETS, METRIC_LABELS, benchmark_import_fingerprint, compare_benchmark_groups, compare_benchmarks,
    format_budget_threshold_label,
    export_comparison_csv, export_comparison_json, export_group_comparison_csv,
    export_group_comparison_json, load_benchmark_csv,
)
from ..core.benchmark_store import BenchmarkStore, MAX_HISTORY, MAX_REFERENCE_RUNS, retain_benchmark_runs
from ..core.backup import restore_from_backup, sha256
from ..core.config_finder import find_skyrim_config
from ..core.profiles import TUNING_PROFILES
from ..core.safety import SafetyError
from ..core.settings_snapshot import read_allowed_setting_snapshot
from ..core.scanner import detect_skyrim_installs, system_snapshot
from .benchmark_chart import FrameTimeChart
from .benchmark_search import matching_benchmark_indices


BG = "#0b1020"
PANEL = "#111a2c"
CARD = "#17243a"
TEXT = "#edf3ff"
MUTED = "#a1b1cc"
ACCENT = "#72a8ff"
GREEN = "#45d6a0"


def probable_duplicate_dialog_dimensions(available_width: int, available_height: int) -> tuple[int, int, int, int]:
    """Return dialog width/height and scroll-area min/max heights for the screen."""
    width = max(240, min(720, available_width - 24))
    height = max(180, min(520, available_height - 24))
    scroll_max = max(48, min(340, height - 200))
    scroll_min = min(140, scroll_max)
    return width, height, scroll_min, scroll_max


class ProbableDuplicateDialog(QDialog):
    """Let users skip or explicitly keep aggregate-matching CSV imports."""

    def __init__(self, duplicates: list[tuple[int, int, str, str]], total: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Возможные дубликаты CSV")
        # QDialog is positioned relative to its parent; size it for that monitor,
        # which may differ from the primary display in a multi-monitor setup.
        screen = parent.screen() if parent else None
        screen = screen or QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else None
        screen_width = available.width() if available else 1280
        screen_height = available.height() if available else 720
        width, height, scroll_min, scroll_max = probable_duplicate_dialog_dimensions(screen_width, screen_height)
        self.setMinimumSize(min(560, width), min(320, height))
        self.resize(width, height)
        layout = QVBoxLayout(self)
        explanation = QLabel(
            f"Найдены возможные дубликаты: {len(duplicates)} из {total}. "
            "Сводные метрики совпадают; это не доказывает, что CSV или захват одинаковые. "
            "По умолчанию отмеченные файлы будут пропущены. Отметь файл, чтобы добавить его всё равно."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        self.duplicate_list = QScrollArea()
        self.duplicate_list.setWidgetResizable(True)
        self.duplicate_list.setMinimumHeight(scroll_min)
        self.duplicate_list.setMaximumHeight(scroll_max)
        duplicate_rows = QWidget()
        duplicate_rows_layout = QVBoxLayout(duplicate_rows)
        self.duplicate_list.setWidget(duplicate_rows)
        layout.addWidget(self.duplicate_list, 1)
        self.choices: list[tuple[int, QCheckBox]] = []
        for position, selected_index, filename, prior in duplicates:
            row = QHBoxLayout()
            checkbox = QCheckBox(f"Добавить всё равно: CSV #{selected_index} — {filename}")
            checkbox.setAccessibleName(f"Добавить возможный дубликат CSV #{selected_index}: {filename} всё равно")
            row.addWidget(checkbox)
            matched_label = QLabel(f"Совпадает с {prior}")
            matched_label.setWordWrap(True)
            row.addWidget(matched_label, 1)
            duplicate_rows_layout.addLayout(row)
            self.choices.append((position, checkbox))
        duplicate_rows_layout.addStretch(1)
        buttons = QDialogButtonBox()
        safe_default = buttons.addButton("Добавить уникальные, пропустить совпадения", QDialogButtonBox.ButtonRole.AcceptRole)
        add_selected = buttons.addButton("Продолжить выбранные", QDialogButtonBox.ButtonRole.AcceptRole)
        cancel_all = buttons.addButton("Отменить весь импорт", QDialogButtonBox.ButtonRole.RejectRole)
        safe_default.setDefault(True)
        safe_default.clicked.connect(self._accept_with_duplicates_skipped)
        add_selected.clicked.connect(self.accept)
        cancel_all.clicked.connect(self.reject)
        layout.addWidget(buttons)

    def _accept_with_duplicates_skipped(self):
        for _, checkbox in self.choices:
            checkbox.setChecked(False)
        self.accept()

    def positions_to_keep(self) -> set[int]:
        return {position for position, checkbox in self.choices if checkbox.isChecked()}


def app_data_dir() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local")) / "FrameForge"
    (root / "backups").mkdir(parents=True, exist_ok=True)
    return root


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FrameForge — Game Tuning Studio")
        self.resize(1200, 780)
        self.setMinimumSize(960, 640)
        self.config_path: Path | None = None
        self.game_folder: Path | None = None
        self.original: bytes | None = None
        self.preview_bytes: bytes | None = None
        self.last_backup: Path | None = None
        self.backup_config: Path | None = None
        self.last_backup_sha256: str | None = None
        self.last_current_sha256: str | None = None
        self._build()
        self._style()
        self.show_page(0)

    def _build(self):
        central = QWidget()
        outer = QHBoxLayout(central)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(14)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(218)
        side = QVBoxLayout(sidebar)
        brand = QLabel("FRAMEFORGE")
        brand.setObjectName("brand")
        side.addWidget(brand)
        tagline = QLabel("SAFE GAME TUNING")
        tagline.setObjectName("tagline")
        side.addWidget(tagline)
        side.addSpacing(24)
        self.nav = []
        for label in ["Обзор", "Игры", "Бенчмарк", "Оптимизатор", "Резервные копии"]:
            button = QPushButton(label)
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, index=len(self.nav): self.show_page(index))
            button.setAccessibleName(f"Открыть раздел {label}")
            side.addWidget(button)
            self.nav.append(button)
        side.addStretch(1)
        safety = QLabel("ЛОКАЛЬНО\nТолько выбранные изменения\nБез античит-твиков")
        safety.setObjectName("safety")
        side.addWidget(safety)
        version = QLabel(f"v{__version__} · MIT")
        version.setObjectName("muted")
        side.addWidget(version)

        right = QVBoxLayout()
        top = QHBoxLayout()
        self.page_title = QLabel("Обзор")
        self.page_title.setObjectName("pageTitle")
        top.addWidget(self.page_title)
        top.addStretch(1)
        win = QLabel("WINDOWS 10 / 11")
        win.setObjectName("tagline")
        top.addWidget(win)
        right.addLayout(top)
        self.stack = QStackedWidget()
        self.stack.addWidget(self._dashboard_page())
        self.stack.addWidget(self._games_page())
        self.stack.addWidget(self._benchmark_page())
        self.stack.addWidget(self._optimizer_page())
        self.stack.addWidget(self._backups_page())
        right.addWidget(self.stack, 1)
        outer.addWidget(sidebar)
        outer.addLayout(right, 1)
        self.setCentralWidget(central)

    def _style(self):
        self.setStyleSheet(f"""
            QWidget {{ background:{BG}; color:{TEXT}; font-family:'Segoe UI'; font-size:10pt; }}
            #sidebar {{ background:{PANEL}; border:1px solid #26354e; border-radius:16px; }}
            #brand {{ color:{TEXT}; font-size:20pt; font-weight:800; letter-spacing:1px; }}
            #tagline {{ color:{ACCENT}; font-size:8pt; font-weight:700; }}
            #pageTitle {{ font-size:20pt; font-weight:700; padding:8px 0; }}
            #muted {{ color:{MUTED}; font-size:9pt; }}
            #safety {{ color:{GREEN}; background:#142b2a; border-radius:10px; padding:12px; font-size:9pt; }}
            #card {{ background:{CARD}; border:1px solid #253651; border-radius:14px; }}
            QPushButton {{ background:#20324d; border:1px solid #2d4466; border-radius:9px; padding:10px 14px; text-align:left; }}
            QPushButton:hover {{ background:#294568; }}
            QPushButton:checked {{ background:#2b5791; border-color:{ACCENT}; }}
            QPushButton#primary {{ background:#2e67b2; border-color:#4384d8; font-weight:700; }}
            QPushButton#primary:hover {{ background:#3d79c8; }}
            QPushButton#danger {{ background:#573d31; border-color:#875437; }}
            QLineEdit, QComboBox, QTextEdit, QListWidget {{ background:#080e19; border:1px solid #293a56; border-radius:8px; padding:8px; selection-background-color:#2b5791; }}
            QTextEdit {{ font-family:Consolas; font-size:9pt; }}
            QScrollArea {{ border:0; }}
            QFrame#separator {{ background:#26354e; max-height:1px; }}
        """)

    def _scroll_page(self):
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 14, 8, 12)
        layout.setSpacing(14)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        return scroll, layout

    def _card(self, title: str, value: str, note: str = "") -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        heading = QLabel(title.upper())
        heading.setObjectName("tagline")
        layout.addWidget(heading)
        data = QLabel(value)
        data.setWordWrap(True)
        data.setFont(QFont("Segoe UI", 12, QFont.Weight.DemiBold))
        layout.addWidget(data)
        if note:
            info = QLabel(note)
            info.setObjectName("muted")
            info.setWordWrap(True)
            layout.addWidget(info)
        return card

    def _dashboard_page(self):
        scroll, layout = self._scroll_page()
        intro = QLabel("Настрой игры осознанно — с предварительным diff и полным откатом")
        intro.setStyleSheet("font-size:17pt;font-weight:700")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        summary = QLabel("FrameForge показывает текущие данные системы только для чтения. Изменения игровых файлов узкие, документированные и обратимые.")
        summary.setObjectName("muted")
        summary.setWordWrap(True)
        layout.addWidget(summary)
        metrics = system_snapshot()
        grid = QGridLayout()
        cards = [
            ("CPU", metrics.get("cpu", "Unavailable") + "\n" + metrics.get("logical_processors", "?") + " логических потоков"),
            ("RAM", f"{metrics.get('ram_available_gb', '—')} GB доступно / {metrics.get('ram_total_gb', '—')} GB"),
            ("Диск", f"{metrics.get('disk_free_gb', '—')} GB свободно / {metrics.get('disk_total_gb', '—')} GB"),
            ("GPU", metrics.get("gpu", "Не определена в этой сборке")),
        ]
        for index, (name, value) in enumerate(cards):
            grid.addWidget(self._card(name, value, "Снимок локальной системы · только чтение"), index // 2, index % 2)
        layout.addLayout(grid)
        installs = detect_skyrim_installs()
        install_text = "Steam: " + ("Найдено: " + "; ".join(str(path) for path in installs) if installs else "игра не обнаружена по Steam library manifest")
        layout.addWidget(self._card("Обнаружение игры", install_text, "Поиск читает libraryfolders.vdf и appmanifest_489830.acf; он не меняет библиотеку. Настройки пользователя обычно лежат отдельно от каталога игры."))
        row = QHBoxLayout()
        go = QPushButton("Открыть оптимизатор Skyrim")
        go.setObjectName("primary")
        go.clicked.connect(lambda: self.show_page(3))
        row.addWidget(go)
        row.addStretch(1)
        layout.addLayout(row)
        return scroll

    def _games_page(self):
        scroll, layout = self._scroll_page()
        layout.addWidget(QLabel("Профили с автоматическим изменением"))
        layout.addWidget(self._card(GAMES[0]["name"], GAMES[0]["description"], "Настраиваемый профиль. Всегда создаёт backup и показывает diff."))
        open_skyrim = QPushButton("Открыть профиль Skyrim")
        open_skyrim.setObjectName("primary")
        open_skyrim.clicked.connect(lambda: self.show_page(3))
        layout.addWidget(open_skyrim)
        layout.addWidget(QLabel("Рекомендации внутри игры · без правки файлов"))
        search = QLineEdit()
        search.setPlaceholderText("Поиск игры в каталоге…")
        layout.addWidget(search)
        game_list = QListWidget()
        game_list.addItems(GUIDE_GAMES)
        layout.addWidget(game_list)
        guide_title = QLabel("Выбери игру")
        guide_title.setStyleSheet("font-size:13pt;font-weight:700")
        layout.addWidget(guide_title)
        recommendation = QTextEdit()
        recommendation.setReadOnly(True)
        recommendation.setPlainText(GUIDE)
        recommendation.setMaximumHeight(160)
        layout.addWidget(recommendation)
        def show_guide(item):
            guide_title.setText(item.text())
            recommendation.setPlainText(GUIDES[item.text()] + "\n\nИзменяй настройки только через меню игры. Поддержка файлов и античита не заявлена.")
        game_list.currentItemChanged.connect(lambda current, previous: show_guide(current) if current else None)
        search.textChanged.connect(lambda text: [game_list.item(i).setHidden(text.casefold() not in game_list.item(i).text().casefold()) for i in range(game_list.count())])
        notice = QLabel("У популярных игр настройки и античит меняются обновлениями. В этой версии FrameForge только открывает безопасный внутриигровой чек-лист для этих игр.")
        notice.setObjectName("muted")
        notice.setWordWrap(True)
        layout.addWidget(notice)
        return scroll

    def _optimizer_page(self):
        scroll, layout = self._scroll_page()
        title = QLabel("Skyrim Special Edition · профили травы")
        title.setStyleSheet("font-size:15pt;font-weight:700")
        layout.addWidget(title)
        profile_row = QHBoxLayout()
        profile_row.addWidget(QLabel("Профиль:"))
        self.profile_select = QComboBox()
        self.profile_select.addItems([profile.name for profile in TUNING_PROFILES])
        profile_row.addWidget(self.profile_select, 1)
        layout.addLayout(profile_row)
        self.profile_info = QLabel()
        self.profile_info.setWordWrap(True)
        self.profile_info.setObjectName("muted")
        layout.addWidget(self.profile_info)
        pathrow = QHBoxLayout()
        self.path_label = QLabel("Папка Skyrim Special Edition не выбрана")
        self.path_label.setObjectName("muted")
        self.path_label.setWordWrap(True)
        pathrow.addWidget(self.path_label, 1)
        choose = QPushButton("Выбрать каталог настроек")
        choose.clicked.connect(self.choose_skyrim_folder)
        pathrow.addWidget(choose)
        layout.addLayout(pathrow)
        values = QHBoxLayout()
        values.addWidget(QLabel("Параметр травы"))
        self.current_value = QLabel("Текущее: —")
        self.current_value.setStyleSheet(f"color:{GREEN};font-weight:700")
        values.addWidget(self.current_value)
        values.addStretch(1)
        values.addWidget(QLabel("Новое значение:"))
        self.value_select = QComboBox()
        values.addWidget(self.value_select)
        layout.addLayout(values)
        actions = QHBoxLayout()
        scan = QPushButton("Проверить и показать diff")
        scan.clicked.connect(self.scan_preview)
        actions.addWidget(scan)
        self.apply_button = QPushButton("Применить с backup")
        self.apply_button.setObjectName("primary")
        self.apply_button.clicked.connect(self.apply_preview)
        actions.addWidget(self.apply_button)
        rollback = QPushButton("Откатить backup")
        rollback.setObjectName("danger")
        rollback.clicked.connect(self.restore_last)
        actions.addWidget(rollback)
        layout.addLayout(actions)
        self.diff_box = QTextEdit()
        self.diff_box.setReadOnly(True)
        self.diff_box.setPlaceholderText("Сканируй файл перед применением; здесь появится точный diff.")
        self.diff_box.setMinimumHeight(280)
        layout.addWidget(self.diff_box)
        source = QLabel('<a href="https://stepmodifications.org/wiki/Guide:SkyrimPrefs_INI/Grass">SkyrimPrefs.ini: дальность прорисовки</a> · <a href="https://stepmodifications.org/wiki/Guide:Skyrim_INI/Grass">Skyrim.ini: плотность травы</a>')
        source.setOpenExternalLinks(True)
        source.setObjectName("muted")
        layout.addWidget(source)
        self.profile_select.currentIndexChanged.connect(self.on_profile_changed)
        self.on_profile_changed()
        return scroll

    def on_profile_changed(self):
        if not hasattr(self, "profile_select"):
            return
        profile = TUNING_PROFILES[self.profile_select.currentIndex()]
        self.profile_info.setText(profile.description + " Игра должна быть закрыта перед применением.")
        self.value_select.clear()
        self.value_select.addItems([str(value) for value in profile.values])
        self.value_select.setCurrentText(str(profile.default_value))
        if self.game_folder:
            try:
                self.config_path = find_skyrim_config(self.game_folder, profile.config_name)
                self.path_label.setText(str(self.config_path))
                self.scan_preview()
            except (SafetyError, OSError, ValueError):
                self.config_path = None
                self.path_label.setText(f"{profile.config_name} не найден в выбранной папке")
                self.original = self.preview_bytes = None
                self.diff_box.clear()
                self.current_value.setText("Текущее: —")
        else:
            self.config_path = None
            self.path_label.setText(f"Папка настроек не выбрана · нужен {profile.config_name}")
            self.original = self.preview_bytes = None
            self.diff_box.clear()
            self.current_value.setText("Текущее: —")

    def _benchmark_page(self):
        scroll, layout = self._scroll_page()
        title = QLabel("Замеры до и после")
        title.setStyleSheet("font-size:15pt;font-weight:700")
        layout.addWidget(title)
        note = QLabel("FrameForge анализирует CSV с frame_time_ms или PresentMon (MsBetweenDisplayChange / MsBetweenPresents). Тип метрики сохраняется; сравнение разных типов помечается как несопоставимое. Захват выполняет внешняя программа; FrameForge ничего не внедряет в игру и не показывает оверлей. Используй одинаковую сцену, разрешение и условия.")
        note.setWordWrap(True)
        note.setObjectName("muted")
        layout.addWidget(note)
        privacy_note = QLabel("История хранится на этом компьютере в %LOCALAPPDATA%\\FrameForge\\benchmarks.json. Сохраняются имя CSV, игра/сцена, заметка, ручные отметки чек-листа, сводные метрики и только выбранный снимок разрешённого параметра Skyrim. Исходный CSV и путь к INI не сохраняются; заметки, отметки, снимки и метки не включаются в экспорт.")
        privacy_note.setObjectName("muted")
        privacy_note.setWordWrap(True)
        layout.addWidget(privacy_note)
        run_label = QLabel("Метки замера (не обязательны, только для локальной истории)")
        run_label.setObjectName("tagline")
        layout.addWidget(run_label)
        self.benchmark_game = QComboBox()
        self.benchmark_game.addItem("Игра не указана", "")
        supported_games = dict.fromkeys([game["name"] for game in GAMES] + GUIDE_GAMES)
        for game_name in supported_games:
            self.benchmark_game.addItem(game_name, game_name)
        layout.addWidget(self.benchmark_game)
        self.benchmark_scene = QLineEdit()
        self.benchmark_scene.setPlaceholderText("Сцена / карта / пресет; не вводи личные пути (до 120 символов)")
        self.benchmark_scene.setMaxLength(120)
        layout.addWidget(self.benchmark_scene)
        change_note_label = QLabel("Заметка только к следующему замеру")
        change_note_label.setObjectName("tagline")
        layout.addWidget(change_note_label)
        self.benchmark_change_note = QLineEdit()
        self.benchmark_change_note.setPlaceholderText("Что изменил перед этим прогоном? Например: тени — высокие → средние (до 160 символов)")
        self.benchmark_change_note.setMaxLength(160)
        layout.addWidget(self.benchmark_change_note)
        self.benchmark_include_setting = QCheckBox("Добавить снимок текущего разрешённого параметра Skyrim (только чтение; путь не сохраняется)")
        self.benchmark_include_setting.setToolTip("Нужна выбранная папка настроек на странице «Оптимизатор». Сохраняется только имя параметра и его целое значение.")
        layout.addWidget(self.benchmark_include_setting)
        checklist_label = QLabel("Что вручную изменено перед этим прогоном? Отмечай только применённые пункты.")
        checklist_label.setObjectName("tagline")
        layout.addWidget(checklist_label)
        self.benchmark_checklist_hint = QLabel()
        self.benchmark_checklist_hint.setObjectName("muted")
        self.benchmark_checklist_hint.setWordWrap(True)
        layout.addWidget(self.benchmark_checklist_hint)
        self.benchmark_changes = QListWidget()
        self.benchmark_changes.setMaximumHeight(112)
        layout.addWidget(self.benchmark_changes)
        self.benchmark_game.currentIndexChanged.connect(self._refresh_benchmark_checklist)
        self._refresh_benchmark_checklist()
        self.benchmark_store = BenchmarkStore(app_data_dir() / "benchmarks.json")
        try:
            self.benchmark_runs: list[Benchmark] = self.benchmark_store.load()
        except (OSError, ValueError) as exc:
            self.benchmark_runs = []
            QMessageBox.warning(self, "История замеров недоступна", f"Создана пустая история в памяти приложения. Исходный файл не изменён.\n{exc}")
        self.benchmark_list = QListWidget()
        self.benchmark_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.benchmark_list.itemSelectionChanged.connect(self._update_reference_controls)
        self.benchmark_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.benchmark_list.customContextMenuRequested.connect(self._show_benchmark_context_menu)
        self._benchmark_group_a: set[int] = set()
        self._benchmark_group_b: set[int] = set()
        self._active_benchmark_baseline: Benchmark | None = None
        self._recent_benchmark_pairs: list[tuple[Benchmark, Benchmark]] = []
        self._last_benchmark_comparison = None
        history_filter_row = QHBoxLayout()
        self.benchmark_history_filter = QLineEdit()
        self.benchmark_history_filter.setPlaceholderText("Фильтр списка для групп: файл, игра, сцена, тип, заметка…")
        self.benchmark_history_filter.setAccessibleName("Фильтр списка замеров для групп")
        self.benchmark_history_filter.setClearButtonEnabled(True)
        self.benchmark_history_filter.textChanged.connect(self._filter_benchmark_history)
        history_filter_row.addWidget(self.benchmark_history_filter, 1)
        self.benchmark_history_count = QLabel()
        self.benchmark_history_count.setObjectName("muted")
        history_filter_row.addWidget(self.benchmark_history_count)
        layout.addLayout(history_filter_row)
        layout.addWidget(self.benchmark_list)
        self.compare_previous_matching_button = QPushButton(
            "Подобрать предыдущий замер той же игры, сцены и метрики"
        )
        self.compare_previous_matching_button.setToolTip(
            "Выбери один прогон. FrameForge подставит ближайший более ранний с такими же метками; сравнение нужно подтвердить отдельно."
        )
        self.compare_previous_matching_button.setEnabled(False)
        self.compare_previous_matching_button.clicked.connect(self.compare_selected_with_previous_matching_run)
        layout.addWidget(self.compare_previous_matching_button)
        self.same_label_history_button = QPushButton("Показать историю тех же игры, сцены и метрики")
        self.same_label_history_button.setToolTip("Только чтение: показывает все прогоны с точно совпадающими метками, включая эталоны.")
        self.same_label_history_button.setEnabled(False)
        self.same_label_history_button.clicked.connect(self.show_selected_same_label_history)
        layout.addWidget(self.same_label_history_button)
        self.compare_active_baseline_button = QPushButton("Сравнить с активной базой")
        self.compare_active_baseline_button.setToolTip("Подставляет активную базу и выбранный прогон в A/B; отчёт строится только после нажатия «Сравнить».")
        self.compare_active_baseline_button.setVisible(False)
        self.compare_active_baseline_button.clicked.connect(self.compare_selected_with_active_baseline)
        layout.addWidget(self.compare_active_baseline_button)
        reference_row = QHBoxLayout()
        self.reference_status = QLabel("Эталоны: 0/5 · закреплённые прогоны сохраняются сверх лимита истории")
        self.reference_status.setObjectName("muted")
        self.reference_status.setWordWrap(True)
        reference_row.addWidget(self.reference_status, 1)
        self.toggle_reference_button = QPushButton("Закрепить выбранный как эталон")
        self.toggle_reference_button.setEnabled(False)
        self.toggle_reference_button.clicked.connect(self.toggle_selected_reference)
        reference_row.addWidget(self.toggle_reference_button)
        layout.addLayout(reference_row)
        group_help = QLabel("Повторные замеры: выдели не менее 3 CSV в каждой группе. Фильтр списка влияет только на это назначение; поля Baseline/Variant используют всю историю. Группы временные и сбросятся при перезапуске.")
        group_help.setObjectName("muted")
        group_help.setWordWrap(True)
        layout.addWidget(group_help)
        group_row = QHBoxLayout()
        self.assign_group_a_button = QPushButton("Выбранные → группа A")
        self.assign_group_a_button.clicked.connect(lambda: self._assign_selected_benchmark_group("A"))
        group_row.addWidget(self.assign_group_a_button)
        self.assign_group_b_button = QPushButton("Выбранные → группа B")
        self.assign_group_b_button.clicked.connect(lambda: self._assign_selected_benchmark_group("B"))
        group_row.addWidget(self.assign_group_b_button)
        self.remove_group_button = QPushButton("Убрать выбранные из групп")
        self.remove_group_button.clicked.connect(self._remove_selected_benchmark_group)
        group_row.addWidget(self.remove_group_button)
        layout.addLayout(group_row)
        self.benchmark_groups_status = QLabel("Группа A: 0 · Группа B: 0")
        self.benchmark_groups_status.setObjectName("tagline")
        layout.addWidget(self.benchmark_groups_status)
        budget_row = QHBoxLayout()
        budget_row.addWidget(QLabel("Frame budget:"))
        self.benchmark_frame_budget = QComboBox()
        for fps in FRAME_BUDGET_FPS_PRESETS:
            self.benchmark_frame_budget.addItem(f"{fps} FPS — {format_budget_threshold_label(fps)}", fps)
        self.benchmark_frame_budget.setCurrentIndex(FRAME_BUDGET_FPS_PRESETS.index(60))
        self.benchmark_frame_budget.setToolTip("Доля принятых кадров, время которых не превышает 1000/FPS. Для старой истории это значение недоступно.")
        self.benchmark_frame_budget.currentIndexChanged.connect(self._refresh_benchmark_budget)
        budget_row.addWidget(self.benchmark_frame_budget)
        budget_hint = QLabel("Доля принятых кадров ≤ выбранному времени; не оценка плавности")
        budget_hint.setObjectName("muted")
        budget_row.addWidget(budget_hint, 1)
        layout.addLayout(budget_row)
        self.compare_groups_button = QPushButton("Сравнить повторные замеры A/B")
        self.compare_groups_button.clicked.connect(self.compare_benchmark_groups_selection)
        layout.addWidget(self.compare_groups_button)
        import_button = QPushButton("Импортировать CSV замера")
        import_button.clicked.connect(self.import_benchmark)
        layout.addWidget(import_button)
        compare_row = QHBoxLayout()
        compare_row.addWidget(QLabel("Baseline (A):"))
        self.benchmark_before = QComboBox()
        self.benchmark_before.currentIndexChanged.connect(self._benchmark_pair_selection_changed)
        compare_row.addWidget(self.benchmark_before, 1)
        compare_row.addWidget(QLabel("Variant (B):"))
        self.benchmark_after = QComboBox()
        self.benchmark_after.currentIndexChanged.connect(self._benchmark_pair_selection_changed)
        compare_row.addWidget(self.benchmark_after, 1)
        compare_button = QPushButton("Сравнить")
        compare_button.setObjectName("primary")
        compare_button.clicked.connect(self.compare_benchmark_selection)
        compare_row.addWidget(compare_button)
        layout.addLayout(compare_row)
        pair_identity_row = QHBoxLayout()
        self.benchmark_before_identity = QLabel()
        self.benchmark_before_identity.setObjectName("muted")
        self.benchmark_before_identity.setWordWrap(True)
        self.benchmark_before_identity.setAccessibleName("Текущий выбранный Baseline")
        self.benchmark_after_identity = QLabel()
        self.benchmark_after_identity.setObjectName("muted")
        self.benchmark_after_identity.setWordWrap(True)
        self.benchmark_after_identity.setAccessibleName("Текущий выбранный Variant")
        pair_identity_row.addWidget(self.benchmark_before_identity, 1)
        pair_identity_row.addWidget(self.benchmark_after_identity, 1)
        layout.addLayout(pair_identity_row)
        swap_pair_row = QHBoxLayout()
        self.swap_benchmark_pair_button = QPushButton("Поменять A ↔ B")
        self.swap_benchmark_pair_button.setAccessibleName("Поменять местами Baseline и Variant")
        self.swap_benchmark_pair_button.setToolTip("Меняет роли выбранных прогонов и сбрасывает текущий отчёт. Для нового нажми «Сравнить» отдельно.")
        self.swap_benchmark_pair_button.clicked.connect(self.swap_benchmark_pair)
        swap_pair_row.addWidget(self.swap_benchmark_pair_button)
        swap_pair_row.addStretch(1)
        layout.addLayout(swap_pair_row)
        compare_scope_hint = QLabel("Поиск замера ниже меняет A/B только после назначения. Фильтр списка истории влияет только на группы.")
        compare_scope_hint.setObjectName("muted")
        layout.addWidget(compare_scope_hint)
        self.recent_pairs_toggle = QToolButton()
        self.recent_pairs_toggle.setText("Недавние сравнения (сессия)")
        self.recent_pairs_toggle.setCheckable(True)
        self.recent_pairs_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.recent_pairs_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.recent_pairs_toggle.setAccessibleName("Показать недавние сравнения в этой сессии")
        layout.addWidget(self.recent_pairs_toggle)
        self.recent_pairs_list = QListWidget()
        self.recent_pairs_list.setAccessibleName("Последние десять сравнений в этой сессии")
        self.recent_pairs_list.setMaximumHeight(132)
        self.recent_pairs_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.recent_pairs_list.setVisible(False)
        self.recent_pairs_toggle.toggled.connect(self._toggle_recent_pairs)
        self.recent_pairs_list.itemClicked.connect(self._restore_recent_pair)
        self.recent_pairs_list.itemActivated.connect(self._restore_recent_pair)
        layout.addWidget(self.recent_pairs_list)
        pair_search_row = QHBoxLayout()
        pair_search_row.addWidget(QLabel("Найти замер для A/B:"))
        self.benchmark_pair_search = QLineEdit()
        self.benchmark_pair_search.setPlaceholderText("Поиск по имени файла, игре, сцене, заметке…")
        self.benchmark_pair_search.setAccessibleName("Поиск замера для Baseline и Variant")
        self.benchmark_pair_search.setClearButtonEnabled(True)
        self.benchmark_pair_search.textChanged.connect(self._search_benchmark_pairs)
        pair_search_row.addWidget(self.benchmark_pair_search, 1)
        layout.addLayout(pair_search_row)
        self.benchmark_pair_search_results = QListWidget()
        self.benchmark_pair_search_results.setAccessibleName("Результаты поиска замеров для A/B")
        self.benchmark_pair_search_results.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.benchmark_pair_search_results.setMaximumHeight(150)
        self.benchmark_pair_search_results.itemSelectionChanged.connect(self._update_pair_assignment_buttons)
        self.benchmark_pair_search_status = QLabel("Начни вводить, чтобы найти замер. Поиск не меняет выбранную пару.")
        self.benchmark_pair_search_status.setObjectName("muted")
        layout.addWidget(self.benchmark_pair_search_results)
        layout.addWidget(self.benchmark_pair_search_status)
        pair_assign_row = QHBoxLayout()
        self.assign_pair_search_baseline = QPushButton("Назначить выбранный как Baseline (A)")
        self.assign_pair_search_baseline.clicked.connect(self._assign_pair_search_result_to_baseline)
        self.assign_pair_search_variant = QPushButton("Назначить выбранный как Variant (B)")
        self.assign_pair_search_variant.clicked.connect(self._assign_pair_search_result_to_variant)
        pair_assign_row.addWidget(self.assign_pair_search_baseline)
        pair_assign_row.addWidget(self.assign_pair_search_variant)
        layout.addLayout(pair_assign_row)
        self._update_pair_assignment_buttons()
        self.export_benchmark_button = QPushButton("Экспортировать сводку…")
        self.export_benchmark_button.clicked.connect(self.export_benchmark_selection)
        self.export_benchmark_button.setEnabled(False)
        self.copy_benchmark_report_button = QPushButton("Скопировать отчёт")
        self.copy_benchmark_report_button.setAccessibleName("Скопировать текущий видимый отчёт сравнения")
        self.copy_benchmark_report_button.setToolTip("Копирует полный текст отчёта, включая имена CSV-прогонов и введённые заметки, чтобы вставить его в другое приложение.")
        self.copy_benchmark_report_button.clicked.connect(self.copy_benchmark_report)
        self.copy_benchmark_report_button.setEnabled(False)
        export_actions_row = QHBoxLayout()
        export_actions_row.addWidget(self.export_benchmark_button)
        export_actions_row.addWidget(self.copy_benchmark_report_button)
        layout.addLayout(export_actions_row)
        export_scope_hint = QLabel("Экспортируется последняя выбранная пара или группа; фильтр списка на экспорт не влияет.")
        export_scope_hint.setObjectName("muted")
        layout.addWidget(export_scope_hint)
        self._refresh_benchmark_history()
        self._refresh_recent_benchmark_pairs()
        self.benchmark_report = QTextEdit()
        self.benchmark_report.setReadOnly(True)
        self.benchmark_report.setPlaceholderText("Импортируй два CSV для обычного сравнения или назначь не менее трёх замеров на каждую группу A/B.")
        self.benchmark_report.setMinimumHeight(200)
        layout.addWidget(self.benchmark_report)
        self.benchmark_chart_title = QLabel("Доля кадров по диапазонам времени (%, A/B и число кадров N показаны в легенде)")
        self.benchmark_chart_title.setObjectName("tagline")
        layout.addWidget(self.benchmark_chart_title)
        self.benchmark_chart = FrameTimeChart()
        layout.addWidget(self.benchmark_chart)
        self.benchmark_chart_note = QLabel("Интервалы слева направо: <8,333; [8,333–16,667); [16,667–33,333); [33,333–50); [50–100); ≥100 мс. Классификация использует точные границы 1000/FPS. При малом N распределение менее устойчиво; разница между прогонами сама по себе не доказывает причину.")
        self.benchmark_chart_note.setObjectName("muted")
        self.benchmark_chart_note.setWordWrap(True)
        layout.addWidget(self.benchmark_chart_note)
        sample = QLabel("CSV: frame_time_ms (свой экспорт) или PresentMon с MsBetweenDisplayChange / MsBetweenPresents.")
        sample.setObjectName("muted")
        layout.addWidget(sample)
        return scroll

    def import_benchmark(self):
        setting_key = ""
        setting_value = None
        paths, _ = QFileDialog.getOpenFileNames(self, "Выбрать один или несколько CSV с временем кадров", "", "CSV files (*.csv);;All files (*)")
        if not paths:
            return
        if self.benchmark_include_setting.isChecked():
            if self.benchmark_game.currentData() != "The Elder Scrolls V: Skyrim Special Edition":
                QMessageBox.warning(self, "Снимок настройки не добавлен", "Для снимка выбери The Elder Scrolls V: Skyrim Special Edition или сними флажок.")
                return
            if not self.config_path:
                QMessageBox.warning(self, "Снимок настройки не добавлен", "Сначала выбери папку настроек на странице «Оптимизатор» или сними флажок.")
                return
            try:
                setting_key, setting_value = read_allowed_setting_snapshot(self.config_path)
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, "Снимок настройки не добавлен", f"Не удалось безопасно прочитать разрешённый параметр. CSV не импортирован.\n{exc}")
                return
        imported: list[Benchmark] = []
        imported_names: list[tuple[int, str]] = []
        file_warnings: list[str] = []
        file_errors: list[str] = []
        manual_changes = tuple(
            self.benchmark_changes.item(index).data(Qt.ItemDataRole.UserRole)
            for index in range(self.benchmark_changes.count())
            if self.benchmark_changes.item(index).checkState() == Qt.CheckState.Checked
        )
        for selected_index, path in enumerate(paths, start=1):
            try:
                run, warnings = load_benchmark_csv(Path(path))
                imported.append(Benchmark(
                    name=run.name,
                    game=self.benchmark_game.currentData() or "",
                    scene=self.benchmark_scene.text().strip(),
                    sample_count=run.sample_count,
                    average_fps=run.average_fps,
                    one_percent_low_fps=run.one_percent_low_fps,
                    p99_frame_time_ms=run.p99_frame_time_ms,
                    median_frame_time_ms=run.median_frame_time_ms,
                    min_frame_time_ms=run.min_frame_time_ms,
                    max_frame_time_ms=run.max_frame_time_ms,
                    frame_time_buckets=run.frame_time_buckets,
                    metric_kind=run.metric_kind,
                    change_note=self.benchmark_change_note.text().strip(),
                    frame_timing=run.frame_timing,
                    frame_budget_counts=run.frame_budget_counts,
                    setting_key=setting_key,
                    setting_value=setting_value,
                    manual_changes=manual_changes,
                ))
                imported_names.append((selected_index, Path(path).name))
                file_warnings.extend(f"#{selected_index} {Path(path).name}: {warning}" for warning in warnings)
            except (OSError, UnicodeError, ValueError, csv.Error) as exc:
                file_errors.append(f"#{selected_index} {Path(path).name}: {exc}")
        if not imported:
            details_lines = file_errors[:10]
            if len(file_errors) > 10:
                details_lines.append(f"… и ещё {len(file_errors) - 10} файлов с ошибками")
            details = "\n".join(details_lines) or "Не удалось получить данные из выбранных файлов."
            QMessageBox.warning(self, "CSV не загружены", details)
            return
        # Aggregate equality is only a hint: two separate captures may coincide.
        # Keep one copy automatically, but ask before skipping any probable duplicate.
        seen: dict[tuple[object, ...], str] = {}
        for old_index, old_run in enumerate(self.benchmark_runs, start=1):
            fingerprint = benchmark_import_fingerprint(old_run)
            if fingerprint is not None:
                pin_label = " · эталон" if old_run.is_reference else ""
                seen.setdefault(fingerprint, f"запись истории #{old_index}{pin_label}: {old_run.name}")
        accepted: list[Benchmark] = []
        probable_duplicates: list[tuple[int, int, str, str]] = []
        for position, run in enumerate(imported):
            selected_index, filename = imported_names[position]
            fingerprint = benchmark_import_fingerprint(run)
            prior = seen.get(fingerprint) if fingerprint is not None else None
            if prior is not None:
                probable_duplicates.append((position, selected_index, filename, prior))
                continue
            accepted.append(run)
            if fingerprint is not None:
                seen[fingerprint] = f"выбранный CSV #{selected_index}: {filename}"
        keep_duplicates: set[int] = set()
        if probable_duplicates:
            dialog = ProbableDuplicateDialog(probable_duplicates, len(imported), self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            keep_duplicates = dialog.positions_to_keep()
            duplicate_positions = {position for position, _, _, _ in probable_duplicates}
            accepted = [run for position, run in enumerate(imported) if position not in duplicate_positions or position in keep_duplicates]
        if not accepted:
            details = ["Все корректные CSV отмечены как возможные дубликаты и пропущены; история не изменена."]
            if file_errors:
                details.append("Не импортировано из-за ошибок:\n" + "\n".join(file_errors[:10]))
                if len(file_errors) > 10:
                    details.append(f"… и ещё {len(file_errors) - 10} файлов с ошибками")
            if file_warnings:
                details.append("Предупреждения импорта:\n" + "\n".join(file_warnings[:12]))
                if len(file_warnings) > 12:
                    details.append(f"… и ещё {len(file_warnings) - 12} предупреждений")
            QMessageBox.information(self, "Новые CSV не добавлены", "\n\n".join(details))
            return
        try:
            updated_runs = retain_benchmark_runs(self.benchmark_runs + accepted)
        except ValueError as exc:
            QMessageBox.warning(self, "Не удалось обновить историю", str(exc))
            return
        try:
            self.benchmark_store.save(updated_runs)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Замеры не сохранены", f"Ни один новый результат не добавлен в историю. Предыдущая история сохранена.\n{exc}")
            return
        self.benchmark_runs = updated_runs
        retained_ids = {id(run) for run in updated_runs}
        self._benchmark_group_a.intersection_update(retained_ids)
        self._benchmark_group_b.intersection_update(retained_ids)
        self.benchmark_history_filter.clear()
        self.benchmark_change_note.clear()
        self.benchmark_include_setting.setChecked(False)
        self._refresh_benchmark_checklist()
        self._refresh_benchmark_history()
        notices = []
        if probable_duplicates:
            skipped = len(probable_duplicates) - len(keep_duplicates)
            notices.append(
                f"Возможные дубликаты: добавлено несмотря на предупреждение — {len(keep_duplicates)}; пропущено — {skipped}. "
                "Решение принято только по совпадению сводных метрик."
            )
        if file_errors:
            error_lines = file_errors[:10]
            if len(file_errors) > 10:
                error_lines.append(f"… и ещё {len(file_errors) - 10} файлов с ошибками")
            notices.append(f"Не импортировано ({len(file_errors)}):\n" + "\n".join(error_lines))
        if file_warnings:
            warning_lines = file_warnings[:12]
            if len(file_warnings) > 12:
                warning_lines.append(f"… и ещё {len(file_warnings) - 12} предупреждений")
            notices.append("Предупреждения импорта:\n" + "\n".join(warning_lines))
        if notices:
            QMessageBox.information(self, f"Импортировано {len(accepted)} из {len(paths)} CSV", "\n\n".join(notices))
        if len(self.benchmark_runs) >= 2:
            self.benchmark_before.setCurrentIndex(len(self.benchmark_runs) - 2)
            self.benchmark_after.setCurrentIndex(len(self.benchmark_runs) - 1)
            self.compare_benchmark_selection(record_recent=False)

    def _refresh_benchmark_history(self):
        self.benchmark_list.clear()
        for index, run in enumerate(self.benchmark_runs):
            label = " · ".join(part for part in (run.game or "Игра не указана", run.scene or "сцена не указана") if part)
            note = f" · изменение: {run.change_note}" if run.change_note else ""
            setting = f" · {run.setting_key}={run.setting_value}" if run.setting_key else ""
            manual = ", ".join(GUIDE_CHECKLIST_LABELS.get(item, item) for item in run.manual_changes)
            manual = f" · чек-лист: {manual}" if manual else ""
            group_tag = "A · " if id(run) in self._benchmark_group_a else "B · " if id(run) in self._benchmark_group_b else ""
            reference_tag = "★ ЭТАЛОН · " if run.is_reference else ""
            if run is self._active_benchmark_baseline:
                reference_tag = "★ АКТИВНАЯ БАЗА · " + reference_tag
            item = QListWidgetItem(f"[{reference_tag}{group_tag or '—'}] {run.name} · {METRIC_LABELS.get(run.metric_kind, run.metric_kind)} · {label}{note}{setting}{manual} · {run.sample_count:,} кадров · {run.average_fps:.1f} avg FPS · {run.one_percent_low_fps:.1f} 1% low")
            item.setData(Qt.ItemDataRole.UserRole, index)
            self.benchmark_list.addItem(item)
        if hasattr(self, "benchmark_groups_status"):
            self.benchmark_groups_status.setText(f"Группа A: {len(self._benchmark_group_a)} · Группа B: {len(self._benchmark_group_b)}")
        self._update_reference_controls()
        self._filter_benchmark_history(self.benchmark_history_filter.text())
        if not hasattr(self, "benchmark_before"):
            return
        previous_before = self.benchmark_before.currentData()
        previous_after = self.benchmark_after.currentData()
        for selector in (self.benchmark_before, self.benchmark_after):
            selector.blockSignals(True)
            selector.clear()
            for index, run in enumerate(self.benchmark_runs):
                setting = f"{run.setting_key}={run.setting_value}" if run.setting_key else ""
                manual = ", ".join(GUIDE_CHECKLIST_LABELS.get(item, item) for item in run.manual_changes)
                label = " · ".join(part for part in (("★ ЭТАЛОН" if run.is_reference else ""), run.name, METRIC_LABELS.get(run.metric_kind, run.metric_kind), run.game or "Игра не указана", run.scene or "", run.change_note, setting, manual) if part)
                selector.addItem(label, index)
            selector.blockSignals(False)
        if self.benchmark_runs:
            self.benchmark_before.setCurrentIndex(previous_before if isinstance(previous_before, int) and previous_before < len(self.benchmark_runs) else 0)
            self.benchmark_after.setCurrentIndex(previous_after if isinstance(previous_after, int) and previous_after < len(self.benchmark_runs) else len(self.benchmark_runs) - 1)
        self._refresh_benchmark_pair_identities()
        if hasattr(self, "benchmark_pair_search"):
            self._search_benchmark_pairs(self.benchmark_pair_search.text())
        self._refresh_recent_benchmark_pairs()

    def _refresh_benchmark_pair_identities(self):
        if not hasattr(self, "benchmark_before_identity"):
            return
        for selector, label, side in (
            (self.benchmark_before, self.benchmark_before_identity, "Baseline (A)"),
            (self.benchmark_after, self.benchmark_after_identity, "Variant (B)"),
        ):
            index = selector.currentData(Qt.ItemDataRole.UserRole)
            if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(self.benchmark_runs):
                status = f"{side}: нет выбранного замера"
                label.setText(status)
                selector.setAccessibleName(status)
                selector.setAccessibleDescription("")
                continue
            run = self.benchmark_runs[index]
            identity = " · ".join(("★ ЭТАЛОН" if run.is_reference else "", run.name, METRIC_LABELS.get(run.metric_kind, run.metric_kind), run.game or "Игра не указана", run.scene or "сцена не указана"))
            description = f"{side} #{index + 1:03d}: {identity}"
            label.setText(description)
            selector.setAccessibleName(f"{side}: {run.name}")
            selector.setAccessibleDescription(description)
        self._update_swap_benchmark_pair_button()

    def _update_swap_benchmark_pair_button(self):
        if not hasattr(self, "swap_benchmark_pair_button"):
            return
        before_index = self.benchmark_before.currentData()
        after_index = self.benchmark_after.currentData()
        valid = all(
            not isinstance(index, bool) and isinstance(index, int) and 0 <= index < len(self.benchmark_runs)
            for index in (before_index, after_index)
        )
        self.swap_benchmark_pair_button.setEnabled(valid and before_index != after_index)

    def _search_benchmark_pairs(self, query: str):
        if not hasattr(self, "benchmark_pair_search_results"):
            return
        results = self.benchmark_pair_search_results
        results.clear()
        needle = query.strip().casefold()
        if not needle:
            self.benchmark_pair_search_status.setText("Начни вводить, чтобы найти замер. Поиск не меняет выбранную пару.")
            self._update_pair_assignment_buttons()
            return
        for index in matching_benchmark_indices(self.benchmark_runs, needle):
            run = self.benchmark_runs[index]
            setting = f" · {run.setting_key}={run.setting_value}" if run.setting_key else ""
            item = QListWidgetItem(
                f"#{index + 1:03d} · {'★ ЭТАЛОН · ' if run.is_reference else ''}{run.name} · {METRIC_LABELS.get(run.metric_kind, run.metric_kind)} · "
                f"{run.game or 'Игра не указана'} · {run.scene or 'сцена не указана'}{setting}"
            )
            item.setData(Qt.ItemDataRole.UserRole, index)
            results.addItem(item)
        count = results.count()
        self.benchmark_pair_search_status.setText(
            f"Найдено: {count}. Выбери строку и назначь её в A или B; поиск сам пару не меняет."
            if count else "Ничего не найдено. Текущая пара A/B не изменена."
        )
        self._update_pair_assignment_buttons()

    def _selected_pair_search_index(self) -> int | None:
        items = self.benchmark_pair_search_results.selectedItems()
        if not items:
            return None
        index = items[0].data(Qt.ItemDataRole.UserRole)
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(self.benchmark_runs):
            return None
        return index

    def _update_pair_assignment_buttons(self, *_args):
        if not hasattr(self, "assign_pair_search_baseline"):
            return
        enabled = self._selected_pair_search_index() is not None
        self.assign_pair_search_baseline.setEnabled(enabled)
        self.assign_pair_search_variant.setEnabled(enabled)

    def _assign_pair_search_result(self, selector: QComboBox):
        index = self._selected_pair_search_index()
        if index is None:
            self._update_pair_assignment_buttons()
            return
        if index >= selector.count() or selector.itemData(index, Qt.ItemDataRole.UserRole) != index:
            self.benchmark_pair_search_status.setText("Не удалось назначить замер: обнови список истории и повтори.")
            return
        selector.setCurrentIndex(index)
        if selector.currentData(Qt.ItemDataRole.UserRole) != index:
            self.benchmark_pair_search_status.setText("Не удалось назначить замер: обнови список истории и повтори.")
            return
        self.benchmark_pair_search_status.setText(
            f"Назначен замер #{index + 1:03d} как {'Baseline (A)' if selector is self.benchmark_before else 'Variant (B)'}."
        )
        self._refresh_benchmark_pair_identities()

    def _assign_pair_search_result_to_baseline(self, *_args):
        self._assign_pair_search_result(self.benchmark_before)

    def _assign_pair_search_result_to_variant(self, *_args):
        self._assign_pair_search_result(self.benchmark_after)

    def _benchmark_pair_selection_changed(self, *_args):
        self._refresh_benchmark_pair_identities()
        comparison = self._last_benchmark_comparison
        if comparison is None or comparison[0] != "pair":
            return
        self._last_benchmark_comparison = None
        if hasattr(self, "export_benchmark_button"):
            self.export_benchmark_button.setEnabled(False)
        if hasattr(self, "copy_benchmark_report_button"):
            self.copy_benchmark_report_button.setEnabled(False)
        if hasattr(self, "benchmark_report"):
            self.benchmark_report.setPlainText("Пара A/B изменена. Нажми «Сравнить», чтобы обновить отчёт и экспорт.")
        if hasattr(self, "benchmark_chart"):
            self.benchmark_chart.hide()
            self.benchmark_chart_title.hide()
            self.benchmark_chart_note.hide()

    def swap_benchmark_pair(self, *_args):
        before_index = self.benchmark_before.currentData()
        after_index = self.benchmark_after.currentData()
        if (
            isinstance(before_index, bool) or not isinstance(before_index, int)
            or isinstance(after_index, bool) or not isinstance(after_index, int)
            or not 0 <= before_index < len(self.benchmark_runs)
            or not 0 <= after_index < len(self.benchmark_runs)
            or before_index == after_index
        ):
            return
        before_signals = self.benchmark_before.blockSignals(True)
        after_signals = self.benchmark_after.blockSignals(True)
        try:
            new_before = self.benchmark_before.findData(after_index)
            new_after = self.benchmark_after.findData(before_index)
            if new_before < 0 or new_after < 0:
                return
            self.benchmark_before.setCurrentIndex(new_before)
            self.benchmark_after.setCurrentIndex(new_after)
        finally:
            self.benchmark_before.blockSignals(before_signals)
            self.benchmark_after.blockSignals(after_signals)
        self._refresh_benchmark_pair_identities()
        self._last_benchmark_comparison = None
        self.export_benchmark_button.setEnabled(False)
        self.copy_benchmark_report_button.setEnabled(False)
        self.benchmark_chart.hide()
        self.benchmark_chart_title.hide()
        self.benchmark_chart_note.hide()
        self.benchmark_report.setPlainText("Поля A/B поменялись местами. Нажми «Сравнить», чтобы построить новый отчёт и экспорт.")

    def _filter_benchmark_history(self, query: str):
        if not hasattr(self, "benchmark_list") or not hasattr(self, "benchmark_history_count"):
            return
        self.benchmark_list.clearSelection()
        needle = query.strip().casefold()
        visible_count = 0
        visible_run_ids = set()
        for row in range(self.benchmark_list.count()):
            item = self.benchmark_list.item(row)
            index = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(index, int) or not 0 <= index < len(self.benchmark_runs):
                item.setHidden(bool(needle))
                visible_count += not bool(needle)
                continue
            run = self.benchmark_runs[index]
            checklist = " ".join(GUIDE_CHECKLIST_LABELS.get(key, key) for key in run.manual_changes)
            searchable = " ".join((
                "эталон" if run.is_reference else "",
                run.name,
                run.game,
                run.scene,
                METRIC_LABELS.get(run.metric_kind, run.metric_kind),
                run.change_note,
                run.setting_key,
                str(run.setting_value) if run.setting_value is not None else "",
                checklist,
            )).casefold()
            hidden = bool(needle) and needle not in searchable
            item.setHidden(hidden)
            visible_count += not hidden
            if not hidden:
                visible_run_ids.add(id(run))
        self.benchmark_history_count.setText(f"{visible_count} из {self.benchmark_list.count()} · выделение сбрасывается, группы сохраняются")
        if hasattr(self, "benchmark_groups_status"):
            hidden_a = len(self._benchmark_group_a - visible_run_ids)
            hidden_b = len(self._benchmark_group_b - visible_run_ids)
            self.benchmark_groups_status.setText(
                f"Группа A: {len(self._benchmark_group_a)} (вне фильтра: {hidden_a}) · "
                f"Группа B: {len(self._benchmark_group_b)} (вне фильтра: {hidden_b})"
            )

    def _refresh_benchmark_checklist(self, *_args):
        self.benchmark_changes.clear()
        game = self.benchmark_game.currentData()
        checklist = GUIDE_CHECKLISTS.get(game, ())
        for item_id, label in checklist:
            item = QListWidgetItem(label, self.benchmark_changes)
            item.setData(Qt.ItemDataRole.UserRole, item_id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
        if checklist:
            hint = "Отмечай параметры, которые вручную менял между прогонами. Это контекст для сравнения, а не вывод о причине разницы FPS."
        elif game == "The Elder Scrolls V: Skyrim Special Edition":
            hint = "Для Skyrim можно включить снимок разрешённой настройки INI выше."
        else:
            hint = "Выбери игру, чтобы увидеть её чек-лист."
        self.benchmark_checklist_hint.setText(hint)

    def compare_benchmark_selection(self, *_args, record_recent: bool = True):
        selection = self._selected_benchmark_pair()
        if selection is None:
            return
        before, after = selection
        self.benchmark_report.setPlainText(compare_benchmarks(before, after, self.benchmark_frame_budget.currentData()))
        self.benchmark_chart.set_runs(before, after)
        self.benchmark_chart_title.show()
        self.benchmark_chart.show()
        self.benchmark_chart_note.show()
        self._last_benchmark_comparison = ("pair", before, after)
        self.export_benchmark_button.setEnabled(True)
        self.copy_benchmark_report_button.setEnabled(True)
        if record_recent:
            self._remember_recent_benchmark_pair(before, after)

    def _toggle_recent_pairs(self, expanded: bool):
        self.recent_pairs_list.setVisible(expanded)
        self.recent_pairs_toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self.recent_pairs_toggle.setAccessibleName(
            "Скрыть недавние сравнения этой сессии" if expanded else "Показать недавние сравнения этой сессии"
        )

    def _recent_run_index(self, target: Benchmark) -> int | None:
        return next((index for index, run in enumerate(self.benchmark_runs) if run is target), None)

    def _refresh_recent_benchmark_pairs(self):
        if not hasattr(self, "recent_pairs_list"):
            return
        self.recent_pairs_list.clear()
        for pair_index, (before, after) in enumerate(self._recent_benchmark_pairs):
            before_index = self._recent_run_index(before)
            after_index = self._recent_run_index(after)
            before_label = f"A #{before_index + 1:03d}" if before_index is not None else "A [нет в истории]"
            after_label = f"B #{after_index + 1:03d}" if after_index is not None else "B [нет в истории]"
            item = QListWidgetItem(f"{before_label} {before.name} → {after_label} {after.name}")
            item.setData(Qt.ItemDataRole.UserRole, pair_index)
            if before_index is None or after_index is None:
                item.setText(f"Недоступна · {item.text()}")
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                item.setToolTip("Один из прогонов больше не находится в истории.")
            else:
                item.setToolTip("Подставить эту пару в A/B; отчёт потребуется построить заново.")
            self.recent_pairs_list.addItem(item)
        can_show = len(self.benchmark_runs) >= 2 and bool(self._recent_benchmark_pairs)
        self.recent_pairs_toggle.setVisible(can_show)
        self.recent_pairs_toggle.setEnabled(can_show)
        self.recent_pairs_toggle.setText(f"Недавние сравнения (сессия) · {len(self._recent_benchmark_pairs)}")
        if not can_show and self.recent_pairs_toggle.isChecked():
            self.recent_pairs_toggle.setChecked(False)

    def _remember_recent_benchmark_pair(self, before: Benchmark, after: Benchmark):
        pair = (before, after)
        self._recent_benchmark_pairs = [
            existing for existing in self._recent_benchmark_pairs
            if self._recent_run_index(existing[0]) is not None and self._recent_run_index(existing[1]) is not None
            and not (existing[0] is before and existing[1] is after)
        ]
        self._recent_benchmark_pairs.insert(0, pair)
        self._recent_benchmark_pairs = self._recent_benchmark_pairs[:10]
        self._refresh_recent_benchmark_pairs()

    def _restore_recent_pair(self, item: QListWidgetItem):
        pair_index = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(pair_index, bool) or not isinstance(pair_index, int) or not 0 <= pair_index < len(self._recent_benchmark_pairs):
            return
        before, after = self._recent_benchmark_pairs[pair_index]
        before_index = self._recent_run_index(before)
        after_index = self._recent_run_index(after)
        if before_index is None or after_index is None or before_index == after_index:
            self.benchmark_pair_search_status.setText("Эта пара больше недоступна в истории.")
            self._refresh_recent_benchmark_pairs()
            return
        self.benchmark_before.blockSignals(True)
        self.benchmark_after.blockSignals(True)
        try:
            self.benchmark_before.setCurrentIndex(before_index)
            self.benchmark_after.setCurrentIndex(after_index)
        finally:
            self.benchmark_before.blockSignals(False)
            self.benchmark_after.blockSignals(False)
        self._last_benchmark_comparison = None
        self.export_benchmark_button.setEnabled(False)
        self.copy_benchmark_report_button.setEnabled(False)
        self.benchmark_report.setPlainText("Недавняя пара подставлена. Нажми «Сравнить», чтобы построить новый отчёт и экспорт.")
        self.benchmark_chart.hide()
        self.benchmark_chart_title.hide()
        self.benchmark_chart_note.hide()
        self.benchmark_pair_search_status.setText("Пара из недавних сравнений подставлена; отчёт ещё не построен.")
        self._refresh_benchmark_pair_identities()

    def _selected_benchmark_runs(self) -> list[Benchmark]:
        indexes = sorted({item.data(Qt.ItemDataRole.UserRole) for item in self.benchmark_list.selectedItems()})
        return [self.benchmark_runs[index] for index in indexes if isinstance(index, int) and 0 <= index < len(self.benchmark_runs)]

    def _show_benchmark_context_menu(self, position):
        item = self.benchmark_list.itemAt(position)
        if item is None:
            return
        index = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(self.benchmark_runs):
            return
        run = self.benchmark_runs[index]
        menu = QMenu(self)
        action = menu.addAction("Сравнить с предыдущим замером той же игры, сцены и метрики")
        action.setEnabled(bool(run.game.strip() and run.scene.strip()))
        action.triggered.connect(lambda _checked=False, run_index=index: self.compare_with_previous_matching_run(run_index))
        if not run.game.strip() or not run.scene.strip():
            action.setToolTip("Для поиска совпадения нужны заполненные метки игры и сцены.")
        menu.addSeparator()
        history_action = menu.addAction("Показать историю тех же игры, сцены и метрики")
        history_action.setEnabled(bool(run.game.strip() and run.scene.strip()))
        history_action.triggered.connect(lambda _checked=False, run_index=index: self.show_same_label_history(run_index))
        if not run.game.strip() or not run.scene.strip():
            history_action.setToolTip("Для поиска совпадений нужны заполненные метки игры и сцены.")
        menu.addSeparator()
        if run.is_reference:
            baseline_action = menu.addAction(
                "Снять активную базу" if run is self._active_benchmark_baseline else "Назначить активной базой на этот сеанс"
            )
            baseline_action.triggered.connect(lambda _checked=False, run_index=index: self.toggle_active_benchmark_baseline(run_index))
        menu.exec(self.benchmark_list.mapToGlobal(position))

    def toggle_active_benchmark_baseline(self, index: int) -> bool:
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(self.benchmark_runs):
            return False
        run = self.benchmark_runs[index]
        if not run.is_reference:
            return False
        selected = self.benchmark_list.selectedItems()
        selected_index = selected[0].data(Qt.ItemDataRole.UserRole) if len(selected) == 1 else None
        self._active_benchmark_baseline = None if self._active_benchmark_baseline is run else run
        self._refresh_benchmark_history()
        if isinstance(selected_index, int) and not isinstance(selected_index, bool) and selected_index < self.benchmark_list.count():
            self.benchmark_list.setCurrentRow(selected_index)
        self._update_reference_controls()
        return True

    def compare_selected_with_active_baseline(self) -> bool:
        selected = self.benchmark_list.selectedItems()
        baseline = self._active_benchmark_baseline
        if baseline is None or not baseline.is_reference or not any(run is baseline for run in self.benchmark_runs):
            self._active_benchmark_baseline = None
            self._update_reference_controls()
            return False
        if len(selected) != 1:
            return False
        index = selected[0].data(Qt.ItemDataRole.UserRole)
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(self.benchmark_runs):
            return False
        variant = self.benchmark_runs[index]
        if variant is baseline or variant.is_reference:
            return False
        baseline_index = next(position for position, run in enumerate(self.benchmark_runs) if run is baseline)
        self.benchmark_before.blockSignals(True)
        self.benchmark_after.blockSignals(True)
        try:
            self.benchmark_before.setCurrentIndex(baseline_index)
            self.benchmark_after.setCurrentIndex(index)
        finally:
            self.benchmark_before.blockSignals(False)
            self.benchmark_after.blockSignals(False)
        self._last_benchmark_comparison = None
        self.export_benchmark_button.setEnabled(False)
        self.copy_benchmark_report_button.setEnabled(False)
        self.benchmark_report.setPlainText("Пара с активной базой подставлена. Нажми «Сравнить», чтобы построить новый отчёт и экспорт.")
        self.benchmark_chart.hide()
        self.benchmark_chart_title.hide()
        self.benchmark_chart_note.hide()
        self.benchmark_pair_search_status.setText("Активная база и выбранный прогон подставлены; отчёт ещё не построен.")
        self._refresh_benchmark_pair_identities()
        return True

    def same_label_history_rows(self, index: int) -> list[tuple[int, Benchmark]]:
        """Return exact-label history rows without claiming capture chronology."""
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(self.benchmark_runs):
            return []
        current = self.benchmark_runs[index]
        if not current.game.strip() or not current.scene.strip():
            return []
        return [
            (history_index, run)
            for history_index, run in enumerate(self.benchmark_runs)
            if run.game == current.game and run.scene == current.scene and run.metric_kind == current.metric_kind
        ]

    def show_same_label_history(self, index: int) -> bool:
        rows = self.same_label_history_rows(index)
        if not rows:
            if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(self.benchmark_runs):
                QMessageBox.information(self, "Выбор устарел", "Эта запись больше недоступна в текущей истории. Выбери её заново.")
            else:
                QMessageBox.information(self, "Нет меток для поиска", "У выбранного замера должны быть заполнены метки игры и сцены. История не изменена.")
            return False
        current = self.benchmark_runs[index]
        if len(rows) == 1:
            QMessageBox.information(
                self, "История совпадающих прогонов",
                f"Для этой игры, сцены и метрики найден только один замер: {current.name}.\n"
                "Это не сравнение и не вывод о производительности.",
            )
            return True
        lines = [
            f"# истории\tИсточник\tСредний FPS\t1% low\tp99, мс\tFrame budget\tЭталон",
        ]
        target_fps = self.benchmark_frame_budget.currentData()
        for history_index, run in rows:
            budget = "нет данных"
            if run.frame_budget_counts is not None and isinstance(target_fps, int) and target_fps in FRAME_BUDGET_FPS_PRESETS:
                count = run.frame_budget_counts[FRAME_BUDGET_FPS_PRESETS.index(target_fps)]
                budget = f"{count / run.sample_count * 100:.1f}% при {target_fps} FPS" if run.sample_count else "нет данных"
            marker = " ← выбран" if history_index == index else ""
            reference = "да" if run.is_reference else "нет"
            lines.append(
                f"#{history_index + 1:03d}{marker}\t{run.name}\t{run.average_fps:.1f}\t{run.one_percent_low_fps:.1f}\t"
                f"{run.p99_frame_time_ms:.2f}\t{budget}\t{reference}"
            )
        screen = self.screen() or QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else None
        dialog = QDialog(self)
        dialog.setWindowTitle("Прогоны с совпадающими метками")
        dialog.resize(
            min(780, max(240, available.width() - 24)) if available else 780,
            min(420, max(180, available.height() - 24)) if available else 420,
        )
        dialog_layout = QVBoxLayout(dialog)
        title = QLabel(f"{current.game} · {current.scene} · {METRIC_LABELS.get(current.metric_kind, current.metric_kind)} · найдено {len(rows)}")
        title.setWordWrap(True)
        dialog_layout.addWidget(title)
        caveat = QLabel("Порядок — позиция в локальной истории, не время захвата; он не доказывает хронологию, тренд или причину различий. Список только для чтения.")
        caveat.setObjectName("muted")
        caveat.setWordWrap(True)
        dialog_layout.addWidget(caveat)
        table = QTextEdit()
        table.setReadOnly(True)
        table.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        table.setPlainText("\n".join(lines))
        dialog_layout.addWidget(table, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.clicked.connect(lambda _button: dialog.accept())
        dialog_layout.addWidget(buttons)
        dialog.exec()
        return True

    def show_selected_same_label_history(self):
        selected = self.benchmark_list.selectedItems()
        if len(selected) != 1:
            return
        self.show_same_label_history(selected[0].data(Qt.ItemDataRole.UserRole))

    def compare_with_previous_matching_run(self, index: int) -> bool:
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(self.benchmark_runs):
            return False
        current = self.benchmark_runs[index]
        if not current.game.strip() or not current.scene.strip():
            self.benchmark_pair_search_status.setText("Нужны заполненные метки игры и сцены; пара не изменена.")
            return False
        previous_index = next((
            candidate_index
            for candidate_index in range(index - 1, -1, -1)
            if self.benchmark_runs[candidate_index].game == current.game
            and self.benchmark_runs[candidate_index].scene == current.scene
            and self.benchmark_runs[candidate_index].metric_kind == current.metric_kind
        ), None)
        if previous_index is None:
            self.benchmark_pair_search_status.setText(
                f"Для #{index + 1:03d} не найден более ранний замер с той же игрой, сценой и метрикой; пара не изменена."
            )
            return False
        self.benchmark_before.blockSignals(True)
        self.benchmark_after.blockSignals(True)
        try:
            self.benchmark_before.setCurrentIndex(previous_index)
            self.benchmark_after.setCurrentIndex(index)
        finally:
            self.benchmark_before.blockSignals(False)
            self.benchmark_after.blockSignals(False)
        self._last_benchmark_comparison = None
        self.export_benchmark_button.setEnabled(False)
        self.copy_benchmark_report_button.setEnabled(False)
        self.benchmark_report.setPlainText("Пара A/B подобрана. Нажми «Сравнить», чтобы построить новый отчёт и экспорт.")
        self.benchmark_chart.hide()
        self.benchmark_chart_title.hide()
        self.benchmark_chart_note.hide()
        self.benchmark_pair_search_status.setText(
            f"Подобрана пара #{previous_index + 1:03d} → #{index + 1:03d}. Нажми «Сравнить», чтобы построить отчёт."
        )
        self._refresh_benchmark_pair_identities()
        return True

    def compare_selected_with_previous_matching_run(self):
        selected = self.benchmark_list.selectedItems()
        if len(selected) != 1:
            self.benchmark_pair_search_status.setText("Выбери один замер в истории, чтобы подобрать предыдущий.")
            return
        self.compare_with_previous_matching_run(selected[0].data(Qt.ItemDataRole.UserRole))

    def _assign_selected_benchmark_group(self, group: str):
        runs = self._selected_benchmark_runs()
        if not runs:
            QMessageBox.information(self, "Ничего не выбрано", "Выдели замеры в списке истории, используя Ctrl или Shift.")
            return
        target = self._benchmark_group_a if group == "A" else self._benchmark_group_b
        other = self._benchmark_group_b if group == "A" else self._benchmark_group_a
        for run in runs:
            other.discard(id(run))
            target.add(id(run))
        self._refresh_benchmark_history()

    def _remove_selected_benchmark_group(self):
        for run in self._selected_benchmark_runs():
            self._benchmark_group_a.discard(id(run))
            self._benchmark_group_b.discard(id(run))
        self._refresh_benchmark_history()

    def compare_benchmark_groups_selection(self):
        group_a = [run for run in self.benchmark_runs if id(run) in self._benchmark_group_a]
        group_b = [run for run in self.benchmark_runs if id(run) in self._benchmark_group_b]
        try:
            report = compare_benchmark_groups(group_a, group_b, self.benchmark_frame_budget.currentData())
        except ValueError as exc:
            QMessageBox.information(self, "Не удалось сравнить группы", str(exc))
            return
        self.benchmark_report.setPlainText(report)
        self.benchmark_chart.hide()
        self.benchmark_chart_title.hide()
        self.benchmark_chart_note.hide()
        self._last_benchmark_comparison = ("groups", group_a, group_b)
        self.export_benchmark_button.setEnabled(True)
        self.copy_benchmark_report_button.setEnabled(True)

    def copy_benchmark_report(self):
        if self._last_benchmark_comparison is None:
            return
        report = self.benchmark_report.toPlainText()
        if not report.strip():
            self.statusBar().showMessage("В отчёте нет текста для копирования.", 5000)
            return
        QApplication.clipboard().setText(report)
        self.statusBar().showMessage("Текст видимого отчёта скопирован в буфер обмена.", 5000)

    def _refresh_benchmark_budget(self, *_args):
        comparison = self._last_benchmark_comparison
        if comparison is None or not hasattr(self, "benchmark_frame_budget"):
            return
        target_fps = self.benchmark_frame_budget.currentData()
        if comparison[0] == "pair":
            _kind, before, after = comparison
            self.benchmark_report.setPlainText(compare_benchmarks(before, after, target_fps))
        else:
            _kind, group_a, group_b = comparison
            self.benchmark_report.setPlainText(compare_benchmark_groups(group_a, group_b, target_fps))

    def _selected_benchmark_pair(self) -> tuple[Benchmark, Benchmark] | None:
        if self.benchmark_before.count() < 2 or self.benchmark_after.count() < 2:
            QMessageBox.information(self, "Нужны два замера", "Импортируй два CSV-файла для сравнения.")
            return None
        before_index = self.benchmark_before.currentData()
        after_index = self.benchmark_after.currentData()
        if (
            isinstance(before_index, bool) or not isinstance(before_index, int)
            or isinstance(after_index, bool) or not isinstance(after_index, int)
            or not 0 <= before_index < len(self.benchmark_runs)
            or not 0 <= after_index < len(self.benchmark_runs)
        ):
            QMessageBox.information(self, "Выбор устарел", "Обнови список замеров и выбери Baseline и Variant заново.")
            return None
        if before_index == after_index:
            QMessageBox.information(self, "Выбраны одинаковые замеры", "Для сравнения выбери два разных результата.")
            return None
        return self.benchmark_runs[before_index], self.benchmark_runs[after_index]

    def export_benchmark_selection(self):
        comparison = self._last_benchmark_comparison
        if comparison is None:
            selection = self._selected_benchmark_pair()
            if selection is None:
                return
            comparison = ("pair", *selection)
        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Экспорт сводки сравнения",
            "FrameForge-comparison.csv",
            "CSV summary (*.csv);;JSON summary (*.json)",
        )
        if not path:
            return
        target = Path(path)
        want_json = "JSON" in selected_filter or target.suffix.casefold() == ".json"
        expected_suffix = ".json" if want_json else ".csv"
        if target.suffix.casefold() != expected_suffix:
            target = target.with_suffix(expected_suffix)
        try:
            if comparison[0] == "groups":
                _kind, group_a, group_b = comparison
                payload = export_group_comparison_json(group_a, group_b, self.benchmark_frame_budget.currentData()) if want_json else export_group_comparison_csv(group_a, group_b, self.benchmark_frame_budget.currentData())
            else:
                _kind, before, after = comparison
                payload = export_comparison_json(before, after, self.benchmark_frame_budget.currentData()) if want_json else export_comparison_csv(before, after, self.benchmark_frame_budget.currentData())
            target.write_text(payload, encoding="utf-8-sig" if not want_json else "utf-8", newline="")
        except OSError as exc:
            QMessageBox.critical(self, "Не удалось экспортировать", f"Сводка не сохранена.\n{exc}")
            return
        QMessageBox.information(
            self,
            "Сводка экспортирована",
            f"Сохранён агрегированный отчёт:\n{target}\n\nВ нём нет исходных путей и кадров CSV.",
        )

    def _update_reference_controls(self, *_args):
        if not hasattr(self, "toggle_reference_button"):
            return
        reference_count = sum(run.is_reference for run in self.benchmark_runs)
        self.reference_status.setText(
            f"Эталоны: {reference_count}/{MAX_REFERENCE_RUNS} · закреплённые прогоны не вытесняются импортом"
        )
        selected = self.benchmark_list.selectedItems()
        if hasattr(self, "compare_previous_matching_button"):
            self.compare_previous_matching_button.setEnabled(len(selected) == 1)
        if hasattr(self, "same_label_history_button"):
            self.same_label_history_button.setEnabled(len(selected) == 1)
        baseline = self._active_benchmark_baseline
        if baseline is not None and (not baseline.is_reference or not any(run is baseline for run in self.benchmark_runs)):
            self._active_benchmark_baseline = None
            baseline = None
        if hasattr(self, "compare_active_baseline_button"):
            self.compare_active_baseline_button.setVisible(baseline is not None)
            can_compare = False
            same_baseline = False
            if len(selected) == 1:
                selected_index = selected[0].data(Qt.ItemDataRole.UserRole)
                if isinstance(selected_index, int) and not isinstance(selected_index, bool) and 0 <= selected_index < len(self.benchmark_runs):
                    selected_run = self.benchmark_runs[selected_index]
                    same_baseline = selected_run is baseline
                    can_compare = baseline is not None and not same_baseline and not selected_run.is_reference
            self.compare_active_baseline_button.setEnabled(can_compare)
            self.compare_active_baseline_button.setToolTip(
                "Выбранный прогон уже является активной базой." if same_baseline else
                "Выбери один обычный прогон; активная база подставится в A." if baseline is not None else
                "Назначь закреплённый прогон активной базой через контекстное меню."
            )
        if len(selected) != 1:
            self.toggle_reference_button.setEnabled(False)
            self.toggle_reference_button.setText("Выбери один замер для эталона")
            return
        index = selected[0].data(Qt.ItemDataRole.UserRole)
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(self.benchmark_runs):
            self.toggle_reference_button.setEnabled(False)
            self.toggle_reference_button.setText("Выбранный замер недоступен")
            return
        run = self.benchmark_runs[index]
        self.toggle_reference_button.setEnabled(run.is_reference or reference_count < MAX_REFERENCE_RUNS)
        self.toggle_reference_button.setText(
            "Снять эталон с выбранного замера" if run.is_reference else "Закрепить выбранный как эталон"
        )

    def toggle_selected_reference(self):
        selected = self.benchmark_list.selectedItems()
        if len(selected) != 1:
            self._update_reference_controls()
            return
        index = selected[0].data(Qt.ItemDataRole.UserRole)
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(self.benchmark_runs):
            QMessageBox.information(self, "Замер недоступен", "Обнови список истории и выбери замер снова.")
            return
        old_run = self.benchmark_runs[index]
        previous_pair_runs = []
        for selector in (self.benchmark_before, self.benchmark_after):
            selected_index = selector.currentData(Qt.ItemDataRole.UserRole)
            previous_pair_runs.append(
                self.benchmark_runs[selected_index]
                if isinstance(selected_index, int) and not isinstance(selected_index, bool) and 0 <= selected_index < len(self.benchmark_runs)
                else None
            )
        pinning = not old_run.is_reference
        if pinning and sum(run.is_reference for run in self.benchmark_runs) >= MAX_REFERENCE_RUNS:
            QMessageBox.information(self, "Лимит эталонов", f"Можно закрепить не больше {MAX_REFERENCE_RUNS} замеров. Сними один эталон и повтори.")
            return
        if not pinning and sum(not run.is_reference for run in self.benchmark_runs) >= MAX_HISTORY:
            oldest_ordinary = next((run for run in self.benchmark_runs if not run.is_reference), None)
            if oldest_ordinary is old_run:
                message = "Этот эталон — самый старый замер. После снятия эталона он сразу будет удалён, чтобы сохранить лимит в 100 обычных записей. Продолжить?"
            else:
                message = "После снятия эталона обычных замеров станет больше 100. Самый старый обычный замер будет удалён из локальной истории. Продолжить?"
            answer = QMessageBox.question(
                self,
                "История заполнена",
                message,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        new_run = replace(old_run, is_reference=pinning)
        updated = list(self.benchmark_runs)
        updated[index] = new_run
        try:
            updated = retain_benchmark_runs(updated)
            self.benchmark_store.save(updated)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Эталон не сохранён", f"История не изменена.\n{exc}")
            return
        old_id, new_id = id(old_run), id(new_run)
        for group in (self._benchmark_group_a, self._benchmark_group_b):
            if old_id in group:
                group.remove(old_id)
                if any(run is new_run for run in updated):
                    group.add(new_id)
        self.benchmark_runs = updated
        if not pinning and self._active_benchmark_baseline is old_run:
            self._active_benchmark_baseline = None
        self._recent_benchmark_pairs = [
            (new_run if before is old_run else before, new_run if after is old_run else after)
            for before, after in self._recent_benchmark_pairs
        ]
        retained_ids = {id(run) for run in updated}
        self._benchmark_group_a.intersection_update(retained_ids)
        self._benchmark_group_b.intersection_update(retained_ids)
        self._last_benchmark_comparison = None
        if hasattr(self, "export_benchmark_button"):
            self.export_benchmark_button.setEnabled(False)
        if hasattr(self, "copy_benchmark_report_button"):
            self.copy_benchmark_report_button.setEnabled(False)
        if hasattr(self, "benchmark_report"):
            self.benchmark_report.setPlainText("Эталон истории обновлён. Выбери пару A/B и сравни её заново.")
        if hasattr(self, "benchmark_chart"):
            self.benchmark_chart.hide()
            self.benchmark_chart_title.hide()
            self.benchmark_chart_note.hide()
        self._refresh_benchmark_history()
        for selector, previous_run, fallback in zip(
            (self.benchmark_before, self.benchmark_after),
            previous_pair_runs,
            (0, max(0, len(self.benchmark_runs) - 1)),
        ):
            target_run = new_run if previous_run is old_run else previous_run
            target_index = next((position for position, run in enumerate(self.benchmark_runs) if run is target_run), None)
            if target_index is not None:
                selector.setCurrentIndex(target_index)
            elif self.benchmark_runs:
                selector.setCurrentIndex(fallback)
        if self.benchmark_list.count() > index and any(run is new_run for run in self.benchmark_runs):
            self.benchmark_list.setCurrentRow(index)
    def _backups_page(self):
        scroll, layout = self._scroll_page()
        layout.addWidget(QLabel("Локальные снимки исходных файлов"))
        note = QLabel("Копии хранятся в %LOCALAPPDATA%\\FrameForge\\backups. Путь к пользовательскому файлу остаётся на этом компьютере.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.backup_list = QListWidget()
        layout.addWidget(self.backup_list)
        self.refresh_backups_button = QPushButton("Обновить список")
        self.refresh_backups_button.clicked.connect(self.refresh_backups)
        layout.addWidget(self.refresh_backups_button)
        restore = QPushButton("Восстановить выбранную копию")
        restore.setObjectName("danger")
        restore.clicked.connect(self.restore_selected)
        layout.addWidget(restore)
        self.refresh_backups()
        return scroll

    def show_page(self, index: int):
        self.stack.setCurrentIndex(index)
        titles = ["Обзор", "Каталог игр", "Бенчмарк", "Оптимизатор", "Резервные копии"]
        self.page_title.setText(titles[index])
        for i, button in enumerate(self.nav):
            button.setChecked(i == index)

    def choose_skyrim_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выбери Documents\\My Games\\Skyrim Special Edition")
        if not folder:
            return
        self.game_folder = Path(folder)
        self.on_profile_changed()
        if not self.config_path:
            profile = TUNING_PROFILES[self.profile_select.currentIndex()]
            QMessageBox.warning(self, "Файл профиля не найден", f"В этой папке нет {profile.config_name}. Выбери другой профиль или папку настроек.")

    def scan_preview(self):
        if not self.config_path:
            QMessageBox.information(self, "FrameForge", "Сначала выбери каталог Skyrim Special Edition.")
            return
        try:
            value, original = read_profile_setting(self.config_path)
            target = int(self.value_select.currentText())
            updated = build_profile_bytes(original, target, self.config_path.name)
            self.original = original
            self.preview_bytes = updated
            self.current_value.setText(f"Текущее: {value}")
            self.diff_box.setPlainText(make_diff(original, updated) or "Выбрано текущее значение; изменений нет.")
        except (SafetyError, OSError, ValueError) as exc:
            self.original = self.preview_bytes = None
            self.diff_box.setPlainText(f"Сканирование остановлено: {exc}")
            QMessageBox.warning(self, "Сканирование остановлено", str(exc))

    def _index_path(self):
        return app_data_dir() / "backup-index.json"

    def _read_index(self):
        try:
            return json.loads(self._index_path().read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []

    def _write_index(self, rows):
        import tempfile
        path = self._index_path()
        fd, temporary = tempfile.mkstemp(prefix=".backup-index-", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(rows[:100], stream, indent=2, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise

    def apply_preview(self):
        if not self.config_path or self.original is None or self.preview_bytes is None:
            QMessageBox.information(self, "FrameForge", "Сначала проверь файл и изучи diff.")
            return
        try:
            _, current_bytes = read_profile_setting(self.config_path)
        except (SafetyError, OSError, ValueError) as exc:
            QMessageBox.warning(self, "Нужно просканировать заново", str(exc))
            return
        if current_bytes != self.original:
            QMessageBox.warning(self, "Файл изменился", f"{self.config_path.name} изменился после сканирования. Проверь его снова и сравни новый diff.")
            self.scan_preview()
            return
        target = int(self.value_select.currentText())
        profile = TUNING_PROFILES[self.profile_select.currentIndex()]
        visible_effect = "Вся трава будет отключена." if profile.config_name == "Skyrim.ini" and target == 0 else "Внешний вид изменится согласно выбранному профилю."
        answer = QMessageBox.question(self, "Подтвердить настройку", f"Будет сохранена точная резервная копия. Изменится только существующая строка [{profile.section}] {profile.setting}: {target}. {visible_effect} Игра должна быть закрыта. Применить?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            backup, applied_sha256 = apply_profile_setting(self.config_path, target, app_data_dir() / "backups", expected_original=self.original)
            rows = self._read_index()
            backup_hash = sha256(backup.read_bytes())
            rows.insert(0, {
                "backup": str(backup),
                "config": str(self.config_path),
                "sha256": backup_hash,
                "expected_current_sha256": applied_sha256,
                "created": datetime.now().isoformat(timespec="seconds"),
            })
            try:
                self._write_index(rows)
            except (OSError, TypeError, ValueError) as index_error:
                try:
                    restore_from_backup(
                        backup,
                        self.config_path,
                        expected_sha256=backup_hash,
                        expected_current_sha256=applied_sha256,
                    )
                except (SafetyError, OSError, ValueError) as restore_error:
                    QMessageBox.critical(
                        self,
                        "Настройка применена, журнал не сохранён",
                        f"Не удалось сохранить список backup и автоматически восстановить исходный INI. "
                        f"Проверь файл и сохранившуюся копию вручную:\n{backup}\n\n{index_error}\n{restore_error}",
                    )
                else:
                    QMessageBox.critical(
                        self,
                        "Настройка отменена",
                        f"Журнал backup не удалось сохранить; исходный INI восстановлен.\n{index_error}",
                    )
                return
            self.last_backup, self.backup_config = backup, self.config_path
            self.last_backup_sha256, self.last_current_sha256 = backup_hash, applied_sha256
            self.refresh_backups()
            self.scan_preview()
            QMessageBox.information(self, "Профиль применён", f"Резервная копия проверена.\n{backup.name}")
        except (SafetyError, OSError, ValueError, RuntimeError) as exc:
            QMessageBox.critical(self, "Не удалось применить", str(exc))

    def refresh_backups(self):
        if not hasattr(self, "backup_list"):
            return
        self.backup_list.clear()
        self.backup_rows = []
        for row in self._read_index():
            backup = Path(row.get("backup", ""))
            config = Path(row.get("config", ""))
            if backup.is_file():
                self.backup_rows.append(row)
                self.backup_list.addItem(f"{row.get('created', '')} · {backup.name} · {config}")

    def restore_last(self):
        if self.last_backup and self.backup_config == self.config_path and self.last_backup_sha256:
            self._restore(self.last_backup, self.config_path, self.last_backup_sha256, self.last_current_sha256)
            return
        self.refresh_backups()
        if self.backup_list.count() == 0:
            QMessageBox.information(self, "Нет копий", "Для Skyrim пока нет резервных копий.")
            return
        self.show_page(4)
        QMessageBox.information(self, "Выбери копию", "Выбери нужную копию в разделе «Резервные копии» и нажми восстановить.")

    def restore_selected(self):
        selected = self.backup_list.currentRow()
        if selected < 0 or selected >= len(self.backup_rows):
            QMessageBox.information(self, "FrameForge", "Выбери резервную копию из списка.")
            return
        row = self.backup_rows[selected]
        if not row.get("sha256"):
            QMessageBox.warning(self, "Нет контрольной суммы", "Эта запись не содержит SHA-256. Для защиты от повреждённой копии восстановление остановлено.")
            return
        self._restore(Path(row["backup"]), Path(row["config"]), row["sha256"], row.get("expected_current_sha256"))

    def _restore(
        self,
        backup: Path,
        config: Path,
        expected_sha256: str | None = None,
        expected_current_sha256: str | None = None,
    ):
        warning = ""
        if expected_current_sha256 is None:
            warning = "\n\nЭта копия создана старой версией FrameForge: сравнить файл с состоянием после применения нельзя. Если после настройки ты редактировал его вручную, эти изменения будут заменены."
        answer = QMessageBox.question(
            self,
            "Подтвердить откат",
            f"Текущий {config.name} будет заменён точной копией выбранного backup. Продолжить?{warning}",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            restored_hash = restore_from_backup(
                backup,
                config,
                expected_sha256,
                expected_current_sha256=expected_current_sha256,
            )
            self.last_backup, self.backup_config = backup, config
            self.last_backup_sha256 = expected_sha256
            self.last_current_sha256 = restored_hash
            rows = self._read_index()
            backup_key = os.path.normcase(os.path.abspath(backup))
            config_key = os.path.normcase(os.path.abspath(config))
            for row in rows:
                if (
                    os.path.normcase(os.path.abspath(row.get("backup", ""))) == backup_key
                    and os.path.normcase(os.path.abspath(row.get("config", ""))) == config_key
                ):
                    row["expected_current_sha256"] = restored_hash
                    break
            try:
                self._write_index(rows)
            except OSError as exc:
                QMessageBox.warning(
                    self,
                    "Файл восстановлен, история не обновлена",
                    f"INI восстановлен побайтово, но список backup не удалось обновить.\n{exc}",
                )
            self.game_folder = config.parent
            profile_index = next((i for i, profile in enumerate(TUNING_PROFILES) if profile.config_name.casefold() == config.name.casefold()), 0)
            self.profile_select.setCurrentIndex(profile_index)
            self.on_profile_changed()
            self.refresh_backups()
            self.show_page(3)
            QMessageBox.information(self, "Восстановлено", "Файл восстановлен побайтово.")
        except (SafetyError, OSError, ValueError) as exc:
            QMessageBox.critical(self, "Откат не выполнен", str(exc))


def run_app():
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    application.exec()
