# audit_trail.py
import sys
import csv
from datetime import datetime
import qtawesome as fa

from PyQt6.QtCore import Qt, QDate, QObject, pyqtSignal, QThread, QTimer, QSize
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
                             QAbstractItemView, QHeaderView, QMessageBox, QHBoxLayout, QLabel,
                             QPushButton, QDateEdit, QLineEdit, QFileDialog, QFormLayout,
                             QStackedWidget, QGroupBox, QApplication, QMainWindow, QTextEdit)
from PyQt6.QtGui import QFont

from sqlalchemy import create_engine, text


# --- Worker to load audit data in the background ---
class AuditDataLoader(QObject):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, engine, params):
        super().__init__()
        self.engine = engine
        self.params = params

    def run(self):
        try:
            # Using a basic structure for SQLite/PostgreSQL compatibility
            query = "SELECT timestamp, username, action_type, details, hostname, ip_address, mac_address FROM qc_audit_trail WHERE 1=1"
            query += " AND timestamp BETWEEN :start_date AND :end_date"
            # Using ILIKE for case-insensitive search (PostgreSQL default, or handled by SQLite if configured)
            if self.params.get('username'): query += " AND username ILIKE :username"
            if self.params.get('action'): query += " AND action_type ILIKE :action"
            if self.params.get('details'): query += " AND details ILIKE :details"
            query += " ORDER BY timestamp DESC"
            with self.engine.connect() as conn:
                result = conn.execute(text(query), self.params).mappings().all()
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(f"Failed to load audit trail: {e}")


class AuditTrailPage(QWidget):
    HEADER_COLOR = "#3a506b"

    def __init__(self, db_engine):
        super().__init__()
        self.engine = db_engine
        self.load_thread = None
        self._setup_ui()
        self.refresh_page()
        self.setStyleSheet(self._get_styles())

    def _create_instruction_box(self, text):
        instruction_box = QGroupBox("Instructions")
        instruction_box.setObjectName("InstructionsBox")
        instruction_layout = QHBoxLayout(instruction_box)
        # --- ADJUSTMENT: Reduced vertical margins in the instruction box layout ---
        instruction_layout.setContentsMargins(10, 10, 10, 10)

        # Icon (Using info-circle, typically blue/cyan)
        icon_label = QLabel()
        icon_label.setPixmap(fa.icon('fa5s.info-circle', color='#17A2B8').pixmap(QSize(24, 24)))

        text_edit = QTextEdit(text, objectName="InstructionsText")
        text_edit.setReadOnly(True)
        # --- ADJUSTMENT: Set max height to 60px (already done, ensuring compliance) ---
        text_edit.setMaximumHeight(60)
        text_edit.setFrameShape(QTextEdit.Shape.NoFrame)

        instruction_layout.addWidget(icon_label)
        instruction_layout.addWidget(text_edit, 1)

        return instruction_box

    def _get_styles(self):
        return f"""
            /* General */
            QGroupBox {{ border: 1px solid #e0e5eb; border-radius: 8px; margin-top: 12px; background-color: white; }}
            QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; padding: 2px 10px; font-weight: bold; color: #4f4f4f; }}

            /* Header */
            QLabel#PageHeader {{ 
                font-size: 15px; 
                font-weight: bold; 
                color: {"#3a506b"}; 
                background-color: transparent; 
                margin-top: 5px;
            }}
            #HeaderWidget {{ background-color: transparent; }}

            /* Buttons */
            #PrimaryButton, #ExportButton {{ 
                background-color: {self.HEADER_COLOR}; 
                color: white; 
                border-radius: 4px; 
                padding: 5px; 
            }}
            #PrimaryButton:hover, #ExportButton:hover {{ 
                background-color: #2b3a4a; 
            }}
            #SecondaryButton {{ 
                background-color: #f8f9fa; 
                color: #333; 
                border: 1px solid #ccc; 
                border-radius: 4px; 
                padding: 5px; 
            }}

            /* Table */
            QTableWidget {{ border: none; background-color: white; }}
            QTableWidget::item:selected {{
                background-color: {self.HEADER_COLOR}; 
                color: white;
            }}

            /* Instructions Box Style */
            QGroupBox#InstructionsBox {{
                border: 1px solid #17A2B8; /* Blue border for info */
                background-color: #f7faff; /* Very light blue background */
                /* Reduced margin from 15px to 5px in the style */
                margin-top: 5px; 
                padding-top: 15px; 
            }} 
            QGroupBox#InstructionsBox::title {{ 
                color: #17A2B8;
                background-color: #f7faff;
            }}
            QTextEdit#InstructionsText {{
                background-color: transparent;
                border: none;
            }}
        """

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        # --- ADJUSTMENT: Use minimal margins for the main layout ---
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8) # Tighten spacing between major widgets

        # --- 1. Structured Header (Icon, Title) ---
        header_widget = QWidget(objectName="HeaderWidget")
        header_layout = QHBoxLayout(header_widget)
        # --- ADJUSTMENT: Tighten margin below header ---
        header_layout.setContentsMargins(0, 0, 0, 5)

        # Icon (Using clipboard-list and HEADER_COLOR)
        icon_pixmap = fa.icon('fa5s.clipboard-list', color=self.HEADER_COLOR).pixmap(QSize(28, 28))
        icon_label = QLabel()
        icon_label.setPixmap(icon_pixmap)
        header_layout.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignLeft)

        # Header Title
        header_label = QLabel("AUDIT TRAIL LOG", objectName="PageHeader")
        header_layout.addWidget(header_label)
        header_layout.addStretch()
        main_layout.addWidget(header_widget)

        # --- 2. Instructions Box ---
        instructions = self._create_instruction_box(
            "The Audit Trail records all significant user actions, including login/logout, data creation, updates, and deletions. Use the date range and filters to quickly search for specific activity. All data is time-stamped with user and machine details."
        )
        main_layout.addWidget(instructions)

        # --- Filters ---
        filter_group = QGroupBox("Filters")
        filter_layout = QFormLayout(filter_group)
        filter_layout.setSpacing(5) # Tighten form spacing

        self.start_date_edit = QDateEdit(calendarPopup=True, displayFormat="yyyy-MM-dd")
        self.end_date_edit = QDateEdit(calendarPopup=True, displayFormat="yyyy-MM-dd")
        self.username_filter = QLineEdit(placeholderText="Filter by username...")
        self.action_filter = QLineEdit(placeholderText="Filter by action (e.g., LOGIN, DELETE)...")
        self.details_filter = QLineEdit(placeholderText="Search in details...")

        self.reset_btn = QPushButton("Reset Filters")
        self.reset_btn.setObjectName("SecondaryButton")
        self.export_btn = QPushButton("Export to CSV")
        self.export_btn.setObjectName("PrimaryButton")  # Setting primary color

        date_range_layout = QHBoxLayout();
        date_range_layout.setContentsMargins(0, 0, 0, 0)
        date_range_layout.addWidget(self.start_date_edit);
        date_range_layout.addWidget(QLabel("to"));
        date_range_layout.addWidget(self.end_date_edit)

        filter_layout.addRow("Date Range:", date_range_layout)
        filter_layout.addRow("Username:", self.username_filter)
        filter_layout.addRow("Action Type:", self.action_filter)
        filter_layout.addRow("Details Search:", self.details_filter)

        button_layout = QHBoxLayout();
        button_layout.addStretch()
        button_layout.addWidget(self.export_btn);
        button_layout.addWidget(self.reset_btn)

        main_layout.addWidget(filter_group)
        main_layout.addLayout(button_layout)

        # --- Table View ---
        self.table_stack = QStackedWidget()
        self.audit_table = QTableWidget()
        self.audit_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.audit_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.audit_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.audit_table.setShowGrid(False)
        self.audit_table.verticalHeader().setVisible(False)
        self.audit_table.horizontalHeader().setHighlightSections(False)
        self.loading_label = QLabel("Loading data...", alignment=Qt.AlignmentFlag.AlignCenter);
        self.loading_label.setStyleSheet("font-size: 14pt; color: grey;")
        self.table_stack.addWidget(self.audit_table);
        # --- MAXIMIZE SPACE: Add stretch factor 1 to the table stack ---
        main_layout.addWidget(self.table_stack, 1)

        # --- Connections ---
        self.filter_timer = QTimer(self);
        self.filter_timer.setSingleShot(True);
        self.filter_timer.setInterval(300);
        self.filter_timer.timeout.connect(self._load_audit_data_async)
        self.start_date_edit.dateChanged.connect(self.filter_timer.start)
        self.end_date_edit.dateChanged.connect(self.filter_timer.start)
        self.username_filter.textChanged.connect(self.filter_timer.start)
        self.action_filter.textChanged.connect(self.filter_timer.start)
        self.details_filter.textChanged.connect(self.filter_timer.start)
        self.reset_btn.clicked.connect(self.refresh_page)
        self.export_btn.clicked.connect(self.export_to_csv)

    def refresh_page(self):
        for w in [self.start_date_edit, self.end_date_edit, self.username_filter, self.action_filter,
                  self.details_filter]: w.blockSignals(True)
        self.start_date_edit.setDate(QDate.currentDate().addDays(-7))
        self.end_date_edit.setDate(QDate.currentDate())
        self.username_filter.clear();
        self.action_filter.clear();
        self.details_filter.clear()
        for w in [self.start_date_edit, self.end_date_edit, self.username_filter, self.action_filter,
                  self.details_filter]: w.blockSignals(False)
        self._load_audit_data_async()

    def _load_audit_data_async(self):
        self.table_stack.setCurrentWidget(self.loading_label)
        params = {
            'start_date': self.start_date_edit.date().toPyDate(),
            'end_date': self.end_date_edit.date().addDays(1).toPyDate(),
            'username': f"%{self.username_filter.text()}%" if self.username_filter.text() else None,
            'action': f"%{self.action_filter.text()}%" if self.action_filter.text() else None,
            'details': f"%{self.details_filter.text()}%" if self.details_filter.text() else None,
        }
        self.load_thread = QThread()
        self.worker = AuditDataLoader(self.engine, params)
        self.worker.moveToThread(self.load_thread)
        self.load_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._on_audit_data_loaded)
        self.worker.error.connect(self._on_load_error)
        self.worker.finished.connect(self.load_thread.quit);
        self.worker.finished.connect(self.worker.deleteLater)
        self.load_thread.finished.connect(self.load_thread.deleteLater)
        self.load_thread.start()

    def _on_audit_data_loaded(self, data):
        self.audit_table.setRowCount(0)
        headers = ["Timestamp", "Username", "Action", "Details", "Hostname", "IP Address", "MAC Address"]
        self.audit_table.setColumnCount(len(headers));
        self.audit_table.setHorizontalHeaderLabels(headers)
        self.audit_table.setRowCount(len(data))
        for row, record in enumerate(data):
            # Ensure timestamp is formatted correctly, handling different date/datetime object types
            timestamp = record['timestamp']
            if isinstance(timestamp, datetime):
                ts_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')
            elif isinstance(timestamp, str):
                ts_str = timestamp  # Assume it's already a valid string if not a datetime object
            else:
                ts_str = str(timestamp)

            self.audit_table.setItem(row, 0, QTableWidgetItem(ts_str))
            self.audit_table.setItem(row, 1, QTableWidgetItem(record.get('username', '')))
            self.audit_table.setItem(row, 2, QTableWidgetItem(record.get('action_type', '')))
            self.audit_table.setItem(row, 3, QTableWidgetItem(record.get('details', '')))
            self.audit_table.setItem(row, 4, QTableWidgetItem(record.get('hostname', '')))
            self.audit_table.setItem(row, 5, QTableWidgetItem(record.get('ip_address', '')))
            self.audit_table.setItem(row, 6, QTableWidgetItem(record.get('mac_address', '')))

        self.audit_table.resizeColumnsToContents()
        self.audit_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table_stack.setCurrentWidget(self.audit_table)

    def _on_load_error(self, error_message):
        QMessageBox.critical(self, "Database Error", error_message)
        self.table_stack.setCurrentWidget(self.audit_table)

    def export_to_csv(self):
        if self.audit_table.rowCount() == 0:
            QMessageBox.information(self, "Export Info", "There is no data to export.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save CSV File",
                                              f"audit_trail_{datetime.now().strftime('%Y%m%d')}.csv",
                                              "CSV Files (*.csv)")
        if not path:
            return
        try:
            with open(path, 'w', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                headers = [self.audit_table.horizontalHeaderItem(i).text() for i in
                           range(self.audit_table.columnCount())]
                writer.writerow(headers)
                for row in range(self.audit_table.rowCount()):
                    row_data = [self.audit_table.item(row, col).text() for col in range(self.audit_table.columnCount())]
                    writer.writerow(row_data)
            QMessageBox.information(self, "Export Successful", f"Audit trail successfully exported to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"An error occurred while exporting the file: {e}")


# --- STANDALONE DEMO SETUP ---

def setup_in_memory_db_for_audit_trail():
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS qc_audit_trail (
                id INTEGER PRIMARY KEY,
                timestamp TIMESTAMP,
                username TEXT,
                action_type TEXT,
                details TEXT,
                hostname TEXT,
                ip_address TEXT,
                mac_address TEXT
            )
        """))

        # Insert mock data
        now = datetime.now()
        data = [
            {'timestamp': now, 'username': 'ADMIN', 'action_type': 'LOGIN', 'details': 'User logged in successfully.',
             'hostname': 'WORKSTATION1', 'ip_address': '192.168.1.10', 'mac_address': 'A1:B2:C3:D4:E5:F6'},
            {'timestamp': now, 'username': 'JANE_DOE', 'action_type': 'CREATE_RECORD',
             'details': 'Created new record INV-001.', 'hostname': 'LAPTOP-JANE', 'ip_address': '192.168.1.11',
             'mac_address': 'B1:B2:C3:D4:E5:F6'},
            {'timestamp': now.replace(minute=now.minute - 5), 'username': 'ADMIN', 'action_type': 'DELETE_RECORD',
             'details': 'Deleted old log entry LOG-2023.', 'hostname': 'WORKSTATION1', 'ip_address': '192.168.1.10',
             'mac_address': 'A1:B2:C3:D4:E5:F6'},
        ]
        conn.execute(text("""
            INSERT INTO qc_audit_trail (timestamp, username, action_type, details, hostname, ip_address, mac_address)
            VALUES (:timestamp, :username, :action_type, :details, :hostname, :ip_address, :mac_address)
        """), data)
        conn.commit()
    return engine


if __name__ == '__main__':
    app = QApplication(sys.argv)

    # 1. Setup Database
    engine = setup_in_memory_db_for_audit_trail()

    # 2. Setup Main Window
    main_window = QMainWindow()
    main_window.setWindowTitle("Standalone Audit Trail Log")
    # Set a large initial size
    main_window.resize(1000, 700)

    # 3. Instantiate the Page
    audit_page = AuditTrailPage(db_engine=engine)
    main_window.setCentralWidget(audit_page)

    # Apply standard global styles
    main_window.setStyleSheet("""
        QMainWindow { background-color: #f0f0f0; }
        QGroupBox { font-weight: bold; }
    """)

    main_window.show()
    sys.exit(app.exec())