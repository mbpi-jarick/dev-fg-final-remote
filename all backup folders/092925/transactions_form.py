# transactions_form.py
# REVISED - Modernized UI with icons, group boxes, and improved table styling.
# REVISED - Selected rows are now highlighted in dark blue.
# MODIFIED - Removed focus rectangle ("square") from the table for a cleaner UI.

import traceback
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
                             QMessageBox, QGroupBox, QStyle)
from PyQt6.QtCore import Qt
from sqlalchemy import text


class UpperCaseLineEdit(QLineEdit):
    """A QLineEdit that automatically converts its text to uppercase."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.textChanged.connect(self._to_upper)

    def _to_upper(self, text: str):
        self.blockSignals(True)
        self.setText(text.upper())
        self.blockSignals(False)


class TransactionsFormPage(QWidget):
    def __init__(self, engine, username, log_audit_trail_func):
        super().__init__()
        self.engine = engine
        self.username = username
        self.log_audit_trail = log_audit_trail_func
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # --- Top layout for controls inside a group box ---
        controls_group = QGroupBox("Filters & Actions")
        controls_layout = QHBoxLayout(controls_group)

        controls_layout.addWidget(QLabel("Search Transactions:"))
        self.search_edit = UpperCaseLineEdit()
        self.search_edit.setPlaceholderText("Filter by Product, Lot, Source Ref No...")
        controls_layout.addWidget(self.search_edit, 1)  # Add stretch factor

        self.refresh_button = QPushButton(" Refresh")
        self.refresh_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        self.refresh_button.setObjectName("PrimaryButton")
        controls_layout.addWidget(self.refresh_button)

        main_layout.addWidget(controls_group)

        # --- Table Widget for Displaying All Transactions ---
        self.table_widget = QTableWidget()
        self.table_widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table_widget.setColumnCount(11)
        self.table_widget.setHorizontalHeaderLabels([
            "ID", "Date", "Type", "Source Ref", "Product Code",
            "Lot Number", "Qty In", "Qty Out", "Unit", "Warehouse", "Encoded By"
        ])
        self.table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table_widget.horizontalHeader().setStretchLastSection(True)
        self.table_widget.horizontalHeader().setHighlightSections(False)
        self.table_widget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_widget.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_widget.verticalHeader().setVisible(False)
        self.table_widget.setShowGrid(False)  # Cleaner look
        main_layout.addWidget(self.table_widget, 1)  # Add stretch factor

        # --- Apply Stylesheet for selected items ---
        self.setStyleSheet("""
            QTableWidget::item:selected {
                background-color: #007BFF; /* Dark blue selection */
                color: white;
            }
        """)

        # --- Connections ---
        self.search_edit.textChanged.connect(self._load_transactions)
        self.refresh_button.clicked.connect(self.refresh_page)

    def refresh_page(self):
        """Called when the page is shown or refresh is clicked."""
        self.search_edit.blockSignals(True)
        self.search_edit.clear()
        self.search_edit.blockSignals(False)
        self._load_transactions()

    def _load_transactions(self):
        self.table_widget.setRowCount(0)
        search_term = self.search_edit.text().strip()

        try:
            with self.engine.connect() as conn:
                base_query = """
                    SELECT id, transaction_date, transaction_type, source_ref_no, product_code, 
                           lot_number, quantity_in, quantity_out, unit, warehouse, encoded_by
                    FROM transactions 
                """

                params = {}
                if search_term:
                    base_query += """
                        WHERE product_code ILIKE :search OR 
                              lot_number ILIKE :search OR
                              source_ref_no ILIKE :search OR
                              transaction_type ILIKE :search
                    """
                    params['search'] = f"%{search_term}%"

                base_query += " ORDER BY id DESC"  # Changed to ID for more stable ordering

                query = text(base_query)
                result = conn.execute(query, params).mappings().all()

                self.table_widget.setRowCount(len(result))
                for row_idx, row_data in enumerate(result):
                    self.table_widget.setItem(row_idx, 0, QTableWidgetItem(str(row_data.get('id', ''))))
                    self.table_widget.setItem(row_idx, 1, QTableWidgetItem(str(row_data.get('transaction_date', ''))))
                    self.table_widget.setItem(row_idx, 2, QTableWidgetItem(str(row_data.get('transaction_type', ''))))
                    self.table_widget.setItem(row_idx, 3, QTableWidgetItem(str(row_data.get('source_ref_no', ''))))
                    self.table_widget.setItem(row_idx, 4, QTableWidgetItem(str(row_data.get('product_code', ''))))
                    self.table_widget.setItem(row_idx, 5, QTableWidgetItem(str(row_data.get('lot_number', ''))))

                    # Format numeric columns
                    qty_in_item = QTableWidgetItem(f"{row_data.get('quantity_in', 0):.2f}")
                    qty_in_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    self.table_widget.setItem(row_idx, 6, qty_in_item)

                    qty_out_item = QTableWidgetItem(f"{row_data.get('quantity_out', 0):.2f}")
                    qty_out_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    self.table_widget.setItem(row_idx, 7, qty_out_item)

                    self.table_widget.setItem(row_idx, 8, QTableWidgetItem(str(row_data.get('unit', ''))))
                    self.table_widget.setItem(row_idx, 9, QTableWidgetItem(str(row_data.get('warehouse', ''))))
                    self.table_widget.setItem(row_idx, 10, QTableWidgetItem(str(row_data.get('encoded_by', ''))))


        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Failed to load transactions: {e}")
            print(traceback.format_exc())