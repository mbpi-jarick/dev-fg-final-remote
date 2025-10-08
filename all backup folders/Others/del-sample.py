import os
import sys
import traceback
import dbfread
from sqlalchemy import create_engine, text
from PyQt6.QtCore import QObject, pyqtSignal, QCoreApplication

# --- CONFIGURATION ---
# --- IMPORTANT: Update these details to match your environment ---
DB_CONFIG = {
    "host": "192.168.1.13",
    "port": 5432,
    "dbname": "dbfg",
    "user": "postgres",
    "password": "mbpi"
}
# --- Path to the shared folder containing the legacy DBF files ---
DBF_BASE_PATH = r'\\system-server\SYSTEM-NEW-OLD'
DELIVERY_DBF_PATH = os.path.join(DBF_BASE_PATH, 'tbl_del01.dbf')
DELIVERY_ITEMS_DBF_PATH = os.path.join(DBF_BASE_PATH, 'tbl_del02.dbf')

# --- DATABASE ENGINE SETUP ---
db_url = (
    f"postgresql+psycopg2://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
    f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}"
)
try:
    engine = create_engine(db_url, pool_pre_ping=True, pool_recycle=3600)
except Exception as e:
    print(f"FATAL: Could not create database engine. Error: {e}")
    exit(1)


def create_delivery_legacy_tables():
    """
    Creates the necessary PostgreSQL tables for storing the legacy delivery data.
    This function is idempotent and can be run safely multiple times.
    """
    print("Initializing database tables for legacy delivery data...")
    try:
        with engine.connect() as connection:
            with connection.begin():
                # Primary table for delivery headers
                connection.execute(text("""
                    CREATE TABLE IF NOT EXISTS product_delivery_primary (
                        id SERIAL PRIMARY KEY,
                        dr_no TEXT NOT NULL UNIQUE,
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
                print(" -> Table 'product_delivery_primary' checked/created.")

                # Items table for delivery details.
                connection.execute(text("""
                    DROP TABLE IF EXISTS product_delivery_items;
                    CREATE TABLE product_delivery_items (
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
                        lot_no_1 TEXT,
                        lot_no_2 TEXT,
                        lot_no_3 TEXT,
                        mfg_date TEXT,
                        alias_code TEXT,
                        alias_desc TEXT,
                        FOREIGN KEY (dr_no) REFERENCES product_delivery_primary (dr_no) ON DELETE CASCADE
                    );
                """))
                print(" -> Table 'product_delivery_items' (re)created.")

        print("\nDatabase tables for delivery initialized successfully.")
    except Exception as e:
        print(f"\nFATAL: Could not initialize delivery database tables: {e}")
        raise


class SyncDeliveryWorker(QObject):
    """
    A worker that syncs delivery data from legacy DBF files to PostgreSQL.
    Now includes print statements to show progress.
    """
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
        """Main execution method for the sync process with loading indicators."""
        print("\n--- Starting Legacy Delivery Sync ---")
        try:
            # --- Step 1: Process Delivery Items (tbl_del02.dbf) ---
            items_by_dr = {}
            print(f"Step 1: Reading items from '{os.path.basename(DELIVERY_ITEMS_DBF_PATH)}'")
            print("Processing item records: ", end='')
            item_count = 0
            with dbfread.DBF(DELIVERY_ITEMS_DBF_PATH, load=True, encoding='latin1') as dbf_items:
                for item_rec in dbf_items:
                    item_count += 1
                    # Add a dot for every 200 records to show progress without flooding the console
                    if item_count % 200 == 0:
                        print(".", end='', flush=True)

                    dr_num = self._get_safe_dr_num(item_rec.get('T_DRNUM'))
                    if not dr_num: continue
                    if dr_num not in items_by_dr: items_by_dr[dr_num] = []

                    attachments = "\n".join(
                        filter(None, [str(item_rec.get(f'T_DESC{i}', '')).strip() for i in range(1, 5)]))

                    items_by_dr[dr_num].append({
                        "dr_no": dr_num, "quantity": self._to_float(item_rec.get('T_TOTALWT')),
                        "unit": str(item_rec.get('T_TOTALWTU', '')).strip(),
                        "product_code": str(item_rec.get('T_PRODCODE', '')).strip(),
                        "product_color": str(item_rec.get('T_PRODCOLO', '')).strip(),
                        "no_of_packing": self._to_float(item_rec.get('T_NUMPACKI')),
                        "weight_per_pack": self._to_float(item_rec.get('T_WTPERPAC')), "lot_numbers": "",
                        "attachments": attachments
                    })
            print(f"\n-> Finished. Processed {item_count} total item records.")

            # --- Step 2: Process Primary Delivery Headers (tbl_del01.dbf) ---
            primary_recs = []
            print(f"\nStep 2: Reading headers from '{os.path.basename(DELIVERY_DBF_PATH)}'")
            print("Processing primary records: ", end='')
            primary_count = 0
            with dbfread.DBF(DELIVERY_DBF_PATH, load=True, encoding='latin1') as dbf_primary:
                for r in dbf_primary:
                    primary_count += 1
                    if primary_count % 200 == 0:
                        print(".", end='', flush=True)

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
                        "prepared_by": str(r.get('T_USERID', '')).strip(),
                        "encoded_on": r.get('T_DENCODED'),
                        "is_deleted": bool(r.get('T_DELETED', False))
                    })
            print(f"\n-> Finished. Processed {primary_count} total primary records.")

            if not primary_recs:
                self.finished.emit(True, "Sync Info: No new delivery records found to sync.")
                return

            # --- Step 3: Execute Database Transactions ---
            print("\nStep 3: Writing data to PostgreSQL database...")
            with engine.connect() as conn:
                with conn.begin():
                    dr_numbers_to_sync = [rec['dr_no'] for rec in primary_recs]

                    print(" -> Deleting existing items for DRs to be synced...")
                    conn.execute(text("DELETE FROM product_delivery_items WHERE dr_no = ANY(:dr_nos)"),
                                 {"dr_nos": dr_numbers_to_sync})

                    print(" -> Inserting/Updating primary delivery records...")
                    conn.execute(text("""
                        INSERT INTO product_delivery_primary (
                            dr_no, delivery_date, customer_name, deliver_to, address, po_no,
                            order_form_no, terms, prepared_by, encoded_on, is_deleted,
                            edited_by, edited_on, encoded_by
                        ) VALUES (
                            :dr_no, :delivery_date, :customer_name, :deliver_to, :address, :po_no,
                            :order_form_no, :terms, :prepared_by, :encoded_on, :is_deleted,
                            'DBF_SYNC', NOW(), :prepared_by
                        ) ON CONFLICT (dr_no) DO UPDATE SET
                            delivery_date = EXCLUDED.delivery_date, customer_name = EXCLUDED.customer_name,
                            deliver_to = EXCLUDED.deliver_to, address = EXCLUDED.address, po_no = EXCLUDED.po_no,
                            order_form_no = EXCLUDED.order_form_no, terms = EXCLUDED.terms,
                            prepared_by = EXCLUDED.prepared_by, encoded_on = EXCLUDED.encoded_on,
                            is_deleted = EXCLUDED.is_deleted, edited_by = 'DBF_SYNC', edited_on = NOW()
                    """), primary_recs)

                    all_items_to_insert = [
                        item for dr_num in dr_numbers_to_sync
                        if dr_num in items_by_dr for item in items_by_dr[dr_num]
                    ]
                    if all_items_to_insert:
                        print(f" -> Inserting {len(all_items_to_insert)} associated items...")
                        conn.execute(text("""
                            INSERT INTO product_delivery_items (
                                dr_no, quantity, unit, product_code, product_color,
                                no_of_packing, weight_per_pack, lot_numbers, attachments
                            ) VALUES (
                                :dr_no, :quantity, :unit, :product_code, :product_color,
                                :no_of_packing, :weight_per_pack, :lot_numbers, :attachments
                            )
                        """), all_items_to_insert)
            print(" -> Database transaction committed successfully.")

            # --- Step 4: Finalize and Emit Signal ---
            msg = (f"Delivery sync complete.\n"
                   f"{len(primary_recs)} primary records and "
                   f"{len(all_items_to_insert)} items processed.")
            self.finished.emit(True, msg)

        except dbfread.DBFNotFound as e:
            self.finished.emit(False, f"File Not Found: A required delivery DBF file is missing.\nDetails: {e}")
        except Exception as e:
            trace_info = traceback.format_exc()
            print(f"DELIVERY SYNC CRITICAL ERROR: {e}\n{trace_info}")
            self.finished.emit(False, (f"An unexpected error occurred during delivery sync:\n{e}\n\n"
                                       "Check console/logs for technical details."))


# This handler function will be connected to the worker's 'finished' signal
def handle_sync_finish(success, message):
    """Prints the final result of the sync process."""
    print("\n--- Sync Process Finished ---")
    if success:
        print("Status: SUCCESS")
        print(f"Message: {message}")
    else:
        print("Status: FAILED")
        print(f"Message: {message}")
    # In a real GUI app, this would close the app or thread
    if QCoreApplication.instance():
        QCoreApplication.instance().quit()


if __name__ == "__main__":
    # This block allows you to run the script directly to test the sync.

    # We need a QCoreApplication for the signal/slot mechanism to work.
    app = QCoreApplication(sys.argv)

    # 1. Ensure the database tables exist by running the creation function.
    print("--- Running Delivery Table Setup ---")
    create_delivery_legacy_tables()

    # 2. Instantiate the worker and connect its signal.
    worker = SyncDeliveryWorker()
    worker.finished.connect(handle_sync_finish)

    # 3. Run the worker.
    worker.run()

    # The handle_sync_finish function will be called when the worker is done.
    # We exit here because for a console script, the work is finished.
    # In a GUI app, you would let app.exec() run.
    sys.exit()