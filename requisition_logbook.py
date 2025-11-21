import sys
import traceback
import math
import qtawesome as fa
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from functools import partial
from typing import Any

# --- PyQt6 Imports ---
from PyQt6.QtCore import Qt, QDate, QSize
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QTabWidget, QFormLayout, QLineEdit,
                             QComboBox, QDateEdit, QPushButton, QTableWidget, QTableWidgetItem,
                             QAbstractItemView, QHeaderView, QMessageBox, QHBoxLayout, QLabel,
                             QDialog, QDialogButtonBox,
                             QGridLayout, QGroupBox, QMenu, QSplitter, QCompleter)
from PyQt6.QtGui import QDoubleValidator

# --- Database Imports ---
from sqlalchemy import create_engine, text, inspect


# --- DUMMY DEPENDENCIES ---
def mock_log_audit_trail(action, description):
    print(f"[AUDIT TRAIL] User: STANDALONE_USER | Action: {action} | Desc: {description}")


def setup_in_memory_db():
    engine = create_engine("sqlite:///:memory:")
    print("Setting up in-memory database schema...")
    with engine.connect() as conn, conn.begin():
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS requisition_logbook (
                id INTEGER PRIMARY KEY, req_id TEXT UNIQUE NOT NULL, manual_ref_no TEXT, category TEXT,
                request_date DATE, requester_name TEXT, department TEXT, product_code TEXT NOT NULL,
                lot_no TEXT, quantity_kg REAL, status TEXT, approved_by TEXT, remarks TEXT, location TEXT,
                request_for TEXT, encoded_by TEXT, encoded_on TIMESTAMP, edited_by TEXT, edited_on TIMESTAMP,
                is_deleted BOOLEAN DEFAULT FALSE
            )
        """))
        conn.execute(text("CREATE TABLE IF NOT EXISTS requisition_requesters (name TEXT UNIQUE)"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS requisition_departments (name TEXT UNIQUE)"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS requisition_approvers (name TEXT UNIQUE)"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS requisition_statuses (status_name TEXT UNIQUE)"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS legacy_production (prod_code TEXT UNIQUE)"))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY, transaction_date DATE, transaction_type TEXT, source_ref_no TEXT,
                product_code TEXT, lot_number TEXT, quantity_out REAL, unit TEXT, warehouse TEXT, encoded_by TEXT, remarks TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS failed_transactions (
                id INTEGER PRIMARY KEY, transaction_date DATE, transaction_type TEXT, source_ref_no TEXT,
                product_code TEXT, lot_number TEXT, quantity_out REAL, unit TEXT, warehouse TEXT, encoded_by TEXT, remarks TEXT
            )
        """))

        initial_requesters = ["JOHN DOE", "JANE SMITH", "ALICE JOHNSON"]
        initial_departments = ["QC", "R&D", "PRODUCTION"]
        initial_approvers = ["MR. CEO", "MS. MANAGER"]
        initial_products = ["PC-100", "PC-200", "PC-RAW-A"]
        initial_statuses = ["PENDING", "APPROVED", "COMPLETED", "REJECTED"]

        for val in initial_requesters: conn.execute(
            text("INSERT INTO requisition_requesters (name) VALUES (:val) ON CONFLICT(name) DO NOTHING"), {"val": val})
        for val in initial_departments: conn.execute(
            text("INSERT INTO requisition_departments (name) VALUES (:val) ON CONFLICT(name) DO NOTHING"), {"val": val})
        for val in initial_approvers: conn.execute(
            text("INSERT INTO requisition_approvers (name) VALUES (:val) ON CONFLICT(name) DO NOTHING"), {"val": val})
        for val in initial_products: conn.execute(
            text("INSERT INTO legacy_production (prod_code) VALUES (:val) ON CONFLICT(prod_code) DO NOTHING"),
            {"val": val})
        for val in initial_statuses: conn.execute(
            text("INSERT INTO requisition_statuses (status_name) VALUES (:val) ON CONFLICT(status_name) DO NOTHING"),
            {"val": val})
        conn.commit()
    return engine


# --- HELPER CLASSES ---
def format_float_with_commas(value: Any, decimals: int = 2) -> str:
    if value is None or value == '': return f"0.{'0' * decimals}"
    try:
        if isinstance(value, str):
            value = float(value.replace(',', ''))
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
        self.blockSignals(True);
        self.setText(text.upper());
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
            self.setText(format_float_with_commas(self.text().replace(',', '') or 0.0))
        except ValueError:
            self.setText("0.00")

    def value(self) -> float:
        try:
            return float(self.text().replace(',', '') or 0.0)
        except ValueError:
            return 0.0


class AddNewValueDialog(QDialog):
    def __init__(self, parent=None, title="Add New Value", label_text="Value:"):
        super().__init__(parent)
        self.setWindowTitle(title);
        self.setMinimumWidth(350)
        layout = QVBoxLayout(self);
        layout.addWidget(QLabel(label_text));
        self.value_edit = UpperCaseLineEdit()
        layout.addWidget(self.value_edit)
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept);
        button_box.rejected.connect(self.reject);
        layout.addWidget(button_box)

    def get_value(self): return self.value_edit.text().strip()


# --- MAIN PAGE WIDGET (RequisitionLogbookPage) ---
class RequisitionLogbookPage(QWidget):
    PRIMARY_ACCENT_COLOR = "#3a506b"

    def __init__(self, db_engine, username, log_audit_trail_func):
        super().__init__()
        self.engine, self.username, self.log_audit_trail = db_engine, username, log_audit_trail_func
        self.current_editing_req_id = None;
        self.current_page, self.records_per_page = 1, 200
        self.total_records, self.total_pages = 0, 1
        self.deleted_current_page, self.deleted_total_records, self.deleted_total_pages = 1, 0, 1
        self.init_ui()
        self._load_all_records()
        # Install event filter for the main widget
        self.installEventFilter(self)

    def _create_instruction_box(self, text):
        instruction_box = QGroupBox("Instructions");
        instruction_layout = QHBoxLayout(instruction_box)
        icon_label = QLabel();
        icon_label.setPixmap(fa.icon('fa5s.info-circle', color='#17A2B8').pixmap(QSize(24, 24)))
        text_label = QLabel(text);
        text_label.setWordWrap(True)
        instruction_layout.addWidget(icon_label);
        instruction_layout.addWidget(text_label, 1)
        instruction_box.setStyleSheet(
            "QGroupBox { border: 1px solid #17A2B8; border-radius: 5px; margin-top: 5px; padding-top: 15px; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px 0 3px; color: #17A2B8; font-weight: bold; }")
        return instruction_box

    def init_ui(self):
        main_layout = QVBoxLayout(self);
        header_widget = QWidget(objectName="HeaderWidget");
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 10);
        icon_pixmap = fa.icon('fa5s.list-alt', color="#3a506b").pixmap(QSize(28, 28))
        icon_label = QLabel();
        icon_label.setPixmap(icon_pixmap);
        header_layout.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignLeft)
        header_label = QLabel("REQUISITION LOGBOOK", objectName="PageHeader");
        header_layout.addWidget(header_label);
        header_layout.addStretch()
        main_layout.addWidget(header_widget);
        self.tab_widget = QTabWidget();
        main_layout.addWidget(self.tab_widget)
        view_tab, self.view_details_tab, self.entry_tab, self.deleted_tab = QWidget(), QWidget(), QWidget(), QWidget()
        self.tab_widget.addTab(view_tab, fa.icon('fa5s.list-alt'), "All Requisitions");
        self.tab_widget.addTab(self.view_details_tab, fa.icon('fa5s.search'), "View Requisition Details")
        self.tab_widget.addTab(self.entry_tab, fa.icon('fa5s.edit'), "Requisition Entry");
        self.tab_widget.addTab(self.deleted_tab, fa.icon('fa5s.archive'), "Deleted Records")
        self._setup_view_tab(view_tab);
        self._setup_view_details_tab(self.view_details_tab);
        self._setup_entry_tab(self.entry_tab);
        self._setup_deleted_tab(self.deleted_tab)
        self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.view_details_tab), False);
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

        # Enhanced stylesheet
        stylesheet = """
            QWidget { font-size: 10pt; }
            #PrimaryButton { 
                background-color: #007BFF; color: white; border-radius: 6px; padding: 8px 16px; 
                font-weight: bold; border: none;
            } 
            #PrimaryButton:hover { background-color: #0056b3; }
            #PrimaryButton:pressed { background-color: #004085; }

            #SecondaryButton { 
                background-color: #6c757d; color: white; border-radius: 6px; padding: 8px 16px;
                font-weight: bold; border: none;
            } 
            #SecondaryButton:hover { background-color: #545b62; }

            #DestructiveButton { 
                background-color: #dc3545; color: white; border-radius: 6px; padding: 8px 16px;
                font-weight: bold; border: none;
            } 
            #DestructiveButton:hover { background-color: #c82333; }

            #FormContainer {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 8px;
            }

            QLineEdit, QComboBox {
                padding: 8px;
                border: 2px solid #ced4da;
                border-radius: 4px;
                background-color: white;
                font-size: 10pt;
            }

            QLineEdit:focus, QComboBox:focus {
                border-color: #007BFF;
                background-color: #fff;
            }

            QComboBox::drop-down {
                border: none;
                width: 25px;
            }

            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #495057;
                width: 0px;
                height: 0px;
            }

            QComboBox QAbstractItemView {
                border: 1px solid #ced4da;
                border-radius: 4px;
                background-color: white;
                selection-background-color: #007BFF;
                selection-color: white;
            }

            QDateEdit::drop-down {
                border: none;
                width: 25px;
            }

            QTabWidget::pane { border: 1px solid #ccc; background: white; } 
            QTabWidget::tab-bar { left: 5px; }
            QTabBar::tab { 
                background: #f8f9fa; 
                padding: 4px 7px; 
                border: 1px solid #dee2e6; 
                border-bottom: none; 
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
            } 
            QTabBar::tab:selected { 
                background: white; 
                border-color: #ccc; 
                border-bottom: 1px solid white;
                margin-bottom: -1px;
            }
            QTabBar::tab:hover:!selected {
                background: #e9ecef;
            }

            QLabel#PageHeader { font-size: 24px; font-weight: bold; color: #3a506b; background-color: transparent; } 
            #HeaderWidget { background-color: transparent; }
            QTableWidget::item:selected { background-color: #3a506b; color: white; }
        """
        self.setStyleSheet(stylesheet)

    def _setup_view_tab(self, tab):
        layout = QVBoxLayout(tab);
        instructions = self._create_instruction_box(
            "Use this tab to view, search, load, or delete active requisitions. Double-click a row or use 'Load Selected for Update' to edit.");
        layout.addWidget(instructions)
        top_layout = QHBoxLayout();
        top_layout.addWidget(QLabel("Search:"));
        self.search_edit = UpperCaseLineEdit(placeholderText="Filter by Req ID, Ref#, Product, Lot...");
        top_layout.addWidget(self.search_edit, 1)
        self.refresh_btn = QPushButton(fa.icon('fa5s.sync'), "Refresh");
        self.update_btn = QPushButton(fa.icon('fa5s.edit'), "Load Selected for Update");
        self.update_btn.setObjectName("PrimaryButton")
        self.delete_btn = QPushButton(fa.icon('fa5s.trash'), "Delete Selected");
        self.delete_btn.setObjectName("DestructiveButton");
        top_layout.addWidget(self.refresh_btn);
        top_layout.addWidget(self.update_btn);
        top_layout.addWidget(self.delete_btn);
        layout.addLayout(top_layout)
        self.records_table = QTableWidget()
        for method in [self.records_table.setFocusPolicy, self.records_table.setShowGrid,
                       self.records_table.setEditTriggers, self.records_table.setSelectionBehavior,
                       self.records_table.setSelectionMode, self.records_table.verticalHeader().setVisible,
                       self.records_table.horizontalHeader().setHighlightSections,
                       self.records_table.setContextMenuPolicy]:
            if method.__name__ in ['setFocusPolicy']:
                method(Qt.FocusPolicy.NoFocus)
            elif method.__name__ in ['setShowGrid']:
                method(False)
            elif method.__name__ in ['setEditTriggers']:
                method(QAbstractItemView.EditTrigger.NoEditTriggers)
            elif method.__name__ in ['setSelectionBehavior']:
                method(QAbstractItemView.SelectionBehavior.SelectRows)
            elif method.__name__ in ['setSelectionMode']:
                method(QAbstractItemView.SelectionMode.SingleSelection)
            elif method.__name__ in ['setVisible']:
                method(False)
            elif method.__name__ in ['setHighlightSections']:
                method(False)
            elif method.__name__ in ['setContextMenuPolicy']:
                method(Qt.ContextMenuPolicy.CustomContextMenu)
        self.records_table.customContextMenuRequested.connect(self._show_records_table_context_menu);
        layout.addWidget(self.records_table)
        pagination_layout = QHBoxLayout();
        self.prev_btn = QPushButton(fa.icon('fa5s.chevron-left'), "<< Previous");
        self.next_btn = QPushButton(fa.icon('fa5s.chevron-right'), "Next >>");
        self.page_label = QLabel("Page 1 of 1")
        pagination_layout.addStretch();
        pagination_layout.addWidget(self.prev_btn);
        pagination_layout.addWidget(self.page_label);
        pagination_layout.addWidget(self.next_btn);
        pagination_layout.addStretch();
        layout.addLayout(pagination_layout)
        self.search_edit.textChanged.connect(self._on_search_text_changed);
        self.refresh_btn.clicked.connect(self._load_all_records);
        self.update_btn.clicked.connect(self._load_record_for_update);
        self.delete_btn.clicked.connect(self._delete_record)
        self.records_table.itemSelectionChanged.connect(self._on_record_selection_changed);
        self.records_table.doubleClicked.connect(self._load_record_for_update);
        self.prev_btn.clicked.connect(self._go_to_prev_page);
        self.next_btn.clicked.connect(self._go_to_next_page);
        self._on_record_selection_changed()

    def _setup_deleted_tab(self, tab):
        layout = QVBoxLayout(tab);
        instructions = self._create_instruction_box(
            "Records soft-deleted from the main log are stored here. Use 'Restore Selected' to return a record and its corresponding inventory transaction back to the active log.");
        layout.addWidget(instructions)
        top_layout = QHBoxLayout();
        top_layout.addWidget(QLabel("Search:"));
        self.deleted_search_edit = UpperCaseLineEdit(placeholderText="Filter deleted records...");
        top_layout.addWidget(self.deleted_search_edit, 1)
        self.restore_btn = QPushButton(fa.icon('fa5s.undo'), "Restore Selected");
        self.restore_btn.setObjectName("PrimaryButton");
        self.restore_btn.setEnabled(False);
        top_layout.addWidget(self.restore_btn);
        layout.addLayout(top_layout)
        self.deleted_records_table = QTableWidget()
        for method in [self.deleted_records_table.setFocusPolicy, self.deleted_records_table.setShowGrid,
                       self.deleted_records_table.setEditTriggers, self.deleted_records_table.setSelectionBehavior,
                       self.deleted_records_table.setSelectionMode,
                       self.deleted_records_table.verticalHeader().setVisible,
                       self.deleted_records_table.horizontalHeader().setHighlightSections]:
            if method.__name__ in ['setFocusPolicy']:
                method(Qt.FocusPolicy.NoFocus)
            elif method.__name__ in ['setShowGrid']:
                method(False)
            elif method.__name__ in ['setEditTriggers']:
                method(QAbstractItemView.EditTrigger.NoEditTriggers)
            elif method.__name__ in ['setSelectionBehavior']:
                method(QAbstractItemView.SelectionBehavior.SelectRows)
            elif method.__name__ in ['setSelectionMode']:
                method(QAbstractItemView.SelectionMode.SingleSelection)
            elif method.__name__ in ['setVisible']:
                method(False)
            elif method.__name__ in ['setHighlightSections']:
                method(False)
        layout.addWidget(self.deleted_records_table)
        pagination_layout = QHBoxLayout();
        self.deleted_prev_btn = QPushButton(fa.icon('fa5s.chevron-left'), "<< Previous");
        self.deleted_next_btn = QPushButton(fa.icon('fa5s.chevron-right'), "Next >>");
        self.deleted_page_label = QLabel("Page 1 of 1")
        pagination_layout.addStretch();
        pagination_layout.addWidget(self.deleted_prev_btn);
        pagination_layout.addWidget(self.deleted_page_label);
        pagination_layout.addWidget(self.deleted_next_btn);
        pagination_layout.addStretch();
        layout.addLayout(pagination_layout)
        self.deleted_search_edit.textChanged.connect(self._on_deleted_search_text_changed);
        self.restore_btn.clicked.connect(self._restore_record);
        self.deleted_records_table.itemSelectionChanged.connect(
            lambda: self.restore_btn.setEnabled(bool(self.deleted_records_table.selectedItems())))
        self.deleted_prev_btn.clicked.connect(self._go_to_deleted_prev_page);
        self.deleted_next_btn.clicked.connect(self._go_to_deleted_next_page)

    def _setup_entry_tab(self, tab):
        layout = QVBoxLayout(tab)

        # Improved instructions with better styling
        instructions = self._create_instruction_box(
            "💡 Enter new requisition details. Use TAB to navigate between fields. Up/Down arrows to browse combo values.")
        layout.addWidget(instructions)

        # Main form container with better styling
        form_container = QWidget()
        form_container.setObjectName("FormContainer")
        layout.addWidget(form_container)

        form_layout = QGridLayout(form_container)
        form_layout.setVerticalSpacing(12)
        form_layout.setHorizontalSpacing(15)
        form_layout.setContentsMargins(20, 20, 20, 20)

        # Initialize fields
        self.req_id_edit = QLineEdit(readOnly=True, placeholderText="Auto-generated")
        self.manual_ref_no_edit = UpperCaseLineEdit()
        self.category_combo = QComboBox()
        self.category_combo.addItems(["MB", "DC"])
        self.request_date_edit = QDateEdit(calendarPopup=True, displayFormat="yyyy-MM-dd")
        self.request_date_edit.setDate(QDate.currentDate())

        # Initialize enhanced combo boxes
        self.requester_name_combo, self.department_combo, self.product_code_combo, self.approved_by_combo, self.status_combo = QComboBox(), QComboBox(), QComboBox(), QComboBox(), QComboBox()
        self.lot_no_edit, self.remarks_edit = UpperCaseLineEdit(), UpperCaseLineEdit()
        self.quantity_edit = FloatLineEdit()
        self.location_combo = QComboBox()
        self.location_combo.addItems(["WH1", "WH2", "WH3", "WH4", "WH5"])
        self.request_for_combo = QComboBox()
        self.request_for_combo.addItems(["PASSED", "FAILED"])

        # Configure enhanced combo boxes
        for combo in [self.requester_name_combo, self.department_combo, self.product_code_combo,
                      self.approved_by_combo, self.status_combo]:
            self._configure_enhanced_combobox(combo, editable=True)

        # Set placeholder texts
        self.manual_ref_no_edit.setPlaceholderText("Enter manual reference number...")
        self.lot_no_edit.setPlaceholderText("Enter lot number...")
        self.remarks_edit.setPlaceholderText("Enter remarks...")

        # Refresh combo data
        self._refresh_entry_combos()

        # Create form rows with better labeling and organization

        # Row 0: Requisition ID and Manual Ref
        form_layout.addWidget(self._create_form_label("Requisition ID:"), 0, 0)
        form_layout.addWidget(self.req_id_edit, 0, 1)
        form_layout.addWidget(self._create_form_label("Manual Ref #:"), 0, 2)
        form_layout.addWidget(self.manual_ref_no_edit, 0, 3)

        # Row 1: Request Date and Category
        form_layout.addWidget(self._create_form_label("Request Date:"), 1, 0)
        form_layout.addWidget(self.request_date_edit, 1, 1)
        form_layout.addWidget(self._create_form_label("Category:"), 1, 2)
        form_layout.addWidget(self.category_combo, 1, 3)

        # Row 2: Requester Name and Department
        form_layout.addWidget(self._create_form_label("Requester Name:*"), 2, 0)
        form_layout.addWidget(self._create_combo_with_add_button(self.requester_name_combo, self._on_add_requester), 2,
                              1)
        form_layout.addWidget(self._create_form_label("Department:*"), 2, 2)
        form_layout.addWidget(self._create_combo_with_add_button(self.department_combo, self._on_add_department), 2, 3)

        # Row 3: Product Code and Lot #
        form_layout.addWidget(self._create_form_label("Product Code:*"), 3, 0)
        form_layout.addWidget(self.product_code_combo, 3, 1)
        form_layout.addWidget(self._create_form_label("Lot #:"), 3, 2)
        form_layout.addWidget(self.lot_no_edit, 3, 3)

        # Row 4: Quantity and Location
        form_layout.addWidget(self._create_form_label("Quantity (kg):*"), 4, 0)
        form_layout.addWidget(self.quantity_edit, 4, 1)
        form_layout.addWidget(self._create_form_label("Location:"), 4, 2)
        form_layout.addWidget(self.location_combo, 4, 3)

        # Row 5: Request For and Status
        form_layout.addWidget(self._create_form_label("Request For:"), 5, 0)
        form_layout.addWidget(self.request_for_combo, 5, 1)
        form_layout.addWidget(self._create_form_label("Status:"), 5, 2)
        form_layout.addWidget(self.status_combo, 5, 3)

        # Row 6: Approved By and Remarks
        form_layout.addWidget(self._create_form_label("Approved By:"), 6, 0)
        form_layout.addWidget(self._create_combo_with_add_button(self.approved_by_combo, self._on_add_approver), 6, 1)
        form_layout.addWidget(self._create_form_label("Remarks:"), 6, 2)
        form_layout.addWidget(self.remarks_edit, 6, 3)

        # Required fields note
        required_note = QLabel("* Required fields")
        required_note.setStyleSheet("color: #dc3545; font-style: italic; font-size: 9pt; padding: 5px;")
        form_layout.addWidget(required_note, 7, 0, 1, 4, Qt.AlignmentFlag.AlignLeft)

        layout.addStretch()

        # Enhanced button layout
        button_layout = QHBoxLayout()
        self.save_btn = QPushButton(fa.icon('fa5s.save', color='white'), "Save Requisition")
        self.save_btn.setObjectName("PrimaryButton")
        self.save_btn.setMinimumHeight(40)

        self.clear_btn = QPushButton(fa.icon('fa5s.file', color='#6c757d'), "New")
        self.clear_btn.setObjectName("SecondaryButton")
        self.clear_btn.setMinimumHeight(40)

        self.cancel_update_btn = QPushButton(fa.icon('fa5s.times-circle', color='white'), "Cancel Update")
        self.cancel_update_btn.setObjectName("DestructiveButton")
        self.cancel_update_btn.setMinimumHeight(40)

        button_layout.addStretch()
        button_layout.addWidget(self.cancel_update_btn)
        button_layout.addWidget(self.clear_btn)
        button_layout.addWidget(self.save_btn)
        layout.addLayout(button_layout)

        # Connect signals
        self.save_btn.clicked.connect(self._save_record)
        self.clear_btn.clicked.connect(self._clear_form)
        self.cancel_update_btn.clicked.connect(self._clear_form)

        self._clear_form()

    def _create_form_label(self, text):
        """Create a consistent form label"""
        label = QLabel(text)
        label.setStyleSheet("font-weight: bold; color: #495057;")
        return label

    def _configure_enhanced_combobox(self, combo: QComboBox, editable: bool = False):
        combo.setEditable(editable)
        if editable:
            combo.setLineEdit(UpperCaseLineEdit(self))
            combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
            combo.completer().setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
            combo.completer().setFilterMode(Qt.MatchFlag.MatchContains)

        # Enable keyboard navigation
        combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def eventFilter(self, obj, event):
        # Handle up/down arrow keys for combo boxes when dropdown is not open
        if isinstance(obj, QComboBox) and event.type() == event.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                if not obj.view().isVisible():
                    current_index = obj.currentIndex()
                    if event.key() == Qt.Key.Key_Down:
                        new_index = min(current_index + 1, obj.count() - 1)
                    else:  # Key_Up
                        new_index = max(current_index - 1, 0)
                    obj.setCurrentIndex(new_index)
                    return True
        return super().eventFilter(obj, event)

    def _create_combo_with_add_button(self, combo: QComboBox, on_add_method):
        container = QWidget();
        layout = QHBoxLayout(container);
        layout.setContentsMargins(0, 0, 0, 0);
        layout.setSpacing(5);
        layout.addWidget(combo, 1);
        add_btn = QPushButton();
        add_btn.setObjectName("SecondaryButton");
        add_btn.setIcon(fa.icon('fa5s.plus'))
        add_btn.setText("");
        add_btn.setFixedSize(30, 30);
        add_btn.setToolTip("Add a new value to the list");
        add_btn.clicked.connect(on_add_method);
        layout.addWidget(add_btn);
        return container

    def _on_add_requester(self):
        self._add_new_lookup_value(self.requester_name_combo, "Requester", 'requisition_requesters', 'name')

    def _on_add_department(self):
        self._add_new_lookup_value(self.department_combo, "Department", 'requisition_departments', 'name')

    def _on_add_approver(self):
        self._add_new_lookup_value(self.approved_by_combo, "Approver", 'requisition_approvers', 'name')

    def _add_new_lookup_value(self, combo, title, table, col):
        dialog = AddNewValueDialog(self, f"Add New {title}", f"Enter new {title.lower()} name:")
        if dialog.exec():
            new_val = dialog.get_value()
            if not new_val: return
            try:
                with self.engine.connect() as conn, conn.begin():
                    conn.execute(text(f"INSERT INTO {table} ({col}) VALUES (:val) ON CONFLICT ({col}) DO NOTHING"),
                                 {"val": new_val})
                self._populate_combo(combo, table, col);
                combo.setCurrentText(new_val)
            except Exception as e:
                QMessageBox.critical(self, "Database Error", f"Could not save new {title.lower()}: {e}")

    def _configure_combobox(self, combo: QComboBox, editable: bool = False):
        combo.setEditable(editable)
        if editable:
            combo.setLineEdit(UpperCaseLineEdit(self));
            combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
            combo.completer().setCompletionMode(QCompleter.CompletionMode.PopupCompletion);
            combo.completer().setFilterMode(Qt.MatchFlag.MatchContains)

    def _refresh_entry_combos(self):
        for combo, table, col in [(self.product_code_combo, 'legacy_production', 'prod_code'),
                                  (self.requester_name_combo, 'requisition_requesters', 'name'),
                                  (self.approved_by_combo, 'requisition_approvers', 'name'),
                                  (self.department_combo, 'requisition_departments', 'name'),
                                  (self.status_combo, 'requisition_statuses', 'status_name')]:
            self._populate_combo(combo, table, col)

    def _populate_combo(self, combo: QComboBox, table: str, column: str):
        current_text = combo.currentText()
        try:
            with self.engine.connect() as conn:
                results = conn.execute(text(
                    f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL AND {column} != '' ORDER BY {column}")).scalars().all()
            combo.blockSignals(True);
            combo.clear()
            if table == 'requisition_statuses' and not results: results = ["PENDING", "APPROVED", "COMPLETED",
                                                                           "REJECTED"]
            combo.addItems(results);
            combo.blockSignals(False);
            combo.setCurrentText(current_text)
            if combo.lineEdit(): combo.lineEdit().setPlaceholderText("SELECT OR TYPE...")
        except Exception as e:
            print(f"Warning: Could not populate combobox from {table}.{column}: {e}")

    def _setup_view_details_tab(self, tab):
        layout = QVBoxLayout(tab);
        instructions = self._create_instruction_box(
            "This read-only tab displays all metadata for the currently selected requisition record.");
        layout.addWidget(instructions)
        details_group = QGroupBox("Requisition Details (Read-Only)");
        self.view_details_layout = QFormLayout(details_group);
        layout.addWidget(details_group);
        layout.addStretch()

    def _on_tab_changed(self, index):
        current_tab = self.tab_widget.widget(index)
        if current_tab == self.view_details_tab:
            self._show_selected_record_in_view_tab()
        elif current_tab == self.entry_tab:
            self._refresh_entry_combos()
        elif current_tab == self.deleted_tab:
            self._load_deleted_records()
        else:  # This is the main view tab (Tab 1)
            # Force refresh when switching to the main view tab
            self._load_all_records()

    def _clear_form(self):
        self.current_editing_req_id = None;
        self.cancel_update_btn.hide();
        self.save_btn.setText("Save Requisition");
        self.save_btn.setIcon(fa.icon('fa5s.save'))
        for w in [self.req_id_edit, self.manual_ref_no_edit, self.lot_no_edit, self.remarks_edit]: w.clear()
        for c in [self.requester_name_combo, self.department_combo, self.product_code_combo,
                  self.approved_by_combo]: c.setCurrentText("")
        self.quantity_edit.setText("0.00");
        self.category_combo.setCurrentIndex(0);
        self.status_combo.setCurrentText("PENDING")
        self.request_date_edit.setDate(QDate.currentDate());
        self.location_combo.setCurrentIndex(0);
        self.request_for_combo.setCurrentIndex(0);
        self.manual_ref_no_edit.setFocus()

    def _generate_req_id(self):
        prefix = f"REQ-{datetime.now().strftime('%Y%m%d')}-"
        try:
            with self.engine.connect() as conn:
                last_ref = conn.execute(
                    text("SELECT req_id FROM requisition_logbook WHERE req_id LIKE :p ORDER BY id DESC LIMIT 1"),
                    {"p": f"{prefix}%"}).scalar_one_or_none()
                if last_ref:
                    try:
                        return f"{prefix}{int(last_ref.split('-')[-1]) + 1:04d}"
                    except (ValueError, IndexError):
                        return f"{prefix}0001"
                return f"{prefix}0001"
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not generate Requisition ID: {e}");
            return None

    def _save_record(self):
        is_update = self.current_editing_req_id is not None
        req_id = self.current_editing_req_id or self._generate_req_id()
        if not req_id: return
        data = {"req_id": req_id, "manual_ref_no": self.manual_ref_no_edit.text(),
                "category": self.category_combo.currentText(),
                "request_date": self.request_date_edit.date().toPyDate(),
                "requester_name": self.requester_name_combo.currentText(),
                "department": self.department_combo.currentText(),
                "product_code": self.product_code_combo.currentText(),
                "lot_no": self.lot_no_edit.text(), "quantity_kg": self.quantity_edit.value(),
                "status": self.status_combo.currentText(),
                "approved_by": self.approved_by_combo.currentText(), "remarks": self.remarks_edit.text(),
                "location": self.location_combo.currentText(),
                "request_for": self.request_for_combo.currentText(), "user": self.username}
        if not data["product_code"]:
            QMessageBox.warning(self, "Input Error", "Product Code is a required field.")
            return
        try:
            with self.engine.connect() as conn, conn.begin():
                for val, table, col in [(data['requester_name'], 'requisition_requesters', 'name'),
                                        (data['department'], 'requisition_departments', 'name'),
                                        (data['approved_by'], 'requisition_approvers', 'name'),
                                        (data['status'], 'requisition_statuses', 'status_name')]:
                    if val: conn.execute(
                        text(f"INSERT INTO {table} ({col}) VALUES (:val) ON CONFLICT ({col}) DO NOTHING"), {"val": val})
                if is_update:
                    sql = text("""UPDATE requisition_logbook SET manual_ref_no=:manual_ref_no, category=:category, request_date=:request_date,
                                  requester_name=:requester_name, department=:department, product_code=:product_code, lot_no=:lot_no, quantity_kg=:quantity_kg,
                                  status=:status, approved_by=:approved_by, remarks=:remarks, location=:location, request_for=:request_for,
                                  edited_by=:user, edited_on=:ts WHERE req_id=:req_id""")
                    action, log_action = "updated", "UPDATE_REQUISITION"
                else:
                    sql = text("""INSERT INTO requisition_logbook (req_id, manual_ref_no, category, request_date, requester_name, department, product_code,
                                  lot_no, quantity_kg, status, approved_by, remarks, location, request_for, encoded_by, encoded_on, edited_by, edited_on)
                                  VALUES (:req_id, :manual_ref_no, :category, :request_date, :requester_name, :department, :product_code, :lot_no,
                                  :quantity_kg, :status, :approved_by, :remarks, :location, :request_for, :user, :ts, :user, :ts)""")
                    action, log_action = "saved", "CREATE_REQUISITION"
                data['ts'] = datetime.now()
                conn.execute(sql, data)
                self._update_or_create_transaction(conn, data)
                self.log_audit_trail(log_action, f"{action.capitalize()} requisition: {req_id}")
                QMessageBox.information(self, "Success", f"Requisition has been {action}.")

            # Refresh the main table data (but don't switch tabs)
            self.current_page = 1
            self._load_all_records()

            # Clear the form and stay in entry tab
            self._clear_form()

            # Set focus to manual ref no for quick next entry
            self.manual_ref_no_edit.setFocus()

        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Could not save record: {e}\n{traceback.format_exc()}")

    def _update_or_create_transaction(self, conn, req_data):
        req_id = req_data['req_id']
        conn.execute(text("DELETE FROM transactions WHERE source_ref_no = :req_id"), {"req_id": req_id})
        conn.execute(text("DELETE FROM failed_transactions WHERE source_ref_no = :req_id"), {"req_id": req_id})
        tx_data = {"date": req_data['request_date'], "type": "REQUISITION", "ref": req_id,
                   "pcode": req_data['product_code'], "lot": req_data['lot_no'], "qty_out": req_data['quantity_kg'],
                   "unit": "KG.", "wh": req_data['location'], "user": self.username, "remarks": req_data['remarks']}
        table = 'transactions' if req_data['request_for'] == 'PASSED' else 'failed_transactions'
        sql = text(
            f"INSERT INTO {table} (transaction_date, transaction_type, source_ref_no, product_code, lot_number, quantity_out, unit, warehouse, encoded_by, remarks) VALUES (:date, :type, :ref, :pcode, :lot, :qty_out, :unit, :wh, :user, :remarks)")
        conn.execute(sql, tx_data)

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
            self.quantity_edit.setText(format_float_with_commas(record.get('quantity_kg', 0.0)))
            self.status_combo.setCurrentText(record.get('status', ''));
            self.approved_by_combo.setCurrentText(record.get('approved_by', ''))
            self.remarks_edit.setText(record.get('remarks', ''));
            self.location_combo.setCurrentText(record.get('location', ''));
            self.request_for_combo.setCurrentText(record.get('request_for', ''))
            req_date = record.get('request_date')
            if req_date:
                if isinstance(req_date, str): req_date = datetime.strptime(req_date, '%Y-%m-%d').date()
                self.request_date_edit.setDate(QDate(req_date))
            self.save_btn.setText("Update Requisition");
            self.save_btn.setIcon(fa.icon('fa5s.arrow-up'));
            self.cancel_update_btn.show();
            self.tab_widget.setCurrentWidget(self.entry_tab)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load record for update: {e}\n{traceback.format_exc()}")

    def _load_all_records(self):
        like_op = "LIKE" if self.engine.dialect.name == 'sqlite' else 'ILIKE'
        search_term = self.search_edit.text().strip()
        params = {}
        filter_clause = ""
        if search_term:
            filter_clause = f"AND (req_id {like_op} :term OR manual_ref_no {like_op} :term OR product_code {like_op} :term OR lot_no {like_op} :term)"
            params['term'] = f"%{search_term}%"
        try:
            with self.engine.connect() as conn:
                self.total_records = conn.execute(
                    text(f"SELECT COUNT(*) FROM requisition_logbook WHERE is_deleted IS NOT TRUE {filter_clause}"),
                    params).scalar_one()
                self.total_pages = math.ceil(self.total_records / self.records_per_page) or 1
                offset = (self.current_page - 1) * self.records_per_page
                params.update({'limit': self.records_per_page, 'offset': offset})
                results = conn.execute(text(f"""SELECT req_id, manual_ref_no, request_date, product_code, lot_no, 
                                          quantity_kg, status, location, request_for, edited_by, edited_on
                                      FROM requisition_logbook WHERE is_deleted IS NOT TRUE {filter_clause}
                                      ORDER BY id DESC LIMIT :limit OFFSET :offset"""), params).mappings().all()
            headers = ["Req ID", "Manual Ref #", "Date", "Product Code", "Lot #", "Qty (kg)", "Status", "Location",
                       "For", "Last Edited By", "Last Edited On"]
            data_keys = ["req_id", "manual_ref_no", "request_date", "product_code", "lot_no", "quantity_kg", "status",
                         "location", "request_for", "edited_by", "edited_on"]
            self._populate_records_table(self.records_table, headers, results, data_keys)
            self._update_pagination_controls();
            self._on_record_selection_changed()
        except Exception as e:
            print(f"ERROR: Failed to load records: {e}\n{traceback.format_exc()}")

    def _load_deleted_records(self):
        like_op = "LIKE" if self.engine.dialect.name == 'sqlite' else 'ILIKE'
        search_term = self.deleted_search_edit.text().strip()
        params = {}
        filter_clause = ""
        if search_term:
            filter_clause = f"AND (req_id {like_op} :term OR product_code {like_op} :term OR lot_no {like_op} :term)"
            params['term'] = f"%{search_term}%"
        try:
            with self.engine.connect() as conn:
                self.deleted_total_records = conn.execute(
                    text(f"SELECT COUNT(*) FROM requisition_logbook WHERE is_deleted IS TRUE {filter_clause}"),
                    params).scalar_one()
                self.deleted_total_pages = math.ceil(self.deleted_total_records / self.records_per_page) or 1
                offset = (self.deleted_current_page - 1) * self.records_per_page
                params.update({'limit': self.records_per_page, 'offset': offset})
                results = conn.execute(text(f"""SELECT req_id, product_code, lot_no, quantity_kg, edited_by as deleted_by, edited_on as deleted_on
                                      FROM requisition_logbook WHERE is_deleted IS TRUE {filter_clause}
                                      ORDER BY edited_on DESC LIMIT :limit OFFSET :offset"""), params).mappings().all()
            headers = ["Req ID", "Product Code", "Lot #", "Qty (kg)", "Deleted By", "Deleted On"]
            data_keys = ["req_id", "product_code", "lot_no", "quantity_kg", "deleted_by", "deleted_on"]
            self._populate_records_table(self.deleted_records_table, headers, results, data_keys)
            self._update_deleted_pagination_controls()
        except Exception as e:
            print(f"ERROR: Failed to load deleted records: {e}\n{traceback.format_exc()}")

    def _populate_records_table(self, table, headers, data, data_keys):
        table.setRowCount(0);
        table.setColumnCount(len(headers));
        table.setHorizontalHeaderLabels(headers)
        if not data: return
        table.setRowCount(len(data))
        for row_idx, record in enumerate(data):
            for col_idx, key in enumerate(data_keys):
                value = record.get(key)
                if isinstance(value, (Decimal, float)):
                    text_val = format_float_with_commas(value)
                elif isinstance(value, datetime):
                    text_val = value.strftime('%Y-%m-%d %H:%M')
                elif isinstance(value, date):
                    text_val = value.strftime('%Y-%m-%d')
                else:
                    text_val = str(value or 'N/A').upper()
                item = QTableWidgetItem(text_val)
                if key == 'quantity_kg': item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(row_idx, col_idx, item)
        table.resizeColumnsToContents()
        if len(headers) > 3: table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

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
        self.deleted_prev_btn.setEnabled(self.deleted_current_page > 1);
        self.deleted_next_btn.setEnabled(self.deleted_current_page < self.deleted_total_pages)

    def _go_to_prev_page(self):
        if self.current_page > 1: self.current_page -= 1; self._load_all_records()

    def _go_to_next_page(self):
        if self.current_page < self.total_pages: self.current_page += 1; self._load_all_records()

    def _go_to_deleted_prev_page(self):
        if self.deleted_current_page > 1: self.deleted_current_page -= 1; self._load_deleted_records()

    def _go_to_deleted_next_page(self):
        if self.deleted_current_page < self.deleted_total_pages: self.deleted_current_page += 1; self._load_deleted_records()

    def _show_selected_record_in_view_tab(self):
        row = self.records_table.currentRow()
        if row < 0: return
        req_id = self.records_table.item(row, 0).text()
        try:
            with self.engine.connect() as conn:
                record = conn.execute(text("SELECT * FROM requisition_logbook WHERE req_id = :req_id"),
                                      {"req_id": req_id}).mappings().first()
            if not record: QMessageBox.warning(self, "Not Found", "Record details could not be retrieved."); return
            while self.view_details_layout.count():
                item = self.view_details_layout.takeAt(0)
                if item.widget(): item.widget().deleteLater()
            for key, value in record.items():
                if key in ['id', 'is_deleted']: continue
                label = key.replace('_', ' ').title()
                if isinstance(value, (datetime, date)):
                    display_value = value.strftime('%Y-%m-%d %H:%M') if isinstance(value, datetime) else value.strftime(
                        '%Y-%m-%d')
                elif isinstance(value, (Decimal, float)):
                    display_value = format_float_with_commas(value)
                else:
                    display_value = str(value or 'N/A').upper()
                self.view_details_layout.addRow(QLabel(f"<b>{label}:</b>"), QLabel(display_value))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load details: {e}\n{traceback.format_exc()}")

    def _on_record_selection_changed(self):
        is_selected = bool(self.records_table.selectionModel().selectedRows())
        self.update_btn.setEnabled(is_selected);
        self.delete_btn.setEnabled(is_selected)
        self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.view_details_tab), is_selected)
        if not is_selected and self.tab_widget.currentIndex() == self.tab_widget.indexOf(self.view_details_tab):
            self.tab_widget.setCurrentIndex(0)

    def _show_records_table_context_menu(self, pos):
        row = self.records_table.rowAt(pos.y())
        if row < 0: return
        self.records_table.selectRow(row)
        menu = QMenu();
        view_action = menu.addAction(fa.icon('fa5s.search'), "View Details");
        edit_action = menu.addAction(fa.icon('fa5s.edit'), "Load for Update");
        delete_action = menu.addAction(fa.icon('fa5s.trash'), "Delete Record")
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
                                     f"Delete requisition <b>{req_id}</b>?\nThis will remove its inventory transaction.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                with self.engine.connect() as conn, conn.begin():
                    conn.execute(text(
                        "UPDATE requisition_logbook SET is_deleted = TRUE, edited_by = :user, edited_on = :ts WHERE req_id = :req_id"),
                        {"req_id": req_id, "user": self.username, "ts": datetime.now()})
                    conn.execute(text("DELETE FROM transactions WHERE source_ref_no = :req_id"), {"req_id": req_id})
                    conn.execute(text("DELETE FROM failed_transactions WHERE source_ref_no = :req_id"),
                                 {"req_id": req_id})
                self.log_audit_trail("DELETE_REQUISITION", f"Soft-deleted requisition: {req_id}")
                QMessageBox.information(self, "Success", f"Requisition {req_id} has been deleted.")
                self._load_all_records()
            except Exception as e:
                QMessageBox.critical(self, "Database Error", f"Failed to delete record: {e}\n{traceback.format_exc()}")

    def _restore_record(self):
        row = self.deleted_records_table.currentRow()
        if row < 0: return
        req_id = self.deleted_records_table.item(row, 0).text()
        reply = QMessageBox.question(self, "Confirm Restore",
                                     f"Restore requisition <b>{req_id}</b>?\nThis re-creates its inventory transaction.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                with self.engine.connect() as conn, conn.begin():
                    conn.execute(text(
                        "UPDATE requisition_logbook SET is_deleted = FALSE, edited_by = :user, edited_on = :ts WHERE req_id = :req_id"),
                        {"req_id": req_id, "user": self.username, "ts": datetime.now()})
                    restored_data = conn.execute(text("SELECT * FROM requisition_logbook WHERE req_id = :req_id"),
                                                 {"req_id": req_id}).mappings().first()
                    if not restored_data: raise Exception("Failed to retrieve restored record data.")
                    self._update_or_create_transaction(conn, restored_data)
                self.log_audit_trail("RESTORE_REQUISITION", f"Restored requisition: {req_id}")
                QMessageBox.information(self, "Success", f"Requisition {req_id} has been restored.")
                self._load_deleted_records();
                self._load_all_records()
            except Exception as e:
                QMessageBox.critical(self, "Database Error", f"Failed to restore record: {e}\n{traceback.format_exc()}")


class StandaloneWindow(QMainWindow):
    def __init__(self, db_engine):
        super().__init__()
        self.setWindowTitle("Standalone Requisition Logbook Module");
        self.setGeometry(100, 100, 1200, 800)
        self.page = RequisitionLogbookPage(db_engine=db_engine, username="STANDALONE_USER",
                                           log_audit_trail_func=mock_log_audit_trail)
        self.setCentralWidget(self.page)


if __name__ == "__main__":
    app = QApplication.instance() or QApplication(sys.argv)
    engine = setup_in_memory_db()
    window = StandaloneWindow(engine)
    window.show()
    sys.exit(app.exec())