import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import pandas as pd
import numpy as np


class ReconciliationApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Production Data Reconciliation Tool")
        self.root.geometry("900x700")

        # Variables to store data
        self.df_sheet1 = None
        self.df_sheet2 = None
        self.df_sheet3 = None

        self.create_widgets()

    def create_widgets(self):
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Title
        title_label = ttk.Label(main_frame, text="Production Data Reconciliation Tool",
                                font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=2, pady=10)

        # File selection button
        file_button = ttk.Button(main_frame, text="Select Excel File",
                                 command=self.load_excel_file)
        file_button.grid(row=1, column=0, columnspan=2, pady=5)

        # File path label
        self.file_path_label = ttk.Label(main_frame, text="No file selected",
                                         foreground="gray")
        self.file_path_label.grid(row=2, column=0, columnspan=2, pady=2)

        # Analyze button
        self.analyze_button = ttk.Button(main_frame, text="Generate Reconciliation Report",
                                         command=self.generate_report, state="disabled")
        self.analyze_button.grid(row=3, column=0, columnspan=2, pady=10)

        # Report area
        report_label = ttk.Label(main_frame, text="Reconciliation Report:",
                                 font=("Arial", 12, "bold"))
        report_label.grid(row=4, column=0, sticky=tk.W, pady=(20, 5))

        self.report_text = scrolledtext.ScrolledText(main_frame, width=100, height=25,
                                                     wrap=tk.WORD, font=("Consolas", 10))
        self.report_text.grid(row=5, column=0, columnspan=2, pady=5, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Status bar
        self.status_var = tk.StringVar()
        self.status_var.set("Ready")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.grid(row=6, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(5, weight=1)

    def load_excel_file(self):
        file_path = filedialog.askopenfilename(
            title="Select Excel File",
            filetypes=[("Excel files", "*.xlsx *.xls"), ("All files", "*.*")]
        )

        if not file_path:
            return

        try:
            self.status_var.set("Loading file...")
            self.root.update()

            # Load all three sheets
            self.df_sheet1 = pd.read_excel(file_path, sheet_name=0)  # Sheet1
            self.df_sheet2 = pd.read_excel(file_path, sheet_name=1)  # Sheet2
            self.df_sheet3 = pd.read_excel(file_path, sheet_name=2)  # Sheet3

            self.file_path_label.config(text=f"Loaded: {file_path.split('/')[-1]}")
            self.analyze_button.config(state="normal")
            self.status_var.set("File loaded successfully. Ready to analyze.")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to load file:\n{str(e)}")
            self.status_var.set("Error loading file")

    def generate_report(self):
        if self.df_sheet1 is None or self.df_sheet2 is None or self.df_sheet3 is None:
            messagebox.showwarning("Warning", "Please load an Excel file first.")
            return

        try:
            self.status_var.set("Analyzing data...")
            self.root.update()

            # Add source columns
            self.df_sheet1['Source'] = 'Sheet1'
            self.df_sheet2['Source'] = 'Sheet2'
            self.df_sheet3['Source'] = 'Sheet3'

            # Combine all data
            combined_df = pd.concat([self.df_sheet1, self.df_sheet2, self.df_sheet3], ignore_index=True)

            # Create a unique key for each production-material combination
            combined_df['Key'] = combined_df['prod_id'].astype(str) + '_' + combined_df['mat_code']

            # Find missing productions
            prod_id_summary = combined_df.groupby(['prod_id', 'Source']).size().unstack(fill_value=0)
            missing_productions = prod_id_summary[(prod_id_summary == 0).any(axis=1)]

            # Find discrepancies for rows that exist in multiple sources
            pivoted = combined_df.pivot_table(
                index=['prod_id', 'mat_code'],
                columns='Source',
                values=['mat_wt', 't_seq'],
                aggfunc='first'
            )

            # Flatten the column multi-index
            pivoted.columns = [f'{col[1]}_{col[0]}' for col in pivoted.columns]

            # Check for missing materials
            missing_materials = pivoted[pivoted.isna().any(axis=1)]

            # Check for weight discrepancies
            weight_discrepancies = pivoted.dropna()
            weight_discrepancies = weight_discrepancies[
                (weight_discrepancies['Sheet1_mat_wt'] != weight_discrepancies['Sheet2_mat_wt']) |
                (weight_discrepancies['Sheet1_mat_wt'] != weight_discrepancies['Sheet3_mat_wt']) |
                (weight_discrepancies['Sheet2_mat_wt'] != weight_discrepancies['Sheet3_mat_wt'])
                ]

            # Check for sequence discrepancies
            seq_discrepancies = pivoted.dropna()
            seq_discrepancies = seq_discrepancies[
                (seq_discrepancies['Sheet1_t_seq'] != seq_discrepancies['Sheet2_t_seq']) |
                (seq_discrepancies['Sheet1_t_seq'] != seq_discrepancies['Sheet3_t_seq']) |
                (seq_discrepancies['Sheet2_t_seq'] != seq_discrepancies['Sheet3_t_seq'])
                ]

            # Generate report
            report_lines = []
            report_lines.append("PRODUCTION DATA RECONCILIATION REPORT")
            report_lines.append("=" * 50)
            report_lines.append(f"Generated from: {self.file_path_label.cget('text').replace('Loaded: ', '')}")
            report_lines.append("")

            # 1. Missing Productions
            report_lines.append("1. MISSING PRODUCTION RUNS (prod_id):")
            report_lines.append("The following production IDs are missing from some sheets:")
            if not missing_productions.empty:
                for prod_id, row in missing_productions.iterrows():
                    missing_in = [sheet for sheet in row.index if row[sheet] == 0]
                    report_lines.append(f"   - prod_id {prod_id}: Missing in {', '.join(missing_in)}")
            else:
                report_lines.append("   - None found. All production IDs are present in all sheets.")
            report_lines.append("")

            # 2. Missing Materials
            report_lines.append("2. MISSING MATERIALS WITHIN PRODUCTION RUNS:")
            report_lines.append("The following material rows are missing for specific production IDs:")
            if not missing_materials.empty:
                for idx, row in missing_materials.iterrows():
                    prod_id, mat_code = idx
                    missing_sources = []
                    for col in ['Sheet1_mat_wt', 'Sheet2_mat_wt', 'Sheet3_mat_wt']:
                        if pd.isna(row[col]):
                            missing_sources.append(col.split('_')[0])
                    report_lines.append(
                        f"   - prod_id {prod_id}, mat_code {mat_code}: Missing in {', '.join(missing_sources)}")
            else:
                report_lines.append("   - None found. All material entries are consistent across sheets.")
            report_lines.append("")

            # 3. Weight Discrepancies
            report_lines.append("3. MATERIAL WEIGHT (mat_wt) DISCREPANCIES:")
            report_lines.append("The following entries have differing material weights:")
            if not weight_discrepancies.empty:
                for idx, row in weight_discrepancies.iterrows():
                    prod_id, mat_code = idx
                    report_lines.append(f"   - prod_id {prod_id}, mat_code {mat_code}:")
                    report_lines.append(f"        Sheet1: {row['Sheet1_mat_wt']}")
                    report_lines.append(f"        Sheet2: {row['Sheet2_mat_wt']}")
                    report_lines.append(f"        Sheet3: {row['Sheet3_mat_wt']}")
                    report_lines.append("")
            else:
                report_lines.append("   - None found. All material weights match across sheets.")
            report_lines.append("")

            # 4. Sequence Discrepancies
            report_lines.append("4. SEQUENCE (t_seq) DISCREPANCIES:")
            report_lines.append("The following entries have differing sequence numbers:")
            if not seq_discrepancies.empty:
                for idx, row in seq_discrepancies.iterrows():
                    prod_id, mat_code = idx
                    report_lines.append(f"   - prod_id {prod_id}, mat_code {mat_code}:")
                    report_lines.append(f"        Sheet1: {row['Sheet1_t_seq']}")
                    report_lines.append(f"        Sheet2: {row['Sheet2_t_seq']}")
                    report_lines.append(f"        Sheet3: {row['Sheet3_t_seq']}")
                    report_lines.append("")
            else:
                report_lines.append("   - None found. All sequence numbers match across sheets.")

            # Display report
            self.report_text.delete(1.0, tk.END)
            self.report_text.insert(1.0, "\n".join(report_lines))

            self.status_var.set("Analysis complete. Report generated.")

            # Offer to save report
            if messagebox.askyesno("Save Report", "Would you like to save this report to a text file?"):
                self.save_report("\n".join(report_lines))

        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate report:\n{str(e)}")
            self.status_var.set("Error generating report")

    def save_report(self, report_text):
        file_path = filedialog.asksaveasfilename(
            title="Save Report As",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )

        if file_path:
            try:
                with open(file_path, 'w') as f:
                    f.write(report_text)
                messagebox.showinfo("Success", f"Report saved successfully to:\n{file_path}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save report:\n{str(e)}")


def main():
    root = tk.Tk()
    app = ReconciliationApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()