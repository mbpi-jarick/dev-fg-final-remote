import sys
import re
import traceback
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

# --- PyQt6 Imports ---
from PyQt6.QtCore import Qt, QDate, QDateTime, QSize
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QTabWidget, QFormLayout, QLineEdit, QDateEdit,
                             QPushButton, QTableWidget, QTableWidgetItem, QComboBox,
                             QAbstractItemView, QHeaderView, QMessageBox, QHBoxLayout, QLabel,
                             QGroupBox, QMenu, QSplitter, QGridLayout, QCheckBox,
                             QDialog, QDialogButtonBox, QInputDialog, QMainWindow)
from PyQt6.QtGui import QDoubleValidator

# --- SQLAlchemy Imports ---
from sqlalchemy import text, create_engine

# --- Icon Library Import ---
try:
    import qtawesome as fa
except ImportError:
    fa = None

# --- Configuration for the secondary QC database ---
DB_CONFIG = {"host": "192.168.1.13", "port": 5432, "dbname": "dbmbpi", "user": "postgres", "password": "mbpi"}
ICON_COLOR = '#27ae60'
INSTRUCTION_STYLE = "color: #4a4e69; background-color: #e0fbfc; border: 1px solid #c5d8e2; padding: 8px; border-radius: 4px; margin-bottom: 10px;"
GLOBAL_STYLES = """
    QTableWidget::item:selected { background-color: #3a506b; color: #FFFFFF; }
    QPushButton#PrimaryButton { background-color: #1e74a8; color: white; border: 1px solid #1e74a8; padding: 5px 10px; border-radius: 3px; }
    QPushButton#SecondaryButton { background-color: #f0f0f0; color: #1e74a8; border: 1px solid #1e74a8; padding: 5px 10px; border-radius: 3px; }
    QPushButton#delete_btn { background-color: #e63946; color: white; border: 1px solid #e63946; padding: 5px 10px; border-radius: 3px; }
    QPushButton#update_btn { background-color: #f39c12; color: white; border: 1px solid #f39c12; padding: 5px 10px; border-radius: 3px; }
    QPushButton#restore_btn { background-color: #5cb85c; color: white; border: 1px solid #5cb85c; padding: 5px 10px; border-radius: 3px; }
"""


class UpperCaseLineEdit(QLineEdit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.textChanged.connect(self._to_upper)

    def _to_upper(self, text: str):
        self.blockSignals(True);
        self.setText(text.upper());
        self.blockSignals(False)


def set_combo_box_uppercase(combo_box: QComboBox):
    if combo_box.isEditable():
        line_edit = combo_box.lineEdit()
        if line_edit:
            line_edit.textChanged.connect(
                lambda text, le=line_edit: (le.blockSignals(True), le.setText(text.upper()), le.blockSignals(False)))


class FloatLineEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        validator = QDoubleValidator(0.0, 99999999.0, 2);
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        self.setValidator(validator);
        self.editingFinished.connect(self._format_text);
        self.setAlignment(Qt.AlignmentFlag.AlignRight);
        self.setText("0.00")

    def _format_text(self):
        try:
            clean_text = self.text().replace(',', '');
            value = float(clean_text or 0.0);
            self.setText(f"{value:,.2f}")
        except ValueError:
            self.setText("0.00")

    def value(self) -> float:
        try:
            clean_text = self.text().replace(',', '');
            return float(clean_text or 0.0)
        except ValueError:
            return 0.0


class AddNewDialog(QDialog):
    def __init__(self, parent, title, label):
        super().__init__(parent);
        self.setWindowTitle(title);
        self.new_value = None
        layout = QFormLayout(self);
        self.name_edit = UpperCaseLineEdit();
        layout.addRow(f"{label}:", self.name_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept);
        buttons.rejected.connect(self.reject);
        layout.addRow(buttons)

    def accept(self):
        self.new_value = self.name_edit.text().strip()
        if not self.new_value: QMessageBox.warning(self, "Input Error", "Value cannot be empty."); return
        super().accept()


class QCFailedPassedPage(QWidget):
    def __init__(self, db_engine, username, log_audit_trail_func):
        super().__init__()
        self.engine, self.username, self.log_audit_trail = db_engine, username, log_audit_trail_func
        self.qc_engine = None
        self.current_editing_ref_no = None;
        self.preview_data = None
        self.current_page, self.records_per_page = 1, 200;
        self.total_records, self.total_pages = 0, 1
        self.init_ui()
        self._load_all_records()

    def init_ui(self):
        self.setStyleSheet(GLOBAL_STYLES);
        main_layout = QVBoxLayout(self)
        header_widget = QWidget();
        header_layout = QHBoxLayout(header_widget);
        header_layout.setContentsMargins(0, 0, 0, 0)
        icon_label = QLabel()
        if fa: icon_label.setPixmap(fa.icon('fa5s.check-circle', color=ICON_COLOR).pixmap(QSize(28, 28)))
        header_layout.addWidget(icon_label)
        header_label = QLabel("QC Failed to Passed Endorsement");
        header_label.setStyleSheet("font-size: 15pt; font-weight: bold; padding: 10px 0; color: #3a506b;")
        header_layout.addWidget(header_label);
        header_layout.addStretch();
        main_layout.addWidget(header_widget)
        self.tab_widget = QTabWidget();
        main_layout.addWidget(self.tab_widget)
        self.view_tab, self.view_details_tab, self.entry_tab, self.deleted_tab = QWidget(), QWidget(), QWidget(), QWidget()
        if fa:
            self.tab_widget.addTab(self.view_tab, fa.icon('fa5s.list', color=ICON_COLOR), "All Endorsements")
            self.tab_widget.addTab(self.entry_tab, fa.icon('fa5s.clipboard-check', color=ICON_COLOR),
                                   "Endorsement Entry")
            self.tab_widget.addTab(self.view_details_tab, fa.icon('fa5s.search', color=ICON_COLOR), "View Details")
            self.tab_widget.addTab(self.deleted_tab, fa.icon('fa5s.trash-restore', color=ICON_COLOR), "Deleted")
        else:
            self.tab_widget.addTab(self.view_tab, "All Endorsements");
            self.tab_widget.addTab(self.entry_tab, "Endorsement Entry")
            self.tab_widget.addTab(self.view_details_tab, "View Details");
            self.tab_widget.addTab(self.deleted_tab, "Deleted")
        self._setup_view_tab(self.view_tab);
        self._setup_view_details_tab(self.view_details_tab);
        self._setup_entry_tab(self.entry_tab);
        self._setup_deleted_tab(self.deleted_tab)
        self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.view_details_tab), False);
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

    def _configure_table_ui(self, table: QTableWidget):
        table.setShowGrid(False);
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus);
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);
        table.verticalHeader().setVisible(False);
        table.horizontalHeader().setHighlightSections(False)
        header = table.horizontalHeader()
        for i in range(header.count()): header.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)

    def _setup_view_tab(self, tab):
        layout = QVBoxLayout(tab);
        instruction_label = QLabel(
            "<b>Instruction:</b> Search for endorsements. Select a record to view details, load for an update, or delete. Deleting a record will reverse the inventory movements.");
        instruction_label.setStyleSheet(INSTRUCTION_STYLE);
        layout.addWidget(instruction_label)
        controls_group = QGroupBox("Search & Actions");
        top_layout = QHBoxLayout(controls_group);
        top_layout.addWidget(QLabel("Search:"));
        self.search_edit = UpperCaseLineEdit(placeholderText="Filter by Ref No, Product Code, Lot No...")
        self.refresh_records_btn = QPushButton(" Refresh");
        self.update_btn = QPushButton(" Load for Update");
        self.delete_btn = QPushButton(" Delete Selected");
        self.update_btn.setObjectName("update_btn");
        self.delete_btn.setObjectName("delete_btn")
        if fa: self.refresh_records_btn.setIcon(fa.icon('fa5s.sync-alt', color=ICON_COLOR)); self.update_btn.setIcon(
            fa.icon('fa5s.edit', color='white')); self.delete_btn.setIcon(fa.icon('fa5s.trash-alt', color='white'))
        top_layout.addWidget(self.search_edit, 1);
        top_layout.addWidget(self.refresh_records_btn);
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
        self.refresh_records_btn.clicked.connect(self._load_all_records);
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
        self.deleted_search_edit = UpperCaseLineEdit(placeholderText="Filter by Ref No, Product Code...")
        self.deleted_refresh_btn = QPushButton(" Refresh");
        self.restore_btn = QPushButton(" Restore Selected");
        self.restore_btn.setObjectName("restore_btn");
        self.restore_btn.setEnabled(False)
        if fa: self.deleted_refresh_btn.setIcon(fa.icon('fa5s.sync-alt', color=ICON_COLOR)); self.restore_btn.setIcon(
            fa.icon('fa5s.undo', color='white'))
        top_layout.addWidget(self.deleted_search_edit, 1);
        top_layout.addWidget(self.deleted_refresh_btn);
        top_layout.addWidget(self.restore_btn);
        layout.addWidget(controls_group)
        self.deleted_records_table = QTableWidget();
        self._configure_table_ui(self.deleted_records_table);
        self.deleted_records_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection);
        self.deleted_records_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu);
        layout.addWidget(self.deleted_records_table)
        self.deleted_search_edit.textChanged.connect(self._load_deleted_records);
        self.deleted_refresh_btn.clicked.connect(self._load_deleted_records);
        self.restore_btn.clicked.connect(self._restore_record);
        self.deleted_records_table.customContextMenuRequested.connect(self._show_deleted_records_context_menu)
        self.deleted_records_table.itemSelectionChanged.connect(
            lambda: self.restore_btn.setEnabled(bool(self.deleted_records_table.selectedItems())))

    def _setup_entry_tab(self, tab):
        main_splitter = QSplitter(Qt.Orientation.Horizontal);
        tab_layout = QHBoxLayout(tab);
        tab_layout.addWidget(main_splitter)
        left_widget = QWidget();
        left_layout = QVBoxLayout(left_widget);
        left_layout.setContentsMargins(0, 0, 5, 0)
        instruction_label = QLabel(
            "<b>Instruction:</b> Fill out the form to create a new endorsement, or load one to update. Always use 'Preview Breakdown' before saving.");
        instruction_label.setStyleSheet(INSTRUCTION_STYLE);
        left_layout.addWidget(instruction_label)
        main_splitter.addWidget(left_widget);
        details_group = QGroupBox("Endorsement Details");
        grid_layout = QGridLayout(details_group)
        self.system_ref_no_edit = QLineEdit(readOnly=True, placeholderText="Auto-generated");
        self.form_ref_no_edit = UpperCaseLineEdit()
        self.endorsement_date_edit = QDateEdit(calendarPopup=True, displayFormat="yyyy-MM-dd");
        self.product_code_combo = QComboBox(editable=True);
        set_combo_box_uppercase(self.product_code_combo)
        self.lot_number_edit = UpperCaseLineEdit(placeholderText="E.G., 12345 OR 12345-12350");
        self.is_lot_range_check = QCheckBox("Calculate lots from a range")
        self.quantity_edit = FloatLineEdit();
        self.weight_per_lot_edit = FloatLineEdit();
        self.endorsed_by_combo = QComboBox();
        self.warehouse_combo = QComboBox()
        self.received_by_combo = QComboBox(editable=True);
        set_combo_box_uppercase(self.received_by_combo)

        # --- FIX: Changed QDateTimeEdit to QDateEdit ---
        self.received_date_edit = QDateEdit(calendarPopup=True, displayFormat="yyyy-MM-dd")

        # --- FIX: Removed the qc_id_lookup_combo and its label ---
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
        grid_layout.addWidget(QLabel("Received Date:"), 7, 2);
        grid_layout.addWidget(self.received_date_edit, 7, 3)  # Changed widget

        grid_layout.setColumnStretch(1, 1);
        grid_layout.setColumnStretch(3, 1);
        left_layout.addWidget(details_group);
        left_layout.addStretch()
        right_widget = QWidget();
        right_layout = QVBoxLayout(right_widget);
        right_layout.setContentsMargins(5, 0, 0, 0);
        main_splitter.addWidget(right_widget)
        preview_splitter = QSplitter(Qt.Orientation.Vertical);
        breakdown_group = QGroupBox("Lot Breakdown (Preview)");
        b_layout = QVBoxLayout(breakdown_group)
        self.preview_breakdown_table = QTableWidget();
        self._configure_table_ui(self.preview_breakdown_table);
        b_layout.addWidget(self.preview_breakdown_table)
        self.breakdown_total_label = QLabel("<b>Total: 0.00 kg</b>");
        self.breakdown_total_label.setAlignment(Qt.AlignmentFlag.AlignRight);
        b_layout.addWidget(self.breakdown_total_label);
        preview_splitter.addWidget(breakdown_group)
        excess_group = QGroupBox("Excess Quantity (Preview)");
        e_layout = QVBoxLayout(excess_group);
        self.preview_excess_table = QTableWidget();
        self._configure_table_ui(self.preview_excess_table);
        e_layout.addWidget(self.preview_excess_table)
        self.excess_total_label = QLabel("<b>Total: 0.00 kg</b>");
        self.excess_total_label.setAlignment(Qt.AlignmentFlag.AlignRight);
        e_layout.addWidget(self.excess_total_label);
        preview_splitter.addWidget(excess_group);
        right_layout.addWidget(preview_splitter)
        main_splitter.setSizes([650, 450]);
        self.preview_btn = QPushButton(" Preview Breakdown");
        self.save_btn = QPushButton(" Save Endorsement");
        self.save_btn.setObjectName("PrimaryButton");
        self.clear_btn = QPushButton(" New");
        self.clear_btn.setObjectName("SecondaryButton");
        self.cancel_update_btn = QPushButton(" Cancel Update");
        self.cancel_update_btn.setObjectName("delete_btn")
        if fa: self.preview_btn.setIcon(fa.icon('fa5s.eye', color=ICON_COLOR)); self.save_btn.setIcon(
            fa.icon('fa5s.save', color='white')); self.clear_btn.setIcon(
            fa.icon('fa5s.eraser', color=ICON_COLOR)); self.cancel_update_btn.setIcon(
            fa.icon('fa5s.times', color='white'))
        button_layout = QHBoxLayout();
        button_layout.addStretch();
        button_layout.addWidget(self.cancel_update_btn);
        button_layout.addWidget(self.clear_btn);
        button_layout.addWidget(self.preview_btn);
        button_layout.addWidget(self.save_btn);
        left_layout.addLayout(button_layout)
        self.preview_btn.clicked.connect(self._preview_endorsement);
        self.save_btn.clicked.connect(self._save_record);
        self.clear_btn.clicked.connect(self._clear_form);
        self.cancel_update_btn.clicked.connect(self._clear_form);
        self._clear_form()

    def _on_record_selection_changed(self):
        is_selected = bool(self.records_table.selectionModel().selectedRows())
        self.update_btn.setEnabled(is_selected);
        self.delete_btn.setEnabled(is_selected)
        self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.view_details_tab), is_selected)
        if is_selected: self._show_selected_record_in_view_tab()
        if not is_selected and self.tab_widget.currentIndex() == self.tab_widget.indexOf(self.view_details_tab):
            self.tab_widget.setCurrentIndex(self.tab_widget.indexOf(self.view_tab))

    def _setup_view_details_tab(self, tab):
        main_layout = QVBoxLayout(tab);
        instruction_label = QLabel(
            "<b>Instruction:</b> This is a read-only, detailed view of the endorsement selected from the 'All Endorsements' tab.");
        instruction_label.setStyleSheet(INSTRUCTION_STYLE);
        main_layout.addWidget(instruction_label)
        details_group = QGroupBox("Endorsement Details (Read-Only)");
        details_container_layout = QHBoxLayout(details_group)
        self.view_left_details_layout = QFormLayout();
        self.view_right_details_layout = QFormLayout();
        details_container_layout.addLayout(self.view_left_details_layout);
        details_container_layout.addLayout(self.view_right_details_layout);
        main_layout.addWidget(details_group)
        tables_splitter = QSplitter(Qt.Orientation.Vertical);
        breakdown_group = QGroupBox("Lot Breakdown");
        breakdown_layout = QVBoxLayout(breakdown_group);
        self.view_breakdown_table = QTableWidget();
        self._configure_table_ui(self.view_breakdown_table);
        breakdown_layout.addWidget(self.view_breakdown_table)
        self.view_breakdown_total_label = QLabel("<b>Total: 0.00 kg</b>");
        self.view_breakdown_total_label.setAlignment(Qt.AlignmentFlag.AlignRight);
        breakdown_layout.addWidget(self.view_breakdown_total_label);
        tables_splitter.addWidget(breakdown_group)
        excess_group = QGroupBox("Excess Quantity");
        excess_layout = QVBoxLayout(excess_group);
        self.view_excess_table = QTableWidget();
        self._configure_table_ui(self.view_excess_table);
        excess_layout.addWidget(self.view_excess_table)
        self.view_excess_total_label = QLabel("<b>Total: 0.00 kg</b>");
        self.view_excess_total_label.setAlignment(Qt.AlignmentFlag.AlignRight);
        excess_layout.addWidget(self.view_excess_total_label);
        tables_splitter.addWidget(excess_group);
        main_layout.addWidget(tables_splitter, 1)

    def _load_deleted_records(self):
        search = f"%{self.deleted_search_edit.text()}%"
        try:
            with self.engine.connect() as conn:
                query = text(
                    """SELECT system_ref_no, form_ref_no, product_code, edited_by, edited_on FROM qcfp_endorsements_primary WHERE is_deleted = TRUE AND (system_ref_no ILIKE :st OR form_ref_no ILIKE :st OR product_code ILIKE :st) ORDER BY edited_on DESC""")
                res = conn.execute(query, {'st': search}).mappings().all()
            headers = ["System Ref No", "Form Ref No", "Product Code", "Deleted By", "Deleted On"]
            self._populate_deleted_records_table(res, headers)
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load deleted records: {e}")

    def _populate_deleted_records_table(self, data, headers):
        table = self.deleted_records_table;
        table.setRowCount(0);
        table.setColumnCount(len(headers));
        table.setHorizontalHeaderLabels(headers);
        self._configure_table_ui(table)
        if not data: return
        table.setRowCount(len(data));
        keys = ["system_ref_no", "form_ref_no", "product_code", "edited_by", "edited_on"]
        for i, row in enumerate(data):
            for j, key in enumerate(keys):
                value = row.get(key);
                display_value = QDateTime(value).toString('yyyy-MM-dd hh:mm AP') if isinstance(value,
                                                                                               datetime) else str(
                    value or "");
                table.setItem(i, j, QTableWidgetItem(display_value))
        table.resizeColumnsToContents();
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

    def _show_deleted_records_context_menu(self, pos):
        row = self.deleted_records_table.rowAt(pos.y())
        if row < 0: return
        self.deleted_records_table.selectRow(row)
        if not self.deleted_records_table.selectedItems(): return
        menu = QMenu();
        restore_action = menu.addAction("Restore Record")
        if fa: restore_action.setIcon(fa.icon('fa5s.undo', color='green'))
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
                    primary_data = conn.execute(
                        text("SELECT * FROM qcfp_endorsements_primary WHERE system_ref_no = :ref"),
                        {"ref": ref_no}).mappings().one()
                    breakdown_lots = conn.execute(text(
                        "SELECT lot_number, quantity_kg FROM qcfp_endorsements_secondary WHERE system_ref_no = :ref"),
                                                  {"ref": ref_no}).mappings().all()
                    excess_lots = conn.execute(
                        text("SELECT lot_number, quantity_kg FROM qcfp_endorsements_excess WHERE system_ref_no = :ref"),
                        {"ref": ref_no}).mappings().all()
                    all_lots = breakdown_lots + excess_lots
                    conn.execute(text(
                        "UPDATE qcfp_endorsements_primary SET is_deleted = FALSE, edited_by = :u, edited_on = :n WHERE system_ref_no = :ref"),
                                 {"u": self.username, "n": datetime.now(), "ref": ref_no})
                    conn.execute(text(
                        "DELETE FROM failed_transactions WHERE source_ref_no = :ref AND transaction_type LIKE 'QC_FP_DELETED%'"),
                                 {"ref": ref_no})
                    conn.execute(text(
                        "DELETE FROM transactions WHERE source_ref_no = :ref AND transaction_type LIKE 'QC_FP_DELETED%'"),
                                 {"ref": ref_no})
                    self._create_inventory_transactions(conn, ref_no, primary_data, all_lots)
                self.log_audit_trail("RESTORE_QCFP_ENDORSEMENT", f"Restored QCFP: {ref_no}")
                QMessageBox.information(self, "Success", f"Endorsement {ref_no} has been restored.")
                self._refresh_all_data_views()
            except Exception as e:
                traceback.print_exc();
                QMessageBox.critical(self, "Database Error", f"Could not restore record: {e}")

    def _refresh_all_data_views(self):
        self._load_all_records();
        self._load_deleted_records()

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
            self._populate_view_table(self.view_breakdown_table, breakdown, ["Lot Number", "Quantity (kg)"]);
            self.view_breakdown_total_label.setText(
                f"<b>Total: {sum(d.get('quantity_kg', 0) for d in breakdown):,.2f} kg</b>")
            self._populate_view_table(self.view_excess_table, excess, ["Associated Lot", "Excess Qty (kg)"]);
            self.view_excess_total_label.setText(
                f"<b>Total: {sum(d.get('quantity_kg', 0) for d in excess):,.2f} kg</b>")
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load details for {sys_ref_no}: {e}")

    def _add_view_detail_row(self, layout, key, value):
        display_text = str(value) if value is not None else "N/A"
        if isinstance(value, (datetime, QDateTime)):
            display_text = QDateTime(value).toString('yyyy-MM-dd hh:mm AP')
        elif isinstance(value, (Decimal, float)):
            display_text = f"{value:,.2f}"
        layout.addRow(QLabel(f"<b>{key.replace('_', ' ').title()}:</b>"), QLabel(display_text))

    def _populate_view_table(self, table, data, headers):
        table.setRowCount(0);
        table.setColumnCount(len(headers));
        table.setHorizontalHeaderLabels(headers);
        self._configure_table_ui(table)
        if not data: return
        table.setRowCount(len(data));
        keys = list(data[0].keys()) if data else []
        for i, row_data in enumerate(data):
            for j, key in enumerate(keys):
                val = row_data.get(key);
                item_text = f"{val:,.2f}" if isinstance(val, (Decimal, float)) else str(val or "")
                item = QTableWidgetItem(item_text)
                if isinstance(val, (Decimal, float)): item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(i, j, item)
        table.resizeColumnsToContents()

    def _show_records_table_context_menu(self, position):
        row = self.records_table.rowAt(position.y())
        if row < 0: return
        self.records_table.selectRow(row)
        if not self.records_table.selectedItems(): return
        menu = QMenu();
        view_action = menu.addAction("View Details");
        edit_action = menu.addAction("Edit Record");
        delete_action = menu.addAction("Delete Record")
        if fa: view_action.setIcon(fa.icon('fa5s.eye', color=ICON_COLOR)); edit_action.setIcon(
            fa.icon('fa5s.edit', color='#f39c12')); delete_action.setIcon(fa.icon('fa5s.trash-alt', color='#e63946'))
        action = menu.exec(self.records_table.mapToGlobal(position))
        if action == view_action:
            self.tab_widget.setCurrentIndex(self.tab_widget.indexOf(self.view_details_tab))
        elif action == edit_action:
            self._load_record_for_update()
        elif action == delete_action:
            self._delete_record()

    def _create_combo_with_add(self, table_name, combo):
        layout = QHBoxLayout();
        layout.setContentsMargins(0, 0, 0, 0);
        layout.addWidget(combo, 1);
        add_btn = QPushButton(" Manage...")
        if fa: add_btn.setIcon(fa.icon('fa5s.plus-circle', color=ICON_COLOR))
        add_btn.clicked.connect(lambda: self._handle_add_new_record(table_name, combo));
        layout.addWidget(add_btn);
        return layout

    def _handle_add_new_record(self, table_name, combo_to_update):
        title_map = {"qcfp_endorsers": "Endorser", "warehouses": "Warehouse", "qcfp_receivers": "Receiver"};
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
        self.save_btn.setText(" Save Endorsement")
        for w in [self.system_ref_no_edit, self.form_ref_no_edit, self.lot_number_edit]: w.clear()
        self._load_combobox_data()
        for c in [self.product_code_combo, self.endorsed_by_combo, self.warehouse_combo, self.received_by_combo]:
            c.setCurrentIndex(0)
            if c.isEditable(): c.clearEditText()
        for w in [self.quantity_edit, self.weight_per_lot_edit]: w.setText("0.00")
        self.endorsement_date_edit.setDate(QDate.currentDate());
        self.received_date_edit.setDate(QDate.currentDate());
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
        self._populate_preview_table(self.preview_breakdown_table, breakdown_data, ["Lot Number", "Quantity (kg)"]);
        self.breakdown_total_label.setText(
            f"<b>Total: {sum(Decimal(str(item['quantity_kg'])) for item in breakdown_data):,.2f} kg</b>")
        self._populate_preview_table(self.preview_excess_table, excess_data, ["Associated Lot", "Excess Qty (kg)"]);
        self.excess_total_label.setText(
            f"<b>Total: {sum(Decimal(str(item['quantity_kg'])) for item in excess_data):,.2f} kg</b>")

    def _ask_excess_handling_method(self):
        msg_box = QMessageBox(self);
        msg_box.setWindowTitle("Excess Quantity Handling");
        msg_box.setText("An excess quantity was calculated for the lot range.\n\nHow should this excess be handled?");
        msg_box.setIcon(QMessageBox.Icon.Question)
        add_new_btn = msg_box.addButton("Add as New Lot Number", QMessageBox.ButtonRole.YesRole);
        assign_btn = msg_box.addButton("Assign Excess to Last Lot of Range", QMessageBox.ButtonRole.NoRole)
        msg_box.addButton(QMessageBox.StandardButton.Cancel);
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
            total_qty = Decimal(str(self.quantity_edit.value()));
            weight_per_lot = Decimal(str(self.weight_per_lot_edit.value()));
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
                                                 "An excess quantity was calculated.\n\nCreate a new lot number for the excess (e.g., 1002AA)?\n\nClick 'No' to use the original lot number (1001AA).",
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
        excess_qty = total_qty % weight_per_lot;
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
                if match:
                    try:
                        next_num = str(int(match.group(1)) + 1).zfill(len(match.group(1))); suffix = match.group(
                            2); excess_lot_number = f"{next_num}{suffix}"
                    except ValueError:
                        excess_lot_number = f"{last_lot}-EXCESS"
                else:
                    excess_lot_number = f"{last_lot}-EXCESS"
                target_list = breakdown_data if not breakdown_data else excess_data
                target_list.append({'lot_number': excess_lot_number, 'quantity_kg': excess_qty})
        return {"breakdown": breakdown_data, "excess": excess_data}

    ### FINAL FIX 1: The definitive save/refresh logic ###
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
            "lot_number": self.lot_number_edit.text().strip(),
            "quantity_kg": self.quantity_edit.value(),
            "weight_per_lot": self.weight_per_lot_edit.value(),
            "endorsed_by": self.endorsed_by_combo.currentText(),
            "warehouse": self.warehouse_combo.currentText(),
            "received_by_name": self.received_by_combo.currentText(),
            "received_date_time": self.received_date_edit.date().toPyDate(),  # Use the new date-only widget
            "encoded_by": self.username, "encoded_on": datetime.now(),
            "edited_by": self.username, "edited_on": datetime.now()
        }

        try:
            with self.engine.connect() as conn, conn.begin():
                if is_update:
                    conn.execute(text("DELETE FROM qcfp_endorsements_secondary WHERE system_ref_no = :ref"),
                                 {"ref": sys_ref_no})
                    conn.execute(text("DELETE FROM qcfp_endorsements_excess WHERE system_ref_no = :ref"),
                                 {"ref": sys_ref_no})
                    update_sql = text("""UPDATE qcfp_endorsements_primary SET 
                        form_ref_no=:form_ref_no, endorsement_date=:endorsement_date, product_code=:product_code, lot_number=:lot_number, quantity_kg=:quantity_kg, weight_per_lot=:weight_per_lot, endorsed_by=:endorsed_by, warehouse=:warehouse, received_by_name=:received_by_name, received_date_time=:received_date_time, edited_by=:edited_by, edited_on=:edited_on 
                        WHERE system_ref_no = :system_ref_no""")
                    conn.execute(update_sql, primary_data)
                    self.log_audit_trail("UPDATE_QCFP_ENDORSEMENT", f"Updated QCFP: {sys_ref_no}")
                    action_text = "updated"
                else:
                    insert_sql = text("""INSERT INTO qcfp_endorsements_primary (system_ref_no, form_ref_no, endorsement_date, product_code, lot_number, quantity_kg, weight_per_lot, endorsed_by, warehouse, received_by_name, received_date_time, encoded_by, encoded_on, edited_by, edited_on) 
                        VALUES (:system_ref_no, :form_ref_no, :endorsement_date, :product_code, :lot_number, :quantity_kg, :weight_per_lot, :endorsed_by, :warehouse, :received_by_name, :received_date_time, :encoded_by, :encoded_on, :edited_by, :edited_on)""")
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

                conn.execute(text("DELETE FROM failed_transactions WHERE source_ref_no = :ref"), {"ref": sys_ref_no})
                conn.execute(text("DELETE FROM transactions WHERE source_ref_no = :ref"), {"ref": sys_ref_no})
                all_lots_to_log = breakdown_lots + excess_lots
                self._create_inventory_transactions(conn, sys_ref_no, primary_data, all_lots_to_log)

            QMessageBox.information(self, "Success", f"QC Endorsement {sys_ref_no} {action_text} successfully.")
            self._clear_form()

            # Reset state for a clean refresh
            self.current_page = 1
            self.search_edit.blockSignals(True)
            self.search_edit.clear()
            self.search_edit.blockSignals(False)

            # Directly call the refresh function
            self._load_all_records()
            self.tab_widget.setCurrentIndex(0)  # Switch to the first tab

        except Exception as e:
            trace_info = traceback.format_exc()
            print(f"SAVE RECORD FAILED: {e}\n{trace_info}")
            QMessageBox.critical(self, "Database Error", f"An error occurred: {e}")

    def _create_inventory_transactions(self, conn, sys_ref_no, primary_data, all_lots_to_log):
        failed_transactions_out = [
            {"transaction_date": primary_data["endorsement_date"], "transaction_type": "QC_FP_OUT_FROM_FAILED",
             "source_ref_no": sys_ref_no, "product_code": primary_data["product_code"], "lot_number": lot["lot_number"],
             "quantity_in": 0, "quantity_out": lot["quantity_kg"], "unit": "KG.",
             "warehouse": primary_data["warehouse"], "encoded_by": self.username,
             "remarks": f"Passed QC. Ref: {sys_ref_no}"} for lot in all_lots_to_log]
        if failed_transactions_out:
            conn.execute(text(
                """INSERT INTO failed_transactions (transaction_date, transaction_type, source_ref_no, product_code, lot_number, quantity_in, quantity_out, unit, warehouse, encoded_by, remarks) VALUES (:transaction_date, :transaction_type, :source_ref_no, :product_code, :lot_number, :quantity_in, :quantity_out, :unit, :warehouse, :encoded_by, :remarks)"""),
                         failed_transactions_out)
        transactions_in = [{"transaction_date": primary_data["endorsement_date"], "transaction_type": "QC_FP_IN_TO_FG",
                            "source_ref_no": sys_ref_no, "product_code": primary_data["product_code"],
                            "lot_number": lot["lot_number"], "quantity_in": lot["quantity_kg"], "quantity_out": 0,
                            "unit": "KG.", "warehouse": primary_data["warehouse"], "encoded_by": self.username,
                            "remarks": f"Received from QC. Ref: {sys_ref_no}"} for lot in all_lots_to_log]
        if transactions_in:
            conn.execute(text(
                """INSERT INTO transactions (transaction_date, transaction_type, source_ref_no, product_code, lot_number, quantity_in, quantity_out, unit, warehouse, encoded_by, remarks) VALUES (:transaction_date, :transaction_type, :source_ref_no, :product_code, :lot_number, :quantity_in, :quantity_out, :unit, :warehouse, :encoded_by, :remarks)"""),
                         transactions_in)

    ### FINAL FIX 2: Corrected the is_deleted check for SQLite compatibility ###
    def _load_all_records(self):
        # Use a boolean check that works for both PostgreSQL and SQLite
        is_deleted_check = "is_deleted IS NOT TRUE" if self.engine.dialect.name == 'postgresql' else "is_deleted = 0"

        like_op = "LIKE" if self.engine.dialect.name == 'sqlite' else 'ILIKE'
        search = f"%{self.search_edit.text()}%"
        offset = (self.current_page - 1) * self.records_per_page
        try:
            with self.engine.connect() as conn:
                filter_clause = ""
                if self.search_edit.text():
                    filter_clause = f" AND (system_ref_no {like_op} :st OR form_ref_no {like_op} :st OR product_code {like_op} :st OR lot_number {like_op} :st)"

                count_query = text(
                    f"SELECT COUNT(id) FROM qcfp_endorsements_primary WHERE {is_deleted_check} {filter_clause}")
                self.total_records = conn.execute(count_query, {'st': search}).scalar_one()

                self.total_pages = (self.total_records + self.records_per_page - 1) // self.records_per_page or 1

                query = text(f"""SELECT system_ref_no, form_ref_no, endorsement_date, product_code, lot_number, quantity_kg 
                                 FROM qcfp_endorsements_primary 
                                 WHERE {is_deleted_check} {filter_clause} 
                                 ORDER BY id DESC LIMIT :limit OFFSET :offset""")
                res = conn.execute(query,
                                   {'st': search, 'limit': self.records_per_page, 'offset': offset}).mappings().all()

            headers = ["System Ref No", "Form Ref No", "Date", "Product Code", "Lot No / Range", "Total Qty"]
            self._populate_records_table(res, headers)
            self._update_pagination_controls()
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load QC endorsements: {e}\n{traceback.format_exc()}")

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
            self.product_code_combo.setCurrentText(record.get('product_code', ''))
            self.lot_number_edit.setText(record.get('lot_number', ''))
            self.quantity_edit.setText(f"{record.get('quantity_kg', 0.0):,.2f}");
            self.weight_per_lot_edit.setText(f"{record.get('weight_per_lot', 0.0):,.2f}")
            self.endorsed_by_combo.setCurrentText(record.get('endorsed_by', ''));
            self.warehouse_combo.setCurrentText(record.get('warehouse', ''));
            self.received_by_combo.setCurrentText(record.get('received_by_name', ''))

            # --- FIX: Handle date-only value from database ---
            if db_date := record.get('received_date_time'):
                q_date = QDate.fromString(str(db_date), "yyyy-MM-dd")
                self.received_date_edit.setDate(q_date)

            self.is_lot_range_check.setChecked('-' in (record.get('lot_number') or ''));
            self.save_btn.setText(" Update Endorsement");
            self.cancel_update_btn.show()
            self.preview_data = {'breakdown': list(breakdown_res), 'excess': list(excess_res)};
            self._populate_preview_widgets(self.preview_data);
            self.tab_widget.setCurrentIndex(self.tab_widget.indexOf(self.entry_tab))
        except Exception as e:
            trace_info = traceback.format_exc()
            print(f"LOAD FOR UPDATE FAILED: {e}\n{trace_info}");
            QMessageBox.critical(self, "DB Error", f"Could not load record {ref_no} for editing: {e}")

    def _delete_record(self):
        selected_rows = self.records_table.selectionModel().selectedRows()
        if not selected_rows: return
        ref_no = self.records_table.item(selected_rows[0].row(), 0).text()
        reply = QMessageBox.question(self, "Confirm Deletion",
                                     f"Are you sure you want to delete endorsement <b>{ref_no}</b>?<br><br>This will reverse the inventory transactions.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.No: return
        password, ok = QInputDialog.getText(self, "Admin Action Required", "Enter admin password:",
                                            QLineEdit.EchoMode.Password)
        if not ok: return
        if password != "Itadmin": QMessageBox.critical(self, "Access Denied", "Incorrect password."); return
        try:
            with self.engine.connect() as conn, conn.begin():
                primary_data = conn.execute(text("SELECT * FROM qcfp_endorsements_primary WHERE system_ref_no = :ref"),
                                            {"ref": ref_no}).mappings().one()
                all_lots = conn.execute(text(
                    "(SELECT lot_number, quantity_kg FROM qcfp_endorsements_secondary WHERE system_ref_no = :ref) UNION ALL (SELECT lot_number, quantity_kg FROM qcfp_endorsements_excess WHERE system_ref_no = :ref)"),
                                        {"ref": ref_no}).mappings().all()
                conn.execute(text(
                    "UPDATE qcfp_endorsements_primary SET is_deleted = TRUE, edited_by = :user, edited_on = :now WHERE system_ref_no = :ref"),
                             {"ref": ref_no, "user": self.username, "now": datetime.now()})
                conn.execute(text("DELETE FROM failed_transactions WHERE source_ref_no = :ref"), {"ref": ref_no});
                conn.execute(text("DELETE FROM transactions WHERE source_ref_no = :ref"), {"ref": ref_no})
                failed_trans_in = [
                    {"type": "QC_FP_DELETED (RETURN_TO_FAILED)", "in": lot['quantity_kg'], "out": 0, **lot} for lot in
                    all_lots]
                if failed_trans_in: conn.execute(text(
                    """INSERT INTO failed_transactions (transaction_date, transaction_type, source_ref_no, product_code, lot_number, quantity_in, quantity_out, unit, warehouse, encoded_by, remarks) VALUES (:date, :type, :ref, :pcode, :lot, :in, :out, 'KG.', :wh, :user, 'Stock returned on deletion')"""),
                                                 [{"date": primary_data['endorsement_date'], "ref": ref_no,
                                                   "pcode": primary_data['product_code'], "lot": l['lot_number'], **l,
                                                   "wh": primary_data['warehouse'], "user": self.username} for l in
                                                  failed_trans_in])
                trans_out = [{"type": "QC_FP_DELETED (RETURN_FROM_FG)", "in": 0, "out": lot['quantity_kg'], **lot} for
                             lot in all_lots]
                if trans_out: conn.execute(text(
                    """INSERT INTO transactions (transaction_date, transaction_type, source_ref_no, product_code, lot_number, quantity_in, quantity_out, unit, warehouse, encoded_by, remarks) VALUES (:date, :type, :ref, :pcode, :lot, :in, :out, 'KG.', :wh, :user, 'Stock returned on deletion')"""),
                                           [{"date": primary_data['endorsement_date'], "ref": ref_no,
                                             "pcode": primary_data['product_code'], "lot": l['lot_number'], **l,
                                             "wh": primary_data['warehouse'], "user": self.username} for l in
                                            trans_out])
            self.log_audit_trail("DELETE_QCFP_ENDORSEMENT", f"Soft-deleted QCFP: {ref_no}");
            QMessageBox.information(self, "Success", f"Endorsement {ref_no} deleted.");
            self._refresh_all_data_views()
        except Exception as e:
            traceback.print_exc();
            QMessageBox.critical(self, "Database Error", f"Could not delete record: {e}")

    # Other functions remain the same as your provided code
    def _on_search_text_changed(self):
        self.current_page = 1; self._load_all_records()

    def _go_to_prev_page(self):
        if self.current_page > 1: self.current_page -= 1; self._load_all_records()

    def _go_to_next_page(self):
        if self.current_page < self.total_pages: self.current_page += 1; self._load_all_records()

    def _update_pagination_controls(self):
        self.total_pages = (self.total_records + self.records_per_page - 1) // self.records_per_page or 1;
        self.page_label.setText(f"Page {self.current_page} of {self.total_pages}")
        self.prev_btn.setEnabled(self.current_page > 1);
        self.next_btn.setEnabled(self.current_page < self.total_pages)

    def _generate_ref_no(self):
        prefix = f"QCFP-{datetime.now().strftime('%y%m')}-"
        with self.engine.connect() as conn:
            last_ref = conn.execute(text(
                "SELECT system_ref_no FROM qcfp_endorsements_primary WHERE system_ref_no LIKE :p ORDER BY id DESC LIMIT 1"),
                                    {"p": f"{prefix}%"}).scalar_one_or_none()
            next_seq = int(last_ref.split('-')[-1]) + 1 if last_ref else 1;
            return f"{prefix}{next_seq:04d}"

    def _parse_lot_range(self, lot_input, num_lots_needed):
        try:
            parts = [s.strip().upper() for s in lot_input.split('-')];
            if len(parts) != 2: raise ValueError("Lot range must contain exactly one hyphen.")
            start_str, end_str = parts;
            start_match = re.match(r'^(\d+)([A-Z]*)$', start_str);
            end_match = re.match(r'^(\d+)([A-Z]*)$', end_str)
            if not start_match or not end_match or start_match.group(2) != end_match.group(2): raise ValueError(
                "Format invalid or suffixes mismatch.")
            start_num, end_num, suffix, num_len = int(start_match.group(1)), int(end_match.group(1)), start_match.group(
                2), len(start_match.group(1))
            if start_num > end_num: raise ValueError("Start lot cannot be greater than end lot.")
            if end_num - start_num + 1 < num_lots_needed:
                QMessageBox.warning(self, "Lot Range Too Small",
                                    f"Range has {end_num - start_num + 1} lots, but {num_lots_needed} are required.");
                return None
            lots = [f"{str(start_num + i).zfill(num_len)}{suffix}" for i in range(num_lots_needed)];
            return {'lots': lots, 'end_lot': end_str}
        except Exception as e:
            QMessageBox.critical(self, "Lot Range Error", f"Could not parse lot range '{lot_input}': {e}");
            return None

    def _populate_records_table(self, data: list, headers: list):
        table = self.records_table;
        table.setRowCount(0);
        table.setColumnCount(len(headers));
        table.setHorizontalHeaderLabels(headers);
        self._configure_table_ui(table)
        if not data: return
        table.setRowCount(len(data))
        for i, row_data in enumerate(data):
            keys = list(row_data.keys())
            for j, key in enumerate(keys):
                val = row_data.get(key);
                item_text = f"{val:,.2f}" if isinstance(val, (float, Decimal)) else str(val if val is not None else "")
                item = QTableWidgetItem(item_text)
                if isinstance(val, (float, Decimal)): item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(i, j, item)
        table.resizeColumnsToContents();
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch);
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)

    def _populate_preview_table(self, table_widget: QTableWidget, data: list, headers: list):
        table_widget.setRowCount(0);
        table_widget.setColumnCount(len(headers));
        table_widget.setHorizontalHeaderLabels(headers);
        self._configure_table_ui(table_widget)
        if not data: return
        table_widget.setRowCount(len(data));
        keys = list(data[0].keys())
        for i, row_data in enumerate(data):
            for j, key in enumerate(keys):
                val = row_data.get(key);
                item_text = f"{val:,.2f}" if isinstance(val, (Decimal, float)) else str(val or "")
                item = QTableWidgetItem(item_text)
                if isinstance(val, (Decimal, float)): item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table_widget.setItem(i, j, item)
        table_widget.resizeColumnsToContents()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    # Using a dummy in-memory SQLite database for standalone testing
    db_engine = create_engine("sqlite:///:memory:")
    # You can replace the above with your actual database engine

    # Setup dummy schema and data
    try:
        with db_engine.connect() as conn, conn.begin():
            # Create tables
            conn.execute(text(
                "CREATE TABLE qcfp_endorsements_primary (id INTEGER PRIMARY KEY, system_ref_no TEXT, form_ref_no TEXT, endorsement_date DATE, product_code TEXT, lot_number TEXT, quantity_kg REAL, weight_per_lot REAL, endorsed_by TEXT, warehouse TEXT, received_by_name TEXT, received_date_time DATE, encoded_by TEXT, encoded_on DATETIME, edited_by TEXT, edited_on DATETIME, is_deleted BOOLEAN DEFAULT 0)"))
            conn.execute(text(
                "CREATE TABLE qcfp_endorsements_secondary (id INTEGER PRIMARY KEY, system_ref_no TEXT, lot_number TEXT, quantity_kg REAL)"))
            conn.execute(text(
                "CREATE TABLE qcfp_endorsements_excess (id INTEGER PRIMARY KEY, system_ref_no TEXT, lot_number TEXT, quantity_kg REAL)"))
            conn.execute(text("CREATE TABLE qcfp_endorsers (name TEXT UNIQUE)"))
            conn.execute(text("CREATE TABLE warehouses (name TEXT UNIQUE)"))
            conn.execute(text("CREATE TABLE qcfp_receivers (name TEXT UNIQUE)"))
            conn.execute(text("CREATE TABLE legacy_production (prod_code TEXT UNIQUE)"))
            conn.execute(text(
                "CREATE TABLE failed_transactions (id INTEGER PRIMARY KEY, transaction_date DATE, transaction_type TEXT, source_ref_no TEXT, product_code TEXT, lot_number TEXT, quantity_in REAL, quantity_out REAL, unit TEXT, warehouse TEXT, encoded_by TEXT, remarks TEXT)"))
            conn.execute(text(
                "CREATE TABLE transactions (id INTEGER PRIMARY KEY, transaction_date DATE, transaction_type TEXT, source_ref_no TEXT, product_code TEXT, lot_number TEXT, quantity_in REAL, quantity_out REAL, unit TEXT, warehouse TEXT, encoded_by TEXT, remarks TEXT)"))

            # Insert dummy data
            conn.execute(text("INSERT INTO qcfp_endorsers (name) VALUES ('JOHN DOE'), ('JANE SMITH')"))
            conn.execute(text("INSERT INTO warehouses (name) VALUES ('MAIN-WH'), ('QC-WH')"))
            conn.execute(text("INSERT INTO qcfp_receivers (name) VALUES ('WAREHOUSE STAFF 1'), ('WAREHOUSE STAFF 2')"))
            conn.execute(text("INSERT INTO legacy_production (prod_code) VALUES ('PROD-A'), ('PROD-B')"))

    except Exception as e:
        print(f"Error setting up dummy database: {e}")

    main_window = QMainWindow()
    main_window.setWindowTitle("QC Failed to Passed Module - Standalone")
    main_window.setGeometry(100, 100, 1200, 800)
    main_widget = QCFailedPassedPage(db_engine, "TEST_USER", lambda x, y: print(f"AUDIT: {x} - {y}"))
    main_window.setCentralWidget(main_widget)
    main_window.show()
    sys.exit(app.exec())