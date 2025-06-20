from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget, QHBoxLayout, QSizePolicy, QStackedLayout
from PySide6.QtCore import QThread, Signal, QPointF, Qt, QTimer, QRect
from PySide6.QtGui import QPainter, QPen, QColor, QGuiApplication

import math, sys
import sys
import time

import can # python-can library for CAN bus communication
import struct # for unpacking binary data

from gpiozero import Button # for button handling
from enum import Enum

import setproctitle

setproctitle.setproctitle("rusolar-dashboard")

print("RUSolar Dashboard started...")

class ButtonType(Enum):
    SWITCH_PAGE = 1
    TOGGLE_LOGGER = 2
    EXIT_FULLSCREEN = 3

# Some global vars
MAX_SPEED = 16 # in m/s # Maximum speed of the vehicle, used to calculate percentage for speed odometer
MAX_SOC = 4471 # in Wh # Maximum SOC of the battery pack, used to calculate percentage for SOC circular meter

ALLOWED_CAN_IDS = [0x110, 0x111, 0x102]  # IDs we expect to receive from Arduino and telemetry board and Pack SOC data from BMS
CAN_BITRATE = 500000  # Standard CAN bitrate

# Global CAN bus setup
can_filters = [{'can_id': can_id, 'can_mask': 0x7FF} for can_id in ALLOWED_CAN_IDS]

bus = can.interface.Bus(channel='can0', interface='socketcan', bitrate=CAN_BITRATE, filters=can_filters)

# Button setup
switching_page_button = Button(2, pull_up=True, bounce_time=0.05)  # GPIO pin 17 for switching pages

# Utility functions
# Convert speed from m/s to mph
def ms2mph(speed):
    return speed * 2.24

# Clamp function to ensure a value is within a specified range
def clamp(value, min_value, max_value):
    return max(min_value, min(value, max_value))

class ButtonWatcher(QThread):
    new_message = Signal(int)
    finished = Signal()

    def __init__(self):
        super().__init__()
        self._running = True
        self.switching_page_button = switching_page_button
        self.switching_page_button.when_pressed = self.on_switching_button_press

    def run(self):
        while self._running:
            time.sleep(0.1)

        print("ButtonWatcher stopped")

        self.finished.emit()

    def stop(self):
        self._running = False
        self.switching_page_button.close()

    def on_switching_button_press(self):
        self.new_message.emit(ButtonType.SWITCH_PAGE.value)

class CANWorker(QThread):
    new_message = Signal(object)
    finished = Signal()

    def __init__(self):
        super().__init__()
        self._running = True

    def run(self):
        while self._running:
            msg = self.read_can_message()
            self.new_message.emit(msg)

        bus.shutdown()

        print("CANWorker stopped")

        self.finished.emit()

    def stop(self):
        self._running = False

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
    def __init__(self, circular_meter_widget, label, surfix, init_value=0):
        super().__init__()
        self.setWindowTitle("Circular Meter Container")
        self.setFixedSize(600, 400)
        self.surfix = surfix
        self.value_label = QLabel(str(round(init_value, 2)) + " " + self.surfix)
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
        self.value_label.setText(str(round(value, 2)) + " " + self.surfix)
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
        self.value_label.setText(str(round(value, 1)) + " °C")

class BPSFaultIndicator(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BPS Fault Indicator")
        self.setFixedSize(50, 50)
        self.is_faulty = False

    def update_fault_status(self, is_faulty):
        self.is_faulty = is_faulty
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self.is_faulty:
            painter.setBrush(QColor(255, 0, 0))  # Red for fault
        else:
            painter.setBrush(QColor(0, 255, 0))  # Green for normal

        painter.drawEllipse(0, 0, 40, 40)  # Draw a circle

class BPSFaultIndicatorContainer(QWidget):
    def __init__(self, label):
        super().__init__()
        self.setWindowTitle("BPS Fault Indicator Container")
        self.setFixedSize(200, 50)

        self.label_widget = QLabel(label)
        self.label_widget.setStyleSheet("font-size: 18px; font-weight: bold;")

        self.bps_fault_indicator = BPSFaultIndicator()

        layout = QHBoxLayout()
        layout.addWidget(self.label_widget)
        layout.addWidget(self.bps_fault_indicator)

        self.setLayout(layout)

    def update_fault_status(self, is_faulty):
        self.bps_fault_indicator.update_fault_status(is_faulty)

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
        text_rect = QRect(center.x() - 40, center.y() - 10, radius * 2 - 20, radius * 2 - 20)

        painter.drawText(text_rect, f"{self.value:.1f}%")

class MainDashboardWindow(QWidget):
    def __init__(self, width=800, height=600):
        super().__init__()
        self.setWindowTitle("Main Dashboard")
        self.setFixedSize(width, height)  # Set to full screen size

        # Add a Vbox layout
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        # Add to Vbox layout a Hbox layout
        hbox = QHBoxLayout()

        self.layout.addLayout(hbox)

        # Add two circular meters to the Hbox layout
        hbox1 = QHBoxLayout()

        self.soc_circular_meter_widget = CircurlarMeterContainer(SOCCircularMeter(), "SOC", "Wh", 0)
        self.speed_circular_meter_widget = CircurlarMeterContainer(CircularMeter(), "Speed", "mph", 0)

        hbox1.addWidget(self.soc_circular_meter_widget)
        hbox1.addWidget(self.speed_circular_meter_widget)

        hbox.addLayout(hbox1)

        # Add a rectangular meter for temperature
        self.cabin_temp = TempMeterContainer("Cabin Temp")
        self.cabin_temp.setMaximumWidth(150)

        self.trunk_temp = TempMeterContainer("Trunk Temp")
        self.trunk_temp.setMaximumWidth(150)
        
        self.bps_fault_indicator = BPSFaultIndicatorContainer("BPS Fault")
        self.bps_fault_indicator.setMaximumWidth(150)
        
        hbox2 = QHBoxLayout()
        hbox2.addWidget(self.cabin_temp)
        hbox2.addWidget(self.trunk_temp)
        hbox2.addWidget(self.bps_fault_indicator)

        self.layout.addLayout(hbox2)

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
        elif id == 0x111:
            # Speed data from telemetry board
            # Extract data
            data = msg.data

            # Unpack the speed value
            value = struct.unpack('<f', bytes(data[0:4]))[0]

            # Update speed odometer
            percentage = value * 100 / MAX_SPEED

            percentage = clamp(percentage, 0, 100)
            
            # Convert value to mph
            value = ms2mph(value)

            self.speed_circular_meter_widget.update_value(percentage)
            self.speed_circular_meter_widget.update_label(value)
        elif id == 0x102:
            # Pack SOC data from BMS
            # Extract data
            data = msg.data
            
            # Pack SOC is byte 0 from 0 to 100
            soc = data[0]
            
            # Update SOC circular meter
            percentage = soc  # Already in percentage
            
            val = (percentage / 100) * MAX_SOC  # Convert percentage to Wh
            
            self.soc_circular_meter_widget.update_value(percentage)
            self.soc_circular_meter_widget.update_label(val)

class CANLoggerWindow(QWidget):
    def __init__(self, width=800, height=600):
        super().__init__()
        self.setWindowTitle("CAN Logger")
        self.setFixedSize(width, height)  # Set to full screen size

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        self.labels = []
        self.limit = 20 # Maximum number of labels to display

    def handle_can_message(self, msg):
        # Handle the CAN message here
        label = QLabel(str(msg))
        self.layout.addWidget(label)
        self.labels.append(label)

        if len(self.labels) > self.limit:
            old_label = self.labels.pop(0)
            self.layout.removeWidget(old_label)
            old_label.deleteLater()

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RUSolar Dashboard")

        # Display fullscreen in the 2nd screen if available
        screens = QGuiApplication.screens()

        screen = screens[1]

        geometry = screen.geometry()

        self.setGeometry(geometry)

        self.move(geometry.topLeft())

        # Get screen size
        if screen is None:
            raise RuntimeError("No screen found")

        size = screen.availableGeometry()

        self.screen_width = size.width()

        self.screen_height = size.height()

        # # Pages
        # self.main_dashboard = MainDashboardWindow(screen_width, screen_height)
        # self.can_logger = CANLoggerWindow(screen_width, screen_height)

        # # Stack
        # self.stack = QStackedLayout()
        # self.stack.addWidget(self.main_dashboard)
        # self.stack.addWidget(self.can_logger)

        # self.setLayout(self.stack)

        # Since we only have two pages, we can use a simple flag to toggle between them
        self.toogle_page = True

        # Default to the main dashboard
        default_page = MainDashboardWindow(self.screen_width, self.screen_height)

        self.stack = QStackedLayout()
        self.stack.addWidget(default_page)
        self.setLayout(self.stack)

        # Listen for button presses
        self.button_watcher = ButtonWatcher()
        self.button_watcher.new_message.connect(self.handle_button_press)
        self.button_watcher.finished.connect(self.button_watcher.deleteLater)
        self.button_watcher.start()

        # Listen for CAN messages
        self.worker = CANWorker()
        self.worker.new_message.connect(self.handle_can_message)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()

    def handle_can_message(self, msg):
        # Log msg to a file
        with open("can_log.txt", "a") as f:
            f.write(f"{msg}\n")

        # Pass the message to the current page
        current_widget = self.stack.currentWidget()
        if isinstance(current_widget, MainDashboardWindow):
            current_widget.handle_can_message(msg)
        elif isinstance(current_widget, CANLoggerWindow):
            current_widget.handle_can_message(msg)
        else:
            raise ValueError("Unknown widget type in stack")

    def handle_button_press(self, button_type):
        if button_type == ButtonType.SWITCH_PAGE.value:
            # Switch between the main dashboard and the CAN logger
            current_widget = self.stack.currentWidget()
            self.stack.removeWidget(current_widget)
            current_widget.deleteLater()

            # Toggle
            self.toogle_page = not self.toogle_page

            if self.toogle_page:
                self.current_page = MainDashboardWindow(self.screen_width, self.screen_height)
            else:
                self.current_page = CANLoggerWindow(self.screen_width, self.screen_height)

            self.stack.addWidget(self.current_page)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.showNormal()

    def closeEvent(self, event):
        print("Stopping thread...")
        self.worker.stop()      # Ask worker to stop loop
        self.worker.quit()      # Quit the thread's event loop
        self.worker.wait()      # Block until thread is finished

        self.button_watcher.stop()  # Stop the button watcher
        self.button_watcher.quit()
        self.button_watcher.wait()

        print("Thread stopped.")

        event.accept()

def cleanup():
    print("Cleanup completed.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.aboutToQuit.connect(cleanup)  # Connect cleanup function to app exit
    main_window = MainWindow()
    main_window.showFullScreen()  # Show the main window in fullscreen mode
    sys.exit(app.exec())
