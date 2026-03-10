import sys
import re
import json
from PyQt5.QtWidgets import (
    QApplication, QFileDialog, QLabel, QTabWidget, QMainWindow, QWidget,
    QVBoxLayout, QTextEdit, QLineEdit, QPushButton, QHBoxLayout,
    QScrollArea, QFrame, QSizePolicy, QMessageBox, QProgressBar, QComboBox,
    QSplitter
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPalette, QFont


# ─────────────────────────────────────────────
#  Constants & helpers
# ─────────────────────────────────────────────

CHARACTER_TAGS = {
    r'<E041 1 0>':    "Рюноскэ",
    r'<E041 3 2>':    "Сусато",
    r'<E041 4 4>':    "Айрис",
    r'<E041 2 1>':    "Шерлок",
    r'<E041 17 1>':   "Шерлок",
    r'<E041 78 56>':  "Вагахаи",
    r'<E041 96 59>':  "Виндибанк",
    r'<E041 47 31>':  "МакНат",
    r'<E041 10 6>':   "Джина",
    r'<E041 94 70>':  "???",
    r'<E041 95 57>':  "Том Летт",
    r'<E041 5 6>':    "Джина",
    r'<E041 7 9>':    "Грегсон",
    r'<E041 77 55>':  "Бобби",
    r'<E041 14 13>':  "Стронгхарт",
    r'<E041 75 24>':  "Пристав",
    r'<E041 15 15>':  "Судья",
    r'<E041 16 8>':   "ван Зикс",
    r'<E041 99 62>':  "Присяжный/-ая 1",
    r'<E041 52 63>':  "Присяжный/-ая 2",
    r'<E041 100 64>': "Присяжный/-ая 3",
    r'<E041 101 65>': "Присяжный/-ая 4",
    r'<E041 102 66>': "Присяжный/-ая 5",
    r'<E041 103 67>': "Присяжный/-ая 6",
    r'<E041 6 7>':    "ван Зикс",
    r'<E041 97 60>':  "Нэш (высокий)",
    r'<E041 94 58>':  "Грейдон",
}

STATUS_UNTRANSLATED = "untranslated"
STATUS_TRANSLATED   = "translated"
STATUS_EDITED       = "edited"
STATUS_APPROVED     = "approved"

STATUS_COLORS = {
    STATUS_UNTRANSLATED: "#3c3c3c",
    STATUS_TRANSLATED:   "#1a3a1a",
    STATUS_EDITED:       "#1a2a3a",
    STATUS_APPROVED:     "#2a1a3a",
}
STATUS_LABELS = {
    STATUS_UNTRANSLATED: "⬜ Не переведено",
    STATUS_TRANSLATED:   "🟩 Переведено",
    STATUS_EDITED:       "🟦 Отредактировано",
    STATUS_APPROVED:     "🟪 Одобрено",
}

MAX_LINE_LEN = 55

_TAG_RE  = re.compile(r'(<[^>]+>)')   # splits AND captures tags
_E003_RE = re.compile(r'^<E003')


def extract_character(segment: str) -> str | None:
    for pattern, name in CHARACTER_TAGS.items():
        if re.search(pattern, segment):
            return name
    return None


def clean_text(segment: str) -> str:
    text = re.sub(r'<[^>]+>', ' ', segment)
    return re.sub(r'\s+', ' ', text).strip()


def line_length_warning(text: str) -> tuple[str, int]:
    if not text.strip():
        return '', 0
    lines = text.splitlines()
    max_len = max(len(l) for l in lines) if lines else 0
    if max_len > MAX_LINE_LEN:
        return 'error', max_len
    elif max_len > MAX_LINE_LEN - 5:
        return 'warn', max_len
    return 'ok', max_len


# ─────────────────────────────────────────────
#  Chunk parsing
#
#  Split a segment into "pause chunks" on <E003 X> boundaries.
#  Each chunk:  { prefix_tags, text, pause_tag }
#  prefix_tags = all tags that come before the first text character of this chunk
#  text        = concatenated visible text (stripped)
#  pause_tag   = the <E003 X> that closes this chunk (or "" for the last one)
# ─────────────────────────────────────────────

def parse_chunks(segment: str) -> list[dict]:
    """Return list of chunk dicts."""
    tokens = _TAG_RE.split(segment)   # alternates: text, tag, text, tag …

    chunks: list[dict] = []
    prefix_tags = ""
    current_text = ""

    def flush(pause_tag: str):
        nonlocal prefix_tags, current_text
        text_clean = re.sub(r'\s+', ' ', current_text).strip()
        chunks.append({
            "prefix_tags": prefix_tags,
            "text":        text_clean,
            "pause_tag":   pause_tag,
        })
        prefix_tags = ""
        current_text = ""

    for token in tokens:
        if not token:
            continue
        if _TAG_RE.match(token):                  # it's a tag
            if _E003_RE.match(token):
                flush(token)
            else:
                if current_text.strip():
                    # tag after text but before E003 — treat as part of text display
                    pass
                else:
                    prefix_tags += token
        else:                                     # it's text
            current_text += token

    # flush trailing chunk
    text_clean = re.sub(r'\s+', ' ', current_text).strip()
    if text_clean or prefix_tags:
        chunks.append({"prefix_tags": prefix_tags, "text": text_clean, "pause_tag": ""})

    # Remove chunks that are completely empty (no text and no meaningful prefix)
    chunks = [c for c in chunks if c["text"]]
    return chunks


def inject_translations(segment: str, translations: list[str]) -> str:
    """
    Replace each visible text run in `segment` with the corresponding
    translation string, keeping every tag in its original position.

    Strategy:
      - Tokenise on tags.
      - Collect runs of non-empty text tokens into groups separated by <E003>.
      - Replace the *first* text token of each group with the translation;
        set subsequent tokens in the same group to "".
    """
    tokens = _TAG_RE.split(segment)   # [text, tag, text, tag …]

    # Identify "real text" token indices and group them by E003 boundary
    groups: list[list[int]] = []
    current_group: list[int] = []

    for i, token in enumerate(tokens):
        if _TAG_RE.match(token):        # tag
            if _E003_RE.match(token) and current_group:
                groups.append(current_group)
                current_group = []
        else:                           # text
            if token.strip():
                current_group.append(i)

    if current_group:
        groups.append(current_group)

    # Build replacement map
    replacement: dict[int, str] = {}
    for gi, group in enumerate(groups):
        trans = translations[gi].strip() if gi < len(translations) else ""
        if not trans:
            continue   # keep original if translation empty
        for ti, tok_idx in enumerate(group):
            replacement[tok_idx] = trans if ti == 0 else ""

    # Rebuild
    result_tokens = []
    for i, token in enumerate(tokens):
        if i in replacement:
            result_tokens.append(replacement[i])
        else:
            result_tokens.append(token)

    return "".join(result_tokens)


# ─────────────────────────────────────────────
#  Styles
# ─────────────────────────────────────────────

ORIG_STYLE = (
    "background: #1e1e1e; color: #cccccc; border: 1px solid #444; "
    "font-family: 'Consolas', monospace; font-size: 12px;"
)
TRANS_STYLE_OK    = (
    "background: #1a2a1a; color: #e0e0e0; border: 1px solid #558855; "
    "font-family: 'Consolas', monospace; font-size: 12px;"
)
TRANS_STYLE_WARN  = (
    "background: #2a2a1a; color: #e0e0e0; border: 2px solid #ffaa00; "
    "font-family: 'Consolas', monospace; font-size: 12px;"
)
TRANS_STYLE_ERROR = (
    "background: #2a1a1a; color: #e0e0e0; border: 2px solid #ff5555; "
    "font-family: 'Consolas', monospace; font-size: 12px;"
)


# ─────────────────────────────────────────────
#  ChunkPair — one original / translation pair
# ─────────────────────────────────────────────

class ChunkPair(QWidget):
    changed = pyqtSignal()

    def __init__(self, original_text: str, pause_tag: str, parent=None):
        super().__init__(parent)
        self.pause_tag = pause_tag

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 2, 0, 2)
        row.setSpacing(6)

        # Left: original
        left = QVBoxLayout()
        left.setSpacing(1)
        badge_text = pause_tag if pause_tag else "↵ конец"
        badge = QLabel(badge_text)
        badge.setStyleSheet(
            "color: #555577; font-size: 10px; font-family: 'Consolas', monospace;"
        )
        left.addWidget(badge)
        self.orig_edit = QTextEdit()
        self.orig_edit.setPlainText(original_text)
        self.orig_edit.setReadOnly(True)
        self.orig_edit.setFixedHeight(65)
        self.orig_edit.setStyleSheet(ORIG_STYLE)
        left.addWidget(self.orig_edit)
        row.addLayout(left)

        # Right: translation
        right = QVBoxLayout()
        right.setSpacing(1)
        top_right = QHBoxLayout()
        self.len_lbl = QLabel("")
        self.len_lbl.setStyleSheet("font-size: 10px;")
        top_right.addStretch()
        top_right.addWidget(self.len_lbl)
        right.addLayout(top_right)
        self.trans_edit = QTextEdit()
        self.trans_edit.setFixedHeight(65)
        self.trans_edit.setStyleSheet(TRANS_STYLE_OK)
        self.trans_edit.textChanged.connect(self._on_changed)
        right.addWidget(self.trans_edit)
        row.addLayout(right)

    def _on_changed(self):
        text = self.trans_edit.toPlainText()
        level, max_len = line_length_warning(text)
        if level == 'error':
            self.len_lbl.setText(f"⛔ {max_len}/{MAX_LINE_LEN}")
            self.len_lbl.setStyleSheet("color: #ff5555; font-size: 10px; font-weight: bold;")
            self.trans_edit.setStyleSheet(TRANS_STYLE_ERROR)
        elif level == 'warn':
            self.len_lbl.setText(f"⚠️ {max_len}/{MAX_LINE_LEN}")
            self.len_lbl.setStyleSheet("color: #ffaa00; font-size: 10px;")
            self.trans_edit.setStyleSheet(TRANS_STYLE_WARN)
        else:
            self.len_lbl.setText(f"✓ {max_len}/{MAX_LINE_LEN}" if max_len else "")
            self.len_lbl.setStyleSheet("color: #55aa55; font-size: 10px;")
            self.trans_edit.setStyleSheet(TRANS_STYLE_OK)
        self.changed.emit()

    def get_translation(self) -> str:
        return self.trans_edit.toPlainText()

    def set_translation(self, text: str):
        self.trans_edit.setPlainText(text)


# ─────────────────────────────────────────────
#  SegmentRow
# ─────────────────────────────────────────────

class SegmentRow(QFrame):
    status_changed = pyqtSignal()

    def __init__(self, index: int, segment: str, character: str | None, parent=None):
        super().__init__(parent)
        self.index = index
        self.raw_segment = segment
        self.character = character
        self.status = STATUS_UNTRANSLATED

        self.setFrameShape(QFrame.StyledPanel)
        self.setObjectName("segmentRow")
        self._apply_status_style()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 6)
        outer.setSpacing(3)

        # Header
        header = QHBoxLayout()
        self.char_label = QLabel(f"👤 {character}" if character else "")
        self.char_label.setStyleSheet(
            "color: #aaaaff; font-weight: bold; font-size: 12px;"
        )
        header.addWidget(self.char_label)
        header.addStretch()
        self.status_combo = QComboBox()
        for key, label in STATUS_LABELS.items():
            self.status_combo.addItem(label, key)
        self.status_combo.setFixedWidth(200)
        self.status_combo.currentIndexChanged.connect(self._on_status_changed)
        self.status_combo.setStyleSheet("font-size: 11px;")
        header.addWidget(self.status_combo)
        outer.addLayout(header)

        # Column headers
        col_hdr = QHBoxLayout()
        col_hdr.setSpacing(6)
        for txt in ("Оригинал (EN)", "Перевод (RU)"):
            lbl = QLabel(txt)
            lbl.setStyleSheet("color: #666688; font-size: 11px; font-style: italic;")
            col_hdr.addWidget(lbl)
        outer.addLayout(col_hdr)

        # Chunk pairs
        self.chunk_pairs: list[ChunkPair] = []
        chunks = parse_chunks(segment)
        if not chunks:
            chunks = [{"prefix_tags": "", "text": clean_text(segment), "pause_tag": ""}]

        for chunk in chunks:
            pair = ChunkPair(chunk["text"], chunk["pause_tag"])
            pair.changed.connect(self._on_any_chunk_changed)
            self.chunk_pairs.append(pair)
            outer.addWidget(pair)

    def _apply_status_style(self):
        color = STATUS_COLORS.get(self.status, "#3c3c3c")
        self.setStyleSheet(f"""
            QFrame#segmentRow {{
                background-color: {color};
                border: 1px solid #555555;
                border-radius: 4px;
                margin: 2px 0px;
            }}
        """)

    def _on_any_chunk_changed(self):
        has_any = any(p.get_translation().strip() for p in self.chunk_pairs)
        if has_any and self.status == STATUS_UNTRANSLATED:
            self._set_status(STATUS_TRANSLATED)
        elif not has_any:
            self._set_status(STATUS_UNTRANSLATED)

    def _set_status(self, status: str):
        self.status = status
        idx = list(STATUS_LABELS.keys()).index(status)
        self.status_combo.blockSignals(True)
        self.status_combo.setCurrentIndex(idx)
        self.status_combo.blockSignals(False)
        self._apply_status_style()
        self.status_changed.emit()

    def _on_status_changed(self):
        self.status = self.status_combo.currentData()
        self._apply_status_style()
        self.status_changed.emit()

    def set_status(self, status: str):
        self._set_status(status)

    def get_translations(self) -> list[str]:
        return [p.get_translation() for p in self.chunk_pairs]

    def set_translations(self, translations: list[str]):
        for i, pair in enumerate(self.chunk_pairs):
            if i < len(translations):
                pair.set_translation(translations[i])

    def get_injected_segment(self) -> str:
        translations = self.get_translations()
        if not any(t.strip() for t in translations):
            return self.raw_segment
        return inject_translations(self.raw_segment, translations)

    def to_dict(self) -> dict:
        return {
            "raw_segment": self.raw_segment,
            "translations": self.get_translations(),
            "status": self.status,
        }


# ─────────────────────────────────────────────
#  Tab 1 — Script input
# ─────────────────────────────────────────────

class Tab1(QWidget):
    def __init__(self, tab2, tab_widget):
        super().__init__()
        self.tab2 = tab2
        self.tab_widget = tab_widget

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        title = QLabel("📄 Исходный скрипт")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #ccccff;")
        toolbar.addWidget(title)
        toolbar.addStretch()
        self.load_btn = QPushButton("📂 Загрузить .myformat")
        self.load_btn.clicked.connect(self.load_from_file)
        toolbar.addWidget(self.load_btn)
        layout.addLayout(toolbar)

        hint = QLabel(
            "Вставьте или загрузите скрипт с тегами ниже, затем нажмите «Разобрать»."
        )
        hint.setStyleSheet("color: #888888; font-size: 11px;")
        layout.addWidget(hint)

        self.text_edit = QTextEdit()
        self.text_edit.setStyleSheet(
            "background: #1a1a2a; color: #dddddd; border: 1px solid #555; "
            "font-family: 'Consolas', monospace; font-size: 12px;"
        )
        layout.addWidget(self.text_edit)

        btn_row = QHBoxLayout()

        self.parse_btn = QPushButton("▶  Разобрать скрипт  →  Перейти к переводу")
        self.parse_btn.setStyleSheet(
            "background: #334455; color: white; font-size: 13px; "
            "padding: 8px; border-radius: 4px;"
        )
        self.parse_btn.clicked.connect(self.parse_and_switch)
        btn_row.addWidget(self.parse_btn)

        self.inject_btn = QPushButton("💉 Внедрить перевод в скрипт")
        self.inject_btn.setStyleSheet(
            "background: #553333; color: white; font-size: 13px; "
            "padding: 8px; border-radius: 4px;"
        )
        self.inject_btn.setToolTip(
            "Заменяет английский текст переводом, сохраняя все теги нетронутыми."
        )
        self.inject_btn.clicked.connect(self.inject_translations)
        btn_row.addWidget(self.inject_btn)

        layout.addLayout(btn_row)

    def parse_and_switch(self):
        text = self.text_edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Пусто", "Вставьте текст скрипта перед разбором.")
            return
        self.tab2.load_script(text)
        self.tab_widget.setCurrentIndex(1)

    def inject_translations(self):
        rows = self.tab2.rows
        if not rows:
            QMessageBox.warning(self, "Нет данных", "Сначала разберите скрипт.")
            return

        untranslated = sum(1 for r in rows if r.status == STATUS_UNTRANSLATED)
        if untranslated:
            reply = QMessageBox.question(
                self, "Есть непереведённые строки",
                f"{untranslated} сегмент(ов) ещё не переведено.\n"
                "Продолжить? Непереведённые строки останутся на английском.",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        raw = self.tab2.raw_script
        all_segments = raw.split('<PAGE>')

        # Map segment index → SegmentRow
        row_by_seg_index: dict[int, SegmentRow] = {}
        row_iter = iter(rows)
        for seg_idx, seg in enumerate(all_segments):
            if clean_text(seg):
                try:
                    row_by_seg_index[seg_idx] = next(row_iter)
                except StopIteration:
                    break

        new_segments = []
        for seg_idx, seg in enumerate(all_segments):
            if seg_idx in row_by_seg_index:
                new_segments.append(row_by_seg_index[seg_idx].get_injected_segment())
            else:
                new_segments.append(seg)

        new_script = '<PAGE>'.join(new_segments)
        self.text_edit.setPlainText(new_script)
        self.tab_widget.setCurrentIndex(0)
        QMessageBox.information(
            self, "Готово",
            "Перевод внедрён!\nСкрипт обновлён на этой вкладке.\n"
            "Нажмите «Сохранить .myformat» для сохранения проекта."
        )

    def load_from_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Открыть файл", "",
            "Мой формат (*.myformat);;JSON (*.json)"
        )
        if not path:
            return
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        raw = data.get("raw_script", "")
        self.text_edit.setPlainText(raw)
        self.tab2.load_script(raw, saved_segments=data.get("segments", []))
        self.tab_widget.setCurrentIndex(1)


# ─────────────────────────────────────────────
#  Tab 2 — Translation editor
# ─────────────────────────────────────────────

class Tab2(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.rows: list[SegmentRow] = []
        self.raw_script = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        # Top bar
        topbar = QHBoxLayout()
        title = QLabel("✏️ Редактор перевода")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #ccccff;")
        topbar.addWidget(title)
        topbar.addStretch()
        self.save_btn = QPushButton("💾 Сохранить .myformat")
        self.save_btn.clicked.connect(self.save_to_file)
        topbar.addWidget(self.save_btn)
        self.export_btn = QPushButton("📤 Экспорт в TXT")
        self.export_btn.clicked.connect(self.export_to_txt)
        topbar.addWidget(self.export_btn)
        outer.addLayout(topbar)

        # Progress bar
        prog_row = QHBoxLayout()
        self.progress_label = QLabel("Прогресс: 0 / 0 сегментов")
        self.progress_label.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        prog_row.addWidget(self.progress_label)
        prog_row.addStretch()
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(300)
        self.progress_bar.setFixedHeight(14)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(
            "QProgressBar { background: #333; border-radius: 3px; }"
            "QProgressBar::chunk { background: #558855; border-radius: 3px; }"
        )
        prog_row.addWidget(self.progress_bar)
        outer.addLayout(prog_row)

        # Filter bar
        filter_bar = QHBoxLayout()
        filter_lbl = QLabel("Фильтр:")
        filter_lbl.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        filter_bar.addWidget(filter_lbl)
        self.filter_combo = QComboBox()
        self.filter_combo.addItem("Все сегменты", "all")
        for key, label in STATUS_LABELS.items():
            self.filter_combo.addItem(label, key)
        self.filter_combo.currentIndexChanged.connect(self._apply_filter)
        self.filter_combo.setFixedWidth(220)
        filter_bar.addWidget(self.filter_combo)
        filter_bar.addStretch()
        outer.addLayout(filter_bar)

        # Scroll area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background: #1e1e1e; border: none;")
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setSpacing(4)
        self.content_layout.setContentsMargins(4, 4, 4, 4)
        self.scroll.setWidget(self.content)
        outer.addWidget(self.scroll)

    def load_script(self, raw: str, saved_segments: list = None):
        self.raw_script = raw
        for row in self.rows:
            self.content_layout.removeWidget(row)
            row.deleteLater()
        self.rows.clear()

        segments = raw.split('<PAGE>')
        saved_map: dict[int, dict] = {}
        if saved_segments:
            for i, s in enumerate(saved_segments):
                saved_map[i] = s

        row_idx = 0
        for seg_idx, seg in enumerate(segments):
            if not clean_text(seg):
                continue
            character = extract_character(seg)
            row = SegmentRow(seg_idx, seg, character)
            saved = saved_map.get(row_idx)
            if saved:
                row.set_translations(saved.get("translations", []))
                row.set_status(saved.get("status", STATUS_UNTRANSLATED))
            row.status_changed.connect(self._update_progress)
            self.rows.append(row)
            self.content_layout.addWidget(row)
            row_idx += 1

        self.content_layout.addStretch()
        self._update_progress()

    def _update_progress(self):
        total = len(self.rows)
        done = sum(1 for r in self.rows if r.status != STATUS_UNTRANSLATED)
        approved = sum(1 for r in self.rows if r.status == STATUS_APPROVED)
        if total:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(done)
            self.progress_label.setText(
                f"Прогресс: {done}/{total} переведено  |  {approved}/{total} одобрено"
            )
        else:
            self.progress_label.setText("Нет сегментов")

    def _apply_filter(self):
        filt = self.filter_combo.currentData()
        for row in self.rows:
            row.setVisible(filt == "all" or row.status == filt)

    def save_to_file(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить", "", "Мой формат (*.myformat);;JSON (*.json)"
        )
        if not path:
            return
        data = {
            "raw_script": self.raw_script,
            "segments": [r.to_dict() for r in self.rows],
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        QMessageBox.information(self, "Сохранено", f"Файл сохранён:\n{path}")

    def export_to_txt(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Экспорт в TXT", "", "Text Files (*.txt)"
        )
        if not path:
            return

        lines = []
        last_character = None

        for row in self.rows:
            char = row.character
            translations = row.get_translations()
            chunks = parse_chunks(row.raw_segment)
            if not chunks:
                chunks = [{"text": clean_text(row.raw_segment), "pause_tag": "", "prefix_tags": ""}]

            if char and char != last_character:
                if lines:
                    lines.append("")
                lines.append(f"{char}:")
                last_character = char

            for i, chunk in enumerate(chunks):
                orig = chunk["text"]
                trans = translations[i].strip() if i < len(translations) else ""
                if orig:
                    lines.append(orig)
                if trans:
                    lines.append(trans)

            lines.append("")

        with open(path, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines))

        QMessageBox.information(self, "Экспорт", f"Файл экспортирован:\n{path}")


# ─────────────────────────────────────────────
#  Main window
# ─────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Редактор перевода скриптов")
        self.setGeometry(100, 100, 1150, 780)
        self.setStyleSheet("background-color: #252526; color: #cccccc;")

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #444; }
            QTabBar::tab { background: #333; color: #aaa; padding: 8px 16px; }
            QTabBar::tab:selected { background: #1e1e2e; color: white; }
        """)

        self.tab2 = Tab2(self)
        self.tab1 = Tab1(self.tab2, self.tabs)

        self.tabs.addTab(self.tab1, "📄  Скрипт")
        self.tabs.addTab(self.tab2, "✏️  Перевод")

        self.setCentralWidget(self.tabs)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.Window,          QColor("#252526"))
    palette.setColor(QPalette.WindowText,      QColor("#cccccc"))
    palette.setColor(QPalette.Base,            QColor("#1e1e1e"))
    palette.setColor(QPalette.AlternateBase,   QColor("#2a2a2a"))
    palette.setColor(QPalette.Text,            QColor("#cccccc"))
    palette.setColor(QPalette.Button,          QColor("#3c3c3c"))
    palette.setColor(QPalette.ButtonText,      QColor("#cccccc"))
    palette.setColor(QPalette.Highlight,       QColor("#264f78"))
    palette.setColor(QPalette.HighlightedText, QColor("white"))
    app.setPalette(palette)

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
