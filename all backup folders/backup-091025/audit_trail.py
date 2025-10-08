# audit_trail.py
# FINAL VERSION - Rebuilt with a modern UI and a new dashboard for activity overview.
# FIX - Corrected tab referencing and event handling to restore full functionality.
# ENHANCED - Upgraded dashboard chart to an interactive pie chart and removed dashboard table borders.
# MODIFICATION - Removed Dashboard feature to simplify the interface.

import sys
import csv
from datetime import datetime

from PyQt6.QtCore import Qt, QDate, QObject, pyqtSignal, QThread, QTimer
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
                             QAbstractItemView, QHeaderView, QMessageBox, QHBoxLayout, QLabel,
                             QPushButton, QDateEdit, QLineEdit, QFileDialog, QFormLayout,
                             QStackedWidget, QGroupBox)

from sqlalchemy import text


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
            query = "SELECT timestamp, username, action_type, details, hostname, ip_address, mac_address FROM qc_audit_trail WHERE 1=1"
            query += " AND timestamp BETWEEN :start_date AND :end_date"
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
    def __init__(self, db_engine):
        super().__init__()
        self.engine = db_engine
        self.load_thread = None
        self._setup_ui()
        self.refresh_page()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)

        # --- Filters ---
        filter_group = QGroupBox("Filters")
        filter_layout = QFormLayout(filter_group)
        filter_layout.setSpacing(10)
        self.start_date_edit = QDateEdit(calendarPopup=True, displayFormat="yyyy-MM-dd")
        self.end_date_edit = QDateEdit(calendarPopup=True, displayFormat="yyyy-MM-dd")
        self.username_filter = QLineEdit(placeholderText="Filter by username...")
        self.action_filter = QLineEdit(placeholderText="Filter by action (e.g., LOGIN, DELETE)...")
        self.details_filter = QLineEdit(placeholderText="Search in details...")
        self.reset_btn = QPushButton("Reset Filters");
        self.reset_btn.setObjectName("SecondaryButton")
        self.export_btn = QPushButton("Export to CSV")

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
        self.table_stack.addWidget(self.loading_label)
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
            self.audit_table.setItem(row, 0, QTableWidgetItem(record['timestamp'].strftime('%Y-%m-%d %H:%M:%S')))
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