import traceback
import dbfread
from sqlalchemy import text
from PyQt6.QtCore import QObject, pyqtSignal

# Local Imports
from Others.database import engine
from Others.config import (
    PRODUCTION_DBF_PATH, CUSTOMER_DBF_PATH, DELIVERY_DBF_PATH,
    DELIVERY_ITEMS_DBF_PATH, RRF_PRIMARY_DBF_PATH, RRF_ITEMS_DBF_PATH
)

class SyncWorker(QObject):
    # (Your entire SyncWorker class code goes here, unchanged)
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
    # (Your entire SyncCustomerWorker class code goes here, unchanged)
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
    # (Your entire SyncDeliveryWorker class code goes here, unchanged)
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
    # (Your entire SyncRRFWorker class code goes here, unchanged)
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