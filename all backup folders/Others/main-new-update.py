# =========================================================================================
# === FINISHED GOODS PROGRAM - CONSOLIDATED APPLICATION V1.1
# === FIX APPLIED: Corrected stylesheet to ensure visible text in all input fields.
# === ENHANCEMENT: Increased default font size for better readability.
# =========================================================================================

import sys
import os
import re
from datetime import datetime, date
import socket
import uuid
import dbfread
import time
import traceback
import collections
import math
from decimal import Decimal, InvalidOperation
from functools import partial

# --- Third-Party Library Imports ---
try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    print("WARNING: 'psutil' library not found. Network graph will be disabled. Install with: pip install psutil")
    PSUTIL_AVAILABLE = False

try:
    import qtawesome as fa
except ImportError:
    print("FATAL ERROR: The 'qtawesome' library is required. Please install it using: pip install qtawesome")
    sys.exit(1)

import fitz
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as ReportLabImage)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import qrcode
import io

# --- PyQt6 Imports ---
from PyQt6.QtCore import (Qt, pyqtSignal, QSize, QEvent, QTimer, QThread, QObject, QPropertyAnimation, QRect, QDate,
                          QDateTime, QSizeF, QRegularExpression)
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, QLineEdit, QPushButton,
                             QMessageBox, QVBoxLayout, QHBoxLayout, QStackedWidget,
                             QFrame, QStatusBar, QDialog, QTabWidget, QFormLayout,
                             QComboBox, QDateEdit, QTableWidget, QTableWidgetItem,
                             QAbstractItemView, QHeaderView, QGridLayout, QGroupBox, QMenu,
                             QSplitter, QCompleter, QDialogButtonBox, QPlainTextEdit,
                             QCheckBox, QInputDialog)
from PyQt6.QtGui import (QFont, QMovie, QIcon, QPainter, QPen, QColor, QPainterPath,
                         QDoubleValidator, QPageSize, QIntValidator, QImage,
                         QRegularExpressionValidator)
from PyQt6.QtPrintSupport import QPrinter, QPrintPreviewDialog

# --- Database Imports ---
from sqlalchemy import create_engine, text

# --- CONFIGURATION ---
DB_CONFIG = {"host": "192.168.1.13", "port": 5432, "dbname": "dbfg", "user": "postgres", "password": "mbpi"}
DBF_BASE_PATH = r'\\system-server\SYSTEM-NEW-OLD'
PRODUCTION_DBF_PATH = os.path.join(DBF_BASE_PATH, 'tbl_prod01.dbf')
CUSTOMER_DBF_PATH = os.path.join(DBF_BASE_PATH, 'tbl_customer01.dbf')
DELIVERY_DBF_PATH = os.path.join(DBF_BASE_PATH, 'tbl_del01.dbf')
DELIVERY_ITEMS_DBF_PATH = os.path.join(DBF_BASE_PATH, 'tbl_del02.dbf')
RRF_DBF_PATH = os.path.join(DBF_BASE_PATH, 'RRF')
RRF_PRIMARY_DBF_PATH = os.path.join(RRF_DBF_PATH, 'tbl_del01.dbf')
RRF_ITEMS_DBF_PATH = os.path.join(RRF_DBF_PATH, 'tbl_del02.dbf')

db_url = f"postgresql+psycopg2://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}"
engine = create_engine(db_url, pool_pre_ping=True, pool_recycle=3600)


# =========================================================================================
# === SHARED HELPER WIDGETS
# =========================================================================================
class UpperCaseLineEdit(QLineEdit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.textChanged.connect(self._to_upper)

    def _to_upper(self, text: str):
        self.blockSignals(True)
        self.setText(text.upper())
        self.blockSignals(False)


class FloatLineEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        validator = QDoubleValidator(0.0, 99999999.0, 6)
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        self.setValidator(validator)
        self.editingFinished.connect(self._format_text)
        self.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.setText("0.00")

    def _format_text(self):
        try:
            value = float(self.text() or 0.0)
            self.setText(f"{value:.2f}")
        except ValueError:
            self.setText("0.00")

    def value(self) -> float:
        return float(self.text() or 0.0)


# =========================================================================================
# === STYLING AND ICONS
# =========================================================================================
class AppStyles:
    PRIMARY_ACCENT_COLOR = "#4D7BFF"
    PRIMARY_ACCENT_HOVER = "#4066d4"
    SECONDARY_ACCENT_COLOR = "#2a9d8f"
    SECONDARY_ACCENT_HOVER = "#268d81"
    DESTRUCTIVE_COLOR = "#e63946"
    DESTRUCTIVE_COLOR_HOVER = "#d62828"
    NEUTRAL_COLOR = "#6c757d"
    NEUTRAL_COLOR_HOVER = "#5a6268"

    LOGIN_STYLESHEET = f"""
        #LoginWindow, #FormFrame {{ background-color: #f4f7fc; }}
        QWidget {{ font-family: "Segoe UI"; font-size: 11pt; }}
        #LoginTitle {{ font-size: 20pt; font-weight: bold; color: #333; }}
        #InputFrame {{ background-color: #fff; border: 1px solid #d1d9e6; border-radius: 8px; padding: 5px; }}
        #InputFrame:focus-within {{ border: 2px solid {PRIMARY_ACCENT_COLOR}; }}
        QLineEdit {{ border: none; background-color: transparent; padding: 8px; font-size: 11pt; color: #212529; }}
        QPushButton#PrimaryButton {{
            background-color: {PRIMARY_ACCENT_COLOR}; color: #fff; border-radius: 8px;
            padding: 12px; font-weight: bold; font-size: 12pt; border: none;
        }}
        QPushButton#PrimaryButton:hover {{ background-color: {PRIMARY_ACCENT_HOVER}; }}
        #StatusLabel {{ color: {DESTRUCTIVE_COLOR}; font-size: 9pt; font-weight: bold; }}
    """

    # --- === THE MAIN STYLESHEET FIX IS HERE === ---
    MAIN_WINDOW_STYLESHEET = f"""
        QMainWindow, QStackedWidget > QWidget {{ background-color: #f4f7fc; }}
        QWidget {{
            font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
            font-size: 10pt;
            color: #333;
        }}
        QWidget#SideMenu {{ background-color: #2c3e50; color: #ecf0f1; }}
        #SideMenu QLabel {{ color: #ecf0f1; font-family: "Segoe UI"; font-size: 9pt; background: transparent; }}
        #SideMenu QPushButton {{
            background-color: transparent; color: #ecf0f1; border: none; padding: 10px 10px 10px 20px;
            text-align: left; font-size: 10pt; border-radius: 6px; qproperty-iconSize: 16px;
        }}
        #SideMenu QPushButton:hover {{ background-color: #34495e; }}
        #SideMenu QPushButton:checked {{
            background-color: {PRIMARY_ACCENT_COLOR}; font-weight: bold; color: white;
        }}
        #SideMenu #ProfileName {{ font-weight: bold; font-size: 10pt; }}
        #SideMenu #ProfileRole {{ color: #bdc3c7; font-size: 9pt; }}
        QGroupBox {{
            border: 1px solid #e0e5eb; border-radius: 8px; margin-top: 12px; background-color: #ffffff;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin; subcontrol-position: top left; padding: 2px 10px;
            background-color: #f4f7fc; border: 1px solid #e0e5eb; border-bottom: 1px solid #ffffff;
            border-top-left-radius: 8px; border-top-right-radius: 8px; font-weight: bold; color: #4f4f4f;
        }}

        /* === FIX APPLIED HERE for visible text and larger font === */
        QLineEdit, QComboBox, QDateEdit, QDateTimeEdit, QPlainTextEdit, QDoubleSpinBox, QTextEdit {{
            border: 1px solid #d1d9e6; padding: 8px; border-radius: 5px;
            background-color: #ffffff;
            selection-background-color: #8eb3ff;
            color: #212529;
            font-size: 11pt;
        }}

        QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QPlainTextEdit:focus, QDoubleSpinBox:focus, QTextEdit:focus {{
            border: 1px solid {PRIMARY_ACCENT_COLOR};
        }}
        QLineEdit[readOnly="true"] {{ background-color: #eff2f7; color: #6c757d; }}
        QPushButton {{
            border: none; padding: 9px 16px; border-radius: 6px; font-weight: bold;
            color: white; background-color: {NEUTRAL_COLOR}; qproperty-iconSize: 16px;
        }}
        QPushButton:hover {{ background-color: {NEUTRAL_COLOR_HOVER}; }}
        QPushButton#PrimaryButton, #save_btn, #update_btn, #save_breakdown_btn, #scan_btn {{ background-color: {PRIMARY_ACCENT_COLOR}; }}
        QPushButton#PrimaryButton:hover, #save_btn:hover, #update_btn:hover, #save_breakdown_btn:hover, #scan_btn:hover {{ background-color: {PRIMARY_ACCENT_HOVER}; }}
        #delete_btn, #remove_item_btn {{ background-color: {DESTRUCTIVE_COLOR}; }}
        #delete_btn:hover, #remove_item_btn:hover {{ background-color: {DESTRUCTIVE_COLOR_HOVER}; }}
        QPushButton#SecondaryButton, #print_btn, #preview_btn {{ background-color: {SECONDARY_ACCENT_COLOR}; }}
        QPushButton#SecondaryButton:hover, #print_btn:hover, #preview_btn:hover {{ background-color: {SECONDARY_ACCENT_HOVER}; }}
        QTableWidget {{
            border: none; background-color: #ffffff; selection-behavior: SelectRows; color: #212529;
        }}
        QTableWidget::item {{ border-bottom: 1px solid #f4f7fc; padding: 10px; }}
        QTableWidget::item:selected {{ background-color: {PRIMARY_ACCENT_COLOR}; color: #ffffff; }}
        QHeaderView::section {{
            background-color: #ffffff; color: #6c757d; padding: 8px;
            border: none; border-bottom: 2px solid #e0e5eb; font-weight: bold;
        }}
        QTabWidget::pane {{
            border: 1px solid #e0e5eb; border-radius: 8px; background-color: #ffffff;
            padding: 10px; margin-top: -1px;
        }}
        QTabBar {{ qproperty-drawBase: 0; background-color: transparent; margin-bottom: 0px; }}
        QTabBar::tab {{
            background-color: #e9eff7; color: {NEUTRAL_COLOR}; padding: 10px 25px;
            border-top-left-radius: 8px; border-top-right-radius: 8px;
            border: 1px solid #e0e5eb; border-bottom: none; margin-right: 4px; font-weight: bold;
        }}
        QTabBar::tab:selected {{
            color: {PRIMARY_ACCENT_COLOR}; background-color: #ffffff;
            border-bottom-color: #ffffff; margin-bottom: -1px;
        }}
        QTabBar::tab:hover {{ color: {PRIMARY_ACCENT_COLOR}; background-color: #f0f3f8; }}
        QStatusBar {{ background-color: #e9ecef; color: #333; font-size: 9pt; padding: 2px 0px; }}
        QStatusBar::item {{ border: none; }}
        QStatusBar QLabel {{ color: #333; background: transparent; padding: 0 4px; }}
    """


class IconProvider:
    APP_ICON = 'fa5s.box-open';
    WINDOW_ICON = 'fa5s.check-double';
    LOGIN_FORM_ICON = 'fa5s.boxes'
    MENU_TOGGLE = 'fa5s.bars';
    MAXIMIZE = 'fa5s.expand-arrows-alt';
    RESTORE = 'fa5s.compress-arrows-alt'
    DATABASE = 'fa5s.database';
    DESKTOP = 'fa5s.desktop';
    CLOCK = 'fa5s.clock'
    USERNAME = 'fa5s.user';
    PASSWORD = 'fa5s.lock';
    USER_PROFILE = 'fa5s.user-circle'
    USER_MANAGEMENT = 'fa5s.users-cog';
    LOGOUT = 'fa5s.sign-out-alt';
    EXIT = 'fa5s.power-off'
    FG_ENDORSEMENT = 'fa5s.file-signature';
    TRANSACTIONS = 'fa5s.exchange-alt'
    FAILED_TRANSACTIONS = 'fa5s.exclamation-triangle';
    OUTGOING_FORM = 'fa5s.sign-out-alt'
    RRF_FORM = 'fa5s.undo-alt';
    RECEIVING_REPORT = 'fa5s.truck-loading';
    QC_PASSED = 'fa5s.flask'
    QC_EXCESS = 'fa5s.box';
    QC_FAILED = 'fa5s.times-circle';
    PRODUCT_DELIVERY = 'fa5s.truck'
    REQUISITION = 'fa5s.book';
    AUDIT_TRAIL = 'fa5s.clipboard-list';
    SYNC = 'fa5s.sync-alt'
    CUSTOMERS = 'fa5s.address-book';
    DELIVERIES = 'fa5s.history';
    RRF_SYNC = 'fa5s.retweet'
    SUCCESS = 'fa5s.check-circle';
    ERROR = 'fa5s.times-circle';
    WARNING = 'fa5s.exclamation-triangle'

    @staticmethod
    def get_icon(icon_name: str, color: str = "#333333") -> QIcon:
        return fa.icon(icon_name, color=color)

    @staticmethod
    def get_pixmap(icon_name: str, color: str, size: QSize) -> QIcon:
        return fa.icon(icon_name, color=color).pixmap(size)


# =========================================================================================
# === SYNC WORKERS & BACKGROUND TASKS
# =========================================================================================
class NetworkGraphWidget(QWidget):
    # This class is unchanged
    def __init__(self, parent=None):
        super().__init__(parent)
        self.history_size = 60
        self.upload_history = collections.deque([0.0] * self.history_size, maxlen=self.history_size)
        self.download_history = collections.deque([0.0] * self.history_size, maxlen=self.history_size)
        self.last_stats = psutil.net_io_counters() if PSUTIL_AVAILABLE else None
        self.current_upload_speed = 0;
        self.current_download_speed = 0
        self.setMinimumSize(200, 25);
        self.setToolTip("Network Activity (Upload/Download)")
        self.timer = QTimer(self);
        self.timer.timeout.connect(self.update_stats);
        self.timer.start(1000)

    def _format_speed(self, speed_bps):
        if speed_bps < 1024:
            return f"{speed_bps:.1f} B/s"
        elif speed_bps < 1024 ** 2:
            return f"{speed_bps / 1024:.1f} KB/s"
        elif speed_bps < 1024 ** 3:
            return f"{speed_bps / (1024 ** 2):.1f} MB/s"
        else:
            return f"{speed_bps / (1024 ** 3):.1f} GB/s"

    def update_stats(self):
        if not PSUTIL_AVAILABLE or self.last_stats is None: return
        current_stats = psutil.net_io_counters()
        self.current_upload_speed = current_stats.bytes_sent - self.last_stats.bytes_sent
        self.current_download_speed = current_stats.bytes_recv - self.last_stats.bytes_recv
        self.last_stats = current_stats
        self.upload_history.append(self.current_upload_speed);
        self.download_history.append(self.current_download_speed)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self);
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        upload_text = f"↑ {self._format_speed(self.current_upload_speed)}"
        download_text = f"↓ {self._format_speed(self.current_download_speed)}"
        font = self.font();
        font.setPointSize(8);
        painter.setFont(font)
        painter.setPen(QColor("#e67e22"));
        painter.drawText(QRect(5, 0, self.width() // 2 - 5, self.height()),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, upload_text)
        painter.setPen(QColor("#3498db"));
        painter.drawText(QRect(self.width() // 2, 0, self.width() // 2 - 5, self.height()),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, download_text)


class SyncWorker(QObject):
    finished = pyqtSignal(bool, str)

    def _to_float(self, value, default=None):
        if value is None: return default
        try:
            return float(value)
        except (ValueError, TypeError):
            try:
                cleaned_value = str(value).strip(); return float(cleaned_value) if cleaned_value else default
            except (ValueError, TypeError):
                return default

    def run(self):
        try:
            dbf = dbfread.DBF(PRODUCTION_DBF_PATH, load=True, encoding='latin1')
            recs = [{'lot': str(r.get('T_LOTNUM', '')).strip().upper(), 'code': str(r.get('T_PRODCODE', '')).strip(),
                     'cust': str(r.get('T_CUSTOMER', '')).strip(),
                     'fid': str(int(r.get('T_FID'))) if r.get('T_FID') is not None else '',
                     'op': str(r.get('T_OPER', '')).strip(), 'sup': str(r.get('T_SUPER', '')).strip(),
                     'prod_id': str(r.get('T_PRODID', '')).strip(), 'machine': str(r.get('T_MACHINE', '')).strip(),
                     'qty_prod': self._to_float(r.get('T_QTYPROD')), 'prod_date': r.get('T_PRODDATE'),
                     'prod_color': str(r.get('T_PRODCOLO', '')).strip()} for r in dbf.records if
                    str(r.get('T_LOTNUM', '')).strip()]
            if not recs: self.finished.emit(True, "Sync Info: No new records found."); return
            with engine.connect() as conn:
                with conn.begin(): conn.execute(text(
                    "INSERT INTO legacy_production(lot_number, prod_code, customer_name, formula_id, operator, supervisor, prod_id, machine, qty_prod, prod_date, prod_color, last_synced_on) VALUES (:lot, :code, :cust, :fid, :op, :sup, :prod_id, :machine, :qty_prod, :prod_date, :prod_color, NOW()) ON CONFLICT(lot_number) DO UPDATE SET prod_code=EXCLUDED.prod_code, customer_name=EXCLUDED.customer_name, formula_id=EXCLUDED.formula_id, operator=EXCLUDED.operator, supervisor=EXCLUDED.supervisor, prod_id=EXCLUDED.prod_id, machine=EXCLUDED.machine, qty_prod=EXCLUDED.qty_prod, prod_date=EXCLUDED.prod_date, prod_color=EXCLUDED.prod_color, last_synced_on=NOW()"),
                                                recs)
            self.finished.emit(True, f"Production sync complete. {len(recs)} records processed.")
        except dbfread.DBFNotFound:
            self.finished.emit(False, f"File Not Found: {PRODUCTION_DBF_PATH}")
        except Exception as e:
            self.finished.emit(False, f"An unexpected error occurred: {e}")


class SyncCustomerWorker(QObject):
    finished = pyqtSignal(bool, str)

    def run(self):
        try:
            dbf = dbfread.DBF(CUSTOMER_DBF_PATH, load=True, encoding='latin1')
            recs = [{'name': str(r.get('T_CUSTOMER', '')).strip(),
                     'address': (str(r.get('T_ADD1', '')).strip() + ' ' + str(r.get('T_ADD2', '')).strip()).strip(),
                     'deliver_to': str(r.get('T_CUSTOMER', '')).strip(), 'tin': str(r.get('T_TIN', '')).strip(),
                     'terms': str(r.get('T_TERMS', '')).strip(), 'is_deleted': bool(r.get('T_DELETED', False))} for r in
                    dbf.records if str(r.get('T_CUSTOMER', '')).strip()]
            if not recs: self.finished.emit(True, "Sync Info: No new customer records found."); return
            with engine.connect() as conn:
                with conn.begin(): conn.execute(text(
                    "INSERT INTO customers (name, address, deliver_to, tin, terms, is_deleted) VALUES (:name, :address, :deliver_to, :tin, :terms, :is_deleted) ON CONFLICT (name) DO UPDATE SET address = EXCLUDED.address, deliver_to = EXCLUDED.deliver_to, tin = EXCLUDED.tin, terms = EXCLUDED.terms, is_deleted = EXCLUDED.is_deleted"),
                                                recs)
            self.finished.emit(True, f"Customer sync complete. {len(recs)} records processed.")
        except dbfread.DBFNotFound:
            self.finished.emit(False, f"File Not Found: {CUSTOMER_DBF_PATH}")
        except Exception as e:
            self.finished.emit(False, f"An unexpected error occurred: {e}")


class SyncDeliveryWorker(QObject):
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
                    attachments = "\n".join(
                        filter(None, [str(item_rec.get(f'T_DESC{i}', '')).strip() for i in range(1, 5)]))
                    items_by_dr[dr_num].append({'dr_no': dr_num, 'quantity': self._to_float(item_rec.get('T_TOTALWT')),
                                                'unit': str(item_rec.get('T_TOTALWTU', '')).strip(),
                                                'product_code': str(item_rec.get('T_PRODCODE', '')).strip(),
                                                'product_color': str(item_rec.get('T_PRODCOLO', '')).strip(),
                                                'no_of_packing': self._to_float(item_rec.get('T_NUMPACKI')),
                                                'weight_per_pack': self._to_float(item_rec.get('T_WTPERPAC')),
                                                'lot_numbers': "", 'attachments': attachments, 'unit_price': None,
                                                'lot_no_1': None, 'lot_no_2': None, 'lot_no_3': None, 'mfg_date': None,
                                                'alias_code': None, 'alias_desc': None})
            primary_recs_from_dbf = []
            with dbfread.DBF(DELIVERY_DBF_PATH, load=True, encoding='latin1') as dbf_primary:
                for r in dbf_primary.records:
                    dr_num = self._get_safe_dr_num(r.get('T_DRNUM'))
                    if not dr_num: continue
                    address = (str(r.get('T_ADD1', '')).strip() + ' ' + str(r.get('T_ADD2', '')).strip()).strip()
                    primary_recs_from_dbf.append({'dr_no': dr_num, 'delivery_date': r.get('T_DRDATE'),
                                                  'customer_name': str(r.get('T_CUSTOMER', '')).strip(),
                                                  'deliver_to': str(r.get('T_DELTO', '')).strip(), 'address': address,
                                                  'po_no': str(r.get('T_CPONUM', '')).strip(),
                                                  'order_form_no': str(r.get('T_ORDERNUM', '')).strip(),
                                                  'terms': str(r.get('T_REMARKS', '')).strip(),
                                                  'prepared_by': str(r.get('T_USERID', '')).strip(),
                                                  'encoded_on': r.get('T_DENCODED'),
                                                  'is_deleted': bool(r.get('T_DELETED', False))})
            if not primary_recs_from_dbf: self.finished.emit(True,
                                                             "Sync Info: No new delivery records to sync."); return
            with engine.connect() as conn:
                with conn.begin():
                    existing_dr_nos_query = conn.execute(text("SELECT dr_no FROM product_delivery_primary"))
                    existing_dr_nos = {row[0] for row in existing_dr_nos_query}
                    primary_recs_to_insert = [rec for rec in primary_recs_from_dbf if
                                              rec['dr_no'] not in existing_dr_nos]
                    if not primary_recs_to_insert: self.finished.emit(True,
                                                                      "Sync Info: All delivery records from DBF already exist."); return
                    conn.execute(text(
                        "INSERT INTO product_delivery_primary (dr_no, delivery_date, customer_name, deliver_to, address, po_no, order_form_no, terms, prepared_by, encoded_on, is_deleted, edited_by, edited_on, encoded_by) VALUES (:dr_no, :delivery_date, :customer_name, :deliver_to, :address, :po_no, :order_form_no, :terms, :prepared_by, :encoded_on, :is_deleted, 'DBF_SYNC', NOW(), :prepared_by) ON CONFLICT (dr_no) DO NOTHING"),
                                 primary_recs_to_insert)
                    dr_numbers_to_insert = [rec['dr_no'] for rec in primary_recs_to_insert]
                    all_items_to_insert = [item for dr_num in dr_numbers_to_insert if dr_num in items_by_dr for item in
                                           items_by_dr[dr_num]]
                    if all_items_to_insert: conn.execute(text(
                        "INSERT INTO product_delivery_items (dr_no, quantity, unit, product_code, product_color, no_of_packing, weight_per_pack, lot_numbers, attachments, unit_price, lot_no_1, lot_no_2, lot_no_3, mfg_date, alias_code, alias_desc) VALUES (:dr_no, :quantity, :unit, :product_code, :product_color, :no_of_packing, :weight_per_pack, :lot_numbers, :attachments, :unit_price, :lot_no_1, :lot_no_2, :lot_no_3, :mfg_date, :alias_code, :alias_desc)"),
                                                         all_items_to_insert)
            self.finished.emit(True, f"Delivery sync complete. {len(primary_recs_to_insert)} new records processed.")
        except dbfread.DBFNotFound as e:
            self.finished.emit(False, f"File Not Found: {e}")
        except Exception as e:
            self.finished.emit(False, f"An unexpected error occurred: {e}")


class SyncRRFWorker(QObject):
    finished = pyqtSignal(bool, str)

    def _get_safe_rrf_num(self, rrf_num_raw):
        if rrf_num_raw is None: return None
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
                cleaned_value = str(value).strip(); return float(cleaned_value) if cleaned_value else default
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
                    items_by_rrf[rrf_num].append(
                        {'rrf_no': rrf_num, 'quantity': self._to_float(item_rec.get('T_TOTALWT')),
                         'unit': str(item_rec.get('T_TOTALWTU', '')).strip(),
                         'product_code': str(item_rec.get('T_PRODCODE', '')).strip(),
                         'lot_number': str(item_rec.get('T_DESC1', '')).strip(),
                         'reference_number': str(item_rec.get('T_DESC2', '')).strip(), 'remarks': remarks})
            primary_recs = []
            with dbfread.DBF(RRF_PRIMARY_DBF_PATH, load=True, encoding='latin1') as dbf_primary:
                for r in dbf_primary.records:
                    rrf_num = self._get_safe_rrf_num(r.get('T_DRNUM'))
                    if not rrf_num: continue
                    primary_recs.append({'rrf_no': rrf_num, 'rrf_date': r.get('T_DRDATE'),
                                         'customer_name': str(r.get('T_CUSTOMER', '')).strip(),
                                         'material_type': str(r.get('T_DELTO', '')).strip(),
                                         'prepared_by': str(r.get('T_USERID', '')).strip(),
                                         'is_deleted': bool(r.get('T_DELETED', False))})
            if not primary_recs: self.finished.emit(True, "Sync Info: No new RRF records found."); return
            with engine.connect() as conn:
                with conn.begin():
                    rrf_numbers_to_sync = [rec['rrf_no'] for rec in primary_recs]
                    conn.execute(text("DELETE FROM rrf_items WHERE rrf_no = ANY(:rrf_nos)"),
                                 {"rrf_nos": rrf_numbers_to_sync})
                    conn.execute(text(
                        "INSERT INTO rrf_primary (rrf_no, rrf_date, customer_name, material_type, prepared_by, is_deleted, encoded_by, encoded_on, edited_by, edited_on) VALUES (:rrf_no, :rrf_date, :customer_name, :material_type, :prepared_by, :is_deleted, 'DBF_SYNC', NOW(), 'DBF_SYNC', NOW()) ON CONFLICT (rrf_no) DO UPDATE SET rrf_date = EXCLUDED.rrf_date, customer_name = EXCLUDED.customer_name, material_type = EXCLUDED.material_type, prepared_by = EXCLUDED.prepared_by, is_deleted = EXCLUDED.is_deleted, edited_by = 'DBF_SYNC', edited_on = NOW()"),
                                 primary_recs)
                    all_items_to_insert = [item for rrf_num in rrf_numbers_to_sync if rrf_num in items_by_rrf for item
                                           in items_by_rrf[rrf_num]]
                    if all_items_to_insert: conn.execute(text(
                        "INSERT INTO rrf_items (rrf_no, quantity, unit, product_code, lot_number, reference_number, remarks) VALUES (:rrf_no, :quantity, :unit, :product_code, :lot_number, :reference_number, :remarks)"),
                                                         all_items_to_insert)
            self.finished.emit(True,
                               f"RRF sync complete. {len(primary_recs)} records and {len(all_items_to_insert)} items processed.")
        except dbfread.DBFNotFound as e:
            self.finished.emit(False, f"File Not Found: {e}")
        except Exception as e:
            self.finished.emit(False, f"An unexpected error occurred: {e}")


def initialize_database():
    print("Initializing database schema...")
    try:
        with engine.connect() as connection:
            with connection.begin():
                # --- All CREATE TABLE statements from your previous file go here... ---
                # This is kept the same to avoid breaking anything
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL, qc_access BOOLEAN DEFAULT TRUE, role TEXT DEFAULT 'Editor');"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS qc_audit_trail (id SERIAL PRIMARY KEY, timestamp TIMESTAMP, username TEXT, action_type TEXT, details TEXT, hostname TEXT, ip_address TEXT, mac_address TEXT);"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS transactions (id SERIAL PRIMARY KEY, transaction_date DATE NOT NULL, transaction_type VARCHAR(50) NOT NULL, source_ref_no VARCHAR(50), product_code VARCHAR(50) NOT NULL, lot_number VARCHAR(50), quantity_in NUMERIC(15, 6) DEFAULT 0, quantity_out NUMERIC(15, 6) DEFAULT 0, unit VARCHAR(20), warehouse VARCHAR(50), encoded_by VARCHAR(50), encoded_on TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP, remarks TEXT);"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS failed_transactions (id SERIAL PRIMARY KEY, transaction_date DATE NOT NULL, transaction_type VARCHAR(50) NOT NULL, source_ref_no VARCHAR(50), product_code VARCHAR(50) NOT NULL, lot_number VARCHAR(50), quantity_in NUMERIC(15, 6) DEFAULT 0, quantity_out NUMERIC(15, 6) DEFAULT 0, unit VARCHAR(20), warehouse VARCHAR(50), encoded_by VARCHAR(50), encoded_on TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP, remarks TEXT);"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS app_settings (setting_key VARCHAR(50) PRIMARY KEY, setting_value VARCHAR(255));"))
                connection.execute(text(
                    "INSERT INTO app_settings (setting_key, setting_value) VALUES ('RRF_SEQUENCE_START', '15000'), ('DR_SEQUENCE_START', '100001') ON CONFLICT (setting_key) DO NOTHING;"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS legacy_production (lot_number TEXT PRIMARY KEY, prod_code TEXT, customer_name TEXT, formula_id TEXT, operator TEXT, supervisor TEXT, prod_id TEXT, machine TEXT, qty_prod NUMERIC(15, 6), prod_date DATE, prod_color TEXT, last_synced_on TIMESTAMP);"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS customers (id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL, deliver_to TEXT, address TEXT, tin TEXT, terms TEXT, is_deleted BOOLEAN NOT NULL DEFAULT FALSE);"))
                connection.execute(
                    text("CREATE TABLE IF NOT EXISTS units (id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL);"))
                connection.execute(
                    text("INSERT INTO units (name) VALUES ('KG.'), ('PCS'), ('BOX') ON CONFLICT (name) DO NOTHING;"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS product_aliases (id SERIAL PRIMARY KEY, product_code TEXT UNIQUE NOT NULL, alias_code TEXT, description TEXT, extra_description TEXT);"))
                # ... many other table creation statements
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS product_delivery_primary (id SERIAL PRIMARY KEY, dr_no TEXT NOT NULL UNIQUE, delivery_date DATE, customer_name TEXT, deliver_to TEXT, address TEXT, po_no TEXT, order_form_no TEXT, fg_out_id TEXT, terms TEXT, prepared_by TEXT, encoded_by TEXT, encoded_on TIMESTAMP, edited_by TEXT, edited_on TIMESTAMP, is_deleted BOOLEAN NOT NULL DEFAULT FALSE, is_printed BOOLEAN NOT NULL DEFAULT FALSE);"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS product_delivery_items (id SERIAL PRIMARY KEY, dr_no TEXT NOT NULL, quantity NUMERIC(15, 6), unit TEXT, product_code TEXT, product_color TEXT, no_of_packing NUMERIC(15, 2), weight_per_pack NUMERIC(15, 6), lot_numbers TEXT, attachments TEXT, unit_price NUMERIC(15, 6), lot_no_1 TEXT, lot_no_2 TEXT, lot_no_3 TEXT, mfg_date TEXT, alias_code TEXT, alias_desc TEXT, FOREIGN KEY (dr_no) REFERENCES product_delivery_primary (dr_no) ON DELETE CASCADE);"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS product_delivery_lot_breakdown (id SERIAL PRIMARY KEY, dr_no TEXT NOT NULL, item_id INTEGER, lot_number TEXT NOT NULL, quantity_kg NUMERIC(15, 6), FOREIGN KEY (dr_no) REFERENCES product_delivery_primary (dr_no) ON DELETE CASCADE);"))
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS requisition_logbook (id SERIAL PRIMARY KEY, req_id TEXT NOT NULL UNIQUE, manual_ref_no TEXT, category TEXT, request_date DATE, requester_name TEXT, department TEXT, product_code TEXT, lot_no TEXT, quantity_kg NUMERIC(15, 6), status TEXT, approved_by TEXT, remarks TEXT, location VARCHAR(50), request_for VARCHAR(10), encoded_by TEXT, encoded_on TIMESTAMP, edited_by TEXT, edited_on TIMESTAMP, is_deleted BOOLEAN NOT NULL DEFAULT FALSE);"))
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
                # ... other initial data inserts

        print("Database initialized successfully.")
    except Exception as e:
        QApplication(sys.argv)
        QMessageBox.critical(None, "DB Init Error", f"Could not initialize database: {e}")
        sys.exit(1)


# =========================================================================================
# === PAGE WIDGETS (RequisitionLogbookPage and placeholders)
# =========================================================================================

# --- Requisition Logbook Page (Fully Implemented) ---
class RequisitionLogbookPage(QWidget):
    # The full code for RequisitionLogbookPage from the previous turn goes here.
    # I have included it below, with the one-line fix applied.
    def __init__(self, db_engine, username, log_audit_trail_func):
        super().__init__()
        self.engine, self.username, self.log_audit_trail = db_engine, username, log_audit_trail_func
        self.current_editing_req_id = None
        self.current_page = 1
        self.records_per_page = 200
        self.total_records, self.total_pages = 0, 1
        self.deleted_current_page = 1
        self.deleted_total_records, self.deleted_total_pages = 0, 1
        self.init_ui()
        self._load_all_records()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)
        view_tab = QWidget()
        self.view_details_tab, self.entry_tab, self.deleted_tab = QWidget(), QWidget(), QWidget()
        self.tab_widget.addTab(view_tab, "All Requisitions")
        self.tab_widget.addTab(self.view_details_tab, "View Requisition Details")
        self.tab_widget.addTab(self.entry_tab, "Requisition Entry")
        self.tab_widget.addTab(self.deleted_tab, "Deleted Records")
        if fa:
            self.tab_widget.setTabIcon(self.tab_widget.indexOf(view_tab), fa.icon('fa5s.list-alt'))
            self.tab_widget.setTabIcon(self.tab_widget.indexOf(self.view_details_tab), fa.icon('fa5s.info-circle'))
            self.tab_widget.setTabIcon(self.tab_widget.indexOf(self.entry_tab), fa.icon('fa5s.edit'))
            self.tab_widget.setTabIcon(self.tab_widget.indexOf(self.deleted_tab), fa.icon('fa5s.trash-alt'))
        self._setup_view_tab(view_tab)
        self._setup_view_details_tab(self.view_details_tab)
        self._setup_entry_tab(self.entry_tab)
        self._setup_deleted_tab(self.deleted_tab)
        self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.view_details_tab), False)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

    def _setup_view_tab(self, tab):
        layout = QVBoxLayout(tab);
        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("Search:"));
        self.search_edit = UpperCaseLineEdit(placeholderText="Filter by Req ID, Ref#, Product, Lot...")
        top_layout.addWidget(self.search_edit, 1)
        self.refresh_btn = QPushButton(" Refresh");
        self.update_btn = QPushButton(" Load for Update");
        self.delete_btn = QPushButton(" Delete")
        if fa: self.refresh_btn.setIcon(fa.icon('fa5s.sync-alt')); self.update_btn.setIcon(
            fa.icon('fa5s.pencil-alt')); self.delete_btn.setIcon(fa.icon('fa5s.trash-alt'))
        top_layout.addWidget(self.refresh_btn);
        top_layout.addWidget(self.update_btn);
        top_layout.addWidget(self.delete_btn)
        layout.addLayout(top_layout)
        self.records_table = QTableWidget();
        self.records_table.setFocusPolicy(Qt.FocusPolicy.NoFocus);
        self.records_table.setShowGrid(False)
        self.records_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);
        self.records_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.records_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection);
        self.records_table.verticalHeader().setVisible(False)
        self.records_table.horizontalHeader().setHighlightSections(False);
        self.records_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.records_table.customContextMenuRequested.connect(self._show_records_table_context_menu)
        layout.addWidget(self.records_table)
        pagination_layout = QHBoxLayout();
        self.prev_btn, self.next_btn = QPushButton(" Previous"), QPushButton("Next ")
        if fa: self.prev_btn.setIcon(fa.icon('fa5s.chevron-left')); self.next_btn.setIcon(
            fa.icon('fa5s.chevron-right')); self.next_btn.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.page_label = QLabel("Page 1 of 1");
        pagination_layout.addStretch();
        pagination_layout.addWidget(self.prev_btn)
        pagination_layout.addWidget(self.page_label);
        pagination_layout.addWidget(self.next_btn);
        pagination_layout.addStretch()
        layout.addLayout(pagination_layout)
        self.search_edit.textChanged.connect(self._on_search_text_changed);
        self.refresh_btn.clicked.connect(self._load_all_records)
        self.update_btn.clicked.connect(self._load_record_for_update);
        self.delete_btn.clicked.connect(self._delete_record)
        self.records_table.itemSelectionChanged.connect(self._on_record_selection_changed);
        self.records_table.doubleClicked.connect(self._load_record_for_update)
        self.prev_btn.clicked.connect(self._go_to_prev_page);
        self.next_btn.clicked.connect(self._go_to_next_page);
        self._on_record_selection_changed()

    def _setup_deleted_tab(self, tab):
        layout = QVBoxLayout(tab);
        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("Search:"));
        self.deleted_search_edit = UpperCaseLineEdit(placeholderText="Filter deleted records...")
        top_layout.addWidget(self.deleted_search_edit, 1)
        self.restore_btn = QPushButton(" Restore Selected")
        if fa: self.restore_btn.setIcon(fa.icon('fa5s.undo'))
        self.restore_btn.setEnabled(False);
        top_layout.addWidget(self.restore_btn);
        layout.addLayout(top_layout)
        self.deleted_records_table = QTableWidget();
        self.deleted_records_table.setFocusPolicy(Qt.FocusPolicy.NoFocus);
        self.deleted_records_table.setShowGrid(False)
        self.deleted_records_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);
        self.deleted_records_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.deleted_records_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection);
        self.deleted_records_table.verticalHeader().setVisible(False)
        self.deleted_records_table.horizontalHeader().setHighlightSections(False);
        self.deleted_records_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.deleted_records_table.customContextMenuRequested.connect(self._show_deleted_table_context_menu)
        layout.addWidget(self.deleted_records_table)
        pagination_layout = QHBoxLayout();
        self.deleted_prev_btn, self.deleted_next_btn = QPushButton(" Previous"), QPushButton("Next ")
        if fa: self.deleted_prev_btn.setIcon(fa.icon('fa5s.chevron-left')); self.deleted_next_btn.setIcon(
            fa.icon('fa5s.chevron-right')); self.deleted_next_btn.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.deleted_page_label = QLabel("Page 1 of 1");
        pagination_layout.addStretch();
        pagination_layout.addWidget(self.deleted_prev_btn)
        pagination_layout.addWidget(self.deleted_page_label);
        pagination_layout.addWidget(self.deleted_next_btn);
        pagination_layout.addStretch()
        layout.addLayout(pagination_layout)
        self.deleted_search_edit.textChanged.connect(self._on_deleted_search_text_changed);
        self.restore_btn.clicked.connect(self._restore_record)
        self.deleted_records_table.itemSelectionChanged.connect(
            lambda: self.restore_btn.setEnabled(bool(self.deleted_records_table.selectedItems())))
        self.deleted_prev_btn.clicked.connect(self._go_to_deleted_prev_page);
        self.deleted_next_btn.clicked.connect(self._go_to_deleted_next_page)

    def _setup_entry_tab(self, tab):
        layout = QVBoxLayout(tab);
        form_group = QGroupBox("Requisition Details");
        layout.addWidget(form_group)
        form_layout = QGridLayout(form_group)
        self.req_id_edit = QLineEdit(readOnly=True, placeholderText="Auto-generated");
        self.manual_ref_no_edit = UpperCaseLineEdit()
        self.category_combo = QComboBox();
        self.category_combo.addItems(["MB", "DC"]);
        self.request_date_edit = QDateEdit(calendarPopup=True, displayFormat="yyyy-MM-dd")
        self.requester_name_combo = QComboBox();
        self.department_combo = QComboBox();
        self.product_code_combo = QComboBox();
        self.approved_by_combo = QComboBox()
        self.status_combo = QComboBox();
        self.lot_no_edit = UpperCaseLineEdit();
        self.quantity_edit = FloatLineEdit();
        self.remarks_edit = UpperCaseLineEdit()
        self.location_combo = QComboBox();
        self.location_combo.addItems(["WH1", "WH2", "WH3", "WH4", "WH5"]);
        self.request_for_combo = QComboBox();
        self.request_for_combo.addItems(["PASSED", "FAILED"])
        self._configure_combobox(self.requester_name_combo, editable=True);
        self._configure_combobox(self.department_combo, editable=True)
        self._configure_combobox(self.product_code_combo, editable=True);
        self._configure_combobox(self.approved_by_combo, editable=True)
        self._configure_combobox(self.status_combo, editable=True);
        self._refresh_entry_combos()
        requester_widget = self._create_combo_with_add_button(self.requester_name_combo, self._on_add_requester)
        department_widget = self._create_combo_with_add_button(self.department_combo, self._on_add_department)
        approved_by_widget = self._create_combo_with_add_button(self.approved_by_combo, self._on_add_approver)
        form_layout.addWidget(QLabel("Requisition ID:"), 0, 0);
        form_layout.addWidget(self.req_id_edit, 0, 1)
        form_layout.addWidget(QLabel("Manual Ref #:"), 0, 2);
        form_layout.addWidget(self.manual_ref_no_edit, 0, 3)
        form_layout.addWidget(QLabel("Request Date:"), 1, 0);
        form_layout.addWidget(self.request_date_edit, 1, 1)
        form_layout.addWidget(QLabel("Category:"), 1, 2);
        form_layout.addWidget(self.category_combo, 1, 3)
        form_layout.addWidget(QLabel("Requester Name:"), 2, 0);
        form_layout.addWidget(requester_widget, 2, 1)
        form_layout.addWidget(QLabel("Department:"), 2, 2);
        form_layout.addWidget(department_widget, 2, 3)
        form_layout.addWidget(QLabel("Product Code:"), 3, 0);
        form_layout.addWidget(self.product_code_combo, 3, 1)
        form_layout.addWidget(QLabel("Lot #:"), 3, 2);
        form_layout.addWidget(self.lot_no_edit, 3, 3)
        form_layout.addWidget(QLabel("Quantity (kg):"), 4, 0);
        form_layout.addWidget(self.quantity_edit, 4, 1)
        form_layout.addWidget(QLabel("Location:"), 4, 2);
        form_layout.addWidget(self.location_combo, 4, 3)
        form_layout.addWidget(QLabel("Request For:"), 5, 0);
        form_layout.addWidget(self.request_for_combo, 5, 1)
        form_layout.addWidget(QLabel("Status:"), 5, 2);
        form_layout.addWidget(self.status_combo, 5, 3)
        form_layout.addWidget(QLabel("Approved By:"), 6, 0);
        form_layout.addWidget(approved_by_widget, 6, 1)
        form_layout.addWidget(QLabel("Remarks:"), 6, 2);
        form_layout.addWidget(self.remarks_edit, 6, 3)
        layout.addStretch();
        button_layout = QHBoxLayout();
        self.save_btn = QPushButton(" Save");
        self.clear_btn = QPushButton(" New");
        self.cancel_update_btn = QPushButton(" Cancel Update")
        if fa: self.save_btn.setIcon(fa.icon('fa5s.save')); self.clear_btn.setIcon(
            fa.icon('fa5s.file')); self.cancel_update_btn.setIcon(fa.icon('fa5s.times'))
        button_layout.addStretch();
        button_layout.addWidget(self.cancel_update_btn);
        button_layout.addWidget(self.clear_btn);
        button_layout.addWidget(self.save_btn)
        layout.addLayout(button_layout)
        self.save_btn.clicked.connect(self._save_record);
        self.clear_btn.clicked.connect(self._clear_form);
        self.cancel_update_btn.clicked.connect(self._clear_form)
        self._clear_form()

    def _create_combo_with_add_button(self, combo: QComboBox, on_add_method):
        container = QWidget();
        layout = QHBoxLayout(container);
        layout.setContentsMargins(0, 0, 0, 0);
        layout.setSpacing(5);
        layout.addWidget(combo, 1);
        add_btn = QPushButton()
        if fa:
            add_btn.setIcon(fa.icon('fa5s.plus'))
        else:
            add_btn.setText("+")
        add_btn.setFixedSize(30, 30);
        add_btn.setToolTip("Add a new value to the list");
        add_btn.clicked.connect(on_add_method);
        layout.addWidget(add_btn)
        return container

    def _on_add_requester(self):
        self._add_new_lookup_value(self.requester_name_combo, "Requester", 'requisition_requesters', 'name')

    def _on_add_department(self):
        self._add_new_lookup_value(self.department_combo, "Department", 'requisition_departments', 'name')

    def _on_add_approver(self):
        self._add_new_lookup_value(self.approved_by_combo, "Approver", 'requisition_approvers', 'name')

    def _add_new_lookup_value(self, combo_widget, dialog_title, table_name, column_name):
        dialog = AddNewValueDialog(self, f"Add New {dialog_title}", f"Enter new {dialog_title.lower()} name:")
        if dialog.exec():
            new_value = dialog.get_value()
            if not new_value: return
            try:
                with self.engine.connect() as conn, conn.begin():
                    conn.execute(text(
                        f"INSERT INTO {table_name} ({column_name}) VALUES (:value) ON CONFLICT ({column_name}) DO NOTHING"),
                                 {"value": new_value})
                self._populate_combo(combo_widget, table_name, column_name);
                combo_widget.setCurrentText(new_value)
            except Exception as e:
                QMessageBox.critical(self, "Database Error", f"Could not save new {dialog_title.lower()}: {e}")

    def _configure_combobox(self, combo: QComboBox, editable: bool = False):
        combo.setEditable(editable)
        if editable:
            line_edit = UpperCaseLineEdit(self)
            # The line `line_edit.setFont(self.font())` was correctly removed to fix the invisible font issue.
            combo.setLineEdit(line_edit)
            combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
            completer = QCompleter();
            completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion);
            completer.setFilterMode(Qt.MatchFlag.MatchContains);
            combo.setCompleter(completer)

    def _refresh_entry_combos(self):
        self._populate_combo(self.product_code_combo, 'legacy_production', 'prod_code');
        self._populate_combo(self.requester_name_combo, 'requisition_requesters', 'name')
        self._populate_combo(self.approved_by_combo, 'requisition_approvers', 'name');
        self._populate_combo(self.department_combo, 'requisition_departments', 'name')
        self._populate_combo(self.status_combo, 'requisition_statuses', 'status_name')

    def _populate_combo(self, combo: QComboBox, table: str, column: str):
        current_text = combo.currentText()
        try:
            with self.engine.connect() as conn:
                results = conn.execute(text(
                    f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL AND {column} != '' ORDER BY {column}")).scalars().all()
            combo.blockSignals(True);
            combo.clear()
            if table == 'requisition_statuses' and not results: results = ["PENDING", "APPROVED", "COMPLETED",
                                                                           "REJECTED"]
            combo.addItems(results);
            combo.blockSignals(False);
            combo.setCurrentText(current_text)
            if combo.lineEdit(): combo.lineEdit().setPlaceholderText("SELECT OR TYPE...")
        except Exception as e:
            if table == 'requisition_statuses': combo.addItems(["PENDING", "APPROVED", "COMPLETED", "REJECTED"])

    def _setup_view_details_tab(self, tab):
        layout = QVBoxLayout(tab);
        details_group = QGroupBox("Requisition Details (Read-Only)");
        self.view_details_layout = QFormLayout(details_group)
        layout.addWidget(details_group);
        layout.addStretch()

    def _on_tab_changed(self, index):
        tab_widget = self.tab_widget.widget(index)
        if tab_widget == self.view_details_tab:
            self._show_selected_record_in_view_tab()
        elif tab_widget == self.entry_tab:
            self._refresh_entry_combos()
        elif tab_widget == self.deleted_tab:
            self._load_deleted_records()

    def _clear_form(self):
        self.current_editing_req_id = None;
        self.cancel_update_btn.hide();
        self.save_btn.setText("Save Requisition")
        for w in [self.req_id_edit, self.manual_ref_no_edit, self.lot_no_edit, self.remarks_edit]: w.clear()
        for c in [self.requester_name_combo, self.department_combo, self.product_code_combo,
                  self.approved_by_combo]: c.setCurrentText("")
        self.quantity_edit.setText("0.00");
        self.category_combo.setCurrentIndex(0);
        self.status_combo.setCurrentText("PENDING")
        self.request_date_edit.setDate(QDate.currentDate());
        self.location_combo.setCurrentIndex(0);
        self.request_for_combo.setCurrentIndex(0);
        self.manual_ref_no_edit.setFocus()

    def _generate_req_id(self):
        prefix = f"REQ-{datetime.now().strftime('%Y%m%d')}-"
        try:
            with self.engine.connect() as conn:
                last_ref = conn.execute(
                    text("SELECT req_id FROM requisition_logbook WHERE req_id LIKE :p ORDER BY id DESC LIMIT 1"),
                    {"p": f"{prefix}%"}).scalar_one_or_none()
                return f"{prefix}{int(last_ref.split('-')[-1]) + 1:04d}" if last_ref else f"{prefix}0001"
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not generate Requisition ID: {e}"); return None

    def _save_record(self):
        is_update = self.current_editing_req_id is not None
        req_id = self.current_editing_req_id or self._generate_req_id()
        if not req_id: return
        data = {"req_id": req_id, "manual_ref_no": self.manual_ref_no_edit.text(),
                "category": self.category_combo.currentText(), "request_date": self.request_date_edit.date().toPyDate(),
                "requester_name": self.requester_name_combo.currentText(),
                "department": self.department_combo.currentText(),
                "product_code": self.product_code_combo.currentText(), "lot_no": self.lot_no_edit.text(),
                "quantity_kg": self.quantity_edit.value(), "status": self.status_combo.currentText(),
                "approved_by": self.approved_by_combo.currentText(), "remarks": self.remarks_edit.text(),
                "location": self.location_combo.currentText(), "request_for": self.request_for_combo.currentText(),
                "user": self.username}
        if not data["product_code"]: QMessageBox.warning(self, "Input Error",
                                                         "Product Code is a required field."); return
        try:
            with self.engine.connect() as conn, conn.begin():
                for value, table, column in [(data['requester_name'], 'requisition_requesters', 'name'),
                                             (data['department'], 'requisition_departments', 'name'),
                                             (data['approved_by'], 'requisition_approvers', 'name'),
                                             (data['status'], 'requisition_statuses', 'status_name')]:
                    if value: conn.execute(
                        text(f"INSERT INTO {table} ({column}) VALUES (:value) ON CONFLICT ({column}) DO NOTHING"),
                        {"value": value})
                if is_update:
                    sql = text(
                        "UPDATE requisition_logbook SET manual_ref_no=:manual_ref_no, category=:category, request_date=:request_date, requester_name=:requester_name, department=:department, product_code=:product_code, lot_no=:lot_no, quantity_kg=:quantity_kg, status=:status, approved_by=:approved_by, remarks=:remarks, location=:location, request_for=:request_for, edited_by=:user, edited_on=NOW() WHERE req_id=:req_id")
                    action, log_action = "updated", "UPDATE_REQUISITION"
                else:
                    sql = text(
                        "INSERT INTO requisition_logbook (req_id, manual_ref_no, category, request_date, requester_name, department, product_code, lot_no, quantity_kg, status, approved_by, remarks, location, request_for, encoded_by, encoded_on, edited_by, edited_on) VALUES (:req_id, :manual_ref_no, :category, :request_date, :requester_name, :department, :product_code, :lot_no, :quantity_kg, :status, :approved_by, :remarks, :location, :request_for, :user, NOW(), :user, NOW())")
                    action, log_action = "saved", "CREATE_REQUISITION"
                conn.execute(sql, data)
                self._update_or_create_transaction(conn, data)
                self.log_audit_trail(log_action, f"{action.capitalize()} requisition: {req_id}")
                QMessageBox.information(self, "Success", f"Requisition has been {action}.")
                self._refresh_entry_combos();
                self._clear_form();
                self.tab_widget.setCurrentIndex(0);
                self.search_edit.clear()
                if not self.search_edit.text(): self._load_all_records()
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Could not save record: {e}")

    def _update_or_create_transaction(self, conn, requisition_data):
        req_id = requisition_data['req_id']
        conn.execute(text("DELETE FROM transactions WHERE source_ref_no = :req_id"), {"req_id": req_id})
        conn.execute(text("DELETE FROM failed_transactions WHERE source_ref_no = :req_id"), {"req_id": req_id})
        transaction_data = {"transaction_date": requisition_data['request_date'], "transaction_type": "REQUISITION",
                            "source_ref_no": req_id, "product_code": requisition_data['product_code'],
                            "lot_number": requisition_data['lot_no'], "quantity_out": requisition_data['quantity_kg'],
                            "unit": "KG.", "warehouse": requisition_data['location'], "encoded_by": self.username,
                            "remarks": requisition_data['remarks']}
        if requisition_data['request_for'] == 'PASSED':
            sql = text(
                "INSERT INTO transactions (transaction_date, transaction_type, source_ref_no, product_code, lot_number, quantity_out, unit, warehouse, encoded_by, remarks) VALUES (:transaction_date, :transaction_type, :source_ref_no, :product_code, :lot_number, :quantity_out, :unit, :warehouse, :encoded_by, :remarks)")
            conn.execute(sql, transaction_data)
        elif requisition_data['request_for'] == 'FAILED':
            sql = text(
                "INSERT INTO failed_transactions (transaction_date, transaction_type, source_ref_no, product_code, lot_number, quantity_out, unit, warehouse, encoded_by, remarks) VALUES (:transaction_date, :transaction_type, :source_ref_no, :product_code, :lot_number, :quantity_out, :unit, :warehouse, :encoded_by, :remarks)")
            conn.execute(sql, transaction_data)

    def _load_record_for_update(self):
        row = self.records_table.currentRow();
        if row < 0: return
        req_id = self.records_table.item(row, 0).text()
        try:
            with self.engine.connect() as conn:
                record = conn.execute(text("SELECT * FROM requisition_logbook WHERE req_id = :req_id"),
                                      {"req_id": req_id}).mappings().first()
            if not record: QMessageBox.warning(self, "Not Found", "Record not found."); return
            self._clear_form();
            self.current_editing_req_id = req_id;
            self.req_id_edit.setText(record.get('req_id', ''));
            self.manual_ref_no_edit.setText(record.get('manual_ref_no', ''))
            self.category_combo.setCurrentText(record.get('category', ''));
            self.requester_name_combo.setCurrentText(record.get('requester_name', ''));
            self.department_combo.setCurrentText(record.get('department', ''))
            self.product_code_combo.setCurrentText(record.get('product_code', ''));
            self.lot_no_edit.setText(record.get('lot_no', ''));
            self.quantity_edit.setText(f"{record.get('quantity_kg', 0.00):.2f}")
            self.status_combo.setCurrentText(record.get('status', ''));
            self.approved_by_combo.setCurrentText(record.get('approved_by', ''));
            self.remarks_edit.setText(record.get('remarks', ''))
            self.location_combo.setCurrentText(record.get('location', ''));
            self.request_for_combo.setCurrentText(record.get('request_for', ''))
            if record.get('request_date'): self.request_date_edit.setDate(QDate(record['request_date']))
            self.save_btn.setText("Update Requisition");
            self.cancel_update_btn.show();
            self.tab_widget.setCurrentWidget(self.entry_tab)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load record for update: {e}")

    def _load_all_records(self):
        search_term = self.search_edit.text().strip();
        params = {};
        filter_clause = ""
        if search_term: filter_clause = "AND (req_id ILIKE :term OR manual_ref_no ILIKE :term OR product_code ILIKE :term OR lot_no ILIKE :term)";
        params['term'] = f"%{search_term}%"
        try:
            with self.engine.connect() as conn:
                self.total_records = conn.execute(
                    text(f"SELECT COUNT(*) FROM requisition_logbook WHERE is_deleted IS NOT TRUE {filter_clause}"),
                    params).scalar_one()
                self.total_pages = math.ceil(self.total_records / self.records_per_page) or 1;
                offset = (self.current_page - 1) * self.records_per_page
                params['limit'], params['offset'] = self.records_per_page, offset
                results = conn.execute(text(
                    f"SELECT req_id, manual_ref_no, request_date, product_code, lot_no, quantity_kg, status, location, request_for, edited_by, edited_on FROM requisition_logbook WHERE is_deleted IS NOT TRUE {filter_clause} ORDER BY id DESC LIMIT :limit OFFSET :offset"),
                                       params).mappings().all()
            headers = ["Req ID", "Manual Ref #", "Date", "Product Code", "Lot #", "Qty (kg)", "Status", "Location",
                       "For", "Last Edited By", "Last Edited On"]
            self._populate_records_table(self.records_table, headers, results);
            self._update_pagination_controls();
            self._on_record_selection_changed()
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Failed to load records: {e}")

    def _load_deleted_records(self):
        search_term = self.deleted_search_edit.text().strip();
        params = {};
        filter_clause = ""
        if search_term: filter_clause = "AND (req_id ILIKE :term OR product_code ILIKE :term OR lot_no ILIKE :term)";
        params['term'] = f"%{search_term}%"
        try:
            with self.engine.connect() as conn:
                self.deleted_total_records = conn.execute(
                    text(f"SELECT COUNT(*) FROM requisition_logbook WHERE is_deleted IS TRUE {filter_clause}"),
                    params).scalar_one()
                self.deleted_total_pages = math.ceil(self.deleted_total_records / self.records_per_page) or 1;
                offset = (self.deleted_current_page - 1) * self.records_per_page
                params['limit'], params['offset'] = self.records_per_page, offset
                results = conn.execute(text(
                    f"SELECT req_id, product_code, lot_no, quantity_kg, edited_by as deleted_by, edited_on as deleted_on FROM requisition_logbook WHERE is_deleted IS TRUE {filter_clause} ORDER BY edited_on DESC LIMIT :limit OFFSET :offset"),
                                       params).mappings().all()
            headers = ["Req ID", "Product Code", "Lot #", "Qty (kg)", "Deleted By", "Deleted On"]
            self._populate_records_table(self.deleted_records_table, headers, results);
            self._update_deleted_pagination_controls()
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Failed to load deleted records: {e}")

    def _on_search_text_changed(self, text):
        self.current_page = 1; self._load_all_records()

    def _on_deleted_search_text_changed(self, text):
        self.deleted_current_page = 1; self._load_deleted_records()

    def _update_pagination_controls(self):
        self.page_label.setText(f"Page {self.current_page} of {self.total_pages}"); self.prev_btn.setEnabled(
            self.current_page > 1); self.next_btn.setEnabled(self.current_page < self.total_pages)

    def _update_deleted_pagination_controls(self):
        self.deleted_page_label.setText(
            f"Page {self.deleted_current_page} of {self.deleted_total_pages}"); self.deleted_prev_btn.setEnabled(
            self.deleted_current_page > 1); self.deleted_next_btn.setEnabled(
            self.deleted_current_page < self.deleted_total_pages)

    def _go_to_prev_page(self):
        if self.current_page > 1: self.current_page -= 1; self._load_all_records()

    def _go_to_next_page(self):
        if self.current_page < self.total_pages: self.current_page += 1; self._load_all_records()

    def _go_to_deleted_prev_page(self):
        if self.deleted_current_page > 1: self.deleted_current_page -= 1; self._load_deleted_records()

    def _go_to_deleted_next_page(self):
        if self.deleted_current_page < self.deleted_total_pages: self.deleted_current_page += 1; self._load_deleted_records()

    def _populate_records_table(self, table, headers, data):
        table.setRowCount(0);
        table.setColumnCount(len(headers));
        table.setHorizontalHeaderLabels(headers)
        if not data: return
        table.setRowCount(len(data))
        keys_in_order = [h.lower().replace(' ', '_').replace('#', 'no').replace('last_edited_by', 'edited_by').replace(
            'last_edited_on', 'edited_on').replace('for', 'request_for') for h in headers]
        for row_idx, record in enumerate(data):
            for col_idx, key in enumerate(keys_in_order):
                value = record.get(key)
                if isinstance(value, (Decimal, float)):
                    text_val = f"{value:.2f}"
                elif isinstance(value, (date, datetime)):
                    text_val = value.strftime('%Y-%m-%d %H:%M')
                else:
                    text_val = str(value or '')
                item = QTableWidgetItem(text_val)
                if key in ('quantity_kg',): item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(row_idx, col_idx, item)
        table.resizeColumnsToContents()
        if len(headers) > 3: table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

    def _show_selected_record_in_view_tab(self):
        row = self.records_table.currentRow();
        if row < 0: return
        req_id = self.records_table.item(row, 0).text()
        try:
            with self.engine.connect() as conn:
                record = conn.execute(text("SELECT * FROM requisition_logbook WHERE req_id = :req_id"),
                                      {"req_id": req_id}).mappings().first()
            if not record: QMessageBox.warning(self, "Not Found", "Record not found."); return
            while self.view_details_layout.count(): self.view_details_layout.takeAt(0).widget().deleteLater()
            for key, value in record.items():
                if key in ['id', 'is_deleted']: continue
                label = key.replace('_', ' ').title()
                display_value = value.strftime('%Y-%m-%d %H:%M') if isinstance(value, (
                datetime, date)) else f"{value:.2f}" if isinstance(value, (Decimal, float)) else str(value or 'N/A')
                self.view_details_layout.addRow(QLabel(f"<b>{label}:</b>"), QLabel(display_value))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load details: {e}")

    def _on_record_selection_changed(self):
        is_selected = bool(self.records_table.selectionModel().selectedRows())
        self.update_btn.setEnabled(is_selected);
        self.delete_btn.setEnabled(is_selected)
        self.tab_widget.setTabEnabled(self.tab_widget.indexOf(self.view_details_tab), is_selected)
        if not is_selected and self.tab_widget.currentIndex() == self.tab_widget.indexOf(
            self.view_details_tab): self.tab_widget.setCurrentIndex(0)

    def _show_records_table_context_menu(self, pos):
        if not self.records_table.selectedItems(): return
        menu = QMenu();
        view_action = menu.addAction("View Details");
        edit_action = menu.addAction("Load for Update");
        delete_action = menu.addAction("Delete Record")
        if fa: view_action.setIcon(fa.icon('fa5s.eye')); edit_action.setIcon(
            fa.icon('fa5s.pencil-alt')); delete_action.setIcon(fa.icon('fa5s.trash-alt'))
        action = menu.exec(self.records_table.mapToGlobal(pos))
        if action == view_action:
            self._show_selected_record_in_view_tab(); self.tab_widget.setCurrentWidget(self.view_details_tab)
        elif action == edit_action:
            self._load_record_for_update()
        elif action == delete_action:
            self._delete_record()

    def _show_deleted_table_context_menu(self, pos):
        if not self.deleted_records_table.selectedItems(): return
        menu = QMenu();
        restore_action = menu.addAction("Restore Record")
        if fa: restore_action.setIcon(fa.icon('fa5s.undo'))
        action = menu.exec(self.deleted_records_table.mapToGlobal(pos))
        if action == restore_action: self._restore_record()

    def _delete_record(self):
        row = self.records_table.currentRow();
        if row < 0: return
        req_id = self.records_table.item(row, 0).text()
        if QMessageBox.question(self, "Confirm Deletion",
                                f"Are you sure you want to delete requisition <b>{req_id}</b>?\nThis will also remove its corresponding inventory transaction.",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            try:
                with self.engine.connect() as conn, conn.begin():
                    conn.execute(text(
                        "UPDATE requisition_logbook SET is_deleted = TRUE, edited_by = :user, edited_on = NOW() WHERE req_id = :req_id"),
                                 {"req_id": req_id, "user": self.username})
                    conn.execute(text("DELETE FROM transactions WHERE source_ref_no = :req_id"), {"req_id": req_id})
                    conn.execute(text("DELETE FROM failed_transactions WHERE source_ref_no = :req_id"),
                                 {"req_id": req_id})
                self.log_audit_trail("DELETE_REQUISITION",
                                     f"Soft-deleted requisition and removed transaction for: {req_id}")
                QMessageBox.information(self, "Success", f"Requisition {req_id} has been deleted.");
                self._load_all_records()
            except Exception as e:
                QMessageBox.critical(self, "Database Error", f"Failed to delete record: {e}")

    def _restore_record(self):
        row = self.deleted_records_table.currentRow();
        if row < 0: return
        req_id = self.deleted_records_table.item(row, 0).text()
        if QMessageBox.question(self, "Confirm Restore",
                                f"Are you sure you want to restore requisition <b>{req_id}</b>?\nThis will re-create its inventory transaction.",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            try:
                with self.engine.connect() as conn, conn.begin():
                    conn.execute(text(
                        "UPDATE requisition_logbook SET is_deleted = FALSE, edited_by = :user, edited_on = NOW() WHERE req_id = :req_id"),
                                 {"req_id": req_id, "user": self.username})
                    restored_data = conn.execute(text("SELECT * FROM requisition_logbook WHERE req_id = :req_id"),
                                                 {"req_id": req_id}).mappings().first()
                    if not restored_data: raise Exception("Failed to retrieve restored record data.")
                    self._update_or_create_transaction(conn, restored_data)
                self.log_audit_trail("RESTORE_REQUISITION",
                                     f"Restored requisition and re-created transaction for: {req_id}")
                QMessageBox.information(self, "Success", f"Requisition {req_id} has been restored.");
                self._load_deleted_records();
                self._load_all_records()
            except Exception as e:
                QMessageBox.critical(self, "Database Error", f"Failed to restore record: {e}")


# --- Placeholder for ProductDeliveryPage (replace with your full code) ---
class ProductDeliveryPage(QWidget):
    def __init__(self, db_engine, username, log_audit_trail_func):
        super().__init__()
        layout = QVBoxLayout(self)
        label = QLabel("Product Delivery Page Placeholder")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)


# --- Other Placeholder Pages ---
class FGEndorsementPage(QWidget):
    def __init__(self, db_engine, username, log_audit_trail_func):
        super().__init__()
        layout = QVBoxLayout(self);
        layout.addWidget(QLabel("FG Endorsement Page", alignment=Qt.AlignmentFlag.AlignCenter))


class OutgoingFormPage(QWidget):
    def __init__(self, db_engine, username, log_audit_trail_func):
        super().__init__()
        layout = QVBoxLayout(self);
        layout.addWidget(QLabel("Outgoing Form Page", alignment=Qt.AlignmentFlag.AlignCenter))


class RRFPage(QWidget):
    def __init__(self, db_engine, username, log_audit_trail_func):
        super().__init__()
        layout = QVBoxLayout(self);
        layout.addWidget(QLabel("RRF Page", alignment=Qt.AlignmentFlag.AlignCenter))


class ReceivingReportPage(QWidget):
    def __init__(self, db_engine, username, log_audit_trail_func):
        super().__init__()
        layout = QVBoxLayout(self);
        layout.addWidget(QLabel("Receiving Report Page", alignment=Qt.AlignmentFlag.AlignCenter))


class QCFailedPassedPage(QWidget):
    def __init__(self, db_engine, username, log_audit_trail_func):
        super().__init__()
        layout = QVBoxLayout(self);
        layout.addWidget(QLabel("QC Failed -> Passed Page", alignment=Qt.AlignmentFlag.AlignCenter))


class QCExcessEndorsementPage(QWidget):
    def __init__(self, db_engine, username, log_audit_trail_func):
        super().__init__()
        layout = QVBoxLayout(self);
        layout.addWidget(QLabel("QC Excess Endorsement Page", alignment=Qt.AlignmentFlag.AlignCenter))


class QCFailedEndorsementPage(QWidget):
    def __init__(self, db_engine, username, log_audit_trail_func):
        super().__init__()
        layout = QVBoxLayout(self);
        layout.addWidget(QLabel("QC Failed Endorsement Page", alignment=Qt.AlignmentFlag.AlignCenter))


class TransactionsFormPage(QWidget):
    def __init__(self, db_engine, username, log_audit_trail_func):
        super().__init__()
        layout = QVBoxLayout(self);
        layout.addWidget(QLabel("Transactions Form Page", alignment=Qt.AlignmentFlag.AlignCenter))


class FailedTransactionsFormPage(QWidget):
    def __init__(self, db_engine, username, log_audit_trail_func):
        super().__init__()
        layout = QVBoxLayout(self);
        layout.addWidget(QLabel("Failed Transactions Form Page", alignment=Qt.AlignmentFlag.AlignCenter))


class AuditTrailPage(QWidget):
    def __init__(self, db_engine):
        super().__init__()
        layout = QVBoxLayout(self);
        layout.addWidget(QLabel("Audit Trail Page", alignment=Qt.AlignmentFlag.AlignCenter))


class UserManagementPage(QWidget):
    def __init__(self, db_engine, username, log_audit_trail_func):
        super().__init__()
        layout = QVBoxLayout(self);
        layout.addWidget(QLabel("User Management Page", alignment=Qt.AlignmentFlag.AlignCenter))


# =========================================================================================
# === MAIN APPLICATION WINDOW AND LOGIN
# =========================================================================================
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
        pixmap = IconProvider.get_pixmap(IconProvider.LOGIN_FORM_ICON, AppStyles.PRIMARY_ACCENT_COLOR, QSize(150, 150));
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
        pixmap = IconProvider.get_pixmap(icon_name, '#bdbdbd', QSize(20, 20));
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
            self.status_label.setText("Database connection error."); print(f"Login Error: {e}")
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
    EXPANDED_MENU_WIDTH = 230
    COLLAPSED_MENU_WIDTH = 60

    def __init__(self, username, user_role, login_window):
        super().__init__()
        self.username, self.user_role, self.login_window = username, user_role, login_window
        self.icon_maximize = IconProvider.get_icon(IconProvider.MAXIMIZE, color='#ecf0f1')
        self.icon_restore = IconProvider.get_icon(IconProvider.RESTORE, color='#ecf0f1')
        self.setWindowTitle("Finished Goods Program");
        self.setWindowIcon(IconProvider.get_icon(IconProvider.WINDOW_ICON, color='gray'));
        self.setMinimumSize(1280, 720);
        self.setGeometry(100, 100, 1366, 768)
        self.workstation_info = self._get_workstation_info()
        self.sync_thread, self.sync_worker = None, None
        self.customer_sync_thread, self.customer_sync_worker = None, None
        self.delivery_sync_thread, self.delivery_sync_worker = None, None
        self.rrf_sync_thread, self.rrf_sync_worker = None, None
        self.is_menu_expanded = True;
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
            with engine.connect() as connection:
                with connection.begin(): connection.execute(text(
                    "INSERT INTO qc_audit_trail (timestamp, username, action_type, details, hostname, ip_address, mac_address) VALUES (NOW(), :u, :a, :d, :h, :i, :m)"),
                                                            {"u": self.username, "a": action_type, "d": details,
                                                             **self.workstation_info})
        except Exception as e:
            print(f"CRITICAL: Audit trail error: {e}")

    def init_ui(self):
        main_widget = QWidget();
        main_layout = QHBoxLayout(main_widget);
        main_layout.setContentsMargins(0, 0, 0, 0);
        main_layout.setSpacing(0)
        self.side_menu = self.create_side_menu();
        main_layout.addWidget(self.side_menu)
        self.stacked_widget = QStackedWidget();
        main_layout.addWidget(self.stacked_widget)
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
        pages = [self.fg_endorsement_page, self.transactions_page, self.failed_transactions_page,
                 self.outgoing_form_page, self.rrf_page, self.receiving_report_page, self.qc_failed_passed_page,
                 self.qc_excess_page, self.qc_failed_endorsement_page, self.product_delivery_page,
                 self.requisition_logbook_page, self.audit_trail_page, self.user_management_page]
        for page in pages: self.stacked_widget.addWidget(page)
        self.setCentralWidget(main_widget);
        self.setup_status_bar();
        self.apply_styles()
        if self.user_role != 'Admin': self.btn_user_mgmt.hide()
        self.update_maximize_button();
        self.show_page(0);
        self.btn_fg_endorsement.setChecked(True)

    def create_side_menu(self):
        self.menu_buttons = [];
        menu = QWidget(objectName="SideMenu");
        menu.setMinimumWidth(self.EXPANDED_MENU_WIDTH);
        layout = QVBoxLayout(menu);
        layout.setContentsMargins(5, 10, 5, 10);
        layout.setSpacing(3);
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.btn_toggle_menu = QPushButton(icon=IconProvider.get_icon(IconProvider.MENU_TOGGLE, color='#ecf0f1'));
        self.btn_toggle_menu.clicked.connect(self.toggle_side_menu);
        self.btn_toggle_menu.setStyleSheet(
            "background-color: transparent; border: none; text-align: left; padding: 5px 5px 5px 15px;");
        self.btn_toggle_menu.setIconSize(QSize(20, 20));
        layout.addWidget(self.btn_toggle_menu);
        layout.addSpacing(5)
        profile = QWidget();
        pl = QHBoxLayout(profile);
        pl.setContentsMargins(10, 0, 0, 0);
        pl.setAlignment(Qt.AlignmentFlag.AlignLeft);
        pixmap = IconProvider.get_pixmap(IconProvider.USER_PROFILE, '#ecf0f1', QSize(36, 36));
        pl.addWidget(QLabel(pixmap=pixmap));
        profile_text_layout = QVBoxLayout();
        profile_text_layout.setSpacing(0)
        self.profile_name_label = QLabel(f"{self.username}", objectName="ProfileName");
        self.profile_role_label = QLabel(f"{self.user_role}", objectName="ProfileRole");
        profile_text_layout.addWidget(self.profile_name_label);
        profile_text_layout.addWidget(self.profile_role_label);
        pl.addLayout(profile_text_layout);
        layout.addWidget(profile);
        layout.addSpacing(10)
        self.btn_fg_endorsement = self.create_menu_button("  FG Endorsement", IconProvider.FG_ENDORSEMENT, 0);
        self.btn_transactions = self.create_menu_button("  Log Transaction", IconProvider.TRANSACTIONS, 1);
        self.btn_failed_transactions = self.create_menu_button("  FG Failed Log", IconProvider.FAILED_TRANSACTIONS, 2);
        self.btn_outgoing_form = self.create_menu_button("  Outgoing Form", IconProvider.OUTGOING_FORM, 3)
        self.btn_rrf = self.create_menu_button("  RRF Form", IconProvider.RRF_FORM, 4);
        self.btn_receiving_report = self.create_menu_button("  Receiving Report", IconProvider.RECEIVING_REPORT, 5);
        self.btn_qc_failed_passed = self.create_menu_button("  QC Failed->Passed", IconProvider.QC_PASSED, 6);
        self.btn_qc_excess = self.create_menu_button("  QC Excess", IconProvider.QC_EXCESS, 7);
        self.btn_qc_failed = self.create_menu_button("  QC Failed", IconProvider.QC_FAILED, 8)
        self.btn_product_delivery = self.create_menu_button("  Product Delivery", IconProvider.PRODUCT_DELIVERY, 9);
        self.btn_requisition_logbook = self.create_menu_button("  Requisition Logbook", IconProvider.REQUISITION, 10);
        self.btn_sync_prod = self.create_menu_button("  Sync Production", IconProvider.SYNC, -1,
                                                     self.start_sync_process)
        self.btn_sync_customers = self.create_menu_button("  Sync Customers", IconProvider.CUSTOMERS, -1,
                                                          self.start_customer_sync_process);
        self.btn_sync_deliveries = self.create_menu_button("  Sync Deliveries", IconProvider.DELIVERIES, -1,
                                                           self.start_delivery_sync_process);
        self.btn_sync_rrf = self.create_menu_button("  Sync RRF", IconProvider.RRF_SYNC, -1,
                                                    self.start_rrf_sync_process)
        self.btn_audit_trail = self.create_menu_button("  Audit Trail", IconProvider.AUDIT_TRAIL, 11);
        self.btn_user_mgmt = self.create_menu_button("  User Management", IconProvider.USER_MANAGEMENT, 12);
        self.btn_maximize = self.create_menu_button("  Maximize", IconProvider.MAXIMIZE, -1, self.toggle_maximize)
        self.btn_logout = self.create_menu_button("  Logout", IconProvider.LOGOUT, -1, self.logout);
        self.btn_exit = self.create_menu_button("  Exit", IconProvider.EXIT, -1, self.exit_application)
        layout.addWidget(self.btn_fg_endorsement);
        layout.addWidget(self.btn_transactions);
        layout.addWidget(self.btn_failed_transactions);
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
        separator1.setStyleSheet("background-color: #34495e; margin: 8px 5px;");
        layout.addWidget(separator1)
        layout.addWidget(self.btn_sync_prod);
        layout.addWidget(self.btn_sync_customers);
        layout.addWidget(self.btn_sync_deliveries);
        layout.addWidget(self.btn_sync_rrf);
        separator2 = QFrame();
        separator2.setFrameShape(QFrame.Shape.HLine);
        separator2.setFixedHeight(1);
        separator2.setStyleSheet("background-color: #34495e; margin: 8px 5px;");
        layout.addWidget(separator2)
        layout.addWidget(self.btn_audit_trail);
        layout.addWidget(self.btn_user_mgmt);
        layout.addStretch(1);
        layout.addWidget(self.btn_maximize);
        layout.addWidget(self.btn_logout);
        layout.addWidget(self.btn_exit)
        return menu

    def create_menu_button(self, text, icon_name, page_index, on_click_func=None):
        btn = QPushButton(text, icon=IconProvider.get_icon(icon_name, color='#ecf0f1'));
        btn.setProperty("fullText", text);
        btn.setIconSize(QSize(20, 20))
        if page_index != -1:
            btn.setCheckable(True); btn.setAutoExclusive(True); btn.clicked.connect(lambda: self.show_page(page_index))
        else:
            if on_click_func: btn.clicked.connect(on_click_func)
        self.menu_buttons.append(btn);
        return btn

    def toggle_side_menu(self):
        start_width = self.side_menu.width();
        end_width = self.COLLAPSED_MENU_WIDTH if self.is_menu_expanded else self.EXPANDED_MENU_WIDTH
        if self.is_menu_expanded: self.profile_name_label.setVisible(False); self.profile_role_label.setVisible(
            False); [button.setText("") for button in self.menu_buttons]
        self.animation = QPropertyAnimation(self.side_menu, b"minimumWidth");
        self.animation.setDuration(300);
        self.animation.setStartValue(start_width);
        self.animation.setEndValue(end_width);
        self.animation.finished.connect(self.on_menu_animation_finished);
        self.animation.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def create_status_widget(self, icon_name, initial_text, icon_color='#6c757d'):
        widget = QWidget();
        layout = QHBoxLayout(widget);
        layout.setContentsMargins(5, 0, 5, 0);
        layout.setSpacing(5);
        icon_label = QLabel();
        icon_label.setPixmap(IconProvider.get_pixmap(icon_name, icon_color, QSize(12, 12)));
        text_label = QLabel(initial_text);
        layout.addWidget(icon_label);
        layout.addWidget(text_label);
        widget.icon_label = icon_label;
        widget.text_label = text_label;
        return widget

    def setup_status_bar(self):
        self.status_bar = QStatusBar();
        self.setStatusBar(self.status_bar);
        self.status_bar.showMessage(f"Ready | Logged in as: {self.username}")
        if PSUTIL_AVAILABLE: self.network_widget = NetworkGraphWidget(); self.status_bar.addPermanentWidget(
            self.network_widget); separator_net = QFrame(); separator_net.setFrameShape(
            QFrame.Shape.VLine); separator_net.setFrameShadow(QFrame.Shadow.Sunken); self.status_bar.addPermanentWidget(
            separator_net)
        self.db_status_widget = self.create_status_widget(IconProvider.DATABASE, "Connecting...");
        self.status_bar.addPermanentWidget(self.db_status_widget);
        separator1 = QFrame();
        separator1.setFrameShape(QFrame.Shape.VLine);
        separator1.setFrameShadow(QFrame.Shadow.Sunken);
        self.status_bar.addPermanentWidget(separator1)
        workstation_widget = self.create_status_widget(IconProvider.DESKTOP, self.workstation_info['h']);
        workstation_widget.setToolTip(f"IP: {self.workstation_info['i']}\nMAC: {self.workstation_info['m']}");
        self.status_bar.addPermanentWidget(workstation_widget);
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

    def start_sync_process(self):
        if QMessageBox.question(self, "Confirm Sync", "This will sync legacy production data. Continue?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.No: return
        self.btn_sync_prod.setEnabled(False);
        self.loading_dialog = self._create_loading_dialog();
        self.sync_thread = QThread();
        self.sync_worker = SyncWorker();
        self.sync_worker.moveToThread(self.sync_thread);
        self.sync_thread.started.connect(self.sync_worker.run);
        self.sync_worker.finished.connect(self.on_sync_finished);
        self.sync_worker.finished.connect(self.sync_thread.quit);
        self.sync_worker.finished.connect(self.sync_worker.deleteLater);
        self.sync_thread.finished.connect(self.sync_thread.deleteLater);
        self.sync_thread.start();
        self.loading_dialog.exec()

    def start_customer_sync_process(self):
        if QMessageBox.question(self, "Confirm Sync", "This will sync customer data. Continue?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.No: return
        self.btn_sync_customers.setEnabled(False);
        self.loading_dialog = self._create_loading_dialog();
        self.customer_sync_thread = QThread();
        self.customer_sync_worker = SyncCustomerWorker();
        self.customer_sync_worker.moveToThread(self.customer_sync_thread);
        self.customer_sync_thread.started.connect(self.customer_sync_worker.run);
        self.customer_sync_worker.finished.connect(self.on_customer_sync_finished);
        self.customer_sync_worker.finished.connect(self.customer_sync_thread.quit);
        self.customer_sync_worker.finished.connect(self.customer_sync_worker.deleteLater);
        self.customer_sync_thread.finished.connect(self.customer_sync_thread.deleteLater);
        self.customer_sync_thread.start();
        self.loading_dialog.exec()

    def start_delivery_sync_process(self):
        if QMessageBox.question(self, "Confirm Sync", "This will sync delivery records. Continue?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.No: return
        self.btn_sync_deliveries.setEnabled(False);
        self.loading_dialog = self._create_loading_dialog();
        self.delivery_sync_thread = QThread();
        self.delivery_sync_worker = SyncDeliveryWorker();
        self.delivery_sync_worker.moveToThread(self.delivery_sync_thread);
        self.delivery_sync_thread.started.connect(self.delivery_sync_worker.run);
        self.delivery_sync_worker.finished.connect(self.on_delivery_sync_finished);
        self.delivery_sync_worker.finished.connect(self.delivery_sync_thread.quit);
        self.delivery_sync_worker.finished.connect(self.delivery_sync_worker.deleteLater);
        self.delivery_sync_thread.finished.connect(self.delivery_sync_thread.deleteLater);
        self.delivery_sync_thread.start();
        self.loading_dialog.exec()

    def start_rrf_sync_process(self):
        if QMessageBox.question(self, "Confirm Sync", "This will sync RRF records. Continue?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.No: return
        self.btn_sync_rrf.setEnabled(False);
        self.loading_dialog = self._create_loading_dialog();
        self.rrf_sync_thread = QThread();
        self.rrf_sync_worker = SyncRRFWorker();
        self.rrf_sync_worker.moveToThread(self.rrf_sync_thread);
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
        dialog.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground);
        layout = QVBoxLayout(dialog);
        frame = QFrame();
        frame.setStyleSheet("background-color: white; border-radius: 15px; padding: 20px;");
        frame_layout = QVBoxLayout(frame);
        loading_label = QLabel("Loading...");
        loading_label.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold));
        message_label = QLabel("Syncing... Please wait.");
        message_label.setStyleSheet("font-size: 11pt;");
        frame_layout.addWidget(loading_label, alignment=Qt.AlignmentFlag.AlignCenter);
        frame_layout.addWidget(message_label, alignment=Qt.AlignmentFlag.AlignCenter);
        layout.addWidget(frame);
        return dialog

    def on_menu_animation_finished(self):
        self.is_menu_expanded = not self.is_menu_expanded; self.restore_menu_texts()

    def restore_menu_texts(self):
        if self.is_menu_expanded: self.profile_name_label.setVisible(True); self.profile_role_label.setVisible(True); [
            button.setText(button.property("fullText")) for button in self.menu_buttons]

    def on_sync_finished(self, success, message):
        self.loading_dialog.close(); self.btn_sync_prod.setEnabled(True); QMessageBox.information(self, "Sync Result",
                                                                                                  message) if success else QMessageBox.critical(
            self, "Sync Result", message)

    def on_customer_sync_finished(self, success, message):
        self.loading_dialog.close();
        self.btn_sync_customers.setEnabled(True)
        if success:
            QMessageBox.information(self, "Sync Result", message)
            if hasattr(self.product_delivery_page,
                       '_load_combobox_data'): self.product_delivery_page._load_combobox_data()
            if hasattr(self.rrf_page, '_load_combobox_data'): self.rrf_page._load_combobox_data()
        else:
            QMessageBox.critical(self, "Sync Result", message)

    def on_delivery_sync_finished(self, success, message):
        self.loading_dialog.close();
        self.btn_sync_deliveries.setEnabled(True)
        if success:
            QMessageBox.information(self, "Sync Result", message)
            if self.stacked_widget.currentWidget() == self.product_delivery_page: self.product_delivery_page._load_all_records()
        else:
            QMessageBox.critical(self, "Sync Result", message)

    def on_rrf_sync_finished(self, success, message):
        self.loading_dialog.close();
        self.btn_sync_rrf.setEnabled(True)
        if success:
            QMessageBox.information(self, "Sync Result", message)
            if self.stacked_widget.currentWidget() == self.rrf_page: self.rrf_page._load_all_records()
        else:
            QMessageBox.critical(self, "Sync Result", message)

    def update_time(self):
        self.time_widget.text_label.setText(datetime.now().strftime('%b %d, %Y  %I:%M:%S %p'))

    def check_db_status(self):
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            pixmap = IconProvider.get_pixmap(IconProvider.SUCCESS, '#28a745', QSize(12, 12));
            self.db_status_widget.icon_label.setPixmap(pixmap);
            self.db_status_widget.text_label.setText("DB Connected");
            self.db_status_widget.setToolTip("Database connection is stable.")
        except Exception as e:
            pixmap = IconProvider.get_pixmap(IconProvider.ERROR, '#dc3545', QSize(12, 12));
            self.db_status_widget.icon_label.setPixmap(pixmap);
            self.db_status_widget.text_label.setText("DB Disconnected");
            self.db_status_widget.setToolTip(f"Database connection failed.\nError: {e}")

    def apply_styles(self):
        self.setStyleSheet(AppStyles.MAIN_WINDOW_STYLESHEET)

    def show_page(self, index):
        if self.stacked_widget.currentIndex() == index: return
        self.stacked_widget.setCurrentIndex(index);
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
        if QMessageBox.question(self, 'Confirm Exit', 'Are you sure you want to exit?',
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes: self.log_audit_trail(
            "LOGOUT", "User exited application."); QApplication.instance().quit()

    def closeEvent(self, event):
        for thread in [self.sync_thread, self.customer_sync_thread, self.delivery_sync_thread, self.rrf_sync_thread]:
            if thread and thread.isRunning(): thread.quit(); thread.wait()
        event.accept()


# =========================================================================================
# === APPLICATION ENTRY POINT
# =========================================================================================
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
        # Initial state is expanded, so we toggle once to collapse it to the icon-only view
        main_window.toggle_side_menu()


    login_window.login_successful.connect(on_login_success)
    login_window.show()
    sys.exit(app.exec())