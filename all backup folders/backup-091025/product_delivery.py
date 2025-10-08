# product_delivery.py
# MODIFIED - Removed the "Dashboard" tab and all associated UI and logic.
# FINAL - Dashboard now updates in real-time based on user actions across all relevant tabs.
# REVISED - Revamped Lot Breakdown Tool for better UX: DR dropdown, auto lot calculation, and save functionality.
# ENHANCED - Integrated advanced lot breakdown logic from fg_endorsement.py
# FIXED - Completely refactored Lot Breakdown Tool logic to be standalone and have no excess quantity.
# ENHANCED - Upgraded dashboard chart to an interactive pie chart and removed dashboard table borders.
# NEW - Added selectable DR Templates ('Standard' and 'Terumo') for different item entry workflows.
# FIX - Resolved 'copy' column error by correctly converting SQLAlchemy Row to dict before processing.
# REVISED - Improved PDF generation to consistently display special descriptions regardless of entry method.

import sys
import io
import re
from datetime import datetime, date
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from functools import partial
import math
import socket
import uuid

# --- ReportLab & PyMuPDF Imports ---
import fitz
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Frame, KeepInFrame,
                                Image as ReportLabImage)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# --- PyQt6 Imports ---
from PyQt6.QtCore import Qt, QDate, QSize, QSizeF, QDateTime, QRect, QRegularExpression
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QTabWidget, QFormLayout, QLineEdit, QDateEdit,
                             QPushButton, QTableWidget, QTableWidgetItem, QComboBox,
                             QAbstractItemView, QHeaderView, QMessageBox, QHBoxLayout, QLabel,
                             QGroupBox, QMenu, QGridLayout, QDialog, QDialogButtonBox,
                             QPlainTextEdit, QSplitter, QCheckBox, QInputDialog)
from PyQt6.QtGui import (QDoubleValidator, QPainter, QPageSize, QColor, QIntValidator, QImage,
                         QRegularExpressionValidator, QFont)
from PyQt6.QtPrintSupport import QPrinter, QPrintPreviewDialog


# --- Database Imports ---
from sqlalchemy import create_engine, text

# --- NEW: QR Code Import ---
import qrcode


class FloatLineEdit(QLineEdit):
    """ A QLineEdit for float values, formatted to 2 decimal places. """

    def __init__(self, parent=None):
        super().__init__(parent)
        validator = QDoubleValidator(0.0, 99999999.0, 6)
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


class UpperCaseLineEdit(QLineEdit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.textChanged.connect(self._to_upper)

    def _to_upper(self, text: str):
        self.blockSignals(True)
        self.setText(text.upper())
        self.blockSignals(False)


class StandardItemEntryDialog(QDialog):
    def __init__(self, db_engine, units, prod_codes, item_data=None, parent=None):
        super().__init__(parent)
        self.engine = db_engine
        self.setWindowTitle("Enter Item Details (Standard)")
        self.setMinimumWidth(450)
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.quantity_edit = QLineEdit("0.00")
        self.quantity_edit.setValidator(QDoubleValidator(0.0, 9999999.99, 2))
        self.unit_edit = QComboBox(editable=True)
        self.unit_edit.addItems(units)
        self.product_code_edit = QComboBox(editable=True)
        self.product_code_edit.addItems(prod_codes)
        self.product_color_edit = QComboBox(editable=True)
        self.no_packing_edit = QLineEdit("0")
        self.no_packing_edit.setValidator(QIntValidator(0, 9999))
        self.weight_pack_edit = QLineEdit("0.00")
        self.weight_pack_edit.setValidator(QDoubleValidator(0.0, 9999.99, 2))
        self.unit_price_edit = QLineEdit("0.00")
        self.unit_price_edit.setValidator(QDoubleValidator(0.0, 999999.99, 2))
        self.lot_numbers_edit = QPlainTextEdit()  # Single text box for multiple lots
        self.attachments_edit = QPlainTextEdit()

        form_layout.addRow("Quantity:", self.quantity_edit)
        form_layout.addRow("Unit:", self.unit_edit)
        form_layout.addRow("Product Code:", self.product_code_edit)
        form_layout.addRow("Product Color:", self.product_color_edit)
        form_layout.addRow("No. of Packing:", self.no_packing_edit)
        form_layout.addRow("Weight/Pack:", self.weight_pack_edit)
        form_layout.addRow("Unit Price (for receipt):", self.unit_price_edit)
        form_layout.addRow("Lot No(s):", self.lot_numbers_edit)
        form_layout.addRow("Attachments/Remarks:", self.attachments_edit)
        layout.addLayout(form_layout)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.product_code_edit.currentTextChanged.connect(self._on_prod_code_changed)

        if item_data:
            self.populate_data(item_data)
        else:
            self.unit_edit.setCurrentText("KG.")

    def _on_prod_code_changed(self, prod_code):
        self.product_color_edit.clear()
        if not prod_code:
            return
        try:
            with self.engine.connect() as conn:
                query = text(
                    "SELECT DISTINCT prod_color FROM legacy_production WHERE prod_code = :code AND prod_color IS NOT NULL AND prod_color != ''")
                colors = conn.execute(query, {"code": prod_code}).scalars().all()
            if colors:
                self.product_color_edit.addItems(colors)
        except Exception as e:
            print(f"Error fetching product color: {e}")

    def populate_data(self, data):
        self.quantity_edit.setText(str(data.get("quantity", "0.00")))
        self.unit_edit.setCurrentText(data.get("unit", "KG."))
        self.product_code_edit.setCurrentText(data.get("product_code", ""))
        self._on_prod_code_changed(data.get("product_code", ""))
        self.product_color_edit.setCurrentText(data.get("product_color", ""))
        self.no_packing_edit.setText(str(data.get("no_of_packing", "0")))
        self.weight_pack_edit.setText(str(data.get("weight_per_pack", "0.00")))
        self.unit_price_edit.setText(str(data.get("unit_price", "0.00")))

        # Combine lot numbers back into the single text box
        lot_numbers_text = "\n".join(
            filter(None, [data.get("lot_no_1", ""), data.get("lot_no_2", ""), data.get("lot_no_3", "")]))
        self.lot_numbers_edit.setPlainText(lot_numbers_text)

        self.attachments_edit.setPlainText(data.get("attachments", ""))

    def get_item_data(self):
        return {
            "quantity": self.quantity_edit.text(), "unit": self.unit_edit.currentText().upper(),
            "product_code": self.product_code_edit.currentText().upper(),
            "product_color": self.product_color_edit.currentText().upper(),
            "no_of_packing": self.no_packing_edit.text(), "weight_per_pack": self.weight_pack_edit.text(),
            "unit_price": self.unit_price_edit.text(),
            "lot_numbers_text": self.lot_numbers_edit.toPlainText(),  # Return the raw text
            "attachments": self.attachments_edit.toPlainText()
        }


class TerumoItemEntryDialog(QDialog):
    def __init__(self, db_engine, units, prod_codes, item_data=None, parent=None):
        super().__init__(parent)
        self.engine = db_engine
        self.setWindowTitle("Enter Item Details (Terumo)")
        self.setMinimumWidth(450)
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.quantity_edit = QLineEdit("0.00")
        self.quantity_edit.setValidator(QDoubleValidator(0.0, 9999999.99, 2))
        self.unit_edit = QComboBox(editable=True)
        self.unit_edit.addItems(units)
        self.product_code_edit = QComboBox(editable=True)
        self.product_code_edit.addItems(prod_codes)
        self.product_color_edit = QComboBox(editable=True)
        self.no_packing_edit = QLineEdit("0")
        self.no_packing_edit.setValidator(QIntValidator(0, 9999))
        self.weight_pack_edit = QLineEdit("0.00")
        self.weight_pack_edit.setValidator(QDoubleValidator(0.0, 9999.99, 2))
        self.unit_price_edit = QLineEdit("0.00")
        self.unit_price_edit.setValidator(QDoubleValidator(0.0, 999999.99, 2))

        self.lot_no_1_edit = UpperCaseLineEdit()
        self.lot_no_2_edit = UpperCaseLineEdit()
        self.lot_no_3_edit = UpperCaseLineEdit()

        self.attachments_edit = QPlainTextEdit()

        self.description_1_edit = QLineEdit()
        self.description_2_edit = QLineEdit()

        form_layout.addRow("Quantity:", self.quantity_edit)
        form_layout.addRow("Unit:", self.unit_edit)
        form_layout.addRow("Product Code:", self.product_code_edit)
        form_layout.addRow("Product Color:", self.product_color_edit)
        form_layout.addRow("No. of Packing:", self.no_packing_edit)
        form_layout.addRow("Weight/Pack:", self.weight_pack_edit)
        form_layout.addRow("Unit Price (for receipt):", self.unit_price_edit)
        form_layout.addRow("Lot No. 1:", self.lot_no_1_edit)
        form_layout.addRow("Lot No. 2:", self.lot_no_2_edit)
        form_layout.addRow("Lot No. 3:", self.lot_no_3_edit)
        form_layout.addRow("Attachments/Remarks:", self.attachments_edit)
        layout.addLayout(form_layout)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.product_code_edit.currentTextChanged.connect(self._on_prod_code_changed)

        if item_data:
            self.populate_data(item_data)
        else:
            self.unit_edit.setCurrentText("KG.")

    def _on_prod_code_changed(self, prod_code):
        self.product_color_edit.clear()

        descriptions = self.parent()._get_special_descriptions(prod_code)
        self.description_1_edit.setText(descriptions.get("ter1", ""))
        self.description_2_edit.setText(descriptions.get("ter2", ""))

        if not prod_code:
            return

        try:
            with self.engine.connect() as conn:
                query = text(
                    "SELECT DISTINCT prod_color FROM legacy_production WHERE prod_code = :code AND prod_color IS NOT NULL AND prod_color != ''")
                colors = conn.execute(query, {"code": prod_code}).scalars().all()

            if colors:
                self.product_color_edit.addItems(colors)
        except Exception as e:
            print(f"Error fetching product color: {e}")

    def populate_data(self, data):
        self.quantity_edit.setText(str(data.get("quantity", "0.00")))
        self.unit_edit.setCurrentText(data.get("unit", "KG."))
        self.product_code_edit.setCurrentText(data.get("product_code", ""))
        self._on_prod_code_changed(data.get("product_code", ""))
        self.product_color_edit.setCurrentText(data.get("product_color", ""))
        self.no_packing_edit.setText(str(data.get("no_of_packing", "0")))
        self.weight_pack_edit.setText(str(data.get("weight_per_pack", "0.00")))
        self.unit_price_edit.setText(str(data.get("unit_price", "0.00")))
        self.lot_no_1_edit.setText(data.get("lot_no_1", ""))
        self.lot_no_2_edit.setText(data.get("lot_no_2", ""))
        self.lot_no_3_edit.setText(data.get("lot_no_3", ""))
        self.description_1_edit.setText(data.get("description_1", ""))
        self.description_2_edit.setText(data.get("description_2", ""))
        self.attachments_edit.setPlainText(data.get("attachments", ""))

    def get_item_data(self):
        return {"quantity": self.quantity_edit.text(), "unit": self.unit_edit.currentText().upper(),
                "product_code": self.product_code_edit.currentText().upper(),
                "product_color": self.product_color_edit.currentText().upper(),
                "no_of_packing": self.no_packing_edit.text(), "weight_per_pack": self.weight_pack_edit.text(),
                "unit_price": self.unit_price_edit.text(),
                "lot_no_1": self.lot_no_1_edit.text(),
                "lot_no_2": self.lot_no_2_edit.text(),
                "lot_no_3": self.lot_no_3_edit.text(),
                "description_1": self.description_1_edit.text(),
                "description_2": self.description_2_edit.text(),
                "attachments": self.attachments_edit.toPlainText()}


class ProductDeliveryPage(QWidget):
    def __init__(self, db_engine, username, log_audit_trail_func):
        super().__init__()
        self.engine, self.username, self.log_audit_trail = db_engine, username, log_audit_trail_func
        self.current_editing_dr_no, self.MAX_ITEMS = None, 4
        self.current_page, self.records_per_page = 1, 200
        self.total_records, self.total_pages = 0, 1
        self.printer, self.current_pdf_buffer = QPrinter(), None
        self.breakdown_preview_data = None
        self.unit_list, self.prod_code_list = [], []

        self.workstation_details = self._get_workstation_details()
        self.prepared_by_string = f"{self.workstation_details['mac']} | {self.workstation_details['ip']} | {self.username.upper()}"

        self.init_ui()
        self._load_all_records()

    def _get_special_descriptions(self, product_code):
        """
        Replicates the hardcoded VFP logic for populating description fields.
        Returns a dictionary with 'ter1' and 'ter2'.
        """
        # Mapping for products that use "MASTERBATCH..." description
        mapping = {
            "OA14430E": ("PL00X814MB", "MASTERBATCH ORANGE OA14430E"),
            "TA14363E": ("PL00X816MB", "MASTERBATCH GRAY TA14363E"),
            "GA14433E": ("PL00X818MB", "MASTERBATCH GREEN GA14433E"),
            "BA14432E": ("PL00X822MB", "MASTERBATCH BLUE BA14432E"),
            "YA14431E": ("PL00X620MB", "MASTERBATCH YELLOW YA14431E"),
            "WA14429E": ("PL00X800MB", "MASTERBATCH WHITE WA14429E"),
        }
        if product_code in mapping:
            ter1, ter2 = mapping[product_code]
            return {"ter1": ter1, "ter2": ter2}

        # Mapping for products that use "(CODE:...)" description format
        mapping_other = {
            "WA12282E": ("RITESEAL88", "WHITE(CODE: WA12282E)"),
            "BA12556E": ("RITESEAL88", "BLUE(CODE: BA12556E)"),
            "WA15151E": ("RITESEAL88", "NATURAL(CODE: WA15151E)"),
            "WA7997E": ("RITESEAL88", "NATURAL(CODE: WA7997E)"),
            "WA15229E": ("RITESEAL88", "NATURAL(CODE: WA15229E)"),
            "WA15218E": ("RITESEAL88", "NATURAL(CODE: WA15229E)"),
            "AD-17248E": ("L-4", "DISPERSING AGENT(CODE: AD-17248E)"),
            "DU-W17246E": ("R104", "(CODE: DU-W17246E)"),
            "DU-W16441E": ("R104", "(CODE: DU-W16441E)"),
            "DU-LL16541E": ("LLPDE", "(CODE: DU-LL16541E)"),
            "BA17070E": ("RITESEAL88", "BLUE(CODE: BA17070E)"),
        }
        if product_code in mapping_other:
            ter1, ter2 = mapping_other[product_code]
            return {"ter1": ter1, "ter2": ter2}

        # Default: return empty strings if no match is found
        return {"ter1": "", "ter2": ""}

    def _get_workstation_details(self):
        try:
            hostname = socket.gethostname()
            ip_address = socket.gethostbyname(hostname)
        except:
            ip_address = "N/A"
        try:
            mac_address = ':'.join(re.findall('..', '%012x' % uuid.getnode()))
        except:
            mac_address = "N/A"
        return {"ip": ip_address, "mac": mac_address.upper()}

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)
        view_tab, tracking_tab = QWidget(), QWidget()
        scanner_tab, self.view_details_tab = QWidget(), QWidget()
        entry_tab, breakdown_tab = QWidget(), QWidget()
        deleted_tab = QWidget()

        self.tab_widget.addTab(view_tab, "Delivery Records")
        self.tab_widget.addTab(self.view_details_tab, "View Details")
        self.tab_widget.addTab(entry_tab, "Delivery Entry")
        self.tab_widget.addTab(deleted_tab, "Deleted Records")
        self.tab_widget.addTab(breakdown_tab, "Lot Breakdown Tool")
        self.tab_widget.addTab(scanner_tab, "QR Scanner")
        self.tab_widget.addTab(tracking_tab, "Delivery Tracking")

        self._setup_view_tab(view_tab)
        self._setup_view_details_tab(self.view_details_tab)
        self._setup_entry_tab(entry_tab)
        self._setup_deleted_tab(deleted_tab)
        self._setup_lot_breakdown_tab(breakdown_tab)
        self._setup_scanner_tab(scanner_tab)
        self._setup_tracking_tab(tracking_tab)

        self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.view_details_tab), False)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

    def _setup_tracking_tab(self, tab):
        layout = QVBoxLayout(tab)
        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(0, 10, 0, 10)
        top_layout.addWidget(QLabel("Search DR No:"))
        self.tracking_search_edit = UpperCaseLineEdit(placeholderText="Filter by DR No...")
        top_layout.addWidget(self.tracking_search_edit, 1)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setObjectName("SecondaryButton")
        top_layout.addWidget(refresh_btn)
        layout.addLayout(top_layout)
        self.tracking_table = QTableWidget()
        self.tracking_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.tracking_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.tracking_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tracking_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tracking_table.verticalHeader().setVisible(False)
        layout.addWidget(self.tracking_table)
        refresh_btn.clicked.connect(self._load_tracking_data)
        self.tracking_search_edit.textChanged.connect(self._load_tracking_data)

    def _setup_scanner_tab(self, tab):
        layout = QVBoxLayout(tab)
        layout.setSpacing(15)
        scan_group = QGroupBox("Scan QR Code to Update Status")
        form_layout = QFormLayout(scan_group)
        form_layout.setContentsMargins(20, 20, 20, 20)
        self.scanner_input = UpperCaseLineEdit()
        self.scanner_input.setPlaceholderText("Scan or Enter DR No. Here")
        self.scanner_input.setStyleSheet("font-size: 14pt;")
        self.scanner_input.returnPressed.connect(self._update_delivery_status)
        scan_btn = QPushButton("Update Status to 'Out for Delivery'")
        scan_btn.setObjectName("scan_btn")
        form_layout.addRow(self.scanner_input)
        form_layout.addRow(scan_btn)
        scan_btn.clicked.connect(self._update_delivery_status)
        log_group = QGroupBox("Recently Scanned (This Session)")
        log_layout = QVBoxLayout(log_group)
        self.scanner_log_table = QTableWidget()
        self.scanner_log_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.scanner_log_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.scanner_log_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.scanner_log_table.verticalHeader().setVisible(False)
        self.scanner_log_table.setColumnCount(3)
        self.scanner_log_table.setHorizontalHeaderLabels(["Time Scanned", "DR No.", "Status"])
        self.scanner_log_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        log_button_layout = QHBoxLayout()
        clear_log_btn = QPushButton("Clear Log")
        log_button_layout.addStretch()
        log_button_layout.addWidget(clear_log_btn)
        clear_log_btn.clicked.connect(self._clear_scanner_log)
        log_layout.addWidget(self.scanner_log_table)
        log_layout.addLayout(log_button_layout)
        layout.addWidget(scan_group)
        layout.addWidget(log_group, 1)

    def _clear_scanner_log(self):
        self.scanner_log_table.setRowCount(0)

    def _setup_lot_breakdown_tab(self, tab):
        layout = QVBoxLayout(tab)
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(main_splitter)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 5, 0)
        main_splitter.addWidget(left_widget)

        fetch_dr_group = QGroupBox("1. Select Delivery Receipt")
        fetch_dr_layout = QFormLayout(fetch_dr_group)
        self.breakdown_dr_no_combo = QComboBox()
        self.breakdown_dr_qty_display = QLineEdit("0.00", readOnly=True)
        self.breakdown_dr_qty_display.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.breakdown_dr_qty_display.setStyleSheet("background-color: #f0f0f0; font-weight: bold;")
        fetch_dr_layout.addRow("Select DR Number:", self.breakdown_dr_no_combo)
        fetch_dr_layout.addRow("Target Quantity (kg):", self.breakdown_dr_qty_display)
        left_layout.addWidget(fetch_dr_group)

        params_group = QGroupBox("2. Define Breakdown")
        params_layout = QGridLayout(params_group)
        self.breakdown_weight_per_lot_edit = FloatLineEdit()
        self.breakdown_num_lots_edit = QLineEdit("0", readOnly=True)
        self.breakdown_num_lots_edit.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.breakdown_num_lots_edit.setStyleSheet("background-color: #f0f0f0;")
        self.breakdown_lot_range_edit = UpperCaseLineEdit(placeholderText="e.g., 12345 or 12345-12350")
        self.breakdown_is_range_check = QCheckBox("Lot input is a range")
        params_layout.addWidget(QLabel("Weight per Lot (kg):"), 0, 0)
        params_layout.addWidget(self.breakdown_weight_per_lot_edit, 0, 1)
        params_layout.addWidget(QLabel("Calculated No. of Lots:"), 0, 2)
        params_layout.addWidget(self.breakdown_num_lots_edit, 0, 3)
        params_layout.addWidget(QLabel("Lot Start/Range:"), 1, 0)
        params_layout.addWidget(self.breakdown_lot_range_edit, 1, 1, 1, 3)
        params_layout.addWidget(self.breakdown_is_range_check, 2, 1, 1, 3)
        left_layout.addWidget(params_group)
        left_layout.addStretch()

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(5, 0, 0, 0)
        main_splitter.addWidget(right_widget)

        breakdown_preview_group = QGroupBox("3. Preview and Save")
        breakdown_preview_layout = QVBoxLayout(breakdown_preview_group)
        self.breakdown_preview_table = QTableWidget(editTriggers=QAbstractItemView.EditTrigger.NoEditTriggers)
        self.breakdown_preview_table.verticalHeader().setVisible(False)
        self.breakdown_preview_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.breakdown_total_label = QLabel("<b>Total: 0.00 kg</b>")
        self.breakdown_total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        breakdown_preview_layout.addWidget(self.breakdown_preview_table)
        breakdown_preview_layout.addWidget(self.breakdown_total_label)
        right_layout.addWidget(breakdown_preview_group)
        main_splitter.setSizes([500, 600])

        button_layout = QHBoxLayout()
        self.breakdown_save_btn = QPushButton("Save Breakdown")
        self.breakdown_save_btn.setObjectName("PrimaryButton")
        preview_btn = QPushButton("Preview Breakdown")
        clear_btn = QPushButton("Clear")
        clear_btn.setObjectName("SecondaryButton")
        button_layout.addStretch()
        button_layout.addWidget(clear_btn)
        button_layout.addWidget(preview_btn)
        button_layout.addWidget(self.breakdown_save_btn)
        left_layout.addLayout(button_layout)

        self.breakdown_dr_no_combo.currentIndexChanged.connect(self._on_breakdown_dr_selected)
        self.breakdown_weight_per_lot_edit.textChanged.connect(self._recalculate_num_lots)
        preview_btn.clicked.connect(self._preview_lot_breakdown)
        clear_btn.clicked.connect(self._clear_breakdown_tool)
        self.breakdown_save_btn.clicked.connect(self._save_lot_breakdown_to_db)

    def _setup_view_tab(self, tab):
        layout = QVBoxLayout(tab)
        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(0, 10, 0, 10)
        top_layout.addWidget(QLabel("Search:"))
        self.search_edit = UpperCaseLineEdit(placeholderText="Filter by DR No, Customer, Order No...")
        top_layout.addWidget(self.search_edit, 1)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setObjectName("SecondaryButton")
        top_layout.addWidget(refresh_btn)

        self.update_btn = QPushButton("Load Selected for Update")
        self.update_btn.setObjectName("update_btn")
        self.delete_btn = QPushButton("Delete Selected")
        self.delete_btn.setObjectName("delete_btn")
        top_layout.addWidget(self.update_btn)
        top_layout.addWidget(self.delete_btn)
        layout.addLayout(top_layout)
        self.records_table = QTableWidget(editTriggers=QAbstractItemView.EditTrigger.NoEditTriggers,
                                          alternatingRowColors=False,
                                          selectionMode=QAbstractItemView.SelectionMode.SingleSelection)
        self.records_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.records_table.verticalHeader().setVisible(False)
        self.records_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.records_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.records_table.setShowGrid(False)
        self.records_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.records_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.records_table.horizontalHeader().setHighlightSections(False)
        layout.addWidget(self.records_table)
        pagination_layout = QHBoxLayout()
        self.prev_btn, self.next_btn = QPushButton("<< Previous"), QPushButton("Next >>")
        self.page_label = QLabel("Page 1 of 1")
        pagination_layout.addStretch();
        pagination_layout.addWidget(self.prev_btn);
        pagination_layout.addWidget(self.page_label);
        pagination_layout.addWidget(self.next_btn);
        pagination_layout.addStretch()
        layout.addLayout(pagination_layout)
        self.search_edit.textChanged.connect(self._on_search_text_changed)
        refresh_btn.clicked.connect(self._load_all_records)
        self.update_btn.clicked.connect(self._load_record_for_update)
        self.delete_btn.clicked.connect(self._delete_record)
        self.records_table.doubleClicked.connect(self._load_record_for_update)
        self.records_table.customContextMenuRequested.connect(self._show_records_table_context_menu)
        self.records_table.itemSelectionChanged.connect(self._on_record_selection_changed)
        self.prev_btn.clicked.connect(self._go_to_prev_page)
        self.next_btn.clicked.connect(self._go_to_next_page)
        self._on_record_selection_changed()

    def _setup_deleted_tab(self, tab):
        layout = QVBoxLayout(tab)
        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(0, 10, 0, 10)
        top_layout.addWidget(QLabel("Search Deleted:"))
        self.deleted_search_edit = UpperCaseLineEdit(placeholderText="Filter by DR No, Customer...")
        top_layout.addWidget(self.deleted_search_edit, 1)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setObjectName("SecondaryButton")
        top_layout.addWidget(refresh_btn)
        layout.addLayout(top_layout)

        self.deleted_records_table = QTableWidget(editTriggers=QAbstractItemView.EditTrigger.NoEditTriggers)
        self.deleted_records_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.deleted_records_table.verticalHeader().setVisible(False)
        self.deleted_records_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.deleted_records_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.deleted_records_table.setShowGrid(False)
        self.deleted_records_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.deleted_records_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        layout.addWidget(self.deleted_records_table)

        refresh_btn.clicked.connect(self._load_deleted_records)
        self.deleted_search_edit.textChanged.connect(self._load_deleted_records)
        self.deleted_records_table.customContextMenuRequested.connect(self._show_deleted_table_context_menu)

    def _setup_view_details_tab(self, tab):
        main_layout = QVBoxLayout(tab)
        main_splitter = QSplitter(Qt.Orientation.Vertical)
        main_layout.addWidget(main_splitter)
        details_group = QGroupBox("Delivery Details (Read-Only from Database)")
        details_container_layout = QHBoxLayout(details_group)
        self.view_left_details_layout, self.view_right_details_layout = QFormLayout(), QFormLayout()
        details_container_layout.addLayout(self.view_left_details_layout)
        details_container_layout.addLayout(self.view_right_details_layout)
        main_splitter.addWidget(details_group)
        bottom_widget = QWidget()
        bottom_layout = QHBoxLayout(bottom_widget)
        main_splitter.addWidget(bottom_widget)
        items_group = QGroupBox("Delivered Items (from Database)")
        items_layout = QVBoxLayout(items_group)
        self.view_items_table = QTableWidget(editTriggers=QAbstractItemView.EditTrigger.NoEditTriggers)
        self.view_items_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.view_items_table.verticalHeader().setVisible(False)
        self.view_items_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.view_items_table.setShowGrid(False)
        self.view_items_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        items_layout.addWidget(self.view_items_table)
        bottom_layout.addWidget(items_group)
        breakdown_group = QGroupBox("Lot Breakdown (from Database)")
        breakdown_layout = QVBoxLayout(breakdown_group)
        self.view_breakdown_table = QTableWidget(editTriggers=QAbstractItemView.EditTrigger.NoEditTriggers)
        self.view_breakdown_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.view_breakdown_table.verticalHeader().setVisible(False)
        self.view_breakdown_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.view_breakdown_table.setShowGrid(False)
        self.view_breakdown_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        breakdown_layout.addWidget(self.view_breakdown_table)
        bottom_layout.addWidget(breakdown_group)
        main_splitter.setSizes([200, 400])

    def _setup_entry_tab(self, tab):
        main_layout = QVBoxLayout(tab)
        primary_group = QGroupBox("Customer Information")
        primary_layout = QGridLayout(primary_group)
        self.dr_no_edit = QLineEdit(readOnly=True)
        self.delivery_date_edit = QDateEdit(calendarPopup=True, displayFormat="yyyy-MM-dd")

        # --- NEW: DR Template ComboBox ---
        self.dr_type_combo = QComboBox()
        self.dr_type_combo.addItems(["Standard DR", "Terumo DR"])

        self.customer_combo = QComboBox(editable=True)
        self.deliver_to_edit = UpperCaseLineEdit()
        self.po_no_edit, self.order_form_no_edit = UpperCaseLineEdit(), UpperCaseLineEdit()
        self.terms_edit = UpperCaseLineEdit()
        self.prepared_by_label = QLabel(self.prepared_by_string)

        primary_layout.addWidget(QLabel("Delivery Number:"), 0, 0);
        primary_layout.addWidget(self.dr_no_edit, 0, 1)
        primary_layout.addWidget(QLabel("Delivery Date:"), 0, 2);
        primary_layout.addWidget(self.delivery_date_edit, 0, 3)
        primary_layout.addWidget(QLabel("Customer:"), 1, 0);
        primary_layout.addWidget(self.customer_combo, 1, 1)
        primary_layout.addWidget(QLabel("DR Template:"), 1, 2);
        primary_layout.addWidget(self.dr_type_combo, 1, 3)
        primary_layout.addWidget(QLabel("Deliver To:"), 2, 0);
        primary_layout.addWidget(self.deliver_to_edit, 2, 1, 1, 3)
        primary_layout.addWidget(QLabel("Address:"), 3, 0);
        self.address_edit = QPlainTextEdit()
        self.address_edit.setMaximumHeight(60)
        primary_layout.addWidget(self.address_edit, 3, 1, 1, 3)
        primary_layout.addWidget(QLabel("Purchase Order No.:"), 4, 0);
        primary_layout.addWidget(self.po_no_edit, 4, 1)
        primary_layout.addWidget(QLabel("Order Form No.:"), 4, 2);
        primary_layout.addWidget(self.order_form_no_edit, 4, 3)
        primary_layout.addWidget(QLabel("Terms:"), 5, 0);
        primary_layout.addWidget(self.terms_edit, 5, 1)
        primary_layout.addWidget(QLabel("Prepared By:"), 5, 2);
        primary_layout.addWidget(self.prepared_by_label, 5, 3)

        main_layout.addWidget(primary_group)
        items_group = QGroupBox("Item Description")
        items_layout = QVBoxLayout(items_group)
        self.items_table = QTableWidget(alternatingRowColors=False)
        self.items_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.items_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.items_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.items_table.verticalHeader().setVisible(False)
        self.items_table.setShowGrid(False)
        self.items_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.items_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.items_table.setColumnCount(14)
        self.items_table.setHorizontalHeaderLabels(
            ["Qty", "Unit", "Product Code", "Color", "No. Packing", "Weight/Pack", "Unit Price", "Lot No(s)",
             "Attachments", "desc1", "desc2", "lot1", "lot2", "lot3"])
        for i in range(9, 14):
            self.items_table.hideColumn(i)

        self.items_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        items_layout.addWidget(self.items_table)
        items_button_layout = QHBoxLayout()
        self.item_count_label = QLabel(f"No. of Item(s): 0 (Max: {self.MAX_ITEMS})")
        items_button_layout.addWidget(self.item_count_label, 1, Qt.AlignmentFlag.AlignLeft)
        add_item_btn, self.edit_item_btn = QPushButton("Add Item"), QPushButton("Edit Item")
        self.remove_item_btn = QPushButton("Remove Item")
        self.remove_item_btn.setObjectName("remove_item_btn")
        items_button_layout.addWidget(add_item_btn);
        items_button_layout.addWidget(self.edit_item_btn);
        items_button_layout.addWidget(self.remove_item_btn)
        items_layout.addLayout(items_button_layout)
        main_layout.addWidget(items_group, 1)
        action_button_layout = QHBoxLayout()
        self.cancel_update_btn, self.clear_btn = QPushButton("Cancel Update"), QPushButton("New")
        self.save_btn, self.print_btn = QPushButton("Save"), QPushButton("Print Preview")
        self.save_btn.setObjectName("save_btn")
        self.print_btn.setObjectName("print_btn")
        action_button_layout.addStretch();
        action_button_layout.addWidget(self.cancel_update_btn);
        action_button_layout.addWidget(self.clear_btn);
        action_button_layout.addWidget(self.save_btn);
        action_button_layout.addWidget(self.print_btn)
        main_layout.addLayout(action_button_layout)
        add_item_btn.clicked.connect(self._add_item_row);
        self.edit_item_btn.clicked.connect(self._edit_item_row);
        self.remove_item_btn.clicked.connect(self._remove_item_row)
        self.customer_combo.currentIndexChanged.connect(self._customer_selected)
        self.clear_btn.clicked.connect(self._clear_form);
        self.cancel_update_btn.clicked.connect(self._clear_form)
        self.save_btn.clicked.connect(self._save_record);
        self.print_btn.clicked.connect(
            lambda: self._print_receipt(self.dr_no_edit.text()) if self.dr_no_edit.text() else QMessageBox.warning(self,
                                                                                                                   "No Record Loaded",
                                                                                                                   "Load a record to print."))
        self.items_table.itemSelectionChanged.connect(self._on_item_selection_changed)
        self._clear_form()

    def _on_search_text_changed(self, text):
        self.current_page = 1
        self._load_all_records()

    def _go_to_prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self._load_all_records()

    def _go_to_next_page(self):
        if self.current_page < self.total_pages:
            self.current_page += 1
            self._load_all_records()

    def _update_pagination_controls(self):
        self.total_pages = (self.total_records + self.records_per_page - 1) // self.records_per_page or 1
        self.page_label.setText(f"Page {self.current_page} of {self.total_pages}")
        self.prev_btn.setEnabled(self.current_page > 1)
        self.next_btn.setEnabled(self.current_page < self.total_pages)

    def _on_record_selection_changed(self):
        selected = self.records_table.selectionModel().selectedRows()
        is_printed = selected and self.records_table.item(selected[0].row(),
                                                          self.records_table.columnCount() - 1).data(
            Qt.ItemDataRole.UserRole)
        self.update_btn.setEnabled(bool(selected) and not is_printed)
        self.delete_btn.setEnabled(bool(selected) and not is_printed)
        self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.view_details_tab), bool(selected))
        if selected:
            self._show_selected_record_in_view_tab()
        elif self.tab_widget.currentIndex() == self.tab_widget.indexOf(self.view_details_tab):
            self.tab_widget.setCurrentIndex(1)

    def _show_selected_record_in_view_tab(self):
        selected = self.records_table.selectionModel().selectedRows()
        if not selected: return
        dr_no = self.records_table.item(selected[0].row(), 0).text()
        try:
            with self.engine.connect() as conn:
                primary = conn.execute(text("SELECT * FROM product_delivery_primary WHERE dr_no = :dr_no"),
                                       {"dr_no": dr_no}).mappings().one()
                items = conn.execute(text(
                    """SELECT id, quantity, unit, product_code, product_color, no_of_packing, weight_per_pack, 
                       lot_no_1, lot_no_2, lot_no_3, attachments, unit_price, description_1, description_2
                       FROM product_delivery_items WHERE dr_no = :dr_no ORDER BY id"""),
                    {"dr_no": dr_no}).mappings().all()
                breakdown = conn.execute(text(
                    "SELECT lot_number, quantity_kg FROM product_delivery_lot_breakdown WHERE dr_no = :dr_no ORDER BY id"),
                    {"dr_no": dr_no}).mappings().all()
            for layout in [self.view_left_details_layout, self.view_right_details_layout]:
                while layout.count():
                    child = layout.takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()
            items_list = list(primary.items())
            midpoint = (len(items_list) + 1) // 2
            for k, v in items_list[:midpoint]: self._add_view_detail_row(self.view_left_details_layout, k, v)
            for k, v in items_list[midpoint:]: self._add_view_detail_row(self.view_right_details_layout, k, v)
            item_headers = ["ID", "Qty", "Unit", "Code", "Color", "Packing", "Wt/Pack", "Lot 1", "Lot 2", "Lot 3",
                            "Attachments", "Price", "Desc1", "Desc2"]
            self._populate_table_generic(self.view_items_table, items, item_headers)
            breakdown_headers = ["Lot Number", "Quantity (kg)"]
            self._populate_table_generic(self.view_breakdown_table, breakdown, breakdown_headers)
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load details for DR {dr_no}: {e}")

    def _add_view_detail_row(self, layout, key, value):
        display_text = str(value) if value is not None else "N/A"
        if isinstance(value, datetime):
            display_text = QDateTime(value).toString('yyyy-MM-dd hh:mm AP')
        elif isinstance(value, (QDate, date)):
            display_text = QDate(value).toString('yyyy-MM-dd')
        elif isinstance(value, (Decimal, float)):
            display_text = f"{float(value):.3f}"
        layout.addRow(QLabel(f"<b>{key.replace('_', ' ').title()}:</b>"), QLabel(display_text))

    def _on_item_selection_changed(self):
        selected = bool(self.items_table.selectionModel().selectedRows())
        self.edit_item_btn.setEnabled(selected)
        self.remove_item_btn.setEnabled(selected)

    def _update_item_count(self):
        self.item_count_label.setText(f"No. of Item(s): {self.items_table.rowCount()} (Max: {self.MAX_ITEMS})")

    def _add_item_row(self):
        if self.items_table.rowCount() >= self.MAX_ITEMS:
            QMessageBox.warning(self, "Limit Reached", f"Max {self.MAX_ITEMS} items.")
            return

        dr_type = self.dr_type_combo.currentText()
        if dr_type == "Terumo DR":
            dialog = TerumoItemEntryDialog(self.engine, self.unit_list, self.prod_code_list, parent=self)
        else:  # Standard DR
            dialog = StandardItemEntryDialog(self.engine, self.unit_list, self.prod_code_list, parent=self)

        if dialog.exec():
            item_data = dialog.get_item_data()

            # --- Smart data processing ---
            if 'lot_numbers_text' in item_data:  # Data is from Standard Dialog
                lot_lines = [line.strip() for line in item_data['lot_numbers_text'].split('\n') if line.strip()]
                item_data['lot_no_1'] = lot_lines[0] if len(lot_lines) > 0 else ""
                item_data['lot_no_2'] = lot_lines[1] if len(lot_lines) > 1 else ""
                item_data['lot_no_3'] = lot_lines[2] if len(lot_lines) > 2 else ""

            new_unit = item_data.get("unit")
            if new_unit and new_unit not in self.unit_list:
                self._add_new_unit(new_unit)

            row = self.items_table.rowCount()
            self.items_table.insertRow(row)
            self._populate_item_row(row, item_data)
            self._update_item_count()

    def _edit_item_row(self):
        selected = self.items_table.selectionModel().selectedRows()
        if not selected: return

        current_data = self._get_item_data_from_row(selected[0].row())
        dr_type = self.dr_type_combo.currentText()

        if dr_type == "Terumo DR":
            dialog = TerumoItemEntryDialog(self.engine, self.unit_list, self.prod_code_list, item_data=current_data,
                                           parent=self)
        else:  # Standard DR
            dialog = StandardItemEntryDialog(self.engine, self.unit_list, self.prod_code_list, item_data=current_data,
                                             parent=self)

        if dialog.exec():
            item_data = dialog.get_item_data()

            if 'lot_numbers_text' in item_data:  # Data is from Standard Dialog
                lot_lines = [line.strip() for line in item_data['lot_numbers_text'].split('\n') if line.strip()]
                item_data['lot_no_1'] = lot_lines[0] if len(lot_lines) > 0 else ""
                item_data['lot_no_2'] = lot_lines[1] if len(lot_lines) > 1 else ""
                item_data['lot_no_3'] = lot_lines[2] if len(lot_lines) > 2 else ""

            new_unit = item_data.get("unit")
            if new_unit and new_unit not in self.unit_list:
                self._add_new_unit(new_unit)
            self._populate_item_row(selected[0].row(), item_data)

    def _remove_item_row(self):
        selected = self.items_table.selectionModel().selectedRows()
        if not selected: return
        if QMessageBox.question(self, "Confirm Remove", "Remove this item?") == QMessageBox.StandardButton.Yes:
            self.items_table.removeRow(selected[0].row())
            self._update_item_count()

    def _populate_item_row(self, row, item_data):
        # --- FIX: Convert the SQLAlchemy Row object to a dictionary first ---
        if not isinstance(item_data, dict):
            item_data = dict(item_data)

        headers = ["quantity", "unit", "product_code", "product_color", "no_of_packing", "weight_per_pack",
                   "unit_price", "lot_no_s_display", "attachments", "description_1", "description_2",
                   "lot_no_1", "lot_no_2", "lot_no_3"]

        # Create a display-friendly concatenation of lot numbers
        lot_numbers_display = ", ".join(filter(None, [
            item_data.get("lot_no_1", ""), item_data.get("lot_no_2", ""), item_data.get("lot_no_3", "")
        ]))

        data_to_populate = item_data.copy()
        data_to_populate['lot_no_s_display'] = lot_numbers_display

        for col, header in enumerate(headers):
            value = str(data_to_populate.get(header, ''))
            self.items_table.setItem(row, col, QTableWidgetItem(value))

    def _get_item_data_from_row(self, row):
        headers = ["quantity", "unit", "product_code", "product_color", "no_of_packing", "weight_per_pack",
                   "unit_price", "lot_no_s_display", "attachments", "description_1", "description_2",
                   "lot_no_1", "lot_no_2", "lot_no_3"]
        return {h: self.items_table.item(row, i).text() if self.items_table.item(row, i) else "" for i, h in
                enumerate(headers)}

    def _customer_selected(self):
        name = self.customer_combo.currentText()

        # --- NEW: Automatically switch to Terumo DR if customer is TERUMO ---
        if "TERUMO" in name.upper():
            self.dr_type_combo.setCurrentText("Terumo DR")
        else:
            if not self.current_editing_dr_no:  # Only switch back if it's a new record
                self.dr_type_combo.setCurrentText("Standard DR")

        if not name:
            self.deliver_to_edit.clear();
            self.address_edit.clear();
            self.terms_edit.clear()
            return
        try:
            with self.engine.connect() as conn:
                res = conn.execute(text("SELECT deliver_to, address, terms FROM customers WHERE name = :n"),
                                   {"n": name}).mappings().one_or_none()
            if res:
                self.deliver_to_edit.setText(res.get('deliver_to', ''));
                self.address_edit.setPlainText(res.get('address', ''));
                self.terms_edit.setText(res.get('terms', ''))
            else:
                self.deliver_to_edit.setText(name);
                self.address_edit.clear();
                self.terms_edit.clear()
        except Exception as e:
            QMessageBox.warning(self, "DB Error", f"Could not fetch customer details: {e}")

    def _on_tab_changed(self, index):
        tab_text = self.tab_widget.tabText(index)
        if tab_text == "Delivery Records":
            self._load_all_records()
        elif tab_text == "Deleted Records":
            self._load_deleted_records()
        elif tab_text == "Delivery Tracking":
            self._load_tracking_data()
        elif tab_text == "Delivery Entry" and not self.current_editing_dr_no:
            self._load_combobox_data()
            if not self.dr_no_edit.text():
                self.dr_no_edit.setText(self._get_next_dr_number())
        elif tab_text == "Lot Breakdown Tool":
            self._clear_breakdown_tool()
            self._load_dr_for_breakdown_combo()

    def _clear_form(self):
        self.current_editing_dr_no = None
        self.dr_no_edit.clear()
        for w in [self.deliver_to_edit, self.po_no_edit, self.order_form_no_edit, self.terms_edit]: w.clear()
        self.address_edit.clear();
        self.delivery_date_edit.setDate(QDate.currentDate());
        self.items_table.setRowCount(0)
        self._load_combobox_data();
        self.customer_combo.setCurrentIndex(-1)
        self.dr_type_combo.setCurrentIndex(0)  # Default to Standard
        self.dr_type_combo.setEnabled(True)  # Ensure it's enabled for new records
        self.save_btn.setText("Save");
        self.cancel_update_btn.hide();
        self.print_btn.setEnabled(False)
        self.prepared_by_label.setText(self.prepared_by_string)
        self.dr_no_edit.setText(self._get_next_dr_number())
        self._update_item_count();
        self._on_item_selection_changed()

    def _load_combobox_data(self):
        try:
            with self.engine.connect() as conn:
                customers = conn.execute(
                    text("SELECT name FROM customers WHERE is_deleted IS NOT TRUE ORDER BY name")).scalars().all()
                self.unit_list = conn.execute(text("SELECT name FROM units ORDER BY name")).scalars().all()
                self.prod_code_list = conn.execute(text(
                    "SELECT DISTINCT prod_code FROM legacy_production WHERE prod_code IS NOT NULL AND prod_code != '' ORDER BY prod_code")).scalars().all()

            current_customer = self.customer_combo.currentText()
            self.customer_combo.clear()
            self.customer_combo.addItems([""] + customers)
            if current_customer in customers:
                self.customer_combo.setCurrentText(current_customer)
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load combobox data: {e}")

    def _add_new_unit(self, unit_name):
        reply = QMessageBox.question(self, "Add New Unit",
                                     f"The unit '{unit_name}' is not in the list. Would you like to add it to the database?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                with self.engine.connect() as conn, conn.begin():
                    conn.execute(text("INSERT INTO units (name) VALUES (:name) ON CONFLICT (name) DO NOTHING"),
                                 {"name": unit_name})
                QMessageBox.information(self, "Success", f"Unit '{unit_name}' has been added.")
                self.log_audit_trail("ADD_UNIT", f"Added new unit: {unit_name}")
                self._load_combobox_data()
            except Exception as e:
                QMessageBox.critical(self, "Database Error", f"Could not add the new unit: {e}")

    def _save_record(self):
        if not self.customer_combo.currentText() or self.items_table.rowCount() == 0:
            QMessageBox.warning(self, "Input Error", "Customer and at least one item are required.")
            return

        dr_no = self.current_editing_dr_no or self.dr_no_edit.text()
        if not dr_no:
            QMessageBox.warning(self, "Input Error", "Cannot save record without a valid DR Number.")
            return

        primary_data = {
            "dr_no": dr_no, "dr_type": self.dr_type_combo.currentText(),  # Save the type
            "delivery_date": self.delivery_date_edit.date().toPyDate(),
            "customer_name": self.customer_combo.currentText(), "deliver_to": self.deliver_to_edit.text(),
            "address": self.address_edit.toPlainText(), "po_no": self.po_no_edit.text(),
            "order_form_no": self.order_form_no_edit.text(), "terms": self.terms_edit.text(),
            "prepared_by": self.prepared_by_string, "encoded_by": self.username,
            "encoded_on": datetime.now(), "edited_by": self.username, "edited_on": datetime.now()
        }

        items_data = [self._get_item_data_from_row(row) for row in range(self.items_table.rowCount())]
        for item in items_data: item['dr_no'] = dr_no

        try:
            with self.engine.connect() as conn, conn.begin():
                if self.current_editing_dr_no:
                    del primary_data['encoded_by'], primary_data['encoded_on']
                    update_query = text("""
                        UPDATE product_delivery_primary SET dr_type=:dr_type, delivery_date=:delivery_date, 
                        customer_name=:customer_name, deliver_to=:deliver_to, address=:address, po_no=:po_no, 
                        order_form_no=:order_form_no, terms=:terms, prepared_by=:prepared_by, 
                        edited_by=:edited_by, edited_on=:edited_on 
                        WHERE dr_no=:dr_no
                    """)
                    conn.execute(update_query, primary_data)
                    conn.execute(text("DELETE FROM product_delivery_items WHERE dr_no = :dr_no"), {"dr_no": dr_no})
                    log, action = "UPDATE_DELIVERY", "updated"
                else:
                    insert_query = text("""
                        INSERT INTO product_delivery_primary (dr_no, dr_type, delivery_date, customer_name, deliver_to, 
                        address, po_no, order_form_no, terms, prepared_by, encoded_by, encoded_on, edited_by, edited_on) 
                        VALUES (:dr_no, :dr_type, :delivery_date, :customer_name, :deliver_to, :address, :po_no, 
                        :order_form_no, :terms, :prepared_by, :encoded_by, :encoded_on, :edited_by, :edited_on)
                    """)
                    conn.execute(insert_query, primary_data)
                    log, action = "CREATE_DELIVERY", "saved"

                if items_data:
                    conn.execute(text("""
                        INSERT INTO product_delivery_items (dr_no, quantity, unit, product_code, product_color, 
                        no_of_packing, weight_per_pack, attachments, unit_price, description_1, description_2,
                        lot_no_1, lot_no_2, lot_no_3) 
                        VALUES (:dr_no, :quantity, :unit, :product_code, :product_color, :no_of_packing, 
                        :weight_per_pack, :attachments, :unit_price, :description_1, :description_2,
                        :lot_no_1, :lot_no_2, :lot_no_3)
                    """), items_data)

                self.log_audit_trail(log, f"Delivery Receipt: {dr_no}")

            QMessageBox.information(self, "Success", f"DR {dr_no} has been {action}.")
            self._clear_form()
            self.tab_widget.setCurrentIndex(0) # Switch to the first tab (Delivery Records)
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"An error occurred: {e}")

    def _load_record_for_viewing(self, dr_no):
        self._load_record(dr_no, True);
        self.tab_widget.setCurrentIndex(2)

    def _load_record_for_update(self):
        selected = self.records_table.selectionModel().selectedRows()
        if not selected: return
        if self.records_table.item(selected[0].row(), self.records_table.columnCount() - 1).data(
                Qt.ItemDataRole.UserRole):
            QMessageBox.warning(self, "Record Locked", "Printed records cannot be edited or deleted.")
            return

        dr_no = self.records_table.item(selected[0].row(), 0).text()
        self._load_record(dr_no, True)

        # Find the "Delivery Entry" tab by object name or text
        for i in range(self.tab_widget.count()):
            if self.tab_widget.tabText(i) == "Delivery Entry":
                self.tab_widget.setCurrentIndex(i)
                break

    def _load_record(self, dr_no, set_current=False):
        try:
            with self.engine.connect() as conn:
                primary = conn.execute(text("SELECT * FROM product_delivery_primary WHERE dr_no = :dr_no"),
                                       {"dr_no": dr_no}).mappings().one()
                items = conn.execute(text("SELECT * FROM product_delivery_items WHERE dr_no = :dr_no ORDER BY id"),
                                     {"dr_no": dr_no}).mappings().all()
            self._clear_form()
            if set_current: self.current_editing_dr_no = dr_no
            self.dr_no_edit.setText(primary.get('dr_no'));

            self.dr_type_combo.setCurrentText(primary.get('dr_type', 'Standard DR'))

            self.delivery_date_edit.setDate(primary.get('delivery_date', QDate.currentDate()))
            self.customer_combo.setCurrentText(primary.get('customer_name', ''));
            self.deliver_to_edit.setText(primary.get('deliver_to', ''))
            self.address_edit.setPlainText(primary.get('address', ''));
            self.po_no_edit.setText(primary.get('po_no', ''))
            self.order_form_no_edit.setText(primary.get('order_form_no', ''));
            self.terms_edit.setText(primary.get('terms', ''));
            self.prepared_by_label.setText(primary.get('prepared_by', self.prepared_by_string))
            self.items_table.setRowCount(0)
            for item_data in items:
                row = self.items_table.rowCount();
                self.items_table.insertRow(row);
                self._populate_item_row(row, item_data)
            self._update_item_count()
            if set_current:
                self.save_btn.setText("Update");
                self.cancel_update_btn.show()
                self.dr_type_combo.setEnabled(False)
            self.print_btn.setEnabled(True)
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load DR {dr_no}: {e}")

    def _delete_record(self):
        selected = self.records_table.selectionModel().selectedRows()
        if not selected: return

        if self.records_table.item(selected[0].row(), self.records_table.columnCount() - 1).data(
                Qt.ItemDataRole.UserRole):
            QMessageBox.warning(self, "Record Locked", "Printed records cannot be deleted.")
            return

        dr_no = self.records_table.item(selected[0].row(), 0).text()

        if QMessageBox.question(self, "Confirm Deletion",
                                f"Delete DR No: <b>{dr_no}</b>?") == QMessageBox.StandardButton.Yes:
            password, ok = QInputDialog.getText(self, 'Admin Password Required', 'Enter password to confirm deletion:',
                                                QLineEdit.EchoMode.Password)

            if ok and password == 'Itadmin':
                try:
                    with self.engine.connect() as conn, conn.begin():
                        conn.execute(text(
                            "UPDATE product_delivery_primary SET is_deleted = TRUE, edited_by = :u, edited_on = :n WHERE dr_no = :dr"),
                            {"u": self.username, "n": datetime.now(), "dr": dr_no})
                        conn.execute(text("DELETE FROM product_delivery_lot_breakdown WHERE dr_no = :dr"),
                                     {"dr": dr_no})
                    self.log_audit_trail("DELETE_DELIVERY", f"Soft-deleted DR: {dr_no} and its lot breakdown.")
                    QMessageBox.information(self, "Success", f"DR {dr_no} deleted.")
                    self._load_all_records()
                except Exception as e:
                    QMessageBox.critical(self, "Database Error", f"Could not delete record: {e}")
            elif ok:
                QMessageBox.warning(self, "Incorrect Password", "The password was incorrect. Deletion cancelled.")

    def _restore_record(self):
        selected = self.deleted_records_table.selectionModel().selectedRows()
        if not selected:
            return

        dr_no = self.deleted_records_table.item(selected[0].row(), 0).text()

        if QMessageBox.question(self, "Confirm Restore",
                                f"Restore DR No: <b>{dr_no}</b>?") == QMessageBox.StandardButton.Yes:
            try:
                with self.engine.connect() as conn, conn.begin():
                    conn.execute(text(
                        "UPDATE product_delivery_primary SET is_deleted = FALSE, edited_by = :u, edited_on = :n WHERE dr_no = :dr"),
                        {"u": self.username, "n": datetime.now(), "dr": dr_no})
                self.log_audit_trail("RESTORE_DELIVERY", f"Restored DR: {dr_no}")
                QMessageBox.information(self, "Success", f"DR {dr_no} has been restored.")
                self._load_deleted_records()
                self._load_all_records()
            except Exception as e:
                QMessageBox.critical(self, "Database Error", f"Could not restore record: {e}")

    def _load_all_records(self):
        search = f"%{self.search_edit.text()}%"
        offset = (self.current_page - 1) * self.records_per_page
        try:
            with self.engine.connect() as conn:
                count_params = {}
                count_query_base = "FROM product_delivery_primary p WHERE p.is_deleted IS NOT TRUE"
                filter_clause = ""
                if self.search_edit.text():
                    filter_clause = " AND (p.dr_no ILIKE :st OR p.customer_name ILIKE :st OR p.order_form_no ILIKE :st)"
                    count_params['st'] = search

                count_res = conn.execute(text(f"SELECT COUNT(p.id) {count_query_base} {filter_clause}"),
                                         count_params).scalar_one_or_none()
                self.total_records = count_res if count_res is not None else 0

                data_params = {'limit': self.records_per_page, 'offset': offset}
                if self.search_edit.text():
                    data_params['st'] = search

                res = conn.execute(text(f"""
                    SELECT 
                        p.dr_no, p.delivery_date, p.customer_name, p.order_form_no, p.is_printed,
                        STRING_AGG(i.product_code, ', ') as product_codes,
                        SUM(i.quantity) as total_quantity
                    FROM product_delivery_primary p
                    LEFT JOIN product_delivery_items i ON p.dr_no = i.dr_no
                    WHERE p.is_deleted IS NOT TRUE {filter_clause}
                    GROUP BY p.id, p.dr_no, p.delivery_date, p.customer_name, p.order_form_no, p.is_printed
                    ORDER BY p.id DESC 
                    LIMIT :limit OFFSET :offset
                """), data_params).mappings().all()

            headers = ["DR NO.", "DR DATE", "CUSTOMER", "ORDER NO.", "PRODUCT CODES", "TOTAL QTY", "Printed"]
            self._populate_records_table(self.records_table, res, headers)
            self._update_pagination_controls()
            self._on_record_selection_changed()
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load records: {e}")

    def _load_deleted_records(self):
        search = f"%{self.deleted_search_edit.text()}%"
        try:
            with self.engine.connect() as conn:
                params = {}
                filter_clause = ""
                if self.deleted_search_edit.text():
                    filter_clause = " AND (p.dr_no ILIKE :st OR p.customer_name ILIKE :st)"
                    params['st'] = search

                res = conn.execute(text(f"""
                    SELECT 
                        p.dr_no, p.delivery_date, p.customer_name, p.edited_by, p.edited_on
                    FROM product_delivery_primary p
                    WHERE p.is_deleted IS TRUE {filter_clause}
                    ORDER BY p.edited_on DESC
                """), params).mappings().all()

            headers = ["DR NO.", "DR DATE", "CUSTOMER", "DELETED BY", "DELETED ON"]
            self.deleted_records_table.setRowCount(0)
            self.deleted_records_table.setColumnCount(len(headers))
            self.deleted_records_table.setHorizontalHeaderLabels(headers)
            if not res: return

            self.deleted_records_table.setRowCount(len(res))
            for i, row in enumerate(res):
                self.deleted_records_table.setItem(i, 0, QTableWidgetItem(row.get('dr_no')))
                self.deleted_records_table.setItem(i, 1, QTableWidgetItem(str(row.get('delivery_date'))))
                self.deleted_records_table.setItem(i, 2, QTableWidgetItem(row.get('customer_name')))
                self.deleted_records_table.setItem(i, 3, QTableWidgetItem(row.get('edited_by')))
                self.deleted_records_table.setItem(i, 4, QTableWidgetItem(
                    QDateTime(row.get('edited_on')).toString('yyyy-MM-dd hh:mm AP')))

            self.deleted_records_table.resizeColumnsToContents()
            self.deleted_records_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load deleted records: {e}")

    def _populate_table_generic(self, table, data, headers):
        table.setRowCount(0)
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        if not data: return
        table.setRowCount(len(data))
        keys = list(data[0].keys())
        for i, row_data in enumerate(data):
            for j, key in enumerate(keys):
                value = row_data.get(key)
                item_text = f"{float(value):.2f}" if isinstance(value, (Decimal, float)) else str(value or "")
                item = QTableWidgetItem(item_text)
                if isinstance(value, (Decimal, float)):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(i, j, item)

    def _populate_records_table(self, table, data, headers):
        table.setRowCount(0)
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        if not data: return
        printed_row_color = QColor("#e9ecef")
        keys = ["dr_no", "delivery_date", "customer_name", "order_form_no", "product_codes", "total_quantity",
                "is_printed"]
        table.setRowCount(len(data))
        for i, row in enumerate(data):
            is_printed = row.get('is_printed', False)
            for j, key in enumerate(keys):
                value = row.get(key)
                if key == 'is_printed':
                    item = QTableWidgetItem()
                    item.setData(Qt.ItemDataRole.UserRole, is_printed)
                elif key == 'total_quantity' and value is not None:
                    item = QTableWidgetItem(f"{float(value):.2f}")
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                else:
                    item = QTableWidgetItem(str(value or ""))
                table.setItem(i, j, item)
            if is_printed:
                for col_index in range(table.columnCount()):
                    table.item(i, col_index).setBackground(printed_row_color)
        table.resizeColumnsToContents()
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        table.hideColumn(len(headers) - 1)

    def _get_next_dr_number(self):
        try:
            with self.engine.connect() as conn:
                start_num_query = text("SELECT setting_value FROM app_settings WHERE setting_key = 'DR_SEQUENCE_START'")
                start_num_str = conn.execute(start_num_query).scalar_one_or_none()
                start_num = int(start_num_str) if start_num_str and start_num_str.isdigit() else 100001
                max_dr_query = text("SELECT MAX(CAST(dr_no AS BIGINT)) FROM product_delivery_primary")
                max_existing_dr = conn.execute(max_dr_query).scalar_one_or_none() or 0
                next_dr = max(max_existing_dr + 1, start_num)
                return str(next_dr)
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not generate the next DR number: {e}")
            return ""

    def _show_records_table_context_menu(self, pos):
        if not self.records_table.selectedItems(): return
        selected_row = self.records_table.selectionModel().selectedRows()[0].row()
        dr_no = self.records_table.item(selected_row, 0).text()
        menu = QMenu()
        view_dr_action = menu.addAction("Print Delivery Receipt")
        view_details_action = menu.addAction("View Record Details")
        menu.addSeparator()
        edit_action = menu.addAction("Edit Record")
        delete_action = menu.addAction("Delete Record")
        is_printed = self.records_table.item(selected_row, self.records_table.columnCount() - 1).data(
            Qt.ItemDataRole.UserRole)
        edit_action.setEnabled(not is_printed)
        delete_action.setEnabled(not is_printed)
        action = menu.exec(self.records_table.mapToGlobal(pos))
        if action == view_dr_action:
            self._print_receipt(dr_no)
        elif action == view_details_action:
            details_tab_index = self.tab_widget.indexOf(self.view_details_tab)
            self.tab_widget.setCurrentIndex(details_tab_index)
        elif action == edit_action:
            self._load_record_for_update()
        elif action == delete_action:
            self._delete_record()

    def _show_deleted_table_context_menu(self, pos):
        if not self.deleted_records_table.selectedItems(): return

        menu = QMenu()
        restore_action = menu.addAction("Restore Record")

        action = menu.exec(self.deleted_records_table.mapToGlobal(pos))
        if action == restore_action:
            self._restore_record()

    def _clear_breakdown_tool(self):
        self.breakdown_dr_no_combo.blockSignals(True)
        self.breakdown_dr_no_combo.setCurrentIndex(0)
        self.breakdown_dr_no_combo.blockSignals(False)
        self.breakdown_dr_qty_display.setText("0.00")
        self.breakdown_num_lots_edit.setText("0")
        self.breakdown_weight_per_lot_edit.setText("0.00")
        self.breakdown_lot_range_edit.clear()
        self.breakdown_is_range_check.setChecked(False)
        self.breakdown_preview_table.setRowCount(0)
        self.breakdown_total_label.setText("<b>Total: 0.00 kg</b>")
        self.breakdown_preview_data = None

    def _load_dr_for_breakdown_combo(self):
        try:
            with self.engine.connect() as conn:
                query = text("SELECT dr_no FROM product_delivery_primary WHERE is_deleted IS NOT TRUE ORDER BY id DESC")
                dr_numbers = conn.execute(query).scalars().all()

            self.breakdown_dr_no_combo.blockSignals(True)
            self.breakdown_dr_no_combo.clear()
            self.breakdown_dr_no_combo.addItems(["-- Select a DR --"] + dr_numbers)
            self.breakdown_dr_no_combo.blockSignals(False)
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load DR numbers for breakdown tool: {e}")

    def _on_breakdown_dr_selected(self):
        dr_no = self.breakdown_dr_no_combo.currentText()
        if not dr_no or self.breakdown_dr_no_combo.currentIndex() == 0:
            self.breakdown_dr_qty_display.setText("0.00")
            self._recalculate_num_lots()
            return

        try:
            with self.engine.connect() as conn:
                query = text("""
                    SELECT SUM(i.quantity) as total_quantity
                    FROM product_delivery_items i
                    WHERE i.dr_no = :dr_no
                """)
                result = conn.execute(query, {"dr_no": dr_no}).scalar_one_or_none()

            total_qty = Decimal(result or "0.00")
            self.breakdown_dr_qty_display.setText(f"{total_qty:.2f}")
            self._recalculate_num_lots()

        except Exception as e:
            self.breakdown_dr_qty_display.setText("0.00")
            QMessageBox.critical(self, "Database Error", f"An error occurred while fetching DR data: {e}")

    def _recalculate_num_lots(self):
        try:
            target_qty = Decimal(self.breakdown_dr_qty_display.text())
            weight_per_lot = Decimal(self.breakdown_weight_per_lot_edit.text())

            if target_qty <= 0 or weight_per_lot <= 0:
                self.breakdown_num_lots_edit.setText("0")
                return

            num_lots = math.ceil(target_qty / weight_per_lot)
            self.breakdown_num_lots_edit.setText(str(num_lots))

        except (ValueError, InvalidOperation):
            self.breakdown_num_lots_edit.setText("0")

    def _validate_and_calculate_breakdown(self):
        try:
            target_qty = Decimal(self.breakdown_dr_qty_display.text())
            weight_per_lot = Decimal(self.breakdown_weight_per_lot_edit.text())
            lot_input = self.breakdown_lot_range_edit.text().strip()
            num_lots = int(self.breakdown_num_lots_edit.text())

            if not all([target_qty > 0, weight_per_lot > 0, lot_input, num_lots > 0]):
                QMessageBox.warning(self, "Input Error",
                                    "Please ensure a DR is selected and all parameter fields are filled with valid values.")
                return None
        except (ValueError, InvalidOperation):
            QMessageBox.warning(self, "Input Error", "Please enter valid numbers for lots and weight.")
            return None

        lot_list = []
        if self.breakdown_is_range_check.isChecked():
            parsed_list = self._parse_lot_range(lot_input)
            if parsed_list is None: return None

            if len(parsed_list) != num_lots:
                QMessageBox.warning(self, "Mismatch Error",
                                    f"The number of lots in your range text ({len(parsed_list)}) does not match the 'Calculated No. of Lots' ({num_lots}).")
                return None
            lot_list = parsed_list
        else:
            single_lot_pattern = r'^\d+[A-Z]*$'
            if not re.match(single_lot_pattern, lot_input.upper()):
                QMessageBox.warning(self, "Input Error",
                                    f"Invalid format for a single starting lot number: '{lot_input}'.\n"
                                    f"Expected format is like '1234' or '1234AA'. No hyphens allowed.")
                return None

            start_match = re.match(r'^(\d+)([A-Z]*)$', lot_input.upper())
            if start_match:
                start_num, suffix, num_len = int(start_match.group(1)), start_match.group(2), len(start_match.group(1))
                lot_list = [f"{str(start_num + i).zfill(num_len)}{suffix}" for i in range(num_lots)]
            else:
                return None

        num_full_lots = int(target_qty // weight_per_lot)
        remainder_qty = target_qty % weight_per_lot

        breakdown_items = []
        for i in range(num_full_lots):
            breakdown_items.append({'lot_number': lot_list[i], 'quantity_kg': weight_per_lot})

        if remainder_qty > 0:
            breakdown_items.append({'lot_number': lot_list[num_full_lots], 'quantity_kg': remainder_qty})

        return breakdown_items

    def _parse_lot_range(self, lot_input):
        try:
            parts = [s.strip().upper() for s in lot_input.split('-')]
            if len(parts) != 2: raise ValueError("Lot range must contain exactly one hyphen.")
            start_str, end_str = parts
            start_match = re.match(r'^(\d+)([A-Z]*)$', start_str)
            end_match = re.match(r'^(\d+)([A-Z]*)$', end_str)
            if not start_match or not end_match or start_match.group(2) != end_match.group(2):
                raise ValueError("Format invalid or suffixes mismatch. Expected: '100A-105A'.")
            start_num, end_num, suffix, num_len = int(start_match.group(1)), int(end_match.group(1)), start_match.group(
                2), len(start_match.group(1))
            if start_num > end_num: raise ValueError("Start lot cannot be greater than end lot.")

            return [f"{str(start_num + i).zfill(num_len)}{suffix}" for i in range(end_num - start_num + 1)]
        except Exception as e:
            QMessageBox.critical(self, "Lot Range Error", f"Could not parse lot range '{lot_input}': {e}")
            return None

    def _preview_lot_breakdown(self):
        self.breakdown_preview_data = None
        self.breakdown_preview_table.setRowCount(0)
        self.breakdown_total_label.setText("<b>Total: 0.00 kg</b>")

        breakdown_items = self._validate_and_calculate_breakdown()

        if not breakdown_items:
            return

        self.breakdown_preview_data = breakdown_items
        self._populate_preview_table(self.breakdown_preview_table, breakdown_items, ["Lot Number", "Quantity (kg)"])

        total_preview_qty = sum(item['quantity_kg'] for item in breakdown_items)
        self.breakdown_total_label.setText(f"<b>Total: {float(total_preview_qty):.2f} kg</b>")

    def _save_lot_breakdown_to_db(self):
        dr_no = self.breakdown_dr_no_combo.currentText()
        if not dr_no or self.breakdown_dr_no_combo.currentIndex() == 0:
            QMessageBox.warning(self, "No DR Selected", "Please select a Delivery Receipt to save the breakdown to.")
            return

        if not self.breakdown_preview_data:
            QMessageBox.warning(self, "No Preview Data", "Please generate a preview of the breakdown before saving.")
            return

        reply = QMessageBox.question(self, "Confirm Save",
                                     f"This will <b>delete any existing breakdown</b> for DR {dr_no} and save the new one. Are you sure you want to proceed?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)

        if reply == QMessageBox.StandardButton.Cancel:
            return

        try:
            with self.engine.connect() as conn, conn.begin():
                delete_stmt = text("DELETE FROM product_delivery_lot_breakdown WHERE dr_no = :dr_no")
                conn.execute(delete_stmt, {"dr_no": dr_no})

                insert_stmt = text("""
                    INSERT INTO product_delivery_lot_breakdown (dr_no, lot_number, quantity_kg)
                    VALUES (:dr_no, :lot_number, :quantity_kg)
                """)

                insert_data = [
                    {"dr_no": dr_no, "lot_number": item['lot_number'], "quantity_kg": item['quantity_kg']}
                    for item in self.breakdown_preview_data
                ]

                if insert_data:
                    conn.execute(insert_stmt, insert_data)

                self.log_audit_trail("SAVE_LOT_BREAKDOWN", f"Saved lot breakdown for DR: {dr_no}")
                QMessageBox.information(self, "Success", f"Lot breakdown for DR {dr_no} has been saved successfully.")
                self._clear_breakdown_tool()

        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Failed to save lot breakdown: {e}")

    def _populate_preview_table(self, table_widget: QTableWidget, data: list, headers: list):
        table_widget.setRowCount(0);
        table_widget.setColumnCount(len(headers));
        table_widget.setHorizontalHeaderLabels(headers)
        if not data: return
        table_widget.setRowCount(len(data));
        keys = list(data[0].keys())
        for i, row_data in enumerate(data):
            for j, key in enumerate(keys):
                val = row_data.get(key)
                item_text = f"{float(val):.2f}" if isinstance(val, (Decimal, float)) else str(val or "")
                item = QTableWidgetItem(item_text)
                if isinstance(val, (Decimal, float)): item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table_widget.setItem(i, j, item)

    def _load_tracking_data(self):
        search_text = f"%{self.tracking_search_edit.text()}%"
        try:
            with self.engine.connect() as conn:
                sql = text("""
                    SELECT 
                        dt.dr_no, p.customer_name, dt.status, dt.scanned_by, dt.scanned_on 
                    FROM delivery_tracking dt
                    JOIN product_delivery_primary p ON dt.dr_no = p.dr_no
                    WHERE dt.dr_no ILIKE :search ORDER BY dt.scanned_on DESC
                """)
                results = conn.execute(sql, {"search": search_text}).mappings().all()
            self.tracking_table.setRowCount(len(results))
            self.tracking_table.setColumnCount(5)
            self.tracking_table.setHorizontalHeaderLabels(["DR No.", "Customer", "Status", "Updated By", "Updated On"])
            for row, record in enumerate(results):
                dr_no_item = QTableWidgetItem(record['dr_no'])
                customer_item = QTableWidgetItem(record['customer_name'])
                status_item = QTableWidgetItem(record['status'])
                scanned_by_item = QTableWidgetItem(record['scanned_by'])
                scanned_on_str = QDateTime(record['scanned_on']).toString("yyyy-MM-dd hh:mm AP") if record[
                    'scanned_on'] else ""
                scanned_on_item = QTableWidgetItem(scanned_on_str)
                if record['status'] == 'Out for Delivery':
                    font = QFont("Segoe UI", 10);
                    font.setBold(True)
                    status_item.setFont(font);
                    status_item.setForeground(QColor('#e67e22'))
                self.tracking_table.setItem(row, 0, dr_no_item)
                self.tracking_table.setItem(row, 1, customer_item)
                self.tracking_table.setItem(row, 2, status_item)
                self.tracking_table.setItem(row, 3, scanned_by_item)
                self.tracking_table.setItem(row, 4, scanned_on_item)
            self.tracking_table.resizeColumnsToContents()
            self.tracking_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        except Exception as e:
            QMessageBox.critical(self, "Tracking Error", f"Could not load tracking data: {e}")

    def _update_delivery_status(self):
        dr_no = self.scanner_input.text().strip()
        if not dr_no:
            QMessageBox.warning(self, "Input Error", "Please scan or enter a DR Number.")
            return
        status = "Out for Delivery"
        try:
            with self.engine.connect() as conn, conn.begin():
                dr_exists = conn.execute(text(
                    "SELECT EXISTS(SELECT 1 FROM product_delivery_primary WHERE dr_no = :dr_no AND is_deleted IS NOT TRUE)"),
                    {"dr_no": dr_no}).scalar()
                if not dr_exists:
                    QMessageBox.critical(self, "Not Found", f"Delivery Receipt '{dr_no}' does not exist.")
                    return
                upsert_sql = text("""
                    INSERT INTO delivery_tracking (dr_no, status, scanned_by, scanned_on)
                    VALUES (:dr_no, :status, :user, :now)
                    ON CONFLICT (dr_no) DO UPDATE SET 
                        status = EXCLUDED.status, scanned_by = EXCLUDED.scanned_by, scanned_on = EXCLUDED.scanned_on;
                """)
                conn.execute(upsert_sql,
                             {"dr_no": dr_no, "status": status, "user": self.username, "now": datetime.now()})
            QMessageBox.information(self, "Success", f"DR #{dr_no} status updated to '{status}'.")
            scan_time = QDateTime.currentDateTime().toString("hh:mm:ss AP")
            self.scanner_log_table.insertRow(0)
            self.scanner_log_table.setItem(0, 0, QTableWidgetItem(scan_time))
            self.scanner_log_table.setItem(0, 1, QTableWidgetItem(dr_no))
            self.scanner_log_table.setItem(0, 2, QTableWidgetItem(status))
            self.log_audit_trail("UPDATE_DELIVERY_STATUS", f"DR: {dr_no}, New Status: {status}")
            self.scanner_input.clear()
            self._load_tracking_data()
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Could not update status for DR {dr_no}: {e}")

    def _print_receipt(self, dr_no):
        if not dr_no:
            QMessageBox.warning(self, "No Record Selected", "A record must be selected to print.")
            return
        try:
            with self.engine.connect() as conn:
                primary = conn.execute(
                    text("SELECT * FROM product_delivery_primary WHERE dr_no = :dr_no"),
                    {"dr_no": dr_no}).mappings().one()
                items_data = conn.execute(
                    text("""SELECT * FROM product_delivery_items 
                            WHERE dr_no = :dr_no ORDER BY id"""),
                    {"dr_no": dr_no}).mappings().all()
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Could not fetch record {dr_no} for printing: {e}")
            return
        primary_data = {
            "dr_no": primary.get('dr_no'),
            "delivery_date": QDate(primary.get('delivery_date')).toString("MM/dd/yyyy"),
            "charge_to": primary.get('customer_name', ''),
            "deliver_to": primary.get('deliver_to', ''),
            "address": primary.get('address', ''),
            "po_no": primary.get('po_no', ''),
            "terms": primary.get('terms', '')
        }
        try:
            self.current_pdf_buffer = self._generate_reportlab_pdf(primary_data, items_data)
        except Exception as e:
            QMessageBox.critical(self, "PDF Generation Error", f"Could not generate PDF: {e}");
            return
        custom_size = QSizeF(8.5, 6.5)
        custom_page_size = QPageSize(custom_size, QPageSize.Unit.Inch, "Delivery Receipt (Landscape 8.5x6.5)")
        self.printer.setPageSize(custom_page_size)
        self.printer.setFullPage(True)
        preview = QPrintPreviewDialog(self.printer, self)
        preview.paintRequested.connect(self._handle_paint_request)
        preview.resize(1000, 800)
        if preview.exec():
            try:
                with self.engine.connect() as conn, conn.begin():
                    conn.execute(text(
                        "UPDATE product_delivery_primary SET is_printed = TRUE, edited_by = :u, edited_on = :n WHERE dr_no = :dr"),
                        {"u": self.username, "n": datetime.now(), "dr": dr_no})
                self.log_audit_trail("PRINT_DELIVERY", f"Printed DR: {dr_no}")
                self._load_all_records()
            except Exception as e:
                QMessageBox.critical(self, "Database Error", f"Could not mark record as printed: {e}")

    def _draw_dr_page_template(self, canvas, doc, footer_table):
        canvas.saveState()
        page_width, page_height = doc.pagesize
        footer_w, footer_h = footer_table.wrapOn(canvas, doc.width, doc.bottomMargin)
        footer_table.drawOn(canvas, doc.leftMargin, 0.25 * inch)
        canvas.restoreState()

    def _generate_reportlab_pdf(self, primary_data, items_data):
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=(8.5 * inch, 6.5 * inch),
                                topMargin=0.25 * inch, bottomMargin=1.8 * inch,
                                leftMargin=0.25 * inch, rightMargin=0.25 * inch)
        qr_img = qrcode.make(primary_data['dr_no'])
        qr_buffer = io.BytesIO()
        qr_img.save(qr_buffer, format='PNG')
        qr_buffer.seek(0)
        reportlab_qr = ReportLabImage(qr_buffer, width=0.8 * inch, height=0.8 * inch)
        try:
            pdfmetrics.registerFont(TTFont('Arial', 'arial.ttf'))
            pdfmetrics.registerFont(TTFont('Arial-Bold', 'arialbd.ttf'))
            FONT_NORMAL, FONT_BOLD = 'Arial', 'Arial-Bold'
        except Exception:
            FONT_NORMAL, FONT_BOLD = 'Helvetica', 'Helvetica-Bold'
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name='DRTitle', fontName=FONT_BOLD, fontSize=14, alignment=TA_LEFT))
        styles.add(ParagraphStyle(name='DRLabel', fontName=FONT_NORMAL, fontSize=10, alignment=TA_LEFT))
        styles.add(ParagraphStyle(name='DRNumber', fontName=FONT_BOLD, fontSize=16, alignment=TA_LEFT))
        styles.add(ParagraphStyle(name='DRData', fontName=FONT_NORMAL, fontSize=10, alignment=TA_LEFT))
        styles.add(ParagraphStyle(name='CustomerData', fontName=FONT_BOLD, fontSize=12, leading=12))
        styles.add(ParagraphStyle(name='CustomerData2', fontName=FONT_BOLD, fontSize=10, leading=12))
        styles.add(ParagraphStyle(name='ItemHeader', fontName=FONT_BOLD, fontSize=9, alignment=TA_CENTER))
        styles.add(ParagraphStyle(name='ItemText', fontName=FONT_NORMAL, fontSize=10, alignment=TA_CENTER))
        styles.add(ParagraphStyle(name='ItemTextRight', parent=styles['ItemText'], alignment=TA_RIGHT))
        styles.add(ParagraphStyle(name='ItemDesc', fontName=FONT_BOLD, fontSize=10, leading=11))
        styles.add(ParagraphStyle(name='NothingFollows', fontName=FONT_BOLD, fontSize=9, alignment=TA_CENTER))
        styles.add(ParagraphStyle(name='FooterText', fontName=FONT_NORMAL, fontSize=9))
        styles.add(ParagraphStyle(name='Footerby', fontName=FONT_NORMAL, fontSize=9, alignment=TA_LEFT, leading=10))
        styles.add(ParagraphStyle(name='ImportantText', fontName=FONT_NORMAL, fontSize=7, leading=8))
        received_by_text = "Received the above items in good order and condition.<br/><br/>By: _____________________________<br/><font size=8>Signature over printed Name/Date</font>"
        important_text = """
                IMPORTANT: Merchandise described in this Delivery Receipt remains the property of MASTERBATCH PHILIPPINES, INC. until fully paid. Interest of 18% per annum
                is to be charged on all overdue accounts. An additional sum equal to 25% of the amount will be charged by the vendor or attorney's fees and cost
                of collection in case of suit. Parties expressly submit themselves to the jurisdiction of the courts of MANILA in any legal action arising from the transaction.
                """
        full_footer_data = [
            [Paragraph(received_by_text, styles['Footerby']),
             Paragraph("Delivery Time In: ________________", styles['FooterText']),
             Paragraph("Delivery Time Out: ________________", styles['FooterText'])],
            [Paragraph(important_text, styles['ImportantText']), '', '']
        ]
        full_footer_table = Table(full_footer_data, colWidths=[3.0 * inch, 2.5 * inch, 2.5 * inch],
                                  rowHeights=[0.8 * inch, None])
        full_footer_table.setStyle(TableStyle(
            [('VALIGN', (0, 0), (-1, 0), 'TOP'), ('SPAN', (0, 1), (2, 1)), ('TOPPADDING', (0, 1), (-1, 1), 10)]))
        Story = []
        left_header_text = "<b>MASTERBATCH PHILIPPINES INC.</b><br/><font size='9'>24 Diamond Road Caloocan Industrial Subdivision, Bo. Kaybiga, Caloocan City, Philippines</font><br/><font size='9'>Tel. Nos.: 8935-9579 / 7758-1207 Telefax: 8374-7085</font><br/><font size='9'>TIN NO.: 238-034-470-000</font>"
        left_header = Paragraph(left_header_text, styles['CustomerData'])
        right_header_top_table = Table([[Paragraph("DELIVERY RECEIPT", styles['DRTitle']), reportlab_qr]],
                                       colWidths=[2.2 * inch, 1.0 * inch], style=[('VALIGN', (0, 0), (-1, -1), 'TOP')])
        right_header_data = [[right_header_top_table], [Table(
            [[Paragraph("No.:", styles['DRLabel']), Paragraph(primary_data['dr_no'], styles['DRNumber'])],
             [Paragraph("Delivery Date:", styles['DRLabel']),
              Paragraph(primary_data['delivery_date'], styles['DRData'])],
             [Paragraph("PO No.:", styles['DRLabel']), Paragraph(primary_data['po_no'], styles['DRData'])],
             [Paragraph("Terms of Payment:", styles['DRLabel']), '']], colWidths=[1.1 * inch, 1.8 * inch],
            style=[('VALIGN', (0, 0), (-1, -1), 'MIDDLE')])]]
        right_header_table = Table(right_header_data, rowHeights=[0.4 * inch, 0.8 * inch]);
        right_header_table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
        header_table = Table([[left_header, right_header_table]], colWidths=[4.8 * inch, 3.2 * inch],
                             style=[('VALIGN', (0, 0), (-1, -1), 'TOP')])
        Story.append(header_table)
        Story.append(Spacer(1, 0.1 * inch))
        address_html = primary_data.get('address', '').replace('\n', '<br/>')
        customer_info_text = f"<font size=9>Customer's Name/Address</font><br/><b>Charge to: &nbsp;&nbsp;&nbsp;{primary_data['charge_to']}</b><br/><b>Deliver to: &nbsp;&nbsp;{primary_data['deliver_to']}</b><br/><b>Address: &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{address_html}</b>"
        Story.append(Paragraph(customer_info_text, styles['CustomerData2']))
        Story.append(Spacer(1, 0.15 * inch))
        table_data = [[Paragraph("QUANTITY", styles['ItemHeader']), Paragraph("UNIT", styles['ItemHeader']),
                       Paragraph("DESCRIPTION", styles['ItemHeader']), Paragraph("UNIT PRICE", styles['ItemHeader']),
                       Paragraph("AMOUNT", styles['ItemHeader'])]]

        for item_row in items_data:
            # Convert the SQLAlchemy Row to a dictionary
            item = dict(item_row)
            desc_parts = []

            # --- REVISED LOGIC ---
            # 1. Prioritize special descriptions if they exist.
            desc1 = item.get('description_1', '')
            desc2 = item.get('description_2', '')

            first_line = f"{desc1} {desc2}".strip()
            # 2. If no special descriptions, fall back to product code/color.
            if not first_line:
                first_line = f"{item.get('product_code', '')} {item.get('product_color', '')}".strip()

            if first_line:
                desc_parts.append(first_line)

            # 3. Add packing info
            no_packing_str = str(item.get('no_of_packing', '0') or '0')
            try:
                if float(no_packing_str) > 0:
                    desc_parts.append(f"{no_packing_str} Bag(s) by {item.get('weight_per_pack')} KG.")
            except (ValueError, TypeError):
                pass  # Ignore if it's not a valid number

            # 4. Add lot numbers
            if lot1 := item.get('lot_no_1'): desc_parts.append(lot1)
            if lot2 := item.get('lot_no_2'): desc_parts.append(lot2)
            if lot3 := item.get('lot_no_3'): desc_parts.append(lot3)

            # 5. Add attachments
            if attachments := item.get('attachments'):
                # Split attachments by newline to show them on separate lines in the PDF
                attachment_lines = [line.strip() for line in attachments.split('\n') if line.strip()]
                desc_parts.extend(attachment_lines)

            desc = "<br/>".join(p for p in desc_parts if p)

            unit_price_val, quantity_val = item.get('unit_price'), item.get('quantity')
            unit_price_str = f"{float(unit_price_val):.2f}" if unit_price_val is not None else ""
            quantity_str = f"{float(quantity_val):.2f}" if quantity_val is not None else ""
            amount_str = ""
            if unit_price_val is not None and quantity_val is not None:
                try:
                    amount = float(unit_price_val) * float(quantity_val)
                    amount_str = f"{amount:,.2f}"
                except (ValueError, TypeError):
                    amount_str = ""

            table_data.append([
                Paragraph(quantity_str, styles['ItemTextRight']),
                Paragraph(item.get('unit', ''), styles['ItemText']),
                Paragraph(desc, styles['ItemDesc']),
                Paragraph(unit_price_str, styles['ItemTextRight']),
                Paragraph(amount_str, styles['ItemTextRight'])
            ])

        items_table = Table(table_data, colWidths=[1.0 * inch, 0.5 * inch, 4.0 * inch, 1.2 * inch, 1.3 * inch],
                            repeatRows=1)
        items_table.setStyle(TableStyle(
            [('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LINEBELOW', (0, 0), (-1, 0), 1, colors.black),
             ('LEFTPADDING', (0, 0), (-1, -1), 4), ('RIGHTPADDING', (0, 0), (-1, -1), 4)]))
        Story.append(items_table)
        Story.append(Spacer(1, 0.1 * inch))
        Story.append(Paragraph("******************** NOTHING FOLLOWS ********************", styles['NothingFollows']))
        page_template_drawer = partial(self._draw_dr_page_template, footer_table=full_footer_table)
        doc.build(Story, onFirstPage=page_template_drawer, onLaterPages=page_template_drawer)
        buffer.seek(0)
        return buffer

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