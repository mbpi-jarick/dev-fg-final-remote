# receiving_report.py
# FINAL VERSION - Rebuilt with a modern UI, dashboard, pagination, and features consistent with other modules.
# FIX - Implemented intelligent auto-sizing for all table headers.
# UPDATE - Added PDF generation and print preview functionality.
# UPDATE - Integrated remarks into the main table, removed grid lines, and enforced a single-page layout for a cleaner PDF.
# ENHANCED - Upgraded dashboard chart to an interactive pie chart and removed dashboard table borders.
# COLORFUL DASHBOARD - Implemented colorful KPI cards and a vibrant pie chart for a modern look.
# V2 - Added Deleted Tab with Restore, auto-sizing tables, and enhanced validation.

import sys
import io
from datetime import datetime, date
from decimal import Decimal
from functools import partial

# --- PDF & Printing Imports ---
import fitz  # PyMuPDF
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Table, TableStyle)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# --- PyQt6 Imports ---
from PyQt6.QtCore import Qt, QDate, pyqtSignal, QSizeF, QDateTime
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTabWidget, QFormLayout, QLineEdit, QDateEdit,
                             QPushButton, QTableWidget, QTableWidgetItem, QComboBox, QCompleter,
                             QAbstractItemView, QHeaderView, QMessageBox, QHBoxLayout, QLabel,
                             QDialog, QDialogButtonBox, QGroupBox, QMenu, QGridLayout, QSplitter)
from PyQt6.QtGui import QDoubleValidator, QPainter, QPageSize, QImage
from PyQt6.QtPrintSupport import QPrinter, QPrintPreviewDialog
from PyQt6.QtCharts import QChartView, QChart, QPieSeries, QPieSlice

from sqlalchemy import text


class UpperCaseLineEdit(QLineEdit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.textChanged.connect(self._to_upper)

    def _to_upper(self, text: str):
        self.blockSignals(True)
        self.setText(text.upper())
        self.blockSignals(False)


class FloatLineEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        validator = QDoubleValidator(0.0, 99999999.0, 2)
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        self.setValidator(validator)
        self.editingFinished.connect(self._format_text)
        self.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.setText("0.00")

    def _format_text(self):
        try:
            value = float(self.text() or 0.0)
            self.setText(f"{value:.2f}")
        except ValueError:
            self.setText("0.00")

    def value(self) -> float:
        return float(self.text() or 0.0)


class AddNewRecordDialog(QDialog):
    def __init__(self, parent, title, label, table_name, engine):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.table_name = table_name
        self.engine = engine
        self.new_record_name = None
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        self.name_edit = UpperCaseLineEdit()
        form_layout.addRow(f"{label}:", self.name_edit)
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.on_accept)
        button_box.rejected.connect(self.reject)
        layout.addLayout(form_layout)
        layout.addWidget(button_box)
        self.setMinimumWidth(350)

    def on_accept(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Input Error", "Name cannot be empty.")
            return
        try:
            with self.engine.connect() as conn, conn.begin():
                conn.execute(text(f"INSERT INTO {self.table_name} (name) VALUES (:name) ON CONFLICT (name) DO NOTHING"),
                             {"name": name})
            self.new_record_name = name
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Could not add new record: {e}")
            self.reject()


class AddItemDialog(QDialog):
    data_refreshed_signal = pyqtSignal()

    def __init__(self, parent=None, data=None, warehouses=None, engine=None):
        super().__init__(parent)
        self.engine = engine
        self.setWindowTitle("Edit Item" if data else "Add New Item")
        self.setMinimumWidth(450)

        main_layout = QVBoxLayout(self)

        # Instruction Label
        instruction_label = QLabel("All fields are required. Please provide valid information for the item.")
        instruction_label.setStyleSheet("font-style: italic; color: #555; padding-bottom: 10px;")
        main_layout.addWidget(instruction_label)

        layout = QFormLayout()

        # --- Upgraded Product Code to ComboBox ---
        self.material_code_edit = QComboBox(editable=True)
        completer = QCompleter()
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.material_code_edit.setCompleter(completer)
        self.material_code_edit.lineEdit().textChanged.connect(
            lambda text, le=self.material_code_edit.lineEdit(): (
            le.blockSignals(True), le.setText(text.upper()), le.blockSignals(False))
        )

        self.lot_no_edit = UpperCaseLineEdit()
        self.quantity_edit = FloatLineEdit()
        self.status_edit = QComboBox()
        self.status_edit.addItems(["", "PASSED", "FAILED", "FOR EVALUATION", "FOR CHECKING"])
        self.location_edit = QComboBox()
        if warehouses: self.location_edit.addItems([""] + warehouses)

        location_layout = QHBoxLayout()
        location_layout.setContentsMargins(0, 0, 0, 0)
        location_layout.addWidget(self.location_edit, 1)
        add_location_btn = QPushButton("Manage...")
        add_location_btn.clicked.connect(self._manage_locations)
        location_layout.addWidget(add_location_btn)

        layout.addRow("Product Code:", self.material_code_edit)
        layout.addRow("Lot No.:", self.lot_no_edit)
        layout.addRow("Quantity (kg):", self.quantity_edit)
        layout.addRow("Status:", self.status_edit)
        layout.addRow("Location:", location_layout)

        main_layout.addLayout(layout)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)
        self.setLayout(main_layout)

        self._load_product_codes()

        if data:
            self.material_code_edit.setCurrentText(data.get('material_code', ''))
            self.lot_no_edit.setText(data.get('lot_no', ''))
            self.quantity_edit.setText(data.get('quantity_kg', '0.00'))
            self.status_edit.setCurrentText(data.get('status', ''))
            self.location_edit.setCurrentText(data.get('location', ''))

    def _load_product_codes(self):
        try:
            with self.engine.connect() as conn:
                prod_codes = conn.execute(
                    text("SELECT DISTINCT prod_code FROM legacy_production ORDER BY prod_code")
                ).scalars().all()

            self.material_code_edit.addItems([""] + prod_codes)
            self.material_code_edit.completer().setModel(self.material_code_edit.model())
        except Exception as e:
            QMessageBox.warning(self, "Database Error", f"Could not load product codes: {e}")

    def accept(self):
        """Override accept to add validation."""
        if not self.material_code_edit.currentText().strip():
            QMessageBox.warning(self, "Validation Error", "Product Code is required.")
            return
        if not self.lot_no_edit.text().strip():
            QMessageBox.warning(self, "Validation Error", "Lot Number is required.")
            return
        if self.quantity_edit.value() <= 0:
            QMessageBox.warning(self, "Validation Error", "Quantity must be greater than zero.")
            return
        if not self.status_edit.currentText():
            QMessageBox.warning(self, "Validation Error", "Status is required.")
            return
        if not self.location_edit.currentText():
            QMessageBox.warning(self, "Validation Error", "Location is required.")
            return

        super().accept()

    def _manage_locations(self):
        dialog = AddNewRecordDialog(self, "Manage Locations", "Location Name", "warehouses", self.engine)
        if dialog.exec() and dialog.new_record_name:
            self.data_refreshed_signal.emit()
            if self.location_edit.findText(dialog.new_record_name) == -1:
                self.location_edit.addItem(dialog.new_record_name)
            self.location_edit.setCurrentText(dialog.new_record_name)

    def get_data(self):
        return {"material_code": self.material_code_edit.currentText().strip(), "lot_no": self.lot_no_edit.text(),
                "quantity_kg": self.quantity_edit.text(), "status": self.status_edit.currentText(),
                "location": self.location_edit.currentText()}


class ReceivingReportPage(QWidget):
    def __init__(self, db_engine, username, log_audit_trail_func):
        super().__init__()
        self.engine, self.username, self.log_audit_trail = db_engine, username, log_audit_trail_func
        self.current_editing_rr_no = None
        self.item_headers = ["Product Code", "Lot no.", "Quantity (kg)", "Status", "Location"]
        self.warehouses_list, self.receivers_list, self.reporters_list = [], [], []
        self.current_page, self.records_per_page = 1, 200
        self.total_records, self.total_pages = 0, 1
        self.printer = QPrinter()
        self.current_pdf_buffer = None
        self.init_ui()
        self._load_all_records()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        dashboard_tab, view_tab, self.view_details_tab, self.entry_tab, deleted_tab = QWidget(), QWidget(), QWidget(), QWidget(), QWidget()

        self.tab_widget.addTab(dashboard_tab, "Dashboard")
        self.tab_widget.addTab(view_tab, "All Reports")
        self.tab_widget.addTab(self.view_details_tab, "View Report Details")
        self.tab_widget.addTab(self.entry_tab, "Report Entry Form")
        self.tab_widget.addTab(deleted_tab, "Deleted")

        self._setup_dashboard_tab(dashboard_tab)
        self._setup_view_tab(view_tab)
        self._setup_view_details_tab(self.view_details_tab)
        self._setup_entry_tab(self.entry_tab)
        self._setup_deleted_tab(deleted_tab)

        self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.view_details_tab), False)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

    def _configure_table_autosize(self, table: QTableWidget, stretch_last_col: bool = True):
        """Helper function to apply consistent auto-sizing to tables."""
        header = table.horizontalHeader()
        for i in range(header.count()):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)

        if stretch_last_col and header.count() > 0:
            header.setSectionResizeMode(header.count() - 1, QHeaderView.ResizeMode.Stretch)

        # You can add specific column adjustments here if needed
        # Example: if table is self.records_table: header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)

    def _create_kpi_card(self, value_text, label_text):
        card = QWidget()
        card.setObjectName("kpi_card")
        card.setStyleSheet("#kpi_card { background-color: #ffffff; border: 1px solid #e0e5eb; border-radius: 8px; }")
        layout = QVBoxLayout(card)
        value_label = QLabel(value_text)
        value_label.setObjectName("kpi_value")
        value_label.setStyleSheet("font-size: 24pt; font-weight: bold; color: #4D7BFF;")
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label = QLabel(label_text)
        label.setObjectName("kpi_label")
        label.setStyleSheet("font-size: 10pt; color: #6c757d;")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(value_label)
        layout.addWidget(label)
        return card, value_label

    def _setup_dashboard_tab(self, tab):
        main_layout = QGridLayout(tab)
        main_layout.setSpacing(20)

        (self.kpi_reports_card, self.kpi_reports_value) = self._create_kpi_card("0", "Reports Today")
        (self.kpi_qty_card, self.kpi_qty_value) = self._create_kpi_card("0.00", "Total KG Received Today")
        (self.kpi_customers_card, self.kpi_customers_value) = self._create_kpi_card("0", "Unique Customers Today")
        (self.kpi_products_card, self.kpi_products_value) = self._create_kpi_card("0", "Unique Products Today")

        main_layout.addWidget(self.kpi_reports_card, 0, 0)
        main_layout.addWidget(self.kpi_qty_card, 0, 1)
        main_layout.addWidget(self.kpi_customers_card, 0, 2)
        main_layout.addWidget(self.kpi_products_card, 0, 3)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter, 1, 0, 1, 4)
        recent_group = QGroupBox("Recent Reports")
        recent_layout = QVBoxLayout(recent_group)
        self.dashboard_recent_table = QTableWidget()

        self.dashboard_recent_table.setShowGrid(False)
        self.dashboard_recent_table.setStyleSheet("QTableWidget { border: none; }")
        self.dashboard_recent_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.dashboard_recent_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.dashboard_recent_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.dashboard_recent_table.verticalHeader().setVisible(False)
        self.dashboard_recent_table.horizontalHeader().setHighlightSections(False)
        self._configure_table_autosize(self.dashboard_recent_table)
        recent_layout.addWidget(self.dashboard_recent_table)
        splitter.addWidget(recent_group)

        top_customers_group = QGroupBox("Top Customers by Quantity (All Time)")
        chart_layout = QVBoxLayout(top_customers_group)
        self.customer_chart_view = QChartView()
        self.customer_chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.customer_chart = QChart()
        self.customer_pie_series = QPieSeries()
        self.customer_pie_series.setHoleSize(0.35)
        self.customer_pie_series.hovered.connect(self._handle_pie_slice_hover)
        self.customer_chart.addSeries(self.customer_pie_series)
        self.customer_chart.setTitle("Top 5 Customers by Total Received Quantity")
        self.customer_chart.setAnimationOptions(QChart.AnimationOption.SeriesAnimations)
        self.customer_chart.legend().setVisible(True)
        self.customer_chart.legend().setAlignment(Qt.AlignmentFlag.AlignRight)
        self.customer_chart_view.setChart(self.customer_chart)
        chart_layout.addWidget(self.customer_chart_view)
        splitter.addWidget(top_customers_group)
        splitter.setSizes([450, 550])

    def _setup_deleted_tab(self, tab):
        layout = QVBoxLayout(tab)
        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("Search Deleted:"))
        self.deleted_search_edit = UpperCaseLineEdit(placeholderText="Filter by RRRG No, Customer...")
        top_layout.addWidget(self.deleted_search_edit, 1)
        layout.addLayout(top_layout)

        self.deleted_records_table = QTableWidget()
        self.deleted_records_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.deleted_records_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.deleted_records_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.deleted_records_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.deleted_records_table.setShowGrid(False)
        self.deleted_records_table.verticalHeader().setVisible(False)
        self.deleted_records_table.horizontalHeader().setHighlightSections(False)
        self.deleted_records_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._configure_table_autosize(self.deleted_records_table)
        layout.addWidget(self.deleted_records_table)

        self.deleted_search_edit.textChanged.connect(self._load_deleted_records)
        self.deleted_records_table.customContextMenuRequested.connect(self._show_deleted_records_context_menu)

    # --- DELETED TAB METHODS ---
    def _load_deleted_records(self):
        search = f"%{self.deleted_search_edit.text()}%"
        try:
            with self.engine.connect() as conn:
                query = text("""
                    SELECT rr_no, receive_date, receive_from, edited_by, edited_on
                    FROM receiving_reports_primary WHERE is_deleted = TRUE
                    AND (rr_no ILIKE :st OR receive_from ILIKE :st)
                    ORDER BY edited_on DESC
                """)
                res = conn.execute(query, {'st': search}).mappings().all()

            headers = ["RRRG No.", "Date Received", "Received From", "Deleted By", "Deleted On"]
            self._populate_deleted_records_table(res, headers)
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load deleted records: {e}")

    def _populate_deleted_records_table(self, data, headers):
        table = self.deleted_records_table
        table.setRowCount(0)
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        self._configure_table_autosize(table)  # Re-apply in case headers change

        if not data:
            return

        table.setRowCount(len(data))
        keys = ["rr_no", "receive_date", "receive_from", "edited_by", "edited_on"]
        for i, row in enumerate(data):
            for j, key in enumerate(keys):
                value = row.get(key)
                if isinstance(value, date):
                    display_value = QDate(value).toString('yyyy-MM-dd')
                elif isinstance(value, datetime):
                    display_value = QDateTime(value).toString('yyyy-MM-dd hh:mm AP')
                else:
                    display_value = str(value or "")
                table.setItem(i, j, QTableWidgetItem(display_value))

        # Fine-tune column sizes after populating
        table.resizeColumnsToContents()
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

    def _show_deleted_records_context_menu(self, pos):
        if not self.deleted_records_table.selectedItems(): return
        menu = QMenu()
        restore_action = menu.addAction("Restore Record")
        action = menu.exec(self.deleted_records_table.mapToGlobal(pos))
        if action == restore_action:
            self._restore_record()

    def _restore_record(self):
        selected = self.deleted_records_table.selectionModel().selectedRows()
        if not selected: return
        rr_no = self.deleted_records_table.item(selected[0].row(), 0).text()

        reply = QMessageBox.question(self, "Confirm Restore",
                                     f"Are you sure you want to restore Receiving Report <b>{rr_no}</b>?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            try:
                with self.engine.connect() as conn, conn.begin():
                    conn.execute(text(
                        "UPDATE receiving_reports_primary SET is_deleted = FALSE, edited_by = :u, edited_on = :n WHERE rr_no = :rr"),
                        {"u": self.username, "n": datetime.now(), "rr": rr_no})

                self.log_audit_trail("RESTORE_RECEIVING_REPORT", f"Restored report: {rr_no}")
                QMessageBox.information(self, "Success", f"Report {rr_no} has been restored.")
                self._refresh_all_data_views()
            except Exception as e:
                QMessageBox.critical(self, "Database Error", f"Could not restore record: {e}")

    def _refresh_all_data_views(self):
        self._load_all_records()
        self._load_deleted_records()
        self._update_dashboard_data()

    def _load_combobox_data(self):
        try:
            with self.engine.connect() as conn:
                self.warehouses_list = conn.execute(text("SELECT name FROM warehouses ORDER BY name")).scalars().all()
                self.receivers_list = conn.execute(text("SELECT name FROM rr_receivers ORDER BY name")).scalars().all()
                self.reporters_list = conn.execute(text("SELECT name FROM rr_reporters ORDER BY name")).scalars().all()
                customers = conn.execute(
                    text("SELECT name FROM customers WHERE is_deleted IS NOT TRUE ORDER BY name")).scalars().all()

            for combo, data_list in [(self.received_by_combo, self.receivers_list),
                                     (self.reported_by_combo, self.reporters_list)]:
                current_text = combo.currentText()
                combo.clear();
                combo.addItems([""] + data_list);
                combo.setCurrentText(current_text)

            current_customer = self.customer_combo.currentText()
            self.customer_combo.clear();
            self.customer_combo.addItems([""] + customers)
            self.customer_combo.setCurrentText(current_customer)
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load data for dropdowns: {e}")

    def _setup_view_tab(self, tab):
        layout = QVBoxLayout(tab)
        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("Search:"))
        self.search_edit = UpperCaseLineEdit(placeholderText="Filter by RRRG No, POF No, Product Code...")
        top_layout.addWidget(self.search_edit, 1)
        self.update_btn = QPushButton("Load Selected for Update");
        self.update_btn.setObjectName("update_btn")
        self.delete_btn = QPushButton("Delete Selected");
        self.delete_btn.setObjectName("delete_btn")
        top_layout.addWidget(self.update_btn);
        top_layout.addWidget(self.delete_btn)
        layout.addLayout(top_layout)

        self.records_table = QTableWidget()
        self.records_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.records_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.records_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.records_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.records_table.setShowGrid(False)
        self.records_table.verticalHeader().setVisible(False)
        self.records_table.horizontalHeader().setHighlightSections(False)
        self.records_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._configure_table_autosize(self.records_table)
        layout.addWidget(self.records_table)

        pagination_layout = QHBoxLayout()
        self.prev_btn, self.next_btn = QPushButton("<< Previous"), QPushButton("Next >>")
        self.page_label = QLabel("Page 1 of 1")
        pagination_layout.addStretch();
        pagination_layout.addWidget(self.prev_btn)
        pagination_layout.addWidget(self.page_label);
        pagination_layout.addWidget(self.next_btn)
        pagination_layout.addStretch()
        layout.addLayout(pagination_layout)

        self.search_edit.textChanged.connect(self._on_search_text_changed)
        self.records_table.customContextMenuRequested.connect(self._show_records_context_menu)
        self.records_table.itemSelectionChanged.connect(self._on_record_selection_changed)
        self.update_btn.clicked.connect(self._load_record_for_update)
        self.delete_btn.clicked.connect(self._delete_record)
        self.prev_btn.clicked.connect(self._go_to_prev_page)
        self.next_btn.clicked.connect(self._go_to_next_page)
        self._on_record_selection_changed()

    def _setup_view_details_tab(self, tab):
        layout = QVBoxLayout(tab)
        primary_group = QGroupBox("RECEIVING REPORT for RETURNED GOODS (Read-Only)")
        form_layout = QFormLayout(primary_group)
        self.view_receive_from_edit = QLineEdit(readOnly=True);
        self.view_rr_no_edit = QLineEdit(readOnly=True)
        self.view_pull_out_form_edit = QLineEdit(readOnly=True)
        self.view_date_edit = QDateEdit(readOnly=True, buttonSymbols=QDateEdit.ButtonSymbols.NoButtons)
        self.view_remarks_edit = QLineEdit(readOnly=True);
        self.view_received_by_edit = QLineEdit(readOnly=True)
        self.view_reported_by_edit = QLineEdit(readOnly=True);
        self.view_encoded_by = QLineEdit(readOnly=True)
        self.view_edited_by = QLineEdit(readOnly=True)
        form_layout.addRow("Received From:", self.view_receive_from_edit);
        form_layout.addRow("RRRG No:", self.view_rr_no_edit)
        form_layout.addRow("Pull Out Form#:", self.view_pull_out_form_edit);
        form_layout.addRow("Date Received:", self.view_date_edit)

        items_group = QGroupBox("Items")
        items_layout = QVBoxLayout(items_group)
        self.view_items_table = QTableWidget()
        self.view_items_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.view_items_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.view_items_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.view_items_table.setShowGrid(False)
        self.view_items_table.setColumnCount(len(self.item_headers));
        self.view_items_table.setHorizontalHeaderLabels(self.item_headers)
        self.view_items_table.verticalHeader().setVisible(False)
        self.view_items_table.horizontalHeader().setHighlightSections(False)
        self._configure_table_autosize(self.view_items_table)
        items_layout.addWidget(self.view_items_table)

        layout.addWidget(primary_group);
        layout.addWidget(items_group, 1)
        bottom_form_layout = QFormLayout()
        bottom_form_layout.addRow("Remarks:", self.view_remarks_edit)
        bottom_form_layout.addRow("Received and checked by:", self.view_received_by_edit)
        bottom_form_layout.addRow("Reported by:", self.view_reported_by_edit)
        bottom_form_layout.addRow("Encoded by/on:", self.view_encoded_by)
        bottom_form_layout.addRow("Last Edited by/on:", self.view_edited_by)
        layout.addLayout(bottom_form_layout)

    def _setup_entry_tab(self, tab):
        layout = QVBoxLayout(tab)
        primary_group = QGroupBox("RECEIVING REPORT for RETURNED GOODS")
        form_layout = QGridLayout(primary_group)
        self.customer_combo = QComboBox(editable=True);
        self.rr_no_edit = QLineEdit(readOnly=True, placeholderText="Auto-generated")
        self.pull_out_form_edit = UpperCaseLineEdit();
        self.date_edit = QDateEdit(calendarPopup=True, displayFormat="yyyy-MM-dd")
        form_layout.addWidget(QLabel("Received From:"), 0, 0);
        form_layout.addWidget(self.customer_combo, 0, 1, 1, 3)
        form_layout.addWidget(QLabel("RRRG No:"), 1, 0);
        form_layout.addWidget(self.rr_no_edit, 1, 1)
        form_layout.addWidget(QLabel("Pull Out Form#:"), 1, 2);
        form_layout.addWidget(self.pull_out_form_edit, 1, 3)
        form_layout.addWidget(QLabel("Date Received:"), 2, 0);
        form_layout.addWidget(self.date_edit, 2, 1)

        items_group = QGroupBox("Items")
        items_layout = QVBoxLayout(items_group)
        self.items_table = QTableWidget()
        self.items_table.setShowGrid(False)  # Removes the grid/border lines
        self.items_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # Removes the dotted focus rectangle
        self.items_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)  # Sets row selection
        self.items_table.setColumnCount(len(self.item_headers));
        self.items_table.setHorizontalHeaderLabels(self.item_headers)
        self.items_table.verticalHeader().setVisible(False)
        self.items_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._configure_table_autosize(self.items_table)
        items_layout.addWidget(self.items_table)

        items_button_layout = QHBoxLayout();
        add_row_btn = QPushButton("Add Item");
        edit_row_btn = QPushButton("Edit Selected");
        remove_row_btn = QPushButton("Remove Selected")
        items_button_layout.addStretch();
        items_button_layout.addWidget(add_row_btn);
        items_button_layout.addWidget(edit_row_btn);
        items_button_layout.addWidget(remove_row_btn)
        items_layout.addLayout(items_button_layout)
        add_row_btn.clicked.connect(self._show_add_item_dialog);
        edit_row_btn.clicked.connect(self._show_edit_item_dialog)
        self.items_table.doubleClicked.connect(self._show_edit_item_dialog);
        remove_row_btn.clicked.connect(self._remove_item_row)

        layout.addWidget(primary_group);
        layout.addWidget(items_group, 1)

        personnel_group = QGroupBox("Personnel & Remarks")
        bottom_form_layout = QFormLayout(personnel_group)
        self.remarks_edit = QLineEdit()
        self.received_by_combo = QComboBox();
        receiver_layout = self._create_combo_with_add_button(self.received_by_combo, self._add_new_receiver)
        self.reported_by_combo = QComboBox();
        reporter_layout = self._create_combo_with_add_button(self.reported_by_combo, self._add_new_reporter)
        bottom_form_layout.addRow("Remarks:", self.remarks_edit);
        bottom_form_layout.addRow("Received and checked by:", receiver_layout)
        bottom_form_layout.addRow("Reported by:", reporter_layout)
        layout.addWidget(personnel_group)

        self.save_btn = QPushButton("Save Report");
        self.clear_btn = QPushButton("New");
        self.cancel_update_btn = QPushButton("Cancel Update")
        self.print_btn = QPushButton("Print Preview")
        self.save_btn.setObjectName("PrimaryButton");
        self.clear_btn.setObjectName("SecondaryButton")
        button_layout = QHBoxLayout();
        button_layout.addStretch();
        button_layout.addWidget(self.cancel_update_btn)
        button_layout.addWidget(self.clear_btn);
        button_layout.addWidget(self.save_btn)
        button_layout.addWidget(self.print_btn)
        layout.addLayout(button_layout)

        self.save_btn.clicked.connect(self._save_record);
        self.clear_btn.clicked.connect(self._clear_form)
        self.cancel_update_btn.clicked.connect(self._clear_form)
        self.print_btn.clicked.connect(self._print_from_entry_form)
        self._clear_form()

    def _create_combo_with_add_button(self, combo, on_add_clicked):
        layout = QHBoxLayout();
        layout.setContentsMargins(0, 0, 0, 0);
        layout.addWidget(combo, 1)
        add_btn = QPushButton("Manage...");
        add_btn.clicked.connect(on_add_clicked);
        layout.addWidget(add_btn)
        return layout

    def _add_new_receiver(self):
        self._handle_add_new_record("Manage Receivers", "Receiver Name", "rr_receivers", self.received_by_combo)

    def _add_new_reporter(self):
        self._handle_add_new_record("Manage Reporters", "Reporter Name", "rr_reporters", self.reported_by_combo)

    def _handle_add_new_record(self, title, label, table_name, combo_to_update):
        dialog = AddNewRecordDialog(self, title, label, table_name, self.engine)
        if dialog.exec() and dialog.new_record_name:
            self._load_combobox_data();
            combo_to_update.setCurrentText(dialog.new_record_name)

    def _on_record_selection_changed(self):
        is_row_selected = bool(self.records_table.selectionModel().selectedRows())
        self.update_btn.setEnabled(is_row_selected);
        self.delete_btn.setEnabled(is_row_selected)
        self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.view_details_tab), is_row_selected)
        if is_row_selected: self._show_selected_record_in_view_tab()
        if not is_row_selected and self.tab_widget.currentIndex() == self.tab_widget.indexOf(self.view_details_tab):
            self.tab_widget.setCurrentIndex(1)

    def _fetch_record_data(self, rr_no):
        with self.engine.connect() as conn:
            primary = conn.execute(text("SELECT * FROM receiving_reports_primary WHERE rr_no = :rr_no"),
                                   {"rr_no": rr_no}).mappings().one()
            items = conn.execute(text("SELECT * FROM receiving_reports_items WHERE rr_no = :rr_no ORDER BY id"),
                                 {"rr_no": rr_no}).mappings().all()
            return primary, items

    def _show_selected_record_in_view_tab(self):
        selected_rows = self.records_table.selectionModel().selectedRows()
        if not selected_rows: return
        rr_no = self.records_table.item(selected_rows[0].row(), 0).text()
        try:
            primary, items = self._fetch_record_data(rr_no)
            self.view_rr_no_edit.setText(primary['rr_no']);
            self.view_date_edit.setDate(primary['receive_date'])
            self.view_receive_from_edit.setText(primary.get('receive_from', ''))
            self.view_pull_out_form_edit.setText(primary.get('pull_out_form_no', ''))
            self.view_received_by_edit.setText(primary.get('received_by', ''))
            self.view_reported_by_edit.setText(primary.get('reported_by', ''))
            self.view_remarks_edit.setText(primary.get('remarks', ''))
            encoded_info = f"{primary.get('encoded_by', 'N/A')} on {primary.get('encoded_on').strftime('%Y-%m-%d %H:%M') if primary.get('encoded_on') else 'N/A'}"
            edited_info = f"{primary.get('edited_by', 'N/A')} on {primary.get('edited_on').strftime('%Y-%m-%d %H:%M') if primary.get('edited_on') else 'N/A'}"
            self.view_encoded_by.setText(encoded_info);
            self.view_edited_by.setText(edited_info)
            self.view_items_table.setRowCount(0)
            for item_data in items: self._add_item_row_to_table(dict(item_data), table=self.view_items_table)
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load record {rr_no} for viewing: {e}")

    def _load_record_for_update(self):
        selected_rows = self.records_table.selectionModel().selectedRows()
        if not selected_rows: return
        rr_no = self.records_table.item(selected_rows[0].row(), 0).text()
        try:
            primary, items = self._fetch_record_data(rr_no)
            self._clear_form();
            self.current_editing_rr_no = rr_no
            self.rr_no_edit.setText(primary['rr_no']);
            self.date_edit.setDate(primary['receive_date'])
            self.customer_combo.setCurrentText(primary.get('receive_from', ''))
            self.pull_out_form_edit.setText(primary.get('pull_out_form_no', ''))
            self.received_by_combo.setCurrentText(primary.get('received_by', ''))
            self.reported_by_combo.setCurrentText(primary.get('reported_by', ''))
            self.remarks_edit.setText(primary.get('remarks', ''))
            self.items_table.setRowCount(0)
            for item_data in items: self._add_item_row_to_table(dict(item_data), table=self.items_table)
            self.save_btn.setText("Update Report");
            self.cancel_update_btn.show()
            self.print_btn.setEnabled(True)
            self.tab_widget.setCurrentIndex(self.tab_widget.indexOf(self.entry_tab))
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load record {rr_no} for editing: {e}")

    def _add_item_row_to_table(self, data, table):
        row = table.rowCount();
        table.insertRow(row)
        table.setItem(row, 0, QTableWidgetItem(data.get('material_code', '')));
        table.setItem(row, 1, QTableWidgetItem(data.get('lot_no', '')))
        qty_item = QTableWidgetItem(f"{float(data.get('quantity_kg', 0)):.2f}");
        qty_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        table.setItem(row, 2, qty_item);
        table.setItem(row, 3, QTableWidgetItem(data.get('status', '')));
        table.setItem(row, 4, QTableWidgetItem(data.get('location', '')))

    def _show_add_item_dialog(self):
        dialog = AddItemDialog(self, warehouses=self.warehouses_list, engine=self.engine)
        dialog.data_refreshed_signal.connect(self._load_combobox_data)
        if dialog.exec():
            self._add_item_row_to_table(dialog.get_data(), table=self.items_table)

    def _show_edit_item_dialog(self):
        row = self.items_table.currentRow()
        if row < 0: return
        existing_data = {"material_code": self.items_table.item(row, 0).text(),
                         "lot_no": self.items_table.item(row, 1).text(),
                         "quantity_kg": self.items_table.item(row, 2).text(),
                         "status": self.items_table.item(row, 3).text(),
                         "location": self.items_table.item(row, 4).text()}
        dialog = AddItemDialog(self, data=existing_data, warehouses=self.warehouses_list, engine=self.engine)
        dialog.data_refreshed_signal.connect(self._load_combobox_data)
        if dialog.exec():
            new_data = dialog.get_data()
            self.items_table.item(row, 0).setText(new_data['material_code']);
            self.items_table.item(row, 1).setText(new_data['lot_no'])
            self.items_table.item(row, 2).setText(new_data['quantity_kg']);
            self.items_table.item(row, 3).setText(new_data['status'])
            self.items_table.item(row, 4).setText(new_data['location'])

    def _remove_item_row(self):
        if (row := self.items_table.currentRow()) >= 0:
            self.items_table.removeRow(row)
        else:
            QMessageBox.information(self, "Selection Required", "Please select an item to remove.")

    def _show_records_context_menu(self, position):
        if not self.records_table.selectedItems(): return
        menu = QMenu();
        view_action = menu.addAction("View Details");
        edit_action = menu.addAction("Edit Record");
        delete_action = menu.addAction("Delete Record")
        menu.addSeparator()
        print_action = menu.addAction("Print Preview")
        action = menu.exec(self.records_table.mapToGlobal(position))
        if action == view_action:
            self.tab_widget.setCurrentIndex(self.tab_widget.indexOf(self.view_details_tab))
        elif action == edit_action:
            self._load_record_for_update()
        elif action == delete_action:
            self._delete_record()
        elif action == print_action:
            self._print_selected_record()

    def _on_tab_changed(self, index):
        tab_text = self.tab_widget.tabText(index)
        if tab_text == "Dashboard":
            self._update_dashboard_data()
        elif tab_text == "All Reports":
            self._load_all_records()
        elif tab_text == "Report Entry Form" and not self.current_editing_rr_no:
            self._load_combobox_data()
        elif tab_text == "Deleted":
            self._load_deleted_records()

    def _clear_form(self):
        self.current_editing_rr_no = None;
        self.cancel_update_btn.hide();
        self.save_btn.setText("Save Report")
        self.print_btn.setEnabled(False)
        [w.clear() for w in [self.rr_no_edit, self.pull_out_form_edit, self.remarks_edit]]
        self.customer_combo.clearEditText()
        self._load_combobox_data()
        self.received_by_combo.setCurrentIndex(0);
        self.reported_by_combo.setCurrentIndex(0);
        self.customer_combo.setCurrentIndex(-1)
        self.date_edit.setDate(QDate.currentDate());
        self.items_table.setRowCount(0);
        self.customer_combo.setFocus()

    def _save_record(self):
        primary_data = {"receive_date": self.date_edit.date().toPyDate(),
                        "receive_from": self.customer_combo.currentText().strip(),
                        "pull_out_form_no": self.pull_out_form_edit.text().strip(),
                        "received_by": self.received_by_combo.currentText(),
                        "reported_by": self.reported_by_combo.currentText(),
                        "remarks": self.remarks_edit.text().strip(), "edited_by": self.username,
                        "edited_on": datetime.now()}

        # Enhanced Validation
        if not primary_data["pull_out_form_no"]:
            QMessageBox.warning(self, "Validation Error", "The 'Pull Out Form#' field is required before saving.")
            return
        if not primary_data["receive_from"]:
            QMessageBox.warning(self, "Validation Error", "'Received From' is required.")
            return
        if not primary_data["received_by"]:
            QMessageBox.warning(self, "Validation Error", "'Received by' is required.")
            return

        items_data = []
        for row in range(self.items_table.rowCount()):
            try:
                # Validation is now handled in the AddItemDialog, this is a fallback
                item_data = {
                    "material_code": self.items_table.item(row, 0).text().strip(),
                    "lot_no": self.items_table.item(row, 1).text().strip(),
                    "quantity_kg": float(self.items_table.item(row, 2).text()),
                    "status": self.items_table.item(row, 3).text().strip(),
                    "location": self.items_table.item(row, 4).text().strip()
                }
                if not all(item_data.values()) or item_data["quantity_kg"] <= 0:
                    QMessageBox.warning(self, "Data Error",
                                        f"Invalid or incomplete data in items table at row {row + 1}.");
                    return
                items_data.append(item_data)
            except (AttributeError, ValueError, TypeError):
                QMessageBox.warning(self, "Data Error", f"Invalid data format in items table at row {row + 1}.");
                return

        if not items_data:
            QMessageBox.warning(self, "Input Error", "Please add at least one valid item to the report.");
            return

        try:
            with self.engine.connect() as conn, conn.begin():
                if self.current_editing_rr_no:
                    rr_no = self.current_editing_rr_no;
                    primary_data["rr_no"] = rr_no
                    conn.execute(text(
                        "UPDATE receiving_reports_primary SET receive_date=:receive_date, receive_from=:receive_from, pull_out_form_no=:pull_out_form_no, received_by=:received_by, reported_by=:reported_by, remarks=:remarks, edited_by=:edited_by, edited_on=:edited_on WHERE rr_no=:rr_no"),
                        primary_data)
                    conn.execute(text("DELETE FROM receiving_reports_items WHERE rr_no = :rr_no"), {"rr_no": rr_no});
                    self.log_audit_trail("UPDATE_RECEIVING_REPORT", f"Updated: {rr_no}");
                    action_text = "updated"
                else:
                    rr_no = self._generate_rr_no();
                    primary_data["rr_no"] = rr_no;
                    primary_data["encoded_by"] = self.username;
                    primary_data["encoded_on"] = datetime.now()
                    conn.execute(text(
                        "INSERT INTO receiving_reports_primary (rr_no, receive_date, receive_from, pull_out_form_no, received_by, reported_by, remarks, encoded_by, encoded_on, edited_by, edited_on) VALUES (:rr_no, :receive_date, :receive_from, :pull_out_form_no, :received_by, :reported_by, :remarks, :encoded_by, :encoded_on, :edited_by, :edited_on)"),
                        primary_data)
                    self.log_audit_trail("CREATE_RECEIVING_REPORT", f"Created: {rr_no}");
                    action_text = "saved"
                for item in items_data: item["rr_no"] = rr_no
                conn.execute(text(
                    "INSERT INTO receiving_reports_items (rr_no, material_code, lot_no, quantity_kg, status, location) VALUES (:rr_no, :material_code, :lot_no, :quantity_kg, :status, :location)"),
                    items_data)
            QMessageBox.information(self, "Success", f"Receiving Report {rr_no} {action_text} successfully.");
            self._clear_form();
            self._refresh_all_data_views();
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"An error occurred: {e}")

    def _load_all_records(self):
        search = f"%{self.search_edit.text()}%"
        offset = (self.current_page - 1) * self.records_per_page
        try:
            with self.engine.connect() as conn:
                count_query_base = "FROM receiving_reports_primary p LEFT JOIN receiving_reports_items i ON p.rr_no = i.rr_no WHERE p.is_deleted IS NOT TRUE"
                filter_clause = ""
                params = {'limit': self.records_per_page, 'offset': offset}
                if self.search_edit.text():
                    filter_clause = " AND (p.rr_no ILIKE :st OR p.pull_out_form_no ILIKE :st OR i.material_code ILIKE :st OR p.receive_from ILIKE :st)"
                    params['st'] = search

                count_res = conn.execute(text(f"SELECT COUNT(DISTINCT p.id) {count_query_base} {filter_clause}"),
                                         {'st': search} if self.search_edit.text() else {}).scalar_one()
                self.total_records = count_res

                query = text(f"""
                    SELECT p.rr_no, p.receive_date, p.receive_from, p.pull_out_form_no, p.received_by
                    FROM receiving_reports_primary p
                    LEFT JOIN receiving_reports_items i ON p.rr_no = i.rr_no
                    WHERE p.is_deleted IS NOT TRUE {filter_clause}
                    GROUP BY p.id, p.rr_no, p.receive_date, p.receive_from, p.pull_out_form_no, p.received_by
                    ORDER BY p.id DESC LIMIT :limit OFFSET :offset
                """)
                res = conn.execute(query, params).mappings().all()

            headers = ["RRRG No.", "Date Received", "Received From", "Pull Out Form#", "Received By"]
            self._populate_records_table(res, headers)
            self._update_pagination_controls()
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load receiving reports: {e}")

    def _update_pagination_controls(self):
        self.total_pages = (self.total_records + self.records_per_page - 1) // self.records_per_page or 1
        self.page_label.setText(f"Page {self.current_page} of {self.total_pages}")
        self.prev_btn.setEnabled(self.current_page > 1)
        self.next_btn.setEnabled(self.current_page < self.total_pages)

    def _on_search_text_changed(self):
        self.current_page = 1
        self._load_all_records()

    def _go_to_prev_page(self):
        if self.current_page > 1: self.current_page -= 1; self._load_all_records()

    def _go_to_next_page(self):
        if self.current_page < self.total_pages: self.current_page += 1; self._load_all_records()

    # In ReceivingReportPage class
    # Replace the entire existing _delete_record method with this one.

    def _delete_record(self):
        selected_rows = self.records_table.selectionModel().selectedRows()
        if not selected_rows: return

        rr_no = self.records_table.item(selected_rows[0].row(), 0).text()

        # First, confirm the user's intent to delete.
        reply = QMessageBox.question(self, "Confirm Deletion",
                                     f"Are you sure you want to delete Receiving Report <b>{rr_no}</b>?<br><br>"
                                     "This will move the record to the 'Deleted' tab.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.No:
            return  # User cancelled the action

        # --- NEW: Password Prompt ---
        # If they confirmed, now ask for the password.
        # We need to import QInputDialog for this to work.
        from PyQt6.QtWidgets import QInputDialog

        password, ok = QInputDialog.getText(
            self,
            "Admin Action Required",
            "Enter the administrator password to proceed with deletion:",
            QLineEdit.EchoMode.Password
        )

        if not ok:
            return  # User cancelled the password dialog

        if password != "Itadmin":
            QMessageBox.critical(self, "Access Denied", "Incorrect password. The record was not deleted.")
            return
        # --- END OF NEW CODE ---

        # If the password is correct, proceed with the deletion logic.
        try:
            with self.engine.connect() as conn, conn.begin():
                conn.execute(text(
                    "UPDATE receiving_reports_primary SET is_deleted = TRUE, edited_by = :u, edited_on = :n WHERE rr_no = :rr"),
                    {"u": self.username, "n": datetime.now(), "rr": rr_no}
                )

            self.log_audit_trail("DELETE_RECEIVING_REPORT", f"Soft-deleted report: {rr_no}")
            QMessageBox.information(self, "Success", f"Report {rr_no} has been moved to the Deleted tab.")
            self._refresh_all_data_views()
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Could not delete record: {e}")

    def _generate_rr_no(self):
        prefix = f"RRRG{datetime.now().strftime('%y%m')}"
        with self.engine.connect() as conn:
            last_ref = conn.execute(
                text("SELECT rr_no FROM receiving_reports_primary WHERE rr_no LIKE :p ORDER BY rr_no DESC LIMIT 1"),
                {"p": f"{prefix}%"}
            ).scalar_one_or_none()

            last_seq = 0
            if last_ref and last_ref.startswith(prefix):
                try:
                    last_seq = int(last_ref[len(prefix):])
                except (ValueError, IndexError):
                    pass  # Fallback to 0 if format is unexpected

            return f"{prefix}{(last_seq + 1):03d}"

    def _populate_records_table(self, data, headers):
        table = self.records_table
        table.setRowCount(0);
        table.setColumnCount(len(headers));
        table.setHorizontalHeaderLabels(headers)
        self._configure_table_autosize(table)

        if not data: return

        table.setRowCount(len(data))
        for i, row_data in enumerate(data):
            keys = list(row_data.keys())
            for j, key in enumerate(keys):
                value = row_data.get(key)
                item_text = str(value) if not isinstance(value, date) else QDate(value).toString("yyyy-MM-dd")
                table.setItem(i, j, QTableWidgetItem(item_text))

        # Fine-tune after populating
        table.resizeColumnsToContents()
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

    def _print_from_entry_form(self):
        if not self.current_editing_rr_no:
            QMessageBox.warning(self, "No Record Loaded", "Please load a record to print.")
            return

        primary_data = {
            "rr_no": self.rr_no_edit.text(),
            "receive_date": self.date_edit.date().toString("MM/dd/yy"),
            "receive_from": self.customer_combo.currentText(),
            "pull_out_form_no": self.pull_out_form_edit.text(),
            "received_by": self.received_by_combo.currentText(),
            "reported_by": self.reported_by_combo.currentText(),
            "remarks": self.remarks_edit.text()
        }
        items_data = []
        for row in range(self.items_table.rowCount()):
            items_data.append({
                "material_code": self.items_table.item(row, 0).text(),
                "lot_no": self.items_table.item(row, 1).text(),
                "quantity_kg": self.items_table.item(row, 2).text(),
                "status": self.items_table.item(row, 3).text(),
                "location": self.items_table.item(row, 4).text()
            })

        self._initiate_print_preview(primary_data, items_data)

    def _print_selected_record(self):
        selected_rows = self.records_table.selectionModel().selectedRows()
        if not selected_rows: return
        rr_no = self.records_table.item(selected_rows[0].row(), 0).text()

        try:
            primary_db, items_db = self._fetch_record_data(rr_no)
            primary_data = {
                "rr_no": primary_db.get('rr_no'),
                "receive_date": primary_db.get('receive_date').strftime("%m/%d/%y"),
                "receive_from": primary_db.get('receive_from'),
                "pull_out_form_no": primary_db.get('pull_out_form_no'),
                "received_by": primary_db.get('received_by'),
                "reported_by": primary_db.get('reported_by'),
                "remarks": primary_db.get('remarks')
            }
            items_data = [dict(item) for item in items_db]
            self._initiate_print_preview(primary_data, items_data)
        except Exception as e:
            QMessageBox.critical(self, "Data Fetch Error", f"Could not fetch data for printing {rr_no}: {e}")

    def _initiate_print_preview(self, primary_data, items_data):
        try:
            self.current_pdf_buffer = self._generate_report_pdf(primary_data, items_data)
            if self.current_pdf_buffer is None: return
        except Exception as e:
            QMessageBox.critical(self, "PDF Generation Error", f"Could not generate PDF: {e}")
            return

        custom_size = QSizeF(8.5, 5.5)
        custom_page_size = QPageSize(custom_size, QPageSize.Unit.Inch, "RRRG Form")
        self.printer.setPageSize(custom_page_size)
        self.printer.setFullPage(True)

        preview = QPrintPreviewDialog(self.printer, self)
        preview.paintRequested.connect(self._handle_paint_request)
        preview.resize(1000, 800)
        preview.exec()

    def _handle_paint_request(self, printer: QPrinter):
        if not self.current_pdf_buffer: return
        painter = QPainter()
        if not painter.begin(printer):
            QMessageBox.critical(self, "Print Error", "Could not initialize painter.")
            return
        self.current_pdf_buffer.seek(0)
        pdf_doc = fitz.open(stream=self.current_pdf_buffer, filetype="pdf")
        dpi = 300
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        page_rect_dev_pixels = printer.pageRect(QPrinter.Unit.DevicePixel)

        for i, page in enumerate(pdf_doc):
            if i > 0: printer.newPage()
            pix = page.get_pixmap(matrix=mat, alpha=False)
            image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
            painter.drawImage(page_rect_dev_pixels.toRect(), image, image.rect())
        pdf_doc.close()
        painter.end()

    def _draw_page_template(self, canvas, doc, header_table, footer_table):
        canvas.saveState()
        page_width, page_height = doc.pagesize
        header_table.wrapOn(canvas, doc.width, doc.topMargin)
        header_table.drawOn(canvas, doc.leftMargin, page_height - header_table._height - (0.2 * inch))
        footer_table.wrapOn(canvas, doc.width, doc.bottomMargin)
        footer_table.drawOn(canvas, doc.leftMargin, 0.2 * inch)
        canvas.restoreState()

    def _generate_report_pdf(self, primary_data, items_data):
        try:
            pdfmetrics.registerFont(TTFont('LucidaSans', 'C:/Windows/Fonts/LSANS.TTF'))
            pdfmetrics.registerFont(TTFont('LucidaSans-Bold', 'C:/Windows/Fonts/LTYPEB.TTF'))
            pdfmetrics.registerFontFamily('LucidaSans', normal='LucidaSans', bold='LucidaSans-Bold')
        except Exception:
            try:
                pdfmetrics.registerFont(TTFont('Arial', 'arial.ttf'))
                pdfmetrics.registerFont(TTFont('Arial-Bold', 'arialbd.ttf'))
                pdfmetrics.registerFontFamily('LucidaSans', normal='Arial', bold='Arial-Bold')
            except Exception as e:
                QMessageBox.critical(self, "Font Error",
                                     f"Could not register fallback font 'Arial'. Ensure it is installed.\nError: {e}")
                return None

        buffer = io.BytesIO()
        page_width, page_height = (8.5 * inch, 5.5 * inch)
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name='MainStyle', fontName='LucidaSans', fontSize=9, leading=10))
        styles.add(ParagraphStyle(name='MainStyleBold', parent=styles['MainStyle'], fontName='LucidaSans-Bold'))
        styles.add(ParagraphStyle(name='MainStyleRight', parent=styles['MainStyle'], alignment=TA_RIGHT))
        styles.add(ParagraphStyle(name='MainStyleBoldRight', parent=styles['MainStyleBold'], alignment=TA_RIGHT))
        styles.add(ParagraphStyle(name='MainStyleCenter', parent=styles['MainStyle'], alignment=TA_CENTER))
        styles.add(ParagraphStyle(name='MainStyleBoldCenter', parent=styles['MainStyleBold'], alignment=TA_CENTER))
        styles.add(ParagraphStyle(name='Footer', fontName='LucidaSans-Bold', fontSize=8, leading=9))
        styles.add(ParagraphStyle(name='FooterSig', fontName='LucidaSans', fontSize=8, alignment=TA_CENTER))
        styles.add(ParagraphStyle(name='FooterSub', fontName='LucidaSans', fontSize=7, alignment=TA_CENTER))
        styles.add(ParagraphStyle(name='RemarkStyle', fontName='LucidaSans', fontSize=8, leading=9, leftIndent=5))

        header_left_text = """<font name='LucidaSans-Bold' size='12'>MASTERBATCH PHILIPPINES INC.</font><br/><font size='8'>24 Diamond Road, Caloocan Industrial Subd., Bo. Kaybiga Caloocan City</font><br/><font size='8'>Tel. Nos.: 8935-93-75 | 8935-93-76 | 7738-1207</font>"""
        header_right_text = f"""<font name='LucidaSans-Bold' size='12'>RECEIVING REPORT</font><br/><font name='LucidaSans-Bold' size='12'>FOR RETURNED GOODS</font><br/><br/><font name='LucidaSans-Bold' size='11'>RRRG No.: {primary_data['rr_no']}</font>"""
        header_table = Table([[Paragraph(header_left_text, styles['MainStyle']),
                               Paragraph(header_right_text, styles['MainStyleBoldRight'])]],
                             colWidths=[4.8 * inch, 2.8 * inch], style=[('VALIGN', (0, 0), (-1, -1), 'TOP')])

        signature_line = "_" * 25
        footer_data = [
            [Paragraph("Received and checked by:", styles['Footer']), Paragraph("Reported by:", styles['Footer']),
             Paragraph("Noted by:", styles['Footer'])],
            [Paragraph(f"<br/>{primary_data.get('received_by', '').upper()}", styles['FooterSig']),
             Paragraph(f"<br/>{primary_data.get('reported_by', '').upper()}", styles['FooterSig']),
             Paragraph("<br/>", styles['FooterSig'])],
            [Paragraph(signature_line, styles['FooterSig']), Paragraph(signature_line, styles['FooterSig']),
             Paragraph(signature_line, styles['FooterSig'])],
            [Paragraph("Signature Over Printed Name", styles['FooterSub']),
             Paragraph("Signature Over Printed Name", styles['FooterSub']),
             Paragraph("Signature Over Printed Name", styles['FooterSub'])]]
        footer_table = Table(footer_data, colWidths=[2.6 * inch] * 3,
                             rowHeights=[0.15 * inch, 0.25 * inch, 0.05 * inch, 0.15 * inch])
        footer_table.setStyle(
            TableStyle([('VALIGN', (0, 0), (-1, -1), 'BOTTOM'), ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))

        _, header_height = header_table.wrap(page_width, page_height)
        _, footer_height = footer_table.wrap(page_width, page_height)
        doc = SimpleDocTemplate(buffer, pagesize=(page_width, page_height), leftMargin=0.3 * inch,
                                rightMargin=0.3 * inch, topMargin=header_height + 0.3 * inch,
                                bottomMargin=footer_height + 0.25 * inch)
        Story = []

        details_data = [
            [Paragraph(f"<b>Received From:</b> {primary_data['receive_from']}", styles['MainStyle']),
             Paragraph(f"<b>Date Received:</b> {primary_data['receive_date']}", styles['MainStyle'])],
            [Paragraph(f"<b>Pull Out Form#:</b> {primary_data['pull_out_form_no']}", styles['MainStyle']), ""]]
        details_table = Table(details_data, colWidths=[5.4 * inch, 2.5 * inch])
        details_table.setStyle(
            TableStyle([('GRID', (0, 0), (-1, -1), 0.5, colors.black), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('LEFTPADDING', (0, 0), (-1, -1), 5), ('SPAN', (1, 1), (1, 1))]))
        Story.append(details_table)

        MAX_CONTENT_ROWS = 10
        items_tbl_headers = ["Product Code", "Lot no.", "Quantity (kg)", "Status", "Location"]
        items_tbl_data = [[Paragraph(f'<b>{h}</b>', styles['MainStyleBoldCenter']) for h in items_tbl_headers]]
        row_heights = [0.25 * inch]

        styles_dyn = [
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ('LINEBELOW', (0, 0), (-1, 0), 0.5, colors.black),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ]

        for item in items_data:
            if len(items_tbl_data) > MAX_CONTENT_ROWS: break
            qty_val = item.get('quantity_kg', 0)
            qty_str = f"{float(qty_val):.2f}" if qty_val else "0.00"
            items_tbl_data.append([
                Paragraph(str(item.get('material_code', '')), styles['MainStyle']),
                Paragraph(str(item.get('lot_no', '')), styles['MainStyle']),
                Paragraph(qty_str, styles['MainStyleRight']),
                Paragraph(str(item.get('status', '')), styles['MainStyleCenter']),
                Paragraph(str(item.get('location', '')), styles['MainStyleCenter'])])
            row_heights.append(0.22 * inch)

        remarks_text = primary_data.get('remarks', '').strip()
        if remarks_text:
            if len(items_tbl_data) <= MAX_CONTENT_ROWS:
                remark_idx = len(items_tbl_data)
                remark_para = Paragraph(f"<b>Remarks:</b> {remarks_text}", styles['RemarkStyle'])
                items_tbl_data.append([remark_para, '', '', '', ''])
                row_heights.append(0.5 * inch)
                styles_dyn.extend([
                    ('SPAN', (0, remark_idx), (-1, remark_idx)),
                    ('VALIGN', (0, remark_idx), (-1, remark_idx), 'TOP'),
                    ('TOPPADDING', (0, remark_idx), (-1, remark_idx), 5)
                ])

        if len(items_tbl_data) <= MAX_CONTENT_ROWS:
            nf_idx = len(items_tbl_data)
            items_tbl_data.append([Paragraph("***** NOTHING FOLLOWS *****", styles['MainStyleCenter']), '', '', '', ''])
            row_heights.append(0.22 * inch)
            styles_dyn.append(('SPAN', (0, nf_idx), (-1, nf_idx)))

        while len(items_tbl_data) <= MAX_CONTENT_ROWS:
            items_tbl_data.append([''] * len(items_tbl_headers))
            row_heights.append(0.22 * inch)

        styles_dyn.append(('LINEBELOW', (0, len(items_tbl_data) - 1), (-1, len(items_tbl_data) - 1), 0.5, colors.black))

        items_table = Table(items_tbl_data,
                            colWidths=[2.0 * inch, 2.0 * inch, 1.2 * inch, 1.3 * inch, 1.4 * inch],
                            rowHeights=row_heights)
        items_table.setStyle(TableStyle(styles_dyn))
        Story.append(items_table)

        doc.build(Story, onFirstPage=partial(self._draw_page_template, header_table=header_table,
                                             footer_table=footer_table))
        buffer.seek(0)
        return buffer

    def _handle_pie_slice_hover(self, slice_item: QPieSlice, state: bool):
        if state:
            slice_item.setExploded(True)
            slice_item.setLabel(f"{slice_item.label()} ({slice_item.percentage():.1%})")
        else:
            slice_item.setExploded(False)
            original_label = slice_item.label().split(" (")[0]
            slice_item.setLabel(original_label)

    def _populate_table_generic(self, table, data, headers):
        table.setRowCount(0);
        table.setColumnCount(len(headers));
        table.setHorizontalHeaderLabels(headers)
        self._configure_table_autosize(table)

        if not data: return

        table.setRowCount(len(data));
        keys = list(data[0].keys()) if data else []
        for i, row_data in enumerate(data):
            for j, key in enumerate(keys):
                value = row_data.get(key)
                if isinstance(value, (float, Decimal)):
                    item_text = f"{float(value):.2f}"
                elif isinstance(value, date):
                    item_text = QDate(value).toString('yyyy-MM-dd')
                else:
                    item_text = str(value or "")
                item = QTableWidgetItem(item_text)
                if isinstance(value, (float, Decimal)): item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(i, j, item)

    def _update_dashboard_data(self):
        try:
            with self.engine.connect() as conn:
                reports_today = conn.execute(text(
                    "SELECT COUNT(*) FROM receiving_reports_primary WHERE receive_date = CURRENT_DATE AND is_deleted IS NOT TRUE")).scalar_one_or_none() or 0
                qty_today = conn.execute(text(
                    "SELECT SUM(i.quantity_kg) FROM receiving_reports_items i JOIN receiving_reports_primary p ON i.rr_no = p.rr_no WHERE p.receive_date = CURRENT_DATE AND p.is_deleted IS NOT TRUE")).scalar_one_or_none() or Decimal(
                    '0.00')
                customers_today = conn.execute(text(
                    "SELECT COUNT(DISTINCT receive_from) FROM receiving_reports_primary WHERE receive_date = CURRENT_DATE AND is_deleted IS NOT TRUE")).scalar_one_or_none() or 0
                products_today = conn.execute(text(
                    "SELECT COUNT(DISTINCT i.material_code) FROM receiving_reports_items i JOIN receiving_reports_primary p ON i.rr_no = p.rr_no WHERE p.receive_date = CURRENT_DATE AND p.is_deleted IS NOT TRUE")).scalar_one_or_none() or 0
                recent_reports = conn.execute(text(
                    "SELECT rr_no, receive_from, receive_date FROM receiving_reports_primary WHERE is_deleted IS NOT TRUE ORDER BY id DESC LIMIT 5")).mappings().all()
                top_customers = conn.execute(text(
                    "SELECT p.receive_from, SUM(i.quantity_kg) as total_quantity FROM receiving_reports_primary p JOIN receiving_reports_items i ON p.rr_no = i.rr_no WHERE p.is_deleted IS NOT TRUE GROUP BY p.receive_from ORDER BY total_quantity DESC LIMIT 5")).mappings().all()

            self.kpi_reports_value.setText(str(reports_today))
            self.kpi_qty_value.setText(f"{float(qty_today):.2f}")
            self.kpi_customers_value.setText(str(customers_today))
            self.kpi_products_value.setText(str(products_today))

            self.dashboard_recent_table.setRowCount(len(recent_reports))
            self.dashboard_recent_table.setColumnCount(3)
            self.dashboard_recent_table.setHorizontalHeaderLabels(["RRRG No.", "Customer", "Date"])
            self._configure_table_autosize(self.dashboard_recent_table)

            for row, record in enumerate(recent_reports):
                self.dashboard_recent_table.setItem(row, 0, QTableWidgetItem(record['rr_no']))
                self.dashboard_recent_table.setItem(row, 1, QTableWidgetItem(record['receive_from']))
                self.dashboard_recent_table.setItem(row, 2, QTableWidgetItem(
                    QDate(record['receive_date']).toString("yyyy-MM-dd")))

            self.dashboard_recent_table.resizeColumnsToContents()
            self.dashboard_recent_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

            # --- Pie Chart Logic ---
            self.customer_pie_series.clear()
            if not top_customers:
                self.customer_chart.setTitle("Top 5 Customers by Total Received Quantity (No Data)")
                return

            self.customer_chart.setTitle("Top 5 Customers by Total Received Quantity")

            for customer in top_customers:
                name = customer['receive_from']
                total_quantity = float(customer.get('total_quantity') or 0.0)
                slice_item = self.customer_pie_series.append(f"{name}\n{total_quantity:.2f} kg", total_quantity)
                slice_item.setLabelVisible(True)

        except Exception as e:
            QMessageBox.critical(self, "Dashboard Error", f"Could not load dashboard data: {e}")