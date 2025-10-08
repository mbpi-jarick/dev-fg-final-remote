# fg_endorsement.py
# FINAL VERSION - Rebuilt with a modern UI, dashboard, and features consistent with product_delivery.py.
# UX/UI POLISH - Fixed table selection behavior, restored context menus, and implemented auto-sizing table headers across all tabs.
# FIX - Corrected table click/selection events, fixed error on loading a record, and now auto-switches to entry tab on edit.
# ENHANCED - Replaced dashboard bar chart with an interactive pie chart.
# NEW FEATURE - When using a lot range, user can now assign excess quantity to the last lot number in the range, displayed in the excess preview table.
# SECURITY & RECOVERY - Implemented password protection for deletion and added a "Deleted Records" tab with a restore function and right-click context menu.

import sys
import re
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

# --- PyQt6 Imports ---
from PyQt6.QtCore import Qt, QDate, QRegularExpression
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTabWidget, QFormLayout, QLineEdit,
                             QComboBox, QDateEdit, QPushButton, QTableWidget, QTableWidgetItem,
                             QAbstractItemView, QHeaderView, QMessageBox, QHBoxLayout, QLabel,
                             QCheckBox, QDialog, QListWidget, QDialogButtonBox, QListWidgetItem,
                             QSplitter, QGridLayout, QGroupBox, QMenu, QInputDialog)
from PyQt6.QtGui import QDoubleValidator, QRegularExpressionValidator, QPainter, QColor, QFont
from PyQt6.QtCharts import QChartView, QChart, QPieSeries, QPieSlice

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


class FGEndorsementPage(QWidget):
    def __init__(self, db_engine, username, log_audit_trail_func):
        super().__init__()
        self.engine, self.username, self.log_audit_trail = db_engine, username, log_audit_trail_func
        self.current_editing_ref, self.preview_data = None, None
        self.current_page, self.records_per_page = 1, 200
        self.total_records, self.total_pages = 0, 1
        self.init_ui()
        self._load_all_endorsements()
        self._update_dashboard_data()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        self.setStyleSheet("""
            QPushButton#PrimaryButton {
                background-color: #28a745; color: white; font-weight: bold; border-radius: 4px; padding: 6px 12px;
            }
            QPushButton#PrimaryButton:hover { background-color: #218838; }
            QPushButton#DangerButton {
                background-color: #dc3545; color: white; font-weight: bold; border-radius: 4px; padding: 6px 12px;
            }
            QPushButton#DangerButton:hover { background-color: #c82333; }
            QPushButton#InfoButton {
                background-color: #17a2b8; color: white; font-weight: bold; border-radius: 4px; padding: 6px 12px;
            }
            QPushButton#InfoButton:hover { background-color: #138496; }
            QPushButton#SecondaryButton {
                background-color: #6c757d; color: white; font-weight: bold; border-radius: 4px; padding: 6px 12px;
            }
            QPushButton#SecondaryButton:hover { background-color: #5a6268; }
        """)

        dashboard_tab = QWidget()
        view_tab = QWidget()
        self.view_details_tab = QWidget()
        self.entry_tab = QWidget()
        self.deleted_tab = QWidget()

        self.tab_widget.addTab(dashboard_tab, "Dashboard")
        self.tab_widget.addTab(view_tab, "All Endorsement Records")
        self.tab_widget.addTab(self.view_details_tab, "View Endorsement Details")
        self.tab_widget.addTab(self.entry_tab, "Endorsement Entry")
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
        # --- APPLIED AUTO-SIZING ---
        self.deleted_records_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.deleted_records_table.customContextMenuRequested.connect(self._show_deleted_table_context_menu)
        layout.addWidget(self.deleted_records_table)

        self.deleted_search_edit.textChanged.connect(self._load_deleted_endorsements)
        self.restore_btn.clicked.connect(self._restore_record)
        self.deleted_records_table.itemSelectionChanged.connect(self._on_deleted_record_selection_changed)
        self._on_deleted_record_selection_changed()

    def _create_kpi_card(self, value_text, label_text):
        card = QWidget()
        card.setObjectName("kpi_card")
        card.setStyleSheet("#kpi_card { background-color: #ffffff; border: 1px solid #e0e5eb; border-radius: 8px; }")
        layout = QVBoxLayout(card)
        value_label = QLabel(value_text)
        value_label.setObjectName("kpi_value")
        value_label.setStyleSheet("font-size: 24pt; font-weight: bold; color: #4D7BFF;")
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label = QLabel(label_text)
        label.setObjectName("kpi_label")
        label.setStyleSheet("font-size: 10pt; color: #6c757d;")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(value_label)
        layout.addWidget(label)
        return card, value_label

    def _setup_dashboard_tab(self, tab):
        main_layout = QGridLayout(tab)
        main_layout.setSpacing(20)
        (self.kpi_endorsed_card, self.kpi_endorsed_value) = self._create_kpi_card("0", "Endorsements Today")
        (self.kpi_qty_card, self.kpi_qty_value) = self._create_kpi_card("0.00", "Total KG Endorsed Today")
        (self.kpi_products_card, self.kpi_products_value) = self._create_kpi_card("0", "Unique Products Today")
        (self.kpi_lots_card, self.kpi_lots_value) = self._create_kpi_card("0", "Lots Endorsed Today")
        main_layout.addWidget(self.kpi_endorsed_card, 0, 0)
        main_layout.addWidget(self.kpi_qty_card, 0, 1)
        main_layout.addWidget(self.kpi_products_card, 0, 2)
        main_layout.addWidget(self.kpi_lots_card, 0, 3)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter, 1, 0, 1, 4)
        recent_group = QGroupBox("Recent Endorsements")
        recent_layout = QVBoxLayout(recent_group)
        self.dashboard_recent_table = QTableWidget()
        self.dashboard_recent_table.setShowGrid(False)
        self.dashboard_recent_table.setStyleSheet("QTableWidget { border: none; }")
        self.dashboard_recent_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.dashboard_recent_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.dashboard_recent_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.dashboard_recent_table.verticalHeader().setVisible(False)
        self.dashboard_recent_table.horizontalHeader().setHighlightSections(False)
        # --- APPLIED AUTO-SIZING ---
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
        self.product_chart.setTitle("Top 5 Products by Total Endorsed Quantity")
        self.product_chart.setAnimationOptions(QChart.AnimationOption.SeriesAnimations)
        self.product_chart.legend().setVisible(True)
        self.product_chart.legend().setAlignment(Qt.AlignmentFlag.AlignRight)
        self.product_chart_view.setChart(self.product_chart)
        chart_layout.addWidget(self.product_chart_view)
        splitter.addWidget(top_products_group)
        splitter.setSizes([450, 550])

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
        self.view_breakdown_table.setShowGrid(False)
        self.view_breakdown_table.setStyleSheet("QTableWidget { border: none; }")
        self.view_breakdown_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.view_breakdown_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.view_breakdown_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.view_breakdown_table.verticalHeader().setVisible(False)
        self.view_breakdown_table.horizontalHeader().setHighlightSections(False)
        # --- APPLIED AUTO-SIZING ---
        self.view_breakdown_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        breakdown_layout.addWidget(self.view_breakdown_table)
        self.view_breakdown_total_label = QLabel("<b>Total: 0.00 kg</b>")
        self.view_breakdown_total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        breakdown_layout.addWidget(self.view_breakdown_total_label)
        tables_splitter.addWidget(breakdown_group)
        excess_group = QGroupBox("Excess Quantity")
        excess_layout = QVBoxLayout(excess_group)
        self.view_excess_table = QTableWidget()
        self.view_excess_table.setShowGrid(False)
        self.view_excess_table.setStyleSheet("QTableWidget { border: none; }")
        self.view_excess_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.view_excess_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.view_excess_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.view_excess_table.verticalHeader().setVisible(False)
        self.view_excess_table.horizontalHeader().setHighlightSections(False)
        # --- APPLIED AUTO-SIZING ---
        self.view_excess_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        excess_layout.addWidget(self.view_excess_table)
        self.view_excess_total_label = QLabel("<b>Total: 0.00 kg</b>")
        self.view_excess_total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        excess_layout.addWidget(self.view_excess_total_label)
        tables_splitter.addWidget(excess_group)
        main_layout.addWidget(tables_splitter, 1)

    def _setup_entry_tab(self, tab):
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        tab_layout = QHBoxLayout(tab)
        tab_layout.addWidget(main_splitter)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 5, 0)
        main_splitter.addWidget(left_widget)

        primary_group = QGroupBox("Primary Information")
        primary_layout = QGridLayout(primary_group)
        self.sys_ref_no_edit = QLineEdit(readOnly=True, placeholderText="Auto-generated")
        self.form_ref_no_edit = UpperCaseLineEdit()
        self.form_ref_no_edit.setValidator(QRegularExpressionValidator(QRegularExpression("[A-Z0-9\\-]+")))
        self.date_endorsed_edit = QDateEdit(calendarPopup=True, displayFormat="yyyy-MM-dd")
        self.category_combo = QComboBox()
        self.category_combo.addItems(["MB", "DC"])
        primary_layout.addWidget(QLabel("System Ref:"), 0, 0);
        primary_layout.addWidget(self.sys_ref_no_edit, 0, 1)
        primary_layout.addWidget(QLabel("Form Ref:"), 0, 2);
        primary_layout.addWidget(self.form_ref_no_edit, 0, 3)
        primary_layout.addWidget(QLabel("Date Endorsed:"), 1, 0);
        primary_layout.addWidget(self.date_endorsed_edit, 1, 1)
        primary_layout.addWidget(QLabel("Category:"), 1, 2);
        primary_layout.addWidget(self.category_combo, 1, 3)
        left_layout.addWidget(primary_group)

        product_group = QGroupBox("Product & Lot Details")
        product_layout = QGridLayout(product_group)
        self.product_code_combo = QComboBox(editable=True, insertPolicy=QComboBox.InsertPolicy.NoInsert)
        self.product_code_combo.lineEdit().setPlaceholderText("TYPE OR SELECT PRODUCT CODE")
        self.lot_number_edit = UpperCaseLineEdit()
        self.is_lot_range_check = QCheckBox("Calculate lots from a range")
        set_combo_box_uppercase(self.product_code_combo)
        product_layout.addWidget(QLabel("Product Code:"), 0, 0);
        product_layout.addWidget(self.product_code_combo, 0, 1)
        product_layout.addWidget(QLabel("Lot Number/Range:"), 1, 0);
        product_layout.addWidget(self.lot_number_edit, 1, 1)
        product_layout.addWidget(self.is_lot_range_check, 2, 1)
        left_layout.addWidget(product_group)

        quantity_group = QGroupBox("Quantity Details")
        quantity_layout = QGridLayout(quantity_group)
        self.quantity_edit = FloatLineEdit()
        self.weight_per_lot_edit = FloatLineEdit()
        self.calculated_lots_label = QLabel("Calculated: 0 lot(s) with 0.00 kg excess")
        self.calculated_lots_label.setStyleSheet("font-style: italic; color: #555;")
        quantity_layout.addWidget(QLabel("Total Qty (kg):"), 0, 0);
        quantity_layout.addWidget(self.quantity_edit, 0, 1)
        quantity_layout.addWidget(QLabel("Weight/Lot (kg):"), 0, 2);
        quantity_layout.addWidget(self.weight_per_lot_edit, 0, 3)
        quantity_layout.addWidget(self.calculated_lots_label, 1, 1, 1, 3)
        left_layout.addWidget(quantity_group)
        self.quantity_edit.textChanged.connect(self._update_calculated_lots_display)
        self.weight_per_lot_edit.textChanged.connect(self._update_calculated_lots_display)

        endorsement_group = QGroupBox("Default Endorsement Details (for all lots)")
        endorsement_layout = QGridLayout(endorsement_group)
        self.bag_no_combo = QComboBox(editable=True)
        self.bag_no_combo.addItems([str(i) for i in range(1, 21)])
        self.status_combo = QComboBox();
        self.status_combo.addItems(["Passed", "Failed"])
        self.endorsed_by_combo = QComboBox(editable=True)
        self.remarks_combo = QComboBox(editable=True)
        set_combo_box_uppercase(self.bag_no_combo);
        set_combo_box_uppercase(self.endorsed_by_combo);
        set_combo_box_uppercase(self.remarks_combo)
        self.manage_endorser_btn = QPushButton("Manage...");
        self.manage_remarks_btn = QPushButton("Manage...")
        self.location_combo = QComboBox()
        self.add_location_btn = QPushButton("Manage...");
        self.lock_location_check = QCheckBox("Lock")
        endorser_layout = QHBoxLayout();
        endorser_layout.setContentsMargins(0, 0, 0, 0);
        endorser_layout.addWidget(self.endorsed_by_combo, 1);
        endorser_layout.addWidget(self.manage_endorser_btn)
        remarks_layout = QHBoxLayout();
        remarks_layout.setContentsMargins(0, 0, 0, 0);
        remarks_layout.addWidget(self.remarks_combo, 1);
        remarks_layout.addWidget(self.manage_remarks_btn)
        location_layout = QHBoxLayout();
        location_layout.setContentsMargins(0, 0, 0, 0);
        location_layout.addWidget(self.location_combo, 1);
        location_layout.addWidget(self.add_location_btn);
        location_layout.addWidget(self.lock_location_check)
        endorsement_layout.addWidget(QLabel("Location:"), 0, 0);
        endorsement_layout.addLayout(location_layout, 0, 1, 1, 3)
        endorsement_layout.addWidget(QLabel("Status:"), 1, 0);
        endorsement_layout.addWidget(self.status_combo, 1, 1)
        endorsement_layout.addWidget(QLabel("Bag Number:"), 1, 2);
        endorsement_layout.addWidget(self.bag_no_combo, 1, 3)
        endorsement_layout.addWidget(QLabel("Endorsed By:"), 2, 0);
        endorsement_layout.addLayout(endorser_layout, 2, 1, 1, 3)
        endorsement_layout.addWidget(QLabel("Remarks:"), 3, 0);
        endorsement_layout.addLayout(remarks_layout, 3, 1, 1, 3)
        left_layout.addWidget(endorsement_group)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(5, 0, 0, 0)
        main_splitter.addWidget(right_widget)

        breakdown_group = QGroupBox("Lot Breakdown (Preview)")
        breakdown_layout = QVBoxLayout(breakdown_group)
        self.preview_breakdown_table = QTableWidget()
        self.preview_breakdown_table.setShowGrid(False);
        self.preview_breakdown_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.preview_breakdown_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.preview_breakdown_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.preview_breakdown_table.verticalHeader().setVisible(False);
        self.preview_breakdown_table.horizontalHeader().setHighlightSections(False)
        # --- APPLIED AUTO-SIZING ---
        self.preview_breakdown_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        breakdown_layout.addWidget(self.preview_breakdown_table)
        self.breakdown_total_label = QLabel("<b>Total: 0.00 kg</b>");
        self.breakdown_total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        breakdown_layout.addWidget(self.breakdown_total_label)

        excess_group = QGroupBox("Excess Quantity (Preview)")
        excess_layout = QVBoxLayout(excess_group)
        self.preview_excess_table = QTableWidget()
        self.preview_excess_table.setShowGrid(False);
        self.preview_excess_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.preview_excess_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.preview_excess_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.preview_excess_table.verticalHeader().setVisible(False);
        self.preview_excess_table.horizontalHeader().setHighlightSections(False)
        # --- APPLIED AUTO-SIZING ---
        self.preview_excess_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        excess_layout.addWidget(self.preview_excess_table)
        self.excess_total_label = QLabel("<b>Total: 0.00 kg</b>");
        self.excess_total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        excess_layout.addWidget(self.excess_total_label)

        right_splitter = QSplitter(Qt.Orientation.Vertical)
        right_splitter.addWidget(breakdown_group);
        right_splitter.addWidget(excess_group)
        right_layout.addWidget(right_splitter)

        main_splitter.setSizes([600, 500])

        button_layout = QHBoxLayout()
        self.preview_btn = QPushButton("Preview Breakdown");
        self.preview_btn.setObjectName("InfoButton")
        self.save_btn = QPushButton("Save Endorsement");
        self.save_btn.setObjectName("PrimaryButton")
        self.clear_btn = QPushButton("New");
        self.clear_btn.setObjectName("SecondaryButton")
        self.cancel_update_btn = QPushButton("Cancel Update");
        self.cancel_update_btn.setObjectName("DangerButton")
        button_layout.addStretch()
        button_layout.addWidget(self.cancel_update_btn);
        button_layout.addWidget(self.clear_btn)
        button_layout.addWidget(self.preview_btn);
        button_layout.addWidget(self.save_btn)
        left_layout.addLayout(button_layout)

        self.preview_btn.clicked.connect(self._preview_endorsement)
        self.save_btn.clicked.connect(self._save_endorsement)
        self.clear_btn.clicked.connect(self._clear_form)
        self.cancel_update_btn.clicked.connect(self._clear_form)
        self.manage_endorser_btn.clicked.connect(
            lambda: self._manage_list("endorsers", "name", "Manage Endorsers", self._load_endorsers))
        self.manage_remarks_btn.clicked.connect(
            lambda: self._manage_list("endorsement_remarks", "remark_text", "Manage Remarks", self._load_remarks))
        self.add_location_btn.clicked.connect(
            lambda: self._manage_list("warehouses", "name", "Manage Locations", self._load_locations))
        self.lock_location_check.stateChanged.connect(self._toggle_location_lock)
        self._clear_form()

    def _setup_view_tab(self, tab):
        layout = QVBoxLayout(tab)
        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("Search:"))
        self.search_edit = UpperCaseLineEdit(placeholderText="Filter by Ref No, Product Code, Lot No...")
        top_layout.addWidget(self.search_edit, 1)
        self.update_btn = QPushButton("Load Selected for Update");
        self.update_btn.setObjectName("InfoButton")
        self.delete_btn = QPushButton("Delete Selected");
        self.delete_btn.setObjectName("DangerButton")
        top_layout.addWidget(self.update_btn);
        top_layout.addWidget(self.delete_btn)
        layout.addLayout(top_layout)

        self.records_table = QTableWidget()
        self.records_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.records_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.records_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.records_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.records_table.setShowGrid(False);
        self.records_table.verticalHeader().setVisible(False)
        self.records_table.horizontalHeader().setHighlightSections(False)
        self.records_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        # --- APPLIED AUTO-SIZING ---
        self.records_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.records_table.customContextMenuRequested.connect(self._show_records_table_context_menu)
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
        self.records_table.itemSelectionChanged.connect(self._on_record_selection_changed)
        self.prev_btn.clicked.connect(self._go_to_prev_page)
        self.next_btn.clicked.connect(self._go_to_next_page)
        self._on_record_selection_changed()

    def _on_search_text_changed(self, text):
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
        is_selected = bool(self.records_table.selectionModel().selectedRows())
        self.update_btn.setEnabled(is_selected)
        self.delete_btn.setEnabled(is_selected)
        self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.view_details_tab), is_selected)
        if is_selected:
            self._show_selected_record_in_view_tab()
        elif self.tab_widget.currentIndex() == self.tab_widget.indexOf(self.view_details_tab):
            self.tab_widget.setCurrentIndex(1)

    def _on_deleted_record_selection_changed(self):
        is_selected = bool(self.deleted_records_table.selectionModel().selectedRows())
        self.restore_btn.setEnabled(is_selected)
        self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.view_details_tab), is_selected)

    def _show_records_table_context_menu(self, position):
        if not self.records_table.selectedItems(): return
        menu = QMenu()
        view_action = menu.addAction("View Details...")
        edit_action = menu.addAction("Edit Record")
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
        view_action = menu.addAction("View Details...")
        action = menu.exec(self.deleted_records_table.mapToGlobal(position))
        if action == restore_action:
            self._restore_record()
        elif action == view_action:
            self._show_selected_deleted_record_in_view_tab()

    def _toggle_location_lock(self):
        is_locked = self.lock_location_check.isChecked()
        self.location_combo.setEnabled(not is_locked)
        self.add_location_btn.setEnabled(not is_locked)

    def _update_calculated_lots_display(self):
        try:
            total_qty = Decimal(self.quantity_edit.text() or "0")
            weight_per_lot = Decimal(self.weight_per_lot_edit.text() or "0")
            if weight_per_lot > 0:
                num_lots = int(total_qty // weight_per_lot)
                excess = total_qty % weight_per_lot
                self.calculated_lots_label.setText(f"Calculated: {num_lots} lot(s) with {excess:.2f} kg excess")
            else:
                self.calculated_lots_label.setText("Weight/Lot must be > 0")
        except (InvalidOperation, ValueError):
            self.calculated_lots_label.setText("Invalid quantity input")

    def _on_tab_changed(self, index):
        tab_text = self.tab_widget.tabText(index)
        if tab_text == "Dashboard":
            self._update_dashboard_data()
        elif tab_text == "All Endorsement Records":
            self._load_all_endorsements()
        elif tab_text == "Deleted Records":
            self._load_deleted_endorsements()
        elif tab_text == "Endorsement Entry" and self.current_editing_ref is None:
            self._load_initial_data()
        elif tab_text == "View Endorsement Details":
            if self.records_table.selectionModel().selectedRows():
                self._show_selected_record_in_view_tab()
            elif self.deleted_records_table.selectionModel().selectedRows():
                self._show_selected_deleted_record_in_view_tab()

    def _clear_form(self):
        self.current_editing_ref, self.preview_data = None, None
        self.cancel_update_btn.hide()
        self.save_btn.setText("Save Endorsement")
        for w in [self.sys_ref_no_edit, self.form_ref_no_edit, self.lot_number_edit]: w.clear()
        self.quantity_edit.setText("0.00");
        self.weight_per_lot_edit.setText("0.00")
        if not self.lock_location_check.isChecked(): self.location_combo.setCurrentIndex(
            0 if self.location_combo.count() > 0 else -1)
        for c in [self.product_code_combo, self.endorsed_by_combo, self.remarks_combo]: c.setCurrentIndex(
            -1); c.clearEditText()
        for c in [self.category_combo, self.bag_no_combo, self.status_combo]: c.setCurrentIndex(0)
        self.date_endorsed_edit.setDate(QDate.currentDate())
        self.is_lot_range_check.setChecked(False)
        self._clear_form_previews()
        self.form_ref_no_edit.setFocus()
        self._update_calculated_lots_display()

    def _ask_excess_handling_method(self):
        msg_box = QMessageBox(self);
        msg_box.setWindowTitle("Excess Quantity Handling")
        msg_box.setText("An excess quantity was calculated for the lot range.\n\nHow should this excess be handled?")
        msg_box.setIcon(QMessageBox.Icon.Question)
        add_new_btn = msg_box.addButton("Add as New Lot Number", QMessageBox.ButtonRole.YesRole)
        assign_btn = msg_box.addButton("Assign Excess to Last Lot of Range", QMessageBox.ButtonRole.NoRole)
        cancel_btn = msg_box.addButton(QMessageBox.StandardButton.Cancel)
        msg_box.setDefaultButton(add_new_btn)
        msg_box.exec()
        if msg_box.clickedButton() == add_new_btn:
            return 'NEW_LOT'
        elif msg_box.clickedButton() == assign_btn:
            return 'ASSIGN_TO_LAST_IN_RANGE'
        else:
            return None

    def _validate_and_calculate_lots(self):
        try:
            total_qty = Decimal(self.quantity_edit.text() or "0")
            weight_per_lot = Decimal(self.weight_per_lot_edit.text() or "0")
            lot_input = self.lot_number_edit.text().strip()
            if not all([self.form_ref_no_edit.text(), self.product_code_combo.currentText(), lot_input,
                        self.endorsed_by_combo.currentText(), self.location_combo.currentText()]):
                QMessageBox.warning(self, "Input Error",
                                    "Required fields: Form Ref, Product, Lot, Endorsed By, Location.")
                return None
            if weight_per_lot <= 0:
                QMessageBox.warning(self, "Input Error", "Weight per Lot must be greater than zero.")
                return None

            excess_handling_method = 'NEW_LOT'
            if self.is_lot_range_check.isChecked() and (total_qty % weight_per_lot > 0):
                choice = self._ask_excess_handling_method()
                if choice is None: return None
                excess_handling_method = choice

            return self._perform_lot_calculation(total_qty, weight_per_lot, lot_input,
                                                 self.is_lot_range_check.isChecked(), excess_handling_method)
        except (InvalidOperation, ValueError):
            QMessageBox.warning(self, "Input Error", "Enter valid numbers for Quantity and Weight per Lot.")
            return None

    def _perform_lot_calculation(self, total_qty, weight_per_lot, lot_input, is_range, excess_handling_method):
        num_full_lots = int(total_qty // weight_per_lot)
        excess_qty = total_qty % weight_per_lot
        breakdown_data, excess_data = [], []
        range_end_lot = None

        calculated_lots = [lot_input.upper()] * num_full_lots
        if is_range:
            range_info = self._parse_lot_range(lot_input, num_full_lots)
            if range_info is None: return None
            calculated_lots = range_info['lots']
            range_end_lot = range_info['end_lot']

        if calculated_lots:
            breakdown_data = [{'lot_number': lot, 'quantity_kg': weight_per_lot} for lot in calculated_lots]

        if excess_qty > 0:
            if is_range and excess_handling_method == 'ASSIGN_TO_LAST_IN_RANGE':
                excess_data.append({'lot_number': range_end_lot, 'quantity_kg': excess_qty})
            else:
                last_lot = calculated_lots[-1] if calculated_lots else lot_input.upper()
                match = re.match(r'^(\d+)([A-Z]*)$', last_lot)
                excess_lot_number = f"{str(int(match.group(1)) + 1).zfill(len(match.group(1)))}{match.group(2)}" if match else f"{last_lot}-EXCESS"

                target_list = breakdown_data if not breakdown_data else excess_data
                target_list.append({'lot_number': excess_lot_number, 'quantity_kg': excess_qty})

        return {"breakdown": breakdown_data, "excess": excess_data}

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

    def _clear_form_previews(self):
        self.preview_data = None
        self.preview_breakdown_table.setRowCount(0);
        self.preview_excess_table.setRowCount(0)
        self.breakdown_total_label.setText("<b>Total: 0.00 kg</b>");
        self.excess_total_label.setText("<b>Total: 0.00 kg</b>")

    def _save_endorsement(self):
        if not self.preview_data:
            QMessageBox.warning(self, "Preview Required",
                                "Please click 'Preview Breakdown' to generate lots before saving.")
            return

        is_update = self.current_editing_ref is not None
        sys_ref_no = self.current_editing_ref if is_update else self._generate_system_ref_no()

        primary_data = {
            "system_ref_no": sys_ref_no, "form_ref_no": self.form_ref_no_edit.text().strip(),
            "date_endorsed": self.date_endorsed_edit.date().toPyDate(), "category": self.category_combo.currentText(),
            "product_code": self.product_code_combo.currentText(), "lot_number": self.lot_number_edit.text().strip(),
            "quantity_kg": self.quantity_edit.value(), "weight_per_lot": self.weight_per_lot_edit.value(),
            "bag_no": self.bag_no_combo.currentText(), "status": self.status_combo.currentText(),
            "endorsed_by": self.endorsed_by_combo.currentText(), "remarks": self.remarks_combo.currentText(),
            "location": self.location_combo.currentText(),
            "encoded_by": self.username, "encoded_on": datetime.now(),
            "edited_by": self.username, "edited_on": datetime.now()
        }

        try:
            with self.engine.connect() as conn, conn.begin():
                if is_update:
                    conn.execute(text("DELETE FROM fg_endorsements_secondary WHERE system_ref_no = :ref"),
                                 {"ref": sys_ref_no})
                    conn.execute(text("DELETE FROM fg_endorsements_excess WHERE system_ref_no = :ref"),
                                 {"ref": sys_ref_no})
                    update_sql = text(
                        "UPDATE fg_endorsements_primary SET form_ref_no=:form_ref_no, date_endorsed=:date_endorsed, category=:category, product_code=:product_code, lot_number=:lot_number, quantity_kg=:quantity_kg, weight_per_lot=:weight_per_lot, bag_no=:bag_no, status=:status, endorsed_by=:endorsed_by, remarks=:remarks, location=:location, edited_by=:edited_by, edited_on=:edited_on WHERE system_ref_no = :system_ref_no")
                    conn.execute(update_sql, primary_data)
                    self.log_audit_trail("UPDATE_FG_ENDORSEMENT", f"Updated endorsement: {sys_ref_no}")
                    QMessageBox.information(self, "Success", f"Endorsement {sys_ref_no} has been updated.")
                else:
                    insert_sql = text(
                        "INSERT INTO fg_endorsements_primary (system_ref_no, form_ref_no, date_endorsed, category, product_code, lot_number, quantity_kg, weight_per_lot, bag_no, status, endorsed_by, remarks, location, encoded_by, encoded_on, edited_by, edited_on) VALUES (:system_ref_no, :form_ref_no, :date_endorsed, :category, :product_code, :lot_number, :quantity_kg, :weight_per_lot, :bag_no, :status, :endorsed_by, :remarks, :location, :encoded_by, :encoded_on, :edited_by, :edited_on)")
                    conn.execute(insert_sql, primary_data)
                    self.log_audit_trail("CREATE_FG_ENDORSEMENT", f"Created endorsement: {sys_ref_no}")
                    QMessageBox.information(self, "Success",
                                            f"Endorsement saved! System Reference Number: {sys_ref_no}")

                sql_template = "INSERT INTO {table} (system_ref_no, lot_number, quantity_kg, product_code, status, bag_no, endorsed_by) VALUES (:system_ref_no, :lot_number, :quantity_kg, :product_code, :status, :bag_no, :endorsed_by)"
                common_details = {"product_code": primary_data["product_code"], "status": primary_data["status"],
                                  "bag_no": primary_data["bag_no"], "endorsed_by": primary_data["endorsed_by"]}

                breakdown_lots, excess_lots = self.preview_data.get('breakdown', []), self.preview_data.get('excess',
                                                                                                            [])
                if breakdown_lots: conn.execute(text(sql_template.format(table="fg_endorsements_secondary")),
                                                [{'system_ref_no': sys_ref_no, **lot_data, **common_details} for
                                                 lot_data in breakdown_lots])
                if excess_lots: conn.execute(text(sql_template.format(table="fg_endorsements_excess")),
                                             [{'system_ref_no': sys_ref_no, **lot_data, **common_details} for lot_data
                                              in excess_lots])

            self._clear_form();
            self._load_all_endorsements();
            self._update_dashboard_data()
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"An error occurred while saving: {e}")

    def _load_all_endorsements(self):
        search_term = f"%{self.search_edit.text()}%"
        offset = (self.current_page - 1) * self.records_per_page
        try:
            with self.engine.connect() as conn:
                filter_clause = " AND (system_ref_no ILIKE :st OR form_ref_no ILIKE :st OR product_code ILIKE :st OR lot_number ILIKE :st)" if self.search_edit.text() else ""
                params = {'limit': self.records_per_page, 'offset': offset, 'st': search_term}
                count_res = conn.execute(
                    text(f"SELECT COUNT(id) FROM fg_endorsements_primary WHERE is_deleted IS NOT TRUE {filter_clause}"),
                    params).scalar_one()
                self.total_records = count_res
                query = text(
                    f"SELECT system_ref_no, form_ref_no, date_endorsed, product_code, lot_number, quantity_kg, location, status FROM fg_endorsements_primary WHERE is_deleted IS NOT TRUE {filter_clause} ORDER BY id DESC LIMIT :limit OFFSET :offset")
                res = conn.execute(query, params).mappings().all()
            headers = ["Sys Ref No", "Form Ref No", "Date", "Product Code", "Lot No / Range", "Total Qty", "Location",
                       "Status"]
            self._populate_records_table(self.records_table, res, headers)
            self._update_pagination_controls();
            self._on_record_selection_changed()
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load endorsement records: {e}")

    def _load_deleted_endorsements(self):
        search_term = f"%{self.deleted_search_edit.text()}%"
        try:
            with self.engine.connect() as conn:
                filter_clause = " AND (system_ref_no ILIKE :st OR form_ref_no ILIKE :st OR product_code ILIKE :st OR lot_number ILIKE :st)" if self.deleted_search_edit.text() else ""
                query = text(
                    f"SELECT system_ref_no, form_ref_no, date_endorsed, product_code, lot_number, quantity_kg FROM fg_endorsements_primary WHERE is_deleted IS TRUE {filter_clause} ORDER BY id DESC")
                res = conn.execute(query, {'st': search_term}).mappings().all()
            headers = ["Sys Ref No", "Form Ref No", "Date", "Product Code", "Lot No / Range", "Total Qty"]
            self._populate_records_table(self.deleted_records_table, res, headers)
            self._on_deleted_record_selection_changed()
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load deleted records: {e}")

    def _show_selected_record_in_view_tab(self):
        selected_rows = self.records_table.selectionModel().selectedRows()
        if not selected_rows: return
        sys_ref_no = self.records_table.item(selected_rows[0].row(), 0).text()
        self._populate_view_details_tab(sys_ref_no)

    def _show_selected_deleted_record_in_view_tab(self):
        selected_rows = self.deleted_records_table.selectionModel().selectedRows()
        if not selected_rows: return
        sys_ref_no = self.deleted_records_table.item(selected_rows[0].row(), 0).text()
        self._populate_view_details_tab(sys_ref_no)
        self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.view_details_tab), True)
        self.tab_widget.setCurrentIndex(self.tab_widget.indexOf(self.view_details_tab))

    def _populate_view_details_tab(self, sys_ref_no):
        try:
            with self.engine.connect() as conn:
                primary = conn.execute(text("SELECT * FROM fg_endorsements_primary WHERE system_ref_no = :ref"),
                                       {"ref": sys_ref_no}).mappings().one()
                breakdown = conn.execute(text(
                    "SELECT lot_number, quantity_kg, status, bag_no, endorsed_by FROM fg_endorsements_secondary WHERE system_ref_no = :ref ORDER BY id"),
                                         {"ref": sys_ref_no}).mappings().all()
                excess = conn.execute(
                    text("SELECT lot_number, quantity_kg FROM fg_endorsements_excess WHERE system_ref_no = :ref"),
                    {"ref": sys_ref_no}).mappings().all()

            for layout in [self.view_left_details_layout, self.view_right_details_layout]:
                while layout.count(): layout.takeAt(0).widget().deleteLater()

            items_list = list(primary.items())
            midpoint = (len(items_list) + 1) // 2
            for key, value in items_list[:midpoint]: self._add_view_detail_row(self.view_left_details_layout, key,
                                                                               value)
            for key, value in items_list[midpoint:]: self._add_view_detail_row(self.view_right_details_layout, key,
                                                                               value)

            self._populate_view_table(self.view_breakdown_table, breakdown,
                                      ["Lot Number", "Qty (kg)", "Status", "Bag No", "Endorsed By"])
            self.view_breakdown_total_label.setText(
                f"<b>Total: {sum(item.get('quantity_kg', Decimal('0.0')) for item in breakdown):.2f} kg</b>")
            self._populate_view_table(self.view_excess_table, excess, ["Associated Lot", "Excess Qty (kg)"])
            self.view_excess_total_label.setText(
                f"<b>Total: {sum(item.get('quantity_kg', Decimal('0.0')) for item in excess):.2f} kg</b>")
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load details for {sys_ref_no}: {e}")

    def _add_view_detail_row(self, layout, key, value):
        display_text = str(value) if value is not None else "N/A"
        if isinstance(value, datetime):
            display_text = value.strftime('%Y-%m-%d %I:%M %p')
        elif isinstance(value, (Decimal, float)):
            display_text = f"{value:.2f}"
        layout.addRow(QLabel(f"<b>{key.replace('_', ' ').title()}:</b>"), QLabel(display_text))

    def _populate_view_table(self, table_widget: QTableWidget, data: list, headers: list):
        table_widget.setRowCount(0);
        table_widget.setColumnCount(len(headers));
        table_widget.setHorizontalHeaderLabels(headers)
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

    def _load_record_for_update(self):
        selected_rows = self.records_table.selectionModel().selectedRows()
        if not selected_rows: return
        sys_ref_no = self.records_table.item(selected_rows[0].row(), 0).text()
        try:
            with self.engine.connect() as conn:
                record = conn.execute(text("SELECT * FROM fg_endorsements_primary WHERE system_ref_no = :ref"),
                                      {"ref": sys_ref_no}).mappings().one_or_none()
                if not record: QMessageBox.critical(self, "Error", f"Record {sys_ref_no} not found."); return
                breakdown_res = conn.execute(text(
                    "SELECT lot_number, quantity_kg FROM fg_endorsements_secondary WHERE system_ref_no = :ref ORDER BY id"),
                                             {"ref": sys_ref_no}).mappings().all()
                excess_res = conn.execute(text(
                    "SELECT lot_number, quantity_kg FROM fg_endorsements_excess WHERE system_ref_no = :ref ORDER BY id"),
                                          {"ref": sys_ref_no}).mappings().all()

            self._clear_form();
            self.current_editing_ref = sys_ref_no
            self.sys_ref_no_edit.setText(record.get('system_ref_no', ''));
            self.form_ref_no_edit.setText(record.get('form_ref_no', ''))
            self.date_endorsed_edit.setDate(QDate.fromString(str(record.get('date_endorsed', '')), "yyyy-MM-dd"))
            self.category_combo.setCurrentText(record.get('category', ''));
            self.product_code_combo.setCurrentText(record.get('product_code', ''))
            self.lot_number_edit.setText(record.get('lot_number', ''));
            self.quantity_edit.setText(f"{Decimal(record.get('quantity_kg', '0.00')):.2f}")
            self.weight_per_lot_edit.setText(f"{Decimal(record.get('weight_per_lot', '0.00')):.2f}");
            self.bag_no_combo.setCurrentText(record.get('bag_no', ''))
            self.status_combo.setCurrentText(record.get('status', ''));
            self.endorsed_by_combo.setCurrentText(record.get('endorsed_by', ''))
            self.remarks_combo.setCurrentText(record.get('remarks', ''));
            self.location_combo.setCurrentText(record.get('location', ''))
            self.is_lot_range_check.setChecked('-' in (record.get('lot_number') or ''))
            self.save_btn.setText("Update Endorsement");
            self.cancel_update_btn.show()

            self.preview_data = {'breakdown': list(breakdown_res), 'excess': list(excess_res)}
            self._populate_preview_widgets(self.preview_data)
            self.tab_widget.setCurrentIndex(self.tab_widget.indexOf(self.entry_tab))
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load record {sys_ref_no}: {e}")

    def _delete_record(self):
        selected_rows = self.records_table.selectionModel().selectedRows()
        if not selected_rows: return
        sys_ref_no = self.records_table.item(selected_rows[0].row(), 0).text()

        password, ok = QInputDialog.getText(self, "Admin Authentication", "Enter Admin Password:",
                                            QLineEdit.EchoMode.Password)
        if not ok: return
        if password != ADMIN_PASSWORD:
            QMessageBox.warning(self, "Authentication Failed", "Incorrect password. Deletion cancelled.");
            return

        if QMessageBox.question(self, "Confirm Delete",
                                f"Delete endorsement <b>{sys_ref_no}</b>?") == QMessageBox.StandardButton.Yes:
            try:
                with self.engine.connect() as conn, conn.begin():
                    conn.execute(
                        text("UPDATE fg_endorsements_primary SET is_deleted = TRUE WHERE system_ref_no = :ref"),
                        {"ref": sys_ref_no})
                    self.log_audit_trail("DELETE_FG_ENDORSEMENT", f"Soft-deleted endorsement: {sys_ref_no}")
                QMessageBox.information(self, "Success", f"Endorsement {sys_ref_no} has been moved to Deleted Records.")
                self._load_all_endorsements();
                self._load_deleted_endorsements();
                self._update_dashboard_data()
            except Exception as e:
                QMessageBox.critical(self, "Database Error", f"An error occurred while deleting: {e}")

    def _restore_record(self):
        selected_rows = self.deleted_records_table.selectionModel().selectedRows()
        if not selected_rows: return
        sys_ref_no = self.deleted_records_table.item(selected_rows[0].row(), 0).text()

        if QMessageBox.question(self, "Confirm Restore",
                                f"Restore endorsement <b>{sys_ref_no}</b>?") == QMessageBox.StandardButton.Yes:
            try:
                with self.engine.connect() as conn, conn.begin():
                    conn.execute(
                        text("UPDATE fg_endorsements_primary SET is_deleted = FALSE WHERE system_ref_no = :ref"),
                        {"ref": sys_ref_no})
                    self.log_audit_trail("RESTORE_FG_ENDORSEMENT", f"Restored endorsement: {sys_ref_no}")
                QMessageBox.information(self, "Success", f"Endorsement {sys_ref_no} has been restored.")
                self._load_all_endorsements();
                self._load_deleted_endorsements();
                self._update_dashboard_data()
            except Exception as e:
                QMessageBox.critical(self, "Database Error", f"An error occurred while restoring: {e}")

    def _load_initial_data(self):
        self._load_product_codes();
        self._load_endorsers();
        self._load_remarks();
        self._load_locations()

    def _load_dropdown_data(self, combo: QComboBox, query_str: str, make_upper: bool = False):
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query_str)).scalars().all()
            current_text = combo.currentText();
            combo.blockSignals(True);
            combo.clear()
            combo.addItems([""] + [r.upper() if make_upper else r for r in result])
            combo.blockSignals(False)
            if combo.isEditable():
                combo.setCurrentText(current_text)
            else:
                combo.setCurrentIndex(combo.findText(current_text) if combo.findText(current_text) != -1 else 0)
        except Exception as e:
            QMessageBox.critical(self, "Dropdown Load Error", f"Could not load data: {e}")

    def _load_product_codes(self):
        self._load_dropdown_data(self.product_code_combo,
                                 "SELECT DISTINCT prod_code FROM legacy_production WHERE prod_code IS NOT NULL AND prod_code != '' ORDER BY prod_code",
                                 True)

    def _load_endorsers(self):
        self._load_dropdown_data(self.endorsed_by_combo, "SELECT name FROM endorsers ORDER BY name")

    def _load_remarks(self):
        self._load_dropdown_data(self.remarks_combo, "SELECT remark_text FROM endorsement_remarks ORDER BY remark_text")

    def _load_locations(self):
        self._load_dropdown_data(self.location_combo, "SELECT name FROM warehouses ORDER BY name")

    def _manage_list(self, table, column, title, callback):
        ManageListDialog(self, self.engine, table, column, title).exec(); callback()

    def _generate_system_ref_no(self):
        prefix = f"FGE-{datetime.now().strftime('%Y%m%d')}-"
        with self.engine.connect() as conn:
            last_ref = conn.execute(text(
                "SELECT system_ref_no FROM fg_endorsements_primary WHERE system_ref_no LIKE :p ORDER BY id DESC LIMIT 1"),
                                    {"p": f"{prefix}%"}).scalar_one_or_none()
            return f"{prefix}{int(last_ref.split('-')[-1]) + 1 if last_ref else 1:04d}"

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

    def _populate_records_table(self, table: QTableWidget, data: list, headers: list):
        table.setRowCount(0);
        table.setColumnCount(len(headers));
        table.setHorizontalHeaderLabels(headers)
        if not data: return
        table.setRowCount(len(data))
        for i, row_data in enumerate(data):
            for j, key in enumerate(list(row_data.keys())):
                val = row_data.get(key)
                item_text = f"{val:.2f}" if isinstance(val, (Decimal, float)) else str(val if val is not None else "")
                item = QTableWidgetItem(item_text)
                if isinstance(val, (Decimal, float)): item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(i, j, item)

    def _populate_preview_table(self, table_widget: QTableWidget, data: list, headers: list):
        table_widget.setRowCount(0);
        table_widget.setColumnCount(len(headers));
        table_widget.setHorizontalHeaderLabels(headers)
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

    def _handle_pie_slice_hover(self, slice_item: QPieSlice, state: bool):
        if state:
            slice_item.setExploded(True); slice_item.setLabel(f"{slice_item.label()} ({slice_item.percentage():.1%})")
        else:
            slice_item.setExploded(False); slice_item.setLabel(slice_item.label().split(" (")[0])

    def _update_dashboard_data(self):
        try:
            with self.engine.connect() as conn:
                base_query = "FROM fg_endorsements_primary WHERE is_deleted IS NOT TRUE"
                today_query = f"{base_query} AND date_endorsed = CURRENT_DATE"
                endorsed_today = conn.execute(text(f"SELECT COUNT(*) {today_query}")).scalar_one_or_none() or 0
                qty_today = conn.execute(
                    text(f"SELECT SUM(quantity_kg) {today_query}")).scalar_one_or_none() or Decimal('0.00')
                products_today = conn.execute(
                    text(f"SELECT COUNT(DISTINCT product_code) {today_query}")).scalar_one_or_none() or 0
                lots_today = conn.execute(text(
                    f"SELECT COUNT(*) FROM fg_endorsements_secondary s JOIN fg_endorsements_primary p ON s.system_ref_no = p.system_ref_no WHERE p.date_endorsed = CURRENT_DATE AND p.is_deleted IS NOT TRUE")).scalar_one_or_none() or 0
                recent_endorsements = conn.execute(text(
                    f"SELECT form_ref_no, product_code, date_endorsed {base_query} ORDER BY id DESC LIMIT 5")).mappings().all()
                top_products = conn.execute(text(
                    f"SELECT product_code, SUM(quantity_kg) as total_quantity {base_query} GROUP BY product_code ORDER BY total_quantity DESC LIMIT 5")).mappings().all()

            self.kpi_endorsed_value.setText(str(endorsed_today))
            self.kpi_qty_value.setText(f"{float(qty_today):.2f}")
            self.kpi_products_value.setText(str(products_today))
            self.kpi_lots_value.setText(str(lots_today))

            self.dashboard_recent_table.setRowCount(len(recent_endorsements))
            self.dashboard_recent_table.setColumnCount(3)
            self.dashboard_recent_table.setHorizontalHeaderLabels(["Ref No.", "Product Code", "Date"])
            for row, record in enumerate(recent_endorsements):
                self.dashboard_recent_table.setItem(row, 0, QTableWidgetItem(record['form_ref_no']))
                self.dashboard_recent_table.setItem(row, 1, QTableWidgetItem(record['product_code']))
                self.dashboard_recent_table.setItem(row, 2, QTableWidgetItem(
                    QDate(record['date_endorsed']).toString("yyyy-MM-dd")))

            self.product_pie_series.clear()
            self.product_chart.setTitle(
                f"Top 5 Products by Total Endorsed Quantity{' (No Data)' if not top_products else ''}")
            if top_products:
                for prod in top_products:
                    slice_item = self.product_pie_series.append(
                        f"{prod['product_code']}\n{float(prod.get('total_quantity') or 0.0):.2f} kg",
                        float(prod.get('total_quantity') or 0.0))
                    slice_item.setLabelVisible(True)
        except Exception as e:
            QMessageBox.critical(self, "Dashboard Error", f"Could not load dashboard data: {e}")