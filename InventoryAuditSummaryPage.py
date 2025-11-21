import pandas as pd
import os
import sys
import traceback
from datetime import datetime
import qtawesome as fa

# --- Email Imports ---
from email.message import EmailMessage
from io import BytesIO
import smtplib
import ssl

# --- PyQt6 Imports ---
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QThread, QDate, QSize, QSettings
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QTableWidget,
                             QTableWidgetItem, QHeaderView, QMessageBox, QHBoxLayout,
                             QLabel, QPushButton, QLineEdit, QAbstractItemView,
                             QDateEdit, QGroupBox, QFileDialog, QTabWidget,
                             QGridLayout, QProgressBar, QComboBox, QDialog,
                             QFormLayout, QDialogButtonBox, QSpinBox)
from PyQt6.QtGui import QColor

# --- SQLAlchemy and OpenPyXL Imports ---
from sqlalchemy import text
from sqlalchemy.engine import Engine
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

# --- UI CONSTANTS (Assuming they are shared) ---
PRIMARY_ACCENT_COLOR = "#007bff"
HEADER_AND_ICON_COLOR = "#3a506b"
BACKGROUND_CONTENT_COLOR = "#f4f7fc"
INPUT_BACKGROUND_COLOR = "#ffffff"
GROUP_BOX_HEADER_COLOR = "#f4f7fc"
TABLE_HEADER_TEXT_COLOR = "#4f4f4f"
NEUTRAL_COLOR = "#6c757d"


# --- Helper Widgets and Functions (Reused) ---
class UpperCaseLineEdit(QLineEdit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.textEdited.connect(self._to_upper)

    def _to_upper(self, text: str):
        if text and text != self.text().upper():
            self.blockSignals(True);
            self.setText(text.upper());
            self.blockSignals(False)


def show_error_message(parent, title, message, detailed_text=""):
    msg_box = QMessageBox(parent);
    msg_box.setIcon(QMessageBox.Icon.Critical);
    msg_box.setWindowTitle(title);
    msg_box.setText(f"<b>{message}</b>")
    if detailed_text: msg_box.setDetailedText(detailed_text)
    msg_box.exec()


# --- Audit Worker ---

class AuditWorker(QObject):
    finished = pyqtSignal(pd.DataFrame)
    error = pyqtSignal(str, str)

    def __init__(self, engine: Engine, product_filter: str, lot_filter: str, as_of_date: str):
        super().__init__()
        self.engine = engine
        self.product_filter = product_filter
        self.lot_filter = lot_filter
        self.as_of_date = as_of_date

    def run(self):
        try:
            params = {'as_of_date': self.as_of_date}

            product_filter_clause = ""
            if self.product_filter:
                product_filter_clause = "AND lm.product_code ILIKE :product_search"
                params['product_search'] = f"%{self.product_filter}%"

            lot_filter_clause = ""
            if self.lot_filter:
                lot_filter_clause = "AND lm.lot_number ILIKE :lot_search"
                params['lot_search'] = f"%{self.lot_filter}%"

            query_str = f"""
                -- CTE 1: Combine all transactions (Begin Inv + Movement)
                WITH all_tx AS (
                    SELECT 
                        UPPER(TRIM(product_code)) AS product_code, 
                        UPPER(TRIM(lot_number)) AS lot_number,
                        COALESCE(CAST(qty AS NUMERIC), 0) AS quantity_in, 
                        0.0 AS quantity_out,
                        NULL::date AS transaction_date,
                        0 AS sort_order
                    FROM beginv_sheet1
                    WHERE product_code IS NOT NULL AND TRIM(product_code) <> '' 
                      AND lot_number IS NOT NULL AND TRIM(lot_number) <> ''

                    UNION ALL

                    SELECT 
                        UPPER(TRIM(t.product_code)) AS product_code, 
                        UPPER(TRIM(t.lot_number)) AS lot_number,
                        COALESCE(CAST(t.quantity_in AS NUMERIC), 0) AS quantity_in, 
                        COALESCE(CAST(t.quantity_out AS NUMERIC), 0) AS quantity_out,
                        t.transaction_date,
                        1 AS sort_order
                    FROM transactions t
                    WHERE t.product_code IS NOT NULL AND TRIM(t.product_code) <> '' 
                      AND t.lot_number IS NOT NULL AND TRIM(t.lot_number) <> ''
                      AND t.transaction_date <= :as_of_date
                ),

                -- CTE 2: Calculate running balances for all movements
                running_balances AS (
                    SELECT
                        lot_number,
                        product_code,
                        quantity_in,
                        quantity_out,
                        -- Calculate the running balance at every step
                        SUM(quantity_in - quantity_out) OVER (
                            PARTITION BY lot_number 
                            ORDER BY sort_order, transaction_date ASC NULLS FIRST
                            ROWS UNBOUNDED PRECEDING
                        ) AS current_running_balance
                    FROM all_tx
                ),

                -- CTE 3: Summarize metrics per lot
                lot_metrics AS (
                    SELECT
                        lot_number,
                        MAX(product_code) AS product_code,
                        SUM(quantity_in) AS total_in,
                        SUM(quantity_out) AS total_out,
                        -- The final balance is the MAX running balance (since it's ordered chronologically)
                        MAX(current_running_balance) AS final_balance, 
                        MIN(current_running_balance) AS minimum_running_balance,

                        -- Audit Check: Difference between totals and final balance should be near zero
                        (SUM(quantity_in) - SUM(quantity_out) - MAX(current_running_balance)) AS calculation_check,

                        -- Audit Status Flag
                        CASE 
                            WHEN MIN(current_running_balance) < -0.001 THEN 'ERROR (Negative Stock)'
                            ELSE 'OK' 
                        END AS audit_status
                    FROM running_balances
                    GROUP BY lot_number
                    -- Only show lots that have a meaningful balance or negative history
                    HAVING MAX(current_running_balance) > 0.001 OR MIN(current_running_balance) < -0.001
                )

                -- FINAL SELECT: Apply top-level filters
                SELECT 
                    lm.product_code, 
                    lm.lot_number, 
                    lm.final_balance,
                    lm.total_in,
                    lm.total_out,
                    (lm.total_in - lm.total_out) AS calculated_difference,
                    lm.minimum_running_balance,
                    lm.audit_status
                FROM lot_metrics lm
                WHERE 1=1 {product_filter_clause} {lot_filter_clause}
                ORDER BY lm.audit_status DESC, lm.product_code, lm.lot_number;
            """

            with self.engine.connect() as conn:
                results = conn.execute(text(query_str), params).mappings().all()

            df = pd.DataFrame(results) if results else pd.DataFrame(
                columns=['product_code', 'lot_number', 'final_balance', 'total_in', 'total_out',
                         'calculated_difference', 'minimum_running_balance', 'audit_status'])

            self.finished.emit(df)
        except Exception:
            self.error.emit("Database query failed.", traceback.format_exc())


# --- Audit Page UI ---

class InventoryAuditSummaryPage(QWidget):
    def __init__(self, engine: Engine, username: str, log_audit_trail_func):
        super().__init__()
        self.engine = engine
        self.username = username
        self.log_audit_trail = log_audit_trail_func
        self.audit_thread: QThread | None = None
        self.audit_worker: AuditWorker | None = None
        self.current_audit_df = pd.DataFrame()
        self.init_ui()
        self.setStyleSheet(self._get_styles())

    def refresh_page(self):
        self._start_audit_calculation()

    def _get_styles(self) -> str:
        return f"QWidget{{background-color:{BACKGROUND_CONTENT_COLOR};}} QGroupBox{{border:1px solid #e0e5eb; border-radius:8px; margin-top:12px; background-color:{INPUT_BACKGROUND_COLOR};}} QGroupBox::title{{subcontrol-origin:margin; subcontrol-position:top left; padding:2px 10px; background-color:{GROUP_BOX_HEADER_COLOR}; border:1px solid #e0e5eb; border-bottom:1px solid {INPUT_BACKGROUND_COLOR}; border-top-left-radius:8px; border-top-right-radius:8px; font-weight:bold; color:#4f4f4f;}} QLabel#PageHeader{{font-size:15pt; font-weight:bold; color:{HEADER_AND_ICON_COLOR}; background-color:transparent;}} QLineEdit, QDateEdit, QComboBox{{border:1px solid #d1d9e6; padding:8px; border-radius:5px; background-color:{INPUT_BACKGROUND_COLOR};}} QPushButton#PrimaryButton{{color:{HEADER_AND_ICON_COLOR}; border:1px solid {HEADER_AND_ICON_COLOR}; padding: 8px 15px; border-radius: 6px; font-weight: bold; background-color: {INPUT_BACKGROUND_COLOR};}} QPushButton#PrimaryButton:hover{{background-color:#e9f0ff;}} QTableWidget{{border:1px solid #e0e5eb; background-color:{INPUT_BACKGROUND_COLOR}; gridline-color: #f0f3f8;}} QHeaderView::section{{background-color: #f4f7fc; padding: 5px; border: none; font-weight: bold; color: {TABLE_HEADER_TEXT_COLOR};}}"

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)

        icon_label = QLabel()
        icon_label.setPixmap(fa.icon('fa5s.clipboard-check', color=HEADER_AND_ICON_COLOR).pixmap(QSize(28, 28)))
        header_layout.addWidget(icon_label)
        header_layout.addWidget(QLabel("Inventory Audit Summary", objectName="PageHeader"))
        header_layout.addStretch()
        main_layout.addWidget(header_widget)

        instruction_label = QLabel(
            "This report analyzes the full transaction history of every lot up to the selected date to identify inconsistencies like negative running balances."
        )
        instruction_label.setStyleSheet("font-style: italic; color: #555; background: transparent;")
        main_layout.addWidget(instruction_label)

        main_layout.addWidget(self._create_filter_controls())
        self.audit_table = self._create_audit_table()
        main_layout.addWidget(self.audit_table, 1)

    def _create_filter_controls(self) -> QGroupBox:
        group = QGroupBox("Audit Scope & Actions")
        layout = QHBoxLayout(group)

        layout.addWidget(QLabel("As Of Date:"))
        self.date_picker = QDateEdit(calendarPopup=True, date=QDate.currentDate(), displayFormat="yyyy-MM-dd")
        layout.addWidget(self.date_picker)

        layout.addSpacing(10)
        layout.addWidget(QLabel("Product:"))
        self.product_code_input = UpperCaseLineEdit(placeholderText="Filter Product Code")
        layout.addWidget(self.product_code_input, 1)

        layout.addSpacing(10)
        layout.addWidget(QLabel("Lot:"))
        self.lot_number_input = UpperCaseLineEdit(placeholderText="Filter Lot Number")
        layout.addWidget(self.lot_number_input, 1)

        layout.addStretch()

        self.refresh_button = QPushButton("Run Audit", objectName="PrimaryButton",
                                          icon=fa.icon('fa5s.search', color=HEADER_AND_ICON_COLOR))
        self.export_button = QPushButton("Export Audit to Excel", objectName="PrimaryButton",
                                         icon=fa.icon('fa5s.file-excel', color=HEADER_AND_ICON_COLOR))
        self.export_button.setEnabled(False)

        layout.addWidget(self.refresh_button)
        layout.addWidget(self.export_button)

        self.refresh_button.clicked.connect(self._start_audit_calculation)
        self.product_code_input.returnPressed.connect(self._start_audit_calculation)
        self.lot_number_input.returnPressed.connect(self._start_audit_calculation)
        self.date_picker.dateChanged.connect(self._start_audit_calculation)
        self.export_button.clicked.connect(self._export_to_excel)

        return group

    def _create_audit_table(self) -> QTableWidget:
        table = QTableWidget(columnCount=8);
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);
        table.verticalHeader().setVisible(False);
        table.setAlternatingRowColors(True);

        table.setHorizontalHeaderLabels([
            "Product Code", "Lot Number", "Final Balance", "Total IN", "Total OUT",
            "Min Balance", "Status", "Difference Check"
        ])

        header = table.horizontalHeader();
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # Product Code
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # Lot Number
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        return table

    def _start_audit_calculation(self):
        if self.audit_thread and self.audit_thread.isRunning(): return
        self.set_controls_enabled(False);
        self._show_loading_state(self.audit_table, "Running comprehensive audit calculation...")

        date_str = self.date_picker.date().toString(Qt.DateFormat.ISODate)

        self.audit_thread = QThread()
        self.audit_worker = AuditWorker(
            engine=self.engine,
            product_filter=self.product_code_input.text().strip().upper(),
            lot_filter=self.lot_number_input.text().strip().upper(),
            as_of_date=date_str
        )
        self.audit_worker.moveToThread(self.audit_thread)
        self.audit_thread.started.connect(self.audit_worker.run)
        self.audit_worker.finished.connect(self._on_audit_finished)
        self.audit_worker.error.connect(self._on_calculation_error)
        self.audit_worker.finished.connect(self.audit_thread.quit)
        self.audit_worker.error.connect(self.audit_thread.quit)
        self.audit_thread.finished.connect(self.audit_worker.deleteLater)
        self.audit_thread.finished.connect(self.audit_thread.deleteLater)
        self.audit_thread.finished.connect(self._reset_thread_state)
        self.audit_thread.start()

    def _reset_thread_state(self):
        self.audit_thread = None
        self.audit_worker = None

    def set_controls_enabled(self, enabled: bool):
        self.lot_number_input.setEnabled(enabled)
        self.product_code_input.setEnabled(enabled)
        self.refresh_button.setEnabled(enabled)
        self.date_picker.setEnabled(enabled)
        self.export_button.setEnabled(enabled and not self.current_audit_df.empty)

    def _on_audit_finished(self, df: pd.DataFrame):
        self.current_audit_df = df.copy()
        self._display_audit_summary(df)
        self.set_controls_enabled(True)

    def _on_calculation_error(self, error_message: str, detailed_traceback: str):
        show_error_message(self, "Audit Calculation Error", error_message, detailed_traceback)
        self._show_loading_state(self.audit_table, "Error during audit calculation.")
        self.set_controls_enabled(True)

    def _show_loading_state(self, table: QTableWidget, message: str):
        table.setRowCount(1)
        table.setSpan(0, 0, 1, table.columnCount())
        loading_item = QTableWidgetItem(message)
        loading_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        table.setItem(0, 0, loading_item)

    def _display_audit_summary(self, df: pd.DataFrame):
        self.audit_table.setRowCount(0)
        if df.empty:
            self._show_loading_state(self.audit_table, "No lots found for audit scope.")
            return

        self.audit_table.setRowCount(len(df))

        COL_PROD = 0
        COL_LOT = 1
        COL_FINAL = 2
        COL_IN = 3
        COL_OUT = 4
        COL_MIN = 5
        COL_STATUS = 6
        COL_DIFF = 7

        error_count = 0

        for i, row in df.iterrows():
            audit_status = str(row.get('audit_status', 'N/A'))

            # 0, 1: Product & Lot
            self.audit_table.setItem(i, COL_PROD, QTableWidgetItem(str(row['product_code'])))
            self.audit_table.setItem(i, COL_LOT, QTableWidgetItem(str(row['lot_number'])))

            # 2, 3, 4, 5, 7: Numeric/Balance Fields

            # Helper for numeric items
            def create_numeric_item(value, alignment=Qt.AlignmentFlag.AlignRight):
                item = QTableWidgetItem(f"{value:,.2f}")
                item.setTextAlignment(alignment | Qt.AlignmentFlag.AlignVCenter)
                return item

            self.audit_table.setItem(i, COL_FINAL, create_numeric_item(row['final_balance']))
            self.audit_table.setItem(i, COL_IN, create_numeric_item(row['total_in']))
            self.audit_table.setItem(i, COL_OUT, create_numeric_item(row['total_out']))
            self.audit_table.setItem(i, COL_MIN, create_numeric_item(row['minimum_running_balance']))
            self.audit_table.setItem(i, COL_DIFF,
                                     create_numeric_item(row['calculated_difference']))  # Should be near zero

            # 6: Status Field (Styling based on audit result)
            status_item = QTableWidgetItem(audit_status)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            if 'ERROR' in audit_status:
                status_item.setBackground(QColor(255, 100, 100))
                status_item.setForeground(QColor(Qt.GlobalColor.white))
                error_count += 1
            else:
                status_item.setBackground(QColor(220, 255, 220))  # Very Light Green

            self.audit_table.setItem(i, COL_STATUS, status_item)

        # Update summary status
        if error_count > 0:
            QMessageBox.warning(self, "Audit Warning",
                                f"{error_count} lots flagged with audit errors (Negative running balance detected).")

    def _format_excel_sheet(self, worksheet: Worksheet, df: pd.DataFrame):
        # Format numeric columns (3rd column onwards typically)

        # Helper function to auto-size and format currency
        def setup_column(col_idx, num_format=None):
            column_letter = get_column_letter(col_idx)
            max_length = max(df.iloc[:, col_idx - 1].astype(str).map(len).max(), len(df.columns[col_idx - 1])) + 2
            worksheet.column_dimensions[column_letter].width = max_length
            if num_format:
                for cell in worksheet[column_letter][1:]:
                    cell.number_format = num_format

        # Format columns based on their index (1-based)
        for i in range(3, 8):
            setup_column(i, '#,##0.00')

        # Auto-size remaining columns
        setup_column(1)
        setup_column(2)
        setup_column(8)

    def _export_to_excel(self):
        if self.current_audit_df.empty:
            QMessageBox.information(self, "Export Failed", "No audit data to export.")
            return

        default_filename = f"FG_Inventory_Audit_Summary_{datetime.now():%Y-%m-%d}.xlsx"
        filepath, _ = QFileDialog.getSaveFileName(self, "Save Audit Report", default_filename, "Excel Files (*.xlsx)")

        if filepath:
            try:
                export_df = self.current_audit_df.rename(
                    columns={
                        'product_code': 'PRODUCT_CODE',
                        'lot_number': 'LOT_NUMBER',
                        'final_balance': 'FINAL_BALANCE_QTY',
                        'total_in': 'TOTAL_IN_QTY',
                        'total_out': 'TOTAL_OUT_QTY',
                        'calculated_difference': 'BALANCE_CHECK_DIFF',
                        'minimum_running_balance': 'MIN_RUNNING_BALANCE',
                        'audit_status': 'AUDIT_STATUS'
                    }
                )

                # Reorder columns slightly for Excel readability
                final_cols = ['PRODUCT_CODE', 'LOT_NUMBER', 'FINAL_BALANCE_QTY', 'TOTAL_IN_QTY', 'TOTAL_OUT_QTY',
                              'BALANCE_CHECK_DIFF', 'MIN_RUNNING_BALANCE', 'AUDIT_STATUS']

                with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
                    export_df[final_cols].to_excel(writer, index=False, sheet_name='Audit Summary')
                    self._format_excel_sheet(writer.sheets['Audit Summary'], export_df[final_cols])

                filename = os.path.basename(filepath)
                self.log_audit_trail("EXPORT_AUDIT_SUMMARY", f"User exported audit summary report to '{filename}'.")
                QMessageBox.information(self, "Export Successful", f"Audit data exported to:\n{filename}")
            except Exception:
                show_error_message(self, "Export Error", "Failed to save file.", traceback.format_exc())

# Note: For this to run, the caller application needs to instantiate this InventoryAuditSummaryPage
# and pass the required engine, username, and log function.