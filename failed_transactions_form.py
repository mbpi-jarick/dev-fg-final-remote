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

# Mock data for failed transactions (note: source table name is 'failed_transactions')
MOCK_FAILED_TRANSACTION_DATA = [
    {'id': 203, 'transaction_date': '2023-11-03', 'transaction_type': 'PGI', 'source_ref_no': 'SHIP006',
     'product_code': 'FG-D04', 'lot_number': 'L231103', 'quantity_in': 0, 'quantity_out': 100.00, 'unit': 'BAG',
     'warehouse': 'WH1', 'encoded_by': 'JANE'},
    {'id': 202, 'transaction_date': '2023-11-02', 'transaction_type': 'PGR', 'source_ref_no': 'PROD006',
     'product_code': 'FG-E05', 'lot_number': 'L231102', 'quantity_in': 50.00, 'quantity_out': 0, 'unit': 'PC',
     'warehouse': 'WH3', 'encoded_by': 'JOHN'},
    {'id': 201, 'transaction_date': '2023-11-01', 'transaction_type': 'PGI', 'source_ref_no': 'SHIP005',
     'product_code': 'FG-A01', 'lot_number': 'L231002', 'quantity_in': 0, 'quantity_out': 500.00, 'unit': 'BAG',
     'warehouse': 'WH1', 'encoded_by': 'ADMIN'},
]


class MockResult:
    """Simulates SQLAlchemy result object, fixed for .mappings().all() chaining."""

    def __init__(self, data):
        self._data = data

    def mappings(self):
        # Return self to allow chaining
        return self

    def all(self):
        # Returns the list of dicts
        return self._data


class MockConnection:
    """Simulates SQLAlchemy connection object with basic filtering."""

    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def execute(self, query, params=None):
        search_term = params.get('search', '').strip('%').upper() if params and 'search' in params else ''

        filtered_data = []
        if search_term:
            for row in self.data:
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
        # Connects to the mock failed data
        return MockConnection(MOCK_FAILED_TRANSACTION_DATA)


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


class FailedTransactionsFormPage(QWidget):
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

        # Colored icon qtawsome (Warning icon, Red color)
        icon_label = QLabel()
        icon_label.setPixmap(qta.icon('fa5s.exclamation-triangle', color='#dc3545').pixmap(32, 32))  # Red
        header_layout.addWidget(icon_label)

        # Header FG Failed Transaction
        title_label = QLabel("FG Failed Transaction")
        title_label.setStyleSheet("font-size: 15pt; font-weight: bold; color: #dc3545;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        main_layout.addLayout(header_layout)

        # Instruction
        instruction_label = QLabel(
            "This list shows transactions that failed processing (e.g., insufficient stock or missing master data).")
        instruction_label.setWordWrap(True)
        main_layout.addWidget(instruction_label)

        # ------------------------------------------------

        # --- Top layout for controls inside a group box ---
        controls_group = QGroupBox("Filters & Actions")
        controls_layout = QHBoxLayout(controls_group)

        controls_layout.addWidget(QLabel("Search Failed Transactions:"))
        self.search_edit = UpperCaseLineEdit()
        self.search_edit.setPlaceholderText("Filter by Product, Lot, Source Ref No...")
        controls_layout.addWidget(self.search_edit, 1)  # Add stretch factor

        self.refresh_button = QPushButton("Refresh")
        # REQUIREMENT: light color buttons only (Removed object name 'PrimaryButton')
        # self.refresh_button.setObjectName("PrimaryButton") <-- REMOVED
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
                    FROM failed_transactions 
                """

                params = {}
                if search_term:
                    # SQL query portion is still structured for a real DB connection
                    base_query += """
                        WHERE product_code ILIKE :search OR 
                              lot_number ILIKE :search OR
                              source_ref_no ILIKE :search OR
                              transaction_type ILIKE :search
                    """
                    params['search'] = f"%{search_term}%"

                base_query += " ORDER BY id DESC"

                query = text(base_query)
                # The execution uses the MockEngine/MockConnection structure
                result = conn.execute(query, params).mappings().all()

                self.table_widget.setRowCount(len(result))
                for row_idx, row_data in enumerate(result):
                    self.table_widget.setItem(row_idx, 0, QTableWidgetItem(str(row_data.get('id', ''))))
                    self.table_widget.setItem(row_idx, 1, QTableWidgetItem(str(row_data.get('transaction_date', ''))))
                    self.table_widget.setItem(row_idx, 2, QTableWidgetItem(str(row_data.get('transaction_type', ''))))
                    self.table_widget.setItem(row_idx, 3, QTableWidgetItem(str(row_data.get('source_ref_no', ''))))
                    self.table_widget.setItem(row_idx, 4, QTableWidgetItem(str(row_data.get('product_code', ''))))
                    self.table_widget.setItem(row_idx, 5, QTableWidgetItem(str(row_data.get('lot_number', ''))))

                    # Format numeric columns to 2 decimal places and align right
                    qty_in = row_data.get('quantity_in', 0.0) or 0.0
                    # --- CHANGE HERE: Added comma (,) for thousands separator ---
                    qty_in_item = QTableWidgetItem(f"{float(qty_in):,.2f}")
                    # -----------------------------------------------------------
                    qty_in_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    self.table_widget.setItem(row_idx, 6, qty_in_item)

                    qty_out = row_data.get('quantity_out', 0.0) or 0.0
                    # --- CHANGE HERE: Added comma (,) for thousands separator ---
                    qty_out_item = QTableWidgetItem(f"{float(qty_out):,.2f}")
                    # -----------------------------------------------------------
                    qty_out_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    self.table_widget.setItem(row_idx, 7, qty_out_item)

                    self.table_widget.setItem(row_idx, 8, QTableWidgetItem(str(row_data.get('unit', ''))))
                    self.table_widget.setItem(row_idx, 9, QTableWidgetItem(str(row_data.get('warehouse', ''))))
                    self.table_widget.setItem(row_idx, 10, QTableWidgetItem(str(row_data.get('encoded_by', ''))))

        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Failed to load transactions: {e}")
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
    main_window.setWindowTitle("Standalone Failed Transaction Viewer")

    # 3. Instantiate the Form Page
    transaction_page = FailedTransactionsFormPage(
        engine=mock_db_engine,
        username=mock_username,
        log_audit_trail_func=mock_log
    )

    # 4. Set the Form as the Central Widget
    main_window.setCentralWidget(transaction_page)
    main_window.resize(1000, 600)
    main_window.show()

    sys.exit(app.exec())