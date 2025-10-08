# user_management.py
# FINAL VERIFIED VERSION (with background data loading)
# ENHANCED - Added dashboard with KPIs and an interactive pie chart for user activity.
# UI TWEAK - Removed borders from all tables for a cleaner, modern look.
# FIX - Removed cell focus rectangle on click for cleaner row selection.

from PyQt6.QtCore import Qt, QObject, pyqtSignal, QThread
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
                             QAbstractItemView, QHeaderView, QMessageBox, QHBoxLayout, QLabel,
                             QPushButton, QLineEdit, QComboBox, QCheckBox, QFormLayout, QGroupBox,
                             QStackedWidget, QTabWidget, QGridLayout, QSplitter)
from PyQt6.QtGui import QPainter, QColor
from PyQt6.QtCharts import QChartView, QChart, QPieSeries, QPieSlice

from sqlalchemy import text


# --- Worker to load user data in the background ---
class UserDataLoader(QObject):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, engine):
        super().__init__()
        self.engine = engine

    def run(self):
        try:
            with self.engine.connect() as conn:
                result = conn.execute(
                    text("SELECT id, username, role, qc_access FROM users ORDER BY username")).mappings().all()
                self.finished.emit(result)
        except Exception as e:
            self.error.emit(f"Failed to load users: {e}")


class UserManagementPage(QWidget):
    def __init__(self, db_engine, current_username, log_audit_trail_func):
        super().__init__()
        self.engine = db_engine
        self.current_username = current_username
        self.log_audit_trail = log_audit_trail_func

        self.current_editing_user_id = None
        self.load_thread = None
        self._setup_ui()
        self.refresh_page()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        self.dashboard_tab = QWidget()
        self.management_tab = QWidget()

        self.tab_widget.addTab(self.dashboard_tab, "Dashboard")
        self.tab_widget.addTab(self.management_tab, "User Management")

        self._setup_dashboard_tab(self.dashboard_tab)
        self._setup_management_tab(self.management_tab)

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
        (self.kpi_total_users_card, self.kpi_total_users_value) = self._create_kpi_card("0", "Total Users")
        (self.kpi_admins_card, self.kpi_admins_value) = self._create_kpi_card("0", "Admin Accounts")
        (self.kpi_editors_card, self.kpi_editors_value) = self._create_kpi_card("0", "Editor Accounts")
        (self.kpi_wh_access_card, self.kpi_wh_access_value) = self._create_kpi_card("0", "Users with WH Access")
        main_layout.addWidget(self.kpi_total_users_card, 0, 0)
        main_layout.addWidget(self.kpi_admins_card, 0, 1)
        main_layout.addWidget(self.kpi_editors_card, 0, 2)
        main_layout.addWidget(self.kpi_wh_access_card, 0, 3)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter, 1, 0, 1, 4)
        recent_group = QGroupBox("Recent Activity")
        recent_layout = QVBoxLayout(recent_group)
        self.dashboard_recent_table = QTableWidget()

        self.dashboard_recent_table.setShowGrid(False)
        self.dashboard_recent_table.setStyleSheet("QTableWidget { border: none; }")
        self.dashboard_recent_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # FIX: Remove focus rectangle

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

    def _setup_management_tab(self, tab):
        main_layout = QVBoxLayout(tab)

        table_group = QGroupBox("Existing Users")
        table_layout = QVBoxLayout()

        self.table_stack = QStackedWidget()
        self.users_table = QTableWidget()

        # --- UI TWEAK: Set row selection, remove grid lines, and remove focus rectangle ---
        self.users_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.users_table.setShowGrid(False)
        self.users_table.setStyleSheet("QTableWidget { border: none; }")
        self.users_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.users_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.users_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.users_table.verticalHeader().setVisible(False)
        self.users_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        self.loading_label = QLabel("Loading data...", alignment=Qt.AlignmentFlag.AlignCenter)
        self.loading_label.setStyleSheet("font-size: 14pt; color: grey;")

        self.table_stack.addWidget(self.users_table)
        self.table_stack.addWidget(self.loading_label)

        table_layout.addWidget(self.table_stack)
        table_group.setLayout(table_layout)

        form_group = QGroupBox("Add / Edit User")
        self.form_layout = QFormLayout()
        self.form_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        self.form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self.username_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("Leave empty to keep current password")
        self.confirm_password_edit = QLineEdit()
        self.confirm_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.role_combo = QComboBox()
        self.role_combo.addItems(["Editor", "Admin"])
        self.qc_access_check = QCheckBox("Has WH Program Access")
        self.form_layout.addRow("Username:", self.username_edit)
        self.form_layout.addRow("New Password:", self.password_edit)
        self.form_layout.addRow("Confirm Password:", self.confirm_password_edit)
        self.form_layout.addRow("Role:", self.role_combo)
        self.form_layout.addRow(self.qc_access_check)
        form_group.setLayout(self.form_layout)

        self.load_btn = QPushButton("Load Selected User")
        self.save_btn = QPushButton("Save New User")
        self.save_btn.setObjectName("PrimaryButton")
        self.delete_btn = QPushButton("Delete Selected User")
        self.clear_btn = QPushButton("Clear Form / New User")
        top_button_layout = QHBoxLayout()
        top_button_layout.addStretch()
        top_button_layout.addWidget(self.load_btn)
        top_button_layout.addWidget(self.delete_btn)
        bottom_button_layout = QHBoxLayout()
        bottom_button_layout.addStretch()
        bottom_button_layout.addWidget(self.clear_btn)
        bottom_button_layout.addWidget(self.save_btn)

        main_layout.addWidget(table_group)
        main_layout.addLayout(top_button_layout)
        main_layout.addWidget(form_group)
        main_layout.addLayout(bottom_button_layout)

        self.load_btn.clicked.connect(self._load_selected_user_to_form)
        self.users_table.doubleClicked.connect(self._load_selected_user_to_form)
        self.save_btn.clicked.connect(self._save_user)
        self.delete_btn.clicked.connect(self._delete_user)
        self.clear_btn.clicked.connect(self._clear_form)

    def refresh_page(self):
        if self.tab_widget.currentIndex() == self.tab_widget.indexOf(self.dashboard_tab):
            self._update_dashboard_data()
        else:
            self._load_users_async()
        self._clear_form()

    def _on_tab_changed(self, index):
        if index == self.tab_widget.indexOf(self.dashboard_tab):
            self._update_dashboard_data()
        elif index == self.tab_widget.indexOf(self.management_tab):
            self._load_users_async()

    def _load_users_async(self):
        self.table_stack.setCurrentWidget(self.loading_label)

        self.load_thread = QThread()
        self.worker = UserDataLoader(self.engine)
        self.worker.moveToThread(self.load_thread)

        self.load_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._on_users_loaded)
        self.worker.error.connect(self._on_load_error)

        self.worker.finished.connect(self.load_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.load_thread.finished.connect(self.load_thread.deleteLater)

        self.load_thread.start()

    def _on_users_loaded(self, user_list):
        self.users_table.setRowCount(0)
        headers = ["ID", "Username", "Role", "WH Access"]
        self.users_table.setColumnCount(len(headers))
        self.users_table.setHorizontalHeaderLabels(headers)

        self.users_table.setRowCount(len(user_list))
        for row, user in enumerate(user_list):
            self.users_table.setItem(row, 0, QTableWidgetItem(str(user['id'])))
            self.users_table.setItem(row, 1, QTableWidgetItem(user['username']))
            self.users_table.setItem(row, 2, QTableWidgetItem(user['role']))
            access_item = QTableWidgetItem("Yes" if user['qc_access'] else "No")
            access_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.users_table.setItem(row, 3, access_item)
            self.users_table.item(row, 0).setData(Qt.ItemDataRole.UserRole, user['id'])

        self.users_table.resizeColumnsToContents()
        self.users_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_stack.setCurrentWidget(self.users_table)

    def _on_load_error(self, error_message):
        QMessageBox.critical(self, "Database Error", error_message)
        self.table_stack.setCurrentWidget(self.users_table)

    def _clear_form(self):
        self.current_editing_user_id = None
        self.username_edit.clear();
        self.username_edit.setReadOnly(False)
        self.password_edit.clear();
        self.confirm_password_edit.clear()
        self.role_combo.setCurrentText("Editor");
        self.qc_access_check.setChecked(True)
        self.save_btn.setText("Save New User");
        self.users_table.clearSelection()
        self.username_edit.setFocus()

    def _load_selected_user_to_form(self):
        selected_rows = self.users_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "Selection Required", "Please select a user to load.")
            return
        user_id = self.users_table.item(selected_rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        try:
            with self.engine.connect() as conn:
                user = conn.execute(text("SELECT * FROM users WHERE id = :id"), {"id": user_id}).mappings().one()
            self._clear_form()
            self.current_editing_user_id = user['id']
            self.username_edit.setText(user['username']);
            self.username_edit.setReadOnly(True)
            self.role_combo.setCurrentText(user['role']);
            self.qc_access_check.setChecked(user['qc_access'])
            self.save_btn.setText("Update User")
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Could not load user data: {e}")

    def _save_user(self):
        username = self.username_edit.text().strip()
        password = self.password_edit.text()
        confirm_password = self.confirm_password_edit.text()
        role = self.role_combo.currentText()
        has_access = self.qc_access_check.isChecked()

        if not username: QMessageBox.warning(self, "Input Error", "Username cannot be empty."); return
        if password != confirm_password: QMessageBox.warning(self, "Input Error", "Passwords do not match."); return
        if self.current_editing_user_id is None and not password: QMessageBox.warning(self, "Input Error",
                                                                                      "Password is required for new users."); return

        try:
            with self.engine.connect() as conn:
                with conn.begin() as transaction:
                    if self.current_editing_user_id:
                        if password:
                            conn.execute(text(
                                "UPDATE users SET password = :pwd, role = :role, qc_access = :access WHERE id = :id"),
                                {"pwd": password, "role": role, "access": has_access,
                                 "id": self.current_editing_user_id})
                        else:
                            conn.execute(text("UPDATE users SET role = :role, qc_access = :access WHERE id = :id"),
                                         {"role": role, "access": has_access, "id": self.current_editing_user_id})
                        self.log_audit_trail("UPDATE_USER", f"Updated details for user: {username}");
                        QMessageBox.information(self, "Success", f"User '{username}' has been updated.")
                    else:
                        exists = conn.execute(text("SELECT id FROM users WHERE username = :user"),
                                              {"user": username}).scalar_one_or_none()
                        if exists: QMessageBox.critical(self, "Error",
                                                        f"Username '{username}' already exists."); transaction.rollback(); return
                        conn.execute(text(
                            "INSERT INTO users (username, password, role, qc_access) VALUES (:user, :pwd, :role, :access)"),
                            {"user": username, "pwd": password, "role": role, "access": has_access})
                        self.log_audit_trail("CREATE_USER", f"Created new user: {username}");
                        QMessageBox.information(self, "Success", f"New user '{username}' has been created.")
            self._load_users_async();
            self._clear_form()
            self._update_dashboard_data()
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"An error occurred while saving the user: {e}")

    def _delete_user(self):
        selected_rows = self.users_table.selectionModel().selectedRows()
        if not selected_rows: QMessageBox.warning(self, "Selection Required", "Please select a user to delete."); return
        row = selected_rows[0].row()
        user_id = self.users_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        username = self.users_table.item(row, 1).text()
        if username == self.current_username: QMessageBox.critical(self, "Action Not Allowed",
                                                                   "You cannot delete your own account."); return
        reply = QMessageBox.question(self, "Confirm Deletion",
                                     f"Are you sure you want to permanently delete the user '{username}'?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                with self.engine.connect() as conn:
                    with conn.begin():
                        conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
                        self.log_audit_trail("DELETE_USER", f"Deleted user: {username}")
                QMessageBox.information(self, "Success", f"User '{username}' has been deleted.")
                self._load_users_async();
                self._clear_form()
                self._update_dashboard_data()
            except Exception as e:
                QMessageBox.critical(self, "Database Error", f"An error occurred while deleting the user: {e}")

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
                total_users = conn.execute(text("SELECT COUNT(*) FROM users")).scalar_one_or_none() or 0
                admins = conn.execute(text("SELECT COUNT(*) FROM users WHERE role = 'Admin'")).scalar_one_or_none() or 0
                editors = conn.execute(
                    text("SELECT COUNT(*) FROM users WHERE role = 'Editor'")).scalar_one_or_none() or 0
                wh_access = conn.execute(
                    text("SELECT COUNT(*) FROM users WHERE qc_access = TRUE")).scalar_one_or_none() or 0
                recent_activity = conn.execute(text(
                    "SELECT timestamp, username, action_type FROM qc_audit_trail ORDER BY timestamp DESC LIMIT 5")).mappings().all()
                top_users = conn.execute(text(
                    "SELECT username, COUNT(*) as action_count FROM qc_audit_trail GROUP BY username ORDER BY action_count DESC LIMIT 5")).mappings().all()

            self.kpi_total_users_value.setText(str(total_users))
            self.kpi_admins_value.setText(str(admins))
            self.kpi_editors_value.setText(str(editors))
            self.kpi_wh_access_value.setText(str(wh_access))

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