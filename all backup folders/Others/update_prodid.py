import sys
import pandas as pd
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QPushButton, QLabel, QLineEdit, QFileDialog, QMessageBox, QStatusBar,
    QGridLayout
)
from PyQt6.QtGui import QFont


class MultiKeyUpdater(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Excel Multi-Column Matcher & Updater")
        self.setGeometry(100, 100, 800, 450)

        # Main widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        grid_layout = QGridLayout()
        grid_layout.setSpacing(10)

        # --- Source File (warehouse-f) ---
        source_label = QLabel("<b>1. Source File (warehouse-f)</b><br><i>Contains the IDs to copy from</i>")
        self.source_path_edit = QLineEdit()
        self.source_path_edit.setPlaceholderText("Click 'Browse...' to select your warehouse file")
        self.source_path_edit.setReadOnly(True)
        source_browse_btn = QPushButton("Browse...")
        source_browse_btn.clicked.connect(self.browse_source_file)

        source_key1_label = QLabel("Source Key 1 (Material):")
        self.source_key1_edit = QLineEdit("t_matcode")
        source_key2_label = QLabel("Source Key 2 (Document):")
        self.source_key2_edit = QLineEdit("t_pid")
        source_value_label = QLabel("Value to Copy Column:")
        self.source_value_edit = QLineEdit("t_prodid")

        grid_layout.addWidget(source_label, 0, 0, 1, 4)
        grid_layout.addWidget(self.source_path_edit, 1, 0, 1, 3)
        grid_layout.addWidget(source_browse_btn, 1, 3)
        grid_layout.addWidget(source_key1_label, 2, 0)
        grid_layout.addWidget(self.source_key1_edit, 2, 1)
        grid_layout.addWidget(source_key2_label, 2, 2)
        grid_layout.addWidget(self.source_key2_edit, 2, 3)
        grid_layout.addWidget(source_value_label, 3, 0)
        grid_layout.addWidget(self.source_value_edit, 3, 1)

        # --- Target File (francis-f) ---
        target_label = QLabel("<b>2. Target File (francis-f)</b><br><i>The file that needs to be updated</i>")
        self.target_path_edit = QLineEdit()
        self.target_path_edit.setPlaceholderText("Click 'Browse...' to select your Francis file")
        self.target_path_edit.setReadOnly(True)
        target_browse_btn = QPushButton("Browse...")
        target_browse_btn.clicked.connect(self.browse_target_file)

        target_key1_label = QLabel("Target Key 1 (Material):")
        self.target_key1_edit = QLineEdit("mat_co")
        target_key2_label = QLabel("Target Key 2 (Document):")
        self.target_key2_edit = QLineEdit("document_number")  # Updated with correct name
        target_new_col_label = QLabel("New Column Name:")
        self.target_new_col_edit = QLineEdit("prodid")

        grid_layout.addWidget(target_label, 4, 0, 1, 4)
        grid_layout.addWidget(self.target_path_edit, 5, 0, 1, 3)
        grid_layout.addWidget(target_browse_btn, 5, 3)
        grid_layout.addWidget(target_key1_label, 6, 0)
        grid_layout.addWidget(self.target_key1_edit, 6, 1)
        grid_layout.addWidget(target_key2_label, 6, 2)
        grid_layout.addWidget(self.target_key2_edit, 6, 3)
        grid_layout.addWidget(target_new_col_label, 7, 0)
        grid_layout.addWidget(self.target_new_col_edit, 7, 1)

        # --- Process Button ---
        self.process_btn = QPushButton("3. Process Files and Create Updated File")
        self.process_btn.setFont(QFont("Segoe UI", 12))
        self.process_btn.setStyleSheet("padding: 10px;")
        self.process_btn.clicked.connect(self.process_files)

        main_layout.addLayout(grid_layout)
        main_layout.addStretch()
        main_layout.addWidget(self.process_btn)

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Please select files and confirm key columns.")

    def browse_source_file(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Select Source File", "", "Excel Files (*.xlsx *.xls)")
        if file_name: self.source_path_edit.setText(file_name)

    def browse_target_file(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Select Target File", "", "Excel Files (*.xlsx *.xls)")
        if file_name: self.target_path_edit.setText(file_name)

    def process_files(self):
        source_file = self.source_path_edit.text()
        target_file = self.target_path_edit.text()

        if not source_file or not target_file:
            QMessageBox.warning(self, "Missing Files", "Please select both the source and target files.")
            return

        source_keys = [self.source_key1_edit.text().strip(), self.source_key2_edit.text().strip()]
        target_keys = [self.target_key1_edit.text().strip(), self.target_key2_edit.text().strip()]
        value_col = self.source_value_edit.text().strip()
        new_col_name = self.target_new_col_edit.text().strip()

        if not all(source_keys + target_keys + [value_col, new_col_name]):
            QMessageBox.warning(self, "Missing Column Names", "Please ensure all column name fields are filled.")
            return

        try:
            self.statusBar().showMessage("Processing... Loading files...")
            QApplication.processEvents()

            # Read all data as strings to prevent matching errors (e.g., '00123' vs 123)
            source_df = pd.read_excel(source_file, dtype=str)
            target_df = pd.read_excel(target_file, dtype=str)

            # Clean column names by removing leading/trailing spaces
            source_df.columns = source_df.columns.str.strip()
            target_df.columns = target_df.columns.str.strip()

            # Prepare a smaller source dataframe with only the columns we need.
            # Drop duplicates based on the keys to ensure a clean merge.
            source_subset = source_df[source_keys + [value_col]].drop_duplicates(subset=source_keys)

            self.statusBar().showMessage("Processing... Merging data based on two key columns...")
            QApplication.processEvents()

            # Perform a 'left merge'. This keeps all rows from the target file (francis-f)
            # and brings in the 'prodid' from the source file only where BOTH keys match.
            merged_df = pd.merge(
                target_df,
                source_subset,
                left_on=target_keys,
                right_on=source_keys,
                how='left'
            )

            # Rename the newly added column to the desired name (e.g., 'prodid')
            merged_df.rename(columns={value_col: new_col_name}, inplace=True)

            # Replace any non-matches (which appear as NaN) with a blank string.
            merged_df[new_col_name] = merged_df[new_col_name].fillna('')

            output_filename, _ = QFileDialog.getSaveFileName(self, "Save Updated File As", "francis-f-UPDATED.xlsx",
                                                             "Excel Files (*.xlsx)")

            if output_filename:
                # Save the final result to a new Excel file, without the pandas index column.
                merged_df.to_excel(output_filename, index=False)
                self.statusBar().showMessage(f"Success! File saved as {output_filename}")
                QMessageBox.information(self, "Success",
                                        f"The file has been processed successfully!\n\nSaved as: {output_filename}")
            else:
                self.statusBar().showMessage("Save operation cancelled.")

        except Exception as e:
            self.statusBar().showMessage(f"An error occurred.")
            QMessageBox.critical(self, "Error", f"An error occurred during processing:\n\n{e}")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MultiKeyUpdater()
    window.show()
    sys.exit(app.exec())