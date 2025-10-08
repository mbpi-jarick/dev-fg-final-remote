import pandas as pd
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import numpy as np
import os
import re


class ExcelComparator:
    def __init__(self, root):
        self.root = root
        self.root.title("Excel File Comparator by Lot Number")
        self.root.geometry("1200x800")

        # Variables to store file paths
        self.file1_path = tk.StringVar()
        self.file2_path = tk.StringVar()

        # Variables to store dataframes
        self.df1 = None
        self.df2 = None
        self.comparison_result = None

        # Comparison mode
        self.comparison_mode = tk.StringVar(value="lot_number")  # lot_number or product_code

        self.create_widgets()

    def create_widgets(self):
        # Create notebook (tabbed interface)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=5)

        # Create tabs
        self.file_selection_tab = ttk.Frame(self.notebook)
        self.results_tab = ttk.Frame(self.notebook)
        self.summary_tab = ttk.Frame(self.notebook)

        self.notebook.add(self.file_selection_tab, text="File Selection")
        self.notebook.add(self.results_tab, text="Comparison Results")
        self.notebook.add(self.summary_tab, text="Summary")

        # Setup each tab
        self.setup_file_selection_tab()
        self.setup_results_tab()
        self.setup_summary_tab()

    def setup_file_selection_tab(self):
        # File selection frame
        file_frame = ttk.LabelFrame(self.file_selection_tab, text="File Selection", padding="10")
        file_frame.pack(fill="x", padx=10, pady=5)

        # File 1 selection
        ttk.Label(file_frame, text="Production File (ver-1-prod.xlsx):").grid(row=0, column=0, sticky="w", pady=5)
        ttk.Entry(file_frame, textvariable=self.file1_path, width=70).grid(row=0, column=1, padx=5)
        ttk.Button(file_frame, text="Browse", command=self.browse_file1).grid(row=0, column=2, padx=5)

        # File 2 selection
        ttk.Label(file_frame, text="Modified File (ver-1-orig-mod.xlsx):").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(file_frame, textvariable=self.file2_path, width=70).grid(row=1, column=1, padx=5)
        ttk.Button(file_frame, text="Browse", command=self.browse_file2).grid(row=1, column=2, padx=5)

        # Comparison mode selection
        ttk.Label(file_frame, text="Comparison Mode:").grid(row=2, column=0, sticky="w", pady=5)
        mode_frame = ttk.Frame(file_frame)
        mode_frame.grid(row=2, column=1, sticky="w", pady=5)
        ttk.Radiobutton(mode_frame, text="By Lot Number", variable=self.comparison_mode, value="lot_number").pack(
            side="left")
        ttk.Radiobutton(mode_frame, text="By Product Code", variable=self.comparison_mode, value="product_code").pack(
            side="left")

        # Compare button
        ttk.Button(file_frame, text="Compare Files", command=self.compare_files).grid(row=3, column=1, pady=10)

        # File info frame
        info_frame = ttk.LabelFrame(self.file_selection_tab, text="File Information", padding="10")
        info_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # File 1 info
        ttk.Label(info_frame, text="File 1 Info:").grid(row=0, column=0, sticky="w", pady=5)
        self.file1_info = tk.Text(info_frame, height=5, width=80)
        self.file1_info.grid(row=1, column=0, padx=5, pady=5, sticky="nsew")

        # File 2 info
        ttk.Label(info_frame, text="File 2 Info:").grid(row=2, column=0, sticky="w", pady=5)
        self.file2_info = tk.Text(info_frame, height=5, width=80)
        self.file2_info.grid(row=3, column=0, padx=5, pady=5, sticky="nsew")

        # Configure grid weights for proper resizing
        info_frame.grid_rowconfigure(1, weight=1)
        info_frame.grid_rowconfigure(3, weight=1)
        info_frame.grid_columnconfigure(0, weight=1)

    def setup_results_tab(self):
        # Create notebook within results tab for different views
        self.results_notebook = ttk.Notebook(self.results_tab)
        self.results_notebook.pack(fill="both", expand=True, padx=10, pady=5)

        # All results tab
        self.all_results_frame = ttk.Frame(self.results_notebook)
        self.results_notebook.add(self.all_results_frame, text="All Results")

        # Treeview for all results
        self.tree = ttk.Treeview(self.all_results_frame,
                                 columns=(
                                 "Product Code", "Lot Number", "File1 Qty", "File2 Qty", "Difference", "Status"),
                                 show="headings")

        # Define headings
        self.tree.heading("Product Code", text="Product Code")
        self.tree.heading("Lot Number", text="Lot Number")
        self.tree.heading("File1 Qty", text="File1 Qty")
        self.tree.heading("File2 Qty", text="File2 Qty")
        self.tree.heading("Difference", text="Difference")
        self.tree.heading("Status", text="Status")

        # Define column widths
        self.tree.column("Product Code", width=120)
        self.tree.column("Lot Number", width=150)
        self.tree.column("File1 Qty", width=100)
        self.tree.column("File2 Qty", width=100)
        self.tree.column("Difference", width=100)
        self.tree.column("Status", width=100)

        # Add scrollbar
        scrollbar = ttk.Scrollbar(self.all_results_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        # Pack tree and scrollbar
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Create tabs for different status categories
        self.create_status_tabs()

    def create_status_tabs(self):
        # Matches tab
        self.matches_frame = ttk.Frame(self.results_notebook)
        self.results_notebook.add(self.matches_frame, text="Matches")
        self.matches_tree = self.create_treeview_for_status(self.matches_frame)

        # Mismatches tab
        self.mismatches_frame = ttk.Frame(self.results_notebook)
        self.results_notebook.add(self.mismatches_frame, text="Mismatches")
        self.mismatches_tree = self.create_treeview_for_status(self.mismatches_frame)

        # Only in File1 tab
        self.only_file1_frame = ttk.Frame(self.results_notebook)
        self.results_notebook.add(self.only_file1_frame, text="Only in File1")
        self.only_file1_tree = self.create_treeview_for_status(self.only_file1_frame)

        # Only in File2 tab
        self.only_file2_frame = ttk.Frame(self.results_notebook)
        self.results_notebook.add(self.only_file2_frame, text="Only in File2")
        self.only_file2_tree = self.create_treeview_for_status(self.only_file2_frame)

    def create_treeview_for_status(self, parent):
        tree = ttk.Treeview(parent,
                            columns=("Product Code", "Lot Number", "File1 Qty", "File2 Qty", "Difference", "Status"),
                            show="headings")

        # Define headings
        tree.heading("Product Code", text="Product Code")
        tree.heading("Lot Number", text="Lot Number")
        tree.heading("File1 Qty", text="File1 Qty")
        tree.heading("File2 Qty", text="File2 Qty")
        tree.heading("Difference", text="Difference")
        tree.heading("Status", text="Status")

        # Define column widths
        tree.column("Product Code", width=120)
        tree.column("Lot Number", width=150)
        tree.column("File1 Qty", width=100)
        tree.column("File2 Qty", width=100)
        tree.column("Difference", width=100)
        tree.column("Status", width=100)

        # Add scrollbar
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)

        # Pack tree and scrollbar
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        return tree

    def setup_summary_tab(self):
        # Summary frame
        summary_frame = ttk.LabelFrame(self.summary_tab, text="Comparison Summary", padding="10")
        summary_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # Summary text widget
        self.summary_text = tk.Text(summary_frame, height=20, width=100)
        self.summary_text.pack(fill="both", expand=True, padx=5, pady=5)

        # Export button
        ttk.Button(summary_frame, text="Export Summary to CSV", command=self.export_summary).pack(pady=10)

    def browse_file1(self):
        file_path = filedialog.askopenfilename(
            title="Select Production File",
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")]
        )
        if file_path:
            self.file1_path.set(file_path)
            self.display_file_info(file_path, self.file1_info)

    def browse_file2(self):
        file_path = filedialog.askopenfilename(
            title="Select Modified File",
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")]
        )
        if file_path:
            self.file2_path.set(file_path)
            self.display_file_info(file_path, self.file2_info)

    def display_file_info(self, file_path, text_widget):
        try:
            df = pd.read_excel(file_path)
            info = f"File: {os.path.basename(file_path)}\n"
            info += f"Shape: {df.shape[0]} rows, {df.shape[1]} columns\n"
            info += f"Columns: {', '.join(df.columns)}\n"
            info += f"First 5 rows:\n{df.head().to_string()}"

            text_widget.delete(1.0, tk.END)
            text_widget.insert(1.0, info)
        except Exception as e:
            text_widget.delete(1.0, tk.END)
            text_widget.insert(1.0, f"Error reading file: {str(e)}")

    def expand_lot_numbers(self, df, lot_col, qty_col):
        """Expand lot number ranges into individual lot numbers"""
        expanded_rows = []

        for _, row in df.iterrows():
            lot_value = str(row[lot_col])

            # Check if this is a range (contains hyphen)
            if '-' in lot_value and not lot_value.startswith('DU-') and not lot_value.startswith('PP-'):
                try:
                    # Handle lot number ranges like "6266AM-6268AM"
                    start, end = lot_value.split('-')

                    # Extract the numeric part and suffix
                    start_num = re.search(r'(\d+)([A-Z]*)', start)
                    end_num = re.search(r'(\d+)([A-Z]*)', end)

                    if start_num and end_num:
                        start_num_val = int(start_num.group(1))
                        end_num_val = int(end_num.group(1))
                        suffix = start_num.group(2)  # Assume both have same suffix

                        # Calculate quantity per lot
                        num_lots = end_num_val - start_num_val + 1
                        qty_per_lot = row[qty_col] / num_lots

                        # Create individual lot entries
                        for lot_num in range(start_num_val, end_num_val + 1):
                            new_row = row.copy()
                            new_row[lot_col] = f"{lot_num}{suffix}"
                            new_row[qty_col] = qty_per_lot
                            expanded_rows.append(new_row)
                    else:
                        # If we can't parse the range, keep the original
                        expanded_rows.append(row)
                except:
                    # If anything goes wrong, keep the original row
                    expanded_rows.append(row)
            else:
                # Not a range, keep as is
                expanded_rows.append(row)

        return pd.DataFrame(expanded_rows)

    def compare_files(self):
        if not self.file1_path.get() or not self.file2_path.get():
            messagebox.showerror("Error", "Please select both files")
            return

        try:
            # Read the files
            self.df1 = pd.read_excel(self.file1_path.get())
            self.df2 = pd.read_excel(self.file2_path.get())

            # Clean column names (remove extra spaces and make lowercase)
            self.df1.columns = self.df1.columns.str.strip().str.lower()
            self.df2.columns = self.df2.columns.str.strip().str.lower()

            # Check if required columns exist
            if 'product code' not in self.df1.columns or 'qty. produced' not in self.df1.columns or 'lot#' not in self.df1.columns:
                messagebox.showerror("Error", "File 1 must contain 'PRODUCT CODE', 'LOT#', and 'QTY. PRODUCED' columns")
                return

            if 'prodcode' not in self.df2.columns or 'total_wt_per_lot' not in self.df2.columns or 'lot_num' not in self.df2.columns:
                messagebox.showerror("Error",
                                     "File 2 must contain 'PRODCODE', 'LOT_NUM', and 'TOTAL_WT_PER_LOT' columns")
                return

            # Expand lot number ranges
            self.df1_expanded = self.expand_lot_numbers(self.df1, 'lot#', 'qty. produced')
            self.df2_expanded = self.expand_lot_numbers(self.df2, 'lot_num', 'total_wt_per_lot')

            if self.comparison_mode.get() == "lot_number":
                # Compare by lot number
                self.compare_by_lot_number()
            else:
                # Compare by product code
                self.compare_by_product_code()

            # Display results
            self.display_results()

            # Update summary
            self.update_summary()

            # Switch to results tab
            self.notebook.select(1)

        except Exception as e:
            messagebox.showerror("Error", f"An error occurred: {str(e)}")

    def compare_by_lot_number(self):
        # --- NEW: Clean and prepare the dataframes ---
        # Rename columns for consistency before merging
        df1_prep = self.df1_expanded.rename(
            columns={'product code': 'Product Code', 'lot#': 'Lot Number', 'qty. produced': 'File1 Qty'})
        df2_prep = self.df2_expanded.rename(
            columns={'prodcode': 'Product Code', 'lot_num': 'Lot Number', 'total_wt_per_lot': 'File2 Qty'})

        # Select only the relevant columns to avoid confusion from other columns
        df1_prep = df1_prep[['Product Code', 'Lot Number', 'File1 Qty']]
        df2_prep = df2_prep[['Product Code', 'Lot Number', 'File2 Qty']]

        # --- MODIFIED: Merge primarily on 'Lot Number' ---
        # This will correctly identify rows with the same lot number, regardless of product code discrepancies.
        merged_df = pd.merge(
            df1_prep,
            df2_prep,
            on='Lot Number',  # Merge ONLY on Lot Number
            how='outer',
            indicator=True,
            suffixes=('_file1', '_file2')
        )

        # Create comparison result
        self.comparison_result = pd.DataFrame()

        # --- NEW LOGIC for handling Product Codes ---
        # Use the product code from File 1 if it exists, otherwise use the one from File 2.
        # This makes the output clearer when product codes differ for the same lot number.
        self.comparison_result['Product Code'] = merged_df['Product Code_file1'].combine_first(
            merged_df['Product Code_file2'])

        self.comparison_result['Lot Number'] = merged_df['Lot Number']
        self.comparison_result['File1 Qty'] = merged_df['File1 Qty']
        self.comparison_result['File2 Qty'] = merged_df['File2 Qty']

        # Fill NaN quantities with 0 for accurate difference calculation
        self.comparison_result['Difference'] = self.comparison_result['File1 Qty'].fillna(0) - self.comparison_result[
            'File2 Qty'].fillna(0)

        # --- REFINED: Add status column with more precise logic ---
        conditions = [
            (merged_df['_merge'] == 'left_only'),
            (merged_df['_merge'] == 'right_only'),
            # A 'match' requires quantities to be almost equal AND product codes to be the same.
            ((abs(self.comparison_result['Difference']) < 0.01) & (
                        merged_df['Product Code_file1'] == merged_df['Product Code_file2'])),
            # Anything else that is in 'both' is a mismatch (either qty diff or product code diff)
            (merged_df['_merge'] == 'both')
        ]
        choices = [
            'Only in File1',
            'Only in File2',
            'Match',
            'Mismatch'  # This is the crucial default for all 'both' cases that are not a perfect match
        ]
        self.comparison_result['Status'] = np.select(conditions, choices, default='Unknown')

        # To prevent showing 0.00 in difference for "Only in..." rows for clarity
        self.comparison_result.loc[
            self.comparison_result['Status'].isin(['Only in File1', 'Only in File2']), 'Difference'] = np.nan

    def compare_by_product_code(self):
        # Group by product code and sum quantities for both files
        df1_grouped = self.df1_expanded.groupby('product code')['qty. produced'].sum().reset_index()
        df2_grouped = self.df2_expanded.groupby('prodcode')['total_wt_per_lot'].sum().reset_index()

        # Merge the dataframes
        merged_df = pd.merge(
            df1_grouped,
            df2_grouped,
            left_on='product code',
            right_on='prodcode',
            how='outer',
            indicator=True
        )

        # Create comparison result
        self.comparison_result = pd.DataFrame()
        self.comparison_result['Product Code'] = merged_df['product code'].combine_first(merged_df['prodcode'])
        self.comparison_result['Lot Number'] = "N/A"  # Not applicable for product code comparison
        self.comparison_result['File1 Qty'] = merged_df['qty. produced']
        self.comparison_result['File2 Qty'] = merged_df['total_wt_per_lot']
        self.comparison_result['Difference'] = self.comparison_result['File1 Qty'] - self.comparison_result['File2 Qty']

        # Add status column
        conditions = [
            (merged_df['_merge'] == 'left_only'),
            (merged_df['_merge'] == 'right_only'),
            (abs(self.comparison_result['Difference']) < 0.01),  # Considering floating point precision
            (abs(self.comparison_result['Difference']) >= 0.01)
        ]
        choices = [
            'Only in File1',
            'Only in File2',
            'Match',
            'Mismatch'
        ]
        self.comparison_result['Status'] = np.select(conditions, choices, default='Unknown')

    def display_results(self):
        # Clear existing items in all treeviews
        for tree in [self.tree, self.matches_tree, self.mismatches_tree, self.only_file1_tree, self.only_file2_tree]:
            for item in tree.get_children():
                tree.delete(item)

        # Add data to treeviews
        for _, row in self.comparison_result.iterrows():
            values = (
                row['Product Code'],
                row['Lot Number'],
                f"{row['File1 Qty']:.2f}" if pd.notna(row['File1 Qty']) else "N/A",
                f"{row['File2 Qty']:.2f}" if pd.notna(row['File2 Qty']) else "N/A",
                f"{row['Difference']:.2f}" if pd.notna(row['Difference']) else "N/A",
                row['Status']
            )

            # Add to main treeview
            self.tree.insert("", "end", values=values)

            # Add to specific treeview based on status
            if row['Status'] == 'Match':
                self.matches_tree.insert("", "end", values=values)
                self.matches_tree.item(self.matches_tree.get_children()[-1], tags=('match',))
            elif row['Status'] == 'Mismatch':
                self.mismatches_tree.insert("", "end", values=values)
                self.mismatches_tree.item(self.mismatches_tree.get_children()[-1], tags=('mismatch',))
            elif row['Status'] == 'Only in File1':
                self.only_file1_tree.insert("", "end", values=values)
                self.only_file1_tree.item(self.only_file1_tree.get_children()[-1], tags=('only1',))
            elif row['Status'] == 'Only in File2':
                self.only_file2_tree.insert("", "end", values=values)
                self.only_file2_tree.item(self.only_file2_tree.get_children()[-1], tags=('only2',))

            # Color code based on status in main treeview
            if row['Status'] == 'Match':
                self.tree.item(self.tree.get_children()[-1], tags=('match',))
            elif row['Status'] == 'Mismatch':
                self.tree.item(self.tree.get_children()[-1], tags=('mismatch',))
            elif row['Status'] == 'Only in File1':
                self.tree.item(self.tree.get_children()[-1], tags=('only1',))
            elif row['Status'] == 'Only in File2':
                self.tree.item(self.tree.get_children()[-1], tags=('only2',))

        # Configure tags for colors
        for tree in [self.tree, self.matches_tree, self.mismatches_tree, self.only_file1_tree, self.only_file2_tree]:
            tree.tag_configure('match', background='lightgreen')
            tree.tag_configure('mismatch', background='lightcoral')
            tree.tag_configure('only1', background='lightyellow')
            tree.tag_configure('only2', background='lightblue')

    def update_summary(self):
        # Calculate summary statistics
        total_records = len(self.comparison_result)
        matches = len(self.comparison_result[self.comparison_result['Status'] == 'Match'])
        mismatches = len(self.comparison_result[self.comparison_result['Status'] == 'Mismatch'])
        only_file1 = len(self.comparison_result[self.comparison_result['Status'] == 'Only in File1'])
        only_file2 = len(self.comparison_result[self.comparison_result['Status'] == 'Only in File2'])

        # Calculate quantity totals
        total_file1_qty = self.comparison_result['File1 Qty'].sum()
        total_file2_qty = self.comparison_result['File2 Qty'].sum()
        total_difference = total_file1_qty - total_file2_qty

        # Calculate totals by status
        match_qty_file1 = self.comparison_result[self.comparison_result['Status'] == 'Match']['File1 Qty'].sum()
        match_qty_file2 = self.comparison_result[self.comparison_result['Status'] == 'Match']['File2 Qty'].sum()

        mismatch_qty_file1 = self.comparison_result[self.comparison_result['Status'] == 'Mismatch']['File1 Qty'].sum()
        mismatch_qty_file2 = self.comparison_result[self.comparison_result['Status'] == 'Mismatch']['File2 Qty'].sum()

        only_file1_qty = self.comparison_result[self.comparison_result['Status'] == 'Only in File1']['File1 Qty'].sum()
        only_file2_qty = self.comparison_result[self.comparison_result['Status'] == 'Only in File2']['File2 Qty'].sum()

        # Create summary text
        summary_text = f"COMPARISON SUMMARY\n"
        summary_text += "=" * 50 + "\n\n"

        summary_text += f"Comparison Mode: {'By Lot Number' if self.comparison_mode.get() == 'lot_number' else 'By Product Code'}\n\n"

        summary_text += f"Total Records: {total_records}\n"
        summary_text += f"Matches: {matches} ({matches / total_records * 100:.1f}%)\n"
        summary_text += f"Mismatches: {mismatches} ({mismatches / total_records * 100:.1f}%)\n"
        summary_text += f"Only in File1: {only_file1} ({only_file1 / total_records * 100:.1f}%)\n"
        summary_text += f"Only in File2: {only_file2} ({only_file2 / total_records * 100:.1f}%)\n\n"

        summary_text += f"Total File1 Quantity: {total_file1_qty:.2f}\n"
        summary_text += f"Total File2 Quantity: {total_file2_qty:.2f}\n"
        summary_text += f"Total Difference: {total_difference:.2f}\n\n"

        summary_text += "BREAKDOWN BY STATUS\n"
        summary_text += "-" * 30 + "\n"
        summary_text += f"Matches - File1 Qty: {match_qty_file1:.2f}, File2 Qty: {match_qty_file2:.2f}\n"
        summary_text += f"Mismatches - File1 Qty: {mismatch_qty_file1:.2f}, File2 Qty: {mismatch_qty_file2:.2f}\n"
        summary_text += f"Only in File1 - Qty: {only_file1_qty:.2f}\n"
        summary_text += f"Only in File2 - Qty: {only_file2_qty:.2f}\n\n"

        summary_text += "FILE INFORMATION\n"
        summary_text += "-" * 30 + "\n"
        summary_text += f"File1: {os.path.basename(self.file1_path.get())}\n"
        summary_text += f"File2: {os.path.basename(self.file2_path.get())}\n"

        # Update summary text widget
        self.summary_text.delete(1.0, tk.END)
        self.summary_text.insert(1.0, summary_text)

    def export_summary(self):
        if self.comparison_result is None:
            messagebox.showerror("Error", "No comparison results to export")
            return

        file_path = filedialog.asksaveasfilename(
            title="Save Summary CSV",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )

        if file_path:
            try:
                # Export the comparison results
                self.comparison_result.to_csv(file_path, index=False)
                messagebox.showinfo("Success", f"Summary exported to {file_path}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to export summary: {str(e)}")


# Run the application
if __name__ == "__main__":
    root = tk.Tk()
    app = ExcelComparator(root)
    root.mainloop()