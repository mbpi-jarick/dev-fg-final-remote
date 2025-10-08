import traceback
import pandas as pd
import os
import sys
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict
import qtawesome as qta

# PyQt6 Imports
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QThread, QDate, QSize
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
                             QHeaderView, QMessageBox, QHBoxLayout, QLabel,
                             QPushButton, QLineEdit, QAbstractItemView, QDateEdit,
                             QGroupBox, QFileDialog, QSizePolicy, QTextEdit,
                             QTabWidget, QGridLayout, QProgressBar, QApplication, QMainWindow, QFrame)

# SQLAlchemy Imports
from sqlalchemy import create_engine, text, Engine
from sqlalchemy.engine import URL

# --- UI CONSTANTS (Aligned with AppStyles for visual consistency) ---
PRIMARY_ACCENT_COLOR = "#007bff"
PRIMARY_ACCENT_HOVER = "#e9f0ff"  # Very light blue for hover background
NEUTRAL_COLOR = "#6c757d"
SUCCESS_COLOR = "#28a745"
LIGHT_TEXT_COLOR = "#333333"
BACKGROUND_CONTENT_COLOR = "#f4f7fc"
INPUT_BACKGROUND_COLOR = "#ffffff"
GROUP_BOX_HEADER_COLOR = "#f4f7fc"
TABLE_SELECTION_COLOR = "#3a506b"


# --- Custom UpperCaseLineEdit Widget ---
class UpperCaseLineEdit(QLineEdit):
    """A QLineEdit that automatically converts its text to uppercase."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.textEdited.connect(self._to_upper)

    def _to_upper(self, text: str):
        if text and text != self.text().upper():
            self.blockSignals(True)
            self.setText(text.upper())
            self.blockSignals(False)


# --- WORKER: For Calculating Inventory Summary ---
class InventoryWorker(QObject):
    finished = pyqtSignal(pd.DataFrame)
    error = pyqtSignal(str)

    def __init__(self, engine: Engine, product_filter: str = None, lot_filter: str = None, as_of_date: str = None):
        super().__init__()
        self.engine = engine
        self.product_filter = product_filter
        self.lot_filter = lot_filter
        self.as_of_date = as_of_date

    def run(self):
        try:
            params = {}
            date_filter_clause = ""
            lot_filter_clause = ""
            product_filter_clause = ""

            if self.as_of_date:
                date_filter_clause = "AND transaction_date <= :as_of_date"
                params['as_of_date'] = self.as_of_date
            if self.product_filter and self.product_filter.strip():
                product_filter_clause = "AND product_code = :product"
                params['product'] = self.product_filter.strip().upper()
            if self.lot_filter and self.lot_filter.strip():
                lot_filter_clause = "AND lot_number = :lot"
                params['lot'] = self.lot_filter.strip().upper()

            combined_movements_query = f"""
                (
                    SELECT
                        UPPER(TRIM(product_code)) AS product_code, UPPER(TRIM(lot_number)) AS lot_number,
                        CAST(qty AS NUMERIC) AS quantity_in, 0.0 AS quantity_out 
                    FROM beginv_sheet1
                    WHERE product_code IS NOT NULL AND TRIM(product_code) <> '' 
                      AND lot_number IS NOT NULL AND TRIM(lot_number) <> ''
                    UNION ALL
                    SELECT
                        UPPER(TRIM(product_code)) AS product_code, UPPER(TRIM(lot_number)) AS lot_number,
                        CAST(quantity_in AS NUMERIC), CAST(quantity_out AS NUMERIC)
                    FROM transactions
                    WHERE product_code IS NOT NULL AND TRIM(product_code) <> '' 
                      AND lot_number IS NOT NULL AND TRIM(lot_number) <> '' 
                      {date_filter_clause}
                )
            """

            combined_filters = (
                    (product_filter_clause if product_filter_clause else "") +
                    (lot_filter_clause if lot_filter_clause else "")
            )

            # NOTE: We must cast the results of the subquery to ensure correct filtering.
            query_str = f"""
                WITH combined_movements AS {combined_movements_query}
                SELECT MAX(product_code) AS product_code, lot_number,
                       COALESCE(SUM(quantity_in), 0) - COALESCE(SUM(quantity_out), 0) AS current_balance
                FROM combined_movements
                WHERE 1=1 {combined_filters} 
                GROUP BY lot_number
                HAVING (COALESCE(SUM(quantity_in), 0) - COALESCE(SUM(quantity_out), 0)) > 0.001
                ORDER BY product_code, lot_number;
            """

            with self.engine.connect() as conn:
                results = conn.execute(text(query_str), params).mappings().all()

            df = pd.DataFrame(results) if results else pd.DataFrame(
                columns=['product_code', 'lot_number', 'current_balance'])

            if not df.empty:
                df['current_balance'] = pd.to_numeric(df['current_balance'])

            self.finished.emit(df)

        except Exception as e:
            error_msg = f"Database query failed: {type(e).__name__}: {e}"
            self.error.emit(error_msg)
            traceback.print_exc()


# --- ADVANCED DASHBOARD WIDGET ---
class DashboardWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.data_df = pd.DataFrame()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(15)

        grid_layout = QGridLayout()

        # 1. Overall Summary
        summary_group = QGroupBox("Overall Summary Metrics")
        summary_group.setObjectName("SummaryGroup")
        summary_layout = QHBoxLayout(summary_group)

        self.total_lots_label = self._create_summary_label("Total Lots:", "0")
        self.total_products_label = self._create_summary_label("Unique Products:", "0")
        self.overall_balance_label = self._create_summary_label("Overall Balance (kg):", "0.00")

        summary_layout.addWidget(self.total_lots_label)
        summary_layout.addWidget(self.total_products_label)
        summary_layout.addWidget(self.overall_balance_label)

        grid_layout.addWidget(summary_group, 0, 0, 1, 2)

        # 2. Product Contribution
        self.contribution_table = self._create_contribution_table()
        contribution_group = QGroupBox("Top 10 Product Contribution (by Mass)")
        contribution_group.setObjectName("ContributionGroup")
        vbox_contribution = QVBoxLayout(contribution_group)
        vbox_contribution.addWidget(self.contribution_table)
        grid_layout.addWidget(contribution_group, 1, 0)

        # 3. Lot Size Distribution
        self.lot_stats_group = self._create_lot_statistics_group()
        grid_layout.addWidget(self.lot_stats_group, 1, 1)

        self.layout.addLayout(grid_layout)
        self.layout.addStretch(1)
        self.setStyleSheet(self._get_dashboard_styles())

    def _get_dashboard_styles(self) -> str:
        return f"""
            QGroupBox#SummaryGroup, QGroupBox#ContributionGroup {{
                border: 1px solid #e0e5eb; border-radius: 8px;
                margin-top: 12px; background-color: {INPUT_BACKGROUND_COLOR};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; subcontrol-position: top left;
                padding: 2px 10px; background-color: {GROUP_BOX_HEADER_COLOR};
                border: 1px solid #e0e5eb; border-bottom: 1px solid {INPUT_BACKGROUND_COLOR};
                border-top-left-radius: 8px; border-top-right-radius: 8px;
                font-weight: bold; color: #4f4f4f;
            }}

            /* Summary Boxes */
            QWidget[styleSheet*="border: 1px solid #d1d9e6;"] {{ /* Target internal summary widgets */
                border: 1px solid #d1d9e6; 
                border-radius: 8px; 
                background-color: {INPUT_BACKGROUND_COLOR};
            }}

            /* Ensure all Labels in the dashboard are white backgrounded */
            QLabel {{ background-color: {INPUT_BACKGROUND_COLOR}; }}

            QLabel#TitleLabel {{ font-size: 10pt; color: {NEUTRAL_COLOR}; }}
            QLabel#ValueLabel {{ font-size: 16pt; font-weight: bold; color: {PRIMARY_ACCENT_COLOR}; }}

            /* Tables in Dashboard */
            QTableWidget {{ border: none; background-color: {INPUT_BACKGROUND_COLOR}; }}
            QTableWidget::item {{ border-bottom: 1px solid #f4f7fc; }}
            QHeaderView::section {{ background-color: {INPUT_BACKGROUND_COLOR}; color: {NEUTRAL_COLOR}; }}

            /* Progress Bar Styling */
            QProgressBar {{ border: 1px solid #d1d9e6; border-radius: 4px; background-color: #eff2f7; }}
            QProgressBar::chunk {{ background-color: {PRIMARY_ACCENT_COLOR}; border-radius: 4px; }}
        """

    def _create_summary_label(self, title: str, initial_value: str) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 10, 15, 10)

        title_label = QLabel(title)
        title_label.setObjectName("TitleLabel")

        value_label = QLabel(initial_value)
        value_label.setObjectName("ValueLabel")
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(title_label, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(value_label, alignment=Qt.AlignmentFlag.AlignCenter)
        # Apply base style for internal summary widgets that the CSS selector targets
        widget.setStyleSheet(
            f"border: 1px solid #d1d9e6; border-radius: 8px; background-color: {INPUT_BACKGROUND_COLOR};")
        return widget

    def _create_contribution_table(self) -> QTableWidget:
        table = QTableWidget(columnCount=4)
        table.setHorizontalHeaderLabels(["Product Code", "Balance (kg)", "Share (%)", "Visual Share"])
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.verticalHeader().setVisible(False)
        table.setFrameShape(QTableWidget.Shape.NoFrame)
        table.setShowGrid(False)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        table.setMaximumHeight(350)
        return table

    def _create_lot_statistics_group(self) -> QGroupBox:
        group = QGroupBox("Lot Size Statistics")
        group.setObjectName("LotStatsGroup")
        layout = QGridLayout(group)
        layout.setContentsMargins(15, 20, 15, 15)

        self.lot_stats = {
            'max_lot': QLabel("N/A"),
            'min_lot': QLabel("N/A"),
            'avg_lot': QLabel("N/A"),
            'median_lot': QLabel("N/A"),
        }

        # Apply internal style consistent with the theme
        label_style = f"font-size: 10pt; color: {NEUTRAL_COLOR};"
        value_style = f"font-weight: bold; color: {PRIMARY_ACCENT_COLOR};"

        layout.addWidget(QLabel("Largest Lot Size (kg):", styleSheet=label_style), 0, 0)
        self.lot_stats['max_lot'].setStyleSheet(value_style)
        layout.addWidget(self.lot_stats['max_lot'], 0, 1, alignment=Qt.AlignmentFlag.AlignRight)

        layout.addWidget(QLabel("Smallest Lot Size (kg):", styleSheet=label_style), 1, 0)
        self.lot_stats['min_lot'].setStyleSheet(value_style)
        layout.addWidget(self.lot_stats['min_lot'], 1, 1, alignment=Qt.AlignmentFlag.AlignRight)

        layout.addWidget(QLabel("Average Lot Size (kg):", styleSheet=label_style), 2, 0)
        self.lot_stats['avg_lot'].setStyleSheet(value_style)
        layout.addWidget(self.lot_stats['avg_lot'], 2, 1, alignment=Qt.AlignmentFlag.AlignRight)

        layout.addWidget(QLabel("Median Lot Size (kg):", styleSheet=label_style), 3, 0)
        self.lot_stats['median_lot'].setStyleSheet(value_style)
        layout.addWidget(self.lot_stats['median_lot'], 3, 1, alignment=Qt.AlignmentFlag.AlignRight)

        layout.setColumnStretch(1, 1)
        layout.setRowStretch(4, 1)
        return group

    def update_dashboard(self, df: pd.DataFrame):
        self.data_df = df

        if df.empty:
            for container_widget in [self.total_lots_label, self.total_products_label, self.overall_balance_label]:
                value_label = container_widget.findChild(QLabel, "ValueLabel")
                if value_label:
                    title_label = container_widget.findChild(QLabel, "TitleLabel")
                    is_lot_count = 'Lots' in title_label.text()
                    value_label.setText("0" if is_lot_count else "0.00")

            for label in self.lot_stats.values():
                label.setText("N/A")
            self.contribution_table.setRowCount(0)
            return

        total_lots = len(df)
        total_products = df['product_code'].nunique()
        overall_balance = df['current_balance'].sum()

        self.total_lots_label.findChild(QLabel, "ValueLabel").setText(f"{total_lots}")
        self.total_products_label.findChild(QLabel, "ValueLabel").setText(f"{total_products}")
        self.overall_balance_label.findChild(QLabel, "ValueLabel").setText(f"{overall_balance:.2f}")

        # Update lot stats values
        self.lot_stats['max_lot'].setText(f"{df['current_balance'].max():.2f}")
        self.lot_stats['min_lot'].setText(f"{df['current_balance'].min():.2f}")
        self.lot_stats['avg_lot'].setText(f"{df['current_balance'].mean():.2f}")
        self.lot_stats['median_lot'].setText(f"{df['current_balance'].median():.2f}")

        product_summary = df.groupby('product_code')['current_balance'].sum().reset_index()
        product_summary['percentage'] = (product_summary['current_balance'] / overall_balance) * 100

        product_summary = product_summary.nlargest(10, 'current_balance').reset_index(drop=True)
        self.contribution_table.setRowCount(len(product_summary))

        for i, row in product_summary.iterrows():
            product_code = str(row['product_code'])
            balance_val = row['current_balance']
            percentage = row['percentage']

            self.contribution_table.setItem(i, 0, QTableWidgetItem(product_code))

            balance_item = QTableWidgetItem(f"{balance_val:.2f}")
            balance_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.contribution_table.setItem(i, 1, balance_item)

            percent_item = QTableWidgetItem(f"{percentage:.1f}%")
            percent_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.contribution_table.setItem(i, 2, percent_item)

            progress_bar = QProgressBar()
            progress_bar.setMaximum(100)
            progress_bar.setValue(int(percentage))
            progress_bar.setTextVisible(False)
            progress_bar.setStyleSheet(f"""
                QProgressBar {{ border: 1px solid #d1d9e6; border-radius: 4px; background-color: #eff2f7; }}
                QProgressBar::chunk {{ background-color: {PRIMARY_ACCENT_COLOR}; border-radius: 4px; }} 
            """)
            self.contribution_table.setCellWidget(i, 3, progress_bar)


# --- MAIN TAB MANAGER CLASS ---
class GoodInventoryPage(QWidget):
    def __init__(self, engine: Engine, username=None, log_audit_trail_func=None):
        super().__init__()
        self.engine = engine
        self.inventory_thread: QThread | None = None
        self.inventory_worker: InventoryWorker | None = None
        self.current_inventory_df = pd.DataFrame(columns=['product_code', 'lot_number', 'current_balance'])

        self.dashboard_widget = DashboardWidget()

        self.init_ui()
        self.setStyleSheet(self._get_styles())
        self._start_inventory_calculation()

    def _get_styles(self) -> str:
        # Combined styles for the main page elements
        return f"""
            /* Base Widget Styles */
            QWidget {{ 
                background-color: {BACKGROUND_CONTENT_COLOR};
                color: {LIGHT_TEXT_COLOR};
                font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
            }}

            /* Explicitly set all QLabels to have a white background */
            QLabel {{
                background-color: {INPUT_BACKGROUND_COLOR};
                color: {LIGHT_TEXT_COLOR}; /* Inherit dark text color */
                padding: 0 4px; /* Slight padding to avoid cutting text */
            }}

            /* Header Title */
            QLabel#PageHeader {{ 
                font-size: 16pt; 
                font-weight: bold; 
                color: {PRIMARY_ACCENT_COLOR}; 
                background-color: transparent; /* Title transparency override */
            }}

            /* Header Widget Container Transparency */
            #HeaderWidget {{
                background-color: transparent;
            }}

            /* Input Fields (QDateEdit and QLineEdit) */
            QLineEdit, QDateEdit {{
                border: 1px solid #d1d9e6; 
                padding: 8px; 
                border-radius: 5px;
                background-color: {INPUT_BACKGROUND_COLOR};
                color: {LIGHT_TEXT_COLOR};
            }}
            QLineEdit:focus, QDateEdit:focus {{
                border: 1px solid {PRIMARY_ACCENT_COLOR};
            }}

            /* Group Box Styling */
            QGroupBox {{
                border: 1px solid #e0e5eb; border-radius: 8px;
                margin-top: 12px; background-color: {INPUT_BACKGROUND_COLOR};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; subcontrol-position: top left;
                padding: 2px 10px; background-color: {GROUP_BOX_HEADER_COLOR};
                border: 1px solid #e0e5eb; border-bottom: 1px solid {INPUT_BACKGROUND_COLOR};
                border-top-left-radius: 8px; border-top-right-radius: 8px;
                font-weight: bold; color: #4f4f4f;
            }}

            /* Instruction Box */
            QGroupBox#InstructionsBox {{
                background-color: #e9f0ff; /* Very Light Blue background */
                border: 1px solid {PRIMARY_ACCENT_COLOR};
                color: {LIGHT_TEXT_COLOR};
            }}
            QTextEdit#InstructionsBox {{
                background-color: transparent; 
                border: none;
            }}

            /* --- BUTTON STYLES (Light Color Scheme) --- */
            QPushButton {{
                border: 1px solid #d1d9e6; 
                padding: 8px 15px;
                border-radius: 6px;
                font-weight: bold;
                color: {LIGHT_TEXT_COLOR}; 
                background-color: {INPUT_BACKGROUND_COLOR}; 
                qproperty-iconSize: 16px;
            }}
            QPushButton:hover {{
                background-color: #f0f3f8; /* Standard Light Gray Hover */
                border: 1px solid #c0c0c0;
            }}

            /* Primary Action Button (Refresh/Export - using Primary Accent Color for border/text/icon) */
            QPushButton[objectName="PrimaryButton"] {{
                color: {PRIMARY_ACCENT_COLOR}; 
                border: 1px solid {PRIMARY_ACCENT_COLOR};
            }}
            QPushButton[objectName="PrimaryButton"]:hover {{
                background-color: {PRIMARY_ACCENT_HOVER}; 
                border: 1px solid {PRIMARY_ACCENT_COLOR};
            }}

            /* Tab Bar Styling */
            QTabWidget::pane {{ border: 1px solid #e0e5eb; border-radius: 8px; background-color: {INPUT_BACKGROUND_COLOR}; padding: 10px; margin-top: -1px; }}
            QTabBar::tab {{ background-color: #e9eff7; color: {NEUTRAL_COLOR}; padding: 8px 15px; border-top-left-radius: 6px; border-top-right-radius: 6px; border: 1px solid #e0e5eb; border-bottom: none; margin-right: 4px; font-weight: normal; }}
            QTabBar::tab:selected {{ color: {PRIMARY_ACCENT_COLOR}; background-color: {INPUT_BACKGROUND_COLOR}; border-bottom-color: {INPUT_BACKGROUND_COLOR}; margin-bottom: -1px; font-weight: bold;}}
            QTabBar::tab:hover {{ background-color: #f0f3f8; }}

            /* Inventory Table Styling */
            QTableWidget {{
                border: 1px solid #e0e5eb;
                background-color: {INPUT_BACKGROUND_COLOR};
                selection-behavior: SelectRows;
                color: {LIGHT_TEXT_COLOR};
                border-radius: 8px;
            }}
            QTableWidget::item {{
                border-bottom: 1px solid #f4f7fc;
                padding: 5px;
            }}
            QTableWidget::item:selected {{
                background-color: {TABLE_SELECTION_COLOR}; /* Side menu selection color */
                color: white;
                border: 0px; 
            }}

            /* Total Balance Label */
            QLabel#TotalBalanceLabel {{
                background-color: {INPUT_BACKGROUND_COLOR};
                color: {PRIMARY_ACCENT_COLOR};
                padding: 10px;
                border-radius: 6px;
                border: 1px solid #e0e5eb;
                margin-top: 5px;
            }}
        """

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # --- Header (Icon, Title) ---
        header_widget = QWidget()
        header_widget.setObjectName("HeaderWidget")  # Used for transparency styling
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)

        # Icon (Dark color on light background)
        icon_pixmap = qta.icon('fa5s.calculator', color=PRIMARY_ACCENT_COLOR).pixmap(QSize(28, 28))
        icon_label = QLabel()
        icon_label.setPixmap(icon_pixmap)
        header_layout.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignLeft)

        # Header Title
        title_label = QLabel("FG Inventory Passed Computation and Export", objectName="PageHeader")
        title_label.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        main_layout.addWidget(header_widget)
        # ----------------------------------

        self.controls_widget = QWidget()
        controls_layout = QVBoxLayout(self.controls_widget)
        controls_layout.addWidget(self._create_instructions_box())
        controls_layout.addWidget(self._create_filter_controls())
        controls_layout.setContentsMargins(0, 0, 0, 0)

        main_layout.addWidget(self.controls_widget)

        self.tab_widget = QTabWidget()
        self.tab_widget.setIconSize(QSize(16, 16))

        self.inventory_tab = QWidget()
        self.inventory_layout = QVBoxLayout(self.inventory_tab)
        self.inventory_table = self._create_inventory_table()

        self.total_balance_label = QLabel("Total Balance: 0.00 kg", objectName="TotalBalanceLabel")
        self.total_balance_label.setAlignment(Qt.AlignmentFlag.AlignRight)

        self.inventory_layout.addWidget(self.inventory_table, 1)
        self.inventory_layout.addWidget(self.total_balance_label)

        # Updated Tab Icons (using accent colors)
        self.tab_widget.addTab(self.inventory_tab, qta.icon('fa5.list-alt', color=PRIMARY_ACCENT_COLOR),
                               "Inventory Details")
        self.tab_widget.addTab(self.dashboard_widget, qta.icon('fa5s.chart-area', color=PRIMARY_ACCENT_COLOR),
                               "Dashboard")  # Using PRIMARY_ACCENT for chart icon
        main_layout.addWidget(self.tab_widget)

        # --- Connections ---
        self.refresh_button.clicked.connect(self._start_inventory_calculation)
        self.lot_number_input.editingFinished.connect(self._start_inventory_calculation)
        self.product_code_input.editingFinished.connect(self._start_inventory_calculation)
        self.date_picker.dateChanged.connect(self._start_inventory_calculation)
        self.export_button.clicked.connect(self._export_to_excel)

    def _create_instructions_box(self) -> QGroupBox:
        group = QGroupBox("Computation Instructions")
        group.setObjectName("InstructionsBox")
        layout = QVBoxLayout(group)

        instructions = """
        This report calculates the Current Inventory Balance per Lot based on movements up to the 'As Of Date'.

        **Calculation Logic:** Balance = (Beginning Inventory) + (Transactions In) - (Transactions Out) [up to As Of Date]

        **Display:** Only lots with a positive current balance (> 0.001 kg) are shown.
        """
        text_edit = QTextEdit(instructions, objectName="InstructionsBox")
        text_edit.setReadOnly(True)
        text_edit.setMaximumHeight(100)
        text_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(text_edit)
        return group

    def _create_filter_controls(self) -> QGroupBox:
        controls_group = QGroupBox("Filters & Actions")
        filter_layout = QHBoxLayout(controls_group)
        filter_layout.setContentsMargins(10, 15, 10, 10)

        filter_layout.addWidget(QLabel("As Of Date:"))
        self.date_picker = QDateEdit(calendarPopup=True, date=QDate.currentDate(), displayFormat="yyyy-MM-dd")
        self.date_picker.setMinimumWidth(100)
        filter_layout.addWidget(self.date_picker)

        filter_layout.addSpacing(10)
        filter_layout.addWidget(QLabel("Product:"))
        self.product_code_input = UpperCaseLineEdit(placeholderText="Product Code")
        filter_layout.addWidget(self.product_code_input, 1)

        filter_layout.addSpacing(10)
        filter_layout.addWidget(QLabel("Lot:"))
        self.lot_number_input = UpperCaseLineEdit(placeholderText="Lot Number")
        filter_layout.addWidget(self.lot_number_input, 1)

        filter_layout.addSpacing(20)

        # BUTTONS - Standard Light Style (Blue accent)

        self.refresh_button = QPushButton("Refresh", objectName="PrimaryButton")
        # Icon color must be PRIMARY_ACCENT_COLOR for light button style
        self.refresh_button.setIcon(qta.icon('fa5s.sync-alt', color=PRIMARY_ACCENT_COLOR))
        filter_layout.addWidget(self.refresh_button)

        self.export_button = QPushButton("Export", objectName="PrimaryButton")
        # Icon color must be PRIMARY_ACCENT_COLOR for light button style
        self.export_button.setIcon(qta.icon('fa5s.file-excel', color=PRIMARY_ACCENT_COLOR))
        filter_layout.addWidget(self.export_button)

        return controls_group

    def _create_inventory_table(self) -> QTableWidget:
        table = QTableWidget(columnCount=3)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.verticalHeader().setVisible(False)

        table.setShowGrid(False)
        table.setFrameShape(QTableWidget.Shape.NoFrame)

        table.setAlternatingRowColors(True)
        table.horizontalHeader().setHighlightSections(False)
        table.setHorizontalHeaderLabels(["Associated Product", "Lot Number", "Current Balance (kg)"])
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        return table

    def _start_inventory_calculation(self):
        if self.inventory_thread and self.inventory_thread.isRunning():
            return

        product_filter = self.product_code_input.text().strip()
        lot_filter = self.lot_number_input.text().strip()
        as_of_date = self.date_picker.date().toString(Qt.DateFormat.ISODate)

        self.set_controls_enabled(False)
        self._show_loading_state(self.inventory_table, "Calculating inventory balance...")
        self.dashboard_widget.update_dashboard(pd.DataFrame())

        self.inventory_thread = QThread()
        self.inventory_worker = InventoryWorker(self.engine, product_filter, lot_filter, as_of_date)
        self.inventory_worker.moveToThread(self.inventory_thread)

        self.inventory_thread.started.connect(self.inventory_worker.run)

        self.inventory_worker.finished.connect(self._on_inventory_finished)
        self.inventory_worker.error.connect(self._on_calculation_error)

        # 1. Trigger thread termination immediately after worker completes (Success or Error)
        self.inventory_worker.finished.connect(self.inventory_thread.quit)
        self.inventory_worker.error.connect(self.inventory_thread.quit)

        # 2. FIX: Centralize cleanup to a single slot connected to thread.finished
        self.inventory_thread.finished.connect(self._cleanup_thread_and_worker)

        self.inventory_thread.start()

    def _cleanup_thread_and_worker(self):
        """Safely delete the thread and worker objects after the thread has quit."""
        if self.inventory_worker:
            self.inventory_worker.deleteLater()
            self.inventory_worker = None

        if self.inventory_thread:
            self.inventory_thread.deleteLater()
            self.inventory_thread = None

    def set_controls_enabled(self, enabled: bool):
        self.lot_number_input.setEnabled(enabled)
        self.product_code_input.setEnabled(enabled)
        self.refresh_button.setEnabled(enabled)
        self.date_picker.setEnabled(enabled)
        self.export_button.setEnabled(enabled and not self.current_inventory_df.empty)

    def _on_inventory_finished(self, df: pd.DataFrame):
        self.current_inventory_df = df.copy()
        self._display_inventory(df)
        self.dashboard_widget.update_dashboard(df)
        self.set_controls_enabled(True)

    def _on_calculation_error(self, error_message: str):
        QMessageBox.critical(self, "Calculation Error", error_message)
        self.inventory_table.setRowCount(0)
        self.current_inventory_df = pd.DataFrame()
        self.total_balance_label.setText("Total Balance: Error")
        self.dashboard_widget.update_dashboard(pd.DataFrame())
        self.set_controls_enabled(True)

    def _show_loading_state(self, table: QTableWidget, message: str):
        table.setRowCount(1)
        table.setSpan(0, 0, 1, table.columnCount())
        loading_item = QTableWidgetItem(message)
        loading_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        table.setItem(0, 0, loading_item)

    def _display_inventory(self, df: pd.DataFrame):
        self.inventory_table.setRowCount(0)

        total_balance = df['current_balance'].sum() if not df.empty else 0.0
        self.inventory_table.setRowCount(len(df))

        for i, row in df.iterrows():
            product_code = str(row.get('product_code', ''))
            lot_number = str(row.get('lot_number', ''))
            balance_val = row.get('current_balance', 0.0)

            qty_item = QTableWidgetItem(f"{balance_val:.2f}")
            qty_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            self.inventory_table.setItem(i, 0, QTableWidgetItem(product_code))
            self.inventory_table.setItem(i, 1, QTableWidgetItem(lot_number))
            self.inventory_table.setItem(i, 2, qty_item)

        is_filtered = bool(self.lot_number_input.text().strip() or self.product_code_input.text().strip())

        prefix = "Total Balance"
        if is_filtered and len(df) > 0:
            prefix = f"Filtered Total Balance ({len(df)} lots)"
        elif not is_filtered:
            prefix = f"Overall Total Balance ({len(df)} lots)"

        self.total_balance_label.setText(f"{prefix}: {total_balance:.2f} kg")

    def _export_to_excel(self):
        if self.current_inventory_df.empty:
            QMessageBox.information(self, "Export Failed", "No data available to export.")
            return

        # 1. Generate Filename based on the current date (date of generation)
        date_of_generate_str = QDate.currentDate().toString("yyyyMMdd")
        default_filename = f"FG-Inventory-Report-Passed as of {date_of_generate_str}.xlsx"

        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Save Inventory Report",
            default_filename,
            "Excel Files (*.xlsx)"
        )

        if filepath:
            try:
                # 2. Rename and Reorder Columns
                export_df = self.current_inventory_df.rename(columns={
                    'lot_number': 'Lot number',
                    'product_code': 'Product code',
                    'current_balance': 'Current balance (kg)'
                })

                # Reorder the columns explicitly: Lot number, Product code, Current balance (kg)
                export_df = export_df[['Lot number', 'Product code', 'Current balance (kg)']]

                export_df.to_excel(filepath, index=False, engine='openpyxl')

                QMessageBox.information(
                    self,
                    "Export Successful",
                    f"Inventory data exported successfully to:\n{os.path.basename(filepath)}"
                )

            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Export Error",
                    f"Failed to save file. Ensure the file is not currently open.\nError: {e}"
                )
                traceback.print_exc()


# --- MAIN APPLICATION EXECUTION (Kept for standalone testing capability) ---

class InventoryApp(QMainWindow):
    def __init__(self, engine: Engine):
        super().__init__()
        self.setWindowTitle("FG Inventory Computation and Export")
        self.setGeometry(100, 100, 1200, 800)
        self.setStyleSheet(f"QMainWindow {{ background-color: {BACKGROUND_CONTENT_COLOR}; }}")

        inventory_page = GoodInventoryPage(engine)
        self.setCentralWidget(inventory_page)


def setup_postgres_engine() -> Engine:
    """Creates and returns the PostgreSQL engine using provided credentials."""
    # NOTE: These credentials must be valid for the application to run.
    DB_CONFIG = {
        "host": "192.168.1.13",
        "port": 5432,
        "database": "dbfg",
        "username": "postgres",
        "password": "mbpi"
    }

    db_url = URL.create(
        "postgresql+psycopg2",
        host=DB_CONFIG["host"],
        port=DB_CONFIG["port"],
        database=DB_CONFIG["database"],
        username=DB_CONFIG["username"],
        password=DB_CONFIG["password"],
    )

    try:
        # Use pool_recycle to prevent connection timeout issues in a long-running app
        engine = create_engine(db_url, pool_recycle=3600)
        with engine.connect():
            # In a mock environment, this will pass if the DB is reachable.
            pass
        return engine
    except Exception as e:
        print(f"Error connecting to PostgreSQL: {e}")
        app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None, "Database Connection Error",
                             f"Failed to connect to PostgreSQL at {DB_CONFIG['host']}:{DB_CONFIG['port']}.\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # To run this standalone, you must have a PostgreSQL instance running
    # with the credentials defined in setup_postgres_engine().
    app = QApplication(sys.argv)

    db_engine = setup_postgres_engine()

    main_window = InventoryApp(db_engine)
    main_window.show()
    sys.exit(app.exec())