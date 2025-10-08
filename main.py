import sys
import os
import re
from datetime import datetime, date
from decimal import Decimal
import socket
import uuid
import dbfread
import traceback
import collections

# --- New Imports ---
try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    print("WARNING: 'psutil' library not found. Network graph will be disabled. Install with: pip install psutil")
    PSUTIL_AVAILABLE = False

from sqlalchemy import text, create_engine

try:
    import qtawesome as fa
except ImportError:
    print("FATAL ERROR: The 'qtawesome' library is required. Please install it using: pip install qtawesome")
    sys.exit(1)

from PyQt6.QtCore import (Qt, pyqtSignal, QSize, QEvent, QTimer, QThread, QObject, QPropertyAnimation, QRect, QPointF)
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, QLineEdit, QPushButton,
                             QMessageBox, QVBoxLayout, QHBoxLayout, QStackedWidget,
                             QFrame, QStatusBar, QDialog, QGridLayout, QGroupBox,
                             QTableWidget, QHeaderView, QAbstractItemView, QTableWidgetItem)
from PyQt6.QtGui import QFont, QIcon, QPainter, QPen, QColor, QPainterPath

# --- NEW: Charting Library Import ---
try:
    from PyQt6.QtCharts import (
        QChart, QChartView, QLineSeries,
        QValueAxis, QBarCategoryAxis, QHorizontalBarSeries, QBarSeries, QBarSet
    )

    CHARTS_AVAILABLE = True
except ImportError:
    print("WARNING: 'PyQt6-Charts' is not installed. Dashboard charts will be disabled.")
    print("Install it with: pip install PyQt6-Charts")
    CHARTS_AVAILABLE = False

# --- All page imports (assuming these files exist) ---
try:
    # --- DASHBOARD MODIFICATION: The dashboard is now part of this file, so no import needed. ---
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
    from good_inventory_page import GoodInventoryPage
    from failed_inventory_report import FailedInventoryReportPage
except ImportError as e:
    # print(f"Warning: Page import failed: {e}. If the application runs without issues, ignore this.")
    pass  # Suppressing verbose import warning if the structure assumes external files


    # Define placeholder classes if needed to prevent crash
    class PlaceholderPage(QWidget):
        def __init__(self, *args, **kwargs):
            super().__init__()
            self.setLayout(QVBoxLayout())
            self.layout().addWidget(QLabel(f"Placeholder for Missing Page: {e}"))

        def refresh_page(self): pass

        def _load_all_records(self): pass


    # --- DASHBOARD MODIFICATION: No need for a Dashboard placeholder anymore. ---
    if 'FGEndorsementPage' not in locals(): FGEndorsementPage = PlaceholderPage
    if 'OutgoingFormPage' not in locals(): OutgoingFormPage = PlaceholderPage
    if 'RRFPage' not in locals(): RRFPage = PlaceholderPage
    if 'ReceivingReportPage' not in locals(): ReceivingReportPage = PlaceholderPage
    if 'QCFailedPassedPage' not in locals(): QCFailedPassedPage = PlaceholderPage
    if 'QCExcessEndorsementPage' not in locals(): QCExcessEndorsementPage = PlaceholderPage
    if 'QCFailedEndorsementPage' not in locals(): QCFailedEndorsementPage = PlaceholderPage
    if 'ProductDeliveryPage' not in locals(): ProductDeliveryPage = PlaceholderPage
    if 'RequisitionLogbookPage' not in locals(): RequisitionLogbookPage = PlaceholderPage
    if 'AuditTrailPage' not in locals(): AuditTrailPage = PlaceholderPage
    if 'UserManagementPage' not in locals(): UserManagementPage = PlaceholderPage
    if 'TransactionsFormPage' not in locals(): TransactionsFormPage = PlaceholderPage
    if 'FailedTransactionsFormPage' not in locals(): FailedTransactionsFormPage = PlaceholderPage
    if 'GoodInventoryPage' not in locals(): GoodInventoryPage = PlaceholderPage
    if 'FailedInventoryReportPage' not in locals(): FailedInventoryReportPage = PlaceholderPage
# ---------------------------------------


# --- CONFIGURATION ---
DB_CONFIG = {"host": "192.168.1.13", "port": 5432, "dbname":
    "dbfg", "user": "postgres", "password": "mbpi"}
DBF_BASE_PATH = r'\\system-server\SYSTEM-NEW-OLD'
PRODUCTION_DBF_PATH = os.path.join(DBF_BASE_PATH, 'tbl_prod01.dbf')
CUSTOMER_DBF_PATH = os.path.join(DBF_BASE_PATH, 'tbl_customer01.dbf')
DELIVERY_DBF_PATH = os.path.join(DBF_BASE_PATH, 'tbl_del01.dbf')
DELIVERY_ITEMS_DBF_PATH = os.path.join(DBF_BASE_PATH, 'tbl_del02.dbf')

# --- RRF PATHS ---
RRF_DBF_PATH = os.path.join(DBF_BASE_PATH, 'RRF')
RRF_PRIMARY_DBF_PATH = os.path.join(RRF_DBF_PATH, 'tbl_del01.dbf')
RRF_ITEMS_DBF_PATH = os.path.join(RRF_DBF_PATH, 'tbl_del02.dbf')

db_url = f"postgresql+psycopg2://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}"
engine = create_engine(db_url, pool_pre_ping=True, pool_recycle=3600)


class AppStyles:
    """A class to hold all the stylesheet strings for the application."""

    # --- Refined Dark Theme Palette ---
    PRIMARY_ACCENT_COLOR = "#007bff"  # Clear Blue for primary highlights
    PRIMARY_ACCENT_HOVER = "#0056b3"
    SUCCESS_COLOR = '#28a745'  # Green for success indicators

    # --- MODIFIED: Dark Mode Base Colors for Menu and Status Bar ---
    DARK_MENU_BASE = "#212529"  # Very dark gray/near black
    DARK_MENU_SECONDARY = "#343a40"  # Slightly lighter dark gray

    # MODIFIED: Selected Row Color (Darker blue/gray, suitable for white text)
    TABLE_SELECTION_COLOR = "#3a506b"

    # Secondary and destructive colors
    SECONDARY_ACCENT_COLOR = "#ffc107"  # Yellow/Gold
    SECONDARY_ACCENT_HOVER = "#e0a800"
    DESTRUCTIVE_COLOR = "#dc3545"  # Red
    DESTRUCTIVE_COLOR_HOVER = "#c82333"
    NEUTRAL_COLOR = "#6c757d"
    NEUTRAL_COLOR_HOVER = "#5a6268"

    # Text color for dark elements
    DARK_TEXT_COLOR = "#f8f9fa"
    LIGHT_TEXT_COLOR = "#333333"

    # --- Side Menu/Login Background Gradient (Retained for menu, but not for Login) ---
    SIDE_MENU_GRADIENT = f"qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {DARK_MENU_BASE}, stop:1 {DARK_MENU_SECONDARY});"
    SIDE_MENU_ACTIVE_COLOR = PRIMARY_ACCENT_COLOR  # Using the clear blue for the checked button background

    # --- NEW: Light Login Variables ---
    LIGHT_LOGIN_BG = "#ffffff"
    LIGHT_INPUT_BG = "#f8f8f8"

    # --- FIX: New Icon Color ---
    LOGIN_ICON_COLOR = "#3a506b"  # Specified dark gray-blue color

    LOGIN_STYLESHEET = f"""
        #LoginWindow, #FormFrame {{ 
            background-color: {LIGHT_LOGIN_BG};
        }}
        QWidget {{ 
            font-family: "Segoe UI"; 
            font-size: 11pt; 
            color: {LIGHT_TEXT_COLOR}; 
        }}

        #LoginTitle {{ 
            font-size: 20pt; 
            font-weight: bold; 
            color: {"#3a506b"}; 
        }}

        /* Input Frame now uses a very light background */
        #InputFrame {{ 
            background-color: {LIGHT_INPUT_BG}; 
            border: 1px solid #d1d9e6; 
            border-radius: 8px; 
            padding: 5px; 
        }}
        #InputFrame:focus-within {{ border: 2px solid {PRIMARY_ACCENT_COLOR}; }}

        /* Input line edit text needs to be dark gray on the light input background */
        QLineEdit {{ 
            border: none; 
            background-color: transparent; 
            padding: 8px; 
            font-size: 11pt;
            color: {LIGHT_TEXT_COLOR}; 
        }}

        /* FIX: Login icon color set to the new specified color */
        #InputFrame QLabel {{ color: {LOGIN_ICON_COLOR}; }}

        QPushButton#PrimaryButton {{
            background-color: {"#3a506b"};
            color: #fff;
            border-radius: 8px;
            padding: 12px;
            font-weight: bold;
            font-size: 12pt;
            border: none;
        }}
        QPushButton#PrimaryButton:hover {{ background-color: {PRIMARY_ACCENT_HOVER}; }}
        QPushButton#PrimaryButton:pressed {{ transform: scale(0.98); }}

        /* Status label remains visible red/destructive color */
        #StatusLabel {{ color: {DESTRUCTIVE_COLOR}; font-size: 9pt; font-weight: bold; }}
    """

    @staticmethod
    def get_main_stylesheet(font_size_pt: int = 9):
        """
        Generates the main window stylesheet, applying light content area styles
        and dark side menu/status bar styles.
        """
        profile_name_size = font_size_pt
        profile_role_size = font_size_pt - 1

        return f"""
        QMainWindow, QStackedWidget > QWidget {{
            background-color: #f4f7fc; /* Light Content Area */
        }}
        QWidget {{
            font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
            font-size: 10pt;
            color: {AppStyles.LIGHT_TEXT_COLOR}; /* Dark text for light areas */
        }}
        /* === Side Menu Styling (Matching Login Theme - Dark Gradient, White Icons) === */
        QWidget#SideMenu {{
            background-color: {AppStyles.SIDE_MENU_GRADIENT};
            color: #ecf0f1; /* Light text for dark areas */
        }}
        #SideMenu QLabel {{ color: #ecf0f1; font-family: "Segoe UI"; background: transparent; }}

        /* Side menu buttons (White icons and text) */
        #SideMenu QPushButton {{
            background-color: transparent;
            color: #ecf0f1; /* White icon/text color */
            border: none;
            padding: 10px 10px 10px 20px;
            text-align: left;
            font-size: {font_size_pt}pt;
            font-weight: normal;
            border-radius: 6px;
            qproperty-iconSize: 16px;
        }}
        #SideMenu QPushButton:hover {{ background-color: rgba(255, 255, 255, 0.1); }}
        #SideMenu QPushButton:checked {{
            background-color: {AppStyles.SIDE_MENU_ACTIVE_COLOR}; /* Blue Active State */
            font-weight: bold;
            color: white;
        }}

        #SideMenu #ProfileName {{ font-weight: bold; font-size: {profile_name_size}pt; }}
        #SideMenu #ProfileRole {{ color: #bdc3c7; font-size: {profile_role_size}pt; }}

        /* === Header Bar Styling (MODIFIED TO WHITE & SMALL) === */
        #HeaderBar {{ 
            background-color: #ffffff; /* White background */
            border-bottom: 1px solid #e0e5eb; /* Light border */
        }}
        #HeaderBar QLabel {{
            color: {AppStyles.LIGHT_TEXT_COLOR}; /* Dark text */
            font-size: 9pt; /* Slightly smaller title */

        }}
        #HeaderBar QPushButton {{
            background-color: transparent;
            color: {AppStyles.LIGHT_TEXT_COLOR}; /* Dark icon/text color defined here, overriding default QWidget dark text */
            border: none;
            padding: 4px 10px; /* Reduced vertical padding for smaller height */
            text-align: center;
            font-size: 9pt;
            font-weight: normal;
            border-radius: 4px;
            qproperty-iconSize: 16px; 
        }}
        #HeaderBar QPushButton:hover {{ 
            background-color: #f0f0f0; /* Light gray hover effect */
        }}
        #HeaderBar QPushButton:pressed {{ transform: scale(0.98); }}


        /* === Main Content Area Widgets (FORM STYLING) === */
        QGroupBox {{
            border: 1px solid #e0e5eb; border-radius: 8px;
            margin-top: 12px; background-color: #ffffff;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin; subcontrol-position: top left;
            padding: 2px 10px; background-color: #f4f7fc;
            border: 1px solid #e0e5eb; border-bottom: 1px solid #ffffff;
            border-top-left-radius: 8px; border-top-right-radius: 8px;
            font-weight: bold; color: #4f4f4f;
        }}
        QLineEdit, QComboBox, QDateEdit, QDateTimeEdit, QPlainTextEdit, QDoubleSpinBox, QTextEdit {{
            border: 1px solid #d1d9e6; padding: 8px; border-radius: 5px;
            background-color: #ffffff;
            selection-background-color: #aed6f1;
        }}
        QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QPlainTextEdit:focus, QDoubleSpinBox:focus, QTextEdit:focus {{
            border: 1px solid {AppStyles.PRIMARY_ACCENT_COLOR};
        }}
        QLineEdit[readOnly="true"] {{ background-color: #eff2f7; color: #6c757d; }}

        /* === Button Styling: Light Color Scheme (FOR ALL FORM BUTTONS) === */
        QPushButton {{
            border: 1px solid #d1d9e6; 
            padding: 8px 15px;
            border-radius: 6px;
            font-weight: bold;
            color: #333; 
            background-color: #ffffff; 
            qproperty-iconSize: 16px;
        }}
        QPushButton:hover {{ 
            background-color: #f0f3f8; 
            border: 1px solid #c0c0c0;
        }}
        QPushButton:pressed {{ transform: scale(0.98); }}

        /* Primary Action Buttons (Blue Accent) */
        QPushButton#PrimaryButton, #save_btn, #update_btn, #save_breakdown_btn, #scan_btn {{
            color: {AppStyles.PRIMARY_ACCENT_COLOR};
            border: 1px solid {AppStyles.PRIMARY_ACCENT_COLOR};
        }}
        QPushButton#PrimaryButton:hover, #save_btn:hover, #update_btn:hover, #save_breakdown_btn:hover, #scan_btn:hover {{
            background-color: #e9f0ff; 
            border: 1px solid {AppStyles.PRIMARY_ACCENT_HOVER};
        }}

        /* Destructive Action Buttons (Red Accent) */
        #delete_btn, #remove_item_btn {{ 
            color: {AppStyles.DESTRUCTIVE_COLOR}; 
            border: 1px solid {AppStyles.DESTRUCTIVE_COLOR};
        }}
        #delete_btn:hover, #remove_item_btn:hover {{ 
            background-color: #fbe6e8; 
            border: 1px solid {AppStyles.DESTRUCTIVE_COLOR_HOVER};
        }}

        /* Secondary/Positive Action Buttons (Yellow/Gold Accent) */
        QPushButton#SecondaryButton, #print_btn, #preview_btn {{
            color: {AppStyles.SECONDARY_ACCENT_COLOR};
            border: 1px solid {AppStyles.SECONDARY_ACCENT_COLOR};
        }}
        QPushButton#SecondaryButton:hover, #print_btn:hover, #preview_btn:hover {{
            background-color: #fff8e1;
            border: 1px solid {AppStyles.SECONDARY_ACCENT_HOVER};
        }}

        /* Neutral/Default Buttons (Gray Accent) */
        QPushButton:not([id^="PrimaryButton"]):not([id^="SecondaryButton"]):not(#save_btn):not(#update_btn):not(#save_breakdown_btn):not(#scan_btn):not(#delete_btn):not(#remove_item_btn):not(#print_btn):not(#preview_btn) {{
            color: {AppStyles.NEUTRAL_COLOR};
            border: 1px solid {AppStyles.NEUTRAL_COLOR};
        }}
        QPushButton:not([id^="PrimaryButton"]):not([id^="SecondaryButton"]):not(#save_btn):not(#update_btn):not(#save_breakdown_btn):not(#scan_btn):not(#delete_btn):not(#remove_item_btn):not(#print_btn):not(#preview_btn):hover {{
            background-color: #f0f3f8;
            border: 1px solid {AppStyles.NEUTRAL_COLOR_HOVER};
        }}

        /* === Table Styling === */
        QTableWidget {{ border: none; background-color: #ffffff; selection-behavior: SelectRows; color: #212529; }}
        QTableWidget::item {{ border-bottom: 1px solid #f4f7fc; padding: 10px; }}
        QTableWidget::item:selected {{ 
            background-color: {AppStyles.TABLE_SELECTION_COLOR}; /* Darker Gray-Blue */
            color: white; 
        }}

        QHeaderView::section {{ background-color: #ffffff; color: {AppStyles.NEUTRAL_COLOR}; padding: 8px; border: none; border-bottom: 2px solid #e0e5eb; font-weight: bold; text-align: left; }}
        QTabWidget::pane {{ border: 1px solid #e0e5eb; border-radius: 8px; background-color: #ffffff; padding: 10px; margin-top: -1px; }}
        QTabBar {{ qproperty-drawBase: 0; background-color: transparent; margin-bottom: 0px; }}
        QTabBar::tab {{ background-color: #e9eff7; color: {AppStyles.NEUTRAL_COLOR}; padding: 10px 25px; border-top-left-radius: 8px; border-top-right-radius: 8px; border: 1px solid #e0e5eb; border-bottom: none; margin-right: 4px; font-weight: bold; }}
        QTabBar::tab:selected {{ color: {AppStyles.PRIMARY_ACCENT_COLOR}; background-color: #ffffff; border: 1px solid #e0e5eb; border-bottom-color: #ffffff; margin-bottom: -1px; }}
        QTabBar::tab:hover {{ color: {AppStyles.PRIMARY_ACCENT_COLOR}; background-color: #f0f3f8; }}
        QTabBar::tab:selected:hover {{ background-color: #ffffff; }}

        /* MODIFIED: Status Bar Styling (Matching Side Menu Theme - Dark Gradient) */
        QStatusBar {{ 
            background-color: {AppStyles.DARK_MENU_BASE}; 
            color: {AppStyles.DARK_TEXT_COLOR}; 
            font-size: 9pt; padding: 2px 0px; 
            background: {AppStyles.SIDE_MENU_GRADIENT};
        }}
        QStatusBar::item {{ border: none; }}
        QStatusBar QLabel {{ color: {AppStyles.DARK_TEXT_COLOR}; background: transparent; padding: 0 4px; }}

        /* Status Bar Separators */
        QStatusBar QFrame[frameShape="VLine"] {{ background-color: rgba(255, 255, 255, 0.2); }}
    """


class IconProvider:
    """
    A central provider for application icons, using the qtawesome library.
    This ensures all icons are consistent, scalable, and can be dynamically colored.
    """
    # Application & Window Icons
    APP_ICON = 'fa5s.box-open'
    WINDOW_ICON = 'fa5s.check-double'
    LOGIN_FORM_ICON = 'fa5s.boxes'  # Warehouse icon for login

    # Common UI Icons
    MENU_TOGGLE = 'fa5s.bars'
    MAXIMIZE = 'fa5s.expand-arrows-alt'
    RESTORE = 'fa5s.compress-arrows-alt'
    DATABASE = 'fa5s.database'
    DESKTOP = 'fa5s.desktop'  # Used for Dashboard
    CLOCK = 'fa5s.clock'

    # User & Auth Icons
    USERNAME = 'fa5s.user'
    PASSWORD = 'fa5s.lock'
    USER_PROFILE = 'fa5s.user-circle'
    USER_MANAGEMENT = 'fa5s.users-cog'
    LOGOUT = 'fa5s.sign-out-alt'
    EXIT = 'fa5s.power-off'

    # Module / Page Icons
    FG_ENDORSEMENT = 'fa5s.file-signature'
    TRANSACTIONS = 'fa5s.exchange-alt'
    FAILED_TRANSACTIONS = 'fa5s.exclamation-triangle'

    # --- INVENTORY ICONS ---
    GOOD_INVENTORY = 'fa5s.warehouse'
    FAILED_INVENTORY_REPORT = 'fa5s.balance-scale-right'
    # -----------------------

    OUTGOING_FORM = 'fa5s.sign-out-alt'
    RRF_FORM = 'fa5s.undo-alt'
    RECEIVING_REPORT = 'fa5s.truck-loading'
    QC_PASSED = 'fa5s.flask'
    QC_EXCESS = 'fa5s.box'
    QC_FAILED = 'fa5s.times-circle'
    PRODUCT_DELIVERY = 'fa5s.truck'
    REQUISITION = 'fa5s.book'
    AUDIT_TRAIL = 'fa5s.clipboard-list'

    # Sync Icons
    SYNC = 'fa5s.sync-alt'
    CUSTOMERS = 'fa5s.address-book'
    DELIVERIES = 'fa5s.history'
    RRF_SYNC = 'fa5s.retweet'

    # Status & Action Icons
    SUCCESS = 'fa5s.check-circle'
    ERROR = 'fa5s.times-circle'
    WARNING = 'fa5s.exclamation-triangle'

    @staticmethod
    def get_icon(icon_name: str, color: str = "#333333") -> QIcon:
        """
        Gets a specific icon by name with a specified color.
        """
        return fa.icon(icon_name, color=color)

    @staticmethod
    def get_pixmap(icon_name: str, color: str, size: QSize) -> QIcon:
        """
        Gets a specific icon as a pixmap with a specified color and size.
        """
        return fa.icon(icon_name, color=color).pixmap(size)


class NetworkGraphWidget(QWidget):
    """A widget to display real-time network activity."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.history_size = 60  # seconds of history
        self.upload_history = collections.deque([0.0] * self.history_size, maxlen=self.history_size)
        self.download_history = collections.deque([0.0] * self.history_size, maxlen=self.history_size)
        self.last_stats = psutil.net_io_counters() if PSUTIL_AVAILABLE else None
        self.current_upload_speed = 0
        self.current_download_speed = 0

        self.setMinimumSize(200, 25)
        self.setToolTip("Network Activity (Upload/Download)")

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_stats)
        self.timer.start(1000)  # Update every second

    def _format_speed(self, speed_bps):
        """Formats speed in bytes per second to a human-readable string."""
        if speed_bps < 1024:
            return f"{speed_bps:.1f} B/s"
        elif speed_bps < 1024 ** 2:
            return f"{speed_bps / 1024:.1f} KB/s"
        elif speed_bps < 1024 ** 3:
            return f"{speed_bps / (1024 ** 2):.1f} MB/s"
        else:
            return f"{speed_bps / (1024 ** 3):.1f} GB/s"

    def update_stats(self):
        if not PSUTIL_AVAILABLE or self.last_stats is None:
            return

        current_stats = psutil.net_io_counters()
        self.current_upload_speed = current_stats.bytes_sent - self.last_stats.bytes_sent
        self.current_download_speed = current_stats.bytes_recv - self.last_stats.bytes_recv
        self.last_stats = current_stats

        self.upload_history.append(self.current_upload_speed)
        self.download_history.append(self.current_download_speed)

        self.update()  # Trigger a repaint

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(Qt.GlobalColor.transparent)

        # Draw text
        upload_text = f"↑ {self._format_speed(self.current_upload_speed)}"
        download_text = f"↓ {self._format_speed(self.current_download_speed)}"
        font = self.font()
        font.setPointSize(8)
        painter.setFont(font)

        # Using colors that contrast well on a dark status bar
        painter.setPen(QColor("#ffc107"))  # Yellow for upload
        painter.drawText(QRect(5, 0, self.width() // 2 - 5, self.height()),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, upload_text)

        painter.setPen(QColor(AppStyles.PRIMARY_ACCENT_COLOR))  # Blue for download
        painter.drawText(QRect(self.width() // 2, 0, self.width() // 2 - 5, self.height()),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, download_text)

        # Draw graph lines in the background
        max_speed = max(max(self.upload_history), max(self.download_history), 1)  # Avoid division by zero
        graph_area_width = self.width() - 10
        graph_area_height = self.height() - 4
        if self.history_size > 1:
            point_spacing = graph_area_width / (self.history_size - 1)
        else:
            point_spacing = 0

        # Draw upload graph
        upload_path = QPainterPath()
        upload_path.moveTo(5, self.height() - 2 - (self.upload_history[0] / max_speed * graph_area_height))
        for i, speed in enumerate(self.upload_history):
            x = 5 + i * point_spacing
            y = self.height() - 2 - (speed / max_speed * graph_area_height)
            upload_path.lineTo(x, y)
        painter.setPen(QPen(QColor(255, 193, 7, 100), 1.5))  # Semi-transparent yellow
        painter.drawPath(upload_path)

        # Draw download graph
        download_path = QPainterPath()
        download_path.moveTo(5, self.height() - 2 - (self.download_history[0] / max_speed * graph_area_height))
        for i, speed in enumerate(self.download_history):
            x = 5 + i * point_spacing
            y = self.height() - 2 - (speed / max_speed * graph_area_height)
            download_path.lineTo(x, y)
        painter.setPen(QPen(QColor(0, 123, 255, 100), 1.5))  # Semi-transparent blue
        painter.drawPath(download_path)


class SyncWorker(QObject):
    finished = pyqtSignal(bool, str)
    progress = pyqtSignal(int)

    def _to_float(self, value, default=None):
        """Safely converts a value to a float, returning a default on failure."""
        if value is None:
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            try:
                cleaned_value = str(value).strip()
                return float(cleaned_value) if cleaned_value else default
            except (ValueError, TypeError):
                return default

    def run(self):
        try:
            dbf = dbfread.DBF(PRODUCTION_DBF_PATH, load=True, encoding='latin1')
            total_records = len(dbf)
            if 'T_LOTNUM' not in dbf.field_names:
                self.finished.emit(False, "Sync Error: Required column 'T_LOTNUM' not found.")
                return

            if total_records == 0:
                self.finished.emit(True, "Sync Info: No new records found in DBF file to sync.")
                return

            recs = []
            last_percent = -1
            for i, r in enumerate(dbf.records):
                lot_num = str(r.get('T_LOTNUM', '')).strip().upper()
                if not lot_num:
                    continue
                recs.append({
                    "lot": lot_num,
                    "code": str(r.get('T_PRODCODE', '')).strip(),
                    "cust": str(r.get('T_CUSTOMER', '')).strip(),
                    "fid": str(int(r.get('T_FID'))) if r.get('T_FID') is not None else '',
                    "op": str(r.get('T_OPER', '')).strip(),
                    "sup": str(r.get('T_SUPER', '')).strip(),
                    "prod_id": str(r.get('T_PRODID', '')).strip(),
                    "machine": str(r.get('T_MACHINE', '')).strip(),
                    "qty_prod": self._to_float(r.get('T_QTYPROD')),
                    "prod_date": r.get('T_PRODDATE'),
                    "prod_color": str(r.get('T_PRODCOLO', '')).strip()
                })
                percent = int(((i + 1) / total_records) * 80)
                if percent > last_percent:
                    self.progress.emit(percent)
                    last_percent = percent
            self.progress.emit(80)

            self.progress.emit(90)
            with engine.connect() as conn:
                with conn.begin():
                    conn.execute(text("""
                        INSERT INTO legacy_production(
                            lot_number, prod_code, customer_name, formula_id, operator, supervisor,
                            prod_id, machine, qty_prod, prod_date, prod_color, last_synced_on
                        ) VALUES (
                            :lot, :code, :cust, :fid, :op, :sup,
                            :prod_id, :machine, :qty_prod, :prod_date, :prod_color, NOW()
                        )
                        ON CONFLICT(lot_number) DO UPDATE SET
                            prod_code=EXCLUDED.prod_code,
                            customer_name=EXCLUDED.customer_name,
                            formula_id=EXCLUDED.formula_id,
                            operator=EXCLUDED.operator,
                            supervisor=EXCLUDED.supervisor,
                            prod_id=EXCLUDED.prod_id,
                            machine=EXCLUDED.machine,
                            qty_prod=EXCLUDED.qty_prod,
                            prod_date=EXCLUDED.prod_date,
                            prod_color=EXCLUDED.prod_color,
                            last_synced_on=NOW()
                    """), recs)

            self.progress.emit(100)
            final_msg = f"Production sync complete.\n{len(recs)} records processed."
            self.finished.emit(True, final_msg)

        except dbfread.DBFNotFound:
            self.finished.emit(False, f"File Not Found: Production DBF not found at:\n{PRODUCTION_DBF_PATH}")
        except Exception as e:
            trace_info = traceback.format_exc()
            print(f"PRODUCTION SYNC CRITICAL ERROR: {e}\n{trace_info}")
            self.finished.emit(False, f"An unexpected error occurred during production sync:\n{e}")


class SyncCustomerWorker(QObject):
    finished = pyqtSignal(bool, str)
    progress = pyqtSignal(int)

    def run(self):
        try:
            dbf = dbfread.DBF(CUSTOMER_DBF_PATH, load=True, encoding='latin1')
            total_records = len(dbf)
            if 'T_CUSTOMER' not in dbf.field_names:
                self.finished.emit(False, "Sync Error: Required column 'T_CUSTOMER' not found in customer DBF.")
                return

            if total_records == 0:
                self.finished.emit(True, "Sync Info: No new customer records found to sync.")
                return

            recs = []
            last_percent = -1
            for i, r in enumerate(dbf.records):
                name = str(r.get('T_CUSTOMER', '')).strip()
                if name:
                    address = (str(r.get('T_ADD1', '')).strip() + ' ' + str(r.get('T_ADD2', '')).strip()).strip()
                    recs.append({
                        "name": name,
                        "address": address,
                        "deliver_to": name,
                        "tin": str(r.get('T_TIN', '')).strip(),
                        "terms": str(r.get('T_TERMS', '')).strip(),
                        "is_deleted": bool(r.get('T_DELETED', False))
                    })
                percent = int(((i + 1) / total_records) * 80)
                if percent > last_percent:
                    self.progress.emit(percent)
                    last_percent = percent
            self.progress.emit(80)

            self.progress.emit(90)
            with engine.connect() as conn:
                with conn.begin():
                    conn.execute(text("""
                        INSERT INTO customers (name, address, deliver_to, tin, terms, is_deleted)
                        VALUES (:name, :address, :deliver_to, :tin, :terms, :is_deleted)
                        ON CONFLICT (name) DO UPDATE SET
                            address = EXCLUDED.address,
                            deliver_to = EXCLUDED.deliver_to,
                            tin = EXCLUDED.tin,
                            terms = EXCLUDED.terms,
                            is_deleted = EXCLUDED.is_deleted
                    """), recs)
            self.progress.emit(100)
            self.finished.emit(True, f"Customer sync complete.\n{len(recs)} records processed.")
        except dbfread.DBFNotFound:
            self.finished.emit(False, f"File Not Found: Customer DBF not found at:\n{CUSTOMER_DBF_PATH}")
        except Exception as e:
            self.finished.emit(False, f"An unexpected error occurred during customer sync:\n{e}")


class SyncDeliveryWorker(QObject):
    finished = pyqtSignal(bool, str)
    progress = pyqtSignal(int)

    def _get_safe_dr_num(self, dr_num_raw):
        """Safely converts various DR number formats to a clean string."""
        if dr_num_raw is None:
            return None
        try:
            # Handle cases where it might be a float like 10001.0
            return str(int(float(dr_num_raw)))
        except (ValueError, TypeError):
            # Handle cases where it's already a string or something else
            return str(dr_num_raw).strip() if dr_num_raw else None

    def _to_float(self, value, default=0.0):
        """Safely converts a value to float, handling None, strings, and errors."""
        if value is None:
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            try:
                # Attempt to clean up and convert if it's a string
                cleaned_value = str(value).strip()
                return float(cleaned_value) if cleaned_value else default
            except (ValueError, TypeError):
                return default

    def run(self):
        try:
            # --- Phase 1: Read Items DBF (45% of work) ---
            items_by_dr = {}
            with dbfread.DBF(DELIVERY_ITEMS_DBF_PATH, load=True, encoding='latin1') as dbf_items:
                total_items = len(dbf_items)
                last_percent = -1
                for i, item_rec in enumerate(dbf_items.records):
                    dr_num = self._get_safe_dr_num(item_rec.get('T_DRNUM'))
                    if not dr_num:
                        continue

                    if dr_num not in items_by_dr:
                        items_by_dr[dr_num] = []

                    attachments = "\n".join(
                        filter(None, [str(item_rec.get(f'T_DESC{i}', '')).strip() for i in range(1, 5)]))

                    items_by_dr[dr_num].append({
                        "dr_no": dr_num,
                        "quantity": self._to_float(item_rec.get('T_TOTALWT')),
                        "unit": str(item_rec.get('T_TOTALWTU', '')).strip(),
                        "product_code": str(item_rec.get('T_PRODCODE', '')).strip(),
                        "product_color": str(item_rec.get('T_PRODCOLO', '')).strip(),
                        "no_of_packing": self._to_float(item_rec.get('T_NUMPACKI')),
                        "weight_per_pack": self._to_float(item_rec.get('T_WTPERPAC')),
                        "lot_numbers": "",
                        "attachments": attachments,
                        "unit_price": None,
                        "lot_no_1": None,
                        "lot_no_2": None,
                        "lot_no_3": None,
                        "mfg_date": None,
                        "alias_code": None,
                        "alias_desc": None
                    })

                    if total_items > 0:
                        percent = int(((i + 1) / total_items) * 45)
                        if percent > last_percent:
                            self.progress.emit(percent)
                            last_percent = percent
            self.progress.emit(45)

            # --- Phase 2: Read Primary DBF (45% of work) ---
            primary_recs = []
            with dbfread.DBF(DELIVERY_DBF_PATH, load=True, encoding='latin1') as dbf_primary:
                total_primary = len(dbf_primary)
                last_percent = -1
                for i, r in enumerate(dbf_primary.records):
                    dr_num = self._get_safe_dr_num(r.get('T_DRNUM'))
                    if not dr_num:
                        continue

                    address = (str(r.get('T_ADD1', '')).strip() + ' ' + str(r.get('T_ADD2', '')).strip()).strip()

                    primary_recs.append({
                        "dr_no": dr_num,
                        "delivery_date": r.get('T_DRDATE'),
                        "customer_name": str(r.get('T_CUSTOMER', '')).strip(),
                        "deliver_to": str(r.get('T_DELTO', '')).strip(),
                        "address": address,
                        "po_no": str(r.get('T_CPONUM', '')).strip(),
                        "order_form_no": str(r.get('T_ORDERNUM', '')).strip(),
                        "terms": str(r.get('T_REMARKS', '')).strip(),
                        "prepared_by": str(r.get('T_USERID', '')).strip(),
                        "encoded_on": r.get('T_DENCODED'),
                        "is_deleted": bool(r.get('T_DELETED', False))
                    })
                    if total_primary > 0:
                        percent = 45 + int(((i + 1) / total_primary) * 45)
                        if percent > last_percent:
                            self.progress.emit(percent)
                            last_percent = percent
            self.progress.emit(90)

            if not primary_recs:
                self.finished.emit(True, "Sync Info: No new delivery records found to sync.")
                return

            # --- NEW SAFEGUARD ---
            all_items_to_insert = [item for dr_num in [rec['dr_no'] for rec in primary_recs] if dr_num in items_by_dr
                                   for item in items_by_dr[dr_num]]

            if not all_items_to_insert and primary_recs:
                self.finished.emit(False,
                                   "Sync Warning: Found delivery headers but no matching items in the DBF file.\n\nSync aborted to prevent data loss. Please check the `tbl_del02.dbf` file.")
                return
            # --- END SAFEGUARD ---

            # --- Phase 3: DB Operations (10% of work) ---
            with engine.connect() as conn:
                with conn.begin():
                    dr_numbers_to_sync = [rec['dr_no'] for rec in primary_recs]
                    self.progress.emit(92)

                    conn.execute(text("DELETE FROM product_delivery_items WHERE dr_no = ANY(:dr_nos)"),
                                 {"dr_nos": dr_numbers_to_sync})

                    self.progress.emit(95)

                    conn.execute(text("""
                        INSERT INTO product_delivery_primary (
                            dr_no, delivery_date, customer_name, deliver_to, address, po_no, 
                            order_form_no, terms, prepared_by, encoded_on, is_deleted, 
                            edited_by, edited_on, encoded_by
                        )
                        VALUES (
                            :dr_no, :delivery_date, :customer_name, :deliver_to, :address, :po_no, 
                            :order_form_no, :terms, :prepared_by, :encoded_on, :is_deleted, 
                            'DBF_SYNC', NOW(), :prepared_by
                        )
                        ON CONFLICT (dr_no) DO UPDATE SET
                            delivery_date = EXCLUDED.delivery_date,
                            customer_name = EXCLUDED.customer_name,
                            deliver_to = EXCLUDED.deliver_to,
                            address = EXCLUDED.address,
                            po_no = EXCLUDED.po_no,
                            order_form_no = EXCLUDED.order_form_no,
                            terms = EXCLUDED.terms,
                            prepared_by = EXCLUDED.prepared_by,
                            encoded_on = EXCLUDED.encoded_on,
                            is_deleted = EXCLUDED.is_deleted,
                            edited_by = 'DBF_SYNC',
                            edited_on = NOW()
                    """), primary_recs)

                    self.progress.emit(98)

                    if all_items_to_insert:
                        conn.execute(text("""
                            INSERT INTO product_delivery_items (
                                dr_no, quantity, unit, product_code, product_color, 
                                no_of_packing, weight_per_pack, lot_numbers, attachments,
                                unit_price, lot_no_1, lot_no_2, lot_no_3, mfg_date, 
                                alias_code, alias_desc
                            )
                            VALUES (
                                :dr_no, :quantity, :unit, :product_code, :product_color, 
                                :no_of_packing, :weight_per_pack, :lot_numbers, :attachments,
                                :unit_price, :lot_no_1, :lot_no_2, :lot_no_3, :mfg_date, 
                                :alias_code, :alias_desc
                            )
                        """), all_items_to_insert)

            self.progress.emit(100)
            self.finished.emit(True,
                               f"Delivery sync complete.\n{len(primary_recs)} primary records and {len(all_items_to_insert)} items processed.")

        except dbfread.DBFNotFound as e:
            self.finished.emit(False, f"File Not Found: A required delivery DBF file is missing.\nDetails: {e}")
        except Exception as e:
            trace_info = traceback.format_exc()
            print(f"DELIVERY SYNC CRITICAL ERROR: {e}\n{trace_info}")
            self.finished.emit(False,
                               f"An unexpected error occurred during delivery sync:\n{e}\n\nCheck console/logs for technical details.")


class SyncRRFWorker(QObject):
    finished = pyqtSignal(bool, str)
    progress = pyqtSignal(int)

    def _get_safe_rrf_num(self, rrf_num_raw):
        if rrf_num_raw is None:
            return None
        try:
            return str(int(float(rrf_num_raw)))
        except (ValueError, TypeError):
            return str(rrf_num_raw).strip() if rrf_num_raw else None

    def _to_float(self, value, default=0.0):
        if value is None: return default
        try:
            return float(value)
        except (ValueError, TypeError):
            try:
                cleaned_value = str(value).strip()
                return float(cleaned_value) if cleaned_value else default
            except (ValueError, TypeError):
                return default

    def run(self):
        try:
            items_by_rrf = {}
            with dbfread.DBF(RRF_ITEMS_DBF_PATH, load=True, encoding='latin1') as dbf_items:
                total_items = len(dbf_items)
                last_percent = -1
                for i, item_rec in enumerate(dbf_items.records):
                    rrf_num = self._get_safe_rrf_num(item_rec.get('T_DRNUM'))
                    if not rrf_num: continue
                    if rrf_num not in items_by_rrf: items_by_rrf[rrf_num] = []

                    remarks = "\n".join(
                        filter(None, [str(item_rec.get(f'T_DESC{i}', '')).strip() for i in range(3, 5)]))

                    items_by_rrf[rrf_num].append({
                        "rrf_no": rrf_num, "quantity": self._to_float(item_rec.get('T_TOTALWT')),
                        "unit": str(item_rec.get('T_TOTALWTU', '')).strip(),
                        "product_code": str(item_rec.get('T_PRODCODE', '')).strip(),
                        "lot_number": str(item_rec.get('T_DESC1', '')).strip(),
                        "reference_number": str(item_rec.get('T_DESC2', '')).strip(), "remarks": remarks
                    })
                    if total_items > 0:
                        percent = int(((i + 1) / total_items) * 45)
                        if percent > last_percent:
                            self.progress.emit(percent)
                            last_percent = percent
            self.progress.emit(45)

            primary_recs = []
            with dbfread.DBF(RRF_PRIMARY_DBF_PATH, load=True, encoding='latin1') as dbf_primary:
                total_primary = len(dbf_primary)
                last_percent = -1
                for i, r in enumerate(dbf_primary.records):
                    rrf_num = self._get_safe_rrf_num(r.get('T_DRNUM'))
                    if not rrf_num: continue
                    primary_recs.append({
                        "rrf_no": rrf_num, "rrf_date": r.get('T_DRDATE'),
                        "customer_name": str(r.get('T_CUSTOMER', '')).strip(),
                        "material_type": str(r.get('T_DELTO', '')).strip(),
                        "prepared_by": str(r.get('T_USERID', '')).strip(),
                        "is_deleted": bool(r.get('T_DELETED', False))
                    })
                    if total_primary > 0:
                        percent = 45 + int(((i + 1) / total_primary) * 45)
                        if percent > last_percent:
                            self.progress.emit(percent)
                            last_percent = percent
            self.progress.emit(90)

            if not primary_recs:
                self.finished.emit(True, "Sync Info: No new RRF records found to sync.");
                return

            with engine.connect() as conn:
                with conn.begin():
                    rrf_numbers_to_sync = [rec['rrf_no'] for rec in primary_recs]
                    self.progress.emit(92)
                    conn.execute(text("DELETE FROM rrf_items WHERE rrf_no = ANY(:rrf_nos)"),
                                 {"rrf_nos": rrf_numbers_to_sync})

                    self.progress.emit(95)
                    conn.execute(text("""
                        INSERT INTO rrf_primary (rrf_no, rrf_date, customer_name, material_type, prepared_by, is_deleted, encoded_by, encoded_on, edited_by, edited_on)
                        VALUES (:rrf_no, :rrf_date, :customer_name, :material_type, :prepared_by, :is_deleted, 'DBF_SYNC', NOW(), 'DBF_SYNC', NOW())
                        ON CONFLICT (rrf_no) DO UPDATE SET
                            rrf_date = EXCLUDED.rrf_date,
                            customer_name = EXCLUDED.customer_name,
                            material_type = EXCLUDED.material_type,
                            prepared_by = EXCLUDED.prepared_by,
                            is_deleted = EXCLUDED.is_deleted,
                            edited_by = 'DBF_SYNC',
                            edited_on = NOW()
                    """), primary_recs)

                    self.progress.emit(98)
                    all_items_to_insert = [item for rrf_num in rrf_numbers_to_sync if rrf_num in items_by_rrf for item
                                           in items_by_rrf[rrf_num]]
                    if all_items_to_insert:
                        conn.execute(text("""
                            INSERT INTO rrf_items (rrf_no, quantity, unit, product_code, lot_number, reference_number, remarks)
                            VALUES (:rrf_no, :quantity, :unit, :product_code, :lot_number, :reference_number, :remarks)
                        """), all_items_to_insert)

            self.progress.emit(100)
            self.finished.emit(True,
                               f"RRF sync complete.\n{len(primary_recs)} primary records and {len(all_items_to_insert)} items processed.")
        except dbfread.DBFNotFound as e:
            self.finished.emit(False, f"File Not Found: A required RRF DBF file is missing.\nDetails: {e}")
        except Exception as e:
            trace_info = traceback.format_exc()
            print(f"RRF SYNC CRITICAL ERROR: {e}\n{trace_info}")
            self.finished.emit(False,
                               f"An unexpected error occurred during RRF sync:\n{e}\n\nCheck console/logs for technical details.")


# --- DASHBOARD WIDGETS (INTEGRATED) ---
class KPIWidget(QFrame):
    """A stylized frame to display a Key Performance Indicator."""

    def __init__(self, title, value, icon_name, icon_color, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)
        self.setFixedHeight(120)
        self.setStyleSheet("""
            QFrame { 
                background-color: #ffffff; 
                border-radius: 8px;
            }
            QLabel { background-color: transparent; }
        """)
        layout = QHBoxLayout(self)
        icon_label = QLabel()
        icon_label.setPixmap(fa.icon(icon_name, color=icon_color).pixmap(QSize(48, 48)))
        layout.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignLeft)
        text_layout = QVBoxLayout()
        title_label = QLabel(f"<b>{title}</b>")
        title_label.setFont(QFont("Segoe UI", 10))
        value_label = QLabel(f"{value}")
        value_label.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        text_layout.addWidget(title_label)
        text_layout.addWidget(value_label)
        text_layout.addStretch()
        layout.addLayout(text_layout)
        layout.addStretch()


class DashboardPage(QWidget):
    """The main dashboard page with KPIs, charts, and recent activity."""

    def __init__(self, db_engine, username, log_audit_trail_func):
        super().__init__()
        self.engine = db_engine
        self.username = username
        self.log_audit_trail = log_audit_trail_func
        self._setup_ui()
        self.refresh_page()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)

        top_header_layout = QHBoxLayout()
        header = QLabel("<h1>Inventory Data Overview</h1>")
        header.setStyleSheet("color: #3a506b;")

        instruction_label = QLabel(
            "This dashboard provides a real-time summary of inventory metrics and recent activities.")
        instruction_label.setStyleSheet("font-style: italic; color: #555;")

        self.refresh_button = QPushButton(fa.icon('fa5s.sync-alt'), " Refresh Data")
        self.refresh_button.clicked.connect(self.refresh_page)

        top_header_layout.addWidget(header)
        top_header_layout.addWidget(instruction_label, 1, Qt.AlignmentFlag.AlignCenter)
        top_header_layout.addWidget(self.refresh_button)
        main_layout.addLayout(top_header_layout)

        kpi_group = QGroupBox("Key Performance Indicators (KPIs)")
        self.kpi_layout = QGridLayout(kpi_group)
        main_layout.addWidget(kpi_group)

        content_grid = QGridLayout()
        content_grid.setSpacing(15)

        flow_chart_group = QGroupBox("Inventory Flow (In, Out & Net - Last 12 Months)")
        flow_layout = QVBoxLayout(flow_chart_group)
        self.flow_chart_view = self._create_chart_view_or_placeholder("Line Chart")
        flow_layout.addWidget(self.flow_chart_view)
        content_grid.addWidget(flow_chart_group, 0, 0)

        volume_chart_group = QGroupBox("Transaction Volume by Type")
        volume_layout = QVBoxLayout(volume_chart_group)
        self.volume_chart_view = self._create_chart_view_or_placeholder("Bar Chart")
        volume_layout.addWidget(self.volume_chart_view)
        content_grid.addWidget(volume_chart_group, 0, 1)

        top_products_group = QGroupBox("Top 10 Products by Stock Level (kg)")
        top_products_layout = QVBoxLayout(top_products_group)
        self.top_products_chart_view = self._create_chart_view_or_placeholder("Bar Chart")
        top_products_layout.addWidget(self.top_products_chart_view)
        content_grid.addWidget(top_products_group, 1, 0)

        activity_group = QGroupBox("Recent Inventory Activity (Last 20 records)")
        activity_layout = QVBoxLayout(activity_group)
        self.activity_table = QTableWidget()
        self.activity_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.activity_table.setColumnCount(7)
        self.activity_table.setHorizontalHeaderLabels(
            ["Date", "Type", "Ref No", "Product", "IN (kg)", "OUT (kg)", "Remarks"])
        self.activity_table.verticalHeader().setVisible(False)
        self.activity_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.activity_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        activity_layout.addWidget(self.activity_table)
        content_grid.addWidget(activity_group, 1, 1)

        main_layout.addLayout(content_grid, 1)

    def _create_chart_view_or_placeholder(self, chart_type: str) -> QWidget:
        if CHARTS_AVAILABLE:
            chart_view = QChartView()
            chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
            return chart_view
        else:
            placeholder = QLabel(
                f"PyQt6-Charts not installed.\n{chart_type} is unavailable.\n\nPlease run: pip install PyQt6-Charts")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setMinimumHeight(350)
            placeholder.setStyleSheet("border: 1px dashed #ccc; color: #555;")
            return placeholder

    def refresh_page(self):
        self._clear_kpis()
        self._load_data()
        self.log_audit_trail("REFRESH_DASHBOARD", "User refreshed the analytics dashboard.")

    def _clear_kpis(self):
        while self.kpi_layout.count():
            child = self.kpi_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _load_data(self):
        self._load_recent_activity()
        kpi_data = self._fetch_kpi_data()

        self.kpi_layout.addWidget(
            KPIWidget("Total Stock (KG)", f"{kpi_data['total_stock']:,.2f}", 'fa5s.weight',
                      AppStyles.PRIMARY_ACCENT_COLOR), 0, 0)
        self.kpi_layout.addWidget(
            KPIWidget("Total Stock IN (YTD)", f"{kpi_data['total_in_ytd']:,.2f}", 'fa5s.arrow-alt-circle-down',
                      AppStyles.SUCCESS_COLOR), 0, 1)
        self.kpi_layout.addWidget(
            KPIWidget("Total Stock OUT (YTD)", f"{kpi_data['total_out_ytd']:,.2f}", 'fa5s.arrow-alt-circle-up',
                      AppStyles.DESTRUCTIVE_COLOR), 0, 2)
        self.kpi_layout.addWidget(
            KPIWidget("Unique Products in Stock", f"{kpi_data['unique_products']:,}", 'fa5s.boxes',
                      AppStyles.SECONDARY_ACCENT_COLOR), 1, 0)
        self.kpi_layout.addWidget(
            KPIWidget("Total Transactions (YTD)", f"{kpi_data['total_transactions_ytd']:,}", 'fa5s.exchange-alt',
                      AppStyles.NEUTRAL_COLOR), 1, 1)
        self.kpi_layout.addWidget(
            KPIWidget("Failed Transactions (30d)", f"{kpi_data['failed_tx_30d']:,}", 'fa5s.exclamation-triangle',
                      AppStyles.DESTRUCTIVE_COLOR), 1, 2)

        if CHARTS_AVAILABLE:
            self._create_flow_chart()
            self._create_volume_barchart()
            self._create_top_products_chart()

    def _fetch_kpi_data(self):
        try:
            current_year = date.today().year
            with self.engine.connect() as conn:
                summary_query = text("""
                    SELECT 
                        (SELECT SUM(quantity_in - quantity_out) FROM transactions) as total_stock,
                        (SELECT COUNT(id) FROM transactions WHERE EXTRACT(YEAR FROM transaction_date) = :year) as total_tx_ytd,
                        (SELECT COALESCE(SUM(quantity_in), 0) FROM transactions WHERE EXTRACT(YEAR FROM transaction_date) = :year) as total_in_ytd,
                        (SELECT COALESCE(SUM(quantity_out), 0) FROM transactions WHERE EXTRACT(YEAR FROM transaction_date) = :year) as total_out_ytd,
                        (SELECT COUNT(DISTINCT product_code) FROM transactions) as unique_products,
                        (SELECT COUNT(id) FROM failed_transactions WHERE transaction_date >= NOW() - INTERVAL '30 days') as failed_count;
                """)
                result = conn.execute(summary_query, {"year": current_year}).mappings().one()

            return {
                'total_stock': Decimal(result['total_stock'] or 0),
                'total_in_ytd': Decimal(result['total_in_ytd'] or 0),
                'total_out_ytd': Decimal(result['total_out_ytd'] or 0),
                'total_transactions_ytd': int(result['total_tx_ytd'] or 0),
                'unique_products': int(result['unique_products'] or 0),
                'failed_tx_30d': int(result['failed_count'] or 0),
            }
        except Exception as e:
            print(f"Error fetching KPI data: {e}")
            return {key: 0 for key in
                    ['total_stock', 'total_in_ytd', 'total_out_ytd', 'total_transactions_ytd', 'unique_products',
                     'failed_tx_30d']}

    def _load_recent_activity(self):
        try:
            with self.engine.connect() as conn:
                query = text("""
                    SELECT transaction_date, transaction_type, source_ref_no, product_code, 
                           quantity_in, quantity_out, remarks
                    FROM transactions ORDER BY transaction_date DESC, id DESC LIMIT 20
                """)
                results = conn.execute(query).mappings().all()

            self.activity_table.setRowCount(len(results))
            for row_idx, record in enumerate(results):
                self.activity_table.setItem(row_idx, 0, QTableWidgetItem(str(record['transaction_date'])))
                self.activity_table.setItem(row_idx, 1, QTableWidgetItem(record['transaction_type']))
                self.activity_table.setItem(row_idx, 2, QTableWidgetItem(record['source_ref_no']))
                self.activity_table.setItem(row_idx, 3, QTableWidgetItem(record['product_code'] or 'N/A'))
                in_qty = Decimal(record.get('quantity_in', 0) or 0)
                out_qty = Decimal(record.get('quantity_out', 0) or 0)
                in_item = QTableWidgetItem(f"{in_qty:,.2f}");
                out_item = QTableWidgetItem(f"{out_qty:,.2f}")
                in_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                out_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.activity_table.setItem(row_idx, 4, in_item)
                self.activity_table.setItem(row_idx, 5, out_item)
                self.activity_table.setItem(row_idx, 6, QTableWidgetItem(record.get('remarks', '') or ''))
        except Exception as e:
            print(f"Error loading recent activity: {e}")
            self.activity_table.setRowCount(0)

    def _create_flow_chart(self):
        series_in = QLineSeries();
        series_in.setName("Stock IN")
        series_out = QLineSeries();
        series_out.setName("Stock OUT")
        series_net = QLineSeries();
        series_net.setName("Net Flow")

        series_in.setPen(QPen(QColor(AppStyles.SUCCESS_COLOR), 3))
        series_out.setPen(QPen(QColor(AppStyles.DESTRUCTIVE_COLOR), 3))
        net_pen = QPen(QColor(AppStyles.PRIMARY_ACCENT_COLOR), 2);
        net_pen.setStyle(Qt.PenStyle.DashLine);
        series_net.setPen(net_pen)

        series_in.hovered.connect(self._handle_series_hover);
        series_out.hovered.connect(self._handle_series_hover);
        series_net.hovered.connect(self._handle_series_hover)

        query = text("""
            SELECT to_char(transaction_date, 'YYYY-MM') AS month, SUM(quantity_in) AS total_in, SUM(quantity_out) AS total_out
            FROM transactions WHERE transaction_date >= date_trunc('month', NOW()) - INTERVAL '11 months'
            GROUP BY month ORDER BY month;
        """)
        categories, max_val = [], 0
        try:
            with self.engine.connect() as conn:
                results = conn.execute(query).mappings().all()
            for i, row in enumerate(results):
                categories.append(datetime.strptime(row['month'], '%Y-%m').strftime('%b-%y'))
                qty_in = float(row['total_in'] or 0);
                qty_out = float(row['total_out'] or 0)
                series_in.append(i, qty_in);
                series_out.append(i, qty_out);
                series_net.append(i, qty_in - qty_out)
                max_val = max(max_val, qty_in, qty_out)
        except Exception as e:
            print(f"Error fetching line chart data: {e}")

        chart = QChart();
        chart.addSeries(series_in);
        chart.addSeries(series_out);
        chart.addSeries(series_net)
        chart.setAnimationOptions(QChart.AnimationOption.SeriesAnimations)
        axis_x = QBarCategoryAxis();
        axis_x.append(categories);
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        axis_y = QValueAxis();
        axis_y.setLabelFormat("%.0f kg");
        axis_y.setRange(0, (max_val * 1.1) if max_val > 0 else 10)
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series_in.attachAxis(axis_x);
        series_in.attachAxis(axis_y);
        series_out.attachAxis(axis_x);
        series_out.attachAxis(axis_y);
        series_net.attachAxis(axis_x);
        series_net.attachAxis(axis_y)
        chart.legend().setVisible(True);
        chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)
        self.flow_chart_view.setChart(chart)

    def _handle_series_hover(self, point: QPointF, state: bool):
        if state:
            series = self.sender()
            self.flow_chart_view.setToolTip(f"{series.name()}: {point.y():,.2f} kg")
        else:
            self.flow_chart_view.setToolTip("")

    def _create_volume_barchart(self):
        series = QHorizontalBarSeries()
        query = text(
            "SELECT transaction_type, COUNT(id) as tx_count FROM transactions GROUP BY transaction_type ORDER BY tx_count ASC;")
        categories, max_val = [], 0
        try:
            with self.engine.connect() as conn:
                results = conn.execute(query).mappings().all()
            bar_set = QBarSet("Count")
            for row in results:
                categories.append(row['transaction_type']);
                count = int(row['tx_count']);
                bar_set.append(count);
                max_val = max(max_val, count)
            series.append(bar_set)
        except Exception as e:
            print(f"Error fetching bar chart data: {e}")

        chart = QChart();
        chart.addSeries(series);
        chart.setAnimationOptions(QChart.AnimationOption.SeriesAnimations)
        axis_y = QBarCategoryAxis();
        axis_y.append(categories);
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        axis_x = QValueAxis();
        axis_x.setRange(0, (max_val * 1.1) if max_val > 0 else 10);
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(axis_x);
        series.attachAxis(axis_y)
        chart.legend().setVisible(False)
        self.volume_chart_view.setChart(chart)

    def _create_top_products_chart(self):
        series = QBarSeries()
        query = text("""
            SELECT product_code, SUM(quantity_in - quantity_out) as stock_balance 
            FROM transactions GROUP BY product_code HAVING SUM(quantity_in - quantity_out) > 0 
            ORDER BY stock_balance DESC LIMIT 10;
        """)
        categories, max_val = [], 0
        try:
            with self.engine.connect() as conn:
                results = conn.execute(query).mappings().all()
            bar_set = QBarSet("Stock (kg)")
            for row in results:
                categories.append(row['product_code']);
                balance = float(row['stock_balance']);
                bar_set.append(balance);
                max_val = max(max_val, balance)
            series.append(bar_set)
        except Exception as e:
            print(f"Error fetching top products data: {e}")

        chart = QChart();
        chart.addSeries(series);
        chart.setAnimationOptions(QChart.AnimationOption.SeriesAnimations)
        axis_x = QBarCategoryAxis();
        axis_x.append(categories);
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        axis_y = QValueAxis();
        axis_y.setRange(0, (max_val * 1.1) if max_val > 0 else 10);
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_x);
        series.attachAxis(axis_y)
        chart.legend().setVisible(False)
        self.top_products_chart_view.setChart(chart)


# --- END OF DASHBOARD WIDGETS ---

def initialize_database():
    """
    Initializes the database schema, including the beginv_sheet1 table
    and ensuring all tables, especially outgoing_records_items, have the required columns.
    """
    print("Initializing database schema...")
    try:
        with engine.connect() as connection:
            with connection.begin():
                # --- System Tables ---
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL, qc_access BOOLEAN DEFAULT TRUE, role TEXT DEFAULT 'Editor');"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS qc_audit_trail (id SERIAL PRIMARY KEY, timestamp TIMESTAMP, username TEXT, action_type TEXT, details TEXT, hostname TEXT, ip_address TEXT, mac_address TEXT);"))

                # --- Central Transactions Table for Inventory ---
                connection.execute(text("""
                    CREATE TABLE IF NOT EXISTS transactions (
                        id SERIAL PRIMARY KEY,
                        transaction_date DATE NOT NULL,
                        transaction_type VARCHAR(50) NOT NULL, 
                        source_ref_no VARCHAR(50),             
                        product_code VARCHAR(50) NOT NULL,
                        lot_number VARCHAR(50),
                        quantity_in NUMERIC(15, 6) DEFAULT 0,
                        quantity_out NUMERIC(15, 6) DEFAULT 0,
                        unit VARCHAR(20),
                        warehouse VARCHAR(50),
                        encoded_by VARCHAR(50),
                        encoded_on TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        remarks TEXT
                    );
                """))
                connection.execute(
                    text("CREATE INDEX IF NOT EXISTS idx_transactions_product_code ON transactions (product_code);"))
                connection.execute(
                    text("CREATE INDEX IF NOT EXISTS idx_transactions_lot_number ON transactions (lot_number);"))
                connection.execute(text(
                    "CREATE INDEX IF NOT EXISTS idx_transactions_source_ref_no ON transactions (source_ref_no);"))

                # --- NEW: FAILED Transactions Table ---
                connection.execute(text("""
                    CREATE TABLE IF NOT EXISTS failed_transactions (
                        id SERIAL PRIMARY KEY,
                        transaction_date DATE NOT NULL,
                        transaction_type VARCHAR(50) NOT NULL,
                        source_ref_no VARCHAR(50),
                        product_code VARCHAR(50) NOT NULL,
                        lot_number VARCHAR(50),
                        quantity_in NUMERIC(15, 6) DEFAULT 0,
                        quantity_out NUMERIC(15, 6) DEFAULT 0,
                        unit VARCHAR(20),
                        warehouse VARCHAR(50),
                        encoded_by VARCHAR(50),
                        encoded_on TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        remarks TEXT
                    );
                """))
                connection.execute(text(
                    "CREATE INDEX IF NOT EXISTS idx_failed_transactions_product_code ON failed_transactions (product_code);"))
                connection.execute(text(
                    "CREATE INDEX IF NOT EXISTS idx_failed_transactions_lot_number ON failed_transactions (lot_number);"))
                connection.execute(text(
                    "CREATE INDEX IF NOT EXISTS idx_failed_transactions_source_ref_no ON failed_transactions (source_ref_no);"))

                # --- Application Settings Table ---
                connection.execute(text("""
                    CREATE TABLE IF NOT EXISTS app_settings (
                        setting_key VARCHAR(50) PRIMARY KEY,
                        setting_value VARCHAR(255)
                    );
                """))
                connection.execute(text("""
                    INSERT INTO app_settings (setting_key, setting_value)
                    VALUES
                        ('RRF_SEQUENCE_START', '15000'),
                        ('DR_SEQUENCE_START', '100001')
                    ON CONFLICT (setting_key) DO NOTHING;
                """))

                # --- Legacy & Core Data Tables ---
                connection.execute(text("""
                    CREATE TABLE IF NOT EXISTS legacy_production (
                        lot_number TEXT PRIMARY KEY, prod_code TEXT, customer_name TEXT, formula_id TEXT, operator TEXT,
                        supervisor TEXT, prod_id TEXT, machine TEXT, qty_prod NUMERIC(15, 6),
                        prod_date DATE, prod_color TEXT, last_synced_on TIMESTAMP
                    );
                """))
                connection.execute(text(
                    "CREATE INDEX IF NOT EXISTS idx_legacy_production_lot_number ON legacy_production (lot_number);"))

                # --- Beginning Inventory Table (beginv_sheet1) ---
                connection.execute(text("""
                    CREATE TABLE IF NOT EXISTS beginv_sheet1 (
                        id SERIAL PRIMARY KEY,
                        fg_type VARCHAR(50),
                        production_date DATE,
                        product_code VARCHAR(50) NOT NULL,
                        customer TEXT,
                        lot_number VARCHAR(50) NOT NULL,
                        qty NUMERIC(15, 6) NOT NULL,
                        location VARCHAR(50),
                        remarks TEXT,
                        box_number VARCHAR(50),
                        bag_number VARCHAR(50),
                        floor_number VARCHAR(50)
                    );
                """))
                connection.execute(text(
                    "CREATE INDEX IF NOT EXISTS idx_beginv_product_lot ON beginv_sheet1 (product_code, lot_number);"
                ))

                # --- NEW: Beginning Inventory Table for Failed Items (beg_invfailed1) ---
                connection.execute(text("""
                                    CREATE TABLE IF NOT EXISTS beg_invfailed1 (
                                        id SERIAL PRIMARY KEY,
                                        fg_type VARCHAR(50),
                                        production_date DATE,
                                        product_code VARCHAR(50) NOT NULL,
                                        customer TEXT,
                                        lot_number VARCHAR(50) NOT NULL,
                                        qty NUMERIC(15, 6) NOT NULL,
                                        location VARCHAR(50),
                                        remarks TEXT,
                                        box_number VARCHAR(50),
                                        bag_number VARCHAR(50),
                                        floor_number VARCHAR(50)
                                    );
                                """))
                connection.execute(text(
                    "CREATE INDEX IF NOT EXISTS idx_beg_invfailed1_product_lot ON beg_invfailed1 (product_code, lot_number);"
                ))
                # --- Customers, Units, Aliases ---
                connection.execute(text("""
                    CREATE TABLE IF NOT EXISTS customers (id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL, deliver_to TEXT, address TEXT, tin TEXT, terms TEXT, is_deleted BOOLEAN NOT NULL DEFAULT FALSE);
                """))
                connection.execute(
                    text("CREATE TABLE IF NOT EXISTS units (id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL);"))
                connection.execute(
                    text("INSERT INTO units (name) VALUES ('KG.'), ('PCS'), ('BOX') ON CONFLICT (name) DO NOTHING;"))

                connection.execute(text("""
                    CREATE TABLE IF NOT EXISTS product_aliases (
                        id SERIAL PRIMARY KEY,
                        product_code TEXT UNIQUE NOT NULL,
                        alias_code TEXT,
                        description TEXT,
                        extra_description TEXT
                    );
                """))

                # --- Dropdown/Helper Tables ---
                connection.execute(
                    text("CREATE TABLE IF NOT EXISTS endorsers (id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL);"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS endorsement_remarks (id SERIAL PRIMARY KEY, remark_text TEXT UNIQUE NOT NULL);"))
                connection.execute(
                    text("CREATE TABLE IF NOT EXISTS warehouses (id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL);"))
                connection.execute(
                    text("CREATE TABLE IF NOT EXISTS rr_receivers (id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL);"))
                connection.execute(
                    text("CREATE TABLE IF NOT EXISTS rr_reporters (id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL);"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS qcfp_endorsers (id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL);"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS qcfp_receivers (id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL);"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS qce_endorsers (id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL);"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS qce_receivers (id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL);"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS qcf_endorsers (id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL);"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS qcf_receivers (id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL);"))

                # --- NEW: Failure Reasons Lookup Table ---
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS qcf_failure_reasons (id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL);"))
                # ----------------------------------------

                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS qce_bag_numbers (id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL);"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS qce_box_numbers (id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL);"))
                connection.execute(
                    text("CREATE TABLE IF NOT EXISTS qce_remarks (id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL);"))

                # --- FG Endorsement Tables (unchanged) ---
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS fg_endorsements_primary (id SERIAL PRIMARY KEY, system_ref_no TEXT NOT NULL UNIQUE, form_ref_no TEXT, date_endorsed DATE, category TEXT, product_code TEXT, lot_number TEXT, quantity_kg NUMERIC(15, 6), weight_per_lot NUMERIC(15, 6), bag_no TEXT, status TEXT, endorsed_by TEXT, remarks TEXT, location TEXT, encoded_by TEXT, encoded_on TIMESTAMP, edited_by TEXT, edited_on TIMESTAMP, is_deleted BOOLEAN NOT NULL DEFAULT FALSE);"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS fg_endorsements_secondary (id SERIAL PRIMARY KEY, system_ref_no TEXT, lot_number TEXT, quantity_kg NUMERIC(15, 6), product_code TEXT, status TEXT, bag_no TEXT, endorsed_by TEXT);"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS fg_endorsements_excess (id SERIAL PRIMARY KEY, system_ref_no TEXT, lot_number TEXT, quantity_kg NUMERIC(15, 6), product_code TEXT, status TEXT, bag_no TEXT, endorsed_by TEXT);"))

                # --- Receiving Report Tables (unchanged) ---
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS receiving_reports_primary (id SERIAL PRIMARY KEY, rr_no TEXT NOT NULL UNIQUE, receive_date DATE NOT NULL, receive_from TEXT, pull_out_form_no TEXT, received_by TEXT, reported_by TEXT, remarks TEXT, encoded_by TEXT, encoded_on TIMESTAMP, edited_by TEXT, edited_on TIMESTAMP, is_deleted BOOLEAN NOT NULL DEFAULT FALSE);"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS receiving_reports_items (id SERIAL PRIMARY KEY, rr_no TEXT NOT NULL, material_code TEXT, lot_no TEXT, quantity_kg NUMERIC(15, 6), status TEXT, location TEXT, remarks TEXT, FOREIGN KEY (rr_no) REFERENCES receiving_reports_primary (rr_no) ON DELETE CASCADE);"))

                # --- QC Endorsement Tables (QC Passed/Excess) ---
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS qcfp_endorsements_primary (id SERIAL PRIMARY KEY, system_ref_no TEXT NOT NULL UNIQUE, form_ref_no TEXT, endorsement_date DATE NOT NULL, product_code TEXT NOT NULL, lot_number TEXT NOT NULL, quantity_kg NUMERIC(15, 6), weight_per_lot NUMERIC(15, 6), endorsed_by TEXT, warehouse TEXT, received_by_name TEXT, received_date_time TIMESTAMP, encoded_by TEXT, encoded_on TIMESTAMP, edited_by TEXT, edited_on TIMESTAMP, is_deleted BOOLEAN NOT NULL DEFAULT FALSE);"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS qcfp_endorsements_secondary (id SERIAL PRIMARY KEY, system_ref_no TEXT NOT NULL, lot_number TEXT NOT NULL, quantity_kg NUMERIC(15, 6));"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS qcfp_endorsements_excess (id SERIAL PRIMARY KEY, system_ref_no TEXT NOT NULL, lot_number TEXT NOT NULL, quantity_kg NUMERIC(15, 6));"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS qce_endorsements_primary (id SERIAL PRIMARY KEY, system_ref_no TEXT NOT NULL UNIQUE, form_ref_no TEXT, product_code TEXT, lot_number TEXT, quantity_kg NUMERIC(15, 6), weight_per_lot NUMERIC(15, 6), status TEXT, bag_number TEXT, box_number TEXT, remarks TEXT, date_endorsed DATE, endorsed_by TEXT, date_received TIMESTAMP, received_by TEXT, encoded_by TEXT, encoded_on TIMESTAMP, is_deleted BOOLEAN NOT NULL DEFAULT FALSE);"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS qce_endorsements_secondary (id SERIAL PRIMARY KEY, system_ref_no TEXT NOT NULL, lot_number TEXT NOT NULL, quantity_kg NUMERIC(15, 6), bag_number TEXT, box_number TEXT, remarks TEXT);"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS qce_endorsements_excess (id SERIAL PRIMARY KEY, system_ref_no TEXT NOT NULL, lot_number TEXT NOT NULL, quantity_kg NUMERIC(15, 6), bag_number TEXT, box_number TEXT, remarks TEXT);"))

                # --- QC Failed Endorsement Tables (UPDATED SCHEMA) ---
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS qcf_endorsements_primary (id SERIAL PRIMARY KEY, system_ref_no TEXT NOT NULL UNIQUE, form_ref_no TEXT, endorsement_date DATE NOT NULL, product_code TEXT NOT NULL, lot_number TEXT NOT NULL, quantity_kg NUMERIC(15, 6), weight_per_lot NUMERIC(15, 6), failure_reason TEXT, endorsed_by TEXT, warehouse TEXT, received_by_name TEXT, received_date_time TIMESTAMP, encoded_by TEXT, encoded_on TIMESTAMP, edited_by TEXT, edited_on TIMESTAMP, is_deleted BOOLEAN NOT NULL DEFAULT FALSE);"))

                # *** MIGRATION CHECK for existing installations ***
                connection.execute(text("""
                    DO $$ 
                    BEGIN
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                       WHERE table_name='qcf_endorsements_primary' AND column_name='failure_reason') THEN
                            ALTER TABLE qcf_endorsements_primary ADD COLUMN failure_reason TEXT;
                        END IF;
                    END
                    $$;
                """))
                # ---------------------------------------------------

                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS qcf_endorsements_secondary (id SERIAL PRIMARY KEY, system_ref_no TEXT NOT NULL, lot_number TEXT NOT NULL, quantity_kg NUMERIC(15, 6));"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS qcf_endorsements_excess (id SERIAL PRIMARY KEY, system_ref_no TEXT NOT NULL, lot_number TEXT NOT NULL, quantity_kg NUMERIC(15, 6));"))

                # --- RRF & Product Delivery Tables (unchanged) ---
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS rrf_primary (id SERIAL PRIMARY KEY, rrf_no TEXT NOT NULL UNIQUE, rrf_date DATE, customer_name TEXT, material_type TEXT, prepared_by TEXT, encoded_by TEXT, encoded_on TIMESTAMP, edited_by TEXT, edited_on TIMESTAMP, is_deleted BOOLEAN NOT NULL DEFAULT FALSE);"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS rrf_items (id SERIAL PRIMARY KEY, rrf_no TEXT NOT NULL, quantity NUMERIC(15, 6), unit TEXT, product_code TEXT, lot_number TEXT, reference_number TEXT, remarks TEXT, FOREIGN KEY (rrf_no) REFERENCES rrf_primary (rrf_no) ON DELETE CASCADE);"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS rrf_lot_breakdown (id SERIAL PRIMARY KEY, rrf_no TEXT NOT NULL, item_id INTEGER, lot_number TEXT NOT NULL, quantity_kg NUMERIC(15, 6), FOREIGN KEY (rrf_no) REFERENCES rrf_primary (rrf_no) ON DELETE CASCADE);"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS product_delivery_primary (id SERIAL PRIMARY KEY, dr_no TEXT NOT NULL UNIQUE, delivery_date DATE, customer_name TEXT, deliver_to TEXT, address TEXT, po_no TEXT, order_form_no TEXT, fg_out_id TEXT, terms TEXT, prepared_by TEXT, encoded_by TEXT, encoded_on TIMESTAMP, edited_by TEXT, edited_on TIMESTAMP, is_deleted BOOLEAN NOT NULL DEFAULT FALSE, is_printed BOOLEAN NOT NULL DEFAULT FALSE);"))

                # --- product_delivery_items (unchanged) ---
                connection.execute(text("""
                    CREATE TABLE IF NOT EXISTS product_delivery_items (
                        id SERIAL PRIMARY KEY,
                        dr_no TEXT NOT NULL,
                        quantity NUMERIC(15, 6),
                        unit TEXT,
                        product_code TEXT,
                        product_color TEXT,
                        no_of_packing NUMERIC(15, 2),
                        weight_per_pack NUMERIC(15, 6),
                        lot_numbers TEXT,
                        attachments TEXT,
                        unit_price NUMERIC(15, 6),
                        lot_no_1 TEXT,      -- NEW
                        lot_no_2 TEXT,      -- NEW
                        lot_no_3 TEXT,      -- NEW
                        mfg_date TEXT,      -- NEW
                        alias_code TEXT,    -- NEW (to store 'PL00X814MB')
                        alias_desc TEXT,    -- NEW (to store 'MASTERBATCH ORANGE OA14430E')
                        FOREIGN KEY (dr_no) REFERENCES product_delivery_primary (dr_no) ON DELETE CASCADE
                    );
                """))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS product_delivery_lot_breakdown (id SERIAL PRIMARY KEY, dr_no TEXT NOT NULL, item_id INTEGER, lot_number TEXT NOT NULL, quantity_kg NUMERIC(15, 6), FOREIGN KEY (dr_no) REFERENCES product_delivery_primary (dr_no) ON DELETE CASCADE);"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS delivery_tracking (id SERIAL PRIMARY KEY, dr_no VARCHAR(20) NOT NULL UNIQUE, status VARCHAR(50) NOT NULL, scanned_by VARCHAR(50), scanned_on TIMESTAMP);"))

                # --- Outgoing Form Tables (Primary and Items) ---
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS outgoing_releasers (id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL);"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS outgoing_qty_produced_options (id SERIAL PRIMARY KEY, value TEXT UNIQUE NOT NULL);"))
                connection.execute(text("""
                    CREATE TABLE IF NOT EXISTS outgoing_records_primary (
                        id SERIAL PRIMARY KEY, production_form_id TEXT NOT NULL, ref_no TEXT, date_out DATE, activity TEXT,
                        released_by TEXT, encoded_by TEXT, encoded_on TIMESTAMP, edited_by TEXT, edited_on TIMESTAMP, is_deleted BOOLEAN NOT NULL DEFAULT FALSE
                    );
                """))

                # --- NOTE: We create the basic item table schema first ---
                connection.execute(text("""
                    CREATE TABLE IF NOT EXISTS outgoing_records_items (
                        id SERIAL PRIMARY KEY, primary_id INTEGER NOT NULL REFERENCES outgoing_records_primary(id) ON DELETE CASCADE,
                        prod_id TEXT, product_code TEXT, lot_used TEXT, quantity_required_kg NUMERIC(15, 6),
                        new_lot_details TEXT, status TEXT, box_number TEXT, remaining_quantity NUMERIC(15, 6), quantity_produced TEXT
                    );
                """))

                # *** FIX: ADD MISSING WAREHOUSE COLUMN VIA SAFE MIGRATION ***
                connection.execute(text("""
                    DO $$ 
                    BEGIN
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                       WHERE table_name='outgoing_records_items' AND column_name='warehouse') THEN
                            ALTER TABLE outgoing_records_items ADD COLUMN warehouse VARCHAR(50);
                        END IF;
                    END
                    $$;
                """))
                # -----------------------------------------------------------

                # --- Requisition Logbook Tables (unchanged) ---
                connection.execute(text("""
                    CREATE TABLE IF NOT EXISTS requisition_logbook (
                        id SERIAL PRIMARY KEY,
                        req_id TEXT NOT NULL UNIQUE,
                        manual_ref_no TEXT,
                        category TEXT,
                        request_date DATE,
                        requester_name TEXT,
                        department TEXT,
                        product_code TEXT,
                        lot_no TEXT,
                        quantity_kg NUMERIC(15, 6),
                        status TEXT,
                        approved_by TEXT,
                        remarks TEXT,
                        location VARCHAR(50),
                        request_for VARCHAR(10),
                        encoded_by TEXT,
                        encoded_on TIMESTAMP,
                        edited_by TEXT,
                        edited_on TIMESTAMP,
                        is_deleted BOOLEAN NOT NULL DEFAULT FALSE
                    );
                """))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS requisition_requesters (id SERIAL PRIMARY KEY, name VARCHAR(255) UNIQUE NOT NULL);"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS requisition_departments (id SERIAL PRIMARY KEY, name VARCHAR(255) UNIQUE NOT NULL);"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS requisition_approvers (id SERIAL PRIMARY KEY, name VARCHAR(255) UNIQUE NOT NULL);"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS requisition_statuses (id SERIAL PRIMARY KEY, status_name VARCHAR(255) UNIQUE NOT NULL);"))
                connection.execute(text(
                    "INSERT INTO requisition_statuses (status_name) VALUES ('PENDING'), ('APPROVED'), ('COMPLETED'), ('REJECTED') ON CONFLICT (status_name) DO NOTHING;"))

                # --- Populate Default & Alias Data (unchanged) ---
                connection.execute(text("INSERT INTO warehouses (name) VALUES (:name) ON CONFLICT (name) DO NOTHING;"),
                                   [{"name": "WH1"}, {"name": "WH2"}, {"name": "WH3"}, {"name": "WH4"},
                                    {"name": "WH5"}])
                connection.execute(text(
                    "INSERT INTO users (username, password, role) VALUES (:user, :pwd, :role) ON CONFLICT (username) DO NOTHING;"),
                    [{"user": "admin", "pwd": "itadmin", "role": "Admin"},
                     {"user": "itsup", "pwd": "itsup", "role": "Editor"}])

                alias_data = [
                    {'product_code': 'OA14430E', 'alias_code': 'PL00X814MB',
                     'description': 'MASTERBATCH ORANGE OA14430E', 'extra_description': 'MASTERBATCH ORANGE OA14430E'},
                    {'product_code': 'TA14363E', 'alias_code': 'PL00X816MB', 'description': 'MASTERBATCH GRAY TA14363E',
                     'extra_description': 'MASTERBATCH GRAY TA14363E'},
                    {'product_code': 'GA14433E', 'alias_code': 'PL00X818MB',
                     'description': 'MASTERBATCH GREEN GA14433E', 'extra_description': 'MASTERBATCH GREEN GA14433E'},
                    {'product_code': 'BA14432E', 'alias_code': 'PL00X822MB', 'description': 'MASTERBATCH BLUE BA14432E',
                     'extra_description': 'MASTERBATCH BLUE BA14432E'},
                    {'product_code': 'YA14431E', 'alias_code': 'PL00X620MB',
                     'description': 'MASTERBATCH YELLOW YA14431E', 'extra_description': 'MASTERBATCH YELLOW YA14431E'},
                    {'product_code': 'WA14429E', 'alias_code': 'PL00X800MB',
                     'description': 'MASTERBATCH WHITE WA14429E', 'extra_description': 'MASTERBATCH WHITE WA14429E'},
                    {'product_code': 'WA12282E', 'alias_code': 'RITESEAL88', 'description': 'WHITE(CODE: WA12282E)',
                     'extra_description': ''},
                    {'product_code': 'BA12556E', 'alias_code': 'RITESEAL88', 'description': 'BLUE(CODE: BA12556E)',
                     'extra_description': ''},
                    {'product_code': 'WA15151E', 'alias_code': 'RITESEAL88', 'description': 'NATURAL(CODE: WA15151E)',
                     'extra_description': ''},
                    {'product_code': 'WA7997E', 'alias_code': 'RITESEAL88', 'description': 'NATURAL(CODE: WA7997E)',
                     'extra_description': ''},
                    {'product_code': 'WA15229E', 'alias_code': 'RITESEAL88', 'description': 'NATURAL(CODE: WA15229E)',
                     'extra_description': ''},
                    {'product_code': 'WA15218E', 'alias_code': 'RITESEAL88', 'description': 'NATURAL(CODE: WA15229E)',
                     'extra_description': ''},
                    {'product_code': 'AD-17248E', 'alias_code': 'L-4',
                     'description': 'DISPERSING AGENT(CODE: AD-17248E)', 'extra_description': ''},
                    {'product_code': 'DU-W17246E', 'alias_code': 'R104', 'description': '(CODE: DU-W17246E)',
                     'extra_description': ''},
                    {'product_code': 'DU-W16441E', 'alias_code': 'R104', 'description': '(CODE: DU-W16441E)',
                     'extra_description': ''},
                    {'product_code': 'DU-LL16541E', 'alias_code': 'LLPDE', 'description': '(CODE: DU-LL16541E)',
                     'extra_description': ''},
                    {'product_code': 'BA17070E', 'alias_code': 'RITESEAL88', 'description': 'BLUE(CODE: BA17070E)',
                     'extra_description': ''}
                ]

                connection.execute(text("""
                    INSERT INTO product_aliases (product_code, alias_code, description, extra_description)
                    VALUES (:product_code, :alias_code, :description, :extra_description)
                    ON CONFLICT (product_code) DO UPDATE SET
                        alias_code = EXCLUDED.alias_code,
                        description = EXCLUDED.description,
                        extra_description = EXCLUDED.extra_description;
                """), alias_data)

                customer_data = [
                    {"name": "ZELLER PLASTIK PHILIPPINES, INC.", "deliver_to": "ZELLER PLASTIK PHILIPPINES, INC.",
                     "address": "Bldg. 3 Philcrest Cmpd. km. 23 West Service Rd.\nCupang, Muntinlupa City"},
                    {"name": "TERUMO (PHILS.) CORPORATION", "deliver_to": "TERUMO (PHILS.) CORPORATION",
                     "address": "Barangay Saimsim, Calamba City, Laguna"},
                    {"name": "EVEREST PLASTIC CONTAINERS IND., I", "deliver_to": "EVEREST PLASTI CCONTAINERS IND., I",
                     "address": "Canumay, Valenzuela City"}]
                connection.execute(text(
                    "INSERT INTO customers (name, deliver_to, address) VALUES (:name, :deliver_to, :address) ON CONFLICT (name) DO NOTHING;"),
                    customer_data)
        print("Database initialized successfully.")
    except Exception as e:
        QApplication(sys.argv)
        QMessageBox.critical(None, "DB Init Error", f"Could not initialize database: {e}")
        sys.exit(1)


class LoginWindow(QMainWindow):
    login_successful = pyqtSignal(str, str)

    def __init__(self):
        super().__init__();
        self.setObjectName("LoginWindow");
        self.setupUi()

    def setupUi(self):
        # --- ICON COLOR DEFINITION ---
        NEW_ICON_COLOR = "#3a506b"
        # -----------------------------

        self.setWindowTitle("Finished Goods Program - Login");
        # FIX 1: Set window icon color to the new specified color
        self.setWindowIcon(IconProvider.get_icon(IconProvider.APP_ICON, color=NEW_ICON_COLOR));
        self.resize(500, 650)
        widget = QWidget();
        self.setCentralWidget(widget);
        main_layout = QHBoxLayout(widget);
        main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        frame = QFrame(objectName="FormFrame");
        frame.setMaximumWidth(400);
        main_layout.addWidget(frame)
        layout = QVBoxLayout(frame);
        layout.setContentsMargins(40, 30, 40, 30);
        layout.setSpacing(15);
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # FIX 2: Use the new icon color for the main login icon
        pixmap = IconProvider.get_pixmap(IconProvider.LOGIN_FORM_ICON, NEW_ICON_COLOR, QSize(150, 150))
        layout.addWidget(QLabel(pixmap=pixmap), alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addSpacing(10);

        # 1. Main Title
        layout.addWidget(
            QLabel("Finished Goods Login", objectName="LoginTitle", alignment=Qt.AlignmentFlag.AlignCenter));

        # FIX 4: Add Instruction Label
        instruction_label = QLabel("Please use your registered system credentials to access the application.",
                                   alignment=Qt.AlignmentFlag.AlignCenter)
        # Use a soft gray color for instruction text
        instruction_label.setStyleSheet("font-size: 7.5pt; color: #6c757d; font-weight: 500;")
        layout.addWidget(instruction_label)

        layout.addSpacing(25)

        # Input fields rely on the stylesheet rule #InputFrame QLabel { color: ... }
        self.username_widget, self.username = self._create_input_field(IconProvider.USERNAME, "Username")
        self.password_widget, self.password = self._create_input_field(IconProvider.PASSWORD, "Password")

        self.password.setEchoMode(QLineEdit.EchoMode.Password);
        layout.addWidget(self.username_widget);
        layout.addWidget(self.password_widget);
        layout.addSpacing(15)
        self.login_btn = QPushButton("Login", objectName="PrimaryButton", shortcut="Return", clicked=self.login);
        self.login_btn.setMinimumHeight(45);
        layout.addWidget(self.login_btn)
        self.status_label = QLabel("", objectName="StatusLabel", alignment=Qt.AlignmentFlag.AlignCenter);
        layout.addWidget(self.status_label);
        layout.addStretch()
        self.setStyleSheet(AppStyles.LOGIN_STYLESHEET)

    def _create_input_field(self, icon_name, placeholder):
        c = QWidget(objectName="InputFrame");
        l = QHBoxLayout(c);
        l.setContentsMargins(10, 0, 5, 0);
        l.setSpacing(10)

        # FIX 3: Pass the new icon color explicitly for input field icons
        NEW_ICON_COLOR = "#3a506b"
        pixmap = IconProvider.get_pixmap(icon_name, NEW_ICON_COLOR, QSize(20, 20))
        il = QLabel(pixmap=pixmap);

        le = QLineEdit(placeholderText=placeholder)
        l.addWidget(il);
        l.addWidget(le);
        return c, le

    def login(self):
        u, p = self.username.text(), self.password.text()
        if not u or not p: self.status_label.setText("Username and password are required."); return
        self.login_btn.setEnabled(False);
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
                        self.login_successful.emit(u, res[2]);
                        self.close()
                    else:
                        self.status_label.setText("Invalid credentials.")
        except Exception as e:
            self.status_label.setText("Database connection error.");
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


# --- MODIFIED: ModernMainWindow with Header Bar implementation ---
class ModernMainWindow(QMainWindow):
    EXPANDED_MENU_WIDTH = 230
    COLLAPSED_MENU_WIDTH = 60

    def __init__(self, username, user_role, login_window):
        super().__init__()
        self.username, self.user_role, self.login_window = username, user_role, login_window

        # Define the dark color for header icons/text
        self.DARK_HEADER_ICON_COLOR = AppStyles.LIGHT_TEXT_COLOR  # #333333

        # Icons (QIcon objects) for maximize/restore now use the dark color
        self.icon_maximize_obj = IconProvider.get_icon(IconProvider.MAXIMIZE, color=self.DARK_HEADER_ICON_COLOR)
        self.icon_restore_obj = IconProvider.get_icon(IconProvider.RESTORE, color=self.DARK_HEADER_ICON_COLOR)

        # Flag used to manage the clean logout flow and bypass the prompt in closeEvent
        self._is_logging_out = False

        self.setWindowTitle("MASTERBATCH PHILIPPINES INC. | MBPI-SYSTEM-2025 VERSION: 100125-1.0.1 | IT DEPARTMENT")
        self.setWindowIcon(IconProvider.get_icon(IconProvider.WINDOW_ICON, color='gray'))
        self.setMinimumSize(1280, 720)
        self.setGeometry(100, 100, 1366, 768)
        self.workstation_info = self._get_workstation_info()
        self.sync_thread, self.sync_worker = None, None
        self.customer_sync_thread, self.customer_sync_worker = None, None
        self.delivery_sync_thread, self.delivery_sync_worker = None, None
        self.rrf_sync_thread, self.rrf_sync_worker = None, None
        self.is_menu_expanded = True

        screen = QApplication.primaryScreen()
        self.screen_height = screen.geometry().height()

        # Initialize maximize button as None temporarily, will be instantiated in create_header_bar
        self.btn_maximize = None

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

    def _calculate_dynamic_font_size(self):
        """
        Calculates a smaller font size for the side menu based on screen resolution.
        """
        if self.screen_height <= 768:
            return 8
        elif self.screen_height <= 1080:
            return 9
        elif self.screen_height <= 1440:
            return 10
        else:
            return 11

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

        # --- Content Area Layout (Header + Stacked Widget) ---
        content_area = QWidget()
        content_vlayout = QVBoxLayout(content_area)
        content_vlayout.setContentsMargins(0, 0, 0, 0)
        content_vlayout.setSpacing(0)

        # 1. Create and add Header Bar
        self.header_bar = self.create_header_bar()
        content_vlayout.addWidget(self.header_bar)

        # 2. Add Stacked Widget below the header
        self.stacked_widget = QStackedWidget()
        content_vlayout.addWidget(self.stacked_widget)

        main_layout.addWidget(content_area)
        # --- END LAYOUT ---

        # Page Instantiations
        # --- DASHBOARD MODIFICATION (New Index 0) ---
        self.dashboard_page = DashboardPage(engine, self.username, self.log_audit_trail)
        # --------------------------------------------
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
        self.good_inventory_page = GoodInventoryPage(engine, self.username, self.log_audit_trail)
        self.failed_inventory_report_page = FailedInventoryReportPage(engine, self.username, self.log_audit_trail)
        self.audit_trail_page = AuditTrailPage(engine)
        self.user_management_page = UserManagementPage(engine, self.username, self.log_audit_trail)

        # Add pages to Stacked Widget (Adjusted Indices)
        pages = [
            # --- DASHBOARD MODIFICATION (Index 0) ---
            self.dashboard_page,  # 0
            # ----------------------------------------
            self.fg_endorsement_page,  # 1
            self.transactions_page,  # 2
            self.failed_transactions_page,  # 3
            self.good_inventory_page,  # 4
            self.failed_inventory_report_page,  # 5
            self.outgoing_form_page,  # 6
            self.rrf_page,  # 7
            self.receiving_report_page,  # 8
            self.qc_failed_passed_page,  # 9
            self.qc_excess_page,  # 10
            self.qc_failed_endorsement_page,  # 11
            self.product_delivery_page,  # 12
            self.requisition_logbook_page,  # 13
            self.audit_trail_page,  # 14
            self.user_management_page  # 15
        ]
        for page in pages: self.stacked_widget.addWidget(page)

        self.setCentralWidget(main_widget)
        self.setup_status_bar()
        self.apply_styles()

        # Check Admin access for the sidebar button
        if self.user_role != 'Admin' and hasattr(self, 'btn_user_mgmt_sidebar'):
            self.btn_user_mgmt_sidebar.hide()

        # Update maximize state immediately after the button is created in create_header_bar
        self.update_maximize_button()

        # --- DASHBOARD MODIFICATION (Set Dashboard as startup page) ---
        self.show_page(0);
        self.btn_dashboard.setChecked(True)
        # -------------------------------------------------------------

    def create_header_button(self, text, icon_name, on_click_func, initial_icon=None):
        """Helper function for buttons in the header bar, using dark icons."""

        # Determine the icon to use
        if initial_icon:
            icon = initial_icon
        else:
            icon = IconProvider.get_icon(icon_name, color=self.DARK_HEADER_ICON_COLOR)

        btn = QPushButton(text, icon=icon)
        btn.setIconSize(QSize(16, 16))
        btn.clicked.connect(on_click_func)
        return btn

    def create_header_bar(self):
        header = QFrame()
        header.setObjectName("HeaderBar")

        h_layout = QHBoxLayout(header)
        # Reduced vertical margins for a smaller header bar (2 pixels top/bottom)
        h_layout.setContentsMargins(10, 2, 10, 2)
        h_layout.setSpacing(10)
        h_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Application Title
        title_label = QLabel("")
        h_layout.addWidget(title_label)

        h_layout.addStretch(1)  # Push buttons to the right

        # 1. User Management Button (Navigates to page 15)
        self.btn_user_mgmt_header = self.create_header_button(
            "User Management", IconProvider.USER_MANAGEMENT, self.show_user_management
        )
        if self.user_role != 'Admin':
            self.btn_user_mgmt_header.hide()
        h_layout.addWidget(self.btn_user_mgmt_header)

        # 2. Maximize/Restore Button (Instantiated here)
        self.btn_maximize = self.create_header_button(
            "Maximize",
            IconProvider.MAXIMIZE,
            self.toggle_maximize,
            initial_icon=self.icon_maximize_obj
        )
        h_layout.addWidget(self.btn_maximize)

        # 3. Logout Button
        self.btn_logout = self.create_header_button("Logout", IconProvider.LOGOUT, self.logout)
        h_layout.addWidget(self.btn_logout)

        # 4. Exit Button
        self.btn_exit = self.create_header_button("Exit", IconProvider.EXIT, self.exit_application)
        h_layout.addWidget(self.btn_exit)

        return header

    def create_side_menu(self):
        self.menu_buttons = []
        menu = QWidget(objectName="SideMenu")
        menu.setMinimumWidth(self.EXPANDED_MENU_WIDTH)
        layout = QVBoxLayout(menu)
        layout.setContentsMargins(5, 10, 5, 10)
        layout.setSpacing(3)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Ensure menu toggle icon is white (for dark menu)
        self.btn_toggle_menu = QPushButton(icon=IconProvider.get_icon(IconProvider.MENU_TOGGLE, color='#ecf0f1'))
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
        # Ensure profile icon is white (for dark menu)
        pixmap = IconProvider.get_pixmap(IconProvider.USER_PROFILE, '#ecf0f1', QSize(36, 36))
        pl.addWidget(QLabel(pixmap=pixmap))

        profile_text_layout = QVBoxLayout()
        profile_text_layout.setSpacing(0)
        self.profile_name_label = QLabel(f"{self.username}", objectName="ProfileName")
        self.profile_role_label = QLabel(f"{self.user_role}", objectName="ProfileRole")
        profile_text_layout.addWidget(self.profile_name_label)
        profile_text_layout.addWidget(self.profile_role_label)
        pl.addLayout(profile_text_layout)
        layout.addWidget(profile)
        layout.addSpacing(10)

        # Menu Buttons (Indices updated below)
        # --- DASHBOARD MODIFICATION (New Index 0) ---
        self.btn_dashboard = self.create_menu_button("  Dashboard", IconProvider.DESKTOP, 0)
        # --------------------------------------------
        self.btn_fg_endorsement = self.create_menu_button("  FG Endorsement", IconProvider.FG_ENDORSEMENT, 1)
        self.btn_transactions = self.create_menu_button("  FG Passed Log", IconProvider.TRANSACTIONS, 2)
        self.btn_failed_transactions = self.create_menu_button("  FG Failed Log", IconProvider.FAILED_TRANSACTIONS, 3)
        self.btn_good_inventory = self.create_menu_button("  FG Inventory Report (Good)", IconProvider.GOOD_INVENTORY,
                                                          4)
        self.btn_failed_inventory_report = self.create_menu_button("  FG Inventory Report (Failed)",
                                                                   IconProvider.FAILED_INVENTORY_REPORT, 5)
        self.btn_outgoing_form = self.create_menu_button("  Outgoing Form", IconProvider.OUTGOING_FORM, 6)
        self.btn_rrf = self.create_menu_button("  RRF Form", IconProvider.RRF_FORM, 7)
        self.btn_receiving_report = self.create_menu_button("  Receiving Report", IconProvider.RECEIVING_REPORT, 8)
        self.btn_qc_failed_passed = self.create_menu_button("  QC Failed->Passed", IconProvider.QC_PASSED, 9)
        self.btn_qc_excess = self.create_menu_button("  QC Excess", IconProvider.QC_EXCESS, 10)
        self.btn_qc_failed = self.create_menu_button("  QC Failed", IconProvider.QC_FAILED, 11)
        self.btn_product_delivery = self.create_menu_button("  Product Delivery", IconProvider.PRODUCT_DELIVERY, 12)
        self.btn_requisition_logbook = self.create_menu_button("  Requisition Logbook", IconProvider.REQUISITION, 13)

        # SYNC BUTTONS
        self.btn_sync_prod = self.create_menu_button("  Sync Production", IconProvider.SYNC, -1,
                                                     self.start_sync_process)
        self.btn_sync_customers = self.create_menu_button("  Sync Customers", IconProvider.CUSTOMERS, -1,
                                                          self.start_customer_sync_process)
        self.btn_sync_deliveries = self.create_menu_button("  Sync Deliveries", IconProvider.DELIVERIES, -1,
                                                           self.start_delivery_sync_process)
        self.btn_sync_rrf = self.create_menu_button("  Sync RRF", IconProvider.RRF_SYNC, -1,
                                                    self.start_rrf_sync_process)

        self.btn_audit_trail = self.create_menu_button("  Audit Trail", IconProvider.AUDIT_TRAIL, 14)
        self.btn_user_mgmt_sidebar = self.create_menu_button("  User Management", IconProvider.USER_MANAGEMENT, 15)

        # Add buttons to layout
        # --- DASHBOARD MODIFICATION (Add Dashboard first) ---
        layout.addWidget(self.btn_dashboard);
        # --------------------------------------------------
        layout.addWidget(self.btn_fg_endorsement);
        layout.addWidget(self.btn_transactions);
        layout.addWidget(self.btn_failed_transactions);
        layout.addWidget(self.btn_good_inventory);
        layout.addWidget(self.btn_failed_inventory_report);
        layout.addWidget(self.btn_outgoing_form);
        layout.addWidget(self.btn_rrf);
        layout.addWidget(self.btn_receiving_report);
        layout.addWidget(self.btn_qc_failed_passed);
        layout.addWidget(self.btn_qc_excess);
        layout.addWidget(self.btn_qc_failed);
        layout.addWidget(self.btn_product_delivery);
        layout.addWidget(self.btn_requisition_logbook)
        separator1 = QFrame();
        separator1.setFrameShape(QFrame.Shape.HLine);
        separator1.setFixedHeight(1);
        separator1.setStyleSheet("background-color: rgba(255, 255, 255, 0.2); margin: 8px 5px;");
        layout.addWidget(separator1)
        layout.addWidget(self.btn_sync_prod);
        layout.addWidget(self.btn_sync_customers);
        layout.addWidget(self.btn_sync_deliveries);
        layout.addWidget(self.btn_sync_rrf);
        separator2 = QFrame();
        separator2.setFrameShape(QFrame.Shape.HLine);
        separator2.setFixedHeight(1);
        separator2.setStyleSheet("background-color: rgba(255, 255, 255, 0.2); margin: 8px 5px;");
        layout.addWidget(separator2)
        layout.addWidget(self.btn_audit_trail);
        layout.addWidget(self.btn_user_mgmt_sidebar)
        layout.addStretch(1);

        return menu

    def create_menu_button(self, text, icon_name, page_index, on_click_func=None):
        # Default icon color for the dark menu is white/light gray
        btn = QPushButton(text, icon=IconProvider.get_icon(icon_name, color='#ecf0f1'))
        btn.setProperty("fullText", text)
        btn.setIconSize(QSize(20, 20))
        if page_index != -1:
            btn.setCheckable(True);
            btn.setAutoExclusive(True)
            btn.clicked.connect(lambda: self.show_page(page_index))
        elif on_click_func:
            btn.clicked.connect(on_click_func)
        self.menu_buttons.append(btn)
        return btn

    def toggle_side_menu(self):
        start_width = self.side_menu.width()
        end_width = self.COLLAPSED_MENU_WIDTH if self.is_menu_expanded else self.EXPANDED_MENU_WIDTH
        if self.is_menu_expanded:
            self.profile_name_label.setVisible(False);
            self.profile_role_label.setVisible(False)
            for button in self.menu_buttons: button.setText("")
        self.animation = QPropertyAnimation(self.side_menu, b"minimumWidth");
        self.animation.setDuration(300);
        self.animation.setStartValue(start_width);
        self.animation.setEndValue(end_width);
        self.animation.finished.connect(self.on_menu_animation_finished);
        self.animation.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def on_menu_animation_finished(self):
        self.is_menu_expanded = not self.is_menu_expanded
        if self.is_menu_expanded:
            self.profile_name_label.setVisible(True);
            self.profile_role_label.setVisible(True)
            for button in self.menu_buttons: button.setText(button.property("fullText"))

    def setup_status_bar(self):
        self.status_bar = QStatusBar();
        self.setStatusBar(self.status_bar);
        self.status_bar.showMessage(f"Ready | Logged in as: {self.username}")

        # NOTE: Network widget colors adjusted inside NetworkGraphWidget to fit dark theme
        if PSUTIL_AVAILABLE:
            self.network_widget = NetworkGraphWidget();
            self.status_bar.addPermanentWidget(self.network_widget)
            separator_net = QFrame();
            separator_net.setFrameShape(QFrame.Shape.VLine);
            separator_net.setFrameShadow(QFrame.Shadow.Sunken);
            self.status_bar.addPermanentWidget(separator_net)

        # Database Status Widget (Default light gray icon)
        self.db_status_widget = self.create_status_widget(IconProvider.DATABASE, "Connecting...", icon_color='#f8f9fa');
        self.status_bar.addPermanentWidget(self.db_status_widget)
        separator1 = QFrame();
        separator1.setFrameShape(QFrame.Shape.VLine);
        separator1.setFrameShadow(QFrame.Shadow.Sunken);
        self.status_bar.addPermanentWidget(separator1)

        # Workstation Widget (Default light gray icon)
        workstation_widget = self.create_status_widget(IconProvider.DESKTOP, self.workstation_info['h'],
                                                       icon_color='#f8f9fa');
        workstation_widget.setToolTip(
            f"IP Address: {self.workstation_info['i']}\nMAC Address: {self.workstation_info['m']}");
        self.status_bar.addPermanentWidget(workstation_widget)
        separator2 = QFrame();
        separator2.setFrameShape(QFrame.Shape.VLine);
        separator2.setFrameShadow(QFrame.Shadow.Sunken);
        self.status_bar.addPermanentWidget(separator2)

        # Time Widget (Default light gray icon)
        self.time_widget = self.create_status_widget(IconProvider.CLOCK, "", icon_color='#f8f9fa');
        self.status_bar.addPermanentWidget(self.time_widget)
        self.time_timer = QTimer(self, timeout=self.update_time);
        self.time_timer.start(1000);
        self.update_time()
        self.db_check_timer = QTimer(self, timeout=self.check_db_status);
        self.db_check_timer.start(5000);
        self.check_db_status()

    def create_status_widget(self, icon_name, initial_text, icon_color='#f8f9fa'):
        widget = QWidget();
        layout = QHBoxLayout(widget);
        layout.setContentsMargins(5, 0, 5, 0);
        layout.setSpacing(5)
        # Icons guaranteed via IconProvider
        icon_label = QLabel(pixmap=IconProvider.get_pixmap(icon_name, icon_color, QSize(12, 12)));
        text_label = QLabel(initial_text)
        layout.addWidget(icon_label);
        layout.addWidget(text_label)
        widget.icon_label = icon_label;
        widget.text_label = text_label
        return widget

    def update_sync_progress(self, percent):
        if hasattr(self,
                   'loading_dialog') and self.loading_dialog.isVisible(): self.loading_dialog.progress_label.setText(
            f"{percent}%")

    def _create_loading_dialog(self):
        dialog = QDialog(self);
        dialog.setModal(True);
        dialog.setWindowFlag(Qt.WindowType.FramelessWindowHint);
        dialog.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout = QVBoxLayout(dialog);
        frame = QFrame();
        frame.setStyleSheet("background-color: white; border-radius: 15px; padding: 20px;");
        frame_layout = QVBoxLayout(frame)
        loading_label = QLabel("Syncing...");
        loading_label.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold));
        message_label = QLabel("Processing records... Please wait.");
        message_label.setStyleSheet("font-size: 11pt;")
        progress_label = QLabel("0%");
        progress_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold));
        progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter);
        progress_label.setStyleSheet(f"color: {AppStyles.PRIMARY_ACCENT_COLOR};");
        dialog.progress_label = progress_label
        frame_layout.addWidget(loading_label, alignment=Qt.AlignmentFlag.AlignCenter);
        frame_layout.addWidget(message_label, alignment=Qt.AlignmentFlag.AlignCenter);
        frame_layout.addSpacing(10);
        frame_layout.addWidget(progress_label, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(frame);
        return dialog

    def start_sync_process(self):
        if QMessageBox.question(self, "Confirm Sync", "This will sync legacy production data. Proceed?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.No: return
        self.btn_sync_prod.setEnabled(False);
        self.loading_dialog = self._create_loading_dialog();
        self.sync_thread = QThread();
        self.sync_worker = SyncWorker();
        self.sync_worker.moveToThread(self.sync_thread);
        self.sync_thread.started.connect(self.sync_worker.run);
        self.sync_worker.progress.connect(self.update_sync_progress);
        self.sync_worker.finished.connect(self.on_sync_finished);
        self.sync_worker.finished.connect(self.sync_thread.quit);
        self.sync_worker.finished.connect(self.sync_worker.deleteLater);
        self.sync_thread.finished.connect(self.sync_thread.deleteLater);
        self.sync_thread.start();
        self.loading_dialog.exec()

    def start_customer_sync_process(self):
        if QMessageBox.question(self, "Confirm Sync", "This will sync legacy customer data. Proceed?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.No: return
        self.btn_sync_customers.setEnabled(False);
        self.loading_dialog = self._create_loading_dialog();
        self.customer_sync_thread = QThread();
        self.customer_sync_worker = SyncCustomerWorker();
        self.customer_sync_worker.moveToThread(self.customer_sync_thread);
        self.customer_sync_thread.started.connect(self.customer_sync_worker.run);
        self.customer_sync_worker.progress.connect(self.update_sync_progress);
        self.customer_sync_worker.finished.connect(self.on_customer_sync_finished);
        self.customer_sync_worker.finished.connect(self.customer_sync_thread.quit);
        self.customer_sync_worker.finished.connect(self.customer_sync_worker.deleteLater);
        self.customer_sync_thread.finished.connect(self.customer_sync_thread.deleteLater);
        self.customer_sync_thread.start();
        self.loading_dialog.exec()

    def start_delivery_sync_process(self):
        if QMessageBox.question(self, "Confirm Sync", "This will sync legacy delivery records. Proceed?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.No: return
        self.btn_sync_deliveries.setEnabled(False);
        self.loading_dialog = self._create_loading_dialog();
        self.delivery_sync_thread = QThread();
        self.delivery_sync_worker = SyncDeliveryWorker();
        self.delivery_sync_worker.moveToThread(self.delivery_sync_thread);
        self.delivery_sync_thread.started.connect(self.delivery_sync_worker.run);
        self.delivery_sync_worker.progress.connect(self.update_sync_progress);
        self.delivery_sync_worker.finished.connect(self.on_delivery_sync_finished);
        self.delivery_sync_worker.finished.connect(self.delivery_sync_thread.quit);
        self.delivery_sync_worker.finished.connect(self.delivery_sync_worker.deleteLater);
        self.delivery_sync_thread.finished.connect(self.delivery_sync_thread.deleteLater);
        self.delivery_sync_thread.start();
        self.loading_dialog.exec()

    def start_rrf_sync_process(self):
        if QMessageBox.question(self, "Confirm Sync", "This will sync legacy RRF records. Proceed?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.No: return
        self.btn_sync_rrf.setEnabled(False);
        self.loading_dialog = self._create_loading_dialog();
        self.rrf_sync_thread = QThread();
        self.rrf_sync_worker = SyncRRFWorker();
        self.rrf_sync_worker.moveToThread(self.rrf_sync_thread);
        self.rrf_sync_thread.started.connect(self.rrf_sync_worker.run);
        self.rrf_sync_worker.progress.connect(self.update_sync_progress);
        self.rrf_sync_worker.finished.connect(self.on_rrf_sync_finished);
        self.rrf_sync_worker.finished.connect(self.rrf_sync_thread.quit);
        self.rrf_sync_worker.finished.connect(self.rrf_sync_worker.deleteLater);
        self.rrf_sync_thread.finished.connect(self.rrf_sync_thread.deleteLater);
        self.rrf_sync_thread.start();
        self.loading_dialog.exec()

    def on_sync_finished(self, success, message):
        self.loading_dialog.close();
        self.btn_sync_prod.setEnabled(True);
        QMessageBox.information(self, "Sync Result",
                                message) if success else QMessageBox.critical(
            self, "Sync Result", message)

    def on_customer_sync_finished(self, success, message):
        self.loading_dialog.close();
        self.btn_sync_customers.setEnabled(True);
        QMessageBox.information(self,
                                "Sync Result",
                                message) if success else QMessageBox.critical(
            self, "Sync Result",
            message);
        self.product_delivery_page._load_combobox_data();
        self.rrf_page._load_combobox_data()

    def on_delivery_sync_finished(self, success, message):
        self.loading_dialog.close();
        self.btn_sync_deliveries.setEnabled(True);
        QMessageBox.information(self,
                                "Sync Result",
                                message) if success else QMessageBox.critical(
            self, "Sync Result", message);
        self.product_delivery_page._load_all_records()

    def on_rrf_sync_finished(self, success, message):
        self.loading_dialog.close();
        self.btn_sync_rrf.setEnabled(True);
        QMessageBox.information(self, "Sync Result",
                                message) if success else QMessageBox.critical(
            self, "Sync Result", message);
        self.rrf_page._load_all_records()

    def update_time(self):
        self.time_widget.text_label.setText(datetime.now().strftime('%b %d, %Y  %I:%M:%S %p'))

    def check_db_status(self):
        try:
            with engine.connect() as c:
                c.execute(text("SELECT 1"))
            # Icons guaranteed via IconProvider (Green success on dark background)
            self.db_status_widget.icon_label.setPixmap(
                IconProvider.get_pixmap(IconProvider.SUCCESS, AppStyles.SUCCESS_COLOR, QSize(12, 12)));
            self.db_status_widget.text_label.setText("DB Connected");
            self.db_status_widget.setToolTip("Database connection is stable.")
        except Exception as e:
            # Icons guaranteed via IconProvider (Red error on dark background)
            self.db_status_widget.icon_label.setPixmap(
                IconProvider.get_pixmap(IconProvider.ERROR, AppStyles.DESTRUCTIVE_COLOR, QSize(12, 12)));
            self.db_status_widget.text_label.setText("DB Disconnected");
            self.db_status_widget.setToolTip(f"Database connection failed.\nError: {e}")

    def apply_styles(self):
        dynamic_font_pt = self._calculate_dynamic_font_size()
        self.setStyleSheet(AppStyles.get_main_stylesheet(font_size_pt=dynamic_font_pt))

    def show_user_management(self):
        """Navigate to User Management page and ensure sidebar button is checked. Index 15."""
        user_mgmt_index = 15
        self.show_page(user_mgmt_index)
        if hasattr(self, 'btn_user_mgmt_sidebar'):
            self.btn_user_mgmt_sidebar.setChecked(True)

    def show_page(self, index):
        if self.stacked_widget.currentIndex() == index: return
        self.stacked_widget.setCurrentIndex(index)
        current_widget = self.stacked_widget.currentWidget()

        # Ensure that if we navigate away from User Management, the header button is unchecked
        if index != 15 and hasattr(self, 'btn_user_mgmt_sidebar') and self.btn_user_mgmt_sidebar.isChecked():
            self.btn_user_mgmt_sidebar.setChecked(False)

        if hasattr(current_widget, 'refresh_page'):
            current_widget.refresh_page()
        elif hasattr(current_widget, '_load_all_records'):
            current_widget._load_all_records()

    def toggle_maximize(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def update_maximize_button(self):
        """Updates the icon and text of the maximize button based on window state."""
        # Check if the button object exists before trying to update it (important for startup)
        if not self.btn_maximize:
            return

        # Use the stored QIcon objects (icon_maximize_obj, icon_restore_obj)
        if self.isMaximized():
            self.btn_maximize.setText("Restore");
            self.btn_maximize.setIcon(self.icon_restore_obj)
        else:
            self.btn_maximize.setText("Maximize");
            self.btn_maximize.setIcon(self.icon_maximize_obj)

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange: self.update_maximize_button()
        super().changeEvent(event)

    # --- START FIX: LOGOUT/CLOSE LOGIC ---
    def logout(self):
        """
        Handles the dedicated logout button click.
        Sets a flag to bypass the prompt in closeEvent for clean closure.
        """
        self._is_logging_out = True

        self.log_audit_trail("LOGOUT", "User logged out.")

        self.close()

        # Show login window immediately
        self.login_window.show()

    def exit_application(self):
        """Triggers the close event, which will handle the prompt."""
        self.close()

    def closeEvent(self, event):
        # Clean up threads
        for thread in [self.sync_thread, self.customer_sync_thread, self.delivery_sync_thread, self.rrf_sync_thread]:
            if thread and thread.isRunning(): thread.quit(); thread.wait()

        # FIX: Check if logout() was called (bypassing the dialog)
        if hasattr(self, '_is_logging_out') and self._is_logging_out:
            event.accept()
            # Clean up the flag
            del self._is_logging_out
            return

        # Handle close initiated by 'X' button or exit_application()
        action = self.prompt_on_close()

        if action == 'EXIT':
            # EXIT means quit the application entirely
            self.log_audit_trail("LOGOUT", "User exited application (via close dialog).")
            QApplication.instance().quit()
            event.accept()
        elif action == 'LOGOUT':
            # LOGOUT means show the login screen. We handle the transition and IGNORE the close event
            # to prevent the window handle from disappearing until the process terminates naturally.
            self.log_audit_trail("LOGOUT", "User logged out (via close dialog).")
            self.login_window.show()
            event.ignore()
        else:
            # CANCEL
            event.ignore()

    def prompt_on_close(self):
        """
        Presents the dialog and returns 'LOGOUT', 'EXIT', or 'CANCEL'.
        This method no longer calls self.logout() recursively.
        """
        dialog = QMessageBox(self);
        dialog.setWindowTitle("Confirm Action");
        dialog.setText("What would you like to do?");
        dialog.setIcon(QMessageBox.Icon.Question);
        dialog.setStandardButtons(QMessageBox.StandardButton.Cancel)

        logout_button = dialog.addButton("Logout", QMessageBox.ButtonRole.ActionRole);
        exit_button = dialog.addButton("Exit Application", QMessageBox.ButtonRole.DestructiveRole);

        dialog.exec()

        if dialog.clickedButton() == logout_button:
            return 'LOGOUT'
        elif dialog.clickedButton() == exit_button:
            return 'EXIT'
        else:
            return 'CANCEL'
    # --- END FIX: LOGOUT/CLOSE LOGIC ---


if __name__ == "__main__":
    app = QApplication(sys.argv)
    initialize_database()
    login_window = LoginWindow()
    main_window = None


    def on_login_success(username, user_role):
        global main_window
        login_window.hide()
        main_window = ModernMainWindow(username, user_role, login_window)
        main_window.showMaximized()
        main_window.toggle_side_menu()


    login_window.login_successful.connect(on_login_success)
    login_window.show()
    sys.exit(app.exec())