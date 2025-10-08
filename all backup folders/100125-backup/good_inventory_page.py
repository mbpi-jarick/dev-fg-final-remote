import traceback
from decimal import Decimal
import pandas as pd

from PyQt6.QtCore import Qt, QObject, pyqtSignal, QThread, QDate
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
                             QHeaderView, QMessageBox, QHBoxLayout, QLabel,
                             QPushButton, QLineEdit, QAbstractItemView, QDateEdit,
                             QGroupBox)  # QTabWidget, QSplitter, QFormLayout removed
from sqlalchemy import text


# --- Custom UpperCaseLineEdit Widget ---
class UpperCaseLineEdit(QLineEdit):
    """A QLineEdit that automatically converts its text to uppercase."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.textChanged.connect(self._to_upper)

    def _to_upper(self, text: str):
        self.blockSignals(True)
        self.setText(text.upper())
        self.blockSignals(False)


# --- WORKER: For Calculating Inventory Summary (Only Worker 1 remains) ---
class InventoryWorker(QObject):
    finished = pyqtSignal(pd.DataFrame)
    error = pyqtSignal(str)

    def __init__(self, engine, lot_filter=None, as_of_date=None):
        super().__init__()
        self.engine = engine
        self.lot_filter = lot_filter
        self.as_of_date = as_of_date

    def run(self):
        try:
            date_condition = f"AND transaction_date <= '{self.as_of_date}'" if self.as_of_date else ""
            lot_filter_clause = ""
            params = {}
            if self.lot_filter:
                lot_filter_clause = "AND lot_number = :lot"
                params['lot'] = self.lot_filter.strip().upper()

            query_str = f"""
                WITH combined_movements AS (
                    SELECT
                        UPPER(TRIM(product_code)) AS product_code, UPPER(TRIM(lot_number)) AS lot_number,
                        CAST(qty AS NUMERIC) AS quantity_in, 0.0 AS quantity_out
                    FROM beginv_sheet1
                    WHERE product_code IS NOT NULL AND TRIM(product_code) <> '' AND lot_number IS NOT NULL AND TRIM(lot_number) <> ''
                    UNION ALL
                    SELECT
                        UPPER(TRIM(product_code)) AS product_code, UPPER(TRIM(lot_number)) AS lot_number,
                        quantity_in, quantity_out
                    FROM transactions
                    WHERE product_code IS NOT NULL AND TRIM(product_code) <> '' AND lot_number IS NOT NULL AND TRIM(lot_number) <> '' {date_condition}
                )
                SELECT MAX(product_code) AS product_code, lot_number,
                       COALESCE(SUM(quantity_in), 0) - COALESCE(SUM(quantity_out), 0) AS current_balance
                FROM combined_movements WHERE 1=1 {lot_filter_clause}
                GROUP BY lot_number
                HAVING (COALESCE(SUM(quantity_in), 0) - COALESCE(SUM(quantity_out), 0)) > 0.001
                ORDER BY lot_number;
            """
            with self.engine.connect() as conn:
                results = conn.execute(text(query_str), params).mappings().all()
            df = pd.DataFrame(results) if results else pd.DataFrame(
                columns=['product_code', 'lot_number', 'current_balance'])
            self.finished.emit(df)
        except Exception as e:
            self.error.emit(f"Database query failed: {e}")
            traceback.print_exc()


# --- Main Page Class (Simplified) ---
class GoodInventoryPage(QWidget):
    def __init__(self, engine, username=None, log_audit_trail_func=None):
        super().__init__()
        self.engine = engine
        self.inventory_thread, self.inventory_worker = None, None
        # self.history_thread, self.history_worker = None, None # Removed
        # self.current_history_df = None # Removed
        self.init_ui()
        self.setStyleSheet(self._get_styles())

    def _get_styles(self):
        # --- MODERNIZED STYLESHEET ---
        return """
            QTableWidget { outline: 0; } /* Removes focus rectangle */
            QTableWidget::item:selected {
                background-color: #2596be; /* Dark blue selection */
                color: white;
            }
            #TotalBalanceLabel { color: #007BFF; }
            QGroupBox { font-weight: bold; }
        """

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # --- Filter controls ---
        filter_group = self._create_filter_controls()
        main_layout.addWidget(filter_group)

        # --- Inventory Summary (Now main content, no QTabWidget) ---
        self.inventory_table = self._create_inventory_table()
        self.total_balance_label = QLabel("Total Balance: 0.00 kg", objectName="TotalBalanceLabel")
        self.total_balance_label.setStyleSheet("font-size: 14pt; font-weight: bold; padding: 10px;")
        self.total_balance_label.setAlignment(Qt.AlignmentFlag.AlignRight)

        main_layout.addWidget(self.inventory_table, 1)
        main_layout.addWidget(self.total_balance_label)

        # --- Connections ---
        self.refresh_button.clicked.connect(self._start_inventory_calculation)
        self.date_picker.dateChanged.connect(self._start_inventory_calculation)
        self.lot_number_input.returnPressed.connect(self._start_inventory_calculation)
        # Removed connections related to history/selection change

    def _create_filter_controls(self):
        # --- FILTER GROUPBOX ---
        controls_group = QGroupBox("Filters & Actions (Inventory Summary)")
        filter_layout = QHBoxLayout(controls_group)

        filter_layout.addWidget(QLabel("As Of:"))
        self.date_picker = QDateEdit(calendarPopup=True, date=QDate.currentDate(), displayFormat="yyyy-MM-dd")
        self.date_picker.setMinimumWidth(120)
        filter_layout.addWidget(self.date_picker)

        filter_layout.addSpacing(20)

        filter_layout.addWidget(QLabel("Search Lot:"))
        self.lot_number_input = UpperCaseLineEdit(placeholderText="Enter Specific Lot or Leave Blank for All...")
        filter_layout.addWidget(self.lot_number_input, 1)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setObjectName("PrimaryButton")
        filter_layout.addWidget(self.refresh_button)

        return controls_group

    def _configure_table(self, table: QTableWidget):
        """Helper function to apply consistent styling to all tables."""
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.verticalHeader().setVisible(False)
        table.setShowGrid(False)  # Cleaner look
        table.horizontalHeader().setHighlightSections(False)

    def _create_inventory_table(self):
        table = QTableWidget(columnCount=3)
        self._configure_table(table)
        table.setHorizontalHeaderLabels(["Associated Product", "Lot Number", "Current Balance (kg)"])
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        return table

    # Removed: _create_history_table, _create_history_tab_layout, _clear_history_tab, _clear_history_details, _on_lot_selected, _on_history_finished, _display_history, _on_history_item_selected

    def refresh_page(self):
        self.lot_number_input.clear()
        self.date_picker.setDate(QDate.currentDate())
        self._start_inventory_calculation()

    def _start_inventory_calculation(self):
        lot_filter = self.lot_number_input.text().strip()
        as_of_date = self.date_picker.date().toString(Qt.DateFormat.ISODate)

        self.set_controls_enabled(False)
        self._show_loading_state(self.inventory_table, "Calculating inventory balance...")

        self.inventory_thread = QThread()
        self.inventory_worker = InventoryWorker(self.engine, lot_filter, as_of_date)
        self.inventory_worker.moveToThread(self.inventory_thread)

        self.inventory_thread.started.connect(self.inventory_worker.run)
        self.inventory_worker.finished.connect(self._on_inventory_finished)
        self.inventory_worker.error.connect(self._on_calculation_error)

        self.inventory_worker.finished.connect(self.inventory_thread.quit)
        self.inventory_worker.finished.connect(self.inventory_worker.deleteLater)
        self.inventory_thread.finished.connect(self.inventory_thread.deleteLater)
        self.inventory_thread.start()

    def set_controls_enabled(self, enabled):
        self.lot_number_input.setEnabled(enabled)
        self.refresh_button.setEnabled(enabled)
        self.date_picker.setEnabled(enabled)

    def _on_inventory_finished(self, df):
        is_specific_lot = bool(self.lot_number_input.text().strip())
        self._display_inventory(df, is_specific_lot)
        self.set_controls_enabled(True)

    def _on_calculation_error(self, error_message):
        QMessageBox.critical(self, "Calculation Error", error_message)
        self.inventory_table.setRowCount(0)
        self.set_controls_enabled(True)

    def _show_loading_state(self, table, message):
        table.setRowCount(1)
        table.setSpan(0, 0, 1, table.columnCount())
        loading_item = QTableWidgetItem(message)
        loading_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        table.setItem(0, 0, loading_item)

    def _display_inventory(self, df, is_specific_lot):
        self.inventory_table.setRowCount(0)
        self.inventory_table.setSpan(0, 0, 1, 1)
        total_balance = df['current_balance'].sum()
        self.inventory_table.setRowCount(len(df))

        for i, row in df.iterrows():
            qty_item = QTableWidgetItem(f"{Decimal(row.get('current_balance', 0)):.2f}")
            qty_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.inventory_table.setItem(i, 0, QTableWidgetItem(str(row.get('product_code', ''))))
            self.inventory_table.setItem(i, 1, QTableWidgetItem(str(row.get('lot_number', ''))))
            self.inventory_table.setItem(i, 2, qty_item)

        label_text = f"Total Balance: {total_balance:.2f} kg" if is_specific_lot and len(
            df) > 0 else f"Overall Total Balance: {total_balance:.2f} kg"
        self.total_balance_label.setText(label_text)