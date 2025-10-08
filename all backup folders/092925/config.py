import os

# --- DATABASE CONFIGURATION ---
DB_CONFIG = {
    "host": "192.168.1.13",
    "port": 5432,
    "dbname": "dbfg",
    "user": "postgres",
    "password": "mbpi"
}

# --- DBF FILE PATHS ---
DBF_BASE_PATH = r'\\system-server\SYSTEM-NEW-OLD'

# Production Paths
PRODUCTION_DBF_PATH = os.path.join(DBF_BASE_PATH, 'tbl_prod01.dbf')
CUSTOMER_DBF_PATH = os.path.join(DBF_BASE_PATH, 'tbl_customer01.dbf')

# Delivery Paths
DELIVERY_DBF_PATH = os.path.join(DBF_BASE_PATH, 'tbl_del01.dbf')
DELIVERY_ITEMS_DBF_PATH = os.path.join(DBF_BASE_PATH, 'tbl_del02.dbf')

# RRF Paths
RRF_DBF_PATH = os.path.join(DBF_BASE_PATH, 'RRF')
RRF_PRIMARY_DBF_PATH = os.path.join(RRF_DBF_PATH, 'tbl_del01.dbf')
RRF_ITEMS_DBF_PATH = os.path.join(RRF_DBF_PATH, 'tbl_del02.dbf')