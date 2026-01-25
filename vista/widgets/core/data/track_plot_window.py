"""Track plot window for visualizing track point-by-point data"""
import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QRadioButton, QSpinBox, QTabWidget, QVBoxLayout, QWidget
)

from vista.sensors.sampled_sensor import SampledSensor
from vista.tracks.track import Track
from vista.transforms.polynomials import evaluate_2d_polynomial


class TrackPlotWindow(QWidget):
    """Modeless window for plotting track details."""

    # Available symbols in pyqtgraph
    SYMBOLS = ['o', 's', 't', 'd', '+', 'x', 'star']

    # Distinct color palette for tracks/trackers
    COLORS = [
        '#1f77b4',  # Blue
        '#ff7f0e',  # Orange
        '#2ca02c',  # Green
        '#d62728',  # Red
        '#9467bd',  # Purple
        '#8c564b',  # Brown
        '#e377c2',  # Pink
        '#7f7f7f',  # Gray
        '#bcbd22',  # Olive
        '#17becf',  # Cyan
    ]

    def __init__(self, parent, viewer):
        """
        Initialize the TrackPlotWindow.

        Parameters
        ----------
        parent : QWidget
            Parent widget
        viewer : ImageryViewer
            Reference to the main imagery viewer for frame synchronization
        """
        super().__init__(parent)
        self.viewer = viewer
        self.tracks = []  # List of Track objects
        self.tracker_map = {}  # track.uuid -> tracker name

        # Cache for plottable data
        self._cached_data = {}  # track.uuid -> dict of data arrays

        # Store plot data items for hover detection
        self._static_plot_items = []  # List of (track, PlotDataItem)
        self._animated_plot_items = []  # List of (track, PlotDataItem)

        self.setWindowTitle("Track Details Plot")
        self.setWindowFlags(Qt.WindowType.Window)
        self.resize(800, 600)

        self.init_ui()

        # Connect tab change to update only the visible plot
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()

        # Selected tracks display
        self.tracks_label = QLabel("Selected Tracks: None")
        self.tracks_label.setWordWrap(True)
        layout.addWidget(self.tracks_label)

        # Tab widget for static and animated plots
        self.tab_widget = QTabWidget()

        # === Static Plot Tab ===
        static_widget = QWidget()
        static_layout = QVBoxLayout()

        # Axis selection
        static_axis_layout = QHBoxLayout()
        static_axis_layout.addWidget(QLabel("X-Axis:"))
        self.static_x_combo = QComboBox()
        self.static_x_combo.setMinimumWidth(150)
        self.static_x_combo.currentIndexChanged.connect(self._on_static_settings_changed)
        static_axis_layout.addWidget(self.static_x_combo)

        static_axis_layout.addWidget(QLabel("Y-Axis:"))
        self.static_y_combo = QComboBox()
        self.static_y_combo.setMinimumWidth(150)
        self.static_y_combo.currentIndexChanged.connect(self._on_static_settings_changed)
        static_axis_layout.addWidget(self.static_y_combo)

        static_axis_layout.addStretch()
        static_layout.addLayout(static_axis_layout)

        # Color mode and legend checkbox
        static_color_layout = QHBoxLayout()
        static_color_layout.addWidget(QLabel("Color By:"))
        self.static_color_by_track = QRadioButton("Track")
        self.static_color_by_track.setChecked(True)
        self.static_color_by_tracker = QRadioButton("Tracker")
        self.static_color_group = QButtonGroup()
        self.static_color_group.addButton(self.static_color_by_track, 0)
        self.static_color_group.addButton(self.static_color_by_tracker, 1)
        self.static_color_group.buttonClicked.connect(self._on_static_settings_changed)
        static_color_layout.addWidget(self.static_color_by_track)
        static_color_layout.addWidget(self.static_color_by_tracker)

        # Show legend checkbox
        self.static_show_legend = QCheckBox("Show Legend")
        self.static_show_legend.setChecked(False)
        self.static_show_legend.stateChanged.connect(self._on_static_legend_toggled)
        static_color_layout.addWidget(self.static_show_legend)

        # Symmetric log Y-axis checkbox
        self.static_symlog_y = QCheckBox("Symlog Y")
        self.static_symlog_y.setToolTip("Use symmetric logarithmic scale for Y-axis\n(handles both positive and negative values)")
        self.static_symlog_y.setChecked(False)
        self.static_symlog_y.stateChanged.connect(self._on_static_settings_changed)
        static_color_layout.addWidget(self.static_symlog_y)

        static_color_layout.addStretch()
        static_layout.addLayout(static_color_layout)

        # Static plot widget
        self.static_plot = pg.PlotWidget()
        self.static_plot.showGrid(x=True, y=True)
        self._static_legend = None  # Will be created on demand
        static_layout.addWidget(self.static_plot)

        # Hover info label for static plot
        self.static_hover_label = QLabel("")
        self.static_hover_label.setStyleSheet("color: gray; font-style: italic;")
        static_layout.addWidget(self.static_hover_label)

        # Connect mouse move for hover detection
        self.static_plot.scene().sigMouseMoved.connect(self._on_static_mouse_moved)

        static_widget.setLayout(static_layout)
        self.tab_widget.addTab(static_widget, "Static Plot")

        # === Animated Plot Tab ===
        animated_widget = QWidget()
        animated_layout = QVBoxLayout()

        # Axis selection
        animated_axis_layout = QHBoxLayout()
        animated_axis_layout.addWidget(QLabel("X-Axis:"))
        self.animated_x_combo = QComboBox()
        self.animated_x_combo.setMinimumWidth(150)
        self.animated_x_combo.currentIndexChanged.connect(self._on_animated_settings_changed)
        animated_axis_layout.addWidget(self.animated_x_combo)

        animated_axis_layout.addWidget(QLabel("Y-Axis:"))
        self.animated_y_combo = QComboBox()
        self.animated_y_combo.setMinimumWidth(150)
        self.animated_y_combo.currentIndexChanged.connect(self._on_animated_settings_changed)
        animated_axis_layout.addWidget(self.animated_y_combo)

        animated_axis_layout.addStretch()
        animated_layout.addLayout(animated_axis_layout)

        # Color mode and legend checkbox
        animated_color_layout = QHBoxLayout()
        animated_color_layout.addWidget(QLabel("Color By:"))
        self.animated_color_by_track = QRadioButton("Track")
        self.animated_color_by_track.setChecked(True)
        self.animated_color_by_tracker = QRadioButton("Tracker")
        self.animated_color_group = QButtonGroup()
        self.animated_color_group.addButton(self.animated_color_by_track, 0)
        self.animated_color_group.addButton(self.animated_color_by_tracker, 1)
        self.animated_color_group.buttonClicked.connect(self._on_animated_settings_changed)
        animated_color_layout.addWidget(self.animated_color_by_track)
        animated_color_layout.addWidget(self.animated_color_by_tracker)

        # Show legend checkbox
        self.animated_show_legend = QCheckBox("Show Legend")
        self.animated_show_legend.setChecked(False)
        self.animated_show_legend.stateChanged.connect(self._on_animated_legend_toggled)
        animated_color_layout.addWidget(self.animated_show_legend)

        # Symmetric log Y-axis checkbox
        self.animated_symlog_y = QCheckBox("Symlog Y")
        self.animated_symlog_y.setToolTip("Use symmetric logarithmic scale for Y-axis\n(handles both positive and negative values)")
        self.animated_symlog_y.setChecked(False)
        self.animated_symlog_y.stateChanged.connect(self._on_animated_settings_changed)
        animated_color_layout.addWidget(self.animated_symlog_y)

        animated_color_layout.addStretch()
        animated_layout.addLayout(animated_color_layout)

        # Display mode selection
        display_mode_layout = QHBoxLayout()
        display_mode_layout.addWidget(QLabel("Display Mode:"))
        self.up_to_frame_radio = QRadioButton("Up to frame")
        self.up_to_frame_radio.setChecked(True)
        self.tail_length_radio = QRadioButton("Tail length")
        self.display_mode_group = QButtonGroup()
        self.display_mode_group.addButton(self.up_to_frame_radio, 0)
        self.display_mode_group.addButton(self.tail_length_radio, 1)
        self.display_mode_group.buttonClicked.connect(self._on_display_mode_changed)
        display_mode_layout.addWidget(self.up_to_frame_radio)
        display_mode_layout.addWidget(self.tail_length_radio)

        display_mode_layout.addWidget(QLabel("Tail Length:"))
        self.tail_length_spin = QSpinBox()
        self.tail_length_spin.setMinimum(1)
        self.tail_length_spin.setMaximum(1000)
        self.tail_length_spin.setValue(10)
        self.tail_length_spin.setEnabled(False)
        self.tail_length_spin.valueChanged.connect(self._on_animated_settings_changed)
        display_mode_layout.addWidget(self.tail_length_spin)
        display_mode_layout.addStretch()
        animated_layout.addLayout(display_mode_layout)

        # Animated plot widget
        self.animated_plot = pg.PlotWidget()
        self.animated_plot.showGrid(x=True, y=True)
        self._animated_legend = None  # Will be created on demand
        animated_layout.addWidget(self.animated_plot)

        # Hover info label for animated plot
        self.animated_hover_label = QLabel("")
        self.animated_hover_label.setStyleSheet("color: gray; font-style: italic;")
        animated_layout.addWidget(self.animated_hover_label)

        # Connect mouse move for hover detection
        self.animated_plot.scene().sigMouseMoved.connect(self._on_animated_mouse_moved)

        animated_widget.setLayout(animated_layout)
        self.tab_widget.addTab(animated_widget, "Animated Plot")

        layout.addWidget(self.tab_widget)

        # Bottom buttons
        button_layout = QHBoxLayout()
        self.export_data_btn = QPushButton("Export Data...")
        self.export_data_btn.clicked.connect(self.export_data)
        button_layout.addWidget(self.export_data_btn)

        self.export_plot_btn = QPushButton("Export Plot...")
        self.export_plot_btn.clicked.connect(self.export_plot)
        button_layout.addWidget(self.export_plot_btn)

        button_layout.addStretch()

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.close)
        button_layout.addWidget(self.close_btn)

        layout.addLayout(button_layout)

        self.setLayout(layout)

    def _on_tab_changed(self, index):
        """Handle tab change - update the newly visible plot"""
        if index == 0:
            self.update_static_plot()
        else:
            self.update_animated_plot()

    def _on_static_settings_changed(self):
        """Handle static plot settings change"""
        if self.tab_widget.currentIndex() == 0:
            self.update_static_plot()

    def _on_animated_settings_changed(self):
        """Handle animated plot settings change"""
        if self.tab_widget.currentIndex() == 1:
            self.update_animated_plot()

    def _on_display_mode_changed(self):
        """Handle display mode radio button change"""
        self.tail_length_spin.setEnabled(self.tail_length_radio.isChecked())
        self._on_animated_settings_changed()

    def _on_static_legend_toggled(self, state):
        """Toggle static plot legend visibility"""
        if state == Qt.CheckState.Checked.value:
            if self._static_legend is None:
                self._static_legend = self.static_plot.addLegend()
            self.update_static_plot()  # Redraw to populate legend
        else:
            if self._static_legend is not None:
                # Remove legend from scene properly
                self._static_legend.scene().removeItem(self._static_legend)
                self.static_plot.plotItem.legend = None
                self._static_legend = None
                self.update_static_plot()  # Redraw without legend

    def _symlog(self, x):
        """
        Apply symmetric logarithmic transform.

        This transform handles both positive and negative values:
        symlog(x) = sign(x) * log10(1 + |x|)

        Parameters
        ----------
        x : np.ndarray
            Input data

        Returns
        -------
        np.ndarray
            Transformed data
        """
        return np.sign(x) * np.log10(1 + np.abs(x))

    def _on_animated_legend_toggled(self, state):
        """Toggle animated plot legend visibility"""
        if state == Qt.CheckState.Checked.value:
            if self._animated_legend is None:
                self._animated_legend = self.animated_plot.addLegend()
            self.update_animated_plot()  # Redraw to populate legend
        else:
            if self._animated_legend is not None:
                # Remove legend from scene properly
                self._animated_legend.scene().removeItem(self._animated_legend)
                self.animated_plot.plotItem.legend = None
                self._animated_legend = None
                self.update_animated_plot()  # Redraw without legend

    def _on_static_mouse_moved(self, pos):
        """Handle mouse move on static plot for hover detection"""
        self._handle_mouse_hover(pos, self.static_plot, self._static_plot_items, self.static_hover_label)

    def _on_animated_mouse_moved(self, pos):
        """Handle mouse move on animated plot for hover detection"""
        self._handle_mouse_hover(pos, self.animated_plot, self._animated_plot_items, self.animated_hover_label)

    def _handle_mouse_hover(self, pos, plot_widget, plot_items, hover_label):
        """Handle mouse hover to display track info"""
        if len(plot_items) == 0:
            hover_label.setText("")
            return

        # Map position to data coordinates
        vb = plot_widget.plotItem.vb
        if not plot_widget.sceneBoundingRect().contains(pos):
            hover_label.setText("")
            return

        mouse_point = vb.mapSceneToView(pos)
        x, y = mouse_point.x(), mouse_point.y()

        # Calculate tolerance based on view range
        view_range = vb.viewRange()
        x_range = view_range[0][1] - view_range[0][0]
        y_range = view_range[1][1] - view_range[1][0]
        tolerance = max(x_range, y_range) * 0.02  # 2% of view range

        # Find closest point
        closest_track = None
        closest_distance = float('inf')

        for track, x_data, y_data in plot_items:
            if len(x_data) == 0:
                continue

            # Calculate distances to all points
            distances = np.sqrt((x_data - x)**2 + (y_data - y)**2)
            min_dist = np.min(distances)

            if min_dist < tolerance and min_dist < closest_distance:
                closest_distance = min_dist
                closest_track = track

        if closest_track is not None:
            tracker_name = self.tracker_map.get(closest_track.uuid, 'Unknown')
            hover_label.setText(f"Track: {closest_track.name}  |  Tracker: {tracker_name}")
        else:
            hover_label.setText("")

    def set_tracks(self, tracks: list, tracker_map: dict):
        """
        Update displayed tracks.

        Parameters
        ----------
        tracks : list[Track]
            List of Track objects to display
        tracker_map : dict
            Mapping from track.uuid to tracker name
        """
        self.tracks = tracks
        self.tracker_map = tracker_map

        # Clear cached data
        self._cached_data = {}

        # Update tracks label
        if len(tracks) == 0:
            self.tracks_label.setText("Selected Tracks: None")
        else:
            track_names = [t.name for t in tracks]
            self.tracks_label.setText(f"Selected Tracks: {', '.join(track_names)}")

        # Refresh available axis options based on data
        self._refresh_axis_options()

        # Only update the currently visible plot
        if self.tab_widget.currentIndex() == 0:
            self.update_static_plot()
        else:
            self.update_animated_plot()

    def on_frame_changed(self, frame: int):
        """
        Handle frame change from main viewer.

        Parameters
        ----------
        frame : int
            Current frame number
        """
        # Only update animated plot if it's the active tab
        if self.tab_widget.currentIndex() == 1:
            self.update_animated_plot()

    def _refresh_axis_options(self):
        """Refresh axis combo boxes based on available data"""
        # Build list of available axes for X (includes Frame/Time)
        x_axis_options = ['Frame', 'Row', 'Column']
        # Y-axis excludes Frame and Time (they don't make sense as dependent variables)
        y_axis_options = ['Row', 'Column']

        # Check if any track has time data
        has_time = False
        has_geolocation = False
        has_extraction = False

        for track in self.tracks:
            # Check time
            times = track.get_times()
            if times is not None and not np.all(np.isnat(times)):
                has_time = True

            # Check geolocation
            if hasattr(track.sensor, 'can_geolocate') and track.sensor.can_geolocate():
                has_geolocation = True

            # Check extraction metadata
            if track.extraction_metadata is not None:
                has_extraction = True

        if has_geolocation:
            geo_options = ['ARF Azimuth (rad)', 'ARF Elevation (rad)', 'Latitude', 'Longitude']
            x_axis_options.extend(geo_options)
            y_axis_options.extend(geo_options)

        if has_extraction:
            extraction_options = ['Signal Total', 'Signal Pixels', 'Noise']
            x_axis_options.extend(extraction_options)
            y_axis_options.extend(extraction_options)

        # Update X-axis combo boxes
        for combo in [self.static_x_combo, self.animated_x_combo]:
            combo.blockSignals(True)
            current = combo.currentText()
            combo.clear()
            combo.addItems(x_axis_options)
            # Try to restore previous selection
            idx = combo.findText(current)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            combo.blockSignals(False)

        # Update Y-axis combo boxes
        for combo in [self.static_y_combo, self.animated_y_combo]:
            combo.blockSignals(True)
            current = combo.currentText()
            combo.clear()
            combo.addItems(y_axis_options)
            # Try to restore previous selection
            idx = combo.findText(current)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            combo.blockSignals(False)

        # Set default axes
        if self.static_x_combo.currentText() == '':
            self.static_x_combo.setCurrentText('Frame')
        if self.static_y_combo.currentText() == '':
            self.static_y_combo.setCurrentText('Row')
        if self.animated_x_combo.currentText() == '':
            self.animated_x_combo.setCurrentText('Column')
        if self.animated_y_combo.currentText() == '':
            self.animated_y_combo.setCurrentText('Row')

    def _get_plottable_data(self, track: Track) -> dict:
        """
        Extract all available data arrays from track.

        Parameters
        ----------
        track : Track
            Track to extract data from

        Returns
        -------
        dict
            Dictionary mapping axis names to numpy arrays
        """
        # Check cache
        if track.uuid in self._cached_data:
            return self._cached_data[track.uuid]

        data = {
            'Frame': track.frames.astype(float),
            'Row': track.rows,
            'Column': track.columns,
        }

        # Add times if available
        times = track.get_times()
        if times is not None and not np.all(np.isnat(times)):
            # Convert datetime64 to float (seconds since epoch) for plotting
            data['Time'] = times.astype('datetime64[ns]').astype(np.float64) / 1e9

        # Add geolocation if sensor supports it
        if hasattr(track.sensor, 'can_geolocate') and track.sensor.can_geolocate():
            if isinstance(track.sensor, SampledSensor):
                azimuths = []
                elevations = []
                lats = []
                lons = []

                for i, frame in enumerate(track.frames):
                    row, col = track.rows[i], track.columns[i]

                    # Get ARF angles
                    try:
                        frame_idx = np.where(track.sensor.frames == frame)[0]
                        if len(frame_idx) > 0:
                            frame_idx = frame_idx[0]
                            az_coeffs = track.sensor.poly_pixel_to_arf_azimuth[frame_idx]
                            el_coeffs = track.sensor.poly_pixel_to_arf_elevation[frame_idx]
                            az = evaluate_2d_polynomial(az_coeffs, np.array([col]), np.array([row]))[0]
                            el = evaluate_2d_polynomial(el_coeffs, np.array([col]), np.array([row]))[0]
                            azimuths.append(az)
                            elevations.append(el)
                        else:
                            azimuths.append(np.nan)
                            elevations.append(np.nan)
                    except (IndexError, KeyError):
                        azimuths.append(np.nan)
                        elevations.append(np.nan)

                    # Get geodetic coordinates
                    try:
                        locations = track.sensor.pixel_to_geodetic(frame, np.array([row]), np.array([col]))
                        if locations is not None and len(locations) > 0:
                            lats.append(locations[0].lat.deg)
                            lons.append(locations[0].lon.deg)
                        else:
                            lats.append(np.nan)
                            lons.append(np.nan)
                    except Exception:
                        lats.append(np.nan)
                        lons.append(np.nan)

                data['ARF Azimuth (rad)'] = np.array(azimuths)
                data['ARF Elevation (rad)'] = np.array(elevations)
                data['Latitude'] = np.array(lats)
                data['Longitude'] = np.array(lons)

        # Add extraction metadata if available
        if track.extraction_metadata is not None:
            chips = track.extraction_metadata.get('chips')
            masks = track.extraction_metadata.get('signal_masks')
            noise = track.extraction_metadata.get('noise_stds')

            if chips is not None and masks is not None:
                data['Signal Total'] = np.sum(chips * masks, axis=(1, 2))
                data['Signal Pixels'] = np.sum(masks, axis=(1, 2)).astype(float)
            if noise is not None:
                data['Noise'] = noise

        # Cache the data
        self._cached_data[track.uuid] = data
        return data

    def _assign_colors_and_symbols(self, color_by='track'):
        """
        Assign colors and symbols based on coloring mode.

        Parameters
        ----------
        color_by : str
            'track' or 'tracker'

        Returns
        -------
        dict
            Mapping from track.uuid to {'color': str, 'symbol': str}
        """
        assignments = {}

        if color_by == 'track':
            # Each track gets unique color, each tracker gets unique symbol
            tracker_symbols = {}
            tracker_names = list(set(self.tracker_map.values()))
            for i, tracker_name in enumerate(tracker_names):
                tracker_symbols[tracker_name] = self.SYMBOLS[i % len(self.SYMBOLS)]

            for i, track in enumerate(self.tracks):
                tracker_name = self.tracker_map.get(track.uuid, 'Unknown')
                assignments[track.uuid] = {
                    'color': self.COLORS[i % len(self.COLORS)],
                    'symbol': tracker_symbols.get(tracker_name, 'o'),
                    'name': f"{track.name} ({tracker_name})"
                }
        else:  # color_by == 'tracker'
            # Each tracker gets unique color, each track within tracker gets unique symbol
            tracker_colors = {}
            tracker_track_indices = {}  # tracker_name -> count of tracks seen
            tracker_names = list(set(self.tracker_map.values()))

            for i, tracker_name in enumerate(tracker_names):
                tracker_colors[tracker_name] = self.COLORS[i % len(self.COLORS)]
                tracker_track_indices[tracker_name] = 0

            for track in self.tracks:
                tracker_name = self.tracker_map.get(track.uuid, 'Unknown')
                track_idx = tracker_track_indices.get(tracker_name, 0)
                tracker_track_indices[tracker_name] = track_idx + 1

                assignments[track.uuid] = {
                    'color': tracker_colors.get(tracker_name, self.COLORS[0]),
                    'symbol': self.SYMBOLS[track_idx % len(self.SYMBOLS)],
                    'name': f"{track.name} ({tracker_name})"
                }

        return assignments

    def update_static_plot(self):
        """Update the static plot"""
        self.static_plot.clear()
        self._static_plot_items = []

        # Recreate legend if it was enabled
        if self.static_show_legend.isChecked():
            self._static_legend = self.static_plot.addLegend()

        if len(self.tracks) == 0:
            return

        x_axis = self.static_x_combo.currentText()
        y_axis = self.static_y_combo.currentText()

        if not x_axis or not y_axis:
            return

        color_by = 'track' if self.static_color_by_track.isChecked() else 'tracker'
        assignments = self._assign_colors_and_symbols(color_by)

        for track in self.tracks:
            data = self._get_plottable_data(track)

            if x_axis not in data or y_axis not in data:
                continue

            x_data = data[x_axis]
            y_data = data[y_axis]

            # Apply symlog transform if enabled
            if self.static_symlog_y.isChecked():
                y_data = self._symlog(y_data)

            assignment = assignments.get(track.uuid, {'color': 'g', 'symbol': 'o', 'name': track.name})

            # Plot scatter with lines
            name = assignment['name'] if self.static_show_legend.isChecked() else None
            self.static_plot.plot(
                x_data, y_data,
                pen=pg.mkPen(assignment['color'], width=2),
                symbol=assignment['symbol'],
                symbolPen=pg.mkPen(assignment['color']),
                symbolBrush=pg.mkBrush(assignment['color']),
                symbolSize=8,
                name=name
            )

            # Store for hover detection
            self._static_plot_items.append((track, x_data, y_data))

        # Set axis labels
        self.static_plot.setLabel('bottom', x_axis)
        y_label = f"{y_axis} (symlog)" if self.static_symlog_y.isChecked() else y_axis
        self.static_plot.setLabel('left', y_label)

    def update_animated_plot(self):
        """Update the animated plot based on current frame"""
        self.animated_plot.clear()
        self._animated_plot_items = []

        # Recreate legend if it was enabled
        if self.animated_show_legend.isChecked():
            self._animated_legend = self.animated_plot.addLegend()

        if len(self.tracks) == 0:
            return

        x_axis = self.animated_x_combo.currentText()
        y_axis = self.animated_y_combo.currentText()

        if not x_axis or not y_axis:
            return

        current_frame = self.viewer.current_frame_number if self.viewer else 0

        color_by = 'track' if self.animated_color_by_track.isChecked() else 'tracker'
        assignments = self._assign_colors_and_symbols(color_by)

        for track in self.tracks:
            data = self._get_plottable_data(track)

            if x_axis not in data or y_axis not in data:
                continue

            x_data = data[x_axis]
            y_data = data[y_axis]
            frames = track.frames

            # Filter data based on display mode
            if self.up_to_frame_radio.isChecked():
                # Show all data up to current frame
                mask = frames <= current_frame
            else:
                # Show only last N frames
                tail_length = self.tail_length_spin.value()
                mask = (frames <= current_frame) & (frames > current_frame - tail_length)

            if not np.any(mask):
                continue

            x_filtered = x_data[mask]
            y_filtered = y_data[mask]

            # Apply symlog transform if enabled
            use_symlog = self.animated_symlog_y.isChecked()
            if use_symlog:
                y_filtered = self._symlog(y_filtered)

            assignment = assignments.get(track.uuid, {'color': 'g', 'symbol': 'o', 'name': track.name})

            # Plot scatter with lines
            name = assignment['name'] if self.animated_show_legend.isChecked() else None
            self.animated_plot.plot(
                x_filtered, y_filtered,
                pen=pg.mkPen(assignment['color'], width=2),
                symbol=assignment['symbol'],
                symbolPen=pg.mkPen(assignment['color']),
                symbolBrush=pg.mkBrush(assignment['color']),
                symbolSize=8,
                name=name
            )

            # Store for hover detection (filtered data)
            self._animated_plot_items.append((track, x_filtered, y_filtered))

            # Highlight current frame position with a larger marker
            current_idx = np.where(frames == current_frame)[0]
            if len(current_idx) > 0:
                idx = current_idx[0]
                y_current = self._symlog(np.array([y_data[idx]]))[0] if use_symlog else y_data[idx]
                self.animated_plot.plot(
                    [x_data[idx]], [y_current],
                    pen=None,
                    symbol=assignment['symbol'],
                    symbolPen=pg.mkPen('w', width=2),
                    symbolBrush=pg.mkBrush(assignment['color']),
                    symbolSize=14,
                )

        # Set axis labels
        self.animated_plot.setLabel('bottom', x_axis)
        y_label = f"{y_axis} (symlog)" if self.animated_symlog_y.isChecked() else y_axis
        self.animated_plot.setLabel('left', y_label)

    def export_data(self):
        """Export currently plotted data to CSV"""
        if len(self.tracks) == 0:
            QMessageBox.warning(self, "No Data", "No tracks selected to export.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Data", "", "CSV Files (*.csv);;All Files (*)"
        )

        if not file_path:
            return

        try:
            import pandas as pd

            # Collect all data
            rows = []
            for track in self.tracks:
                data = self._get_plottable_data(track)
                tracker_name = self.tracker_map.get(track.uuid, 'Unknown')

                for i in range(len(track.frames)):
                    row = {
                        'Tracker': tracker_name,
                        'Track': track.name,
                    }
                    for key, values in data.items():
                        if i < len(values):
                            row[key] = values[i]
                    rows.append(row)

            df = pd.DataFrame(rows)
            df.to_csv(file_path, index=False)
            QMessageBox.information(self, "Export Complete", f"Data exported to {file_path}")

        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export data: {e}")

    def export_plot(self):
        """Export current plot to image file"""
        # Determine which plot is currently visible
        current_tab = self.tab_widget.currentIndex()
        plot_widget = self.static_plot if current_tab == 0 else self.animated_plot

        file_path, selected_filter = QFileDialog.getSaveFileName(
            self, "Export Plot", "",
            "PNG Files (*.png);;SVG Files (*.svg);;All Files (*)"
        )

        if not file_path:
            return

        try:
            # Use pyqtgraph's export functionality
            exporter = pg.exporters.ImageExporter(plot_widget.plotItem)

            if file_path.lower().endswith('.svg'):
                exporter = pg.exporters.SVGExporter(plot_widget.plotItem)

            exporter.export(file_path)
            QMessageBox.information(self, "Export Complete", f"Plot exported to {file_path}")

        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export plot: {e}")

    def closeEvent(self, event):
        """Handle window close event"""
        # Clear references
        self.tracks = []
        self.tracker_map = {}
        self._cached_data = {}
        self._static_plot_items = []
        self._animated_plot_items = []
        super().closeEvent(event)
