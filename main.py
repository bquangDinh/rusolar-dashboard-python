from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget, QHBoxLayout, QSizePolicy
from PySide6.QtCore import QThread, Signal, QPointF, Qt, QTimer, QRect
from PySide6.QtGui import QPainter, QPen, QColor
import math, sys
import sys
import time
import can # python-can library for CAN bus communication
import struct

# Global CAN bus setup
bus = can.interface.Bus(channel='can0', interface='socketcan')

class CANWorker(QThread):
    new_message = Signal(object)

    def run(self):
        while True:
            msg = self.read_can_message()
            self.new_message.emit(msg)

    def read_can_message(self):
        msg = bus.recv()        
        return msg

class CircularMeter(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Circular Meter")
        self.setFixedSize(300, 300)
        self.value = 0

    # Update the value of the meter, the value should be between 0 and 100
    def update_value(self, value):
        self.value = value
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        center = self.rect().center()
        radius = min(self.width(), self.height()) // 2 - 20
        angle_span = 240  # how wide the arc is
        start_angle = 150  # where the arc starts

        # Draw background arc
        pen = QPen(QColor(200, 200, 200), 20)
        painter.setPen(pen)
        painter.drawArc(
            center.x() - radius,
            center.y() - radius,
            radius * 2,
            radius * 2,
            (start_angle) * 16,
            (-angle_span) * 16,
        )

        # Draw needle arc
        pen.setColor(QColor(50, 200, 50))
        painter.setPen(pen)
        span = int(self.value / 100 * angle_span)
        painter.drawArc(
            center.x() - radius,
            center.y() - radius,
            radius * 2,
            radius * 2,
            (start_angle) * 16,
            (-span) * 16,
        )

        # Draw needle line
        painter.setPen(QPen(Qt.red, 4))
        angle_deg = start_angle - self.value / 100 * angle_span
        angle_rad = math.radians(angle_deg)
        needle_length = radius - 20
        x = center.x() + math.cos(angle_rad) * needle_length
        y = center.y() - math.sin(angle_rad) * needle_length
        painter.drawLine(center, QPointF(x, y))

        # Draw center dot
        painter.setPen(Qt.NoPen)
        painter.setBrush(Qt.black)
        painter.drawEllipse(center, 5, 5)

class CircurlarMeterContainer(QWidget):
    def __init__(self, circular_meter_widget, label, surfix, process_val_func, init_value=0):
        super().__init__()
        self.setWindowTitle("Circular Meter Container")
        self.setFixedSize(600, 400)
        self.surfix = surfix
        self.value_label = QLabel(str(process_val_func(init_value)) + " " + self.surfix)
        self.value_label.setStyleSheet("font-size: 24px; font-weight: bold;")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.value_label.setMaximumWidth(300)
        self.circular_meter = circular_meter_widget

        label_widget = QLabel(label)
        label_widget.setStyleSheet("font-size: 18px; font-weight: bold;")
        label_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label_widget.setMaximumWidth(300)

        layout = QVBoxLayout()
        layout.addWidget(label_widget)
        layout.addWidget(self.circular_meter)
        layout.addWidget(self.value_label)

        self.circular_meter.update_value(init_value)

        self.setLayout(layout)

    def update_value(self, value):
        self.circular_meter.update_value(value)
    
    def update_label(self, value):
        self.value_label.setText(str(value))
        self.value_label.update()

class TempMeterContainer(QWidget):
    def __init__(self, label, init_value=0):
        super().__init__()
        self.setWindowTitle("Temperature Meter Container")
        self.setFixedSize(300, 50)

        self.value_label = QLabel(str(init_value) + " °C")
        self.value_label.setStyleSheet("font-size: 24px; font-weight: bold;")
        
        self.label_widget = QLabel(label)
        self.label_widget.setStyleSheet("font-size: 18px; font-weight: bold;")

        self.layout = QHBoxLayout()
        self.layout.addWidget(self.label_widget)
        self.layout.addWidget(self.value_label)
        self.setLayout(self.layout)

    def update_value(self, value):
        self.value_label.setText(str(value) + " °C")

class SOCCircularMeter(QWidget):
    def __init__(self):
            super().__init__()
            self.setWindowTitle("Circular Meter")
            self.setFixedSize(300, 300)
            self.value = 0

    # Update the value of the meter, the value should be between 0 and 100
    def update_value(self, value):
        self.value = value
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        center = self.rect().center()
        radius = min(self.width(), self.height()) // 2 - 20

        # Draw a full circle background
        pen = QPen(QColor(200, 200, 200), 20)
        painter.setPen(pen)
        painter.drawEllipse(center, radius, radius)

        # Draw the filled arc based on the value
        angle_span = 360 * self.value / 100
        start_angle = 90  # Start from the top
        pen.setColor(QColor(50, 200, 50))
        painter.setPen(pen)
        painter.drawArc(
            center.x() - radius,
            center.y() - radius,
            radius * 2,
            radius * 2,
            (start_angle - angle_span) * 16,
            angle_span * 16,
        )

        # Draw the text in the center
        painter.setPen(Qt.black)
        font = painter.font()
        font.setPointSize(24)
        painter.setFont(font)

        # Offset the text slightly to center it, only change the x position
        text_rect = QRect(center.x() - 50, center.y() - 10, radius * 2 - 20, radius * 2 - 20)

        painter.drawText(text_rect, f"{self.value:.1f}%")

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CAN + Qt GUI")

        # Add a Vbox layout
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        # Add to Vbox layout a Hbox layout
        hbox = QHBoxLayout()

        self.layout.addLayout(hbox)

        # Add two circular meters to the Hbox layout
        hbox1 = QHBoxLayout()

        self.circular_meter_widget1 = CircurlarMeterContainer(SOCCircularMeter(), "SOC", "W", lambda x: x, 100)
        self.circular_meter_widget2 = CircurlarMeterContainer(CircularMeter(), "Speed", "km/h", lambda x: x, 75)
        
        hbox1.addWidget(self.circular_meter_widget1)
        hbox1.addWidget(self.circular_meter_widget2)

        hbox.addLayout(hbox1)

        # Add a rectangular meter for temperature
        self.cabin_temp = TempMeterContainer("Cabin Temp")
        self.cabin_temp.setMaximumWidth(300)

        self.trunk_temp = TempMeterContainer("Trunk Temp")
        self.trunk_temp.setMaximumWidth(300)

        hbox2 = QHBoxLayout()
        hbox2.addWidget(self.cabin_temp)
        hbox2.addWidget(self.trunk_temp)

        self.layout.addLayout(hbox2)

        # Listen for CAN messages
        self.worker = CANWorker()
        self.worker.new_message.connect(self.handle_can_message)
        self.worker.start()

    def handle_can_message(self, msg):
        # Extract ID
        id = msg.arbitration_id

        # If ID is from Arduino (0x110)
        if id == 0x110:
            # Extract data
            data = msg.data

            # The first byte represents ID of the sensor (where it is located)
            sensor_id = data[0]

            # The next 4 bytes represent the value (float)
            value = struct.unpack('<f', bytes(data[1:5]))[0]

            # Update the corresponding circular meter or temperature meter
            if sensor_id == 0x00:
                self.cabin_temp.update_value(value)
            elif sensor_id == 0x01:
                self.trunk_temp.update_value(value)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.showNormal()  # exit fullscreen

if __name__ == "__main__":
    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.showFullScreen()
    sys.exit(app.exec())
