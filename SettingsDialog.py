# File: SettingsDialog.py

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLineEdit,
                             QPushButton, QDialogButtonBox, QGroupBox, QSpinBox, QMessageBox)
from PyQt6.QtCore import QSettings


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Email Settings")
        self.setMinimumWidth(450)

        # Use QSettings to store data persistently
        # The arguments are your company/organization name and your application name
        self.settings = QSettings("MyCompany", "FGInventoryApp")

        main_layout = QVBoxLayout(self)

        # --- Sender Configuration ---
        sender_group = QGroupBox("Sender Details (SMTP)")
        sender_layout = QFormLayout(sender_group)

        self.sender_email_input = QLineEdit()
        self.sender_password_input = QLineEdit()
        self.sender_password_input.setEchoMode(QLineEdit.EchoMode.Password)  # Hide password
        self.smtp_server_input = QLineEdit()
        self.smtp_port_input = QSpinBox()
        self.smtp_port_input.setRange(1, 65535)

        sender_layout.addRow("Sender Email:", self.sender_email_input)
        sender_layout.addRow("Password:", self.sender_password_input)
        sender_layout.addRow("SMTP Server:", self.smtp_server_input)
        sender_layout.addRow("SMTP Port:", self.smtp_port_input)

        main_layout.addWidget(sender_group)

        # --- Recipient Configuration ---
        recipient_group = QGroupBox("Default Recipient")
        recipient_layout = QFormLayout(recipient_group)
        self.recipient_email_input = QLineEdit()
        self.recipient_email_input.setPlaceholderText("e.g., user1@example.com, user2@example.com")
        recipient_layout.addRow("Recipient Email(s):", self.recipient_email_input)

        main_layout.addWidget(recipient_group)

        # --- Save/Cancel Buttons ---
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)  # The accept slot will trigger saving
        button_box.rejected.connect(self.reject)

        main_layout.addWidget(button_box)

        self.load_settings()

    def load_settings(self):
        """Load settings from QSettings and populate the fields."""
        self.sender_email_input.setText(self.settings.value("email/sender_email", ""))
        # For security, we don't load/show the saved password, but we need to check if it exists.
        # A more advanced app would use the system keychain for secure storage.
        if self.settings.value("email/sender_password"):
            self.sender_password_input.setPlaceholderText("Password is saved. Enter a new one to change.")

        self.smtp_server_input.setText(self.settings.value("email/smtp_server", ""))
        self.smtp_port_input.setValue(int(self.settings.value("email/smtp_port", 587)))
        self.recipient_email_input.setText(self.settings.value("email/recipient_email", ""))

    def accept(self):
        """Save the current settings and close the dialog."""
        self.settings.setValue("email/sender_email", self.sender_email_input.text().strip())

        # Only save the password if the user has entered a new one
        if self.sender_password_input.text():
            self.settings.setValue("email/sender_password", self.sender_password_input.text())

        self.settings.setValue("email/smtp_server", self.smtp_server_input.text().strip())
        self.settings.setValue("email/smtp_port", self.smtp_port_input.value())
        self.settings.setValue("email/recipient_email", self.recipient_email_input.text().strip())

        QMessageBox.information(self, "Success", "Settings have been saved.")
        super().accept()