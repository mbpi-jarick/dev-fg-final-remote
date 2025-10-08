import os
import traceback # Explicitly importing traceback as it is used in exception handlers
import pandas as pd
import numpy as np
import qtawesome as qta
import sys
from typing import List, Dict, Any, Mapping

# SQLAlchemy Imports
from sqlalchemy import create_engine, text, Engine, MetaData, Table, Column, String, Float, insert, exc
from sqlalchemy.engine import URL
from decimal import Decimal

# PyQt6 Imports
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QThread, QDate, QSize
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QAbstractItemView, QDateEdit,
    QGroupBox, QFileDialog, QSizePolicy, QTextEdit,
    QTabWidget, QGridLayout, QProgressBar, QApplication, QMainWindow, QFrame
)

# --- UI CONSTANTS (Aligned with AppStyles for visual consistency) ---
PRIMARY_ACCENT_COLOR = "#007bff"
DANGER_ACCENT_COLOR = "#dc3545"  # Red accent for Failed Report
DANGER_ACCENT_HOVER = "#fbe6e8"  # Very light red for hover background
NEUTRAL_COLOR = "#6c757d"
LIGHT_TEXT_COLOR = "#333333"
BACKGROUND_CONTENT_COLOR = "#f4f7fc"
INPUT_BACKGROUND_COLOR = "#ffffff"
GROUP_BOX_HEADER_COLOR = "#f4f7fc"
TABLE_SELECTION_COLOR = "#3a506b"  # Dark Blue-Gray from side menu selection

# --- Configuration ---
DB_CONFIG = {
    "host": "192.168.1.13",
    "port": 5432,
    "dbname": "dbfg",
    "user": "postgres",
    "password": "mbpi"
}


# --- Custom UpperCaseLineEdit Widget (Unchanged) ---
class UpperCaseLineEdit(QLineEdit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.textChanged.connect(self._to_upper)

    def _to_upper(self, text: str):
        if text and text != self.text().upper():
            self.blockSignals(True)
            self.setText(text.upper())
            self.blockSignals(False)


# --- WORKER: For Calculating Failed Inventory Summary ---
class FailedInventoryWorker(QObject):
    finished = pyqtSignal(pd.DataFrame)
    error = pyqtSignal(str)

    def __init__(self, engine: Engine, lot_filter: str = None, as_of_date: str = None):
        super().__init__()
        self.engine = engine
        self.lot_filter = lot_filter
        self.as_of_date = as_of_date

    def run(self):
        try:
            params = {}
            date_filter_clause = ""
            lot_filter_clause = ""

            if self.as_of_date:
                date_filter_clause = "AND transaction_date <= :as_of_date"
                params['as_of_date'] = self.as_of_date

            if self.lot_filter and self.lot_filter.strip():
                lot_filter_clause = "AND lot_number = :lot"
                params['lot'] = self.lot_filter.strip().upper()

            # Using double precision (PostgreSQL standard float) for calculations
            query_str = f"""
                WITH combined_movements AS (
                    -- Beginning Inventory (Using beg_invfailed1)
                    SELECT
                        UPPER(TRIM(product_code)) AS product_code, UPPER(TRIM(lot_number)) AS lot_number,
                        CAST(qty AS double precision) AS quantity_in, 0.0 AS quantity_out,
                        '1900-01-01' AS transaction_date 
                    FROM beg_invfailed1 
                    WHERE product_code IS NOT NULL AND TRIM(product_code) <> '' 
                      AND lot_number IS NOT NULL AND TRIM(lot_number) <> ''
                    UNION ALL
                    -- Failed Transactions
                    SELECT
                        UPPER(TRIM(product_code)) AS product_code, UPPER(TRIM(lot_number)) AS lot_number,
                        CAST(quantity_in AS double precision), CAST(quantity_out AS double precision),
                        transaction_date
                    FROM failed_transactions
                    WHERE product_code IS NOT NULL AND TRIM(product_code) <> '' 
                      AND lot_number IS NOT NULL AND TRIM(lot_number) <> '' 
                      AND transaction_date IS NOT NULL 
                      {date_filter_clause}
                )
                SELECT MAX(product_code) AS product_code, lot_number,
                       COALESCE(SUM(quantity_in), 0) - COALESCE(SUM(quantity_out), 0) AS current_balance
                FROM combined_movements 
                WHERE 1=1 {lot_filter_clause}
                GROUP BY lot_number
                HAVING (COALESCE(SUM(quantity_in), 0) - COALESCE(SUM(quantity_out), 0)) > 0.001
                ORDER BY lot_number;
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


# --- FAILED INVENTORY DASHBOARD WIDGET (FIXED FOR SPACE MAXIMIZATION) ---
class FailedDashboardWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.data_df = pd.DataFrame()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(15)

        grid_layout = QGridLayout()

        # 1. Overall Summary
        summary_group = QGroupBox("Overall Failed Metrics")
        summary_group.setObjectName("SummaryGroup")
        # Ensure summary group takes minimum vertical space
        summary_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        summary_layout = QHBoxLayout(summary_group)

        self.total_lots_label = self._create_summary_label("Total Failed Lots:", "0")
        self.total_products_label = self._create_summary_label("Unique Failed Products:", "0")
        self.overall_balance_label = self._create_summary_label("Overall Failed Balance (kg):", "0.00")

        summary_layout.addWidget(self.total_lots_label)
        summary_layout.addWidget(self.total_products_label)
        summary_layout.addWidget(self.overall_balance_label)

        grid_layout.addWidget(summary_group, 0, 0, 1, 2)

        # 2. Product Contribution
        self.contribution_table = self._create_contribution_table()
        contribution_group = QGroupBox("Top 10 Failed Product Contribution (by Mass)")
        contribution_group.setObjectName("ContributionGroup")
        # Ensure contribution group expands vertically
        contribution_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        vbox_contribution = QVBoxLayout(contribution_group)
        vbox_contribution.addWidget(self.contribution_table)
        grid_layout.addWidget(contribution_group, 1, 0)

        # 3. Lot Size Distribution
        self.lot_stats_group = self._create_lot_statistics_group()
        # Ensure stats group expands vertically
        self.lot_stats_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        grid_layout.addWidget(self.lot_stats_group, 1, 1)

        # FIX 1: Ensure the second row (index 1) stretches vertically
        grid_layout.setRowStretch(1, 1)

        self.layout.addLayout(grid_layout)
        # FIX 2: Removed self.layout.addStretch(1) from the main QVBoxLayout

        self.setStyleSheet(self._get_dashboard_styles())

    def _get_dashboard_styles(self) -> str:
        return f"""
            QGroupBox#SummaryGroup, QGroupBox#ContributionGroup, QGroupBox#LotStatsGroup {{
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
            QWidget[styleSheet*="border: 1px solid #d1d9e6;"] {{ 
                border: 1px solid #d1d9e6; 
                border-radius: 8px; 
                background-color: {INPUT_BACKGROUND_COLOR};
            }}

            /* Ensure all Labels in the dashboard are white backgrounded */
            QLabel {{ background-color: {INPUT_BACKGROUND_COLOR}; }}

            QLabel#TitleLabel {{ font-size: 10pt; color: {NEUTRAL_COLOR}; }}
            QLabel#ValueLabel {{ font-size: 15pt; font-weight: bold; color: {DANGER_ACCENT_COLOR}; }}

            /* Tables in Dashboard */
            QTableWidget {{ border: none; background-color: {INPUT_BACKGROUND_COLOR}; }}
            QTableWidget::item {{ border-bottom: 1px solid #f4f7fc; }}
            QHeaderView::section {{ background-color: {INPUT_BACKGROUND_COLOR}; color: {NEUTRAL_COLOR}; }}

            /* Progress Bar Styling (Red Accent) */
            QProgressBar {{ border: 1px solid #d1d9e6; border-radius: 4px; background-color: #eff2f7; }}
            QProgressBar::chunk {{ background-color: {DANGER_ACCENT_COLOR}; border-radius: 4px; }}
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
        widget.setStyleSheet(
            f"border: 1px solid #d1d9e6; border-radius: 8px; background-color: {INPUT_BACKGROUND_COLOR};")
        return widget

    def _create_contribution_table(self) -> QTableWidget:
        table = QTableWidget(columnCount=4)
        table.setHorizontalHeaderLabels(["Product Code", "Failed Balance (kg)", "Share (%)", "Visual Share"])
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.verticalHeader().setVisible(False)
        table.setFrameShape(QTableWidget.Shape.NoFrame)
        table.setShowGrid(False)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        # FIX 3: Removed table.setMaximumHeight(350)
        return table

    def _create_lot_statistics_group(self) -> QGroupBox:
        group = QGroupBox("Failed Lot Size Statistics")
        layout = QGridLayout(group)
        layout.setContentsMargins(15, 20, 15, 15)

        self.lot_stats = {
            'max_lot': QLabel("N/A"),
            'min_lot': QLabel("N/A"),
            'avg_lot': QLabel("N/A"),
            'median_lot': QLabel("N/A"),
        }

        label_style = f"font-size: 10pt; color: {NEUTRAL_COLOR};"
        value_style = f"font-weight: bold; color: {DANGER_ACCENT_COLOR};"

        layout.addWidget(QLabel("Largest Failed Lot (kg):", styleSheet=label_style), 0, 0)
        self.lot_stats['max_lot'].setStyleSheet(value_style)
        layout.addWidget(self.lot_stats['max_lot'], 0, 1, alignment=Qt.AlignmentFlag.AlignRight)

        layout.addWidget(QLabel("Smallest Failed Lot (kg):", styleSheet=label_style), 1, 0)
        self.lot_stats['min_lot'].setStyleSheet(value_style)
        layout.addWidget(self.lot_stats['min_lot'], 1, 1, alignment=Qt.AlignmentFlag.AlignRight)

        layout.addWidget(QLabel("Average Failed Lot (kg):", styleSheet=label_style), 2, 0)
        self.lot_stats['avg_lot'].setStyleSheet(value_style)
        layout.addWidget(self.lot_stats['avg_lot'], 2, 1, alignment=Qt.AlignmentFlag.AlignRight)

        layout.addWidget(QLabel("Median Failed Lot (kg):", styleSheet=label_style), 3, 0)
        self.lot_stats['median_lot'].setStyleSheet(value_style)
        layout.addWidget(self.lot_stats['median_lot'], 3, 1, alignment=Qt.AlignmentFlag.AlignRight)

        layout.setColumnStretch(1, 1)
        # Ensure this group box content stretches
        layout.setRowStretch(4, 1)
        return group

    def update_dashboard(self, df: pd.DataFrame):
        self.data_df = df

        if df.empty or df['current_balance'].sum() == 0:
            for container_widget in [self.total_lots_label, self.total_products_label, self.overall_balance_label]:
                value_label = container_widget.findChild(QLabel, "ValueLabel")
                if value_label:
                    title_label = container_widget.findChild(QLabel, "TitleLabel")
                    is_lot_count = title_label and 'Lots' in title_label.text()
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

        self.lot_stats['max_lot'].setText(f"{df['current_balance'].max():.2f}")
        self.lot_stats['min_lot'].setText(f"{df['current_balance'].min():.2f}")
        self.lot_stats['avg_lot'].setText(f"{df['current_balance'].mean():.2f}")
        self.lot_stats['median_lot'].setText(f"{df['current_balance'].median():.2f}")

        # Update contribution table
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
                QProgressBar::chunk {{ background-color: {DANGER_ACCENT_COLOR}; border-radius: 4px; }} 
            """)
            self.contribution_table.setCellWidget(i, 3, progress_bar)


# --- MAIN TAB MANAGER CLASS ---
class FailedInventoryReportPage(QWidget):
    def __init__(self, engine: Engine, username=None, log_audit_trail_func=None):
        super().__init__()
        self.engine = engine
        self.inventory_thread: QThread | None = None
        self.inventory_worker: FailedInventoryWorker | None = None
        self.current_inventory_df = pd.DataFrame(columns=['product_code', 'lot_number', 'current_balance'])

        self.dashboard_widget = FailedDashboardWidget()

        self.init_ui()
        self.setStyleSheet(self._get_styles())
        QThread.msleep(10)  # Small delay for UI initialization
        self._start_inventory_calculation()

    # ... (rest of FailedInventoryReportPage methods remain the same) ...

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

            /* Header Widget Container Transparency (Header containing icon and title) */
            #HeaderWidget {{
                background-color: transparent;
            }}

            /* Header Title */
            QLabel#PageHeader {{ 
                font-size: 16pt; 
                font-weight: bold; 
                color: {DANGER_ACCENT_COLOR}; 
                background-color: transparent; /* Explicitly ensure title background is transparent */
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
                border: 1px solid {DANGER_ACCENT_COLOR};
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
                background-color: #fef0f0; /* Very Light Red background */
                border: 1px solid {DANGER_ACCENT_COLOR};
                color: {LIGHT_TEXT_COLOR};
            }}
            QTextEdit#InstructionsBox {{
                background-color: transparent; 
                border: none;
            }}

            /* --- BUTTON STYLES (Light Color Scheme, Red Accent) --- */
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

            /* Primary Action Button (Refresh/Export - using Danger Accent Color for border/text/icon) */
            QPushButton[objectName="PrimaryButton"] {{
                color: {DANGER_ACCENT_COLOR}; 
                border: 1px solid {DANGER_ACCENT_COLOR};
            }}
            QPushButton[objectName="PrimaryButton"]:hover {{
                background-color: {DANGER_ACCENT_HOVER}; 
                border: 1px solid {DANGER_ACCENT_COLOR};
            }}

            /* Tab Bar Styling */
            QTabWidget::pane {{ border: 1px solid #e0e5eb; border-radius: 8px; background-color: {INPUT_BACKGROUND_COLOR}; padding: 10px; margin-top: -1px; }}
            QTabBar::tab {{ background-color: #e9eff7; color: {NEUTRAL_COLOR}; padding: 8px 15px; border-top-left-radius: 6px; border-top-right-radius: 6px; border: 1px solid #e0e5eb; border-bottom: none; margin-right: 4px; font-weight: normal; }}
            QTabBar::tab:selected {{ color: {DANGER_ACCENT_COLOR}; background-color: {INPUT_BACKGROUND_COLOR}; border-bottom-color: {INPUT_BACKGROUND_COLOR}; margin-bottom: -1px; font-weight: bold;}}
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
                color: {DANGER_ACCENT_COLOR};
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

        # Icon (Red Accent)
        icon_pixmap = qta.icon('fa5s.times-circle', color=DANGER_ACCENT_COLOR).pixmap(QSize(28, 28))
        icon_label = QLabel()
        icon_label.setPixmap(icon_pixmap)
        header_layout.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignLeft)

        # Header Title
        title_label = QLabel("FG Inventory Failed Computation and Export", objectName="PageHeader")
        title_label.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        main_layout.addWidget(header_widget)
        # ----------------------------

        controls_widget = QWidget()
        controls_layout = QVBoxLayout(controls_widget)
        controls_layout.addWidget(self._create_instructions_box())
        controls_layout.addWidget(self._create_filter_controls())
        controls_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(controls_widget)

        self.tab_widget = QTabWidget()
        self.tab_widget.setIconSize(QSize(16, 16))

        self.inventory_tab = QWidget()
        self.inventory_layout = QVBoxLayout(self.inventory_tab)
        self.inventory_table = self._create_inventory_table()

        self.total_balance_label = QLabel(
            "Overall Failed Record Balance: 0.00 kg", objectName="TotalBalanceLabel"
        )
        self.total_balance_label.setAlignment(Qt.AlignmentFlag.AlignRight)

        self.inventory_layout.addWidget(self.inventory_table, 1)
        self.inventory_layout.addWidget(self.total_balance_label)

        # Tab Icons (Red Accent)
        self.tab_widget.addTab(
            self.inventory_tab,
            qta.icon('fa5s.times-circle', color=DANGER_ACCENT_COLOR),
            "Failed Inventory Details"
        )

        self.tab_widget.addTab(
            self.dashboard_widget,
            qta.icon('fa5s.chart-line', color=DANGER_ACCENT_COLOR),
            "Advanced Dashboard"
        )

        # Ensure the QTabWidget takes up all remaining vertical space
        main_layout.addWidget(self.tab_widget, 1)

        # --- Connections ---
        self.refresh_button.clicked.connect(self._start_inventory_calculation)
        self.lot_number_input.editingFinished.connect(self._start_inventory_calculation)
        self.date_picker.dateChanged.connect(self._start_inventory_calculation)
        self.export_button.clicked.connect(self._export_to_excel)

    def _create_instructions_box(self) -> QGroupBox:
        group = QGroupBox("Computation Instructions")
        group.setObjectName("InstructionsBox")
        layout = QVBoxLayout(group)
        instructions = """
        This report calculates the Current Inventory Balance per Lot specifically for **FAILED** records up to the 'As Of Date'.

        Calculation Logic: Balance = (Failed Beginning Inventory) + (Failed Transactions In) - (Failed Transactions Out) [up to As Of Date]

        Data Sources: Uses beg_invfailed1 and failed_transactions tables.
        Display: Only lots with a positive failed balance (> 0.001 kg) are shown.
        """
        text_edit = QTextEdit(instructions, objectName="InstructionsBox")
        text_edit.setReadOnly(True)
        text_edit.setMaximumHeight(60)
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

        filter_layout.addSpacing(20)

        filter_layout.addWidget(QLabel("Lot Filter:"))
        self.lot_number_input = UpperCaseLineEdit(placeholderText="Lot Number")
        filter_layout.addWidget(self.lot_number_input, 1)

        filter_layout.addSpacing(20)

        # BUTTONS - Standard Light Style (Red Accent)
        self.refresh_button = QPushButton("Refresh", objectName="PrimaryButton")
        self.refresh_button.setIcon(qta.icon('fa5s.sync-alt', color=DANGER_ACCENT_COLOR))
        filter_layout.addWidget(self.refresh_button)

        self.export_button = QPushButton("Export", objectName="PrimaryButton")
        self.export_button.setIcon(qta.icon('fa5s.file-excel', color=DANGER_ACCENT_COLOR))
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

        table.setHorizontalHeaderLabels(["Associated Product", "Lot Number", "Failed Balance (kg)"])
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        return table

    def _start_inventory_calculation(self):
        if self.inventory_thread and self.inventory_thread.isRunning():
            return

        lot_filter = self.lot_number_input.text().strip()
        as_of_date = self.date_picker.date().toString(Qt.DateFormat.ISODate)

        self.export_button.setEnabled(False)
        self.set_controls_enabled(False)

        self._show_loading_state(self.inventory_table, "Calculating failed inventory balance...")
        self.dashboard_widget.update_dashboard(pd.DataFrame())

        self.inventory_thread = QThread()
        self.inventory_worker = FailedInventoryWorker(self.engine, lot_filter, as_of_date)
        self.inventory_worker.moveToThread(self.inventory_thread)

        self.inventory_thread.started.connect(self.inventory_worker.run)
        self.inventory_worker.finished.connect(self._on_inventory_finished)
        self.inventory_worker.error.connect(self._on_calculation_error)

        # 1. Signal the thread to quit upon worker completion (success or error)
        self.inventory_worker.finished.connect(self.inventory_thread.quit)
        self.inventory_worker.error.connect(self.inventory_thread.quit)

        # 2. V4 FIX: Delete worker and thread only AFTER the thread has safely quit
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
        self.refresh_button.setEnabled(enabled)
        self.date_picker.setEnabled(enabled)

        if enabled:
            can_export = not self.current_inventory_df.empty
            self.export_button.setEnabled(can_export)

    def _on_inventory_finished(self, df: pd.DataFrame):
        self.current_inventory_df = df.copy()
        is_filtered = bool(self.lot_number_input.text().strip())

        self._display_inventory(df, is_filtered)
        self.dashboard_widget.update_dashboard(df)

        self.set_controls_enabled(True)

    def _on_calculation_error(self, error_message: str):
        QMessageBox.critical(self, "Calculation Error", error_message)
        self.inventory_table.setRowCount(0)
        self.current_inventory_df = pd.DataFrame()
        self.total_balance_label.setText("Failed Record Balance: Error")
        self.dashboard_widget.update_dashboard(pd.DataFrame())
        self.set_controls_enabled(True)

    def _show_loading_state(self, table: QTableWidget, message: str):
        table.setRowCount(1)
        table.setSpan(0, 0, 1, table.columnCount())
        loading_item = QTableWidgetItem(message)
        loading_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        table.setItem(0, 0, loading_item)

    def _display_inventory(self, df: pd.DataFrame, is_filtered: bool):
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

        prefix = "Overall Failed Record Balance"
        if is_filtered and len(df) > 0:
            prefix = f"Filtered Failed Balance ({len(df)} lots)"
        elif not is_filtered:
            prefix = f"Overall Failed Record Balance ({len(df)} lots)"

        self.total_balance_label.setText(f"{prefix}: {total_balance:.2f} kg")

    def _export_to_excel(self):
        if self.current_inventory_df.empty:
            QMessageBox.information(self, "Export Failed", "No data available to export.")
            return

        # 1. Generate Filename based on the current date (date of generation)
        date_of_generate_str = QDate.currentDate().toString("yyyyMMdd")
        default_filename = f"FG-Inventory-Report-Failed as of {date_of_generate_str}.xlsx"

        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Save Failed Inventory Report",
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

                export_df.to_excel(filepath, index=False, engine='openpyxl') # Ensure openpyxl is used

                QMessageBox.information(
                    self,
                    "Export Successful",
                    f"Failed inventory data exported successfully to:\n{os.path.basename(filepath)}"
                )

            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Export Error",
                    f"Failed to save file. Ensure the file is not currently open.\nError: {e}"
                )
                traceback.print_exc()


# --- DATABASE ENGINE PROVIDER & MOCK DATA SETUP ---

class DatabaseEngineProvider:
    """Connects to PostgreSQL and ensures necessary tables exist for the demo."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.engine = self._create_engine()
        self.metadata = MetaData()
        self._define_and_check_tables()
        self._insert_mock_data_if_empty()

    def _create_engine(self) -> Engine:
        try:
            url = (
                f"postgresql+psycopg2://{self.config['user']}:{self.config['password']}@"
                f"{self.config['host']}:{self.config['port']}/{self.config['dbname']}"
            )
            print("Attempting to connect to PostgreSQL...")
            # Use pool_recycle to prevent connection timeout issues
            engine = create_engine(url, pool_recycle=3600)
            # Test connection immediately
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print("PostgreSQL connection successful.")
            return engine
        except Exception as e:
            QMessageBox.critical(None, "Database Connection Error",
                                 f"Failed to connect to PostgreSQL using provided config.\nError: {type(e).__name__}: {e}")
            sys.exit(1)

    def _define_and_check_tables(self):
        # Table 1: beg_invfailed1 (Beginning Inventory)
        Table('beg_invfailed1', self.metadata,
              Column('product_code', String(50)),
              Column('lot_number', String(50)),
              Column('qty', Float(precision=53)),
              extend_existing=True
              )

        # Table 2: failed_transactions
        Table('failed_transactions', self.metadata,
              Column('id', Float(asdecimal=False), primary_key=True),
              Column('transaction_date', String(10)),  # Stored as 'YYYY-MM-DD' text
              Column('product_code', String(50)),
              Column('lot_number', String(50)),
              Column('quantity_in', Float(precision=53)),
              Column('quantity_out', Float(precision=53)),
              extend_existing=True
              )

        # Create tables if they don't exist
        try:
            self.metadata.create_all(self.engine)
            print("Required tables ensured in PostgreSQL.")
        except Exception as e:
            print(f"Error creating tables: {e}")

    def _insert_mock_data_if_empty(self):
        # Insert mock data for testing purposes if tables are empty
        try:
            with self.engine.begin() as conn:
                # Check beg_invfailed1
                if conn.execute(text("SELECT COUNT(*) FROM beg_invfailed1")).scalar() == 0:
                    print("Inserting mock data into beg_invfailed1.")
                    beg_inv = self.metadata.tables['beg_invfailed1']
                    conn.execute(insert(beg_inv), [
                        {'product_code': 'P001', 'lot_number': 'LOTF1', 'qty': 500.0},
                        {'product_code': 'P002', 'lot_number': 'LOTF2', 'qty': 100.0},
                        {'product_code': 'P003', 'lot_number': 'LOTF3', 'qty': 50.0},
                    ])

                # Check failed_transactions
                if conn.execute(text("SELECT COUNT(*) FROM failed_transactions")).scalar() == 0:
                    print("Inserting mock data into failed_transactions.")
                    txns = self.metadata.tables['failed_transactions']

                    current_date = QDate.currentDate().toString(Qt.DateFormat.ISODate)
                    yesterday = QDate.currentDate().addDays(-1).toString(Qt.DateFormat.ISODate)
                    last_week = QDate.currentDate().addDays(-7).toString(Qt.DateFormat.ISODate)
                    # Data needed for insert
                    data = [
                        # LOTF1 movements (500 BI + 100 IN + 50 IN - 50 OUT = 600)
                        {'id': 1, 'transaction_date': yesterday, 'product_code': 'P001', 'lot_number': 'LOTF1',
                         'quantity_in': 100.0, 'quantity_out': 0.0},
                        {'id': 2, 'transaction_date': current_date, 'product_code': 'P001', 'lot_number': 'LOTF1',
                         'quantity_in': 50.0, 'quantity_out': 0.0},
                        {'id': 3, 'transaction_date': current_date, 'product_code': 'P001', 'lot_number': 'LOTF1',
                         'quantity_in': 0.0, 'quantity_out': 50.0},
                        # LOTF2 movements (100 BI + 200 IN - 10 OUT = 290)
                        {'id': 4, 'transaction_date': last_week, 'product_code': 'P002', 'lot_number': 'LOTF2',
                         'quantity_in': 200.0, 'quantity_out': 0.0},
                        {'id': 5, 'transaction_date': current_date, 'product_code': 'P002', 'lot_number': 'LOTF2',
                         'quantity_in': 0.0, 'quantity_out': 10.0},
                        # LOTF3 movements (50 BI - 51 OUT = -1 (Should disappear))
                        {'id': 6, 'transaction_date': yesterday, 'product_code': 'P003', 'lot_number': 'LOTF3',
                         'quantity_in': 0.0, 'quantity_out': 51.0},
                        # LOTF4 (Only transactions, 100 IN - 20 OUT = 80)
                        {'id': 7, 'transaction_date': yesterday, 'product_code': 'P004', 'lot_number': 'LOTF4',
                         'quantity_in': 100.0, 'quantity_out': 0.0},
                        {'id': 8, 'transaction_date': current_date, 'product_code': 'P004', 'lot_number': 'LOTF4',
                         'quantity_in': 0.0, 'quantity_out': 20.0},
                    ]
                    conn.execute(insert(txns), data)
                    print("Mock data inserted.")

        except exc.IntegrityError as e:
            # Catch primary key violations if rerunning against existing data
            print(f"Warning: Integrity error during mock data insertion (likely already exists). {e}")
        except Exception as e:
            print(f"Warning: Could not check/insert mock data into tables. Error: {e}")
            traceback.print_exc()

    def get_engine(self) -> Engine:
        return self.engine


# --- STANDALONE EXECUTION ---

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setApplicationName("Failed Inventory Report Tool (PostgreSQL)")

    # 1. Setup Database Connection (and mock data if tables are empty)
    db_provider = DatabaseEngineProvider(DB_CONFIG)
    pg_engine = db_provider.get_engine()

    # 2. Setup Main Window
    main_window = QMainWindow()
    main_window.setWindowTitle("FG Inventory Failed Computation and Export")
    main_window.resize(1000, 750)
    main_window.setStyleSheet(f"QMainWindow {{ background-color: {BACKGROUND_CONTENT_COLOR}; }}")

    # 3. Instantiate the Report Widget
    report_widget = FailedInventoryReportPage(engine=pg_engine)
    main_window.setCentralWidget(report_widget)

    main_window.show()
    sys.exit(app.exec())