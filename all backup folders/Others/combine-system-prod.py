import sys
import pandas as pd
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem,
                             QFileDialog, QLabel, QHeaderView, QMessageBox)
from PyQt6.QtCore import Qt


class ExcelProcessorApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Excel Product ID Processor")
        self.setGeometry(100, 100, 1000, 700)

        # Central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # File selection button
        file_layout = QHBoxLayout()
        self.file_button = QPushButton("Select Excel File")
        self.file_button.clicked.connect(self.select_file)
        file_layout.addWidget(self.file_button)

        # Process button
        self.process_button = QPushButton("Process Data")
        self.process_button.clicked.connect(self.process_data)
        self.process_button.setEnabled(False)
        file_layout.addWidget(self.process_button)

        # Export button
        self.export_button = QPushButton("Export Results")
        self.export_button.clicked.connect(self.export_results)
        self.export_button.setEnabled(False)
        file_layout.addWidget(self.export_button)

        layout.addLayout(file_layout)

        # Status label
        self.status_label = QLabel("No file selected")
        layout.addWidget(self.status_label)

        # Results table
        self.results_table = QTableWidget()
        layout.addWidget(self.results_table)

        # Store the file path and data
        self.file_path = None
        self.original_df = None
        self.result_df = None

    def select_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Excel File", "", "Excel Files (*.xlsx *.xls)"
        )

        if file_path:
            self.file_path = file_path
            self.status_label.setText(f"Selected: {file_path.split('/')[-1]}")
            self.process_button.setEnabled(True)
            self.export_button.setEnabled(False)

    def process_data(self):
        if not self.file_path:
            self.status_label.setText("No file selected")
            return

        try:
            # Read the Excel file
            self.original_df = pd.read_excel(self.file_path)

            # Check if required columns exist
            if 't_prodid' not in self.original_df.columns or 't_wt' not in self.original_df.columns:
                QMessageBox.critical(self, "Error", "Excel file must contain 't_prodid' and 't_wt' columns")
                return

            # Convert t_wt to numeric, handling any potential errors
            self.original_df['t_wt'] = pd.to_numeric(self.original_df['t_wt'], errors='coerce')

            # Group by t_prodid and keep all columns
            # First, calculate the total weight for each product ID
            total_weights = self.original_df.groupby('t_prodid')['t_wt'].sum().reset_index()
            total_weights.columns = ['t_prodid', 'total_t_wt']

            # Get all unique rows for each product ID (keeping the first occurrence of other columns)
            unique_rows = self.original_df.drop_duplicates('t_prodid', keep='first')

            # Merge the total weights with the unique rows
            self.result_df = pd.merge(unique_rows, total_weights, on='t_prodid', how='left')

            # Reorder columns to put total_t_wt at the end
            cols = [col for col in self.result_df.columns if col != 'total_t_wt'] + ['total_t_wt']
            self.result_df = self.result_df[cols]

            # Format the total weight for better readability
            self.result_df['total_t_wt'] = self.result_df['total_t_wt'].round(2)

            # Display results in table
            self.display_results(self.result_df)

            self.status_label.setText(f"Processed {len(self.result_df)} product IDs successfully")
            self.export_button.setEnabled(True)

        except Exception as e:
            self.status_label.setText(f"Error: {str(e)}")
            QMessageBox.critical(self, "Error", f"An error occurred: {str(e)}")

    def display_results(self, result_df):
        # Clear previous results
        self.results_table.clear()

        # Set table dimensions
        self.results_table.setRowCount(result_df.shape[0])
        self.results_table.setColumnCount(result_df.shape[1])

        # Set headers
        self.results_table.setHorizontalHeaderLabels(result_df.columns)

        # Populate table with data
        for row in range(result_df.shape[0]):
            for col in range(result_df.shape[1]):
                value = result_df.iloc[row, col]
                # Handle different data types
                if pd.isna(value):
                    display_value = ""
                elif isinstance(value, float):
                    display_value = f"{value:.2f}"
                else:
                    display_value = str(value)

                item = QTableWidgetItem(display_value)
                # Right-align numeric values, left-align others
                if isinstance(value, (int, float)):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.results_table.setItem(row, col, item)

        # Adjust column widths
        header = self.results_table.horizontalHeader()
        for i in range(result_df.shape[1]):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)

    def export_results(self):
        if self.result_df is None:
            QMessageBox.warning(self, "Warning", "No data to export. Please process a file first.")
            return

        try:
            # Get save file path
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Save Results", "", "Excel Files (*.xlsx)"
            )

            if file_path:
                # Ensure the file has the correct extension
                if not file_path.endswith('.xlsx'):
                    file_path += '.xlsx'

                # Save to Excel
                self.result_df.to_excel(file_path, index=False)

                self.status_label.setText(f"Results exported to {file_path.split('/')[-1]}")
                QMessageBox.information(self, "Success", f"Results successfully exported to {file_path}")

        except Exception as e:
            self.status_label.setText(f"Export error: {str(e)}")
            QMessageBox.critical(self, "Export Error", f"An error occurred during export: {str(e)}")


def main():
    app = QApplication(sys.argv)
    window = ExcelProcessorApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()