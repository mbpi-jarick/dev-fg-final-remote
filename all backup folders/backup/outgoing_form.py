# outgoing_form.py
# ENHANCED: Applied security and recovery features consistent with fg_endorsement.py.
# NEW: Implemented password protection for deletion ("Itadmin").
# NEW: Added a "Deleted Records" tab with a restore function and right-click context menu.
# UI POLISH: Ensured all table headers auto-size to fill available space.
# FIX: Corrected the sorting of the Production/Series ID combo box to be numerically descending (highest first).
# FEATURE: In Add/Edit Item dialog, "Box#" is now a 1-999 ComboBox, and "Qty Produced" is a manageable ComboBox.
# VALIDATION: Added rule to ensure "Remaining Qty" is not greater than "Qty Req'd".
# VALIDATION: Added checks to ensure "Ref#" and "Released By" are filled before saving.
# FIX: Restored the fully functional "Released By" ComboBox and its "Manage..." button.
# WORKFLOW: All data-mutating actions now auto-refresh all tables without changing tabs. Added manual Refresh button and auto-refresh on tab switch.

import sys
import traceback
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

# --- PyQt6 Imports ---
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTabWidget, QFormLayout, QLineEdit,
                             QComboBox, QDateEdit, QPushButton, QTableWidget, QTableWidgetItem,
                             QAbstractItemView, QHeaderView, QMessageBox, QHBoxLayout, QLabel,
                             QDialog, QDialogButtonBox, QInputDialog, QListWidget, QListWidgetItem,
                             QGridLayout, QGroupBox, QMenu, QSplitter)
from PyQt6.QtGui import QDoubleValidator, QPainter
from PyQt6.QtCharts import QChartView, QChart, QPieSeries, QPieSlice

# --- Icon Imports ---
try:
    import qtawesome as fa
except ImportError:
    fa = None

# --- Database Imports ---
from sqlalchemy import text

# --- CONSTANTS ---
ADMIN_PASSWORD = "Itadmin"


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
        remove_btn.setObjectName("SecondaryButton")
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
        self.setMinimumWidth(450)
        self.setModal(True)
        layout = QFormLayout(self)
        self.prod_id = UpperCaseLineEdit()
        self.product_code = UpperCaseLineEdit()
        self.lot_used = UpperCaseLineEdit()
        self.qty_req = FloatLineEdit()
        self.new_lot = UpperCaseLineEdit()
        self.status = QComboBox();
        self.status.addItems(["", "PASSED", "FAILED"])

        self.box_num = QComboBox()
        self.box_num.setEditable(True)
        self.box_num.addItems([""] + [str(i) for i in range(1, 1000)])

        self.rem_qty = FloatLineEdit()

        self.qty_prod = QComboBox()
        self.qty_prod.setEditable(True)
        manage_qty_prod_btn = QPushButton("Manage...")
        qty_prod_layout = QHBoxLayout()
        qty_prod_layout.setContentsMargins(0, 0, 0, 0)
        qty_prod_layout.addWidget(self.qty_prod, 1)
        qty_prod_layout.addWidget(manage_qty_prod_btn)
        manage_qty_prod_btn.clicked.connect(self._manage_qty_produced_list)

        layout.addRow("Prod'n ID:", self.prod_id)
        layout.addRow("Product Code:", self.product_code)
        layout.addRow("Lot# Used:", self.lot_used)
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

        self._load_qty_produced_options()

        if data:
            self.prod_id.setText(data.get('prod_id', ''))
            self.product_code.setText(data.get('product_code', ''))
            self.lot_used.setText(data.get('lot_used', ''))
            self.qty_req.setText(str(data.get('quantity_required_kg', '0.00')))
            self.new_lot.setText(data.get('new_lot_details', ''))
            self.status.setCurrentText(data.get('status', ''))
            self.box_num.setCurrentText(str(data.get('box_number', '')))
            self.rem_qty.setText(str(data.get('remaining_quantity', '0.00')))
            self.qty_prod.setCurrentText(data.get('quantity_produced', ''))

    def accept(self):
        qty_req = self.qty_req.value()
        rem_qty = self.rem_qty.value()

        if rem_qty > qty_req:
            QMessageBox.warning(self, "Validation Error", "The 'Remaining Qty' cannot be greater than the 'Qty Req'd'.")
            return

        super().accept()

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
            "quantity_produced": self.qty_prod.currentText()
        }


class OutgoingFormPage(QWidget):
    ITEM_TABLE_HEADERS = [
        "Prod'n ID", "Product Code", "Lot# Used", "Qty Req'd", "New Lot Details",
        "Status", "Box#", "Rem. Qty", "Qty Prod."
    ]

    def __init__(self, db_engine, username, log_audit_trail_func):
        super().__init__()
        self.engine, self.username, self.log_audit_trail = db_engine, username, log_audit_trail_func
        self.current_editing_primary_id = None
        self.current_page, self.records_per_page = 1, 200
        self.total_records, self.total_pages = 0, 1
        self.init_ui()
        self._load_all_records()
        self._update_dashboard_data()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)
        self.setStyleSheet("""
            QPushButton#PrimaryButton { background-color: #28a745; color: white; font-weight: bold; border-radius: 4px; padding: 6px 12px; }
            QPushButton#PrimaryButton:hover { background-color: #218838; }
            QPushButton#DangerButton { background-color: #dc3545; color: white; font-weight: bold; border-radius: 4px; padding: 6px 12px; }
            QPushButton#DangerButton:hover { background-color: #c82333; }
            QPushButton#InfoButton { background-color: #17a2b8; color: white; font-weight: bold; border-radius: 4px; padding: 6px 12px; }
            QPushButton#InfoButton:hover { background-color: #138496; }
            QPushButton#SecondaryButton { background-color: #6c757d; color: white; font-weight: bold; border-radius: 4px; padding: 6px 12px; }
            QPushButton#SecondaryButton:hover { background-color: #5a6268; }
            QTableWidget { border: none; gridline-color: transparent; }
        """)

        dashboard_tab, view_tab = QWidget(), QWidget()
        self.view_details_tab, self.entry_tab = QWidget(), QWidget()
        self.deleted_tab = QWidget()

        self.tab_widget.addTab(dashboard_tab, "Dashboard")
        self.tab_widget.addTab(view_tab, "All Outgoing Forms")
        self.tab_widget.addTab(self.view_details_tab, "View Form Details")
        self.tab_widget.addTab(self.entry_tab, "Form Entry")
        self.tab_widget.addTab(self.deleted_tab, "Deleted Records")

        self._setup_dashboard_tab(dashboard_tab)
        self._setup_view_tab(view_tab)
        self._setup_view_details_tab(self.view_details_tab)
        self._setup_entry_tab(self.entry_tab)
        self._setup_deleted_tab(self.deleted_tab)

        self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.view_details_tab), False)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

    def _setup_deleted_tab(self, tab):
        layout = QVBoxLayout(tab)
        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("Search Deleted:"))
        self.deleted_search_edit = UpperCaseLineEdit(placeholderText="Filter deleted records...")
        top_layout.addWidget(self.deleted_search_edit, 1)
        self.restore_btn = QPushButton("Restore Selected")
        self.restore_btn.setObjectName("PrimaryButton")
        top_layout.addWidget(self.restore_btn)
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
        self.deleted_records_table.customContextMenuRequested.connect(self._show_deleted_table_context_menu)
        self.deleted_records_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.deleted_records_table)

        self.deleted_search_edit.textChanged.connect(self._load_deleted_records)
        self.restore_btn.clicked.connect(self._restore_record)
        self.deleted_records_table.itemSelectionChanged.connect(self._on_deleted_record_selection_changed)
        self._on_deleted_record_selection_changed()

    def _create_kpi_card(self, value_text, label_text):
        card = QWidget()
        card.setObjectName("kpi_card")
        card.setStyleSheet("#kpi_card { background-color: #ffffff; border: 1px solid #e0e5eb; border-radius: 8px; }")
        layout = QVBoxLayout(card)
        value_label = QLabel(value_text)
        value_label.setStyleSheet("font-size: 24pt; font-weight: bold; color: #4D7BFF;")
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label = QLabel(label_text)
        label.setStyleSheet("font-size: 10pt; color: #6c757d;")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(value_label)
        layout.addWidget(label)
        return card, value_label

    def _setup_dashboard_tab(self, tab):
        main_layout = QGridLayout(tab)
        main_layout.setSpacing(20)
        (self.kpi_forms_card, self.kpi_forms_value) = self._create_kpi_card("0", "Forms Created Today")
        (self.kpi_qty_card, self.kpi_qty_value) = self._create_kpi_card("0.00", "Total KG Processed Today")
        (self.kpi_products_card, self.kpi_products_value) = self._create_kpi_card("0", "Unique Products Today")
        (self.kpi_items_card, self.kpi_items_value) = self._create_kpi_card("0", "Items Processed Today")
        main_layout.addWidget(self.kpi_forms_card, 0, 0)
        main_layout.addWidget(self.kpi_qty_card, 0, 1)
        main_layout.addWidget(self.kpi_products_card, 0, 2)
        main_layout.addWidget(self.kpi_items_card, 0, 3)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter, 1, 0, 1, 4)
        recent_group = QGroupBox("Recent Outgoing Forms")
        recent_layout = QVBoxLayout(recent_group)
        self.dashboard_recent_table = QTableWidget()
        self.dashboard_recent_table.setShowGrid(False)
        self.dashboard_recent_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.dashboard_recent_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.dashboard_recent_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.dashboard_recent_table.verticalHeader().setVisible(False)
        self.dashboard_recent_table.horizontalHeader().setHighlightSections(False)
        self.dashboard_recent_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        recent_layout.addWidget(self.dashboard_recent_table)
        splitter.addWidget(recent_group)
        top_products_group = QGroupBox("Top 5 Products by Quantity (All Time)")
        chart_layout = QVBoxLayout(top_products_group)
        self.product_chart_view = QChartView()
        self.product_chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.product_chart = QChart()
        self.product_pie_series = QPieSeries()
        self.product_pie_series.setHoleSize(0.35)
        self.product_pie_series.hovered.connect(self._handle_pie_slice_hover)
        self.product_chart.addSeries(self.product_pie_series)
        self.product_chart.setTitle("Top 5 Products by Total Quantity")
        self.product_chart.setAnimationOptions(QChart.AnimationOption.SeriesAnimations)
        self.product_chart.legend().setVisible(True)
        self.product_chart.legend().setAlignment(Qt.AlignmentFlag.AlignRight)
        self.product_chart_view.setChart(self.product_chart)
        chart_layout.addWidget(self.product_chart_view)
        splitter.addWidget(top_products_group)
        splitter.setSizes([450, 550])

    def _setup_view_tab(self, tab):
        layout = QVBoxLayout(tab)
        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("Search:"))
        self.search_edit = UpperCaseLineEdit(placeholderText="Filter by Prod'n ID, Ref#, Activity...")
        top_layout.addWidget(self.search_edit, 1)
        self.update_btn = QPushButton("Load Selected for Update")
        self.update_btn.setObjectName("InfoButton")
        self.delete_btn = QPushButton("Delete Selected")
        self.delete_btn.setObjectName("DangerButton")

        # --- NEW: Refresh button ---
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("SecondaryButton")
        if fa:
            self.refresh_btn.setIcon(fa.icon('fa5s.sync-alt', color='white'))

        top_layout.addWidget(self.refresh_btn)
        top_layout.addWidget(self.update_btn)
        top_layout.addWidget(self.delete_btn)
        layout.addLayout(top_layout)

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
        self.prev_btn, self.next_btn = QPushButton("<< Previous"), QPushButton("Next >>")
        self.page_label = QLabel("Page 1 of 1")
        pagination_layout.addStretch();
        pagination_layout.addWidget(self.prev_btn)
        pagination_layout.addWidget(self.page_label);
        pagination_layout.addWidget(self.next_btn)
        pagination_layout.addStretch()
        layout.addLayout(pagination_layout)

        self.refresh_btn.clicked.connect(self._load_all_records)  # Connect refresh button
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
        primary_group = QGroupBox("Form Details")
        primary_layout = QGridLayout(primary_group)
        self.production_form_id_combo = QComboBox();
        self.production_form_id_combo.setEditable(True)
        self.fetch_details_btn = QPushButton("Fetch Details");
        self.fetch_details_btn.setObjectName("InfoButton")
        self.ref_no_edit = UpperCaseLineEdit()
        self.date_out_edit = QDateEdit(calendarPopup=True, displayFormat="yyyy-MM-dd")
        self.activity_edit = UpperCaseLineEdit()
        self.released_by_combo = QComboBox(editable=True)
        prod_id_layout = QHBoxLayout();
        prod_id_layout.addWidget(self.production_form_id_combo);
        prod_id_layout.addWidget(self.fetch_details_btn)

        self.manage_releasers_btn = QPushButton("Manage...")
        released_by_layout = QHBoxLayout()
        released_by_layout.setContentsMargins(0, 0, 0, 0)
        released_by_layout.addWidget(self.released_by_combo, 1)
        released_by_layout.addWidget(self.manage_releasers_btn)

        primary_layout.addWidget(QLabel("Prod'n Form ID#/Series#:"), 0, 0)
        primary_layout.addLayout(prod_id_layout, 0, 1)
        primary_layout.addWidget(QLabel("Ref#:"), 0, 2);
        primary_layout.addWidget(self.ref_no_edit, 0, 3)
        primary_layout.addWidget(QLabel("Date Out:"), 1, 0);
        primary_layout.addWidget(self.date_out_edit, 1, 1)
        primary_layout.addWidget(QLabel("Activity:"), 2, 0);
        primary_layout.addWidget(self.activity_edit, 2, 1)
        primary_layout.addWidget(QLabel("Released By:"), 2, 2)
        primary_layout.addLayout(released_by_layout, 2, 3)
        main_layout.addWidget(primary_group)

        items_group = QGroupBox("Outgoing Items")
        items_layout = QVBoxLayout(items_group)
        self.entry_items_table = QTableWidget()
        self.entry_items_table.setFocusPolicy(Qt.FocusPolicy.NoFocus);
        self.entry_items_table.setShowGrid(False)
        self.entry_items_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.entry_items_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.entry_items_table.setColumnCount(len(self.ITEM_TABLE_HEADERS))
        self.entry_items_table.setHorizontalHeaderLabels(self.ITEM_TABLE_HEADERS)
        self.entry_items_table.verticalHeader().setVisible(False)
        self.entry_items_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        items_layout.addWidget(self.entry_items_table)
        item_buttons_layout = QHBoxLayout()
        self.add_item_btn = QPushButton("Add Item");
        self.add_item_btn.setObjectName("PrimaryButton")
        self.edit_item_btn = QPushButton("Edit Selected");
        self.edit_item_btn.setObjectName("InfoButton")
        self.remove_item_btn = QPushButton("Remove Selected");
        self.remove_item_btn.setObjectName("DangerButton")
        item_buttons_layout.addStretch();
        item_buttons_layout.addWidget(self.add_item_btn)
        item_buttons_layout.addWidget(self.edit_item_btn);
        item_buttons_layout.addWidget(self.remove_item_btn)
        items_layout.addLayout(item_buttons_layout)
        main_layout.addWidget(items_group, 1)
        button_layout = QHBoxLayout()
        self.save_btn = QPushButton("Save Form");
        self.save_btn.setObjectName("PrimaryButton")
        self.clear_btn = QPushButton("New");
        self.clear_btn.setObjectName("SecondaryButton")
        self.cancel_update_btn = QPushButton("Cancel Update");
        self.cancel_update_btn.setObjectName("DangerButton")
        button_layout.addStretch();
        button_layout.addWidget(self.cancel_update_btn)
        button_layout.addWidget(self.clear_btn);
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

    def _on_tab_changed(self, index):
        tab_text = self.tab_widget.tabText(index)
        if tab_text == "Dashboard":
            self._update_dashboard_data()
        elif tab_text == "All Outgoing Forms":
            self._load_all_records()  # Auto-refresh on tab switch
        elif tab_text == "Deleted Records":
            self._load_deleted_records()
        elif tab_text == "Form Entry" and not self.current_editing_primary_id:
            self._load_combobox_data()
        elif tab_text == "View Form Details":
            if self.records_table.selectedItems():
                self._show_selected_record_in_view_tab()
            elif self.deleted_records_table.selectedItems():
                self._show_selected_deleted_record_in_view_tab()

    def _clear_form(self):
        self.current_editing_primary_id = None;
        self.cancel_update_btn.hide();
        self.save_btn.setText("Save Form")
        self.production_form_id_combo.setCurrentIndex(-1);
        self.ref_no_edit.clear();
        self.activity_edit.clear()
        self.released_by_combo.setCurrentIndex(-1);
        self.date_out_edit.setDate(QDate.currentDate())
        self.entry_items_table.setRowCount(0);
        self.production_form_id_combo.setFocus()
        self._load_combobox_data()

    def _show_add_item_dialog(self):
        dialog_data = {'prod_id': self.production_form_id_combo.currentText().strip()}
        dialog = AddItemDialog(self, db_engine=self.engine, data=dialog_data)
        if dialog.exec(): self._add_item_to_table(dialog.get_data())

    def _show_edit_item_dialog(self):
        selected_row = self.entry_items_table.currentRow()
        if selected_row < 0:
            QMessageBox.warning(self, "Selection Error", "Please select an item to edit.");
            return
        dialog_data = {
            "prod_id": self.entry_items_table.item(selected_row, 0).text(),
            "product_code": self.entry_items_table.item(selected_row, 1).text(),
            "lot_used": self.entry_items_table.item(selected_row, 2).text(),
            "quantity_required_kg": self.entry_items_table.item(selected_row, 3).text(),
            "new_lot_details": self.entry_items_table.item(selected_row, 4).text(),
            "status": self.entry_items_table.item(selected_row, 5).text(),
            "box_number": self.entry_items_table.item(selected_row, 6).text(),
            "remaining_quantity": self.entry_items_table.item(selected_row, 7).text(),
            "quantity_produced": self.entry_items_table.item(selected_row, 8).text()
        }
        dialog = AddItemDialog(self, db_engine=self.engine, data=dialog_data)
        if dialog.exec(): self._update_table_row(selected_row, dialog.get_data())

    def _remove_selected_item(self):
        selected_row = self.entry_items_table.currentRow()
        if selected_row >= 0:
            self.entry_items_table.removeRow(selected_row)
        else:
            QMessageBox.warning(self, "Selection Error", "Please select an item to remove.")

    def _add_item_to_table(self, data):
        row_pos = self.entry_items_table.rowCount()
        self.entry_items_table.insertRow(row_pos)
        self._update_table_row(row_pos, data)

    def _update_table_row(self, row, data):
        keys = ["prod_id", "product_code", "lot_used", "quantity_required_kg", "new_lot_details", "status",
                "box_number", "remaining_quantity", "quantity_produced"]
        for col, key in enumerate(keys):
            value = data.get(key)
            item = QTableWidgetItem(f"{value:.2f}" if isinstance(value, (float, Decimal)) else str(value or ''))
            if isinstance(value, (float, Decimal)): item.setTextAlignment(
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
            if not results: QMessageBox.information(self, "Not Found",
                                                    f"No production details found for ID# {form_id}."); return
            self.entry_items_table.setRowCount(0)
            for rec in results:
                self._add_item_to_table({"prod_id": rec.get('prod_id'), "product_code": rec.get('prod_code'),
                                         "lot_used": rec.get('lot_number'),
                                         "quantity_required_kg": rec.get('qty_prod')})
            QMessageBox.information(self, "Success", f"Fetched {len(results)} items for ID# {form_id}.")
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Could not fetch details: {e}")

    def _refresh_all_data_views(self):
        """Reloads data for all relevant views (main table, deleted table, dashboard)."""
        self._load_all_records()
        self._load_deleted_records()
        self._update_dashboard_data()

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
            items_data.append({
                "prod_id": self.entry_items_table.item(row, 0).text(),
                "product_code": self.entry_items_table.item(row, 1).text(),
                "lot_used": self.entry_items_table.item(row, 2).text(),
                "quantity_required_kg": float(self.entry_items_table.item(row, 3).text() or 0.0),
                "new_lot_details": self.entry_items_table.item(row, 4).text(),
                "status": self.entry_items_table.item(row, 5).text(),
                "box_number": self.entry_items_table.item(row, 6).text(),
                "remaining_quantity": float(self.entry_items_table.item(row, 7).text() or 0.0),
                "quantity_produced": self.entry_items_table.item(row, 8).text()
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
                        "INSERT INTO outgoing_records_items (primary_id, prod_id, product_code, lot_used, quantity_required_kg, new_lot_details, status, box_number, remaining_quantity, quantity_produced) VALUES (:primary_id, :prod_id, :product_code, :lot_used, :quantity_required_kg, :new_lot_details, :status, :box_number, :remaining_quantity, :quantity_produced)")
                    conn.execute(items_sql, items_data)
                self.log_audit_trail(log_action,
                                     f"{action.capitalize()} form with Prod'n ID: {primary_data['production_form_id']}")
                QMessageBox.information(self, "Success", f"Form has been {action}.")

                self._clear_form()
                self._refresh_all_data_views()

        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"An error occurred while saving: {e}")

    def _load_record_for_update(self):
        row = self.records_table.currentRow();
        if row < 0: return
        primary_id = int(self.records_table.item(row, 0).text())
        try:
            with self.engine.connect() as conn:
                primary_rec = conn.execute(text("SELECT * FROM outgoing_records_primary WHERE id = :id"),
                                           {"id": primary_id}).mappings().first()
                item_recs = conn.execute(
                    text("SELECT * FROM outgoing_records_items WHERE primary_id = :id ORDER BY id"),
                    {"id": primary_id}).mappings().all()
            self._clear_form();
            self.current_editing_primary_id = primary_id
            self.production_form_id_combo.setCurrentText(primary_rec['production_form_id'])
            self.ref_no_edit.setText(primary_rec.get('ref_no', ''))
            self.date_out_edit.setDate(QDate(primary_rec['date_out']))
            self.activity_edit.setText(primary_rec.get('activity', ''))
            self.released_by_combo.setCurrentText(primary_rec.get('released_by', ''))
            self.entry_items_table.setRowCount(0)
            for item in item_recs: self._add_item_to_table(item)
            self.save_btn.setText("Update Form");
            self.cancel_update_btn.show();
            self.tab_widget.setCurrentWidget(self.entry_tab)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load record for update: {e}");
            self._clear_form()

    def _manage_releasers_list(self):
        dialog = ManageListDialog(self, self.engine, "outgoing_releasers", "name", "Manage Releasers")
        dialog.exec()
        self._load_combobox_data()

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
            self.released_by_combo.blockSignals(True);
            self.released_by_combo.clear()
            self.released_by_combo.addItems([""] + releasers);
            self.released_by_combo.setCurrentText(current_releaser)
            self.released_by_combo.blockSignals(False)

            current_prod_id = self.production_form_id_combo.currentText()
            self.production_form_id_combo.blockSignals(True);
            self.production_form_id_combo.clear()
            self.production_form_id_combo.addItems([""] + prod_ids);
            self.production_form_id_combo.setCurrentText(current_prod_id)
            self.production_form_id_combo.blockSignals(False)
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load dropdown data: {e}")

    def _on_search_text_changed(self, text):
        self.current_page = 1; self._load_all_records()

    def _go_to_prev_page(self):
        if self.current_page > 1: self.current_page -= 1; self._load_all_records()

    def _go_to_next_page(self):
        if self.current_page < self.total_pages: self.current_page += 1; self._load_all_records()

    def _update_pagination_controls(self):
        self.total_pages = (self.total_records + self.records_per_page - 1) // self.records_per_page or 1
        self.page_label.setText(f"Page {self.current_page} of {self.total_pages}")
        self.prev_btn.setEnabled(self.current_page > 1);
        self.next_btn.setEnabled(self.current_page < self.total_pages)

    def _on_record_selection_changed(self):
        is_selected = bool(self.records_table.selectionModel().selectedRows())
        self.update_btn.setEnabled(is_selected);
        self.delete_btn.setEnabled(is_selected)
        self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.view_details_tab), is_selected)
        if not is_selected and self.tab_widget.currentIndex() == self.tab_widget.indexOf(self.view_details_tab):
            self.tab_widget.setCurrentIndex(1)

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
            self._update_pagination_controls();
            self._on_record_selection_changed()
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Failed to load records: {e}")

    def _populate_records_table(self, table, headers, data):
        table.setRowCount(0);
        table.setColumnCount(len(headers));
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

    def _show_records_table_context_menu(self, pos):
        if not self.records_table.selectedItems(): return
        menu = QMenu()
        view_action = menu.addAction("View Details");
        edit_action = menu.addAction("Load for Update")
        delete_action = menu.addAction("Delete Record")
        action = menu.exec(self.records_table.mapToGlobal(pos))
        if action == view_action:
            self._show_selected_record_in_view_tab()
        elif action == edit_action:
            self._load_record_for_update()
        elif action == delete_action:
            self._delete_record()

    def _show_deleted_table_context_menu(self, pos):
        if not self.deleted_records_table.selectedItems(): return
        menu = QMenu();
        restore_action = menu.addAction("Restore Record");
        view_action = menu.addAction("View Details")
        action = menu.exec(self.deleted_records_table.mapToGlobal(pos))
        if action == restore_action:
            self._restore_record()
        elif action == view_action:
            self._show_selected_deleted_record_in_view_tab()

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

            edited_on = primary.get('edited_on');
            last_edited_text = "N/A"
            if edited_on: last_edited_text = f"{primary.get('edited_by', 'Unknown')} on {edited_on.strftime('%Y-%m-%d %H:%M')}"
            details_map = {"Prod'n Form ID#:": primary.get('production_form_id', ''),
                           "Ref#:": primary.get('ref_no', ''), "Date Out:": str(primary.get('date_out', '')),
                           "Activity:": primary.get('activity', ''), "Released By:": primary.get('released_by', ''),
                           "Last Edited:": last_edited_text}
            for label, value in details_map.items(): self.view_details_layout.addRow(QLabel(f"<b>{label}</b>"),
                                                                                     QLabel(str(value or '')))

            self.view_items_table.setRowCount(0);
            self.view_items_table.setColumnCount(len(self.ITEM_TABLE_HEADERS));
            self.view_items_table.setHorizontalHeaderLabels(self.ITEM_TABLE_HEADERS)
            if items:
                self.view_items_table.setRowCount(len(items))
                item_keys = ['prod_id', 'product_code', 'lot_used', 'quantity_required_kg', 'new_lot_details', 'status',
                             'box_number', 'remaining_quantity', 'quantity_produced']
                for row_idx, record in enumerate(items):
                    for col_idx, key in enumerate(item_keys):
                        value = record.get(key, '')
                        item = QTableWidgetItem(
                            f"{value:.2f}" if isinstance(value, (float, Decimal)) else str(value or ''))
                        if isinstance(value, (float, Decimal)): item.setTextAlignment(
                            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                        self.view_items_table.setItem(row_idx, col_idx, item)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load details:\n{e}\n\n{traceback.format_exc()}")

    def _handle_pie_slice_hover(self, slice_item: QPieSlice, state: bool):
        if state:
            slice_item.setExploded(True);
            slice_item.setLabel(f"{slice_item.label()} ({slice_item.percentage():.1%})")
        else:
            slice_item.setExploded(False);
            slice_item.setLabel(slice_item.label().split(" (")[0])

    def _update_dashboard_data(self):
        try:
            with self.engine.connect() as conn:
                base = "FROM outgoing_records_primary p JOIN outgoing_records_items i ON p.id = i.primary_id WHERE p.is_deleted IS NOT TRUE"
                today_cond = "AND p.date_out = CURRENT_DATE"
                forms_today = conn.execute(text(
                    f"SELECT COUNT(DISTINCT p.id) FROM outgoing_records_primary p WHERE p.is_deleted IS NOT TRUE AND p.date_out = CURRENT_DATE")).scalar_one_or_none() or 0
                qty_today = conn.execute(
                    text(f"SELECT SUM(i.quantity_required_kg) {base} {today_cond}")).scalar_one_or_none() or Decimal(
                    '0.00')
                products_today = conn.execute(
                    text(f"SELECT COUNT(DISTINCT i.product_code) {base} {today_cond}")).scalar_one_or_none() or 0
                items_today = conn.execute(text(f"SELECT COUNT(i.id) {base} {today_cond}")).scalar_one_or_none() or 0
                recent_forms = conn.execute(text(
                    "SELECT production_form_id, ref_no, date_out FROM outgoing_records_primary WHERE is_deleted IS NOT TRUE ORDER BY id DESC LIMIT 5")).mappings().all()
                top_products = conn.execute(text(
                    "SELECT product_code, SUM(quantity_required_kg) as total_quantity FROM outgoing_records_items WHERE product_code IS NOT NULL AND product_code != '' GROUP BY product_code ORDER BY total_quantity DESC LIMIT 5")).mappings().all()

            self.kpi_forms_value.setText(str(forms_today));
            self.kpi_qty_value.setText(f"{float(qty_today):.2f}")
            self.kpi_products_value.setText(str(products_today));
            self.kpi_items_value.setText(str(items_today))

            self.dashboard_recent_table.setRowCount(len(recent_forms));
            self.dashboard_recent_table.setColumnCount(3)
            self.dashboard_recent_table.setHorizontalHeaderLabels(["Prod'n Form ID#", "Ref #", "Date Out"])
            for row, record in enumerate(recent_forms):
                self.dashboard_recent_table.setItem(row, 0, QTableWidgetItem(record['production_form_id']))
                self.dashboard_recent_table.setItem(row, 1, QTableWidgetItem(record['ref_no']))
                self.dashboard_recent_table.setItem(row, 2,
                                                    QTableWidgetItem(QDate(record['date_out']).toString("yyyy-MM-dd")))

            self.product_pie_series.clear()
            self.product_chart.setTitle(f"Top 5 Products by Quantity{' (No Data)' if not top_products else ''}")
            if top_products:
                for prod in top_products:
                    slice_item = self.product_pie_series.append(
                        f"{prod['product_code']}\n{float(prod.get('total_quantity') or 0.0):.2f} kg",
                        float(prod.get('total_quantity') or 0.0))
                    slice_item.setLabelVisible(True)
        except Exception as e:
            QMessageBox.critical(self, "Dashboard Error", f"Could not load dashboard data: {e}")

    def _delete_record(self):
        row = self.records_table.currentRow()
        if row < 0: return
        primary_id = int(self.records_table.item(row, 0).text())
        prod_id = self.records_table.item(row, 1).text()

        password, ok = QInputDialog.getText(self, "Admin Authentication", "Enter Admin Password:",
                                            QLineEdit.EchoMode.Password)
        if not ok: return
        if password != ADMIN_PASSWORD:
            QMessageBox.warning(self, "Authentication Failed", "Incorrect password. Deletion cancelled.");
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
                self.log_audit_trail("DELETE_OUTGOING_FORM", f"Soft-deleted form: {prod_id}")
                QMessageBox.information(self, "Success", f"Form {prod_id} has been moved to Deleted Records.")
                self._refresh_all_data_views()
            except Exception as e:
                QMessageBox.critical(self, "Database Error", f"Failed to delete record: {e}")

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
                self.log_audit_trail("RESTORE_OUTGOING_FORM", f"Restored form: {prod_id}")
                QMessageBox.information(self, "Success", f"Form {prod_id} has been restored.")
                self._refresh_all_data_views()
            except Exception as e:
                QMessageBox.critical(self, "Database Error", f"Failed to restore record: {e}")

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