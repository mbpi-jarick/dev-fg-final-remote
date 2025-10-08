# qc_excess_endorsement.py
# UPDATE - Added real-time inventory validation for the source Lot Number/Range.

import sys
import re
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
import traceback

# --- PyQt6 Imports ---
from PyQt6.QtCore import Qt, QDate, QDateTime
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTabWidget, QFormLayout, QLineEdit, QDateEdit,
                             QPushButton, QTableWidget, QTableWidgetItem, QComboBox,
                             QAbstractItemView, QHeaderView, QMessageBox, QHBoxLayout, QLabel,
                             QGroupBox, QMenu, QDateTimeEdit, QSplitter, QGridLayout, QCheckBox,
                             QDialog, QDialogButtonBox, QInputDialog)
from PyQt6.QtGui import QDoubleValidator

# --- SQLAlchemy Imports ---
from sqlalchemy import text, create_engine, inspect


class UpperCaseLineEdit(QLineEdit):
    # ... (This class is unchanged) ...
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.textChanged.connect(self._to_upper)

    def _to_upper(self, text: str):
        self.blockSignals(True)
        self.setText(text.upper())
        self.blockSignals(False)


def set_combo_box_uppercase(combo_box: QComboBox):
    # ... (This function is unchanged) ...
    if combo_box.isEditable():
        line_edit = combo_box.lineEdit()
        if line_edit:
            line_edit.textChanged.connect(
                lambda text, le=line_edit: (le.blockSignals(True), le.setText(text.upper()), le.blockSignals(False))
            )


class FloatLineEdit(QLineEdit):
    # ... (This class is unchanged) ...
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


class AddNewDialog(QDialog):
    # ... (This class is unchanged) ...
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
        self._load_all_records()

    def init_ui(self):
        # ... (This method is largely unchanged, just adding the validation UI) ...
        main_layout = QVBoxLayout(self)
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        self.view_tab = QWidget()
        self.view_details_tab = QWidget()
        self.entry_tab = QWidget()
        self.deleted_tab = QWidget()

        self.tab_widget.addTab(self.view_tab, "All QC Excess Endorsements")
        self.tab_widget.addTab(self.view_details_tab, "View Endorsement Details")
        self.tab_widget.addTab(self.entry_tab, "Endorsement Entry Form")
        self.tab_widget.addTab(self.deleted_tab, "Deleted Records")

        self._setup_view_tab(self.view_tab)
        self._setup_view_details_tab(self.view_details_tab)
        self._setup_entry_tab(self.entry_tab)
        self._setup_deleted_tab(self.deleted_tab)

        self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.view_details_tab), False)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

    def _setup_view_tab(self, tab):
        # ... (This method is unchanged) ...
        layout = QVBoxLayout(tab)
        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("Search:"))
        self.search_edit = UpperCaseLineEdit(placeholderText="Filter by Ref No, Product Code, Lot No...")
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
        self.update_btn.clicked.connect(self._load_record_for_update)
        self.delete_btn.clicked.connect(self._delete_record)
        self.records_table.customContextMenuRequested.connect(self._show_records_table_context_menu)
        self.records_table.itemSelectionChanged.connect(self._on_record_selection_changed)
        self.prev_btn.clicked.connect(self._go_to_prev_page)
        self.next_btn.clicked.connect(self._go_to_next_page)
        self._on_record_selection_changed()

    def _setup_deleted_tab(self, tab):
        # ... (This method is unchanged) ...
        layout = QVBoxLayout(tab)
        top_layout = QHBoxLayout()
        self.restore_btn = QPushButton("Restore Selected Record")
        self.restore_btn.setObjectName("update_btn")
        self.restore_btn.setEnabled(False)
        top_layout.addWidget(self.restore_btn)
        top_layout.addStretch()
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
        layout.addWidget(self.deleted_records_table)

        self.restore_btn.clicked.connect(self._restore_record)
        self.deleted_records_table.itemSelectionChanged.connect(
            lambda: self.restore_btn.setEnabled(bool(self.deleted_records_table.selectedItems())))
        self.deleted_records_table.customContextMenuRequested.connect(self._show_deleted_table_context_menu)

    def _on_record_selection_changed(self):
        # ... (This method is unchanged) ...
        is_selected = bool(self.records_table.selectionModel().selectedRows())
        self.update_btn.setEnabled(is_selected)
        self.delete_btn.setEnabled(is_selected)
        self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.view_details_tab), is_selected)
        if is_selected: self._show_selected_record_in_view_tab()
        if not is_selected and self.tab_widget.currentIndex() == self.tab_widget.indexOf(self.view_details_tab):
            self.tab_widget.setCurrentIndex(self.tab_widget.indexOf(self.view_tab))

    def _setup_view_details_tab(self, tab):
        # ... (This method is unchanged) ...
        main_layout = QVBoxLayout(tab)
        details_group = QGroupBox("Endorsement Details (Read-Only)")
        details_container_layout = QHBoxLayout(details_group)
        self.view_left_details_layout = QFormLayout();
        self.view_right_details_layout = QFormLayout()
        details_container_layout.addLayout(self.view_left_details_layout);
        details_container_layout.addLayout(self.view_right_details_layout)
        main_layout.addWidget(details_group)

        tables_splitter = QSplitter(Qt.Orientation.Vertical)
        breakdown_group = QGroupBox("Lot Breakdown");
        breakdown_layout = QVBoxLayout(breakdown_group)
        self.view_breakdown_table = QTableWidget()
        self.view_breakdown_table.setFocusPolicy(Qt.FocusPolicy.NoFocus);
        self.view_breakdown_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.view_breakdown_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);
        self.view_breakdown_table.verticalHeader().setVisible(False)
        self.view_breakdown_table.horizontalHeader().setHighlightSections(False);
        self.view_breakdown_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.view_breakdown_table.setStyleSheet("QTableWidget { border: none; }")
        self.view_breakdown_table.setShowGrid(False)
        breakdown_layout.addWidget(self.view_breakdown_table)
        self.view_breakdown_total_label = QLabel("<b>Total: 0.00 kg</b>");
        self.view_breakdown_total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        breakdown_layout.addWidget(self.view_breakdown_total_label)
        tables_splitter.addWidget(breakdown_group)

        excess_group = QGroupBox("Excess Quantity");
        excess_layout = QVBoxLayout(excess_group)
        self.view_excess_table = QTableWidget()
        self.view_excess_table.setFocusPolicy(Qt.FocusPolicy.NoFocus);
        self.view_excess_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.view_excess_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);
        self.view_excess_table.verticalHeader().setVisible(False)
        self.view_excess_table.horizontalHeader().setHighlightSections(False);
        self.view_excess_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.view_excess_table.setStyleSheet("QTableWidget { border: none; }")
        self.view_excess_table.setShowGrid(False)
        excess_layout.addWidget(self.view_excess_table)
        self.view_excess_total_label = QLabel("<b>Total: 0.00 kg</b>");
        self.view_excess_total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        excess_layout.addWidget(self.view_excess_total_label)
        tables_splitter.addWidget(excess_group)
        main_layout.addWidget(tables_splitter, 1)

    def _show_selected_record_in_view_tab(self):
        # ... (This method is unchanged) ...
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
            self.view_breakdown_total_label.setText(
                f"<b>Total: {sum(Decimal(d.get('quantity_kg', 0)) for d in breakdown):.2f} kg</b>")
            self._populate_view_table(self.view_excess_table, excess,
                                      ["Associated Lot", "Excess Qty (kg)", "Bag No", "Box No", "Remarks"])
            self.view_excess_total_label.setText(
                f"<b>Total: {sum(Decimal(d.get('quantity_kg', 0)) for d in excess):.2f} kg</b>")
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load details for {sys_ref_no}: {e}")

    # ... (Other helper methods _add_view_detail_row, _populate_view_table, etc. are unchanged) ...
    def _add_view_detail_row(self, layout, key, value):
        display_text = str(value) if value is not None else "N/A"
        if isinstance(value, (datetime, QDateTime)):
            display_text = QDateTime(value).toString('yyyy-MM-dd hh:mm AP')
        elif isinstance(value, date):
            display_text = value.strftime('%Y-%m-%d')
        elif isinstance(value, (Decimal, float)):
            display_text = f"{float(value):.2f}"
        layout.addRow(QLabel(f"<b>{key.replace('_', ' ').title()}:</b>"), QLabel(display_text))

    def _populate_view_table(self, table, data, headers):
        table.setRowCount(0);
        table.setColumnCount(len(headers));
        table.setHorizontalHeaderLabels(headers)
        if not data:
            header = table.horizontalHeader()
            if header.count() > 0:
                header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            return

        table.setRowCount(len(data));
        keys_in_order = list(data[0].keys())

        for i, row_data in enumerate(data):
            for j, key in enumerate(keys_in_order):
                val = row_data.get(key)
                item_text = f"{float(val):.2f}" if isinstance(val, (Decimal, float)) else str(val or "")
                item = QTableWidgetItem(item_text)
                if isinstance(val, (Decimal, float)): item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(i, j, item)
        table.resizeColumnsToContents()
        table.horizontalHeader().setSectionResizeMode(len(headers) - 1, QHeaderView.ResizeMode.Stretch)

    def _show_records_table_context_menu(self, position):
        if not self.records_table.selectedItems(): return
        menu = QMenu();
        view_action = menu.addAction("View Details");
        edit_action = menu.addAction("Edit Record");
        delete_action = menu.addAction("Delete Record")
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
        restore_action = menu.addAction("Restore Record")
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
        details_group = QGroupBox("QC Excess Endorsement");
        grid_layout = QGridLayout(details_group)

        self.ref_no_edit = QLineEdit(readOnly=True, placeholderText="Auto-generated")
        self.form_ref_no_edit = UpperCaseLineEdit()
        self.date_endorsed_edit = QDateEdit(calendarPopup=True, displayFormat="yyyy-MM-dd")
        self.product_code_combo = QComboBox(editable=True);
        set_combo_box_uppercase(self.product_code_combo)
        self.lot_number_edit = UpperCaseLineEdit(placeholderText="E.G., 12345 OR 12345-12350")

        # --- NEW INVENTORY VALIDATION WIDGETS ---
        self.check_inventory_btn = QPushButton("Check Stock")
        self.inventory_status_label = QLabel("Status: Awaiting check...")
        self.inventory_status_label.setStyleSheet("font-style: italic; color: #555;")

        lot_layout = QHBoxLayout()
        lot_layout.setContentsMargins(0, 0, 0, 0)
        lot_layout.addWidget(self.lot_number_edit, 1)
        lot_layout.addWidget(self.check_inventory_btn)
        # --- END NEW WIDGETS ---

        self.is_lot_range_check = QCheckBox("Calculate lots from a range")
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
        grid_layout.addWidget(QLabel("Status:"), 0, 2);
        grid_layout.addWidget(self.status_combo, 0, 3)
        grid_layout.addWidget(QLabel("<b>Form Ref No:</b>"), 1, 0);
        grid_layout.addWidget(self.form_ref_no_edit, 1, 1)
        grid_layout.addWidget(QLabel("Date Endorsed:"), 1, 2);
        grid_layout.addWidget(self.date_endorsed_edit, 1, 3)
        grid_layout.addWidget(QLabel("<b>Product Code:</b>"), 2, 0);
        grid_layout.addWidget(self.product_code_combo, 2, 1, 1, 3)
        grid_layout.addWidget(QLabel("<b>Lot Number/Range:</b>"), 3, 0);
        grid_layout.addLayout(lot_layout, 3, 1, 1, 2)  # Use the new layout
        grid_layout.addWidget(self.is_lot_range_check, 4, 0)
        grid_layout.addWidget(self.inventory_status_label, 4, 1, 1, 3)  # Add the status label
        grid_layout.addWidget(QLabel("Total Qty (kg):"), 5, 0);
        grid_layout.addWidget(self.quantity_edit, 5, 1)
        grid_layout.addWidget(QLabel("Weight/Lot (kg):"), 5, 2);
        grid_layout.addWidget(self.weight_per_lot_edit, 5, 3)
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
        breakdown_group = QGroupBox("Lot Breakdown (Preview)")
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

        excess_group = QGroupBox("Excess Quantity (Preview)")
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

        self.preview_btn = QPushButton("Preview Breakdown");
        self.save_btn = QPushButton("Save Endorsement");
        self.clear_btn = QPushButton("New");
        self.cancel_update_btn = QPushButton("Cancel Update")
        self.save_btn.setObjectName("PrimaryButton");
        self.clear_btn.setObjectName("SecondaryButton");
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

        # --- NEW CONNECTIONS FOR INVENTORY VALIDATION ---
        self.check_inventory_btn.clicked.connect(self._check_lot_in_inventory)
        self.lot_number_edit.editingFinished.connect(self._check_lot_in_inventory)
        self.lot_number_edit.textChanged.connect(self._reset_validation)

        self._clear_form()

    # --- NEW INVENTORY VALIDATION METHODS ---
    def _reset_validation(self):
        self.preview_btn.setEnabled(False)
        self.inventory_status_label.setText("Status: Awaiting check...")
        self.inventory_status_label.setStyleSheet("font-style: italic; color: #555;")

    def _get_lot_beginning_qty(self, conn, lot_number):
        # This function is identical to the one in rrf.py
        inspector = inspect(self.engine)
        schema = inspector.default_schema_name
        all_tables = [tbl for tbl in inspector.get_table_names(schema=schema) if tbl.startswith('beginv_')]
        total_qty = Decimal('0.0')
        for tbl in all_tables:
            columns = [col['name'] for col in inspector.get_columns(tbl, schema=schema)]
            lot_col = next((c for c in columns if 'lot' in c.lower()), None)
            qty_col = next((c for c in columns if 'qty' in c.lower() or 'quantity' in c.lower()), None)
            if lot_col and qty_col:
                query = text(f'SELECT SUM("{qty_col}") FROM "{tbl}" WHERE "{lot_col}" = :lot')
                result = conn.execute(query, {"lot": lot_number}).scalar_one_or_none()
                if result:
                    total_qty += Decimal(result)
        return total_qty

    def _get_lot_additions_qty(self, conn, lot_number):
        # This function is identical to the one in rrf.py
        query = text("""
            SELECT COALESCE(SUM(quantity_kg), 0) FROM (
                SELECT quantity_kg FROM fg_endorsements_secondary WHERE lot_number = :lot
                UNION ALL
                SELECT quantity_kg FROM fg_endorsements_excess WHERE lot_number = :lot
                UNION ALL
                SELECT i.quantity FROM rrf_items i JOIN rrf_primary p ON i.rrf_no = p.rrf_no
                WHERE i.lot_number = :lot AND p.material_type != 'RAW MATERIAL' AND p.is_deleted IS NOT TRUE
            ) as additions
        """)
        return conn.execute(query, {"lot": lot_number}).scalar_one()

    def _get_lot_removals_qty(self, conn, lot_number):
        # This function is identical to the one in rrf.py
        query = text("""
            SELECT COALESCE(SUM(quantity_kg), 0) FROM (
                SELECT b.quantity_kg FROM product_delivery_lot_breakdown b
                JOIN product_delivery_primary p ON b.dr_no = p.dr_no WHERE b.lot_number = :lot AND p.is_deleted IS NOT TRUE
                UNION ALL
                SELECT i.quantity_required_kg FROM outgoing_records_items i
                JOIN outgoing_records_primary p ON i.primary_id = p.id WHERE i.lot_used = :lot AND p.is_deleted IS NOT TRUE
                UNION ALL
                SELECT i.quantity FROM rrf_items i JOIN rrf_primary p ON i.rrf_no = p.rrf_no
                WHERE i.lot_number = :lot AND p.material_type = 'RAW MATERIAL' AND p.is_deleted IS NOT TRUE
            ) as removals
        """)
        return conn.execute(query, {"lot": lot_number}).scalar_one()

    def _check_lot_in_inventory(self):
        lot_number = self.lot_number_edit.text().strip()
        if not lot_number:
            self._reset_validation()
            return

        # This endorsement is a removal, so we must check for positive stock
        try:
            with self.engine.connect() as conn:
                beginning = self._get_lot_beginning_qty(conn, lot_number)
                additions = self._get_lot_additions_qty(conn, lot_number)
                removals = self._get_lot_removals_qty(conn, lot_number)

            current_stock = Decimal(beginning) + Decimal(additions) - Decimal(removals)

            if current_stock > 0:
                self.inventory_status_label.setText(f"Status: Found in stock. Available Qty: {current_stock:.2f} kg")
                self.inventory_status_label.setStyleSheet("font-weight: bold; color: #2ecc71;")  # Green
                self.preview_btn.setEnabled(True)
                self.quantity_edit.setText(f"{current_stock:.2f}")  # Auto-fill total quantity
            else:
                self.inventory_status_label.setText(
                    f"Status: NOT FOUND or stock is zero. (Current: {current_stock:.2f} kg)")
                self.inventory_status_label.setStyleSheet("font-weight: bold; color: #e74c3c;")  # Red
                self.preview_btn.setEnabled(False)

        except Exception as e:
            self.inventory_status_label.setText("Status: Error during inventory check.")
            self.inventory_status_label.setStyleSheet("font-weight: bold; color: #e74c3c;")
            self.preview_btn.setEnabled(False)
            QMessageBox.critical(self, "DB Error", f"An error occurred while checking inventory: {e}")
            print(traceback.format_exc())

    def _create_combo_with_add(self, table_name, combo):
        layout = QHBoxLayout();
        layout.setContentsMargins(0, 0, 0, 0);
        layout.addWidget(combo, 1)
        add_btn = QPushButton("Manage");
        add_btn.clicked.connect(lambda: self._handle_add_new_record(table_name, combo))
        layout.addWidget(add_btn);
        return layout

    def _handle_add_new_record(self, table_name, combo_to_update):
        title_map = {
            "qce_endorsers": "Endorser",
            "qce_receivers": "Receiver",
            "qce_bag_numbers": "Bag Number",
            "qce_box_numbers": "Box Number",
            "qce_remarks": "Remark"
        };
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
        queries = {
            self.endorsed_by_combo: "SELECT name FROM qce_endorsers ORDER BY name",
            self.received_by_combo: "SELECT name FROM qce_receivers ORDER BY name",
            self.bag_number_combo: "SELECT name FROM qce_bag_numbers ORDER BY name",
            self.box_number_combo: "SELECT name FROM qce_box_numbers ORDER BY name",
            self.remarks_combo: "SELECT name FROM qce_remarks ORDER BY name",
            self.product_code_combo: "SELECT DISTINCT prod_code FROM legacy_production WHERE prod_code IS NOT NULL AND prod_code != '' ORDER BY prod_code"
        }
        try:
            with self.engine.connect() as conn:
                for combo, query in queries.items():
                    current_text = combo.currentText();
                    items = conn.execute(text(query)).scalars().all();
                    combo.clear();
                    combo.addItems([""] + items)
                    if current_text in items: combo.setCurrentText(current_text)
        except Exception as e:
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
        calculation_data = self._perform_lot_calculation(
            total_qty=record_data.get('quantity_kg', Decimal(0)),
            weight_per_lot=record_data.get('weight_per_lot', Decimal(0)),
            lot_input=record_data.get('lot_number', ''),
            is_range='-' in record_data.get('lot_number', ''),
            is_update=True
        )
        if calculation_data:
            self.preview_data = calculation_data
            self._populate_preview_widgets(self.preview_data)

    def _populate_preview_widgets(self, data):
        breakdown_data = [{'lot_number': lot, 'quantity_kg': data['weight_per_lot']} for lot in data['lots']]
        self._populate_preview_table(self.preview_breakdown_table, breakdown_data, ["Lot Number", "Quantity (kg)"])
        breakdown_total = data['weight_per_lot'] * len(data['lots'])
        self.breakdown_total_label.setText(f"<b>Total: {float(breakdown_total):.2f} kg</b>")
        if data['excess_qty'] > 0 and data['excess_lot_number']:
            excess_data = [{'lot_number': data['excess_lot_number'], 'quantity_kg': data['excess_qty']}]
            self._populate_preview_table(self.preview_excess_table, excess_data, ["Associated Lot", "Excess Qty (kg)"])
            self.excess_total_label.setText(f"<b>Total: {float(data['excess_qty']):.2f} kg</b>")

    def _validate_and_calculate_lots(self):
        required_fields = {
            "Form Ref No": self.form_ref_no_edit.text(),
            "Product Code": self.product_code_combo.currentText(),
            "Lot Number/Range": self.lot_number_edit.text(),
            "Endorsed By": self.endorsed_by_combo.currentText(),
            "Received By": self.received_by_combo.currentText()
        }
        missing_fields = [name for name, value in required_fields.items() if not value.strip()]
        if missing_fields:
            QMessageBox.warning(self, "Input Error", "Please complete all required fields before previewing:\n\n- " + "\n- ".join(missing_fields))
            return None

        try:
            total_qty = Decimal(self.quantity_edit.text() or "0");
            weight_per_lot = Decimal(self.weight_per_lot_edit.text() or "0")
            lot_input = self.lot_number_edit.text().strip()
            if weight_per_lot <= 0: QMessageBox.warning(self, "Input Error", "Weight per Lot must be > 0."); return None
        except (InvalidOperation, ValueError):
            QMessageBox.warning(self, "Input Error", "Invalid numbers for Quantity or Weight per Lot.");
            return None
        return self._perform_lot_calculation(total_qty, weight_per_lot, lot_input, self.is_lot_range_check.isChecked())

    def _perform_lot_calculation(self, total_qty, weight_per_lot, lot_input, is_range, is_update=False):
        num_full_lots = int(total_qty // weight_per_lot);
        excess_qty = total_qty % weight_per_lot
        lot_list, excess_lot_number = [], None

        if is_range:
            lot_list = self._parse_lot_range(lot_input, num_full_lots)
            if lot_list is None: return None
        else:
            lot_list = [lot_input.upper()] * num_full_lots

        if excess_qty > 0:
            if lot_list:
                last_full_lot = lot_list[-1]
                match = re.match(r'^(\d+)([A-Z]*)$', last_full_lot)
                if match:
                    num_part, suffix_part, num_len = int(match.group(1)), match.group(2), len(match.group(1))
                    new_lot_num = f"{str(num_part + 1).zfill(num_len)}{suffix_part}"
                else:
                    new_lot_num = f"{last_full_lot}-EXCESS"

                if not is_update:
                    msg_box = QMessageBox(self)
                    msg_box.setIcon(QMessageBox.Icon.Question)
                    msg_box.setWindowTitle("Excess Quantity Handling")
                    msg_box.setText(f"There is an excess of {excess_qty:.2f} kg.")
                    msg_box.setInformativeText("How should the lot number for this excess be handled?")
                    retain_btn = msg_box.addButton(f"Associate with Last Lot ({last_full_lot})", QMessageBox.ButtonRole.YesRole)
                    create_new_btn = msg_box.addButton(f"Create New Lot ({new_lot_num})", QMessageBox.ButtonRole.NoRole)
                    msg_box.addButton(QMessageBox.StandardButton.Cancel)
                    msg_box.exec()

                    clicked = msg_box.clickedButton()
                    if clicked == retain_btn:
                        excess_lot_number = last_full_lot
                    elif clicked == create_new_btn:
                        excess_lot_number = new_lot_num
                    else:
                        return None
                else:
                    excess_lot_number = new_lot_num

            elif lot_input:
                excess_lot_number = lot_input.upper()

        return {"lots": lot_list, "excess_qty": excess_qty, "weight_per_lot": weight_per_lot,
                "excess_lot_number": excess_lot_number}

    def _save_record(self):
        required_fields = {
            "Form Ref No": self.form_ref_no_edit.text(),
            "Product Code": self.product_code_combo.currentText(),
            "Lot Number/Range": self.lot_number_edit.text(),
            "Endorsed By": self.endorsed_by_combo.currentText(),
            "Received By": self.received_by_combo.currentText()
        }
        missing_fields = [name for name, value in required_fields.items() if not value.strip()]
        if missing_fields:
            QMessageBox.warning(self, "Validation Error", "Please complete all required fields:\n\n- " + "\n- ".join(missing_fields))
            return

        if not self.preview_data:
            QMessageBox.warning(self, "Preview Required", "Please 'Preview Breakdown' before saving.");
            return

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
                    update_sql = text(
                        "UPDATE qce_endorsements_primary SET form_ref_no=:form_ref_no, product_code=:product_code, lot_number=:lot_number, quantity_kg=:quantity_kg, weight_per_lot=:weight_per_lot, status=:status, bag_number=:bag_number, box_number=:box_number, remarks=:remarks, date_endorsed=:date_endorsed, endorsed_by=:endorsed_by, date_received=:date_received, received_by=:received_by, edited_by=:edited_by, edited_on=:edited_on WHERE system_ref_no = :system_ref_no")
                    conn.execute(update_sql, primary_data);
                    self.log_audit_trail("UPDATE_QC_EXCESS", f"Updated QC Excess: {sys_ref_no}");
                    action_text = "updated"
                else:
                    insert_sql = text(
                        "INSERT INTO qce_endorsements_primary (system_ref_no, form_ref_no, product_code, lot_number, quantity_kg, weight_per_lot, status, bag_number, box_number, remarks, date_endorsed, endorsed_by, date_received, received_by, encoded_by, encoded_on, edited_by, edited_on) VALUES (:system_ref_no, :form_ref_no, :product_code, :lot_number, :quantity_kg, :weight_per_lot, :status, :bag_number, :box_number, :remarks, :date_endorsed, :endorsed_by, :date_received, :received_by, :encoded_by, :encoded_on, :edited_by, :edited_on)")
                    conn.execute(insert_sql, primary_data);
                    self.log_audit_trail("CREATE_QC_EXCESS", f"Created QC Excess: {sys_ref_no}");
                    action_text = "saved"
                if self.preview_data['lots']:
                    secondary_records = [{'system_ref_no': sys_ref_no, 'lot_number': lot,
                                          'quantity_kg': self.preview_data['weight_per_lot'],
                                          'bag_number': primary_data['bag_number'],
                                          'box_number': primary_data['box_number'], 'remarks': primary_data['remarks']}
                                         for lot in self.preview_data['lots']]
                    conn.execute(text(
                        "INSERT INTO qce_endorsements_secondary (system_ref_no, lot_number, quantity_kg, bag_number, box_number, remarks) VALUES (:system_ref_no, :lot_number, :quantity_kg, :bag_number, :box_number, :remarks)"),
                        secondary_records)
                if self.preview_data['excess_qty'] > 0 and self.preview_data['excess_lot_number']:
                    excess_record = {'system_ref_no': sys_ref_no, 'lot_number': self.preview_data['excess_lot_number'],
                                     'quantity_kg': self.preview_data['excess_qty'],
                                     'bag_number': primary_data['bag_number'], 'box_number': primary_data['box_number'],
                                     'remarks': primary_data['remarks']}
                    conn.execute(text(
                        "INSERT INTO qce_endorsements_excess (system_ref_no, lot_number, quantity_kg, bag_number, box_number, remarks) VALUES (:system_ref_no, :lot_number, :quantity_kg, :bag_number, :box_number, :remarks)"),
                        [excess_record])
            QMessageBox.information(self, "Success", f"QC Excess Endorsement {sys_ref_no} {action_text} successfully.");
            self._clear_form();
            self._refresh_all_data_views();
            self.tab_widget.setCurrentIndex(0);
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"An error occurred: {e}")

    def _load_all_records(self):
        search = f"%{self.search_edit.text()}%"
        offset = (self.current_page - 1) * self.records_per_page
        try:
            with self.engine.connect() as conn:
                count_query_base = "FROM qce_endorsements_primary WHERE is_deleted IS NOT TRUE"
                filter_clause = ""
                params = {'limit': self.records_per_page, 'offset': offset}
                if self.search_edit.text():
                    filter_clause = " AND (system_ref_no ILIKE :st OR form_ref_no ILIKE :st OR product_code ILIKE :st OR lot_number ILIKE :st)"
                    params['st'] = search

                count_res = conn.execute(text(f"SELECT COUNT(id) {count_query_base} {filter_clause}"),
                                         {'st': search} if self.search_edit.text() else {}).scalar_one()
                self.total_records = count_res

                query = text(f"""
                    SELECT system_ref_no, form_ref_no, date_endorsed, product_code, lot_number, quantity_kg
                    FROM qce_endorsements_primary
                    WHERE is_deleted IS NOT TRUE {filter_clause}
                    ORDER BY id DESC LIMIT :limit OFFSET :offset
                """)
                res = conn.execute(query, params).mappings().all()

            headers = ["System Ref No", "Form Ref No", "Date", "Product Code", "Lot No / Range", "Total Qty"]
            self._populate_records_table(self.records_table, res, headers)
            self._update_pagination_controls()
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load QC Excess endorsements: {e}")

    def _load_deleted_records(self):
        try:
            with self.engine.connect() as conn:
                res = conn.execute(text("""
                    SELECT system_ref_no, form_ref_no, date_endorsed, product_code, lot_number, quantity_kg, edited_by, edited_on
                    FROM qce_endorsements_primary
                    WHERE is_deleted = TRUE
                    ORDER BY edited_on DESC
                """)).mappings().all()
            headers = ["System Ref No", "Form Ref No", "Date", "Product Code", "Lot No / Range", "Total Qty", "Deleted By", "Deleted On"]
            self._populate_records_table(self.deleted_records_table, res, headers)
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load deleted records: {e}")


    def _on_search_text_changed(self):
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
            self.ref_no_edit.setText(record.get('system_ref_no', ''))
            self.form_ref_no_edit.setText(record.get('form_ref_no', ''))
            if db_date := record.get('date_endorsed'): self.date_endorsed_edit.setDate(QDate(db_date))
            self.product_code_combo.setCurrentText(record.get('product_code', ''))
            self.lot_number_edit.setText(record.get('lot_number', ''))
            self.quantity_edit.setText(f"{record.get('quantity_kg', 0.0):.2f}")
            self.weight_per_lot_edit.setText(f"{record.get('weight_per_lot', 0.0):.2f}")
            self.status_combo.setCurrentText(record.get('status', ''))
            self.bag_number_combo.setCurrentText(record.get('bag_number', ''))
            self.box_number_combo.setCurrentText(record.get('box_number', ''))
            self.remarks_combo.setCurrentText(record.get('remarks', ''))
            self.endorsed_by_combo.setCurrentText(record.get('endorsed_by', ''))
            if db_datetime := record.get('date_received'): self.received_date_time_edit.setDateTime(
                QDateTime(db_datetime))
            self.received_by_combo.setCurrentText(record.get('received_by', ''))
            self.is_lot_range_check.setChecked('-' in (record.get('lot_number') or ''))
            self.save_btn.setText("Update Endorsement");
            self.cancel_update_btn.show()
            self._generate_preview_from_data(record)
            self.tab_widget.setCurrentIndex(self.tab_widget.indexOf(self.entry_tab))
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load record {ref_no} for editing: {e}")

    def _delete_record(self):
        selected_rows = self.records_table.selectionModel().selectedRows()
        if not selected_rows: return
        ref_no = self.records_table.item(selected_rows[0].row(), 0).text()

        password, ok = QInputDialog.getText(self, "Password Required", "Enter password to delete:", QLineEdit.EchoMode.Password)
        if not ok:
            return
        if password != "Itadmin":
            QMessageBox.warning(self, "Incorrect Password", "The password you entered is incorrect. Deletion cancelled.")
            return

        if QMessageBox.question(self, "Confirm Delete",
                                f"Are you sure you want to delete endorsement <b>{ref_no}</b>?") == QMessageBox.StandardButton.Yes:
            try:
                with self.engine.connect() as conn, conn.begin():
                    conn.execute(text(
                        "UPDATE qce_endorsements_primary SET is_deleted = TRUE, edited_by = :user, edited_on = :now WHERE system_ref_no = :ref"),
                        {"ref": ref_no, "user": self.username, "now": datetime.now()})
                self.log_audit_trail("DELETE_QC_EXCESS", f"Soft-deleted QC Excess: {ref_no}")
                QMessageBox.information(self, "Success", f"Endorsement {ref_no} has been deleted.")
                self._refresh_all_data_views()
            except Exception as e:
                QMessageBox.critical(self, "Database Error", f"Could not delete record: {e}")

    def _restore_record(self):
        selected_rows = self.deleted_records_table.selectionModel().selectedRows()
        if not selected_rows: return
        ref_no = self.deleted_records_table.item(selected_rows[0].row(), 0).text()
        if QMessageBox.question(self, "Confirm Restore",
                                f"Are you sure you want to restore endorsement <b>{ref_no}</b>?") == QMessageBox.StandardButton.Yes:
            try:
                with self.engine.connect() as conn, conn.begin():
                    conn.execute(text(
                        "UPDATE qce_endorsements_primary SET is_deleted = FALSE, edited_by = :user, edited_on = :now WHERE system_ref_no = :ref"),
                        {"ref": ref_no, "user": self.username, "now": datetime.now()})
                self.log_audit_trail("RESTORE_QC_EXCESS", f"Restored QC Excess: {ref_no}")
                QMessageBox.information(self, "Success", f"Endorsement {ref_no} has been restored.")
                self._refresh_all_data_views()
            except Exception as e:
                QMessageBox.critical(self, "Database Error", f"Could not restore record: {e}")


    def _generate_ref_no(self):
        prefix = f"QCE-{datetime.now().strftime('%y%m')}-"
        with self.engine.connect() as conn:
            last_ref = conn.execute(text(
                "SELECT system_ref_no FROM qce_endorsements_primary WHERE system_ref_no LIKE :p ORDER BY id DESC LIMIT 1"),
                {"p": f"{prefix}%"}).scalar_one_or_none()
            next_seq = int(last_ref.split('-')[-1]) + 1 if last_ref else 1
            return f"{prefix}{next_seq:04d}"

    def _parse_lot_range(self, lot_input, num_lots):
        try:
            parts = [s.strip().upper() for s in lot_input.split('-')];
            if len(parts) != 2: raise ValueError("Lot range must contain exactly one hyphen.")
            start_str, end_str = parts;
            start_match = re.match(r'^(\d+)([A-Z]*)$', start_str);
            end_match = re.match(r'^(\d+)([A-Z]*)$', end_str)
            if not start_match or not end_match or start_match.group(2) != end_match.group(2): raise ValueError(
                "Format invalid or suffixes mismatch. Expected: '100A-105A'.")
            start_num, end_num, suffix, num_len = int(start_match.group(1)), int(end_match.group(1)), start_match.group(
                2), len(start_match.group(1))
            if start_num > end_num: raise ValueError("Start lot cannot be greater than end lot.")
            actual_lots_in_range = end_num - start_num + 1
            if actual_lots_in_range != num_lots:
                msg_box = QMessageBox(self);
                msg_box.setIcon(QMessageBox.Icon.Question);
                msg_box.setWindowTitle("Lot Mismatch")
                msg_box.setText("The lot range count and quantity calculation do not match.")
                msg_box.setInformativeText(
                    f"<b>Lot Range:</b> {actual_lots_in_range} lots<br><b>Quantity Calc:</b> {num_lots} lots<br><br>How to proceed?")
                use_range_btn = msg_box.addButton(f"Use Range ({actual_lots_in_range} Lots)",
                                                  QMessageBox.ButtonRole.YesRole)
                use_calc_btn = msg_box.addButton(f"Use Calc ({num_lots} Lots)", QMessageBox.ButtonRole.NoRole)
                cancel_btn = msg_box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole);
                msg_box.exec()
                if msg_box.clickedButton() == use_range_btn:
                    return [f"{str(start_num + i).zfill(num_len)}{suffix}" for i in range(actual_lots_in_range)]
                elif msg_box.clickedButton() == use_calc_btn:
                    return [f"{str(start_num + i).zfill(num_len)}{suffix}" for i in range(num_lots)]
                else:
                    return None
            return [f"{str(start_num + i).zfill(num_len)}{suffix}" for i in range(actual_lots_in_range)]
        except Exception as e:
            QMessageBox.critical(self, "Lot Range Error", f"Could not parse lot range '{lot_input}': {e}");
            return None

    def _populate_records_table(self, table, data, headers):
        table.setRowCount(0);
        table.setColumnCount(len(headers));
        table.setHorizontalHeaderLabels(headers)
        header = table.horizontalHeader()

        if not data:
            if header.count() > 0:
                header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
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
                    item_text = f"{float(value):.2f}"
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
            if table_widget.horizontalHeader().count() > 0:
                table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            return
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
        table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)