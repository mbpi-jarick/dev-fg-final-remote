import sys
import traceback
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QGroupBox, QApplication, QMainWindow
)
from PyQt6.QtCore import Qt
from sqlalchemy import text, create_engine
import qtawesome as qta


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
        self.refresh_page()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        header_layout = QHBoxLayout()
        icon_label = QLabel()
        icon_label.setPixmap(qta.icon('fa5s.exclamation-triangle', color='#dc3545').pixmap(32, 32))
        header_layout.addWidget(icon_label)
        title_label = QLabel("FG Failed Transaction")
        title_label.setStyleSheet("font-size: 15pt; font-weight: bold; color: #dc3545;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        instruction_label = QLabel(
            "This list shows transactions for items in the FAILED inventory (e.g., QC failures, returns).")
        instruction_label.setWordWrap(True)
        main_layout.addWidget(instruction_label)

        controls_group = QGroupBox("Filters & Actions")
        controls_layout = QHBoxLayout(controls_group)
        controls_layout.addWidget(QLabel("Search Failed Transactions:"))
        self.search_edit = UpperCaseLineEdit()
        self.search_edit.setPlaceholderText("Filter by Product, Lot, Source Ref No...")
        controls_layout.addWidget(self.search_edit, 1)
        self.refresh_button = QPushButton("Refresh")
        controls_layout.addWidget(self.refresh_button)
        main_layout.addWidget(controls_group)

        self.table_widget = QTableWidget()
        self.table_widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # --- FIX 1: Increase column count to 12 ---
        self.table_widget.setColumnCount(12)

        # --- FIX 2: Add 'Bag/Box No.' to the header labels ---
        self.table_widget.setHorizontalHeaderLabels([
            "ID", "Date", "Type", "Source Ref", "Product Code",
            "Lot Number", "Bag/Box No.", "Qty In", "Qty Out", "Unit", "Warehouse", "Encoded By"
        ])

        self.table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table_widget.horizontalHeader().setStretchLastSection(True)
        self.table_widget.horizontalHeader().setHighlightSections(False)
        self.table_widget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_widget.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_widget.verticalHeader().setVisible(False)
        self.table_widget.setShowGrid(False)
        main_layout.addWidget(self.table_widget, 1)

        self.setStyleSheet("""
            QTableWidget::item:selected {
                background-color: #3a506b; /* Dark blue selection */
                color: white;
            }
        """)

        self.search_edit.textChanged.connect(self._load_transactions)
        self.refresh_button.clicked.connect(self.refresh_page)

    def refresh_page(self):
        self.search_edit.blockSignals(True)
        self.search_edit.clear()
        self.search_edit.blockSignals(False)
        self._load_transactions()

    def _load_transactions(self):
        self.table_widget.setRowCount(0)
        search_term = self.search_edit.text().strip()

        try:
            with self.engine.connect() as conn:
                # --- FIX 3: Updated SQL query to include joins for bag/box number ---
                base_query = """
                    SELECT 
                        t.id, t.transaction_date, t.transaction_type, t.source_ref_no, t.product_code, 
                        t.lot_number, 
                        COALESCE(
                            b.bag_number, 
                            b.box_number, 
                            qcf.bag_no,
                            ''
                        ) as bag_box_number,
                        t.quantity_in, t.quantity_out, t.unit, t.warehouse, t.encoded_by
                    FROM failed_transactions t
                    LEFT JOIN beg_invfailed1 b ON t.lot_number = b.lot_number
                    LEFT JOIN qcf_endorsements_primary qcf ON t.source_ref_no = qcf.system_ref_no
                """

                where_clauses = []
                params = {}
                if search_term:
                    where_clauses.append(
                        """(t.product_code ILIKE :search OR 
                            t.lot_number ILIKE :search OR 
                            t.source_ref_no ILIKE :search OR
                            t.transaction_type ILIKE :search)"""
                    )
                    params['search'] = f"%{search_term}%"

                if where_clauses:
                    query_string = f"{base_query} WHERE {' AND '.join(where_clauses)} ORDER BY t.id DESC"
                else:
                    query_string = f"{base_query} ORDER BY t.id DESC"

                query = text(query_string)
                result = conn.execute(query, params).mappings().all()

                self.table_widget.setRowCount(len(result))
                for row_idx, row_data in enumerate(result):
                    # --- FIX 4: Updated item placement to match new column order ---
                    self.table_widget.setItem(row_idx, 0, QTableWidgetItem(str(row_data.get('id', ''))))
                    self.table_widget.setItem(row_idx, 1, QTableWidgetItem(str(row_data.get('transaction_date', ''))))
                    self.table_widget.setItem(row_idx, 2, QTableWidgetItem(str(row_data.get('transaction_type', ''))))
                    self.table_widget.setItem(row_idx, 3, QTableWidgetItem(str(row_data.get('source_ref_no', ''))))
                    self.table_widget.setItem(row_idx, 4, QTableWidgetItem(str(row_data.get('product_code', ''))))
                    self.table_widget.setItem(row_idx, 5, QTableWidgetItem(str(row_data.get('lot_number', ''))))

                    self.table_widget.setItem(row_idx, 6, QTableWidgetItem(str(row_data.get('bag_box_number', ''))))

                    qty_in = row_data.get('quantity_in', 0.0) or 0.0
                    qty_in_item = QTableWidgetItem(f"{float(qty_in):,.2f}")
                    qty_in_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    self.table_widget.setItem(row_idx, 7, qty_in_item)

                    qty_out = row_data.get('quantity_out', 0.0) or 0.0
                    qty_out_item = QTableWidgetItem(f"{float(qty_out):,.2f}")
                    qty_out_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    self.table_widget.setItem(row_idx, 8, qty_out_item)

                    self.table_widget.setItem(row_idx, 9, QTableWidgetItem(str(row_data.get('unit', ''))))
                    self.table_widget.setItem(row_idx, 10, QTableWidgetItem(str(row_data.get('warehouse', ''))))
                    self.table_widget.setItem(row_idx, 11, QTableWidgetItem(str(row_data.get('encoded_by', ''))))

        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Failed to load failed transactions: {e}")
            print(traceback.format_exc())


if __name__ == "__main__":
    # --- MOCK DATABASE SETUP FOR STANDALONE EXECUTION ---
    class MockConnection:
        def __enter__(self): return self

        def __exit__(self, exc_type, exc_val, exc_tb): pass

        def execute(self, query, params=None):
            # This mock doesn't need to be complex as the real DB will be used in production.
            # It just returns an empty result to prevent crashes during standalone testing.
            class MockResult:
                def mappings(self): return self

                def all(self): return []

            return MockResult()


    class MockEngine:
        def connect(self): return MockConnection()


    # --- END MOCK DATABASE SETUP ---

    app = QApplication(sys.argv)

    mock_db_engine = MockEngine()
    mock_username = "STANDALONE_USER"


    def mock_log(action, details):
        print(f"[AUDIT LOG MOCK] User: {mock_username}, Action: {action}, Details: {details}")


    main_window = QMainWindow()
    main_window.setWindowTitle("Standalone Failed Transaction Viewer")

    transaction_page = FailedTransactionsFormPage(
        engine=mock_db_engine,
        username=mock_username,
        log_audit_trail_func=mock_log
    )

    main_window.setCentralWidget(transaction_page)
    main_window.resize(1000, 600)
    main_window.show()

    sys.exit(app.exec())