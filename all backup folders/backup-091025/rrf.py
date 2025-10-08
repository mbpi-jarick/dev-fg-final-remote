# rrf.py (Returned/Replacement Form - with Breakdown Management Tab)
# FINAL - Merged modern UI, fixed breakdown view, and upgraded the Lot Breakdown Tool logic.
# ENHANCED - Added right-click print preview, total labels in view tab, and an interactive pie chart on the dashboard.
# FIXED - Corrected chart update logic to prevent crashes by connecting signals only once.
# UI TWEAK - Removed borders from the dashboard's 'Recent RRFs' table for a cleaner look.
# V3 - Added Deleted Tab, Restore, Auto-Refresh, Auto-Size Tables, Validation, and Refresh Buttons.
# V4 - Upgraded Item Entry with ComboBoxes for Unit/Product Code and a formatted Quantity input.
# V5 - Reordered tabs, added auto-filtering of product codes by material type, and a warning on type change.
# V6.1 - Implemented user-manageable 'Units' list and refined product code loading to use DISTINCT records.
# V7.0 - Removed Dashboard tab and updated button colors based on function for a streamlined UI.
# V7.1 - Fixed tab navigation errors after dashboard removal by using dynamic tab lookups.
# V7.2 - Styled pagination buttons with a black background and white text for better UI consistency.

import sys
import io
import re
import math
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from functools import partial

# --- ReportLab & PyMuPDF Imports ---
import fitz
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Table, TableStyle)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# --- PyQt6 Imports ---
from PyQt6.QtCore import Qt, QDate, QSize, QSizeF, QDateTime
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QTabWidget, QFormLayout, QLineEdit, QDateEdit,
                             QPushButton, QTableWidget, QTableWidgetItem, QComboBox,
                             QAbstractItemView, QHeaderView, QMessageBox, QHBoxLayout, QLabel,
                             QGroupBox, QMenu, QGridLayout, QDialog, QDialogButtonBox,
                             QPlainTextEdit, QSplitter, QCheckBox, QInputDialog, QCompleter,
                             QListWidget, QListWidgetItem)
from PyQt6.QtGui import (QDoubleValidator, QPainter, QPageSize, QImage)
from PyQt6.QtPrintSupport import QPrinter, QPrintPreviewDialog

# --- Database Imports ---
from sqlalchemy import create_engine, text


class FloatLineEdit(QLineEdit):
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
            self.setText(f"{float(self.text() or 0.0):.2f}")
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


def set_combo_box_uppercase(combo_box: QComboBox):
    if combo_box.isEditable():
        line_edit = combo_box.lineEdit()
        if line_edit:
            line_edit.textChanged.connect(
                lambda text, le=line_edit: (le.blockSignals(True), le.setText(text.upper()), le.blockSignals(False))
            )


class ManageListDialog(QDialog):
    def __init__(self, parent, db_engine, table_name, column_name, title):
        super().__init__(parent)
        self.engine, self.table_name, self.column_name = db_engine, table_name, column_name
        self.setWindowTitle(title)
        self.setMinimumWidth(350)
        self.setModal(True)
        layout = QVBoxLayout(self)
        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)
        button_layout = QHBoxLayout()
        add_btn, remove_btn = QPushButton("Add"), QPushButton("Remove")
        add_btn.setObjectName("PrimaryButton")
        remove_btn.setObjectName("DeleteButton")
        button_layout.addStretch()
        button_layout.addWidget(add_btn)
        button_layout.addWidget(remove_btn)
        layout.addLayout(button_layout)
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        layout.addWidget(button_box)
        add_btn.clicked.connect(self._add_item)
        remove_btn.clicked.connect(self._remove_item)
        button_box.rejected.connect(self.reject)
        self._load_items()

    def _load_items(self):
        self.list_widget.clear()
        try:
            with self.engine.connect() as conn:
                res = conn.execute(
                    text(
                        f"SELECT id, {self.column_name} FROM {self.table_name} ORDER BY {self.column_name}")).mappings().all()
                for row in res:
                    item = QListWidgetItem(row[self.column_name])
                    item.setData(Qt.ItemDataRole.UserRole, row['id'])
                    self.list_widget.addItem(item)
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load items: {e}")

    def _add_item(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Add New Item")
        layout, edit = QFormLayout(dialog), UpperCaseLineEdit()
        layout.addRow("New Value:", edit)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        layout.addRow(buttons)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        if dialog.exec():
            value = edit.text().strip()
            if value:
                try:
                    with self.engine.connect() as conn, conn.begin():
                        conn.execute(
                            text(
                                f"INSERT INTO {self.table_name} ({self.column_name}) VALUES (:v) ON CONFLICT ({self.column_name}) DO NOTHING"),
                            {"v": value})
                    self._load_items()
                except Exception as e:
                    QMessageBox.critical(self, "DB Error", f"Could not add item: {e}")

    def _remove_item(self):
        item = self.list_widget.currentItem()
        if not item: return
        if QMessageBox.question(self, "Confirm", f"Remove '{item.text()}'?") == QMessageBox.StandardButton.Yes:
            try:
                with self.engine.connect() as conn, conn.begin():
                    conn.execute(text(f"DELETE FROM {self.table_name} WHERE id = :id"),
                                 {"id": item.data(Qt.ItemDataRole.UserRole)})
                self._load_items()
            except Exception as e:
                QMessageBox.critical(self, "DB Error", f"Could not remove item: {e}")


class RRFItemEntryDialog(QDialog):
    def __init__(self, db_engine, material_type, item_data=None, parent=None):
        super().__init__(parent)
        self.engine = db_engine
        self.material_type = material_type
        self.setWindowTitle("Enter Item Details")
        self.setMinimumWidth(450)

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.quantity_edit = FloatLineEdit()
        self.unit_edit = QComboBox(editable=True)
        set_combo_box_uppercase(self.unit_edit)
        self.manage_units_btn = QPushButton("Manage...")
        unit_layout = QHBoxLayout()
        unit_layout.setContentsMargins(0, 0, 0, 0)
        unit_layout.addWidget(self.unit_edit, 1)
        unit_layout.addWidget(self.manage_units_btn)

        self.product_code_edit = QComboBox(editable=True)
        self.product_code_edit.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        completer = QCompleter(self)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.product_code_edit.setCompleter(completer)
        set_combo_box_uppercase(self.product_code_edit)

        self.lot_number_edit = UpperCaseLineEdit()
        self.reference_number_edit = UpperCaseLineEdit()
        self.remarks_edit = QPlainTextEdit()

        form_layout.addRow("Quantity:", self.quantity_edit)
        form_layout.addRow("Unit:", unit_layout)
        form_layout.addRow("Product Code:", self.product_code_edit)
        form_layout.addRow("Lot Number:", self.lot_number_edit)
        form_layout.addRow("Reference Number:", self.reference_number_edit)
        form_layout.addRow("Remarks:", self.remarks_edit)

        layout.addLayout(form_layout)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.manage_units_btn.clicked.connect(self._manage_units)
        self._load_combobox_data()
        if item_data:
            self.populate_data(item_data)

    def _manage_units(self):
        dialog = ManageListDialog(self, self.engine, "units", "name", "Manage Units")
        dialog.exec()
        self._load_units()

    def _load_combobox_data(self):
        self._load_units()
        self._load_product_codes()

    def _load_units(self):
        try:
            with self.engine.connect() as conn:
                units = conn.execute(text("SELECT name FROM units ORDER BY name")).scalars().all()
            current_unit = self.unit_edit.currentText()
            self.unit_edit.blockSignals(True)
            self.unit_edit.clear()
            self.unit_edit.addItems(units)
            self.unit_edit.blockSignals(False)
            if current_unit and current_unit in units:
                self.unit_edit.setCurrentText(current_unit)
            elif "KG." in units:
                self.unit_edit.setCurrentText("KG.")
        except Exception as e:
            QMessageBox.warning(self, "Database Error", f"Could not load unit data: {e}")

    def _load_product_codes(self):
        try:
            with self.engine.connect() as conn:
                query_str = conn.execute(
                    text("SELECT DISTINCT prod_code FROM legacy_production ORDER BY prod_code")).scalars().all()
                current = self.product_code_edit.currentText()
                self.product_code_edit.clear()
                self.product_code_edit.addItems([""] + query_str)
                self.product_code_edit.completer().setModel(self.product_code_edit.model())
                if current in query_str:
                    self.product_code_edit.setCurrentText(current)
        except Exception as e:
            QMessageBox.warning(self, "Database Error", f"Could not load product codes: {e}")

    def accept(self):
        if self.quantity_edit.value() <= 0:
            QMessageBox.warning(self, "Validation Error", "Quantity must be greater than zero.")
            return
        if not self.unit_edit.currentText().strip():
            QMessageBox.warning(self, "Validation Error", "Unit cannot be empty.")
            return
        if not self.product_code_edit.currentText().strip():
            QMessageBox.warning(self, "Validation Error", "Product Code cannot be empty.")
            return
        super().accept()

    def populate_data(self, data):
        self.quantity_edit.setText(str(data.get("quantity", "0.00")))
        self.unit_edit.setCurrentText(data.get("unit", "KG."))
        self.product_code_edit.setCurrentText(data.get("product_code", ""))
        self.lot_number_edit.setText(data.get("lot_number", ""))
        self.reference_number_edit.setText(data.get("reference_number", ""))
        self.remarks_edit.setPlainText(data.get("remarks", ""))

    def get_item_data(self):
        return {
            "quantity": self.quantity_edit.text(),
            "unit": self.unit_edit.currentText().strip().upper(),
            "product_code": self.product_code_edit.currentText().strip().upper(),
            "lot_number": self.lot_number_edit.text(),
            "reference_number": self.reference_number_edit.text(),
            "remarks": self.remarks_edit.toPlainText()
        }


class RRFPage(QWidget):
    def __init__(self, db_engine, username, log_audit_trail_func):
        super().__init__()
        self.engine, self.username, self.log_audit_trail = db_engine, username, log_audit_trail_func
        self.current_editing_rrf_no, self.MAX_ITEMS = None, 15
        self.printer, self.current_pdf_buffer = QPrinter(), None
        self.breakdown_preview_data = None
        self.current_page, self.records_per_page = 1, 200
        self.total_records, self.total_pages = 0, 1
        self.previous_material_type_index = 0
        self.init_ui()
        self._load_all_records()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)
        self.setStyleSheet("""
            QPushButton {
                padding: 6px 12px;
                font-size: 10pt;
                border-radius: 4px;
                border: 1px solid #cccccc;
                background-color: #f0f0f0;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
            QPushButton#PrimaryButton { /* Green for Save/Create */
                background-color: #28a745;
                color: white;
                border-color: #28a745;
            }
            QPushButton#PrimaryButton:hover {
                background-color: #218838;
                border-color: #1e7e34;
            }
            QPushButton#UpdateButton { /* Blue for Load/Update/Preview */
                background-color: #007bff;
                color: white;
                border-color: #007bff;
            }
            QPushButton#UpdateButton:hover {
                background-color: #0069d9;
                border-color: #0062cc;
            }
            QPushButton#DeleteButton { /* Red for Delete/Remove */
                background-color: #dc3545;
                color: white;
                border-color: #dc3545;
            }
            QPushButton#DeleteButton:hover {
                background-color: #c82333;
                border-color: #bd2130;
            }
            QPushButton#SecondaryButton { /* Gray for Cancel/Clear/Refresh */
                background-color: #6c757d;
                color: white;
                border-color: #6c757d;
            }
            QPushButton#SecondaryButton:hover {
                background-color: #5a6268;
                border-color: #545b62;
            }
            QPushButton#PaginationButton { /* gray for Next/Previous */
                background-color: #6c757d;
                color: white;
                border-color: #6c757d;
            }
            QPushButton#PaginationButton:hover {
                background-color: #343a40;
                border-color: #343a40;
            }
        """)

        # Define Tab Widgets
        view_tab = QWidget()
        self.entry_tab = QWidget()
        self.view_details_tab = QWidget()
        breakdown_tool_tab = QWidget()
        breakdown_records_tab = QWidget()
        deleted_tab = QWidget()

        # Add Tabs in Order
        self.tab_widget.addTab(view_tab, "RRF Records")
        self.tab_widget.addTab(self.entry_tab, "RRF Entry")
        self.tab_widget.addTab(self.view_details_tab, "View RRF Details")
        self.tab_widget.addTab(breakdown_tool_tab, "Lot Breakdown Tool")
        self.tab_widget.addTab(breakdown_records_tab, "Breakdown Records")
        self.tab_widget.addTab(deleted_tab, "Deleted")

        # Setup UI for each tab
        self._setup_view_tab(view_tab)
        self._setup_entry_tab(self.entry_tab)
        self._setup_view_details_tab(self.view_details_tab)
        self._setup_lot_breakdown_tab(breakdown_tool_tab)
        self._setup_breakdown_records_tab(breakdown_records_tab)
        self._setup_deleted_tab(deleted_tab)

        self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.view_details_tab), False)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

    def _setup_view_tab(self, tab):
        layout = QVBoxLayout(tab)
        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("Search:"))
        self.search_edit = UpperCaseLineEdit(placeholderText="Filter by RRF No, Customer, Product Code...")
        self.refresh_records_btn = QPushButton("Refresh")
        self.refresh_records_btn.setObjectName("SecondaryButton")
        self.update_btn = QPushButton("Load Selected for Update")
        self.update_btn.setObjectName("UpdateButton")
        self.delete_btn = QPushButton("Delete Selected")
        self.delete_btn.setObjectName("DeleteButton")
        top_layout.addWidget(self.search_edit, 1)
        top_layout.addWidget(self.refresh_records_btn)
        top_layout.addWidget(self.update_btn)
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
        layout.addWidget(self.records_table)
        pagination_layout = QHBoxLayout()
        self.prev_btn = QPushButton("<< Previous")
        self.next_btn = QPushButton("Next >>")
        self.prev_btn.setObjectName("PaginationButton")
        self.next_btn.setObjectName("PaginationButton")
        self.page_label = QLabel("Page 1 of 1")
        pagination_layout.addStretch()
        pagination_layout.addWidget(self.prev_btn)
        pagination_layout.addWidget(self.page_label)
        pagination_layout.addWidget(self.next_btn)
        pagination_layout.addStretch()
        layout.addLayout(pagination_layout)
        self.search_edit.textChanged.connect(self._on_search_text_changed)
        self.refresh_records_btn.clicked.connect(self._load_all_records)
        self.update_btn.clicked.connect(self._load_record_for_update)
        self.delete_btn.clicked.connect(self._delete_record)
        self.records_table.doubleClicked.connect(self._load_record_for_update)
        self.records_table.customContextMenuRequested.connect(self._show_records_table_context_menu)
        self.records_table.itemSelectionChanged.connect(self._on_record_selection_changed)
        self.prev_btn.clicked.connect(self._go_to_prev_page)
        self.next_btn.clicked.connect(self._go_to_next_page)
        self._on_record_selection_changed()

    def _setup_entry_tab(self, tab):
        main_layout = QVBoxLayout(tab)
        primary_group = QGroupBox("RRF Information")
        primary_layout = QGridLayout(primary_group)
        self.rrf_no_edit = QLineEdit(readOnly=True, placeholderText="Auto-generated")
        self.rrf_date_edit = QDateEdit(calendarPopup=True, displayFormat="yyyy-MM-dd")
        self.customer_combo = QComboBox(editable=True)
        self.material_type_combo = QComboBox()
        self.material_type_combo.addItems(["FINISHED GOOD", "RAW MATERIAL", "SEMI-FINISHED GOOD", "OTHER"])
        self.prepared_by_label = QLabel(self.username.upper())
        primary_layout.addWidget(QLabel("RRF Number:"), 0, 0);
        primary_layout.addWidget(self.rrf_no_edit, 0, 1)
        primary_layout.addWidget(QLabel("RRF Date:"), 0, 2);
        primary_layout.addWidget(self.rrf_date_edit, 0, 3)
        primary_layout.addWidget(QLabel("Supplier/Customer:"), 1, 0);
        primary_layout.addWidget(self.customer_combo, 1, 1, 1, 3)
        primary_layout.addWidget(QLabel("Material Type:"), 2, 0);
        primary_layout.addWidget(self.material_type_combo, 2, 1)
        primary_layout.addWidget(QLabel("Prepared By:"), 2, 2);
        primary_layout.addWidget(self.prepared_by_label, 2, 3)
        main_layout.addWidget(primary_group)
        items_group = QGroupBox("Item Details")
        items_layout = QVBoxLayout(items_group)
        self.items_table = QTableWidget()
        self.items_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.items_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.items_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.items_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.items_table.setShowGrid(False)
        self.items_table.verticalHeader().setVisible(False)
        self.items_table.horizontalHeader().setHighlightSections(False)
        self.items_table.setColumnCount(6)
        self.items_table.setHorizontalHeaderLabels(
            ["Qty", "Unit", "Product Code", "Lot Number", "Reference No.", "Remarks"])
        self.items_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.items_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.items_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        items_layout.addWidget(self.items_table)
        items_button_layout = QHBoxLayout()
        self.item_count_label = QLabel(f"Items: 0 / {self.MAX_ITEMS}")
        items_button_layout.addWidget(self.item_count_label, 1)
        add_item_btn = QPushButton("Add Item")
        add_item_btn.setObjectName("SecondaryButton")
        self.edit_item_btn = QPushButton("Edit Item")
        self.remove_item_btn = QPushButton("Remove Item")
        self.remove_item_btn.setObjectName("DeleteButton")
        items_button_layout.addWidget(add_item_btn);
        items_button_layout.addWidget(self.edit_item_btn);
        items_button_layout.addWidget(self.remove_item_btn)
        items_layout.addLayout(items_button_layout)
        main_layout.addWidget(items_group, 1)
        action_button_layout = QHBoxLayout()
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("SecondaryButton")
        self.save_btn = QPushButton("Save");
        self.save_btn.setObjectName("PrimaryButton")
        self.print_btn = QPushButton("Print Preview")
        action_button_layout.addStretch()
        action_button_layout.addWidget(self.cancel_btn)
        action_button_layout.addWidget(self.save_btn)
        action_button_layout.addWidget(self.print_btn)
        main_layout.addLayout(action_button_layout)
        add_item_btn.clicked.connect(self._add_item_row);
        self.edit_item_btn.clicked.connect(self._edit_item_row)
        self.remove_item_btn.clicked.connect(self._remove_item_row)
        self.cancel_btn.clicked.connect(self._clear_form)
        self.save_btn.clicked.connect(self._save_record);
        self.print_btn.clicked.connect(self._trigger_print_preview_from_form)
        self.items_table.itemSelectionChanged.connect(self._on_item_selection_changed)
        self.material_type_combo.currentIndexChanged.connect(self._on_material_type_changed)
        self._clear_form()

    def _on_material_type_changed(self):
        self.material_type_combo.blockSignals(True)
        current_index = self.material_type_combo.currentIndex()
        if self.items_table.rowCount() > 0:
            reply = QMessageBox.question(self, "Confirm Change",
                                         "Changing the material type will clear the current list of items.\n\n"
                                         "Are you sure you want to proceed?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

            if reply == QMessageBox.StandardButton.Yes:
                self.items_table.setRowCount(0)
                self._update_item_count()
                self.previous_material_type_index = current_index
            else:
                self.material_type_combo.setCurrentIndex(self.previous_material_type_index)
        else:
            self.previous_material_type_index = current_index
        self.material_type_combo.blockSignals(False)

    def _setup_lot_breakdown_tab(self, tab):
        layout = QVBoxLayout(tab)
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(main_splitter)
        left_widget = QWidget();
        left_layout = QVBoxLayout(left_widget);
        left_layout.setContentsMargins(0, 0, 5, 0)
        main_splitter.addWidget(left_widget)
        fetch_group = QGroupBox("1. Select RRF Item");
        fetch_layout = QFormLayout(fetch_group)
        self.breakdown_rrf_combo = QComboBox();
        self.breakdown_item_combo = QComboBox()
        self.breakdown_item_qty_display = QLineEdit("0.00", readOnly=True);
        self.breakdown_item_qty_display.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.breakdown_item_qty_display.setStyleSheet("background-color: #f0f0f0; font-weight: bold;")
        fetch_layout.addRow("RRF Number:", self.breakdown_rrf_combo);
        fetch_layout.addRow("Item to Break Down:", self.breakdown_item_combo)
        fetch_layout.addRow("Target Quantity (kg):", self.breakdown_item_qty_display)
        left_layout.addWidget(fetch_group)
        params_group = QGroupBox("2. Define Breakdown");
        params_layout = QGridLayout(params_group)
        self.breakdown_weight_per_lot_edit = FloatLineEdit()
        self.breakdown_num_lots_edit = QLineEdit("0", readOnly=True);
        self.breakdown_num_lots_edit.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.breakdown_num_lots_edit.setStyleSheet("background-color: #f0f0f0;")
        self.breakdown_lot_range_edit = UpperCaseLineEdit(placeholderText="e.g., 12345 or 12345-12350")
        self.breakdown_is_range_check = QCheckBox("Lot input is a range")
        params_layout.addWidget(QLabel("Weight per Lot (kg):"), 0, 0);
        params_layout.addWidget(self.breakdown_weight_per_lot_edit, 0, 1)
        params_layout.addWidget(QLabel("Calculated No. of Lots:"), 0, 2);
        params_layout.addWidget(self.breakdown_num_lots_edit, 0, 3)
        params_layout.addWidget(QLabel("Lot Start/Range:"), 1, 0);
        params_layout.addWidget(self.breakdown_lot_range_edit, 1, 1, 1, 3)
        params_layout.addWidget(self.breakdown_is_range_check, 2, 1, 1, 3)
        left_layout.addWidget(params_group)
        left_layout.addStretch()
        right_widget = QWidget();
        right_layout = QVBoxLayout(right_widget);
        right_layout.setContentsMargins(5, 0, 0, 0)
        main_splitter.addWidget(right_widget)
        breakdown_preview_group = QGroupBox("3. Preview and Save");
        breakdown_preview_layout = QVBoxLayout(breakdown_preview_group)
        self.breakdown_preview_table = QTableWidget(editTriggers=QAbstractItemView.EditTrigger.NoEditTriggers)
        self.breakdown_preview_table.setShowGrid(False);
        self.breakdown_preview_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.breakdown_preview_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.breakdown_preview_table.verticalHeader().setVisible(False);
        self.breakdown_preview_table.horizontalHeader().setHighlightSections(False)
        self.breakdown_preview_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.breakdown_total_label = QLabel("<b>Total: 0.00 kg</b>");
        self.breakdown_total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        breakdown_preview_layout.addWidget(self.breakdown_preview_table);
        breakdown_preview_layout.addWidget(self.breakdown_total_label)
        right_layout.addWidget(breakdown_preview_group)
        main_splitter.setSizes([500, 600])
        button_layout = QHBoxLayout()
        self.breakdown_save_btn = QPushButton("Save Breakdown");
        self.breakdown_save_btn.setObjectName("PrimaryButton")
        preview_btn = QPushButton("Preview Breakdown");
        preview_btn.setObjectName("UpdateButton")
        clear_btn = QPushButton("Clear");
        clear_btn.setObjectName("SecondaryButton")
        button_layout.addStretch();
        button_layout.addWidget(clear_btn);
        button_layout.addWidget(preview_btn);
        button_layout.addWidget(self.breakdown_save_btn)
        left_layout.addLayout(button_layout)
        self.breakdown_rrf_combo.currentIndexChanged.connect(self._on_breakdown_rrf_selected)
        self.breakdown_item_combo.currentIndexChanged.connect(self._on_breakdown_item_selected)
        self.breakdown_weight_per_lot_edit.textChanged.connect(self._recalculate_num_lots)
        preview_btn.clicked.connect(self._preview_lot_breakdown);
        clear_btn.clicked.connect(self._clear_breakdown_tool)
        self.breakdown_save_btn.clicked.connect(self._save_lot_breakdown)

    def _setup_breakdown_records_tab(self, tab):
        layout = QVBoxLayout(tab)
        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("Search:"))
        self.breakdown_search_edit = UpperCaseLineEdit(placeholderText="Filter by RRF No or Product Code...")
        self.refresh_breakdown_btn = QPushButton("Refresh")
        self.refresh_breakdown_btn.setObjectName("SecondaryButton")
        self.load_breakdown_btn = QPushButton("Load for Update");
        self.load_breakdown_btn.setObjectName("UpdateButton")
        self.delete_breakdown_btn = QPushButton("Delete Selected Breakdown");
        self.delete_breakdown_btn.setObjectName("DeleteButton")
        top_layout.addWidget(self.breakdown_search_edit, 1);
        top_layout.addWidget(self.refresh_breakdown_btn)
        top_layout.addWidget(self.load_breakdown_btn);
        top_layout.addWidget(self.delete_breakdown_btn)
        layout.addLayout(top_layout)
        self.breakdown_records_table = QTableWidget()
        self.breakdown_records_table.setShowGrid(False);
        self.breakdown_records_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.breakdown_records_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.breakdown_records_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.breakdown_records_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.breakdown_records_table.verticalHeader().setVisible(False);
        self.breakdown_records_table.horizontalHeader().setHighlightSections(False)
        self.breakdown_records_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.breakdown_records_table)
        self.breakdown_search_edit.textChanged.connect(self._load_all_breakdown_records)
        self.refresh_breakdown_btn.clicked.connect(self._load_all_breakdown_records)
        self.load_breakdown_btn.clicked.connect(self._load_breakdown_for_update)
        self.delete_breakdown_btn.clicked.connect(self._delete_selected_breakdown)
        self.breakdown_records_table.doubleClicked.connect(self._load_breakdown_for_update)
        self.breakdown_records_table.itemSelectionChanged.connect(lambda: (
            self.load_breakdown_btn.setEnabled(bool(self.breakdown_records_table.selectionModel().selectedRows())),
            self.delete_breakdown_btn.setEnabled(bool(self.breakdown_records_table.selectionModel().selectedRows()))
        ))
        self.load_breakdown_btn.setEnabled(False);
        self.delete_breakdown_btn.setEnabled(False)

    def _setup_deleted_tab(self, tab):
        layout = QVBoxLayout(tab)
        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("Search Deleted Records:"))
        self.deleted_search_edit = UpperCaseLineEdit(placeholderText="Filter by RRF No, Customer...")
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
        self.deleted_records_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.deleted_records_table)
        self.deleted_search_edit.textChanged.connect(self._load_deleted_records)
        self.deleted_records_table.customContextMenuRequested.connect(self._show_deleted_records_context_menu)

    def _on_tab_changed(self, index):
        tab_text = self.tab_widget.tabText(index)
        if tab_text == "RRF Records":
            self._load_all_records()
        elif tab_text == "RRF Entry" and not self.current_editing_rrf_no:
            self._load_combobox_data()
        elif tab_text == "Lot Breakdown Tool":
            self._clear_breakdown_tool(); self._load_rrf_numbers_for_breakdown()
        elif tab_text == "Breakdown Records":
            self._load_all_breakdown_records()
        elif tab_text == "Deleted":
            self._load_deleted_records()

    def _on_search_text_changed(self):
        self.current_page = 1;
        self._load_all_records()

    def _go_to_prev_page(self):
        if self.current_page > 1: self.current_page -= 1; self._load_all_records()

    def _go_to_next_page(self):
        if self.current_page < self.total_pages: self.current_page += 1; self._load_all_records()

    def _update_pagination_controls(self):
        self.total_pages = (self.total_records + self.records_per_page - 1) // self.records_per_page or 1
        self.page_label.setText(f"Page {self.current_page} of {self.total_pages}")
        self.prev_btn.setEnabled(self.current_page > 1);
        self.next_btn.setEnabled(self.current_page < self.total_pages)

    def _load_all_breakdown_records(self):
        search_term = f"%{self.breakdown_search_edit.text()}%"
        query = text("""
            SELECT b.rrf_no, b.item_id, i.product_code, i.quantity AS original_item_quantity,
                   COUNT(b.id) AS lot_count, STRING_AGG(b.lot_number, ', ' ORDER BY b.id) AS lot_numbers
            FROM rrf_lot_breakdown b
            JOIN rrf_items i ON b.rrf_no = i.rrf_no AND b.item_id = i.id
            WHERE b.rrf_no ILIKE :search OR i.product_code ILIKE :search
            GROUP BY b.rrf_no, b.item_id, i.product_code, i.quantity
            ORDER BY b.rrf_no DESC, b.item_id ASC;
        """)
        try:
            with self.engine.connect() as conn:
                results = conn.execute(query, {"search": search_term}).mappings().all()
            headers = ["RRF No", "Item ID", "Product Code", "Original Qty", "Lot Count", "Generated Lot Numbers"]
            self._populate_breakdown_records_table(results, headers)
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Could not load breakdown records: {e}")

    def _populate_breakdown_records_table(self, data, headers):
        table = self.breakdown_records_table
        table.setRowCount(0);
        table.setColumnCount(len(headers));
        table.setHorizontalHeaderLabels(headers)
        if not data: table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch); return
        table.setRowCount(len(data))
        keys = ["rrf_no", "item_id", "product_code", "original_item_quantity", "lot_count", "lot_numbers"]
        for i, row in enumerate(data):
            for j, key in enumerate(keys):
                value = row.get(key)
                display_value = f"{float(value):.2f}" if isinstance(value, (Decimal, float)) else str(value or "")
                item = QTableWidgetItem(display_value)
                if key in ["original_item_quantity", "lot_count"]:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(i, j, item)
        table.resizeColumnsToContents()
        table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)

    def _load_breakdown_for_update(self):
        selected = self.breakdown_records_table.selectionModel().selectedRows();
        if not selected: return
        row_index = selected[0].row()
        rrf_no = self.breakdown_records_table.item(row_index, 0).text()
        item_id = int(self.breakdown_records_table.item(row_index, 1).text())

        breakdown_tool_widget = None
        for i in range(self.tab_widget.count()):
            if self.tab_widget.tabText(i) == "Lot Breakdown Tool":
                breakdown_tool_widget = self.tab_widget.widget(i)
                break

        if breakdown_tool_widget:
            self.tab_widget.setCurrentWidget(breakdown_tool_widget)
        else:
            return

        rrf_combo_index = self.breakdown_rrf_combo.findText(rrf_no, Qt.MatchFlag.MatchFixedString)
        if rrf_combo_index >= 0:
            self.breakdown_rrf_combo.setCurrentIndex(rrf_combo_index)
        else:
            QMessageBox.warning(self, "Not Found", f"Could not find RRF No {rrf_no} in the dropdown.");
            return
        QApplication.processEvents()
        for i in range(self.breakdown_item_combo.count()):
            if (item_data := self.breakdown_item_combo.itemData(i)) and item_data.get('id') == item_id:
                self.breakdown_item_combo.setCurrentIndex(i);
                break
        QMessageBox.information(self, "Loaded for Update",
                                f"RRF Item {item_id} from RRF {rrf_no} is loaded.\n\n"
                                "You can now adjust parameters and click 'Save Breakdown' to overwrite.")

    def _delete_selected_breakdown(self):
        selected = self.breakdown_records_table.selectionModel().selectedRows();
        if not selected: return
        row_index = selected[0].row()
        rrf_no = self.breakdown_records_table.item(row_index, 0).text()
        item_id = self.breakdown_records_table.item(row_index, 1).text()
        reply = QMessageBox.question(self, "Confirm Deletion",
                                     f"Are you sure you want to permanently delete the lot breakdown for Item ID <b>{item_id}</b> on RRF No: <b>{rrf_no}</b>?<br><br>This action cannot be undone.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        if reply != QMessageBox.StandardButton.Yes: return
        try:
            with self.engine.connect() as conn, conn.begin():
                conn.execute(
                    text("DELETE FROM rrf_lot_breakdown WHERE rrf_no = :rrf_no AND item_id = :item_id"),
                    {"rrf_no": rrf_no, "item_id": int(item_id)}
                )
            self.log_audit_trail("DELETE_RRF_BREAKDOWN", f"Deleted breakdown for RRF {rrf_no}, Item {item_id}")
            QMessageBox.information(self, "Success", "The selected lot breakdown has been deleted.")
            self._load_all_breakdown_records()
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Could not delete the breakdown record: {e}")

    def _setup_view_details_tab(self, tab):
        main_splitter = QSplitter(Qt.Orientation.Vertical);
        main_layout = QVBoxLayout(tab);
        main_layout.addWidget(main_splitter)
        details_group = QGroupBox("RRF Details (Read-Only)");
        details_container_layout = QHBoxLayout(details_group)
        self.view_left_details_layout, self.view_right_details_layout = QFormLayout(), QFormLayout()
        details_container_layout.addLayout(self.view_left_details_layout);
        details_container_layout.addLayout(self.view_right_details_layout)
        main_splitter.addWidget(details_group)
        bottom_splitter = QSplitter(Qt.Orientation.Horizontal)
        items_group = QGroupBox("Items");
        items_layout = QVBoxLayout(items_group)
        self.view_items_table = QTableWidget();
        self.view_items_table.setShowGrid(False);
        self.view_items_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.view_items_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);
        self.view_items_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.view_items_table.verticalHeader().setVisible(False);
        self.view_items_table.horizontalHeader().setHighlightSections(False)
        self.view_items_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        items_layout.addWidget(self.view_items_table)
        self.view_items_total_label = QLabel("<b>Total Quantity: 0.00</b>");
        self.view_items_total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        items_layout.addWidget(self.view_items_total_label)
        bottom_splitter.addWidget(items_group)
        breakdown_group = QGroupBox("Lot Breakdown");
        breakdown_layout = QVBoxLayout(breakdown_group)
        self.view_breakdown_table = QTableWidget();
        self.view_breakdown_table.setShowGrid(False);
        self.view_breakdown_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.view_breakdown_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);
        self.view_breakdown_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.view_breakdown_table.verticalHeader().setVisible(False);
        self.view_breakdown_table.horizontalHeader().setHighlightSections(False)
        self.view_breakdown_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        breakdown_layout.addWidget(self.view_breakdown_table)
        self.view_breakdown_total_label = QLabel("<b>Total Quantity: 0.00</b>");
        self.view_breakdown_total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        breakdown_layout.addWidget(self.view_breakdown_total_label)
        bottom_splitter.addWidget(breakdown_group)
        main_splitter.addWidget(bottom_splitter);
        main_splitter.setSizes([150, 400])

    def _on_record_selection_changed(self):
        is_selected = bool(self.records_table.selectionModel().selectedRows())
        self.update_btn.setEnabled(is_selected)
        self.delete_btn.setEnabled(is_selected)
        self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.view_details_tab), is_selected)
        if is_selected:
            self._show_selected_record_in_view_tab()
        elif self.tab_widget.currentIndex() == self.tab_widget.indexOf(self.view_details_tab):
            self.tab_widget.setCurrentIndex(0)

    def _show_selected_record_in_view_tab(self):
        selected = self.records_table.selectionModel().selectedRows();
        if not selected: return
        rrf_no = self.records_table.item(selected[0].row(), 0).text()
        try:
            with self.engine.connect() as conn:
                primary = conn.execute(text("SELECT * FROM rrf_primary WHERE rrf_no = :rrf_no"),
                                       {"rrf_no": rrf_no}).mappings().one()
                items = conn.execute(text(
                    "SELECT id, quantity, unit, product_code, lot_number, reference_number, remarks FROM rrf_items WHERE rrf_no = :rrf_no ORDER BY id"),
                                     {"rrf_no": rrf_no}).mappings().all()
                breakdown = conn.execute(text(
                    "SELECT item_id, lot_number, quantity_kg FROM rrf_lot_breakdown WHERE rrf_no = :rrf_no ORDER BY item_id, id"),
                                         {"rrf_no": rrf_no}).mappings().all()
            for layout in [self.view_left_details_layout, self.view_right_details_layout]:
                while layout.count():
                    child = layout.takeAt(0)
                    if child and child.widget(): child.widget().deleteLater()
            items_list = list(primary.items());
            midpoint = (len(items_list) + 1) // 2
            for k, v in items_list[:midpoint]: self._add_view_detail_row(self.view_left_details_layout, k, v)
            for k, v in items_list[midpoint:]: self._add_view_detail_row(self.view_right_details_layout, k, v)
            item_headers = ["ID", "Qty", "Unit", "Product Code", "Lot No.", "Ref No.", "Remarks"]
            self._populate_table_generic(self.view_items_table, items, item_headers)
            breakdown_headers = ["Orig. Item ID", "Lot Number", "Quantity (kg)"]
            self._populate_table_generic(self.view_breakdown_table, breakdown, breakdown_headers)
            total_items_qty = sum(Decimal(item.get('quantity', 0)) for item in items)
            self.view_items_total_label.setText(f"<b>Total Quantity: {total_items_qty:.2f}</b>")
            total_breakdown_qty = sum(Decimal(item.get('quantity_kg', 0)) for item in breakdown)
            self.view_breakdown_total_label.setText(f"<b>Total Quantity: {total_breakdown_qty:.2f}</b>")
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load details for RRF {rrf_no}: {e}")

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
        is_selected = bool(self.items_table.selectionModel().selectedRows())
        self.edit_item_btn.setEnabled(is_selected);
        self.remove_item_btn.setEnabled(is_selected)

    def _update_item_count(self):
        self.item_count_label.setText(f"Items: {self.items_table.rowCount()} / {self.MAX_ITEMS}")

    def _add_item_row(self):
        if self.items_table.rowCount() >= self.MAX_ITEMS:
            QMessageBox.warning(self, "Limit Reached", f"You can add a maximum of {self.MAX_ITEMS} items.");
            return

        material_type = self.material_type_combo.currentText()
        dialog = RRFItemEntryDialog(self.engine, material_type=material_type, parent=self)

        if dialog.exec():
            row = self.items_table.rowCount()
            self.items_table.insertRow(row);
            self._populate_item_row(row, dialog.get_item_data());
            self._update_item_count()

    def _edit_item_row(self):
        selected = self.items_table.selectionModel().selectedRows();
        if not selected: return

        material_type = self.material_type_combo.currentText()
        dialog = RRFItemEntryDialog(self.engine, material_type=material_type,
                                    item_data=self._get_item_data_from_row(selected[0].row()), parent=self)

        if dialog.exec(): self._populate_item_row(selected[0].row(), dialog.get_item_data())

    def _remove_item_row(self):
        selected = self.items_table.selectionModel().selectedRows()
        if selected and QMessageBox.question(self, "Confirm Remove",
                                             "Are you sure you want to remove this item?") == QMessageBox.StandardButton.Yes:
            self.items_table.removeRow(selected[0].row());
            self._update_item_count()

    def _populate_item_row(self, row, item_data):
        headers = ["quantity", "unit", "product_code", "lot_number", "reference_number", "remarks"]
        for col, header in enumerate(headers):
            self.items_table.setItem(row, col, QTableWidgetItem(str(item_data.get(header, ''))))

    def _get_item_data_from_row(self, row):
        headers = ["quantity", "unit", "product_code", "lot_number", "reference_number", "remarks"]
        return {h: self.items_table.item(row, i).text() if self.items_table.item(row, i) else "" for i, h in
                enumerate(headers)}

    def _clear_form(self):
        self.current_editing_rrf_no = None
        self.rrf_no_edit.setText(self._generate_rrf_no())
        self.rrf_date_edit.setDate(QDate.currentDate())
        self.customer_combo.setCurrentIndex(-1)
        self.items_table.setRowCount(0)
        self._load_combobox_data()
        self.save_btn.setText("Save")
        self.print_btn.setEnabled(False)
        self._update_item_count()
        self._on_item_selection_changed()

    def _load_combobox_data(self):
        try:
            with self.engine.connect() as conn:
                customers = conn.execute(
                    text("SELECT name FROM customers WHERE is_deleted IS NOT TRUE ORDER BY name")).scalars().all()
            current = self.customer_combo.currentText()
            self.customer_combo.clear();
            self.customer_combo.addItems([""] + customers)
            if current in customers: self.customer_combo.setCurrentText(current)
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load customer data: {e}")

    def _save_record(self):
        if not self.customer_combo.currentText() or self.items_table.rowCount() == 0:
            QMessageBox.warning(self, "Input Error", "Customer/Supplier and at least one item are required.");
            return
        rrf_no = self.current_editing_rrf_no or self._generate_rrf_no()
        primary_data = {"rrf_no": rrf_no, "rrf_date": self.rrf_date_edit.date().toPyDate(),
                        "customer_name": self.customer_combo.currentText(),
                        "material_type": self.material_type_combo.currentText(), "prepared_by": self.username,
                        "encoded_by": self.username,
                        "encoded_on": datetime.now(), "edited_by": self.username, "edited_on": datetime.now()}
        items_data = [self._get_item_data_from_row(row) for row in range(self.items_table.rowCount())]
        for item in items_data: item['rrf_no'] = rrf_no
        try:
            with self.engine.connect() as conn, conn.begin():
                if self.current_editing_rrf_no:
                    del primary_data['encoded_by'], primary_data['encoded_on']
                    conn.execute(text(
                        "UPDATE rrf_primary SET rrf_date=:rrf_date, customer_name=:customer_name, material_type=:material_type, prepared_by=:prepared_by, edited_by=:edited_by, edited_on=:edited_on WHERE rrf_no=:rrf_no"),
                                 primary_data)
                    conn.execute(text("DELETE FROM rrf_items WHERE rrf_no = :rrf_no"), {"rrf_no": rrf_no})
                    log, action = "UPDATE_RRF", "updated"
                else:
                    conn.execute(text(
                        "INSERT INTO rrf_primary (rrf_no, rrf_date, customer_name, material_type, prepared_by, encoded_by, encoded_on, edited_by, edited_on) VALUES (:rrf_no, :rrf_date, :customer_name, :material_type, :prepared_by, :encoded_by, :encoded_on, :edited_by, :edited_on)"),
                                 primary_data)
                    log, action = "CREATE_RRF", "saved"

                if items_data:
                    conn.execute(text(
                        "INSERT INTO rrf_items (rrf_no, quantity, unit, product_code, lot_number, reference_number, remarks) VALUES (:rrf_no, :quantity, :unit, :product_code, :lot_number, :reference_number, :remarks)"),
                                 items_data)

                new_units = {item['unit'] for item in items_data if item['unit']}
                if new_units:
                    insert_stmt = text("INSERT INTO units (name) VALUES (:name) ON CONFLICT(name) DO NOTHING")
                    conn.execute(insert_stmt, [{"name": unit} for unit in new_units])

                self.log_audit_trail(log, f"RRF: {rrf_no}")

            QMessageBox.information(self, "Success", f"RRF {rrf_no} has been {action}.")
            self._clear_form();
            self._refresh_all_data_views()
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"An error occurred: {e}")

    def _load_record_for_update(self):
        selected = self.records_table.selectionModel().selectedRows();
        if not selected: return
        self._load_record(self.records_table.item(selected[0].row(), 0).text())

    def _load_record(self, rrf_no):
        try:
            with self.engine.connect() as conn:
                primary = conn.execute(text("SELECT * FROM rrf_primary WHERE rrf_no = :rrf_no"),
                                       {"rrf_no": rrf_no}).mappings().one()
                items = conn.execute(text("SELECT * FROM rrf_items WHERE rrf_no = :rrf_no ORDER BY id"),
                                     {"rrf_no": rrf_no}).mappings().all()
            self._clear_form()
            self.current_editing_rrf_no = rrf_no
            self.rrf_no_edit.setText(primary.get('rrf_no'))
            self.rrf_date_edit.setDate(primary.get('rrf_date', QDate.currentDate()))
            self.customer_combo.setCurrentText(primary.get('customer_name', ''))

            self.material_type_combo.blockSignals(True)
            self.material_type_combo.setCurrentText(primary.get('material_type', ''))
            self.previous_material_type_index = self.material_type_combo.currentIndex()
            self.material_type_combo.blockSignals(False)

            self.prepared_by_label.setText(primary.get('prepared_by', self.username).upper())
            self.items_table.setRowCount(0)
            for item_data in items:
                row = self.items_table.rowCount();
                self.items_table.insertRow(row);
                self._populate_item_row(row, item_data)
            self._update_item_count()
            self.save_btn.setText("Update");
            self.print_btn.setEnabled(True)
            self.tab_widget.setCurrentIndex(self.tab_widget.indexOf(self.entry_tab))
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load RRF {rrf_no}: {e}")

    def _delete_record(self):
        selected = self.records_table.selectionModel().selectedRows();
        if not selected: return
        rrf_no = self.records_table.item(selected[0].row(), 0).text()
        if QMessageBox.question(self, "Confirm Deletion",
                                f"Delete RRF No: <b>{rrf_no}</b> and move it to the deleted tab?") == QMessageBox.StandardButton.Yes:
            try:
                with self.engine.connect() as conn, conn.begin():
                    conn.execute(text(
                        "UPDATE rrf_primary SET is_deleted = TRUE, edited_by = :u, edited_on = :n WHERE rrf_no = :rrf"),
                                 {"u": self.username, "n": datetime.now(), "rrf": rrf_no})
                self.log_audit_trail("DELETE_RRF", f"Soft-deleted RRF: {rrf_no}")
                QMessageBox.information(self, "Success", f"RRF {rrf_no} deleted.")
                self._refresh_all_data_views()
            except Exception as e:
                QMessageBox.critical(self, "Database Error", f"Could not delete record: {e}")

    def _load_all_records(self):
        search = f"%{self.search_edit.text()}%";
        offset = (self.current_page - 1) * self.records_per_page
        try:
            with self.engine.connect() as conn:
                count_query_base = "FROM rrf_primary p LEFT JOIN rrf_items i ON p.rrf_no = i.rrf_no WHERE p.is_deleted IS NOT TRUE"
                filter_clause = "";
                params = {'limit': self.records_per_page, 'offset': offset}
                if self.search_edit.text():
                    filter_clause = " AND (p.rrf_no ILIKE :st OR p.customer_name ILIKE :st OR i.product_code ILIKE :st)"
                    params['st'] = search
                count_res = conn.execute(text(f"SELECT COUNT(DISTINCT p.id) {count_query_base} {filter_clause}"),
                                         {'st': search} if self.search_edit.text() else {}).scalar_one()
                self.total_records = count_res
                query = text(f"""
                    SELECT p.rrf_no, p.rrf_date, p.customer_name, p.material_type,
                           STRING_AGG(DISTINCT i.product_code, ', ') as product_codes, SUM(i.quantity) as total_quantity
                    FROM rrf_primary p LEFT JOIN rrf_items i ON p.rrf_no = i.rrf_no
                    WHERE p.is_deleted IS NOT TRUE {filter_clause}
                    GROUP BY p.id, p.rrf_no, p.rrf_date, p.customer_name, p.material_type
                    ORDER BY p.id DESC LIMIT :limit OFFSET :offset
                """)
                res = conn.execute(query, params).mappings().all()
            headers = ["RRF No.", "Date", "Customer/Supplier", "Material Type", "Product Codes", "Total Quantity"]
            self._populate_records_table(self.records_table, res, headers)
            self._update_pagination_controls();
            self._on_record_selection_changed()
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load records: {e}")

    def _populate_records_table(self, table, data, headers):
        table.setRowCount(0);
        table.setColumnCount(len(headers));
        table.setHorizontalHeaderLabels(headers)
        if not data: table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch); return
        table.setRowCount(len(data))
        keys = ["rrf_no", "rrf_date", "customer_name", "material_type", "product_codes", "total_quantity"]
        for i, row in enumerate(data):
            for j, key in enumerate(keys):
                value = row.get(key)
                if key == 'total_quantity' and value is not None:
                    display_value = f"{float(value):.2f}"
                elif isinstance(value, date):
                    display_value = QDate(value).toString('yyyy-MM-dd')
                else:
                    display_value = str(value or "")
                item = QTableWidgetItem(display_value)
                if key == 'total_quantity': item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(i, j, item)
        table.resizeColumnsToContents()
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)

    def _generate_rrf_no(self):
        with self.engine.connect() as conn:
            start_num_query = text("SELECT setting_value FROM app_settings WHERE setting_key = 'RRF_SEQUENCE_START'")
            start_num_str = conn.execute(start_num_query).scalar_one_or_none()
            try:
                start_number = int(start_num_str) if start_num_str else 1
            except (ValueError, TypeError):
                start_number = 1

            last_num_query = text("""
                SELECT MAX(CAST(rrf_no AS INTEGER)) 
                FROM rrf_primary 
                WHERE rrf_no ~ '^[0-9]+$' AND LENGTH(rrf_no) = 5
            """)
            last_num = conn.execute(last_num_query).scalar_one_or_none()

        base_number = max((last_num or 0), start_number - 1)
        next_seq = base_number + 1
        return f"{next_seq:05d}"

    def _show_records_table_context_menu(self, pos):
        if not self.records_table.selectedItems(): return
        menu = QMenu();
        view_action = menu.addAction("View Details");
        print_action = menu.addAction("Print Preview")
        menu.addSeparator();
        edit_action = menu.addAction("Edit Record");
        delete_action = menu.addAction("Delete Record")
        action = menu.exec(self.records_table.mapToGlobal(pos))
        if action == view_action:
            self.tab_widget.setCurrentIndex(self.tab_widget.indexOf(self.view_details_tab))
        elif action == edit_action:
            self._load_record_for_update()
        elif action == delete_action:
            self._delete_record()
        elif action == print_action:
            self._trigger_print_preview(self.records_table.item(self.records_table.currentRow(), 0).text())

    # --- DELETED TAB METHODS ---
    def _load_deleted_records(self):
        search = f"%{self.deleted_search_edit.text()}%"
        try:
            with self.engine.connect() as conn:
                query = text("""
                    SELECT rrf_no, rrf_date, customer_name, material_type, edited_by, edited_on
                    FROM rrf_primary WHERE is_deleted = TRUE
                    AND (rrf_no ILIKE :st OR customer_name ILIKE :st)
                    ORDER BY edited_on DESC
                """)
                res = conn.execute(query, {'st': search}).mappings().all()
            headers = ["RRF No.", "Date", "Customer/Supplier", "Deleted By", "Deleted On"]
            self._populate_deleted_records_table(res, headers)
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load deleted records: {e}")

    def _populate_deleted_records_table(self, data, headers):
        table = self.deleted_records_table
        table.setRowCount(0);
        table.setColumnCount(len(headers));
        table.setHorizontalHeaderLabels(headers)
        if not data: table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch); return
        table.setRowCount(len(data))
        keys = ["rrf_no", "rrf_date", "customer_name", "edited_by", "edited_on"]
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
        table.resizeColumnsToContents()
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

    def _show_deleted_records_context_menu(self, pos):
        if not self.deleted_records_table.selectedItems(): return
        menu = QMenu();
        restore_action = menu.addAction("Restore Record")
        action = menu.exec(self.deleted_records_table.mapToGlobal(pos))
        if action == restore_action: self._restore_record()

    def _restore_record(self):
        selected = self.deleted_records_table.selectionModel().selectedRows()
        if not selected: return
        rrf_no = self.deleted_records_table.item(selected[0].row(), 0).text()
        password, ok = QInputDialog.getText(self, "Admin Action", "Enter password to restore:",
                                            QLineEdit.EchoMode.Password)
        if not ok: return
        if password != "Itadmin":
            QMessageBox.critical(self, "Access Denied", "Incorrect password.");
            return
        if QMessageBox.question(self, "Confirm Restore",
                                f"Restore RRF No: <b>{rrf_no}</b>?") == QMessageBox.StandardButton.Yes:
            try:
                with self.engine.connect() as conn, conn.begin():
                    conn.execute(text(
                        "UPDATE rrf_primary SET is_deleted = FALSE, edited_by = :u, edited_on = :n WHERE rrf_no = :rrf"),
                                 {"u": self.username, "n": datetime.now(), "rrf": rrf_no})
                self.log_audit_trail("RESTORE_RRF", f"Restored RRF: {rrf_no}")
                QMessageBox.information(self, "Success", f"RRF {rrf_no} has been restored.")
                self._refresh_all_data_views()
            except Exception as e:
                QMessageBox.critical(self, "Database Error", f"Could not restore record: {e}")

    def _refresh_all_data_views(self):
        self._load_all_records()
        self._load_deleted_records()
        self._load_all_breakdown_records()

    # --- LOT BREAKDOWN TOOL METHODS ---
    def _clear_breakdown_tool(self):
        self.breakdown_rrf_combo.blockSignals(True);
        self.breakdown_item_combo.blockSignals(True)
        self.breakdown_rrf_combo.setCurrentIndex(0);
        self.breakdown_item_combo.clear()
        self.breakdown_item_combo.addItem("-- Select RRF First --", userData=None)
        self.breakdown_rrf_combo.blockSignals(False);
        self.breakdown_item_combo.blockSignals(False)
        self.breakdown_item_qty_display.setText("0.00");
        self.breakdown_num_lots_edit.setText("0")
        self.breakdown_weight_per_lot_edit.setText("0.00");
        self.breakdown_lot_range_edit.clear()
        self.breakdown_is_range_check.setChecked(False);
        self.breakdown_preview_table.setRowCount(0)
        self.breakdown_total_label.setText("<b>Total: 0.00 kg</b>");
        self.breakdown_preview_data = None

    def _load_rrf_numbers_for_breakdown(self):
        try:
            with self.engine.connect() as conn:
                query = text("SELECT rrf_no FROM rrf_primary WHERE is_deleted IS NOT TRUE ORDER BY id DESC LIMIT 200")
                rrf_numbers = conn.execute(query).scalars().all()
            self.breakdown_rrf_combo.blockSignals(True)
            self.breakdown_rrf_combo.clear();
            self.breakdown_rrf_combo.addItems(["-- Select an RRF --"] + rrf_numbers)
            self.breakdown_rrf_combo.blockSignals(False);
            self._on_breakdown_rrf_selected()
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load RRF numbers for breakdown tool: {e}")

    def _on_breakdown_rrf_selected(self):
        self.breakdown_item_combo.blockSignals(True);
        self.breakdown_item_combo.clear()
        rrf_no = self.breakdown_rrf_combo.currentText()
        if not rrf_no or self.breakdown_rrf_combo.currentIndex() == 0:
            self.breakdown_item_combo.addItem("-- Select RRF First --", userData=None)
            self.breakdown_item_combo.blockSignals(False);
            self._on_breakdown_item_selected();
            return
        try:
            with self.engine.connect() as conn:
                items = conn.execute(text(
                    "SELECT rrf_no, id, quantity, unit, product_code FROM rrf_items WHERE rrf_no = :rrf_no ORDER BY id"),
                                     {"rrf_no": rrf_no}).mappings().all()
            self.breakdown_item_combo.addItem("-- Select an Item --", userData=None)
            for item in items:
                quantity = item.get('quantity')
                display_qty = f"{float(quantity):.2f}" if quantity is not None else "0.00"
                self.breakdown_item_combo.addItem(
                    f"ID: {item['id']} - {display_qty} {item['unit']} - {item['product_code']}", userData=item)
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load items for RRF {rrf_no}: {e}")
        finally:
            self.breakdown_item_combo.blockSignals(False);
            self._on_breakdown_item_selected()

    def _on_breakdown_item_selected(self):
        item_data = self.breakdown_item_combo.currentData()
        quantity = Decimal(item_data.get('quantity', 0.0)) if item_data else Decimal("0.0")
        self.breakdown_item_qty_display.setText(f"{quantity:.2f}");
        self._recalculate_num_lots()

    def _recalculate_num_lots(self):
        try:
            target_qty = Decimal(self.breakdown_item_qty_display.text())
            weight_per_lot = Decimal(self.breakdown_weight_per_lot_edit.text())
            if target_qty <= 0 or weight_per_lot <= 0:
                self.breakdown_num_lots_edit.setText("0");
                return
            num_lots = math.ceil(target_qty / weight_per_lot)
            self.breakdown_num_lots_edit.setText(str(num_lots))
        except (ValueError, InvalidOperation):
            self.breakdown_num_lots_edit.setText("0")

    def _validate_and_calculate_breakdown(self):
        try:
            item_data = self.breakdown_item_combo.currentData()
            target_qty = Decimal(self.breakdown_item_qty_display.text())
            weight_per_lot = Decimal(self.breakdown_weight_per_lot_edit.text())
            lot_input = self.breakdown_lot_range_edit.text().strip()
            num_lots = int(self.breakdown_num_lots_edit.text())
            if not item_data: QMessageBox.warning(self, "Input Error",
                                                  "Please select an RRF item to break down."); return None
            if target_qty <= 0 or weight_per_lot <= 0 or num_lots <= 0: QMessageBox.warning(self, "Input Error",
                                                                                            "Target quantity, weight per lot, and calculated lots must all be greater than zero."); return None
            if not lot_input: QMessageBox.warning(self, "Input Error",
                                                  "Please provide a Lot Start/Range value."); return None
        except (ValueError, InvalidOperation):
            QMessageBox.warning(self, "Input Error", "Please enter valid numbers for lots and weight.");
            return None
        lot_list = []
        if self.breakdown_is_range_check.isChecked():
            parsed_list = self._parse_lot_range(lot_input)
            if parsed_list is None: return None
            if len(parsed_list) != num_lots:
                QMessageBox.warning(self, "Mismatch Error",
                                    f"The number of lots in your range ({len(parsed_list)}) does not match the 'Calculated No. of Lots' ({num_lots}).");
                return None
            lot_list = parsed_list
        else:
            pattern = r'^\d+[A-Z]*$';
            if not re.match(pattern, lot_input.upper()):
                QMessageBox.warning(self, "Input Error",
                                    f"Invalid format for a single starting lot: '{lot_input}'. Expected '1234' or '1234AA'.");
                return None
            start_match = re.match(r'^(\d+)([A-Z]*)$', lot_input.upper())
            if start_match:
                start_num, suffix, num_len = int(start_match.group(1)), start_match.group(2), len(start_match.group(1))
                lot_list = [f"{str(start_num + i).zfill(num_len)}{suffix}" for i in range(num_lots)]
            else:
                return None
        num_full_lots = int(target_qty // weight_per_lot);
        remainder_qty = target_qty % weight_per_lot
        breakdown_items = []
        for i in range(num_full_lots): breakdown_items.append(
            {'lot_number': lot_list[i], 'quantity_kg': weight_per_lot})
        if remainder_qty > 0: breakdown_items.append(
            {'lot_number': lot_list[num_full_lots], 'quantity_kg': remainder_qty})
        return {'items': breakdown_items, 'rrf_no': item_data['rrf_no'], 'item_id': item_data['id']}

    def _parse_lot_range(self, lot_input):
        try:
            parts = [s.strip().upper() for s in lot_input.split('-')]
            if len(parts) != 2: raise ValueError("Lot range must contain exactly one hyphen.")
            start_str, end_str = parts;
            start_match = re.match(r'^(\d+)([A-Z]*)$', start_str);
            end_match = re.match(r'^(\d+)([A-Z]*)$', end_str)
            if not start_match or not end_match or start_match.group(2) != end_match.group(2): raise ValueError(
                "Format invalid or suffixes mismatch. Expected: '100A-105A'.")
            start_num, end_num, suffix, num_len = int(start_match.group(1)), int(end_match.group(1)), start_match.group(
                2), len(start_match.group(1))
            if start_num > end_num: raise ValueError("Start lot cannot be greater than end lot.")
            return [f"{str(start_num + i).zfill(num_len)}{suffix}" for i in range(end_num - start_num + 1)]
        except Exception as e:
            QMessageBox.critical(self, "Lot Range Error", f"Could not parse lot range '{lot_input}': {e}");
            return None

    def _preview_lot_breakdown(self):
        self.breakdown_preview_data = None;
        self.breakdown_preview_table.setRowCount(0)
        self.breakdown_total_label.setText("<b>Total: 0.00 kg</b>")
        preview_data = self._validate_and_calculate_breakdown()
        if not preview_data: return
        self.breakdown_preview_data = preview_data
        items_to_display = preview_data['items']
        self._populate_preview_table(self.breakdown_preview_table, items_to_display, ["Lot Number", "Quantity (kg)"])
        total_preview_qty = sum(item['quantity_kg'] for item in items_to_display)
        self.breakdown_total_label.setText(f"<b>Total: {float(total_preview_qty):.2f} kg</b>")

    def _save_lot_breakdown(self):
        if not self.breakdown_preview_data: QMessageBox.warning(self, "No Preview Data",
                                                                "Please generate a preview before saving."); return
        data = self.breakdown_preview_data;
        rrf_no, item_id = data['rrf_no'], data['item_id']
        reply = QMessageBox.question(self, "Confirm Save",
                                     f"This will <b>delete any existing breakdown</b> for Item ID {item_id} on RRF {rrf_no} and save this new one. Proceed?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        if reply == QMessageBox.StandardButton.Cancel: return
        records_to_insert = [{'rrf_no': rrf_no, 'item_id': item_id, **item} for item in data['items']]
        try:
            with self.engine.connect() as conn, conn.begin():
                conn.execute(text("DELETE FROM rrf_lot_breakdown WHERE rrf_no = :rrf_no AND item_id = :item_id"),
                             {"rrf_no": rrf_no, "item_id": item_id})
                if records_to_insert:
                    conn.execute(text(
                        "INSERT INTO rrf_lot_breakdown (rrf_no, item_id, lot_number, quantity_kg) VALUES (:rrf_no, :item_id, :lot_number, :quantity_kg)"),
                                 records_to_insert)
            self.log_audit_trail("CREATE_RRF_BREAKDOWN", f"Saved breakdown for RRF: {rrf_no}, Item: {item_id}")
            QMessageBox.information(self, "Success", f"Lot breakdown for RRF {rrf_no}, Item {item_id} saved.")
            self._clear_breakdown_tool();
            self._load_all_breakdown_records()
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Could not save breakdown: {e}")

    def _populate_preview_table(self, table_widget, data, headers):
        table_widget.setRowCount(0);
        table_widget.setColumnCount(len(headers));
        table_widget.setHorizontalHeaderLabels(headers)
        if not data: table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch); return
        table_widget.setRowCount(len(data));
        keys = list(data[0].keys())
        for i, row_data in enumerate(data):
            for j, key in enumerate(keys):
                val = row_data.get(key)
                item = QTableWidgetItem(f"{val:.2f}" if isinstance(val, (Decimal, float)) else str(val or ""))
                if isinstance(val, (Decimal, float)): item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table_widget.setItem(i, j, item)
        table_widget.resizeColumnsToContents()
        table_widget.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

    # --- PDF GENERATION AND PRINTING ---
    def _trigger_print_preview_from_form(self):
        if not self.rrf_no_edit.text(): QMessageBox.warning(self, "No Record Loaded",
                                                            "Please load a record to print."); return
        self._trigger_print_preview(self.rrf_no_edit.text())

    def _trigger_print_preview(self, rrf_no):
        try:
            with self.engine.connect() as conn:
                primary = conn.execute(text("SELECT * FROM rrf_primary WHERE rrf_no = :rrf_no"),
                                       {"rrf_no": rrf_no}).mappings().one()
                items_data = conn.execute(text("SELECT * FROM rrf_items WHERE rrf_no = :rrf_no ORDER BY id"),
                                          {"rrf_no": rrf_no}).mappings().all()
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not fetch RRF {rrf_no} for printing: {e}");
            return
        primary_data = {"rrf_no": primary.get('rrf_no'),
                        "rrf_date": QDate(primary.get('rrf_date')).toString("MM/dd/yy"),
                        "customer_name": primary.get('customer_name'),
                        "material_type": primary.get('material_type'), "prepared_by": primary.get('prepared_by')}
        try:
            self.current_pdf_buffer = self._generate_rrf_pdf(primary_data, items_data)
            if self.current_pdf_buffer is None: return
        except Exception as e:
            QMessageBox.critical(self, "PDF Generation Error", f"Could not generate PDF: {e}");
            return
        custom_size = QSizeF(8.5, 5.5);
        custom_page_size = QPageSize(custom_size, QPageSize.Unit.Inch, "RRF Form")
        self.printer.setPageSize(custom_page_size);
        self.printer.setFullPage(True)
        preview = QPrintPreviewDialog(self.printer, self)
        preview.paintRequested.connect(self._handle_paint_request)
        preview.resize(1000, 800);
        preview.exec()

    def _draw_page_template(self, canvas, doc, header_table, footer_table):
        canvas.saveState();
        page_width, page_height = doc.pagesize
        header_table.wrapOn(canvas, doc.width, doc.topMargin);
        header_table.drawOn(canvas, doc.leftMargin, page_height - header_table._height - (0.2 * inch))
        footer_table.wrapOn(canvas, doc.width, doc.bottomMargin);
        footer_table.drawOn(canvas, doc.leftMargin, 0.2 * inch)
        canvas.restoreState()

    def _generate_rrf_pdf(self, primary_data, items_data):
        try:
            pdfmetrics.registerFont(TTFont('LucidaSans', 'C:/Windows/Fonts/LSANS.TTF'));
            pdfmetrics.registerFont(TTFont('LucidaSans-Bold', 'C:/Windows/Fonts/LTYPEB.TTF'))
            pdfmetrics.registerFontFamily('LucidaSans', normal='LucidaSans', bold='LucidaSans-Bold')
        except Exception:
            try:
                pdfmetrics.registerFont(TTFont('Arial', 'arial.ttf'));
                pdfmetrics.registerFont(TTFont('Arial-Bold', 'arialbd.ttf'))
                pdfmetrics.registerFontFamily('LucidaSans', normal='Arial', bold='Arial-Bold')
            except Exception as e:
                QMessageBox.critical(self, "Font Error",
                                     f"Could not register fallback font 'Arial'. Ensure it is installed.\nError: {e}");
                return None
        buffer = io.BytesIO();
        page_width, page_height = (8.5 * inch, 5.5 * inch)
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name='MainStyle', fontName='LucidaSans', fontSize=10, leading=11))
        styles.add(ParagraphStyle(name='MainStyleBold', parent=styles['MainStyle'], fontName='LucidaSans-Bold'))
        styles.add(ParagraphStyle(name='MainStyleRight', parent=styles['MainStyleBold'], alignment=TA_RIGHT))
        styles.add(ParagraphStyle(name='MainStyleCenter', parent=styles['MainStyleBold'], alignment=TA_CENTER))
        styles.add(ParagraphStyle(name='Footer', fontName='LucidaSans-Bold', fontSize=9, leading=10))
        styles.add(ParagraphStyle(name='FooterSig', fontName='LucidaSans', fontSize=8, alignment=TA_CENTER))
        styles.add(ParagraphStyle(name='FooterSub', fontName='LucidaSans', fontSize=8, alignment=TA_CENTER))
        styles.add(ParagraphStyle(name='RemarkStyle', fontName='LucidaSans', fontSize=9, leading=9, leftIndent=10))
        header_left_text = """<font name='LucidaSans-Bold' size='14'>MASTERBATCH PHILIPPINES INC.</font><br/><font size='9'>24 Diamond Road, Caloocan Industrial Subd., Bo. Kaybiga Caloocan City</font><br/><font size='9'>Tel. Nos.: 8935-93-75 | 8935-9376 | 7738-1207</font>"""
        header_right_text = f"""<font name='LucidaSans-Bold' size='14'>RETURN/REPLACEMENT FORM</font><br/><br/><font name='LucidaSans-Bold' size='14'>RRF No.: {primary_data['rrf_no']}</font>"""
        header_table = Table([[Paragraph(header_left_text, styles['MainStyle']),
                               Paragraph(header_right_text, styles['MainStyleRight'])]],
                             colWidths=[4.5 * inch, 3.1 * inch], style=[('VALIGN', (0, 0), (-1, -1), 'TOP')])
        signature_line = "_" * 28
        footer_data = [[Paragraph("Prepared by:", styles['Footer']), Paragraph("Checked by:", styles['Footer']),
                        Paragraph("Approved by:", styles['Footer']), Paragraph("Received by:", styles['Footer'])],
                       [Paragraph(f"<br/>{primary_data.get('prepared_by', '').upper()}", styles['FooterSig']),
                        Paragraph("<br/>", styles['FooterSig']), Paragraph("<br/>", styles['FooterSig']),
                        Paragraph("<br/>", styles['FooterSig'])],
                       [Paragraph(signature_line, styles['FooterSig']), Paragraph(signature_line, styles['FooterSig']),
                        Paragraph(signature_line, styles['FooterSig']), Paragraph(signature_line, styles['FooterSig'])],
                       [Paragraph("Signature Over Printed Name", styles['FooterSub']),
                        Paragraph("Signature Over Printed Name", styles['FooterSub']),
                        Paragraph("Signature Over Printed Name", styles['FooterSub']),
                        Paragraph("Signature Over Printed Name", styles['FooterSub'])]]
        footer_table = Table(footer_data, colWidths=[1.9 * inch] * 4,
                             rowHeights=[0.15 * inch, 0.25 * inch, 0.05 * inch, 0.15 * inch])
        footer_table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'BOTTOM'), ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                                          ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
        _, header_height = header_table.wrap(page_width, page_height);
        _, footer_height = footer_table.wrap(page_width, page_height)
        doc = SimpleDocTemplate(buffer, pagesize=(page_width, page_height), leftMargin=0.3 * inch,
                                rightMargin=0.3 * inch, topMargin=header_height + 0.3 * inch,
                                bottomMargin=footer_height + 0.2 * inch)
        page_template_drawer = partial(self._draw_page_template, header_table=header_table, footer_table=footer_table)
        Story = []
        details_data = [[Paragraph(f"<b>Supplier / Customer:</b> {primary_data['customer_name']}", styles['MainStyle']),
                         Paragraph(f"<b>Date:</b> {primary_data['rrf_date']}", styles['MainStyle'])],
                        [Paragraph(f"<b>Material Type:</b> {primary_data['material_type']}", styles['MainStyle']), ""]]
        details_table = Table(details_data, colWidths=[5.4 * inch, 2.5 * inch], rowHeights=[0.25 * inch, 0.25 * inch])
        details_table.setStyle(TableStyle(
            [('GRID', (0, 0), (-1, -1), 0.5, colors.black), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
             ('LEFTPADDING', (0, 0), (-1, -1), 5), ('SPAN', (1, 0), (1, 1))]));
        Story.append(details_table)
        MAX_PDF_ROWS = 10;
        H_ROW = 0.25 * inch;
        D_ROW = 0.22 * inch
        items_tbl_data, row_heights, styles_dyn = [[Paragraph(f'<b>{h}</b>', styles['MainStyleCenter']) for h in
                                                    ["Quantity", "Unit", "Product Code", "Lot Number",
                                                     "Reference #"]]], [H_ROW], [
            ('LINEBELOW', (0, 0), (-1, 0), 1, colors.black), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 3), ('RIGHTPADDING', (0, 0), (-1, -1), 3)]
        lines_used = 0
        for item in items_data:
            if lines_used >= MAX_PDF_ROWS: break
            qty = item.get('quantity', 0);
            display_qty = f"{float(qty):.2f}" if qty else "0.00"
            items_tbl_data.append([Paragraph(display_qty, styles['MainStyleRight']),
                                   Paragraph(str(item.get('unit', '')), styles['MainStyle']),
                                   Paragraph(str(item.get('product_code', '')), styles['MainStyle']),
                                   Paragraph(str(item.get('lot_number', '')), styles['MainStyle']),
                                   Paragraph(str(item.get('reference_number', '')), styles['MainStyle'])]);
            row_heights.append(D_ROW);
            lines_used += 1
            if remarks := item.get('remarks', '').strip():
                if lines_used >= MAX_PDF_ROWS: continue
                remark_idx = len(items_tbl_data);
                items_tbl_data.append(
                    [Paragraph(f"<i><b>Remarks:</b> {remarks}</i>", styles['RemarkStyle']), '', '', '', '']);
                row_heights.append(D_ROW);
                lines_used += 1;
                styles_dyn.append(('SPAN', (0, remark_idx), (-1, remark_idx)))
        if lines_used < MAX_PDF_ROWS:
            nf_idx = len(items_tbl_data);
            items_tbl_data.append(
                [Paragraph("***** NOTHING FOLLOWS *****", styles['MainStyleCenter']), '', '', '', '']);
            row_heights.append(D_ROW);
            styles_dyn.append(('SPAN', (0, nf_idx), (-1, nf_idx)));
            lines_used += 1
        while lines_used < MAX_PDF_ROWS: items_tbl_data.append([''] * 5); row_heights.append(D_ROW); lines_used += 1
        items_table = Table(items_tbl_data, colWidths=[1.1 * inch, 0.6 * inch, 1.8 * inch, 2.4 * inch, 2.0 * inch],
                            rowHeights=row_heights)
        items_table.setStyle(TableStyle(styles_dyn));
        Story.append(items_table)
        doc.build(Story, onFirstPage=page_template_drawer, onLaterPages=page_template_drawer)
        buffer.seek(0);
        return buffer

    def _handle_paint_request(self, printer: QPrinter):
        if not self.current_pdf_buffer: return
        painter = QPainter();
        if not painter.begin(printer): QMessageBox.critical(self, "Print Error",
                                                            "Could not initialize painter."); return
        self.current_pdf_buffer.seek(0);
        pdf_doc = fitz.open(stream=self.current_pdf_buffer, filetype="pdf")
        dpi = 300;
        zoom = dpi / 72.0;
        mat = fitz.Matrix(zoom, zoom)
        page_rect_dev_pixels = printer.pageRect(QPrinter.Unit.DevicePixel)
        for i, page in enumerate(pdf_doc):
            if i > 0: printer.newPage()
            pix = page.get_pixmap(matrix=mat, alpha=False)
            image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
            painter.drawImage(page_rect_dev_pixels.toRect(), image, image.rect())
        pdf_doc.close();
        painter.end()

    def _populate_table_generic(self, table, data, headers):
        table.setRowCount(0);
        table.setColumnCount(len(headers));
        table.setHorizontalHeaderLabels(headers)
        if not data: table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch); return
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
        table.resizeColumnsToContents()
        table.horizontalHeader().setSectionResizeMode(len(headers) - 1, QHeaderView.ResizeMode.Stretch)