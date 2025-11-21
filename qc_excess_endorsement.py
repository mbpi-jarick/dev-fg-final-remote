import sys
import re
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
import traceback
from typing import Any

# --- PyQt6 Imports ---
from PyQt6.QtCore import Qt, QDate, QDateTime, QSize
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QTabWidget, QFormLayout, QLineEdit, QDateEdit,
                             QPushButton, QTableWidget, QTableWidgetItem, QComboBox,
                             QAbstractItemView, QHeaderView, QMessageBox, QHBoxLayout, QLabel,
                             QGroupBox, QMenu, QDateTimeEdit, QSplitter, QGridLayout, QCheckBox,
                             QDialog, QDialogButtonBox, QInputDialog)
from PyQt6.QtGui import QDoubleValidator

# --- SQLAlchemy Imports ---
from sqlalchemy import text, create_engine, inspect

# --- Icon Library Import ---
import qtawesome as fa

# =========================================================================
# Configuration (MOCK/PLACEHOLDER)
# IMPORTANT: Replace with your actual database configuration if running
# in a real environment.
DB_CONFIG = {"host": "localhost", "port": 5432, "dbname": "your_db_name", "user": "postgres",
             "password": "your_password"}
USERNAME = "TEST_USER_QCE"
ICON_COLOR = '#1e74a8'  # Color for the header icon

# --- Style for Tab Instructions ---
INSTRUCTION_STYLE = "color: #4a4e69; background-color: #e0fbfc; border: 1px solid #c5d8e2; padding: 8px; border-radius: 4px; margin-bottom: 10px;"


def create_db_engine():
    """Placeholder function to create a SQLAlchemy engine."""
    try:
        db_url = (f"postgresql://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
                  f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}")
        engine = create_engine(db_url, pool_pre_ping=True, pool_recycle=3600)
        with engine.connect():
            print(f"Successfully connected to PostgreSQL DB.")
            return engine
    except Exception as e:
        print(f"Warning: Could not connect to configured PostgreSQL DB. Using mock SQLite in memory.")
        print(f"Error details: {e}")
        engine = create_engine("sqlite:///:memory:")
        setup_mock_schema(engine)
        return engine


def log_audit_trail_func(event, details):
    """Mock audit trail logging function."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[AUDIT] {now} | User: {USERNAME} | Event: {event} | Details: {details}")


def setup_mock_schema(engine):
    """Sets up a minimal mock schema for standalone testing."""
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE qce_endorsements_primary (
                id INTEGER PRIMARY KEY, system_ref_no TEXT UNIQUE, form_ref_no TEXT, product_code TEXT, 
                lot_number TEXT, quantity_kg NUMERIC, weight_per_lot NUMERIC, status TEXT, 
                bag_number TEXT, box_number TEXT, remarks TEXT, date_endorsed DATE, 
                endorsed_by TEXT, date_received TIMESTAMP, received_by TEXT, 
                encoded_by TEXT, encoded_on TIMESTAMP, edited_by TEXT, edited_on TIMESTAMP, 
                is_deleted BOOLEAN DEFAULT FALSE
            );
        """))
        conn.execute(text("""
            CREATE TABLE qce_endorsements_secondary (
                id INTEGER PRIMARY KEY, system_ref_no TEXT, lot_number TEXT, quantity_kg NUMERIC, 
                bag_number TEXT, box_number TEXT, remarks TEXT
            );
        """))
        conn.execute(text("""
            CREATE TABLE qce_endorsements_excess (
                id INTEGER PRIMARY KEY, system_ref_no TEXT, lot_number TEXT, quantity_kg NUMERIC, 
                bag_number TEXT, box_number TEXT, remarks TEXT
            );
        """))
        conn.execute(text(
            "CREATE TABLE transactions (id INTEGER PRIMARY KEY, source_ref_no TEXT, transaction_date DATE, transaction_type TEXT, product_code TEXT, lot_number TEXT, quantity_in NUMERIC, quantity_out NUMERIC, unit TEXT, warehouse TEXT, encoded_by TEXT, remarks TEXT);"))
        conn.execute(text(
            "CREATE TABLE failed_transactions (id INTEGER PRIMARY KEY, source_ref_no TEXT, transaction_date DATE, transaction_type TEXT, product_code TEXT, lot_number TEXT, quantity_in NUMERIC, quantity_out NUMERIC, unit TEXT, warehouse TEXT, encoded_by TEXT, remarks TEXT);"))
        conn.execute(text("CREATE TABLE qce_endorsers (name TEXT UNIQUE);"))
        conn.execute(text("CREATE TABLE qce_receivers (name TEXT UNIQUE);"))
        conn.execute(text("CREATE TABLE qce_bag_numbers (name TEXT UNIQUE);"))
        conn.execute(text("CREATE TABLE qce_box_numbers (name TEXT UNIQUE);"))
        conn.execute(text("CREATE TABLE qce_remarks (name TEXT UNIQUE);"))
        conn.execute(text("CREATE TABLE legacy_production (prod_code TEXT UNIQUE);"))
        conn.execute(text("INSERT INTO qce_endorsers (name) VALUES ('JOHN DOE') ON CONFLICT DO NOTHING;"))
        conn.execute(text("INSERT INTO legacy_production (prod_code) VALUES ('P100') ON CONFLICT DO NOTHING;"))
        conn.execute(text("INSERT INTO legacy_production (prod_code) VALUES ('P200') ON CONFLICT DO NOTHING;"))
        conn.commit()


# =========================================================================

# --- NEW: Helper Function for Formatting ---
def format_float_with_commas(value: Any, decimals: int = 2) -> str:
    """Formats a number (float, Decimal, or string convertible to float) with comma separators."""
    if value is None or value == '':
        return f"0.{'0' * decimals}"
    try:
        if isinstance(value, str):
            cleaned_value = value.replace(',', '')
            value = float(cleaned_value)
        elif isinstance(value, Decimal):
            value = float(value)

        return f"{value:,.{decimals}f}"
    except (ValueError, TypeError):
        return str(value)


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


# --- MODIFIED: Upgraded FloatLineEdit to handle commas ---
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
            text_cleaned = self.text().replace(',', '')
            value = float(text_cleaned or 0.0)
            self.setText(format_float_with_commas(value))
        except ValueError:
            self.setText("0.00")

    def value(self) -> float:
        try:
            return float(self.text().replace(',', '') or 0.0)
        except ValueError:
            return 0.0


class AddNewDialog(QDialog):
    def __init__(self, parent, title, label):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.new_value = None
        layout = QFormLayout(self)
        self.name_edit = UpperCaseLineEdit()
        layout.addRow(f"{label}:", self.name_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def accept(self):
        self.new_value = self.name_edit.text().strip()
        if not self.new_value:
            QMessageBox.warning(self, "Input Error", "Value cannot be empty.")
            return
        super().accept()


class QCExcessEndorsementPage(QWidget):
    def __init__(self, db_engine, username, log_audit_trail_func):
        super().__init__()
        self.engine, self.username, self.log_audit_trail = db_engine, username, log_audit_trail_func
        self.current_editing_ref_no = None
        self.preview_data = None
        self.current_page, self.records_per_page = 1, 200
        self.total_records, self.total_pages = 0, 1
        self.init_ui()
        self.setStyleSheet("""
            QTableWidget::item:selected {
                background-color: #3a506b;
                color: white;
            }
            QPushButton#PrimaryButton {
                background-color: #1e74a8;
                color: white;
                border: 1px solid #1e74a8;
                padding: 5px 10px;
                border-radius: 3px;
            }
            QPushButton#SecondaryButton {
                background-color: #f0f0f0;
                color: #1e74a8;
                border: 1px solid #1e74a8;
                padding: 5px 10px;
                border-radius: 3px;
            }
            QPushButton#delete_btn {
                background-color: #e63946;
                color: white;
                border: 1px solid #e63946;
                padding: 5px 10px;
                border-radius: 3px;
            }
        """)
        self._load_all_records()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        icon_label = QLabel()
        icon_pixmap = fa.icon('fa5s.plus-square', color=ICON_COLOR).pixmap(QSize(28, 28))
        icon_label.setPixmap(icon_pixmap)
        header_layout.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header_label = QLabel("QC Excess Endorsement")
        header_label.setStyleSheet(
            "font-size: 15pt; font-weight: bold; padding: 10px 0; color: #3a506b; background-color: transparent;")
        header_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header_layout.addWidget(header_label)
        header_layout.addStretch()
        main_layout.addWidget(header_widget)
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)
        self.view_tab = QWidget()
        self.view_details_tab = QWidget()
        self.entry_tab = QWidget()
        self.deleted_tab = QWidget()
        self.tab_widget.addTab(self.view_tab, fa.icon('fa5s.list', color=ICON_COLOR), "All QC Excess Endorsements")
        self.tab_widget.addTab(self.entry_tab, fa.icon('fa5s.clipboard', color=ICON_COLOR), "Endorsement Entry Form")
        self.tab_widget.addTab(self.view_details_tab, fa.icon('fa5s.search', color=ICON_COLOR),
                               "View Endorsement Details")
        self.tab_widget.addTab(self.deleted_tab, fa.icon('fa5s.trash-restore', color=ICON_COLOR), "Deleted Records")
        self._setup_view_tab(self.view_tab)
        self._setup_view_details_tab(self.view_details_tab)
        self._setup_entry_tab(self.entry_tab)
        self._setup_deleted_tab(self.deleted_tab)
        self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.view_details_tab), False)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

    def _setup_view_tab(self, tab):
        layout = QVBoxLayout(tab)
        instruction_label = QLabel(
            "<b>Instruction:</b> Use this tab to view, search, load for update, or soft-delete existing QC Excess Endorsements. Double-click a row or use 'Load for Update' to open the entry form. Select a row and switch to 'View Endorsement Details' for a breakdown."
        )
        instruction_label.setStyleSheet(INSTRUCTION_STYLE)
        layout.addWidget(instruction_label)
        controls_group = QGroupBox("Search & Actions")
        top_layout = QHBoxLayout(controls_group)
        top_layout.addWidget(QLabel("Search:"))
        self.search_edit = UpperCaseLineEdit(placeholderText="Filter by Ref No, Product Code, Lot No...")
        self.refresh_records_btn = QPushButton(fa.icon('fa5s.sync', color=ICON_COLOR), " Refresh")
        self.update_btn = QPushButton(fa.icon('fa5s.pencil-alt', color=ICON_COLOR), " Load for Update")
        self.delete_btn = QPushButton(fa.icon('fa5s.trash-alt', color='white'), " Delete Selected")
        self.update_btn.setObjectName("SecondaryButton")
        self.delete_btn.setObjectName("delete_btn")
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
        self.records_table.doubleClicked.connect(self._load_record_for_update)
        layout.addWidget(self.records_table)
        pagination_layout = QHBoxLayout()
        self.prev_btn = QPushButton(fa.icon('fa5s.chevron-left', color=ICON_COLOR), " Previous")
        self.next_btn = QPushButton(fa.icon('fa5s.chevron-right', color=ICON_COLOR), "Next ")
        self.next_btn.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
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
        self.records_table.customContextMenuRequested.connect(self._show_records_table_context_menu)
        self.records_table.itemSelectionChanged.connect(self._on_record_selection_changed)
        self.prev_btn.clicked.connect(self._go_to_prev_page)
        self.next_btn.clicked.connect(self._go_to_next_page)
        self._on_record_selection_changed()

    def _setup_deleted_tab(self, tab):
        layout = QVBoxLayout(tab)
        instruction_label = QLabel(
            "<b>Instruction:</b> Records shown here have been soft-deleted. Select a record and click 'Restore Selected' to reactivate it and re-create its corresponding inventory transactions."
        )
        instruction_label.setStyleSheet(INSTRUCTION_STYLE)
        layout.addWidget(instruction_label)
        controls_group = QGroupBox("Search & Restore")
        top_layout = QHBoxLayout(controls_group)
        self.deleted_refresh_btn = QPushButton(fa.icon('fa5s.sync', color=ICON_COLOR), " Refresh")
        self.restore_btn = QPushButton(fa.icon('fa5s.undo', color='white'), " Restore Selected")
        self.restore_btn.setObjectName("PrimaryButton")
        self.restore_btn.setEnabled(False)
        top_layout.addStretch()
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
        layout.addWidget(self.deleted_records_table)
        self.deleted_refresh_btn.clicked.connect(self._load_deleted_records)
        self.restore_btn.clicked.connect(self._restore_record)
        self.deleted_records_table.itemSelectionChanged.connect(
            lambda: self.restore_btn.setEnabled(bool(self.deleted_records_table.selectedItems())))
        self.deleted_records_table.customContextMenuRequested.connect(self._show_deleted_table_context_menu)

    def _on_record_selection_changed(self):
        is_selected = bool(self.records_table.selectionModel().selectedRows())
        self.update_btn.setEnabled(is_selected)
        self.delete_btn.setEnabled(is_selected)
        self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.view_details_tab), is_selected)
        if is_selected: self._show_selected_record_in_view_tab()
        if not is_selected and self.tab_widget.currentIndex() == self.tab_widget.indexOf(self.view_details_tab):
            self.tab_widget.setCurrentIndex(self.tab_widget.indexOf(self.view_tab))

    def _setup_view_details_tab(self, tab):
        main_layout = QVBoxLayout(tab)
        instruction_label = QLabel(
            "<b>Instruction:</b> This tab provides a read-only view of the selected endorsement from the 'All QC Excess Endorsements' tab, showing primary data and the generated Lot Breakdown and Excess Quantity details."
        )
        instruction_label.setStyleSheet(INSTRUCTION_STYLE)
        main_layout.addWidget(instruction_label)
        details_group = QGroupBox("Endorsement Details (Read-Only)")
        details_container_layout = QHBoxLayout(details_group)
        self.view_left_details_layout = QFormLayout()
        self.view_right_details_layout = QFormLayout()
        details_container_layout.addLayout(self.view_left_details_layout)
        details_container_layout.addLayout(self.view_right_details_layout)
        main_layout.addWidget(details_group)
        tables_splitter = QSplitter(Qt.Orientation.Vertical)
        breakdown_group = QGroupBox("Lot Breakdown")
        breakdown_layout = QVBoxLayout(breakdown_group)
        self.view_breakdown_table = QTableWidget()
        self.view_breakdown_table.setFocusPolicy(Qt.FocusPolicy.NoFocus);
        self.view_breakdown_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.view_breakdown_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);
        self.view_breakdown_table.verticalHeader().setVisible(False)
        self.view_breakdown_table.horizontalHeader().setHighlightSections(False);
        self.view_breakdown_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.view_breakdown_table.setShowGrid(False)
        breakdown_layout.addWidget(self.view_breakdown_table)
        self.view_breakdown_total_label = QLabel("<b>Total: 0.00 kg</b>");
        self.view_breakdown_total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        breakdown_layout.addWidget(self.view_breakdown_total_label)
        tables_splitter.addWidget(breakdown_group)
        excess_group = QGroupBox("Excess Quantity")
        excess_layout = QVBoxLayout(excess_group)
        self.view_excess_table = QTableWidget()
        self.view_excess_table.setFocusPolicy(Qt.FocusPolicy.NoFocus);
        self.view_excess_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.view_excess_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);
        self.view_excess_table.verticalHeader().setVisible(False)
        self.view_excess_table.horizontalHeader().setHighlightSections(False);
        self.view_excess_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.view_excess_table.setShowGrid(False)
        excess_layout.addWidget(self.view_excess_table)
        self.view_excess_total_label = QLabel("<b>Total: 0.00 kg</b>");
        self.view_excess_total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        excess_layout.addWidget(self.view_excess_total_label)
        tables_splitter.addWidget(excess_group)
        main_layout.addWidget(tables_splitter, 1)

    def _show_selected_record_in_view_tab(self):
        selected_rows = self.records_table.selectionModel().selectedRows()
        if not selected_rows: return
        sys_ref_no = self.records_table.item(selected_rows[0].row(), 0).text()
        try:
            with self.engine.connect() as conn:
                primary = conn.execute(text("SELECT * FROM qce_endorsements_primary WHERE system_ref_no = :ref"),
                                       {"ref": sys_ref_no}).mappings().one()
                breakdown = conn.execute(text(
                    "SELECT lot_number, quantity_kg, bag_number, box_number, remarks FROM qce_endorsements_secondary WHERE system_ref_no = :ref"),
                    {"ref": sys_ref_no}).mappings().all()
                excess = conn.execute(text(
                    "SELECT lot_number, quantity_kg, bag_number, box_number, remarks FROM qce_endorsements_excess WHERE system_ref_no = :ref"),
                    {"ref": sys_ref_no}).mappings().all()
            for layout in [self.view_left_details_layout, self.view_right_details_layout]:
                while layout.count():
                    child = layout.takeAt(0)
                    if child.widget(): child.widget().deleteLater()
            items_list = list(primary.items());
            midpoint = (len(items_list) + 1) // 2
            for key, value in items_list[:midpoint]: self._add_view_detail_row(self.view_left_details_layout, key,
                                                                               value)
            for key, value in items_list[midpoint:]: self._add_view_detail_row(self.view_right_details_layout, key,
                                                                               value)
            self._populate_view_table(self.view_breakdown_table, breakdown,
                                      ["Lot Number", "Qty (kg)", "Bag No", "Box No", "Remarks"])
            total_breakdown = sum(Decimal(d.get('quantity_kg', 0)) for d in breakdown)
            self.view_breakdown_total_label.setText(f"<b>Total: {format_float_with_commas(total_breakdown)} kg</b>")
            self._populate_view_table(self.view_excess_table, excess,
                                      ["Associated Lot", "Excess Qty (kg)", "Bag No", "Box No", "Remarks"])
            total_excess = sum(Decimal(d.get('quantity_kg', 0)) for d in excess)
            self.view_excess_total_label.setText(f"<b>Total: {format_float_with_commas(total_excess)} kg</b>")
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load details for {sys_ref_no}: {e}")

    def _add_view_detail_row(self, layout, key, value):
        display_text = str(value) if value is not None else "N/A"
        if isinstance(value, (datetime, QDateTime)):
            display_text = QDateTime(value).toString('yyyy-MM-dd hh:mm AP')
        elif isinstance(value, date):
            display_text = value.strftime('%Y-%m-%d')
        elif isinstance(value, (Decimal, float)):
            display_text = format_float_with_commas(value)
        layout.addRow(QLabel(f"<b>{key.replace('_', ' ').title()}:</b>"), QLabel(display_text))

    def _populate_view_table(self, table, data, headers):
        table.setRowCount(0);
        table.setColumnCount(len(headers));
        table.setHorizontalHeaderLabels(headers)
        if not data:
            header = table.horizontalHeader()
            if header.count() > 0: header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            return
        table.setRowCount(len(data));
        keys_in_order = list(data[0].keys())
        for i, row_data in enumerate(data):
            for j, key in enumerate(keys_in_order):
                val = row_data.get(key)
                item_text = format_float_with_commas(val) if isinstance(val, (Decimal, float)) else str(val or "")
                item = QTableWidgetItem(item_text)
                if isinstance(val, (Decimal, float)): item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(i, j, item)
        table.resizeColumnsToContents()
        table.horizontalHeader().setSectionResizeMode(len(headers) - 1, QHeaderView.ResizeMode.Stretch)

    def _show_records_table_context_menu(self, position):
        if not self.records_table.selectedItems(): return
        menu = QMenu()
        view_action = menu.addAction(fa.icon('fa5s.eye', color=ICON_COLOR), "View Details")
        edit_action = menu.addAction(fa.icon('fa5s.pencil-alt', color=ICON_COLOR), "Edit Record")
        delete_action = menu.addAction(fa.icon('fa5s.trash-alt', color='red'), "Delete Record")
        action = menu.exec(self.records_table.mapToGlobal(position))
        if action == view_action:
            self.tab_widget.setCurrentIndex(self.tab_widget.indexOf(self.view_details_tab))
        elif action == edit_action:
            self._load_record_for_update()
        elif action == delete_action:
            self._delete_record()

    def _show_deleted_table_context_menu(self, position):
        if not self.deleted_records_table.selectedItems(): return
        menu = QMenu()
        restore_action = menu.addAction(fa.icon('fa5s.undo', color=ICON_COLOR), "Restore Record")
        action = menu.exec(self.deleted_records_table.mapToGlobal(position))
        if action == restore_action:
            self._restore_record()

    def _setup_entry_tab(self, tab):
        main_splitter = QSplitter(Qt.Orientation.Horizontal);
        tab_layout = QHBoxLayout(tab);
        tab_layout.addWidget(main_splitter)
        left_widget = QWidget();
        left_layout = QVBoxLayout(left_widget);
        left_layout.setContentsMargins(0, 0, 5, 0);
        main_splitter.addWidget(left_widget)
        instruction_label = QLabel(
            "<b>Instruction:</b> Fill out all required fields (marked <b>bold</b>). If generating new lots, ensure 'Weight/Lot' is set and 'Generate new lot numbers from a range' is checked. Always click 'Preview Breakdown' before clicking 'Save Endorsement'."
        )
        instruction_label.setStyleSheet(INSTRUCTION_STYLE)
        left_layout.addWidget(instruction_label)
        details_group = QGroupBox("QC Excess Endorsement");
        grid_layout = QGridLayout(details_group)
        self.ref_no_edit = QLineEdit(readOnly=True, placeholderText="Auto-generated")
        self.form_ref_no_edit = UpperCaseLineEdit()
        self.date_endorsed_edit = QDateEdit(calendarPopup=True, displayFormat="yyyy-MM-dd")
        self.product_code_combo = QComboBox(editable=True);
        set_combo_box_uppercase(self.product_code_combo)
        self.lot_number_edit = UpperCaseLineEdit(placeholderText="E.G., 12345 or 12345-12347")
        self.is_lot_range_check = QCheckBox("Generate new lot numbers from a range")
        self.quantity_edit = FloatLineEdit();
        self.weight_per_lot_edit = FloatLineEdit()
        self.status_combo = QComboBox();
        self.status_combo.addItems(["Passed", "Failed"])
        self.bag_number_combo = QComboBox(editable=True);
        set_combo_box_uppercase(self.bag_number_combo)
        self.box_number_combo = QComboBox(editable=True)
        set_combo_box_uppercase(self.box_number_combo)
        self.remarks_combo = QComboBox(editable=True);
        set_combo_box_uppercase(self.remarks_combo)
        self.endorsed_by_combo = QComboBox(editable=True);
        set_combo_box_uppercase(self.endorsed_by_combo)
        self.received_by_combo = QComboBox(editable=True)
        set_combo_box_uppercase(self.received_by_combo)
        self.received_date_time_edit = QDateTimeEdit(calendarPopup=True, displayFormat="yyyy-MM-dd hh:mm AP")
        grid_layout.addWidget(QLabel("Reference No:"), 0, 0);
        grid_layout.addWidget(self.ref_no_edit, 0, 1)
        grid_layout.addWidget(QLabel("<b>Status:</b>"), 0, 2);
        grid_layout.addWidget(self.status_combo, 0, 3)
        grid_layout.addWidget(QLabel("<b>Form Ref No:</b>"), 1, 0);
        grid_layout.addWidget(self.form_ref_no_edit, 1, 1)
        grid_layout.addWidget(QLabel("Date Endorsed:"), 1, 2);
        grid_layout.addWidget(self.date_endorsed_edit, 1, 3)
        grid_layout.addWidget(QLabel("<b>Product Code:</b>"), 2, 0);
        grid_layout.addWidget(self.product_code_combo, 2, 1, 1, 3)
        grid_layout.addWidget(QLabel("<b>Source Lot (Reference):</b>"), 3, 0);
        grid_layout.addWidget(self.lot_number_edit, 3, 1, 1, 3)
        grid_layout.addWidget(QLabel("Total Qty (kg):"), 4, 0);
        grid_layout.addWidget(self.quantity_edit, 4, 1)
        grid_layout.addWidget(QLabel("Weight/Lot (kg):"), 4, 2);
        grid_layout.addWidget(self.weight_per_lot_edit, 4, 3)
        grid_layout.addWidget(self.is_lot_range_check, 5, 1, 1, 3)
        grid_layout.addWidget(QLabel("Bag Number:"), 6, 0);
        grid_layout.addLayout(self._create_combo_with_add("qce_bag_numbers", self.bag_number_combo), 6, 1)
        grid_layout.addWidget(QLabel("Box Number:"), 6, 2);
        grid_layout.addLayout(self._create_combo_with_add("qce_box_numbers", self.box_number_combo), 6, 3)
        grid_layout.addWidget(QLabel("Remarks:"), 7, 0);
        grid_layout.addLayout(self._create_combo_with_add("qce_remarks", self.remarks_combo), 7, 1, 1, 3)
        grid_layout.addWidget(QLabel("<b>Endorsed By:</b>"), 8, 0);
        grid_layout.addLayout(self._create_combo_with_add("qce_endorsers", self.endorsed_by_combo), 8, 1)
        grid_layout.addWidget(QLabel("<b>Received By:</b>"), 8, 2);
        grid_layout.addLayout(self._create_combo_with_add("qce_receivers", self.received_by_combo), 8, 3)
        grid_layout.addWidget(QLabel("Date/Time Received:"), 9, 0);
        grid_layout.addWidget(self.received_date_time_edit, 9, 1, 1, 3)
        grid_layout.setColumnStretch(1, 1);
        grid_layout.setColumnStretch(3, 1)
        left_layout.addWidget(details_group);
        left_layout.addStretch()
        right_widget = QWidget();
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(5, 0, 0, 0);
        main_splitter.addWidget(right_widget)
        preview_splitter = QSplitter(Qt.Orientation.Vertical)
        breakdown_group = QGroupBox("New Lot Breakdown (Preview)")
        b_layout = QVBoxLayout(breakdown_group)
        self.preview_breakdown_table = QTableWidget()
        self.preview_breakdown_table.setFocusPolicy(Qt.FocusPolicy.NoFocus);
        self.preview_breakdown_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.preview_breakdown_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);
        self.preview_breakdown_table.verticalHeader().setVisible(False)
        self.preview_breakdown_table.horizontalHeader().setHighlightSections(False);
        self.preview_breakdown_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        b_layout.addWidget(self.preview_breakdown_table)
        self.breakdown_total_label = QLabel("<b>Total: 0.00 kg</b>");
        self.breakdown_total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        b_layout.addWidget(self.breakdown_total_label)
        preview_splitter.addWidget(breakdown_group)
        excess_group = QGroupBox("New Excess Quantity (Preview)")
        e_layout = QVBoxLayout(excess_group)
        self.preview_excess_table = QTableWidget()
        self.preview_excess_table.setFocusPolicy(Qt.FocusPolicy.NoFocus);
        self.preview_excess_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.preview_excess_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);
        self.preview_excess_table.verticalHeader().setVisible(False)
        self.preview_excess_table.horizontalHeader().setHighlightSections(False);
        self.preview_excess_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        e_layout.addWidget(self.preview_excess_table)
        self.excess_total_label = QLabel("<b>Total: 0.00 kg</b>");
        self.excess_total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        e_layout.addWidget(self.excess_total_label)
        preview_splitter.addWidget(excess_group)
        right_layout.addWidget(preview_splitter)
        main_splitter.setSizes([650, 450])
        self.preview_btn = QPushButton(fa.icon('fa5s.eye', color=ICON_COLOR), " Preview Breakdown");
        self.save_btn = QPushButton(fa.icon('fa5s.save', color='white'), " Save Endorsement");
        self.clear_btn = QPushButton(fa.icon('fa5s.eraser', color=ICON_COLOR), " New");
        self.cancel_update_btn = QPushButton(fa.icon('fa5s.times', color='white'), " Cancel Update")
        self.save_btn.setObjectName("PrimaryButton");
        self.clear_btn.setObjectName("SecondaryButton");
        self.cancel_update_btn.setObjectName("delete_btn")
        button_layout = QHBoxLayout();
        button_layout.addStretch();
        button_layout.addWidget(self.cancel_update_btn)
        button_layout.addWidget(self.clear_btn);
        button_layout.addWidget(self.preview_btn);
        button_layout.addWidget(self.save_btn)
        left_layout.addLayout(button_layout)
        self.preview_btn.clicked.connect(self._preview_endorsement);
        self.save_btn.clicked.connect(self._save_record)
        self.clear_btn.clicked.connect(self._clear_form);
        self.cancel_update_btn.clicked.connect(self._clear_form)
        self._clear_form()

    def _create_combo_with_add(self, table_name, combo):
        layout = QHBoxLayout();
        layout.setContentsMargins(0, 0, 0, 0);
        layout.addWidget(combo, 1)
        add_btn = QPushButton(fa.icon('fa5s.plus-circle', color=ICON_COLOR), " Manage...");
        add_btn.clicked.connect(lambda: self._handle_add_new_record(table_name, combo))
        layout.addWidget(add_btn);
        return layout

    def _handle_add_new_record(self, table_name, combo_to_update):
        title_map = {"qce_endorsers": "Endorser", "qce_receivers": "Receiver", "qce_bag_numbers": "Bag Number",
                     "qce_box_numbers": "Box Number", "qce_remarks": "Remark"}
        title = title_map.get(table_name, "New Record")
        dialog = AddNewDialog(self, f"Add New {title}", f"{title} Name")
        if dialog.exec() and dialog.new_value:
            new_item_text = dialog.new_value
            try:
                with self.engine.connect() as conn, conn.begin():
                    conn.execute(text(f"INSERT INTO {table_name} (name) VALUES (:name) ON CONFLICT (name) DO NOTHING"),
                                 {"name": new_item_text})
                self._load_combobox_data();
                combo_to_update.setCurrentText(new_item_text)
            except Exception as e:
                QMessageBox.critical(self, "Database Error", f"Could not add new record: {e}")

    def _load_combobox_data(self):
        queries = {"endorsed_by_combo": "SELECT name FROM qce_endorsers ORDER BY name",
                   "received_by_combo": "SELECT name FROM qce_receivers ORDER BY name",
                   "bag_number_combo": "SELECT name FROM qce_bag_numbers ORDER BY name",
                   "box_number_combo": "SELECT name FROM qce_box_numbers ORDER BY name",
                   "remarks_combo": "SELECT name FROM qce_remarks ORDER BY name",
                   "product_code_combo": "SELECT DISTINCT prod_code FROM legacy_production WHERE prod_code IS NOT NULL AND prod_code != '' ORDER BY prod_code"}
        try:
            with self.engine.connect() as conn:
                for combo_name, query in queries.items():
                    combo = getattr(self, combo_name)
                    current_text = combo.currentText();
                    items = conn.execute(text(query)).scalars().all();
                    combo.clear();
                    combo.addItems([""] + items)
                    if current_text in items: combo.setCurrentText(current_text)
        except Exception as e:
            if "no such table" not in str(e).lower():
                QMessageBox.critical(self, "DB Error", f"Could not load dropdown data: {e}")

    def _on_tab_changed(self, index):
        if index == self.tab_widget.indexOf(self.view_tab):
            self._load_all_records()
        elif index == self.tab_widget.indexOf(self.entry_tab) and not self.current_editing_ref_no:
            self._load_combobox_data()
        elif index == self.tab_widget.indexOf(self.deleted_tab):
            self._load_deleted_records()

    def _clear_form(self):
        self.current_editing_ref_no = None;
        self.preview_data = None
        self.cancel_update_btn.hide();
        self.save_btn.setText("Save Endorsement")
        for w in [self.ref_no_edit, self.form_ref_no_edit, self.lot_number_edit]: w.clear()
        self._load_combobox_data()
        for c in [self.product_code_combo, self.endorsed_by_combo, self.received_by_combo, self.bag_number_combo,
                  self.box_number_combo, self.remarks_combo, self.status_combo]:
            c.setCurrentIndex(0)
            if c.isEditable(): c.clearEditText()
        for w in [self.quantity_edit, self.weight_per_lot_edit]: w.setText("0.00")
        self.date_endorsed_edit.setDate(QDate.currentDate())
        self.received_date_time_edit.setDateTime(QDateTime.currentDateTime())
        self.is_lot_range_check.setChecked(False);
        self._clear_form_previews();
        self.form_ref_no_edit.setFocus()

    def _clear_form_previews(self):
        self.preview_data = None;
        self.preview_breakdown_table.setRowCount(0);
        self.preview_excess_table.setRowCount(0)
        self.breakdown_total_label.setText("<b>Total: 0.00 kg</b>");
        self.excess_total_label.setText("<b>Total: 0.00 kg</b>")

    def _preview_endorsement(self):
        self._clear_form_previews()
        self.preview_data = self._validate_and_calculate_lots()
        if not self.preview_data: return
        self._populate_preview_widgets(self.preview_data)

    def _generate_preview_from_data(self, record_data):
        self._clear_form_previews()
        calculation_data = self._perform_lot_calculation(total_qty=record_data.get('quantity_kg', Decimal(0)),
                                                         weight_per_lot=record_data.get('weight_per_lot', Decimal(0)),
                                                         lot_input=record_data.get('lot_number', ''),
                                                         is_range='-' in record_data.get('lot_number', ''),
                                                         is_update=True)
        if calculation_data:
            self.preview_data = calculation_data
            self._populate_preview_widgets(self.preview_data)

    def _populate_preview_widgets(self, data):
        breakdown_data = [{'lot_number': lot, 'quantity_kg': data['weight_per_lot']} for lot in data['lots']]
        self._populate_preview_table(self.preview_breakdown_table, breakdown_data, ["Lot Number", "Quantity (kg)"])
        breakdown_total = data['weight_per_lot'] * len(data['lots'])
        self.breakdown_total_label.setText(f"<b>Total: {format_float_with_commas(breakdown_total)} kg</b>")
        if data['excess_qty'] > 0 and data['excess_lot_number']:
            excess_data = [{'lot_number': data['excess_lot_number'], 'quantity_kg': data['excess_qty']}]
            self._populate_preview_table(self.preview_excess_table, excess_data, ["Associated Lot", "Excess Qty (kg)"])
            self.excess_total_label.setText(f"<b>Total: {format_float_with_commas(data['excess_qty'])} kg</b>")

    def _validate_and_calculate_lots(self):
        required_fields = {"Form Ref No": self.form_ref_no_edit.text(),
                           "Product Code": self.product_code_combo.currentText(),
                           "Source Lot (Reference)": self.lot_number_edit.text(),
                           "Endorsed By": self.endorsed_by_combo.currentText(),
                           "Received By": self.received_by_combo.currentText()}
        missing_fields = [name for name, value in required_fields.items() if not value.strip()]
        if missing_fields:
            QMessageBox.warning(self, "Input Error",
                                "Please complete all required fields:\n\n- " + "\n- ".join(missing_fields))
            return None
        try:
            total_qty = self.quantity_edit.value()
            weight_per_lot = self.weight_per_lot_edit.value()
            lot_input = self.lot_number_edit.text().strip()
            if weight_per_lot <= 0 and total_qty > 0 and self.is_lot_range_check.isChecked():
                QMessageBox.warning(self, "Input Error", "Weight per Lot must be > 0 if generating from a range.");
                return None
        except (InvalidOperation, ValueError):
            QMessageBox.warning(self, "Input Error", "Invalid numbers for Quantity or Weight per Lot.");
            return None
        return self._perform_lot_calculation(Decimal(str(total_qty)), Decimal(str(weight_per_lot)), lot_input,
                                             self.is_lot_range_check.isChecked())

    def _perform_lot_calculation(self, total_qty, weight_per_lot, lot_input, is_range, is_update=False):
        lot_list, excess_qty, excess_lot_number = [], Decimal(0), None

        if is_range:
            if total_qty <= 0 or weight_per_lot <= 0:
                QMessageBox.warning(self, "Input Error", "Total Qty and Weight/Lot must be > 0 for range generation.")
                return None

            lot_list = self._parse_lot_range(lot_input)
            if lot_list is None: return None  # Error message handled in parsing function

            num_full_lots = len(lot_list)
            total_from_lots = weight_per_lot * num_full_lots

            if total_from_lots > total_qty:
                QMessageBox.warning(self, "Calculation Error",
                                    f"The lot range implies a total of {total_from_lots} kg, which is greater than the Total Qty of {total_qty} kg.")
                return None

            excess_qty = total_qty - total_from_lots

            if excess_qty > 0:
                last_full_lot = lot_list[-1]
                match_last = re.match(r'^(\d+)([A-Z]*)$', last_full_lot)
                if match_last:
                    excess_lot_number = f"{str(int(match_last.group(1)) + 1).zfill(len(match_last.group(1)))}{match_last.group(2)}"
                else:
                    excess_lot_number = f"{last_full_lot}-EXCESS"
        else:
            # Simple excess, no range generation
            lot_list = []
            excess_qty = total_qty
            match = re.match(r'^(\d+)([A-Z]*)$', lot_input.upper())
            if match:
                excess_lot_number = f"{str(int(match.group(1)) + 1).zfill(len(match.group(1)))}{match.group(2)}"
            else:
                excess_lot_number = f"{lot_input.upper()}-EXCESS" if lot_input else "EXCESS"

        return {"lots": lot_list, "excess_qty": excess_qty, "weight_per_lot": weight_per_lot,
                "excess_lot_number": excess_lot_number}

    def _save_record(self):
        if not self.preview_data: QMessageBox.warning(self, "Preview Required",
                                                      "Please 'Preview Breakdown' before saving."); return
        is_update = self.current_editing_ref_no is not None
        sys_ref_no = self.current_editing_ref_no if is_update else self._generate_ref_no()
        primary_data = {"system_ref_no": sys_ref_no, "form_ref_no": self.form_ref_no_edit.text().strip(),
                        "product_code": self.product_code_combo.currentText(),
                        "lot_number": self.lot_number_edit.text().strip(), "quantity_kg": self.quantity_edit.value(),
                        "weight_per_lot": self.weight_per_lot_edit.value(), "status": self.status_combo.currentText(),
                        "bag_number": self.bag_number_combo.currentText(),
                        "box_number": self.box_number_combo.currentText(), "remarks": self.remarks_combo.currentText(),
                        "date_endorsed": self.date_endorsed_edit.date().toPyDate(),
                        "endorsed_by": self.endorsed_by_combo.currentText(),
                        "date_received": self.received_date_time_edit.dateTime().toPyDateTime(),
                        "received_by": self.received_by_combo.currentText(), "encoded_by": self.username,
                        "encoded_on": datetime.now(), "edited_by": self.username, "edited_on": datetime.now()}
        try:
            with self.engine.connect() as conn, conn.begin():
                if is_update:
                    conn.execute(text("DELETE FROM qce_endorsements_secondary WHERE system_ref_no = :ref"),
                                 {"ref": sys_ref_no})
                    conn.execute(text("DELETE FROM qce_endorsements_excess WHERE system_ref_no = :ref"),
                                 {"ref": sys_ref_no})
                    conn.execute(text(
                        """UPDATE qce_endorsements_primary SET form_ref_no=:form_ref_no, product_code=:product_code, lot_number=:lot_number, quantity_kg=:quantity_kg, weight_per_lot=:weight_per_lot, status=:status, bag_number=:bag_number, box_number=:box_number, remarks=:remarks, date_endorsed=:date_endorsed, endorsed_by=:endorsed_by, date_received=:date_received, received_by=:received_by, edited_by=:edited_by, edited_on=:edited_on WHERE system_ref_no = :system_ref_no"""),
                        primary_data)
                    action_text = "updated";
                    self.log_audit_trail("UPDATE_QC_EXCESS", f"Updated QC Excess: {sys_ref_no}")
                else:
                    conn.execute(text(
                        """INSERT INTO qce_endorsements_primary (system_ref_no, form_ref_no, product_code, lot_number, quantity_kg, weight_per_lot, status, bag_number, box_number, remarks, date_endorsed, endorsed_by, date_received, received_by, encoded_by, encoded_on, edited_by, edited_on) VALUES (:system_ref_no, :form_ref_no, :product_code, :lot_number, :quantity_kg, :weight_per_lot, :status, :bag_number, :box_number, :remarks, :date_endorsed, :endorsed_by, :date_received, :received_by, :encoded_by, :encoded_on, :edited_by, :edited_on)"""),
                        primary_data)
                    action_text = "saved";
                    self.log_audit_trail("CREATE_QC_EXCESS", f"Created QC Excess: {sys_ref_no}")
                if self.preview_data.get('lots'):
                    conn.execute(text(
                        "INSERT INTO qce_endorsements_secondary (system_ref_no, lot_number, quantity_kg, bag_number, box_number, remarks) VALUES (:system_ref_no, :lot_number, :quantity_kg, :bag_number, :box_number, :remarks)"),
                        [{'system_ref_no': sys_ref_no, 'lot_number': lot,
                          'quantity_kg': self.preview_data['weight_per_lot'],
                          **{k: primary_data[k] for k in ['bag_number', 'box_number', 'remarks']}} for lot in
                         self.preview_data['lots']])
                if self.preview_data.get('excess_qty') > 0 and self.preview_data.get('excess_lot_number'):
                    conn.execute(text(
                        "INSERT INTO qce_endorsements_excess (system_ref_no, lot_number, quantity_kg, bag_number, box_number, remarks) VALUES (:system_ref_no, :lot_number, :quantity_kg, :bag_number, :box_number, :remarks)"),
                        [{'system_ref_no': sys_ref_no, 'lot_number': self.preview_data['excess_lot_number'],
                          'quantity_kg': self.preview_data['excess_qty'],
                          **{k: primary_data[k] for k in ['bag_number', 'box_number', 'remarks']}}])
                self._create_inventory_transactions(conn, primary_data, self.preview_data)
            QMessageBox.information(self, "Success", f"QC Excess Endorsement {sys_ref_no} {action_text} successfully.")
            self._clear_form();
            self._refresh_all_data_views();
            self.tab_widget.setCurrentIndex(0)
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"An error occurred: {e}");
            traceback.print_exc()

    def _create_inventory_transactions(self, conn, primary_data, preview_data):
        sys_ref_no = primary_data['system_ref_no']
        conn.execute(text("DELETE FROM transactions WHERE source_ref_no = :ref"), {"ref": sys_ref_no})
        conn.execute(text("DELETE FROM failed_transactions WHERE source_ref_no = :ref"), {"ref": sys_ref_no})
        all_new_lots = ([{'lot_number': lot, 'quantity_kg': preview_data['weight_per_lot']} for lot in
                         preview_data['lots']] if preview_data.get('lots') else []) + ([{'lot_number': preview_data[
            'excess_lot_number'], 'quantity_kg': preview_data['excess_qty']}] if preview_data.get('excess_qty',
                                                                                                  0) > 0 and preview_data.get(
            'excess_lot_number') else [])
        if primary_data["status"] == "Passed":
            if all_new_lots: conn.execute(text(
                """INSERT INTO transactions (transaction_date, transaction_type, source_ref_no, product_code, lot_number, quantity_in, quantity_out, unit, warehouse, encoded_by, remarks) VALUES (:transaction_date, :transaction_type, :source_ref_no, :product_code, :lot_number, :quantity_in, 0, 'KG.', NULL, :encoded_by, :remarks)"""),
                [{"transaction_date": primary_data["date_endorsed"],
                  "transaction_type": "QC_EXCESS_IN_TO_FG", "source_ref_no": sys_ref_no,
                  "product_code": primary_data["product_code"],
                  "lot_number": lot["lot_number"], "quantity_in": lot["quantity_kg"],
                  "encoded_by": self.username,
                  "remarks": f"Excess passed QC. QCE No: {sys_ref_no}"} for lot in
                 all_new_lots])
        elif primary_data["status"] == "Failed":
            if all_new_lots: conn.execute(text(
                """INSERT INTO failed_transactions (transaction_date, transaction_type, source_ref_no, product_code, lot_number, quantity_in, quantity_out, unit, warehouse, encoded_by, remarks) VALUES (:transaction_date, :transaction_type, :source_ref_no, :product_code, :lot_number, :quantity_in, 0, 'KG.', NULL, :encoded_by, :remarks)"""),
                [{"transaction_date": primary_data["date_endorsed"],
                  "transaction_type": "QC_EXCESS_IN_TO_FAILED", "source_ref_no": sys_ref_no,
                  "product_code": primary_data["product_code"],
                  "lot_number": lot["lot_number"], "quantity_in": lot["quantity_kg"],
                  "encoded_by": self.username,
                  "remarks": f"Excess failed QC. QCE No: {sys_ref_no}"} for lot in
                 all_new_lots])

    def _load_all_records(self):
        search = f"%{self.search_edit.text()}%";
        offset = (self.current_page - 1) * self.records_per_page
        try:
            with self.engine.connect() as conn:
                count_query_base = "FROM qce_endorsements_primary WHERE is_deleted IS NOT TRUE";
                filter_clause = ""
                params = {'limit': self.records_per_page, 'offset': offset}
                like_operator = "ILIKE" if self.engine.dialect.name != 'sqlite' else "LIKE"
                if self.search_edit.text():
                    filter_clause = f" AND (system_ref_no {like_operator} :st OR form_ref_no {like_operator} :st OR product_code {like_operator} :st OR lot_number {like_operator} :st)";
                    params['st'] = search
                self.total_records = conn.execute(text(f"SELECT COUNT(id) {count_query_base} {filter_clause}"),
                                                  {'st': search} if self.search_edit.text() else {}).scalar_one()
                query_sql = f"SELECT system_ref_no, form_ref_no, date_endorsed, product_code, lot_number, quantity_kg FROM qce_endorsements_primary WHERE is_deleted IS NOT TRUE {filter_clause} ORDER BY id DESC LIMIT :limit OFFSET :offset"
                res = conn.execute(text(query_sql), params).mappings().all()
            self._populate_records_table(self.records_table, res,
                                         ["System Ref No", "Form Ref No", "Date", "Product Code", "Lot No / Range",
                                          "Total Qty"])
            self._update_pagination_controls()
        except Exception as e:
            if "no such table" not in str(e).lower():
                QMessageBox.critical(self, "DB Error", f"Could not load QC Excess endorsements: {e}")

    def _load_deleted_records(self):
        try:
            with self.engine.connect() as conn:
                res = conn.execute(text(
                    "SELECT system_ref_no, form_ref_no, date_endorsed, product_code, lot_number, quantity_kg, edited_by, edited_on FROM qce_endorsements_primary WHERE is_deleted = TRUE ORDER BY edited_on DESC")).mappings().all()
            self._populate_records_table(self.deleted_records_table, res,
                                         ["System Ref No", "Form Ref No", "Date", "Product Code", "Lot No / Range",
                                          "Total Qty", "Deleted By", "Deleted On"])
        except Exception as e:
            if "no such table" not in str(e).lower():
                QMessageBox.critical(self, "DB Error", f"Could not load deleted records: {e}")

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

    def _load_record_for_update(self):
        selected_rows = self.records_table.selectionModel().selectedRows()
        if not selected_rows: return
        ref_no = self.records_table.item(selected_rows[0].row(), 0).text()
        try:
            with self.engine.connect() as conn:
                record = conn.execute(text("SELECT * FROM qce_endorsements_primary WHERE system_ref_no = :ref"),
                                      {"ref": ref_no}).mappings().one_or_none()
            if not record: QMessageBox.critical(self, "Error", f"Record {ref_no} not found."); return
            self._clear_form();
            self.current_editing_ref_no = ref_no
            self.ref_no_edit.setText(record.get('system_ref_no', ''));
            self.form_ref_no_edit.setText(record.get('form_ref_no', ''))
            if db_date := record.get('date_endorsed'):
                q_date = QDate(db_date) if isinstance(db_date, date) else QDate.fromString(str(db_date).split()[0],
                                                                                           "yyyy-MM-dd")
                self.date_endorsed_edit.setDate(q_date)
            self.product_code_combo.setCurrentText(record.get('product_code', ''));
            self.lot_number_edit.setText(record.get('lot_number', ''))
            self.quantity_edit.setText(format_float_with_commas(record.get('quantity_kg', 0.0)))
            self.weight_per_lot_edit.setText(format_float_with_commas(record.get('weight_per_lot', 0.0)))
            self.status_combo.setCurrentText(record.get('status', ''));
            self.bag_number_combo.setCurrentText(record.get('bag_number', ''));
            self.box_number_combo.setCurrentText(record.get('box_number', ''));
            self.remarks_combo.setCurrentText(record.get('remarks', ''))
            self.endorsed_by_combo.setCurrentText(record.get('endorsed_by', ''))
            if db_datetime := record.get('date_received'):
                q_datetime = QDateTime(db_datetime) if isinstance(db_datetime, datetime) else QDateTime.fromString(
                    str(db_datetime).split('.')[0], 'yyyy-MM-dd HH:mm:ss')
                self.received_date_time_edit.setDateTime(q_datetime)
            self.received_by_combo.setCurrentText(record.get('received_by', ''))
            self.is_lot_range_check.setChecked('-' in (record.get('lot_number') or ''))
            self.save_btn.setText("Update Endorsement");
            self.cancel_update_btn.show()
            self._generate_preview_from_data(record);
            self.tab_widget.setCurrentIndex(self.tab_widget.indexOf(self.entry_tab))
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load record {ref_no} for editing: {e}")
            traceback.print_exc()

    def _delete_record(self):
        selected_rows = self.records_table.selectionModel().selectedRows()
        if not selected_rows: return
        ref_no = self.records_table.item(selected_rows[0].row(), 0).text()
        password, ok = QInputDialog.getText(self, "Password Required", "Enter password to delete:",
                                            QLineEdit.EchoMode.Password)
        if not ok or password != "Itadmin": QMessageBox.warning(self, "Incorrect Password",
                                                                "Deletion cancelled."); return
        if QMessageBox.question(self, "Confirm Delete",
                                f"Are you sure you want to delete endorsement <b>{ref_no}</b>? This will permanently delete its inventory records.") == QMessageBox.StandardButton.Yes:
            try:
                with self.engine.connect() as conn, conn.begin():
                    conn.execute(text(
                        "UPDATE qce_endorsements_primary SET is_deleted = TRUE, edited_by = :user, edited_on = :now WHERE system_ref_no = :ref"),
                        {"ref": ref_no, "user": self.username, "now": datetime.now()})
                    conn.execute(text("DELETE FROM transactions WHERE source_ref_no = :ref"), {"ref": ref_no})
                    conn.execute(text("DELETE FROM failed_transactions WHERE source_ref_no = :ref"), {"ref": ref_no})
                self.log_audit_trail("DELETE_QC_EXCESS",
                                     f"Soft-deleted QC Excess: {ref_no} and deleted its inventory transactions.")
                QMessageBox.information(self, "Success", f"Endorsement {ref_no} has been deleted.")
                self._refresh_all_data_views()
            except Exception as e:
                QMessageBox.critical(self, "Database Error", f"Could not delete record: {e}");
                traceback.print_exc()

    def _restore_record(self):
        selected_rows = self.deleted_records_table.selectionModel().selectedRows()
        if not selected_rows: return
        ref_no = self.deleted_records_table.item(selected_rows[0].row(), 0).text()
        if QMessageBox.question(self, "Confirm Restore",
                                f"Are you sure you want to restore endorsement <b>{ref_no}</b>?") == QMessageBox.StandardButton.Yes:
            try:
                with self.engine.connect() as conn, conn.begin():
                    primary_data = conn.execute(
                        text("SELECT * FROM qce_endorsements_primary WHERE system_ref_no = :ref"),
                        {"ref": ref_no}).mappings().one()
                    secondary_data = conn.execute(
                        text("SELECT * FROM qce_endorsements_secondary WHERE system_ref_no = :ref"),
                        {"ref": ref_no}).mappings().all()
                    excess_data = conn.execute(text("SELECT * FROM qce_endorsements_excess WHERE system_ref_no = :ref"),
                                               {"ref": ref_no}).mappings().all()
                    preview_data = self._generate_preview_for_restore(primary_data, secondary_data, excess_data)
                    conn.execute(text(
                        "UPDATE qce_endorsements_primary SET is_deleted = FALSE, edited_by = :user, edited_on = :now WHERE system_ref_no = :ref"),
                        {"ref": ref_no, "user": self.username, "now": datetime.now()})
                    self._create_inventory_transactions(conn, primary_data, preview_data)
                self.log_audit_trail("RESTORE_QC_EXCESS", f"Restored QC Excess: {ref_no}")
                QMessageBox.information(self, "Success", f"Endorsement {ref_no} has been restored.")
                self._refresh_all_data_views()
            except Exception as e:
                QMessageBox.critical(self, "Database Error", f"Could not restore record: {e}");
                traceback.print_exc()

    def _generate_preview_for_restore(self, primary_data, secondary_data, excess_data):
        lots = [rec['lot_number'] for rec in secondary_data]
        excess_qty, excess_lot_number = (
            Decimal(str(excess_data[0]['quantity_kg'])), excess_data[0]['lot_number']) if excess_data else (
            Decimal(0), None)
        return {"lots": lots, "excess_qty": excess_qty, "weight_per_lot": Decimal(str(primary_data['weight_per_lot'])),
                "excess_lot_number": excess_lot_number}

    def _generate_ref_no(self):
        prefix = f"QCE-{datetime.now().strftime('%y%m')}-"
        with self.engine.connect() as conn:
            try:
                last_ref = conn.execute(text(
                    "SELECT system_ref_no FROM qce_endorsements_primary WHERE system_ref_no LIKE :p ORDER BY id DESC LIMIT 1"),
                    {"p": f"{prefix}%"}).scalar_one_or_none()
                next_seq = int(last_ref.split('-')[-1]) + 1 if last_ref else 1
            except Exception:
                next_seq = 1
            return f"{prefix}{next_seq:04d}"

    # --- FIX IS HERE: Corrected Lot Range Parsing ---
    def _parse_lot_range(self, lot_input: str):
        try:
            parts = [s.strip().upper() for s in lot_input.split('-')]
            if len(parts) != 2:
                raise ValueError("Lot range must contain exactly one hyphen.")

            start_str, end_str = parts
            start_match = re.match(r'^(\d+)([A-Z]*)$', start_str)
            end_match = re.match(r'^(\d+)([A-Z]*)$', end_str)

            if not start_match or not end_match:
                raise ValueError("Lot format must be numeric with an optional text suffix (e.g., 1234AA).")
            if start_match.group(2) != end_match.group(2):
                raise ValueError("Start and end lot suffixes must match.")

            start_num = int(start_match.group(1))
            end_num = int(end_match.group(1))
            suffix = start_match.group(2)
            num_len = len(start_match.group(1))

            if start_num > end_num:
                raise ValueError("Start lot number cannot be greater than the end lot number.")

            return [f"{str(i).zfill(num_len)}{suffix}" for i in range(start_num, end_num + 1)]
        except Exception as e:
            QMessageBox.critical(self, "Lot Range Error", f"Could not parse lot range '{lot_input}':\n{e}")
            return None

    def _populate_records_table(self, table, data, headers):
        table.setRowCount(0);
        table.setColumnCount(len(headers));
        table.setHorizontalHeaderLabels(headers)
        header = table.horizontalHeader()
        if not data:
            if header.count() > 0: header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            return
        table.setRowCount(len(data))
        for i, row_data in enumerate(data):
            keys = list(row_data.keys())
            for j, key in enumerate(keys):
                value = row_data.get(key)
                if isinstance(value, datetime):
                    item_text = value.strftime('%Y-%m-%d %H:%M')
                elif isinstance(value, date):
                    item_text = value.strftime('%Y-%m-%d')
                elif isinstance(value, (float, Decimal)):
                    item_text = format_float_with_commas(value)
                else:
                    item_text = str(value or "")
                item = QTableWidgetItem(item_text)
                if isinstance(value, (float, Decimal)): item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(i, j, item)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for col_index, header_text in enumerate(headers):
            if "Ref No" in header_text or "Date" in header_text:
                header.setSectionResizeMode(col_index, QHeaderView.ResizeMode.ResizeToContents)
            elif "Product Code" in header_text or "Lot No" in header_text:
                header.setSectionResizeMode(col_index, QHeaderView.ResizeMode.Stretch)

    def _populate_preview_table(self, table_widget, data, headers):
        table_widget.setRowCount(0);
        table_widget.setColumnCount(len(headers));
        table_widget.setHorizontalHeaderLabels(headers)
        if not data:
            if table_widget.horizontalHeader().count() > 0: table_widget.horizontalHeader().setSectionResizeMode(
                QHeaderView.ResizeMode.Stretch)
            return
        table_widget.setRowCount(len(data));
        keys = list(data[0].keys())
        for i, row_data in enumerate(data):
            for j, key in enumerate(keys):
                val = row_data.get(key)
                item_text = format_float_with_commas(val) if isinstance(val, (Decimal, float)) else str(val or "")
                item = QTableWidgetItem(item_text)
                if isinstance(val, (Decimal, float)): item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table_widget.setItem(i, j, item)
        table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    def _refresh_all_data_views(self):
        self._load_all_records()
        self._load_deleted_records()


# --- Main Application Execution ---

if __name__ == '__main__':
    app = QApplication(sys.argv)
    db_engine = create_db_engine()
    main_window = QCExcessEndorsementPage(db_engine, USERNAME, log_audit_trail_func)
    main_window.setWindowTitle("MBPI - QC Excess Endorsement (QCE)")
    main_window.resize(1200, 800)
    main_window.show()
    sys.exit(app.exec())