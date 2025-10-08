import sys
import re
import socket
import uuid

try:
    import qtawesome as fa
except ImportError:
    print("FATAL ERROR: The 'qtawesome' library is required. Please install it using: pip install qtawesome")
    sys.exit(1)

from sqlalchemy import text
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtWidgets import (QMainWindow, QWidget, QLabel, QLineEdit,
                             QPushButton, QVBoxLayout, QHBoxLayout, QFrame)

# Local Imports
from Others.database import engine
from styles import AppStyles

class LoginWindow(QMainWindow):
    login_successful = pyqtSignal(str, str)

    def __init__(self):
        super().__init__()
        self.setObjectName("LoginWindow")
        self.setupUi()

    def setupUi(self):
        self.setWindowTitle("Finished Goods Program - Login")
        self.setWindowIcon(fa.icon('fa5s.box-open', color=AppStyles.PRIMARY_ACCENT_COLOR))
        self.resize(500, 650)
        widget = QWidget()
        self.setCentralWidget(widget)
        main_layout = QHBoxLayout(widget)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        frame = QFrame(objectName="FormFrame")
        frame.setMaximumWidth(400)
        main_layout.addWidget(frame)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(15)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(
            QLabel(pixmap=fa.icon('fa5s.boxes', color=AppStyles.PRIMARY_ACCENT_COLOR).pixmap(QSize(150, 150))),
            alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(10)
        layout.addWidget(
            QLabel("Finished Goods Login", objectName="LoginTitle", alignment=Qt.AlignmentFlag.AlignCenter))
        layout.addSpacing(25)
        self.username_widget, self.username = self._create_input_field('fa5s.user', "Username")
        self.password_widget, self.password = self._create_input_field('fa5s.lock', "Password")
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.username_widget)
        layout.addWidget(self.password_widget)
        layout.addSpacing(15)
        self.login_btn = QPushButton("Login", objectName="PrimaryButton", shortcut="Return", clicked=self.login)
        self.login_btn.setMinimumHeight(45)
        layout.addWidget(self.login_btn)
        self.status_label = QLabel("", objectName="StatusLabel", alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)
        layout.addStretch()
        self.setStyleSheet(AppStyles.LOGIN_STYLESHEET)

    def _create_input_field(self, icon, placeholder):
        c = QWidget(objectName="InputFrame")
        l = QHBoxLayout(c)
        l.setContentsMargins(10, 0, 5, 0)
        l.setSpacing(10)
        il = QLabel(pixmap=fa.icon(icon, color='#bdbdbd').pixmap(QSize(20, 20)))
        le = QLineEdit(placeholderText=placeholder)
        l.addWidget(il)
        l.addWidget(le)
        return c, le

    def login(self):
        u, p = self.username.text(), self.password.text()
        if not u or not p: self.status_label.setText("Username and password are required."); return
        self.login_btn.setEnabled(False)
        self.status_label.setText("Verifying...")
        try:
            with engine.connect() as c:
                with c.begin():
                    res = c.execute(text("SELECT password, qc_access, role FROM users WHERE username=:u"),
                                    {"u": u}).fetchone()
                    if res and res[0] == p:
                        if not res[1]: self.status_label.setText(
                            "This user does not have access."); self.login_btn.setEnabled(True); return
                        c.execute(text(
                            "INSERT INTO qc_audit_trail(timestamp, username, action_type, details, hostname, ip_address, mac_address) VALUES (NOW(), :u, 'LOGIN', 'User logged in.', :h, :i, :m)"),
                            {"u": u, **self._get_workstation_info()})
                        self.login_successful.emit(u, res[2])
                        self.close()
                    else:
                        self.status_label.setText("Invalid credentials.")
        except Exception as e:
            self.status_label.setText("Database connection error.")
            print(f"Login Error: {e}")
        finally:
            self.login_btn.setEnabled(True)

    def _get_workstation_info(self):
        try:
            h, i = socket.gethostname(), socket.gethostbyname(socket.gethostname())
        except:
            h, i = 'Unknown', 'N/A'
        try:
            m = ':'.join(re.findall('..', '%012x' % uuid.getnode()))
        except:
            m = 'N/A'
        return {"h": h, "i": i, "m": m}