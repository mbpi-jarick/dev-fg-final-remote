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

# --- Icon Imports ---
try:
    import qtawesome as fa
except ImportError:
    print("WARNING: qtawesome library not found. 'Add' buttons will not have icons.")
    fa = None

# --- HELPER CLASSES ---

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
        self.current_page, self.records_per_page = 1, 200
        self.total_records, self.total_pages = 0, 1
        self.init_ui()
        self._load_all_records()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        view_tab = QWidget()
        self.view_details_tab, self.entry_tab = QWidget(), QWidget()

        self.tab_widget.addTab(view_tab, "All Requisitions")
        self.tab_widget.addTab(self.view_details_tab, "View Requisition Details")
        self.tab_widget.addTab(self.entry_tab, "Requisition Entry")

        self._setup_view_tab(view_tab)
        self._setup_view_details_tab(self.view_details_tab)
        self._setup_entry_tab(self.entry_tab)

        self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.view_details_tab), False)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

    def _setup_view_tab(self, tab):
        layout = QVBoxLayout(tab); top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("Search:")); self.search_edit = UpperCaseLineEdit(placeholderText="Filter by Req ID, Ref#, Product, Lot...")
        top_layout.addWidget(self.search_edit, 1); self.update_btn = QPushButton("Load Selected for Update")
        self.update_btn.setObjectName("InfoButton"); self.delete_btn = QPushButton("Delete Selected"); self.delete_btn.setObjectName("DangerButton")
        top_layout.addWidget(self.update_btn); top_layout.addWidget(self.delete_btn); layout.addLayout(top_layout)
        self.records_table = QTableWidget(); self.records_table.setFocusPolicy(Qt.FocusPolicy.NoFocus); self.records_table.setShowGrid(False)
        self.records_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers); self.records_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.records_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection); self.records_table.verticalHeader().setVisible(False)
        self.records_table.horizontalHeader().setHighlightSections(False); self.records_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.records_table.customContextMenuRequested.connect(self._show_records_table_context_menu); layout.addWidget(self.records_table)
        pagination_layout = QHBoxLayout(); self.prev_btn, self.next_btn = QPushButton("<< Previous"), QPushButton("Next >>")
        self.page_label = QLabel("Page 1 of 1"); pagination_layout.addStretch(); pagination_layout.addWidget(self.prev_btn)
        pagination_layout.addWidget(self.page_label); pagination_layout.addWidget(self.next_btn); pagination_layout.addStretch()
        layout.addLayout(pagination_layout); self.search_edit.textChanged.connect(self._on_search_text_changed)
        self.update_btn.clicked.connect(self._load_record_for_update); self.delete_btn.clicked.connect(self._delete_record)
        self.records_table.itemSelectionChanged.connect(self._on_record_selection_changed); self.records_table.doubleClicked.connect(self._load_record_for_update)
        self.prev_btn.clicked.connect(self._go_to_prev_page); self.next_btn.clicked.connect(self._go_to_next_page)
        self._on_record_selection_changed()

    def _setup_entry_tab(self, tab):
        layout = QVBoxLayout(tab)
        form_group = QGroupBox("Requisition Details"); layout.addWidget(form_group)
        form_layout = QGridLayout(form_group)

        # --- Widgets ---
        self.req_id_edit = QLineEdit(readOnly=True, placeholderText="Auto-generated")
        self.manual_ref_no_edit = UpperCaseLineEdit()
        self.category_combo = QComboBox(); self.category_combo.addItems(["MB", "DC"])
        self.request_date_edit = QDateEdit(calendarPopup=True, displayFormat="yyyy-MM-dd")
        self.requester_name_combo = QComboBox(); self.department_combo = QComboBox()
        self.product_code_combo = QComboBox(); self.approved_by_combo = QComboBox()
        self.status_combo = QComboBox(); self.lot_no_edit = UpperCaseLineEdit()
        self.quantity_edit = FloatLineEdit(); self.remarks_edit = UpperCaseLineEdit()

        self._configure_combobox(self.requester_name_combo, editable=True)
        self._configure_combobox(self.department_combo, editable=True)
        self._configure_combobox(self.product_code_combo, editable=True)
        self._configure_combobox(self.approved_by_combo, editable=True)
        self._configure_combobox(self.status_combo, editable=True)
        self._refresh_entry_combos()

        # --- Create Combo with Add Button Widgets ---
        requester_widget = self._create_combo_with_add_button(self.requester_name_combo, self._on_add_requester)
        department_widget = self._create_combo_with_add_button(self.department_combo, self._on_add_department)
        approved_by_widget = self._create_combo_with_add_button(self.approved_by_combo, self._on_add_approver)

        # --- Layout ---
        form_layout.addWidget(QLabel("Requisition ID:"), 0, 0); form_layout.addWidget(self.req_id_edit, 0, 1)
        form_layout.addWidget(QLabel("Manual Ref #:"), 0, 2); form_layout.addWidget(self.manual_ref_no_edit, 0, 3)
        form_layout.addWidget(QLabel("Request Date:"), 1, 0); form_layout.addWidget(self.request_date_edit, 1, 1)
        form_layout.addWidget(QLabel("Category:"), 1, 2); form_layout.addWidget(self.category_combo, 1, 3)
        form_layout.addWidget(QLabel("Requester Name:"), 2, 0); form_layout.addWidget(requester_widget, 2, 1)
        form_layout.addWidget(QLabel("Department:"), 2, 2); form_layout.addWidget(department_widget, 2, 3)
        form_layout.addWidget(QLabel("Product Code:"), 3, 0); form_layout.addWidget(self.product_code_combo, 3, 1)
        form_layout.addWidget(QLabel("Lot #:"), 3, 2); form_layout.addWidget(self.lot_no_edit, 3, 3)
        form_layout.addWidget(QLabel("Quantity (kg):"), 4, 0); form_layout.addWidget(self.quantity_edit, 4, 1)
        form_layout.addWidget(QLabel("Status:"), 4, 2); form_layout.addWidget(self.status_combo, 4, 3)
        form_layout.addWidget(QLabel("Approved By:"), 5, 0); form_layout.addWidget(approved_by_widget, 5, 1)
        form_layout.addWidget(QLabel("Remarks:"), 5, 2); form_layout.addWidget(self.remarks_edit, 5, 3)

        layout.addStretch()
        button_layout = QHBoxLayout()
        self.save_btn = QPushButton("Save Requisition"); self.save_btn.setObjectName("PrimaryButton")
        self.clear_btn = QPushButton("New"); self.clear_btn.setObjectName("SecondaryButton")
        self.cancel_update_btn = QPushButton("Cancel Update"); self.cancel_update_btn.setObjectName("DangerButton")
        button_layout.addStretch(); button_layout.addWidget(self.cancel_update_btn)
        button_layout.addWidget(self.clear_btn); button_layout.addWidget(self.save_btn)
        layout.addLayout(button_layout)

        self.save_btn.clicked.connect(self._save_record)
        self.clear_btn.clicked.connect(self._clear_form)
        self.cancel_update_btn.clicked.connect(self._clear_form)
        self._clear_form()

    def _create_combo_with_add_button(self, combo: QComboBox, on_add_method):
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(5)
        layout.addWidget(combo, 1)
        add_btn = QPushButton()
        add_btn.setObjectName("SecondaryButton")
        if fa: add_btn.setIcon(fa.icon('fa5s.plus', color='white'))
        else: add_btn.setText("+")
        add_btn.setFixedSize(30, 30)
        add_btn.setToolTip("Add a new value to the list")
        add_btn.clicked.connect(on_add_method)
        layout.addWidget(add_btn)
        return container

    def _on_add_requester(self): self._add_new_lookup_value(self.requester_name_combo, "Requester", 'requisition_requesters', 'name')
    def _on_add_department(self): self._add_new_lookup_value(self.department_combo, "Department", 'requisition_departments', 'name')
    def _on_add_approver(self): self._add_new_lookup_value(self.approved_by_combo, "Approver", 'requisition_approvers', 'name')

    def _add_new_lookup_value(self, combo_widget, dialog_title, table_name, column_name):
        dialog = AddNewValueDialog(self, f"Add New {dialog_title}", f"Enter new {dialog_title.lower()} name:")
        if dialog.exec():
            new_value = dialog.get_value()
            if not new_value: return
            try:
                with self.engine.connect() as conn, conn.begin():
                    sql = text(f"INSERT INTO {table_name} ({column_name}) VALUES (:value) ON CONFLICT ({column_name}) DO NOTHING")
                    conn.execute(sql, {"value": new_value})
                self._populate_combo(combo_widget, table_name, column_name)
                combo_widget.setCurrentText(new_value)
            except Exception as e:
                trace = traceback.format_exc()
                print(f"ERROR: Could not add new lookup value: {e}\n{trace}")
                msg_box = QMessageBox(QMessageBox.Icon.Critical, "Database Error", f"Could not save new {dialog_title.lower()}: {e}")
                msg_box.setDetailedText(trace); msg_box.exec()

    def _configure_combobox(self, combo: QComboBox, editable: bool = False):
        combo.setEditable(editable)
        if editable:
            line_edit = UpperCaseLineEdit(self); line_edit.setFont(self.font())
            combo.setLineEdit(line_edit); combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
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
                query = text(f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL AND {column} != '' ORDER BY {column}")
                results = conn.execute(query).scalars().all()
            combo.blockSignals(True)
            combo.clear()
            if table == 'requisition_statuses' and not results: results = ["PENDING", "APPROVED", "COMPLETED", "REJECTED"]
            combo.addItems(results)
            combo.blockSignals(False)
            combo.setCurrentText(current_text)
            if combo.lineEdit(): combo.lineEdit().setPlaceholderText("SELECT OR TYPE...")
        except Exception as e:
            trace = traceback.format_exc()
            print(f"Warning: Could not populate combobox from {table}.{column}: {e}\n{trace}")
            if table == 'requisition_statuses': combo.addItems(["PENDING", "APPROVED", "COMPLETED", "REJECTED"])

    def _setup_view_details_tab(self, tab):
        layout = QVBoxLayout(tab)
        details_group = QGroupBox("Requisition Details (Read-Only)")
        self.view_details_layout = QFormLayout(details_group)
        layout.addWidget(details_group); layout.addStretch()

    def _on_tab_changed(self, index):
        tab_text = self.tab_widget.tabText(index)
        if tab_text == "View Requisition Details": self._show_selected_record_in_view_tab()
        elif tab_text == "Requisition Entry": self._refresh_entry_combos()

    def _clear_form(self):
        self.current_editing_req_id = None
        self.cancel_update_btn.hide(); self.save_btn.setText("Save Requisition")
        for w in [self.req_id_edit, self.manual_ref_no_edit, self.lot_no_edit, self.remarks_edit]: w.clear()
        for c in [self.requester_name_combo, self.department_combo, self.product_code_combo, self.approved_by_combo]: c.setCurrentText("")
        self.quantity_edit.setText("0.00"); self.category_combo.setCurrentIndex(0)
        self.status_combo.setCurrentText("PENDING"); self.request_date_edit.setDate(QDate.currentDate())
        self.manual_ref_no_edit.setFocus()

    def _generate_req_id(self):
        prefix = f"REQ-{datetime.now().strftime('%Y%m%d')}-"
        try:
            with self.engine.connect() as conn:
                last_ref = conn.execute(text("SELECT req_id FROM requisition_logbook WHERE req_id LIKE :p ORDER BY id DESC LIMIT 1"), {"p": f"{prefix}%"}).scalar_one_or_none()
                if last_ref:
                    last_num = int(last_ref.split('-')[-1])
                    return f"{prefix}{last_num + 1:04d}"
                return f"{prefix}0001"
        except Exception as e:
            trace = traceback.format_exc()
            print(f"ERROR: Could not generate Requisition ID: {e}\n{trace}")
            msg_box = QMessageBox(QMessageBox.Icon.Critical, "DB Error", f"Could not generate Requisition ID: {e}")
            msg_box.setDetailedText(trace); msg_box.exec(); return None

    def _save_record(self):
        is_update = self.current_editing_req_id is not None
        req_id = self.current_editing_req_id or self._generate_req_id()
        if not req_id: return
        data = {
            "req_id": req_id, "manual_ref_no": self.manual_ref_no_edit.text(),
            "category": self.category_combo.currentText(), "request_date": self.request_date_edit.date().toPyDate(),
            "requester_name": self.requester_name_combo.currentText(), "department": self.department_combo.currentText(),
            "product_code": self.product_code_combo.currentText(), "lot_no": self.lot_no_edit.text(),
            "quantity_kg": self.quantity_edit.value(), "status": self.status_combo.currentText(),
            "approved_by": self.approved_by_combo.currentText(), "remarks": self.remarks_edit.text(),
            "user": self.username
        }
        if not data["product_code"]:
            QMessageBox.warning(self, "Input Error", "Product Code is a required field."); return
        lookups_to_add = [
            (data['requester_name'], 'requisition_requesters', 'name'),
            (data['department'], 'requisition_departments', 'name'),
            (data['approved_by'], 'requisition_approvers', 'name'),
            (data['status'], 'requisition_statuses', 'status_name'),
        ]
        try:
            with self.engine.connect() as conn, conn.begin():
                for value, table, column in lookups_to_add:
                    if value:
                        add_sql = text(f"INSERT INTO {table} ({column}) VALUES (:value) ON CONFLICT ({column}) DO NOTHING")
                        conn.execute(add_sql, {"value": value})
                if is_update:
                    sql = text("""UPDATE requisition_logbook SET
                                  manual_ref_no=:manual_ref_no, category=:category, request_date=:request_date,
                                  requester_name=:requester_name, department=:department, product_code=:product_code,
                                  lot_no=:lot_no, quantity_kg=:quantity_kg, status=:status, approved_by=:approved_by,
                                  remarks=:remarks, edited_by=:user, edited_on=NOW()
                                  WHERE req_id=:req_id""")
                    conn.execute(sql, data)
                    action, log_action = "updated", "UPDATE_REQUISITION"
                else:
                    sql = text("""INSERT INTO requisition_logbook (req_id, manual_ref_no, category, request_date,
                                  requester_name, department, product_code, lot_no, quantity_kg, status, approved_by,
                                  remarks, encoded_by, encoded_on, edited_by, edited_on) VALUES (:req_id, :manual_ref_no,
                                  :category, :request_date, :requester_name, :department, :product_code, :lot_no,
                                  :quantity_kg, :status, :approved_by, :remarks, :user, NOW(), :user, NOW())""")
                    conn.execute(sql, data)
                    action, log_action = "saved", "CREATE_REQUISITION"
                self.log_audit_trail(log_action, f"{action.capitalize()} requisition: {req_id}")
                QMessageBox.information(self, "Success", f"Requisition has been {action}.")
                self._refresh_entry_combos(); self._clear_form(); self._load_all_records()
                self.tab_widget.setCurrentIndex(0) # Index 0 is now "All Requisitions"
        except Exception as e:
            trace = traceback.format_exc(); print(f"ERROR: Could not save record: {e}\n{trace}")
            msg_box = QMessageBox(QMessageBox.Icon.Critical, "Database Error", f"Could not save record: {e}")
            msg_box.setDetailedText(trace); msg_box.exec()

    def _load_record_for_update(self):
        row = self.records_table.currentRow()
        if row < 0: return
        req_id = self.records_table.item(row, 0).text()
        try:
            with self.engine.connect() as conn:
                record = conn.execute(text("SELECT * FROM requisition_logbook WHERE req_id = :req_id"), {"req_id": req_id}).mappings().first()
            if not record: QMessageBox.warning(self, "Not Found", "Record not found."); return
            self._clear_form()
            self.current_editing_req_id = req_id
            self.req_id_edit.setText(record.get('req_id', '')); self.manual_ref_no_edit.setText(record.get('manual_ref_no', ''))
            self.category_combo.setCurrentText(record.get('category', ''))
            if record.get('request_date'): self.request_date_edit.setDate(QDate(record['request_date']))
            self.requester_name_combo.setCurrentText(record.get('requester_name', '')); self.department_combo.setCurrentText(record.get('department', ''))
            self.product_code_combo.setCurrentText(record.get('product_code', '')); self.lot_no_edit.setText(record.get('lot_no', ''))
            self.quantity_edit.setText(f"{record.get('quantity_kg', 0.00):.2f}"); self.status_combo.setCurrentText(record.get('status', ''))
            self.approved_by_combo.setCurrentText(record.get('approved_by', '')); self.remarks_edit.setText(record.get('remarks', ''))
            self.save_btn.setText("Update Requisition"); self.cancel_update_btn.show(); self.tab_widget.setCurrentWidget(self.entry_tab)
        except Exception as e:
            trace = traceback.format_exc(); print(f"ERROR: Could not load record for update: {e}\n{trace}")
            msg_box = QMessageBox(QMessageBox.Icon.Critical, "Error", f"Could not load record for update: {e}")
            msg_box.setDetailedText(trace); msg_box.exec()

    def _load_all_records(self):
        search_term = self.search_edit.text().strip()
        params = {}; filter_clause = ""
        if search_term:
            filter_clause = "AND (req_id ILIKE :term OR manual_ref_no ILIKE :term OR product_code ILIKE :term OR lot_no ILIKE :term)"
            params['term'] = f"%{search_term}%"
        try:
            with self.engine.connect() as conn:
                count_query = text(f"SELECT COUNT(*) FROM requisition_logbook WHERE is_deleted IS NOT TRUE {filter_clause}")
                self.total_records = conn.execute(count_query, params).scalar_one()
                self.total_pages = math.ceil(self.total_records / self.records_per_page) or 1
                offset = (self.current_page - 1) * self.records_per_page
                params['limit'], params['offset'] = self.records_per_page, offset
                data_query = text(f"""SELECT req_id, manual_ref_no, request_date, product_code, lot_no, quantity_kg, status
                                      FROM requisition_logbook WHERE is_deleted IS NOT TRUE {filter_clause}
                                      ORDER BY id DESC LIMIT :limit OFFSET :offset""")
                results = conn.execute(data_query, params).mappings().all()
            headers = ["Req ID", "Manual Ref #", "Date", "Product Code", "Lot #", "Qty (kg)", "Status"]
            self._populate_records_table(self.records_table, headers, results)
            self._update_pagination_controls(); self._on_record_selection_changed()
        except Exception as e:
            trace = traceback.format_exc(); print(f"ERROR: Failed to load records: {e}\n{trace}")
            msg_box = QMessageBox(QMessageBox.Icon.Critical, "Database Error", f"Failed to load records: {e}")
            msg_box.setDetailedText(trace); msg_box.exec()

    def _on_search_text_changed(self, text): self.current_page = 1; self._load_all_records()
    def _update_pagination_controls(self):
        self.page_label.setText(f"Page {self.current_page} of {self.total_pages}")
        self.prev_btn.setEnabled(self.current_page > 1); self.next_btn.setEnabled(self.current_page < self.total_pages)
    def _go_to_prev_page(self):
        if self.current_page > 1: self.current_page -= 1; self._load_all_records()
    def _go_to_next_page(self):
        if self.current_page < self.total_pages: self.current_page += 1; self._load_all_records()
    def _populate_records_table(self, table, headers, data):
        table.setRowCount(0); table.setColumnCount(len(headers)); table.setHorizontalHeaderLabels(headers)
        if not data: return
        table.setRowCount(len(data))
        keys_in_order = ['req_id', 'manual_ref_no', 'request_date', 'product_code', 'lot_no', 'quantity_kg', 'status']
        for row_idx, record in enumerate(data):
            for col_idx, key in enumerate(keys_in_order):
                value = record[key]
                if isinstance(value, (Decimal, float)): text_val = f"{value:.2f}"
                elif isinstance(value, date): text_val = value.strftime('%Y-%m-%d')
                else: text_val = str(value or '')
                item = QTableWidgetItem(text_val)
                if key == 'quantity_kg': item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(row_idx, col_idx, item)
        table.resizeColumnsToContents(); table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    def _show_selected_record_in_view_tab(self):
        row = self.records_table.currentRow()
        if row < 0: return
        req_id = self.records_table.item(row, 0).text()
        try:
            with self.engine.connect() as conn:
                record = conn.execute(text("SELECT * FROM requisition_logbook WHERE req_id = :req_id"), {"req_id": req_id}).mappings().first()
            if not record: QMessageBox.warning(self, "Not Found", "Record not found."); return
            while self.view_details_layout.count(): self.view_details_layout.takeAt(0).widget().deleteLater()
            for key, value in record.items():
                if key in ['id', 'is_deleted']: continue
                label = key.replace('_', ' ').title()
                if isinstance(value, (datetime, date)): display_value = value.strftime('%Y-%m-%d %H:%M')
                elif isinstance(value, (Decimal, float)): display_value = f"{value:.2f}"
                else: display_value = str(value or 'N/A')
                self.view_details_layout.addRow(QLabel(f"<b>{label}:</b>"), QLabel(display_value))
        except Exception as e:
            trace = traceback.format_exc(); print(f"ERROR: Could not load details: {e}\n{trace}")
            msg_box = QMessageBox(QMessageBox.Icon.Critical, "Error", f"Could not load details: {e}"); msg_box.setDetailedText(trace); msg_box.exec()

    def _on_record_selection_changed(self):
        is_selected = bool(self.records_table.selectionModel().selectedRows())
        self.update_btn.setEnabled(is_selected); self.delete_btn.setEnabled(is_selected)
        self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.view_details_tab), is_selected)
        if not is_selected and self.tab_widget.currentIndex() == self.tab_widget.indexOf(self.view_details_tab):
            self.tab_widget.setCurrentIndex(0) # Index 0 is now "All Requisitions"

    def _show_records_table_context_menu(self, pos):
        if not self.records_table.selectedItems(): return
        menu = QMenu(); view_action = menu.addAction("View Details"); edit_action = menu.addAction("Load for Update"); delete_action = menu.addAction("Delete Record")
        action = menu.exec(self.records_table.mapToGlobal(pos))
        if action == view_action: self._show_selected_record_in_view_tab(); self.tab_widget.setCurrentWidget(self.view_details_tab)
        elif action == edit_action: self._load_record_for_update()
        elif action == delete_action: self._delete_record()

    def _delete_record(self):
        row = self.records_table.currentRow()
        if row < 0: return
        req_id = self.records_table.item(row, 0).text()
        reply = QMessageBox.question(self, "Confirm Deletion", f"Are you sure you want to delete requisition <b>{req_id}</b>?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                with self.engine.connect() as conn, conn.begin():
                    conn.execute(text("UPDATE requisition_logbook SET is_deleted = TRUE, edited_by = :user, edited_on = NOW() WHERE req_id = :req_id"), {"req_id": req_id, "user": self.username})
                self.log_audit_trail("DELETE_REQUISITION", f"Soft-deleted requisition: {req_id}")
                QMessageBox.information(self, "Success", f"Requisition {req_id} has been deleted.")
                self._load_all_records()
            except Exception as e:
                trace = traceback.format_exc(); print(f"ERROR: Failed to delete record: {e}\n{trace}")
                msg_box = QMessageBox(QMessageBox.Icon.Critical, "Database Error", f"Failed to delete record: {e}"); msg_box.setDetailedText(trace); msg_box.exec()