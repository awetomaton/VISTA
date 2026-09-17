"""PlaybackControls widget for controlling playback"""

from PyQt6.QtCore import QElapsedTimer, Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDial,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QStyle,
    QVBoxLayout,
    QWidget,
)


class PlaybackControls(QWidget):
    """Widget for playback controls"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_playing = False
        self.min_index = 0  # Minimum display index
        self.max_index = 0  # Maximum display index
        self.current_index = 0  # Current display index
        self.fps = 10  # Playback frames (indices) per second
        self.playback_direction = 1  # 1 for forward, -1 for reverse
        self.bounce_mode = False
        self.bounce_start = 0
        self.bounce_end = 0

        # Elapsed time tracking for responsive playback
        self.elapsed_timer = QElapsedTimer()
        self.last_frame_time = 0  # Time in ms when last frame was advanced

        # Actual FPS tracking
        self.frame_times = []  # Store recent frame timestamps for FPS calculation
        self.max_frame_history = 30  # Use last 30 frames for FPS calculation

        # Callback to get current time from imagery
        self.get_current_time = None  # Function that returns current datetime or None

        self.init_ui()

        # Timer for playback - fires frequently to check if it's time to advance
        self.timer = QTimer()
        self.timer.timeout.connect(self.on_timer_tick)

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)  # left, top, right, bottom
        # layout.setSpacing(3)  # Reduce spacing between slider_section and button_layout

        # Frame slider and info layout
        slider_section = QVBoxLayout()
        slider_section.setContentsMargins(0, 0, 0, 0)
        slider_section.setSpacing(10)

        # Slider on top
        self.index_slider = QSlider(Qt.Orientation.Horizontal)
        self.index_slider.setMinimum(0)
        self.index_slider.setMaximum(0)
        self.index_slider.valueChanged.connect(self.on_slider_changed)
        slider_section.addWidget(self.index_slider)

        # Index and time info underneath
        info_layout = QHBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)

        self.index_label = QLabel("Index: 0 / 0")
        self.time_label = QLabel("")  # Will show ISO time when available

        info_layout.addStretch()
        info_layout.addWidget(self.index_label)
        info_layout.addWidget(self.time_label)
        info_layout.addStretch()

        slider_section.addLayout(info_layout)

        # Playback buttons row
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)

        # Get standard icons from the application style
        style = QApplication.style()

        self.play_button = QPushButton()
        self.play_icon = style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
        self.pause_icon = style.standardIcon(QStyle.StandardPixmap.SP_MediaPause)
        self.play_button.setIcon(self.play_icon)
        self.play_button.setToolTip("Play")
        self.play_button.clicked.connect(self.toggle_play)

        self.reverse_button = QPushButton()
        self.reverse_button.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_MediaSeekBackward))
        self.reverse_button.setToolTip("Reverse")
        self.reverse_button.clicked.connect(self.toggle_reverse)

        self.prev_button = QPushButton()
        self.prev_button.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_MediaSkipBackward))
        self.prev_button.setToolTip("Previous Frame")
        self.prev_button.clicked.connect(self.prev_index)

        self.next_button = QPushButton()
        self.next_button.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_MediaSkipForward))
        self.next_button.setToolTip("Next Frame")
        self.next_button.clicked.connect(self.next_index)

        button_layout.addStretch()
        button_layout.addWidget(self.play_button)
        button_layout.addWidget(self.reverse_button)
        button_layout.addWidget(self.prev_button)
        button_layout.addWidget(self.next_button)

        # Bounce mode controls row
        bounce_layout = QHBoxLayout()
        bounce_layout.setContentsMargins(0, 0, 0, 0)
        bounce_layout.setSpacing(5)

        self.bounce_checkbox = QCheckBox("Bounce Mode")
        self.bounce_checkbox.stateChanged.connect(self.on_bounce_toggled)

        self.bounce_start_label = QLabel("Start:")
        self.bounce_start_spinbox = QSpinBox()
        self.bounce_start_spinbox.setMinimum(0)
        self.bounce_start_spinbox.setMaximum(0)
        self.bounce_start_spinbox.setValue(0)
        self.bounce_start_spinbox.setEnabled(False)
        self.bounce_start_spinbox.valueChanged.connect(self.on_bounce_range_changed)

        self.bounce_end_label = QLabel("End:")
        self.bounce_end_spinbox = QSpinBox()
        self.bounce_end_spinbox.setMinimum(0)
        self.bounce_end_spinbox.setMaximum(0)
        self.bounce_end_spinbox.setValue(0)
        self.bounce_end_spinbox.setEnabled(False)
        self.bounce_end_spinbox.valueChanged.connect(self.on_bounce_range_changed)

        bounce_layout.addWidget(self.bounce_checkbox)
        bounce_layout.addWidget(self.bounce_start_label)
        bounce_layout.addWidget(self.bounce_start_spinbox)
        bounce_layout.addWidget(self.bounce_end_label)
        bounce_layout.addWidget(self.bounce_end_spinbox)

        button_layout.addLayout(bounce_layout)

        # FPS controls
        self.fps_label = QLabel("FPS:")
        self.fps_spinbox = QSpinBox()
        self.fps_spinbox.setMinimum(-100)
        self.fps_spinbox.setMaximum(100)
        self.fps_spinbox.setValue(self.fps)
        self.fps_spinbox.setMaximumWidth(60)
        self.fps_spinbox.valueChanged.connect(self.on_fps_spinbox_changed)

        self.fps_dial = QDial()
        self.fps_dial.setMinimum(-100)
        self.fps_dial.setMaximum(100)
        self.fps_dial.setValue(self.fps)
        self.fps_dial.setMaximumWidth(80)
        self.fps_dial.setMaximumHeight(80)
        self.fps_dial.setNotchesVisible(True)
        self.fps_dial.setWrapping(False)
        self.fps_dial.valueChanged.connect(self.on_fps_dial_changed)

        button_layout.addWidget(self.fps_label)
        button_layout.addWidget(self.fps_spinbox)
        button_layout.addWidget(self.fps_dial)

        # Actual FPS display
        self.actual_fps_label = QLabel("Actual: -- FPS")
        self.actual_fps_label.setMinimumWidth(100)
        self.actual_fps_label.setStyleSheet("QLabel { color: #666; font-style: italic; }")
        button_layout.addWidget(self.actual_fps_label)

        button_layout.addStretch()

        layout.addLayout(slider_section)
        layout.addLayout(button_layout)
        self.setLayout(layout)

    def set_index_range(self, min_index: int, max_index: int):
        """Set the range of indices without changing current index"""
        self.min_index = min_index
        self.max_index = max_index

        # Block signals to prevent triggering index changes while updating range
        self.index_slider.blockSignals(True)

        # Update slider range
        self.index_slider.setMinimum(min_index)
        self.index_slider.setMaximum(max_index)
        # Don't set value here - let set_index() handle it

        # Unblock signals
        self.index_slider.blockSignals(False)

        # Update bounce spinboxes
        self.bounce_start_spinbox.setMinimum(min_index)
        self.bounce_start_spinbox.setMaximum(max_index)
        self.bounce_start_spinbox.setValue(min_index)

        self.bounce_end_spinbox.setMinimum(min_index)
        self.bounce_end_spinbox.setMaximum(max_index)
        self.bounce_end_spinbox.setValue(max_index)

        self.bounce_start = min_index
        self.bounce_end = max_index

        self.update_label()

    def set_index(self, index: int):
        """Set current index"""
        self.current_index = index
        self.index_slider.setValue(index)
        self.update_label()

    def update_label(self):
        """Update frame label and time display"""
        self.index_label.setText(f"Index: {self.current_index} / {self.max_index}")

        # Update time display if callback is available
        if self.get_current_time is not None:
            current_time = self.get_current_time()
            if current_time is not None:
                # Convert numpy.datetime64 to ISO format string
                time_str = str(current_time)
                self.time_label.setText(f"Time: {time_str}")
            else:
                self.time_label.setText("")
        else:
            self.time_label.setText("")

    def on_slider_changed(self, value):
        """Handle slider value change"""
        self.current_index = value
        self.index_changed(value)
        self.update_label()

    def on_fps_dial_changed(self, value):
        """Handle FPS dial change"""
        if value == 0:
            # Don't allow 0 FPS, skip to 1 or -1
            return

        self.fps = abs(value)

        # Set playback direction based on sign
        if value < 0:
            self.playback_direction = -1
        else:
            self.playback_direction = 1

        # Update spinbox
        self.fps_spinbox.blockSignals(True)
        self.fps_spinbox.setValue(value)
        self.fps_spinbox.blockSignals(False)
        # No need to update timer interval - on_timer_tick uses self.fps directly

    def on_fps_spinbox_changed(self, value):
        """Handle FPS spinbox change"""
        if value == 0:
            # Don't allow 0 FPS, skip to 1 or -1 (-playback direction)
            self.fps_spinbox.setValue(-self.playback_direction)
            return

        self.fps = abs(value)

        # Set playback direction based on sign
        if value < 0:
            self.playback_direction = -1
        else:
            self.playback_direction = 1

        # Update dial
        self.fps_dial.blockSignals(True)
        self.fps_dial.setValue(value)
        self.fps_dial.blockSignals(False)
        # No need to update timer interval - on_timer_tick uses self.fps directly

    def toggle_play(self):
        """Toggle playback"""
        if self.is_playing:
            self.pause()
        else:
            self.play()

    def toggle_reverse(self):
        """Toggle reverse playback"""
        self.playback_direction *= -1

        # Update dial and spinbox to reflect direction
        new_value = self.fps * self.playback_direction

        self.fps_dial.blockSignals(True)
        self.fps_dial.setValue(new_value)
        self.fps_dial.blockSignals(False)

        self.fps_spinbox.blockSignals(True)
        self.fps_spinbox.setValue(new_value)
        self.fps_spinbox.blockSignals(False)

    def play(self):
        """Start playback"""
        self.is_playing = True
        self.play_button.setIcon(self.pause_icon)
        self.play_button.setToolTip("Pause")
        # Start elapsed timer and reset frame time
        self.elapsed_timer.start()
        self.last_frame_time = 0
        # Reset FPS tracking
        self.frame_times.clear()
        # Timer fires every 10ms to check if we should advance frame (responsive)
        self.timer.start(10)

    def pause(self):
        """Pause playback"""
        self.is_playing = False
        self.play_button.setIcon(self.play_icon)
        self.play_button.setToolTip("Play")
        self.timer.stop()
        # Reset actual FPS display
        self.actual_fps_label.setText("Actual: -- FPS")

    def on_timer_tick(self):
        """Called by timer frequently - checks if enough time has passed to advance frame"""
        if not self.is_playing:
            return

        # Calculate frame period in milliseconds
        frame_period_ms = 1000.0 / self.fps if self.fps > 0 else 1000.0

        # Get elapsed time since last frame
        elapsed_ms = self.elapsed_timer.elapsed()
        time_since_last_frame = elapsed_ms - self.last_frame_time

        # Only advance if enough time has passed
        if time_since_last_frame >= frame_period_ms:
            self.last_frame_time = elapsed_ms
            self.advance_index()

            # Track frame time for actual FPS calculation
            self.frame_times.append(elapsed_ms)
            if len(self.frame_times) > self.max_frame_history:
                self.frame_times.pop(0)

            # Calculate and update actual FPS
            self.update_actual_fps()

            # Process pending events to ensure UI remains responsive
            # This allows pause/stop actions to take effect immediately
            QApplication.processEvents()

    def advance_index(self):
        """Advance index based on playback direction and bounce mode"""
        if self.bounce_mode:
            # Bounce between start and end indices
            next_index = self.current_index + self.playback_direction

            if next_index > self.bounce_end:
                # Hit the end, reverse direction
                self.playback_direction = -1
                next_index = self.bounce_end - 1
            elif next_index < self.bounce_start:
                # Hit the start, reverse direction
                self.playback_direction = 1
                next_index = self.bounce_start + 1

            self.set_index(next_index)
        else:
            # Normal playback with looping
            if self.playback_direction == 1:
                self.next_index()
            else:
                self.prev_index_reverse()

    def next_index(self):
        """Go to next index"""
        if self.current_index < self.max_index:
            self.set_index(self.current_index + 1)
        else:
            # Loop back to beginning
            self.set_index(self.min_index)

    def prev_index(self):
        """Go to previous index"""
        if self.current_index > self.min_index:
            self.set_index(self.current_index - 1)

    def prev_index_reverse(self):
        """Go to previous index (for reverse playback with looping)"""
        if self.current_index > self.min_index:
            self.set_index(self.current_index - 1)
        else:
            # Loop to end
            self.set_index(self.max_index)

    def update_actual_fps(self):
        """Calculate and update the actual achieved FPS display"""
        if len(self.frame_times) < 2:
            self.actual_fps_label.setText("Actual: -- FPS")
            return

        # Calculate FPS from frame times
        time_span_ms = self.frame_times[-1] - self.frame_times[0]
        if time_span_ms > 0:
            num_frames = len(self.frame_times) - 1
            actual_fps = (num_frames * 1000.0) / time_span_ms
            self.actual_fps_label.setText(f"Actual: {actual_fps:.1f} FPS")
        else:
            self.actual_fps_label.setText("Actual: -- FPS")

    def on_bounce_toggled(self, state):
        """Handle bounce mode toggle"""
        self.bounce_mode = state == Qt.CheckState.Checked.value
        self.bounce_start_spinbox.setEnabled(self.bounce_mode)
        self.bounce_end_spinbox.setEnabled(self.bounce_mode)

    def on_bounce_range_changed(self):
        """Handle bounce range change"""
        self.bounce_start = self.bounce_start_spinbox.value()
        self.bounce_end = self.bounce_end_spinbox.value()

        # Ensure start < end
        if self.bounce_start >= self.bounce_end:
            self.bounce_start_spinbox.blockSignals(True)
            self.bounce_start = max(0, self.bounce_end - 1)
            self.bounce_start_spinbox.setValue(self.bounce_start)
            self.bounce_start_spinbox.blockSignals(False)

    def index_changed(self, index):
        """Override this method to handle index changes"""
        pass
