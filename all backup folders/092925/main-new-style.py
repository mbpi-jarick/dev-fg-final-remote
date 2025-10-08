import sys
import os
import re
from datetime import datetime
import socket
import uuid
import dbfread
import time
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
from PyQt6.QtGui import QFont, QMovie, QIcon, QPainter, QPen, QColor, QPainterPath

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
from user_management import UserManagementPage
from transactions_form import TransactionsFormPage
# --- IMPORT THE NEW FAILED TRANSACTIONS FORM ---
from failed_transactions_form import FailedTransactionsFormPage

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
    """
    A class to hold all the stylesheet strings for the application.
    This is a professional, clean light theme with a dark blue sidebar for contrast and branding.
    """
    # ==================================================================================
    # === COLOR PALETTE ===
    # ==================================================================================
    # --- Primary Accents (Used across both light and dark areas) ---
    PRIMARY_ACCENT_COLOR = "#3498db"      # A strong, clear blue for primary actions & selections
    PRIMARY_ACCENT_HOVER = "#2980b9"
    SECONDARY_ACCENT_COLOR = "#1abc9c"    # Teal/Green for secondary actions
    SECONDARY_ACCENT_HOVER = "#16a085"
    DESTRUCTIVE_COLOR = "#e74c3c"         # Red for destructive actions (delete, remove)
    DESTRUCTIVE_COLOR_HOVER = "#c0392b"

    # --- Light Theme Neutrals (For the main content area) ---
    BG_PRIMARY = "#f4f7fc"                # Very light cool gray for the main window background
    SURFACE_COLOR = "#ffffff"             # Pure white for content areas (cards, tables, etc.)
    TEXT_PRIMARY = "#212529"              # Very dark gray (near black) for high readability
    TEXT_SECONDARY = "#6c757d"            # Muted gray for labels, headers, etc.
    BORDER_COLOR = "#dee2e6"              # Light, subtle border for defining elements
    HEADER_BG = "#e9ecef"                 # Header background for tables, group boxes

    # --- Dark Sidebar Specific Colors ---
    SIDEBAR_BG = "#2c3e50"                # Deep Midnight Blue
    SIDEBAR_BG_HOVER = "#34495e"          # Slightly lighter blue for hover states
    SIDEBAR_TEXT_PRIMARY = "#ecf0f1"      # Soft off-white for primary sidebar text
    SIDEBAR_TEXT_SECONDARY = "#bdc3c7"    # Lighter gray for secondary sidebar text (profile role)
    SIDEBAR_BORDER_SEPARATOR = "#34495e"  # Border color that blends with the sidebar

    LOGIN_STYLESHEET = f"""
        #LoginWindow, #FormFrame {{ background-color: {BG_PRIMARY}; }}
        QWidget {{ font-family: "Segoe UI"; font-size: 11pt; color: {TEXT_PRIMARY}; }}
        #LoginTitle {{ font-size: 20pt; font-weight: bold; color: {TEXT_PRIMARY}; }}
        #InputFrame {{
            background-color: {SURFACE_COLOR}; border: 1px solid {BORDER_COLOR}; border-radius: 8px; padding: 5px;
        }}
        #InputFrame:focus-within {{ border: 2px solid {PRIMARY_ACCENT_COLOR}; }}
        QLineEdit {{ border: none; background-color: transparent; padding: 8px; font-size: 11pt; }}
        QPushButton#PrimaryButton {{
            background-color: {PRIMARY_ACCENT_COLOR}; color: white;
            border-radius: 8px; padding: 12px; font-weight: bold; font-size: 12pt; border: none;
        }}
        QPushButton#PrimaryButton:hover {{ background-color: {PRIMARY_ACCENT_HOVER}; }}
        QPushButton#PrimaryButton:pressed {{ transform: scale(0.98); }}
        #StatusLabel {{ color: {DESTRUCTIVE_COLOR}; font-size: 9pt; font-weight: bold; }}
    """
    MAIN_WINDOW_STYLESHEET = f"""
        QMainWindow, QStackedWidget > QWidget {{ background-color: {BG_PRIMARY}; }}
        QWidget {{
            font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
            font-size: 10pt; color: {TEXT_PRIMARY};
        }}

        /* ==================== SIDE MENU (Dark Theme) ==================== */
        QWidget#SideMenu {{
            background-color: {SIDEBAR_BG}; border-right: 1px solid {SIDEBAR_BORDER_SEPARATOR};
        }}
        #SideMenu #ProfileName, #SideMenu #ProfileRole, #SideMenu #MenuLabel {{ background: transparent; }}
        #SideMenu #ProfileName {{ color: {SIDEBAR_TEXT_PRIMARY}; font-weight: bold; font-size: 11pt; }}
        #SideMenu #ProfileRole {{ color: {SIDEBAR_TEXT_SECONDARY}; font-size: 9pt; }}
        #SideMenu #MenuLabel {{
            font-size: 9pt; font-weight: bold; text-transform: uppercase; color: #95a5a6; /* A slightly darker gray for labels */
            padding: 10px 10px 4px 15px; margin-top: 8px; border-top: 1px solid {SIDEBAR_BORDER_SEPARATOR};
        }}
        #SideMenu #MenuLabel:first-of-type {{ border-top: none; }}
        #SideMenu QPushButton {{
            border: none; color: {SIDEBAR_TEXT_PRIMARY}; background-color: transparent;
            text-align: left; padding: 10px 10px 10px 15px;
            border-radius: 5px; margin: 2px 5px;
        }}
        #SideMenu QPushButton:hover {{ background-color: {SIDEBAR_BG_HOVER}; }}
        #SideMenu QPushButton:checked {{
            background-color: {PRIMARY_ACCENT_COLOR}; color: white; font-weight: bold;
        }}

        /* ==================== CONTENT AREA (Light Theme) ==================== */
        QGroupBox {{
            border: 1px solid {BORDER_COLOR}; border-radius: 8px;
            margin-top: 12px; background-color: {SURFACE_COLOR};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin; subcontrol-position: top left;
            padding: 2px 10px; background-color: {HEADER_BG};
            border: 1px solid {BORDER_COLOR}; border-bottom: none;
            border-top-left-radius: 8px; border-top-right-radius: 8px;
            font-weight: bold; color: {TEXT_SECONDARY};
        }}
        QLineEdit, QComboBox, QDateEdit, QDateTimeEdit, QPlainTextEdit, QDoubleSpinBox, QTextEdit {{
            border: 1px solid {BORDER_COLOR}; padding: 8px; border-radius: 5px;
            background-color: {SURFACE_COLOR};
            selection-background-color: {PRIMARY_ACCENT_COLOR}; selection-color: white;
        }}
        QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QPlainTextEdit:focus, QDoubleSpinBox:focus, QTextEdit:focus {{
            border: 1px solid {PRIMARY_ACCENT_COLOR};
        }}
        QLineEdit[readOnly="true"] {{ background-color: {HEADER_BG}; color: {TEXT_SECONDARY}; }}

        /* ==================== BUTTONS (Light Theme) ==================== */
        QPushButton {{
            border: none; padding: 9px 18px; border-radius: 6px;
            font-weight: bold; color: white;
            background-color: {TEXT_SECONDARY};
        }}
        QPushButton:hover {{ background-color: #5a6268; }}
        QPushButton:pressed {{ transform: scale(0.98); }}
        QPushButton:disabled {{ background-color: {HEADER_BG}; color: {TEXT_SECONDARY}; border: 1px solid {BORDER_COLOR}; }}

        QPushButton#PrimaryButton, #save_btn {{ background-color: {PRIMARY_ACCENT_COLOR}; }}
        QPushButton#PrimaryButton:hover, #save_btn:hover {{ background-color: {PRIMARY_ACCENT_HOVER}; }}
        QPushButton#SecondaryButton, #update_btn, #preview_btn {{ background-color: {SECONDARY_ACCENT_COLOR}; }}
        QPushButton#SecondaryButton:hover, #update_btn:hover, #preview_btn:hover {{ background-color: {SECONDARY_ACCENT_HOVER}; }}
        QPushButton#delete_btn, QPushButton#remove_item_btn {{ background-color: {DESTRUCTIVE_COLOR}; }}
        QPushButton#delete_btn:hover, QPushButton#remove_item_btn:hover {{ background-color: {DESTRUCTIVE_COLOR_HOVER}; }}

        /* ==================== TABLE (Light Theme) ==================== */
        QTableWidget {{
            border: 1px solid {BORDER_COLOR}; background-color: {SURFACE_COLOR};
            selection-behavior: SelectRows; color: {TEXT_PRIMARY}; gridline-color: {BORDER_COLOR};
            alternate-background-color: #fafcfe;
        }}
        QHeaderView::section {{
            background-color: {HEADER_BG}; padding: 8px; border: none;
            border-bottom: 1px solid {BORDER_COLOR}; font-weight: bold; text-align: left;
            color: #4f4f4f;
        }}
        QTableWidget::item {{ border-bottom: 1px solid {BORDER_COLOR}; padding: 6px 8px; }}
        QTableWidget::item:hover {{ background-color: #e6f7ff; }}
        QTableWidget::item:selected {{ background-color: {PRIMARY_ACCENT_COLOR}; color: white; }}

        /* ==================== TABS (Light Theme) ==================== */
        QTabWidget::pane {{
            border: 1px solid {BORDER_COLOR}; border-radius: 8px;
            background-color: {SURFACE_COLOR}; padding: 10px; margin-top: -1px;
        }}
        QTabBar {{ qproperty-drawBase: 0; background-color: transparent; }}
        QTabBar::tab {{
            background-color: {HEADER_BG}; color: {TEXT_SECONDARY};
            padding: 10px 25px; border-top-left-radius: 8px; border-top-right-radius: 8px;
            border: 1px solid {BORDER_COLOR}; border-bottom: none;
            margin-right: 4px; font-weight: bold;
        }}
        QTabBar::tab:selected {{
            color: {PRIMARY_ACCENT_COLOR}; background-color: {SURFACE_COLOR};
            border-bottom-color: {SURFACE_COLOR}; margin-bottom: -1px;
        }}
        QTabBar::tab:hover:!selected {{ color: {PRIMARY_ACCENT_COLOR}; }}

        /* ==================== STATUS BAR (Light Theme) ==================== */
        QStatusBar {{
            background-color: {HEADER_BG}; color: {TEXT_SECONDARY};
            font-size: 9pt; border-top: 1px solid {BORDER_COLOR};
        }}
        QStatusBar::item {{ border: none; }}
        QStatusBar QLabel {{ color: {TEXT_SECONDARY}; background: transparent; padding: 0 4px; }}
    """


class NetworkGraphWidget(QWidget):
    # ... (This class is unchanged) ...
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
    # ... (This class is unchanged) ...
    finished = pyqtSignal(bool, str)

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
            if 'T_LOTNUM' not in dbf.field_names:
                self.finished.emit(False, "Sync Error: Required column 'T_LOTNUM' not found.")
                return

            recs = []
            for r in dbf.records:
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

            if not recs:
                self.finished.emit(True, "Sync Info: No new records found in DBF file to sync.")
                return

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

            final_msg = f"Production sync complete.\n{len(recs)} records processed."
            self.finished.emit(True, final_msg)

        except dbfread.DBFNotFound:
            self.finished.emit(False, f"File Not Found: Production DBF not found at:\n{PRODUCTION_DBF_PATH}")
        except Exception as e:
            trace_info = traceback.format_exc()
            print(f"PRODUCTION SYNC CRITICAL ERROR: {e}\n{trace_info}")
            self.finished.emit(False, f"An unexpected error occurred during production sync:\n{e}")


class SyncCustomerWorker(QObject):
    # ... (This class is unchanged) ...
    finished = pyqtSignal(bool, str)

    def run(self):
        try:
            dbf = dbfread.DBF(CUSTOMER_DBF_PATH, load=True, encoding='latin1')
            if 'T_CUSTOMER' not in dbf.field_names:
                self.finished.emit(False, "Sync Error: Required column 'T_CUSTOMER' not found in customer DBF.")
                return

            recs = []
            for r in dbf.records:
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

            if not recs:
                self.finished.emit(True, "Sync Info: No new customer records found to sync.")
                return

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
            self.finished.emit(True, f"Customer sync complete.\n{len(recs)} records processed.")
        except dbfread.DBFNotFound:
            self.finished.emit(False, f"File Not Found: Customer DBF not found at:\n{CUSTOMER_DBF_PATH}")
        except Exception as e:
            self.finished.emit(False, f"An unexpected error occurred during customer sync:\n{e}")


class SyncDeliveryWorker(QObject):
    # ... (This class is unchanged) ...
    finished = pyqtSignal(bool, str)

    def _get_safe_dr_num(self, dr_num_raw):
        if dr_num_raw is None: return None
        try:
            return str(int(float(dr_num_raw)))
        except (ValueError, TypeError):
            return None

    def _to_float(self, value, default=0.0):
        if value is None: return default
        try:
            return float(value)
        except (ValueError, TypeError):
            try:
                return float(str(value).strip()) if str(value).strip() else default
            except (ValueError, TypeError):
                return default

    def run(self):
        try:
            items_by_dr = {}
            with dbfread.DBF(DELIVERY_ITEMS_DBF_PATH, load=True, encoding='latin1') as dbf_items:
                for item_rec in dbf_items.records:
                    dr_num = self._get_safe_dr_num(item_rec.get('T_DRNUM'))
                    if not dr_num: continue
                    if dr_num not in items_by_dr: items_by_dr[dr_num] = []

                    # attachments logic is correct
                    attachments = "\n".join(
                        filter(None, [str(item_rec.get(f'T_DESC{i}', '')).strip() for i in range(1, 5)]))

                    # --- MODIFIED: Added all new columns with default values ---
                    items_by_dr[dr_num].append({
                        "dr_no": dr_num,
                        "quantity": self._to_float(item_rec.get('T_TOTALWT')),
                        "unit": str(item_rec.get('T_TOTALWTU', '')).strip(),
                        "product_code": str(item_rec.get('T_PRODCODE', '')).strip(),
                        "product_color": str(item_rec.get('T_PRODCOLO', '')).strip(),
                        "no_of_packing": self._to_float(item_rec.get('T_NUMPACKI')),
                        "weight_per_pack": self._to_float(item_rec.get('T_WTPERPAC')),
                        "lot_numbers": "",  # Keep this for compatibility if needed, though new columns are preferred
                        "attachments": attachments,
                        "unit_price": None,  # Default to NULL
                        "lot_no_1": None,  # Default to NULL
                        "lot_no_2": None,  # Default to NULL
                        "lot_no_3": None,  # Default to NULL
                        "mfg_date": None,  # Default to NULL
                        "alias_code": None,  # Default to NULL
                        "alias_desc": None  # Default to NULL
                    })

            primary_recs = []
            with dbfread.DBF(DELIVERY_DBF_PATH, load=True, encoding='latin1') as dbf_primary:
                for r in dbf_primary.records:
                    dr_num = self._get_safe_dr_num(r.get('T_DRNUM'))
                    if not dr_num: continue
                    address = (str(r.get('T_ADD1', '')).strip() + ' ' + str(r.get('T_ADD2', '')).strip()).strip()
                    primary_recs.append({
                        "dr_no": dr_num, "delivery_date": r.get('T_DRDATE'),
                        "customer_name": str(r.get('T_CUSTOMER', '')).strip(),
                        "deliver_to": str(r.get('T_DELTO', '')).strip(), "address": address,
                        "po_no": str(r.get('T_CPONUM', '')).strip(),
                        "order_form_no": str(r.get('T_ORDERNUM', '')).strip(),
                        "terms": str(r.get('T_REMARKS', '')).strip(),
                        "prepared_by": str(r.get('T_USERID', '')).strip(), "encoded_on": r.get('T_DENCODED'),
                        "is_deleted": bool(r.get('T_DELETED', False))
                    })

            if not primary_recs:
                self.finished.emit(True, "Sync Info: No new delivery records found to sync.");
                return

            with engine.connect() as conn:
                with conn.begin():
                    dr_numbers_to_sync = [rec['dr_no'] for rec in primary_recs]
                    conn.execute(text("DELETE FROM product_delivery_items WHERE dr_no = ANY(:dr_nos)"),
                                 {"dr_nos": dr_numbers_to_sync})
                    conn.execute(text("""
                        INSERT INTO product_delivery_primary (dr_no, delivery_date, customer_name, deliver_to, address, po_no, order_form_no, terms, prepared_by, encoded_on, is_deleted, edited_by, edited_on, encoded_by)
                        VALUES (:dr_no, :delivery_date, :customer_name, :deliver_to, :address, :po_no, :order_form_no, :terms, :prepared_by, :encoded_on, :is_deleted, 'DBF_SYNC', NOW(), :prepared_by)
                        ON CONFLICT (dr_no) DO UPDATE SET
                            delivery_date = EXCLUDED.delivery_date, customer_name = EXCLUDED.customer_name, deliver_to = EXCLUDED.deliver_to, address = EXCLUDED.address,
                            po_no = EXCLUDED.po_no, order_form_no = EXCLUDED.order_form_no, terms = EXCLUDED.terms, prepared_by = EXCLUDED.prepared_by,
                            encoded_on = EXCLUDED.encoded_on, is_deleted = EXCLUDED.is_deleted, edited_by = 'DBF_SYNC', edited_on = NOW()
                    """), primary_recs)
                    all_items_to_insert = [item for dr_num in dr_numbers_to_sync if dr_num in items_by_dr for item in
                                           items_by_dr[dr_num]]
                    if all_items_to_insert:
                        # --- MODIFIED: Updated INSERT statement to include all new columns ---
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

            self.finished.emit(True,
                               f"Delivery sync complete.\n{len(primary_recs)} primary records and {len(all_items_to_insert)} items processed.")
        except dbfread.DBFNotFound as e:
            self.finished.emit(False, f"File Not Found: A required delivery DBF file is missing.\nDetails: {e}")
        except Exception as e:
            trace_info = traceback.format_exc();
            print(f"DELIVERY SYNC CRITICAL ERROR: {e}\n{trace_info}")
            self.finished.emit(False,
                               f"An unexpected error occurred during delivery sync:\n{e}\n\nCheck console/logs for technical details.")


class SyncRRFWorker(QObject):
    # ... (This class is unchanged) ...
    finished = pyqtSignal(bool, str)

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
                for item_rec in dbf_items.records:
                    rrf_num = self._get_safe_rrf_num(item_rec.get('T_DRNUM'))
                    if not rrf_num: continue
                    if rrf_num not in items_by_rrf: items_by_rrf[rrf_num] = []

                    remarks = "\n".join(
                        filter(None, [str(item_rec.get(f'T_DESC{i}', '')).strip() for i in range(3, 5)]))

                    items_by_rrf[rrf_num].append({
                        "rrf_no": rrf_num,
                        "quantity": self._to_float(item_rec.get('T_TOTALWT')),
                        "unit": str(item_rec.get('T_TOTALWTU', '')).strip(),
                        "product_code": str(item_rec.get('T_PRODCODE', '')).strip(),
                        "lot_number": str(item_rec.get('T_DESC1', '')).strip(),
                        "reference_number": str(item_rec.get('T_DESC2', '')).strip(),
                        "remarks": remarks
                    })

            primary_recs = []
            with dbfread.DBF(RRF_PRIMARY_DBF_PATH, load=True, encoding='latin1') as dbf_primary:
                for r in dbf_primary.records:
                    rrf_num = self._get_safe_rrf_num(r.get('T_DRNUM'))
                    if not rrf_num: continue
                    primary_recs.append({
                        "rrf_no": rrf_num,
                        "rrf_date": r.get('T_DRDATE'),
                        "customer_name": str(r.get('T_CUSTOMER', '')).strip(),
                        "material_type": str(r.get('T_DELTO', '')).strip(),
                        "prepared_by": str(r.get('T_USERID', '')).strip(),
                        "is_deleted": bool(r.get('T_DELETED', False))
                    })

            if not primary_recs:
                self.finished.emit(True, "Sync Info: No new RRF records found to sync.");
                return

            with engine.connect() as conn:
                with conn.begin():
                    rrf_numbers_to_sync = [rec['rrf_no'] for rec in primary_recs]
                    conn.execute(text("DELETE FROM rrf_items WHERE rrf_no = ANY(:rrf_nos)"),
                                 {"rrf_nos": rrf_numbers_to_sync})

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

                    all_items_to_insert = [item for rrf_num in rrf_numbers_to_sync if rrf_num in items_by_rrf for item
                                           in items_by_rrf[rrf_num]]
                    if all_items_to_insert:
                        conn.execute(text("""
                            INSERT INTO rrf_items (rrf_no, quantity, unit, product_code, lot_number, reference_number, remarks)
                            VALUES (:rrf_no, :quantity, :unit, :product_code, :lot_number, :reference_number, :remarks)
                        """), all_items_to_insert)

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
    Initializes the database schema.
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
                connection.execute(text("CREATE INDEX IF NOT EXISTS idx_transactions_product_code ON transactions (product_code);"))
                connection.execute(text("CREATE INDEX IF NOT EXISTS idx_transactions_lot_number ON transactions (lot_number);"))
                connection.execute(text("CREATE INDEX IF NOT EXISTS idx_transactions_source_ref_no ON transactions (source_ref_no);")) # Index for faster lookups

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
                connection.execute(text("CREATE INDEX IF NOT EXISTS idx_failed_transactions_product_code ON failed_transactions (product_code);"))
                connection.execute(text("CREATE INDEX IF NOT EXISTS idx_failed_transactions_lot_number ON failed_transactions (lot_number);"))
                connection.execute(text("CREATE INDEX IF NOT EXISTS idx_failed_transactions_source_ref_no ON failed_transactions (source_ref_no);")) # Index for faster lookups


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
                connection.execute(text("""
                    CREATE TABLE IF NOT EXISTS customers (id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL, deliver_to TEXT, address TEXT, tin TEXT, terms TEXT, is_deleted BOOLEAN NOT NULL DEFAULT FALSE);
                """))
                connection.execute(
                    text("CREATE TABLE IF NOT EXISTS units (id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL);"))
                connection.execute(
                    text("INSERT INTO units (name) VALUES ('KG.'), ('PCS'), ('BOX') ON CONFLICT (name) DO NOTHING;"))

                # --- Table for special product descriptions (replaces hard-coded logic) ---
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
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS qce_bag_numbers (id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL);"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS qce_box_numbers (id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL);"))
                connection.execute(
                    text("CREATE TABLE IF NOT EXISTS qce_remarks (id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL);"))

                # --- FG Endorsement Tables ---
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS fg_endorsements_primary (id SERIAL PRIMARY KEY, system_ref_no TEXT NOT NULL UNIQUE, form_ref_no TEXT, date_endorsed DATE, category TEXT, product_code TEXT, lot_number TEXT, quantity_kg NUMERIC(15, 6), weight_per_lot NUMERIC(15, 6), bag_no TEXT, status TEXT, endorsed_by TEXT, remarks TEXT, location TEXT, encoded_by TEXT, encoded_on TIMESTAMP, edited_by TEXT, edited_on TIMESTAMP, is_deleted BOOLEAN NOT NULL DEFAULT FALSE);"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS fg_endorsements_secondary (id SERIAL PRIMARY KEY, system_ref_no TEXT, lot_number TEXT, quantity_kg NUMERIC(15, 6), product_code TEXT, status TEXT, bag_no TEXT, endorsed_by TEXT);"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS fg_endorsements_excess (id SERIAL PRIMARY KEY, system_ref_no TEXT, lot_number TEXT, quantity_kg NUMERIC(15, 6), product_code TEXT, status TEXT, bag_no TEXT, endorsed_by TEXT);"))

                # --- Receiving Report Tables ---
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS receiving_reports_primary (id SERIAL PRIMARY KEY, rr_no TEXT NOT NULL UNIQUE, receive_date DATE NOT NULL, receive_from TEXT, pull_out_form_no TEXT, received_by TEXT, reported_by TEXT, remarks TEXT, encoded_by TEXT, encoded_on TIMESTAMP, edited_by TEXT, edited_on TIMESTAMP, is_deleted BOOLEAN NOT NULL DEFAULT FALSE);"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS receiving_reports_items (id SERIAL PRIMARY KEY, rr_no TEXT NOT NULL, material_code TEXT, lot_no TEXT, quantity_kg NUMERIC(15, 6), status TEXT, location TEXT, remarks TEXT, FOREIGN KEY (rr_no) REFERENCES receiving_reports_primary (rr_no) ON DELETE CASCADE);"))

                # --- QC Endorsement Tables (Failed->Passed, Excess, Failed) ---
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

                # --- RRF & Product Delivery Tables ---
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS rrf_primary (id SERIAL PRIMARY KEY, rrf_no TEXT NOT NULL UNIQUE, rrf_date DATE, customer_name TEXT, material_type TEXT, prepared_by TEXT, encoded_by TEXT, encoded_on TIMESTAMP, edited_by TEXT, edited_on TIMESTAMP, is_deleted BOOLEAN NOT NULL DEFAULT FALSE);"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS rrf_items (id SERIAL PRIMARY KEY, rrf_no TEXT NOT NULL, quantity NUMERIC(15, 6), unit TEXT, product_code TEXT, lot_number TEXT, reference_number TEXT, remarks TEXT, FOREIGN KEY (rrf_no) REFERENCES rrf_primary (rrf_no) ON DELETE CASCADE);"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS rrf_lot_breakdown (id SERIAL PRIMARY KEY, rrf_no TEXT NOT NULL, item_id INTEGER, lot_number TEXT NOT NULL, quantity_kg NUMERIC(15, 6), FOREIGN KEY (rrf_no) REFERENCES rrf_primary (rrf_no) ON DELETE CASCADE);"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS product_delivery_primary (id SERIAL PRIMARY KEY, dr_no TEXT NOT NULL UNIQUE, delivery_date DATE, customer_name TEXT, deliver_to TEXT, address TEXT, po_no TEXT, order_form_no TEXT, fg_out_id TEXT, terms TEXT, prepared_by TEXT, encoded_by TEXT, encoded_on TIMESTAMP, edited_by TEXT, edited_on TIMESTAMP, is_deleted BOOLEAN NOT NULL DEFAULT FALSE, is_printed BOOLEAN NOT NULL DEFAULT FALSE);"))

                # --- MODIFIED: Update product_delivery_items table ---
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

                # --- Outgoing Form Tables ---
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
                connection.execute(text("""
                    CREATE TABLE IF NOT EXISTS outgoing_records_items (
                        id SERIAL PRIMARY KEY, primary_id INTEGER NOT NULL REFERENCES outgoing_records_primary(id) ON DELETE CASCADE,
                        prod_id TEXT, product_code TEXT, lot_used TEXT, quantity_required_kg NUMERIC(15, 6),
                        new_lot_details TEXT, status TEXT, box_number TEXT, remaining_quantity NUMERIC(15, 6), quantity_produced TEXT
                    );
                """))

                # --- Requisition Logbook Tables ---
                # --- MODIFIED: Added location and request_for columns ---
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

                # --- Populate Default & Alias Data ---
                connection.execute(text("INSERT INTO warehouses (name) VALUES (:name) ON CONFLICT (name) DO NOTHING;"),
                                   [{"name": "WH1"}, {"name": "WH2"}, {"name": "WH3"}, {"name": "WH4"}, {"name": "WH5"}]) # Added WH3, WH5
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
                    {"name": "EVEREST PLASTIC CONTAINERS IND., I", "deliver_to": "EVEREST PLASTIC CONTAINERS IND., I",
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
    # ... (This class is unchanged) ...
    login_successful = pyqtSignal(str, str)

    def __init__(self):
        super().__init__();
        self.setObjectName("LoginWindow");
        self.setupUi()

    def setupUi(self):
        self.setWindowTitle("Finished Goods Program - Login");
        self.setWindowIcon(fa.icon('fa5s.box-open', color=AppStyles.PRIMARY_ACCENT_COLOR));
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
        layout.addWidget(
            QLabel(pixmap=fa.icon('fa5s.boxes', color=AppStyles.PRIMARY_ACCENT_COLOR).pixmap(QSize(150, 150))),
            alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(10);
        layout.addWidget(
            QLabel("Finished Goods Login", objectName="LoginTitle", alignment=Qt.AlignmentFlag.AlignCenter));
        layout.addSpacing(25)
        self.username_widget, self.username = self._create_input_field('fa5s.user', "Username")
        self.password_widget, self.password = self._create_input_field('fa5s.lock', "Password")
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

    def _create_input_field(self, icon, placeholder):
        c = QWidget(objectName="InputFrame");
        l = QHBoxLayout(c);
        l.setContentsMargins(10, 0, 5, 0);
        l.setSpacing(10)
        il = QLabel(pixmap=fa.icon(icon, color='#bdbdbd').pixmap(QSize(20, 20)));
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


class ModernMainWindow(QMainWindow):
    # ... (This class is unchanged) ...
    EXPANDED_MENU_WIDTH = 230
    COLLAPSED_MENU_WIDTH = 60

    def __init__(self, username, user_role, login_window):
        super().__init__()
        self.username, self.user_role, self.login_window = username, user_role, login_window
        self.icon_maximize, self.icon_restore = fa.icon('fa5s.expand-arrows-alt', color='#ecf0f1'), fa.icon(
            'fa5s.compress-arrows-alt', color='#ecf0f1')
        self.setWindowTitle("Finished Goods Program");
        self.setWindowIcon(fa.icon('fa5s.check-double', color='gray'));
        self.setMinimumSize(1280, 720);
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
        main_widget = QWidget();
        main_layout = QHBoxLayout(main_widget);
        main_layout.setContentsMargins(0, 0, 0, 0);
        main_layout.setSpacing(0)

        self.side_menu = self.create_side_menu()
        main_layout.addWidget(self.side_menu)

        self.stacked_widget = QStackedWidget();
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
        # --- NEW: Instantiate the failed transactions page ---
        self.failed_transactions_page = FailedTransactionsFormPage(engine, self.username, self.log_audit_trail)
        self.audit_trail_page = AuditTrailPage(engine)
        self.user_management_page = UserManagementPage(engine, self.username, self.log_audit_trail)

        # Add pages to Stacked Widget in order
        pages = [
            self.fg_endorsement_page,       # 0
            self.transactions_page,         # 1
            self.failed_transactions_page,  # 2 <-- NEW PAGE
            self.outgoing_form_page,        # 3
            self.rrf_page,                  # 4
            self.receiving_report_page,     # 5
            self.qc_failed_passed_page,     # 6
            self.qc_excess_page,            # 7
            self.qc_failed_endorsement_page,# 8
            self.product_delivery_page,     # 9
            self.requisition_logbook_page,  # 10
            self.audit_trail_page,          # 11
            self.user_management_page       # 12
        ]
        for page in pages:
            self.stacked_widget.addWidget(page)

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
        # --- NEW: Add button for failed transactions ---
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

        # Add Buttons to Layout in the correct visual order
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

        separator1 = QFrame()
        separator1.setFrameShape(QFrame.Shape.HLine)
        separator1.setFixedHeight(1)
        separator1.setStyleSheet("background-color: #34495e; margin: 8px 5px;")
        layout.addWidget(separator1)

        layout.addWidget(self.btn_sync_prod);
        layout.addWidget(self.btn_sync_customers);
        layout.addWidget(self.btn_sync_deliveries);
        layout.addWidget(self.btn_sync_rrf);

        separator2 = QFrame()
        separator2.setFrameShape(QFrame.Shape.HLine)
        separator2.setFixedHeight(1)
        separator2.setStyleSheet("background-color: #34495e; margin: 8px 5px;")
        layout.addWidget(separator2)

        layout.addWidget(self.btn_audit_trail);
        layout.addWidget(self.btn_user_mgmt)

        layout.addStretch(1);
        layout.addWidget(self.btn_maximize);
        layout.addWidget(self.btn_logout)
        layout.addWidget(self.btn_exit)

        return menu

    def create_menu_button(self, text, icon, page_index, on_click_func=None):
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
        if self.is_menu_expanded:
            self.profile_name_label.setVisible(True)
            self.profile_role_label.setVisible(True)
            for button in self.menu_buttons:
                button.setText(button.property("fullText"))

    def create_status_widget(self, icon_name, initial_text, icon_color='#6c757d'):
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
        self.status_bar = QStatusBar();
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage(f"Ready | Logged in as: {self.username}")

        if PSUTIL_AVAILABLE:
            self.network_widget = NetworkGraphWidget()
            self.status_bar.addPermanentWidget(self.network_widget)
            separator_net = QFrame()
            separator_net.setFrameShape(QFrame.Shape.VLine)
            separator_net.setFrameShadow(QFrame.Shadow.Sunken)
            self.status_bar.addPermanentWidget(separator_net)

        self.db_status_widget = self.create_status_widget('fa5s.database', "Connecting...")
        self.status_bar.addPermanentWidget(self.db_status_widget)

        separator1 = QFrame()
        separator1.setFrameShape(QFrame.Shape.VLine)
        separator1.setFrameShadow(QFrame.Shadow.Sunken)
        self.status_bar.addPermanentWidget(separator1)

        workstation_widget = self.create_status_widget('fa5s.desktop', self.workstation_info['h'])
        workstation_widget.setToolTip(
            f"IP Address: {self.workstation_info['i']}\nMAC Address: {self.workstation_info['m']}")
        self.status_bar.addPermanentWidget(workstation_widget)

        separator2 = QFrame()
        separator2.setFrameShape(QFrame.Shape.VLine)
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

    def on_menu_animation_finished(self):
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
            QMessageBox.information(self, "Sync Result", message);
            self.status_bar.showMessage("Production DB synchronized.", 5000)
        else:
            QMessageBox.critical(self, "Sync Result", message);
            self.status_bar.showMessage("Sync failed.", 5000)

    def on_customer_sync_finished(self, success, message):
        self.loading_dialog.close();
        self.btn_sync_customers.setEnabled(True)
        if success:
            QMessageBox.information(self, "Sync Result", message);
            self.status_bar.showMessage("Customer DB synchronized.", 5000)
            if hasattr(self.product_delivery_page, '_load_combobox_data'):
                self.product_delivery_page._load_combobox_data()
            if hasattr(self.rrf_page, '_load_combobox_data'):
                self.rrf_page._load_combobox_data()
        else:
            QMessageBox.critical(self, "Sync Result", message);
            self.status_bar.showMessage("Customer sync failed.", 5000)

    def on_delivery_sync_finished(self, success, message):
        self.loading_dialog.close();
        self.btn_sync_deliveries.setEnabled(True)
        if success:
            QMessageBox.information(self, "Sync Result", message);
            self.status_bar.showMessage("Delivery records synchronized.", 5000)
            if self.stacked_widget.currentWidget() == self.product_delivery_page:
                self.product_delivery_page._load_all_records()
        else:
            QMessageBox.critical(self, "Sync Result", message);
            self.status_bar.showMessage("Delivery sync failed.", 5000)

    def on_rrf_sync_finished(self, success, message):
        self.loading_dialog.close();
        self.btn_sync_rrf.setEnabled(True)
        if success:
            QMessageBox.information(self, "Sync Result", message);
            self.status_bar.showMessage("RRF records synchronized.", 5000)
            if self.stacked_widget.currentWidget() == self.rrf_page:
                self.rrf_page._load_all_records()
        else:
            QMessageBox.critical(self, "Sync Result", message);
            self.status_bar.showMessage("RRF sync failed.", 5000)

    def update_time(self):
        self.time_widget.text_label.setText(datetime.now().strftime('%b %d, %Y  %I:%M:%S %p'))

    def check_db_status(self):
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            self.db_status_widget.icon_label.setPixmap(
                fa.icon('fa5s.check-circle', color='#28a745').pixmap(QSize(12, 12)))
            self.db_status_widget.text_label.setText("DB Connected")
            self.db_status_widget.setToolTip("Database connection is stable.")
        except Exception as e:
            self.db_status_widget.icon_label.setPixmap(
                fa.icon('fa5s.times-circle', color='#dc3545').pixmap(QSize(12, 12)))
            self.db_status_widget.text_label.setText("DB Disconnected")
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
        self.login_window.show()

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