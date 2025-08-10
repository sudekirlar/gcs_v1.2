
import sys
from PyQt5 import QtWidgets, QtCore
from login_ui import Ui_LoginWindow
from login_logic import LoginHandler


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    MainWindow = QtWidgets.QMainWindow()

    # Frameless pencere ve ekran ortalama
    MainWindow.setWindowFlags(QtCore.Qt.FramelessWindowHint)
    screen = QtWidgets.QDesktopWidget().screenGeometry()
    x = (screen.width() - 1920) // 2
    y = (screen.height() - 1080) // 2
    MainWindow.setGeometry(x, y, 1920, 1080)

    ui = Ui_LoginWindow()
    handler = LoginHandler(MainWindow)
    ui.setupUi(MainWindow, handler)

    MainWindow.show()
    sys.exit(app.exec_())
