"""
PyQt6 Beginning Inventory Viewer
- Connects to PostgreSQL and lists all tables starting with 'beginv_'
- Displays selected table in QTableWidget (read-only by default)
- Editable mode can be unlocked by entering password 'itadmin'
- Allows exporting viewed table to Excel

Dependencies:
    pip install psycopg2-binary pandas openpyxl PyQt6

Usage:
    python pyqt6_beginning_inventory_viewer.py
"""

import sys
import pandas as pd
import psycopg2
from sqlalchemy import create_engine, inspect
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QTableWidget, QTableWidgetItem,
    QMessageBox, QFileDialog, QLineEdit
)
from PyQt6.QtCore import Qt

# ---------- DB defaults ----------
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "user": "postgres",
    "password": "mbpi",
    "dbname": "dbfg"
}

EDIT_PASSWORD = "itadmin"


# ---------- Helper ----------
def get_engine():
    url = f"postgresql+psycopg2://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}"
    return create_engine(url)


def list_beginv_tables():
    engine = get_engine()
    insp = inspect(engine)
    tables = [t for t in insp.get_table_names() if t.startswith("beginv_")]
    engine.dispose()
    return tables


def load_table(table):
    engine = get_engine()
    df = pd.read_sql(f'select * from "{table}"', engine)
    engine.dispose()
    return df


# ---------- Main Window ----------
class ViewerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Beginning Inventory Viewer")
        self.resize(1000, 600)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Top controls
        controls_layout = QHBoxLayout()

        self.table_combo = QComboBox()
        self.btn_load = QPushButton("Load Table")
        self.btn_refresh = QPushButton("Refresh List")
        self.btn_export = QPushButton("Export to Excel")
        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("Enter password for edit mode")
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.btn_unlock = QPushButton("Unlock Edit")

        controls_layout.addWidget(QLabel("Select Table:"))
        controls_layout.addWidget(self.table_combo)
        controls_layout.addWidget(self.btn_load)
        controls_layout.addWidget(self.btn_refresh)
        controls_layout.addWidget(self.btn_export)
        controls_layout.addStretch()
        controls_layout.addWidget(self.password_edit)
        controls_layout.addWidget(self.btn_unlock)

        # Table widget
        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        layout.addLayout(controls_layout)
        layout.addWidget(self.table)

        # Signals
        self.btn_load.clicked.connect(self.load_selected_table)
        self.btn_refresh.clicked.connect(self.refresh_tables)
        self.btn_export.clicked.connect(self.export_table)
        self.btn_unlock.clicked.connect(self.unlock_edit)

        # init
        self.refresh_tables()

    def refresh_tables(self):
        try:
            tables = list_beginv_tables()
            self.table_combo.clear()
            self.table_combo.addItems(tables)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to list tables: {e}")

    def load_selected_table(self):
        tbl = self.table_combo.currentText()
        if not tbl:
            return
        try:
            df = load_table(tbl)
            self.populate_table(df)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load table: {e}")

    def populate_table(self, df: pd.DataFrame):
        self.table.clear()
        self.table.setRowCount(len(df))
        self.table.setColumnCount(len(df.columns))
        self.table.setHorizontalHeaderLabels(df.columns)
        for i in range(len(df)):
            for j, col in enumerate(df.columns):
                val = str(df.iloc[i, j])
                self.table.setItem(i, j, QTableWidgetItem(val))

    def export_table(self):
        tbl = self.table_combo.currentText()
        if not tbl:
            return
        try:
            df = load_table(tbl)
            path, _ = QFileDialog.getSaveFileName(self, "Save Excel", f"{tbl}.xlsx", "Excel Files (*.xlsx)")
            if path:
                df.to_excel(path, index=False)
                QMessageBox.information(self, "Exported", f"Table exported to {path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export: {e}")

    def unlock_edit(self):
        if self.password_edit.text() == EDIT_PASSWORD:
            self.table.setEditTriggers(QTableWidget.EditTrigger.AllEditTriggers)
            QMessageBox.information(self, "Unlocked", "Edit mode enabled.")
        else:
            QMessageBox.warning(self, "Wrong password", "Incorrect password. Table remains read-only.")


# ---------- Run ----------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = ViewerWindow()
    w.show()
    sys.exit(app.exec())
