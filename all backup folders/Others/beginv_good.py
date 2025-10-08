# beginv_good.py (Version 5 - Compute by Lot Number Only)
# This is your main application file. Run this file to use the inventory system.

import sys
import traceback
from decimal import Decimal

import pandas as pd
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QThread
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
                             QHeaderView, QMessageBox, QHBoxLayout, QLabel,
                             QPushButton, QComboBox, QAbstractItemView, QMainWindow)
from sqlalchemy import create_engine, text

# --- IMPORTANT: CONFIGURE YOUR DATABASE CONNECTION HERE ---
DATABASE_URL = "postgresql+psycopg2://postgres:mbpi@localhost:5432/dbfg"


# ==============================================================================
# SECTION 1: INVENTORY CALCULATION WORKER (for threading)
# ==============================================================================
class InventoryWorker(QObject):
    finished = pyqtSignal(pd.DataFrame)
    error = pyqtSignal(str)

    def __init__(self, engine, lot_filter=None):
        super().__init__()
        self.engine = engine
        self.lot_filter = lot_filter

    def run(self):
        try:
            # --- MODIFIED: Query now only selects and groups by lot_number ---
            query_str = """
                SELECT
                    lot_number,
                    COALESCE(SUM(quantity_in), 0) - COALESCE(SUM(quantity_out), 0) AS current_balance
                FROM transactions
                {where_clause}
                GROUP BY lot_number
            """

            params = {}
            where_clause = "WHERE lot_number IS NOT NULL AND lot_number != ''"
            if self.lot_filter:
                where_clause += " AND lot_number = :lot"
                params['lot'] = self.lot_filter

            final_query = text(query_str.format(where_clause=where_clause))
            with self.engine.connect() as conn:
                results = conn.execute(final_query, params).mappings().all()

            # The DataFrame no longer contains a 'product_code' column
            df = pd.DataFrame(results) if results else pd.DataFrame(
                columns=['lot_number', 'current_balance'])
            self.finished.emit(df)
        except Exception as e:
            self.error.emit(f"Database query failed: {e}")
            traceback.print_exc()


# ==============================================================================
# SECTION 2: THE MAIN INVENTORY PAGE WIDGET
# ==============================================================================
class GoodInventoryPage(QWidget):
    def __init__(self, db_engine):
        super().__init__()
        self.engine = db_engine
        self.thread = None
        self.worker = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        filter_group_box = QWidget()
        filter_layout = QHBoxLayout(filter_group_box)

        self.lot_number_combo = QComboBox(editable=True)
        self.lot_number_combo.setPlaceholderText("Select or Type a Lot Number...")
        self.lot_number_combo.setMinimumWidth(300)
        self.lot_number_combo.lineEdit().returnPressed.connect(self._check_specific_inventory)

        self.check_specific_btn = QPushButton("Check Specific Lot")
        self.refresh_btn = QPushButton("Refresh All")
        self.refresh_btn.setObjectName("PrimaryButton")

        filter_layout.addWidget(QLabel("<b>Lot Number:</b>"))
        filter_layout.addWidget(self.lot_number_combo, 1)
        filter_layout.addWidget(self.check_specific_btn)
        filter_layout.addWidget(self.refresh_btn)
        filter_layout.addStretch()
        layout.addWidget(filter_group_box)

        # --- MODIFIED: Table is now 2 columns, header labels updated ---
        self.inventory_table = QTableWidget(columnCount=2)
        self.inventory_table.setHorizontalHeaderLabels(["Lot Number", "Current Balance (kg)"])
        self.inventory_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.inventory_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        header = self.inventory_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)

        layout.addWidget(self.inventory_table, 1)
        self.total_balance_label = QLabel("Total Balance: 0.00 kg")
        self.total_balance_label.setStyleSheet("font-size: 14pt; font-weight: bold; padding: 10px;")
        self.total_balance_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.total_balance_label)
        self.check_specific_btn.clicked.connect(self._check_specific_inventory)
        self.refresh_btn.clicked.connect(self.refresh_page)
        self._load_lot_numbers()

    def refresh_page(self):
        self.lot_number_combo.setCurrentIndex(0)
        self._start_calculation(lot_filter=None)

    def _load_lot_numbers(self):
        try:
            with self.engine.connect() as conn:
                query = text(
                    "SELECT DISTINCT lot_number FROM transactions WHERE lot_number IS NOT NULL AND lot_number != '' ORDER BY lot_number;")
                result = conn.execute(query).scalars().all()
            self.lot_number_combo.clear()
            self.lot_number_combo.addItem("")
            self.lot_number_combo.addItems(result)
        except Exception as e:
            QMessageBox.warning(self, "Load Error", f"Could not load lot numbers: {e}")

    def _check_specific_inventory(self):
        lot_filter = self.lot_number_combo.currentText().strip()
        if not lot_filter:
            self.refresh_page()
            return
        self._start_calculation(lot_filter=lot_filter)

    def _start_calculation(self, lot_filter=None):
        self.set_controls_enabled(False)
        self._show_loading_state()
        self.thread = QThread()
        self.worker = InventoryWorker(self.engine, lot_filter)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._on_calculation_finished)
        self.worker.error.connect(self._on_calculation_error)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def _on_calculation_finished(self, df):
        is_specific = bool(self.lot_number_combo.currentText().strip())
        # --- MODIFIED: Sorting now only by lot_number ---
        df = df[df['current_balance'] > 0.001].sort_values(by=['lot_number'])
        self._display_inventory(df, is_specific_lot=is_specific)
        self.set_controls_enabled(True)

    def _on_calculation_error(self, error_message):
        QMessageBox.critical(self, "Calculation Error", error_message)
        self.inventory_table.setRowCount(0)
        self.set_controls_enabled(True)

    def set_controls_enabled(self, enabled):
        self.lot_number_combo.setEnabled(enabled)
        self.check_specific_btn.setEnabled(enabled)
        self.refresh_btn.setEnabled(enabled)

    def _show_loading_state(self):
        self.inventory_table.setRowCount(1)
        loading_item = QTableWidgetItem("Loading data, please wait...")
        loading_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.inventory_table.setItem(0, 0, loading_item)
        self.inventory_table.setSpan(0, 0, 1, self.inventory_table.columnCount())
        self.total_balance_label.setText("Calculating...")

    def _display_inventory(self, df, is_specific_lot):
        self.inventory_table.setRowCount(0)
        self.inventory_table.setSpan(0, 0, 1, 1)
        total_balance = Decimal(df['current_balance'].sum())
        if df.empty:
            msg = "No current balance found for the selected lot." if is_specific_lot else "No lots with a positive balance were found."

        self.inventory_table.setRowCount(len(df))
        for i, row in df.iterrows():
            # --- MODIFIED: Code for setting product_code is removed ---
            # Column 0 is now Lot Number
            self.inventory_table.setItem(i, 0, QTableWidgetItem(str(row.get('lot_number', ''))))

            # Column 1 is now the balance
            qty_item = QTableWidgetItem(f"{Decimal(row.get('current_balance', 0)):.2f}")
            qty_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.inventory_table.setItem(i, 1, qty_item)

        if is_specific_lot:
            self.total_balance_label.setText(f"Balance for Selected Lot: {total_balance:.2f} kg")
        else:
            self.total_balance_label.setText(f"Overall Total Balance (All Lots): {total_balance:.2f} kg")


# ==============================================================================
# SECTION 3 & 4: APPLICATION FRAMEWORK AND MAIN EXECUTION (No Changes Needed)
# ==============================================================================

class LoginWindow(QWidget):
    login_successful = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Login")
        self.setFixedSize(300, 150)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Click the button to open the inventory page."))
        login_button = QPushButton("Simulate Successful Login")
        login_button.clicked.connect(self.login_successful.emit)
        layout.addWidget(login_button)


class MainWindow(QMainWindow):
    def __init__(self, engine):
        super().__init__()
        self.setWindowTitle("Main Application - Inventory Management")
        self.resize(1100, 750)
        self.inventory_page = GoodInventoryPage(engine)
        self.setCentralWidget(self.inventory_page)


def main():
    app = QApplication(sys.argv)
    try:
        engine = create_engine(DATABASE_URL)
        with engine.connect() as connection:
            print("Database connection successful!")
    except Exception as e:
        QMessageBox.critical(None, "Database Error",
                             f"Could not connect to the database.\nPlease check DATABASE_URL in the script.\n\nError: {e}")
        return
    main_window = None
    login_window = LoginWindow()

    def on_login_success():
        nonlocal main_window
        login_window.close()
        main_window = MainWindow(engine)
        main_window.show()
        main_window.inventory_page.refresh_page()

    login_window.login_successful.connect(on_login_success)
    login_window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()