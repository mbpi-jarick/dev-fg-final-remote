import sys
import os
import re
from datetime import datetime
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

from sqlalchemy import create_engine, text

try:
    import qtawesome as fa
except ImportError:
    print("FATAL ERROR: The 'qtawesome' library is required. Please install it using: pip install qtawesome")
    sys.exit(1)

from PyQt6.QtCore import (Qt, pyqtSignal, QSize, QEvent, QTimer, QThread, QObject, QPropertyAnimation, QRect)
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, QLineEdit, QPushButton,
                             QMessageBox, QVBoxLayout, QHBoxLayout, QStackedWidget,
                             QFrame, QStatusBar, QDialog)
from PyQt6.QtGui import QFont, QIcon, QPainter, QPen, QColor, QPainterPath

# --- All page imports ---
from fg_endorsement import FGEndorsementPage
from outgoing_form import OutgoingFormPage
from rrf import RRFPage
from receiving_report import ReceivingReportPage
from qc_failed_passed_endorsement import QCFailedPassedPage
from qc_excess_endorsement import QCExcessEndorsementPage
from qc_failed_endorsement import (
    QCFailedEndorsementPage)
from product_delivery import ProductDeliveryPage
from requisition_logbook import RequisitionLogbookPage
from audit_trail import AuditTrailPage
from Others.user_management import UserManagementPage
from transactions_form import TransactionsFormPage
from failed_transactions_form import FailedTransactionsFormPage

# --- NEW IMPORT: INVENTORY PAGES ---
from good_inventory_page import GoodInventoryPage
from failed_inventory_report import FailedInventoryReportPage  # <-- NEW IMPORT

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
    # --- MODIFIED: New blue color palette ---
    PRIMARY_ACCENT_COLOR = "#5DADE2"  # A lighter, clearer blue for highlights
    PRIMARY_ACCENT_HOVER = "#4E9DCE"  # A slightly darker version for hover
    SECONDARY_ACCENT_COLOR = "#f4a261"  # Sandy Brown/Orange (still a good complement to blue)
    SECONDARY_ACCENT_HOVER = "#e76f51"  # Burnt Sienna
    DESTRUCTIVE_COLOR = "#e63946"  # Red
    DESTRUCTIVE_COLOR_HOVER = "#d62828"
    NEUTRAL_COLOR = "#6c757d"  # Gray
    NEUTRAL_COLOR_HOVER = "#5a6268"

    # --- MODIFIED: New "Gradient Blue" for the side menu background ---
    SIDE_MENU_GRADIENT = "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2E86C1, stop:1 #154360);"

    LOGIN_STYLESHEET = f"""
        #LoginWindow, #FormFrame {{ background-color: #f4f7fc; }}
        QWidget {{ font-family: "Segoe UI"; font-size: 11pt; }}
        #LoginTitle {{ font-size: 20pt; font-weight: bold; color: #333; }}
        #InputFrame {{ background-color: #fff; border: 1px solid #d1d9e6; border-radius: 8px; padding: 5px; }}
        #InputFrame:focus-within {{ border: 2px solid {PRIMARY_ACCENT_COLOR}; }}
        QLineEdit {{ border: none; background-color: transparent; padding: 8px; font-size: 11pt;}}
        QPushButton#PrimaryButton {{
            background-color: {PRIMARY_ACCENT_COLOR};
            color: #fff;
            border-radius: 8px;
            padding: 12px;
            font-weight: bold;
            font-size: 12pt;
            border: none;
        }}
        QPushButton#PrimaryButton:hover {{ background-color: {PRIMARY_ACCENT_HOVER}; }}
        QPushButton#PrimaryButton:pressed {{ transform: scale(0.98); }}
        #StatusLabel {{ color: {DESTRUCTIVE_COLOR}; font-size: 9pt; font-weight: bold; }}
    """

    @staticmethod
    def get_main_stylesheet(font_size_pt: int = 9):  # Default changed to 9
        """
        Generates the main window stylesheet with a dynamic font size for the side menu.
        """
        profile_name_size = font_size_pt
        profile_role_size = font_size_pt - 1

        return f"""
        QMainWindow, QStackedWidget > QWidget {{
            background-color: #f4f7fc;
        }}
        QWidget {{
            font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
            font-size: 10pt;
            color: #333;
        }}
        /* === Side Menu Styling === */
        QWidget#SideMenu {{
            background-color: {AppStyles.SIDE_MENU_GRADIENT}; /* MODIFIED: Using blue gradient */
            color: #ecf0f1;
        }}
        #SideMenu QLabel {{ color: #ecf0f1; font-family: "Segoe UI"; background: transparent; }}

        /* Side menu buttons - updated for icons and dynamic font size */
        #SideMenu QPushButton {{
            background-color: transparent;
            color: #ecf0f1;
            border: none;
            padding: 10px 10px 10px 20px;
            text-align: left;
            font-size: {font_size_pt}pt; /* Dynamic font size is applied here */
            font-weight: normal;
            border-radius: 6px;
            qproperty-iconSize: 16px;
        }}
        #SideMenu QPushButton:hover {{ background-color: rgba(255, 255, 255, 0.1); }}
        #SideMenu QPushButton:checked {{
            background-color: {AppStyles.PRIMARY_ACCENT_COLOR}; /* MODIFIED: Using new accent blue */
            font-weight: bold;
            color: white;
        }}

        #SideMenu #ProfileName {{ font-weight: bold; font-size: {profile_name_size}pt; }}
        #SideMenu #ProfileRole {{ color: #bdc3c7; font-size: {profile_role_size}pt; }}

        /* === Main Content Area Widgets (Inherits new blue accent color) === */
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

        /* === Button Styling === */
        QPushButton {{
            border: none;
            padding: 9px 16px;
            border-radius: 6px;
            font-weight: bold;
            color: white;
            background-color: {AppStyles.NEUTRAL_COLOR};
            qproperty-iconSize: 16px;
        }}
        QPushButton:hover {{ background-color: {AppStyles.NEUTRAL_COLOR_HOVER}; opacity: 0.95; }}
        QPushButton:pressed {{ transform: scale(0.98); }}

        /* Primary Action Buttons (Light Blue) */
        QPushButton#PrimaryButton, #save_btn, #update_btn, #save_breakdown_btn, #scan_btn {{
            background-color: {AppStyles.PRIMARY_ACCENT_COLOR};
        }}
        QPushButton#PrimaryButton:hover, #save_btn:hover, #update_btn:hover, #save_breakdown_btn:hover, #scan_btn:hover {{
            background-color: {AppStyles.PRIMARY_ACCENT_HOVER};
        }}

        /* Destructive Action Buttons (Red) */
        #delete_btn, #remove_item_btn {{ background-color: {AppStyles.DESTRUCTIVE_COLOR}; }}
        #delete_btn:hover, #remove_item_btn:hover {{ background-color: {AppStyles.DESTRUCTIVE_COLOR_HOVER}; }}

        /* Secondary/Positive Action Buttons (Orange/Brown) */
        QPushButton#SecondaryButton, #print_btn, #preview_btn {{
            background-color: {AppStyles.SECONDARY_ACCENT_COLOR};
        }}
        QPushButton#SecondaryButton:hover, #print_btn:hover, #preview_btn:hover {{
            background-color: {AppStyles.SECONDARY_ACCENT_HOVER};
        }}

        /* === Other Styles (unchanged) === */
        QTableWidget {{ border: none; background-color: #ffffff; selection-behavior: SelectRows; color: #212529; }}
        QTableWidget::item {{ border-bottom: 1px solid #f4f7fc; padding: 10px; }}
        QTableWidget::item:selected {{ background-color: #e2e9ff; color: #212529; }}
        QHeaderView::section {{ background-color: #ffffff; color: #6c757d; padding: 8px; border: none; border-bottom: 2px solid #e0e5eb; font-weight: bold; text-align: left; }}
        QTabWidget::pane {{ border: 1px solid #e0e5eb; border-radius: 8px; background-color: #ffffff; padding: 10px; margin-top: -1px; }}
        QTabBar {{ qproperty-drawBase: 0; background-color: transparent; margin-bottom: 0px; }}
        QTabBar::tab {{ background-color: #e9eff7; color: {AppStyles.NEUTRAL_COLOR}; padding: 10px 25px; border-top-left-radius: 8px; border-top-right-radius: 8px; border: 1px solid #e0e5eb; border-bottom: none; margin-right: 4px; font-weight: bold; }}
        QTabBar::tab:selected {{ color: {AppStyles.PRIMARY_ACCENT_COLOR}; background-color: #ffffff; border: 1px solid #e0e5eb; border-bottom-color: #ffffff; margin-bottom: -1px; }}
        QTabBar::tab:hover {{ color: {AppStyles.PRIMARY_ACCENT_COLOR}; background-color: #f0f3f8; }}
        QTabBar::tab:selected:hover {{ background-color: #ffffff; }}
        QStatusBar {{ background-color: #e9ecef; color: #333; font-size: 9pt; padding: 2px 0px; }}
        QStatusBar::item {{ border: none; }}
        QStatusBar QLabel {{ color: #333; background: transparent; padding: 0 4px; }}
    """


class IconProvider:
    """
    A central provider for application icons, using the qtawesome library.
    This ensures all icons are consistent, scalable, and can be dynamically colored.
    """
    # Application & Window Icons
    APP_ICON = 'fa5s.box-open'
    WINDOW_ICON = 'fa5s.check-double'
    LOGIN_FORM_ICON = 'fa5s.boxes'

    # Common UI Icons
    MENU_TOGGLE = 'fa5s.bars'
    MAXIMIZE = 'fa5s.expand-arrows-alt'
    RESTORE = 'fa5s.compress-arrows-alt'
    DATABASE = 'fa5s.database'
    DESKTOP = 'fa5s.desktop'
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
    FAILED_INVENTORY_REPORT = 'fa5s.balance-scale-right'  # <-- ADDED ICON
    # -----------------------

    OUTGOING_FORM = 'fa5s.sign-out-alt'  # Reusing logout icon
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
    ERROR = 'fa5s.times-circle'  # Reusing QC_FAILED icon
    WARNING = 'fa5s.exclamation-triangle'  # Reusing FAILED_TRANSACTIONS icon

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
        """Formats speed in bytes pe r second to a human-readable string."""
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

        painter.setPen(QColor("#e67e22"))  # Orange for upload
        painter.drawText(QRect(5, 0, self.width() // 2 - 5, self.height()),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, upload_text)

        painter.setPen(QColor("#3498db"))  # Blue for download
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
        painter.setPen(QPen(QColor(230, 126, 34, 100), 1.5))  # Semi-transparent orange
        painter.drawPath(upload_path)

        # Draw download graph
        download_path = QPainterPath()
        download_path.moveTo(5, self.height() - 2 - (self.download_history[0] / max_speed * graph_area_height))
        for i, speed in enumerate(self.download_history):
            x = 5 + i * point_spacing
            y = self.height() - 2 - (speed / max_speed * graph_area_height)
            download_path.lineTo(x, y)
        painter.setPen(QPen(QColor(52, 152, 219, 100), 1.5))  # Semi-transparent blue
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

                # --- Dropdown/Helper Tables (unchanged) ---
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

                # --- QC Endorsement Tables (unchanged) ---
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS qcfp_endorsements_primary (id SERIAL PRIMARY KEY, system_ref_no TEXT NOT NULL UNIQUE, form_ref_no TEXT, endorsement_date DATE NOT NULL, product_code TEXT NOT NULL, lot_number TEXT NOT NULL, quantity_kg NUMERIC(15, 6), weight_per_lot NUMERIC(15, 6), endorsed_by TEXT, warehouse TEXT, received_by_name TEXT, received_date_time TIMESTAMP, encoded_by TEXT, encoded_on TIMESTAMP, edited_by TEXT, edited_on TIMESTAMP, is_deleted BOOLEAN NOT NULL DEFAULT FALSE);"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS qcfp_endorsements_secondary (id SERIAL PRIMARY KEY, system_ref_no TEXT NOT NULL, lot_number TEXT NOT NULL, quantity_kg NUMERIC(15, 6));"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS qcfp_endorsements_excess (id SERIAL PRIMARY KEY, system_ref_no TEXT NOT NULL, lot_number TEXT NOT NULL, quantity_kg NUMERIC(15, 6));"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS qce_endorsements_primary (id SERIAL PRIMARY KEY, system_ref_no TEXT NOT NULL UNIQUE, form_ref_no TEXT, product_code TEXT, lot_number TEXT, quantity_kg NUMERIC(15, 6), weight_per_lot NUMERIC(15, 6), status TEXT, bag_number TEXT, box_number TEXT, remarks TEXT, date_endorsed DATE, endorsed_by TEXT, date_received TIMESTAMP, received_by TEXT, encoded_by TEXT, encoded_on TIMESTAMP, edited_by TEXT, edited_on TIMESTAMP, is_deleted BOOLEAN NOT NULL DEFAULT FALSE);"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS qce_endorsements_secondary (id SERIAL PRIMARY KEY, system_ref_no TEXT NOT NULL, lot_number TEXT NOT NULL, quantity_kg NUMERIC(15, 6), bag_number TEXT, box_number TEXT, remarks TEXT);"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS qce_endorsements_excess (id SERIAL PRIMARY KEY, system_ref_no TEXT NOT NULL, lot_number TEXT NOT NULL, quantity_kg NUMERIC(15, 6), bag_number TEXT, box_number TEXT, remarks TEXT);"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS qcf_endorsements_primary (id SERIAL PRIMARY KEY, system_ref_no TEXT NOT NULL UNIQUE, form_ref_no TEXT, endorsement_date DATE NOT NULL, product_code TEXT NOT NULL, lot_number TEXT NOT NULL, quantity_kg NUMERIC(15, 6), weight_per_lot NUMERIC(15, 6), endorsed_by TEXT, warehouse TEXT, received_by_name TEXT, received_date_time TIMESTAMP, encoded_by TEXT, encoded_on TIMESTAMP, edited_by TEXT, edited_on TIMESTAMP, is_deleted BOOLEAN NOT NULL DEFAULT FALSE);"))
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

                # ... (inside initialize_database function, inside connection.begin() block)

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
                # ... (rest of the initialization)

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
        self.setWindowTitle("Finished Goods Program - Login");
        self.setWindowIcon(IconProvider.get_icon(IconProvider.APP_ICON, color=AppStyles.PRIMARY_ACCENT_COLOR));
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

        pixmap = IconProvider.get_pixmap(IconProvider.LOGIN_FORM_ICON, AppStyles.PRIMARY_ACCENT_COLOR, QSize(150, 150))
        layout.addWidget(QLabel(pixmap=pixmap), alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addSpacing(10);
        layout.addWidget(
            QLabel("Finished Goods Login", objectName="LoginTitle", alignment=Qt.AlignmentFlag.AlignCenter));
        layout.addSpacing(25)
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
        pixmap = IconProvider.get_pixmap(icon_name, '#bdbdbd', QSize(20, 20))
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


# --- MODIFIED: ModernMainWindow with dynamic font and color logic ---
class ModernMainWindow(QMainWindow):
    EXPANDED_MENU_WIDTH = 230  # Adjusted width for smaller fonts
    COLLAPSED_MENU_WIDTH = 60

    def __init__(self, username, user_role, login_window):
        super().__init__()
        self.username, self.user_role, self.login_window = username, user_role, login_window
        self.icon_maximize = IconProvider.get_icon(IconProvider.MAXIMIZE, color='#ecf0f1')
        self.icon_restore = IconProvider.get_icon(IconProvider.RESTORE, color='#ecf0f1')
        self.setWindowTitle("Finished Goods Program")
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

    # --- MODIFIED: Font sizes are now smaller ---
    def _calculate_dynamic_font_size(self):
        """
        Calculates a smaller font size for the side menu based on screen resolution.
        """
        if self.screen_height <= 768:
            return 8  # Extra compact size for low-res screens
        elif self.screen_height <= 1080:
            return 9  # Compact size for standard Full HD
        elif self.screen_height <= 1440:
            return 10  # Standard size for QHD
        else:
            return 11  # Clear size for 4K and above

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
        self.good_inventory_page = GoodInventoryPage(engine, self.username, self.log_audit_trail)

        # --- NEW PAGE INSTANTIATION ---
        self.failed_inventory_report_page = FailedInventoryReportPage(engine, self.username, self.log_audit_trail)

        self.audit_trail_page = AuditTrailPage(engine)
        self.user_management_page = UserManagementPage(engine, self.username, self.log_audit_trail)

        # Add pages to Stacked Widget (Adjusted Indices)
        pages = [
            self.fg_endorsement_page,  # 0
            self.transactions_page,  # 1
            self.failed_transactions_page,  # 2
            self.good_inventory_page,  # 3
            self.failed_inventory_report_page,  # 4 <-- NEW INDEX
            self.outgoing_form_page,  # 5 (was 4)
            self.rrf_page,  # 6 (was 5)
            self.receiving_report_page,  # 7 (was 6)
            self.qc_failed_passed_page,  # 8 (was 7)
            self.qc_excess_page,  # 9 (was 8)
            self.qc_failed_endorsement_page,  # 10 (was 9)
            self.product_delivery_page,  # 11 (was 10)
            self.requisition_logbook_page,  # 12 (was 11)
            self.audit_trail_page,  # 13 (was 12)
            self.user_management_page  # 14 (was 13)
        ]
        for page in pages: self.stacked_widget.addWidget(page)

        self.setCentralWidget(main_widget)
        self.setup_status_bar()
        self.apply_styles()
        if self.user_role != 'Admin': self.btn_user_mgmt.hide()
        self.update_maximize_button()
        self.show_page(0);
        self.btn_fg_endorsement.setChecked(True)

    def create_side_menu(self):
        self.menu_buttons = []
        menu = QWidget(objectName="SideMenu")
        menu.setMinimumWidth(self.EXPANDED_MENU_WIDTH)
        layout = QVBoxLayout(menu)
        layout.setContentsMargins(5, 10, 5, 10)
        layout.setSpacing(3)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

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

        # Menu Buttons (UPDATED INDICES)
        self.btn_fg_endorsement = self.create_menu_button("  FG Endorsement", IconProvider.FG_ENDORSEMENT, 0)
        self.btn_transactions = self.create_menu_button("  FG Passed Log", IconProvider.TRANSACTIONS, 1)
        self.btn_failed_transactions = self.create_menu_button("  FG Failed Log", IconProvider.FAILED_TRANSACTIONS, 2)
        self.btn_good_inventory = self.create_menu_button("  FG Inventory Report (Good)", IconProvider.GOOD_INVENTORY,
                                                          3)

        # --- NEW BUTTON (Index 4) ---
        self.btn_failed_inventory_report = self.create_menu_button("  FG Inventory Report (Failed)",
                                                                   IconProvider.FAILED_INVENTORY_REPORT, 4)

        # SHIFTED INDICES
        self.btn_outgoing_form = self.create_menu_button("  Outgoing Form", IconProvider.OUTGOING_FORM, 5)
        self.btn_rrf = self.create_menu_button("  RRF Form", IconProvider.RRF_FORM, 6)
        self.btn_receiving_report = self.create_menu_button("  Receiving Report", IconProvider.RECEIVING_REPORT, 7)
        self.btn_qc_failed_passed = self.create_menu_button("  QC Failed->Passed", IconProvider.QC_PASSED, 8)
        self.btn_qc_excess = self.create_menu_button("  QC Excess", IconProvider.QC_EXCESS, 9)
        self.btn_qc_failed = self.create_menu_button("  QC Failed", IconProvider.QC_FAILED, 10)
        self.btn_product_delivery = self.create_menu_button("  Product Delivery", IconProvider.PRODUCT_DELIVERY, 11)
        self.btn_requisition_logbook = self.create_menu_button("  Requisition Logbook", IconProvider.REQUISITION, 12)

        # SYNC BUTTONS (no index change)
        self.btn_sync_prod = self.create_menu_button("  Sync Production", IconProvider.SYNC, -1,
                                                     self.start_sync_process)
        self.btn_sync_customers = self.create_menu_button("  Sync Customers", IconProvider.CUSTOMERS, -1,
                                                          self.start_customer_sync_process)
        self.btn_sync_deliveries = self.create_menu_button("  Sync Deliveries", IconProvider.DELIVERIES, -1,
                                                           self.start_delivery_sync_process)
        self.btn_sync_rrf = self.create_menu_button("  Sync RRF", IconProvider.RRF_SYNC, -1,
                                                    self.start_rrf_sync_process)

        # SHIFTED INDICES
        self.btn_audit_trail = self.create_menu_button("  Audit Trail", IconProvider.AUDIT_TRAIL, 13)
        self.btn_user_mgmt = self.create_menu_button("  User Management", IconProvider.USER_MANAGEMENT, 14)

        self.btn_maximize = self.create_menu_button("  Maximize", IconProvider.MAXIMIZE, -1, self.toggle_maximize)
        self.btn_logout = self.create_menu_button("  Logout", IconProvider.LOGOUT, -1, self.logout)
        self.btn_exit = self.create_menu_button("  Exit", IconProvider.EXIT, -1, self.exit_application)

        # Add buttons to layout
        layout.addWidget(self.btn_fg_endorsement);
        layout.addWidget(self.btn_transactions);
        layout.addWidget(self.btn_failed_transactions);
        layout.addWidget(self.btn_good_inventory);
        layout.addWidget(self.btn_failed_inventory_report);  # <-- ADDED TO LAYOUT
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
        separator1.setStyleSheet("background-color: rgba(255,255,255,0.2); margin: 8px 5px;");
        layout.addWidget(separator1)
        layout.addWidget(self.btn_sync_prod);
        layout.addWidget(self.btn_sync_customers);
        layout.addWidget(self.btn_sync_deliveries);
        layout.addWidget(self.btn_sync_rrf);
        separator2 = QFrame();
        separator2.setFrameShape(QFrame.Shape.HLine);
        separator2.setFixedHeight(1);
        separator2.setStyleSheet("background-color: rgba(255,255,255,0.2); margin: 8px 5px;");
        layout.addWidget(separator2)
        layout.addWidget(self.btn_audit_trail);
        layout.addWidget(self.btn_user_mgmt)
        layout.addStretch(1);
        layout.addWidget(self.btn_maximize);
        layout.addWidget(self.btn_logout);
        layout.addWidget(self.btn_exit)
        return menu

    def create_menu_button(self, text, icon_name, page_index, on_click_func=None):
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
        if PSUTIL_AVAILABLE:
            self.network_widget = NetworkGraphWidget();
            self.status_bar.addPermanentWidget(self.network_widget)
            separator_net = QFrame();
            separator_net.setFrameShape(QFrame.Shape.VLine);
            separator_net.setFrameShadow(QFrame.Shadow.Sunken);
            self.status_bar.addPermanentWidget(separator_net)
        self.db_status_widget = self.create_status_widget(IconProvider.DATABASE, "Connecting...");
        self.status_bar.addPermanentWidget(self.db_status_widget)
        separator1 = QFrame();
        separator1.setFrameShape(QFrame.Shape.VLine);
        separator1.setFrameShadow(QFrame.Shadow.Sunken);
        self.status_bar.addPermanentWidget(separator1)
        workstation_widget = self.create_status_widget(IconProvider.DESKTOP, self.workstation_info['h']);
        workstation_widget.setToolTip(
            f"IP Address: {self.workstation_info['i']}\nMAC Address: {self.workstation_info['m']}");
        self.status_bar.addPermanentWidget(workstation_widget)
        separator2 = QFrame();
        separator2.setFrameShape(QFrame.Shape.VLine);
        separator2.setFrameShadow(QFrame.Shadow.Sunken);
        self.status_bar.addPermanentWidget(separator2)
        self.time_widget = self.create_status_widget(IconProvider.CLOCK, "");
        self.status_bar.addPermanentWidget(self.time_widget)
        self.time_timer = QTimer(self, timeout=self.update_time);
        self.time_timer.start(1000);
        self.update_time()
        self.db_check_timer = QTimer(self, timeout=self.check_db_status);
        self.db_check_timer.start(5000);
        self.check_db_status()

    def create_status_widget(self, icon_name, initial_text, icon_color='#6c757d'):
        widget = QWidget();
        layout = QHBoxLayout(widget);
        layout.setContentsMargins(5, 0, 5, 0);
        layout.setSpacing(5)
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
            self.db_status_widget.icon_label.setPixmap(
                IconProvider.get_pixmap(IconProvider.SUCCESS, '#28a745', QSize(12, 12)));
            self.db_status_widget.text_label.setText("DB Connected");
            self.db_status_widget.setToolTip("Database connection is stable.")
        except Exception as e:
            self.db_status_widget.icon_label.setPixmap(
                IconProvider.get_pixmap(IconProvider.ERROR, '#dc3545', QSize(12, 12)));
            self.db_status_widget.text_label.setText("DB Disconnected");
            self.db_status_widget.setToolTip(f"Database connection failed.\nError: {e}")

    def apply_styles(self):
        dynamic_font_pt = self._calculate_dynamic_font_size()
        self.setStyleSheet(AppStyles.get_main_stylesheet(font_size_pt=dynamic_font_pt))

    def show_page(self, index):
        if self.stacked_widget.currentIndex() == index: return
        self.stacked_widget.setCurrentIndex(index)
        current_widget = self.stacked_widget.currentWidget()
        if hasattr(current_widget, 'refresh_page'):
            current_widget.refresh_page()
        elif hasattr(current_widget, '_load_all_records'):
            current_widget._load_all_records()

    def toggle_maximize(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def update_maximize_button(self):
        if self.isMaximized():
            self.btn_maximize.setText("  Restore");
            self.btn_maximize.setIcon(self.icon_restore)
        else:
            self.btn_maximize.setText("  Maximize");
            self.btn_maximize.setIcon(self.icon_maximize)

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange: self.update_maximize_button()
        super().changeEvent(event)

    def logout(self):
        self.close();
        self.log_audit_trail("LOGOUT", "User logged out.");
        self.login_window.show()

    def exit_application(self):
        self.prompt_on_close()

    def closeEvent(self, event):
        for thread in [self.sync_thread, self.customer_sync_thread, self.delivery_sync_thread, self.rrf_sync_thread]:
            if thread and thread.isRunning(): thread.quit(); thread.wait()
        if self.prompt_on_close():
            event.accept()
        else:
            event.ignore()

    def prompt_on_close(self):
        dialog = QMessageBox(self);
        dialog.setWindowTitle("Confirm Action");
        dialog.setText("What would you like to do?");
        dialog.setIcon(QMessageBox.Icon.Question);
        dialog.setStandardButtons(QMessageBox.StandardButton.Cancel)
        logout_button = dialog.addButton("Logout", QMessageBox.ButtonRole.ActionRole);
        exit_button = dialog.addButton("Exit Application", QMessageBox.ButtonRole.DestructiveRole);
        dialog.exec()
        if dialog.clickedButton() == logout_button:
            self.logout();
            return False
        elif dialog.clickedButton() == exit_button:
            self.log_audit_trail("LOGOUT", "User exited application.");
            QApplication.instance().quit();
            return True
        else:
            return False


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