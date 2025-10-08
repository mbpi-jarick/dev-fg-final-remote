import sys
import re
import traceback
from datetime import datetime
from decimal import Decimal, InvalidOperation

# --- PyQt6 Imports ---
from PyQt6.QtCore import Qt, QDate, QDateTime
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QTabWidget, QFormLayout, QLineEdit, QDateEdit,
                             QPushButton, QTableWidget, QTableWidgetItem, QComboBox,
                             QAbstractItemView, QHeaderView, QMessageBox, QHBoxLayout, QLabel,
                             QGroupBox, QMenu, QDateTimeEdit, QSplitter, QGridLayout, QCheckBox,
                             QDialog, QDialogButtonBox, QInputDialog)
from PyQt6.QtGui import QDoubleValidator

# --- SQLAlchemy Imports ---
from sqlalchemy import text, create_engine

# --- Configuration for the secondary QC database ---
DB_CONFIG = {"host": "192.168.1.13", "port": 5432, "dbname": "dbmbpi", "user": "postgres", "password": "mbpi"}


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
            value = float(self.text() or 0.0)
            self.setText(f"{value:.2f}")
        except ValueError:
            self.setText("0.00")

    def value(self) -> float:
        return float(self.text() or 0.0)


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


class QCFailedPassedPage(QWidget):
    def __init__(self, db_engine, username, log_audit_trail_func):
        super().__init__()
        self.engine, self.username, self.log_audit_trail = db_engine, username, log_audit_trail_func
        self.qc_engine = None

        try:
            qc_db_url = (f"postgresql://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
                         f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}")
            self.qc_engine = create_engine(qc_db_url, pool_pre_ping=True, pool_recycle=3600)
            with self.qc_engine.connect() as conn:
                pass
            print(f"Successfully connected to secondary QC database '{DB_CONFIG['dbname']}' on '{DB_CONFIG['host']}'.")
        except Exception as e:
            trace_info = traceback.format_exc()
            print(
                f"CRITICAL: Could not connect to engine for '{DB_CONFIG['dbname']}'. QC Lookup will be disabled. Error: {e}\n{trace_info}")
            self.qc_engine = None

        self.current_editing_ref_no = None
        self.preview_data = None
        self.current_page, self.records_per_page = 1, 200
        self.total_records, self.total_pages = 0, 1
        self.init_ui()
        self._load_all_records()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        self.view_tab = QWidget()
        self.view_details_tab = QWidget()
        self.entry_tab = QWidget()
        self.deleted_tab = QWidget()

        self.tab_widget.addTab(self.view_tab, "All QC Endorsements")
        self.tab_widget.addTab(self.view_details_tab, "View Endorsement Details")
        self.tab_widget.addTab(self.entry_tab, "Endorsement Entry Form")
        self.tab_widget.addTab(self.deleted_tab, "Deleted")

        self._setup_view_tab(self.view_tab)
        self._setup_view_details_tab(self.view_details_tab)
        self._setup_entry_tab(self.entry_tab)
        self._setup_deleted_tab(self.deleted_tab)

        self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.view_details_tab), False)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

    def _configure_table_ui(self, table: QTableWidget):
        table.setShowGrid(False)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setHighlightSections(False)
        header = table.horizontalHeader()
        for i in range(header.count()):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)

    def _setup_view_tab(self, tab):
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
        self._configure_table_ui(self.records_table)
        self.records_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
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
        layout = QVBoxLayout(tab)
        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("Search Deleted:"))
        self.deleted_search_edit = UpperCaseLineEdit(placeholderText="Filter by Ref No, Product Code...")
        top_layout.addWidget(self.deleted_search_edit, 1)
        layout.addLayout(top_layout)
        self.deleted_records_table = QTableWidget()
        self._configure_table_ui(self.deleted_records_table)
        self.deleted_records_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.deleted_records_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        layout.addWidget(self.deleted_records_table)
        self.deleted_search_edit.textChanged.connect(self._load_deleted_records)
        self.deleted_records_table.customContextMenuRequested.connect(self._show_deleted_records_context_menu)

    def _on_record_selection_changed(self):
        is_selected = bool(self.records_table.selectionModel().selectedRows())
        self.update_btn.setEnabled(is_selected)
        self.delete_btn.setEnabled(is_selected)
        self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.view_details_tab), is_selected)
        if is_selected:
            self._show_selected_record_in_view_tab()
        if not is_selected and self.tab_widget.currentIndex() == self.tab_widget.indexOf(self.view_details_tab):
            self.tab_widget.setCurrentIndex(self.tab_widget.indexOf(self.view_tab))

    def _setup_view_details_tab(self, tab):
        main_layout = QVBoxLayout(tab)
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
        self._configure_table_ui(self.view_breakdown_table)
        breakdown_layout.addWidget(self.view_breakdown_table)
        self.view_breakdown_total_label = QLabel("<b>Total: 0.00 kg</b>")
        self.view_breakdown_total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        breakdown_layout.addWidget(self.view_breakdown_total_label)
        tables_splitter.addWidget(breakdown_group)
        excess_group = QGroupBox("Excess Quantity")
        excess_layout = QVBoxLayout(excess_group)
        self.view_excess_table = QTableWidget()
        self._configure_table_ui(self.view_excess_table)
        excess_layout.addWidget(self.view_excess_table)
        self.view_excess_total_label = QLabel("<b>Total: 0.00 kg</b>")
        self.view_excess_total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        excess_layout.addWidget(self.view_excess_total_label)
        tables_splitter.addWidget(excess_group)
        main_layout.addWidget(tables_splitter, 1)

    def _setup_entry_tab(self, tab):
        main_splitter = QSplitter(Qt.Orientation.Horizontal);
        tab_layout = QHBoxLayout(tab);
        tab_layout.addWidget(main_splitter)
        left_widget = QWidget();
        left_layout = QVBoxLayout(left_widget);
        left_layout.setContentsMargins(0, 0, 5, 0);
        main_splitter.addWidget(left_widget)
        details_group = QGroupBox("Endorsement Details");
        grid_layout = QGridLayout(details_group)
        self.system_ref_no_edit = QLineEdit(readOnly=True, placeholderText="Auto-generated")
        self.form_ref_no_edit = UpperCaseLineEdit()
        self.endorsement_date_edit = QDateEdit(calendarPopup=True, displayFormat="yyyy-MM-dd")
        self.product_code_combo = QComboBox(editable=True);
        set_combo_box_uppercase(self.product_code_combo)
        self.lot_number_edit = UpperCaseLineEdit(placeholderText="E.G., 12345 OR 12345-12350")
        self.is_lot_range_check = QCheckBox("Calculate lots from a range")
        self.quantity_edit = FloatLineEdit();
        self.weight_per_lot_edit = FloatLineEdit()
        self.endorsed_by_combo = QComboBox();
        self.warehouse_combo = QComboBox()
        self.received_by_combo = QComboBox(editable=True);
        set_combo_box_uppercase(self.received_by_combo)
        self.received_date_time_edit = QDateTimeEdit(calendarPopup=True, displayFormat="yyyy-MM-dd hh:mm AP")
        self.qc_id_lookup_combo = QComboBox(self);
        self.qc_id_lookup_combo.setEditable(True)
        self.qc_id_lookup_combo.setPlaceholderText("Select a QC ID to load data")
        if not self.qc_engine:
            self.qc_id_lookup_combo.setEnabled(False);
            self.qc_id_lookup_combo.setToolTip("QC Database connection failed.")
        grid_layout.addWidget(QLabel("Lookup QC ID:"), 0, 0);
        grid_layout.addWidget(self.qc_id_lookup_combo, 0, 1, 1, 3)
        grid_layout.addWidget(QLabel("System Ref No:"), 1, 0);
        grid_layout.addWidget(self.system_ref_no_edit, 1, 1)
        grid_layout.addWidget(QLabel("Form Ref No:"), 1, 2);
        grid_layout.addWidget(self.form_ref_no_edit, 1, 3)
        grid_layout.addWidget(QLabel("Date Endorsed:"), 2, 0);
        grid_layout.addWidget(self.endorsement_date_edit, 2, 1)
        grid_layout.addWidget(QLabel("Product Code:"), 2, 2);
        grid_layout.addWidget(self.product_code_combo, 2, 3)
        grid_layout.addWidget(QLabel("Lot Number/Range:"), 3, 0);
        grid_layout.addWidget(self.lot_number_edit, 3, 1, 1, 3)
        grid_layout.addWidget(self.is_lot_range_check, 4, 1, 1, 3)
        grid_layout.addWidget(QLabel("Total Qty (kg):"), 5, 0);
        grid_layout.addWidget(self.quantity_edit, 5, 1)
        grid_layout.addWidget(QLabel("Weight/Lot (kg):"), 5, 2);
        grid_layout.addWidget(self.weight_per_lot_edit, 5, 3)
        grid_layout.addWidget(QLabel("Endorsed By:"), 6, 0);
        grid_layout.addLayout(self._create_combo_with_add("qcfp_endorsers", self.endorsed_by_combo), 6, 1)
        grid_layout.addWidget(QLabel("Warehouse:"), 6, 2);
        grid_layout.addLayout(self._create_combo_with_add("warehouses", self.warehouse_combo), 6, 3)
        grid_layout.addWidget(QLabel("Received By:"), 7, 0);
        grid_layout.addLayout(self._create_combo_with_add("qcfp_receivers", self.received_by_combo), 7, 1)
        grid_layout.addWidget(QLabel("Received Date/Time:"), 7, 2);
        grid_layout.addWidget(self.received_date_time_edit, 7, 3)
        grid_layout.setColumnStretch(1, 1);
        grid_layout.setColumnStretch(3, 1)
        left_layout.addWidget(details_group);
        left_layout.addStretch()
        right_widget = QWidget();
        right_layout = QVBoxLayout(right_widget);
        right_layout.setContentsMargins(5, 0, 0, 0);
        main_splitter.addWidget(right_widget)
        preview_splitter = QSplitter(Qt.Orientation.Vertical)
        breakdown_group = QGroupBox("Lot Breakdown (Preview)");
        b_layout = QVBoxLayout(breakdown_group)
        self.preview_breakdown_table = QTableWidget();
        self._configure_table_ui(self.preview_breakdown_table)
        b_layout.addWidget(self.preview_breakdown_table)
        self.breakdown_total_label = QLabel("<b>Total: 0.00 kg</b>");
        self.breakdown_total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        b_layout.addWidget(self.breakdown_total_label);
        preview_splitter.addWidget(breakdown_group)
        excess_group = QGroupBox("Excess Quantity (Preview)");
        e_layout = QVBoxLayout(excess_group)
        self.preview_excess_table = QTableWidget();
        self._configure_table_ui(self.preview_excess_table)
        e_layout.addWidget(self.preview_excess_table)
        self.excess_total_label = QLabel("<b>Total: 0.00 kg</b>");
        self.excess_total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        e_layout.addWidget(self.excess_total_label);
        preview_splitter.addWidget(excess_group)
        right_layout.addWidget(preview_splitter);
        main_splitter.setSizes([650, 450])
        self.preview_btn = QPushButton("Preview Breakdown");
        self.save_btn = QPushButton("Save Endorsement");
        self.save_btn.setObjectName("PrimaryButton")
        self.clear_btn = QPushButton("New");
        self.clear_btn.setObjectName("SecondaryButton");
        self.cancel_update_btn = QPushButton("Cancel Update")
        button_layout = QHBoxLayout();
        button_layout.addStretch();
        button_layout.addWidget(self.cancel_update_btn)
        button_layout.addWidget(self.clear_btn);
        button_layout.addWidget(self.preview_btn);
        button_layout.addWidget(self.save_btn)
        left_layout.addLayout(button_layout)
        self.qc_id_lookup_combo.activated.connect(self._on_qc_id_selected);
        self.preview_btn.clicked.connect(self._preview_endorsement);
        self.save_btn.clicked.connect(self._save_record);
        self.clear_btn.clicked.connect(self._clear_form);
        self.cancel_update_btn.clicked.connect(self._clear_form)
        self._clear_form()

    def _load_deleted_records(self):
        search = f"%{self.deleted_search_edit.text()}%"
        try:
            with self.engine.connect() as conn:
                query = text("""
                    SELECT system_ref_no, form_ref_no, product_code, edited_by, edited_on
                    FROM qcfp_endorsements_primary WHERE is_deleted = TRUE
                    AND (system_ref_no ILIKE :st OR form_ref_no ILIKE :st OR product_code ILIKE :st)
                    ORDER BY edited_on DESC
                """)
                res = conn.execute(query, {'st': search}).mappings().all()
            headers = ["System Ref No", "Form Ref No", "Product Code", "Deleted By", "Deleted On"]
            self._populate_deleted_records_table(res, headers)
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load deleted records: {e}")

    def _populate_deleted_records_table(self, data, headers):
        table = self.deleted_records_table
        table.setRowCount(0);
        table.setColumnCount(len(headers));
        table.setHorizontalHeaderLabels(headers)
        self._configure_table_ui(table)
        if not data: return
        table.setRowCount(len(data))
        keys = ["system_ref_no", "form_ref_no", "product_code", "edited_by", "edited_on"]
        for i, row in enumerate(data):
            for j, key in enumerate(keys):
                value = row.get(key)
                display_value = QDateTime(value).toString('yyyy-MM-dd hh:mm AP') if isinstance(value,
                                                                                               datetime) else str(
                    value or "")
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
        ref_no = self.deleted_records_table.item(selected[0].row(), 0).text()
        reply = QMessageBox.question(self, "Confirm Restore",
                                     f"Are you sure you want to restore Endorsement <b>{ref_no}</b>?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                with self.engine.connect() as conn, conn.begin():
                    # --- Get data for transaction logging ---
                    primary_data = conn.execute(
                        text("SELECT * FROM qcfp_endorsements_primary WHERE system_ref_no = :ref"),
                        {"ref": ref_no}).mappings().one()

                    breakdown_lots = conn.execute(text(
                        "SELECT lot_number, quantity_kg FROM qcfp_endorsements_secondary WHERE system_ref_no = :ref"),
                        {"ref": ref_no}).mappings().all()

                    excess_lots = conn.execute(text(
                        "SELECT lot_number, quantity_kg FROM qcfp_endorsements_excess WHERE system_ref_no = :ref"),
                        {"ref": ref_no}).mappings().all()

                    all_lots = breakdown_lots + excess_lots

                    # 1. Restore the primary record
                    conn.execute(text(
                        "UPDATE qcfp_endorsements_primary SET is_deleted = FALSE, edited_by = :u, edited_on = :n WHERE system_ref_no = :ref"),
                        {"u": self.username, "n": datetime.now(), "ref": ref_no})

                    # 2. Clear out any "reversal" transactions created during deletion
                    conn.execute(text(
                        "DELETE FROM failed_transactions WHERE source_ref_no = :ref AND transaction_type LIKE 'QC_FP_DELETED%'"),
                                 {"ref": ref_no})
                    conn.execute(text(
                        "DELETE FROM transactions WHERE source_ref_no = :ref AND transaction_type LIKE 'QC_FP_DELETED%'"),
                                 {"ref": ref_no})

                    # 3. Re-create the original transactions (OUT from FAILED, IN to FG)
                    self._create_inventory_transactions(conn, ref_no, primary_data, all_lots)

                self.log_audit_trail("RESTORE_QCFP_ENDORSEMENT", f"Restored QCFP: {ref_no}")
                QMessageBox.information(self, "Success",
                                        f"Endorsement {ref_no} has been restored and inventory transactions updated.")
                self._refresh_all_data_views()
            except Exception as e:
                traceback.print_exc()
                QMessageBox.critical(self, "Database Error", f"Could not restore record: {e}")

    def _refresh_all_data_views(self):
        self._load_all_records();
        self._load_deleted_records();

    def _show_selected_record_in_view_tab(self):
        selected_rows = self.records_table.selectionModel().selectedRows()
        if not selected_rows: return
        sys_ref_no = self.records_table.item(selected_rows[0].row(), 0).text()
        try:
            with self.engine.connect() as conn:
                primary = conn.execute(text("SELECT * FROM qcfp_endorsements_primary WHERE system_ref_no = :ref"),
                                       {"ref": sys_ref_no}).mappings().one()
                breakdown = conn.execute(text(
                    "SELECT lot_number, quantity_kg FROM qcfp_endorsements_secondary WHERE system_ref_no = :ref ORDER BY id"),
                    {"ref": sys_ref_no}).mappings().all()
                excess = conn.execute(
                    text("SELECT lot_number, quantity_kg FROM qcfp_endorsements_excess WHERE system_ref_no = :ref"),
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
            self._populate_view_table(self.view_breakdown_table, breakdown, ["Lot Number", "Quantity (kg)"])
            self.view_breakdown_total_label.setText(
                f"<b>Total: {sum(d.get('quantity_kg', 0) for d in breakdown):.2f} kg</b>")
            self._populate_view_table(self.view_excess_table, excess, ["Associated Lot", "Excess Qty (kg)"])
            self.view_excess_total_label.setText(f"<b>Total: {sum(d.get('quantity_kg', 0) for d in excess):.2f} kg</b>")
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load details for {sys_ref_no}: {e}")

    def _add_view_detail_row(self, layout, key, value):
        display_text = str(value) if value is not None else "N/A"
        if isinstance(value, (datetime, QDateTime)):
            display_text = QDateTime(value).toString('yyyy-MM-dd hh:mm AP')
        elif isinstance(value, (Decimal, float)):
            display_text = f"{value:.2f}"
        layout.addRow(QLabel(f"<b>{key.replace('_', ' ').title()}:</b>"), QLabel(display_text))

    def _populate_view_table(self, table, data, headers):
        table.setRowCount(0);
        table.setColumnCount(len(headers));
        table.setHorizontalHeaderLabels(headers)
        self._configure_table_ui(table)
        if not data: return
        table.setRowCount(len(data));
        keys = list(data[0].keys()) if data else []
        for i, row_data in enumerate(data):
            for j, key in enumerate(keys):
                val = row_data.get(key)
                item_text = f"{val:.2f}" if isinstance(val, (Decimal, float)) else str(val or "")
                item = QTableWidgetItem(item_text)
                if isinstance(val, (Decimal, float)): item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(i, j, item)
        table.resizeColumnsToContents()

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

    def _on_qc_id_selected(self):
        qc_id_text = self.qc_id_lookup_combo.currentText()
        if not qc_id_text or not self.qc_engine: return
        try:
            qc_id = int(qc_id_text)
            with self.qc_engine.connect() as conn:
                query = text("SELECT original_lot, product_code FROM quality_control WHERE id = :qc_id")
                result = conn.execute(query, {"qc_id": qc_id}).mappings().one_or_none()
            if result:
                self.product_code_combo.setCurrentText(result.get('product_code', ''));
                self.lot_number_edit.setText(result.get('original_lot', ''));
                self.quantity_edit.setFocus()
            else:
                QMessageBox.warning(self, "Not Found", f"No record found for QC ID {qc_id} in the QC database.")
        except ValueError:
            pass
        except Exception as e:
            QMessageBox.critical(self, "Lookup Error", f"An error occurred while looking up QC ID: {e}")

    def _create_combo_with_add(self, table_name, combo):
        layout = QHBoxLayout();
        layout.setContentsMargins(0, 0, 0, 0);
        layout.addWidget(combo, 1)
        add_btn = QPushButton("Manage...");
        add_btn.clicked.connect(lambda: self._handle_add_new_record(table_name, combo));
        layout.addWidget(add_btn);
        return layout

    def _handle_add_new_record(self, table_name, combo_to_update):
        title_map = {"qcfp_endorsers": "Endorser", "warehouses": "Warehouse", "qcfp_receivers": "Receiver"}
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
        queries = {self.endorsed_by_combo: "SELECT name FROM qcfp_endorsers ORDER BY name",
                   self.warehouse_combo: "SELECT name FROM warehouses ORDER BY name",
                   self.received_by_combo: "SELECT name FROM qcfp_receivers ORDER BY name",
                   self.product_code_combo: "SELECT DISTINCT prod_code FROM legacy_production WHERE prod_code IS NOT NULL AND prod_code != '' ORDER BY prod_code"}
        try:
            with self.engine.connect() as conn:
                for combo, query in queries.items():
                    current_text = combo.currentText();
                    items = conn.execute(text(query)).scalars().all()
                    combo.clear();
                    combo.addItems([""] + items)
                    if current_text in items: combo.setCurrentText(current_text)
            if self.qc_engine:
                with self.qc_engine.connect() as qc_conn:
                    qc_id_results = qc_conn.execute(text("SELECT id FROM quality_control ORDER BY id DESC")).fetchall()
                    qc_ids_list = [str(row[0]) for row in qc_id_results]
                    self.qc_id_lookup_combo.blockSignals(True);
                    self.qc_id_lookup_combo.clear();
                    self.qc_id_lookup_combo.addItems([""] + qc_ids_list)
                    self.qc_id_lookup_combo.setCurrentIndex(0);
                    self.qc_id_lookup_combo.blockSignals(False)
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
        self.preview_data = None;
        self.cancel_update_btn.hide();
        self.save_btn.setText("Save Endorsement")
        for w in [self.system_ref_no_edit, self.form_ref_no_edit, self.lot_number_edit]: w.clear()
        self._load_combobox_data()
        for c in [self.product_code_combo, self.endorsed_by_combo, self.warehouse_combo, self.received_by_combo]:
            c.setCurrentIndex(0);
            if c.isEditable(): c.clearEditText()
        for w in [self.quantity_edit, self.weight_per_lot_edit]: w.setText("0.00")
        self.endorsement_date_edit.setDate(QDate.currentDate());
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

    def _populate_preview_widgets(self, data):
        breakdown_data, excess_data = data.get('breakdown', []), data.get('excess', [])
        self._populate_preview_table(self.preview_breakdown_table, breakdown_data, ["Lot Number", "Quantity (kg)"])
        self.breakdown_total_label.setText(
            f"<b>Total: {sum(Decimal(str(item['quantity_kg'])) for item in breakdown_data):.2f} kg</b>")
        self._populate_preview_table(self.preview_excess_table, excess_data, ["Associated Lot", "Excess Qty (kg)"])
        self.excess_total_label.setText(
            f"<b>Total: {sum(Decimal(str(item['quantity_kg'])) for item in excess_data):.2f} kg</b>")

    def _ask_excess_handling_method(self):
        msg_box = QMessageBox(self);
        msg_box.setWindowTitle("Excess Quantity Handling");
        msg_box.setText("An excess quantity was calculated for the lot range.\n\nHow should this excess be handled?")
        # NOTE: Icon removed as per user request.
        add_new_btn = msg_box.addButton("Add as New Lot Number", QMessageBox.ButtonRole.YesRole)
        assign_btn = msg_box.addButton("Assign Excess to Last Lot of Range", QMessageBox.ButtonRole.NoRole);
        msg_box.addButton(QMessageBox.StandardButton.Cancel)
        msg_box.setDefaultButton(add_new_btn);
        msg_box.exec()
        if msg_box.clickedButton() == add_new_btn:
            return 'NEW_LOT'
        elif msg_box.clickedButton() == assign_btn:
            return 'ASSIGN_TO_LAST_IN_RANGE'
        else:
            return None

    def _validate_and_calculate_lots(self):
        try:
            total_qty = Decimal(self.quantity_edit.text() or "0");
            weight_per_lot = Decimal(self.weight_per_lot_edit.text() or "0")
            lot_input = self.lot_number_edit.text().strip()
            if not all([self.form_ref_no_edit.text().strip(), self.product_code_combo.currentText(), lot_input,
                        self.endorsed_by_combo.currentText(), self.warehouse_combo.currentText(),
                        self.received_by_combo.currentText()]):
                QMessageBox.warning(self, "Input Error", "Please fill all required fields before previewing.");
                return None
            if weight_per_lot <= 0: QMessageBox.warning(self, "Input Error", "Weight per Lot must be > 0."); return None

            excess_handling_method = 'NEW_LOT'
            if total_qty > 0 and weight_per_lot > 0 and (total_qty % weight_per_lot > 0):
                is_range = self.is_lot_range_check.isChecked()
                if is_range:
                    choice = self._ask_excess_handling_method()
                    if choice is None: return None
                    excess_handling_method = choice
                else:
                    reply = QMessageBox.question(self, "Excess Quantity Handling",
                                                 "An excess quantity was calculated.\n\nDo you want to create a new lot number for the excess (e.g., 1002AA)?\n\nClick 'No' to retain the original lot number (1001AA) for the excess.",
                                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
                    if reply == QMessageBox.StandardButton.Yes:
                        excess_handling_method = 'NEW_LOT'
                    elif reply == QMessageBox.StandardButton.No:
                        excess_handling_method = 'RETAIN_ORIGINAL_LOT'
                    else:
                        return None

            return self._perform_lot_calculation(total_qty, weight_per_lot, lot_input,
                                                 self.is_lot_range_check.isChecked(), excess_handling_method)
        except (InvalidOperation, ValueError):
            QMessageBox.warning(self, "Input Error", "Invalid numbers for Quantity or Weight per Lot.");
            return None

    def _perform_lot_calculation(self, total_qty, weight_per_lot, lot_input, is_range, excess_handling_method):
        num_full_lots = int(total_qty // weight_per_lot);
        excess_qty = total_qty % weight_per_lot
        breakdown_data, excess_data = [], [];
        range_end_lot = None
        calculated_lots = [lot_input.upper()] * num_full_lots
        if is_range:
            range_info = self._parse_lot_range(lot_input, num_full_lots)
            if range_info is None: return None
            calculated_lots = range_info['lots'];
            range_end_lot = range_info['end_lot']
        if calculated_lots:
            breakdown_data = [{'lot_number': lot, 'quantity_kg': weight_per_lot} for lot in calculated_lots]
        if excess_qty > 0:
            if is_range and excess_handling_method == 'ASSIGN_TO_LAST_IN_RANGE' and range_end_lot:
                excess_data.append({'lot_number': range_end_lot, 'quantity_kg': excess_qty})
            elif not is_range and excess_handling_method == 'RETAIN_ORIGINAL_LOT':
                excess_data.append({'lot_number': lot_input.upper(), 'quantity_kg': excess_qty})
            else:
                last_lot = calculated_lots[-1] if calculated_lots else lot_input.upper()
                match = re.match(r'^(\d+)([A-Z]*)$', last_lot)
                excess_lot_number = f"{str(int(match.group(1)) + 1).zfill(len(match.group(1)))}{match.group(2)}" if match else f"{last_lot}-EXCESS"
                target_list = breakdown_data if not breakdown_data else excess_data
                target_list.append({'lot_number': excess_lot_number, 'quantity_kg': excess_qty})
        return {"breakdown": breakdown_data, "excess": excess_data}

    def _save_record(self):
        if not self.preview_data:
            QMessageBox.warning(self, "Preview Required", "Please 'Preview Breakdown' before saving.")
            return

        is_update = self.current_editing_ref_no is not None
        sys_ref_no = self.current_editing_ref_no if is_update else self._generate_ref_no()

        primary_data = {
            "system_ref_no": sys_ref_no, "form_ref_no": self.form_ref_no_edit.text().strip(),
            "endorsement_date": self.endorsement_date_edit.date().toPyDate(),
            "product_code": self.product_code_combo.currentText(),
            "lot_number": self.lot_number_edit.text().strip(), "quantity_kg": self.quantity_edit.value(),
            "weight_per_lot": self.weight_per_lot_edit.value(),
            "endorsed_by": self.endorsed_by_combo.currentText(),
            "warehouse": self.warehouse_combo.currentText(),
            "received_by_name": self.received_by_combo.currentText(),
            "received_date_time": self.received_date_time_edit.dateTime().toPyDateTime(),
            "encoded_by": self.username, "encoded_on": datetime.now(),
            "edited_by": self.username, "edited_on": datetime.now()
        }

        try:
            with self.engine.connect() as conn, conn.begin():
                # --- Handle Primary Record and Sub-tables ---
                if is_update:
                    conn.execute(text("DELETE FROM qcfp_endorsements_secondary WHERE system_ref_no = :ref"),
                                 {"ref": sys_ref_no})
                    conn.execute(text("DELETE FROM qcfp_endorsements_excess WHERE system_ref_no = :ref"),
                                 {"ref": sys_ref_no})
                    update_sql = text("""
                        UPDATE qcfp_endorsements_primary SET 
                        form_ref_no=:form_ref_no, endorsement_date=:endorsement_date, product_code=:product_code, 
                        lot_number=:lot_number, quantity_kg=:quantity_kg, weight_per_lot=:weight_per_lot, 
                        endorsed_by=:endorsed_by, warehouse=:warehouse, received_by_name=:received_by_name, 
                        received_date_time=:received_date_time, edited_by=:edited_by, edited_on=:edited_on 
                        WHERE system_ref_no = :system_ref_no
                    """)
                    conn.execute(update_sql, primary_data)
                    self.log_audit_trail("UPDATE_QCFP_ENDORSEMENT", f"Updated QCFP: {sys_ref_no}")
                    action_text = "updated"
                else:
                    insert_sql = text("""
                        INSERT INTO qcfp_endorsements_primary (
                            system_ref_no, form_ref_no, endorsement_date, product_code, lot_number, quantity_kg, 
                            weight_per_lot, endorsed_by, warehouse, received_by_name, received_date_time, 
                            encoded_by, encoded_on, edited_by, edited_on
                        ) VALUES (
                            :system_ref_no, :form_ref_no, :endorsement_date, :product_code, :lot_number, :quantity_kg, 
                            :weight_per_lot, :endorsed_by, :warehouse, :received_by_name, :received_date_time, 
                            :encoded_by, :encoded_on, :edited_by, :edited_on
                        )
                    """)
                    conn.execute(insert_sql, primary_data)
                    self.log_audit_trail("CREATE_QCFP_ENDORSEMENT", f"Created QCFP: {sys_ref_no}")
                    action_text = "saved"

                breakdown_lots = self.preview_data.get('breakdown', [])
                excess_lots = self.preview_data.get('excess', [])

                if breakdown_lots:
                    conn.execute(text(
                        "INSERT INTO qcfp_endorsements_secondary (system_ref_no, lot_number, quantity_kg) VALUES (:system_ref_no, :lot_number, :quantity_kg)"),
                                 [{'system_ref_no': sys_ref_no, **lot} for lot in breakdown_lots])
                if excess_lots:
                    conn.execute(text(
                        "INSERT INTO qcfp_endorsements_excess (system_ref_no, lot_number, quantity_kg) VALUES (:system_ref_no, :lot_number, :quantity_kg)"),
                                 [{'system_ref_no': sys_ref_no, **lot} for lot in excess_lots])

                # --- Handle Inventory Transactions ---
                # 1. Clear old transactions for this ref_no to prevent duplicates on update
                conn.execute(text("DELETE FROM failed_transactions WHERE source_ref_no = :ref"), {"ref": sys_ref_no})
                conn.execute(text("DELETE FROM transactions WHERE source_ref_no = :ref"), {"ref": sys_ref_no})

                # 2. Re-create the transactions with new data
                all_lots_to_log = breakdown_lots + excess_lots
                self._create_inventory_transactions(conn, sys_ref_no, primary_data, all_lots_to_log)

            QMessageBox.information(self, "Success",
                                    f"QC Endorsement {sys_ref_no} {action_text} and inventory transactions logged successfully.")
            self._clear_form()
            self._refresh_all_data_views()
            self.tab_widget.setCurrentIndex(0)
        except Exception as e:
            trace_info = traceback.format_exc()
            print(f"SAVE RECORD FAILED: {e}\n{trace_info}")
            QMessageBox.critical(self, "Database Error", f"An error occurred: {e}")

    def _create_inventory_transactions(self, conn, sys_ref_no, primary_data, all_lots_to_log):
        """Helper function to create inventory transactions."""
        # --- Create QTY_OUT from FAILED_TRANSACTIONS ---
        failed_transactions_out = []
        for lot in all_lots_to_log:
            failed_transactions_out.append({
                "transaction_date": primary_data["endorsement_date"],
                "transaction_type": "QC_FP_OUT_FROM_FAILED",
                "source_ref_no": sys_ref_no,
                "product_code": primary_data["product_code"],
                "lot_number": lot["lot_number"],
                "quantity_in": 0,
                "quantity_out": lot["quantity_kg"],
                "unit": "KG.",
                "warehouse": primary_data["warehouse"],
                "encoded_by": self.username,
                "remarks": f"Passed QC. Moved from failed stock. Ref: {sys_ref_no}"
            })
        if failed_transactions_out:
            conn.execute(text("""
                INSERT INTO failed_transactions (
                    transaction_date, transaction_type, source_ref_no, product_code, lot_number,
                    quantity_in, quantity_out, unit, warehouse, encoded_by, remarks
                ) VALUES (
                    :transaction_date, :transaction_type, :source_ref_no, :product_code, :lot_number,
                    :quantity_in, :quantity_out, :unit, :warehouse, :encoded_by, :remarks
                )
            """), failed_transactions_out)

        # --- Create QTY_IN to main TRANSACTIONS ---
        transactions_in = []
        for lot in all_lots_to_log:
            transactions_in.append({
                "transaction_date": primary_data["endorsement_date"],
                "transaction_type": "QC_FP_IN_TO_FG",
                "source_ref_no": sys_ref_no,
                "product_code": primary_data["product_code"],
                "lot_number": lot["lot_number"],
                "quantity_in": lot["quantity_kg"],
                "quantity_out": 0,
                "unit": "KG.",
                "warehouse": primary_data["warehouse"],
                "encoded_by": self.username,
                "remarks": f"Received from QC Failed->Passed. Ref: {sys_ref_no}"
            })
        if transactions_in:
            conn.execute(text("""
                INSERT INTO transactions (
                    transaction_date, transaction_type, source_ref_no, product_code, lot_number,
                    quantity_in, quantity_out, unit, warehouse, encoded_by, remarks
                ) VALUES (
                    :transaction_date, :transaction_type, :source_ref_no, :product_code, :lot_number,
                    :quantity_in, :quantity_out, :unit, :warehouse, :encoded_by, :remarks
                )
            """), transactions_in)

    def _load_all_records(self):
        search = f"%{self.search_edit.text()}%";
        offset = (self.current_page - 1) * self.records_per_page
        try:
            with self.engine.connect() as conn:
                count_query_base = "FROM qcfp_endorsements_primary WHERE is_deleted IS NOT TRUE"
                filter_clause = " AND (system_ref_no ILIKE :st OR form_ref_no ILIKE :st OR product_code ILIKE :st OR lot_number ILIKE :st)" if self.search_edit.text() else ""
                params = {'limit': self.records_per_page, 'offset': offset, 'st': search}
                count_res = conn.execute(text(f"SELECT COUNT(id) {count_query_base} {filter_clause}"),
                                         params).scalar_one()
                self.total_records = count_res
                query = text(
                    f"SELECT system_ref_no, form_ref_no, endorsement_date, product_code, lot_number, quantity_kg FROM qcfp_endorsements_primary WHERE is_deleted IS NOT TRUE {filter_clause} ORDER BY id DESC LIMIT :limit OFFSET :offset")
                res = conn.execute(query, params).mappings().all()
            headers = ["System Ref No", "Form Ref No", "Date", "Product Code", "Lot No / Range", "Total Qty"]
            self._populate_records_table(res, headers);
            self._update_pagination_controls()
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load QC endorsements: {e}")

    def _on_search_text_changed(self):
        self.current_page = 1;
        self._load_all_records()

    def _go_to_prev_page(self):
        if self.current_page > 1: self.current_page -= 1; self._load_all_records()

    def _go_to_next_page(self):
        if self.current_page < self.total_pages: self.current_page += 1; self._load_all_records()

    def _update_pagination_controls(self):
        self.total_pages = (self.total_records + self.records_per_page - 1) // self.records_per_page or 1
        self.page_label.setText(f"Page {self.current_page} of {self.total_pages}");
        self.prev_btn.setEnabled(self.current_page > 1);
        self.next_btn.setEnabled(self.current_page < self.total_pages)

    def _load_record_for_update(self):
        selected_rows = self.records_table.selectionModel().selectedRows()
        if not selected_rows: return
        ref_no = self.records_table.item(selected_rows[0].row(), 0).text()
        try:
            with self.engine.connect() as conn:
                record = conn.execute(text("SELECT * FROM qcfp_endorsements_primary WHERE system_ref_no = :ref"),
                                      {"ref": ref_no}).mappings().one_or_none()
                if not record: QMessageBox.critical(self, "Error", f"Record {ref_no} not found."); return
                breakdown_res = conn.execute(text(
                    "SELECT lot_number, quantity_kg FROM qcfp_endorsements_secondary WHERE system_ref_no = :ref ORDER BY id"),
                    {"ref": ref_no}).mappings().all()
                excess_res = conn.execute(text(
                    "SELECT lot_number, quantity_kg FROM qcfp_endorsements_excess WHERE system_ref_no = :ref ORDER BY id"),
                    {"ref": ref_no}).mappings().all()
            self._clear_form();
            self.current_editing_ref_no = ref_no
            self.system_ref_no_edit.setText(record.get('system_ref_no', ''));
            self.form_ref_no_edit.setText(record.get('form_ref_no', ''))
            if db_date := record.get('endorsement_date'): self.endorsement_date_edit.setDate(
                QDate.fromString(str(db_date), "yyyy-MM-dd"))
            self.product_code_combo.setCurrentText(record.get('product_code', ''));
            self.lot_number_edit.setText(record.get('lot_number', ''))
            self.quantity_edit.setText(f"{record.get('quantity_kg', 0.0):.2f}");
            self.weight_per_lot_edit.setText(f"{record.get('weight_per_lot', 0.0):.2f}")
            self.endorsed_by_combo.setCurrentText(record.get('endorsed_by', ''));
            self.warehouse_combo.setCurrentText(record.get('warehouse', ''))
            self.received_by_combo.setCurrentText(record.get('received_by_name', ''))
            if db_datetime := record.get('received_date_time'): self.received_date_time_edit.setDateTime(
                QDateTime(db_datetime))
            self.is_lot_range_check.setChecked('-' in (record.get('lot_number') or ''))
            self.save_btn.setText("Update Endorsement");
            self.cancel_update_btn.show()
            self.preview_data = {'breakdown': list(breakdown_res), 'excess': list(excess_res)}
            self._populate_preview_widgets(self.preview_data)
            self.tab_widget.setCurrentIndex(self.tab_widget.indexOf(self.entry_tab))
        except Exception as e:
            trace_info = traceback.format_exc();
            print(f"LOAD FOR UPDATE FAILED: {e}\n{trace_info}")
            QMessageBox.critical(self, "DB Error", f"Could not load record {ref_no} for editing: {e}")

    def _delete_record(self):
        selected_rows = self.records_table.selectionModel().selectedRows()
        if not selected_rows: return

        ref_no = self.records_table.item(selected_rows[0].row(), 0).text()

        reply = QMessageBox.question(self, "Confirm Deletion",
                                     f"Are you sure you want to delete endorsement <b>{ref_no}</b>?<br><br>"
                                     "This will move it to the 'Deleted' tab and reverse the inventory transactions.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.No: return

        password, ok = QInputDialog.getText(self, "Admin Action Required", "Enter the administrator password:",
                                            QLineEdit.EchoMode.Password)
        if not ok: return
        if password != "Itadmin":
            QMessageBox.critical(self, "Access Denied", "Incorrect password. Deletion cancelled.")
            return

        try:
            with self.engine.connect() as conn, conn.begin():
                # --- Get data for transaction logging before deleting ---
                primary_data = conn.execute(
                    text("SELECT * FROM qcfp_endorsements_primary WHERE system_ref_no = :ref"),
                    {"ref": ref_no}).mappings().one()

                breakdown_lots = conn.execute(
                    text("SELECT lot_number, quantity_kg FROM qcfp_endorsements_secondary WHERE system_ref_no = :ref"),
                    {"ref": ref_no}).mappings().all()
                excess_lots = conn.execute(
                    text("SELECT lot_number, quantity_kg FROM qcfp_endorsements_excess WHERE system_ref_no = :ref"),
                    {"ref": ref_no}).mappings().all()
                all_lots = breakdown_lots + excess_lots

                # 1. Soft-delete the primary record
                conn.execute(text(
                    "UPDATE qcfp_endorsements_primary SET is_deleted = TRUE, edited_by = :user, edited_on = NOW() WHERE system_ref_no = :ref"),
                    {"ref": ref_no, "user": self.username}
                )

                # 2. Clear out the original transactions
                conn.execute(text("DELETE FROM failed_transactions WHERE source_ref_no = :ref"), {"ref": ref_no})
                conn.execute(text("DELETE FROM transactions WHERE source_ref_no = :ref"), {"ref": ref_no})

                # 3. Create reversal transactions (IN to FAILED, OUT from FG)
                # IN to failed_transactions
                failed_trans_in = [
                    {**lot, "type": "QC_FP_DELETED (RETURN_TO_FAILED)", "in": lot['quantity_kg'], "out": 0} for lot in
                    all_lots]
                if failed_trans_in:
                    conn.execute(text("""
                        INSERT INTO failed_transactions (transaction_date, transaction_type, source_ref_no, product_code, lot_number, quantity_in, quantity_out, unit, warehouse, encoded_by, remarks) 
                        VALUES (:date, :type, :ref, :pcode, :lot, :in, :out, 'KG.', :wh, :user, 'Stock returned on deletion of QCFP')
                    """), [
                        {"date": primary_data['endorsement_date'], "ref": ref_no, "pcode": primary_data['product_code'],
                         "lot": l['lot_number'], "in": l['quantity_kg'], "out": 0, "type": "QC_FP_DELETED (RETURN_TO_FAILED)",
                         "wh": primary_data['warehouse'], "user": self.username} for l in failed_trans_in])

                # OUT from transactions
                trans_out = [{**lot, "type": "QC_FP_DELETED (RETURN_FROM_FG)", "in": 0, "out": lot['quantity_kg']} for
                             lot in all_lots]
                if trans_out:
                    conn.execute(text("""
                        INSERT INTO transactions (transaction_date, transaction_type, source_ref_no, product_code, lot_number, quantity_in, quantity_out, unit, warehouse, encoded_by, remarks) 
                        VALUES (:date, :type, :ref, :pcode, :lot, :in, :out, 'KG.', :wh, :user, 'Stock returned on deletion of QCFP')
                    """), [
                        {"date": primary_data['endorsement_date'], "ref": ref_no, "pcode": primary_data['product_code'],
                         "lot": l['lot_number'], "in": 0, "out": l['quantity_kg'], "type": "QC_FP_DELETED (RETURN_FROM_FG)",
                         "wh": primary_data['warehouse'], "user": self.username} for l in trans_out])

            self.log_audit_trail("DELETE_QCFP_ENDORSEMENT", f"Soft-deleted QCFP: {ref_no}")
            QMessageBox.information(self, "Success",
                                    f"Endorsement {ref_no} has been deleted and inventory transactions have been reversed.")
            self._refresh_all_data_views()
        except Exception as e:
            traceback.print_exc()
            QMessageBox.critical(self, "Database Error", f"Could not delete record: {e}")

    def _generate_ref_no(self):
        prefix = f"QCFP-{datetime.now().strftime('%y%m')}-"
        with self.engine.connect() as conn:
            last_ref = conn.execute(text(
                "SELECT system_ref_no FROM qcfp_endorsements_primary WHERE system_ref_no LIKE :p ORDER BY id DESC LIMIT 1"),
                {"p": f"{prefix}%"}).scalar_one_or_none()
            next_seq = int(last_ref.split('-')[-1]) + 1 if last_ref else 1
            return f"{prefix}{next_seq:04d}"

    def _parse_lot_range(self, lot_input, num_lots_needed):
        try:
            parts = [s.strip().upper() for s in lot_input.split('-')];
            if len(parts) != 2: raise ValueError("Lot range must contain exactly one hyphen.")
            start_str, end_str = parts
            start_match = re.match(r'^(\d+)([A-Z]*)$', start_str);
            end_match = re.match(r'^(\d+)([A-Z]*)$', end_str)
            if not start_match or not end_match or start_match.group(2) != end_match.group(2): raise ValueError(
                "Format invalid or suffixes mismatch. Expected: '100A-105A'.")
            start_num, end_num, suffix, num_len = int(start_match.group(1)), int(end_match.group(1)), start_match.group(
                2), len(start_match.group(1))
            if start_num > end_num: raise ValueError("Start lot cannot be greater than end lot.")
            if end_num - start_num + 1 < num_lots_needed:
                QMessageBox.warning(self, "Lot Range Too Small",
                                    f"The provided range has {end_num - start_num + 1} lots, but {num_lots_needed} are required. Please adjust.")
                return None
            lots = [f"{str(start_num + i).zfill(num_len)}{suffix}" for i in range(num_lots_needed)]
            return {'lots': lots, 'end_lot': end_str}
        except Exception as e:
            QMessageBox.critical(self, "Lot Range Error", f"Could not parse lot range '{lot_input}': {e}");
            return None

    def _populate_records_table(self, data: list, headers: list):
        table = self.records_table
        table.setRowCount(0);
        table.setColumnCount(len(headers));
        table.setHorizontalHeaderLabels(headers)
        self._configure_table_ui(table)
        if not data: return
        table.setRowCount(len(data))
        for i, row_data in enumerate(data):
            keys = list(row_data.keys())
            for j, key in enumerate(keys):
                val = row_data.get(key)
                item_text = f"{val:.2f}" if isinstance(val, (float, Decimal)) else str(val if val is not None else "")
                item = QTableWidgetItem(item_text)
                if isinstance(val, (float, Decimal)): item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(i, j, item)
        table.resizeColumnsToContents()
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)

    def _populate_preview_table(self, table_widget: QTableWidget, data: list, headers: list):
        table_widget.setRowCount(0);
        table_widget.setColumnCount(len(headers));
        table_widget.setHorizontalHeaderLabels(headers)
        self._configure_table_ui(table_widget)
        if not data: return
        table_widget.setRowCount(len(data));
        keys = list(data[0].keys())
        for i, row_data in enumerate(data):
            for j, key in enumerate(keys):
                val = row_data.get(key)
                item_text = f"{val:.2f}" if isinstance(val, (Decimal, float)) else str(val or "")
                item = QTableWidgetItem(item_text)
                if isinstance(val, (Decimal, float)): item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table_widget.setItem(i, j, item)