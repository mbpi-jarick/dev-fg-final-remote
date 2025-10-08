import sys
import pandas as pd
import re
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QFileDialog, QLabel, QHeaderView,
    QMessageBox
)
from PyQt6.QtGui import QFont


# --- Core Data Processing Logic ---
def process_dataframe(df):
    """
    Processes a DataFrame by expanding rows where the LOT_NUMBER contains a dash '-'.
    Rows without a dash are left untouched.
    """
    new_rows = []
    print("\n--- Starting Data Processing ---")

    # Iterate over each row in the original DataFrame
    for index, row in df.iterrows():
        lot_number_str = str(row['LOT_NUMBER']).strip()

        # --- PRIMARY CONDITION: Only process if a dash is present ---
        if '-' in lot_number_str:
            print(f"Processing row {index}: LOT_NUMBER = '{lot_number_str}' (Dash detected)")

            # Regex to find a number-range and the text around it.
            # It captures: (prefix)(start_number)-(end_number)(suffix)
            match = re.search(r'^(.*?)(\d+)\s*-\s*(\d+)(.*?)$', lot_number_str)

            if match:
                print("  -> Range pattern MATCHED! Breaking down...")
                prefix, start_num_str, end_num_str, suffix = match.groups()

                try:
                    start_num = int(start_num_str)
                    end_num = int(end_num_str)
                    total_qty = float(row['QTY'])

                    if start_num > end_num:
                        print(f"  -> WARNING: Invalid range (start > end). Keeping original row.")
                        new_rows.append(row.to_dict())
                        continue

                    num_lots = (end_num - start_num) + 1
                    qty_per_lot = total_qty / num_lots if num_lots > 0 else 0

                    # Create a new row for each lot number in the range
                    for i in range(start_num, end_num + 1):
                        new_row = row.to_dict()
                        # Reconstruct the lot number using the detected parts
                        new_row['LOT_NUMBER'] = f"{prefix}{i}{suffix}"
                        new_row['QTY'] = f"{qty_per_lot:.2f}"
                        new_rows.append(new_row)

                    print(f"  -> Successfully expanded into {num_lots} lots.")

                except (ValueError, TypeError) as e:
                    print(f"  -> ERROR: Could not process range. Invalid QTY? Error: {e}. Keeping original row.")
                    new_rows.append(row.to_dict())
            else:
                # The string had a dash, but not in a number-range format we could parse.
                print(f"  -> Dash found, but pattern NOT MATCHED. Keeping original row.")
                new_rows.append(row.to_dict())
        else:
            # --- This row does NOT contain a dash, so we keep it as is ---
            print(f"Processing row {index}: LOT_NUMBER = '{lot_number_str}' (No dash)")
            new_rows.append(row.to_dict())

    print("--- Data Processing Finished ---\n")
    processed_df = pd.DataFrame(new_rows)
    # Reorder columns to match the original DataFrame
    if not df.empty:
        processed_df = processed_df[df.columns]
    return processed_df


# --- PyQt6 GUI Application ---
class LotNumberProcessor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Lot Number Breakdown Tool")
        self.setGeometry(100, 100, 1200, 800)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        self.btn_load = QPushButton("Load and Process CSV File")
        self.btn_load.setFont(QFont("Arial", 12))
        self.btn_load.clicked.connect(self.load_and_process_file)
        self.layout.addWidget(self.btn_load)

        self.layout.addWidget(QLabel("Original Data"))
        self.original_table = QTableWidget()
        self.layout.addWidget(self.original_table)

        self.layout.addWidget(QLabel("Processed Data (Ranges with '-' are broken down)"))
        self.processed_table = QTableWidget()
        self.layout.addWidget(self.processed_table)

    def load_and_process_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open CSV File", "", "CSV Files (*.csv);;All Files (*)"
        )

        if not file_path:
            return

        try:
            # Read all data as strings and fill blank cells with empty strings
            self.original_df = pd.read_csv(file_path, dtype=str).fillna('')

            if 'LOT_NUMBER' not in self.original_df.columns or 'QTY' not in self.original_df.columns:
                self.show_error_message("Error: CSV file must contain 'LOT_NUMBER' and 'QTY' columns.")
                return

            self.populate_table(self.original_table, self.original_df)

            # Process the data using the final logic
            self.processed_df = process_dataframe(self.original_df.copy())

            self.populate_table(self.processed_table, self.processed_df)

        except Exception as e:
            self.show_error_message(f"An error occurred while loading or processing the file:\n{e}")
            print(f"Fatal Error: {e}")

    def populate_table(self, table_widget, df):
        table_widget.clear()

        table_widget.setRowCount(df.shape[0])
        table_widget.setColumnCount(df.shape[1])
        table_widget.setHorizontalHeaderLabels(df.columns)

        for row_idx, row in enumerate(df.values):
            for col_idx, item in enumerate(row):
                table_widget.setItem(row_idx, col_idx, QTableWidgetItem(str(item)))

        table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)

    def show_error_message(self, message):
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setText(message)
        msg_box.setWindowTitle("Error")
        msg_box.exec()


# --- Main execution block ---
if __name__ == '__main__':
    app = QApplication(sys.argv)
    main_window = LotNumberProcessor()
    main_window.show()
    sys.exit(app.exec())