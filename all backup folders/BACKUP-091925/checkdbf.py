# --- Filename: check_dbf_values.py ---
import dbfread
import os

# --- IMPORTANT: UPDATE THIS PATH ---
DELIVERY_ITEMS_DBF_PATH = r'\\system-server\SYSTEM-NEW-OLD\tbl_prod01.dbf'
# --- IMPORTANT: USE THE CORRECT FIELD NAME YOU VERIFIED IN STEP 1 ---
FIELD_TO_CHECK = 't_prodid'

if not os.path.exists(DELIVERY_ITEMS_DBF_PATH):
    print(f"ERROR: File not found at path: {DELIVERY_ITEMS_DBF_PATH}")
else:
    try:
        # Load the DBF to read records
        dbf = dbfread.DBF(DELIVERY_ITEMS_DBF_PATH, load=True, encoding='latin1')

        if FIELD_TO_CHECK not in dbf.field_names:
            print(f"ERROR: The field '{FIELD_TO_CHECK}' was not found in the DBF file.")
            print("Available fields are:", dbf.field_names)
        else:
            print(f"--- Checking values for '{FIELD_TO_CHECK}' in the first 10 records ---")
            for i, record in enumerate(dbf.records):
                if i >= 10:
                    break
                color_value = record.get(FIELD_TO_CHECK)
                print(f"Record {i+1}: Value = '{color_value}' (Type: {type(color_value)})")
            print("------------------------------------------------------------------")

    except Exception as e:
        print(f"An error occurred while reading the DBF file: {e}")