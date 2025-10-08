import sys
import traceback
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QGroupBox, QApplication, QMainWindow
)
from PyQt6.QtCore import Qt
from sqlalchemy import text
import qtawesome as qta

# --- MOCK DATABASE SETUP FOR STANDALONE EXECUTION ---

# Mock data matching the columns retrieved by _load_transactions
MOCK_TRANSACTION_DATA = [
    {'id': 105, 'transaction_date': '2023-11-01', 'transaction_type': 'PGR', 'source_ref_no': 'PROD005',
     'product_code': 'FG-B02', 'lot_number': 'L231105', 'quantity_in': 500.00, 'quantity_out': 0, 'unit': 'BOX',
     'warehouse': 'WH2', 'encoded_by': 'ADMIN'},
    {'id': 104, 'transaction_date': '2023-10-30', 'transaction_type': 'PGI', 'source_ref_no': 'SHIP004',
     'product_code': 'FG-A01', 'lot_number': 'L231002', 'quantity_in': 0, 'quantity_out': 250.50, 'unit': 'BAG',
     'warehouse': 'WH1', 'encoded_by': 'JANE'},
    {'id': 103, 'transaction_date': '2023-10-28', 'transaction_type': 'PGR', 'source_ref_no': 'PROD003',
     'product_code': 'FG-C03', 'lot_number': 'L231003', 'quantity_in': 100.00, 'quantity_out': 0, 'unit': 'PC',
     'warehouse': 'WH3', 'encoded_by': 'JOHN'},
    {'id': 102, 'transaction_date': '2023-10-27', 'transaction_type': 'PGR', 'source_ref_no': 'PROD002',
     'product_code': 'FG-A01', 'lot_number': 'L231001', 'quantity_in': 300.75, 'quantity_out': 0, 'unit': 'BAG',
     'warehouse': 'WH1', 'encoded_by': 'JANE'},
    {'id': 101, 'transaction_date': '2023-10-26', 'transaction_type': 'PGI', 'source_ref_no': 'SHIP001',
     'product_code': 'FG-B02', 'lot_number': 'L231005', 'quantity_in': 0, 'quantity_out': 150.00, 'unit': 'BOX',
     'warehouse': 'WH2', 'encoded_by': 'ADMIN'},
]


class MockResult:
    """Simulates SQLAlchemy result object."""

    def __init__(self, data):
        self._data = data

    def mappings(self):
        # FIX: Return self to allow chaining to .all()
        return self

    def all(self):
        # Returns the list of dicts
        return self._data


class MockConnection:
    """Simulates SQLAlchemy connection object."""

    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def execute(self, query, params=None):
        # Basic filtering logic for demonstration
        search_term = params.get('search', '').strip('%').upper() if params and 'search' in params else ''

        filtered_data = []
        if search_term:
            for row in self.data:
                # Mock search logic
                if (search_term in str(row['product_code']).upper() or
                        search_term in str(row['lot_number']).upper() or
                        search_term in str(row['source_ref_no']).upper() or
                        search_term in str(row['transaction_type']).upper()):
                    filtered_data.append(row)
        else:
            filtered_data = self.data

        return MockResult(filtered_data)


class MockEngine:
    """Simulates SQLAlchemy engine object."""

    def connect(self):
        return MockConnection(MOCK_TRANSACTION_DATA)


# --- END MOCK DATABASE SETUP ---


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
        # Initial load of data
        self.refresh_page()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # --- Header (Icon, Title) and Instruction ---

        # 1. Header Layout
        header_layout = QHBoxLayout()

        # Icon
        icon_label = QLabel()
        icon_label.setPixmap(qta.icon('fa5s.exchange-alt', color='#1E88E5').pixmap(32, 32))
        header_layout.addWidget(icon_label)

        # Header FG Passed Transaction
        title_label = QLabel("FG Passed Transaction")
        title_label.setStyleSheet("font-size: 20pt; font-weight: bold; color: #1E88E5;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        main_layout.addLayout(header_layout)

        # Instruction
        instruction_label = QLabel(
            "Use the filters below to search for specific Finished Goods transactions (In/Out).")
        instruction_label.setWordWrap(True)
        main_layout.addWidget(instruction_label)

        # ------------------------------------------------

        # --- Top layout for controls inside a group box ---
        controls_group = QGroupBox("Filters & Actions")
        controls_layout = QHBoxLayout(controls_group)

        controls_layout.addWidget(QLabel("Search Transactions:"))
        self.search_edit = UpperCaseLineEdit()
        self.search_edit.setPlaceholderText("Filter by Product, Lot, Source Ref No...")
        controls_layout.addWidget(self.search_edit, 1)  # Add stretch factor

        self.refresh_button = QPushButton("Refresh")
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
                background-color: #3a506b; /* Dark blue selection */
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
                    params['search'] = f"%{search_term}%"

                query = text(base_query)
                # This now works because conn.execute returns MockResult,
                # .mappings() returns self, and .all() returns the data list.
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
            QMessageBox.critical(self, "Database Error (Mock/Real)", f"Failed to load transactions: {e}")
            print(traceback.format_exc())


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # 1. Setup Mock Dependencies
    mock_db_engine = MockEngine()
    mock_username = "STANDALONE_USER"


    def mock_log(action, details):
        print(f"[AUDIT LOG MOCK] User: {mock_username}, Action: {action}, Details: {details}")


    # 2. Create Main Window
    main_window = QMainWindow()
    main_window.setWindowTitle("Standalone Inventory Transaction Viewer")

    # 3. Instantiate the Form Page
    transaction_page = TransactionsFormPage(
        engine=mock_db_engine,
        username=mock_username,
        log_audit_trail_func=mock_log
    )

    # 4. Set the Form as the Central Widget
    main_window.setCentralWidget(transaction_page)
    main_window.resize(1000, 600)
    main_window.show()

    sys.exit(app.exec())