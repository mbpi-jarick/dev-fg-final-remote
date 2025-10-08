# audit_trail.py
# FINAL VERSION - Rebuilt with a modern UI and a new dashboard for activity overview.
# FIX - Corrected tab referencing and event handling to restore full functionality.
# ENHANCED - Upgraded dashboard chart to an interactive pie chart and removed dashboard table borders.

import sys
import csv
from datetime import datetime

from PyQt6.QtCore import Qt, QDate, QObject, pyqtSignal, QThread, QTimer
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
                             QAbstractItemView, QHeaderView, QMessageBox, QHBoxLayout, QLabel,
                             QPushButton, QDateEdit, QLineEdit, QFileDialog, QFormLayout,
                             QStackedWidget, QTabWidget, QGridLayout, QGroupBox, QSplitter)
from PyQt6.QtGui import QPainter, QColor
from PyQt6.QtCharts import QChartView, QChart, QPieSeries, QPieSlice

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
        self._update_dashboard_data()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        self.dashboard_tab = QWidget()
        self.view_tab = QWidget()

        self.tab_widget.addTab(self.dashboard_tab, "Dashboard")
        self.tab_widget.addTab(self.view_tab, "Audit Trail Records")

        self._setup_dashboard_tab(self.dashboard_tab)
        self._setup_view_tab(self.view_tab)

        self.tab_widget.currentChanged.connect(self._on_tab_changed)

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
        (self.kpi_events_card, self.kpi_events_value) = self._create_kpi_card("0", "Total Events Today")
        (self.kpi_users_card, self.kpi_users_value) = self._create_kpi_card("0", "Unique Users Today")
        (self.kpi_logins_card, self.kpi_logins_value) = self._create_kpi_card("0", "Logins Today")
        (self.kpi_deletes_card, self.kpi_deletes_value) = self._create_kpi_card("0", "Deletions Today")
        main_layout.addWidget(self.kpi_events_card, 0, 0)
        main_layout.addWidget(self.kpi_users_card, 0, 1)
        main_layout.addWidget(self.kpi_logins_card, 0, 2)
        main_layout.addWidget(self.kpi_deletes_card, 0, 3)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter, 1, 0, 1, 4)
        recent_group = QGroupBox("Recent Activity")
        recent_layout = QVBoxLayout(recent_group)
        self.dashboard_recent_table = QTableWidget()

        # UI TWEAK: Remove borders from dashboard table
        self.dashboard_recent_table.setShowGrid(False)
        self.dashboard_recent_table.setStyleSheet("QTableWidget { border: none; }")

        self.dashboard_recent_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.dashboard_recent_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.dashboard_recent_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.dashboard_recent_table.verticalHeader().setVisible(False)
        self.dashboard_recent_table.horizontalHeader().setHighlightSections(False)
        self.dashboard_recent_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        recent_layout.addWidget(self.dashboard_recent_table)
        splitter.addWidget(recent_group)
        top_users_group = QGroupBox("Top 5 Users by Activity (All Time)")
        chart_layout = QVBoxLayout(top_users_group)
        self.user_chart_view = QChartView()
        self.user_chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)

        # --- NEW CHART SETUP ---
        self.user_chart = QChart()
        self.user_pie_series = QPieSeries()
        self.user_pie_series.setHoleSize(0.35)
        self.user_pie_series.hovered.connect(self._handle_pie_slice_hover)

        self.user_chart.addSeries(self.user_pie_series)
        self.user_chart.setTitle("Top 5 Users by Activity")
        self.user_chart.setAnimationOptions(QChart.AnimationOption.SeriesAnimations)
        self.user_chart.legend().setVisible(True)
        self.user_chart.legend().setAlignment(Qt.AlignmentFlag.AlignRight)
        self.user_chart_view.setChart(self.user_chart)

        chart_layout.addWidget(self.user_chart_view)
        splitter.addWidget(top_users_group)
        splitter.setSizes([550, 450])

    def _setup_view_tab(self, tab):
        main_layout = QVBoxLayout(tab)
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

    def _on_tab_changed(self, index):
        if index == self.tab_widget.indexOf(self.dashboard_tab):
            self._update_dashboard_data()
        elif index == self.tab_widget.indexOf(self.view_tab):
            self.refresh_page()

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
        if self.audit_table.rowCount() == 0: QMessageBox.information(self, "Export Info",
                                                                     "There is no data to export."); return
        path, _ = QFileDialog.getSaveFileName(self, "Save CSV File",
                                              f"audit_trail_{datetime.now().strftime('%Y%m%d')}.csv",
                                              "CSV Files (*.csv)")
        if not path: return
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

    def _handle_pie_slice_hover(self, slice_item: QPieSlice, state: bool):
        if state:
            slice_item.setExploded(True)
            slice_item.setLabel(f"{slice_item.label()} ({slice_item.percentage():.1%})")
        else:
            slice_item.setExploded(False)
            original_label = slice_item.label().split(" (")[0]
            slice_item.setLabel(original_label)

    def _update_dashboard_data(self):
        try:
            with self.engine.connect() as conn:
                events_today = conn.execute(text(
                    "SELECT COUNT(*) FROM qc_audit_trail WHERE DATE(timestamp) = CURRENT_DATE")).scalar_one_or_none() or 0
                users_today = conn.execute(text(
                    "SELECT COUNT(DISTINCT username) FROM qc_audit_trail WHERE DATE(timestamp) = CURRENT_DATE")).scalar_one_or_none() or 0
                logins_today = conn.execute(text(
                    "SELECT COUNT(*) FROM qc_audit_trail WHERE DATE(timestamp) = CURRENT_DATE AND action_type = 'LOGIN_SUCCESS'")).scalar_one_or_none() or 0
                deletes_today = conn.execute(text(
                    "SELECT COUNT(*) FROM qc_audit_trail WHERE DATE(timestamp) = CURRENT_DATE AND action_type ILIKE 'DELETE%'")).scalar_one_or_none() or 0
                recent_activity = conn.execute(text(
                    "SELECT timestamp, username, action_type FROM qc_audit_trail ORDER BY timestamp DESC LIMIT 5")).mappings().all()
                top_users = conn.execute(text(
                    "SELECT username, COUNT(*) as action_count FROM qc_audit_trail GROUP BY username ORDER BY action_count DESC LIMIT 5")).mappings().all()

            self.kpi_events_value.setText(str(events_today))
            self.kpi_users_value.setText(str(users_today))
            self.kpi_logins_value.setText(str(logins_today))
            self.kpi_deletes_value.setText(str(deletes_today))

            self.dashboard_recent_table.setRowCount(len(recent_activity))
            self.dashboard_recent_table.setColumnCount(3)
            self.dashboard_recent_table.setHorizontalHeaderLabels(["Time", "User", "Action"])
            for row, record in enumerate(recent_activity):
                self.dashboard_recent_table.setItem(row, 0, QTableWidgetItem(record['timestamp'].strftime('%H:%M:%S')))
                self.dashboard_recent_table.setItem(row, 1, QTableWidgetItem(record['username']))
                self.dashboard_recent_table.setItem(row, 2, QTableWidgetItem(record['action_type']))
            self.dashboard_recent_table.resizeColumnsToContents()
            self.dashboard_recent_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

            # --- FIXED Pie Chart Logic ---
            self.user_pie_series.clear()
            if not top_users:
                self.user_chart.setTitle("Top 5 Users by Activity (No Data)")
                return

            self.user_chart.setTitle("Top 5 Users by Activity")
            for user in top_users:
                name = user['username']
                action_count = int(user.get('action_count') or 0)
                slice_item = self.user_pie_series.append(f"{name}\n{action_count} actions", action_count)
                slice_item.setLabelVisible(True)

        except Exception as e:
            QMessageBox.critical(self, "Dashboard Error", f"Could not load dashboard data: {e}")