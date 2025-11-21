import sys
import pandas as pd
import numpy as np
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
                             QPushButton, QLabel, QTextEdit, QFileDialog, QWidget,
                             QProgressBar, QMessageBox, QCheckBox, QTableWidget,
                             QTableWidgetItem, QTabWidget, QHeaderView)
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QFont
import os


class ExcelProcessor(QThread):
    progress_updated = pyqtSignal(int)
    processing_finished = pyqtSignal(pd.DataFrame, pd.DataFrame)
    error_occurred = pyqtSignal(str)
    data_loaded = pyqtSignal(pd.DataFrame, pd.DataFrame)

    def __init__(self, file_path=None, process_dc=True, process_mb=True, action="load"):
        super().__init__()
        self.file_path = file_path
        self.process_dc = process_dc
        self.process_mb = process_mb
        self.action = action  # "load" or "process"

    def run(self):
        try:
            if self.action == "load":
                self.load_excel_data()
            elif self.action == "process":
                self.process_excel_data()

        except Exception as e:
            self.error_occurred.emit(str(e))

    def load_excel_data(self):
        """Load data from Excel file"""
        try:
            # Read the Excel file
            excel_file = pd.ExcelFile(self.file_path)

            dc_data = pd.DataFrame()
            mb_data = pd.DataFrame()

            if 'dc' in excel_file.sheet_names:
                dc_data = pd.read_excel(self.file_path, sheet_name='dc')
                # Ensure QTY has 2 decimal places
                if 'QTY' in dc_data.columns:
                    dc_data['QTY'] = dc_data['QTY'].round(2)
                self.progress_updated.emit(50)

            if 'mb' in excel_file.sheet_names:
                mb_data = pd.read_excel(self.file_path, sheet_name='mb')
                # Ensure QTY has 2 decimal places
                if 'QTY' in mb_data.columns:
                    mb_data['QTY'] = mb_data['QTY'].round(2)
                self.progress_updated.emit(100)

            self.data_loaded.emit(dc_data, mb_data)

        except Exception as e:
            self.error_occurred.emit(f"Error loading Excel file: {str(e)}")

    def process_excel_data(self):
        """Process the Excel data to expand lot number ranges"""
        try:
            # Read the Excel file
            excel_file = pd.ExcelFile(self.file_path)

            dc_processed = pd.DataFrame()
            mb_processed = pd.DataFrame()

            if self.process_dc and 'dc' in excel_file.sheet_names:
                df = pd.read_excel(self.file_path, sheet_name='dc')
                dc_processed = self.process_dataframe(df)
                self.progress_updated.emit(50)

            if self.process_mb and 'mb' in excel_file.sheet_names:
                df = pd.read_excel(self.file_path, sheet_name='mb')
                mb_processed = self.process_dataframe(df)
                self.progress_updated.emit(100)

            self.processing_finished.emit(dc_processed, mb_processed)

        except Exception as e:
            self.error_occurred.emit(f"Error processing Excel file: {str(e)}")

    def process_dataframe(self, df):
        """Process a dataframe to expand lot number ranges, including BOX_NUMBER if present."""
        processed_rows = []
        has_box_number = 'BOX_NUMBER' in df.columns  # Check for BOX_NUMBER presence

        for _, row in df.iterrows():
            lot_number = str(row['LOT_NUMBER'])
            quantity = row['QTY']
            product_code = row['PRODUCT_CODE']
            location = row['LOCATION']

            box_number = row['BOX_NUMBER'] if has_box_number else None  # Extract Box Number

            # Check if lot_number contains a range (contains '-')
            if '-' in lot_number and not lot_number.endswith('-'):
                try:
                    # Pass BOX NUMBER info to range processing
                    range_result = self.process_lot_range(
                        lot_number, quantity, product_code, location, box_number, has_box_number
                    )
                    if range_result:
                        processed_rows.extend(range_result)
                    else:
                        # Keep original if processing failed
                        row_data = {
                            'PRODUCT_CODE': product_code,
                            'LOT_NUMBER': lot_number,
                            'QTY': round(float(quantity), 2),
                            'LOCATION': location
                        }
                        if has_box_number:
                            row_data['BOX_NUMBER'] = box_number
                        processed_rows.append(row_data)
                except Exception:
                    # Keep original if any error occurs
                    row_data = {
                        'PRODUCT_CODE': product_code,
                        'LOT_NUMBER': lot_number,
                        'QTY': round(float(quantity), 2),
                        'LOCATION': location
                    }
                    if has_box_number:
                        row_data['BOX_NUMBER'] = box_number
                    processed_rows.append(row_data)
            else:
                # Not a range, keep as is
                row_data = {
                    'PRODUCT_CODE': product_code,
                    'LOT_NUMBER': lot_number,
                    'QTY': round(float(quantity), 2),
                    'LOCATION': location
                }
                if has_box_number:
                    row_data['BOX_NUMBER'] = box_number
                processed_rows.append(row_data)

        result_df = pd.DataFrame(processed_rows)
        # Ensure all QTY values have exactly 2 decimal places
        if 'QTY' in result_df.columns:
            result_df['QTY'] = result_df['QTY'].round(2)

        # Define the target column order
        final_cols = ['PRODUCT_CODE', 'LOT_NUMBER', 'QTY', 'LOCATION']
        if has_box_number:
            final_cols.append('BOX_NUMBER')

        # Filter existing columns and reindex
        if not result_df.empty:
            existing_cols = [col for col in final_cols if col in result_df.columns]
            result_df = result_df.reindex(columns=existing_cols, fill_value='')

        return result_df

    def process_lot_range(self, lot_range, total_qty, product_code, location, box_number, has_box_number):
        """Process a single lot number range, incorporating box number if available."""
        range_parts = lot_range.split('-')
        if len(range_parts) != 2:
            return None

        start_lot = range_parts[0].strip()
        end_lot = range_parts[1].strip()

        # Extract numeric and suffix parts
        start_num = ''.join(filter(str.isdigit, start_lot))
        start_suffix = ''.join(filter(str.isalpha, start_lot))

        end_num = ''.join(filter(str.isdigit, end_lot))
        end_suffix = ''.join(filter(str.isalpha, end_lot))

        # Verify suffixes match and numbers are valid
        if start_suffix == end_suffix and start_num and end_num:
            start_num = int(start_num)
            end_num = int(end_num)

            if start_num <= end_num:
                total_items = end_num - start_num + 1
                qty_per_item = total_qty / total_items

                # Create individual entries
                result = []
                for i in range(total_items):
                    current_num = start_num + i
                    new_lot_number = f"{current_num}{start_suffix}"

                    row_data = {
                        'PRODUCT_CODE': product_code,
                        'LOT_NUMBER': new_lot_number,
                        'QTY': round(qty_per_item, 2),
                        'LOCATION': location
                    }
                    if has_box_number:
                        # Box number is carried over identically for all expanded lot numbers
                        row_data['BOX_NUMBER'] = box_number

                    result.append(row_data)
                return result


class ExcelTableWidget(QTableWidget):
    def __init__(self):
        super().__init__()
        self.setup_style()
        self.setColumnCount(0)  # Start with 0 columns

    def setup_style(self):
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)

    def load_data(self, df):
        if df.empty:
            self.setRowCount(0)
            self.setColumnCount(0)
            return

        # Define desired column order
        display_columns = ['PRODUCT_CODE', 'LOT_NUMBER', 'QTY', 'LOCATION']

        # Dynamically include BOX_NUMBER if available in the DataFrame
        if 'BOX_NUMBER' in df.columns:
            display_columns.append('BOX_NUMBER')

        # Filter columns that actually exist in the DataFrame
        existing_display_columns = [col for col in display_columns if col in df.columns]

        self.setColumnCount(len(existing_display_columns))
        self.setHorizontalHeaderLabels(existing_display_columns)

        self.setRowCount(len(df))

        for row_idx, (_, row) in enumerate(df.iterrows()):
            for col_idx, col_name in enumerate(existing_display_columns):
                value = row[col_name]
                item = QTableWidgetItem()

                if pd.isna(value):
                    item.setText("")
                elif col_name == 'QTY':
                    # Format QTY to 2 decimal places
                    qty_display = f"{float(value):.2f}"
                    item.setText(qty_display)

                elif col_name == 'BOX_NUMBER':
                    # Ensure BOX_NUMBER displays as a clean whole number
                    try:
                        # Check if the value is numerically equal to its integer conversion (e.g., 123.0)
                        if isinstance(value, (int, float)) and value == int(value):
                            item.setText(str(int(value)))
                        else:
                            item.setText(str(value))
                    except (ValueError, TypeError):
                        # Fallback if conversion fails
                        item.setText(str(value))

                else:
                    item.setText(str(value))

                self.setItem(row_idx, col_idx, item)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.dc_data = pd.DataFrame()
        self.mb_data = pd.DataFrame()
        self.dc_processed = pd.DataFrame()
        self.mb_processed = pd.DataFrame()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Excel Lot Number Processor")
        self.setGeometry(100, 100, 1200, 800)

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main layout
        layout = QVBoxLayout()
        central_widget.setLayout(layout)

        # Title
        title = QLabel("Excel Lot Number Range Processor")
        title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        title.setStyleSheet("margin: 10px; color: #2c3e50;")
        layout.addWidget(title)

        # Description
        desc = QLabel(
            "Import Excel files and expand lot number ranges (e.g., '8048X-8051X' QTY=200 → '8048X'=50.00, '8049X'=50.00, '8050X'=50.00, '8051X'=50.00). BOX_NUMBER is carried over if present."
        )
        desc.setStyleSheet("margin: 10px; color: #666;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # File selection section
        file_section = self.create_file_section()
        layout.addLayout(file_section)

        # Control section
        control_section = self.create_control_section()
        layout.addLayout(control_section)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Tab widget for data display
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # Create tabs
        self.original_dc_tab = ExcelTableWidget()
        self.original_mb_tab = ExcelTableWidget()
        self.processed_dc_tab = ExcelTableWidget()
        self.processed_mb_tab = ExcelTableWidget()

        self.tab_widget.addTab(self.original_dc_tab, "Original DC")
        self.tab_widget.addTab(self.original_mb_tab, "Original MB")
        self.tab_widget.addTab(self.processed_dc_tab, "Processed DC")
        self.tab_widget.addTab(self.processed_mb_tab, "Processed MB")

        # Log area
        self.log_area = QTextEdit()
        self.log_area.setMaximumHeight(150)
        self.log_area.setPlaceholderText("Processing log will appear here...")
        layout.addWidget(self.log_area)

        # Current file path
        self.current_file_path = None

    def create_file_section(self):
        layout = QHBoxLayout()

        # File selection
        file_layout = QVBoxLayout()
        file_label = QLabel("Excel File:")
        file_label.setStyleSheet("font-weight: bold;")
        self.select_btn = QPushButton("Import Excel File")
        self.select_btn.clicked.connect(self.import_excel)
        self.select_btn.setStyleSheet("QPushButton { background-color: #3498db; color: white; padding: 8px; }")
        self.file_label = QLabel("No file selected")
        self.file_label.setStyleSheet("color: #666; padding: 5px;")

        file_layout.addWidget(file_label)
        file_layout.addWidget(self.select_btn)
        file_layout.addWidget(self.file_label)
        layout.addLayout(file_layout)

        # Export buttons
        export_layout = QVBoxLayout()
        export_label = QLabel("Export:")
        export_label.setStyleSheet("font-weight: bold;")
        self.export_btn = QPushButton("Export Processed Data")
        self.export_btn.clicked.connect(self.export_data)
        self.export_btn.setEnabled(False)
        self.export_btn.setStyleSheet("QPushButton { background-color: #27ae60; color: white; padding: 8px; }")

        export_layout.addWidget(export_label)
        export_layout.addWidget(self.export_btn)
        layout.addLayout(export_layout)

        return layout

    def create_control_section(self):
        layout = QHBoxLayout()

        # Sheet selection
        sheet_layout = QVBoxLayout()
        sheet_label = QLabel("Process Sheets:")
        sheet_label.setStyleSheet("font-weight: bold;")
        self.dc_checkbox = QCheckBox("DC Sheet")
        self.dc_checkbox.setChecked(True)
        self.mb_checkbox = QCheckBox("MB Sheet")
        self.mb_checkbox.setChecked(True)

        sheet_layout.addWidget(sheet_label)
        sheet_layout.addWidget(self.dc_checkbox)
        sheet_layout.addWidget(self.mb_checkbox)
        layout.addLayout(sheet_layout)

        # Process button
        self.process_btn = QPushButton("Process Lot Number Ranges")
        self.process_btn.clicked.connect(self.process_data)
        self.process_btn.setEnabled(False)
        self.process_btn.setStyleSheet(
            "QPushButton { background-color: #e74c3c; color: white; font-weight: bold; padding: 10px; }")
        layout.addWidget(self.process_btn)

        return layout

    def import_excel(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Excel File",
            "",
            "Excel Files (*.xlsx *.xls)"
        )

        if file_path:
            self.current_file_path = file_path
            self.file_label.setText(os.path.basename(file_path))
            self.process_btn.setEnabled(True)
            self.export_btn.setEnabled(False)
            self.log(f"Importing Excel file: {file_path}")

            # Start loading thread
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)

            self.loader = ExcelProcessor(file_path, action="load")
            self.loader.data_loaded.connect(self.excel_loaded)
            self.loader.progress_updated.connect(self.update_progress)
            self.loader.error_occurred.connect(self.loading_error)
            self.loader.start()

    def excel_loaded(self, dc_data, mb_data):
        self.dc_data = dc_data
        self.mb_data = mb_data
        self.dc_processed = pd.DataFrame()
        self.mb_processed = pd.DataFrame()

        # Display data in tables (tables now handle dynamic column sizing)
        self.original_dc_tab.load_data(dc_data)
        self.original_mb_tab.load_data(mb_data)
        self.processed_dc_tab.load_data(pd.DataFrame())
        self.processed_mb_tab.load_data(pd.DataFrame())

        self.progress_bar.setVisible(False)
        self.log("Excel file loaded successfully!")
        self.log(f"DC data: {len(dc_data)} rows. Columns: {list(dc_data.columns)}")
        self.log(f"MB data: {len(mb_data)} rows. Columns: {list(mb_data.columns)}")

        # Switch to first tab
        self.tab_widget.setCurrentIndex(0)

    def process_data(self):
        if not self.current_file_path:
            QMessageBox.warning(self, "Warning", "Please import an Excel file first.")
            return

        if self.dc_data.empty and self.mb_data.empty:
            QMessageBox.warning(self, "Warning", "No data available to process.")
            return

        # Disable buttons during processing
        self.process_btn.setEnabled(False)
        self.select_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        self.log("Starting lot number range processing...")

        # Start processing thread
        self.processor = ExcelProcessor(
            self.current_file_path,
            self.dc_checkbox.isChecked(),
            self.mb_checkbox.isChecked(),
            action="process"
        )
        self.processor.progress_updated.connect(self.update_progress)
        self.processor.processing_finished.connect(self.processing_complete)
        self.processor.error_occurred.connect(self.processing_error)
        self.processor.start()

    def processing_complete(self, dc_processed, mb_processed):
        self.dc_processed = dc_processed
        self.mb_processed = mb_processed

        # Display processed data
        self.processed_dc_tab.load_data(dc_processed)
        self.processed_mb_tab.load_data(mb_processed)

        self.progress_bar.setVisible(False)
        self.process_btn.setEnabled(True)
        self.select_btn.setEnabled(True)
        self.export_btn.setEnabled(True)

        # Calculate statistics
        dc_original_count = len(self.dc_data) if not self.dc_data.empty else 0
        dc_processed_count = len(dc_processed) if not dc_processed.empty else 0
        mb_original_count = len(self.mb_data) if not self.mb_data.empty else 0
        mb_processed_count = len(mb_processed) if not mb_processed.empty else 0

        self.log("Processing completed successfully!")
        self.log(
            f"DC: {dc_original_count} → {dc_processed_count} rows. Output Columns: {list(dc_processed.columns) if not dc_processed.empty else 'N/A'}")
        self.log(
            f"MB: {mb_original_count} → {mb_processed_count} rows. Output Columns: {list(mb_processed.columns) if not mb_processed.empty else 'N/A'}")

        # Show example of processed quantities
        if not dc_processed.empty:
            sample_qty = dc_processed['QTY'].iloc[0] if len(dc_processed) > 0 else 0
            self.log(f"Sample QTY format: {sample_qty:.2f}")

        # Switch to processed tabs
        if not dc_processed.empty:
            self.tab_widget.setCurrentIndex(2)  # Processed DC tab
        elif not mb_processed.empty:
            self.tab_widget.setCurrentIndex(3)  # Processed MB tab

    def export_data(self):
        if self.dc_processed.empty and self.mb_processed.empty:
            QMessageBox.warning(self, "Warning", "No processed data to export.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Processed Data",
            "processed_lot_data.xlsx",
            "Excel Files (*.xlsx)"
        )

        if file_path:
            try:
                with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
                    if not self.dc_processed.empty:
                        # Prepare DC export: Ensure QTY is rounded, and BOX_NUMBER (if present) is cast to integer type (Int64 handles NaN)
                        dc_export = self.dc_processed.copy()
                        dc_export['QTY'] = dc_export['QTY'].round(2)
                        if 'BOX_NUMBER' in dc_export.columns:
                            # Convert to nullable integer type for export
                            dc_export['BOX_NUMBER'] = pd.to_numeric(dc_export['BOX_NUMBER'], errors='coerce').astype(
                                'Int64')
                        dc_export.to_excel(writer, sheet_name='dc_processed', index=False)

                    if not self.mb_processed.empty:
                        # Prepare MB export
                        mb_export = self.mb_processed.copy()
                        mb_export['QTY'] = mb_export['QTY'].round(2)
                        if 'BOX_NUMBER' in mb_export.columns:
                            # Convert to nullable integer type for export
                            mb_export['BOX_NUMBER'] = pd.to_numeric(mb_export['BOX_NUMBER'], errors='coerce').astype(
                                'Int64')
                        mb_export.to_excel(writer, sheet_name='mb_processed', index=False)

                self.log(f"Data exported successfully to: {file_path}")
                self.log("QTY formatted to 2 decimal places. BOX_NUMBER exported as whole numbers.")
                QMessageBox.information(self, "Export Successful",
                                        f"Data exported to:\n{file_path}\n\nQuantities formatted to 2 decimal places, Box numbers as whole integers.")

            except Exception as e:
                error_msg = f"Error exporting data: {str(e)}"
                self.log(error_msg)
                QMessageBox.critical(self, "Export Error", error_msg)

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def processing_error(self, error_message):
        self.process_btn.setEnabled(True)
        self.select_btn.setEnabled(True)
        self.progress_bar.setVisible(False)

        self.log(f"Processing Error: {error_message}")
        QMessageBox.critical(self, "Processing Error", error_message)

    def loading_error(self, error_message):
        self.progress_bar.setVisible(False)
        self.log(f"Loading Error: {error_message}")
        QMessageBox.critical(self, "Loading Error", error_message)

    def log(self, message):
        self.log_area.append(f"[{pd.Timestamp.now().strftime('%H:%M:%S')}] {message}")


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # Modern style
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()