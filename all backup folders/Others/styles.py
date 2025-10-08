# app_styles.py

class AppStyles:
    """
    A class to hold all the stylesheet strings for the application.
    This is a professional, clean light theme with a dark blue sidebar for contrast and branding.
    """
    # ==================================================================================
    # === COLOR PALETTE ===
    # ==================================================================================
    # --- Primary Accents (Used across both light and dark areas) ---
    PRIMARY_ACCENT_COLOR = "#3498db"      # A strong, clear blue for primary actions & selections
    PRIMARY_ACCENT_HOVER = "#2980b9"
    SECONDARY_ACCENT_COLOR = "#1abc9c"    # Teal/Green for secondary actions
    SECONDARY_ACCENT_HOVER = "#16a085"
    DESTRUCTIVE_COLOR = "#e74c3c"         # Red for destructive actions (delete, remove)
    DESTRUCTIVE_COLOR_HOVER = "#c0392b"

    # --- Light Theme Neutrals (For the main content area) ---
    BG_PRIMARY = "#f4f7fc"                # Very light cool gray for the main window background
    SURFACE_COLOR = "#ffffff"             # Pure white for content areas (cards, tables, etc.)
    TEXT_PRIMARY = "#212529"              # Very dark gray (near black) for high readability
    TEXT_SECONDARY = "#6c757d"            # Muted gray for labels, headers, etc.
    BORDER_COLOR = "#dee2e6"              # Light, subtle border for defining elements
    HEADER_BG = "#e9ecef"                 # Header background for tables, group boxes

    # --- Dark Sidebar Specific Colors ---
    SIDEBAR_BG = "#2c3e50"                # Deep Midnight Blue
    SIDEBAR_BG_HOVER = "#34495e"          # Slightly lighter blue for hover states
    SIDEBAR_TEXT_PRIMARY = "#ecf0f1"      # Soft off-white for primary sidebar text
    SIDEBAR_TEXT_SECONDARY = "#bdc3c7"    # Lighter gray for secondary sidebar text (profile role)
    SIDEBAR_BORDER_SEPARATOR = "#34495e"  # Border color that blends with the sidebar

    LOGIN_STYLESHEET = f"""
        #LoginWindow, #FormFrame {{ background-color: {BG_PRIMARY}; }}
        QWidget {{ font-family: "Segoe UI"; font-size: 11pt; color: {TEXT_PRIMARY}; }}
        #LoginTitle {{ font-size: 20pt; font-weight: bold; color: {TEXT_PRIMARY}; }}
        #InputFrame {{
            background-color: {SURFACE_COLOR}; border: 1px solid {BORDER_COLOR}; border-radius: 8px; padding: 5px;
        }}
        #InputFrame:focus-within {{ border: 2px solid {PRIMARY_ACCENT_COLOR}; }}
        QLineEdit {{ border: none; background-color: transparent; padding: 8px; font-size: 11pt; }}
        QPushButton#PrimaryButton {{
            background-color: {PRIMARY_ACCENT_COLOR}; color: white;
            border-radius: 8px; padding: 12px; font-weight: bold; font-size: 12pt; border: none;
        }}
        QPushButton#PrimaryButton:hover {{ background-color: {PRIMARY_ACCENT_HOVER}; }}
        QPushButton#PrimaryButton:pressed {{ transform: scale(0.98); }}
        #StatusLabel {{ color: {DESTRUCTIVE_COLOR}; font-size: 9pt; font-weight: bold; }}
    """
    MAIN_WINDOW_STYLESHEET = f"""
        QMainWindow, QStackedWidget > QWidget {{ background-color: {BG_PRIMARY}; }}
        QWidget {{
            font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
            font-size: 10pt; color: {TEXT_PRIMARY};
        }}

        /* ==================== SIDE MENU (Dark Theme) ==================== */
        QWidget#SideMenu {{
            background-color: {SIDEBAR_BG}; border-right: 1px solid {SIDEBAR_BORDER_SEPARATOR};
        }}
        #SideMenu #ProfileName, #SideMenu #ProfileRole, #SideMenu #MenuLabel {{ background: transparent; }}
        #SideMenu #ProfileName {{ color: {SIDEBAR_TEXT_PRIMARY}; font-weight: bold; font-size: 11pt; }}
        #SideMenu #ProfileRole {{ color: {SIDEBAR_TEXT_SECONDARY}; font-size: 9pt; }}
        #SideMenu #MenuLabel {{
            font-size: 9pt; font-weight: bold; text-transform: uppercase; color: #95a5a6; /* A slightly darker gray for labels */
            padding: 10px 10px 4px 15px; margin-top: 8px; border-top: 1px solid {SIDEBAR_BORDER_SEPARATOR};
        }}
        #SideMenu #MenuLabel:first-of-type {{ border-top: none; }}
        #SideMenu QPushButton {{
            border: none; color: {SIDEBAR_TEXT_PRIMARY}; background-color: transparent;
            text-align: left; padding: 10px 10px 10px 15px;
            border-radius: 5px; margin: 2px 5px;
        }}
        #SideMenu QPushButton:hover {{ background-color: {SIDEBAR_BG_HOVER}; }}
        #SideMenu QPushButton:checked {{
            background-color: {PRIMARY_ACCENT_COLOR}; color: white; font-weight: bold;
        }}

        /* ==================== CONTENT AREA (Light Theme) ==================== */
        QGroupBox {{
            border: 1px solid {BORDER_COLOR}; border-radius: 8px;
            margin-top: 12px; background-color: {SURFACE_COLOR};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin; subcontrol-position: top left;
            padding: 2px 10px; background-color: {HEADER_BG};
            border: 1px solid {BORDER_COLOR}; border-bottom: none;
            border-top-left-radius: 8px; border-top-right-radius: 8px;
            font-weight: bold; color: {TEXT_SECONDARY};
        }}
        QLineEdit, QComboBox, QDateEdit, QDateTimeEdit, QPlainTextEdit, QDoubleSpinBox, QTextEdit {{
            border: 1px solid {BORDER_COLOR}; padding: 8px; border-radius: 5px;
            background-color: {SURFACE_COLOR};
            selection-background-color: {PRIMARY_ACCENT_COLOR}; selection-color: white;
        }}
        QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QPlainTextEdit:focus, QDoubleSpinBox:focus, QTextEdit:focus {{
            border: 1px solid {PRIMARY_ACCENT_COLOR};
        }}
        QLineEdit[readOnly="true"] {{ background-color: {HEADER_BG}; color: {TEXT_SECONDARY}; }}

        /* ==================== BUTTONS (Light Theme) ==================== */
        QPushButton {{
            border: none; padding: 9px 18px; border-radius: 6px;
            font-weight: bold; color: white;
            background-color: {TEXT_SECONDARY};
        }}
        QPushButton:hover {{ background-color: #5a6268; }}
        QPushButton:pressed {{ transform: scale(0.98); }}
        QPushButton:disabled {{ background-color: {HEADER_BG}; color: {TEXT_SECONDARY}; border: 1px solid {BORDER_COLOR}; }}

        QPushButton#PrimaryButton, #save_btn {{ background-color: {PRIMARY_ACCENT_COLOR}; }}
        QPushButton#PrimaryButton:hover, #save_btn:hover {{ background-color: {PRIMARY_ACCENT_HOVER}; }}
        QPushButton#SecondaryButton, #update_btn, #preview_btn {{ background-color: {SECONDARY_ACCENT_COLOR}; }}
        QPushButton#SecondaryButton:hover, #update_btn:hover, #preview_btn:hover {{ background-color: {SECONDARY_ACCENT_HOVER}; }}
        QPushButton#delete_btn, QPushButton#remove_item_btn {{ background-color: {DESTRUCTIVE_COLOR}; }}
        QPushButton#delete_btn:hover, QPushButton#remove_item_btn:hover {{ background-color: {DESTRUCTIVE_COLOR_HOVER}; }}

        /* ==================== TABLE (Light Theme) ==================== */
        QTableWidget {{
            border: 1px solid {BORDER_COLOR}; background-color: {SURFACE_COLOR};
            selection-behavior: SelectRows; color: {TEXT_PRIMARY}; gridline-color: {BORDER_COLOR};
            alternate-background-color: #fafcfe;
        }}
        QHeaderView::section {{
            background-color: {HEADER_BG}; padding: 8px; border: none;
            border-bottom: 1px solid {BORDER_COLOR}; font-weight: bold; text-align: left;
            color: #4f4f4f;
        }}
        QTableWidget::item {{ border-bottom: 1px solid {BORDER_COLOR}; padding: 6px 8px; }}
        QTableWidget::item:hover {{ background-color: #e6f7ff; }}
        QTableWidget::item:selected {{ background-color: {PRIMARY_ACCENT_COLOR}; color: white; }}

        /* ==================== TABS (Light Theme) ==================== */
        QTabWidget::pane {{
            border: 1px solid {BORDER_COLOR}; border-radius: 8px;
            background-color: {SURFACE_COLOR}; padding: 10px; margin-top: -1px;
        }}
        QTabBar {{ qproperty-drawBase: 0; background-color: transparent; }}
        QTabBar::tab {{
            background-color: {HEADER_BG}; color: {TEXT_SECONDARY};
            padding: 10px 25px; border-top-left-radius: 8px; border-top-right-radius: 8px;
            border: 1px solid {BORDER_COLOR}; border-bottom: none;
            margin-right: 4px; font-weight: bold;
        }}
        QTabBar::tab:selected {{
            color: {PRIMARY_ACCENT_COLOR}; background-color: {SURFACE_COLOR};
            border-bottom-color: {SURFACE_COLOR}; margin-bottom: -1px;
        }}
        QTabBar::tab:hover:!selected {{ color: {PRIMARY_ACCENT_COLOR}; }}

        /* ==================== STATUS BAR (Light Theme) ==================== */
        QStatusBar {{
            background-color: {HEADER_BG}; color: {TEXT_SECONDARY};
            font-size: 9pt; border-top: 1px solid {BORDER_COLOR};
        }}
        QStatusBar::item {{ border: none; }}
        QStatusBar QLabel {{ color: {TEXT_SECONDARY}; background: transparent; padding: 0 4px; }}
    """