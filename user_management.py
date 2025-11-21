# user_management.py
import sys
import qtawesome as fa
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QThread, QSize
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
                             QAbstractItemView, QHeaderView, QMessageBox, QHBoxLayout, QLabel,
                             QPushButton, QLineEdit, QComboBox, QCheckBox, QFormLayout, QGroupBox,
                             QStackedWidget, QApplication, QMainWindow, QTextEdit)
from PyQt6.QtGui import QFont

from sqlalchemy import create_engine, text


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
    HEADER_COLOR = "#3a506b"

    def __init__(self, db_engine, current_username, log_audit_trail_func):
        super().__init__()
        self.engine = db_engine
        self.current_username = current_username
        self.log_audit_trail = log_audit_trail_func
        self.current_editing_user_id = None
        self.load_thread = None

        # MODIFICATION 1: Determine the role of the current user upon initialization.
        self.current_user_role = 'Viewer'  # Default to the most restrictive role for safety
        try:
            with self.engine.connect() as conn:
                role = conn.execute(text("SELECT role FROM users WHERE username = :user"),
                                    {"user": self.current_username}).scalar_one_or_none()
                if role:
                    self.current_user_role = role
        except Exception as e:
            # Log this error in a real application
            print(f"Warning: Could not determine role for '{self.current_username}'. Defaulting to Viewer. Error: {e}")

        self._setup_ui()
        # MODIFICATION 2: Apply permissions based on the user's role after the UI is built.
        self._apply_permissions()

        self.refresh_page()
        self.setStyleSheet(self._get_styles())

    def _create_instruction_box(self, text):
        instruction_box = QGroupBox("Instructions")
        instruction_box.setObjectName("InstructionsBox")
        instruction_layout = QHBoxLayout(instruction_box)
        instruction_layout.setContentsMargins(10, 10, 10, 10)

        icon_label = QLabel()
        icon_label.setPixmap(fa.icon('fa5s.info-circle', color='#17A2B8').pixmap(QSize(24, 24)))

        text_edit = QTextEdit(text, objectName="InstructionsText")
        text_edit.setReadOnly(True)
        text_edit.setMaximumHeight(60)
        text_edit.setFrameShape(QTextEdit.Shape.NoFrame)

        instruction_layout.addWidget(icon_label)
        instruction_layout.addWidget(text_edit, 1)

        return instruction_box

    def _get_styles(self):
        # Styles to ensure the header text and icon are the specified color
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
            #PrimaryButton {{ 
                background-color: {self.HEADER_COLOR}; 
                color: white; 
                border-radius: 4px; 
                padding: 5px; 
            }}
            #PrimaryButton:hover {{ 
                background-color: #2b3a4a; 
            }}
            #DestructiveButton {{ background-color: #dc3545; color: white; border-radius: 4px; padding: 5px; }}
            #DestructiveButton:hover {{ background-color: #c82333; }}

            /* Disabled styles for Viewer mode */
            QPushButton:disabled, QLineEdit:disabled, QComboBox:disabled, QCheckBox:disabled {{
                background-color: #f0f0f0;
                color: #a0a0a0;
            }}

            /* Table */
            QTableWidget {{ border: none; background-color: white; }}
            QTableWidget::item:selected {{
                background-color: {self.HEADER_COLOR}; 
                color: white;
            }}

            /* Instructions Box Style */
            QGroupBox#InstructionsBox {{
                border: 1px solid #17A2B8; 
                background-color: #f7faff; 
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
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # --- 1. Structured Header ---
        header_widget = QWidget(objectName="HeaderWidget")
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 5)

        icon_pixmap = fa.icon('fa5s.users', color=self.HEADER_COLOR).pixmap(QSize(28, 28))
        icon_label = QLabel()
        icon_label.setPixmap(icon_pixmap)
        header_layout.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignLeft)

        header_label = QLabel("USER MANAGEMENT", objectName="PageHeader")
        header_layout.addWidget(header_label)
        header_layout.addStretch()
        main_layout.addWidget(header_widget)

        # --- 2. Instructions Box ---
        # MODIFICATION 3: Display different instructions based on user role.
        if self.current_user_role == 'Viewer':
            instruction_text = "You are in viewing-only mode. You can see the list of users, but you cannot add, edit, or delete accounts."
        else:
            instruction_text = "Use this form to manage user accounts. Double-click an existing user in the table or use 'Load Selected User' to modify their role or password. The Username cannot be changed after creation."

        instructions = self._create_instruction_box(instruction_text)
        main_layout.addWidget(instructions)

        # --- 3. Existing Users Table (STRETCHED) ---
        table_group = QGroupBox("Existing Users")
        table_layout = QVBoxLayout()
        table_layout.setContentsMargins(10, 10, 10, 10)

        self.table_stack = QStackedWidget()
        self.users_table = QTableWidget()
        self.users_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.users_table.setShowGrid(False)
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

        # --- 4. Form Group (COMPACT) ---
        self.form_group = QGroupBox("Add / Edit User")
        self.form_layout = QFormLayout()
        self.form_layout.setContentsMargins(10, 10, 10, 10)
        self.form_layout.setSpacing(5)
        self.form_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        self.form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.username_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("Leave empty to keep current password")
        self.confirm_password_edit = QLineEdit()
        self.confirm_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.role_combo = QComboBox()
        # MODIFICATION 4: Add "Viewer" to the list of available roles.
        self.role_combo.addItems(["Viewer", "Editor", "Admin"])
        self.qc_access_check = QCheckBox("Has WH Program Access")

        self.form_layout.addRow("Username:", self.username_edit)
        self.form_layout.addRow("New Password:", self.password_edit)
        self.form_layout.addRow("Confirm Password:", self.confirm_password_edit)
        self.form_layout.addRow("Role:", self.role_combo)
        self.form_layout.addRow(self.qc_access_check)
        self.form_group.setLayout(self.form_layout)

        self.load_btn = QPushButton("Load Selected User")
        self.save_btn = QPushButton("Save New User")
        self.save_btn.setObjectName("PrimaryButton")
        self.delete_btn = QPushButton("Delete Selected User")
        self.delete_btn.setObjectName("DestructiveButton")
        self.clear_btn = QPushButton("Clear Form / New User")

        top_button_layout = QHBoxLayout()
        top_button_layout.addStretch()
        top_button_layout.addWidget(self.load_btn)
        top_button_layout.addWidget(self.delete_btn)

        bottom_button_layout = QHBoxLayout()
        bottom_button_layout.addStretch()
        bottom_button_layout.addWidget(self.clear_btn)
        bottom_button_layout.addWidget(self.save_btn)

        main_layout.addWidget(table_group, 1)
        main_layout.addLayout(top_button_layout)
        main_layout.addWidget(self.form_group)
        main_layout.addLayout(bottom_button_layout)

        self.load_btn.clicked.connect(self._load_selected_user_to_form)
        self.users_table.doubleClicked.connect(self._load_selected_user_to_form)
        self.save_btn.clicked.connect(self._save_user)
        self.delete_btn.clicked.connect(self._delete_user)
        self.clear_btn.clicked.connect(self._clear_form)

    # MODIFICATION 5: New method to disable UI elements for viewers.
    def _apply_permissions(self):
        """Disables UI controls if the current user has a 'Viewer' role."""
        if self.current_user_role == 'Viewer':
            # Change the form title to indicate read-only status
            self.form_group.setTitle("User Details (Viewing Only)")

            # Disable all interactive form widgets
            self.username_edit.setEnabled(False)
            self.password_edit.setEnabled(False)
            self.confirm_password_edit.setEnabled(False)
            self.role_combo.setEnabled(False)
            self.qc_access_check.setEnabled(False)

            # Disable all action buttons
            self.load_btn.setEnabled(False)
            self.save_btn.setEnabled(False)
            self.delete_btn.setEnabled(False)
            self.clear_btn.setEnabled(False)

            # Prevent loading user data into the form via double-click
            self.users_table.doubleClicked.disconnect(self._load_selected_user_to_form)

    def refresh_page(self):
        self._load_users_async()
        if self.current_user_role != 'Viewer':
            self._clear_form()

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
            except Exception as e:
                QMessageBox.critical(self, "Database Error", f"An error occurred while deleting the user: {e}")


# --- STANDALONE DEMO SETUP ---

def setup_in_memory_db_for_user_management():
    """Sets up a minimal in-memory SQLite database for user management demo."""
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT,
                qc_access BOOLEAN
            )
        """))

        # MODIFICATION 6: Update demo data to include a 'Viewer' role.
        initial_users = [
            {'username': 'ADMIN', 'password': 'hashed_admin_pwd', 'role': 'Admin', 'qc_access': True},
            {'username': 'JANE_DOE', 'password': 'hashed_jane_pwd', 'role': 'Editor', 'qc_access': True},
            {'username': 'VIEWER', 'password': 'hashed_viewer_pwd', 'role': 'Viewer', 'qc_access': False},
        ]
        conn.execute(text(
            "INSERT INTO users (username, password, role, qc_access) VALUES (:username, :password, :role, :qc_access) ON CONFLICT(username) DO NOTHING"
        ), initial_users)
        conn.commit()
    return engine


def mock_log_audit_trail(action, description):
    print(f"[AUDIT TRAIL] User: STANDALONE_USER | Action: {action} | Desc: {description}")


if __name__ == '__main__':
    app = QApplication(sys.argv)

    # 1. Setup Database
    engine = setup_in_memory_db_for_user_management()

    # 2. Setup Main Window
    main_window = QMainWindow()
    main_window.setWindowTitle("Standalone User Management")
    main_window.resize(800, 650)

    # 3. Instantiate the Page
    # --- MODIFICATION 7: Choose which user to test as. ---

    # --- TEST AS ADMIN (Full Access) ---
    # The form and all buttons will be enabled.
    current_user_to_test = "ADMIN"

    # --- TEST AS VIEWER (Read-Only) ---
    # Uncomment the line below to test the viewer mode.
    # The form and all buttons will be disabled.
    # current_user_to_test = "VIEWER"

    user_page = UserManagementPage(
        db_engine=engine,
        current_username=current_user_to_test,
        log_audit_trail_func=mock_log_audit_trail
    )
    main_window.setCentralWidget(user_page)

    # Apply standard global styles if needed (page handles its own theme)
    main_window.setStyleSheet("""
        QMainWindow { background-color: #f0f0f0; }
        QGroupBox { font-weight: bold; }
        #DestructiveButton { background-color: #dc3545; color: white; border-radius: 4px; padding: 5px; }
        #DestructiveButton:hover { background-color: #c82333; }
    """)

    main_window.show()
    sys.exit(app.exec())