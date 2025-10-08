import sys
import re
import traceback
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QListWidget, QMessageBox, QProgressBar, QLineEdit, QAbstractItemView
)
from PyQt6.QtCore import Qt

import pandas as pd
from sqlalchemy import create_engine, text

# ---------- Configuration defaults ----------
DEFAULT_EXCEL = ""
DEFAULT_DB = {
    "host": "192.168.1.13",
    "port": 5432,
    "user": "postgres",
    "password": "mbpi",
    "dbname": "dbfg"
}


# ---------- Helper utilities ----------

def sanitize_identifier(name: str) -> str:
    """Make a safe SQL identifier: lowercase, replace non-alphanum with underscore, trim."""
    if name is None: return "sheet"
    s = str(name).strip().lower()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^0-9a-z_]", "_", s)
    s = re.sub(r"_+", "_", s)
    s = s.strip("_")
    if not s: s = "sheet"
    if s and s[0].isdigit(): s = "_" + s
    return s


def table_name_from_sheet(sheet_name: str) -> str:
    """Generate a database table name from a sheet name."""
    base = sanitize_identifier(sheet_name)
    return f"beginv_{base}"


def find_header_row(df):
    """Find the row that contains the actual column headers."""
    for i in range(min(10, len(df))):
        row = df.iloc[i]
        if any(keyword in str(cell).lower() for cell in row for keyword in
               ['date', 'code', 'customer', 'lot', 'qty', 'quantity', 'number', 'name', 'item']):
            return i
    return 0


def process_excel_sheet(file_path, sheet_name):
    """Read an Excel sheet, find the header, and return a clean DataFrame."""
    try:
        df_raw = pd.read_excel(file_path, sheet_name=sheet_name, header=None, engine="openpyxl")
        if df_raw.empty: return pd.DataFrame()
        header_row = find_header_row(df_raw)
        df = pd.read_excel(file_path, sheet_name=sheet_name, header=header_row, engine="openpyxl")
        if df.empty: return pd.DataFrame()
        df = df.dropna(axis=1, how='all')
        if not df.columns.empty:
            first_col = df.columns[0]
            df = df.dropna(subset=[first_col], how='all')
        df = df.reset_index(drop=True)
        return df
    except Exception as e:
        print(f"Error processing sheet '{sheet_name}': {e}")
        return pd.DataFrame()


def find_column_by_keyword(df, keywords):
    """Finds the first column name in a DataFrame that contains any of the given keywords."""
    for col in df.columns:
        for keyword in keywords:
            if keyword in str(col).lower():
                return col
    return None


def expand_lot_ranges(df):
    """
    Expands rows in a DataFrame where the 'lot number' column contains a range.
    The original row with the range is removed and replaced by the new expanded rows.
    """
    lot_col = find_column_by_keyword(df, ['lot'])
    qty_col = find_column_by_keyword(df, ['qty', 'quantity'])

    if not lot_col or not qty_col:
        print("Warning: 'lot' or 'qty' column not found. Skipping lot number expansion.")
        return df

    expanded_rows = []

    for index, row in df.iterrows():
        lot_val = row[lot_col]
        total_qty = pd.to_numeric(row[qty_col], errors='coerce')

        if isinstance(lot_val, str) and '-' in lot_val and not pd.isna(total_qty):
            match = re.match(r'(\d+)([a-zA-Z]*)?-(\d+)([a-zA-Z]*)?', lot_val.strip())

            if match:
                start_num = int(match.group(1))
                suffix = match.group(2) if match.group(2) is not None else ''
                end_num = int(match.group(3))

                if start_num <= end_num:
                    lot_numbers = [f"{i}{suffix}" for i in range(start_num, end_num + 1)]
                    num_lots = len(lot_numbers)

                    if num_lots > 0:
                        base_qty = int(total_qty // num_lots)
                        remainder = int(total_qty % num_lots)

                        print(
                            f"Expanding lot range '{lot_val}' into {num_lots} lots with base QTY {base_qty} and remainder {remainder}.")

                        for i, new_lot in enumerate(lot_numbers):
                            new_row = row.copy()
                            new_row[lot_col] = new_lot
                            new_row[qty_col] = base_qty + 1 if i < remainder else base_qty
                            expanded_rows.append(new_row)

                        # THE FIX: Skip to the next original row and do not append the current summary row.
                        continue

        # This line is only reached if the row was NOT a range or failed processing. Keep original row.
        expanded_rows.append(row)

    if not expanded_rows:
        return pd.DataFrame(columns=df.columns)

    return pd.DataFrame(expanded_rows).reset_index(drop=True)


# ---------- Main GUI Application ----------
class ImporterWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Excel Processor: Combine Sheets or Import to DB")
        self.resize(800, 600)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # File selection
        file_layout = QHBoxLayout()
        self.file_label = QLabel("No Excel file selected.")
        btn_browse = QPushButton("Browse Excel File...")
        btn_browse.clicked.connect(self.browse_file)
        file_layout.addWidget(self.file_label)
        file_layout.addStretch()
        file_layout.addWidget(btn_browse)

        # DB connection fields
        db_box = QWidget()
        db_layout = QHBoxLayout(db_box)
        db_layout.setContentsMargins(0, 5, 0, 5)
        self.db_host = QLineEdit(DEFAULT_DB["host"]);
        self.db_host.setPlaceholderText("host")
        self.db_port = QLineEdit(str(DEFAULT_DB["port"]));
        self.db_port.setPlaceholderText("port")
        self.db_user = QLineEdit(DEFAULT_DB["user"]);
        self.db_user.setPlaceholderText("user")
        self.db_pass = QLineEdit(DEFAULT_DB["password"]);
        self.db_pass.setPlaceholderText("password");
        self.db_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.db_dbname = QLineEdit(DEFAULT_DB["dbname"]);
        self.db_dbname.setPlaceholderText("database")
        db_layout.addWidget(QLabel("DB Host:"));
        db_layout.addWidget(self.db_host)
        db_layout.addWidget(QLabel("Port:"));
        db_layout.addWidget(self.db_port)
        db_layout.addWidget(QLabel("User:"));
        db_layout.addWidget(self.db_user)
        db_layout.addWidget(QLabel("Password:"));
        db_layout.addWidget(self.db_pass)
        db_layout.addWidget(QLabel("DB Name:"));
        db_layout.addWidget(self.db_dbname)

        # Sheets list and controls
        self.sheets_list = QListWidget()
        self.sheets_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

        btn_reload = QPushButton("Reload Sheets")
        btn_reload.clicked.connect(self.load_sheets)
        btn_select_all = QPushButton("Select All")
        btn_select_all.clicked.connect(self.select_all_sheets)

        btn_combine = QPushButton("Combine Selected to Excel")
        btn_combine.setStyleSheet("background-color: #4CAF50; color: white;")
        btn_combine.clicked.connect(self.combine_selected_sheets)

        btn_import_db = QPushButton("Import Selected to DB")
        btn_import_db.setStyleSheet("background-color: #008CBA; color: white;")
        btn_import_db.clicked.connect(self.import_selected_sheets_to_db)

        controls_layout = QHBoxLayout()
        controls_layout.addWidget(btn_reload)
        controls_layout.addWidget(btn_select_all)
        controls_layout.addStretch()
        controls_layout.addWidget(btn_combine)
        controls_layout.addWidget(btn_import_db)

        # Progress and status
        self.progress = QProgressBar();
        self.progress.setTextVisible(False)
        self.status_label = QLabel("Ready")

        # Layout assembly
        layout.addLayout(file_layout)
        layout.addWidget(QLabel("Sheets found in file:"))
        layout.addWidget(self.sheets_list)
        layout.addLayout(controls_layout)
        layout.addWidget(self.progress)
        layout.addWidget(self.status_label)
        layout.addWidget(QLabel("Database Settings (for DB Import only):"))
        layout.addWidget(db_box)

        # Initialization
        self.excel_path = None
        if DEFAULT_EXCEL and Path(DEFAULT_EXCEL).exists():
            self.excel_path = Path(DEFAULT_EXCEL)
            self.file_label.setText(f"Excel file: {self.excel_path.name}")
            self.load_sheets()

    def browse_file(self):
        start_dir = str(self.excel_path.parent) if self.excel_path else "."
        path, _ = QFileDialog.getOpenFileName(self, "Select Excel file", start_dir, "Excel Files (*.xlsx *.xls *.xlsm)")
        if path:
            self.excel_path = Path(path)
            self.file_label.setText(f"Excel file: {self.excel_path.name}")
            self.load_sheets()

    def load_sheets(self):
        if not self.excel_path:
            self.status_label.setText("Please select an Excel file first.")
            return
        self.sheets_list.clear()
        self.status_label.setText(f"Loading sheets from {self.excel_path.name}...")
        QApplication.processEvents()
        try:
            xl = pd.ExcelFile(self.excel_path)
            self.sheets_list.addItems(xl.sheet_names)
            self.status_label.setText(f"Found {len(xl.sheet_names)} sheets. Please select sheets to process.")
        except Exception as e:
            QMessageBox.critical(self, "Error Loading Excel", f"Failed to read Excel file:\n{e}")
            self.status_label.setText("Error loading Excel file.")

    def select_all_sheets(self):
        self.sheets_list.selectAll()

    def get_selected_sheets(self):
        selected = [it.text() for it in self.sheets_list.selectedItems()]
        if not selected:
            QMessageBox.information(self, "No Sheets Selected", "Please select one or more sheets to process.")
            return None
        return selected

    def combine_selected_sheets(self):
        selected_sheets = self.get_selected_sheets()
        if not selected_sheets: return

        all_dfs = []
        total = len(selected_sheets)
        self.progress.setRange(0, total)
        self.progress.setValue(0)
        self.status_label.setText("Starting combination process...")

        for idx, sheet_name in enumerate(selected_sheets, start=1):
            self.status_label.setText(f"Processing sheet: {sheet_name} ({idx}/{total})")
            QApplication.processEvents()
            try:
                df = process_excel_sheet(self.excel_path, sheet_name)
                if df.empty:
                    print(f"Skipping empty or unreadable sheet: {sheet_name}")
                    continue

                df = expand_lot_ranges(df)

                df['FG_TYPE'] = sheet_name
                all_dfs.append(df)
            except Exception as e:
                QMessageBox.warning(self, f"Error Processing Sheet",
                                    f"Could not process sheet '{sheet_name}'.\nError: {e}")
            self.progress.setValue(idx)

        if not all_dfs:
            QMessageBox.warning(self, "Process Finished", "No data was processed. Combined file was not created.")
            self.status_label.setText("Combination failed: No data could be read.")
            return

        try:
            combined_df = pd.concat(all_dfs, ignore_index=True, sort=False)
            if 'FG_TYPE' in combined_df.columns:
                cols = ['FG_TYPE'] + [col for col in combined_df.columns if col != 'FG_TYPE']
                combined_df = combined_df[cols]

            output_filename = f"{self.excel_path.stem}_COMBINED.xlsx"
            output_path = self.excel_path.parent / output_filename

            self.status_label.setText(f"Saving combined file to {output_path}...")
            QApplication.processEvents()
            combined_df.to_excel(output_path, index=False)

            success_msg = (f"Successfully combined {len(all_dfs)} sheets!\n"
                           f"Total rows in output: {len(combined_df)}\n\n"
                           f"Saved to: {output_path}")
            QMessageBox.information(self, "Success", success_msg)
            self.status_label.setText("Combination complete.")
        except Exception as e:
            tb = traceback.format_exc()
            QMessageBox.critical(self, "Save Failed",
                                 f"An error occurred while saving the file:\n{e}\n\nTraceback:\n{tb}")
            self.status_label.setText("Error saving combined file.")

    def import_selected_sheets_to_db(self):
        selected_sheets = self.get_selected_sheets()
        if not selected_sheets: return
        try:
            host = self.db_host.text().strip() or DEFAULT_DB["host"]
            port = int(self.db_port.text().strip() or DEFAULT_DB["port"])
            user = self.db_user.text().strip() or DEFAULT_DB["user"]
            password = self.db_pass.text() or DEFAULT_DB["password"]
            dbname = self.db_dbname.text().strip() or DEFAULT_DB["dbname"]
            engine_url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}"
            engine = create_engine(engine_url)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception as e:
            QMessageBox.critical(self, "DB Connection Error", f"Failed to connect to database:\n{e}")
            return

        total, imported_count = len(selected_sheets), 0
        self.progress.setRange(0, total)
        self.progress.setValue(0)

        try:
            for idx, sheet in enumerate(selected_sheets, start=1):
                self.status_label.setText(f"Importing sheet: {sheet} ({idx}/{total})")
                QApplication.processEvents()
                try:
                    df = process_excel_sheet(self.excel_path, sheet)
                    if df.empty:
                        self.status_label.setText(f"Skipping empty sheet: {sheet}")
                        continue

                    # NOTE: Applying the lot expansion before DB import as well
                    df = expand_lot_ranges(df)

                    df = df.rename(columns=lambda c: sanitize_identifier(str(c)))
                    tbl = table_name_from_sheet(sheet)
                    df.to_sql(tbl, engine, if_exists='replace', index=False, method='multi')
                    imported_count += 1
                except Exception as e:
                    QMessageBox.warning(self, f"Warning: {sheet}", f"Failed to import sheet '{sheet}':\n{e}")
                self.progress.setValue(idx)

            if imported_count > 0:
                QMessageBox.information(self, "Import Completed",
                                        f"Successfully imported {imported_count} of {total} sheet(s) to database '{dbname}'.")
            else:
                QMessageBox.warning(self, "Import Completed", "No sheets were successfully imported.")
        except Exception as e:
            tb = traceback.format_exc()
            QMessageBox.critical(self, "Import Failed", f"An error occurred during import:\n{e}\n\nTraceback:\n{tb}")
        finally:
            engine.dispose()
            self.status_label.setText("DB import process completed.")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    w = ImporterWindow()
    w.show()
    sys.exit(app.exec())