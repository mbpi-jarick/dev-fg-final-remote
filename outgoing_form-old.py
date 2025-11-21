import sys
import traceback
import re
from datetime import datetime, date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import List, Dict, Any, Mapping

# --- PyQt6 Imports ---
from PyQt6.QtCore import Qt, QDate, QTimer, QSize
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTabWidget, QFormLayout, QLineEdit,
                             QComboBox, QDateEdit, QPushButton, QTableWidget, QTableWidgetItem,
                             QAbstractItemView, QHeaderView, QMessageBox, QHBoxLayout, QLabel,
                             QDialog, QDialogButtonBox, QInputDialog, QListWidget, QListWidgetItem,
                             QGridLayout, QGroupBox, QMenu, QSplitter, QFrame)

from PyQt6.QtGui import QDoubleValidator, QIcon, QFont

# --- Qtawesome Import ---
import qtawesome as fa

# --- Database Imports ---
from sqlalchemy import text, inspect, Engine

# --- UI CONSTANTS (Aligned with AppStyles for visual consistency) ---
PRIMARY_ACCENT_COLOR = '#007bff'
PRIMARY_ACCENT_HOVER = '#e9f0ff'
NEUTRAL_COLOR = '#6c757d'
TABLE_SELECTION_COLOR = '#3a506b'
INPUT_BACKGROUND_COLOR = '#ffffff'
BACKGROUND_CONTENT_COLOR = '#f4f7fc'
LIGHT_TEXT_COLOR = '#333333'
GROUP_BOX_HEADER_COLOR = '#f4f7fc'

# --- Icon Colors (Darker shades for visibility against light buttons) ---
COLOR_SUCCESS = '#27ae60'  # Darker green for visibility
COLOR_DANGER = '#c0392b'  # Darker red for visibility
COLOR_PRIMARY = '#2980b9'  # Darker blue for visibility
COLOR_SECONDARY = '#d35400'  # Darker orange for visibility
COLOR_MANAGEMENT = '#7d3c98'  # Darker purple for visibility
COLOR_DEFAULT = '#34495e'  # Dark grey for default icons


# --- Helper Function for Formatting Quantities ---
def format_float_with_commas(value: Any, decimals: int = 2) -> str:
    """Formats a number (float, Decimal, or string convertible to float) with comma separators."""
    if value is None or value == '':
        return f"0.{'0' * decimals}"
    try:
        if isinstance(value, str):
            # Attempt to clean potential existing commas for safe float conversion
            cleaned_value = value.replace(',', '')
            value = float(cleaned_value)
        elif isinstance(value, Decimal):
            value = float(value)

        # Format using standard locale-independent comma notation
        return f"{value:,.{decimals}f}"
    except (ValueError, TypeError):
        # Fallback if conversion fails
        return str(value)


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
        # Using a standard validator, which typically does not handle comma input directly,
        # so we rely on _format_text and value() to handle display and retrieval.
        validator = QDoubleValidator(0.0, 99999999.0, 6)
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        self.setValidator(validator)
        self.editingFinished.connect(self._format_text)
        self.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.setText("0.00")

    def _format_text(self):
        try:
            # Remove existing commas for safe float conversion
            text_cleaned = self.text().replace(',', '')
            value = float(text_cleaned or 0.0)

            # Apply comma formatting
            self.setText(format_float_with_commas(value))
        except ValueError:
            self.setText("0.00")

    def value(self) -> float:
        try:
            # Ensure commas are removed when retrieving the numerical value
            return float(self.text().replace(',', '') or 0.0)
        except ValueError:
            return 0.0


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

        # ADD ICONS (COLORED)
        add_btn = QPushButton(fa.icon('fa5s.plus', color=COLOR_SUCCESS), "Add")
        remove_btn = QPushButton(fa.icon('fa5s.trash-alt', color=COLOR_DANGER), "Remove")

        add_btn.setObjectName("PrimaryButton")
        remove_btn.setObjectName("remove_item_btn")
        button_layout.addStretch()
        button_layout.addWidget(add_btn)
        button_layout.addWidget(remove_btn)
        layout.addLayout(button_layout)
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        layout.addWidget(button_box)
        button_box.rejected.connect(self.reject)

        add_btn.clicked.connect(self._add_item)
        remove_btn.clicked.connect(self._remove_item)
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
                    item = QListWidgetItem(str(row[self.column_name]))
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


class AddItemDialog(QDialog):
    def __init__(self, parent=None, db_engine=None, data=None):
        super().__init__(parent)
        self.engine = db_engine
        self.setWindowTitle("Add/Edit Outgoing Item")
        self.setMinimumWidth(500)
        self.setModal(True)
        self.setStyleSheet(
            f"QDialog {{ background-color: {INPUT_BACKGROUND_COLOR}; }} QLabel {{ background-color: transparent; }}")

        layout = QFormLayout(self)
        self.prod_id = UpperCaseLineEdit()
        self.product_code = UpperCaseLineEdit()
        self.lot_used = UpperCaseLineEdit()

        # ADD ICON (COLORED) - Light Button Style
        self.check_inventory_btn = QPushButton(fa.icon('fa5s.search', color=COLOR_SECONDARY), "Check Stock")

        self.inventory_status_label = QLabel("Status: Awaiting check...")
        self.inventory_status_label.setStyleSheet("font-style: italic; color: #555; background-color: transparent;")

        lot_layout = QHBoxLayout()
        lot_layout.setContentsMargins(0, 0, 0, 0)
        lot_layout.addWidget(self.lot_used, 1)
        lot_layout.addWidget(self.check_inventory_btn)

        self.qty_req = FloatLineEdit()
        self.new_lot = UpperCaseLineEdit()
        self.status = QComboBox();
        self.status.addItems(["", "PASSED", "FAILED"])
        self.box_num = QComboBox(editable=True)
        self.box_num.addItems([""] + [str(i) for i in range(1, 1000)])
        self.rem_qty = FloatLineEdit()
        self.qty_prod = QComboBox(editable=True)

        self.warehouse_combo = QComboBox()

        # ADD ICON (COLORED) - Light Button Style
        manage_qty_prod_btn = QPushButton(fa.icon('fa5s.wrench', color=COLOR_DEFAULT), "Manage...")

        qty_prod_layout = QHBoxLayout()
        qty_prod_layout.setContentsMargins(0, 0, 0, 0)
        qty_prod_layout.addWidget(self.qty_prod, 1)
        qty_prod_layout.addWidget(manage_qty_prod_btn)
        manage_qty_prod_btn.clicked.connect(self._manage_qty_produced_list)

        layout.addRow("Prod'n ID:", self.prod_id)
        layout.addRow("Product Code:", self.product_code)
        layout.addRow("Lot# Used / Range:", lot_layout)
        layout.addRow("Location/Warehouse:", self.warehouse_combo)
        layout.addRow("", self.inventory_status_label)
        layout.addRow("Qty Req'd (kg):", self.qty_req)
        layout.addRow("New Lot#/Used to:", self.new_lot)
        layout.addRow("Status:", self.status)
        layout.addRow("Box#:", self.box_num)
        layout.addRow("Remaining Qty (kg):", self.rem_qty)
        layout.addRow("Qty Produced (T/M):", qty_prod_layout)

        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addRow(self.button_box)

        self.ok_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        self.ok_button.setEnabled(False)

        # Set button object names for light style application
        self.check_inventory_btn.setObjectName("SecondaryButton")
        self.ok_button.setObjectName("PrimaryButton")
        manage_qty_prod_btn.setObjectName("DefaultButton")

        self._load_qty_produced_options()
        self._load_warehouses()

        self.check_inventory_btn.clicked.connect(self._check_lot_in_inventory)
        self.lot_used.editingFinished.connect(self._check_lot_in_inventory)
        self.lot_used.textChanged.connect(self._reset_validation)

        if data:
            self.prod_id.setText(data.get('prod_id', ''))
            self.product_code.setText(data.get('product_code', ''))
            self.lot_used.setText(data.get('lot_used', ''))

            # --- APPLY COMMA FORMATTING ---
            qty_req = data.get('quantity_required_kg', 0.0)
            self.qty_req.setText(format_float_with_commas(qty_req))

            self.new_lot.setText(data.get('new_lot_details', ''))
            self.status.setCurrentText(data.get('status', ''))
            self.box_num.setCurrentText(str(data.get('box_number', '')))

            # --- APPLY COMMA FORMATTING ---
            rem_qty = data.get('remaining_quantity', 0.0)
            self.rem_qty.setText(format_float_with_commas(rem_qty))

            self.qty_prod.setCurrentText(data.get('quantity_produced', ''))
            self.warehouse_combo.setCurrentText(data.get('warehouse', ''))
            if self.lot_used.text():
                self._check_lot_in_inventory()

    def accept(self):
        qty_req = self.qty_req.value()
        rem_qty = self.rem_qty.value()
        if rem_qty > qty_req:
            QMessageBox.warning(self, "Validation Error", "The 'Remaining Qty' cannot be greater than the 'Qty Req'd'.")
            return
        if not self.warehouse_combo.currentText():
            QMessageBox.warning(self, "Input Error", "Please select a warehouse location.")
            return
        super().accept()

    def _load_warehouses(self):
        try:
            with self.engine.connect() as conn:
                results = conn.execute(text("SELECT name FROM warehouses ORDER BY name")).scalars().all()
            current_text = self.warehouse_combo.currentText()
            self.warehouse_combo.blockSignals(True)
            self.warehouse_combo.clear()
            self.warehouse_combo.addItems([""] + results)
            self.warehouse_combo.setCurrentText(current_text)
            self.warehouse_combo.blockSignals(False)
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load warehouses: {e}")

    def _load_qty_produced_options(self):
        try:
            with self.engine.connect() as conn:
                results = conn.execute(
                    text("SELECT value FROM outgoing_qty_produced_options ORDER BY value")).scalars().all()
            current_text = self.qty_prod.currentText()
            self.qty_prod.blockSignals(True)
            self.qty_prod.clear()
            self.qty_prod.addItems([""] + [r.upper() for r in results])
            self.qty_prod.setCurrentText(current_text)
            self.qty_prod.blockSignals(False)
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load Qty Produced options: {e}")

    def _manage_qty_produced_list(self):
        dialog = ManageListDialog(self, self.engine, "outgoing_qty_produced_options", "value",
                                  "Manage Qty Produced Options")
        dialog.exec()
        self._load_qty_produced_options()

    def get_data(self):
        return {
            "prod_id": self.prod_id.text(), "product_code": self.product_code.text(),
            "lot_used": self.lot_used.text(), "quantity_required_kg": self.qty_req.value(),
            "new_lot_details": self.new_lot.text(), "status": self.status.currentText(),
            "box_number": self.box_num.currentText(), "remaining_quantity": self.rem_qty.value(),
            "quantity_produced": self.qty_prod.currentText(),
            "warehouse": self.warehouse_combo.currentText()
        }

    def _reset_validation(self):
        self.ok_button.setEnabled(False)
        self.inventory_status_label.setText("Status: Awaiting check...")
        self.inventory_status_label.setStyleSheet("font-style: italic; color: #555; background-color: transparent;")

    def _get_lot_beginning_qty(self, conn, lot_number):
        inspector = inspect(self.engine)
        schema = inspector.default_schema_name
        all_tables = [tbl for tbl in inspector.get_table_names(schema=schema) if tbl.startswith('beginv_')]
        total_qty = Decimal('0.0')

        for tbl in all_tables:
            columns = [col['name'] for col in inspector.get_columns(tbl, schema=schema)]
            lot_col = next((c for c in columns if 'lot' in c.lower()), None)
            qty_col = next((c for c in columns if 'qty' in c.lower() or 'quantity' in c.lower()), None)
            if lot_col and qty_col:
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
        lot_number_input = self.lot_used.text().strip()
        if not lot_number_input:
            self._reset_validation()
            return

        lots_to_check = []

        # FIX: Call the parsing method from the parent widget (OutgoingFormPage)
        parse_func = getattr(self.parent(), '_parse_lot_range', None)

        if parse_func and '-' in lot_number_input:
            lots_to_check = parse_func(lot_number_input)
            if lots_to_check is None:
                return
        else:
            lots_to_check = [lot_number_input]

        total_stock = Decimal('0.0')
        try:
            with self.engine.connect() as conn:
                for lot in lots_to_check:
                    beginning = self._get_lot_beginning_qty(conn, lot)
                    additions = self._get_lot_additions_qty(conn, lot)
                    removals = self._get_lot_removals_qty(conn, lot)
                    total_stock += (Decimal(beginning) + Decimal(additions) - Decimal(removals))

            self.ok_button.setEnabled(True)
            formatted_stock = format_float_with_commas(total_stock)

            if total_stock > 0:
                label_text = f"Status: Found. Total available Qty: {formatted_stock} kg"
                if len(lots_to_check) > 1:
                    label_text += f" (from {len(lots_to_check)} lots)"
                self.inventory_status_label.setText(label_text)
                self.inventory_status_label.setStyleSheet(
                    "font-weight: bold; color: #2ecc71; background-color: transparent;")

                # --- APPLY COMMA FORMATTING TO QTY REQ ---
                self.qty_req.setText(formatted_stock)
            else:
                label_text = f"Status: WARNING - No stock found. (Total: {formatted_stock} kg)"
                if len(lots_to_check) > 1:
                    label_text += f" (from {len(lots_to_check)} lots)"
                self.inventory_status_label.setText(label_text)
                self.inventory_status_label.setStyleSheet(
                    "font-weight: bold; color: #f39c12; background-color: transparent;")

        except Exception as e:
            self.inventory_status_label.setText("Status: Error during inventory check.")
            self.inventory_status_label.setStyleSheet(
                "font-weight: bold; color: #e74c3c; background-color: transparent;")
            self.ok_button.setEnabled(False)
            QMessageBox.critical(self, "DB Error",
                                 f"An error occurred while checking inventory: {e}\n\n{traceback.format_exc()}")


class OutgoingFormPage(QWidget):
    ITEM_TABLE_HEADERS = [
        "Prod'n ID", "Product Code", "Lot# Used", "Qty Req'd", "New Lot Details",
        "Status", "Box#", "Rem. Qty", "Qty Prod.", "Warehouse"
    ]

    def __init__(self, db_engine, username, log_audit_trail_func):
        super().__init__()
        self.engine, self.username, self.log_audit_trail = db_engine, username, log_audit_trail_func
        self.current_editing_primary_id = None
        self.current_page, self.records_per_page = 1, 200
        self.total_records, self.total_pages = 0, 1
        self.init_ui()
        self._load_all_records()

    def _parse_lot_range(self, lot_input):
        """Helper method to parse lot ranges (e.g., '100A-105A') into a list of individual lot numbers.
        MOVED FROM AddItemDialog to be accessible by OutgoingFormPage for saving/restoring transactions."""
        try:
            parts = [s.strip().upper() for s in lot_input.split('-')]
            if len(parts) != 2:
                raise ValueError("Lot range must contain exactly one hyphen.")
            start_str, end_str = parts
            start_match = re.match(r'^(\d+)([A-Z]*)$', start_str)
            end_match = re.match(r'^(\d+)([A-Z]*)$', end_str)
            if not start_match or not end_match or start_match.group(2) != end_match.group(2):
                raise ValueError("Format invalid or suffixes mismatch. Expected: '100A-105A'.")

            start_num = int(start_match.group(1))
            end_num = int(end_match.group(1))
            suffix = start_match.group(2)
            num_len = len(start_match.group(1))

            if start_num > end_num:
                raise ValueError("Start lot cannot be greater than end lot.")

            return [f"{str(i).zfill(num_len)}{suffix}" for i in range(start_num, end_num + 1)]
        except Exception as e:
            QMessageBox.critical(self, "Lot Range Error", f"Could not parse lot range '{lot_input}':\n{e}")
            return None

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # MAIN HEADER
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)

        # Icon
        icon_pixmap = fa.icon('fa5s.sign-out-alt', color="#3a506b").pixmap(QSize(28, 28))
        icon_label = QLabel()
        icon_label.setPixmap(icon_pixmap)
        header_layout.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignLeft)

        # Title
        title_label = QLabel("Outgoing Form Management", objectName="PageHeader")
        title_label.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        main_layout.addWidget(header_widget)

        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)
        view_tab = QWidget()
        self.view_details_tab, self.entry_tab = QWidget(), QWidget()
        self.deleted_tab = QWidget()

        # ADD TABS WITH COLORED ICONS (Using standard COLOR_PRIMARY, COLOR_SUCCESS, etc. for icons)
        self.tab_widget.addTab(view_tab, fa.icon('fa5s.list', color=COLOR_PRIMARY), "All Outgoing")
        self.tab_widget.addTab(self.entry_tab, fa.icon('fa5s.file-alt', color=COLOR_PRIMARY), "Form Entry")
        self.tab_widget.addTab(self.view_details_tab, fa.icon('fa5s.search', color=COLOR_SECONDARY), "View Details")
        self.tab_widget.addTab(self.deleted_tab, fa.icon('fa5s.trash-restore-alt', color=COLOR_DANGER), "Deleted")

        self._setup_view_tab(view_tab)
        self._setup_entry_tab(self.entry_tab)
        self._setup_view_details_tab(self.view_details_tab)
        self._setup_deleted_tab(self.deleted_tab)

        # APPLY GLOBAL UI STYLES
        self.setStyleSheet(self._get_styles())

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

    def _get_styles(self) -> str:
        return f"""
            /* Base Widget Styles */
            QWidget {{ 
                background-color: {BACKGROUND_CONTENT_COLOR};
                color: {LIGHT_TEXT_COLOR};
                font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
            }}

            /* EXPLICITLY SET ALL LABELS TO WHITE BACKGROUND */
            QLabel {{
                background-color: {INPUT_BACKGROUND_COLOR};
                color: {LIGHT_TEXT_COLOR};
                padding: 0 4px;
            }}

            /* Header Title */
            QLabel#PageHeader {{ 
                font-size: 15pt; 
                font-weight: bold; 
                color: {"#3a506b"}; 
                background-color: transparent; /* Exception for main header area */
            }}

            /* Input Fields (QLineEdit, QDateEdit, QComboBox) */
            QLineEdit, QDateEdit, QComboBox {{
                border: 1px solid #d1d9e6; 
                padding: 8px; 
                border-radius: 5px;
                background-color: {INPUT_BACKGROUND_COLOR};
                color: {LIGHT_TEXT_COLOR};
            }}
            QLineEdit:focus, QDateEdit:focus, QComboBox:focus {{
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

            /* Instruction Box Style (Using the frame class defined locally) */
            .InstructionBox {{
                background-color: #e9f0ff; /* Light accent background */
                border: 1px solid {PRIMARY_ACCENT_COLOR};
                border-radius: 6px;
                margin-bottom: 10px;
                padding: 10px;
            }}
            .InstructionBox QLabel {{
                background-color: transparent;
                padding: 0;
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
                background-color: #f0f3f8;
                border: 1px solid #c0c0c0;
            }}

            /* Primary Button (Save/Restore) */
            QPushButton#PrimaryButton {{
                border: 1px solid {COLOR_PRIMARY}; 
                color: {COLOR_PRIMARY}; 
            }}
            QPushButton#PrimaryButton:hover {{
                background-color: #ecf0f1; 
            }}

            /* Secondary Button (Update/Fetch/Check Stock) */
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
                border: 1px solid {COLOR_DANGER}; 
                color: {COLOR_DANGER}; 
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

    def _setup_deleted_tab(self, tab):
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # INSTRUCTIONS
        instruction_frame = QFrame()
        instruction_frame.setProperty('class', 'InstructionBox')
        instruction_layout = QHBoxLayout(instruction_frame)
        instruction_label = QLabel(
            "<b>Deleted Records:</b> These are forms soft-deleted from the main view. Restoring a record re-adds its corresponding inventory transactions (stock-out) to the system."
        )
        instruction_label.setWordWrap(True)
        instruction_layout.addWidget(instruction_label)
        layout.addWidget(instruction_frame)

        controls_group = QGroupBox("Search & Restore")
        top_layout = QHBoxLayout(controls_group)

        top_layout.addWidget(QLabel("Search Deleted:"))
        self.deleted_search_edit = UpperCaseLineEdit(placeholderText="Filter deleted records...")
        top_layout.addWidget(self.deleted_search_edit, 1)

        # BUTTONS - Light Button Style
        self.deleted_refresh_btn = QPushButton(fa.icon('fa5s.sync-alt', color=COLOR_DEFAULT), "Refresh")
        self.deleted_refresh_btn.setObjectName("DefaultButton")
        self.restore_btn = QPushButton(fa.icon('fa5s.undo', color=COLOR_PRIMARY), "Restore Selected")
        self.restore_btn.setObjectName("PrimaryButton")

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
        self.deleted_records_table.customContextMenuRequested.connect(self._show_deleted_table_context_menu)
        self.deleted_records_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.deleted_records_table)

        self.deleted_search_edit.textChanged.connect(self._load_deleted_records)
        self.restore_btn.clicked.connect(self._restore_record)
        self.deleted_records_table.itemSelectionChanged.connect(self._on_deleted_record_selection_changed)
        self.deleted_refresh_btn.clicked.connect(self._load_deleted_records)
        self._on_deleted_record_selection_changed()

    def _setup_view_tab(self, tab):
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # INSTRUCTIONS
        instruction_frame = QFrame()
        instruction_frame.setProperty('class', 'InstructionBox')
        instruction_layout = QHBoxLayout(instruction_frame)
        instruction_label = QLabel(
            "<b>All Records:</b> Lists all active outgoing forms. Double-click a row or use 'Update Selected' to load a form for editing."
        )
        instruction_label.setWordWrap(True)
        instruction_layout.addWidget(instruction_label)
        layout.addWidget(instruction_frame)

        controls_group = QGroupBox("Search & Actions")
        top_layout = QHBoxLayout(controls_group)

        top_layout.addWidget(QLabel("Search:"))
        self.search_edit = UpperCaseLineEdit(placeholderText="Filter by Prod'n ID, Ref#, Activity...")
        top_layout.addWidget(self.search_edit, 1)

        # BUTTONS - Light Button Style
        self.refresh_btn = QPushButton(fa.icon('fa5s.sync-alt', color=COLOR_DEFAULT), "Refresh")
        self.refresh_btn.setObjectName("DefaultButton")
        self.update_btn = QPushButton(fa.icon('fa5s.edit', color=COLOR_PRIMARY), "Update Selected")
        self.update_btn.setObjectName("PrimaryButton")
        self.delete_btn = QPushButton(fa.icon('fa5s.trash-alt', color=COLOR_DANGER), "Delete Selected")
        self.delete_btn.setObjectName("delete_btn")

        top_layout.addWidget(self.refresh_btn)
        top_layout.addWidget(self.update_btn)
        top_layout.addWidget(self.delete_btn)
        layout.addWidget(controls_group)

        self.records_table = QTableWidget()
        self.records_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.records_table.setShowGrid(False)
        self.records_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.records_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.records_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.records_table.verticalHeader().setVisible(False)
        self.records_table.horizontalHeader().setHighlightSections(False)
        self.records_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.records_table.customContextMenuRequested.connect(self._show_records_table_context_menu)
        self.records_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.records_table)

        pagination_layout = QHBoxLayout()
        # BUTTONS - Light Button Style
        self.prev_btn = QPushButton(fa.icon('fa5s.arrow-left', color="#3a506b"), "Previous")
        self.prev_btn.setObjectName("PrimaryButton")
        self.next_btn = QPushButton(fa.icon('fa5s.arrow-right', color="#3a506b"), "Next")
        self.next_btn.setObjectName("PrimaryButton")
        self.next_btn.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        self.page_label = QLabel("Page 1 of 1")
        pagination_layout.addStretch()
        pagination_layout.addWidget(self.prev_btn)
        pagination_layout.addWidget(self.page_label)
        pagination_layout.addWidget(self.next_btn)
        pagination_layout.addStretch()
        layout.addLayout(pagination_layout)

        self.refresh_btn.clicked.connect(self._load_all_records)
        self.search_edit.textChanged.connect(self._on_search_text_changed)
        self.update_btn.clicked.connect(self._load_record_for_update)
        self.delete_btn.clicked.connect(self._delete_record)
        self.records_table.itemSelectionChanged.connect(self._on_record_selection_changed)
        self.records_table.doubleClicked.connect(self._load_record_for_update)
        self.prev_btn.clicked.connect(self._go_to_prev_page)
        self.next_btn.clicked.connect(self._go_to_next_page)
        self._on_record_selection_changed()

    def _setup_entry_tab(self, tab):
        main_layout = QVBoxLayout(tab)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # INSTRUCTIONS
        instruction_frame = QFrame()
        instruction_frame.setProperty('class', 'InstructionBox')
        instruction_layout = QHBoxLayout(instruction_frame)
        instruction_label = QLabel(
            "<b>Form Entry:</b> Enter primary form details above. Use 'Fetch Details' to pull initial item lists from Production. Use the 'Add Item' button to enter inventory lots being consumed (stock-out transactions)."
        )
        instruction_label.setWordWrap(True)
        instruction_layout.addWidget(instruction_label)
        main_layout.addWidget(instruction_frame)

        primary_group = QGroupBox("Form Details")
        primary_layout = QGridLayout(primary_group)
        self.production_form_id_combo = QComboBox()
        self.production_form_id_combo.setEditable(True)

        # BUTTONS - Light Button Style
        self.fetch_details_btn = QPushButton(fa.icon('fa5s.database', color=COLOR_SECONDARY), "Fetch Details")
        self.fetch_details_btn.setObjectName("SecondaryButton")

        self.ref_no_edit = UpperCaseLineEdit()
        self.date_out_edit = QDateEdit(calendarPopup=True, displayFormat="yyyy-MM-dd")
        self.activity_edit = UpperCaseLineEdit()
        self.released_by_combo = QComboBox(editable=True)

        prod_id_layout = QHBoxLayout()
        prod_id_layout.addWidget(self.production_form_id_combo)
        prod_id_layout.addWidget(self.fetch_details_btn)

        # BUTTONS - Light Button Style
        self.manage_releasers_btn = QPushButton(fa.icon('fa5s.users', color=COLOR_DEFAULT), "Manage...")
        self.manage_releasers_btn.setObjectName("DefaultButton")

        released_by_layout = QHBoxLayout()
        released_by_layout.setContentsMargins(0, 0, 0, 0)
        released_by_layout.addWidget(self.released_by_combo, 1)
        released_by_layout.addWidget(self.manage_releasers_btn)

        primary_layout.addWidget(QLabel("Prod'n Form ID#/Series#:"), 0, 0)
        primary_layout.addLayout(prod_id_layout, 0, 1)
        primary_layout.addWidget(QLabel("Ref#:"), 0, 2)
        primary_layout.addWidget(self.ref_no_edit, 0, 3)
        primary_layout.addWidget(QLabel("Date Out:"), 1, 0)
        primary_layout.addWidget(self.date_out_edit, 1, 1)
        primary_layout.addWidget(QLabel("Activity:"), 2, 0)
        primary_layout.addWidget(self.activity_edit, 2, 1)
        primary_layout.addWidget(QLabel("Released By:"), 2, 2)
        primary_layout.addLayout(released_by_layout, 2, 3)
        main_layout.addWidget(primary_group)

        items_group = QGroupBox("Outgoing Items")
        items_layout = QVBoxLayout(items_group)
        self.entry_items_table = QTableWidget()
        self.entry_items_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.entry_items_table.setShowGrid(False)
        self.entry_items_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.entry_items_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.entry_items_table.setColumnCount(len(self.ITEM_TABLE_HEADERS))
        self.entry_items_table.setHorizontalHeaderLabels(self.ITEM_TABLE_HEADERS)
        self.entry_items_table.verticalHeader().setVisible(False)
        self.entry_items_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        items_layout.addWidget(self.entry_items_table)

        item_buttons_layout = QHBoxLayout()

        # BUTTONS - Light Button Style
        self.add_item_btn = QPushButton(fa.icon('fa5s.plus', color=COLOR_PRIMARY), "Add Item")
        self.add_item_btn.setObjectName("PrimaryButton")
        self.edit_item_btn = QPushButton(fa.icon('fa5s.edit', color=COLOR_SECONDARY), "Edit Selected")
        self.edit_item_btn.setObjectName("SecondaryButton")
        self.remove_item_btn = QPushButton(fa.icon('fa5s.minus', color=COLOR_DANGER), "Remove Selected")
        self.remove_item_btn.setObjectName("remove_item_btn")

        item_buttons_layout.addStretch()
        item_buttons_layout.addWidget(self.add_item_btn)
        item_buttons_layout.addWidget(self.edit_item_btn)
        item_buttons_layout.addWidget(self.remove_item_btn)
        items_layout.addLayout(item_buttons_layout)
        main_layout.addWidget(items_group, 1)

        button_layout = QHBoxLayout()
        # BUTTONS - Light Button Style
        self.save_btn = QPushButton(fa.icon('fa5s.save', color=COLOR_PRIMARY), "Save Form")
        self.save_btn.setObjectName("PrimaryButton")
        self.clear_btn = QPushButton(fa.icon('fa5s.eraser', color=COLOR_DEFAULT), "New")
        self.clear_btn.setObjectName("DefaultButton")
        self.cancel_update_btn = QPushButton(fa.icon('fa5s.times-circle', color=COLOR_DANGER), "Cancel Update")
        self.cancel_update_btn.setObjectName("delete_btn")

        button_layout.addStretch()
        button_layout.addWidget(self.cancel_update_btn)
        button_layout.addWidget(self.clear_btn)
        button_layout.addWidget(self.save_btn)
        main_layout.addLayout(button_layout)

        self.fetch_details_btn.clicked.connect(self._fetch_production_details)
        self.add_item_btn.clicked.connect(self._show_add_item_dialog)
        self.edit_item_btn.clicked.connect(self._show_edit_item_dialog)
        self.entry_items_table.doubleClicked.connect(self._show_edit_item_dialog)
        self.remove_item_btn.clicked.connect(self._remove_selected_item)
        self.save_btn.clicked.connect(self._save_form)
        self.clear_btn.clicked.connect(self._clear_form)
        self.cancel_update_btn.clicked.connect(self._clear_form)
        self.manage_releasers_btn.clicked.connect(self._manage_releasers_list)
        self._clear_form()

    def _setup_view_details_tab(self, tab):
        main_layout = QVBoxLayout(tab)
        details_group = QGroupBox("Form Details (Read-Only)")
        self.view_details_layout = QFormLayout(details_group)
        main_layout.addWidget(details_group)
        items_group = QGroupBox("Outgoing Items")
        items_layout = QVBoxLayout(items_group)
        self.view_items_table = QTableWidget()
        self.view_items_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.view_items_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.view_items_table.setShowGrid(False)
        self.view_items_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.view_items_table.verticalHeader().setVisible(False)
        self.view_items_table.horizontalHeader().setHighlightSections(False)
        self.view_items_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        items_layout.addWidget(self.view_items_table)
        main_layout.addWidget(items_group, 1)

    # --- Methods involving context menus (ADDING ICONS) ---

    def _show_records_table_context_menu(self, pos):
        if not self.records_table.selectedItems(): return
        menu = QMenu()

        view_action = menu.addAction(fa.icon('fa5s.search', color=COLOR_PRIMARY), "View Details")
        edit_action = menu.addAction(fa.icon('fa5s.edit', color=COLOR_PRIMARY), "Load for Update")
        delete_action = menu.addAction(fa.icon('fa5s.trash-alt', color=COLOR_DANGER), "Delete Record")

        action = menu.exec(self.records_table.mapToGlobal(pos))
        if action == view_action:
            self._show_selected_record_in_view_tab()
        elif action == edit_action:
            self._load_record_for_update()
        elif action == delete_action:
            self._delete_record()

    def _show_deleted_table_context_menu(self, pos):
        if not self.deleted_records_table.selectedItems(): return
        menu = QMenu()

        restore_action = menu.addAction(fa.icon('fa5s.undo', color=COLOR_PRIMARY), "Restore Record")
        view_action = menu.addAction(fa.icon('fa5s.search', color=COLOR_PRIMARY), "View Details")

        action = menu.exec(self.deleted_records_table.mapToGlobal(pos))
        if action == restore_action:
            self._restore_record()
        elif action == view_action:
            self._show_selected_deleted_record_in_view_tab()

    # --- Other necessary methods (Logic Unchanged, only adapting button icons) ---

    def _on_tab_changed(self, index):
        tab_title = self.tab_widget.tabText(index)
        if tab_title == "All Outgoing":
            self._load_all_records()
        elif tab_title == "Deleted":
            self._load_deleted_records()
        elif tab_title == "Form Entry" and not self.current_editing_primary_id:
            self._load_combobox_data()
        elif tab_title == "View Details":
            if self.records_table.selectedItems():
                self._show_selected_record_in_view_tab()
            elif self.deleted_records_table.selectedItems():
                self._show_selected_deleted_record_in_view_tab()

    def _clear_form(self):
        is_cancelling = self.current_editing_primary_id is not None
        self.current_editing_primary_id = None
        self.cancel_update_btn.hide()

        # Reset save button text and icon
        self.save_btn.setText("Save Form")
        self.save_btn.setIcon(fa.icon('fa5s.save', color=COLOR_PRIMARY))

        self.production_form_id_combo.setCurrentIndex(-1)
        self.ref_no_edit.clear()
        self.activity_edit.clear()
        self.released_by_combo.setCurrentIndex(-1)
        self.date_out_edit.setDate(QDate.currentDate())
        self.entry_items_table.setRowCount(0)
        self.production_form_id_combo.setFocus()
        self._load_combobox_data()
        sender = self.sender()
        if is_cancelling:
            self.show_notification("Update cancelled.", 'warning')
        elif sender and isinstance(sender, QPushButton):
            self.show_notification("Form cleared for new entry.", 'info')

    def _show_add_item_dialog(self):
        # When adding a new item, ensure quantities are initialized as float (0.0)
        # so they can be formatted correctly if passed into dialog data.
        dialog_data = {
            'prod_id': self.production_form_id_combo.currentText().strip(),
            'quantity_required_kg': 0.0,
            'remaining_quantity': 0.0
        }
        dialog = AddItemDialog(self, db_engine=self.engine, data=dialog_data)
        if dialog.exec(): self._add_item_to_table(dialog.get_data())

    def _show_edit_item_dialog(self):
        selected_row = self.entry_items_table.currentRow()
        if selected_row < 0:
            QMessageBox.warning(self, "Selection Error", "Please select an item to edit.")
            return

        # Need to retrieve raw numerical values from the table (by cleaning commas)
        def get_float_from_item(row, col):
            try:
                text = self.entry_items_table.item(row, col).text().replace(',', '')
                return float(text)
            except (AttributeError, ValueError):
                return 0.0

        dialog_data = {
            "prod_id": self.entry_items_table.item(selected_row, 0).text(),
            "product_code": self.entry_items_table.item(selected_row, 1).text(),
            "lot_used": self.entry_items_table.item(selected_row, 2).text(),
            "quantity_required_kg": get_float_from_item(selected_row, 3),
            "new_lot_details": self.entry_items_table.item(selected_row, 4).text(),
            "status": self.entry_items_table.item(selected_row, 5).text(),
            "box_number": self.entry_items_table.item(selected_row, 6).text(),
            "remaining_quantity": get_float_from_item(selected_row, 7),
            "quantity_produced": self.entry_items_table.item(selected_row, 8).text(),
            "warehouse": self.entry_items_table.item(selected_row, 9).text()
        }
        dialog = AddItemDialog(self, db_engine=self.engine, data=dialog_data)
        if dialog.exec(): self._update_table_row(selected_row, dialog.get_data())

    def _remove_selected_item(self):
        selected_row = self.entry_items_table.currentRow()
        if selected_row >= 0:
            self.entry_items_table.removeRow(selected_row)
            self.show_notification("Item removed from the list.", 'info')
        else:
            QMessageBox.warning(self, "Selection Error", "Please select an item to remove.")

    def _add_item_to_table(self, data):
        row_pos = self.entry_items_table.rowCount()
        self.entry_items_table.insertRow(row_pos)
        self._update_table_row(row_pos, data)

    def _update_table_row(self, row, data):
        keys = ["prod_id", "product_code", "lot_used", "quantity_required_kg", "new_lot_details", "status",
                "box_number", "remaining_quantity", "quantity_produced", "warehouse"]
        for col, key in enumerate(keys):
            value = data.get(key)

            is_qty = key in ["quantity_required_kg", "remaining_quantity"]

            if is_qty:
                # Apply comma formatting for quantities
                text_val = format_float_with_commas(value)
            else:
                # Standard conversion for non-numeric fields
                text_val = str(value or '')

            item = QTableWidgetItem(text_val)

            if is_qty:
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            self.entry_items_table.setItem(row, col, item)

    def _fetch_production_details(self):
        form_id = self.production_form_id_combo.currentText().strip()
        if not form_id: QMessageBox.warning(self, "Input Error",
                                            "Please enter a Prod'n Form ID# to fetch details."); return
        try:
            with self.engine.connect() as conn:
                query = text(
                    "SELECT prod_id, prod_code, lot_number, qty_prod FROM legacy_production WHERE prod_id = :form_id")
                results = conn.execute(query, {"form_id": form_id}).mappings().all()
            if not results:
                self.show_notification(f"No production details found for ID# {form_id}.", 'warning')
                return
            self.entry_items_table.setRowCount(0)
            for rec in results:
                # Ensure we pass the raw float/decimal value here, relying on _add_item_to_table to format it
                self._add_item_to_table({"prod_id": rec.get('prod_id'), "product_code": rec.get('prod_code'),
                                         "lot_used": rec.get('lot_number'),
                                         "quantity_required_kg": float(rec.get('qty_prod') or 0.0),
                                         "remaining_quantity": 0.0  # Default for new entry
                                         })
            self.show_notification(f"Fetched {len(results)} items for ID# {form_id}.", 'success')
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Could not fetch details: {e}")
            self.show_notification("Failed to fetch production details.", 'error')

    def _refresh_all_data_views(self):
        self._load_all_records()
        self._load_deleted_records()

    def _save_form(self):
        primary_data = {
            "id": self.current_editing_primary_id,
            "production_form_id": self.production_form_id_combo.currentText().strip(),
            "ref_no": self.ref_no_edit.text().strip(), "date_out": self.date_out_edit.date().toPyDate(),
            "activity": self.activity_edit.text().strip(), "released_by": self.released_by_combo.currentText(),
            "user": self.username
        }
        if not all([primary_data['production_form_id'], primary_data['ref_no'], primary_data['released_by']]):
            QMessageBox.warning(self, "Input Error", "Prod'n Form ID#, Ref#, and Released By are required fields.")
            return
        items_data = []
        for row in range(self.entry_items_table.rowCount()):
            def parse_qty_from_table(col_index):
                try:
                    text = self.entry_items_table.item(row, col_index).text().replace(',', '')
                    return float(text)
                except (AttributeError, ValueError):
                    return 0.0

            items_data.append({
                "prod_id": self.entry_items_table.item(row, 0).text(),
                "product_code": self.entry_items_table.item(row, 1).text(),
                "lot_used": self.entry_items_table.item(row, 2).text(),
                "quantity_required_kg": parse_qty_from_table(3),
                "new_lot_details": self.entry_items_table.item(row, 4).text(),
                "status": self.entry_items_table.item(row, 5).text(),
                "box_number": self.entry_items_table.item(row, 6).text(),
                "remaining_quantity": parse_qty_from_table(7),
                "quantity_produced": self.entry_items_table.item(row, 8).text(),
                "warehouse": self.entry_items_table.item(row, 9).text()
            })
        try:
            with self.engine.connect() as conn, conn.begin():
                if self.current_editing_primary_id:
                    primary_sql = text(
                        "UPDATE outgoing_records_primary SET production_form_id=:production_form_id, ref_no=:ref_no, date_out=:date_out, activity=:activity, released_by=:released_by, edited_by=:user, edited_on=NOW() WHERE id=:id RETURNING id;")
                    primary_id = conn.execute(primary_sql, primary_data).scalar_one()
                    conn.execute(text("DELETE FROM outgoing_records_items WHERE primary_id = :id"), {"id": primary_id})
                    action, log_action = "updated", "UPDATE_OUTGOING_FORM"
                else:
                    primary_sql = text(
                        "INSERT INTO outgoing_records_primary (production_form_id, ref_no, date_out, activity, released_by, encoded_by, encoded_on, edited_by, edited_on) VALUES (:production_form_id, :ref_no, :date_out, :activity, :released_by, :user, NOW(), :user, NOW()) RETURNING id;")
                    primary_id = conn.execute(primary_sql, primary_data).scalar_one()
                    action, log_action = "saved", "CREATE_OUTGOING_FORM"

                if items_data:
                    for item in items_data: item['primary_id'] = primary_id
                    items_sql = text(
                        "INSERT INTO outgoing_records_items (primary_id, prod_id, product_code, lot_used, quantity_required_kg, new_lot_details, status, box_number, remaining_quantity, quantity_produced, warehouse) VALUES (:primary_id, :prod_id, :product_code, :lot_used, :quantity_required_kg, :new_lot_details, :status, :box_number, :remaining_quantity, :quantity_produced, :warehouse)")
                    conn.execute(items_sql, items_data)

                # --- TRANSACTION HANDLING (MODIFIED) ---
                ref_no = f"OF-{primary_id}"
                if self.current_editing_primary_id:
                    conn.execute(text(
                        "DELETE FROM transactions WHERE transaction_type = 'OUTGOING_FORM' AND source_ref_no = :ref"),
                        {"ref": ref_no})
                    conn.execute(text(
                        "DELETE FROM failed_transactions WHERE transaction_type = 'OUTGOING_FORM' AND source_ref_no = :ref"),
                        {"ref": ref_no})

                transaction_records = []
                failed_transaction_records = []

                for item in items_data:
                    lot_used_input = item['lot_used']

                    # FIX: Calling self._parse_lot_range, which is now correctly defined here.
                    lots_to_process = self._parse_lot_range(lot_used_input) if '-' in lot_used_input else [
                        lot_used_input]

                    if lots_to_process is None:
                        raise ValueError(f"Invalid lot range format for '{lot_used_input}'. Cannot save.")
                    if not lots_to_process or item['quantity_required_kg'] <= 0:
                        continue

                    qty_per_lot = Decimal(item['quantity_required_kg']) / Decimal(len(lots_to_process))
                    for single_lot in lots_to_process:
                        record_data = {
                            "transaction_date": primary_data["date_out"], "transaction_type": "OUTGOING_FORM",
                            "source_ref_no": ref_no, "product_code": item["product_code"],
                            "lot_number": single_lot, "quantity_in": 0,
                            "quantity_out": qty_per_lot.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP),
                            "unit": "KG.", "warehouse": item["warehouse"], "encoded_by": self.username,
                        }
                        if item['status'] == 'FAILED':
                            record_data[
                                "remarks"] = f"FAILED - Outgoing Form {primary_data['ref_no']}: For activity {primary_data['activity']}"
                            failed_transaction_records.append(record_data)
                        else:
                            record_data[
                                "remarks"] = f"Outgoing Form {primary_data['ref_no']}: Consumed for activity {primary_data['activity']}"
                            transaction_records.append(record_data)

                if transaction_records:
                    conn.execute(text("""
                        INSERT INTO transactions (transaction_date, transaction_type, source_ref_no, product_code, 
                            lot_number, quantity_in, quantity_out, unit, warehouse, encoded_by, remarks) 
                        VALUES (:transaction_date, :transaction_type, :source_ref_no, :product_code, 
                            :lot_number, :quantity_in, :quantity_out, :unit, :warehouse, :encoded_by, :remarks)
                    """), transaction_records)

                if failed_transaction_records:
                    conn.execute(text("""
                        INSERT INTO failed_transactions (transaction_date, transaction_type, source_ref_no, product_code, 
                            lot_number, quantity_in, quantity_out, unit, warehouse, encoded_by, remarks) 
                        VALUES (:transaction_date, :transaction_type, :source_ref_no, :product_code, 
                            :lot_number, :quantity_in, :quantity_out, :unit, :warehouse, :encoded_by, :remarks)
                    """), failed_transaction_records)

                self.log_audit_trail(log_action,
                                     f"{action.capitalize()} form with Prod'n ID: {primary_data['production_form_id']}")
                self.show_notification(f"Form has been {action} successfully.", 'success')

                self.current_editing_primary_id = None
                self._clear_form()
                self._refresh_all_data_views()

        except Exception as e:
            QMessageBox.critical(self, "Database Error",
                                 f"An error occurred while saving: {e}\n\n{traceback.format_exc()}")
            self.show_notification("Error saving form. See dialog for details.", 'error')

    def _load_record_for_update(self):
        row = self.records_table.currentRow()
        if row < 0: return
        primary_id = int(self.records_table.item(row, 0).text())
        try:
            with self.engine.connect() as conn:
                primary_rec = conn.execute(text("SELECT * FROM outgoing_records_primary WHERE id = :id"),
                                           {"id": primary_id}).mappings().first()
                item_recs = conn.execute(
                    text("SELECT * FROM outgoing_records_items WHERE primary_id = :id ORDER BY id"),
                    {"id": primary_id}).mappings().all()
            self._clear_form()
            self.current_editing_primary_id = primary_id
            self.production_form_id_combo.setCurrentText(primary_rec['production_form_id'])
            self.ref_no_edit.setText(primary_rec.get('ref_no', ''))
            self.date_out_edit.setDate(QDate(primary_rec['date_out']))
            self.activity_edit.setText(primary_rec.get('activity', ''))
            self.released_by_combo.setCurrentText(primary_rec.get('released_by', ''))
            self.entry_items_table.setRowCount(0)

            # Use raw data from DB to populate the table (which handles formatting internally)
            for item in item_recs: self._add_item_to_table(item)

            # Update Save button text and icon for update context
            self.save_btn.setText("Update Form")
            self.save_btn.setIcon(fa.icon('fa5s.edit', color=COLOR_PRIMARY))

            self.cancel_update_btn.show()
            self.tab_widget.setCurrentWidget(self.entry_tab)
            self.show_notification(f"Record #{primary_id} loaded for update.", 'info')
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load record for update: {e}")
            self.show_notification(f"Failed to load record #{primary_id} for update.", 'error')
            self._clear_form()

    def _manage_releasers_list(self):
        dialog = ManageListDialog(self, self.engine, "outgoing_releasers", "name", "Manage Releasers")
        dialog.exec()
        self._load_combobox_data()
        self.show_notification("Releasers list updated.", 'info')

    def _load_combobox_data(self):
        try:
            with self.engine.connect() as conn:
                releasers = conn.execute(text("SELECT name FROM outgoing_releasers ORDER BY name")).scalars().all()
                prod_ids_from_db = conn.execute(text(
                    "SELECT DISTINCT prod_id FROM legacy_production WHERE prod_id IS NOT NULL AND prod_id != ''")).scalars().all()

            def sort_key(item):
                try:
                    return int(item)
                except (ValueError, TypeError):
                    return -1

            prod_ids = sorted(prod_ids_from_db, key=sort_key, reverse=True)
            current_releaser = self.released_by_combo.currentText()
            self.released_by_combo.blockSignals(True)
            self.released_by_combo.clear()
            self.released_by_combo.addItems([""] + releasers)
            self.released_by_combo.setCurrentText(current_releaser)
            self.released_by_combo.blockSignals(False)
            current_prod_id = self.production_form_id_combo.currentText()
            self.production_form_id_combo.blockSignals(True)
            self.production_form_id_combo.clear()
            self.production_form_id_combo.addItems([""] + prod_ids)
            self.production_form_id_combo.setCurrentText(current_prod_id)
            self.production_form_id_combo.blockSignals(False)
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load dropdown data: {e}")
            self.show_notification("Failed to load dropdown data.", 'error')

    def _on_search_text_changed(self, text):
        self.current_page = 1
        self._load_all_records()

    def _go_to_prev_page(self):
        if self.current_page > 1: self.current_page -= 1; self._load_all_records()

    def _go_to_next_page(self):
        if self.current_page < self.total_pages: self.current_page += 1; self._load_all_records()

    def _update_pagination_controls(self):
        self.total_pages = (self.total_records + self.records_per_page - 1) // self.records_per_page or 1
        self.page_label.setText(f"Page {self.current_page} of {self.total_pages}")
        self.prev_btn.setEnabled(self.current_page > 1)
        self.next_btn.setEnabled(self.current_page < self.total_pages)

    def _on_record_selection_changed(self):
        is_selected = bool(self.records_table.selectionModel().selectedRows())
        self.update_btn.setEnabled(is_selected)
        self.delete_btn.setEnabled(is_selected)
        self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.view_details_tab), is_selected)
        if not is_selected and self.tab_widget.currentIndex() == self.tab_widget.indexOf(self.view_details_tab):
            self.tab_widget.setCurrentIndex(0)

    def _on_deleted_record_selection_changed(self):
        is_selected = bool(self.deleted_records_table.selectionModel().selectedRows())
        self.restore_btn.setEnabled(is_selected)
        self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.view_details_tab), is_selected)

    def _load_all_records(self):
        search_term = self.search_edit.text().strip()
        base_query = "FROM outgoing_records_primary WHERE is_deleted IS NOT TRUE"
        params = {}
        if search_term:
            base_query += " AND (production_form_id ILIKE :term OR ref_no ILIKE :term OR activity ILIKE :term)"
            params['term'] = f"%{search_term}%"
        try:
            with self.engine.connect() as conn:
                count_query = text(f"SELECT COUNT(*) {base_query}")
                self.total_records = conn.execute(count_query, params).scalar_one()
                offset = (self.current_page - 1) * self.records_per_page
                data_query = text(
                    f"SELECT id, production_form_id, ref_no, date_out, activity, released_by, edited_on {base_query} ORDER BY id DESC LIMIT :limit OFFSET :offset")
                params['limit'], params['offset'] = self.records_per_page, offset
                results = conn.execute(data_query, params).mappings().all()
            headers = ["ID", "Prod'n Form ID#", "Ref#", "Date Out", "Activity", "Released By", "Last Edited"]
            self._populate_records_table(self.records_table, headers, results)
            self._update_pagination_controls()
            self._on_record_selection_changed()
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Failed to load records: {e}")
            self.show_notification("Failed to load outgoing records.", 'error')

    def _populate_records_table(self, table, headers, data):
        table.setRowCount(0)
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        if not data: return
        table.setRowCount(len(data))
        keys = list(data[0].keys())
        for row_idx, record in enumerate(data):
            for col_idx, key in enumerate(keys):
                val = record.get(key)
                text_val = val.strftime('%Y-%m-%d %H:%M') if isinstance(val, datetime) else str(val or '')
                table.setItem(row_idx, col_idx, QTableWidgetItem(text_val))
        table.hideColumn(0)

    def _show_selected_record_in_view_tab(self):
        row = self.records_table.currentRow()
        if row < 0: return
        primary_id = int(self.records_table.item(row, 0).text())
        self._populate_view_details_tab(primary_id)
        self.tab_widget.setCurrentWidget(self.view_details_tab)

    def _show_selected_deleted_record_in_view_tab(self):
        row = self.deleted_records_table.currentRow()
        if row < 0: return
        primary_id = int(self.deleted_records_table.item(row, 0).text())
        self._populate_view_details_tab(primary_id)
        self.tab_widget.setCurrentWidget(self.view_details_tab)

    def _populate_view_details_tab(self, primary_id):
        try:
            with self.engine.connect() as conn:
                primary = conn.execute(text("SELECT * FROM outgoing_records_primary WHERE id = :id"),
                                       {"id": primary_id}).mappings().first()
                if not primary: QMessageBox.warning(self, "Not Found", "The selected record was not found."); return
                items = conn.execute(text("SELECT * FROM outgoing_records_items WHERE primary_id = :id ORDER BY id"),
                                     {"id": primary_id}).mappings().all()
            while self.view_details_layout.count(): self.view_details_layout.takeAt(0).widget().deleteLater()
            edited_on = primary.get('edited_on')
            last_edited_text = "N/A"
            if edited_on: last_edited_text = f"{primary.get('edited_by', 'Unknown')} on {edited_on.strftime('%Y-%m-%d %H:%M')}"
            details_map = {"Prod'n Form ID#:": primary.get('production_form_id', ''),
                           "Ref#:": primary.get('ref_no', ''), "Date Out:": str(primary.get('date_out', '')),
                           "Activity:": primary.get('activity', ''), "Released By:": primary.get('released_by', ''),
                           "Last Edited:": last_edited_text}
            for label, value in details_map.items(): self.view_details_layout.addRow(QLabel(f"<b>{label}</b>"),
                                                                                     QLabel(str(value or '')))
            self.view_items_table.setRowCount(0)
            self.view_items_table.setColumnCount(len(self.ITEM_TABLE_HEADERS))
            self.view_items_table.setHorizontalHeaderLabels(self.ITEM_TABLE_HEADERS)
            if items:
                self.view_items_table.setRowCount(len(items))
                item_keys = ['prod_id', 'product_code', 'lot_used', 'quantity_required_kg', 'new_lot_details', 'status',
                             'box_number', 'remaining_quantity', 'quantity_produced', 'warehouse']
                for row_idx, record in enumerate(items):
                    for col_idx, key in enumerate(item_keys):
                        value = record.get(key, '')

                        is_qty = key in ["quantity_required_kg", "remaining_quantity"]

                        if is_qty:
                            # Apply comma formatting for display
                            text_val = format_float_with_commas(value)
                        else:
                            text_val = str(value or '')

                        item = QTableWidgetItem(text_val)

                        if is_qty:
                            item.setTextAlignment(
                                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

                        self.view_items_table.setItem(row_idx, col_idx, item)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load details:\n{e}\n\n{traceback.format_exc()}")
            self.show_notification(f"Error loading details for record #{primary_id}.", 'error')

    def _delete_record(self):
        row = self.records_table.currentRow()
        if row < 0: return
        primary_id = int(self.records_table.item(row, 0).text())
        prod_id = self.records_table.item(row, 1).text()
        password, ok = QInputDialog.getText(self, "Admin Authentication", "Enter Admin Password:",
                                            QLineEdit.EchoMode.Password)
        if not ok: return
        if password != "ADMIN_PASSWORD":
            QMessageBox.warning(self, "Authentication Failed", "Incorrect password. Deletion cancelled.")
            return
        reply = QMessageBox.question(self, "Confirm Deletion",
                                     f"Are you sure you want to delete form with Prod'n ID <b>{prod_id}</b>?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                with self.engine.connect() as conn, conn.begin():
                    conn.execute(text(
                        "UPDATE outgoing_records_primary SET is_deleted = TRUE, edited_by = :user, edited_on = NOW() WHERE id = :id"),
                        {"id": primary_id, "user": self.username})

                    ref_no = f"OF-{primary_id}"
                    # MODIFIED: Delete from both transaction tables
                    conn.execute(text(
                        "DELETE FROM transactions WHERE transaction_type = 'OUTGOING_FORM' AND source_ref_no = :ref"),
                        {"ref": ref_no})
                    conn.execute(text(
                        "DELETE FROM failed_transactions WHERE transaction_type = 'OUTGOING_FORM' AND source_ref_no = :ref"),
                        {"ref": ref_no})

                self.log_audit_trail("DELETE_OUTGOING_FORM",
                                     f"Soft-deleted form {prod_id} and its inventory transactions")
                self.show_notification(f"Form {prod_id} moved to Deleted Records.", 'success')
                self._refresh_all_data_views()
            except Exception as e:
                QMessageBox.critical(self, "Database Error", f"Failed to delete record: {e}")
                self.show_notification("Error deleting record. See dialog for details.", 'error')

    def _restore_record(self):
        row = self.deleted_records_table.currentRow()
        if row < 0: return
        primary_id = int(self.deleted_records_table.item(row, 0).text())
        prod_id = self.deleted_records_table.item(row, 1).text()
        reply = QMessageBox.question(self, "Confirm Restore",
                                     f"Are you sure you want to restore form with Prod'n ID <b>{prod_id}</b>?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                with self.engine.connect() as conn, conn.begin():
                    conn.execute(text(
                        "UPDATE outgoing_records_primary SET is_deleted = FALSE, edited_by = :user, edited_on = NOW() WHERE id = :id"),
                        {"id": primary_id, "user": self.username})
                    primary_data = conn.execute(text("SELECT * FROM outgoing_records_primary WHERE id = :id"),
                                                {"id": primary_id}).mappings().one()
                    items_data = conn.execute(text("SELECT * FROM outgoing_records_items WHERE primary_id = :id"),
                                              {"id": primary_id}).mappings().all()

                    # --- MODIFIED: Transaction handling for restore ---
                    transaction_records = []
                    failed_transaction_records = []

                    for item in items_data:
                        lot_used_input = item['lot_used']

                        # FIX: Calling self._parse_lot_range
                        lots_to_process = self._parse_lot_range(lot_used_input) if '-' in lot_used_input else [
                            lot_used_input]

                        if lots_to_process is None or not item['quantity_required_kg'] > 0:
                            continue

                        qty_per_lot = Decimal(item['quantity_required_kg']) / Decimal(len(lots_to_process))
                        for single_lot in lots_to_process:
                            record_data = {
                                "transaction_date": primary_data["date_out"], "transaction_type": "OUTGOING_FORM",
                                "source_ref_no": f"OF-{primary_id}", "product_code": item["product_code"],
                                "lot_number": single_lot, "quantity_in": 0,
                                "quantity_out": qty_per_lot.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP),
                                "unit": "KG.", "warehouse": item.get("warehouse"), "encoded_by": self.username,
                            }
                            if item['status'] == 'FAILED':
                                record_data["remarks"] = f"RESTORED FAILED - Outgoing Form {primary_data['ref_no']}"
                                failed_transaction_records.append(record_data)
                            else:
                                record_data["remarks"] = f"RESTORED - Outgoing Form {primary_data['ref_no']}"
                                transaction_records.append(record_data)

                    if transaction_records:
                        conn.execute(text("""
                            INSERT INTO transactions (transaction_date, transaction_type, source_ref_no, product_code, lot_number, 
                                quantity_in, quantity_out, unit, warehouse, encoded_by, remarks) 
                            VALUES (:transaction_date, :transaction_type, :source_ref_no, :product_code, :lot_number, 
                                :quantity_in, :quantity_out, :unit, :warehouse, :encoded_by, :remarks)
                        """), transaction_records)

                    if failed_transaction_records:
                        conn.execute(text("""
                            INSERT INTO failed_transactions (transaction_date, transaction_type, source_ref_no, product_code, lot_number, 
                                quantity_in, quantity_out, unit, warehouse, encoded_by, remarks) 
                            VALUES (:transaction_date, :transaction_type, :source_ref_no, :product_code, :lot_number, 
                                :quantity_in, :quantity_out, :unit, :warehouse, :encoded_by, :remarks)
                        """), failed_transaction_records)

                self.log_audit_trail("RESTORE_OUTGOING_FORM", f"Restored form {prod_id} and its inventory transactions")
                self.show_notification(f"Form {prod_id} has been restored.", 'success')
                self._refresh_all_data_views()
            except Exception as e:
                QMessageBox.critical(self, "Database Error", f"Failed to restore record: {e}")
                self.show_notification("Error restoring record. See dialog for details.", 'error')

    def _load_deleted_records(self):
        search_term = self.deleted_search_edit.text().strip()
        base_query = "FROM outgoing_records_primary WHERE is_deleted IS TRUE"
        params = {}
        if search_term:
            base_query += " AND (production_form_id ILIKE :term OR ref_no ILIKE :term OR activity ILIKE :term)"
            params['term'] = f"%{search_term}%"
        try:
            with self.engine.connect() as conn:
                data_query = text(
                    f"SELECT id, production_form_id, ref_no, date_out, activity, released_by, edited_on {base_query} ORDER BY id DESC")
                results = conn.execute(data_query, params).mappings().all()
            headers = ["ID", "Prod'n Form ID#", "Ref#", "Date Out", "Activity", "Released By", "Last Edited"]
            self._populate_records_table(self.deleted_records_table, headers, results)
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Failed to load deleted records: {e}")
            self.show_notification("Failed to load deleted records.", 'error')