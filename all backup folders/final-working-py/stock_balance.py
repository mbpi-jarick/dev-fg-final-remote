# stock_balance.py
# FINAL FIX - Helper function included directly to resolve ModuleNotFoundError.

import sys
from decimal import Decimal
import traceback
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
                             QHeaderView, QMessageBox, QHBoxLayout, QLabel,
                             QPushButton, QComboBox, QAbstractItemView)
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


class StockBalancePage(QWidget):
    def __init__(self, db_engine):
        super().__init__()
        self.engine = db_engine
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        filter_group_box = QWidget()
        filter_layout = QHBoxLayout(filter_group_box)
        filter_layout.setContentsMargins(0, 0, 0, 10)
        self.product_code_combo = QComboBox(editable=True)
        self.product_code_combo.setPlaceholderText("Select or Type a Product Code...")
        self.product_code_combo.setMinimumWidth(300)
        self.check_specific_btn = QPushButton("Check Specific Product")
        self.check_all_btn = QPushButton("Show All Balances")
        self.check_all_btn.setObjectName("PrimaryButton")
        filter_layout.addWidget(QLabel("<b>Product Code:</b>"))
        filter_layout.addWidget(self.product_code_combo, 1)
        filter_layout.addWidget(self.check_specific_btn)
        filter_layout.addWidget(self.check_all_btn)
        filter_layout.addStretch()
        layout.addWidget(filter_group_box)
        self.balance_table = QTableWidget()
        self.balance_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.balance_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.balance_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.balance_table.verticalHeader().setVisible(False)
        self.balance_table.setColumnCount(3)
        self.balance_table.setHorizontalHeaderLabels(["Product Code", "Lot Number", "Current Balance (kg)"])
        self.balance_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.balance_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.balance_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.balance_table, 1)
        self.total_balance_label = QLabel("Total Balance for Product: 0.00 kg")
        self.total_balance_label.setStyleSheet("font-size: 14pt; font-weight: bold; padding: 10px;")
        self.total_balance_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.total_balance_label)
        self.check_specific_btn.clicked.connect(self._check_specific_balance)
        self.check_all_btn.clicked.connect(self._check_all_balances)
        self._load_product_codes()

    def _load_product_codes(self):
        try:
            with self.engine.connect() as conn:
                query = text("""
                    SELECT DISTINCT product_code FROM (
                        (SELECT DISTINCT product_code FROM fg_endorsements_primary WHERE product_code IS NOT NULL AND product_code != '')
                        UNION
                        (SELECT DISTINCT prod_code AS product_code FROM legacy_production WHERE prod_code IS NOT NULL AND prod_code != '')
                    ) as codes
                    ORDER BY product_code;
                """)
                result = conn.execute(query).scalars().all()
            self.product_code_combo.clear()
            self.product_code_combo.addItem("")
            self.product_code_combo.addItems(result)
        except Exception as e:
            QMessageBox.warning(self, "Load Error", f"Could not load product codes: {e}")

    def _check_specific_balance(self):
        product_filter = self.product_code_combo.currentText().strip()
        if not product_filter:
            QMessageBox.warning(self, "Input Required", "Please select or enter a Product Code to check.")
            return
        self._calculate_and_display_balance(product_filter=product_filter)

    def _check_all_balances(self):
        self._calculate_and_display_balance(product_filter=None)

    def _calculate_and_display_balance(self, product_filter=None):
        try:
            self.check_specific_btn.setEnabled(False)
            self.check_all_btn.setEnabled(False)
            QApplication.processEvents()
            begin_inv_df = self._get_beginning_inventory(product_filter)
            additions_df = self._get_additions(product_filter)
            removals_df = self._get_removals(product_filter)
            all_dfs = [begin_inv_df, additions_df, removals_df]
            master_df = pd.concat(
                [df[['product_code', 'lot_number']] for df in all_dfs if not df.empty]).drop_duplicates().reset_index(
                drop=True)
            if master_df.empty:
                self._display_balance(pd.DataFrame(), is_specific_product=(product_filter is not None))
                return
            if not begin_inv_df.empty:
                master_df = pd.merge(master_df, begin_inv_df, on=['product_code', 'lot_number'], how='left')
            if not additions_df.empty:
                master_df = pd.merge(master_df, additions_df, on=['product_code', 'lot_number'], how='left')
            if not removals_df.empty:
                master_df = pd.merge(master_df, removals_df, on=['product_code', 'lot_number'], how='left')
            balance_df = master_df.fillna(0)
            for col in ['product_code', 'lot_number']:
                if col in balance_df.columns:
                    balance_df[col] = balance_df[col].astype(str).str.strip()
            balance_df = balance_df[balance_df['product_code'].str.lower() != 'nan']
            balance_df = balance_df[balance_df['product_code'] != '']
            balance_df['ending_qty'] = balance_df['beginning_qty'] + balance_df['additions_qty'] - balance_df[
                'removals_qty']
            if product_filter:
                balance_df = balance_df[balance_df['ending_qty'] > 0.001]
            balance_df = balance_df.sort_values(by=['product_code', 'lot_number'])
            self._display_balance(balance_df, is_specific_product=(product_filter is not None))
        except Exception as e:
            QMessageBox.critical(self, "Calculation Error", f"An error occurred: {e}")
            print(f"Balance Check Error: {traceback.format_exc()}")
        finally:
            self.check_specific_btn.setEnabled(True)
            self.check_all_btn.setEnabled(True)

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
                        if product_filter:
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
            print(f"Error getting beginning inventory for balance check: {e}")
            raise e

    def _get_additions(self, product_filter):
        empty_df = pd.DataFrame(columns=['product_code', 'lot_number', 'additions_qty'])
        try:
            query_str = """
                SELECT product_code, lot_number, SUM(quantity_kg) as additions_qty FROM (
                    SELECT p.product_code, e.lot_number, e.quantity_kg FROM fg_endorsements_secondary e JOIN fg_endorsements_primary p ON e.system_ref_no = p.system_ref_no WHERE p.is_deleted IS NOT TRUE
                    UNION ALL
                    SELECT p.product_code, e.lot_number, e.quantity_kg FROM fg_endorsements_excess e JOIN fg_endorsements_primary p ON e.system_ref_no = p.system_ref_no WHERE p.is_deleted IS NOT TRUE
                    UNION ALL
                    SELECT i.product_code, i.lot_number, i.quantity AS quantity_kg FROM rrf_items i JOIN rrf_primary p ON i.rrf_no = p.rrf_no WHERE p.is_deleted IS NOT TRUE AND p.material_type != 'RAW MATERIAL'
                    UNION ALL
                    SELECT i.material_code AS product_code, i.lot_no AS lot_number, i.quantity_kg FROM receiving_reports_items i JOIN receiving_reports_primary p ON i.rr_no = p.rr_no WHERE p.is_deleted IS NOT TRUE
                ) as all_additions
                {where_clause}
                GROUP BY product_code, lot_number
            """
            params = {}
            where_clause = ""
            if product_filter:
                where_clause = "WHERE product_code = :pcode"
                params['pcode'] = product_filter
            final_query = text(query_str.format(where_clause=where_clause))
            with self.engine.connect() as conn:
                results = conn.execute(final_query, params).mappings().all()
            return pd.DataFrame(results) if results else empty_df
        except Exception as e:
            print(f"Error getting additions for balance check: {e}")
            raise e

    def _get_removals(self, product_filter):
        empty_df = pd.DataFrame(columns=['product_code', 'lot_number', 'removals_qty'])
        try:
            query_str = """
                SELECT product_code, lot_number, SUM(quantity_kg) as removals_qty FROM (
                    SELECT i.product_code, b.lot_number, b.quantity_kg FROM product_delivery_lot_breakdown b JOIN product_delivery_primary p ON b.dr_no = p.dr_no JOIN product_delivery_items i ON b.item_id = i.id WHERE p.is_deleted IS NOT TRUE
                    UNION ALL
                    SELECT i.product_code, i.lot_used AS lot_number, i.quantity_required_kg AS quantity_kg FROM outgoing_records_items i JOIN outgoing_records_primary p ON i.primary_id = p.id WHERE p.is_deleted IS NOT TRUE
                    UNION ALL
                    SELECT i.product_code, i.lot_number, i.quantity AS quantity_kg FROM rrf_items i JOIN rrf_primary p ON i.rrf_no = p.rrf_no WHERE p.is_deleted IS NOT TRUE AND p.material_type = 'RAW MATERIAL'
                    UNION ALL
                    SELECT p.product_code, p.lot_number, p.quantity_kg FROM qce_endorsements_primary p WHERE p.is_deleted IS NOT TRUE
                ) AS all_removals
                {where_clause}
                GROUP BY product_code, lot_number
            """
            params = {}
            where_clause = ""
            if product_filter:
                where_clause = "WHERE product_code = :pcode"
                params['pcode'] = product_filter
            final_query = text(query_str.format(where_clause=where_clause))
            with self.engine.connect() as conn:
                results = conn.execute(final_query, params).mappings().all()
            return pd.DataFrame(results) if results else empty_df
        except Exception as e:
            print(f"Error getting removals for balance check: {e}")
            raise e

    def _display_balance(self, df, is_specific_product):
        self.balance_table.setRowCount(0)
        total_balance = Decimal(df['ending_qty'].sum())
        if df.empty:
            if is_specific_product:
                self.total_balance_label.setText(f"Total Balance for Product: 0.00 kg")
                QMessageBox.information(self, "No Stock", "No current balance found for the selected product code.")
            else:
                self.total_balance_label.setText(f"Overall Total Balance: 0.00 kg")
                QMessageBox.information(self, "No Stock", "No products with a positive balance were found.")
            return
        self.balance_table.setRowCount(len(df))
        for i, row in df.iterrows():
            prod_code = str(row.get('product_code', ''))
            lot_number = str(row.get('lot_number', ''))
            ending_qty = Decimal(row.get('ending_qty', 0))
            self.balance_table.setItem(i, 0, QTableWidgetItem(prod_code))
            self.balance_table.setItem(i, 1, QTableWidgetItem(lot_number))
            qty_item = QTableWidgetItem(f"{ending_qty:.2f}")
            qty_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.balance_table.setItem(i, 2, qty_item)
        if is_specific_product:
            self.total_balance_label.setText(f"Total Balance for Product: {total_balance:.2f} kg")
        else:
            self.total_balance_label.setText(f"Overall Total Balance (All Products): {total_balance:.2f} kg")