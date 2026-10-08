from __future__ import annotations

import json
import csv
import os
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QMainWindow, QMessageBox, QPushButton,
    QScrollArea, QStackedWidget, QTextEdit, QVBoxLayout, QWidget,
)

from ..catalog import GUIDE, GUIDE_GAMES, GUIDES, GAMES
from ..core.apply import apply_profile_setting, build_profile_bytes, make_diff, read_profile_setting
from ..core.benchmark import Benchmark, compare_benchmarks, load_frame_time_csv
from ..core.backup import restore_from_backup, sha256
from ..core.config_finder import find_skyrim_config
from ..core.profiles import TUNING_PROFILES
from ..core.safety import SafetyError
from ..core.scanner import detect_skyrim_installs, system_snapshot
from .benchmark_chart import FrameTimeChart


BG = "#0b1020"
PANEL = "#111a2c"
CARD = "#17243a"
TEXT = "#edf3ff"
MUTED = "#a1b1cc"
ACCENT = "#72a8ff"
GREEN = "#45d6a0"


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
        version = QLabel("v0.2.0 · MIT")
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
        note = QLabel("FrameForge анализирует CSV с колонкой frame_time_ms — время каждого кадра в миллисекундах. Захват выполняет внешняя программа; FrameForge ничего не внедряет в игру и не показывает оверлей. Используй одинаковую сцену, разрешение и условия.")
        note.setWordWrap(True)
        note.setObjectName("muted")
        layout.addWidget(note)
        self.benchmark_runs: list[Benchmark] = []
        self.benchmark_list = QListWidget()
        layout.addWidget(self.benchmark_list)
        import_button = QPushButton("Импортировать CSV замера")
        import_button.clicked.connect(self.import_benchmark)
        layout.addWidget(import_button)
        compare_row = QHBoxLayout()
        compare_row.addWidget(QLabel("До:"))
        self.benchmark_before = QComboBox()
        compare_row.addWidget(self.benchmark_before, 1)
        compare_row.addWidget(QLabel("После:"))
        self.benchmark_after = QComboBox()
        compare_row.addWidget(self.benchmark_after, 1)
        compare_button = QPushButton("Сравнить")
        compare_button.setObjectName("primary")
        compare_button.clicked.connect(self.compare_benchmark_selection)
        compare_row.addWidget(compare_button)
        layout.addLayout(compare_row)
        self.benchmark_report = QTextEdit()
        self.benchmark_report.setReadOnly(True)
        self.benchmark_report.setPlaceholderText("Импортируй два CSV, чтобы сравнить результаты.")
        self.benchmark_report.setMinimumHeight(200)
        layout.addWidget(self.benchmark_report)
        chart_title = QLabel("Доля кадров по диапазонам времени (%, A/B и число кадров N показаны в легенде)")
        chart_title.setObjectName("tagline")
        layout.addWidget(chart_title)
        self.benchmark_chart = FrameTimeChart()
        layout.addWidget(self.benchmark_chart)
        chart_note = QLabel("Интервалы слева направо: <8,333; [8,333–16,667); [16,667–33,333); [33,333–50); [50–100); ≥100 мс. Классификация использует точные границы 1000/FPS. При малом N распределение менее устойчиво; разница между прогонами сама по себе не доказывает причину.")
        chart_note.setObjectName("muted")
        chart_note.setWordWrap(True)
        layout.addWidget(chart_note)
        sample = QLabel("Формат CSV: frame_time_ms\n16.6\n16.4\n17.2")
        sample.setObjectName("muted")
        layout.addWidget(sample)
        return scroll

    def import_benchmark(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выбрать CSV с временем кадров", "", "CSV files (*.csv);;All files (*)")
        if not path:
            return
        try:
            run = load_frame_time_csv(Path(path))
        except (OSError, UnicodeError, ValueError, csv.Error) as exc:
            QMessageBox.warning(self, "CSV не загружен", str(exc))
            return
        self.benchmark_runs.append(run)
        self.benchmark_list.addItem(f"{run.name} · {run.sample_count:,} кадров · {run.average_fps:.1f} avg FPS · {run.one_percent_low_fps:.1f} 1% low")
        for selector in (self.benchmark_before, self.benchmark_after):
            selector.addItem(run.name, len(self.benchmark_runs) - 1)
        if len(self.benchmark_runs) >= 2:
            self.benchmark_before.setCurrentIndex(len(self.benchmark_runs) - 2)
            self.benchmark_after.setCurrentIndex(len(self.benchmark_runs) - 1)
            self.compare_benchmark_selection()

    def compare_benchmark_selection(self):
        if self.benchmark_before.count() < 2:
            QMessageBox.information(self, "Нужны два замера", "Импортируй CSV до и после изменения настроек.")
            return
        before = self.benchmark_runs[self.benchmark_before.currentData()]
        after = self.benchmark_runs[self.benchmark_after.currentData()]
        self.benchmark_report.setPlainText(compare_benchmarks(before, after))
        self.benchmark_chart.set_runs(before, after)

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
            backup, _ = apply_profile_setting(self.config_path, target, app_data_dir() / "backups", expected_original=self.original)
            rows = self._read_index()
            backup_hash = sha256(backup.read_bytes())
            rows.insert(0, {"backup": str(backup), "config": str(self.config_path), "sha256": backup_hash, "created": datetime.now().isoformat(timespec="seconds")})
            self._write_index(rows)
            self.last_backup, self.backup_config, self.last_backup_sha256 = backup, self.config_path, backup_hash
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
            self._restore(self.last_backup, self.config_path, self.last_backup_sha256)
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
        self._restore(Path(row["backup"]), Path(row["config"]), row["sha256"])

    def _restore(self, backup: Path, config: Path, expected_sha256: str | None = None):
        answer = QMessageBox.question(self, "Подтвердить откат", f"Текущий {config.name} будет заменён точной копией выбранного backup. Продолжить?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            restored_hash = restore_from_backup(backup, config, expected_sha256)
            self.last_backup, self.backup_config, self.last_backup_sha256 = backup, config, restored_hash
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
