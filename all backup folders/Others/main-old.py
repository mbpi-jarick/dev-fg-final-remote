import sys
from PyQt6.QtWidgets import QApplication

# Local Imports
from Others.database import initialize_database
from ui_login import LoginWindow
from ui_main import ModernMainWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)

    # 1. Initialize the database schema first
    initialize_database()

    # 2. Create the windows (main window is initially None)
    login_window = LoginWindow()
    main_window = None

    # 3. Define the function that runs on successful login
    def on_login_success(username, user_role):
        global main_window
        login_window.hide()
        main_window = ModernMainWindow(username, user_role, login_window)
        main_window.showMaximized()
        # Optional: Start with a collapsed side menu
        # main_window.toggle_side_menu()

    # 4. Connect the login window's signal to our function
    login_window.login_successful.connect(on_login_success)

    # 5. Show the login window and start the application
    login_window.show()
    sys.exit(app.exec())