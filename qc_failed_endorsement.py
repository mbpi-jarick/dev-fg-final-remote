import sys
import re
import traceback
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from typing import Any

# --- PyQt6 Imports ---
from PyQt6.QtCore import Qt, QDate, QDateTime, QSize
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTabWidget, QFormLayout, QLineEdit,
                             QComboBox, QDateEdit, QPushButton, QTableWidget, QTableWidgetItem,
                             QAbstractItemView, QHeaderView, QMessageBox, QHBoxLayout, QLabel,
                             QCheckBox, QDialog, QDialogButtonBox, QInputDialog,
                             QSplitter, QGridLayout, QGroupBox, QMenu,
                             QApplication, QMainWindow)
from PyQt6.QtGui import QDoubleValidator

# --- Database Imports ---
from sqlalchemy import create_engine, text

# --- Icon Library Import ---
try:
    import qtawesome as fa
    import qtawesome as qta
except ImportError:
    print("Warning: qtawesome library not found. Icons will be missing.")
    fa = None
    qta = None

# --- Configuration & Styles ---
ADMIN_PASSWORD = "Itadmin"
ICON_COLOR = '#dc3545'
COLOR_PRIMARY = '#1e74a8'

INSTRUCTION_STYLE = "color: #4a4e69; background-color: #fde4e1; border: 1px solid #f9c6c0; padding: 8px; border-radius: 4px; margin-bottom: 10px;"
GLOBAL_STYLES = f"""
    QTableWidget::item:selected {{
        background-color: #3a506b;
        color: #FFFFFF;
    }}
    QPushButton#PrimaryButton {{
        background-color: {COLOR_PRIMARY};
        color: white;
        border: 1px solid {COLOR_PRIMARY};
        padding: 5px 10px;
        border-radius: 3px;
    }}
    QPushButton#SecondaryButton {{
        background-color: #f0f0f0;
        color: {COLOR_PRIMARY};
        border: 1px solid {COLOR_PRIMARY};
        padding: 5px 10px;
        border-radius: 3px;
    }}
    QPushButton#delete_btn {{ 
        background-color: #e63946; 
        color: white; 
        border: 1px solid #e63946; 
        padding: 5px 10px; 
        border-radius: 3px;
    }}
    QPushButton#update_btn {{
        background-color: #f39c12; /* Orange for update */
        color: white;
        border: 1px solid #f39c12;
        padding: 5px 10px;
        border-radius: 3px;
    }}
    QPushButton#restore_btn {{
        background-color: #5cb85c;
        color: white;
        border: 1px solid #5cb85c;
        padding: 5px 10px;
        border-radius: 3px;
    }}
"""


# --- UTILITY FUNCTIONS ---

def format_float_with_commas(value: Any, decimals: int = 2) -> str:
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
            clean_text = self.text().replace(',', '')
            value = float(clean_text or 0.0)
            self.setText(f"{value:,.2f}")
        except ValueError:
            self.setText("0.00")

    def value(self) -> float:
        try:
            clean_text = self.text().replace(',', '')
            return float(clean_text or 0.0)
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


class InventorySelectionDialog(QDialog):
    def __init__(self, parent, db_engine, product_code=None, lot_number=None):
        super().__init__(parent)
        self.engine = db_engine
        self.setWindowTitle("Select FG Passed Inventory for Transfer")
        self.setModal(True)
        self.setMinimumSize(800, 500)
        self.available_lots_data = {}
        self.transfer_data = []
        self._setup_ui()
        if product_code:
            self.product_filter_combo.setCurrentText(product_code)
        if lot_number:
            self.lot_filter_edit.setText(lot_number)
        self._load_current_inventory()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        filter_group = QGroupBox("Filter Inventory")
        filter_layout = QGridLayout(filter_group)
        filter_layout.addWidget(QLabel("Product Code:"), 0, 0)
        self.product_filter_combo = QComboBox(editable=True)
        set_combo_box_uppercase(self.product_filter_combo)
        filter_layout.addWidget(self.product_filter_combo, 0, 1)
        filter_layout.addWidget(QLabel("Lot Number/Range:"), 1, 0)
        self.lot_filter_edit = UpperCaseLineEdit(placeholderText="LOTA001 or LOTA001-LOTA005")
        filter_layout.addWidget(self.lot_filter_edit, 1, 1)
        self.search_btn = QPushButton(qta.icon('fa5s.search'), "Search Stock")
        filter_layout.addWidget(self.search_btn, 0, 2, 2, 1)
        main_layout.addWidget(filter_group)
        self.inventory_table = QTableWidget(columnCount=3)
        self.inventory_table.setHorizontalHeaderLabels(["Product Code", "Lot Number", "Available Qty (kg)"])
        self.inventory_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.inventory_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.inventory_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.inventory_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.inventory_table.verticalHeader().setVisible(False)
        main_layout.addWidget(self.inventory_table)
        self.status_label = QLabel("Enter Product Code or Lot Number and click 'Search Stock'.")
        main_layout.addWidget(self.status_label)
        button_box = QDialogButtonBox()
        self.ok_button = button_box.addButton("Transfer Full Qty", QDialogButtonBox.ButtonRole.AcceptRole)
        self.partial_button = button_box.addButton("Transfer Partial Qty...", QDialogButtonBox.ButtonRole.ActionRole)
        button_box.addButton(QDialogButtonBox.StandardButton.Cancel)
        self.ok_button.setEnabled(False)
        self.partial_button.setEnabled(False)
        main_layout.addWidget(button_box)
        self.search_btn.clicked.connect(self._load_current_inventory)
        button_box.accepted.connect(self._gather_full_qty_data)
        button_box.rejected.connect(self.reject)
        self.partial_button.clicked.connect(self._gather_partial_qty_data)
        self.inventory_table.itemSelectionChanged.connect(self._on_selection_changed)
        self._load_product_codes()

    def _load_product_codes(self):
        try:
            with self.engine.connect() as conn:
                query = text(
                    "SELECT DISTINCT product_code FROM transactions WHERE product_code IS NOT NULL AND product_code != '' ORDER BY product_code")
                items = conn.execute(query).scalars().all()
                self.product_filter_combo.clear()
                self.product_filter_combo.addItems([""] + [item for item in items if item])
        except Exception as e:
            print(f"DB Error loading products in dialog: {e}")

    def _parse_lot_range_sql(self, lot_input: str) -> str:
        lot_input = lot_input.strip().upper()
        if not lot_input: return ""
        if '-' in lot_input:
            return "lot_number BETWEEN :start_lot AND :end_lot"
        else:
            return "lot_number LIKE :single_lot_search"

    def _load_current_inventory(self):
        self.inventory_table.setRowCount(0)
        product_code = self.product_filter_combo.currentText().strip()
        lot_input = self.lot_filter_edit.text().strip()
        if not product_code and not lot_input:
            self.status_label.setText("Please enter a Product Code or a Lot Number/Range.")
            self._on_selection_changed();
            return
        self.status_label.setText("Loading inventory...");
        QApplication.processEvents()
        try:
            where_clauses, params = [], {}
            if product_code:
                where_clauses.append("product_code = :pcode");
                params['pcode'] = product_code
            if lot_input:
                clause = self._parse_lot_range_sql(lot_input)
                if "BETWEEN" in clause:
                    where_clauses.append(clause);
                    start_lot, end_lot = lot_input.split('-');
                    params.update({'start_lot': start_lot.strip().upper(), 'end_lot': end_lot.strip().upper()})
                elif "LIKE" in clause:
                    where_clauses.append(clause);
                    params['single_lot_search'] = f"%{lot_input}%"
            if not where_clauses:
                self.status_label.setText("Search failed.");
                self._on_selection_changed();
                return
            with self.engine.connect() as conn:
                query = text(
                    f"SELECT product_code, lot_number, SUM(quantity_in) - SUM(quantity_out) AS balance FROM transactions WHERE {' AND '.join(where_clauses)} GROUP BY product_code, lot_number HAVING SUM(quantity_in) > SUM(quantity_out) ORDER BY product_code, lot_number")
                result = conn.execute(query, params).mappings().all()
            self.available_lots_data.clear()
            for row in result:
                balance = Decimal(str(row.get('balance', 0.0) or 0.0))
                if balance > 0:
                    self.available_lots_data[row['lot_number']] = {'qty_available': balance,
                                                                   'product_code': row['product_code']}
            self.inventory_table.setRowCount(len(self.available_lots_data))
            for row_idx, (lot_num, data) in enumerate(self.available_lots_data.items()):
                self.inventory_table.setItem(row_idx, 0, QTableWidgetItem(data['product_code']))
                self.inventory_table.setItem(row_idx, 1, QTableWidgetItem(lot_num))
                item_qty_available = QTableWidgetItem(format_float_with_commas(data['qty_available']))
                item_qty_available.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.inventory_table.setItem(row_idx, 2, item_qty_available)
            self.status_label.setText(f"Loaded {len(self.available_lots_data)} lots with available stock.");
            self._on_selection_changed()
        except Exception as e:
            QMessageBox.critical(self, "Inventory Error", f"Failed to retrieve inventory balance: {e}")
            self.status_label.setText("Error loading inventory.");
            print(traceback.format_exc())

    def _on_selection_changed(self):
        selected_rows = self.inventory_table.selectionModel().selectedRows();
        num_selected = len(selected_rows)
        self.ok_button.setEnabled(num_selected > 0);
        self.partial_button.setEnabled(num_selected == 1)

    def _gather_full_qty_data(self):
        selected_rows = self.inventory_table.selectionModel().selectedRows()
        if not selected_rows: QMessageBox.warning(self, "No Selection",
                                                  "Please select at least one lot to transfer."); return
        self.transfer_data.clear()
        for row_item in selected_rows:
            lot_number = self.inventory_table.item(row_item.row(), 1).text()
            source_data = self.available_lots_data.get(lot_number)
            if source_data:
                self.transfer_data.append({'lot_number': lot_number, 'quantity_kg': float(source_data['qty_available']),
                                           'product_code': source_data['product_code']})
        self.accept()

    def _gather_partial_qty_data(self):
        selected_rows = self.inventory_table.selectionModel().selectedRows()
        if len(selected_rows) != 1: QMessageBox.warning(self, "Invalid Selection",
                                                        "Please select exactly one lot for a partial transfer."); return
        lot_number = self.inventory_table.item(selected_rows[0].row(), 1).text()
        source_data = self.available_lots_data.get(lot_number)
        if not source_data: return
        available_qty = float(source_data['qty_available'])
        qty, ok = QInputDialog.getDouble(self, "Partial Transfer", "Enter quantity to transfer:", value=available_qty,
                                         min=0.01, max=available_qty, decimals=2)
        if ok and qty > 0:
            self.transfer_data = [
                {'lot_number': lot_number, 'quantity_kg': qty, 'product_code': source_data['product_code']}]
            self.accept()

    def get_transfer_data(self):
        return self.transfer_data if self.result() else None


class QCFailedEndorsementPage(QWidget):
    def __init__(self, db_engine, username, log_audit_trail_func):
        super().__init__()
        self.engine, self.username, self.log_audit_trail = db_engine, username, log_audit_trail_func
        self.current_editing_ref, self.preview_data = None, None
        self.current_page, self.records_per_page = 1, 200
        self.total_records, self.total_pages = 0, 1
        self.view_left_details_layout, self.view_right_details_layout = None, None
        self.records_table, self.update_btn, self.delete_btn = None, None, None
        self.view_breakdown_table = QTableWidget()
        self.view_excess_table = QTableWidget()
        self.view_breakdown_total_label, self.view_excess_total_label = QLabel(), QLabel()
        self._retained_form_ref, self._retained_date = "", QDate.currentDate()
        self._retained_product_code, self._retained_endorsed_by, self._retained_warehouse = "", "", ""
        self._retained_received_by, self._retained_remarks, self._retained_bag_no = "", "", ""
        self.init_ui()
        self._load_all_endorsements()

    def init_ui(self):
        self.setStyleSheet(GLOBAL_STYLES);
        main_layout = QVBoxLayout(self)
        header_widget = QWidget();
        header_layout = QHBoxLayout(header_widget);
        header_layout.setContentsMargins(0, 0, 0, 0)
        icon_label = QLabel();
        if fa: icon_label.setPixmap(fa.icon('fa5s.times-circle', color=ICON_COLOR).pixmap(QSize(28, 28)))
        header_layout.addWidget(icon_label)
        header_label = QLabel("QC Failed Endorsement");
        header_label.setStyleSheet("font-size: 15pt; font-weight: bold; padding: 10px 0; color: #3a506b;")
        header_layout.addWidget(header_label);
        header_layout.addStretch();
        main_layout.addWidget(header_widget)
        self.tab_widget = QTabWidget();
        main_layout.addWidget(self.tab_widget)
        self.view_tab, self.view_details_tab, self.entry_tab, self.deleted_tab = QWidget(), QWidget(), QWidget(), QWidget()
        self._setup_view_details_tab(self.view_details_tab);
        self._setup_view_tab(self.view_tab);
        self._setup_entry_tab(self.entry_tab);
        self._setup_deleted_tab(self.deleted_tab)
        if fa:
            self.tab_widget.addTab(self.view_tab, fa.icon('fa5s.list', color=ICON_COLOR), "All QC Failed Endorsements")
            self.tab_widget.addTab(self.entry_tab, fa.icon('fa5s.clipboard-list', color=ICON_COLOR),
                                   "Endorsement Entry")
            self.tab_widget.addTab(self.view_details_tab, fa.icon('fa5s.search', color=ICON_COLOR),
                                   "View Endorsement Details")
            self.tab_widget.addTab(self.deleted_tab, fa.icon('fa5s.trash-restore', color=ICON_COLOR), "Deleted Records")
        self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.view_details_tab), False);
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

    def _configure_table_ui(self, table: QTableWidget):
        table.setShowGrid(False);
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus);
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False);
        table.horizontalHeader().setHighlightSections(False)

    def _setup_view_tab(self, tab):
        layout = QVBoxLayout(tab);
        instruction_label = QLabel(
            "<b>Instruction:</b> Search for endorsements. Select a record to view details, load for an update, or delete.");
        instruction_label.setStyleSheet(INSTRUCTION_STYLE);
        layout.addWidget(instruction_label)
        controls_group = QGroupBox("Search & Actions");
        top_layout = QHBoxLayout(controls_group);
        top_layout.addWidget(QLabel("Search:"));
        self.search_edit = UpperCaseLineEdit(placeholderText="Filter by Ref No, Product Code, Lot No...");
        top_layout.addWidget(self.search_edit, 1)
        self.refresh_btn, self.update_btn, self.delete_btn = QPushButton(" Refresh"), QPushButton(
            " Load for Update"), QPushButton(" Delete Selected");
        self.update_btn.setObjectName("update_btn");
        self.delete_btn.setObjectName("delete_btn")
        if fa: self.refresh_btn.setIcon(fa.icon('fa5s.sync-alt', color=ICON_COLOR)); self.update_btn.setIcon(
            fa.icon('fa5s.edit', color='white')); self.delete_btn.setIcon(fa.icon('fa5s.trash-alt', color='white'))
        top_layout.addWidget(self.refresh_btn);
        top_layout.addWidget(self.update_btn);
        top_layout.addWidget(self.delete_btn);
        layout.addWidget(controls_group)
        self.records_table = QTableWidget();
        self._configure_table_ui(self.records_table);
        self.records_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection);
        self.records_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu);
        layout.addWidget(self.records_table)
        pagination_layout = QHBoxLayout();
        self.prev_btn, self.next_btn = QPushButton(" Previous"), QPushButton("Next ");
        self.next_btn.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        if fa: self.prev_btn.setIcon(fa.icon('fa5s.chevron-left', color=ICON_COLOR)); self.next_btn.setIcon(
            fa.icon('fa5s.chevron-right', color=ICON_COLOR))
        self.page_label = QLabel("Page 1 of 1");
        pagination_layout.addStretch();
        pagination_layout.addWidget(self.prev_btn);
        pagination_layout.addWidget(self.page_label);
        pagination_layout.addWidget(self.next_btn);
        pagination_layout.addStretch();
        layout.addLayout(pagination_layout)
        self.search_edit.textChanged.connect(self._on_search_text_changed);
        self.refresh_btn.clicked.connect(self._load_all_endorsements);
        self.update_btn.clicked.connect(self._load_record_for_update);
        self.delete_btn.clicked.connect(self._delete_record)
        self.records_table.customContextMenuRequested.connect(self._show_records_table_context_menu);
        self.records_table.itemSelectionChanged.connect(self._on_record_selection_changed);
        self.prev_btn.clicked.connect(self._go_to_prev_page);
        self.next_btn.clicked.connect(self._go_to_next_page);
        self._on_record_selection_changed()

    def _setup_deleted_tab(self, tab):
        layout = QVBoxLayout(tab);
        instruction_label = QLabel(
            "<b>Instruction:</b> Browse previously deleted endorsements. To restore a record, select it and click the restore button or right-click.");
        instruction_label.setStyleSheet(INSTRUCTION_STYLE);
        layout.addWidget(instruction_label)
        controls_group = QGroupBox("Search & Actions");
        top_layout = QHBoxLayout(controls_group);
        top_layout.addWidget(QLabel("Search Deleted:"));
        self.deleted_search_edit = UpperCaseLineEdit(placeholderText="Filter by Ref No, Product Code...");
        top_layout.addWidget(self.deleted_search_edit, 1)
        self.refresh_deleted_btn, self.restore_btn = QPushButton(" Refresh"), QPushButton(" Restore Selected");
        self.restore_btn.setObjectName("restore_btn");
        self.restore_btn.setEnabled(False)
        if fa: self.refresh_deleted_btn.setIcon(fa.icon('fa5s.sync-alt', color=ICON_COLOR)); self.restore_btn.setIcon(
            fa.icon('fa5s.undo', color='white'))
        top_layout.addWidget(self.refresh_deleted_btn);
        top_layout.addWidget(self.restore_btn);
        layout.addWidget(controls_group)
        self.deleted_records_table = QTableWidget();
        self._configure_table_ui(self.deleted_records_table);
        self.deleted_records_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection);
        self.deleted_records_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu);
        layout.addWidget(self.deleted_records_table)
        self.deleted_search_edit.textChanged.connect(self._load_deleted_records);
        self.refresh_deleted_btn.clicked.connect(self._load_deleted_records);
        self.restore_btn.clicked.connect(self._restore_record)
        self.deleted_records_table.itemSelectionChanged.connect(
            lambda: self.restore_btn.setEnabled(bool(self.deleted_records_table.selectedItems())));
        self.deleted_records_table.customContextMenuRequested.connect(self._show_deleted_table_context_menu)

    def _setup_view_details_tab(self, tab):
        main_layout = QVBoxLayout(tab);
        instruction_label = QLabel(
            "<b>Instruction:</b> This is a read-only, detailed view of the endorsement selected from the 'All QC Failed Endorsements' tab.");
        instruction_label.setStyleSheet(INSTRUCTION_STYLE);
        main_layout.addWidget(instruction_label)
        details_group = QGroupBox("Endorsement Details (Read-Only)");
        details_container_layout = QHBoxLayout(details_group);
        self.view_left_details_layout, self.view_right_details_layout = QFormLayout(), QFormLayout()
        details_container_layout.addLayout(self.view_left_details_layout);
        details_container_layout.addLayout(self.view_right_details_layout);
        main_layout.addWidget(details_group)
        tables_splitter = QSplitter(Qt.Orientation.Vertical);
        breakdown_group = QGroupBox("Lot Breakdown");
        breakdown_layout = QVBoxLayout(breakdown_group);
        self._configure_table_ui(self.view_breakdown_table);
        breakdown_layout.addWidget(self.view_breakdown_table)
        self.view_breakdown_total_label.setText("<b>Total: 0.00 kg</b>");
        self.view_breakdown_total_label.setAlignment(Qt.AlignmentFlag.AlignRight);
        breakdown_layout.addWidget(self.view_breakdown_total_label)
        tables_splitter.addWidget(breakdown_group);
        excess_group = QGroupBox("Excess Quantity");
        excess_layout = QVBoxLayout(excess_group);
        self._configure_table_ui(self.view_excess_table);
        excess_layout.addWidget(self.view_excess_table)
        self.view_excess_total_label.setText("<b>Total: 0.00 kg</b>");
        self.view_excess_total_label.setAlignment(Qt.AlignmentFlag.AlignRight);
        excess_layout.addWidget(self.view_excess_total_label)
        tables_splitter.addWidget(excess_group);
        main_layout.addWidget(tables_splitter, 1)

    def _setup_entry_tab(self, tab):
        main_splitter = QSplitter(Qt.Orientation.Horizontal);
        tab_layout = QHBoxLayout(tab);
        tab_layout.addWidget(main_splitter)
        left_widget = QWidget();
        left_layout = QVBoxLayout(left_widget);
        left_layout.setContentsMargins(0, 0, 5, 0);
        main_splitter.addWidget(left_widget)
        instruction_label = QLabel(
            f"<b>Instruction:</b> Use 'Load from FG Passed' to initiate a stock transfer. Always use 'Preview Breakdown' before saving.");
        instruction_label.setStyleSheet(INSTRUCTION_STYLE);
        left_layout.addWidget(instruction_label)
        load_group = QGroupBox("Inventory Load");
        load_layout = QHBoxLayout(load_group);
        self.load_fg_passed_btn = QPushButton(qta.icon('fa5s.arrow-right', color='#28a745'), "Load from FG Passed")
        load_layout.addWidget(self.load_fg_passed_btn);
        load_layout.addStretch();
        left_layout.addWidget(load_group)
        details_group = QGroupBox("QC Failed Endorsement Details");
        details_layout = QGridLayout(details_group)
        self.sys_ref_no_edit = QLineEdit(readOnly=True, placeholderText="Auto-generated");
        self.form_ref_no_edit = UpperCaseLineEdit()
        self.endorsement_date_edit = QDateEdit(calendarPopup=True, displayFormat="yyyy-MM-dd");
        self.product_code_combo = QComboBox(editable=True, insertPolicy=QComboBox.InsertPolicy.NoInsert)
        set_combo_box_uppercase(self.product_code_combo);
        self.remarks_edit = QLineEdit(placeholderText="Enter any remarks");
        self.bag_no_combo = QComboBox(editable=True);
        self.bag_no_combo.addItems([str(i) for i in range(1, 21)]);
        set_combo_box_uppercase(self.bag_no_combo)
        self.lot_number_edit = UpperCaseLineEdit(placeholderText="e.g., LOTA001 or LOTA001-LOTA010");
        self.is_lot_range_check = QCheckBox("Calculate lots from a range")
        self.quantity_edit, self.weight_per_lot_edit = FloatLineEdit(), FloatLineEdit();
        self.inventory_status_label = QLabel("Status: Ready");
        self.inventory_status_label.setStyleSheet("font-style: italic; color: #555;")
        self.endorsed_by_combo = QComboBox(editable=True);
        set_combo_box_uppercase(self.endorsed_by_combo);
        self.warehouse_combo = QComboBox();
        self.received_by_name_combo = QComboBox(editable=True);
        set_combo_box_uppercase(self.received_by_name_combo);
        self.received_date_edit = QDateEdit(calendarPopup=True, displayFormat="yyyy-MM-dd")
        details_layout.addWidget(QLabel("System Ref No:"), 0, 0);
        details_layout.addWidget(self.sys_ref_no_edit, 0, 1);
        details_layout.addWidget(QLabel("Form Ref No:"), 0, 2);
        details_layout.addWidget(self.form_ref_no_edit, 0, 3)
        details_layout.addWidget(QLabel("Date Endorsed:"), 1, 0);
        details_layout.addWidget(self.endorsement_date_edit, 1, 1);
        details_layout.addWidget(QLabel("Product Code:"), 1, 2);
        details_layout.addWidget(self.product_code_combo, 1, 3)
        details_layout.addWidget(QLabel("Lot Number/Range:"), 2, 0);
        details_layout.addWidget(self.lot_number_edit, 2, 1, 1, 3);
        details_layout.addWidget(QLabel("Bag Number:"), 3, 0);
        details_layout.addWidget(self.bag_no_combo, 3, 1)
        details_layout.addWidget(QLabel("Remarks:"), 3, 2);
        details_layout.addWidget(self.remarks_edit, 3, 3);
        details_layout.addWidget(self.is_lot_range_check, 4, 0, 1, 4)
        details_layout.addWidget(QLabel("Total Qty (kg):"), 5, 0);
        details_layout.addWidget(self.quantity_edit, 5, 1);
        details_layout.addWidget(QLabel("Weight/Lot (kg):"), 5, 2);
        details_layout.addWidget(self.weight_per_lot_edit, 5, 3)
        details_layout.addWidget(QLabel("Endorsed By:"), 6, 0);
        details_layout.addLayout(self._create_combo_with_manage_button("qcf_endorsers", self.endorsed_by_combo), 6, 1);
        details_layout.addWidget(QLabel("Warehouse:"), 6, 2);
        details_layout.addLayout(self._create_combo_with_manage_button("warehouses", self.warehouse_combo), 6, 3)
        details_layout.addWidget(QLabel("Received By:"), 7, 0);
        details_layout.addLayout(self._create_combo_with_manage_button("qcf_receivers", self.received_by_name_combo), 7,
                                 1);
        details_layout.addWidget(QLabel("Received Date:"), 7, 2);
        details_layout.addWidget(self.received_date_edit, 7, 3)
        details_layout.setColumnStretch(1, 1);
        details_layout.setColumnStretch(3, 1);
        left_layout.addWidget(details_group);
        left_layout.addStretch()
        right_widget = QWidget();
        right_layout = QVBoxLayout(right_widget);
        right_layout.setContentsMargins(5, 0, 0, 0);
        main_splitter.addWidget(right_widget)
        preview_splitter = QSplitter(Qt.Orientation.Vertical);
        breakdown_group = QGroupBox("Lot Breakdown (Preview)");
        b_layout = QVBoxLayout(breakdown_group);
        self.preview_breakdown_table = QTableWidget();
        self._configure_table_ui(self.preview_breakdown_table);
        b_layout.addWidget(self.preview_breakdown_table)
        self.breakdown_total_label = QLabel("<b>Total: 0.00 kg</b>");
        self.breakdown_total_label.setAlignment(Qt.AlignmentFlag.AlignRight);
        b_layout.addWidget(self.breakdown_total_label);
        preview_splitter.addWidget(breakdown_group)
        excess_group = QGroupBox("Excess Quantity (Preview)");
        excess_layout_v = QVBoxLayout(excess_group);
        self.preview_excess_table = QTableWidget();
        self._configure_table_ui(self.preview_excess_table);
        excess_layout_v.addWidget(self.preview_excess_table)
        self.excess_total_label = QLabel("<b>Total: 0.00 kg</b>");
        self.excess_total_label.setAlignment(Qt.AlignmentFlag.AlignRight);
        excess_layout_v.addWidget(self.excess_total_label);
        preview_splitter.addWidget(excess_group);
        right_layout.addWidget(preview_splitter);
        main_splitter.setSizes([650, 450])
        self.preview_btn, self.save_btn, self.clear_btn, self.cancel_update_btn = QPushButton(
            " Preview Breakdown"), QPushButton(" Save Endorsement"), QPushButton(" New"), QPushButton(" Cancel Update")
        self.save_btn.setObjectName("PrimaryButton");
        self.clear_btn.setObjectName("SecondaryButton");
        self.cancel_update_btn.setObjectName("delete_btn")
        if fa: self.preview_btn.setIcon(fa.icon('fa5s.eye', color=ICON_COLOR)); self.save_btn.setIcon(
            fa.icon('fa5s.save', color='white')); self.clear_btn.setIcon(
            fa.icon('fa5s.eraser', color=COLOR_PRIMARY)); self.cancel_update_btn.setIcon(
            fa.icon('fa5s.times', color='white'))
        button_layout = QHBoxLayout();
        button_layout.addStretch();
        button_layout.addWidget(self.cancel_update_btn);
        button_layout.addWidget(self.clear_btn);
        button_layout.addWidget(self.preview_btn);
        button_layout.addWidget(self.save_btn)
        left_layout.addLayout(button_layout)
        self.load_fg_passed_btn.clicked.connect(self._load_from_fg_passed_inventory);
        self.preview_btn.clicked.connect(self._preview_endorsement);
        self.save_btn.clicked.connect(self._save_endorsement);
        self.clear_btn.clicked.connect(self._clear_form);
        self.cancel_update_btn.clicked.connect(self._clear_form)
        self.quantity_edit.textChanged.connect(self._update_calculated_lots_display);
        self.weight_per_lot_edit.textChanged.connect(self._update_calculated_lots_display);
        self.is_lot_range_check.stateChanged.connect(self._update_calculated_lots_display)
        self._clear_form()

    def _update_calculated_lots_display(self):
        try:
            total_qty, weight_per_lot = self.quantity_edit.value(), self.weight_per_lot_edit.value()
            if weight_per_lot > 0:
                num_lots, excess = int(total_qty // weight_per_lot), total_qty % weight_per_lot
                self.inventory_status_label.setText(
                    f"Calculated: {num_lots} lot(s) with {format_float_with_commas(excess)} kg excess")
                self.inventory_status_label.setStyleSheet("font-style: italic; color: #555;")
            else:
                self.inventory_status_label.setText("Weight/Lot must be > 0");
                self.inventory_status_label.setStyleSheet("font-weight: bold; color: #f39c12;")
        except (InvalidOperation, ValueError):
            self.inventory_status_label.setText("Invalid quantity input");
            self.inventory_status_label.setStyleSheet("font-weight: bold; color: #e74c3c;")

    def _on_record_selection_changed(self):
        is_selected = bool(self.records_table.selectionModel().selectedRows())
        self.update_btn.setEnabled(is_selected);
        self.delete_btn.setEnabled(is_selected)
        if is_selected:
            self._show_selected_record_in_view_tab()
        else:
            for layout in [self.view_left_details_layout, self.view_right_details_layout]:
                while layout.count(): item = layout.takeAt(0); item.widget().deleteLater() if item.widget() else None
            self._populate_preview_table(self.view_breakdown_table, [], ["Lot Number", "Quantity (kg)"],
                                         ['lot_number', 'quantity_kg'])
            self._populate_preview_table(self.view_excess_table, [], ["Associated Lot", "Excess Qty (kg)"],
                                         ['lot_number', 'quantity_kg'])
            self.view_breakdown_total_label.setText("<b>Total: 0.00 kg</b>");
            self.view_excess_total_label.setText("<b>Total: 0.00 kg</b>")

    def _load_from_fg_passed_inventory(self):
        if self.current_editing_ref:
            QMessageBox.warning(self, "Update Mode Active",
                                "Cannot load new inventory while updating. Please cancel the current update first.");
            return
        dialog = InventorySelectionDialog(self, self.engine, self.product_code_combo.currentText().strip(),
                                          self.lot_number_edit.text().strip())
        if dialog.exec():
            transfer_data = dialog.get_transfer_data()
            if not transfer_data: return
            self._clear_form()
            total_qty = sum(item['quantity_kg'] for item in transfer_data);
            num_lots = len(transfer_data);
            product_code = transfer_data[0]['product_code'] if transfer_data else ""
            breakdown_lots = []
            for item in transfer_data:
                source_lot = item['lot_number'];
                qty = item['quantity_kg']
                new_lot, ok = QInputDialog.getText(self, "Enter New Failed Lot",
                                                   f"Enter the NEW lot number for the failed quantity ({qty} kg) from source lot '{source_lot}':",
                                                   text=f"{source_lot}-FAILED")
                if not ok or not new_lot.strip():
                    QMessageBox.warning(self, "Cancelled", "Lot number assignment cancelled. Load operation aborted.");
                    self._clear_form();
                    return
                breakdown_lots.append(
                    {'lot_number': new_lot.strip().upper(), 'quantity_kg': qty, 'source_lot': source_lot})
            self.product_code_combo.setCurrentText(product_code);
            self.quantity_edit.setText(format_float_with_commas(total_qty))
            self.lot_number_edit.setText(transfer_data[0]['lot_number'] if num_lots == 1 else "MULTIPLE LOTS LOADED")
            self.preview_data = {"breakdown": breakdown_lots, "excess": [],
                                 "weight_per_lot": float(total_qty / num_lots if num_lots > 0 else 0)}
            self.weight_per_lot_edit.setText(format_float_with_commas(self.preview_data['weight_per_lot']));
            self._populate_preview_widgets(self.preview_data)
            self.inventory_status_label.setText(
                f"Loaded {num_lots} lot(s). Total Qty: {format_float_with_commas(total_qty)} kg. Ready to save.");
            self.inventory_status_label.setStyleSheet("font-weight: bold; color: #28a745;")
            QMessageBox.information(self, "Inventory Loaded",
                                    "Stock loaded successfully. Please verify details and click 'Save Endorsement'.")

    def _create_combo_with_manage_button(self, table_name, combo):
        layout = QHBoxLayout();
        layout.setContentsMargins(0, 0, 0, 0);
        layout.addWidget(combo, 1);
        manage_btn = QPushButton(" Manage...");
        if fa: manage_btn.setIcon(fa.icon('fa5s.plus-circle', color=ICON_COLOR))
        title = {"qcf_endorsers": "Endorser", "warehouses": "Warehouse", "qcf_receivers": "Receiver",
                 "qce_bag_numbers": "Bag Number"}.get(table_name, "Item")
        manage_btn.clicked.connect(lambda: self._manage_list(table_name, "name", f"Manage {title}s", combo));
        layout.addWidget(manage_btn);
        return layout

    def _manage_list(self, table_name, column_name, title, combo_to_update):
        dialog = AddNewDialog(self, title, title.replace("Manage ", "").rstrip('s'))
        if dialog.exec() and dialog.new_value:
            try:
                with self.engine.connect() as conn, conn.begin():
                    conn.execute(text(
                        f"INSERT INTO {table_name} ({column_name}) VALUES (:val) ON CONFLICT ({column_name}) DO NOTHING"),
                        {"val": dialog.new_value})
                self._load_combobox_data();
                combo_to_update.setCurrentText(dialog.new_value)
            except Exception as e:
                QMessageBox.critical(self, "Database Error", f"Could not add item: {e}")

    def _on_tab_changed(self, index):
        entry_tab_index = self.tab_widget.indexOf(self.entry_tab)

        # Ensure update mode is cancelled if we leave the entry tab.
        if index != entry_tab_index and self.current_editing_ref is not None:
            QMessageBox.warning(self, "Update Interrupted",
                                f"Update operation for {self.current_editing_ref} was cancelled due to tab change.")
            self._clear_form()

        if index == self.tab_widget.indexOf(self.view_tab):
            self._load_all_endorsements();
            self._on_record_selection_changed()
        elif index == entry_tab_index and not self.current_editing_ref:
            self._load_combobox_data()
        elif index == self.tab_widget.indexOf(self.deleted_tab):
            self._load_deleted_records()

    def _clear_form(self):
        is_update_mode = self.current_editing_ref is not None
        self.current_editing_ref, self.preview_data = None, None;
        self.cancel_update_btn.hide();
        self.save_btn.setText(" Save Endorsement")
        self.sys_ref_no_edit.clear();
        self.lot_number_edit.clear();
        self.quantity_edit.setText("0.00");
        self.weight_per_lot_edit.setText("0.00")
        self.is_lot_range_check.setChecked(False);
        self._clear_form_previews();
        self._load_combobox_data()

        # When clearing the form after a save (not currently in update mode),
        # restore the retained values, including the date.
        if not is_update_mode:
            self.form_ref_no_edit.setText(self._retained_form_ref);
            # FIX: Retain Endorsement Date after save/update
            self.endorsement_date_edit.setDate(self._retained_date);
            self.received_date_edit.setDate(QDate.currentDate());
            self.remarks_edit.setText(self._retained_remarks)
            if self._retained_product_code: self.product_code_combo.setCurrentText(self._retained_product_code)
            if self._retained_endorsed_by: self.endorsed_by_combo.setCurrentText(self._retained_endorsed_by)
            if self._retained_warehouse: self.warehouse_combo.setCurrentText(self._retained_warehouse)
            if self._retained_received_by: self.received_by_name_combo.setCurrentText(self._retained_received_by)
            if self._retained_bag_no: self.bag_no_combo.setCurrentText(self._retained_bag_no)
        else:
            # If canceling an update, reset to default empty/current date
            self.form_ref_no_edit.clear();
            self.remarks_edit.clear();
            self.endorsement_date_edit.setDate(QDate.currentDate());
            self.received_date_edit.setDate(QDate.currentDate())

        self.form_ref_no_edit.setFocus()

    def _clear_form_previews(self):
        self.preview_data = None;
        self.preview_breakdown_table.setRowCount(0);
        self.preview_excess_table.setRowCount(0)
        self.breakdown_total_label.setText("<b>Total: 0.00 kg</b>");
        self.excess_total_label.setText("<b>Total: 0.00 kg</b>")

    def _load_combobox_data(self):
        queries = {
            "product_code_combo": "SELECT DISTINCT prod_code FROM legacy_production WHERE prod_code IS NOT NULL AND prod_code != '' ORDER BY prod_code",
            "endorsed_by_combo": "SELECT name FROM qcf_endorsers ORDER BY name",
            "warehouse_combo": "SELECT name FROM warehouses ORDER BY name",
            "received_by_name_combo": "SELECT name FROM qcf_receivers ORDER BY name",
            "bag_no_combo": "SELECT name FROM qce_bag_numbers ORDER BY name"}
        try:
            with self.engine.connect() as conn:
                for combo_name, query in queries.items():
                    combo = getattr(self, combo_name);
                    current_text = combo.currentText();
                    items = conn.execute(text(query)).scalars().all()
                    combo.blockSignals(True);
                    combo.clear();
                    combo.addItems([""] + [item for item in items if item]);
                    index = combo.findText(current_text)
                    combo.setCurrentIndex(index if index != -1 else (0 if combo.count() > 0 else -1));
                    combo.blockSignals(False)
        except Exception as e:
            print(f"Error loading combobox data: {e}")

    def _validate_required_fields(self):
        required = {"Form Ref": self.form_ref_no_edit, "Date Endorsed": self.endorsement_date_edit,
                    "Product Code": self.product_code_combo, "Lot Number/Range": self.lot_number_edit,
                    "Endorsed By": self.endorsed_by_combo, "Warehouse": self.warehouse_combo,
                    "Received By": self.received_by_name_combo, "Bag Number": self.bag_no_combo,
                    "Received Date": self.received_date_edit}
        missing = []
        for name, widget in required.items():
            is_empty = False
            if isinstance(widget, (QLineEdit, QDateEdit)):
                if not widget.text().strip(): is_empty = True
            elif isinstance(widget, QComboBox):
                if not widget.currentText().strip(): is_empty = True
            if is_empty: missing.append(name)
        if missing:
            QMessageBox.warning(self, "Input Error",
                                "Please complete all required fields:\n\n- " + "\n- ".join(missing))
            return False
        return True

    def _preview_endorsement(self):
        try:
            if self.preview_data and self.preview_data.get('breakdown') and any(
                    d.get('source_lot') for d in self.preview_data['breakdown']) and not self.current_editing_ref:
                self._populate_preview_widgets(self.preview_data);
                QMessageBox.information(self, "Preview Ready", "Preview is already populated. You can now save.");
                return
            self._clear_form_previews()
            self.preview_data = self._validate_and_calculate_lots()
            if self.preview_data: self._populate_preview_widgets(self.preview_data)
        except Exception as e:
            error_message = f"An unexpected error occurred during preview:\n\n{str(e)}";
            detailed_error = traceback.format_exc()
            print("--- PREVIEW ERROR ---");
            print(detailed_error);
            print("---------------------")
            msg_box = QMessageBox(self);
            msg_box.setIcon(QMessageBox.Icon.Critical);
            msg_box.setWindowTitle("Preview Error");
            msg_box.setText(error_message);
            msg_box.setDetailedText(detailed_error);
            msg_box.setStandardButtons(QMessageBox.StandardButton.Ok);
            msg_box.exec()

    def _validate_and_calculate_lots(self):
        if not self._validate_required_fields(): return None
        try:
            total_qty, weight_per_lot, lot_input = self.quantity_edit.value(), self.weight_per_lot_edit.value(), self.lot_number_edit.text().strip()
            if weight_per_lot <= 0: QMessageBox.warning(self, "Input Error", "Weight per Lot must be > 0."); return None
            excess_handling_method = 'NEW_LOT'
            if total_qty > 0 and weight_per_lot > 0 and (
                    total_qty % weight_per_lot > 0) and not self.is_lot_range_check.isChecked():
                reply = QMessageBox.question(self, "Excess Quantity Handling",
                                             "An excess quantity was calculated.\n\nCreate a new lot number for the excess?\n\nClick 'No' to use the original lot number.",
                                             QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
                if reply == QMessageBox.StandardButton.No:
                    excess_handling_method = 'RETAIN_ORIGINAL_LOT'
                elif reply == QMessageBox.StandardButton.Cancel:
                    return None
            return self._perform_lot_calculation(Decimal(str(total_qty)), Decimal(str(weight_per_lot)), lot_input,
                                                 self.is_lot_range_check.isChecked(), excess_handling_method)
        except (InvalidOperation, ValueError):
            QMessageBox.warning(self, "Input Error", "Invalid numbers for Quantity or Weight per Lot.");
            return None

    def _perform_lot_calculation(self, total_qty, weight_per_lot, lot_input, is_range, excess_handling_method):
        num_full_lots, excess_qty = int(total_qty // weight_per_lot), total_qty % weight_per_lot
        breakdown_data, excess_data, calculated_lots = [], [], []
        if is_range:
            range_info = self._parse_lot_range(lot_input, num_full_lots)
            if not range_info: return None
            calculated_lots = range_info['lots']
            breakdown_data = [{'lot_number': lot, 'quantity_kg': float(weight_per_lot), 'source_lot': lot} for lot in
                              calculated_lots]
        else:
            calculated_lots = [lot_input.upper()] * num_full_lots
            if calculated_lots:
                breakdown_data = [{'lot_number': lot, 'quantity_kg': float(weight_per_lot), 'source_lot': lot_input} for
                                  lot in calculated_lots]
        if excess_qty > 0:
            if not is_range and excess_handling_method == 'RETAIN_ORIGINAL_LOT':
                excess_data.append(
                    {'lot_number': lot_input.upper(), 'quantity_kg': float(excess_qty), 'source_lot': lot_input})
            else:
                last_lot = calculated_lots[-1] if calculated_lots else lot_input.upper()
                match = re.search(r'([A-Z]*?)(\d+)([A-Z]*?)$', last_lot)
                excess_lot_number = f"{last_lot}-EXCESS"
                if match:
                    try:
                        prefix, num_part, suffix = match.groups()
                        next_num = str(int(num_part) + 1).zfill(len(num_part))
                        excess_lot_number = f"{prefix}{next_num}{suffix}"
                    except ValueError:
                        pass
                source_for_excess = calculated_lots[-1] if calculated_lots else lot_input
                excess_data.append({'lot_number': excess_lot_number, 'quantity_kg': float(excess_qty),
                                    'source_lot': source_for_excess})
        return {"breakdown": breakdown_data, "excess": excess_data}

    def _parse_lot_range(self, lot_input, num_lots_needed):
        try:
            parts = lot_input.split('-')
            if len(parts) != 2: raise ValueError("Lot range must contain exactly one hyphen.")
            start_str, end_str = [s.strip().upper() for s in parts]
            start_match = re.match(r'^([A-Z]*?)(\d+)([A-Z]*?)$', start_str)
            end_match = re.match(r'^([A-Z]*?)(\d+)([A-Z]*?)$', end_str)
            if not start_match or not end_match or start_match.groups()[::2] != end_match.groups()[
                                                                                ::2]: raise ValueError(
                "Format invalid or prefixes/suffixes mismatch.")
            prefix, start_num_str, suffix = start_match.groups()
            _, end_num_str, _ = end_match.groups()
            start_num, end_num, num_len = int(start_num_str), int(end_num_str), len(start_num_str)
            if start_num > end_num: raise ValueError("Start lot > end lot.")
            available_lots = end_num - start_num + 1
            if available_lots < num_lots_needed:
                QMessageBox.warning(self, "Lot Range Too Small",
                                    f"The provided range has {available_lots} lots, but {num_lots_needed} are required based on the quantity.");
                return None
            return {'lots': [f"{prefix}{str(start_num + i).zfill(num_len)}{suffix}" for i in range(num_lots_needed)],
                    'end_lot': end_str}
        except Exception as e:
            QMessageBox.critical(self, "Lot Range Error", f"Could not parse lot range '{lot_input}': {e}");
            return None

    def _populate_preview_widgets(self, data):
        breakdown_data, excess_data = data.get('breakdown', []), data.get('excess', [])
        self._populate_preview_table(self.preview_breakdown_table, breakdown_data,
                                     ["New Failed Lot", "Quantity (kg)", "Source Lot"],
                                     ['lot_number', 'quantity_kg', 'source_lot'])
        breakdown_total = sum(Decimal(str(item.get('quantity_kg', 0) or 0)) for item in breakdown_data)
        self.breakdown_total_label.setText(f"<b>Total: {format_float_with_commas(breakdown_total)} kg</b>")
        self._populate_preview_table(self.preview_excess_table, excess_data,
                                     ["New Failed Lot", "Excess Qty (kg)", "Source Lot"],
                                     ['lot_number', 'quantity_kg', 'source_lot'])
        excess_total = sum(Decimal(str(item.get('quantity_kg', 0) or 0)) for item in excess_data)
        self.excess_total_label.setText(f"<b>Total: {format_float_with_commas(excess_total)} kg</b>")

    def _save_endorsement(self):
        if not self._validate_required_fields(): return
        if not self.preview_data: QMessageBox.warning(self, "Preview Required",
                                                      "Please click 'Preview Breakdown' before saving."); return
        is_update = self.current_editing_ref is not None;
        sys_ref_no = self.current_editing_ref if is_update else self._generate_system_ref_no()
        all_lots_to_log = self.preview_data.get('breakdown', []) + self.preview_data.get('excess', [])
        if not all_lots_to_log: QMessageBox.critical(self, "Save Error",
                                                     "No lots were generated or loaded for saving."); return

        # 1. Capture current form data before processing
        endorsement_date_py = self.endorsement_date_edit.date().toPyDate()
        received_date_py = self.received_date_edit.date().toPyDate()

        primary_data = {"system_ref_no": sys_ref_no, "form_ref_no": self.form_ref_no_edit.text().strip(),
                        "endorsement_date": endorsement_date_py,
                        "product_code": self.product_code_combo.currentText(),
                        "lot_number": self.lot_number_edit.text().strip(), "quantity_kg": self.quantity_edit.value(),
                        "weight_per_lot": self.weight_per_lot_edit.value(), "remarks": self.remarks_edit.text().strip(),
                        "endorsed_by": self.endorsed_by_combo.currentText(),
                        "warehouse": self.warehouse_combo.currentText(),
                        "received_by_name": self.received_by_name_combo.currentText(),
                        "received_date_time": received_date_py,
                        "bag_no": self.bag_no_combo.currentText(), "encoded_by": self.username,
                        "encoded_on": datetime.now(), "edited_by": self.username, "edited_on": datetime.now()}
        try:
            with self.engine.connect() as conn, conn.begin():
                if is_update:
                    conn.execute(text("DELETE FROM qcf_endorsements_secondary WHERE system_ref_no = :ref"),
                                 {"ref": sys_ref_no});
                    conn.execute(text("DELETE FROM qcf_endorsements_excess WHERE system_ref_no = :ref"),
                                 {"ref": sys_ref_no})
                    conn.execute(text(
                        "DELETE FROM failed_transactions WHERE source_ref_no = :ref AND transaction_type = 'QC_FAILED_ENDORSEMENT'"),
                        {"ref": sys_ref_no});
                    conn.execute(text(
                        "DELETE FROM transactions WHERE source_ref_no = :ref AND transaction_type = 'QC_TRANSFER_OUT'"),
                        {"ref": sys_ref_no})
                    update_sql = text(
                        "UPDATE qcf_endorsements_primary SET form_ref_no=:form_ref_no, endorsement_date=:endorsement_date, product_code=:product_code, lot_number=:lot_number, quantity_kg=:quantity_kg, weight_per_lot=:weight_per_lot, remarks=:remarks, endorsed_by=:endorsed_by, warehouse=:warehouse, received_by_name=:received_by_name, received_date_time=:received_date_time, bag_no=:bag_no, edited_by=:edited_by, edited_on=:edited_on WHERE system_ref_no = :system_ref_no")
                    conn.execute(update_sql, primary_data);
                    self.log_audit_trail("UPDATE_QC_FAILED", f"Updated endorsement: {sys_ref_no}");
                    action_text = "updated"
                else:
                    insert_sql = text(
                        "INSERT INTO qcf_endorsements_primary (system_ref_no, form_ref_no, endorsement_date, product_code, lot_number, quantity_kg, weight_per_lot, remarks, endorsed_by, warehouse, received_by_name, received_date_time, bag_no, encoded_by, encoded_on, edited_by, edited_on) VALUES (:system_ref_no, :form_ref_no, :endorsement_date, :product_code, :lot_number, :quantity_kg, :weight_per_lot, :remarks, :endorsed_by, :warehouse, :received_by_name, :received_date_time, :bag_no, :encoded_by, :encoded_on, :edited_by, :edited_on)")
                    conn.execute(insert_sql, primary_data);
                    self.log_audit_trail("CREATE_QC_FAILED", f"Created endorsement: {sys_ref_no}");
                    action_text = "saved"
                secondary_records = [
                    {'system_ref_no': sys_ref_no, 'lot_number': lot['lot_number'], 'quantity_kg': lot['quantity_kg']}
                    for lot in self.preview_data.get('breakdown', [])]
                excess_records = [
                    {'system_ref_no': sys_ref_no, 'lot_number': lot['lot_number'], 'quantity_kg': lot['quantity_kg']}
                    for lot in self.preview_data.get('excess', [])]
                if secondary_records: conn.execute(text(
                    "INSERT INTO qcf_endorsements_secondary (system_ref_no, lot_number, quantity_kg) VALUES (:system_ref_no, :lot_number, :quantity_kg)"),
                    secondary_records)
                if excess_records: conn.execute(text(
                    "INSERT INTO qcf_endorsements_excess (system_ref_no, lot_number, quantity_kg) VALUES (:system_ref_no, :lot_number, :quantity_kg)"),
                    excess_records)
                failed_txs, main_txs = [], []
                for lot_data in all_lots_to_log:
                    source_lot = lot_data.get('source_lot', primary_data['lot_number'])
                    failed_txs.append({"transaction_date": primary_data["endorsement_date"],
                                       "transaction_type": "QC_FAILED_ENDORSEMENT", "source_ref_no": sys_ref_no,
                                       "product_code": primary_data["product_code"],
                                       "lot_number": lot_data["lot_number"], "quantity_in": lot_data["quantity_kg"],
                                       "quantity_out": 0, "unit": "KG.", "warehouse": primary_data["warehouse"],
                                       "encoded_by": self.username,
                                       "remarks": f"QC Failure: {primary_data['remarks']}. Bag: {primary_data['bag_no']}. Orig Lot: {source_lot}"})
                    main_txs.append(
                        {"transaction_date": primary_data["endorsement_date"], "transaction_type": "QC_TRANSFER_OUT",
                         "source_ref_no": sys_ref_no, "product_code": primary_data["product_code"],
                         "lot_number": source_lot, "quantity_in": 0, "quantity_out": lot_data["quantity_kg"],
                         "unit": "KG.", "warehouse": primary_data["warehouse"], "encoded_by": self.username,
                         "remarks": f"Transfer OUT for QC Failed endorsement: {sys_ref_no}. New Lot: {lot_data['lot_number']}"})
                if failed_txs: conn.execute(text(
                    "INSERT INTO failed_transactions (transaction_date, transaction_type, source_ref_no, product_code, lot_number, quantity_in, quantity_out, unit, warehouse, encoded_by, remarks) VALUES (:transaction_date, :transaction_type, :source_ref_no, :product_code, :lot_number, :quantity_in, :quantity_out, :unit, :warehouse, :encoded_by, :remarks)"),
                    failed_txs)
                if main_txs: conn.execute(text(
                    "INSERT INTO transactions (transaction_date, transaction_type, source_ref_no, product_code, lot_number, quantity_in, quantity_out, unit, warehouse, encoded_by, remarks) VALUES (:transaction_date, :transaction_type, :source_ref_no, :product_code, :lot_number, :quantity_in, :quantity_out, :unit, :warehouse, :encoded_by, :remarks)"),
                    main_txs)

            # FIX: Update retained variables after SAVE/UPDATE
            self._retained_form_ref = self.form_ref_no_edit.text().strip()
            self._retained_date = self.endorsement_date_edit.date()  # Keep QDate object
            self._retained_product_code = self.product_code_combo.currentText()
            self._retained_endorsed_by = self.endorsed_by_combo.currentText()
            self._retained_warehouse = self.warehouse_combo.currentText()
            self._retained_received_by = self.received_by_name_combo.currentText()
            self._retained_remarks = self.remarks_edit.text().strip()
            self._retained_bag_no = self.bag_no_combo.currentText()

            self._clear_form();
            self._load_all_endorsements();
            self.tab_widget.setCurrentIndex(self.tab_widget.indexOf(self.view_tab));
            QMessageBox.information(self, "Success",
                                    f"Endorsement {sys_ref_no} has been {action_text} and stock transferred.")
        except Exception as e:
            QMessageBox.critical(self, "Database Error",
                                 f"An error occurred while saving: {e}\n{traceback.format_exc()}");
            self._retained_form_ref = ""

    def _delete_record(self):
        selected_row = self.records_table.currentRow()
        if selected_row < 0: return
        ref_no = self.records_table.item(selected_row, 0).text()
        password, ok = QInputDialog.getText(self, "Password Required", "Enter password to delete:",
                                            QLineEdit.EchoMode.Password)
        if not ok: return
        if password != ADMIN_PASSWORD:
            QMessageBox.warning(self, "Incorrect Password", "Deletion cancelled.");
            return
        reply = QMessageBox.question(self, "Confirm Deletion",
                                     f"Are you sure you want to delete endorsement {ref_no}?\n\nThis will reverse the stock transfer by removing the transaction records.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                with self.engine.connect() as conn, conn.begin():
                    conn.execute(text(
                        "UPDATE qcf_endorsements_primary SET is_deleted = TRUE, edited_by = :user, edited_on = :now WHERE system_ref_no = :ref"),
                        {"ref": ref_no, "user": self.username, "now": datetime.now()})
                    conn.execute(text(
                        "DELETE FROM failed_transactions WHERE source_ref_no = :ref AND transaction_type = 'QC_FAILED_ENDORSEMENT'"),
                        {"ref": ref_no})
                    conn.execute(text(
                        "DELETE FROM transactions WHERE source_ref_no = :ref AND transaction_type = 'QC_TRANSFER_OUT'"),
                        {"ref": ref_no})
                self.log_audit_trail("DELETE_QC_FAILED_REVERSE",
                                     f"Soft-deleted endorsement {ref_no} and reversed stock transfer.")
                QMessageBox.information(self, "Success",
                                        f"Endorsement {ref_no} has been deleted and stock transfer reversed.")
                self._load_all_endorsements()
            except Exception as e:
                error_message = f"An unexpected error occurred during deletion:\n\n{str(e)}";
                detailed_error = traceback.format_exc()
                print("--- DELETE ERROR ---");
                print(detailed_error);
                print("--------------------")
                msg_box = QMessageBox(self);
                msg_box.setIcon(QMessageBox.Icon.Critical);
                msg_box.setWindowTitle("Deletion Error");
                msg_box.setText(error_message);
                msg_box.setDetailedText(detailed_error);
                msg_box.setStandardButtons(QMessageBox.StandardButton.Ok);
                msg_box.exec()

    def _restore_record(self):
        selected_row = self.deleted_records_table.currentRow()
        if selected_row < 0: return
        ref_no = self.deleted_records_table.item(selected_row, 0).text()
        if QMessageBox.question(self, "Confirm Restore",
                                f"Are you sure you want to restore endorsement <b>{ref_no}</b>?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            try:
                with self.engine.connect() as conn, conn.begin():
                    conn.execute(text(
                        "UPDATE qcf_endorsements_primary SET is_deleted = FALSE, edited_by = :user, edited_on = :now WHERE system_ref_no = :ref"),
                        {"ref": ref_no, "user": self.username, "now": datetime.now()})
                    primary_data = conn.execute(
                        text("SELECT * FROM qcf_endorsements_primary WHERE system_ref_no = :ref"),
                        {"ref": ref_no}).mappings().one()
                    all_lots_data = conn.execute(text(
                        "SELECT lot_number, quantity_kg FROM qcf_endorsements_secondary WHERE system_ref_no = :ref UNION ALL SELECT lot_number, quantity_kg FROM qcf_endorsements_excess WHERE system_ref_no = :ref"),
                        {"ref": ref_no}).mappings().all()
                    failed_txs, main_txs, source_lot_input = [], [], primary_data.get('lot_number')
                    for lot in all_lots_data:
                        failed_txs.append({"transaction_date": primary_data["endorsement_date"],
                                           "transaction_type": "QC_FAILED_ENDORSEMENT", "source_ref_no": ref_no,
                                           "product_code": primary_data["product_code"],
                                           "lot_number": lot["lot_number"], "quantity_in": lot["quantity_kg"],
                                           "quantity_out": 0, "unit": "KG.", "warehouse": primary_data["warehouse"],
                                           "encoded_by": self.username,
                                           "remarks": f"RESTORED: QC Failure {primary_data.get('remarks', 'N/A')}. Bag: {primary_data.get('bag_no', 'N/A')}. Orig Lot Input: {source_lot_input}"})
                        main_txs.append({"transaction_date": primary_data["endorsement_date"],
                                         "transaction_type": "QC_TRANSFER_OUT", "source_ref_no": ref_no,
                                         "product_code": primary_data["product_code"], "lot_number": source_lot_input,
                                         "quantity_in": 0, "quantity_out": lot["quantity_kg"], "unit": "KG.",
                                         "warehouse": primary_data["warehouse"], "encoded_by": self.username,
                                         "remarks": f"RESTORED: Transfer OUT for QC Failed endorsement: {ref_no}. Failed Lot: {lot['lot_number']}"})
                    if failed_txs:
                        conn.execute(text(
                            "DELETE FROM failed_transactions WHERE source_ref_no = :ref AND transaction_type = 'QC_FAILED_ENDORSEMENT'"),
                            {"ref": ref_no})
                        conn.execute(text(
                            "INSERT INTO failed_transactions (transaction_date, transaction_type, source_ref_no, product_code, lot_number, quantity_in, quantity_out, unit, warehouse, encoded_by, remarks) VALUES (:transaction_date, :transaction_type, :source_ref_no, :product_code, :lot_number, :quantity_in, :quantity_out, :unit, :warehouse, :encoded_by, :remarks)"),
                            failed_txs)
                    if main_txs:
                        conn.execute(text(
                            "DELETE FROM transactions WHERE source_ref_no = :ref AND transaction_type = 'QC_TRANSFER_OUT'"),
                            {"ref": ref_no})
                        conn.execute(text(
                            "INSERT INTO transactions (transaction_date, transaction_type, source_ref_no, product_code, lot_number, quantity_in, quantity_out, unit, warehouse, encoded_by, remarks) VALUES (:transaction_date, :transaction_type, :source_ref_no, :product_code, :lot_number, :quantity_in, :quantity_out, :unit, :warehouse, :encoded_by, :remarks)"),
                            main_txs)
                self.log_audit_trail("RESTORE_QC_FAILED_REINSTATE",
                                     f"Restored endorsement {ref_no} and reinstated inventory transfer.");
                QMessageBox.information(self, "Success", f"Endorsement {ref_no} has been restored.");
                self._load_deleted_records();
                self._load_all_endorsements()
            except Exception as e:
                error_message = f"An unexpected error occurred during restore:\n\n{str(e)}";
                detailed_error = traceback.format_exc()
                print("--- RESTORE ERROR ---");
                print(detailed_error);
                print("---------------------")
                msg_box = QMessageBox(self);
                msg_box.setIcon(QMessageBox.Icon.Critical);
                msg_box.setWindowTitle("Restore Error");
                msg_box.setText(error_message);
                msg_box.setDetailedText(detailed_error);
                msg_box.setStandardButtons(QMessageBox.StandardButton.Ok);
                msg_box.exec()

    def _generate_system_ref_no(self):
        prefix = f"QCF-{datetime.now().strftime('%y%m')}-"
        try:
            with self.engine.connect() as conn:
                last_ref = conn.execute(text(
                    "SELECT system_ref_no FROM qcf_endorsements_primary WHERE system_ref_no LIKE :p ORDER BY id DESC LIMIT 1"),
                    {"p": f"{prefix}%"}).scalar_one_or_none()
                return f"{prefix}{int(last_ref.split('-')[-1]) + 1 if last_ref else 1:04d}"
        except:
            return f"{prefix}0001"

    def _populate_records_table(self, table, data, headers):
        table.setRowCount(0);
        table.setColumnCount(len(headers));
        table.setHorizontalHeaderLabels(headers)
        if not data: table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch); return
        table.setRowCount(len(data));
        keys = list(data[0].keys())
        for i, row_data in enumerate(data):
            for j, key in enumerate(keys):
                val = row_data.get(key);
                item_text = format_float_with_commas(val) if isinstance(val, (float, Decimal)) else str(val or "")
                item = QTableWidgetItem(item_text)
                if isinstance(val, (Decimal, float)): item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(i, j, item)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        if table.columnCount() > 4: table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)

    def _populate_preview_table(self, table_widget: QTableWidget, data: list, headers: list, key_names: list):
        table_widget.setRowCount(0);
        table_widget.setColumnCount(len(headers));
        table_widget.setHorizontalHeaderLabels(headers)
        if not data: table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch); return
        table_widget.setRowCount(len(data))
        for row, row_data in enumerate(data):
            for col_idx, key in enumerate(key_names):
                value = row_data.get(key)
                item_text = format_float_with_commas(value) if isinstance(value, (Decimal, float)) else str(value or "")
                item = QTableWidgetItem(item_text)
                if isinstance(value, (Decimal, float)): item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table_widget.setItem(row, col_idx, item)
        table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        if table_widget.columnCount() > 0: table_widget.horizontalHeader().setSectionResizeMode(0,
                                                                                                QHeaderView.ResizeMode.Stretch)

    def _load_all_endorsements(self):
        search_term = f"%{self.search_edit.text().strip()}%";
        offset = (self.current_page - 1) * self.records_per_page
        try:
            with self.engine.connect() as conn:
                like_op = "ILIKE"  # For PostgreSQL
                filter_clause = f" AND (system_ref_no {like_op} :st OR form_ref_no {like_op} :st OR product_code {like_op} :st OR lot_number {like_op} :st)" if self.search_edit.text() else ""
                count_res = conn.execute(text(
                    f"SELECT COUNT(id) FROM qcf_endorsements_primary WHERE is_deleted IS NOT TRUE {filter_clause}"),
                    {'st': search_term}).scalar_one()
                self.total_records = count_res
                query = text(
                    f"SELECT system_ref_no, form_ref_no, endorsement_date, product_code, lot_number, quantity_kg, remarks FROM qcf_endorsements_primary WHERE is_deleted IS NOT TRUE {filter_clause} ORDER BY id DESC LIMIT :limit OFFSET :offset")
                results = conn.execute(query, {'limit': self.records_per_page, 'offset': offset,
                                               'st': search_term}).mappings().all()
            self._populate_records_table(self.records_table, results,
                                         ["Sys Ref", "Form Ref", "Date", "Product Code", "Lot Input", "Qty (kg)",
                                          "Remarks"])
            self._update_pagination_controls();
            self._on_record_selection_changed()
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load QC endorsements: {e}");
            self._populate_records_table(self.records_table, [], [])

    def _load_deleted_records(self):
        search_term = f"%{self.deleted_search_edit.text().strip()}%"
        try:
            with self.engine.connect() as conn:
                like_op = "ILIKE"  # For PostgreSQL
                filter_clause = f" AND (system_ref_no {like_op} :st OR form_ref_no {like_op} :st OR product_code {like_op} :st OR edited_by {like_op} :st)" if self.deleted_search_edit.text() else ""
                query = text(
                    f"SELECT system_ref_no, form_ref_no, endorsement_date, product_code, edited_by, edited_on FROM qcf_endorsements_primary WHERE is_deleted = TRUE {filter_clause} ORDER BY edited_on DESC")
                res = conn.execute(query, {'st': search_term}).mappings().all()
            self._populate_records_table(self.deleted_records_table, res,
                                         ["Sys Ref", "Form Ref", "Date", "Product", "Deleted By", "Deleted On"])
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load deleted records: {e}");
            self._populate_records_table(self.deleted_records_table, [], [])

    def _on_search_text_changed(self):
        self.current_page = 1;
        self._load_all_endorsements()

    def _go_to_prev_page(self):
        if self.current_page > 1: self.current_page -= 1; self._load_all_endorsements()

    def _go_to_next_page(self):
        if self.current_page < self.total_pages: self.current_page += 1; self._load_all_endorsements()

    def _update_pagination_controls(self):
        self.total_pages = (self.total_records + self.records_per_page - 1) // self.records_per_page or 1
        self.page_label.setText(f"Page {self.current_page} of {self.total_pages}");
        self.prev_btn.setEnabled(self.current_page > 1);
        self.next_btn.setEnabled(self.current_page < self.total_pages)

    def _show_records_table_context_menu(self, pos):
        selected_row = self.records_table.rowAt(pos.y())
        if selected_row < 0:
            if not self.records_table.selectedItems(): return
        else:
            self.records_table.selectRow(selected_row)
        if not self.records_table.selectedItems(): return
        menu = QMenu();
        view_action, edit_action, delete_action = menu.addAction("View Details"), menu.addAction(
            "Load for Update"), menu.addAction("Delete Record")
        if fa: view_action.setIcon(fa.icon('fa5s.eye', color=ICON_COLOR)); edit_action.setIcon(
            fa.icon('fa5s.edit', color='#f39c12')); delete_action.setIcon(fa.icon('fa5s.trash-alt', color='#e63946'))
        action = menu.exec(self.records_table.mapToGlobal(pos))
        if action == view_action:
            self.tab_widget.setCurrentWidget(self.view_details_tab);
            self._show_selected_record_in_view_tab()
        elif action == edit_action:
            self._load_record_for_update()
        elif action == delete_action:
            self._delete_record()

    def _show_deleted_table_context_menu(self, pos):
        selected_row = self.deleted_records_table.rowAt(pos.y())
        if selected_row < 0:
            if not self.deleted_records_table.selectedItems(): return
        else:
            self.deleted_records_table.selectRow(selected_row)
        if not self.deleted_records_table.selectedItems(): return
        menu = QMenu();
        restore_action = menu.addAction("Restore Record")
        if fa: restore_action.setIcon(fa.icon('fa5s.undo', color='green'))
        action = menu.exec(self.deleted_records_table.mapToGlobal(pos))
        if action == restore_action: self._restore_record()

    def _show_selected_record_in_view_tab(self):
        selected_rows = self.records_table.selectionModel().selectedRows()
        if not selected_rows: return
        ref_no = self.records_table.item(selected_rows[0].row(), 0).text()
        try:
            with self.engine.connect() as conn:
                primary_data = conn.execute(text("SELECT * FROM qcf_endorsements_primary WHERE system_ref_no = :ref"),
                                            {"ref": ref_no}).mappings().first()
                if not primary_data: return
                for layout in [self.view_left_details_layout, self.view_right_details_layout]:
                    while layout.count(): item = layout.takeAt(
                        0); item.widget().deleteLater() if item.widget() else None
                items_list = list(primary_data.items());
                midpoint = (len(items_list) + 1) // 2
                for key, value in items_list[:midpoint]: self._add_view_detail_row(self.view_left_details_layout, key,
                                                                                   value)
                for key, value in items_list[midpoint:]: self._add_view_detail_row(self.view_right_details_layout, key,
                                                                                   value)
                breakdown_data = conn.execute(
                    text("SELECT lot_number, quantity_kg FROM qcf_endorsements_secondary WHERE system_ref_no = :ref"),
                    {"ref": ref_no}).mappings().all()
                self._populate_preview_table(self.view_breakdown_table, breakdown_data, ["Lot Number", "Quantity (kg)"],
                                             ['lot_number', 'quantity_kg'])
                breakdown_total = sum(Decimal(str(d.get('quantity_kg', 0) or 0)) for d in breakdown_data);
                self.view_breakdown_total_label.setText(f"<b>Total: {format_float_with_commas(breakdown_total)} kg</b>")
                excess_data = conn.execute(
                    text("SELECT lot_number, quantity_kg FROM qcf_endorsements_excess WHERE system_ref_no = :ref"),
                    {"ref": ref_no}).mappings().all()
                self._populate_preview_table(self.view_excess_table, excess_data, ["Associated Lot", "Excess Qty (kg)"],
                                             ['lot_number', 'quantity_kg'])
                excess_total = sum(Decimal(str(d.get('quantity_kg', 0) or 0)) for d in excess_data);
                self.view_excess_total_label.setText(f"<b>Total: {format_float_with_commas(excess_total)} kg</b>")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load details for {ref_no or 'selected record'}: {e}")

    def _add_view_detail_row(self, layout, key, value):
        display_text = str(value) if value is not None else "N/A"
        if isinstance(value, datetime):
            display_text = QDateTime(value).toString('yyyy-MM-dd hh:mm AP')
        elif isinstance(value, date):
            display_text = value.strftime('%Y-%m-%d')
        elif isinstance(value, (Decimal, float)):
            display_text = format_float_with_commas(value)
        layout.addRow(QLabel(f"<b>{key.replace('_', ' ').title()}:</b>"), QLabel(display_text))

    def _load_record_for_update(self):
        # BEGIN FIX: Comprehensive error handling for tracebacks
        selected_row = self.records_table.currentRow()
        if selected_row < 0: return;

        ref_no = None
        try:
            ref_no = self.records_table.item(selected_row, 0).text()

            with self.engine.connect() as conn:
                record = conn.execute(text("SELECT * FROM qcf_endorsements_primary WHERE system_ref_no = :ref"),
                                      {"ref": ref_no}).mappings().first()
                breakdown_res = conn.execute(
                    text("SELECT lot_number, quantity_kg FROM qcf_endorsements_secondary WHERE system_ref_no = :ref"),
                    {"ref": ref_no}).mappings().all()
                excess_res = conn.execute(
                    text("SELECT lot_number, quantity_kg FROM qcf_endorsements_excess WHERE system_ref_no = :ref"),
                    {"ref": ref_no}).mappings().all()

            if not record:
                QMessageBox.warning(self, "Not Found", f"Record {ref_no} not found.");
                return

            self._clear_form();
            self.current_editing_ref = ref_no;
            self.cancel_update_btn.show();
            self.save_btn.setText(" Update Endorsement");
            self.tab_widget.setCurrentWidget(self.entry_tab)

            self.sys_ref_no_edit.setText(ref_no);
            self.form_ref_no_edit.setText(record.get('form_ref_no', ''))

            endorsement_date_str = str(record.get('endorsement_date', ''));
            if endorsement_date_str:
                self.endorsement_date_edit.setDate(QDate.fromString(endorsement_date_str, "yyyy-MM-dd"))

            received_date_str = str(record.get('received_date_time', ''));
            if received_date_str:
                self.received_date_edit.setDate(QDate.fromString(received_date_str, "yyyy-MM-dd"))

            self.product_code_combo.setCurrentText(record.get('product_code', ''));
            self.lot_number_edit.setText(record.get('lot_number', ''))

            self.quantity_edit.setText(format_float_with_commas(record.get('quantity_kg', 0.0)));
            self.weight_per_lot_edit.setText(format_float_with_commas(record.get('weight_per_lot', 0.0)))

            self.remarks_edit.setText(record.get('remarks', ''));
            self.endorsed_by_combo.setCurrentText(record.get('endorsed_by', ''))
            self.warehouse_combo.setCurrentText(record.get('warehouse', ''));
            self.received_by_name_combo.setCurrentText(record.get('received_by_name', ''))
            self.bag_no_combo.setCurrentText(record.get('bag_no', ''));
            self.is_lot_range_check.setChecked('-' in (record.get('lot_number') or ''))

            source_lot_input = record.get('lot_number', '')
            breakdown_data = [
                {'lot_number': d['lot_number'], 'quantity_kg': d['quantity_kg'], 'source_lot': source_lot_input} for d
                in breakdown_res]
            excess_data = [
                {'lot_number': d['lot_number'], 'quantity_kg': d['quantity_kg'], 'source_lot': source_lot_input} for d
                in excess_res]

            self.preview_data = {"breakdown": breakdown_data, "excess": excess_data};
            self._populate_preview_widgets(self.preview_data)

            self.inventory_status_label.setText("Status: Loaded for Update");
            self.inventory_status_label.setStyleSheet("font-weight: bold; color: #f39c12;")

            QMessageBox.information(self, "Info",
                                    "Record loaded for update. Please Preview Breakdown again before saving changes.")
        except Exception as e:
            error_message = f"Could not load record {ref_no or 'selected'} for update: {e}";
            detailed_error = traceback.format_exc()
            print("--- LOAD FOR UPDATE ERROR ---");
            print(detailed_error);
            print("-----------------------------")

            msg_box = QMessageBox(self);
            msg_box.setIcon(QMessageBox.Icon.Critical);
            msg_box.setWindowTitle("Load Error");
            msg_box.setText(error_message);
            msg_box.setDetailedText(detailed_error);
            msg_box.setStandardButtons(QMessageBox.StandardButton.Ok);
            msg_box.exec()

            self._clear_form()
        # END FIX: Comprehensive error handling


if __name__ == "__main__":
    app = QApplication(sys.argv)
    # This is a mock database for testing. Replace with your actual database connection.
    # For SQLite, use: mock_engine = create_engine("sqlite:///your_database_file.db")
    # For PostgreSQL, use: mock_engine = create_engine("postgresql://user:password@host/dbname")
    mock_engine = create_engine("sqlite:///:memory:")
    try:
        with mock_engine.connect() as conn, conn.begin():
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS qcf_endorsements_primary (id INTEGER PRIMARY KEY, system_ref_no TEXT UNIQUE, form_ref_no TEXT, endorsement_date DATE, product_code TEXT, lot_number TEXT, quantity_kg REAL, weight_per_lot REAL, remarks TEXT, endorsed_by TEXT, warehouse TEXT, received_by_name TEXT, received_date_time DATE, bag_no TEXT, encoded_by TEXT, encoded_on DATETIME, edited_by TEXT, edited_on DATETIME, is_deleted BOOLEAN DEFAULT FALSE);"))
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS qcf_endorsements_secondary (system_ref_no TEXT, lot_number TEXT, quantity_kg REAL);"))
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS qcf_endorsements_excess (system_ref_no TEXT, lot_number TEXT, quantity_kg REAL);"))
            conn.execute(text("CREATE TABLE IF NOT EXISTS legacy_production (prod_code TEXT UNIQUE);"))
            conn.execute(text("CREATE TABLE IF NOT EXISTS qcf_endorsers (name TEXT UNIQUE);"))
            conn.execute(text("CREATE TABLE IF NOT EXISTS warehouses (name TEXT UNIQUE);"))
            conn.execute(text("CREATE TABLE IF NOT EXISTS qcf_receivers (name TEXT UNIQUE);"))
            conn.execute(text("CREATE TABLE IF NOT EXISTS qce_bag_numbers (name TEXT UNIQUE);"))
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS failed_transactions(id INTEGER PRIMARY KEY, transaction_date DATE, transaction_type TEXT, source_ref_no TEXT, product_code TEXT, lot_number TEXT, quantity_in REAL, quantity_out REAL, unit TEXT, warehouse TEXT, encoded_by TEXT, remarks TEXT);"))
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS transactions(id INTEGER PRIMARY KEY, transaction_date DATE, transaction_type TEXT, source_ref_no TEXT, product_code TEXT, lot_number TEXT, quantity_in REAL, quantity_out REAL, unit TEXT, warehouse TEXT, encoded_by TEXT, remarks TEXT);"))
            conn.execute(text("INSERT OR IGNORE INTO legacy_production (prod_code) VALUES ('FG-A01'), ('FG-B02');"))
            conn.execute(text("INSERT OR IGNORE INTO warehouses (name) VALUES ('WH1'), ('WH2');"))
            conn.execute(text("INSERT OR IGNORE INTO qcf_endorsers (name) VALUES ('QC1'), ('QC2');"))
            conn.execute(text("INSERT OR IGNORE INTO qcf_receivers (name) VALUES ('REC1'), ('REC2');"))
            conn.execute(text("INSERT OR IGNORE INTO qce_bag_numbers (name) VALUES ('1'), ('2');"))
            conn.execute(text(
                "INSERT INTO qcf_endorsements_primary (system_ref_no, form_ref_no, endorsement_date, product_code, lot_number, quantity_kg, weight_per_lot, remarks, endorsed_by, warehouse, received_by_name, received_date_time, bag_no) VALUES ('QCF-2406-0001', 'FORM-001', '2024-06-15', 'FG-A01', 'LOTA001', 50.0, 25.0, 'SAMPLE REMARK', 'QC1', 'WH1', 'REC1', '2024-06-15', '1')"))
            conn.execute(text(
                "INSERT INTO qcf_endorsements_secondary (system_ref_no, lot_number, quantity_kg) VALUES ('QCF-2406-0001', 'LOTA001A', 25.0);"))
            conn.execute(text(
                "INSERT INTO qcf_endorsements_secondary (system_ref_no, lot_number, quantity_kg) VALUES ('QCF-2406-0001', 'LOTA001B', 25.0);"))
            conn.execute(text(
                """INSERT INTO transactions (transaction_date, transaction_type, product_code, lot_number, quantity_in, quantity_out) VALUES ('2024-06-01', 'INITIAL', 'FG-A01', 'LOTA001', 500, 0), ('2024-06-02', 'INITIAL', 'FG-A01', 'LOTA002', 250, 0), ('2024-06-03', 'SALES', 'FG-A01', 'LOTA001', 0, 100);"""))
    except Exception as e:
        print(f"Error creating mock database schema: {e}");
        sys.exit(1)

    mock_username = "TEST_USER"


    def mock_log_audit_trail(action, details):
        print(f"[AUDIT LOG] Action: {action}, Details: {details}")


    main_window = QMainWindow()
    main_window.setWindowTitle("QC Failed Endorsement - Standalone Test")
    main_window.setGeometry(100, 100, 1200, 850)
    endorsement_page = QCFailedEndorsementPage(db_engine=mock_engine, username=mock_username,
                                               log_audit_trail_func=mock_log_audit_trail)
    main_window.setCentralWidget(endorsement_page)
    main_window.show()
    sys.exit(app.exec())