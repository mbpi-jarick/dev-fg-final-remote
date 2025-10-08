import traceback
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
                             QMessageBox)
from PyQt6.QtCore import Qt
from sqlalchemy import text


class FailedTransactionsFormPage(QWidget):
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

        # --- Top layout for controls ---
        controls_layout = QHBoxLayout()
        controls_layout.addWidget(QLabel("Search FG Failed Transactions:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filter by Product, Lot, Source Ref No...")
        controls_layout.addWidget(self.search_edit)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setObjectName("PrimaryButton")
        controls_layout.addWidget(self.refresh_button)

        main_layout.addLayout(controls_layout)

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
        self.table_widget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_widget.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_widget.verticalHeader().setVisible(False)
        main_layout.addWidget(self.table_widget)

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
                    FROM failed_transactions 
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

                base_query += " ORDER BY encoded_on DESC"

                query = text(base_query)
                result = conn.execute(query, params)

                for row_data in result:
                    row = self.table_widget.rowCount()
                    self.table_widget.insertRow(row)
                    for col, value in enumerate(row_data):
                        item = QTableWidgetItem(str(value if value is not None else ""))
                        if col in [6, 7]:  # quantity_in, quantity_out
                            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                        self.table_widget.setItem(row, col, item)

        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Failed to load transactions: {e}")
            print(traceback.format_exc())