import pandas as pd
import tkinter as tk
from tkinter import filedialog

# Hide tkinter root window
root = tk.Tk()
root.withdraw()

# Ask user to select input Excel file
input_file = filedialog.askopenfilename(
    title="Select Excel File",
    filetypes=[("Excel files", "*.xlsx *.xls")]
)

if input_file:
    # Load Excel file
    df = pd.read_excel(input_file, sheet_name="Sheet1")

    # Calculate total WT per LOT_NUM
    lot_totals = df.groupby("LOT_NUM")["WT"].transform("sum")

    # Add new column with totals
    df["TOTAL_WT_PER_LOT"] = lot_totals

    # Keep only the requested columns
    df_filtered = df[["PRODID-01", "PRODID-02", "CUSTOMER", "PRODCODE", "LOT_NUM", "TOTAL_WT_PER_LOT"]]

    # Drop duplicates so each LOT_NUM is shown once
    df_filtered = df_filtered.drop_duplicates()

    # Ask where to save the output file
    output_file = filedialog.asksaveasfilename(
        defaultextension=".xlsx",
        filetypes=[("Excel files", "*.xlsx *.xls")],
        title="Save filtered file as..."
    )

    if output_file:
        df_filtered.to_excel(output_file, index=False)
        print(f"File saved as {output_file}")
    else:
        print("Save cancelled.")
else:
    print("No file selected.")
