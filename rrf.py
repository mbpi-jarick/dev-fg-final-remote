import sys
import io
import re
import math
from datetime import datetime, date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import partial
import traceback

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
from PyQt6.QtCore import Qt, QDate, QSize, QSizeF, QDateTime, QTimer
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QTabWidget, QFormLayout, QLineEdit, QDateEdit,
                             QPushButton, QTableWidget, QTableWidgetItem, QComboBox,
                             QAbstractItemView, QHeaderView, QMessageBox, QHBoxLayout, QLabel,
                             QGroupBox, QMenu, QGridLayout, QDialog, QDialogButtonBox,
                             QPlainTextEdit, QSplitter, QCheckBox, QInputDialog, QCompleter,
                             QListWidget, QListWidgetItem, QTextEdit, QSizePolicy, QFrame)

from PyQt6.QtGui import (QDoubleValidator, QPainter, QPageSize, QImage, QFont)
from PyQt6.QtPrintSupport import QPrinter, QPrintPreviewDialog

# --- Icon Imports ---
import qtawesome as fa
# --- Database Imports ---
from sqlalchemy import create_engine, text, inspect

# --- CONSTANTS ---
ADMIN_PASSWORD = "Itadmin"

# --- UI CONSTANTS (Aligned with AppStyles for visual consistency) ---
PRIMARY_ACCENT_COLOR = "#007bff"  # Used for light button primary
PRIMARY_ACCENT_HOVER = "#e9f0ff"
NEUTRAL_COLOR = "#6c757d"
LIGHT_TEXT_COLOR = "#333333"
BACKGROUND_CONTENT_COLOR = "#f4f7fc"
INPUT_BACKGROUND_COLOR = "#ffffff"
GROUP_BOX_HEADER_COLOR = "#f4f7fc"
TABLE_SELECTION_COLOR = "#3a506b"

# --- Icon Colors (Darker shades for visibility against light buttons) ---
COLOR_SUCCESS = '#27ae60'  # Darker green for visibility
COLOR_DANGER = '#c0392b'  # Darker red for visibility
COLOR_PRIMARY = '#2980b9'  # Darker blue for visibility (Used for Icons/Borders)
COLOR_SECONDARY = '#d35400'  # Darker orange for visibility
COLOR_MANAGEMENT = '#7d3c98'  # Darker purple for visibility
COLOR_DEFAULT = '#34495e'  # Dark grey for default icons
DESTRUCTIVE_COLOR = COLOR_DANGER  # Consistency


class FloatLineEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Validator remains standard to prevent input error issues with locale/comma typing
        validator = QDoubleValidator(0.0, 99999999.0, 6)
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        self.setValidator(validator)
        self.editingFinished.connect(self._format_text)
        self.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.setText("0.00")

    def _format_text(self):
        try:
            # CRUCIAL CHANGE: Use the comma separator in formatting
            text_value = self.text().replace(',', '')  # Strip any existing comma for conversion
            self.setText(f"{float(text_value or 0.0):,.2f}")
        except ValueError:
            self.setText("0.00")

    def value(self) -> float:
        # Must strip commas before returning raw float value
        text = self.text().replace(',', '')
        return float(text or 0.0)


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

        # --- QTAWESOME ICON & LIGHT BUTTON STYLE ---
        add_btn = QPushButton(fa.icon('fa5s.plus', color=COLOR_SUCCESS), " Add")
        remove_btn = QPushButton(fa.icon('fa5s.trash-alt', color=DESTRUCTIVE_COLOR), " Remove")
        add_btn.setObjectName("PrimaryButton")
        remove_btn.setObjectName("delete_btn")
        # -------------------------------------------

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

        # Apply specific dialog styles
        self.setStyleSheet(f"""
            QDialog {{ background-color: {INPUT_BACKGROUND_COLOR}; }}
            QLabel {{ background-color: transparent; }}
        """)

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
        buttons.button(QDialogButtonBox.StandardButton.Ok).setObjectName("PrimaryButton")
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
        self.setMinimumWidth(500)
        self.setStyleSheet(
            f"QDialog {{ background-color: {INPUT_BACKGROUND_COLOR}; }} QLabel {{ background-color: transparent; }}")

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.quantity_edit = FloatLineEdit()
        self.unit_edit = QComboBox(editable=True)
        set_combo_box_uppercase(self.unit_edit)
        self.manage_units_btn = QPushButton(" Manage...")

        # --- QTAWESOME ICON & LIGHT BUTTON STYLE ---
        self.manage_units_btn.setIcon(fa.icon('fa5s.cogs', color=COLOR_PRIMARY))
        self.manage_units_btn.setObjectName("PrimaryButton")
        # -------------------------------------------

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
        self.check_inventory_btn = QPushButton(" Check Stock")

        # --- QTAWESOME ICON & LIGHT BUTTON STYLE ---
        self.check_inventory_btn.setIcon(fa.icon('fa5s.search-dollar', color=COLOR_SECONDARY))
        self.check_inventory_btn.setObjectName("SecondaryButton")
        # -------------------------------------------

        self.inventory_status_label = QLabel("Status: Awaiting check...")
        self.inventory_status_label.setStyleSheet("font-style: italic; color: #555; background-color: transparent;")

        lot_layout = QHBoxLayout()
        lot_layout.setContentsMargins(0, 0, 0, 0)
        lot_layout.addWidget(self.lot_number_edit, 1)
        lot_layout.addWidget(self.check_inventory_btn)

        self.reference_number_edit = UpperCaseLineEdit()
        self.remarks_edit = QPlainTextEdit()

        form_layout.addRow("Quantity:", self.quantity_edit)
        form_layout.addRow("Unit:", unit_layout)
        form_layout.addRow("Product Code:", self.product_code_edit)
        form_layout.addRow("Lot Number:", lot_layout)
        form_layout.addRow("", self.inventory_status_label)
        form_layout.addRow("Reference Number:", self.reference_number_edit)
        form_layout.addRow("Remarks:", self.remarks_edit)

        layout.addLayout(form_layout)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok_button.setObjectName("PrimaryButton")

        if self.material_type == "RAW MATERIAL":
            self.ok_button.setEnabled(False)
            self.check_inventory_btn.setVisible(True)
            self.inventory_status_label.setVisible(True)
        else:
            self.ok_button.setEnabled(True)
            self.check_inventory_btn.setVisible(False)
            self.inventory_status_label.setVisible(False)

        self.manage_units_btn.clicked.connect(self._manage_units)
        self.check_inventory_btn.clicked.connect(self._check_lot_in_inventory)
        self.lot_number_edit.editingFinished.connect(self._check_lot_in_inventory)
        self.lot_number_edit.textChanged.connect(self._reset_validation)

        self._load_combobox_data()
        if item_data:
            self.populate_data(item_data)
            if self.material_type == "RAW MATERIAL" and self.lot_number_edit.text():
                self._check_lot_in_inventory()

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
        # Ensure raw float is set, then force formatting to show commas
        qty_str = str(data.get("quantity", "0.00")).replace(',', '')
        try:
            qty_float = float(qty_str)
            self.quantity_edit.setText(str(qty_float))  # Set raw number string
            self.quantity_edit._format_text()  # Force formatting
        except ValueError:
            self.quantity_edit.setText("0.00")

        self.unit_edit.setCurrentText(data.get("unit", "KG."))
        self.product_code_edit.setCurrentText(data.get("product_code", ""))
        self.lot_number_edit.setText(data.get("lot_number", ""))
        self.reference_number_edit.setText(data.get("reference_number", ""))
        self.remarks_edit.setPlainText(data.get("remarks", ""))

    def get_item_data(self):
        # We return the formatted text of quantity, which is handled correctly by _save_record
        return {
            "quantity": self.quantity_edit.value(),  # Use value() to get raw float
            "unit": self.unit_edit.currentText().strip().upper(),
            "product_code": self.product_code_edit.currentText().strip().upper(),
            "lot_number": self.lot_number_edit.text(),
            "reference_number": self.reference_number_edit.text(),
            "remarks": self.remarks_edit.toPlainText()
        }

    def _reset_validation(self):
        if self.material_type == "RAW MATERIAL":
            self.ok_button.setEnabled(False)
            self.inventory_status_label.setText("Status: Awaiting check...")
            self.inventory_status_label.setStyleSheet("font-style: italic; color: #555; background-color: transparent;")

    def _get_lot_beginning_qty(self, conn, lot_number):
        # This function structure remains complex but is necessary to search across all beginning inventory tables
        inspector = inspect(self.engine)
        schema = inspector.default_schema_name
        # Check all tables starting with 'beginv_' or 'beg_invfailed'
        all_tables = [tbl for tbl in inspector.get_table_names(schema=schema) if
                      tbl.startswith('beginv_') or tbl.startswith('beg_invfailed')]
        total_qty = Decimal('0.0')
        for tbl in all_tables:
            columns = [col['name'] for col in inspector.get_columns(tbl, schema=schema)]
            lot_col = next((c for c in columns if 'lot' in c.lower()), None)
            qty_col = next((c for c in columns if 'qty' in c.lower() or 'quantity' in c.lower()), None)
            if lot_col and qty_col:
                # Use double quotes for case-insensitive table/column names in Postgres
                query = text(f'SELECT SUM("{qty_col}"::numeric) FROM "{tbl}" WHERE "{lot_col}" = :lot')
                result = conn.execute(query, {"lot": lot_number}).scalar_one_or_none()
                if result:
                    total_qty += Decimal(result)
        return total_qty

    def _get_lot_additions_qty(self, conn, lot_number):
        query = text("SELECT COALESCE(SUM(quantity_in), 0) FROM transactions WHERE lot_number = :lot")
        return conn.execute(query, {"lot": lot_number}).scalar_one()

    def _get_lot_removals_qty(self, conn, lot_number):
        query = text("SELECT COALESCE(SUM(quantity_out), 0) FROM transactions WHERE lot_number = :lot")
        return conn.execute(query, {"lot": lot_number}).scalar_one()

    def _check_lot_in_inventory(self):
        if self.material_type != "RAW MATERIAL":
            return
        lot_number = self.lot_number_edit.text().strip()
        if not lot_number:
            self._reset_validation()
            return
        try:
            with self.engine.connect() as conn:
                beginning = self._get_lot_beginning_qty(conn, lot_number)
                additions = self._get_lot_additions_qty(conn, lot_number)
                removals = self._get_lot_removals_qty(conn, lot_number)

            current_stock = Decimal(beginning) + Decimal(additions) - Decimal(removals)

            if current_stock > 0:
                # Apply comma formatting
                formatted_stock = f"{current_stock:,.2f}"
                self.inventory_status_label.setText(f"Status: Found in stock. Available Qty: {formatted_stock} kg")
                self.inventory_status_label.setStyleSheet(
                    "font-weight: bold; color: #2ecc71; background-color: transparent;")
                self.ok_button.setEnabled(True)

                # Set raw number, then force formatting to show commas
                self.quantity_edit.setText(str(float(current_stock)))
                self.quantity_edit._format_text()
            else:
                formatted_stock = f"{current_stock:,.2f}"
                self.inventory_status_label.setText(
                    f"Status: NOT FOUND or stock is zero. (Current: {formatted_stock} kg)")
                self.inventory_status_label.setStyleSheet(
                    "font-weight: bold; color: #e74c3c; background-color: transparent;")
                self.ok_button.setEnabled(False)
        except Exception as e:
            self.inventory_status_label.setText("Status: Error during inventory check.")
            self.inventory_status_label.setStyleSheet(
                "font-weight: bold; color: #e74c3c; background-color: transparent;")
            self.ok_button.setEnabled(False)
            QMessageBox.critical(self, "DB Error", f"An error occurred while checking inventory: {e}")
            print(traceback.format_exc())


class RRFPage(QWidget):
    def __init__(self, db_engine, username, log_audit_trail_func):
        super().__init__()
        self.engine, self.username, self.log_audit_trail = db_engine, username, log_audit_trail_func
        self.current_editing_rrf_no, self.MAX_ITEMS = None, 15
        self.printer, self.current_pdf_buffer = QPrinter(), None
        self.breakdown_preview_data = []  # List of dictionaries, each dict is one batch/preview entry
        self.current_page, self.records_per_page = 1, 200
        self.total_records, self.total_pages = 0, 1
        self.previous_material_type_index = 0
        self.init_ui()
        self.setStyleSheet(self._get_styles())
        self._load_all_records()

    def _get_styles(self) -> str:
        return f"""
            /* Base Widget Styles */
            QWidget {{ 
                background-color: {BACKGROUND_CONTENT_COLOR};
                color: {LIGHT_TEXT_COLOR};
                font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
            }}

            /* Explicitly set all QLabels to white background */
            QLabel {{
                background-color: {INPUT_BACKGROUND_COLOR};
                color: {LIGHT_TEXT_COLOR};
                padding: 0 4px;
            }}

            /* Header Widget Container Transparency (Header containing icon and title) */
            #HeaderWidget {{
                background-color: transparent;
            }}

            /* Header Labels: Ensure icon and title are transparent */
            #HeaderWidget QLabel {{
                background-color: transparent;
            }}

            QLabel#PageHeader {{ 
                font-size: 15pt; 
                font-weight: bold; 
                color: {"#3a506b"}; 
            }}

            /* Input Fields (QLineEdit, QDateEdit, QComboBox, QPlainTextEdit, FloatLineEdit) */
            QLineEdit, QDateEdit, QComboBox, QPlainTextEdit, FloatLineEdit {{
                border: 1px solid #d1d9e6; 
                padding: 8px; 
                border-radius: 5px;
                background-color: {INPUT_BACKGROUND_COLOR};
                color: {LIGHT_TEXT_COLOR};
            }}
            QLineEdit:focus, QDateEdit:focus, QComboBox:focus, QPlainTextEdit:focus, FloatLineEdit:focus {{
                border: 1px solid {PRIMARY_ACCENT_COLOR};
            }}

            /* Group Box Styling */
            QGroupBox {{
                border: 1px solid #e0e5eb; border-radius: 8px;
                margin-top: 12px; background-color: {INPUT_BACKGROUND_COLOR};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; subcontrol-position: top left;
                padding: 2px 10px; background-color: {GROUP_BOX_HEADER_COLOR};
                border: 1px solid #e0e5eb; border-bottom: 1px solid {INPUT_BACKGROUND_COLOR};
                border-top-left-radius: 8px; border-top-right-radius: 8px;
                font-weight: bold; color: #4f4f4f;
            }}

            /* Instruction Box Style */
            QGroupBox#InstructionGroup {{
                background-color: #e9f0ff; /* Light accent background */
                border: 1px solid {PRIMARY_ACCENT_COLOR};
                color: {LIGHT_TEXT_COLOR};
            }}
            QGroupBox#InstructionGroup QTextEdit {{
                background-color: transparent; 
                border: none;
            }}
            QGroupBox#InstructionGroup QLabel {{
                background-color: transparent; 
            }}


            /* --- BUTTON STYLES (Light Color Scheme) --- */
            QPushButton {{
                border: 1px solid #d1d9e6; 
                padding: 8px 15px;
                border-radius: 6px;
                font-weight: bold;
                color: {LIGHT_TEXT_COLOR}; 
                background-color: {INPUT_BACKGROUND_COLOR}; 
                qproperty-iconSize: 16px;
            }}
            QPushButton:hover {{
                background-color: #f0f3f8; /* Standard Light Gray Hover */
                border: 1px solid #c0c0c0;
            }}

            /* Primary Button (Save/Restore/Next/Prev) */
            QPushButton#PrimaryButton {{
                border: 1px solid {COLOR_PRIMARY}; 
                color: {COLOR_PRIMARY}; 
            }}
            QPushButton#PrimaryButton:hover {{
                background-color: {PRIMARY_ACCENT_HOVER}; 
                border: 1px solid {COLOR_PRIMARY};
            }}

            /* Secondary Button (Update/Fetch/Edit/Check Stock) */
            QPushButton#SecondaryButton {{
                border: 1px solid {COLOR_SECONDARY};
                color: {COLOR_SECONDARY};
            }}
            QPushButton#SecondaryButton:hover {{
                background-color: #fcf3cf;
            }}

            /* Default Button (Manage lists - using gray accent for utility) */
            QPushButton#DefaultButton {{
                border: 1px solid {NEUTRAL_COLOR}; 
                color: {NEUTRAL_COLOR}; 
            }}
            QPushButton#DefaultButton:hover {{
                background-color: #f0f3f8;
            }}

            /* Delete/Remove Button */
            QPushButton#delete_btn, QPushButton#remove_item_btn {{
                border: 1px solid {DESTRUCTIVE_COLOR}; 
                color: {DESTRUCTIVE_COLOR}; 
            }}
            QPushButton#delete_btn:hover, QPushButton#remove_item_btn:hover {{
                background-color: #fddde1;
            }}

            /* Table Styling */
            QTableWidget {{
                border: 1px solid #e0e5eb;
                background-color: {INPUT_BACKGROUND_COLOR};
                selection-behavior: SelectRows;
                color: {LIGHT_TEXT_COLOR};
                border-radius: 8px;
            }}
            QTableWidget::item {{
                border-bottom: 1px solid #f4f7fc;
                padding: 5px;
            }}
            QTableWidget::item:selected {{
                background-color: {TABLE_SELECTION_COLOR}; 
                color: white;
                border: 0px; 
            }}
        """

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # --- HEADER ---
        header_widget = QWidget()
        header_widget.setObjectName("HeaderWidget")
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)

        icon_label = QLabel()
        icon_label.setPixmap(fa.icon('fa5s.undo-alt', color="#3a506b").pixmap(QSize(28, 28)))
        header_layout.addWidget(icon_label)

        title_label = QLabel("Return Replacement Form", objectName="PageHeader")
        title_label.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        main_layout.addWidget(header_widget)
        # --------------

        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        self.view_tab = QWidget()
        self.entry_tab = QWidget()
        self.view_details_tab = QWidget()
        self.breakdown_tool_tab = QWidget()
        self.breakdown_records_tab = QWidget()
        self.deleted_tab = QWidget()

        # Tabs using updated icon colors (DELETED TAB ALIGNED NEXT IN RFF ENTRIES)
        self.tab_widget.addTab(self.view_tab, fa.icon('fa5s.list-alt', color=COLOR_PRIMARY), "RRF Records")
        self.tab_widget.addTab(self.entry_tab, fa.icon('fa5s.file-signature', color=COLOR_PRIMARY), "RRF Entry")
        self.tab_widget.addTab(self.view_details_tab, fa.icon('fa5s.eye', color=COLOR_SECONDARY), "View RRF Details")

        # Deleted tab moved to position 4, right after the main RRF workflow tabs
        self.tab_widget.addTab(self.deleted_tab, fa.icon('fa5s.trash', color=COLOR_DANGER), "Deleted")

        self.tab_widget.addTab(self.breakdown_tool_tab, fa.icon('fa5s.cut', color=COLOR_DANGER), "Lot Breakdown Tool")
        self.tab_widget.addTab(self.breakdown_records_tab, fa.icon('fa5s.database', color=COLOR_DEFAULT),
                               "Breakdown Records")

        self._setup_view_tab(self.view_tab)
        self._setup_entry_tab(self.entry_tab)
        self._setup_view_details_tab(self.view_details_tab)
        self._setup_lot_breakdown_tab(self.breakdown_tool_tab)
        self._setup_breakdown_records_tab(self.breakdown_records_tab)
        self._setup_deleted_tab(self.deleted_tab)

        self.notification_label = QLabel("")
        self.notification_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.notification_label.setStyleSheet("padding: 8px; font-weight: bold; border-radius: 4px;")
        self.notification_label.hide()
        main_layout.addWidget(self.notification_label)
        self.notification_timer = QTimer(self)
        self.notification_timer.setSingleShot(True)
        self.notification_timer.timeout.connect(self.notification_label.hide)

        self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.view_details_tab), False)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

    def show_notification(self, message: str, level: str = 'info', duration_ms: int = 5000):
        self.notification_timer.stop()
        level_styles = {
            'info': "background-color: #3498db; color: white;",
            'success': "background-color: #2ecc71; color: white;",
            'warning': "background-color: #f39c12; color: white;",
            'error': "background-color: #e74c3c; color: white;"
        }
        base_style = "padding: 8px; font-weight: bold; border-radius: 4px;"
        self.notification_label.setStyleSheet(base_style + level_styles.get(level, level_styles['info']))
        self.notification_label.setText(message)
        self.notification_label.show()
        self.notification_timer.start(duration_ms)

    def _setup_view_tab(self, tab):
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Instruction
        instruction_group = QGroupBox("Instructions", objectName="InstructionGroup")
        instruction_layout = QVBoxLayout(instruction_group)
        instruction_label = QLabel(
            "Browse, search, update, or delete existing Return/Replacement Forms (RRF). Double-click a row to edit.")
        instruction_label.setWordWrap(True)
        instruction_layout.addWidget(instruction_label)
        layout.addWidget(instruction_group)

        controls_group = QGroupBox("Search & Actions")
        top_layout = QHBoxLayout(controls_group)
        top_layout.addWidget(QLabel("Search:"))
        self.search_edit = UpperCaseLineEdit(placeholderText="Filter by RRF No, Customer, Product Code...")
        self.refresh_records_btn = QPushButton(" Refresh")
        self.update_btn = QPushButton(" Update Selected")
        self.delete_btn = QPushButton(" Delete Selected")

        # --- QTAWESOME ICON & LIGHT BUTTON STYLE ---
        self.refresh_records_btn.setIcon(fa.icon('fa5s.sync-alt', color=COLOR_PRIMARY))
        self.update_btn.setIcon(fa.icon('fa5s.edit', color=COLOR_SECONDARY))
        self.delete_btn.setIcon(fa.icon('fa5s.trash-alt', color=DESTRUCTIVE_COLOR))

        self.refresh_records_btn.setObjectName("PrimaryButton")
        self.update_btn.setObjectName("SecondaryButton")
        self.delete_btn.setObjectName("delete_btn")
        # -------------------------------------------

        top_layout.addWidget(self.search_edit, 1)
        top_layout.addWidget(self.refresh_records_btn)
        top_layout.addWidget(self.update_btn)
        top_layout.addWidget(self.delete_btn)
        layout.addWidget(controls_group)

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
        self.prev_btn = QPushButton(" Previous")
        self.next_btn = QPushButton("Next ")
        self.next_btn.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        # --- QTAWESOME ICON & LIGHT BUTTON STYLE ---
        self.prev_btn.setIcon(fa.icon('fa5s.chevron-left', color="#3a506b"))
        self.next_btn.setIcon(fa.icon('fa5s.chevron-right', color="#3a506b"))
        self.prev_btn.setObjectName("PrimaryButton")
        self.next_btn.setObjectName("PrimaryButton")
        # -------------------------------------------

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
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # Instruction Group (Fixed Height for Instructions)
        instruction_group = QGroupBox("Instructions", objectName="InstructionGroup")
        instruction_text = "Enter new Return/Replacement Form (RRF) details, including header information and associated returned items. Use the 'Check Stock' button for Raw Material returns to ensure inventory integrity."

        # Using QTextEdit with controlled height
        instruction_edit = QTextEdit(instruction_text)
        instruction_edit.setReadOnly(True)
        instruction_edit.setMaximumHeight(70)
        instruction_vbox = QVBoxLayout(instruction_group)
        instruction_vbox.addWidget(instruction_edit)
        instruction_vbox.setContentsMargins(5, 5, 5, 5)
        main_layout.addWidget(instruction_group)

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
        self.item_count_label.setStyleSheet("background-color: transparent;")  # Keep transparent here
        items_button_layout.addWidget(self.item_count_label, 1)
        add_item_btn = QPushButton(" Add Item")
        self.edit_item_btn = QPushButton(" Edit Selected")
        self.remove_item_btn = QPushButton(" Remove Selected")

        # --- QTAWESOME ICON & LIGHT BUTTON STYLE ---
        add_item_btn.setIcon(fa.icon('fa5s.plus', color=COLOR_PRIMARY))
        self.edit_item_btn.setIcon(fa.icon('fa5s.pen', color=COLOR_SECONDARY))
        self.remove_item_btn.setIcon(fa.icon('fa5s.minus', color=DESTRUCTIVE_COLOR))
        add_item_btn.setObjectName("PrimaryButton")
        self.edit_item_btn.setObjectName("SecondaryButton")
        self.remove_item_btn.setObjectName("delete_btn")
        # -------------------------------------------

        items_button_layout.addWidget(add_item_btn)
        items_button_layout.addWidget(self.edit_item_btn)
        items_button_layout.addWidget(self.remove_item_btn)
        items_layout.addLayout(items_button_layout)
        main_layout.addWidget(items_group, 1)

        action_button_layout = QHBoxLayout()
        self.save_btn = QPushButton(" Save")
        self.save_btn.setObjectName("PrimaryButton")
        self.clear_btn = QPushButton(" New")
        self.clear_btn.setObjectName("SecondaryButton")
        self.cancel_update_btn = QPushButton(" Cancel Update")
        self.cancel_update_btn.setObjectName("delete_btn")
        self.print_btn = QPushButton(" Print Preview")

        # --- QTAWESOME ICON & LIGHT BUTTON STYLE ---
        self.save_btn.setIcon(fa.icon('fa5s.save', color=COLOR_PRIMARY))
        self.clear_btn.setIcon(fa.icon('fa5s.file-alt', color=COLOR_SECONDARY))
        self.cancel_update_btn.setIcon(fa.icon('fa5s.times', color=DESTRUCTIVE_COLOR))
        self.print_btn.setIcon(fa.icon('fa5s.print', color=COLOR_PRIMARY))
        self.print_btn.setObjectName("SecondaryButton")
        # -------------------------------------------

        action_button_layout.addStretch()
        action_button_layout.addWidget(self.cancel_update_btn)
        action_button_layout.addWidget(self.clear_btn)
        action_button_layout.addWidget(self.save_btn)
        action_button_layout.addWidget(self.print_btn)
        main_layout.addLayout(action_button_layout)

        add_item_btn.clicked.connect(self._add_item_row)
        self.edit_item_btn.clicked.connect(self._edit_item_row)
        self.remove_item_btn.clicked.connect(self._remove_item_row)
        self.clear_btn.clicked.connect(self._clear_form)
        self.cancel_update_btn.clicked.connect(self._clear_form)
        self.save_btn.clicked.connect(self._save_record)
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
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Instruction Group (Fixed Height for Instructions)
        instruction_group = QGroupBox("Instructions", objectName="InstructionGroup")
        instruction_text = "Use this tool to break down a large RRF item quantity into individual lots/bags/boxes for inventory tracking. The quantity to breakdown can be edited but cannot exceed the original item quantity. Use the 'Preview' button multiple times to accumulate batches before saving."

        # Using QTextEdit with controlled height
        instruction_edit = QTextEdit(instruction_text)
        instruction_edit.setReadOnly(True)
        instruction_edit.setMaximumHeight(75)

        instruction_vbox = QVBoxLayout(instruction_group)
        instruction_vbox.addWidget(instruction_edit)
        instruction_vbox.setContentsMargins(5, 5, 5, 5)
        layout.addWidget(instruction_group)

        # Splitter adjusted to take the rest of the vertical space
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(main_splitter, 1)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 5, 0)
        main_splitter.addWidget(left_widget)

        fetch_group = QGroupBox("1. Select RRF Item")
        fetch_layout = QFormLayout(fetch_group)
        self.breakdown_rrf_combo = QComboBox()
        self.breakdown_item_combo = QComboBox()

        # --- MODIFICATION: Use FloatLineEdit for editable quantity ---
        self.breakdown_item_qty_display = FloatLineEdit()
        self.breakdown_item_qty_display.setAlignment(Qt.AlignmentFlag.AlignRight)
        # Set background to standard input color
        self.breakdown_item_qty_display.setStyleSheet(f"background-color: {INPUT_BACKGROUND_COLOR}; font-weight: bold;")

        fetch_layout.addRow("RRF Number:", self.breakdown_rrf_combo)
        fetch_layout.addRow("Item to Break Down:", self.breakdown_item_combo)
        fetch_layout.addRow("Quantity to Breakdown (kg):", self.breakdown_item_qty_display)
        left_layout.addWidget(fetch_group)

        params_group = QGroupBox("2. Define Breakdown")
        params_layout = QGridLayout(params_group)
        self.breakdown_weight_per_lot_edit = FloatLineEdit()
        self.breakdown_num_lots_edit = QLineEdit("0", readOnly=True)
        self.breakdown_num_lots_edit.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.breakdown_num_lots_edit.setStyleSheet(f"background-color: {GROUP_BOX_HEADER_COLOR};")
        self.breakdown_lot_range_edit = UpperCaseLineEdit(placeholderText="e.g., 12345 or 12345-12350")
        params_layout.addWidget(QLabel("Weight per Lot (kg):"), 0, 0)
        params_layout.addWidget(self.breakdown_weight_per_lot_edit, 0, 1)
        params_layout.addWidget(QLabel("Calculated No. of Lots:"), 0, 2)
        params_layout.addWidget(self.breakdown_num_lots_edit, 0, 3)
        params_layout.addWidget(QLabel("Lot Start/Range:"), 1, 0)
        params_layout.addWidget(self.breakdown_lot_range_edit, 1, 1, 1, 3)
        self.breakdown_location_combo = QComboBox()
        self.breakdown_location_combo.addItems(["-- Select a Warehouse --", "WH1", "WH2", "WH3", "WH4"])
        params_layout.addWidget(QLabel("Target Warehouse:"), 2, 0)
        params_layout.addWidget(self.breakdown_location_combo, 2, 1, 1, 3)
        left_layout.addWidget(params_group)
        left_layout.addStretch()

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(5, 0, 0, 0)
        main_splitter.addWidget(right_widget)

        breakdown_preview_group = QGroupBox("3. Preview and Save")
        breakdown_preview_layout = QVBoxLayout(breakdown_preview_group)

        self.breakdown_preview_table = QTableWidget(editTriggers=QAbstractItemView.EditTrigger.NoEditTriggers)
        self.breakdown_preview_table.setShowGrid(False)
        self.breakdown_preview_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.breakdown_preview_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.breakdown_preview_table.verticalHeader().setVisible(False)
        self.breakdown_preview_table.horizontalHeader().setHighlightSections(False)
        self.breakdown_preview_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        breakdown_preview_layout.addWidget(self.breakdown_preview_table, 1)  # Give table stretch factor

        self.breakdown_total_label = QLabel("<b>Total: 0.00 kg</b>")
        self.breakdown_total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        breakdown_preview_layout.addWidget(self.breakdown_total_label)
        right_layout.addWidget(breakdown_preview_group, 1)  # Give group stretch factor

        # Splitter sizes adjusted to 40% (input) and 60% (preview)
        main_splitter.setSizes([400, 600])

        button_layout = QHBoxLayout()
        self.breakdown_save_btn = QPushButton(" Save Breakdown")
        self.breakdown_save_btn.setObjectName("PrimaryButton")
        preview_btn = QPushButton(" Preview Breakdown")
        preview_btn.setObjectName("SecondaryButton")
        clear_btn = QPushButton(" Clear")
        clear_btn.setObjectName("DefaultButton")

        # --- QTAWESOME ICON & LIGHT BUTTON STYLE ---
        self.breakdown_save_btn.setIcon(fa.icon('fa5s.save', color=COLOR_PRIMARY))
        preview_btn.setIcon(fa.icon('fa5s.search', color=COLOR_SECONDARY))
        clear_btn.setIcon(fa.icon('fa5s.eraser', color=COLOR_DEFAULT))
        # -------------------------------------------

        button_layout.addStretch()
        button_layout.addWidget(clear_btn)
        button_layout.addWidget(preview_btn)
        button_layout.addWidget(self.breakdown_save_btn)
        left_layout.addLayout(button_layout)

        # Connect signals
        self.breakdown_rrf_combo.currentIndexChanged.connect(self._on_breakdown_rrf_selected)
        self.breakdown_item_combo.currentIndexChanged.connect(self._on_breakdown_item_selected)

        # Connect the editable quantity field to recalculation
        self.breakdown_item_qty_display.textChanged.connect(self._recalculate_num_lots)
        self.breakdown_item_qty_display.editingFinished.connect(self._recalculate_num_lots)

        self.breakdown_weight_per_lot_edit.textChanged.connect(self._recalculate_num_lots)
        preview_btn.clicked.connect(self._preview_lot_breakdown)
        clear_btn.clicked.connect(self._clear_breakdown_tool)
        self.breakdown_save_btn.clicked.connect(self._save_lot_breakdown)

    def _setup_breakdown_records_tab(self, tab):
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Instruction
        instruction_group = QGroupBox("Instructions", objectName="InstructionGroup")
        instruction_layout = QVBoxLayout(instruction_group)
        instruction_label = QLabel(
            "View previously created lot breakdowns. Use 'Load for Update' to edit the breakdown in the Breakdown Tool tab, or delete the record.")
        instruction_label.setWordWrap(True)
        instruction_layout.addWidget(instruction_label)
        layout.addWidget(instruction_group)

        controls_group = QGroupBox("Search & Actions")
        top_layout = QHBoxLayout(controls_group)
        top_layout.addWidget(QLabel("Search:"))
        self.breakdown_search_edit = UpperCaseLineEdit(placeholderText="Filter by RRF No or Product Code...")
        self.refresh_breakdown_btn = QPushButton(" Refresh")
        self.load_breakdown_btn = QPushButton(" Load for Update")
        self.delete_breakdown_btn = QPushButton(" Delete Selected Breakdown")

        # --- QTAWESOME ICON & LIGHT BUTTON STYLE ---
        self.refresh_breakdown_btn.setIcon(fa.icon('fa5s.sync-alt', color=COLOR_PRIMARY))
        self.load_breakdown_btn.setIcon(fa.icon('fa5s.upload', color=COLOR_SECONDARY))
        self.delete_breakdown_btn.setIcon(fa.icon('fa5s.trash-alt', color=DESTRUCTIVE_COLOR))
        self.refresh_breakdown_btn.setObjectName("PrimaryButton")
        self.load_breakdown_btn.setObjectName("SecondaryButton")
        self.delete_breakdown_btn.setObjectName("delete_btn")
        # -------------------------------------------

        top_layout.addWidget(self.breakdown_search_edit, 1)
        top_layout.addWidget(self.refresh_breakdown_btn)
        top_layout.addWidget(self.load_breakdown_btn)
        top_layout.addWidget(self.delete_breakdown_btn)
        layout.addWidget(controls_group)

        self.breakdown_records_table = QTableWidget()
        self.breakdown_records_table.setShowGrid(False)
        self.breakdown_records_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.breakdown_records_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.breakdown_records_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.breakdown_records_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.breakdown_records_table.verticalHeader().setVisible(False)
        self.breakdown_records_table.horizontalHeader().setHighlightSections(False)
        self.breakdown_records_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)

        # Enable Context Menu for Breakdown Records
        self.breakdown_records_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.breakdown_records_table.customContextMenuRequested.connect(self._show_breakdown_records_context_menu)

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
        self.load_breakdown_btn.setEnabled(False)
        self.delete_breakdown_btn.setEnabled(False)

    def _show_breakdown_records_context_menu(self, pos):
        if not self.breakdown_records_table.selectedItems(): return
        menu = QMenu()
        delete_action = menu.addAction(fa.icon('fa5s.trash-alt', color=DESTRUCTIVE_COLOR), "Delete Breakdown")
        load_action = menu.addAction(fa.icon('fa5s.upload', color=COLOR_SECONDARY), "Load for Update")

        action = menu.exec(self.breakdown_records_table.mapToGlobal(pos))
        if action == delete_action:
            self._delete_selected_breakdown()
        elif action == load_action:
            self._load_breakdown_for_update()

    def _setup_deleted_tab(self, tab):
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Instruction
        instruction_group = QGroupBox("Instructions", objectName="InstructionGroup")
        instruction_layout = QVBoxLayout(instruction_group)
        instruction_label = QLabel(
            "Records shown here have been marked as deleted (soft-deleted). Use the restore button to bring them back to the active RRF records list.")
        instruction_label.setWordWrap(True)
        instruction_layout.addWidget(instruction_label)
        layout.addWidget(instruction_group)

        controls_group = QGroupBox("Search & Restore")
        top_layout = QHBoxLayout(controls_group)
        top_layout.addWidget(QLabel("Search Deleted Records:"))
        self.deleted_search_edit = UpperCaseLineEdit(placeholderText="Filter by RRF No, Customer...")
        top_layout.addWidget(self.deleted_search_edit, 1)
        self.deleted_refresh_btn = QPushButton(" Refresh")
        self.restore_btn = QPushButton(" Restore Selected")

        # --- QTAWESOME ICON & LIGHT BUTTON STYLE ---
        self.deleted_refresh_btn.setIcon(fa.icon('fa5s.sync-alt', color=COLOR_PRIMARY))
        self.restore_btn.setIcon(fa.icon('fa5s.undo', color=COLOR_PRIMARY))
        self.deleted_refresh_btn.setObjectName("PrimaryButton")
        self.restore_btn.setObjectName("PrimaryButton")
        # -------------------------------------------

        top_layout.addWidget(self.deleted_refresh_btn)
        top_layout.addWidget(self.restore_btn)
        layout.addWidget(controls_group)

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
        self.deleted_refresh_btn.clicked.connect(self._load_deleted_records)
        self.restore_btn.clicked.connect(self._restore_record)
        self.deleted_records_table.customContextMenuRequested.connect(self._show_deleted_records_context_menu)
        self.deleted_records_table.itemSelectionChanged.connect(self._on_deleted_record_selection_changed)
        self._on_deleted_record_selection_changed()

    def _on_tab_changed(self, index):
        tab_text = self.tab_widget.tabText(index)
        # Add instruction labels to the main layout of each tab if they are missing

        if tab_text == "View RRF Details":
            if self.records_table.selectionModel().hasSelection():
                self._show_selected_record_in_view_tab()
            elif self.deleted_records_table.selectionModel().hasSelection():
                self._show_selected_deleted_record_in_view_tab()
        elif tab_text == "RRF Records":
            self._load_all_records()
        elif tab_text == "RRF Entry" and not self.current_editing_rrf_no:
            self._load_combobox_data()
        elif tab_text == "Lot Breakdown Tool":
            self._load_rrf_numbers_for_breakdown()
        elif tab_text == "Breakdown Records":
            self._load_all_breakdown_records()
        elif tab_text == "Deleted":
            self._load_deleted_records()

    def _setup_view_details_tab(self, tab):
        main_splitter = QSplitter(Qt.Orientation.Vertical);
        main_layout = QVBoxLayout(tab);

        # Instruction
        instruction_group = QGroupBox("Instructions", objectName="InstructionGroup")
        instruction_layout = QVBoxLayout(instruction_group)
        instruction_label = QLabel(
            "Detailed view of the selected RRF. This view is read-only and shows header, item, and lot breakdown details.")
        instruction_label.setWordWrap(True)
        instruction_layout.addWidget(instruction_label)
        instruction_edit = QTextEdit(instruction_label.text())
        instruction_edit.setReadOnly(True)
        instruction_edit.setMaximumHeight(70)
        instruction_vbox = QVBoxLayout(instruction_group)
        instruction_vbox.addWidget(instruction_edit)
        instruction_vbox.setContentsMargins(5, 5, 5, 5)
        main_layout.addWidget(instruction_group)

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
                # Apply comma formatting
                display_value = f"{float(value):,.2f}" if isinstance(value, (Decimal, float)) else str(value or "")
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

        breakdown_tool_widget = self.breakdown_tool_tab

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
            # Item data stored at UserRole contains {'id': ...}
            item_data = self.breakdown_item_combo.itemData(i)
            if item_data and item_data.get('id') == item_id:
                self.breakdown_item_combo.setCurrentIndex(i);
                break

        # NOTE: Loading for update clears existing breakdown and requires the user to re-preview,
        # which is correct for safety given the complexity of lot numbering.
        self.show_notification(
            f"RRF Item {item_id} from RRF {rrf_no} loaded for update. Please re-enter breakdown batches.", 'warning')

    def _delete_selected_breakdown(self):
        selected = self.breakdown_records_table.selectionModel().selectedRows()
        if not selected: return
        row_index = selected[0].row()
        rrf_no = self.breakdown_records_table.item(row_index, 0).text()
        item_id = int(self.breakdown_records_table.item(row_index, 1).text())

        # Get product code for deletion targeting
        product_code = self.breakdown_records_table.item(row_index, 2).text()

        reply = QMessageBox.question(self, "Confirm Deletion",
                                     f"Are you sure you want to permanently delete the lot breakdown for Item ID <b>{item_id}</b> on RRF No: <b>{rrf_no}</b>?<br><br>"
                                     "This will also remove the associated transaction logs. This action cannot be undone.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        if reply != QMessageBox.StandardButton.Yes: return

        # Define the specific remark pattern used during insertion (RRF + Item ID)
        specific_remark = f"Generated from RRF {rrf_no} (Item {item_id})"

        try:
            with self.engine.connect() as conn, conn.begin():
                # 1. Delete breakdown records (this is unique by (rrf_no, item_id))
                conn.execute(
                    text("DELETE FROM rrf_lot_breakdown WHERE rrf_no = :rrf_no AND item_id = :item_id"),
                    {"rrf_no": rrf_no, "item_id": item_id}
                )

                # 2. Delete associated RRF_BREAKDOWN_OUT transactions
                # We target using RRF No, Product Code, AND the precise Remarks string (Item ID)
                conn.execute(text("""
                    DELETE FROM transactions
                    WHERE transaction_type = 'RRF_BREAKDOWN_OUT'
                    AND source_ref_no = :rrf_no
                    AND product_code = :pc
                    AND remarks = :specific_remark
                """), {"rrf_no": rrf_no, "pc": product_code, "specific_remark": specific_remark})

            self.log_audit_trail("DELETE_RRF_BREAKDOWN",
                                 f"Deleted breakdown and transactions for RRF {rrf_no}, Item {item_id}")
            self.show_notification("The selected lot breakdown has been deleted.", 'success')
            self._load_all_breakdown_records()
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Could not delete the breakdown record: {e}")
            self.show_notification("Error deleting breakdown. See dialog for details.", 'error')
            print(traceback.format_exc())

    def _on_record_selection_changed(self):
        is_selected = bool(self.records_table.selectionModel().selectedRows())
        self.update_btn.setEnabled(is_selected)
        self.delete_btn.setEnabled(is_selected)
        self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.view_details_tab), is_selected)
        if is_selected:
            self.deleted_records_table.clearSelection()
        elif self.tab_widget.currentIndex() == self.tab_widget.indexOf(self.view_details_tab):
            self.tab_widget.setCurrentIndex(0)

    def _on_deleted_record_selection_changed(self):
        is_selected = bool(self.deleted_records_table.selectionModel().selectedRows())
        self.restore_btn.setEnabled(is_selected)
        self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.view_details_tab), is_selected)
        if is_selected:
            self.records_table.clearSelection()
        elif self.tab_widget.currentIndex() == self.tab_widget.indexOf(self.view_details_tab):
            self.tab_widget.setCurrentIndex(self.tab_widget.indexOf(self.deleted_tab))

    def _show_selected_record_in_view_tab(self):
        selected = self.records_table.selectionModel().selectedRows();
        if not selected: return
        rrf_no = self.records_table.item(selected[0].row(), 0).text()
        self._load_and_populate_view_details(rrf_no)

    def _show_selected_deleted_record_in_view_tab(self):
        selected = self.deleted_records_table.selectionModel().selectedRows()
        if not selected: return
        rrf_no = self.deleted_records_table.item(selected[0].row(), 0).text()
        self._load_and_populate_view_details(rrf_no)
        self.tab_widget.setCurrentIndex(self.tab_widget.indexOf(self.view_details_tab))

    def _load_and_populate_view_details(self, rrf_no):
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

            # Apply comma formatting to totals
            total_items_qty = sum(Decimal(item.get('quantity', 0)) for item in items)
            self.view_items_total_label.setText(f"<b>Total Quantity: {total_items_qty:,.2f}</b>")
            total_breakdown_qty = sum(Decimal(item.get('quantity_kg', 0)) for item in breakdown)
            self.view_breakdown_total_label.setText(f"<b>Total Quantity: {total_breakdown_qty:,.2f}</b>")

        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load details for RRF {rrf_no}: {e}")

    def _add_view_detail_row(self, layout, key, value):
        display_text = str(value) if value is not None else "N/A"
        if isinstance(value, datetime):
            display_text = QDateTime(value).toString('yyyy-MM-dd hh:mm AP')
        elif isinstance(value, (QDate, date)):
            display_text = QDate(value).toString('yyyy-MM-dd')
        elif isinstance(value, (Decimal, float)):
            # Apply comma formatting for detailed float view
            display_text = f"{float(value):,.3f}"
        layout.addRow(QLabel(f"<b>{key.replace('_', ' ').title()}:</b>"), QLabel(display_text))

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
                    # Apply comma formatting
                    item_text = f"{float(value):,.2f}"
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
            self.show_notification("Item removed from list.", "info")

    def _populate_item_row(self, row, item_data):
        headers = ["quantity", "unit", "product_code", "lot_number", "reference_number", "remarks"]
        for col, header in enumerate(headers):
            value = item_data.get(header, '')
            if header == 'quantity' and isinstance(value, (float, Decimal)):
                # Store the formatted string in the table widget cell for display
                display_value = f"{float(value):,.2f}"
            else:
                display_value = str(value)

            item = QTableWidgetItem(display_value)
            if header == 'quantity':
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.items_table.setItem(row, col, item)

    def _get_item_data_from_row(self, row):
        headers = ["quantity", "unit", "product_code", "lot_number", "reference_number", "remarks"]

        data = {}
        for i, h in enumerate(headers):
            item = self.items_table.item(row, i)
            value = item.text() if item else ""

            if h == 'quantity':
                # Strip commas when extracting quantity data to pass back to dialog
                data[h] = value.replace(',', '')
            else:
                data[h] = value
        return data

    def _clear_form(self):
        # Identify the widget that triggered this method call
        sender = self.sender()

        # Clear the form state and all widgets
        self.current_editing_rrf_no = None
        self.rrf_no_edit.setText(self._generate_rrf_no())
        self.rrf_date_edit.setDate(QDate.currentDate())
        self.customer_combo.setCurrentIndex(-1)
        self.items_table.setRowCount(0)
        self._load_combobox_data()
        self.save_btn.setText(" Save")
        self.print_btn.setEnabled(False)
        self.cancel_update_btn.hide()
        self._update_item_count()
        self._on_item_selection_changed()

        # --- CORRECTED NOTIFICATION LOGIC ---
        # Only show a notification if a specific button was the sender.
        # If called from _save_record, sender() will be None, and no notification will be shown here.
        if sender == self.cancel_update_btn:
            self.show_notification("Update cancelled.", 'warning')
        elif sender == self.clear_btn:
            self.show_notification("Form cleared for new entry.", 'info')

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
        rrf_date = self.rrf_date_edit.date().toPyDate()
        material_type = self.material_type_combo.currentText()

        primary_data = {"rrf_no": rrf_no, "rrf_date": rrf_date,
                        "customer_name": self.customer_combo.currentText(),
                        "material_type": material_type, "prepared_by": self.username,
                        "encoded_by": self.username,
                        "encoded_on": datetime.now(), "edited_by": self.username, "edited_on": datetime.now()}

        # Get raw float values for database insertion
        items_data_raw = [self._get_item_data_from_row(row) for row in range(self.items_table.rowCount())]

        # Convert quantity strings (which might have been formatted when passing through dialog, but stripped
        # when retrieved) to Decimal for DB insertion.
        items_data = []
        for item in items_data_raw:
            try:
                item['quantity'] = Decimal(item['quantity'])
            except InvalidOperation:
                QMessageBox.critical(self, "Data Error", f"Invalid quantity value found: {item['quantity']}")
                return
            item['rrf_no'] = rrf_no
            items_data.append(item)

        try:
            with self.engine.connect() as conn, conn.begin():
                if self.current_editing_rrf_no:
                    # Update scenario
                    del primary_data['encoded_by'], primary_data['encoded_on']
                    conn.execute(text(
                        "UPDATE rrf_primary SET rrf_date=:rrf_date, customer_name=:customer_name, material_type=:material_type, prepared_by=:prepared_by, edited_by=:edited_by, edited_on=:edited_on WHERE rrf_no=:rrf_no"),
                        primary_data)
                    conn.execute(text("DELETE FROM rrf_items WHERE rrf_no = :rrf_no"), {"rrf_no": rrf_no})
                    log, action = "UPDATE_RRF", "updated"

                    # Delete existing base transactions related to this RRF (RRF_FG_IN/RRF_RM_OUT)
                    conn.execute(text("""
                        DELETE FROM transactions 
                        WHERE source_ref_no = :rrf_no 
                        AND transaction_type IN ('RRF_FG_IN', 'RRF_RM_OUT')
                    """), {"rrf_no": rrf_no})

                else:
                    # Insert scenario
                    conn.execute(text(
                        "INSERT INTO rrf_primary (rrf_no, rrf_date, customer_name, material_type, prepared_by, encoded_by, encoded_on, edited_by, edited_on) VALUES (:rrf_no, :rrf_date, :customer_name, :material_type, :prepared_by, :encoded_by, :encoded_on, :edited_by, :edited_on)"),
                        primary_data)
                    log, action = "CREATE_RRF", "saved"

                if items_data:
                    # Quantity is now Decimal/Float from item_data
                    conn.execute(text(
                        "INSERT INTO rrf_items (rrf_no, quantity, unit, product_code, lot_number, reference_number, remarks) VALUES (:rrf_no, :quantity, :unit, :product_code, :lot_number, :reference_number, :remarks)"),
                        items_data)

                    # --- LOG TRANSACTIONS ---
                    transaction_inserts = []
                    for item in items_data:
                        qty = item['quantity']  # Already Decimal/float

                        if material_type == "FINISHED GOOD" or material_type == "SEMI-FINISHED GOOD" or material_type == "OTHER":
                            # RRF for FG/SFG/Other means IN to inventory
                            transaction_inserts.append({
                                "transaction_date": rrf_date,
                                "transaction_type": "RRF_FG_IN",
                                "source_ref_no": rrf_no,
                                "product_code": item['product_code'],
                                "lot_number": item['lot_number'],
                                "quantity_in": qty,
                                "quantity_out": 0,
                                "unit": item['unit'],
                                "warehouse": "WH1",  # Default warehouse for RRF return
                                "encoded_by": self.username,
                                "remarks": f"RRF Return/Replacement (Material Type: {material_type})"
                            })
                        elif material_type == "RAW MATERIAL":
                            # RRF for RM means OUT of inventory (consumption/adjustment)
                            transaction_inserts.append({
                                "transaction_date": rrf_date,
                                "transaction_type": "RRF_RM_OUT",
                                "source_ref_no": rrf_no,
                                "product_code": item['product_code'],
                                "lot_number": item['lot_number'],
                                "quantity_in": 0,
                                "quantity_out": qty,
                                "unit": item['unit'],
                                "warehouse": "WH1",  # Default warehouse for RRF consumption
                                "encoded_by": self.username,
                                "remarks": f"RRF Return/Replacement Consumption (Material Type: {material_type})"
                            })

                    if transaction_inserts:
                        conn.execute(text("""
                            INSERT INTO transactions (
                                transaction_date, transaction_type, source_ref_no, product_code,
                                lot_number, quantity_in, quantity_out, unit, warehouse, encoded_by, remarks
                            ) VALUES (
                                :transaction_date, :transaction_type, :source_ref_no, :product_code,
                                :lot_number, :quantity_in, :quantity_out, :unit, :warehouse, :encoded_by, :remarks
                            )
                        """), transaction_inserts)

                    # --- END LOG TRANSACTIONS ---

                new_units = {item['unit'] for item in items_data if item['unit']}
                if new_units:
                    insert_stmt = text("INSERT INTO units (name) VALUES (:name) ON CONFLICT(name) DO NOTHING")
                    conn.execute(insert_stmt, [{"name": unit} for unit in new_units])

                self.log_audit_trail(log, f"RRF: {rrf_no}")

            self.show_notification(f"RRF {rrf_no} has been {action}.", 'success')
            self._clear_form();
            self._refresh_all_data_views()
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"An error occurred: {e}")
            self.show_notification("Error saving RRF. See dialog for details.", 'error')

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
            self.save_btn.setText(" Update");
            self.print_btn.setEnabled(True)
            self.cancel_update_btn.show()
            self.tab_widget.setCurrentIndex(self.tab_widget.indexOf(self.entry_tab))
            self.show_notification(f"RRF {rrf_no} loaded for update.", 'info')
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load RRF {rrf_no}: {e}")
            self.show_notification(f"Failed to load RRF {rrf_no}.", 'error')
            self._clear_form()

    def _delete_record(self):
        selected = self.records_table.selectionModel().selectedRows();
        if not selected: return
        rrf_no = self.records_table.item(selected[0].row(), 0).text()

        password, ok = QInputDialog.getText(self, "Admin Authentication", "Enter Admin Password:",
                                            QLineEdit.EchoMode.Password)
        if not ok: return
        if password != ADMIN_PASSWORD:
            QMessageBox.warning(self, "Authentication Failed", "Incorrect password. Deletion cancelled.")
            return

        if QMessageBox.question(self, "Confirm Deletion",
                                f"Delete RRF No: <b>{rrf_no}</b> and move it to the deleted tab?") == QMessageBox.StandardButton.Yes:
            try:
                with self.engine.connect() as conn, conn.begin():
                    # Soft delete the primary record
                    conn.execute(text(
                        "UPDATE rrf_primary SET is_deleted = TRUE, edited_by = :u, edited_on = :n WHERE rrf_no = :rrf"),
                        {"u": self.username, "n": datetime.now(), "rrf": rrf_no})

                    # Remove all associated transactions upon soft delete
                    conn.execute(text("""
                        DELETE FROM transactions 
                        WHERE source_ref_no = :rrf_no 
                        AND transaction_type IN ('RRF_FG_IN', 'RRF_RM_OUT', 'RRF_BREAKDOWN_OUT')
                    """), {"rrf_no": rrf_no})

                self.log_audit_trail("DELETE_RRF", f"Soft-deleted RRF: {rrf_no} and removed transactions.")
                self.show_notification(f"RRF {rrf_no} moved to Deleted tab.", 'success')

                # FIX: Clear deleted search box and refresh views immediately
                self.deleted_search_edit.clear()
                self._refresh_all_data_views()

            except Exception as e:
                QMessageBox.critical(self, "Database Error", f"Could not delete record: {e}")
                self.show_notification(f"Error deleting RRF {rrf_no}.", 'error')

    def _load_all_records(self):
        offset = (self.current_page - 1) * self.records_per_page
        try:
            with self.engine.connect() as conn:
                filter_clause = "";
                params = {'limit': self.records_per_page, 'offset': offset}
                search = f"%{self.search_edit.text()}%"

                # Dynamic filtering for pagination count
                if self.search_edit.text():
                    count_query_sql = f"""
                         SELECT COUNT(DISTINCT p.rrf_no) 
                         FROM rrf_primary p 
                         LEFT JOIN rrf_items i ON p.rrf_no = i.rrf_no 
                         WHERE p.is_deleted IS NOT TRUE 
                           AND (p.rrf_no ILIKE :st OR p.customer_name ILIKE :st OR i.product_code ILIKE :st)
                     """
                    count_res = conn.execute(text(count_query_sql), {'st': search}).scalar_one()
                    filter_clause = " AND (p.rrf_no ILIKE :st OR p.customer_name ILIKE :st OR i.product_code ILIKE :st)"
                    params['st'] = search
                else:
                    count_res = conn.execute(
                        text(f"SELECT COUNT(rrf_no) FROM rrf_primary WHERE is_deleted IS NOT TRUE")).scalar_one()

                self.total_records = count_res

                query = text(f"""
                    SELECT p.rrf_no, p.rrf_date, p.customer_name, p.material_type,
                           STRING_AGG(DISTINCT i.product_code, ', ') as product_codes, SUM(i.quantity) as total_quantity
                    FROM rrf_primary p LEFT JOIN rrf_items i ON p.rrf_no = i.rrf_no
                    WHERE p.is_deleted IS NOT TRUE {filter_clause}
                    GROUP BY p.rrf_no, p.rrf_date, p.customer_name, p.material_type
                    ORDER BY CAST(p.rrf_no AS INTEGER) DESC LIMIT :limit OFFSET :offset
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
                    # Apply comma formatting
                    display_value = f"{float(value):,.2f}"
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
        menu = QMenu()
        view_action = menu.addAction(fa.icon('fa5s.eye', color=COLOR_PRIMARY), "View Details")
        print_action = menu.addAction(fa.icon('fa5s.print', color=COLOR_PRIMARY), "Print Preview")
        menu.addSeparator()
        edit_action = menu.addAction(fa.icon('fa5s.edit', color=COLOR_PRIMARY), "Edit Record")
        delete_action = menu.addAction(fa.icon('fa5s.trash-alt', color=DESTRUCTIVE_COLOR), "Delete Record")

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
                # Ensure we only fetch soft-deleted records (is_deleted = TRUE)
                query = text("""
                    SELECT rrf_no, rrf_date, customer_name, material_type, edited_by, edited_on
                    FROM rrf_primary WHERE is_deleted = TRUE
                    AND (rrf_no ILIKE :st OR customer_name ILIKE :st)
                    ORDER BY edited_on DESC
                """)
                res = conn.execute(query, {'st': search}).mappings().all()
            headers = ["RRF No.", "Date", "Customer/Supplier", "Deleted By", "Deleted On"]
            self._populate_deleted_records_table(res, headers)
            # Ensure data reflects load state
            self._on_deleted_record_selection_changed()
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
        menu = QMenu()
        restore_action = menu.addAction(fa.icon('fa5s.undo', color=COLOR_PRIMARY), "Restore Record")
        view_action = menu.addAction(fa.icon('fa5s.eye', color=COLOR_PRIMARY), "View Details")

        action = menu.exec(self.deleted_records_table.mapToGlobal(pos))
        if action == restore_action:
            self._restore_record()
        elif action == view_action:
            self._show_selected_deleted_record_in_view_tab()

    def _restore_record(self):
        selected = self.deleted_records_table.selectionModel().selectedRows()
        if not selected: return
        rrf_no = self.deleted_records_table.item(selected[0].row(), 0).text()
        password, ok = QInputDialog.getText(self, "Admin Action", "Enter password to restore:",
                                            QLineEdit.EchoMode.Password)
        if not ok: return
        if password != ADMIN_PASSWORD:
            QMessageBox.critical(self, "Access Denied", "Incorrect password.");
            return
        if QMessageBox.question(self, "Confirm Restore",
                                f"Restore RRF No: <b>{rrf_no}</b>?") == QMessageBox.StandardButton.Yes:
            try:
                with self.engine.connect() as conn, conn.begin():
                    # Restore primary record
                    conn.execute(text(
                        "UPDATE rrf_primary SET is_deleted = FALSE, edited_by = :u, edited_on = :n WHERE rrf_no = :rrf"),
                        {"u": self.username, "n": datetime.now(), "rrf": rrf_no})

                    # Fetch data needed for transaction restoration
                    primary_data = conn.execute(text("SELECT * FROM rrf_primary WHERE rrf_no = :rrf_no"),
                                                {"rrf_no": rrf_no}).mappings().one()
                    items_data = conn.execute(text("SELECT * FROM rrf_items WHERE rrf_no = :rrf_no"),
                                              {"rrf_no": rrf_no}).mappings().all()

                    material_type = primary_data.get('material_type')
                    rrf_date = primary_data.get('rrf_date')

                    transaction_inserts = []

                    # Restore base transactions (RRF_FG_IN / RRF_RM_OUT)
                    for item in items_data:
                        qty = Decimal(item.get('quantity', 0))

                        if material_type in ["FINISHED GOOD", "SEMI-FINISHED GOOD", "OTHER"]:
                            transaction_type = "RRF_FG_IN"
                            qty_in, qty_out = qty, 0
                            remarks = f"RRF Return/Replacement (Material Type: {material_type})"
                        elif material_type == "RAW MATERIAL":
                            transaction_type = "RRF_RM_OUT"
                            qty_in, qty_out = 0, qty
                            remarks = f"RRF Return/Replacement Consumption (Material Type: {material_type})"
                        else:
                            continue  # Skip unknown material types

                        transaction_inserts.append({
                            "transaction_date": rrf_date,
                            "transaction_type": transaction_type,
                            "source_ref_no": rrf_no,
                            "product_code": item['product_code'],
                            "lot_number": item['lot_number'],
                            "quantity_in": qty_in,
                            "quantity_out": qty_out,
                            "unit": item['unit'],
                            "warehouse": "WH1",
                            "encoded_by": self.username,
                            "remarks": remarks
                        })

                    # If RRF Breakdown records exist, restore RRF_BREAKDOWN_OUT transactions as well
                    breakdown_records = conn.execute(text("""
                        SELECT T1.item_id, T1.lot_number, T1.quantity_kg, T2.product_code, T2.unit
                        FROM rrf_lot_breakdown T1
                        JOIN rrf_items T2 ON T1.rrf_no = T2.rrf_no AND T1.item_id = T2.id
                        WHERE T1.rrf_no = :rrf_no
                    """), {"rrf_no": rrf_no}).mappings().all()

                    remark_base = f"Generated from RRF {rrf_no}"
                    for rec in breakdown_records:
                        transaction_inserts.append({
                            "transaction_date": rrf_date,
                            "transaction_type": "RRF_BREAKDOWN_OUT",
                            "source_ref_no": rrf_no,
                            "product_code": rec['product_code'],
                            "lot_number": rec['lot_number'],
                            "quantity_in": 0,
                            "quantity_out": rec['quantity_kg'],
                            "unit": rec['unit'],
                            "warehouse": "WH1",  # Default to WH1 if original location isn't stored in breakdown table
                            "encoded_by": self.username,
                            "remarks": f"{remark_base} (Item {rec['item_id']})"
                        })

                    if transaction_inserts:
                        conn.execute(text("""
                            INSERT INTO transactions (
                                transaction_date, transaction_type, source_ref_no, product_code,
                                lot_number, quantity_in, quantity_out, unit, warehouse, encoded_by, remarks
                            ) VALUES (
                                :transaction_date, :transaction_type, :source_ref_no, :product_code,
                                :lot_number, :quantity_in, :quantity_out, :unit, :warehouse, :encoded_by, :remarks
                            )
                        """), transaction_inserts)

                self.log_audit_trail("RESTORE_RRF", f"Restored RRF: {rrf_no} and transactions.")
                self.show_notification(f"RRF {rrf_no} has been restored.", 'success')
                self._refresh_all_data_views()
            except Exception as e:
                QMessageBox.critical(self, "Database Error", f"Could not restore record: {e}")
                self.show_notification(f"Error restoring RRF {rrf_no}.", 'error')

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
        self.breakdown_location_combo.setCurrentIndex(0)

        # Reset cumulative data and display
        self.breakdown_preview_data = []  # Reset to empty list
        self.breakdown_preview_table.setRowCount(0)
        self.breakdown_total_label.setText("<b>Total: 0.00 kg</b>")
        self.show_notification("Breakdown tool cleared.", 'info')

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
        rrf_no = self.breakdown_rrf_combo.currentText()

        if self.breakdown_preview_data:
            # Check if the RRF being selected matches the RRF currently in preview
            current_rrf_in_preview = self.breakdown_preview_data[0]['rrf_no']
            if rrf_no and rrf_no != current_rrf_in_preview:
                QMessageBox.warning(self, "Clear Pending Work",
                                    "Please save or clear the current preview before changing the RRF Number.")
                # Revert to the RRF associated with the preview data
                idx = self.breakdown_rrf_combo.findText(current_rrf_in_preview, Qt.MatchFlag.MatchFixedString)
                if idx >= 0:
                    self.breakdown_rrf_combo.blockSignals(True)
                    self.breakdown_rrf_combo.setCurrentIndex(idx)
                    self.breakdown_rrf_combo.blockSignals(False)
                return

        self.breakdown_item_combo.blockSignals(True);
        self.breakdown_item_combo.clear()

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
                display_qty = f"{float(quantity):,.2f}" if quantity is not None else "0.00"
                self.breakdown_item_combo.addItem(
                    f"ID: {item['id']} - {display_qty} {item['unit']} - {item['product_code']}", userData=item)
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load items for RRF {rrf_no}: {e}")
        finally:
            self.breakdown_item_combo.blockSignals(False);
            # Trigger item selection logic after populating
            self._on_breakdown_item_selected()

    def _on_breakdown_item_selected(self):
        """
        When an RRF item is selected. We adjust the input quantity based on accumulated batches
        for this specific item ID, but keep the overall preview intact if the RRF is the same.
        """
        item_data = self.breakdown_item_combo.currentData()

        if not item_data:
            quantity = 0.0

        else:
            quantity = item_data.get('quantity', 0.0)
            item_id = item_data['id']
            rrf_no = item_data['rrf_no']

            # Check if this item selection belongs to the currently accumulated RRF (if any)
            if self.breakdown_preview_data and rrf_no != self.breakdown_preview_data[0]['rrf_no']:
                # This scenario should be caught by _on_breakdown_rrf_selected, but as a safeguard:
                QMessageBox.critical(self, "Internal Error", "RRF mismatch detected. Please clear the breakdown tool.")
                self._clear_breakdown_tool()
                return

            # Calculate accumulated quantity for THIS specific item ID only
            accumulated_for_this_item = sum(
                Decimal(i['quantity_kg'])
                for entry in self.breakdown_preview_data
                if entry['item_id'] == item_id
                for i in entry['items']
            )

            # Suggest the REMAINING quantity for breakdown, or the full quantity if nothing accumulated yet
            remaining_qty = Decimal(str(quantity)) - accumulated_for_this_item
            quantity = max(0, remaining_qty)

        self.breakdown_item_qty_display.setText(str(float(quantity)))
        self.breakdown_item_qty_display._format_text()

        self.breakdown_weight_per_lot_edit.setText("0.00")
        self.breakdown_lot_range_edit.clear()

        self._recalculate_num_lots()
        self._update_cumulative_preview()

    def _recalculate_num_lots(self):
        try:
            # Use value() method of FloatLineEdit to get the raw float
            target_qty_raw = self.breakdown_item_qty_display.value()
            target_qty = Decimal(str(target_qty_raw))

            weight_per_lot = self.breakdown_weight_per_lot_edit.value()
            weight_per_lot = Decimal(str(weight_per_lot))  # Convert float input to Decimal

            if target_qty <= 0 or weight_per_lot <= 0:
                self.breakdown_num_lots_edit.setText("0")
                return

            # Use Decimal for precise calculation
            num_lots = math.ceil(target_qty / weight_per_lot)
            self.breakdown_num_lots_edit.setText(str(int(num_lots)))
        except (ValueError, InvalidOperation):
            self.breakdown_num_lots_edit.setText("0")

    def _validate_and_calculate_breakdown(self):
        try:
            item_data = self.breakdown_item_combo.currentData()

            if not item_data:
                QMessageBox.warning(self, "Input Error", "Please select an RRF item to break down.");
                return None

            # 1. Get user-defined target quantity (the size of THIS breakdown attempt)
            target_qty_raw = self.breakdown_item_qty_display.value()
            target_qty = Decimal(str(target_qty_raw))

            # 2. Get the original item quantity for validation
            original_item_qty = Decimal(item_data.get('quantity', 0.0))

            # 3. Calculate current total quantity already in the preview list for THIS specific item
            item_id = item_data['id']
            current_preview_total_for_item = sum(
                Decimal(i['quantity_kg'])
                for entry in self.breakdown_preview_data
                if entry['item_id'] == item_id
                for i in entry['items']
            )

            weight_per_lot = self.breakdown_weight_per_lot_edit.value()
            weight_per_lot = Decimal(str(weight_per_lot))

            lot_input = self.breakdown_lot_range_edit.text().strip()
            num_lots = int(self.breakdown_num_lots_edit.text())
            location = self.breakdown_location_combo.currentText()

            # --- CUMULATIVE VALIDATION: Check total + new quantity against original ---
            if target_qty + current_preview_total_for_item > original_item_qty + Decimal('0.001'):
                QMessageBox.warning(self, "Input Error",
                                    f"Total quantity for this item ({item_id}) exceeds its limit. Accumulated: {current_preview_total_for_item:,.2f} kg. New batch: {target_qty:,.2f} kg. Original limit: {original_item_qty:,.2f} kg.")
                return None
            # ------------------------------------------------------------------------

            if self.breakdown_location_combo.currentIndex() == 0:
                QMessageBox.warning(self, "Input Error", "Please select a target warehouse.")
                return None
            if target_qty <= 0 or weight_per_lot <= 0 or num_lots <= 0:
                QMessageBox.warning(self, "Input Error",
                                    "Target quantity, weight per lot, and calculated lots must all be greater than zero.");
                return None
            if not lot_input:
                QMessageBox.warning(self, "Input Error", "Please provide a Lot Start/Range value.");
                return None

        except (ValueError, InvalidOperation, IndexError) as e:
            QMessageBox.warning(self, "Input Error", f"Please enter valid numbers for lots and weight. ({e})");
            return None

        # --- Lot list generation logic ---
        lot_list = []
        try:
            if '-' in lot_input:
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
                    start_num, suffix, num_len = int(start_match.group(1)), start_match.group(2), len(
                        start_match.group(1))
                    lot_list = [f"{str(start_num + i).zfill(num_len)}{suffix}" for i in range(num_lots)]
                else:
                    return None
        except Exception as e:
            QMessageBox.critical(self, "Lot Generation Error", f"Error generating lots: {e}");
            return None

        # Calculate quantities for THIS batch
        num_full_lots = int(target_qty // weight_per_lot)
        remainder_qty = target_qty % weight_per_lot
        breakdown_items = []

        if len(lot_list) < num_lots:
            QMessageBox.warning(self, "Mismatch Error",
                                f"The calculated number of lots ({num_lots}) exceeds the generated lot identifiers ({len(lot_list)}). Please check your range/start lot and weight.")
            return None

        for i in range(num_full_lots):
            breakdown_items.append({'lot_number': lot_list[i], 'quantity_kg': weight_per_lot})

        # Handle the remainder lot if necessary
        if remainder_qty > 0:
            if num_full_lots < len(lot_list):
                breakdown_items.append({'lot_number': lot_list[num_full_lots], 'quantity_kg': remainder_qty})
            else:
                QMessageBox.critical(self, "Calculation Error",
                                     "Lot identifier count error during remainder calculation. Please contact support.")
                return None

        # Return the structured data for THIS single batch/preview attempt
        return {
            'items': breakdown_items,
            'rrf_no': item_data['rrf_no'],
            'item_id': item_data['id'],
            'location': location,
            'product_code': item_data['product_code'],
            'unit': item_data['unit'],
            'source_qty': target_qty
        }

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

        new_batch_data = self._validate_and_calculate_breakdown()
        if not new_batch_data:
            return

        # Check for lot number duplicates across ALL batches currently in preview
        used_lot_numbers = set()
        for entry in self.breakdown_preview_data:
            for item in entry['items']:
                used_lot_numbers.add(item['lot_number'])

        for item in new_batch_data['items']:
            if item['lot_number'] in used_lot_numbers:
                QMessageBox.critical(self, "Duplicate Lot Error",
                                     f"Lot number '{item['lot_number']}' already exists in the preview list. Please choose a different lot range.")
                return

                # Append the new batch to the cumulative data list
        self.breakdown_preview_data.append(new_batch_data)

        # Update the display and total
        self._update_cumulative_preview()

        self.show_notification(
            f"Batch added to preview (Item ID {new_batch_data['item_id']}). Total accumulated batches: {len(self.breakdown_preview_data)}",
            'info')

        # Clear batch-specific input fields for the next batch entry
        # We trigger the item selection logic which handles setting the remaining quantity suggestion.
        self.breakdown_weight_per_lot_edit.setText("0.00")
        self.breakdown_lot_range_edit.clear()
        self.breakdown_num_lots_edit.setText("0")

        # Re-trigger item selection logic to update suggested quantity based on remaining amount of the currently selected item.
        self._on_breakdown_item_selected()

    def _update_cumulative_preview(self):
        """Helper to re-render the preview table based on self.breakdown_preview_data"""
        items_to_display = []
        total_preview_qty = Decimal('0.0')

        # Combine all items from all batches
        for entry in self.breakdown_preview_data:
            for item in entry['items']:
                items_to_display.append({
                    'rrf_no': entry['rrf_no'],
                    'item_id': entry['item_id'],
                    'lot_number': item['lot_number'],
                    'quantity_kg': item['quantity_kg'],
                    'location': entry['location']
                })
                total_preview_qty += item['quantity_kg']

        # Populate the table with all accumulated entries
        headers = ["RRF No", "Item ID", "Lot Number", "Quantity (kg)", "Warehouse"]
        self._populate_preview_table_cumulative(items_to_display, headers)

        # Update the total label
        self.breakdown_total_label.setText(f"<b>Total: {float(total_preview_qty):,.2f} kg</b>")

    def _save_lot_breakdown(self):
        if not self.breakdown_preview_data:
            QMessageBox.warning(self, "No Preview Data", "Please generate at least one batch preview before saving.")
            return

        # Ensure all entries belong to the same RRF, and get that RRF number
        rrf_nos = {entry['rrf_no'] for entry in self.breakdown_preview_data}
        if len(rrf_nos) != 1:
            QMessageBox.critical(self, "Data Mismatch",
                                 "Internal error: Breakdown batches belong to multiple RRF numbers. Please clear the tool.")
            return

        rrf_no = rrf_nos.pop()

        # Group lots by their parent item_id
        lots_by_item_id = {}
        original_item_quantities = {}

        # 1. Gather all lots and check total quantities against original item limits
        for item_combo_idx in range(self.breakdown_item_combo.count()):
            item_data = self.breakdown_item_combo.itemData(item_combo_idx)
            if item_data and item_data['rrf_no'] == rrf_no:
                original_item_quantities[item_data['id']] = Decimal(item_data['quantity'])

        for batch in self.breakdown_preview_data:
            item_id = batch['item_id']
            if item_id not in lots_by_item_id:
                lots_by_item_id[item_id] = {'batches': [], 'cumulative_qty': Decimal('0.0')}

            lots_by_item_id[item_id]['batches'].append(batch)

            # Recalculate cumulative quantity for safety
            batch_qty = sum(item['quantity_kg'] for item in batch['items'])
            lots_by_item_id[item_id]['cumulative_qty'] += batch_qty

        # Final Check on Totals
        for item_id, data in lots_by_item_id.items():
            cumulative_qty = data['cumulative_qty']
            original_qty = original_item_quantities.get(item_id, Decimal('0.0'))

            if cumulative_qty > original_qty + Decimal('0.001'):
                QMessageBox.critical(self, "Validation Error",
                                     f"Item ID {item_id} breakdown total ({cumulative_qty:,.2f} kg) exceeds its original quantity ({original_qty:,.2f} kg). Cannot save.")
                return

        total_lots = sum(data['cumulative_qty'] for data in lots_by_item_id.values())
        total_lot_count = sum(len(batch['items']) for data in lots_by_item_id.values() for batch in data['batches'])

        reply = QMessageBox.question(self, "Confirm Save",
                                     f"This will process breakdowns for RRF <b>{rrf_no}</b> across {len(lots_by_item_id)} item(s), replacing any existing breakdown for these items. "
                                     f"Total lots generated: {total_lot_count} ({total_lots:,.2f} kg).\n\nProceed?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)

        if reply == QMessageBox.StandardButton.Cancel: return

        # Start Transaction
        try:
            with self.engine.connect() as conn, conn.begin():
                rrf_date = conn.execute(text("SELECT rrf_date FROM rrf_primary WHERE rrf_no = :rrf_no"),
                                        {"rrf_no": rrf_no}).scalar_one()

                all_breakdown_inserts = []
                all_transaction_inserts = []
                remark_base = f"Generated from RRF {rrf_no}"

                for item_id, data in lots_by_item_id.items():
                    # 0. Get Product Code and Unit from the first batch of this item for transaction logging consistency
                    if not data['batches']: continue
                    product_code = data['batches'][0]['product_code']
                    unit = data['batches'][0]['unit']

                    # 1. Delete existing records for THIS SPECIFIC ITEM ID
                    conn.execute(text("DELETE FROM rrf_lot_breakdown WHERE rrf_no = :rrf_no AND item_id = :item_id"),
                                 {"rrf_no": rrf_no, "item_id": item_id})

                    # 2. Delete old RRF_BREAKDOWN_OUT transactions for THIS SPECIFIC ITEM ID
                    specific_remark = f"{remark_base} (Item {item_id})"

                    conn.execute(text("""
                        DELETE FROM transactions
                        WHERE transaction_type = 'RRF_BREAKDOWN_OUT'
                        AND source_ref_no = :rrf_no
                        AND product_code = :pc 
                        AND remarks = :specific_remark
                    """), {"rrf_no": rrf_no, "specific_remark": specific_remark, "pc": product_code})

                    for batch in data['batches']:
                        # Insert new breakdown records
                        for rec in batch['items']:
                            all_breakdown_inserts.append({
                                'rrf_no': rrf_no,
                                'item_id': item_id,
                                'lot_number': rec['lot_number'],
                                'quantity_kg': rec['quantity_kg']
                            })

                            # Insert corresponding transactions
                            all_transaction_inserts.append({
                                "transaction_date": rrf_date,
                                "transaction_type": "RRF_BREAKDOWN_OUT",
                                "source_ref_no": rrf_no,
                                "product_code": product_code,
                                "lot_number": rec['lot_number'],
                                "quantity_in": 0,
                                "quantity_out": rec['quantity_kg'],
                                "unit": unit,
                                "warehouse": batch['location'],
                                "encoded_by": self.username,
                                "remarks": specific_remark  # Use the unique remark
                            })

                # Bulk insert operations
                if all_breakdown_inserts:
                    conn.execute(text(
                        "INSERT INTO rrf_lot_breakdown (rrf_no, item_id, lot_number, quantity_kg) VALUES (:rrf_no, :item_id, :lot_number, :quantity_kg)"),
                        all_breakdown_inserts)

                if all_transaction_inserts:
                    conn.execute(text("""
                        INSERT INTO transactions (
                            transaction_date, transaction_type, source_ref_no, product_code,
                            lot_number, quantity_in, quantity_out, unit, warehouse, encoded_by, remarks
                        ) VALUES (
                            :transaction_date, :transaction_type, :source_ref_no, :product_code,
                            :lot_number, :quantity_in, :quantity_out, :unit, :warehouse,
                            :encoded_by, :remarks
                        )
                    """), all_transaction_inserts)

            self.log_audit_trail("CREATE_RRF_BREAKDOWN",
                                 f"Saved breakdown for RRF: {rrf_no}, across {len(lots_by_item_id)} items.")
            self.show_notification(f"Lot breakdown for RRF {rrf_no} saved. Total lots: {len(all_breakdown_inserts)}",
                                   'success')
            self._clear_breakdown_tool()
            self._load_all_breakdown_records()
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Could not save breakdown: {e}")
            self.show_notification("Error saving breakdown. See dialog for details.", 'error')
            print(traceback.format_exc())

    def _populate_preview_table_cumulative(self, data, headers):
        table_widget = self.breakdown_preview_table
        table_widget.setRowCount(0);
        table_widget.setColumnCount(len(headers));
        table_widget.setHorizontalHeaderLabels(headers)
        if not data:
            table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            return

        table_widget.setRowCount(len(data));

        # Keys matching the structure built in _update_cumulative_preview
        keys = ["rrf_no", "item_id", "lot_number", "quantity_kg", "location"]

        for i, row_data in enumerate(data):
            for j, key in enumerate(keys):
                val = row_data.get(key)

                if key == 'quantity_kg' and isinstance(val, (Decimal, float)):
                    item_text = f"{float(val):,.2f}"
                else:
                    item_text = str(val or "")

                item = QTableWidgetItem(item_text)

                if key == 'quantity_kg':
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

                table_widget.setItem(i, j, item)

        table_widget.resizeColumnsToContents()
        # Set column stretch/resize modes
        table_widget.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # RRF No
        table_widget.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Item ID
        table_widget.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)  # Lot Number
        table_widget.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Quantity
        table_widget.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Warehouse

    # --- PDF GENERATION AND PRINTING (Logic Unchanged) ---
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
            # Apply comma formatting to PDF quantity display
            display_qty = f"{float(qty):,.2f}" if qty else "0.00"
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