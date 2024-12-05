import sys
import re
from PyQt5.QtWidgets import (QApplication, QFileDialog, QLabel, QTabWidget, QMainWindow, QWidget, QVBoxLayout, 
                             QTextEdit, QLineEdit, QPushButton, QListWidget, QListWidgetItem, QHBoxLayout, QScrollArea)
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QTextCharFormat, QColor
import json  # Импорт для работы с JSON-файлами
class ClickableLabel(QLabel):
    clicked = pyqtSignal()  # Создаем сигнал для кликов

    def mousePressEvent(self, event):
        self.clicked.emit()  # Испускаем сигнал при клике
        super().mousePressEvent(event)
# Основное окно приложения
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Редактор текста с тегами")
        self.setGeometry(100, 100, 600, 400)

        # Создаем виджет с вкладками
        self.tab_widget = QTabWidget()

        # Инициализируем первую и вторую вкладки
        self.tab2 = SecondTab(self)
        self.tab1 = FirstTab(self.tab2, self.tab_widget)

        # Добавляем вкладки в QTabWidget
        self.tab_widget.addTab(self.tab1, "Первая вкладка")
        self.tab_widget.addTab(self.tab2, "Вторая вкладка")
        
        

        # Компоновка для верхней части, где будет кнопка справа
        top_layout = QHBoxLayout()
        top_layout.addStretch()  # Добавляем растяжение слева, чтобы кнопка была справа
        

        # Основная компоновка для окна
        main_layout = QVBoxLayout()
        main_layout.addLayout(top_layout)  # Добавляем компоновку с кнопкой
        main_layout.addWidget(self.tab_widget)  # Добавляем виджет вкладок
        # Устанавливаем центральный виджет
        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        # Устанавливаем QTabWidget как центральный виджет главного окна
        self.setCentralWidget(central_widget)
    # Метод для загрузки файла
    

# Первая вкладка с текстовым вводом
class FirstTab(QWidget):
    def __init__(self, second_tab, tab_widget):
        super().__init__()

        self.second_tab = second_tab
        self.tab_widget = tab_widget

        layout = QVBoxLayout()

        # Горизонтальный layout для кнопки загрузки
        buttons_layout = QHBoxLayout()

        # Кнопка загрузки файла
        self.load_button = QPushButton("Загрузить файл", self)
        self.load_button.clicked.connect(self.load_from_file)
        buttons_layout.addStretch()  # Растяжение для выравнивания кнопки справа
        buttons_layout.addWidget(self.load_button, alignment=Qt.AlignRight)

        # Добавляем горизонтальный layout в основной layout
        layout.addLayout(buttons_layout)

        self.text_edit = QTextEdit(self)
        self.text_edit.setPlainText(self.get_sample_text())  # Устанавливаем текст с тегами
        layout.addWidget(self.text_edit)

        self.show_button = QPushButton("Показать текст на второй вкладке", self)
        self.show_button.clicked.connect(self.update_second_tab)
        layout.addWidget(self.show_button)
        # Кнопка "Активировать кнопку"
        self.activate_button = QPushButton("Активировать кнопку", self)
        self.activate_button.clicked.connect(self.activate_show_button)
        layout.addWidget(self.activate_button)
        #Изначально деактивируем кнопку "Активировать кнопку"
        self.activate_button.setEnabled(False)

        self.setLayout(layout)

    def get_sample_text(self):
        return '''<b><RDFG 41585><E800 21>Come, Mr Naruhodo!<E003 10>Dilly-dallying will get you nowhere!<E023><PAGE>Sorry?<E023><PAGE>'''

    # Метод для передачи текста на вторую вкладку
    def update_second_tab(self):
        text = self.text_edit.toPlainText()  # Получаем текст с тегами
        text_copy = text  # Создаем копию текста
        self.second_tab.load_text(text)
        self.tab_widget.setCurrentIndex(1)
        # Деактивируем кнопку "Показать текст на второй вкладке"
        self.show_button.setEnabled(False)
        # Активируем кнопку "Активировать кнопку"
        self.activate_button.setEnabled(True)
    # Метод для повторной активации кнопки "Показать текст на второй вкладке"
    def activate_show_button(self):
        self.show_button.setEnabled(True)
        self.activate_button.setEnabled(False)
    def load_from_file(self):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getOpenFileName(self, "Открыть файл", "", "Мой формат (*.myformat);;JSON файлы (*.json)", options=options)

        if file_path:
            with open(file_path, 'r', encoding='utf-8') as file:
                data = json.load(file)
            # Проверяем наличие меток в JSON
            labels_from_json = [segment.get("label", "") for segment in data.get("segments", [])]
            # Загружаем текст в поле QTextEdit
            text_from_first_tab = data.get("first_tab_text", "")
            self.text_edit.setPlainText(text_from_first_tab)
            # Загружаем данные во вторую вкладку
            # Заменяем текст меток на основе данных из JSON
            # Автоматически переходим на вторую вкладку
            self.update_second_tab()
            if labels_from_json:
                for i, label_text in enumerate(labels_from_json):
                    if i < len(self.second_tab.labels):
                        self.second_tab.labels[i].setText(label_text)
            
            

            
            


# Вторая вкладка для отображения текста из первой вкладки
class SecondTab(QWidget):
    def __init__(self, main_window):
        super().__init__()

        self.main_window = main_window

        # Создаем QScrollArea
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)  # Устанавливаем, чтобы виджет занимал всю доступную область

        # Внутренний виджет для размещения layout
        self.content_widget = QWidget()  # Это будет контейнер для всех меток и редакторов
        self.layout = QVBoxLayout(self.content_widget)  # Создаем основной layout для содержимого

        self.scroll_area.setWidget(self.content_widget)  # Устанавливаем внутренний виджет в QScrollArea

        # Устанавливаем layout для главного виджета
        self.main_layout = QVBoxLayout(self)  # Главный layout для SecondTab
        self.main_layout.addWidget(self.scroll_area)  # Добавляем QScrollArea в главный layout

        # Кнопка для открытия всех текстовых редакторов
        self.open_all_button = QPushButton("Открыть все редакторы", self)
        self.open_all_button.clicked.connect(self.open_all_editors)  # Подключаем событие нажатия
        self.main_layout.addWidget(self.open_all_button, alignment=Qt.AlignRight)  # Добавляем кнопку в верхний правый угол

        # Горизонтальный layout для кнопок в верхней части
        buttons_layout = QHBoxLayout()

        # Кнопка для сохранения файла
        self.save_button = QPushButton("Сохранить в файл", self)
        buttons_layout.addWidget(self.save_button, alignment=Qt.AlignRight)
        self.save_button.clicked.connect(self.save_to_file)
        
        # Добавляем горизонтальный layout в основной вертикальный
        self.main_layout.addLayout(buttons_layout)

        # Инициализируем списки для хранения меток и редакторов
        self.labels = []  
        self.text_editors = []  
        self.comment_editors = []  
        self.update_buttons = []  
        self.text_segments = []  
        self.current_label_index = None
        # Словарь для тегов персонажей
        self.character_tags = {
            r'<E041 1 0>': "Рюноске",
            r'<E041 3 2>': "Сусато",
            r'<E041 4 4>': "Айрис",
            r'<E041 2 1>': "Шерлок",
            r'<E041 17 1>': "Шерлок",
            r'<E041 78 56>': "Вагахаи",
            r'<E041 96 59>': "Виндибанк",            
            r'<E041 47 31>': "МакНат",
            r'<E041 10 6>': "Джина",
            r'<E041 94 70>': "???",
            r'<E041 95 57>': "Том Летт",
            r'<E041 5 6>': "Джина",
            r'<E041 7 9>': "Грегсон",
            r'<E041 77 55>': "Бобби",
            r'<E041 14 13>': "Стронгхарт",
            r'<E041 75 24>': "Пристав",
            r'<E041 15 15>': "Судья",
            r'<E041 16 8>': "ван Зикс",
            r'<E041 99 62>': "Присяжный/-ая 1",
            r'<E041 52 63>': "Присяжный/-ая 2",
            r'<E041 100 64>': "Присяжный/-ая 3",
            r'<E041 101 65>': "Присяжный/-ая 4",
            r'<E041 102 66>': "Присяжный/-ая 5",
            r'<E041 103 67>': "Присяжный/-ая 6",
            r'<E041 6 7>': "ван Зикс",
            r'<E041 97 60>': "Нэш (высокий)",
            r'<E041 94 58>': "Грейдон",

            # Добавляйте новых персонажей здесь, используя шаблон тега
        }
        self.color_tags = {
            r'<E006>': "red",
            r'<E007>': "blue",
            r'<E008>': "green",
            # Добавляйте другие цвета и теги здесь
        }
    # Метод для сохранения текста во внешний файл
    def save_to_file(self):
        # Получаем текст из первой вкладки
        first_tab_text = self.main_window.tab1.text_edit.toPlainText()
        # Собираем данные из текстовых и комментарийных редакторов
        # Собираем данные из текстовых и комментарийных редакторов второй вкладки
        segments = []
        for label in self.labels:
            segment = {
                "label": label.text(),
                
                
            }
            segments.append(segment)
        # Формируем данные для сохранения
        data = {
            "first_tab_text": first_tab_text,
            "segments": segments
        }

        # Открываем диалог для выбора имени файла
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getSaveFileName(self, "Сохранить файл", "", "Мой формат (*.myformat);;JSON файлы (*.json)", options=options)

        if file_path:
            # Сохраняем данные в файл
            with open(file_path, 'w', encoding='utf-8') as file:
                json.dump(data, file, ensure_ascii=False, indent=4)
    def enforce_line_length(self, text_editor):
        max_length = 55  # Максимальная длина строки
        # Отключаем сигнал, чтобы избежать бесконечной рекурсии
        text_editor.blockSignals(True)  # Отключаем сигналы, чтобы избежать рекурсии

        # Получаем текст из text_editor и обрабатываем его
        text = text_editor.toPlainText()
        lines = text.splitlines()
        adjusted_lines = []

        for line in lines:
            # Разбиваем строку на подстроки длиной не более max_length
            while len(line) > max_length:
                adjusted_lines.append(line[:max_length])
                line = line[max_length:]
            adjusted_lines.append(line)

        # Обновляем текст в text_editor с добавленными переносами строк
        text_editor.setPlainText("\n".join(adjusted_lines))
        # Ставим курсор в конец текста
        cursor = text_editor.textCursor()
        cursor.movePosition(cursor.End)
        text_editor.setTextCursor(cursor)

        text_editor.blockSignals(False)  # Включаем сигналы обратно

    # Загружаем текст с первой вкладки и создаем метки и редакторы
    def load_text(self, text_copy):
        self.text_segments = text_copy.split('<PAGE>')  # Разбиваем текст по тегу <PAGE>

        # Удаляем старые метки и редакторы из layout и списков
        for widget in self.labels + self.text_editors + self.comment_editors + self.update_buttons:
            self.layout.removeWidget(widget)
            widget.deleteLater()
        self.labels.clear()
        self.text_editors.clear()
        self.comment_editors.clear()
        self.update_buttons.clear()

        # Создаем новые метки, редакторы и кнопки для каждого сегмента
        for index, segment in enumerate(self.text_segments):
            parts = re.findall(r'(<.*?>|[^<>]+)', segment)  # Разбиваем текст на части

        # Контейнер для сегмента
            container = QWidget(self)
            container_layout = QVBoxLayout(container)  # Layout для контейнера

        # Проверка наличия тега <E041>
            character_found = False
            for part in parts:
                for tag_pattern, character_name in self.character_tags.items():
                    if re.match(tag_pattern, part):
                        # Создаем метку с именем персонажа
                        character_label = QLabel(f"{character_name}:", self)
                        character_label.setStyleSheet("font-weight: bold; margin-left: 20px;")
                        container_layout.addWidget(character_label)
                        self.labels.append(character_label)
                        character_found = True
                        break
                if character_found:
                    break
                # Проверка тегов для изменения цвета текста
            colored_text = ""
            color_found = False

            for part in parts:
                for tag_pattern, color in self.color_tags.items():
                    if re.match(tag_pattern, part):
                        color_found = True
                        continue  # Не добавляем тег в текст
                if color_found:
                    colored_text += f'<span style="color: {color};">{part}</span>'
                else:
                    colored_text += part

            color_found = False  # Сбрасываем флаг после обработки сегмента
            
            cleaned_segment = re.sub(r'<.*?>', '', segment).strip()  # Удаляем теги для отображения
            
            if cleaned_segment:
                
                

                # Метка
                label = QLabel(cleaned_segment, self)
                
                label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
                label.mousePressEvent = lambda event, idx=index: self.display_block(idx)
                self.labels.append(label)
                container_layout.addWidget(label)  # Добавляем метку в контейнер

                # Редактор текста
                text_editor = QTextEdit(self)
                text_editor.setPlainText(cleaned_segment)
                text_editor.setFixedHeight(50)
                text_editor.setReadOnly(True)  # Делаем текст только для чтения
                text_editor.setVisible(False)  # Скрываем редактор изначально
                self.text_editors.append(text_editor)
                container_layout.addWidget(text_editor)  # Добавляем редактор в контейнер
                # Подключаем enforce_line_length к сигналу изменения текста
                text_editor.textChanged.connect(lambda te=text_editor: self.enforce_line_length(te))
                # Редактор комментариев
                comment_editor = QListWidget(self)
                comment_editor.setFixedHeight(50)
                comment_editor.setVisible(False)  # Скрываем редактор изначально
                self.comment_editors.append(comment_editor)
                container_layout.addWidget(comment_editor)  # Добавляем редактор комментариев в контейнер

                # Кнопка обновления
                update_button = QPushButton("✓", self)
                update_button.setFixedSize(30, 30)
                update_button.setVisible(False)  # Скрываем кнопку изначально
                update_button.clicked.connect(lambda _, idx=index: self.on_update_button_clicked(idx))
                self.update_buttons.append(update_button)
                container_layout.addWidget(update_button)  # Добавляем кнопку обновления в контейнер

                # Добавляем контейнер в основной layout
                self.layout.addWidget(container)
        self.layout.addStretch()  # Добавляем растяжение, чтобы элементы компоновались корректно
    # Метод для открытия всех текстовых редакторов
    def open_all_editors(self):
        for text_editor in self.text_editors:
            text_editor.setVisible(True)  # Делаем текстовые редакторы видимыми

    # Отображаем редакторы и кнопку для выбранного блока текста
    def display_block(self, index):
        # Делаем видимыми соответствующие редакторы и кнопку для выбранного сегмента
        self.text_editors[index].setVisible(True)
        
        self.comment_editors[index].setVisible(True)
        self.update_buttons[index].setVisible(True)

        # Заполняем comment_editor текущими частями текста
        self.comment_editors[index].clear()
        parts = re.findall(r'(<.*?>|[^<>]+)', self.text_segments[index])
        cleaned_segment = ""
        for part in parts:
            if not part.startswith('<'):  # Только текстовые сегменты
                cleaned_segment += part + ""  # Добавляем очищенный текст
                item = QListWidgetItem(part)
                item.setFlags(item.flags() | Qt.ItemIsEditable)
                self.comment_editors[index].addItem(item)
        self.text_editors[index].setPlainText(cleaned_segment.strip())  # Устанавливаем выбранный текст в редактор

    # Обрабатываем нажатие кнопки обновления
    def on_update_button_clicked(self, index):
        # Обновляем текст сегмента на основе содержимого редакторов
        text_parts = re.findall(r'(<.*?>|[^<>]+)', self.text_segments[index])
        editable_index = 0
        for i, part in enumerate(text_parts):
            if not part.startswith('<'):
                text_parts[i] = self.comment_editors[index].item(editable_index).text()
                editable_index += 1

        # Обновляем текст и отображаем в QLabel
        self.text_segments[index] = ''.join(text_parts)
        
        #self.labels[index].setText(re.sub(r'<.*?>', '', ''.join(text_parts)))
        self.text_with_tags = "<PAGE>".join(self.text_segments)

        # Обновляем текст на первой вкладке
        self.main_window.tab1.text_edit.setPlainText(self.text_with_tags)


        # Скрываем текущие редакторы и кнопку после обновления
        self.text_editors[index].setVisible(False)
        self.comment_editors[index].setVisible(False)
        self.update_buttons[index].setVisible(False)

    





if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())