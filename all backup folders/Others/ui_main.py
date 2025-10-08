import sys
import re
import socket
import uuid
from datetime import datetime

try:
    import qtawesome as fa
except ImportError:
    print("FATAL ERROR: The 'qtawesome' library is required. Please install it using: pip install qtawesome")
    sys.exit(1)

from sqlalchemy import text
from PyQt6.QtCore import (Qt, QSize, QEvent, QTimer, QThread, QPropertyAnimation)
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, QPushButton,
                             QMessageBox, QVBoxLayout, QHBoxLayout, QStackedWidget,
                             QFrame, QStatusBar, QDialog)
from PyQt6.QtGui import QFont

# Local Imports
from Others.database import engine
from styles import AppStyles
from ui_widgets import NetworkGraphWidget, PSUTIL_AVAILABLE
from workers import SyncWorker, SyncCustomerWorker, SyncDeliveryWorker, SyncRRFWorker

# --- All page imports ---
from fg_endorsement import FGEndorsementPage
from outgoing_form import OutgoingFormPage
from rrf import RRFPage
from receiving_report import ReceivingReportPage
from qc_failed_passed_endorsement import QCFailedPassedPage
from qc_excess_endorsement import QCExcessEndorsementPage
from qc_failed_endorsement import QCFailedEndorsementPage
from product_delivery import ProductDeliveryPage
from requisition_logbook import RequisitionLogbookPage
from audit_trail import AuditTrailPage
from user_management import UserManagementPage
from transactions_form import TransactionsFormPage
from failed_transactions_form import FailedTransactionsFormPage


class ModernMainWindow(QMainWindow):
    EXPANDED_MENU_WIDTH = 230
    COLLAPSED_MENU_WIDTH = 60

    def __init__(self, username, user_role, login_window):
        super().__init__()
        self.username, self.user_role, self.login_window = username, user_role, login_window
        self.icon_maximize, self.icon_restore = fa.icon('fa5s.expand-arrows-alt', color='#ecf0f1'), fa.icon(
            'fa5s.compress-arrows-alt', color='#ecf0f1')
        self.setWindowTitle("Finished Goods Program")
        self.setWindowIcon(fa.icon('fa5s.check-double', color='gray'))
        self.setMinimumSize(1280, 720)
        self.setGeometry(100, 100, 1366, 768)
        self.workstation_info = self._get_workstation_info()
        self.sync_thread, self.sync_worker = None, None
        self.customer_sync_thread, self.customer_sync_worker = None, None
        self.delivery_sync_thread, self.delivery_sync_worker = None, None
        self.rrf_sync_thread, self.rrf_sync_worker = None, None
        self.is_menu_expanded = True
        self.init_ui()

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

    def log_audit_trail(self, action_type, details):
        try:
            log_query = text(
                "INSERT INTO qc_audit_trail (timestamp, username, action_type, details, hostname, ip_address, mac_address) VALUES (NOW(), :u, :a, :d, :h, :i, :m)")
            with engine.connect() as connection:
                with connection.begin(): connection.execute(log_query,
                                                            {"u": self.username, "a": action_type, "d": details,
                                                             **self.workstation_info})
        except Exception as e:
            print(f"CRITICAL: Audit trail error: {e}")

    def init_ui(self):
        main_widget = QWidget()
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.side_menu = self.create_side_menu()
        main_layout.addWidget(self.side_menu)

        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget)

        # Page Instantiations
        self.fg_endorsement_page = FGEndorsementPage(engine, self.username, self.log_audit_trail)
        self.outgoing_form_page = OutgoingFormPage(engine, self.username, self.log_audit_trail)
        self.rrf_page = RRFPage(engine, self.username, self.log_audit_trail)
        self.receiving_report_page = ReceivingReportPage(engine, self.username, self.log_audit_trail)
        self.qc_failed_passed_page = QCFailedPassedPage(engine, self.username, self.log_audit_trail)
        self.qc_excess_page = QCExcessEndorsementPage(engine, self.username, self.log_audit_trail)
        self.qc_failed_endorsement_page = QCFailedEndorsementPage(engine, self.username, self.log_audit_trail)
        self.product_delivery_page = ProductDeliveryPage(engine, self.username, self.log_audit_trail)
        self.requisition_logbook_page = RequisitionLogbookPage(engine, self.username, self.log_audit_trail)
        self.transactions_page = TransactionsFormPage(engine, self.username, self.log_audit_trail)
        self.failed_transactions_page = FailedTransactionsFormPage(engine, self.username, self.log_audit_trail)
        self.audit_trail_page = AuditTrailPage(engine)
        self.user_management_page = UserManagementPage(engine, self.username, self.log_audit_trail)

        # Add pages to Stacked Widget
        pages = [
            self.fg_endorsement_page, self.transactions_page, self.failed_transactions_page,
            self.outgoing_form_page, self.rrf_page, self.receiving_report_page,
            self.qc_failed_passed_page, self.qc_excess_page, self.qc_failed_endorsement_page,
            self.product_delivery_page, self.requisition_logbook_page,
            self.audit_trail_page, self.user_management_page
        ]
        for page in pages:
            self.stacked_widget.addWidget(page)

        self.setCentralWidget(main_widget)
        self.setup_status_bar()
        self.apply_styles()
        if self.user_role != 'Admin': self.btn_user_mgmt.hide()
        self.update_maximize_button()
        self.show_page(0)
        self.btn_fg_endorsement.setChecked(True)

    def create_side_menu(self):
        # (Your create_side_menu method code goes here, unchanged)
        self.menu_buttons = []
        menu = QWidget(objectName="SideMenu")
        menu.setMinimumWidth(self.EXPANDED_MENU_WIDTH)
        layout = QVBoxLayout(menu)
        layout.setContentsMargins(5, 10, 5, 10)
        layout.setSpacing(3)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.btn_toggle_menu = QPushButton(icon=fa.icon('fa5s.bars', color='#ecf0f1'))
        self.btn_toggle_menu.clicked.connect(self.toggle_side_menu)
        self.btn_toggle_menu.setStyleSheet(
            "background-color: transparent; border: none; text-align: left; padding: 5px 5px 5px 15px;")
        self.btn_toggle_menu.setIconSize(QSize(20, 20))
        layout.addWidget(self.btn_toggle_menu)
        layout.addSpacing(5)

        profile = QWidget()
        pl = QHBoxLayout(profile)
        pl.setContentsMargins(10, 0, 0, 0)
        pl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        pl.addWidget(QLabel(pixmap=fa.icon('fa5s.user-circle', color='#ecf0f1').pixmap(QSize(36, 36))))
        profile_text_layout = QVBoxLayout()
        profile_text_layout.setSpacing(0)
        self.profile_name_label = QLabel(f"{self.username}", objectName="ProfileName")
        self.profile_role_label = QLabel(f"{self.user_role}", objectName="ProfileRole")
        profile_text_layout.addWidget(self.profile_name_label)
        profile_text_layout.addWidget(self.profile_role_label)
        pl.addLayout(profile_text_layout)
        layout.addWidget(profile)
        layout.addSpacing(10)

        # --- RE-INDEXED MENU BUTTONS ---
        self.btn_fg_endorsement = self.create_menu_button("  FG Endorsement", 'fa5s.file-signature', 0)
        self.btn_transactions = self.create_menu_button("  Log Transaction", 'fa5s.exchange-alt', 1)
        self.btn_failed_transactions = self.create_menu_button("  FG Failed Log", 'fa5s.exclamation-triangle', 2)
        self.btn_outgoing_form = self.create_menu_button("  Outgoing Form", 'fa5s.sign-out-alt', 3)
        self.btn_rrf = self.create_menu_button("  RRF Form", 'fa5s.undo-alt', 4)
        self.btn_receiving_report = self.create_menu_button("  Receiving Report", 'fa5s.truck-loading', 5)
        self.btn_qc_failed_passed = self.create_menu_button("  QC Failed->Passed", 'fa5s.flask', 6)
        self.btn_qc_excess = self.create_menu_button("  QC Excess", 'fa5s.box', 7)
        self.btn_qc_failed = self.create_menu_button("  QC Failed", 'fa5s.times-circle', 8)
        self.btn_product_delivery = self.create_menu_button("  Product Delivery", 'fa5s.truck', 9)
        self.btn_requisition_logbook = self.create_menu_button("  Requisition Logbook", 'fa5s.book', 10)

        self.btn_sync_prod = self.create_menu_button("  Sync Production", 'fa5s.sync-alt', -1, self.start_sync_process)
        self.btn_sync_customers = self.create_menu_button("  Sync Customers", 'fa5s.address-book', -1,
                                                          self.start_customer_sync_process)
        self.btn_sync_deliveries = self.create_menu_button("  Sync Deliveries", 'fa5s.history', -1,
                                                           self.start_delivery_sync_process)
        self.btn_sync_rrf = self.create_menu_button("  Sync RRF", 'fa5s.retweet', -1, self.start_rrf_sync_process)

        self.btn_audit_trail = self.create_menu_button("  Audit Trail", 'fa5s.clipboard-list', 11)
        self.btn_user_mgmt = self.create_menu_button("  User Management", 'fa5s.users-cog', 12)

        self.btn_maximize = self.create_menu_button("  Maximize", 'fa5s.expand-arrows-alt', -1, self.toggle_maximize)
        self.btn_logout = self.create_menu_button("  Logout", 'fa5s.sign-out-alt', -1, self.logout)
        self.btn_exit = self.create_menu_button("  Exit", 'fa5s.power-off', -1, self.exit_application)

        # Add Buttons to Layout
        layout.addWidget(self.btn_fg_endorsement)
        layout.addWidget(self.btn_transactions)
        layout.addWidget(self.btn_failed_transactions)
        layout.addWidget(self.btn_outgoing_form)
        layout.addWidget(self.btn_rrf)
        layout.addWidget(self.btn_receiving_report)
        layout.addWidget(self.btn_qc_failed_passed)
        layout.addWidget(self.btn_qc_excess)
        layout.addWidget(self.btn_qc_failed)
        layout.addWidget(self.btn_product_delivery)
        layout.addWidget(self.btn_requisition_logbook)

        separator1 = QFrame();
        separator1.setFrameShape(QFrame.Shape.HLine);
        separator1.setFixedHeight(1)
        separator1.setStyleSheet("background-color: #34495e; margin: 8px 5px;")
        layout.addWidget(separator1)

        layout.addWidget(self.btn_sync_prod)
        layout.addWidget(self.btn_sync_customers)
        layout.addWidget(self.btn_sync_deliveries)
        layout.addWidget(self.btn_sync_rrf)

        separator2 = QFrame();
        separator2.setFrameShape(QFrame.Shape.HLine);
        separator2.setFixedHeight(1)
        separator2.setStyleSheet("background-color: #34495e; margin: 8px 5px;")
        layout.addWidget(separator2)

        layout.addWidget(self.btn_audit_trail)
        layout.addWidget(self.btn_user_mgmt)

        layout.addStretch(1)
        layout.addWidget(self.btn_maximize)
        layout.addWidget(self.btn_logout)
        layout.addWidget(self.btn_exit)

        return menu

    def create_menu_button(self, text, icon, page_index, on_click_func=None):
        # (Your create_menu_button method code goes here, unchanged)
        btn = QPushButton(text, icon=fa.icon(icon, color='#ecf0f1'))
        btn.setProperty("fullText", text)
        btn.setIconSize(QSize(20, 20))
        if page_index != -1:
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.clicked.connect(lambda: self.show_page(page_index))
        else:
            if on_click_func:
                btn.clicked.connect(on_click_func)
        self.menu_buttons.append(btn)
        return btn

    def toggle_side_menu(self):
        # (Your toggle_side_menu method code goes here, unchanged)
        start_width = self.side_menu.width()
        end_width = self.COLLAPSED_MENU_WIDTH if self.is_menu_expanded else self.EXPANDED_MENU_WIDTH

        if self.is_menu_expanded:
            self.profile_name_label.setVisible(False)
            self.profile_role_label.setVisible(False)
            for button in self.menu_buttons:
                button.setText("")

        self.animation = QPropertyAnimation(self.side_menu, b"minimumWidth")
        self.animation.setDuration(300)
        self.animation.setStartValue(start_width)
        self.animation.setEndValue(end_width)
        self.animation.finished.connect(self.on_menu_animation_finished)
        self.animation.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def restore_menu_texts(self):
        # (Your restore_menu_texts method code goes here, unchanged)
        if self.is_menu_expanded:
            self.profile_name_label.setVisible(True)
            self.profile_role_label.setVisible(True)
            for button in self.menu_buttons:
                button.setText(button.property("fullText"))

    def create_status_widget(self, icon_name, initial_text, icon_color='#6c757d'):
        # (Your create_status_widget method code goes here, unchanged)
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(5, 0, 5, 0)
        layout.setSpacing(5)
        icon_label = QLabel()
        icon_label.setPixmap(fa.icon(icon_name, color=icon_color).pixmap(QSize(12, 12)))
        text_label = QLabel(initial_text)
        layout.addWidget(icon_label)
        layout.addWidget(text_label)
        widget.icon_label = icon_label
        widget.text_label = text_label
        return widget

    def setup_status_bar(self):
        # (Your setup_status_bar method code goes here, unchanged)
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage(f"Ready | Logged in as: {self.username}")

        if PSUTIL_AVAILABLE:
            self.network_widget = NetworkGraphWidget()
            self.status_bar.addPermanentWidget(self.network_widget)
            separator_net = QFrame();
            separator_net.setFrameShape(QFrame.Shape.VLine);
            separator_net.setFrameShadow(QFrame.Shadow.Sunken)
            self.status_bar.addPermanentWidget(separator_net)

        self.db_status_widget = self.create_status_widget('fa5s.database', "Connecting...")
        self.status_bar.addPermanentWidget(self.db_status_widget)

        separator1 = QFrame();
        separator1.setFrameShape(QFrame.Shape.VLine);
        separator1.setFrameShadow(QFrame.Shadow.Sunken)
        self.status_bar.addPermanentWidget(separator1)

        workstation_widget = self.create_status_widget('fa5s.desktop', self.workstation_info['h'])
        workstation_widget.setToolTip(
            f"IP Address: {self.workstation_info['i']}\nMAC Address: {self.workstation_info['m']}")
        self.status_bar.addPermanentWidget(workstation_widget)

        separator2 = QFrame();
        separator2.setFrameShape(QFrame.Shape.VLine);
        separator2.setFrameShadow(QFrame.Shadow.Sunken)
        self.status_bar.addPermanentWidget(separator2)

        self.time_widget = self.create_status_widget('fa5s.clock', "")
        self.status_bar.addPermanentWidget(self.time_widget)

        self.time_timer = QTimer(self, timeout=self.update_time);
        self.time_timer.start(1000)
        self.update_time()

        self.db_check_timer = QTimer(self, timeout=self.check_db_status);
        self.db_check_timer.start(5000)
        self.check_db_status()

    def _create_loading_dialog(self):
        dialog = QDialog(self);
        dialog.setModal(True);
        dialog.setWindowFlag(Qt.WindowType.FramelessWindowHint);
        dialog.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout = QVBoxLayout(dialog);
        frame = QFrame();
        frame.setStyleSheet("background-color: white; border-radius: 15px; padding: 20px;");
        frame_layout = QVBoxLayout(frame)
        loading_label = QLabel("Loading...");
        loading_label.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        message_label = QLabel("Syncing... Please wait.");
        message_label.setStyleSheet("font-size: 11pt;")
        frame_layout.addWidget(loading_label, alignment=Qt.AlignmentFlag.AlignCenter);
        frame_layout.addWidget(message_label, alignment=Qt.AlignmentFlag.AlignCenter);
        layout.addWidget(frame);
        return dialog

    def start_sync_process(self):
        if QMessageBox.question(self, "Confirm Sync",
                                "This will sync with the legacy production database. This may take some time. Are you sure you want to proceed?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.No: return
        self.btn_sync_prod.setEnabled(False);
        self.loading_dialog = self._create_loading_dialog()
        self.sync_thread = QThread();
        self.sync_worker = SyncWorker();
        self.sync_worker.moveToThread(self.sync_thread)
        self.sync_thread.started.connect(self.sync_worker.run);
        self.sync_worker.finished.connect(self.on_sync_finished);
        self.sync_worker.finished.connect(self.sync_thread.quit);
        self.sync_worker.finished.connect(self.sync_worker.deleteLater);
        self.sync_thread.finished.connect(self.sync_thread.deleteLater);
        self.sync_thread.start();
        self.loading_dialog.exec()

    def start_customer_sync_process(self):
        if QMessageBox.question(self, "Confirm Sync",
                                "This will sync customer data from the legacy database. Are you sure?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.No: return
        self.btn_sync_customers.setEnabled(False);
        self.loading_dialog = self._create_loading_dialog()
        self.customer_sync_thread = QThread();
        self.customer_sync_worker = SyncCustomerWorker();
        self.customer_sync_worker.moveToThread(self.customer_sync_thread)
        self.customer_sync_thread.started.connect(self.customer_sync_worker.run);
        self.customer_sync_worker.finished.connect(self.on_customer_sync_finished);
        self.customer_sync_worker.finished.connect(self.customer_sync_thread.quit);
        self.customer_sync_worker.finished.connect(self.customer_sync_worker.deleteLater);
        self.customer_sync_thread.finished.connect(self.customer_sync_thread.deleteLater);
        self.customer_sync_thread.start();
        self.loading_dialog.exec()

    def start_delivery_sync_process(self):
        if QMessageBox.question(self, "Confirm Sync",
                                "This will sync delivery records from the legacy database. This may take a moment. Are you sure?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.No: return
        self.btn_sync_deliveries.setEnabled(False);
        self.loading_dialog = self._create_loading_dialog()
        self.delivery_sync_thread = QThread();
        self.delivery_sync_worker = SyncDeliveryWorker();
        self.delivery_sync_worker.moveToThread(self.delivery_sync_thread)
        self.delivery_sync_thread.started.connect(self.delivery_sync_worker.run);
        self.delivery_sync_worker.finished.connect(self.on_delivery_sync_finished);
        self.delivery_sync_worker.finished.connect(self.delivery_sync_thread.quit);
        self.delivery_sync_worker.finished.connect(self.delivery_sync_worker.deleteLater);
        self.delivery_sync_thread.finished.connect(self.delivery_sync_thread.deleteLater);
        self.delivery_sync_thread.start();
        self.loading_dialog.exec()

    def start_rrf_sync_process(self):
        if QMessageBox.question(self, "Confirm Sync",
                                "This will sync RRF records from the legacy database. This process will map data based on predefined rules. Are you sure?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.No: return
        self.btn_sync_rrf.setEnabled(False);
        self.loading_dialog = self._create_loading_dialog()
        self.rrf_sync_thread = QThread();
        self.rrf_sync_worker = SyncRRFWorker();
        self.rrf_sync_worker.moveToThread(self.rrf_sync_thread)
        self.rrf_sync_thread.started.connect(self.rrf_sync_worker.run);
        self.rrf_sync_worker.finished.connect(self.on_rrf_sync_finished);
        self.rrf_sync_worker.finished.connect(self.rrf_sync_thread.quit);
        self.rrf_sync_worker.finished.connect(self.rrf_sync_worker.deleteLater);
        self.rrf_sync_thread.finished.connect(self.rrf_sync_thread.deleteLater);
        self.rrf_sync_thread.start();
        self.loading_dialog.exec()

    def on_menu_animation_finished(self):
        # (Your on_menu_animation_finished method code goes here, unchanged)
        self.is_menu_expanded = not self.is_menu_expanded
        if self.is_menu_expanded:
            self.profile_name_label.setVisible(True)
            self.profile_role_label.setVisible(True)
            for button in self.menu_buttons:
                button.setText(button.property("fullText"))

    def on_sync_finished(self, success, message):
        self.loading_dialog.close();
        self.btn_sync_prod.setEnabled(True)
        if success:
            QMessageBox.information(self, "Sync Result", message); self.status_bar.showMessage(
                "Production DB synchronized.", 5000)
        else:
            QMessageBox.critical(self, "Sync Result", message); self.status_bar.showMessage("Sync failed.", 5000)

    def on_customer_sync_finished(self, success, message):
        self.loading_dialog.close();
        self.btn_sync_customers.setEnabled(True)
        if success:
            QMessageBox.information(self, "Sync Result", message);
            self.status_bar.showMessage("Customer DB synchronized.", 5000)
            if hasattr(self.product_delivery_page,
                       '_load_combobox_data'): self.product_delivery_page._load_combobox_data()
            if hasattr(self.rrf_page, '_load_combobox_data'): self.rrf_page._load_combobox_data()
        else:
            QMessageBox.critical(self, "Sync Result", message); self.status_bar.showMessage("Customer sync failed.",
                                                                                            5000)

    def on_delivery_sync_finished(self, success, message):
        self.loading_dialog.close();
        self.btn_sync_deliveries.setEnabled(True)
        if success:
            QMessageBox.information(self, "Sync Result", message);
            self.status_bar.showMessage("Delivery records synchronized.", 5000)
            if self.stacked_widget.currentWidget() == self.product_delivery_page: self.product_delivery_page._load_all_records()
        else:
            QMessageBox.critical(self, "Sync Result", message); self.status_bar.showMessage("Delivery sync failed.",
                                                                                            5000)

    def on_rrf_sync_finished(self, success, message):
        self.loading_dialog.close();
        self.btn_sync_rrf.setEnabled(True)
        if success:
            QMessageBox.information(self, "Sync Result", message);
            self.status_bar.showMessage("RRF records synchronized.", 5000)
            if self.stacked_widget.currentWidget() == self.rrf_page: self.rrf_page._load_all_records()
        else:
            QMessageBox.critical(self, "Sync Result", message); self.status_bar.showMessage("RRF sync failed.", 5000)

    def update_time(self):
        self.time_widget.text_label.setText(datetime.now().strftime('%b %d, %Y  %I:%M:%S %p'))

    def check_db_status(self):
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            self.db_status_widget.icon_label.setPixmap(
                fa.icon('fa5s.check-circle', color='#28a745').pixmap(QSize(12, 12)));
            self.db_status_widget.text_label.setText("DB Connected");
            self.db_status_widget.setToolTip("Database connection is stable.")
        except Exception as e:
            self.db_status_widget.icon_label.setPixmap(
                fa.icon('fa5s.times-circle', color='#dc3545').pixmap(QSize(12, 12)));
            self.db_status_widget.text_label.setText("DB Disconnected");
            self.db_status_widget.setToolTip(f"Database connection failed.\nError: {e}")

    def apply_styles(self):
        self.setStyleSheet(AppStyles.MAIN_WINDOW_STYLESHEET)

    def show_page(self, index):
        if self.stacked_widget.currentIndex() == index: return
        self.stacked_widget.setCurrentIndex(index)
        current_widget = self.stacked_widget.widget(index)
        if hasattr(current_widget, 'refresh_page'): current_widget.refresh_page()
        if hasattr(current_widget, '_load_all_records'): current_widget._load_all_records()
        if hasattr(current_widget, '_load_all_endorsements'): current_widget._load_all_endorsements()
        if hasattr(current_widget, '_update_dashboard_data'): current_widget._update_dashboard_data()

    def toggle_maximize(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def update_maximize_button(self):
        if self.isMaximized():
            self.btn_maximize.setText("  Restore"); self.btn_maximize.setIcon(self.icon_restore)
        else:
            self.btn_maximize.setText("  Maximize"); self.btn_maximize.setIcon(self.icon_maximize)

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange: self.update_maximize_button()
        super().changeEvent(event)

    def logout(self):
        self.close(); self.login_window.show()

    def exit_application(self):
        reply = QMessageBox.question(self, 'Confirm Exit', 'Are you sure you want to exit the application?',
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes: self.log_audit_trail("LOGOUT",
                                                                         "User exited application."); QApplication.instance().quit()

    def closeEvent(self, event):
        for thread in [self.sync_thread, self.customer_sync_thread, self.delivery_sync_thread, self.rrf_sync_thread]:
            if thread and thread.isRunning(): thread.quit(); thread.wait()
        event.accept()