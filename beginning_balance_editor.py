# beginning_balance_editor.py

import sys
import traceback
from decimal import Decimal, InvalidOperation
from PyQt6.QtCore import Qt, QDate, QSize
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
                             QMessageBox, QGroupBox, QGridLayout, QAbstractItemView,
                             QDateEdit, QDoubleSpinBox, QComboBox, QFrame)
from sqlalchemy import text, Engine
import qtawesome as fa

# --- UI CONSTANTS (Copied from good_inventory_page.py for consistency) ---
PRIMARY_ACCENT_COLOR = "#007bff"
NEUTRAL_COLOR = "#6c757d"
LIGHT_TEXT_COLOR = "#333333"
BACKGROUND_CONTENT_COLOR = "#f4f7fc"
INPUT_BACKGROUND_COLOR = "#ffffff"
GROUP_BOX_HEADER_COLOR = "#f4f7fc"
TABLE_SELECTION_COLOR = "#3a506b"
DESTRUCTIVE_COLOR = "#dc3545"
HEADER_AND_ICON_COLOR = "#3a506b"
TABLE_HEADER_TEXT_COLOR = "#4f4f4f"


# A helper class from your other file for consistency
class UpperCaseLineEdit(QLineEdit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.textEdited.connect(self._to_upper)

    def _to_upper(self, text: str):
        if text and text != text.upper():
            self.blockSignals(True)
            self.setText(text.upper())
            self.blockSignals(False)


class BeginningBalancePage(QWidget):
    def __init__(self, engine: Engine, username: str, log_audit_trail_func):
        super().__init__()
        self.engine = engine
        self.username = username
        self.log_audit_trail = log_audit_trail_func
        self.selected_record_id = None
        self._setup_ui()
        self.setStyleSheet(self._get_styles())

    def _get_styles(self) -> str:
        """Returns the stylesheet for this page, consistent with GoodInventoryPage."""
        return f"""
            QWidget {{
                background-color: {BACKGROUND_CONTENT_COLOR};
                color: {LIGHT_TEXT_COLOR};
                font-family: 'Segoe UI', Arial, sans-serif;
            }}
            QGroupBox {{
                border: 1px solid #e0e5eb;
                border-radius: 8px;
                margin-top: 12px;
                background-color: {INPUT_BACKGROUND_COLOR};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 2px 10px;
                background-color: {GROUP_BOX_HEADER_COLOR};
                border: 1px solid #e0e5eb;
                border-bottom: 1px solid {INPUT_BACKGROUND_COLOR};
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                font-weight: bold;
                color: #4f4f4f;
            }}
            QGroupBox QLabel {{ background-color: transparent; }}
            QLabel {{ background-color: transparent; }}
            QLineEdit, QDateEdit, QComboBox, QDoubleSpinBox {{
                border: 1px solid #d1d9e6;
                padding: 8px;
                border-radius: 5px;
                background-color: {INPUT_BACKGROUND_COLOR};
            }}
            QLineEdit:focus, QDateEdit:focus, QComboBox:focus, QDoubleSpinBox:focus {{
                border: 1px solid {PRIMARY_ACCENT_COLOR};
            }}
            QPushButton {{
                border: 1px solid #d1d9e6;
                padding: 8px 15px;
                border-radius: 6px;
                font-weight: bold;
                background-color: {INPUT_BACKGROUND_COLOR};
            }}
            QPushButton:hover {{ background-color: #f0f3f8; }}
            QPushButton#PrimaryButton {{
                color: {HEADER_AND_ICON_COLOR};
                border: 1px solid {HEADER_AND_ICON_COLOR};
            }}
            QPushButton#PrimaryButton:hover {{ background-color: #e9f0ff; }}
            QPushButton#DeleteButton {{
                color: {DESTRUCTIVE_COLOR};
                border: 1px solid {DESTRUCTIVE_COLOR};
            }}
            QPushButton#DeleteButton:hover {{ background-color: #fbe6e8; }}
            QTableWidget {{
                border: 1px solid #e0e5eb;
                background-color: {INPUT_BACKGROUND_COLOR};
                selection-behavior: SelectRows;
                gridline-color: #f0f3f8;
            }}
            QTableWidget::item:hover {{
                background-color: transparent; /* <<< MODIFIED LINE: This removes the hover effect */
            }}
            QTableWidget::item:selected {{
                background-color: {TABLE_SELECTION_COLOR};
                color: white;
            }}
            QHeaderView::section {{
                background-color: #f4f7fc;
                padding: 5px;
                border: none;
                font-weight: bold;
                color: {TABLE_HEADER_TEXT_COLOR};
            }}
        """

    def refresh_page(self):
        """Called by main_window when this page is shown."""
        self._load_all_records()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)

        # --- Header ---
        header_layout = QHBoxLayout()
        icon_label = QLabel()
        icon_label.setPixmap(fa.icon('fa5s.edit', color=HEADER_AND_ICON_COLOR).pixmap(QSize(28, 28)))
        header_layout.addWidget(icon_label)
        header_layout.addWidget(QLabel("<h1>Beginning Balance Editor - Good</h1>"))
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        # --- Instruction Box ---
        instruction_group = QGroupBox("Instructions")
        instruction_layout = QVBoxLayout(instruction_group)

        instruction_text = (
            "Manage the foundational inventory records. To edit an item, select it from the table on the left. "
            "To create a new one, click the 'New' button first, then fill in the details and save."
        )
        instruction_label = QLabel(instruction_text)
        instruction_label.setStyleSheet("font-style: italic; color: #555; background: transparent;")
        instruction_label.setWordWrap(True)

        instruction_layout.addWidget(instruction_label)
        main_layout.addWidget(instruction_group)

        # --- Main Grid Layout ---
        grid_layout = QGridLayout()
        grid_layout.setColumnStretch(0, 2)
        grid_layout.setColumnStretch(1, 1)

        # --- Left Side: Table and Filters ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        filter_group = QGroupBox("Search Records")
        filter_layout = QHBoxLayout(filter_group)
        self.search_prod_input = UpperCaseLineEdit(placeholderText="Filter by Product Code...")
        self.search_lot_input = UpperCaseLineEdit(placeholderText="Filter by Lot Number...")
        self.search_button = QPushButton("Search", icon=fa.icon('fa5s.search', color=NEUTRAL_COLOR))
        filter_layout.addWidget(self.search_prod_input)
        filter_layout.addWidget(self.search_lot_input)
        filter_layout.addWidget(self.search_button)
        left_layout.addWidget(filter_group)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Prod. Code", "Lot Number", "Qty (kg)", "Location", "FG Type", "Prod. Date"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.hideColumn(0)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)

        left_layout.addWidget(self.table)
        grid_layout.addWidget(left_widget, 0, 0)

        # --- Right Side: Entry/Edit Form ---
        form_group = QGroupBox("Record Details")
        form_layout = QGridLayout(form_group)

        form_layout.addWidget(QLabel("FG Type:"), 0, 0)
        self.fg_type_combo = QComboBox();
        self.fg_type_combo.addItems(["MB", "DC"])
        form_layout.addWidget(self.fg_type_combo, 0, 1)

        form_layout.addWidget(QLabel("Production Date:"), 1, 0)
        self.prod_date_edit = QDateEdit(calendarPopup=True, date=QDate.currentDate())
        self.prod_date_edit.setDisplayFormat("yyyy-MM-dd")
        form_layout.addWidget(self.prod_date_edit, 1, 1)

        form_layout.addWidget(QLabel("Product Code:"), 2, 0)
        self.prod_code_input = UpperCaseLineEdit()
        form_layout.addWidget(self.prod_code_input, 2, 1)

        form_layout.addWidget(QLabel("Lot Number:"), 3, 0)
        self.lot_number_input = UpperCaseLineEdit()
        form_layout.addWidget(self.lot_number_input, 3, 1)

        form_layout.addWidget(QLabel("Quantity (kg):"), 4, 0)
        self.qty_spinbox = QDoubleSpinBox();
        self.qty_spinbox.setRange(0, 999999.99);
        self.qty_spinbox.setDecimals(2)
        form_layout.addWidget(self.qty_spinbox, 4, 1)

        form_layout.addWidget(QLabel("Location:"), 5, 0)
        self.location_input = QLineEdit()
        form_layout.addWidget(self.location_input, 5, 1)

        form_layout.addWidget(QLabel("Remarks:"), 6, 0)
        self.remarks_input = QLineEdit()
        form_layout.addWidget(self.remarks_input, 6, 1)

        form_layout.setRowStretch(7, 1)

        button_layout = QHBoxLayout()
        self.new_button = QPushButton("New", icon=fa.icon('fa5s.plus-circle', color=NEUTRAL_COLOR))
        self.save_button = QPushButton("Save", icon=fa.icon('fa5s.save', color=HEADER_AND_ICON_COLOR))
        self.delete_button = QPushButton("Delete", icon=fa.icon('fa5s.trash-alt', color=DESTRUCTIVE_COLOR))

        self.save_button.setObjectName("PrimaryButton")
        self.delete_button.setObjectName("DeleteButton")

        button_layout.addWidget(self.new_button)
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.delete_button)
        form_layout.addLayout(button_layout, 8, 0, 1, 2)

        grid_layout.addWidget(form_group, 0, 1)
        main_layout.addLayout(grid_layout, 1)

        # --- Connections ---
        self.search_button.clicked.connect(self._load_all_records)
        self.search_prod_input.returnPressed.connect(self._load_all_records)
        self.search_lot_input.returnPressed.connect(self._load_all_records)
        self.table.itemSelectionChanged.connect(self._populate_form_from_selection)
        self.new_button.clicked.connect(self._clear_form)
        self.save_button.clicked.connect(self._save_record)
        self.delete_button.clicked.connect(self._delete_record)

    def _load_all_records(self):
        self.table.setRowCount(0)
        try:
            prod_filter = self.search_prod_input.text().strip()
            lot_filter = self.search_lot_input.text().strip()

            query_str = "SELECT id, product_code, lot_number, qty, location, fg_type, production_date FROM beginv_sheet1 WHERE 1=1"
            params = {}
            if prod_filter:
                query_str += " AND product_code ILIKE :prod"
                params['prod'] = f"%{prod_filter}%"
            if lot_filter:
                query_str += " AND lot_number ILIKE :lot"
                params['lot'] = f"%{lot_filter}%"
            query_str += " ORDER BY id DESC"

            with self.engine.connect() as conn:
                results = conn.execute(text(query_str), params).mappings().all()

            self.table.setSortingEnabled(False)
            for row_data in results:
                row = self.table.rowCount()
                self.table.insertRow(row)
                self.table.setItem(row, 0, QTableWidgetItem(str(row_data['id'])))
                self.table.setItem(row, 1, QTableWidgetItem(row_data['product_code']))
                self.table.setItem(row, 2, QTableWidgetItem(row_data['lot_number']))

                qty_item = QTableWidgetItem(f"{row_data['qty']:.2f}")
                qty_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, 3, qty_item)

                self.table.setItem(row, 4, QTableWidgetItem(row_data['location']))
                self.table.setItem(row, 5, QTableWidgetItem(row_data['fg_type']))
                self.table.setItem(row, 6, QTableWidgetItem(str(row_data['production_date'] or '')))
            self.table.setSortingEnabled(True)

        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Failed to load records: {e}")
            print(traceback.format_exc())

    def _populate_form_from_selection(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return

        row = selected_rows[0].row()
        self.selected_record_id = int(self.table.item(row, 0).text())

        self.prod_code_input.setText(self.table.item(row, 1).text())
        self.lot_number_input.setText(self.table.item(row, 2).text())
        self.qty_spinbox.setValue(float(self.table.item(row, 3).text()))
        self.location_input.setText(self.table.item(row, 4).text())
        self.fg_type_combo.setCurrentText(self.table.item(row, 5).text())
        date_str = self.table.item(row, 6).text()
        if date_str:
            self.prod_date_edit.setDate(QDate.fromString(date_str, "yyyy-MM-dd"))

        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("SELECT remarks FROM beginv_sheet1 WHERE id = :id"),
                                      {"id": self.selected_record_id}).scalar_one_or_none()
                self.remarks_input.setText(result or "")
        except Exception as e:
            print(f"Could not fetch remarks: {e}")

    def _clear_form(self):
        self.selected_record_id = None
        self.prod_code_input.clear()
        self.lot_number_input.clear()
        self.qty_spinbox.setValue(0.0)
        self.location_input.clear()
        self.remarks_input.clear()
        self.prod_date_edit.setDate(QDate.currentDate())
        self.table.clearSelection()

    def _save_record(self):
        prod_code = self.prod_code_input.text().strip()
        lot_number = self.lot_number_input.text().strip()
        qty = self.qty_spinbox.value()

        if not prod_code or not lot_number:
            QMessageBox.warning(self, "Input Error", "Product Code and Lot Number cannot be empty.")
            return

        data = {
            "fg_type": self.fg_type_combo.currentText(),
            "production_date": self.prod_date_edit.date().toString("yyyy-MM-dd"),
            "product_code": prod_code,
            "lot_number": lot_number,
            "qty": qty,
            "location": self.location_input.text().strip(),
            "remarks": self.remarks_input.text().strip()
        }

        try:
            with self.engine.connect() as conn:
                with conn.begin():
                    if self.selected_record_id:
                        data['id'] = self.selected_record_id
                        query = text("""
                            UPDATE beginv_sheet1 SET
                                fg_type=:fg_type, production_date=:production_date, product_code=:product_code,
                                lot_number=:lot_number, qty=:qty, location=:location, remarks=:remarks
                            WHERE id=:id
                        """)
                        conn.execute(query, data)
                        self.log_audit_trail("UPDATE_BEGINV",
                                             f"Updated record ID {self.selected_record_id}: Lot {lot_number}")
                    else:
                        query = text("""
                            INSERT INTO beginv_sheet1 (fg_type, production_date, product_code, lot_number, qty, location, remarks)
                            VALUES (:fg_type, :production_date, :product_code, :lot_number, :qty, :location, :remarks)
                        """)
                        conn.execute(query, data)
                        self.log_audit_trail("INSERT_BEGINV", f"Created new record: Lot {lot_number}")

            QMessageBox.information(self, "Success", "Record saved successfully.")
            self._clear_form()
            self._load_all_records()

        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Failed to save record: {e}")
            print(traceback.format_exc())

    def _delete_record(self):
        if self.selected_record_id is None:
            QMessageBox.warning(self, "Selection Error", "Please select a record from the table to delete.")
            return

        lot_number = self.lot_number_input.text()
        reply = QMessageBox.question(self, "Confirm Delete",
                                     f"Are you sure you want to permanently delete the record for lot '{lot_number}'?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            try:
                with self.engine.connect() as conn:
                    with conn.begin():
                        conn.execute(text("DELETE FROM beginv_sheet1 WHERE id=:id"), {"id": self.selected_record_id})
                self.log_audit_trail("DELETE_BEGINV", f"Deleted record ID {self.selected_record_id}: Lot {lot_number}")
                QMessageBox.information(self, "Success", "Record deleted successfully.")
                self._clear_form()
                self._load_all_records()
            except Exception as e:
                QMessageBox.critical(self, "Database Error", f"Failed to delete record: {e}")
                print(traceback.format_exc())