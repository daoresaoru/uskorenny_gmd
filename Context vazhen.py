import sys
import re
import json
from PyQt5.QtWidgets import (
    QApplication, QFileDialog, QLabel, QTabWidget, QMainWindow, QWidget,
    QVBoxLayout, QTextEdit, QLineEdit, QPushButton, QHBoxLayout,
    QScrollArea, QFrame, QSizePolicy, QMessageBox, QProgressBar, QComboBox,
    QSplitter
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QColor, QPalette, QFont, QTextCharFormat, QSyntaxHighlighter


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

MAX_LINE_PX   = 612   # pixels — Times New Roman 16pt, fits sample line
MAX_LINE_WARN = 320   # ~10px before limit

_TAG_RE  = re.compile(r'(<[^>]+>)')
_E003_RE = re.compile(r'^<E003')

# Color tags: open → CSS color, E005 = close
COLOR_TAGS: dict[str, str] = {
    '<E006>': '#ff6b6b',   # red
    '<E007>': '#6b9fff',   # blue
    '<E008>': '#6bff8a',   # green
    '<E009>': '#ffe06b',   # yellow
}
COLOR_CLOSE_TAG = '<E005>'

# Tags shown as small badges in the original display
BADGE_TAGS: dict[str, str] = {
    '<E025':  'spd',
    '<E085':  'wait',
    '<E330':  'shake',
    '<E331':  'shake',
    '<E332':  'shake',
    '<E333':  'shake',
    '<E334':  'shake',
    '<E338':  'anim',
    '<E341':  'anim',
    '<E346':  'anim',
    '<E043':  'style',
    '<E044':  'style',
    '<E169':  'lip',
    '<E145':  'expr',
    '<E603':  'sfx',
    '<E606':  'sfx',
    '<E615':  'sfx',
    '<E092':  'cam',
}


def extract_character(segment: str) -> str | None:
    for pattern, name in CHARACTER_TAGS.items():
        if re.search(pattern, segment):
            return name
    return None


def clean_text(segment: str) -> str:
    text = re.sub(r'<[^>]+>', ' ', segment)
    return re.sub(r'\s+', ' ', text).strip()


# Shared font metrics for line-length measurement (Times New Roman 16pt)
_MEASURE_FONT = QFont("Times New Roman", 16)

def _line_px(text: str) -> int:
    """Return pixel width of a single line of text in the game font."""
    from PyQt5.QtGui import QFontMetrics
    return QFontMetrics(_MEASURE_FONT).horizontalAdvance(text)

def line_length_warning(text: str) -> tuple[str, int]:
    if not text.strip():
        return '', 0
    # Strip any tags the translator typed before measuring
    import re as _re
    clean = _re.sub(r'<[^>]+>', '', text)
    max_px = max((_line_px(l) for l in clean.splitlines()), default=0)
    if max_px > MAX_LINE_PX:
        return 'error', max_px
    elif max_px > MAX_LINE_WARN:
        return 'warn', max_px
    return 'ok', max_px


# ─────────────────────────────────────────────
#  Chunk parsing — split on ANY tag boundary
# ─────────────────────────────────────────────

def parse_chunks(segment: str) -> list[dict]:
    """
    Split a segment into translatable chunks. A new chunk begins after every
    tag that interrupts text flow. Each chunk stores:
      prefix_tags  – all tags immediately before this chunk's text (for injection)
      text         – plain stripped text
      pause_tag    – the tag that ended this chunk (for display label)
    """
    tokens = _TAG_RE.split(segment)

    chunks: list[dict] = []
    prefix_tags  = ""
    current_text = ""

    def flush(closing_tag: str):
        nonlocal prefix_tags, current_text
        text_clean = re.sub(r'\s+', ' ', current_text).strip()
        if text_clean:
            chunks.append({
                "prefix_tags": prefix_tags,
                "text":        text_clean,
                "pause_tag":   closing_tag,
            })
        prefix_tags  = ""
        current_text = ""

    for token in tokens:
        if not token:
            continue
        if _TAG_RE.match(token):          # it's a tag
            if current_text.strip():
                # Text was accumulating — this tag ends the current chunk
                flush(token)
                # The tag that caused the split becomes the prefix of the next chunk
                prefix_tags = token
            else:
                # No text yet — accumulate into prefix
                prefix_tags += token
        else:                             # it's text
            current_text += token

    flush("")   # flush any remaining text
    return chunks


def inject_translations(segment: str, translations: list[str]) -> str:
    """
    Replace each visible text run in segment with the corresponding translation,
    keeping every tag in its exact original position.
    Each non-empty text token run between tags maps to one translation entry.
    """
    tokens = _TAG_RE.split(segment)

    # Find indices of all non-empty text tokens in order
    text_indices = [i for i, t in enumerate(tokens) if not _TAG_RE.match(t) and t.strip()]

    replacement: dict[int, str] = {}
    for ti, tok_idx in enumerate(text_indices):
        trans = translations[ti].strip() if ti < len(translations) else ""
        if trans:
            replacement[tok_idx] = trans

    return "".join(replacement.get(i, t) for i, t in enumerate(tokens))


# ─────────────────────────────────────────────
#  Rich HTML rendering for original display
# ─────────────────────────────────────────────

def _tag_badge_html(tag: str) -> str:
    for prefix, label in BADGE_TAGS.items():
        if tag.startswith(prefix):
            return (
                f'<span style="background:#2a2a44;color:#8888cc;'
                f'font-size:9px;border-radius:2px;padding:0 2px;">'
                f'[{label}]</span>'
            )
    return ''


def segment_to_rich_html(prefix_tags: str, text: str) -> str:
    """
    Render a chunk as HTML for the original display panel.
    prefix_tags is scanned first to determine the color context entering 'text'
    (e.g. if <E006> is the prefix, the text renders with a red background).
    Badge tags render as small grey labels; everything else is invisible.
    """
    # Determine color context from prefix_tags
    active_color: str | None = None
    for tag in _TAG_RE.findall(prefix_tags):
        if tag in COLOR_TAGS:
            active_color = COLOR_TAGS[tag]
        elif tag == COLOR_CLOSE_TAG:
            active_color = None

    parts: list[str] = []

    # Open color span if we're entering this chunk already colored
    if active_color:
        parts.append(
            f'<span style="background:{active_color}22;color:{active_color};">'
        )

    # Render the text tokens (may contain further inline tags)
    for token in _TAG_RE.split(text):
        if not token:
            continue
        if _TAG_RE.match(token):
            if token in COLOR_TAGS:
                if active_color:
                    parts.append('</span>')
                active_color = COLOR_TAGS[token]
                parts.append(
                    f'<span style="background:{active_color}22;color:{active_color};">'
                )
            elif token == COLOR_CLOSE_TAG:
                if active_color:
                    parts.append('</span>')
                active_color = None
            else:
                badge = _tag_badge_html(token)
                if badge:
                    parts.append(badge)
        else:
            escaped = (token
                       .replace('&', '&amp;')
                       .replace('<', '&lt;')
                       .replace('>', '&gt;')
                       .replace('\n', '<br>'))
            parts.append(escaped)

    if active_color:
        parts.append('</span>')

    return "".join(parts)


# ─────────────────────────────────────────────
#  Tag syntax highlighter for translation boxes
# ─────────────────────────────────────────────

class TagHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)

        self._tag_format = QTextCharFormat()
        self._tag_format.setForeground(QColor('#888888'))
        self._tag_format.setFontItalic(True)

        self._color_formats: dict[str, QTextCharFormat] = {}
        for tag, css_color in COLOR_TAGS.items():
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(css_color))
            fmt.setFontWeight(700)
            self._color_formats[tag] = fmt

        self._close_format = QTextCharFormat()
        self._close_format.setForeground(QColor('#888888'))
        self._close_format.setFontWeight(700)

        self._tag_re = re.compile(r'<[^>]+>')

    def highlightBlock(self, text: str):
        active_color_fmt: QTextCharFormat | None = None
        i = 0
        while i < len(text):
            m = self._tag_re.search(text, i)
            if active_color_fmt and (m is None or m.start() > i):
                end = m.start() if m else len(text)
                self.setFormat(i, end - i, active_color_fmt)
            if m is None:
                break
            tag = m.group(0)
            start, end = m.start(), m.end()
            if tag in COLOR_TAGS:
                self.setFormat(start, end - start, self._color_formats[tag])
                txt_fmt = QTextCharFormat()
                txt_fmt.setForeground(QColor(COLOR_TAGS[tag]))
                active_color_fmt = txt_fmt
            elif tag == COLOR_CLOSE_TAG:
                self.setFormat(start, end - start, self._close_format)
                active_color_fmt = None
            else:
                self.setFormat(start, end - start, self._tag_format)
            i = end


# ─────────────────────────────────────────────
#  Styles
# ─────────────────────────────────────────────

ORIG_STYLE = (
    "background: #1e1e1e; color: #cccccc; border: 1px solid #444; "
    "font-family: 'Consolas', monospace; font-size: 12px;"
)
TRANS_STYLE_OK = (
    "background: #1a2a1a; color: #e0e0e0; border: 1px solid #558855; "
    "font-family: 'Consolas', monospace; font-size: 12px;"
)
TRANS_STYLE_WARN = (
    "background: #2a2a1a; color: #e0e0e0; border: 2px solid #ffaa00; "
    "font-family: 'Consolas', monospace; font-size: 12px;"
)
TRANS_STYLE_ERROR = (
    "background: #2a1a1a; color: #e0e0e0; border: 2px solid #ff5555; "
    "font-family: 'Consolas', monospace; font-size: 12px;"
)


# ─────────────────────────────────────────────
#  DialoguePreview — two-line in-game textbox
# ─────────────────────────────────────────────

PREVIEW_FONT_FAMILY = "Times New Roman"
PREVIEW_FONT_SIZE   = 16
PREVIEW_MAX_PX      = MAX_LINE_PX
PREVIEW_LINES       = 2
PREVIEW_BG          = QColor("#0a0a1a")
PREVIEW_BORDER      = QColor("#6655aa")
PREVIEW_TEXT        = QColor("#f0f0e0")
PREVIEW_OVERFLOW    = QColor("#ff4444")
PREVIEW_PADDING_X   = 10
PREVIEW_PADDING_Y   = 6


class DialoguePreview(QWidget):
    """
    Mimics the TGAA two-line dialogue textbox.
    Pass plain translated text (no tags); it wraps automatically at
    PREVIEW_MAX_CHARS and renders in a styled box. Lines beyond 2 are
    shown in red to signal overflow.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._text = ""
        self._font = QFont(PREVIEW_FONT_FAMILY, PREVIEW_FONT_SIZE)
        self._font.setStyleHint(QFont.Monospace)
        from PyQt5.QtGui import QFontMetrics
        fm = QFontMetrics(self._font)
        line_h = fm.height()
        total_h = line_h * PREVIEW_LINES + PREVIEW_PADDING_Y * 2 + 6
        self.setFixedHeight(total_h)
        self.setMinimumWidth(200)

    def set_text(self, text: str):
        # Strip any tags the translator may have typed
        clean = re.sub(r'<[^>]+>', '', text).strip()
        self._text = clean
        self.update()

    def _wrap(self, text: str) -> list[str]:
        """Word-wrap text into lines fitting within PREVIEW_MAX_PX pixels."""
        from PyQt5.QtGui import QFontMetrics
        fm = QFontMetrics(self._font)

        def px(s: str) -> int:
            return fm.horizontalAdvance(s)

        if not text:
            return []
        lines: list[str] = []
        for paragraph in text.splitlines():
            if not paragraph:
                lines.append("")
                continue
            words = paragraph.split(' ')
            current = ""
            for word in words:
                # Hard-break a single word that is wider than the box
                while px(word) > PREVIEW_MAX_PX:
                    for cut in range(len(word), 0, -1):
                        if px((current + word[:cut]).strip()) <= PREVIEW_MAX_PX:
                            lines.append((current + word[:cut]).strip())
                            word = word[cut:]
                            current = ""
                            break
                candidate = (current + " " + word).strip()
                if px(candidate) <= PREVIEW_MAX_PX:
                    current = candidate
                else:
                    lines.append(current)
                    current = word
            if current:
                lines.append(current)
        return lines

    def paintEvent(self, event):
        from PyQt5.QtGui import QPainter, QFontMetrics
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()

        # Background
        painter.fillRect(0, 0, w, h, PREVIEW_BG)

        # Border
        painter.setPen(PREVIEW_BORDER)
        painter.drawRect(0, 0, w - 1, h - 1)
        # Inner border double-line effect
        painter.setPen(PREVIEW_BORDER.darker(150))
        painter.drawRect(2, 2, w - 5, h - 5)

        painter.setFont(self._font)
        fm = QFontMetrics(self._font)
        line_h = fm.height()

        lines = self._wrap(self._text)

        for i in range(max(len(lines), PREVIEW_LINES)):
            y = PREVIEW_PADDING_Y + i * line_h + fm.ascent()
            if i >= len(lines):
                break
            line_text = lines[i]
            if i < PREVIEW_LINES:
                painter.setPen(PREVIEW_TEXT)
            else:
                # Overflow line — draw red background strip then red text
                painter.fillRect(
                    PREVIEW_PADDING_X, PREVIEW_PADDING_Y + i * line_h,
                    w - PREVIEW_PADDING_X * 2, line_h,
                    QColor("#330000")
                )
                painter.setPen(PREVIEW_OVERFLOW)
            painter.drawText(PREVIEW_PADDING_X, y, line_text)

        # Overflow indicator label
        if len(lines) > PREVIEW_LINES:
            overflow_count = len(lines) - PREVIEW_LINES
            painter.setPen(PREVIEW_OVERFLOW)
            small = QFont(PREVIEW_FONT_FAMILY, 8)
            painter.setFont(small)
            painter.drawText(
                w - 90, h - 3,
                f"⛔ +{overflow_count} строк(и) лишних"
            )

        painter.end()


# ─────────────────────────────────────────────
#  ChunkPair — one original / translation pair
# ─────────────────────────────────────────────

class ChunkPair(QWidget):
    changed = pyqtSignal()

    def __init__(self, prefix_tags: str, plain_text: str, pause_tag: str, parent=None):
        super().__init__(parent)
        self.pause_tag = pause_tag

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 2, 0, 4)
        outer.setSpacing(3)

        # ── Top row: original (left) | translation (right) ──
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        # Left: original (rich HTML)
        left = QVBoxLayout()
        left.setSpacing(1)
        badge_text = pause_tag if pause_tag else "↵ конец"
        badge = QLabel(badge_text)
        badge.setStyleSheet(
            "color: #555577; font-size: 10px; font-family: 'Consolas', monospace;"
        )
        left.addWidget(badge)
        self.orig_edit = QTextEdit()
        self.orig_edit.setReadOnly(True)
        self.orig_edit.setFixedHeight(65)
        self.orig_edit.setStyleSheet(ORIG_STYLE)
        html_body = segment_to_rich_html(prefix_tags, plain_text)
        self.orig_edit.setHtml(
            f'<div style="font-family:Consolas,monospace;font-size:12px;'
            f'color:#cccccc;background:#1e1e1e;">{html_body}</div>'
        )
        left.addWidget(self.orig_edit)
        top_row.addLayout(left)

        # Right: translation with tag highlighter
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
        self._highlighter = TagHighlighter(self.trans_edit.document())
        right.addWidget(self.trans_edit)
        top_row.addLayout(right)

        outer.addLayout(top_row)

        

    def _on_changed(self):
        text = self.trans_edit.toPlainText()
        # Update preview (strip tags before passing)
       

        level, max_len = line_length_warning(text)
        if level == 'error':
            self.len_lbl.setText(f"⛔ {max_len}/{MAX_LINE_PX}px")
            self.len_lbl.setStyleSheet("color: #ff5555; font-size: 10px; font-weight: bold;")
            self.trans_edit.setStyleSheet(TRANS_STYLE_ERROR)
        elif level == 'warn':
            self.len_lbl.setText(f"⚠️ {max_len}/{MAX_LINE_PX}px")
            self.len_lbl.setStyleSheet("color: #ffaa00; font-size: 10px;")
            self.trans_edit.setStyleSheet(TRANS_STYLE_WARN)
        else:
            self.len_lbl.setText(f"✓ {max_len}/{MAX_LINE_PX}px" if max_len else "")
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
            pair = ChunkPair(
                prefix_tags=chunk["prefix_tags"],
                plain_text=chunk["text"],
                pause_tag=chunk["pause_tag"],
            )
            pair.changed.connect(self._on_any_chunk_changed)
            self.chunk_pairs.append(pair)
            outer.addWidget(pair)

        # ── Page-level preview (all chunks combined) ──
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #444455;")
        outer.addWidget(sep)

        page_lbl = QLabel("📄 Страница целиком:")
        page_lbl.setStyleSheet("color: #8888aa; font-size: 10px; font-style: italic;")
        outer.addWidget(page_lbl)

        self.page_preview = DialoguePreview()
        outer.addWidget(self.page_preview)

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
        self._update_page_preview()

    def _update_page_preview(self):
        combined = " ".join(
            re.sub(r'<[^>]+>', '', p.get_translation()).strip()
            for p in self.chunk_pairs
            if p.get_translation().strip()
        )
        self.page_preview.set_text(combined)

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
        self._update_page_preview()

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
                chunks = [{"prefix_tags": "", "text": clean_text(row.raw_segment), "pause_tag": ""}]

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
