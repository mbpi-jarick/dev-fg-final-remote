import sys
import traceback
import math
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from functools import partial

# --- PyQt6 Imports ---
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTabWidget, QFormLayout, QLineEdit,
                             QComboBox, QDateEdit, QPushButton, QTableWidget, QTableWidgetItem,
                             QAbstractItemView, QHeaderView, QMessageBox, QHBoxLayout, QLabel,
                             QDialog, QDialogButtonBox,
                             QGridLayout, QGroupBox, QMenu, QSplitter, QCompleter)
from PyQt6.QtGui import QDoubleValidator

# --- Database Imports ---
from sqlalchemy import text


# --- Icon Imports (Removed) ---
# Note: The 'fa' variable and the qtawesome library are no longer used.


# --- HELPER CLASSES (Unchanged from your original) ---

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


class AddNewValueDialog(QDialog):
    def __init__(self, parent=None, title="Add New Value", label_text="Value:"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(350)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(label_text))
        self.value_edit = UpperCaseLineEdit()
        layout.addWidget(self.value_edit)
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def get_value(self):
        return self.value_edit.text().strip()


# --- MAIN PAGE WIDGET ---

class RequisitionLogbookPage(QWidget):
    def __init__(self, db_engine, username, log_audit_trail_func):
        super().__init__()
        self.engine, self.username, self.log_audit_trail = db_engine, username, log_audit_trail_func
        self.current_editing_req_id = None

        self.current_page = 1
        self.records_per_page = 200
        self.total_records, self.total_pages = 0, 1

        self.deleted_current_page = 1
        self.deleted_total_records, self.deleted_total_pages = 0, 1

        self.init_ui()
        self._load_all_records()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        view_tab = QWidget()
        self.view_details_tab, self.entry_tab, self.deleted_tab = QWidget(), QWidget(), QWidget()

        # --- Tab Setup (Icons removed) ---
        self.tab_widget.addTab(view_tab, "All Requisitions")
        self.tab_widget.addTab(self.view_details_tab, "View Requisition Details")
        self.tab_widget.addTab(self.entry_tab, "Requisition Entry")
        self.tab_widget.addTab(self.deleted_tab, "Deleted Records")

        self._setup_view_tab(view_tab)
        self._setup_view_details_tab(self.view_details_tab)
        self._setup_entry_tab(self.entry_tab)
        self._setup_deleted_tab(self.deleted_tab)

        self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.view_details_tab), False)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

        # --- MODIFIED: Added stylesheet to set the selected row color for all tables in this widget ---
        stylesheet = """
            QTableWidget::item:selected {
                background-color: #007BFF;
                color: white;
            }
        """
        self.setStyleSheet(stylesheet)

    def _setup_view_tab(self, tab):
        layout = QVBoxLayout(tab)
        top_layout = QHBoxLayout()

        top_layout.addWidget(QLabel("Search:"))
        self.search_edit = UpperCaseLineEdit(placeholderText="Filter by Req ID, Ref#, Product, Lot...")
        top_layout.addWidget(self.search_edit, 1)

        self.refresh_btn = QPushButton("Refresh")
        self.update_btn = QPushButton("Load Selected for Update")
        self.update_btn.setObjectName("PrimaryButton")
        self.delete_btn = QPushButton("Delete Selected")
        self.delete_btn.setObjectName("DestructiveButton")

        # --- Action buttons (Icons removed) ---

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
        layout.addWidget(self.records_table)

        pagination_layout = QHBoxLayout()
        self.prev_btn, self.next_btn = QPushButton("<< Previous"), QPushButton("Next >>")
        self.page_label = QLabel("Page 1 of 1")

        # --- Pagination buttons (Icons removed) ---

        pagination_layout.addStretch()
        pagination_layout.addWidget(self.prev_btn)
        pagination_layout.addWidget(self.page_label)
        pagination_layout.addWidget(self.next_btn)
        pagination_layout.addStretch()
        layout.addLayout(pagination_layout)

        self.search_edit.textChanged.connect(self._on_search_text_changed)
        self.refresh_btn.clicked.connect(self._load_all_records)
        self.update_btn.clicked.connect(self._load_record_for_update)
        self.delete_btn.clicked.connect(self._delete_record)
        self.records_table.itemSelectionChanged.connect(self._on_record_selection_changed)
        self.records_table.doubleClicked.connect(self._load_record_for_update)
        self.prev_btn.clicked.connect(self._go_to_prev_page)
        self.next_btn.clicked.connect(self._go_to_next_page)
        self._on_record_selection_changed()

    def _setup_deleted_tab(self, tab):
        layout = QVBoxLayout(tab)
        top_layout = QHBoxLayout()

        top_layout.addWidget(QLabel("Search:"))
        self.deleted_search_edit = UpperCaseLineEdit(placeholderText="Filter deleted records...")
        top_layout.addWidget(self.deleted_search_edit, 1)

        self.restore_btn = QPushButton("Restore Selected")
        self.restore_btn.setObjectName("PrimaryButton")
        self.restore_btn.setEnabled(False)

        # --- Restore button (Icon removed) ---

        top_layout.addWidget(self.restore_btn)
        layout.addLayout(top_layout)

        self.deleted_records_table = QTableWidget()
        self.deleted_records_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.deleted_records_table.setShowGrid(False)
        self.deleted_records_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.deleted_records_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.deleted_records_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.deleted_records_table.verticalHeader().setVisible(False)
        self.deleted_records_table.horizontalHeader().setHighlightSections(False)
        layout.addWidget(self.deleted_records_table)

        pagination_layout = QHBoxLayout()
        self.deleted_prev_btn, self.deleted_next_btn = QPushButton("<< Previous"), QPushButton("Next >>")
        self.deleted_page_label = QLabel("Page 1 of 1")

        # --- Pagination buttons (Icons removed) ---

        pagination_layout.addStretch()
        pagination_layout.addWidget(self.deleted_prev_btn)
        pagination_layout.addWidget(self.deleted_page_label)
        pagination_layout.addWidget(self.deleted_next_btn)
        pagination_layout.addStretch()
        layout.addLayout(pagination_layout)

        self.deleted_search_edit.textChanged.connect(self._on_deleted_search_text_changed)
        self.restore_btn.clicked.connect(self._restore_record)
        self.deleted_records_table.itemSelectionChanged.connect(
            lambda: self.restore_btn.setEnabled(bool(self.deleted_records_table.selectedItems()))
        )
        self.deleted_prev_btn.clicked.connect(self._go_to_deleted_prev_page)
        self.deleted_next_btn.clicked.connect(self._go_to_deleted_next_page)

    def _setup_entry_tab(self, tab):
        layout = QVBoxLayout(tab)
        form_group = QGroupBox("Requisition Details")
        layout.addWidget(form_group)
        form_layout = QGridLayout(form_group)

        self.req_id_edit = QLineEdit(readOnly=True, placeholderText="Auto-generated")
        self.manual_ref_no_edit = UpperCaseLineEdit()
        self.category_combo = QComboBox()
        self.category_combo.addItems(["MB", "DC"])
        self.request_date_edit = QDateEdit(calendarPopup=True, displayFormat="yyyy-MM-dd")
        self.requester_name_combo = QComboBox()
        self.department_combo = QComboBox()
        self.product_code_combo = QComboBox()
        self.approved_by_combo = QComboBox()
        self.status_combo = QComboBox()
        self.lot_no_edit = UpperCaseLineEdit()
        self.quantity_edit = FloatLineEdit()
        self.remarks_edit = UpperCaseLineEdit()
        self.location_combo = QComboBox()
        self.location_combo.addItems(["WH1", "WH2", "WH3", "WH4", "WH5"])
        self.request_for_combo = QComboBox()
        self.request_for_combo.addItems(["PASSED", "FAILED"])

        self._configure_combobox(self.requester_name_combo, editable=True)
        self._configure_combobox(self.department_combo, editable=True)
        self._configure_combobox(self.product_code_combo, editable=True)
        self._configure_combobox(self.approved_by_combo, editable=True)
        self._configure_combobox(self.status_combo, editable=True)
        self._refresh_entry_combos()

        requester_widget = self._create_combo_with_add_button(self.requester_name_combo, self._on_add_requester)
        department_widget = self._create_combo_with_add_button(self.department_combo, self._on_add_department)
        approved_by_widget = self._create_combo_with_add_button(self.approved_by_combo, self._on_add_approver)

        form_layout.addWidget(QLabel("Requisition ID:"), 0, 0)
        form_layout.addWidget(self.req_id_edit, 0, 1)
        form_layout.addWidget(QLabel("Manual Ref #:"), 0, 2)
        form_layout.addWidget(self.manual_ref_no_edit, 0, 3)
        form_layout.addWidget(QLabel("Request Date:"), 1, 0)
        form_layout.addWidget(self.request_date_edit, 1, 1)
        form_layout.addWidget(QLabel("Category:"), 1, 2)
        form_layout.addWidget(self.category_combo, 1, 3)
        form_layout.addWidget(QLabel("Requester Name:"), 2, 0)
        form_layout.addWidget(requester_widget, 2, 1)
        form_layout.addWidget(QLabel("Department:"), 2, 2)
        form_layout.addWidget(department_widget, 2, 3)
        form_layout.addWidget(QLabel("Product Code:"), 3, 0)
        form_layout.addWidget(self.product_code_combo, 3, 1)
        form_layout.addWidget(QLabel("Lot #:"), 3, 2)
        form_layout.addWidget(self.lot_no_edit, 3, 3)
        form_layout.addWidget(QLabel("Quantity (kg):"), 4, 0)
        form_layout.addWidget(self.quantity_edit, 4, 1)
        form_layout.addWidget(QLabel("Location:"), 4, 2)
        form_layout.addWidget(self.location_combo, 4, 3)
        form_layout.addWidget(QLabel("Request For:"), 5, 0)
        form_layout.addWidget(self.request_for_combo, 5, 1)
        form_layout.addWidget(QLabel("Status:"), 5, 2)
        form_layout.addWidget(self.status_combo, 5, 3)
        form_layout.addWidget(QLabel("Approved By:"), 6, 0)
        form_layout.addWidget(approved_by_widget, 6, 1)
        form_layout.addWidget(QLabel("Remarks:"), 6, 2)
        form_layout.addWidget(self.remarks_edit, 6, 3)

        layout.addStretch()
        button_layout = QHBoxLayout()
        self.save_btn = QPushButton("Save Requisition")
        self.save_btn.setObjectName("PrimaryButton")
        self.clear_btn = QPushButton("New")
        self.clear_btn.setObjectName("SecondaryButton")
        self.cancel_update_btn = QPushButton("Cancel Update")
        self.cancel_update_btn.setObjectName("DestructiveButton")
        button_layout.addStretch()
        button_layout.addWidget(self.cancel_update_btn)
        button_layout.addWidget(self.clear_btn)
        button_layout.addWidget(self.save_btn)
        layout.addLayout(button_layout)

        self.save_btn.clicked.connect(self._save_record)
        self.clear_btn.clicked.connect(self._clear_form)
        self.cancel_update_btn.clicked.connect(self._clear_form)
        self._clear_form()

    def _create_combo_with_add_button(self, combo: QComboBox, on_add_method):
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        layout.addWidget(combo, 1)
        add_btn = QPushButton()
        add_btn.setObjectName("SecondaryButton")
        # --- Icon replaced with text ---
        add_btn.setText("+")
        add_btn.setFixedSize(30, 30)
        add_btn.setToolTip("Add a new value to the list")
        add_btn.clicked.connect(on_add_method)
        layout.addWidget(add_btn)
        return container

    def _on_add_requester(self):
        self._add_new_lookup_value(self.requester_name_combo, "Requester", 'requisition_requesters', 'name')

    def _on_add_department(self):
        self._add_new_lookup_value(self.department_combo, "Department", 'requisition_departments', 'name')

    def _on_add_approver(self):
        self._add_new_lookup_value(self.approved_by_combo, "Approver", 'requisition_approvers', 'name')

    def _add_new_lookup_value(self, combo_widget, dialog_title, table_name, column_name):
        dialog = AddNewValueDialog(self, f"Add New {dialog_title}", f"Enter new {dialog_title.lower()} name:")
        if dialog.exec():
            new_value = dialog.get_value()
            if not new_value: return
            try:
                with self.engine.connect() as conn, conn.begin():
                    sql = text(
                        f"INSERT INTO {table_name} ({column_name}) VALUES (:value) ON CONFLICT ({column_name}) DO NOTHING")
                    conn.execute(sql, {"value": new_value})
                self._populate_combo(combo_widget, table_name, column_name)
                combo_widget.setCurrentText(new_value)
            except Exception as e:
                trace = traceback.format_exc();
                print(f"ERROR: Could not add new lookup value: {e}\n{trace}")
                msg_box = QMessageBox(QMessageBox.Icon.Critical, "Database Error",
                                      f"Could not save new {dialog_title.lower()}: {e}")
                msg_box.setDetailedText(trace);
                msg_box.exec()

    def _configure_combobox(self, combo: QComboBox, editable: bool = False):
        combo.setEditable(editable)
        if editable:
            line_edit = UpperCaseLineEdit(self);
            line_edit.setFont(self.font());
            combo.setLineEdit(line_edit)
            combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
            combo.completer().setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
            combo.completer().setFilterMode(Qt.MatchFlag.MatchContains)

    def _refresh_entry_combos(self):
        self._populate_combo(self.product_code_combo, 'legacy_production', 'prod_code')
        self._populate_combo(self.requester_name_combo, 'requisition_requesters', 'name')
        self._populate_combo(self.approved_by_combo, 'requisition_approvers', 'name')
        self._populate_combo(self.department_combo, 'requisition_departments', 'name')
        self._populate_combo(self.status_combo, 'requisition_statuses', 'status_name')

    def _populate_combo(self, combo: QComboBox, table: str, column: str):
        current_text = combo.currentText()
        try:
            with self.engine.connect() as conn:
                query = text(
                    f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL AND {column} != '' ORDER BY {column}")
                results = conn.execute(query).scalars().all()
            combo.blockSignals(True)
            combo.clear()
            if table == 'requisition_statuses' and not results: results = ["PENDING", "APPROVED", "COMPLETED",
                                                                           "REJECTED"]
            combo.addItems(results)
            combo.blockSignals(False)
            combo.setCurrentText(current_text)
            if combo.lineEdit(): combo.lineEdit().setPlaceholderText("SELECT OR TYPE...")
        except Exception as e:
            trace = traceback.format_exc();
            print(f"Warning: Could not populate combobox from {table}.{column}: {e}\n{trace}")
            if table == 'requisition_statuses': combo.addItems(["PENDING", "APPROVED", "COMPLETED", "REJECTED"])

    def _setup_view_details_tab(self, tab):
        layout = QVBoxLayout(tab)
        details_group = QGroupBox("Requisition Details (Read-Only)")
        self.view_details_layout = QFormLayout(details_group)
        layout.addWidget(details_group)
        layout.addStretch()

    def _on_tab_changed(self, index):
        tab_widget = self.tab_widget.widget(index)
        if tab_widget == self.view_details_tab:
            self._show_selected_record_in_view_tab()
        elif tab_widget == self.entry_tab:
            self._refresh_entry_combos()
        elif tab_widget == self.deleted_tab:
            self._load_deleted_records()

    def _clear_form(self):
        self.current_editing_req_id = None;
        self.cancel_update_btn.hide();
        self.save_btn.setText("Save Requisition")
        for w in [self.req_id_edit, self.manual_ref_no_edit, self.lot_no_edit, self.remarks_edit]: w.clear()
        for c in [self.requester_name_combo, self.department_combo, self.product_code_combo,
                  self.approved_by_combo]: c.setCurrentText("")
        self.quantity_edit.setText("0.00");
        self.category_combo.setCurrentIndex(0);
        self.status_combo.setCurrentText("PENDING")
        self.request_date_edit.setDate(QDate.currentDate());
        self.location_combo.setCurrentIndex(0)
        self.request_for_combo.setCurrentIndex(0);
        self.manual_ref_no_edit.setFocus()

    def _generate_req_id(self):
        prefix = f"REQ-{datetime.now().strftime('%Y%m%d')}-"
        try:
            with self.engine.connect() as conn:
                last_ref = conn.execute(
                    text("SELECT req_id FROM requisition_logbook WHERE req_id LIKE :p ORDER BY id DESC LIMIT 1"),
                    {"p": f"{prefix}%"}).scalar_one_or_none()
                return f"{prefix}{int(last_ref.split('-')[-1]) + 1:04d}" if last_ref else f"{prefix}0001"
        except Exception as e:
            trace = traceback.format_exc();
            print(f"ERROR: Could not generate Requisition ID: {e}\n{trace}")
            msg_box = QMessageBox(QMessageBox.Icon.Critical, "DB Error", f"Could not generate Requisition ID: {e}")
            msg_box.setDetailedText(trace);
            msg_box.exec();
            return None

    def _save_record(self):
        is_update = self.current_editing_req_id is not None
        req_id = self.current_editing_req_id or self._generate_req_id()
        if not req_id: return
        data = {
            "req_id": req_id, "manual_ref_no": self.manual_ref_no_edit.text(),
            "category": self.category_combo.currentText(), "request_date": self.request_date_edit.date().toPyDate(),
            "requester_name": self.requester_name_combo.currentText(),
            "department": self.department_combo.currentText(),
            "product_code": self.product_code_combo.currentText(), "lot_no": self.lot_no_edit.text(),
            "quantity_kg": self.quantity_edit.value(), "status": self.status_combo.currentText(),
            "approved_by": self.approved_by_combo.currentText(), "remarks": self.remarks_edit.text(),
            "location": self.location_combo.currentText(), "request_for": self.request_for_combo.currentText(),
            "user": self.username
        }
        if not data["product_code"]:
            QMessageBox.warning(self, "Input Error", "Product Code is a required field.");
            return

        try:
            with self.engine.connect() as conn, conn.begin():
                for value, table, column in [
                    (data['requester_name'], 'requisition_requesters', 'name'),
                    (data['department'], 'requisition_departments', 'name'),
                    (data['approved_by'], 'requisition_approvers', 'name'),
                    (data['status'], 'requisition_statuses', 'status_name')]:
                    if value:
                        conn.execute(
                            text(f"INSERT INTO {table} ({column}) VALUES (:value) ON CONFLICT ({column}) DO NOTHING"),
                            {"value": value})

                if is_update:
                    sql = text("""UPDATE requisition_logbook SET
                                  manual_ref_no=:manual_ref_no, category=:category, request_date=:request_date,
                                  requester_name=:requester_name, department=:department, product_code=:product_code,
                                  lot_no=:lot_no, quantity_kg=:quantity_kg, status=:status, approved_by=:approved_by,
                                  remarks=:remarks, location=:location, request_for=:request_for,
                                  edited_by=:user, edited_on=NOW() WHERE req_id=:req_id""")
                    action, log_action = "updated", "UPDATE_REQUISITION"
                else:
                    sql = text("""INSERT INTO requisition_logbook (req_id, manual_ref_no, category, request_date, requester_name, 
                                  department, product_code, lot_no, quantity_kg, status, approved_by, remarks, location, 
                                  request_for, encoded_by, encoded_on, edited_by, edited_on) VALUES (:req_id, :manual_ref_no, 
                                  :category, :request_date, :requester_name, :department, :product_code, :lot_no, 
                                  :quantity_kg, :status, :approved_by, :remarks, :location, :request_for, :user, NOW(), :user, NOW())""")
                    action, log_action = "saved", "CREATE_REQUISITION"
                conn.execute(sql, data)

                self._update_or_create_transaction(conn, data)

                self.log_audit_trail(log_action, f"{action.capitalize()} requisition: {req_id}")
                QMessageBox.information(self, "Success", f"Requisition has been {action}.")
                self._refresh_entry_combos()
                self._clear_form()

                # --- AUTO-REFRESH LOGIC: This block automatically refreshes the main view after a save/update ---
                self.tab_widget.setCurrentIndex(0)
                self.search_edit.clear()
                if not self.search_edit.text():
                    self._load_all_records()

        except Exception as e:
            trace = traceback.format_exc();
            print(f"ERROR: Could not save record: {e}\n{trace}")
            msg_box = QMessageBox(QMessageBox.Icon.Critical, "Database Error", f"Could not save record: {e}")
            msg_box.setDetailedText(trace);
            msg_box.exec()

    def _update_or_create_transaction(self, conn, requisition_data):
        """Within a transaction, deletes any existing transaction for the req_id and creates a new one."""
        req_id = requisition_data['req_id']
        conn.execute(text("DELETE FROM transactions WHERE source_ref_no = :req_id"), {"req_id": req_id})
        conn.execute(text("DELETE FROM failed_transactions WHERE source_ref_no = :req_id"), {"req_id": req_id})

        transaction_data = {
            "transaction_date": requisition_data['request_date'], "transaction_type": "REQUISITION",
            "source_ref_no": req_id, "product_code": requisition_data['product_code'],
            "lot_number": requisition_data['lot_no'], "quantity_out": requisition_data['quantity_kg'],
            "unit": "KG.", "warehouse": requisition_data['location'],
            "encoded_by": self.username, "remarks": requisition_data['remarks']
        }

        if requisition_data['request_for'] == 'PASSED':
            sql = text("""INSERT INTO transactions (transaction_date, transaction_type, source_ref_no, product_code, lot_number,
                                                  quantity_out, unit, warehouse, encoded_by, remarks)
                           VALUES (:transaction_date, :transaction_type, :source_ref_no, :product_code, :lot_number,
                                   :quantity_out, :unit, :warehouse, :encoded_by, :remarks)""")
            conn.execute(sql, transaction_data)
        elif requisition_data['request_for'] == 'FAILED':
            sql = text("""INSERT INTO failed_transactions (transaction_date, transaction_type, source_ref_no, product_code, lot_number,
                                                         quantity_out, unit, warehouse, encoded_by, remarks)
                           VALUES (:transaction_date, :transaction_type, :source_ref_no, :product_code, :lot_number,
                                   :quantity_out, :unit, :warehouse, :encoded_by, :remarks)""")
            conn.execute(sql, transaction_data)

    def _load_record_for_update(self):
        row = self.records_table.currentRow()
        if row < 0: return
        req_id = self.records_table.item(row, 0).text()
        try:
            with self.engine.connect() as conn:
                record = conn.execute(text("SELECT * FROM requisition_logbook WHERE req_id = :req_id"),
                                      {"req_id": req_id}).mappings().first()
            if not record: QMessageBox.warning(self, "Not Found", "Record not found."); return
            self._clear_form();
            self.current_editing_req_id = req_id
            self.req_id_edit.setText(record.get('req_id', ''));
            self.manual_ref_no_edit.setText(record.get('manual_ref_no', ''))
            self.category_combo.setCurrentText(record.get('category', ''));
            self.requester_name_combo.setCurrentText(record.get('requester_name', ''))
            self.department_combo.setCurrentText(record.get('department', ''));
            self.product_code_combo.setCurrentText(record.get('product_code', ''))
            self.lot_no_edit.setText(record.get('lot_no', ''));
            self.quantity_edit.setText(f"{record.get('quantity_kg', 0.00):.2f}")
            self.status_combo.setCurrentText(record.get('status', ''));
            self.approved_by_combo.setCurrentText(record.get('approved_by', ''))
            self.remarks_edit.setText(record.get('remarks', ''));
            self.location_combo.setCurrentText(record.get('location', ''))
            self.request_for_combo.setCurrentText(record.get('request_for', ''))
            if record.get('request_date'): self.request_date_edit.setDate(QDate(record['request_date']))
            self.save_btn.setText("Update Requisition");
            self.cancel_update_btn.show();
            self.tab_widget.setCurrentWidget(self.entry_tab)
        except Exception as e:
            trace = traceback.format_exc();
            print(f"ERROR: Could not load record for update: {e}\n{trace}")
            msg_box = QMessageBox(QMessageBox.Icon.Critical, "Error", f"Could not load record for update: {e}")
            msg_box.setDetailedText(trace);
            msg_box.exec()

    def _load_all_records(self):
        search_term = self.search_edit.text().strip()
        params = {}
        filter_clause = ""
        if search_term:
            filter_clause = "AND (req_id ILIKE :term OR manual_ref_no ILIKE :term OR product_code ILIKE :term OR lot_no ILIKE :term)"
            params['term'] = f"%{search_term}%"
        try:
            with self.engine.connect() as conn:
                count_query = text(
                    f"SELECT COUNT(*) FROM requisition_logbook WHERE is_deleted IS NOT TRUE {filter_clause}")
                self.total_records = conn.execute(count_query, params).scalar_one()
                self.total_pages = math.ceil(self.total_records / self.records_per_page) or 1
                offset = (self.current_page - 1) * self.records_per_page
                params['limit'], params['offset'] = self.records_per_page, offset
                data_query = text(f"""SELECT req_id, manual_ref_no, request_date, product_code, lot_no, 
                                          quantity_kg, status, location, request_for, edited_by, edited_on
                                      FROM requisition_logbook WHERE is_deleted IS NOT TRUE {filter_clause}
                                      ORDER BY id DESC LIMIT :limit OFFSET :offset""")
                results = conn.execute(data_query, params).mappings().all()
            headers = ["Req ID", "Manual Ref #", "Date", "Product Code", "Lot #", "Qty (kg)", "Status", "Location",
                       "For", "Last Edited By", "Last Edited On"]
            self._populate_records_table(self.records_table, headers, results)
            self._update_pagination_controls()
            self._on_record_selection_changed()
        except Exception as e:
            trace = traceback.format_exc();
            print(f"ERROR: Failed to load records: {e}\n{trace}")
            msg_box = QMessageBox(QMessageBox.Icon.Critical, "Database Error", f"Failed to load records: {e}")
            msg_box.setDetailedText(trace);
            msg_box.exec()

    def _load_deleted_records(self):
        search_term = self.deleted_search_edit.text().strip()
        params = {}
        filter_clause = ""
        if search_term:
            filter_clause = "AND (req_id ILIKE :term OR product_code ILIKE :term OR lot_no ILIKE :term)"
            params['term'] = f"%{search_term}%"
        try:
            with self.engine.connect() as conn:
                count_query = text(f"SELECT COUNT(*) FROM requisition_logbook WHERE is_deleted IS TRUE {filter_clause}")
                self.deleted_total_records = conn.execute(count_query, params).scalar_one()
                self.deleted_total_pages = math.ceil(self.deleted_total_records / self.records_per_page) or 1
                offset = (self.deleted_current_page - 1) * self.records_per_page
                params['limit'], params['offset'] = self.records_per_page, offset
                data_query = text(f"""SELECT req_id, product_code, lot_no, quantity_kg, edited_by as deleted_by, edited_on as deleted_on
                                      FROM requisition_logbook WHERE is_deleted IS TRUE {filter_clause}
                                      ORDER BY edited_on DESC LIMIT :limit OFFSET :offset""")
                results = conn.execute(data_query, params).mappings().all()
            headers = ["Req ID", "Product Code", "Lot #", "Qty (kg)", "Deleted By", "Deleted On"]
            self._populate_records_table(self.deleted_records_table, headers, results)
            self._update_deleted_pagination_controls()
        except Exception as e:
            trace = traceback.format_exc();
            print(f"ERROR: Failed to load deleted records: {e}\n{trace}")
            msg_box = QMessageBox(QMessageBox.Icon.Critical, "Database Error", f"Failed to load deleted records: {e}")
            msg_box.setDetailedText(trace);
            msg_box.exec()

    def _on_search_text_changed(self, text):
        self.current_page = 1;
        self._load_all_records()

    def _on_deleted_search_text_changed(self, text):
        self.deleted_current_page = 1;
        self._load_deleted_records()

    def _update_pagination_controls(self):
        self.page_label.setText(f"Page {self.current_page} of {self.total_pages}")
        self.prev_btn.setEnabled(self.current_page > 1);
        self.next_btn.setEnabled(self.current_page < self.total_pages)

    def _update_deleted_pagination_controls(self):
        self.deleted_page_label.setText(f"Page {self.deleted_current_page} of {self.deleted_total_pages}")
        self.deleted_prev_btn.setEnabled(self.deleted_current_page > 1)
        self.deleted_next_btn.setEnabled(self.deleted_current_page < self.deleted_total_pages)

    def _go_to_prev_page(self):
        if self.current_page > 1: self.current_page -= 1; self._load_all_records()

    def _go_to_next_page(self):
        if self.current_page < self.total_pages: self.current_page += 1; self._load_all_records()

    def _go_to_deleted_prev_page(self):
        if self.deleted_current_page > 1: self.deleted_current_page -= 1; self._load_deleted_records()

    def _go_to_deleted_next_page(self):
        if self.deleted_current_page < self.deleted_total_pages: self.deleted_current_page += 1; self._load_deleted_records()

    def _populate_records_table(self, table, headers, data):
        table.setRowCount(0);
        table.setColumnCount(len(headers));
        table.setHorizontalHeaderLabels(headers)
        if not data: return
        table.setRowCount(len(data))
        keys_in_order = [h.lower().replace(' ', '_').replace('#', 'no').replace('last_edited_by', 'edited_by').replace(
            'last_edited_on', 'edited_on').replace('for', 'request_for') for h in headers]
        for row_idx, record in enumerate(data):
            for col_idx, key in enumerate(keys_in_order):
                value = record.get(key)
                if isinstance(value, (Decimal, float)):
                    text_val = f"{value:.2f}"
                elif isinstance(value, (date, datetime)):
                    text_val = value.strftime('%Y-%m-%d %H:%M')
                else:
                    text_val = str(value or '')
                item = QTableWidgetItem(text_val)
                if key in ('quantity_kg',): item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(row_idx, col_idx, item)
        table.resizeColumnsToContents()
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    def _show_selected_record_in_view_tab(self):
        row = self.records_table.currentRow()
        if row < 0: return
        req_id = self.records_table.item(row, 0).text()
        try:
            with self.engine.connect() as conn:
                record = conn.execute(text("SELECT * FROM requisition_logbook WHERE req_id = :req_id"),
                                      {"req_id": req_id}).mappings().first()
            if not record: QMessageBox.warning(self, "Not Found", "Record not found."); return
            while self.view_details_layout.count(): self.view_details_layout.takeAt(0).widget().deleteLater()
            for key, value in record.items():
                if key in ['id', 'is_deleted']: continue
                label = key.replace('_', ' ').title()
                display_value = value.strftime('%Y-%m-%d %H:%M') if isinstance(value, (
                    datetime, date)) else f"{value:.2f}" if isinstance(value, (Decimal, float)) else str(value or 'N/A')
                self.view_details_layout.addRow(QLabel(f"<b>{label}:</b>"), QLabel(display_value))
        except Exception as e:
            trace = traceback.format_exc();
            print(f"ERROR: Could not load details: {e}\n{trace}")
            msg_box = QMessageBox(QMessageBox.Icon.Critical, "Error", f"Could not load details: {e}")
            msg_box.setDetailedText(trace);
            msg_box.exec()

    def _on_record_selection_changed(self):
        is_selected = bool(self.records_table.selectionModel().selectedRows())
        self.update_btn.setEnabled(is_selected);
        self.delete_btn.setEnabled(is_selected)
        self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.view_details_tab), is_selected)
        if not is_selected and self.tab_widget.currentIndex() == self.tab_widget.indexOf(self.view_details_tab):
            self.tab_widget.setCurrentIndex(0)

    def _show_records_table_context_menu(self, pos):
        if not self.records_table.selectedItems(): return
        menu = QMenu()
        view_action = menu.addAction("View Details");
        edit_action = menu.addAction("Load for Update");
        delete_action = menu.addAction("Delete Record")
        action = menu.exec(self.records_table.mapToGlobal(pos))
        if action == view_action:
            self._show_selected_record_in_view_tab();
            self.tab_widget.setCurrentWidget(self.view_details_tab)
        elif action == edit_action:
            self._load_record_for_update()
        elif action == delete_action:
            self._delete_record()

    def _delete_record(self):
        row = self.records_table.currentRow()
        if row < 0: return
        req_id = self.records_table.item(row, 0).text()
        reply = QMessageBox.question(self, "Confirm Deletion",
                                     f"Are you sure you want to delete requisition <b>{req_id}</b>?\nThis will also remove its corresponding inventory transaction.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                with self.engine.connect() as conn, conn.begin():
                    conn.execute(text(
                        "UPDATE requisition_logbook SET is_deleted = TRUE, edited_by = :user, edited_on = NOW() WHERE req_id = :req_id"),
                        {"req_id": req_id, "user": self.username})
                    conn.execute(text("DELETE FROM transactions WHERE source_ref_no = :req_id"), {"req_id": req_id})
                    conn.execute(text("DELETE FROM failed_transactions WHERE source_ref_no = :req_id"),
                                 {"req_id": req_id})
                self.log_audit_trail("DELETE_REQUISITION",
                                     f"Soft-deleted requisition and removed transaction for: {req_id}")
                QMessageBox.information(self, "Success", f"Requisition {req_id} has been deleted.")
                self._load_all_records()
            except Exception as e:
                trace = traceback.format_exc();
                print(f"ERROR: Failed to delete record: {e}\n{trace}")
                msg_box = QMessageBox(QMessageBox.Icon.Critical, "Database Error", f"Failed to delete record: {e}")
                msg_box.setDetailedText(trace);
                msg_box.exec()

    def _restore_record(self):
        row = self.deleted_records_table.currentRow()
        if row < 0: return
        req_id = self.deleted_records_table.item(row, 0).text()
        reply = QMessageBox.question(self, "Confirm Restore",
                                     f"Are you sure you want to restore requisition <b>{req_id}</b>?\nThis will re-create its inventory transaction.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                with self.engine.connect() as conn, conn.begin():
                    conn.execute(text(
                        "UPDATE requisition_logbook SET is_deleted = FALSE, edited_by = :user, edited_on = NOW() WHERE req_id = :req_id"),
                        {"req_id": req_id, "user": self.username})

                    restored_data = conn.execute(text("SELECT * FROM requisition_logbook WHERE req_id = :req_id"),
                                                 {"req_id": req_id}).mappings().first()
                    if not restored_data:
                        raise Exception("Failed to retrieve restored record data.")

                    self._update_or_create_transaction(conn, restored_data)

                self.log_audit_trail("RESTORE_REQUISITION",
                                     f"Restored requisition and re-created transaction for: {req_id}")
                QMessageBox.information(self, "Success", f"Requisition {req_id} has been restored.")
                self._load_deleted_records()
                self._load_all_records()
            except Exception as e:
                trace = traceback.format_exc();
                print(f"ERROR: Failed to restore record: {e}\n{trace}")
                msg_box = QMessageBox(QMessageBox.Icon.Critical, "Database Error", f"Failed to restore record: {e}")
                msg_box.setDetailedText(trace);
                msg_box.exec()