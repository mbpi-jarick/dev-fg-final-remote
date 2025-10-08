# migrate_beginning_inventory.py
# This is a one-time script to migrate your starting inventory from the
# 'beginv_sheet1' table into the 'transactions' table.
#
# WARNING: MAKE A BACKUP OF YOUR DATABASE BEFORE RUNNING THIS SCRIPT.
#          DO NOT RUN THIS SCRIPT MORE THAN ONCE.

import sys
import traceback
from decimal import Decimal, InvalidOperation
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

# --- CONFIGURATION ---
# <<<--- IMPORTANT: Use the EXACT SAME connection string as your main application.
DATABASE_URL = "postgresql+psycopg2://postgres:mbpi@192.168.1.13:5432/dbfg"

# <<<--- IMPORTANT: Set a date that is BEFORE any other real transactions.
SNAPSHOT_DATE = '2023-01-01'

# These values will be used for the new transaction records.
TRANSACTION_TYPE = 'BEGINNING BALANCE'
SOURCE_REF_NO = 'MIGRATED_FROM_BEGINV'
ENCODED_BY = 'system_migration'
UNIT = 'kg'


def main():
    """
    Connects to the database and performs the one-time migration of data
    from 'beginv_sheet1' to the 'transactions' table.
    """
    print("--- Beginning Inventory Migration Tool ---")
    print("This script will read data from 'beginv_sheet1' and insert it as")
    print("the starting balance into the 'transactions' table.")
    print("\nWARNING: THIS IS A ONE-TIME OPERATION. DO NOT RUN IT MORE THAN ONCE.")
    print("PLEASE MAKE A BACKUP OF YOUR DATABASE BEFORE PROCEEDING.\n")

    confirm = input("Type 'YES' to continue with the migration: ")
    if confirm != 'YES':
        print("Migration aborted by user.")
        return

    try:
        engine = create_engine(DATABASE_URL)
        with engine.connect() as conn:
            print("\nDatabase connection successful.")

            with conn.begin() as transaction:
                print("Transaction started. Fetching data from 'beginv_sheet1'...")

                select_query = text("""
                    SELECT product_code, lot_number, qty 
                    FROM beginv_sheet1 
                    WHERE product_code IS NOT NULL AND product_code != ''
                      AND lot_number IS NOT NULL AND lot_number != ''
                      AND qty IS NOT NULL AND qty != ''
                """)
                records_to_migrate = conn.execute(select_query).mappings().all()

                if not records_to_migrate:
                    print("No valid records found in 'beginv_sheet1' to migrate. Aborting.")
                    transaction.rollback()
                    return

                print(f"Found {len(records_to_migrate)} records to process.")
                migrated_count = 0
                skipped_count = 0

                insert_query = text("""
                    INSERT INTO transactions (
                        transaction_date, transaction_type, source_ref_no, product_code, 
                        lot_number, quantity_in, quantity_out, unit, encoded_by
                    ) VALUES (
                        :date, :type, :ref, :pcode, :lot, :qty_in, 0, :unit, :by
                    )
                """)

                for row in records_to_migrate:
                    try:
                        quantity = Decimal(row['qty'])
                        if quantity <= 0:
                            print(
                                f"  - SKIPPING: Lot '{row['lot_number']}' has zero or negative quantity ({quantity}).")
                            skipped_count += 1
                            continue

                        conn.execute(insert_query, {
                            "date": SNAPSHOT_DATE, "type": TRANSACTION_TYPE, "ref": SOURCE_REF_NO,
                            "pcode": row['product_code'], "lot": row['lot_number'], "qty_in": quantity,
                            "unit": UNIT, "by": ENCODED_BY
                        })
                        migrated_count += 1
                    except InvalidOperation:
                        print(f"  - SKIPPING: Lot '{row['lot_number']}' has an invalid quantity: '{row['qty']}'.")
                        skipped_count += 1
                        continue

                print("\nAll records processed. Committing transaction...")
            print("\n--- MIGRATION COMPLETE ---")
            print(f"Successfully migrated {migrated_count} records.")
            print(f"Skipped {skipped_count} records due to invalid data.")

    except Exception as e:
        print(f"\nFATAL ERROR: An unexpected error occurred. The transaction has been rolled back.")
        print(f"No data was changed. Error: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()