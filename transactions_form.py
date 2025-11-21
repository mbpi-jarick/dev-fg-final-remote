import sys
import traceback
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QGroupBox, QDialog, QFormLayout, QDialogButtonBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor
from sqlalchemy import text, Engine
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


class LotAuditDialog(QDialog):
    """
    Dialog to display the detailed transaction history and running balance
    for a single lot number to verify data integrity.
    """

    def __init__(self, engine: Engine, lot_number: str, product_code: str, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.lot_number = lot_number
        self.product_code = product_code
        self.setWindowTitle(f"Audit Trail: {lot_number} ({product_code})")
        self.setMinimumSize(950, 600)
        self.setStyleSheet("""
            QDialog { background-color: #f4f7fc; }
            QTableWidget { border: 1px solid #e0e5eb; background-color: white; }
            QHeaderView::section { background-color: #e9f0ff; font-weight: bold; }
            QLabel#Summary { font-weight: bold; font-size: 11pt; padding: 5px; background-color: white; border: 1px solid #d1d9e6; border-radius: 4px; }
            QGroupBox { margin-top: 5px; padding-top: 10px; }
        """)
        self.init_ui()
        self._load_audit_data()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # Header Summary
        header_group = QGroupBox("Lot Summary")
        header_layout = QFormLayout(header_group)
        self.lot_label = QLabel(f"<b>Lot Number:</b> {self.lot_number}")
        self.product_label = QLabel(f"<b>Product Code:</b> {self.product_code}")
        self.final_balance_label = QLabel("<b>Final Calculated Balance:</b> N/A")
        self.final_balance_label.setObjectName("Summary")

        header_layout.addRow(self.lot_label)
        header_layout.addRow(self.product_label)
        header_layout.addRow(self.final_balance_label)
        main_layout.addWidget(header_group)

        # Transaction Table (Audit Log)
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Source", "Date", "Type", "Qty In", "Qty Out", "Running Balance", "Source Ref"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Date
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Qty In
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Qty Out
        self.table.horizontalHeader().setSectionResizeMode(5,
                                                           QHeaderView.ResizeMode.ResizeToContents)  # Running Balance
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setShowGrid(True)
        main_layout.addWidget(self.table, 1)

        # Close button
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)

    def _load_audit_data(self):
        """Loads all transactions and beginning inventory for the lot and calculates the running balance."""
        self.table.setRowCount(0)

        # SQL using PostgreSQL Window Functions for running balance calculation
        query_str = """
            WITH all_movements AS (
                -- 1. Beginning Inventory (Acts as the first 'IN' transaction)
                SELECT
                    'BEGINV' AS source,
                    COALESCE(CAST(qty AS NUMERIC), 0) AS quantity_in,
                    0.0 AS quantity_out,
                    NULL AS transaction_date,
                    'BEGINV' AS transaction_type,
                    lot_number,
                    location,
                    0 AS sort_order, -- Ensure BEGINV is processed first
                    '' AS source_ref_no
                FROM beginv_sheet1
                WHERE lot_number = :lot_num

                UNION ALL

                -- 2. Standard Transactions
                SELECT
                    t.encoded_by AS source,
                    COALESCE(CAST(t.quantity_in AS NUMERIC), 0) AS quantity_in,
                    COALESCE(CAST(t.quantity_out AS NUMERIC), 0) AS quantity_out,
                    t.transaction_date,
                    t.transaction_type,
                    t.lot_number,
                    t.warehouse AS location,
                    1 AS sort_order, -- Transactions come after BEGINV
                    t.source_ref_no
                FROM transactions t
                WHERE t.lot_number = :lot_num
            )
            SELECT 
                source,
                quantity_in,
                quantity_out,
                transaction_date,
                transaction_type,
                -- Calculate Running Balance
                SUM(quantity_in - quantity_out) OVER (
                    ORDER BY sort_order, transaction_date ASC NULLS FIRST
                ) AS running_balance,
                source_ref_no
            FROM all_movements
            ORDER BY sort_order, transaction_date ASC NULLS FIRST;
        """

        try:
            with self.engine.connect() as conn:
                movements_result = conn.execute(
                    text(query_str), {'lot_num': self.lot_number}
                ).mappings().all()

            if not movements_result:
                self.table.setRowCount(1)
                item = QTableWidgetItem("No movements found for this lot number.")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(0, 0, item)
                self.table.setSpan(0, 0, 1, self.table.columnCount())
                return

            self.table.setRowCount(len(movements_result))
            final_balance = 0.0

            for i, row in enumerate(movements_result):

                # Column 0: Source (Encoded By or BEGINV)
                self.table.setItem(i, 0, QTableWidgetItem(str(row['source'])))

                # Column 1: Date
                date_str = str(row['transaction_date']) if row['transaction_date'] else "---"
                self.table.setItem(i, 1, QTableWidgetItem(date_str))

                # Column 2: Type
                type_item = QTableWidgetItem(str(row['transaction_type']))
                if row['transaction_type'] == 'IN' or row['transaction_type'] == 'BEGINV':
                    type_item.setForeground(QColor(0, 128, 0))  # Green
                elif row['transaction_type'] == 'OUT':
                    type_item.setForeground(QColor(220, 50, 50))  # Red
                self.table.setItem(i, 2, type_item)

                # Column 3 & 4: Qty In / Qty Out
                qty_in = float(row['quantity_in'])
                qty_out = float(row['quantity_out'])

                qty_in_item = QTableWidgetItem(f"{qty_in:,.2f}")
                qty_in_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(i, 3, qty_in_item)

                qty_out_item = QTableWidgetItem(f"{qty_out:,.2f}")
                qty_out_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(i, 4, qty_out_item)

                # Column 5: Running Balance
                running_balance = float(row['running_balance'])
                balance_item = QTableWidgetItem(f"{running_balance:,.2f}")
                balance_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

                # Highlight if balance is negative (inventory error)
                if running_balance < -0.001:  # Use small tolerance
                    balance_item.setBackground(QColor(255, 180, 180))  # Light Red
                    balance_item.setToolTip("WARNING: Running balance is negative at this step!")

                self.table.setItem(i, 5, balance_item)
                final_balance = running_balance

                # Column 6: Source Ref
                self.table.setItem(i, 6, QTableWidgetItem(str(row['source_ref_no'])))

            # Update Header Summary
            self.final_balance_label.setText(f"<b>Final Calculated Balance:</b> {final_balance:,.2f} kg")

        except Exception as e:
            QMessageBox.critical(self, "Audit Error",
                                 f"Failed to perform lot audit: {e}",
                                 detailedText=traceback.format_exc())


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
        header_layout = QHBoxLayout()
        icon_label = QLabel()
        icon_label.setPixmap(qta.icon('fa5s.exchange-alt', color='#3a506b').pixmap(32, 32))
        header_layout.addWidget(icon_label)
        title_label = QLabel("FG Passed Transaction")
        title_label.setStyleSheet("font-size: 15pt; font-weight: bold; color: #3a506b;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        instruction_label = QLabel("Use the filters below to search for specific Finished Goods transactions (In/Out).")
        instruction_label.setWordWrap(True)
        main_layout.addWidget(instruction_label)

        # --- Top layout for controls inside a group box ---
        controls_group = QGroupBox("Filters & Actions")
        controls_layout = QHBoxLayout(controls_group)
        controls_layout.addWidget(QLabel("Search Transactions:"))

        self.search_edit = UpperCaseLineEdit()
        self.search_edit.setPlaceholderText("Filter by Product, Lot, Source Ref No...")
        controls_layout.addWidget(self.search_edit, 1)

        # ADDED AUDIT BUTTON
        self.audit_lot_button = QPushButton("Audit Selected Lot History")
        self.audit_lot_button.setEnabled(False)
        controls_layout.addWidget(self.audit_lot_button)

        self.refresh_button = QPushButton("Refresh")
        controls_layout.addWidget(self.refresh_button)
        main_layout.addWidget(controls_group)

        # --- Table Widget for Displaying All Transactions ---
        self.table_widget = QTableWidget()
        self.table_widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.table_widget.setColumnCount(12)

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

        # NEW CONNECTIONS
        self.table_widget.itemSelectionChanged.connect(self._toggle_audit_button)
        self.audit_lot_button.clicked.connect(self._open_lot_audit_dialog)

    def _toggle_audit_button(self):
        """Enable audit button only if exactly one row is selected."""
        selected_rows = self.table_widget.selectionModel().selectedRows()
        self.audit_lot_button.setEnabled(len(selected_rows) == 1)

    def _open_lot_audit_dialog(self):
        """Opens the LotAuditDialog with details from the selected transaction."""
        selected_rows = self.table_widget.selectionModel().selectedRows()
        if not selected_rows:
            return

        row = selected_rows[0].row()

        # Lot Number is index 5, Product Code is index 4
        lot_number_item = self.table_widget.item(row, 5)
        product_code_item = self.table_widget.item(row, 4)

        if not lot_number_item or not product_code_item:
            QMessageBox.warning(self, "Audit Error", "Selected row data is incomplete (missing Lot or Product).")
            return

        lot_number = lot_number_item.text().strip()
        product_code = product_code_item.text().strip()

        if not lot_number:
            QMessageBox.warning(self, "Audit Error", "Selected row does not contain a valid Lot Number.")
            return

        # Log the action
        self.log_audit_trail("AUDIT_LOT_START", f"User started lot audit for Lot: {lot_number}")

        # Execute the dialog
        dialog = LotAuditDialog(self.engine, lot_number, product_code, self)
        dialog.exec()

    def refresh_page(self):
        """Called when the page is shown or refresh is clicked."""
        self.search_edit.blockSignals(True)
        self.search_edit.clear()
        self.search_edit.blockSignals(False)
        self._load_transactions()

    def _load_transactions(self):
        """Loads transaction data from the database into the table, applying filters."""
        self.table_widget.setRowCount(0)
        search_term = self.search_edit.text().strip()

        try:
            with self.engine.connect() as conn:
                # --- SQL QUERY (Retained from previous fix) ---
                base_query = """
                    SELECT 
                        t.id, t.transaction_date, t.transaction_type, t.source_ref_no, t.product_code, 
                        t.lot_number, 
                        COALESCE(
                            b.bag_box_number,  
                            fg.bag_no, 
                            qcf.bag_no,
                            ''
                        ) as bag_box_number,
                        t.quantity_in, t.quantity_out, t.unit, t.warehouse, t.encoded_by
                    FROM transactions t

                    -- Subquery A: Get ONE unique bag/box number per lot_number from Begin Inventory
                    LEFT JOIN (
                        SELECT DISTINCT ON (lot_number) 
                            lot_number, 
                            COALESCE(bag_number, box_number) AS bag_box_number 
                        FROM beginv_sheet1
                        ORDER BY lot_number, bag_number, box_number 
                    ) b ON t.lot_number = b.lot_number

                    -- Subquery B: Get ONE unique bag number per system_ref_no from FG Endorsements
                    LEFT JOIN (
                        SELECT DISTINCT ON (system_ref_no) 
                            system_ref_no, 
                            bag_no
                        FROM fg_endorsements_primary
                        ORDER BY system_ref_no, bag_no
                    ) fg ON t.source_ref_no = fg.system_ref_no

                    -- Subquery C: Get ONE unique bag number per system_ref_no from QCF Endorsements
                    LEFT JOIN (
                        SELECT DISTINCT ON (system_ref_no) 
                            system_ref_no, 
                            bag_no
                        FROM qcf_endorsements_primary
                        ORDER BY system_ref_no, bag_no
                    ) qcf ON t.source_ref_no = qcf.system_ref_no
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
                    self.table_widget.setItem(row_idx, 0, QTableWidgetItem(str(row_data.get('id', ''))))
                    self.table_widget.setItem(row_idx, 1, QTableWidgetItem(str(row_data.get('transaction_date', ''))))
                    self.table_widget.setItem(row_idx, 2, QTableWidgetItem(str(row_data.get('transaction_type', ''))))
                    self.table_widget.setItem(row_idx, 3, QTableWidgetItem(str(row_data.get('source_ref_no', ''))))
                    self.table_widget.setItem(row_idx, 4, QTableWidgetItem(str(row_data.get('product_code', ''))))
                    self.table_widget.setItem(row_idx, 5, QTableWidgetItem(str(row_data.get('lot_number', ''))))

                    self.table_widget.setItem(row_idx, 6, QTableWidgetItem(str(row_data.get('bag_box_number', ''))))

                    qty_in_item = QTableWidgetItem(f"{row_data.get('quantity_in', 0):,.2f}")
                    qty_in_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    self.table_widget.setItem(row_idx, 7, qty_in_item)

                    qty_out_item = QTableWidgetItem(f"{row_data.get('quantity_out', 0):,.2f}")
                    qty_out_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    self.table_widget.setItem(row_idx, 8, qty_out_item)

                    self.table_widget.setItem(row_idx, 9, QTableWidgetItem(str(row_data.get('unit', ''))))
                    self.table_widget.setItem(row_idx, 10, QTableWidgetItem(str(row_data.get('warehouse', ''))))
                    self.table_widget.setItem(row_idx, 11, QTableWidgetItem(str(row_data.get('encoded_by', ''))))

        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Failed to load transactions: {e}")
            print(traceback.format_exc())