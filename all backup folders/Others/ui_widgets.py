import collections
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    print("WARNING: 'psutil' library not found. Network graph will be disabled. Install with: pip install psutil")
    PSUTIL_AVAILABLE = False

from PyQt6.QtCore import Qt, QSize, QTimer, QRect
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QPen, QColor, QPainterPath

class NetworkGraphWidget(QWidget):
    """A widget to display real-time network activity."""
    # (Your entire NetworkGraphWidget class code goes here, unchanged)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.history_size = 60  # seconds of history
        self.upload_history = collections.deque([0.0] * self.history_size, maxlen=self.history_size)
        self.download_history = collections.deque([0.0] * self.history_size, maxlen=self.history_size)
        self.last_stats = psutil.net_io_counters() if PSUTIL_AVAILABLE else None
        self.current_upload_speed = 0
        self.current_download_speed = 0

        self.setMinimumSize(200, 25)
        self.setToolTip("Network Activity (Upload/Download)")

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_stats)
        self.timer.start(1000)  # Update every second

    def _format_speed(self, speed_bps):
        """Formats speed in bytes per second to a human-readable string."""
        if speed_bps < 1024:
            return f"{speed_bps:.1f} B/s"
        elif speed_bps < 1024 ** 2:
            return f"{speed_bps / 1024:.1f} KB/s"
        elif speed_bps < 1024 ** 3:
            return f"{speed_bps / (1024 ** 2):.1f} MB/s"
        else:
            return f"{speed_bps / (1024 ** 3):.1f} GB/s"

    def update_stats(self):
        if not PSUTIL_AVAILABLE or self.last_stats is None:
            return

        current_stats = psutil.net_io_counters()
        self.current_upload_speed = current_stats.bytes_sent - self.last_stats.bytes_sent
        self.current_download_speed = current_stats.bytes_recv - self.last_stats.bytes_recv
        self.last_stats = current_stats

        self.upload_history.append(self.current_upload_speed)
        self.download_history.append(self.current_download_speed)

        self.update()  # Trigger a repaint

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(Qt.GlobalColor.transparent)

        # Draw text
        upload_text = f"↑ {self._format_speed(self.current_upload_speed)}"
        download_text = f"↓ {self._format_speed(self.current_download_speed)}"
        font = self.font()
        font.setPointSize(8)
        painter.setFont(font)

        painter.setPen(QColor("#e67e22"))  # Orange for upload
        painter.drawText(QRect(5, 0, self.width() // 2 - 5, self.height()),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, upload_text)

        painter.setPen(QColor("#3498db"))  # Blue for download
        painter.drawText(QRect(self.width() // 2, 0, self.width() // 2 - 5, self.height()),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, download_text)

        # Draw graph lines in the background
        max_speed = max(max(self.upload_history), max(self.download_history), 1)  # Avoid division by zero
        graph_area_width = self.width() - 10
        graph_area_height = self.height() - 4
        if self.history_size > 1:
            point_spacing = graph_area_width / (self.history_size - 1)
        else:
            point_spacing = 0

        # Draw upload graph
        upload_path = QPainterPath()
        upload_path.moveTo(5, self.height() - 2 - (self.upload_history[0] / max_speed * graph_area_height))
        for i, speed in enumerate(self.upload_history):
            x = 5 + i * point_spacing
            y = self.height() - 2 - (speed / max_speed * graph_area_height)
            upload_path.lineTo(x, y)
        painter.setPen(QPen(QColor(230, 126, 34, 100), 1.5))  # Semi-transparent orange
        painter.drawPath(upload_path)

        # Draw download graph
        download_path = QPainterPath()
        download_path.moveTo(5, self.height() - 2 - (self.download_history[0] / max_speed * graph_area_height))
        for i, speed in enumerate(self.download_history):
            x = 5 + i * point_spacing
            y = self.height() - 2 - (speed / max_speed * graph_area_height)
            download_path.lineTo(x, y)
        painter.setPen(QPen(QColor(52, 152, 219, 100), 1.5))  # Semi-transparent blue
        painter.drawPath(download_path)