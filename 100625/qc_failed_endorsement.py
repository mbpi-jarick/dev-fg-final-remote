import sys
import re
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
import traceback

# --- PyQt6 Imports ---
from PyQt6.QtCore import Qt, QDate, QDateTime, QSize
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTabWidget, QFormLayout, QLineEdit,
                             QComboBox, QDateEdit, QPushButton, QTableWidget, QTableWidgetItem,
                             QAbstractItemView, QHeaderView, QMessageBox, QHBoxLayout, QLabel,
                             QCheckBox, QDialog, QDialogButtonBox, QInputDialog,
                             QSplitter, QGridLayout, QGroupBox, QMenu, QDateTimeEdit,
                             QApplication, QMainWindow)
from PyQt6.QtGui import QDoubleValidator, QIcon

# --- Database Imports ---
from sqlalchemy import create_engine, text

# --- Icon Library Import ---
try:
    import qtawesome as fa
except ImportError:
    fa = None  # Gracefully handle if qtawesome is not installed

# --- Configuration ---
ICON_COLOR = '#d62828'  # Red theme for "Failed" module

# --- Style Definitions ---
INSTRUCTION_STYLE = "color: #4a4e69; background-color: #fde4e1; border: 1px solid #f9c6c0; padding: 8px; border-radius: 4px; margin-bottom: 10px;"
GLOBAL_STYLES = """
    QTableWidget::item:selected {
        background-color: #3a506b;
        color: #FFFFFF;
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
    QPushButton#update_btn {
        background-color: #f39c12; /* Orange for update */
        color: white;
        border: 1px solid #f39c12;
        padding: 5px 10px;
        border-radius: 3px;
    }
    QPushButton#restore_btn { /* Custom style for restore button */
        background-color: #5cb85c;
        color: white;
        border: 1px solid #5cb85c;
        padding: 5px 10px;
        border-radius: 3px;
    }
"""


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
    """QLineEdit customized to handle float input and display with comma thousands separators."""

    def __init__(self, parent=None):
        super().__init__(parent)
        # Use a large range for validator, but comma input is handled by string manipulation
        validator = QDoubleValidator(0.0, 9999999999.0, 6)
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        self.setValidator(validator)
        self.editingFinished.connect(self._format_text)
        self.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.setText("0.00")

    def _format_text(self):
        try:
            # Clean text (remove existing commas) before conversion
            clean_text = self.text().replace(',', '')
            value = float(clean_text or 0.0)
            # Format with comma thousands separator
            self.setText(f"{value:,.2f}")
        except ValueError:
            self.setText("0.00")

    def value(self) -> float:
        # Return the clean float value by stripping commas
        return float(self.text().replace(',', '') or 0.0)


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


class QCFailedEndorsementPage(QWidget):
    def __init__(self, db_engine, username, log_audit_trail_func):
        super().__init__()
        self.engine, self.username, self.log_audit_trail = db_engine, username, log_audit_trail_func
        self.current_editing_ref, self.preview_data = None, None
        self.current_page, self.records_per_page = 1, 200
        self.total_records, self.total_pages = 0, 1

        # Variables to retain values after saving
        self._retained_form_ref = ""
        self._retained_date = QDate.currentDate()
        self._retained_status = ""

        self.init_ui()
        self._load_all_endorsements()

    # --- UI SETUP METHODS ---
    def init_ui(self):
        self.setStyleSheet(GLOBAL_STYLES)
        main_layout = QVBoxLayout(self)

        # --- Header ---
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        icon_label = QLabel()
        if fa:
            icon_pixmap = fa.icon('fa5s.times-circle', color=ICON_COLOR).pixmap(QSize(28, 28))
            icon_label.setPixmap(icon_pixmap)
        header_layout.addWidget(icon_label)
        header_label = QLabel("QC Failed Endorsement")
        header_label.setStyleSheet("font-size: 15pt; font-weight: bold; padding: 10px 0; color: #3a506b;")
        header_layout.addWidget(header_label)
        header_layout.addStretch()
        main_layout.addWidget(header_widget)

        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        self.view_tab = QWidget()
        self.view_details_tab = QWidget()
        self.entry_tab = QWidget()
        self.deleted_tab = QWidget()

        # Add tabs with text and icons
        if fa:
            self.tab_widget.addTab(self.view_tab, fa.icon('fa5s.list', color=ICON_COLOR), "All QC Failed Endorsements")
            self.tab_widget.addTab(self.entry_tab, fa.icon('fa5s.clipboard-list', color=ICON_COLOR),
                                   "Endorsement Entry")
            self.tab_widget.addTab(self.view_details_tab, fa.icon('fa5s.search', color=ICON_COLOR),
                                   "View Endorsement Details")
            self.tab_widget.addTab(self.deleted_tab, fa.icon('fa5s.trash-restore', color=ICON_COLOR), "Deleted Records")
        else:  # Fallback without icons
            self.tab_widget.addTab(self.view_tab, "All QC Failed Endorsements")
            self.tab_widget.addTab(self.entry_tab, "Endorsement Entry")
            self.tab_widget.addTab(self.view_details_tab, "View Endorsement Details")
            self.tab_widget.addTab(self.deleted_tab, "Deleted Records")

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

    def _setup_view_tab(self, tab):
        layout = QVBoxLayout(tab)

        instruction_label = QLabel(
            "<b>Instruction:</b> Search for endorsements. Select a record to view details, load for an update, or delete. Deleting a record will return the inventory to the main transaction log.")
        instruction_label.setStyleSheet(INSTRUCTION_STYLE)
        layout.addWidget(instruction_label)

        controls_group = QGroupBox("Search & Actions")
        top_layout = QHBoxLayout(controls_group)

        top_layout.addWidget(QLabel("Search:"))
        self.search_edit = UpperCaseLineEdit(placeholderText="Filter by Ref No, Product Code, Lot No...")
        top_layout.addWidget(self.search_edit, 1)

        self.refresh_btn = QPushButton(" Refresh")
        self.update_btn = QPushButton(" Load for Update")
        self.delete_btn = QPushButton(" Delete Selected")

        self.update_btn.setObjectName("update_btn")
        self.delete_btn.setObjectName("delete_btn")

        if fa:
            self.refresh_btn.setIcon(fa.icon('fa5s.sync-alt', color=ICON_COLOR))
            self.update_btn.setIcon(fa.icon('fa5s.edit', color='white'))
            self.delete_btn.setIcon(fa.icon('fa5s.trash-alt', color='white'))

        top_layout.addWidget(self.refresh_btn)
        top_layout.addWidget(self.update_btn)
        top_layout.addWidget(self.delete_btn)
        layout.addWidget(controls_group)

        self.records_table = QTableWidget()
        self._configure_table_ui(self.records_table)
        self.records_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.records_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        layout.addWidget(self.records_table)

        pagination_layout = QHBoxLayout()
        self.prev_btn = QPushButton(" Previous")
        self.next_btn = QPushButton("Next ")
        self.next_btn.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        if fa:
            self.prev_btn.setIcon(fa.icon('fa5s.chevron-left', color=ICON_COLOR))
            self.next_btn.setIcon(fa.icon('fa5s.chevron-right', color=ICON_COLOR))

        self.page_label = QLabel("Page 1 of 1")
        pagination_layout.addStretch()
        pagination_layout.addWidget(self.prev_btn)
        pagination_layout.addWidget(self.page_label)
        pagination_layout.addWidget(self.next_btn)
        pagination_layout.addStretch()
        layout.addLayout(pagination_layout)

        self.search_edit.textChanged.connect(self._on_search_text_changed)
        self.refresh_btn.clicked.connect(self._load_all_endorsements)
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
            "<b>Instruction:</b> Browse previously deleted endorsements. To restore a record, select it and click the restore button or right-click.")
        instruction_label.setStyleSheet(INSTRUCTION_STYLE)
        layout.addWidget(instruction_label)

        controls_group = QGroupBox("Search & Actions")
        top_layout = QHBoxLayout(controls_group)

        top_layout.addWidget(QLabel("Search Deleted:"))
        self.deleted_search_edit = UpperCaseLineEdit(placeholderText="Filter by Ref No, Product Code...")
        top_layout.addWidget(self.deleted_search_edit, 1)

        self.refresh_deleted_btn = QPushButton(" Refresh")
        self.restore_btn = QPushButton(" Restore Selected")
        self.restore_btn.setObjectName("restore_btn")
        self.restore_btn.setEnabled(False)

        if fa:
            self.refresh_deleted_btn.setIcon(fa.icon('fa5s.sync-alt', color=ICON_COLOR))
            self.restore_btn.setIcon(fa.icon('fa5s.undo', color='white'))

        top_layout.addWidget(self.refresh_deleted_btn)
        top_layout.addWidget(self.restore_btn)
        layout.addWidget(controls_group)

        self.deleted_records_table = QTableWidget()
        self._configure_table_ui(self.deleted_records_table)
        self.deleted_records_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.deleted_records_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        layout.addWidget(self.deleted_records_table)

        self.deleted_search_edit.textChanged.connect(self._load_deleted_records)
        self.refresh_deleted_btn.clicked.connect(self._load_deleted_records)
        self.restore_btn.clicked.connect(self._restore_record)
        self.deleted_records_table.itemSelectionChanged.connect(
            lambda: self.restore_btn.setEnabled(bool(self.deleted_records_table.selectedItems())))
        self.deleted_records_table.customContextMenuRequested.connect(self._show_deleted_table_context_menu)

    def _setup_view_details_tab(self, tab):
        main_layout = QVBoxLayout(tab)

        instruction_label = QLabel(
            "<b>Instruction:</b> This is a read-only, detailed view of the endorsement selected from the 'All QC Failed Endorsements' tab.")
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
        breakdown_layout.addWidget(self.view_breakdown_table)
        self.view_breakdown_total_label = QLabel("<b>Total: 0.00 kg</b>")
        self.view_breakdown_total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        breakdown_layout.addWidget(self.view_breakdown_total_label)
        tables_splitter.addWidget(breakdown_group)

        excess_group = QGroupBox("Excess Quantity")
        excess_layout = QVBoxLayout(excess_group)
        self.view_excess_table = QTableWidget()
        excess_layout.addWidget(self.view_excess_table)
        self.view_excess_total_label = QLabel("<b>Total: 0.00 kg</b>")
        self.view_excess_total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        excess_layout.addWidget(self.view_excess_total_label)
        tables_splitter.addWidget(excess_group)
        main_layout.addWidget(tables_splitter, 1)

        for table in [self.view_breakdown_table, self.view_excess_table]:
            self._configure_table_ui(table)

    def _setup_entry_tab(self, tab):
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        tab_layout = QHBoxLayout(tab)
        tab_layout.addWidget(main_splitter)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        main_splitter.addWidget(left_widget)

        instruction_label = QLabel(
            "<b>Instruction:</b> Fill out the form to create a new endorsement, or load one to update. Always use 'Preview Breakdown' before saving.")
        instruction_label.setStyleSheet(INSTRUCTION_STYLE)
        left_layout.addWidget(instruction_label)

        details_group = QGroupBox("QC Failed Endorsement Details")
        details_layout = QGridLayout(details_group)

        self.sys_ref_no_edit = QLineEdit(readOnly=True, placeholderText="Auto-generated")
        self.form_ref_no_edit = UpperCaseLineEdit()
        self.endorsement_date_edit = QDateEdit(calendarPopup=True, displayFormat="yyyy-MM-dd")
        self.product_code_combo = QComboBox(editable=True, insertPolicy=QComboBox.InsertPolicy.NoInsert)
        set_combo_box_uppercase(self.product_code_combo)

        # --- NEW FIELD: Failure Status ---
        self.failure_reason_combo = QComboBox(editable=True)
        set_combo_box_uppercase(self.failure_reason_combo)
        # ---------------------------------

        self.lot_number_edit = UpperCaseLineEdit(placeholderText="e.g., 12345 or 12345-12350")
        self.is_lot_range_check = QCheckBox("Calculate lots from a range")
        self.quantity_edit = FloatLineEdit()
        self.weight_per_lot_edit = FloatLineEdit()
        self.endorsed_by_combo = QComboBox(editable=True)
        set_combo_box_uppercase(self.endorsed_by_combo)
        self.warehouse_combo = QComboBox()
        self.received_by_name_combo = QComboBox(editable=True)
        set_combo_box_uppercase(self.received_by_name_combo)
        self.received_date_time_edit = QDateTimeEdit(calendarPopup=True, displayFormat="yyyy-MM-dd hh:mm AP")

        # Row 0
        details_layout.addWidget(QLabel("System Ref:"), 0, 0)
        details_layout.addWidget(self.sys_ref_no_edit, 0, 1)
        details_layout.addWidget(QLabel("<b>Form Ref:</b>"), 0, 2)
        details_layout.addWidget(self.form_ref_no_edit, 0, 3)

        # Row 1
        details_layout.addWidget(QLabel("<b>Date:</b>"), 1, 0)
        details_layout.addWidget(self.endorsement_date_edit, 1, 1)
        details_layout.addWidget(QLabel("<b>Product Code:</b>"), 1, 2)
        details_layout.addWidget(self.product_code_combo, 1, 3)

        # Row 2 (Lot/Range Input)
        details_layout.addWidget(QLabel("<b>Lot Number/Range:</b>"), 2, 0)
        details_layout.addWidget(self.lot_number_edit, 2, 1, 1, 3)  # Span 3 columns

        # Row 3 (Status & Checkbox)
        details_layout.addWidget(QLabel("<b>Failure Status:</b>"), 3, 0)
        details_layout.addLayout(
            self._create_combo_with_manage_button("qcf_failure_reasons", self.failure_reason_combo), 3, 1)
        details_layout.addWidget(self.is_lot_range_check, 3, 2, 1, 2)

        # Row 4 (Quantity)
        details_layout.addWidget(QLabel("Total Qty (kg):"), 4, 0)
        details_layout.addWidget(self.quantity_edit, 4, 1)
        details_layout.addWidget(QLabel("Weight/Lot (kg):"), 4, 2)
        details_layout.addWidget(self.weight_per_lot_edit, 4, 3)

        # Row 5 (Endorsed/Warehouse)
        details_layout.addWidget(QLabel("<b>Endorsed By:</b>"), 5, 0)
        details_layout.addLayout(self._create_combo_with_manage_button("qcf_endorsers", self.endorsed_by_combo), 5, 1)
        details_layout.addWidget(QLabel("<b>Warehouse:</b>"), 5, 2)
        details_layout.addLayout(self._create_combo_with_manage_button("warehouses", self.warehouse_combo), 5, 3)

        # Row 6 (Received)
        details_layout.addWidget(QLabel("<b>Received By:</b>"), 6, 0)
        details_layout.addLayout(
            self._create_combo_with_manage_button("qcf_receivers", self.received_by_name_combo), 6, 1)
        details_layout.addWidget(QLabel("Date/Time Received:"), 6, 2)
        details_layout.addWidget(self.received_date_time_edit, 6, 3)

        details_layout.setColumnStretch(1, 1)
        details_layout.setColumnStretch(3, 1)
        left_layout.addWidget(details_group)
        left_layout.addStretch()

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        main_splitter.addWidget(right_widget)

        breakdown_group = QGroupBox("Lot Breakdown (Preview)")
        breakdown_layout_v = QVBoxLayout(breakdown_group)
        self.preview_breakdown_table = QTableWidget()
        self.breakdown_total_label = QLabel("<b>Total: 0.00 kg</b>")
        self.breakdown_total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        breakdown_layout_v.addWidget(self.preview_breakdown_table)
        breakdown_layout_v.addWidget(self.breakdown_total_label)

        excess_group = QGroupBox("Excess Quantity (Preview)")
        excess_layout_v = QVBoxLayout(excess_group)
        self.preview_excess_table = QTableWidget()
        self.excess_total_label = QLabel("<b>Total: 0.00 kg</b>")
        self.excess_total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        excess_layout_v.addWidget(self.preview_excess_table)
        excess_layout_v.addWidget(self.excess_total_label)

        for table in [self.preview_breakdown_table, self.preview_excess_table]:
            self._configure_table_ui(table)

        right_splitter = QSplitter(Qt.Orientation.Vertical)
        right_splitter.addWidget(breakdown_group)
        right_splitter.addWidget(excess_group)
        right_layout.addWidget(right_splitter)

        main_splitter.setSizes([650, 450])

        button_layout = QHBoxLayout()
        self.preview_btn = QPushButton(" Preview Breakdown")
        self.save_btn = QPushButton(" Save Endorsement")
        self.save_btn.setObjectName("PrimaryButton")
        self.clear_btn = QPushButton(" New")
        self.clear_btn.setObjectName("SecondaryButton")
        self.cancel_update_btn = QPushButton(" Cancel Update")
        self.cancel_update_btn.setObjectName("delete_btn")

        if fa:
            self.preview_btn.setIcon(fa.icon('fa5s.eye', color=ICON_COLOR))
            self.save_btn.setIcon(fa.icon('fa5s.save', color='white'))
            self.clear_btn.setIcon(fa.icon('fa5s.eraser', color="#1e74a8"))
            self.cancel_update_btn.setIcon(fa.icon('fa5s.times', color='white'))

        button_layout.addStretch()
        button_layout.addWidget(self.cancel_update_btn)
        button_layout.addWidget(self.clear_btn)
        button_layout.addWidget(self.preview_btn)
        button_layout.addWidget(self.save_btn)
        left_layout.addLayout(button_layout)

        self.preview_btn.clicked.connect(self._preview_endorsement)
        self.save_btn.clicked.connect(self._save_endorsement)
        self.clear_btn.clicked.connect(self._clear_form)
        self.cancel_update_btn.clicked.connect(self._clear_form)
        self._clear_form()

    def _create_combo_with_manage_button(self, table_name, combo):
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(combo, 1)
        manage_btn = QPushButton(" Manage...")
        if fa:
            manage_btn.setIcon(fa.icon('fa5s.plus-circle', color=ICON_COLOR))
        title_map = {"qcf_endorsers": ("Endorser", "name"), "warehouses": ("Warehouse", "name"),
                     "qcf_receivers": ("Receiver", "name"), "qcf_failure_reasons": ("Failure Reason", "name")}
        title, col = title_map.get(table_name, ("Item", "name"))
        manage_btn.clicked.connect(lambda: self._manage_list(table_name, col, f"Manage {title}s", combo))
        layout.addWidget(manage_btn)
        return layout

    def _show_records_table_context_menu(self, pos):
        if not self.records_table.selectedItems(): return
        menu = QMenu()
        view_action = menu.addAction("View Details")
        edit_action = menu.addAction("Load for Update")
        delete_action = menu.addAction("Delete Record")
        if fa:
            view_action.setIcon(fa.icon('fa5s.eye', color=ICON_COLOR))
            edit_action.setIcon(fa.icon('fa5s.edit', color='#f39c12'))
            delete_action.setIcon(fa.icon('fa5s.trash-alt', color='#e63946'))
        action = menu.exec(self.records_table.mapToGlobal(pos))
        if action == view_action:
            self.tab_widget.setCurrentWidget(self.view_details_tab)
        elif action == edit_action:
            self._load_record_for_update()
        elif action == delete_action:
            self._delete_record()

    def _show_deleted_table_context_menu(self, pos):
        if not self.deleted_records_table.selectedItems(): return
        menu = QMenu()
        restore_action = menu.addAction("Restore Record")
        if fa:
            restore_action.setIcon(fa.icon('fa5s.undo', color='green'))
        action = menu.exec(self.deleted_records_table.mapToGlobal(pos))
        if action == restore_action:
            self._restore_record()

    def _manage_list(self, table_name, column_name, title, combo_to_update):
        dialog = AddNewDialog(self, title, title.replace("Manage ", "").rstrip('s'))
        if dialog.exec() and dialog.new_value:
            try:
                with self.engine.connect() as conn, conn.begin():
                    conn.execute(text(
                        f"INSERT INTO {table_name} ({column_name}) VALUES (:val) ON CONFLICT ({column_name}) DO NOTHING"),
                        {"val": dialog.new_value})
                self._load_combobox_data()
                combo_to_update.setCurrentText(dialog.new_value)
            except Exception as e:
                QMessageBox.critical(self, "DB Error", f"Could not add item: {e}")

    def _on_tab_changed(self, index):
        current_tab_widget = self.tab_widget.widget(index)

        if current_tab_widget == self.view_tab:
            self._load_all_endorsements()
            self._on_record_selection_changed()
        elif current_tab_widget == self.entry_tab and not self.current_editing_ref:
            self._load_combobox_data()
            self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.view_details_tab), False)
        elif current_tab_widget == self.view_details_tab:
            self._show_selected_record_in_view_tab()
        elif current_tab_widget == self.deleted_tab:
            self._load_deleted_records()
            self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.view_details_tab), False)

    def _clear_form(self):
        # 1. Capture retained values if we are clearing *after* a save (not after canceling an update)
        if self.current_editing_ref is None and self.form_ref_no_edit.text() and self.tab_widget.currentWidget() == self.entry_tab:
            self._retained_form_ref = self.form_ref_no_edit.text()
            self._retained_date = self.endorsement_date_edit.date()
            self._retained_status = self.failure_reason_combo.currentText()
        else:
            # If canceling an update or starting fresh, reset retained values to defaults
            self._retained_form_ref = ""
            self._retained_date = QDate.currentDate()
            self._retained_status = ""

        self.current_editing_ref, self.preview_data = None, None
        self.cancel_update_btn.hide()
        self.save_btn.setText(" Save Endorsement")

        self.sys_ref_no_edit.clear()
        self.lot_number_edit.clear()

        # 2. Apply retained values or defaults
        self.form_ref_no_edit.setText(self._retained_form_ref)
        self.endorsement_date_edit.setDate(self._retained_date)

        self.quantity_edit.setText("0.00")
        self.weight_per_lot_edit.setText("0.00")

        self._load_combobox_data()

        # Restore status explicitly after loading combobox data
        self.failure_reason_combo.setCurrentText(self._retained_status)

        # Clear other fields (Product, endorser, warehouse, receiver)
        for c in [self.product_code_combo, self.endorsed_by_combo, self.warehouse_combo, self.received_by_name_combo]:
            if c.isEditable(): c.clearEditText()
            c.setCurrentIndex(-1)

        self.received_date_time_edit.setDateTime(QDateTime.currentDateTime())
        self.is_lot_range_check.setChecked(False)
        self._clear_form_previews()
        self.form_ref_no_edit.setFocus()

    def _clear_form_previews(self):
        self.preview_data = None
        self.preview_breakdown_table.setRowCount(0)
        self.preview_excess_table.setRowCount(0)
        self.breakdown_total_label.setText("<b>Total: 0.00 kg</b>")
        self.excess_total_label.setText("<b>Total: 0.00 kg</b>")

    def _load_combobox_data(self):
        queries = {
            self.product_code_combo: "SELECT DISTINCT prod_code FROM legacy_production WHERE prod_code IS NOT NULL AND prod_code != '' ORDER BY prod_code",
            self.endorsed_by_combo: "SELECT name FROM qcf_endorsers ORDER BY name",
            self.warehouse_combo: "SELECT name FROM warehouses ORDER BY name",
            self.received_by_name_combo: "SELECT name FROM qcf_receivers ORDER BY name",
            # Include Failure Reason Combo
            self.failure_reason_combo: "SELECT name FROM qcf_failure_reasons ORDER BY name"
        }
        try:
            with self.engine.connect() as conn:
                for combo, query in queries.items():
                    current_text = combo.currentText()
                    items = conn.execute(text(query)).scalars().all()
                    combo.clear()
                    combo.addItems([""] + items)
                    if current_text in items:
                        combo.setCurrentText(current_text)
                    else:
                        combo.setCurrentIndex(-1)
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load dropdown data: {e}")

    def _preview_endorsement(self):
        self._clear_form_previews()
        self.preview_data = self._validate_and_calculate_lots()
        if not self.preview_data: return
        self._populate_preview_widgets(self.preview_data)

    def _validate_required_fields(self):
        required_fields = {
            "Form Ref": self.form_ref_no_edit.text(), "Date": self.endorsement_date_edit.text(),
            "Product Code": self.product_code_combo.currentText(),
            "Lot Number/Range": self.lot_number_edit.text(),
            "Failure Status": self.failure_reason_combo.currentText(),  # Validate new field
            "Endorsed By": self.endorsed_by_combo.currentText(), "Warehouse": self.warehouse_combo.currentText(),
            "Received By": self.received_by_name_combo.currentText()}
        missing_fields = [name for name, value in required_fields.items() if not value or not value.strip()]
        if missing_fields:
            QMessageBox.warning(self, "Input Error",
                                "Please complete all required fields:\n\n- " + "\n- ".join(missing_fields))
            return False
        return True

    def _validate_and_calculate_lots(self):
        if not self._validate_required_fields():
            return None
        try:
            total_qty = Decimal(str(self.quantity_edit.value()))
            weight_per_lot = Decimal(str(self.weight_per_lot_edit.value()))
            lot_input = self.lot_number_edit.text().strip()
            if weight_per_lot <= 0:
                QMessageBox.warning(self, "Input Error", "Weight per Lot must be greater than zero.")
                return None
            return self._perform_lot_calculation(total_qty, weight_per_lot, lot_input,
                                                 self.is_lot_range_check.isChecked())
        except (InvalidOperation, ValueError):
            QMessageBox.warning(self, "Input Error", "Enter valid numbers for Quantity and Weight per Lot.")
            return None

    def _perform_lot_calculation(self, total_qty, weight_per_lot, lot_input, is_range, is_update=False):
        num_full_lots = int(total_qty // weight_per_lot)
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
                    # Applied comma formatting
                    msg_box.setText(f"There is an excess of {excess_qty:,.2f} kg.")
                    msg_box.setInformativeText("How should the lot number for this excess be handled?")
                    retain_btn = msg_box.addButton(f"Associate with Last Lot ({last_full_lot})",
                                                   QMessageBox.ButtonRole.YesRole)
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

    def _parse_lot_range(self, lot_input, num_lots):
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
            actual_lots_in_range = end_num - start_num + 1

            if actual_lots_in_range != num_lots:
                msg_box = QMessageBox(self)
                msg_box.setIcon(QMessageBox.Icon.Question)
                msg_box.setWindowTitle("Lot Mismatch")
                msg_box.setText("The lot range count and quantity calculation do not match.")
                msg_box.setInformativeText(
                    f"<b>Lot Range:</b> {actual_lots_in_range} lots<br><b>Quantity Calc:</b> {num_lots} lots<br><br>How to proceed?")
                use_range_btn = msg_box.addButton(f"Use Range ({actual_lots_in_range} Lots)",
                                                  QMessageBox.ButtonRole.YesRole)
                use_calc_btn = msg_box.addButton(f"Use Calc ({num_lots} Lots)", QMessageBox.ButtonRole.NoRole)
                msg_box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
                msg_box.exec()
                clicked = msg_box.clickedButton()
                if clicked == use_range_btn:
                    return [f"{str(start_num + i).zfill(num_len)}{suffix}" for i in range(actual_lots_in_range)]
                elif clicked == use_calc_btn:
                    return [f"{str(start_num + i).zfill(num_len)}{suffix}" for i in range(num_lots)]
                else:
                    return None
            return [f"{str(start_num + i).zfill(num_len)}{suffix}" for i in range(actual_lots_in_range)]
        except Exception as e:
            QMessageBox.critical(self, "Lot Range Error", f"Could not parse lot range '{lot_input}': {e}")
            return None

    def _populate_preview_widgets(self, data):
        breakdown_data = [{'lot_number': lot, 'quantity_kg': data['weight_per_lot']} for lot in data['lots']]
        self._populate_preview_table(self.preview_breakdown_table, breakdown_data, ["Lot Number", "Quantity (kg)"])
        breakdown_total = data['weight_per_lot'] * len(data['lots'])
        # Applied comma formatting
        self.breakdown_total_label.setText(f"<b>Total: {float(breakdown_total):,.2f} kg</b>")
        if data['excess_qty'] > 0 and data['excess_lot_number']:
            excess_data = [{'lot_number': data['excess_lot_number'], 'quantity_kg': data['excess_qty']}]
            self._populate_preview_table(self.preview_excess_table, excess_data, ["Associated Lot", "Excess Qty (kg)"])
            # Applied comma formatting
            self.excess_total_label.setText(f"<b>Total: {float(data['excess_qty']):,.2f} kg</b>")
        else:
            self.preview_excess_table.setRowCount(0)
            self.excess_total_label.setText("<b>Total: 0.00 kg</b>")

    def _save_endorsement(self):
        if not self._validate_required_fields(): return
        if not self.preview_data:
            QMessageBox.warning(self, "Preview Required", "Please click 'Preview Breakdown' before saving.")
            return

        is_update = self.current_editing_ref is not None
        sys_ref_no = self.current_editing_ref if is_update else self._generate_system_ref_no()

        primary_data = {
            "system_ref_no": sys_ref_no, "form_ref_no": self.form_ref_no_edit.text().strip(),
            "endorsement_date": self.endorsement_date_edit.date().toPyDate(),
            "product_code": self.product_code_combo.currentText(), "lot_number": self.lot_number_edit.text().strip(),
            "quantity_kg": self.quantity_edit.value(), "weight_per_lot": self.weight_per_lot_edit.value(),
            "failure_reason": self.failure_reason_combo.currentText(),  # NEW FIELD
            "endorsed_by": self.endorsed_by_combo.currentText(), "warehouse": self.warehouse_combo.currentText(),
            "received_by_name": self.received_by_name_combo.currentText(),
            "received_date_time": self.received_date_time_edit.dateTime().toPyDateTime(),
            "encoded_by": self.username, "encoded_on": datetime.now(),
            "edited_by": self.username, "edited_on": datetime.now()
        }

        try:
            with self.engine.connect() as conn, conn.begin():
                if is_update:
                    # Clean up old transaction logs
                    conn.execute(text(
                        "DELETE FROM failed_transactions WHERE source_ref_no = :ref AND transaction_type = 'QC_FAILED_ENDORSEMENT'"),
                        {"ref": sys_ref_no})
                    conn.execute(text("DELETE FROM qcf_endorsements_secondary WHERE system_ref_no = :ref"),
                                 {"ref": sys_ref_no})
                    conn.execute(text("DELETE FROM qcf_endorsements_excess WHERE system_ref_no = :ref"),
                                 {"ref": sys_ref_no})

                    update_sql = text("""UPDATE qcf_endorsements_primary SET 
                        form_ref_no=:form_ref_no, endorsement_date=:endorsement_date, product_code=:product_code, 
                        lot_number=:lot_number, quantity_kg=:quantity_kg, weight_per_lot=:weight_per_lot, 
                        failure_reason=:failure_reason, 
                        endorsed_by=:endorsed_by, warehouse=:warehouse, received_by_name=:received_by_name, 
                        received_date_time=:received_date_time, edited_by=:edited_by, edited_on=:edited_on 
                        WHERE system_ref_no = :system_ref_no""")
                    conn.execute(update_sql, primary_data)
                    self.log_audit_trail("UPDATE_QC_FAILED", f"Updated endorsement: {sys_ref_no}")
                    action_text = "updated"
                else:
                    insert_sql = text("""INSERT INTO qcf_endorsements_primary (system_ref_no, form_ref_no, endorsement_date, 
                        product_code, lot_number, quantity_kg, weight_per_lot, failure_reason, 
                        endorsed_by, warehouse, received_by_name, received_date_time, encoded_by, encoded_on, edited_by, edited_on) 
                        VALUES (:system_ref_no, :form_ref_no, :endorsement_date, :product_code, :lot_number, 
                        :quantity_kg, :weight_per_lot, :failure_reason, 
                        :endorsed_by, :warehouse, :received_by_name, 
                        :received_date_time, :encoded_by, :encoded_on, :edited_by, :edited_on)""")
                    conn.execute(insert_sql, primary_data)
                    self.log_audit_trail("CREATE_QC_FAILED", f"Created endorsement: {sys_ref_no}")
                    action_text = "saved"

                # Insert secondary and excess records
                breakdown_lots = []
                if self.preview_data['lots']:
                    secondary_records = [{'system_ref_no': sys_ref_no, 'lot_number': lot,
                                          'quantity_kg': self.preview_data['weight_per_lot']} for lot in
                                         self.preview_data['lots']]
                    conn.execute(text(
                        "INSERT INTO qcf_endorsements_secondary (system_ref_no, lot_number, quantity_kg) VALUES (:system_ref_no, :lot_number, :quantity_kg)"),
                        secondary_records)
                    breakdown_lots.extend(secondary_records)

                excess_lots = []
                if self.preview_data['excess_qty'] > 0 and self.preview_data['excess_lot_number']:
                    excess_record = {'system_ref_no': sys_ref_no, 'lot_number': self.preview_data['excess_lot_number'],
                                     'quantity_kg': self.preview_data['excess_qty']}
                    conn.execute(text(
                        "INSERT INTO qcf_endorsements_excess (system_ref_no, lot_number, quantity_kg) VALUES (:system_ref_no, :lot_number, :quantity_kg)"),
                        [excess_record])
                    excess_lots.append(excess_record)

                # Log to failed_transactions
                all_lots_to_log = breakdown_lots + excess_lots
                transactions_to_insert = []
                for lot_data in all_lots_to_log:
                    transactions_to_insert.append({
                        "transaction_date": primary_data["endorsement_date"],
                        "transaction_type": "QC_FAILED_ENDORSEMENT",
                        "source_ref_no": sys_ref_no,
                        "product_code": primary_data["product_code"],
                        "lot_number": lot_data["lot_number"],
                        "quantity_in": lot_data["quantity_kg"],
                        "quantity_out": 0,
                        "unit": "KG.",
                        "warehouse": primary_data["warehouse"],
                        "encoded_by": self.username,
                        "remarks": f"QC Failure: {primary_data['failure_reason']}. QCF No. {sys_ref_no}"
                    })

                if transactions_to_insert:
                    conn.execute(text("""
                        INSERT INTO failed_transactions (
                            transaction_date, transaction_type, source_ref_no, product_code, lot_number, 
                            quantity_in, quantity_out, unit, warehouse, encoded_by, remarks
                        ) VALUES (
                            :transaction_date, :transaction_type, :source_ref_no, :product_code, :lot_number, 
                            :quantity_in, :quantity_out, :unit, :warehouse, :encoded_by, :remarks
                        )
                    """), transactions_to_insert)

                QMessageBox.information(self, "Success",
                                        f"Endorsement {sys_ref_no} has been {action_text} and logged to Failed Transactions.")

                # --- Retention Logic: Capture values before calling _clear_form ---
                if not is_update:
                    # Capture current values
                    self._retained_form_ref = self.form_ref_no_edit.text()
                    self._retained_date = self.endorsement_date_edit.date()
                    self._retained_status = self.failure_reason_combo.currentText()

                self._clear_form()

                # Re-apply retained values after clear only if it was a new save
                if not is_update:
                    self.form_ref_no_edit.setText(self._retained_form_ref)
                    self.endorsement_date_edit.setDate(self._retained_date)
                    self.failure_reason_combo.setCurrentText(self._retained_status)

                self._load_all_endorsements()
                self.tab_widget.setCurrentIndex(self.tab_widget.indexOf(self.view_tab))
        except Exception as e:
            QMessageBox.critical(self, "Database Error",
                                 f"An error occurred while saving: {e}\n{traceback.format_exc()}")
            # If save fails, ensure we reset the retained variables to avoid retaining partial data
            self._retained_form_ref = ""
            self._retained_status = ""

    def _delete_record(self):
        selected_row = self.records_table.currentRow()
        if selected_row < 0: return
        ref_no = self.records_table.item(selected_row, 0).text()

        password, ok = QInputDialog.getText(self, "Password Required", "Enter password to delete:",
                                            QLineEdit.EchoMode.Password)
        if not ok: return
        if password != "Itadmin":
            QMessageBox.warning(self, "Incorrect Password",
                                "The password you entered is incorrect. Deletion cancelled.")
            return

        reply = QMessageBox.question(self, "Confirm Deletion",
                                     f"Are you sure you want to delete endorsement {ref_no}?<br><br>"
                                     "This will remove the item from the failed log and return it to the main inventory.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                with self.engine.connect() as conn, conn.begin():
                    primary_data = conn.execute(
                        text("SELECT * FROM qcf_endorsements_primary WHERE system_ref_no = :ref"),
                        {"ref": ref_no}).mappings().one()
                    all_lots_data = conn.execute(text("""
                        SELECT lot_number, quantity_kg FROM qcf_endorsements_secondary WHERE system_ref_no = :ref
                        UNION ALL
                        SELECT lot_number, quantity_kg FROM qcf_endorsements_excess WHERE system_ref_no = :ref
                    """), {"ref": ref_no}).mappings().all()

                    conn.execute(text(
                        "UPDATE qcf_endorsements_primary SET is_deleted = TRUE, edited_by = :user, edited_on = :now WHERE system_ref_no = :ref"),
                        {"ref": ref_no, "user": self.username, "now": datetime.now()})

                    conn.execute(text(
                        "DELETE FROM failed_transactions WHERE source_ref_no = :ref AND transaction_type = 'QC_FAILED_ENDORSEMENT'"),
                        {"ref": ref_no})

                    transactions_to_insert = []
                    for lot in all_lots_data:
                        transactions_to_insert.append({
                            "transaction_date": primary_data["endorsement_date"],
                            "transaction_type": "QC_FAILED_DELETED (RETURN)",
                            "source_ref_no": ref_no,
                            "product_code": primary_data["product_code"],
                            "lot_number": lot["lot_number"],
                            "quantity_in": lot["quantity_kg"],
                            "quantity_out": 0,
                            "unit": "KG.",
                            "warehouse": primary_data["warehouse"],
                            "encoded_by": self.username,
                            "remarks": f"Stock returned on deletion of QCF No. {ref_no}"
                        })

                    if transactions_to_insert:
                        conn.execute(text("""
                            INSERT INTO transactions (
                                transaction_date, transaction_type, source_ref_no, product_code, lot_number, 
                                quantity_in, quantity_out, unit, warehouse, encoded_by, remarks
                            ) VALUES (
                                :transaction_date, :transaction_type, :source_ref_no, :product_code, :lot_number, 
                                :quantity_in, :quantity_out, :unit, :warehouse, :encoded_by, :remarks
                            )
                        """), transactions_to_insert)

                self.log_audit_trail("DELETE_QC_FAILED",
                                     f"Soft-deleted endorsement: {ref_no} and returned stock to inventory.")
                QMessageBox.information(self, "Success",
                                        f"Endorsement {ref_no} has been deleted and stock returned to main inventory.")
                self._load_all_endorsements()
            except Exception as e:
                QMessageBox.critical(self, "Database Error", f"Failed to delete record: {e}")

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

                    conn.execute(text(
                        "DELETE FROM transactions WHERE source_ref_no = :ref AND transaction_type = 'QC_FAILED_DELETED (RETURN)'"),
                        {"ref": ref_no})

                    primary_data = conn.execute(
                        text("SELECT * FROM qcf_endorsements_primary WHERE system_ref_no = :ref"),
                        {"ref": ref_no}).mappings().one()
                    all_lots_data = conn.execute(text("""
                        SELECT lot_number, quantity_kg FROM qcf_endorsements_secondary WHERE system_ref_no = :ref
                        UNION ALL
                        SELECT lot_number, quantity_kg FROM qcf_endorsements_excess WHERE system_ref_no = :ref
                    """), {"ref": ref_no}).mappings().all()

                    transactions_to_insert = []
                    for lot in all_lots_data:
                        transactions_to_insert.append({
                            "transaction_date": primary_data["endorsement_date"],
                            "transaction_type": "QC_FAILED_ENDORSEMENT",
                            "source_ref_no": ref_no,
                            "product_code": primary_data["product_code"],
                            "lot_number": lot["lot_number"],
                            "quantity_in": lot["quantity_kg"],
                            "quantity_out": 0,
                            "unit": "KG.",
                            "warehouse": primary_data["warehouse"],
                            "encoded_by": self.username,
                            "remarks": f"Restored from QC Failed No. {ref_no}"
                        })

                    if transactions_to_insert:
                        conn.execute(text(
                            "DELETE FROM failed_transactions WHERE source_ref_no = :ref AND transaction_type = 'QC_FAILED_ENDORSEMENT'"),
                            {"ref": ref_no})
                        conn.execute(text("""
                            INSERT INTO failed_transactions (
                                transaction_date, transaction_type, source_ref_no, product_code, lot_number, 
                                quantity_in, quantity_out, unit, warehouse, encoded_by, remarks
                            ) VALUES (
                                :transaction_date, :transaction_type, :source_ref_no, :product_code, :lot_number, 
                                :quantity_in, :quantity_out, :unit, :warehouse, :encoded_by, :remarks
                            )
                        """), transactions_to_insert)

                self.log_audit_trail("RESTORE_QC_FAILED", f"Restored endorsement: {ref_no}")
                QMessageBox.information(self, "Success", f"Endorsement {ref_no} has been restored.")
                self._load_deleted_records()
                self._load_all_endorsements()
            except Exception as e:
                QMessageBox.critical(self, "Database Error", f"Could not restore record: {e}")

    def _generate_system_ref_no(self):
        prefix = f"QCF-{datetime.now().strftime('%y%m')}-"
        try:
            with self.engine.connect() as conn:
                last_ref = conn.execute(text(
                    "SELECT system_ref_no FROM qcf_endorsements_primary WHERE system_ref_no LIKE :p ORDER BY id DESC LIMIT 1"),
                    {"p": f"{prefix}%"}).scalar_one_or_none()
                return f"{prefix}{int(last_ref.split('-')[-1]) + 1 if last_ref else 1:04d}"
        except Exception as e:
            # Fallback for in-memory DB or if table doesn't exist yet
            print(f"DB warning during ref generation: {e}")
            return f"{prefix}0001"

    def _populate_records_table(self, table, data, headers):
        table.setRowCount(0)
        table.setColumnCount(len(headers))
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
                item_text = ""
                if isinstance(value, datetime):
                    item_text = value.strftime('%Y-%m-%d %H:%M')
                elif isinstance(value, date):
                    item_text = value.strftime('%Y-%m-%d')
                elif isinstance(value, (float, Decimal)):
                    item_text = f"{float(value):,.2f}"  # Applied comma formatting
                else:
                    item_text = str(value or "")

                item = QTableWidgetItem(item_text)
                if isinstance(value, (float, Decimal)):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(i, j, item)

        for i in range(header.count()):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)

        try:
            stretch_col_index = headers.index("Product Code")
        except ValueError:
            try:
                stretch_col_index = headers.index("Product")
            except ValueError:
                stretch_col_index = -1

        if stretch_col_index != -1:
            header.setSectionResizeMode(stretch_col_index, QHeaderView.ResizeMode.Stretch)
        elif header.count() > 0:
            header.setStretchLastSection(True)

    def _populate_preview_table(self, table: QTableWidget, data: list, headers: list):
        table.setRowCount(0)
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        header = table.horizontalHeader()

        if not data:
            if header.count() > 0:
                header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            return

        table.setRowCount(len(data))
        for row, item in enumerate(data):
            for col_idx, key in enumerate(item.keys()):
                value = item.get(key)
                # Applied comma formatting
                item_text = f"{float(value):,.2f}" if isinstance(value, (Decimal, float)) else str(value or "")
                table.setItem(row, col_idx, QTableWidgetItem(item_text))

        for i in range(header.count()):
            if i < header.count() - 1:
                header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
            else:  # Last column
                header.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)

    def _on_search_text_changed(self):
        self.current_page = 1
        self._load_all_endorsements()

    def _go_to_prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self._load_all_endorsements()

    def _go_to_next_page(self):
        if self.current_page < self.total_pages:
            self.current_page += 1
            self._load_all_endorsements()

    def _update_pagination_controls(self):
        self.total_pages = (self.total_records + self.records_per_page - 1) // self.records_per_page or 1
        self.page_label.setText(f"Page {self.current_page} of {self.total_pages}")
        self.prev_btn.setEnabled(self.current_page > 1)
        self.next_btn.setEnabled(self.current_page < self.total_pages)

    def _on_record_selection_changed(self):
        is_selected = bool(self.records_table.selectedItems())
        self.update_btn.setEnabled(is_selected)
        self.delete_btn.setEnabled(is_selected)
        self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.view_details_tab), is_selected)
        if is_selected:
            self._show_selected_record_in_view_tab()
        if not is_selected and self.tab_widget.currentIndex() == self.tab_widget.indexOf(self.view_details_tab):
            self.tab_widget.setCurrentIndex(self.tab_widget.indexOf(self.view_tab))

    def _show_selected_record_in_view_tab(self):
        selected_row = self.records_table.currentRow()
        if selected_row < 0: return
        ref_no = self.records_table.item(selected_row, 0).text()

        try:
            with self.engine.connect() as conn:
                primary_data = conn.execute(
                    text("SELECT * FROM qcf_endorsements_primary WHERE system_ref_no = :ref"), {"ref": ref_no}
                ).mappings().first()
                if not primary_data:
                    for layout in [self.view_left_details_layout, self.view_right_details_layout]:
                        while layout.count():
                            item = layout.takeAt(0)
                            if item.widget(): item.widget().deleteLater()
                    return

                for layout in [self.view_left_details_layout, self.view_right_details_layout]:
                    while layout.count():
                        item = layout.takeAt(0)
                        if item.widget(): item.widget().deleteLater()

                items_list = list(primary_data.items())
                midpoint = (len(items_list) + 1) // 2

                for key, value in items_list[:midpoint]:
                    self._add_view_detail_row(self.view_left_details_layout, key, value)
                for key, value in items_list[midpoint:]:
                    self._add_view_detail_row(self.view_right_details_layout, key, value)

                breakdown_data = conn.execute(text(
                    "SELECT lot_number, quantity_kg FROM qcf_endorsements_secondary WHERE system_ref_no = :ref"),
                    {"ref": ref_no}).mappings().all()
                self._populate_preview_table(self.view_breakdown_table, breakdown_data, ["Lot Number", "Quantity (kg)"])

                # Applied comma formatting
                self.view_breakdown_total_label.setText(
                    f"<b>Total: {sum(d.get('quantity_kg', Decimal(0)) for d in breakdown_data):,.2f} kg</b>")

                excess_data = conn.execute(text(
                    "SELECT lot_number, quantity_kg FROM qcf_endorsements_excess WHERE system_ref_no = :ref"),
                    {"ref": ref_no}).mappings().all()
                self._populate_preview_table(self.view_excess_table, excess_data, ["Associated Lot", "Excess Qty (kg)"])

                # Applied comma formatting
                self.view_excess_total_label.setText(
                    f"<b>Total: {sum(d.get('quantity_kg', Decimal(0)) for d in excess_data):,.2f} kg</b>")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load details for {ref_no}: {e}")

    def _add_view_detail_row(self, layout, key, value):
        display_text = str(value) if value is not None else "N/A"
        if isinstance(value, datetime):
            display_text = QDateTime(value).toString('yyyy-MM-dd hh:mm AP')
        elif isinstance(value, date):
            display_text = value.strftime('%Y-%m-%d')
        elif isinstance(value, (Decimal, float)):
            display_text = f"{float(value):,.2f}"  # Applied comma formatting
        layout.addRow(QLabel(f"<b>{key.replace('_', ' ').title()}:</b>"), QLabel(display_text))

    def _load_all_endorsements(self):
        search_term = f"%{self.search_edit.text().strip()}%"
        offset = (self.current_page - 1) * self.records_per_page

        try:
            with self.engine.connect() as conn:
                count_query_base = "FROM qcf_endorsements_primary WHERE is_deleted IS NOT TRUE"
                filter_clause = ""
                params = {'limit': self.records_per_page, 'offset': offset}
                if self.search_edit.text():
                    filter_clause = " AND (system_ref_no ILIKE :st OR form_ref_no ILIKE :st OR product_code ILIKE :st OR lot_number ILIKE :st)"
                    params['st'] = search_term

                count_res = conn.execute(text(f"SELECT COUNT(id) {count_query_base} {filter_clause}"),
                                         {'st': search_term} if self.search_edit.text() else {}).scalar_one()
                self.total_records = count_res

                query = text(f"""
                    SELECT system_ref_no, form_ref_no, endorsement_date, product_code, lot_number, quantity_kg
                    FROM qcf_endorsements_primary WHERE is_deleted IS NOT TRUE {filter_clause}
                    ORDER BY id DESC LIMIT :limit OFFSET :offset""")
                results = conn.execute(query, params).mappings().all()

            headers = ["Sys Ref", "Form Ref", "Date", "Product Code", "Lot Input", "Qty (kg)"]
            self._populate_records_table(self.records_table, results, headers)
            self._update_pagination_controls()
            self._on_record_selection_changed()
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Failed to load endorsements: {e}")
            self._populate_records_table(self.records_table, [],
                                         ["Sys Ref", "Form Ref", "Date", "Product Code", "Lot Input", "Qty (kg)"])

    def _load_deleted_records(self):
        search_term = ""
        if hasattr(self, 'deleted_search_edit'):
            search_term = f"%{self.deleted_search_edit.text().strip()}%"
        try:
            with self.engine.connect() as conn:
                filter_clause = ""
                params = {}
                if search_term:
                    filter_clause = " AND (system_ref_no ILIKE :st OR form_ref_no ILIKE :st OR product_code ILIKE :st OR edited_by ILIKE :st)"
                    params['st'] = search_term
                query = text(f"""
                    SELECT system_ref_no, form_ref_no, endorsement_date, product_code, edited_by, edited_on
                    FROM qcf_endorsements_primary WHERE is_deleted = TRUE {filter_clause} ORDER BY edited_on DESC
                """)
                res = conn.execute(query, params).mappings().all()
            headers = ["Sys Ref", "Form Ref", "Date", "Product", "Deleted By", "Deleted On"]
            self._populate_records_table(self.deleted_records_table, res, headers)
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load deleted records: {e}")
            self._populate_records_table(self.deleted_records_table, [],
                                         ["Sys Ref", "Form Ref", "Date", "Product", "Deleted By", "Deleted On"])

    def _load_record_for_update(self):
        selected_row = self.records_table.currentRow()
        if selected_row < 0: return
        ref_no = self.records_table.item(selected_row, 0).text()
        try:
            with self.engine.connect() as conn:
                record = conn.execute(text("SELECT * FROM qcf_endorsements_primary WHERE system_ref_no = :ref"),
                                      {"ref": ref_no}).mappings().first()
            if not record:
                QMessageBox.warning(self, "Not Found", f"Record {ref_no} not found.")
                return

            # Clear retained values as we are loading an update, not starting a chain of new entries
            self._retained_form_ref = ""
            self._retained_status = ""

            self._clear_form()  # Clears fields but resets retained_date to current date, we fix below.

            self.current_editing_ref = ref_no
            self.sys_ref_no_edit.setText(ref_no)
            self.form_ref_no_edit.setText(record.get('form_ref_no', ''))

            if record.get('endorsement_date'):
                date_val = QDate.fromString(str(record['endorsement_date']), "yyyy-MM-dd")
                self.endorsement_date_edit.setDate(date_val)
                self._retained_date = date_val  # Update retained date too, in case they start new after cancel

            if record.get('received_date_time'): self.received_date_time_edit.setDateTime(
                QDateTime.fromString(str(record['received_date_time']), "yyyy-MM-dd HH:mm:ss"))

            self.product_code_combo.setCurrentText(record.get('product_code', ''))
            self.lot_number_edit.setText(record.get('lot_number', ''))

            # Applied comma formatting
            self.quantity_edit.setText(f"{record.get('quantity_kg', Decimal(0)):,.2f}")
            self.weight_per_lot_edit.setText(f"{record.get('weight_per_lot', Decimal(0)):,.2f}")

            self.failure_reason_combo.setCurrentText(record.get('failure_reason', ''))  # Load new field
            self.endorsed_by_combo.setCurrentText(record.get('endorsed_by', ''))
            self.warehouse_combo.setCurrentText(record.get('warehouse', ''))
            self.received_by_name_combo.setCurrentText(record.get('received_by_name', ''))
            self.is_lot_range_check.setChecked('-' in (record.get('lot_number') or ''))

            self.save_btn.setText(" Update Endorsement")
            self.cancel_update_btn.show()
            self.tab_widget.setCurrentWidget(self.entry_tab)
            QMessageBox.information(self, "Info",
                                    "Record loaded for update. Please Preview Breakdown again before saving changes.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load record for update: {e}\n{traceback.format_exc()}")
            self._clear_form()


# =========================================================================================
# === STANDALONE TEST RUNNER (This block is ignored when the class is imported) =========
# =========================================================================================
if __name__ == "__main__":
    # This block allows the widget to be run and tested independently.

    # 1. Create a mock application environment
    app = QApplication(sys.argv)

    # 2. Set up mock dependencies (database, user, logger)
    # Use an in-memory SQLite database for testing, so no file is created.
    mock_engine = create_engine("sqlite:///:memory:")

    # Create dummy tables required by the widget to prevent crashes on startup.
    try:
        with mock_engine.connect() as conn, conn.begin():
            # Mock QCF Primary with the failure_reason column (as derived from the required changes)
            conn.execute(text(
                "CREATE TABLE qcf_endorsements_primary (id INTEGER PRIMARY KEY, system_ref_no TEXT UNIQUE, form_ref_no TEXT, endorsement_date TEXT, product_code TEXT, lot_number TEXT, quantity_kg REAL, weight_per_lot REAL, failure_reason TEXT, endorsed_by TEXT, warehouse TEXT, received_by_name TEXT, received_date_time TEXT, encoded_by TEXT, encoded_on TEXT, edited_by TEXT, edited_on TEXT, is_deleted BOOLEAN DEFAULT FALSE);"))

            conn.execute(text(
                "CREATE TABLE qcf_endorsements_secondary (system_ref_no TEXT, lot_number TEXT, quantity_kg REAL);"))
            conn.execute(
                text("CREATE TABLE qcf_endorsements_excess (system_ref_no TEXT, lot_number TEXT, quantity_kg REAL);"))
            conn.execute(text("CREATE TABLE legacy_production (prod_code TEXT UNIQUE);"))
            conn.execute(text("CREATE TABLE qcf_endorsers (name TEXT UNIQUE);"))
            conn.execute(text("CREATE TABLE warehouses (name TEXT UNIQUE);"))
            conn.execute(text("CREATE TABLE qcf_receivers (name TEXT UNIQUE);"))
            conn.execute(text("CREATE TABLE qcf_failure_reasons (name TEXT UNIQUE);"))  # New Lookup Table
            conn.execute(text(
                "CREATE TABLE failed_transactions(id INTEGER PRIMARY KEY, transaction_date TEXT, transaction_type TEXT, source_ref_no TEXT, product_code TEXT, lot_number TEXT, quantity_in REAL, quantity_out REAL, unit TEXT, warehouse TEXT, encoded_by TEXT, remarks TEXT);"))
            conn.execute(text("CREATE TABLE transactions(id INTEGER PRIMARY KEY);"))

            # Add some dummy data for dropdowns
            conn.execute(text("INSERT INTO legacy_production (prod_code) VALUES ('PROD-A'), ('PROD-B');"))
            conn.execute(text("INSERT INTO warehouses (name) VALUES ('MAIN-WH'), ('WH-2');"))
            conn.execute(
                text("INSERT INTO qcf_failure_reasons (name) VALUES ('CONTAMINATION'), ('WRONG SPEC'), ('DAMAGE');"))

    except Exception as e:
        print(f"Error creating mock database schema: {e}")

    mock_username = "TEST_USER"


    def mock_log_audit_trail(action, details):
        print(f"[AUDIT LOG] Action: {action}, Details: {details}")


    # 3. Create the main window and the widget instance
    main_window = QMainWindow()
    main_window.setWindowTitle("QC Failed Endorsement - Standalone Test")
    main_window.setGeometry(100, 100, 1200, 800)

    # Instantiate your widget with the mock dependencies
    endorsement_page = QCFailedEndorsementPage(
        db_engine=mock_engine,
        username=mock_username,
        log_audit_trail_func=mock_log_audit_trail
    )

    # 4. Show the window and run the app
    main_window.setCentralWidget(endorsement_page)
    main_window.show()
    sys.exit(app.exec())