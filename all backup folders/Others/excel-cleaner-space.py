import pandas as pd
import tkinter as tk
from tkinter import filedialog, messagebox
import os


def clean_excel_file(file_path):
    """
    Reads an Excel file, removes all spaces from text cells in all sheets,
    and saves the result to a new file.
    """
    try:
        print(f"Reading Excel file: {file_path}")
        # Read all sheets from the Excel file into a dictionary of DataFrames
        excel_data = pd.read_excel(file_path, sheet_name=None)

        cleaned_sheets = {}

        # Loop through each sheet in the workbook
        for sheet_name, df in excel_data.items():
            print(f"Processing sheet: {sheet_name}...")

            # Use applymap to apply a function to every cell in the DataFrame
            # This function checks if a cell is a string. If it is, it removes all spaces.
            # If it's not a string (e.g., a number, date), it leaves it as is.
            cleaned_df = df.applymap(lambda x: x.replace(' ', '') if isinstance(x, str) else x)
            cleaned_sheets[sheet_name] = cleaned_df

        # --- Create the output file path ---
        # Get the directory and the original filename
        dir_name = os.path.dirname(file_path)
        base_name = os.path.basename(file_path)

        # Split the filename into its name and extension
        file_name, file_ext = os.path.splitext(base_name)

        # Create the new filename
        output_filename = f"{file_name}_cleaned{file_ext}"
        output_path = os.path.join(dir_name, output_filename)

        print(f"Saving cleaned file to: {output_path}")

        # --- Save the cleaned data to a new Excel file ---
        # Use ExcelWriter to save multiple sheets
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            for sheet_name, cleaned_df in cleaned_sheets.items():
                # Write each cleaned DataFrame to its corresponding sheet in the new file
                # index=False prevents pandas from writing the DataFrame index as a column
                cleaned_df.to_excel(writer, sheet_name=sheet_name, index=False)

        # Show a success message to the user
        messagebox.showinfo("Success", f"File cleaned successfully!\n\nSaved as: {output_path}")

    except Exception as e:
        # Show an error message if something goes wrong
        messagebox.showerror("Error", f"An error occurred: {e}")
        print(f"Error: {e}")


def main():
    """
    Main function to set up the Tkinter root and open the file dialog.
    """
    # Create the main Tkinter window
    root = tk.Tk()
    # Hide the main window because we only need the file dialog
    root.withdraw()

    # Open a file dialog to ask the user to select a file
    file_path = filedialog.askopenfilename(
        title="Select an Excel File to Clean",
        filetypes=[("Excel Files", "*.xlsx *.xls"), ("All files", "*.*")]
    )

    # If the user selected a file (and didn't cancel)
    if file_path:
        clean_excel_file(file_path)
    else:
        print("No file selected. Exiting.")


# This ensures the script runs the main function when executed
if __name__ == "__main__":
    main()