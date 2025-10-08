import sys
from datetime import datetime, date
from decimal import Decimal
from typing import Dict, Any, List
import traceback

# --- PyQt6 Imports ---
from PyQt6.QtCore import Qt, QSize, QPointF
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QGridLayout, QGroupBox, QLabel,
    QFrame, QHBoxLayout, QSplitter, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QApplication, QSizePolicy,
    QTabWidget, QLineEdit, QPushButton, QMessageBox
)
from PyQt6.QtGui import QFont, QColor, QPainter, QPen

# --- Qtawesome Import ---
import qtawesome as fa
import qtawesome as qta

# --- Charting Library Import ---
try:
    from PyQt6.QtCharts import (
        QChart, QChartView, QLineSeries, QPieSeries, QPieSlice,
        QValueAxis, QBarCategoryAxis, QHorizontalBarSeries, QBarSeries, QBarSet
    )

    CHARTS_AVAILABLE = True
except ImportError:
    print("WARNING: 'PyQt6-Charts' is not installed. Dashboard charts will be disabled.")
    print("Install it with: pip install PyQt6-Charts")
    CHARTS_AVAILABLE = False

# --- Database Imports ---
from sqlalchemy import text, create_engine, exc

# --- UNIFIED UI CONSTANTS ---
COLOR_ACCENT = '#007bff'
COLOR_PRIMARY = '#2980b9'
COLOR_SECONDARY = '#d35400'
COLOR_SUCCESS = '#27ae60'
COLOR_DANGER = '#c0392b'
COLOR_DEFAULT = '#34495e'
INPUT_BACKGROUND_COLOR = '#ffffff'
BACKGROUND_CONTENT_COLOR = '#f4f7fc'
LIGHT_TEXT_COLOR = '#333333'
GROUP_BOX_HEADER_COLOR = '#ecf0f1'
SELECTION_COLOR = '#3a506b'

# --- NEW: POSTGRESQL DATABASE CONFIGURATION ---
DB_CONFIG = {
    "host": "192.168.1.13",
    "port": 5432,
    "dbname": "dbfg",
    "user": "postgres",
    "password": "mbpi"
}


# --- HELPER WIDGETS ---
class UpperCaseLineEdit(QLineEdit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.textChanged.connect(self._to_upper)

    def _to_upper(self, text: str):
        self.blockSignals(True)
        self.setText(text.upper())
        self.blockSignals(False)


# --- DATA OVERVIEW/VISUALIZATION MODULE (DashboardAnalyticsPage) ---
class KPIWidget(QFrame):
    def __init__(self, title, value, icon_name, icon_color, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)
        self.setFixedHeight(120)
        self.setStyleSheet(f"""
            QFrame {{ 
                background-color: {INPUT_BACKGROUND_COLOR}; 
                border-radius: 8px;
            }}
            QLabel {{ background-color: transparent; }}
        """)
        layout = QHBoxLayout(self)
        icon_label = QLabel()
        icon_label.setPixmap(fa.icon(icon_name, color=icon_color).pixmap(QSize(48, 48)))
        layout.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignLeft)
        text_layout = QVBoxLayout()
        title_label = QLabel(f"<b>{title}</b>")
        title_label.setFont(QFont("Segoe UI", 10))
        value_label = QLabel(f"{value}")
        value_label.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        text_layout.addWidget(title_label)
        text_layout.addWidget(value_label)
        text_layout.addStretch()
        layout.addLayout(text_layout)
        layout.addStretch()


# --- DashboardAnalyticsPage ---
class DashboardAnalyticsPage(QWidget):
    def __init__(self, db_engine, username, log_audit_trail_func):
        super().__init__()
        self.engine = db_engine
        self.username = username
        self.log_audit_trail = log_audit_trail_func
        self._setup_ui()
        self.refresh_page()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)

        top_header_layout = QHBoxLayout()
        header = QLabel("<h1>Inventory Data Overview</h1>")
        header.setStyleSheet("color: #3a506b;")

        instruction_label = QLabel(
            "This dashboard provides a real-time summary of inventory metrics and recent activities.")
        instruction_label.setStyleSheet("font-style: italic; color: #555;")

        self.refresh_button = QPushButton(fa.icon('fa5s.sync-alt'), " Refresh Data")
        self.refresh_button.clicked.connect(self.refresh_page)

        top_header_layout.addWidget(header)
        top_header_layout.addWidget(instruction_label, 1, Qt.AlignmentFlag.AlignCenter)
        top_header_layout.addWidget(self.refresh_button)
        main_layout.addLayout(top_header_layout)

        kpi_group = QGroupBox("Key Performance Indicators (KPIs)")
        self.kpi_layout = QGridLayout(kpi_group)
        main_layout.addWidget(kpi_group)

        content_grid = QGridLayout()
        content_grid.setSpacing(15)

        flow_chart_group = QGroupBox("Inventory Flow (In, Out & Net - Last 12 Months)")
        flow_layout = QVBoxLayout(flow_chart_group)
        self.flow_chart_view = self._create_chart_view_or_placeholder("Line Chart")
        flow_layout.addWidget(self.flow_chart_view)
        content_grid.addWidget(flow_chart_group, 0, 0)

        volume_chart_group = QGroupBox("Transaction Volume by Type")
        volume_layout = QVBoxLayout(volume_chart_group)
        self.volume_chart_view = self._create_chart_view_or_placeholder("Bar Chart")
        volume_layout.addWidget(self.volume_chart_view)
        content_grid.addWidget(volume_chart_group, 0, 1)

        top_products_group = QGroupBox("Top 10 Products by Stock Level (kg)")
        top_products_layout = QVBoxLayout(top_products_group)
        self.top_products_chart_view = self._create_chart_view_or_placeholder("Bar Chart")
        top_products_layout.addWidget(self.top_products_chart_view)
        content_grid.addWidget(top_products_group, 1, 0)

        activity_group = QGroupBox("Recent Inventory Activity (Last 20 records)")
        activity_layout = QVBoxLayout(activity_group)
        self.activity_table = QTableWidget()
        self.activity_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.activity_table.setColumnCount(7)
        self.activity_table.setHorizontalHeaderLabels(
            ["Date", "Type", "Ref No", "Product", "IN (kg)", "OUT (kg)", "Remarks"])
        self.activity_table.verticalHeader().setVisible(False)
        self.activity_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.activity_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        activity_layout.addWidget(self.activity_table)
        content_grid.addWidget(activity_group, 1, 1)

        main_layout.addLayout(content_grid, 1)

    def _create_chart_view_or_placeholder(self, chart_type: str) -> QWidget:
        if CHARTS_AVAILABLE:
            chart_view = QChartView()
            chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
            return chart_view
        else:
            placeholder = QLabel(
                f"PyQt6-Charts not installed.\n{chart_type} is unavailable.\n\nPlease run: pip install PyQt6-Charts")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setMinimumHeight(350)
            placeholder.setStyleSheet("border: 1px dashed #ccc; color: #555;")
            return placeholder

    def refresh_page(self):
        self._clear_kpis()
        self._load_data()
        self.log_audit_trail("REFRESH_DASHBOARD", "User refreshed the analytics dashboard.")

    def _clear_kpis(self):
        while self.kpi_layout.count():
            child = self.kpi_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _load_data(self):
        self._load_recent_activity()
        kpi_data = self._fetch_kpi_data()

        self.kpi_layout.addWidget(
            KPIWidget("Total Stock (KG)", f"{kpi_data.get('total_stock', 0):,.2f}", 'fa5s.weight', COLOR_PRIMARY), 0, 0)
        self.kpi_layout.addWidget(
            KPIWidget("Total Stock IN (YTD)", f"{kpi_data.get('total_in_ytd', 0):,.2f}", 'fa5s.arrow-alt-circle-down',
                      COLOR_SUCCESS), 0, 1)
        self.kpi_layout.addWidget(
            KPIWidget("Total Stock OUT (YTD)", f"{kpi_data.get('total_out_ytd', 0):,.2f}", 'fa5s.arrow-alt-circle-up',
                      COLOR_DANGER), 0, 2)
        self.kpi_layout.addWidget(
            KPIWidget("Unique Products in Stock", f"{kpi_data.get('unique_products', 0):,}", 'fa5s.boxes',
                      COLOR_SECONDARY), 1,
            0)
        self.kpi_layout.addWidget(
            KPIWidget("Total Transactions (YTD)", f"{kpi_data.get('total_transactions_ytd', 0):,}", 'fa5s.exchange-alt',
                      COLOR_DEFAULT), 1, 1)
        self.kpi_layout.addWidget(
            KPIWidget("Failed Transactions (30d)", f"{kpi_data.get('failed_tx_30d', 0):,}", 'fa5s.exclamation-triangle',
                      COLOR_DANGER), 1, 2)

        if CHARTS_AVAILABLE:
            self._create_flow_chart()
            self._create_volume_barchart()
            self._create_top_products_chart()

    # --- UPDATED QUERY FOR POSTGRESQL ---
    def _fetch_kpi_data(self) -> Dict[str, Any]:
        try:
            with self.engine.connect() as conn:
                summary_query = text("""
                    SELECT 
                        (SELECT SUM(quantity_in - quantity_out) FROM transactions) as total_stock,
                        (SELECT COUNT(id) FROM transactions WHERE EXTRACT(YEAR FROM transaction_date) = EXTRACT(YEAR FROM NOW())) as total_tx_ytd,
                        (SELECT COALESCE(SUM(quantity_in), 0) FROM transactions WHERE EXTRACT(YEAR FROM transaction_date) = EXTRACT(YEAR FROM NOW())) as total_in_ytd,
                        (SELECT COALESCE(SUM(quantity_out), 0) FROM transactions WHERE EXTRACT(YEAR FROM transaction_date) = EXTRACT(YEAR FROM NOW())) as total_out_ytd,
                        (SELECT COUNT(DISTINCT product_code) FROM transactions) as unique_products,
                        (SELECT COUNT(id) FROM failed_transactions WHERE transaction_date >= NOW() - INTERVAL '30 days') as failed_count;
                """)
                result = conn.execute(summary_query).mappings().one()

            return dict(result)

        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Failed to fetch KPI data: {e}")
            print(f"Error fetching KPI data: {e}")
            return {}

    def _load_recent_activity(self):
        try:
            with self.engine.connect() as conn:
                query = text("""
                    SELECT transaction_date, transaction_type, source_ref_no, product_code, 
                           quantity_in, quantity_out, remarks
                    FROM transactions ORDER BY transaction_date DESC, id DESC LIMIT 20
                """)
                results = conn.execute(query).mappings().all()

            self.activity_table.setRowCount(len(results))
            for row_idx, record in enumerate(results):
                self.activity_table.setItem(row_idx, 0, QTableWidgetItem(str(record['transaction_date'])))
                self.activity_table.setItem(row_idx, 1, QTableWidgetItem(record['transaction_type']))
                self.activity_table.setItem(row_idx, 2, QTableWidgetItem(record['source_ref_no']))
                self.activity_table.setItem(row_idx, 3, QTableWidgetItem(record['product_code'] or 'N/A'))
                in_qty = Decimal(str(record.get('quantity_in', 0) or 0))
                out_qty = Decimal(str(record.get('quantity_out', 0) or 0))
                in_item = QTableWidgetItem(f"{in_qty:,.2f}");
                out_item = QTableWidgetItem(f"{out_qty:,.2f}")
                in_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                out_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.activity_table.setItem(row_idx, 4, in_item)
                self.activity_table.setItem(row_idx, 5, out_item)
                self.activity_table.setItem(row_idx, 6, QTableWidgetItem(record.get('remarks', '') or ''))
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Failed to load recent activity: {e}")
            self.activity_table.setRowCount(0)

    # --- UPDATED QUERY FOR POSTGRESQL ---
    def _create_flow_chart(self):
        series_in = QLineSeries();
        series_in.setName("Stock IN")
        series_out = QLineSeries();
        series_out.setName("Stock OUT")
        series_net = QLineSeries();
        series_net.setName("Net Flow")

        series_in.setPen(QPen(QColor(COLOR_SUCCESS), 3))
        series_out.setPen(QPen(QColor(COLOR_DANGER), 3))
        net_pen = QPen(QColor(COLOR_PRIMARY), 2);
        net_pen.setStyle(Qt.PenStyle.DashLine);
        series_net.setPen(net_pen)
        series_in.hovered.connect(self._handle_series_hover)
        series_out.hovered.connect(self._handle_series_hover)
        series_net.hovered.connect(self._handle_series_hover)

        query = text("""
            SELECT TO_CHAR(transaction_date, 'YYYY-MM') AS month, 
                   SUM(quantity_in) AS total_in, 
                   SUM(quantity_out) AS total_out
            FROM transactions 
            WHERE transaction_date >= date_trunc('month', NOW()) - INTERVAL '11 months'
            GROUP BY month 
            ORDER BY month;
        """)
        categories, max_val = [], 0
        try:
            with self.engine.connect() as conn:
                results = conn.execute(query).mappings().all()
            for i, row in enumerate(results):
                categories.append(datetime.strptime(row['month'], '%Y-%m').strftime('%b-%y'))
                qty_in = float(row['total_in'] or 0);
                qty_out = float(row['total_out'] or 0)
                series_in.append(i, qty_in);
                series_out.append(i, qty_out);
                series_net.append(i, qty_in - qty_out)
                max_val = max(max_val, qty_in, qty_out)
        except Exception as e:
            QMessageBox.critical(self, "Chart Error", f"Error fetching line chart data: {e}")

        chart = QChart();
        chart.addSeries(series_in);
        chart.addSeries(series_out);
        chart.addSeries(series_net)
        chart.setAnimationOptions(QChart.AnimationOption.SeriesAnimations)
        axis_x = QBarCategoryAxis();
        axis_x.append(categories);
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        axis_y = QValueAxis();
        axis_y.setLabelFormat("%.0f kg");
        axis_y.setRange(0, (max_val * 1.1) if max_val > 0 else 10)
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series_in.attachAxis(axis_x);
        series_in.attachAxis(axis_y)
        series_out.attachAxis(axis_x);
        series_out.attachAxis(axis_y)
        series_net.attachAxis(axis_x);
        series_net.attachAxis(axis_y)
        chart.legend().setVisible(True);
        chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)
        self.flow_chart_view.setChart(chart)

    def _handle_series_hover(self, point: QPointF, state: bool):
        if state:
            series = self.sender()
            self.flow_chart_view.setToolTip(f"{series.name()}: {point.y():,.2f} kg")
        else:
            self.flow_chart_view.setToolTip("")

    def _create_volume_barchart(self):
        series = QHorizontalBarSeries()
        query = text(
            "SELECT transaction_type, COUNT(id) as tx_count FROM transactions GROUP BY transaction_type ORDER BY tx_count ASC;")
        categories, max_val = [], 0
        try:
            with self.engine.connect() as conn:
                results = conn.execute(query).mappings().all()
            bar_set = QBarSet("Count")
            for row in results:
                categories.append(row['transaction_type'])
                count = int(row['tx_count'])
                bar_set.append(count)
                max_val = max(max_val, count)
            series.append(bar_set)
        except Exception as e:
            QMessageBox.critical(self, "Chart Error", f"Error fetching bar chart data: {e}")

        chart = QChart();
        chart.addSeries(series)
        chart.setAnimationOptions(QChart.AnimationOption.SeriesAnimations)
        axis_y = QBarCategoryAxis();
        axis_y.append(categories);
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        axis_x = QValueAxis();
        axis_x.setRange(0, (max_val * 1.1) if max_val > 0 else 10);
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(axis_x);
        series.attachAxis(axis_y)
        chart.legend().setVisible(False)
        self.volume_chart_view.setChart(chart)

    def _create_top_products_chart(self):
        series = QBarSeries()
        query = text("""
            SELECT product_code, SUM(quantity_in - quantity_out) as stock_balance 
            FROM transactions GROUP BY product_code HAVING SUM(quantity_in - quantity_out) > 0 
            ORDER BY stock_balance DESC LIMIT 10;
        """)
        categories, max_val = [], 0
        try:
            with self.engine.connect() as conn:
                results = conn.execute(query).mappings().all()
            bar_set = QBarSet("Stock (kg)")
            for row in results:
                categories.append(row['product_code'])
                balance = float(row['stock_balance'])
                bar_set.append(balance)
                max_val = max(max_val, balance)
            series.append(bar_set)
        except Exception as e:
            QMessageBox.critical(self, "Chart Error", f"Error fetching top products data: {e}")

        chart = QChart();
        chart.addSeries(series)
        chart.setAnimationOptions(QChart.AnimationOption.SeriesAnimations)
        axis_x = QBarCategoryAxis();
        axis_x.append(categories);
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        axis_y = QValueAxis();
        axis_y.setRange(0, (max_val * 1.1) if max_val > 0 else 10);
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_x);
        series.attachAxis(axis_y)
        chart.legend().setVisible(False)
        self.top_products_chart_view.setChart(chart)


# --- (The rest of the file is unchanged, but included for completeness) ---
class TransactionsFormPage(QWidget):
    def __init__(self, engine, username, log_audit_trail_func):
        super().__init__()
        self.engine = engine
        self.username = username
        self.log_audit_trail = log_audit_trail_func
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self);
        main_layout.setContentsMargins(10, 10, 10, 10);
        main_layout.setSpacing(10);
        header_layout = QHBoxLayout();
        icon_label = QLabel();
        icon_label.setPixmap(qta.icon('fa5s.clipboard-check', color=COLOR_SUCCESS).pixmap(32, 32));
        header_layout.addWidget(icon_label);
        title_label = QLabel("FG Passed Transaction Log");
        title_label.setStyleSheet("font-size: 15pt; font-weight: bold; color: #3a506b;");
        header_layout.addWidget(title_label);
        header_layout.addStretch();
        main_layout.addLayout(header_layout);
        instruction_label = QLabel(
            "Use the filters below to search for specific Finished Goods transactions (In/Out) that were successfully recorded.");
        instruction_label.setWordWrap(True);
        main_layout.addWidget(instruction_label);
        controls_group = QGroupBox("Filters & Actions");
        controls_layout = QHBoxLayout(controls_group);
        controls_layout.addWidget(QLabel("Search Transactions:"));
        self.search_edit = UpperCaseLineEdit();
        self.search_edit.setPlaceholderText("Filter by Product, Lot, Source Ref No...");
        controls_layout.addWidget(self.search_edit, 1);
        self.refresh_button = QPushButton(qta.icon('fa5s.sync'), "Refresh");
        controls_layout.addWidget(self.refresh_button);
        main_layout.addWidget(controls_group);
        self.table_widget = QTableWidget();
        self.table_widget.setColumnCount(11);
        self.table_widget.setHorizontalHeaderLabels(
            ["ID", "Date", "Type", "Source Ref", "Product Code", "Lot Number", "Qty In", "Qty Out", "Unit", "Warehouse",
             "Encoded By"]);
        self.table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents);
        self.table_widget.horizontalHeader().setStretchLastSection(True);
        self.table_widget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers);
        self.table_widget.verticalHeader().setVisible(False);
        self.table_widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        main_layout.addWidget(self.table_widget, 1);
        self.search_edit.textChanged.connect(self._load_transactions);
        self.refresh_button.clicked.connect(self.refresh_page)

    def refresh_page(self):
        self.search_edit.blockSignals(True);
        self.search_edit.clear();
        self.search_edit.blockSignals(
            False);
        self._load_transactions()

    def _load_transactions(self):
        self.table_widget.setRowCount(0);
        search_term = self.search_edit.text().strip()
        try:
            with self.engine.connect() as conn:
                base_query = """SELECT id, transaction_date, transaction_type, source_ref_no, product_code, lot_number, quantity_in, quantity_out, unit, warehouse, encoded_by FROM transactions """;
                params = {}
                if search_term: base_query += """WHERE product_code LIKE :search OR lot_number LIKE :search OR source_ref_no LIKE :search OR transaction_type LIKE :search""";
                params['search'] = f"%{search_term}%"
                base_query += " ORDER BY id DESC";
                query = text(base_query);
                result = conn.execute(query, params).mappings().all()
                self.table_widget.setRowCount(len(result))
                for row_idx, row_data in enumerate(result): self.table_widget.setItem(row_idx, 0, QTableWidgetItem(
                    str(row_data.get('id', ''))));self.table_widget.setItem(row_idx, 1, QTableWidgetItem(
                    str(row_data.get('transaction_date', ''))));self.table_widget.setItem(row_idx, 2, QTableWidgetItem(
                    str(row_data.get('transaction_type', ''))));self.table_widget.setItem(row_idx, 3, QTableWidgetItem(
                    str(row_data.get('source_ref_no', ''))));self.table_widget.setItem(row_idx, 4, QTableWidgetItem(
                    str(row_data.get('product_code', ''))));self.table_widget.setItem(row_idx, 5, QTableWidgetItem(
                    str(row_data.get('lot_number', ''))));qty_in_item = QTableWidgetItem(
                    f"{float(row_data.get('quantity_in', 0)):.2f}");qty_in_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter);self.table_widget.setItem(row_idx, 6,
                                                                                                           qty_in_item);qty_out_item = QTableWidgetItem(
                    f"{float(row_data.get('quantity_out', 0)):.2f}");qty_out_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter);self.table_widget.setItem(row_idx, 7,
                                                                                                           qty_out_item);self.table_widget.setItem(
                    row_idx, 8, QTableWidgetItem(str(row_data.get('unit', ''))));self.table_widget.setItem(row_idx, 9,
                                                                                                           QTableWidgetItem(
                                                                                                               str(row_data.get(
                                                                                                                   'warehouse',
                                                                                                                   ''))));self.table_widget.setItem(
                    row_idx, 10, QTableWidgetItem(str(row_data.get('encoded_by', ''))))
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Failed to load transactions: {e}");
            print(
                traceback.format_exc())


class FailedTransactionsFormPage(QWidget):
    def __init__(self, engine, username, log_audit_trail_func):
        super().__init__()
        self.engine = engine
        self.username = username
        self.log_audit_trail = log_audit_trail_func
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self);
        main_layout.setContentsMargins(10, 10, 10, 10);
        main_layout.setSpacing(10);
        header_layout = QHBoxLayout();
        icon_label = QLabel();
        icon_label.setPixmap(qta.icon('fa5s.exclamation-triangle', color=COLOR_DANGER).pixmap(32, 32));
        header_layout.addWidget(icon_label);
        title_label = QLabel("FG Failed Transaction Log");
        title_label.setStyleSheet(f"font-size: 15pt; font-weight: bold; color: {COLOR_DANGER};");
        header_layout.addWidget(title_label);
        header_layout.addStretch();
        main_layout.addLayout(header_layout);
        instruction_label = QLabel(
            "This list shows transactions that failed processing (e.g., insufficient stock or missing master data).");
        instruction_label.setWordWrap(True);
        main_layout.addWidget(instruction_label);
        controls_group = QGroupBox("Filters & Actions");
        controls_layout = QHBoxLayout(controls_group);
        controls_layout.addWidget(QLabel("Search Failed Transactions:"));
        self.search_edit = UpperCaseLineEdit();
        self.search_edit.setPlaceholderText("Filter by Product, Lot, Source Ref No...");
        controls_layout.addWidget(self.search_edit, 1);
        self.refresh_button = QPushButton(qta.icon('fa5s.sync'), "Refresh");
        controls_layout.addWidget(self.refresh_button);
        main_layout.addWidget(controls_group);
        self.table_widget = QTableWidget();
        self.table_widget.setColumnCount(11);
        self.table_widget.setHorizontalHeaderLabels(
            ["ID", "Date", "Type", "Source Ref", "Product Code", "Lot Number", "Qty In", "Qty Out", "Unit", "Warehouse",
             "Encoded By"]);
        self.table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents);
        self.table_widget.horizontalHeader().setStretchLastSection(True);
        self.table_widget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers);
        self.table_widget.verticalHeader().setVisible(False);
        self.table_widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        main_layout.addWidget(self.table_widget, 1);
        self.search_edit.textChanged.connect(self._load_transactions);
        self.refresh_button.clicked.connect(self.refresh_page)

    def refresh_page(self):
        self.search_edit.blockSignals(True);
        self.search_edit.clear();
        self.search_edit.blockSignals(
            False);
        self._load_transactions()

    def _load_transactions(self):
        self.table_widget.setRowCount(0);
        search_term = self.search_edit.text().strip()
        try:
            with self.engine.connect() as conn:
                base_query = """SELECT id, transaction_date, transaction_type, source_ref_no, product_code, lot_number, quantity_in, quantity_out, unit, warehouse, encoded_by FROM failed_transactions """;
                params = {}
                if search_term: base_query += """WHERE product_code LIKE :search OR lot_number LIKE :search OR source_ref_no LIKE :search OR transaction_type LIKE :search""";
                params['search'] = f"%{search_term}%"
                base_query += " ORDER BY id DESC";
                query = text(base_query);
                result = conn.execute(query, params).mappings().all()
                self.table_widget.setRowCount(len(result))
                for row_idx, row_data in enumerate(result): self.table_widget.setItem(row_idx, 0, QTableWidgetItem(
                    str(row_data.get('id', ''))));self.table_widget.setItem(row_idx, 1, QTableWidgetItem(
                    str(row_data.get('transaction_date', ''))));self.table_widget.setItem(row_idx, 2, QTableWidgetItem(
                    str(row_data.get('transaction_type', ''))));self.table_widget.setItem(row_idx, 3, QTableWidgetItem(
                    str(row_data.get('source_ref_no', ''))));self.table_widget.setItem(row_idx, 4, QTableWidgetItem(
                    str(row_data.get('product_code', ''))));self.table_widget.setItem(row_idx, 5, QTableWidgetItem(
                    str(row_data.get('lot_number', ''))));qty_in_item = QTableWidgetItem(
                    f"{float(row_data.get('quantity_in', 0)):.2f}");qty_in_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter);self.table_widget.setItem(row_idx, 6,
                                                                                                           qty_in_item);qty_out_item = QTableWidgetItem(
                    f"{float(row_data.get('quantity_out', 0)):.2f}");qty_out_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter);self.table_widget.setItem(row_idx, 7,
                                                                                                           qty_out_item);self.table_widget.setItem(
                    row_idx, 8, QTableWidgetItem(str(row_data.get('unit', ''))));self.table_widget.setItem(row_idx, 9,
                                                                                                           QTableWidgetItem(
                                                                                                               str(row_data.get(
                                                                                                                   'warehouse',
                                                                                                                   ''))));self.table_widget.setItem(
                    row_idx, 10, QTableWidgetItem(str(row_data.get('encoded_by', ''))))
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Failed to load transactions: {e}");
            print(
                traceback.format_exc())


class MainWindow(QMainWindow):
    def __init__(self, db_engine, username, log_audit_trail_func):
        super().__init__()
        self.engine = db_engine;
        self.username = username;
        self.log_audit_trail = log_audit_trail_func
        self.setWindowTitle("MBPI Inventory System Dashboard");
        self.setGeometry(50, 50, 1400, 900)
        self._apply_global_styles();
        self._setup_content()

    def _apply_global_styles(self):
        self.setStyleSheet(
            f"QMainWindow{{background-color:{BACKGROUND_CONTENT_COLOR}}}"
            f"QGroupBox{{border:1px solid #e0e5eb;border-radius:8px;margin-top:12px;background-color:{INPUT_BACKGROUND_COLOR}}}"
            f"QGroupBox::title{{subcontrol-origin:margin;subcontrol-position:top left;padding:2px 10px;background-color:{GROUP_BOX_HEADER_COLOR};border:1px solid #e0e5eb;border-top-left-radius:8px;border-top-right-radius:8px;font-weight:bold;color:#4f4f4f}}"
            f"QTableWidget{{border: none; background-color:{INPUT_BACKGROUND_COLOR}; selection-behavior:SelectRows; border-radius:8px}}"
            f"QTableWidget::item:selected {{ background-color:{SELECTION_COLOR}; color: white; }}"
            f"QHeaderView::section{{background-color:{GROUP_BOX_HEADER_COLOR};padding:5px}}"
            f"QTabWidget::pane{{border:1px solid #c4c4c3;background:{BACKGROUND_CONTENT_COLOR}}}"
            f"QTabWidget::tab-bar{{left:5px}}"
            f"QTabBar::tab{{background:{GROUP_BOX_HEADER_COLOR};border:1px solid #c4c4c3;border-bottom-color:#c2c7cb;border-top-left-radius:4px;border-top-right-radius:4px;padding:5px 10px}}"
            f"QTabBar::tab:selected{{background:{INPUT_BACKGROUND_COLOR};border-color:{COLOR_PRIMARY};border-bottom-color:{INPUT_BACKGROUND_COLOR}}}"
        )

    def _setup_content(self):
        tab_widget = QTabWidget();
        self.analytics_page = DashboardAnalyticsPage(self.engine, self.username, self.log_audit_trail);
        tab_widget.addTab(self.analytics_page, fa.icon('fa5s.chart-line'), "Inventory Analytics");
        self.passed_tx_page = TransactionsFormPage(self.engine, self.username, self.log_audit_trail);
        tab_widget.addTab(self.passed_tx_page, fa.icon('fa5s.clipboard-check', color=COLOR_SUCCESS),
                          "Passed Transactions");
        self.failed_tx_page = FailedTransactionsFormPage(self.engine, self.username, self.log_audit_trail);
        tab_widget.addTab(self.failed_tx_page, fa.icon('fa5s.exclamation-triangle', color=COLOR_DANGER),
                          "Failed Transactions");
        tab_widget.currentChanged.connect(self._handle_tab_change);
        self.setCentralWidget(tab_widget)

    def _handle_tab_change(self, index): widget = self.centralWidget().widget(index);getattr(widget, 'refresh_page',
                                                                                             lambda: None)()


# --- UPDATED: Connect to PostgreSQL ---
def create_db_engine():
    """Creates a SQLAlchemy engine for the PostgreSQL database."""
    try:
        # Construct the database URL from the DB_CONFIG dictionary
        db_url = (
            f"postgresql+psycopg2://{DB_CONFIG['user']}:{DB_CONFIG['password']}@"
            f"{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}"
        )
        engine = create_engine(db_url)
        # Test the connection
        with engine.connect() as connection:
            print("Successfully connected to the PostgreSQL database.")
        return engine
    except ImportError:
        QMessageBox.critical(None, "Driver Error", "psycopg2 is not installed. Please run: pip install psycopg2-binary")
        sys.exit(1)
    except exc.OperationalError as e:
        QMessageBox.critical(None, "Database Connection Error",
                             f"Could not connect to the database.\n"
                             f"Please check the connection details and ensure the database is running.\n\nError: {e}")
        sys.exit(1)
    except Exception as e:
        QMessageBox.critical(None, "Error", f"An unexpected error occurred while connecting to the database: {e}")
        sys.exit(1)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    db_engine = create_db_engine()

    if not db_engine:
        sys.exit(1)  # Exit if engine creation failed

    MOCK_USERNAME = "INVENTORY_MANAGER"


    def mock_log_audit_trail(action, details):
        print(f"[AUDIT LOG] {datetime.now().strftime('%H:%M:%S')} | {MOCK_USERNAME} | {action} | {details}")


    main_window = MainWindow(db_engine, MOCK_USERNAME, mock_log_audit_trail)
    main_window.show()
    sys.exit(app.exec())