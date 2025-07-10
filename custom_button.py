from PyQt5 import QtWidgets, QtGui, QtCore



from PyQt5 import QtWidgets, QtGui, QtCore

from PyQt5 import QtWidgets, QtGui, QtCore


from PyQt5 import QtWidgets, QtGui, QtCore

class red1Button(QtWidgets.QPushButton):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        # Butonun checkable (toggle) özelliğini aktif ediyoruz ancak kullanıcı mouse ile etkileşime girmesin:
        self.setCheckable(True)
        # Butona mouse ile dokunulmasını tamamen engelle:
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        # Focus alınmamasını sağlıyoruz:
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        # Başlangıç toggle durumu:
        self._toggled = False

    def setToggleState(self, state: bool):
        """Programatik olarak buton toggle durumunu ayarlar."""
        self._toggled = state
        self.setChecked(state)
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setClipping(False)

        # Eğer toggle durumunda (basılı) ise kırmızı glow, aksi halde hiçbir efekt.
        if self._toggled:
            glow_color = QtGui.QColor(255, 0, 0, 200)  # Kırmızı, belirgin opaklık
        else:
            glow_color = QtCore.Qt.transparent

        if glow_color != QtCore.Qt.transparent:
            extra = 6  # Işığın dışa yayılma miktarı (piksel cinsinden)
            extended_rect = self.rect().adjusted(-extra, -extra, extra, extra)
            gradient = QtGui.QRadialGradient(extended_rect.center(), extended_rect.width() / 2)
            gradient.setColorAt(0.0, glow_color)
            gradient.setColorAt(1.0, QtCore.Qt.transparent)
            painter.setBrush(QtGui.QBrush(gradient))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRoundedRect(extended_rect, 200, 200)
        # Butonun metnini veya diğer içeriğini çizmek isterseniz aşağıya ekleyebilirsiniz.



class portButton(QtWidgets.QPushButton):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setMouseTracking(True)
        self._hover = False
        self._pressed = False
        self._still_pressed = False
        # Butonun kendi görünür içeriğini çizmek istemiyoruz.
        self.setStyleSheet("background: transparent; border: none;")
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        if not self._pressed:
            self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        self._pressed = True
        self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._pressed = False
        self._still_pressed = True
        self.update()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        # İstenilen glow efektinin widget sınırlarının dışına taşabilmesi için clipping'i kapatalım:
        painter.setClipping(False)

        # Glow rengi belirleniyor
        if self._pressed:
            glow_color = QtGui.QColor(0, 255, 255, 133)  # Hover durumunda cyan ve daha az şeffaf

        elif self._hover:

            glow_color = QtGui.QColor(255, 255, 255, 140)  # Press durumunda beyaz ve daha az şeffaf
        else:
            glow_color = QtCore.Qt.transparent  # Diğer durumlarda ışık yok

        if glow_color != QtCore.Qt.transparent:
            # Buton sınırlarının dışına çıkması için ekstra piksel ekleyelim:
            extra = 0  # Ne kadar dışa yayılacağı (piksel cinsinden)
            extended_rect = self.rect().adjusted(-extra, -extra, extra, extra)
            # Radial gradient; extended_rect'in merkezi ve genişliği kullanılarak:
            gradient = QtGui.QRadialGradient(extended_rect.center(), extended_rect.width() / 2)
            gradient.setColorAt(0.0, glow_color)
            gradient.setColorAt(1.0, QtCore.Qt.transparent)
            painter.setBrush(QtGui.QBrush(gradient))
            painter.setPen(QtCore.Qt.NoPen)
            # Yuvarlatılmış dikdörtgen; butonun orijinal köşe yarıçapını koruyabilir veya değiştirebilirsiniz:
            painter.drawRoundedRect(extended_rect, 1, 1)

        # Butonun kendi içeriğini çizmek istemiyoruz; sadece glow efektini çiziyoruz.


class profilButton(QtWidgets.QPushButton):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setMouseTracking(True)
        self._hover = False
        self._pressed = False
        self._still_pressed = False
        # Butonun kendi görünür içeriğini çizmek istemiyoruz.
        self.setStyleSheet("background: transparent; border: none;")
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        if not self._pressed:
            self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        self._pressed = True
        self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._pressed = False
        self._still_pressed = True
        self.update()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        # İstenilen glow efektinin widget sınırlarının dışına taşabilmesi için clipping'i kapatalım:
        painter.setClipping(False)

        # Glow rengi belirleniyor
        if self._pressed:
            glow_color = QtGui.QColor(255, 255, 255, 150)  # Press durumunda beyaz ve daha az şeffaf
        elif self._hover:

            glow_color = QtGui.QColor(255, 255, 255, 140)
        else:
            glow_color = QtCore.Qt.transparent  # Diğer durumlarda ışık yok

        if glow_color != QtCore.Qt.transparent:
            # Buton sınırlarının dışına çıkması için ekstra piksel ekleyelim:
            extra = 5  # Ne kadar dışa yayılacağı (piksel cinsinden)
            extended_rect = self.rect().adjusted(-extra, -extra, extra, extra)
            # Radial gradient; extended_rect'in merkezi ve genişliği kullanılarak:
            gradient = QtGui.QRadialGradient(extended_rect.center(), extended_rect.width() / 2)
            gradient.setColorAt(0.0, glow_color)
            gradient.setColorAt(1.0, QtCore.Qt.transparent)
            painter.setBrush(QtGui.QBrush(gradient))
            painter.setPen(QtCore.Qt.NoPen)
            # Yuvarlatılmış dikdörtgen; butonun orijinal köşe yarıçapını koruyabilir veya değiştirebilirsiniz:
            painter.drawRoundedRect(extended_rect, 100, 100)

        # Butonun kendi içeriğini çizmek istemiyoruz; sadece glow efektini çiziyoruz.


class cizgiButton(QtWidgets.QPushButton):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setMouseTracking(True)
        self._hover = False
        self._pressed = False
        self._still_pressed = False
        # Butonun kendi görünür içeriğini çizmek istemiyoruz.
        self.setStyleSheet("background: transparent; border: none;")
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        if not self._pressed:
            self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        self._pressed = True
        self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._pressed = False
        self._still_pressed = True
        self.update()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        # İstenilen glow efektinin widget sınırlarının dışına taşabilmesi için clipping'i kapatalım:
        painter.setClipping(False)

        # Glow rengi belirleniyor
        if self._pressed:
            glow_color = QtGui.QColor(0, 255, 255, 133)  # Hover durumunda cyan ve daha az şeffaf

        elif self._hover:

            glow_color = QtGui.QColor(255, 255, 255, 140)  # Press durumunda beyaz ve daha az şeffaf
        else:
            glow_color = QtCore.Qt.transparent  # Diğer durumlarda ışık yok

        if glow_color != QtCore.Qt.transparent:
            # Buton sınırlarının dışına çıkması için ekstra piksel ekleyelim:
            extra = 2  # Ne kadar dışa yayılacağı (piksel cinsinden)
            extended_rect = self.rect().adjusted(-extra, -extra, extra, extra)
            # Radial gradient; extended_rect'in merkezi ve genişliği kullanılarak:
            gradient = QtGui.QRadialGradient(extended_rect.center(), extended_rect.width() / 2)
            gradient.setColorAt(0.0, glow_color)
            gradient.setColorAt(1.0, QtCore.Qt.transparent)
            painter.setBrush(QtGui.QBrush(gradient))
            painter.setPen(QtCore.Qt.NoPen)
            # Yuvarlatılmış dikdörtgen; butonun orijinal köşe yarıçapını koruyabilir veya değiştirebilirsiniz:
            painter.drawRoundedRect(extended_rect, 50, 50)

        # Butonun kendi içeriğini çizmek istemiyoruz; sadece glow efektini çiziyoruz.



class redButton(QtWidgets.QPushButton):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setMouseTracking(True)
        self._hover = False
        self._pressed = False
        self._still_pressed = False
        # Butonun kendi görünür içeriğini çizmek istemiyoruz.
        self.setStyleSheet("background: transparent; border: none;")
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        if not self._pressed:
            self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        self._pressed = True
        self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._pressed = False
        self._still_pressed = True
        self.update()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        # İstenilen glow efektinin widget sınırlarının dışına taşabilmesi için clipping'i kapatalım:
        painter.setClipping(False)

        # Glow rengi belirleniyor
        if self._pressed:
            glow_color = QtGui.QColor(128, 0, 128, 140)  # Press durumunda mor ve daha şeffaf (purple)
        elif self._hover:
            glow_color = QtGui.QColor(255, 0, 0, 145)  # Hover durumunda kırmızı ve daha şeffaf (red)
        else:
            glow_color = QtCore.Qt.transparent  # Diğer durumlarda ışık yok

        if glow_color != QtCore.Qt.transparent:
            # Buton sınırlarının dışına çıkması için ekstra piksel ekleyelim:
            extra = 4  # Ne kadar dışa yayılacağı (piksel cinsinden)
            extended_rect = self.rect().adjusted(-extra, -extra, extra, extra)
            # Radial gradient; extended_rect'in merkezi ve genişliği kullanılarak:
            gradient = QtGui.QRadialGradient(extended_rect.center(), extended_rect.width() / 2)
            gradient.setColorAt(0.0, glow_color)
            gradient.setColorAt(1.0, QtCore.Qt.transparent)
            painter.setBrush(QtGui.QBrush(gradient))
            painter.setPen(QtCore.Qt.NoPen)
            # Yuvarlatılmış dikdörtgen; butonun orijinal köşe yarıçapını koruyabilir veya değiştirebilirsiniz:
            painter.drawRoundedRect(extended_rect, 40, 40)

        # Butonun kendi içeriğini çizmek istemiyoruz; sadece glow efektini çiziyoruz.

from PyQt5 import QtWidgets, QtGui, QtCore

class GlowButton(QtWidgets.QPushButton):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setMouseTracking(True)
        self._hover = False
        self._pressed = False
        self._still_pressed = False
        # Butonun kendi görünür içeriğini çizmek istemiyoruz.
        self.setStyleSheet("background: transparent; border: none;")
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        if not self._pressed:
            self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        self._pressed = True
        self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._pressed = False
        self._still_pressed = True
        self.update()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        # İstenilen glow efektinin widget sınırlarının dışına taşabilmesi için clipping'i kapatalım:
        painter.setClipping(False)

        # Glow rengi belirleniyor
        if self._pressed:
            glow_color = QtGui.QColor(0, 255, 255, 133)  # Hover durumunda cyan ve daha az şeffaf

        elif self._hover:

            glow_color = QtGui.QColor(255, 255, 255, 140)  # Press durumunda beyaz ve daha az şeffaf
        else:
            glow_color = QtCore.Qt.transparent  # Diğer durumlarda ışık yok

        if glow_color != QtCore.Qt.transparent:
            # Buton sınırlarının dışına çıkması için ekstra piksel ekleyelim:
            extra = 10  # Ne kadar dışa yayılacağı (piksel cinsinden)
            extended_rect = self.rect().adjusted(-extra, -extra, extra, extra)
            # Radial gradient; extended_rect'in merkezi ve genişliği kullanılarak:
            gradient = QtGui.QRadialGradient(extended_rect.center(), extended_rect.width() / 2)
            gradient.setColorAt(0.0, glow_color)
            gradient.setColorAt(1.0, QtCore.Qt.transparent)
            painter.setBrush(QtGui.QBrush(gradient))
            painter.setPen(QtCore.Qt.NoPen)
            # Yuvarlatılmış dikdörtgen; butonun orijinal köşe yarıçapını koruyabilir veya değiştirebilirsiniz:
            painter.drawRoundedRect(extended_rect, 80, 80)

        # Butonun kendi içeriğini çizmek istemiyoruz; sadece glow efektini çiziyoruz.
