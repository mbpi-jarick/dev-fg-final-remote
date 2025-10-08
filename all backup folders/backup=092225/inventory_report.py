# inventory_report.py
# FINAL FIX - Helper function included directly to resolve ModuleNotFoundError.

import sys
from decimal import Decimal
import traceback
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
                             QHeaderView, QMessageBox, QHBoxLayout, QLabel,
                             QPushButton, QDateEdit, QComboBox, QAbstractItemView)
from sqlalchemy import text
import pandas as pd


# --- HELPER FUNCTION ADDED DIRECTLY ---
def find_best_match_column(columns, keywords, priority_exact=None):
    """
    Finds the best matching column from a list of columns based on a prioritized search.
    """
    columns_lower = {c.lower(): c for c in columns}

    if priority_exact:
        for p_exact in priority_exact:
            if p_exact.lower() in columns_lower:
                return columns_lower[p_exact.lower()]

    for kw in keywords:
        for col_lower, col_original in columns_lower.items():
            if col_lower.startswith(kw):
                return col_original

    for kw in keywords:
        for col_lower, col_original in columns_lower.items():
            if kw in col_lower:
                return col_original

    return None


class InventoryReportPage(QWidget):
    def __init__(self, db_engine):
        super().__init__()
        self.engine = db_engine
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        filter_group_box = QWidget()
        filter_layout = QHBoxLayout(filter_group_box)
        filter_layout.setContentsMargins(0, 0, 0, 10)
        self.start_date_edit = QDateEdit(calendarPopup=True, displayFormat="yyyy-MM-dd")
        self.start_date_edit.setDate(QDate.currentDate().addMonths(-1))
        self.end_date_edit = QDateEdit(calendarPopup=True, displayFormat="yyyy-MM-dd")
        self.end_date_edit.setDate(QDate.currentDate())
        self.product_code_combo = QComboBox(editable=True)
        self.product_code_combo.setPlaceholderText("ALL PRODUCTS")
        self.generate_btn = QPushButton("Generate Report")
        self.generate_btn.setObjectName("PrimaryButton")
        filter_layout.addWidget(QLabel("Date Range:"))
        filter_layout.addWidget(self.start_date_edit)
        filter_layout.addWidget(QLabel("to"))
        filter_layout.addWidget(self.end_date_edit)
        filter_layout.addSpacing(20)
        filter_layout.addWidget(QLabel("Product Code:"))
        filter_layout.addWidget(self.product_code_combo, 1)
        filter_layout.addStretch()
        filter_layout.addWidget(self.generate_btn)
        layout.addWidget(filter_group_box)
        self.report_table = QTableWidget()
        self.report_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.report_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.report_table.verticalHeader().setVisible(False)
        self.report_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.report_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(self.report_table, 1)
        self.generate_btn.clicked.connect(self._generate_report)
        self._load_product_codes()

    def _load_product_codes(self):
        try:
            with self.engine.connect() as conn:
                query = text("""
                    (SELECT DISTINCT product_code FROM fg_endorsements_primary WHERE product_code IS NOT NULL AND product_code != '')
                    UNION
                    (SELECT DISTINCT prod_code AS product_code FROM legacy_production WHERE prod_code IS NOT NULL AND prod_code != '')
                    ORDER BY product_code;
                """)
                result = conn.execute(query).scalars().all()
            self.product_code_combo.clear()
            self.product_code_combo.addItem("ALL PRODUCTS")
            self.product_code_combo.addItems(result)
        except Exception as e:
            QMessageBox.warning(self, "Load Error", f"Could not load product codes: {e}")

    def _generate_report(self):
        start_date = self.start_date_edit.date().toString("yyyy-MM-dd")
        end_date = self.end_date_edit.date().toString("yyyy-MM-dd")
        product_filter = self.product_code_combo.currentText()
        try:
            self.generate_btn.setEnabled(False)
            self.generate_btn.setText("Generating...")
            QApplication.processEvents()
            begin_inv_df = self._get_beginning_inventory(product_filter)
            additions_df = self._get_additions(start_date, end_date, product_filter)
            removals_df = self._get_removals(start_date, end_date, product_filter)
            all_dfs = [begin_inv_df, additions_df, removals_df]

            valid_dfs = [df[['product_code', 'lot_number']] for df in all_dfs if not df.empty]
            if not valid_dfs:
                self._display_report(pd.DataFrame())
                return

            master_df = pd.concat(valid_dfs).drop_duplicates().reset_index(drop=True)

            if master_df.empty:
                self._display_report(pd.DataFrame())
                return

            if not begin_inv_df.empty:
                master_df = pd.merge(master_df, begin_inv_df, on=['product_code', 'lot_number'], how='left')
            if not additions_df.empty:
                master_df = pd.merge(master_df, additions_df, on=['product_code', 'lot_number'], how='left')
            if not removals_df.empty:
                master_df = pd.merge(master_df, removals_df, on=['product_code', 'lot_number'], how='left')

            final_report_df = master_df.fillna(0)

            for col in ['product_code', 'lot_number']:
                if col in final_report_df.columns:
                    final_report_df[col] = final_report_df[col].astype(str).str.strip()

            final_report_df = final_report_df[final_report_df['product_code'].str.lower() != 'nan']
            final_report_df = final_report_df[final_report_df['product_code'] != '']

            final_report_df['ending_qty'] = final_report_df['beginning_qty'] + final_report_df['additions_qty'] - \
                                            final_report_df['removals_qty']
            final_report_df = final_report_df.sort_values(by=['product_code', 'lot_number'])

            # Display only rows with a positive balance in the final report
            display_df = final_report_df[final_report_df['ending_qty'] > 0.001]
            self._display_report(display_df)
        except Exception as e:
            QMessageBox.critical(self, "Report Generation Error", f"An error occurred: {e}")
            print(f"Report Error: {traceback.format_exc()}")
        finally:
            self.generate_btn.setEnabled(True)
            self.generate_btn.setText("Generate Report")

    def _get_beginning_inventory(self, product_filter):
        empty_df = pd.DataFrame(columns=['product_code', 'lot_number', 'beginning_qty'])
        try:
            with self.engine.connect() as conn:
                all_tables_res = conn.execute(text(
                    "SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'beginv_%'")).mappings().all()
                if not all_tables_res: return empty_df
                all_tables = [row['table_name'] for row in all_tables_res]
                union_queries = []
                params = {}
                for i, tbl in enumerate(all_tables):
                    cols_res = conn.execute(text(
                        f"SELECT column_name FROM information_schema.columns WHERE table_name = '{tbl}'")).mappings().all()
                    columns = [row['column_name'] for row in cols_res]
                    pcode_col = find_best_match_column(columns, ['code', 'product'],
                                                       priority_exact=['prod_code', 'product_code'])
                    lot_col = find_best_match_column(columns, ['lot'], priority_exact=['lot_number'])
                    qty_col = find_best_match_column(columns, ['qty', 'quantity'])
                    if all([pcode_col, lot_col, qty_col]):
                        query_part = f'SELECT "{pcode_col}"::TEXT AS product_code, "{lot_col}"::TEXT AS lot_number, SUM(CAST("{qty_col}" AS NUMERIC)) AS beginning_qty FROM "{tbl}"'
                        where_clauses = [f'"{pcode_col}" IS NOT NULL', f'"{pcode_col}" != \'\'']
                        if product_filter != "ALL PRODUCTS":
                            param_name = f'pcode_{i}'
                            where_clauses.append(f'"{pcode_col}" = :{param_name}')
                            params[param_name] = product_filter
                        query_part += " WHERE " + " AND ".join(where_clauses)
                        query_part += f' GROUP BY "{pcode_col}", "{lot_col}"'
                        union_queries.append(query_part)
                if not union_queries: return empty_df
                full_query = " UNION ALL ".join(union_queries)
                results = conn.execute(text(full_query), params).mappings().all()
                return pd.DataFrame(results)
        except Exception as e:
            print(f"Error getting beginning inventory: {e}")
            raise e

    def _get_additions(self, start_date, end_date, product_filter):
        empty_df = pd.DataFrame(columns=['product_code', 'lot_number', 'additions_qty'])
        try:
            query_str = """
                SELECT product_code, lot_number, SUM(quantity_kg) as additions_qty FROM (
                    SELECT p.product_code, e.lot_number, e.quantity_kg FROM fg_endorsements_secondary e JOIN fg_endorsements_primary p ON e.system_ref_no = p.system_ref_no WHERE p.is_deleted IS NOT TRUE AND p.date_endorsed BETWEEN :start_date AND :end_date
                    UNION ALL
                    SELECT p.product_code, e.lot_number, e.quantity_kg FROM fg_endorsements_excess e JOIN fg_endorsements_primary p ON e.system_ref_no = p.system_ref_no WHERE p.is_deleted IS NOT TRUE AND p.date_endorsed BETWEEN :start_date AND :end_date
                    UNION ALL
                    SELECT i.product_code, i.lot_number, i.quantity AS quantity_kg FROM rrf_items i JOIN rrf_primary p ON i.rrf_no = p.rrf_no WHERE p.is_deleted IS NOT TRUE AND p.material_type != 'RAW MATERIAL' AND p.rrf_date BETWEEN :start_date AND :end_date
                    UNION ALL
                    SELECT i.material_code AS product_code, i.lot_no AS lot_number, i.quantity_kg FROM receiving_reports_items i JOIN receiving_reports_primary p ON i.rr_no = p.rr_no WHERE p.is_deleted IS NOT TRUE AND p.receive_date BETWEEN :start_date AND :end_date
                ) as all_additions
                {product_clause}
                GROUP BY product_code, lot_number
            """
            params = {'start_date': start_date, 'end_date': end_date}
            product_clause = ""
            if product_filter != "ALL PRODUCTS":
                product_clause = "WHERE all_additions.product_code = :pcode"
                params['pcode'] = product_filter
            full_query = text(query_str.format(product_clause=product_clause))
            with self.engine.connect() as conn:
                results = conn.execute(full_query, params).mappings().all()
            return pd.DataFrame(results) if results else empty_df
        except Exception as e:
            print(f"Error getting additions: {e}")
            raise e

    def _get_removals(self, start_date, end_date, product_filter):
        empty_df = pd.DataFrame(columns=['product_code', 'lot_number', 'removals_qty'])
        try:
            query_str = """
                SELECT product_code, lot_number, SUM(quantity_kg) as removals_qty FROM (
                    SELECT i.product_code, b.lot_number, b.quantity_kg FROM product_delivery_lot_breakdown b JOIN product_delivery_primary p ON b.dr_no = p.dr_no JOIN product_delivery_items i ON b.item_id = i.id WHERE p.is_deleted IS NOT TRUE AND p.delivery_date BETWEEN :start_date AND :end_date
                    UNION ALL
                    SELECT i.product_code, i.lot_used AS lot_number, i.quantity_required_kg AS quantity_kg FROM outgoing_records_items i JOIN outgoing_records_primary p ON i.primary_id = p.id WHERE p.is_deleted IS NOT TRUE AND p.date_out BETWEEN :start_date AND :end_date
                    UNION ALL
                    SELECT i.product_code, i.lot_number, i.quantity AS quantity_kg FROM rrf_items i JOIN rrf_primary p ON i.rrf_no = p.rrf_no WHERE p.is_deleted IS NOT TRUE AND p.material_type = 'RAW MATERIAL' AND p.rrf_date BETWEEN :start_date AND :end_date
                    UNION ALL
                    SELECT p.product_code, p.lot_number, p.quantity_kg FROM qce_endorsements_primary p WHERE p.is_deleted IS NOT TRUE AND p.date_endorsed BETWEEN :start_date AND :end_date
                ) AS all_removals
                {product_clause}
                GROUP BY product_code, lot_number
            """
            params = {'start_date': start_date, 'end_date': end_date}
            product_clause = ""
            if product_filter != "ALL PRODUCTS":
                product_clause = "WHERE all_removals.product_code = :pcode"
                params['pcode'] = product_filter
            full_query = text(query_str.format(product_clause=product_clause))
            with self.engine.connect() as conn:
                results = conn.execute(full_query, params).mappings().all()
            return pd.DataFrame(results) if results else empty_df
        except Exception as e:
            print(f"Error getting removals (deliveries/outgoing/rrf/qce): {e}")
            raise e

    def _display_report(self, df):
        headers = ["Product Code", "Lot Number", "Beginning Qty", "Additions", "Removals", "Ending Qty"]
        df = df.reindex(
            columns=['product_code', 'lot_number', 'beginning_qty', 'additions_qty', 'removals_qty', 'ending_qty'],
            fill_value=0)
        self.report_table.setRowCount(len(df))
        self.report_table.setColumnCount(len(headers))
        self.report_table.setHorizontalHeaderLabels(headers)
        for i, row in df.iterrows():
            for j, col_name in enumerate(df.columns):
                value = row[col_name]
                item_text = f"{Decimal(value):.2f}" if pd.api.types.is_number(value) else str(value)
                item = QTableWidgetItem(item_text)
                if pd.api.types.is_number(value):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.report_table.setItem(i, j, item)
        QMessageBox.information(self, "Report Generated", f"Successfully generated report with {len(df)} records.")