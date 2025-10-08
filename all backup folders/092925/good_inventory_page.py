# good_inventory_page.py
# FINAL VERSION - Includes date filtering, blank record filtering, styling fixes,
# Lot Number normalization (critical for inventory accuracy), and UI tweaks.

import traceback
from decimal import Decimal

# Note: You must have pandas installed for this file to work: pip install pandas
import pandas as pd

from PyQt6.QtCore import Qt, QObject, pyqtSignal, QThread, QDate
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
                             QHeaderView, QMessageBox, QHBoxLayout, QLabel,
                             QPushButton, QComboBox, QAbstractItemView, QDateEdit, QStyle)
from sqlalchemy import text


# --- Worker Object for Threading ---
class InventoryWorker(QObject):
    finished = pyqtSignal(pd.DataFrame)
    error = pyqtSignal(str)

    def __init__(self, engine, product_filter=None, as_of_date=None):
        super().__init__()
        self.engine = engine
        self.product_filter = product_filter
        self.as_of_date = as_of_date  # Format: YYYY-MM-DD string

    def run(self):
        try:
            # Date filter to apply to transactions
            date_condition = ""
            if self.as_of_date:
                # Transactions must have occurred ON or BEFORE the specified date
                date_condition = f"AND transaction_date <= '{self.as_of_date}'"

            # Product filter logic setup
            product_filter_clause = ""
            params = {}
            if self.product_filter:
                # We normalize the filter input to match the normalized columns in the final SELECT
                product_filter_clause = "AND product_code = :pcode"
                params['pcode'] = self.product_filter.strip().upper()  # Normalize filter input

            # --- MODIFIED SQL QUERY: Historical Inventory Calculation + LOT NORMALIZATION ---
            query_str = f"""
                WITH combined_movements AS (
                    -- 1. Beginning Inventory (Treated as an initial IN movement)
                    SELECT
                        UPPER(TRIM(product_code)) AS product_code, 
                        UPPER(TRIM(lot_number)) AS lot_number, -- <<< NORMALIZED
                        CAST(qty AS NUMERIC) AS quantity_in, 
                        0.0 AS quantity_out 
                    FROM beginv_sheet1
                    -- Filter out blanks from beginv_sheet1
                    WHERE product_code IS NOT NULL AND TRIM(product_code) != ''
                    AND lot_number IS NOT NULL AND TRIM(lot_number) != ''

                    UNION ALL

                    -- 2. Transactions (Filtered by Date)
                    SELECT 
                        UPPER(TRIM(product_code)) AS product_code, 
                        UPPER(TRIM(lot_number)) AS lot_number, -- <<< NORMALIZED
                        quantity_in, 
                        quantity_out
                    FROM transactions
                    -- Filter out blanks from transactions + Apply date filter
                    WHERE product_code IS NOT NULL AND TRIM(product_code) != ''
                    AND lot_number IS NOT NULL AND TRIM(lot_number) != ''
                    {date_condition} 
                )
                SELECT
                    product_code, lot_number,
                    COALESCE(SUM(quantity_in), 0) - COALESCE(SUM(quantity_out), 0) AS current_balance
                FROM combined_movements
                WHERE 1=1 {product_filter_clause} -- Apply product filter (using AND)
                GROUP BY product_code, lot_number
            """

            final_query = text(query_str)

            with self.engine.connect() as conn:
                results = conn.execute(final_query, params).mappings().all()

            df = pd.DataFrame(results) if results else pd.DataFrame(
                columns=['product_code', 'lot_number', 'current_balance'])

            self.finished.emit(df)
        except Exception as e:
            self.error.emit(f"Database query failed: {e}")
            traceback.print_exc()


class GoodInventoryPage(QWidget):
    def __init__(self, engine, username=None, log_audit_trail_func=None):
        super().__init__()
        self.engine = engine
        self.thread = None
        self.worker = None
        self.init_ui()
        self.setStyleSheet(self._get_styles())  # Apply styles after widgets are created

    def _get_styles(self):
        """Custom styles for the table and labels."""
        return """
            QTableWidget {
                /* Fix: Remove focus rectangle (the square box) */
                outline: 0; 
            }
            QTableWidget::item:selected {
                /* Requested selected row color */
                background-color: #007BFF; 
                color: white;
            }
            #TotalBalanceLabel {
                /* Requested font color for the total label */
                color: #007BFF; 
            }
        """

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        # --- Filters & Controls Group ---
        filter_group_box = QWidget()
        filter_layout = QHBoxLayout(filter_group_box)

        # 1. Date Picker (Historical Inventory)
        self.date_picker = QDateEdit(calendarPopup=True)
        self.date_picker.setDate(QDate.currentDate())
        self.date_picker.setDisplayFormat("yyyy-MM-dd")
        self.date_picker.setMinimumWidth(120)

        # 2. Product Code Combo
        self.product_code_combo = QComboBox(editable=True)
        self.product_code_combo.setPlaceholderText("All Products...")
        self.product_code_combo.setMinimumWidth(200)

        # 3. Action Button
        self.check_specific_btn = QPushButton("Calculate Inventory")
        self.check_specific_btn.setObjectName("PrimaryButton")

        filter_layout.addWidget(QLabel("<b>Inventory As Of:</b>"))
        filter_layout.addWidget(self.date_picker)
        filter_layout.addSpacing(20)
        filter_layout.addWidget(QLabel("<b>Product Code:</b>"))
        filter_layout.addWidget(self.product_code_combo, 1)
        filter_layout.addWidget(self.check_specific_btn)
        filter_layout.addStretch()
        layout.addWidget(filter_group_box)

        # --- Table Widget ---
        self.inventory_table = QTableWidget(columnCount=3)
        self.inventory_table.setHorizontalHeaderLabels(["Product Code", "Lot Number", "Current Balance (kg)"])
        self.inventory_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.inventory_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.inventory_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # FIX: Remove row numbering on the left side
        self.inventory_table.verticalHeader().setVisible(False)

        header = self.inventory_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.inventory_table, 1)

        # --- Total Balance Label (Styled) ---
        self.total_balance_label = QLabel("Total Balance: 0.00 kg", objectName="TotalBalanceLabel")
        self.total_balance_label.setFont(self.font())
        self.total_balance_label.setStyleSheet("font-size: 14pt; font-weight: bold; padding: 10px;")
        self.total_balance_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.total_balance_label)

        # --- Connections ---
        self.check_specific_btn.clicked.connect(self._start_inventory_calculation)
        self.date_picker.dateChanged.connect(self._start_inventory_calculation)

        self._load_product_codes()

    def refresh_page(self):
        """Called when the page is shown."""
        self._load_product_codes()
        self.product_code_combo.setCurrentIndex(0)
        self.date_picker.setDate(QDate.currentDate())
        self._start_inventory_calculation()

    def _load_product_codes(self):
        """Loads distinct product codes from both inventory sources."""
        try:
            with self.engine.connect() as conn:
                # Query combining normalized product codes from both tables, excluding blanks
                query = text("""
                    SELECT UPPER(TRIM(product_code)) FROM transactions 
                    WHERE product_code IS NOT NULL AND TRIM(product_code) != ''
                    UNION 
                    SELECT UPPER(TRIM(product_code)) FROM beginv_sheet1 
                    WHERE product_code IS NOT NULL AND TRIM(product_code) != ''
                    ORDER BY 1;
                """)
                result = conn.execute(query).scalars().all()

            self.product_code_combo.blockSignals(True)
            self.product_code_combo.clear()
            self.product_code_combo.addItem("")  # For 'All Products'
            self.product_code_combo.addItems(result)
            self.product_code_combo.blockSignals(False)
        except Exception as e:
            if 'relation "beginv_sheet1" does not exist' not in str(e):
                QMessageBox.warning(self, "Load Error", f"Could not load product codes: {e}")

    def _start_inventory_calculation(self):
        """Collects filters and starts the calculation thread."""
        product_filter = self.product_code_combo.currentText().strip()

        # Get the date as YYYY-MM-DD string
        as_of_date = self.date_picker.date().toString(Qt.DateFormat.ISODate)

        self.set_controls_enabled(False)
        self._show_loading_state()

        self.thread = QThread()
        # Pass the date filter to the worker
        self.worker = InventoryWorker(self.engine, product_filter, as_of_date)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._on_calculation_finished)
        self.worker.error.connect(self._on_calculation_error)

        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        self.thread.start()

    def _on_calculation_finished(self, df):
        is_specific = bool(self.product_code_combo.currentText().strip())

        # Filter for positive balances and sort
        # FIX: Sort primarily by Lot Number, then Product Code
        df = df[df['current_balance'] > 0.001].sort_values(by=['lot_number', 'product_code'])

        self._display_inventory(df, is_specific_product=is_specific)
        self.set_controls_enabled(True)

    def _on_calculation_error(self, error_message):
        QMessageBox.critical(self, "Calculation Error", error_message)
        self.inventory_table.setRowCount(0)
        self.set_controls_enabled(True)

    def set_controls_enabled(self, enabled):
        self.product_code_combo.setEnabled(enabled)
        self.check_specific_btn.setEnabled(enabled)
        self.date_picker.setEnabled(enabled)

    def _show_loading_state(self):
        self.inventory_table.setRowCount(1)
        loading_item = QTableWidgetItem("Calculating inventory balance...")
        loading_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.inventory_table.setItem(0, 0, loading_item)
        self.inventory_table.setSpan(0, 0, 1, self.inventory_table.columnCount())
        self.total_balance_label.setText("Calculating...")

    def _display_inventory(self, df, is_specific_product):
        self.inventory_table.setRowCount(0)
        self.inventory_table.setSpan(0, 0, 1, 1)

        total_balance = Decimal(df['current_balance'].sum())
        self.inventory_table.setRowCount(len(df))

        for i, row in df.iterrows():
            self.inventory_table.setItem(i, 0, QTableWidgetItem(str(row.get('product_code', ''))))
            self.inventory_table.setItem(i, 1, QTableWidgetItem(str(row.get('lot_number', ''))))

            qty_item = QTableWidgetItem(f"{Decimal(row.get('current_balance', 0)):.2f}")
            qty_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.inventory_table.setItem(i, 2, qty_item)

        # Update the total label text
        if is_specific_product:
            self.total_balance_label.setText(f"Total Balance for Product: {total_balance:.2f} kg")
        else:
            self.total_balance_label.setText(f"Overall Total Balance (All Products): {total_balance:.2f} kg")