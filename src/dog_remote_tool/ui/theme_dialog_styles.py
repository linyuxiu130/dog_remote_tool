from __future__ import annotations


DIALOG_STYLESHEET = """
        QLabel#DialogTitle {
            font-size: 13pt;
            font-weight: 800;
            color: #17324d;
        }
        QDialog, QMessageBox, QInputDialog, QFileDialog {
            background: #ffffff;
        }
        QDialog#ToolDialog {
            background: #ffffff;
        }
        QFrame#MessageDialogSurface {
            background: #ffffff;
            border: none;
        }
        QLabel#MessageDialogText {
            color: #10233f;
            font-size: 11pt;
            line-height: 150%;
            padding: 0 0 2px 0;
        }
        QFrame#MessageDialogFooter {
            background: #ffffff;
            border: none;
        }
        QMessageBox {
            min-width: 520px;
        }
        QMessageBox QLabel {
            color: #1e293b;
            font-size: 10pt;
            padding: 2px 0;
        }
        QMessageBox QLabel#qt_msgbox_label {
            color: #10233f;
            font-size: 10pt;
            min-width: 480px;
        }
        QMessageBox QLabel#qt_msgboxex_icon_label {
            min-width: 42px;
            min-height: 42px;
            padding-right: 8px;
        }
        QMessageBox QPushButton, QInputDialog QPushButton, QFileDialog QPushButton {
            min-width: 88px;
            min-height: 30px;
            padding: 4px 14px;
        }
        QInputDialog {
            min-width: 520px;
        }
        QInputDialog QLabel {
            color: #52677e;
            font-size: 9pt;
            font-weight: 700;
        }
        QInputDialog QLineEdit {
            min-height: 34px;
            font-size: 10pt;
        }
        QFileDialog {
            min-width: 1100px;
            min-height: 720px;
        }
        QFileDialog QLabel {
            color: #52677e;
            font-weight: 700;
        }
        QFileDialog QLineEdit, QFileDialog QComboBox {
            min-height: 32px;
            font-size: 10pt;
        }
        QFileDialog QPushButton {
            min-width: 96px;
            min-height: 34px;
        }
        QFileDialog QListView, QFileDialog QTreeView {
            background: #ffffff;
            border: 1px solid #d9e3ef;
            border-radius: 8px;
            alternate-background-color: #f8fafc;
            selection-background-color: #dbeafe;
            selection-color: #10233f;
            font-size: 10pt;
        }
        QFileDialog QListView::item, QFileDialog QTreeView::item {
            min-height: 30px;
            padding: 5px 7px;
        }
        QFileDialog QSplitter::handle {
            background: #e2e8f0;
        }
        QFrame#DialogFooter {
            background: #ffffff;
            border-top: 1px solid #e2e8f0;
        }
        QPlainTextEdit#PreviewText {
            background: #0b1220;
            color: #d1d9e6;
            border: 1px solid #1d314d;
            border-radius: 6px;
            padding: 10px;
            font-family: "DejaVu Sans Mono", "Consolas", monospace;
            font-size: 9pt;
        }
        QScrollArea#DialogScroll {
            background: #f8fafc;
            border: 1px solid #cbd7e6;
            border-radius: 6px;
        }
"""
