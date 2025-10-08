import sys
from sqlalchemy import create_engine, text
from PyQt6.QtWidgets import QApplication, QMessageBox
from config import DB_CONFIG

# --- DATABASE ENGINE ---
db_url = f"postgresql+psycopg2://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}"
try:
    engine = create_engine(db_url, pool_pre_ping=True, pool_recycle=3600)
except Exception as e:
    print(f"FATAL: Could not create database engine. Error: {e}")
    # In a real app, you might show a message box here before exiting.
    sys.exit(1)


def initialize_database():
    """
    Initializes the database schema.
    (Your entire initialize_database function code goes here, unchanged)
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
        # We need a QApplication instance to show a QMessageBox
        app_instance = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None, "DB Init Error", f"Could not initialize database: {e}")
        sys.exit(1)