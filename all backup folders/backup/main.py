# main-old.py

import sys
import os
import re
from datetime import datetime
import socket
import uuid
import dbfread
import time
import traceback

from sqlalchemy import create_engine, text

try:
    import qtawesome as fa
except ImportError:
    print("FATAL ERROR: The 'qtawesome' library is required. Please install it using: pip install qtawesome")
    sys.exit(1)

from PyQt6.QtCore import (Qt, pyqtSignal, QSize, QEvent, QTimer, QThread, QObject)
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, QLineEdit, QPushButton,
                             QMessageBox, QVBoxLayout, QHBoxLayout, QStackedWidget,
                             QFrame, QStatusBar, QDialog)
from PyQt6.QtGui import QFont, QMovie, QIcon

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
    # ... (AppStyles class remains unchanged) ...
    """A class to hold all the stylesheet strings for the application."""
    PRIMARY_ACCENT_COLOR = "#4D7BFF"  # Indigo
    PRIMARY_ACCENT_HOVER = "#4066d4"
    SECONDARY_ACCENT_COLOR = "#2a9d8f"  # Green
    SECONDARY_ACCENT_HOVER = "#268d81"
    DESTRUCTIVE_COLOR = "#e63946"  # Red
    DESTRUCTIVE_COLOR_HOVER = "#d62828"
    NEUTRAL_COLOR = "#6c757d"  # Gray
    NEUTRAL_COLOR_HOVER = "#5a6268"

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
    MAIN_WINDOW_STYLESHEET = f"""
        QMainWindow, QStackedWidget > QWidget {{
            background-color: #f4f7fc; /* A very light, cool gray */
        }}
        QWidget {{
            font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
            font-size: 10pt;
            color: #333;
        }}
        /* === Side Menu Styling === */
        QWidget#SideMenu {{
            background-color: #2c3e50;
            color: #ecf0f1;
            width: 230px; /* Slightly wider */
        }}
        /* ADJUSTMENT: Reduced general label font size for compactness */
        #SideMenu QLabel {{ color: #ecf0f1; font-family: "Segoe UI"; font-size: 9pt; background: transparent; }}

        /* ADJUSTMENT: Reduced padding and margin-top to save vertical space */
        #SideMenu #MenuLabel {{
            font-size: 9pt;
            font-weight: bold;
            color: #95a5a6; /* Lighter gray for headers */
            padding: 10px 10px 4px 15px; /* Reduced vertical padding */
            margin-top: 8px; /* Reduced margin */
            border-top: 1px solid #34495e;
        }}

        /* ADJUSTMENT: Reduced padding and font size for all buttons to fit 768p screens */
        #SideMenu QPushButton {{
            background-color: transparent;
            color: #ecf0f1;
            border: none;
            padding: 9px 9px 9px 25px; /* Reduced vertical padding, kept left padding for icon */
            text-align: left;
            font-size: 9pt; /* Reduced font size */
            font-weight: normal; /* Normal weight for readability */
            border-radius: 6px;
        }}
        #SideMenu QPushButton:hover {{ background-color: #34495e; }}
        #SideMenu QPushButton:checked {{
            background-color: {PRIMARY_ACCENT_COLOR};
            font-weight: bold;
            color: white;
        }}

        /* ADJUSTMENT: Reduced font size for profile name for a more compact header */
        #SideMenu #ProfileName {{ font-weight: bold; font-size: 10pt; }}
        #SideMenu #ProfileRole {{ color: #bdc3c7; font-size: 9pt; }}

        /* === Main Content Area Widgets === */
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
        QLineEdit, QComboBox, QDateEdit, QDateTimeEdit, QPlainTextEdit {{
            border: 1px solid #d1d9e6; padding: 8px; border-radius: 5px;
            background-color: #ffffff;
            selection-background-color: #8eb3ff;
        }}
        QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QPlainTextEdit:focus {{
            border: 1px solid {PRIMARY_ACCENT_COLOR};
        }}
        QLineEdit[readOnly="true"] {{ background-color: #eff2f7; color: #6c757d; }}

        /* === Button Styling === */
        QPushButton {{
            border: none; padding: 9px 18px; border-radius: 6px;
            font-weight: bold; color: white;
            background-color: {NEUTRAL_COLOR}; /* Default to neutral gray */
        }}
        QPushButton:hover {{ background-color: {NEUTRAL_COLOR_HOVER}; opacity: 0.95; }}
        QPushButton:pressed {{ transform: scale(0.98); }}

        /* Primary Action Buttons (Indigo) */
        QPushButton#PrimaryButton, #save_btn, #update_btn, #save_breakdown_btn, #scan_btn {{
            background-color: {PRIMARY_ACCENT_COLOR};
        }}
        QPushButton#PrimaryButton:hover, #save_btn:hover, #update_btn:hover, #save_breakdown_btn:hover, #scan_btn:hover {{
            background-color: {PRIMARY_ACCENT_HOVER};
        }}


        /* Destructive Action Buttons (Red) */
        #delete_btn, #remove_item_btn {{ background-color: {DESTRUCTIVE_COLOR}; }}
        #delete_btn:hover, #remove_item_btn:hover {{ background-color: {DESTRUCTIVE_COLOR_HOVER}; }}

        /* Secondary/Positive Action Buttons (Green) */
        QPushButton#SecondaryButton, #print_btn, #preview_btn {{
            background-color: {SECONDARY_ACCENT_COLOR};
        }}
        QPushButton#SecondaryButton:hover, #print_btn:hover, #preview_btn:hover {{
            background-color: {SECONDARY_ACCENT_HOVER};
        }}

        /* === Table Styling === */
        QTableWidget {{
            border: none; background-color: #ffffff;
            selection-behavior: SelectRows; color: #212529;
        }}
        QTableWidget::item {{ border-bottom: 1px solid #f4f7fc; padding: 10px; }}
        QTableWidget::item:selected {{ background-color: #e2e9ff; color: #212529; }}
        QHeaderView::section {{
            background-color: #ffffff; color: #6c757d; padding: 8px;
            border: none; border-bottom: 2px solid #e0e5eb;
            font-weight: bold; text-align: left;
        }}

        /* === Tab Styling === */
        QTabWidget::pane {{
            border: 1px solid #e0e5eb; border-top: none;
            background-color: #ffffff; padding: 10px;
        }}
        QTabBar::tab {{
            background-color: transparent; color: {NEUTRAL_COLOR};
            padding: 10px 20px; border: none;
            border-bottom: 2px solid transparent; margin-right: 4px;
            font-weight: bold;
        }}
        QTabBar::tab:selected {{ color: {PRIMARY_ACCENT_COLOR}; border-bottom: 2px solid {PRIMARY_ACCENT_COLOR}; }}
        QTabBar::tab:hover {{ color: {PRIMARY_ACCENT_COLOR}; background-color: #f4f7fc; }}

        /* === StatusBar Styling === */
        QStatusBar, QStatusBar QLabel {{
            background-color: #e9ecef;
            color: #333;
            font-size: 9pt;
            padding: 2px 5px;
        }}
    """


# ... (SyncWorker and SyncCustomerWorker remain unchanged) ...
class SyncWorker(QObject):
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


# --- CORRECTED SyncDeliveryWorker ---
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

                    # The T_DESC fields contain all descriptive text, including lot numbers
                    attachments = "\n".join(
                        filter(None, [str(item_rec.get(f'T_DESC{i}', '')).strip() for i in range(1, 5)]))

                    items_by_dr[dr_num].append({
                        "dr_no": dr_num, "quantity": self._to_float(item_rec.get('T_TOTALWT')),
                        "unit": str(item_rec.get('T_TOTALWTU', '')).strip(),
                        "product_code": str(item_rec.get('T_PRODCODE', '')).strip(),
                        "product_color": str(item_rec.get('T_PRODCOLO', '')).strip(),
                        "no_of_packing": self._to_float(item_rec.get('T_NUMPACKI')),
                        "weight_per_pack": self._to_float(item_rec.get('T_WTPERPAC')),
                        "attachments": attachments
                        # The old `lot_numbers` field is intentionally removed
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
                        # CORRECTED INSERT statement, removing lot_numbers
                        conn.execute(text("""
                            INSERT INTO product_delivery_items (dr_no, quantity, unit, product_code, product_color, no_of_packing, weight_per_pack, attachments)
                            VALUES (:dr_no, :quantity, :unit, :product_code, :product_color, :no_of_packing, :weight_per_pack, :attachments)
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


# ... (SyncRRFWorker remains unchanged) ...
class SyncRRFWorker(QObject):
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
    # ... (This function is the same as the corrected one provided previously)
    """
    Initializes the database schema with the correct table structures.
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

                # --- CORRECTED Product Delivery Tables ---
                connection.execute(text("""
                    CREATE TABLE IF NOT EXISTS product_delivery_primary (
                        id SERIAL PRIMARY KEY, 
                        dr_no TEXT NOT NULL UNIQUE, 
                        dr_type VARCHAR(50) DEFAULT 'Standard DR' NOT NULL,
                        delivery_date DATE, 
                        customer_name TEXT, 
                        deliver_to TEXT, 
                        address TEXT, 
                        po_no TEXT, 
                        order_form_no TEXT, 
                        fg_out_id TEXT, 
                        terms TEXT, 
                        prepared_by TEXT, 
                        encoded_by TEXT, 
                        encoded_on TIMESTAMP, 
                        edited_by TEXT, 
                        edited_on TIMESTAMP, 
                        is_deleted BOOLEAN NOT NULL DEFAULT FALSE, 
                        is_printed BOOLEAN NOT NULL DEFAULT FALSE
                    );
                """))
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
                        attachments TEXT, 
                        unit_price NUMERIC(15, 6),
                        description_1 TEXT,
                        description_2 TEXT,
                        lot_no_1 TEXT,
                        lot_no_2 TEXT,
                        lot_no_3 TEXT,
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
                connection.execute(text(
                    "CREATE TABLE IF NOT EXISTS requisition_logbook (id SERIAL PRIMARY KEY, req_id TEXT NOT NULL UNIQUE, manual_ref_no TEXT, category TEXT, request_date DATE, requester_name TEXT, department TEXT, product_code TEXT, lot_no TEXT, quantity_kg NUMERIC(15, 6), status TEXT, approved_by TEXT, remarks TEXT, encoded_by TEXT, encoded_on TIMESTAMP, edited_by TEXT, edited_on TIMESTAMP, is_deleted BOOLEAN NOT NULL DEFAULT FALSE);"))
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

                # --- Populate Default Data ---
                connection.execute(text("INSERT INTO warehouses (name) VALUES (:name) ON CONFLICT (name) DO NOTHING;"),
                                   [{"name": "WH1"}, {"name": "WH2"}, {"name": "WH4"}])
                connection.execute(text(
                    "INSERT INTO users (username, password, role) VALUES (:user, :pwd, :role) ON CONFLICT (username) DO NOTHING;"),
                    [{"user": "admin", "pwd": "itadmin", "role": "Admin"},
                     {"user": "itsup", "pwd": "itsup", "role": "Editor"}])

        print("Database initialized successfully.")
    except Exception as e:
        QApplication(sys.argv)
        QMessageBox.critical(None, "DB Init Error", f"Could not initialize database: {e}\n\n{traceback.format_exc()}")
        sys.exit(1)


# ... (LoginWindow and ModernMainWindow classes remain unchanged, as do the execution block)
class LoginWindow(QMainWindow):
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
    def __init__(self, username, user_role, login_window):
        super().__init__()
        self.username, self.user_role, self.login_window = username, user_role, login_window
        self.icon_maximize, self.icon_restore = fa.icon('fa5s.expand-arrows-alt', color='#ecf0f1'), fa.icon(
            'fa5s.compress-arrows-alt', color='#ecf0f1')
        self.icon_db_ok, self.icon_db_fail = fa.icon('fa5s.check-circle', color='#4CAF50'), fa.icon('fa5s.times-circle',
                                                                                                    color='#D32F2F')
        self.setWindowTitle("Finished Goods Program");
        self.setWindowIcon(fa.icon('fa5s.check-double', color='gray'));
        self.setMinimumSize(1280, 720);
        self.setGeometry(100, 100, 1366, 768)
        self.workstation_info = self._get_workstation_info()
        self.sync_thread, self.sync_worker = None, None
        self.customer_sync_thread, self.customer_sync_worker = None, None
        self.delivery_sync_thread, self.delivery_sync_worker = None, None
        self.rrf_sync_thread, self.rrf_sync_worker = None, None
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
        main_layout.addWidget(self.create_side_menu())
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
        self.audit_trail_page = AuditTrailPage(engine)
        self.user_management_page = UserManagementPage(engine, self.username, self.log_audit_trail)

        # Add pages to Stacked Widget in order
        pages = [
            self.fg_endorsement_page,
            self.outgoing_form_page,
            self.rrf_page,
            self.receiving_report_page,
            self.qc_failed_passed_page,
            self.qc_excess_page,
            self.qc_failed_endorsement_page,
            self.product_delivery_page,
            self.requisition_logbook_page,
            self.audit_trail_page,
            self.user_management_page
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
        menu = QWidget(objectName="SideMenu");
        layout = QVBoxLayout(menu);
        layout.setContentsMargins(10, 15, 10, 10);
        layout.setSpacing(3);
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        profile = QWidget();
        pl = QHBoxLayout(profile);
        pl.setContentsMargins(5, 0, 0, 0);
        pl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        pl.addWidget(QLabel(pixmap=fa.icon('fa5s.user-circle', color='#ecf0f1').pixmap(QSize(36, 36))));

        profile_text_layout = QVBoxLayout()
        profile_text_layout.setSpacing(0)
        profile_text_layout.addWidget(QLabel(f"{self.username}", objectName="ProfileName"))
        profile_text_layout.addWidget(QLabel(f"{self.user_role}", objectName="ProfileRole"))
        pl.addLayout(profile_text_layout)

        # Create buttons with updated page indices
        self.btn_fg_endorsement = self.create_menu_button("  FG Endorsement", 'fa5s.file-signature', 0)
        self.btn_outgoing_form = self.create_menu_button("  Outgoing Form", 'fa5s.sign-out-alt', 1)
        self.btn_rrf = self.create_menu_button("  RRF Form", 'fa5s.undo-alt', 2)
        self.btn_receiving_report = self.create_menu_button("  Receiving Report", 'fa5s.truck-loading', 3)
        self.btn_qc_failed_passed = self.create_menu_button("  QC Failed->Passed", 'fa5s.flask', 4)
        self.btn_qc_excess = self.create_menu_button("  QC Excess", 'fa5s.box', 5)
        self.btn_qc_failed = self.create_menu_button("  QC Failed", 'fa5s.times-circle', 6)
        self.btn_product_delivery = self.create_menu_button("  Product Delivery", 'fa5s.truck', 7)
        self.btn_requisition_logbook = self.create_menu_button("  Requisition Logbook", 'fa5s.book', 8)

        self.btn_sync_prod = self.create_menu_button("  Sync Production", 'fa5s.sync-alt', -1, self.start_sync_process)
        self.btn_sync_customers = self.create_menu_button("  Sync Customers", 'fa5s.address-book', -1,
                                                          self.start_customer_sync_process)
        self.btn_sync_deliveries = self.create_menu_button("  Sync Deliveries", 'fa5s.history', -1,
                                                           self.start_delivery_sync_process)
        self.btn_sync_rrf = self.create_menu_button("  Sync RRF", 'fa5s.retweet', -1, self.start_rrf_sync_process)

        self.btn_audit_trail = self.create_menu_button("  Audit Trail", 'fa5s.clipboard-list', 9)
        self.btn_user_mgmt = self.create_menu_button("  User Management", 'fa5s.users-cog', 10)

        self.btn_maximize = self.create_menu_button("  Maximize", 'fa5s.expand-arrows-alt', -1, self.toggle_maximize)
        self.btn_logout = self.create_menu_button("  Logout", 'fa5s.sign-out-alt', -1, self.logout)
        self.btn_exit = self.create_menu_button("  Exit", 'fa5s.power-off', -1, self.exit_application)

        # Add buttons to layout
        layout.addWidget(profile);
        layout.addWidget(QLabel("FG MANAGEMENT", objectName="MenuLabel"))
        layout.addWidget(self.btn_fg_endorsement)
        layout.addWidget(self.btn_outgoing_form)
        layout.addWidget(self.btn_rrf)
        layout.addWidget(self.btn_receiving_report)
        layout.addWidget(self.btn_qc_failed_passed)
        layout.addWidget(self.btn_qc_excess)
        layout.addWidget(self.btn_qc_failed)
        layout.addWidget(self.btn_product_delivery)
        layout.addWidget(self.btn_requisition_logbook)
        layout.addWidget(QLabel("DATA SYNC", objectName="MenuLabel"))
        layout.addWidget(self.btn_sync_prod);
        layout.addWidget(self.btn_sync_customers);
        layout.addWidget(self.btn_sync_deliveries);
        layout.addWidget(self.btn_sync_rrf);
        layout.addWidget(QLabel("SYSTEM", objectName="MenuLabel"))
        layout.addWidget(self.btn_audit_trail);
        layout.addWidget(self.btn_user_mgmt)
        layout.addStretch(1);
        layout.addWidget(self.btn_maximize);
        layout.addWidget(self.btn_logout)
        layout.addWidget(self.btn_exit)
        return menu

    def create_menu_button(self, text, icon, page_index, on_click_func=None):
        btn = QPushButton(text, icon=fa.icon(icon, color='#ecf0f1'))
        if page_index != -1:  # Page-switching button
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.clicked.connect(lambda: self.show_page(page_index))
        else:  # Action button
            if on_click_func:
                btn.clicked.connect(on_click_func)
        return btn

    def setup_status_bar(self):
        self.status_bar = QStatusBar();
        self.setStatusBar(self.status_bar);
        self.status_bar.showMessage(f"Ready | Logged in as: {self.username}")
        self.db_status_icon_label, self.db_status_text_label, self.time_label = QLabel(), QLabel(), QLabel()
        self.db_status_icon_label.setFixedSize(QSize(20, 20))
        for w in [self.db_status_icon_label, self.db_status_text_label, self.time_label,
                  QLabel(f" | PC: {self.workstation_info['h']}"), QLabel(f" | IP: {self.workstation_info['i']}"),
                  QLabel(f" | MAC: {self.workstation_info['m']}")]: self.status_bar.addPermanentWidget(w)
        self.time_timer = QTimer(self, timeout=self.update_time);
        self.time_timer.start(1000);
        self.update_time()
        self.db_check_timer = QTimer(self, timeout=self.check_db_status);
        self.db_check_timer.start(5000);
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

    def on_sync_finished(self, success, message):
        self.loading_dialog.close();
        self.btn_sync_prod.setEnabled(True)
        if success:
            QMessageBox.information(self, "Sync Result", message);
            self.status_bar.showMessage(
                "Production DB synchronized.", 5000)
        else:
            QMessageBox.critical(self, "Sync Result", message);
            self.status_bar.showMessage("Sync failed.", 5000)

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
            QMessageBox.critical(self, "Sync Result", message);
            self.status_bar.showMessage("Customer sync failed.", 5000)

    def on_delivery_sync_finished(self, success, message):
        self.loading_dialog.close();
        self.btn_sync_deliveries.setEnabled(True)
        if success:
            QMessageBox.information(self, "Sync Result", message);
            self.status_bar.showMessage("Delivery records synchronized.", 5000)
            if self.stacked_widget.currentWidget() == self.product_delivery_page: self.product_delivery_page._load_all_records()
        else:
            QMessageBox.critical(self, "Sync Result", message);
            self.status_bar.showMessage("Delivery sync failed.", 5000)

    def on_rrf_sync_finished(self, success, message):
        self.loading_dialog.close();
        self.btn_sync_rrf.setEnabled(True)
        if success:
            QMessageBox.information(self, "Sync Result", message);
            self.status_bar.showMessage("RRF records synchronized.", 5000)
            if self.stacked_widget.currentWidget() == self.rrf_page: self.rrf_page._load_all_records()
        else:
            QMessageBox.critical(self, "Sync Result", message);
            self.status_bar.showMessage("RRF sync failed.", 5000)

    def update_time(self):
        self.time_label.setText(f" | {datetime.now().strftime('%b %d, %Y  %I:%M:%S %p')} ")

    def check_db_status(self):
        try:
            with engine.connect() as c:
                c.execute(text("SELECT 1"))
            self.db_status_icon_label.setPixmap(self.icon_db_ok.pixmap(QSize(11, 11)));
            self.db_status_text_label.setText("DB Connected")
        except:
            self.db_status_icon_label.setPixmap(self.icon_db_fail.pixmap(QSize(11, 11)));
            self.db_status_text_label.setText("DB Disconnected")

    def apply_styles(self):
        self.setStyleSheet(AppStyles.MAIN_WINDOW_STYLESHEET)

    def show_page(self, index):
        if self.stacked_widget.currentIndex() == index: return
        self.stacked_widget.setCurrentIndex(index)
        current_widget = self.stacked_widget.widget(index)
        if hasattr(current_widget, 'refresh_page'): current_widget.refresh_page()
        if hasattr(current_widget, '_load_all_records'): current_widget._load_all_records()
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


    login_window.login_successful.connect(on_login_success)
    login_window.show()
    sys.exit(app.exec())