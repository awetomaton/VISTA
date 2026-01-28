"""Track plot window for visualizing track point-by-point data"""
import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QRadioButton, QSpinBox, QVBoxLayout, QWidget
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
        self._plot_items = []  # List of (track, PlotDataItem)

        self.setWindowTitle("Track Details Plot")
        self.setWindowFlags(Qt.WindowType.Window)
        self.resize(800, 600)

        self.init_ui()

        # Connect to view range changed for dynamic symlog tick updates
        self.plot.getViewBox().sigRangeChanged.connect(self._on_range_changed)

    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()

        # Selected tracks display
        self.tracks_label = QLabel("Selected Tracks: None")
        self.tracks_label.setWordWrap(True)
        layout.addWidget(self.tracks_label)

        # Axis selection
        axis_layout = QHBoxLayout()
        axis_layout.addWidget(QLabel("X-Axis:"))
        self.x_combo = QComboBox()
        self.x_combo.setMinimumWidth(150)
        self.x_combo.currentIndexChanged.connect(self._on_settings_changed)
        axis_layout.addWidget(self.x_combo)

        axis_layout.addWidget(QLabel("Y-Axis:"))
        self.y_combo = QComboBox()
        self.y_combo.setMinimumWidth(150)
        self.y_combo.currentIndexChanged.connect(self._on_settings_changed)
        axis_layout.addWidget(self.y_combo)

        axis_layout.addStretch()
        layout.addLayout(axis_layout)

        # Color mode and legend checkbox
        color_layout = QHBoxLayout()
        color_layout.addWidget(QLabel("Color By:"))
        self.color_by_track = QRadioButton("Track")
        self.color_by_track.setChecked(True)
        self.color_by_tracker = QRadioButton("Tracker")
        self.color_group = QButtonGroup()
        self.color_group.addButton(self.color_by_track, 0)
        self.color_group.addButton(self.color_by_tracker, 1)
        self.color_group.buttonClicked.connect(self._on_settings_changed)
        color_layout.addWidget(self.color_by_track)
        color_layout.addWidget(self.color_by_tracker)

        # Show legend checkbox
        self.show_legend = QCheckBox("Show Legend")
        self.show_legend.setChecked(False)
        self.show_legend.stateChanged.connect(self._on_legend_toggled)
        color_layout.addWidget(self.show_legend)

        # Symmetric log Y-axis checkbox
        self.symlog_y = QCheckBox("Symlog Y")
        self.symlog_y.setToolTip("Use symmetric logarithmic scale for Y-axis\n(handles both positive and negative values)")
        self.symlog_y.setChecked(False)
        self.symlog_y.stateChanged.connect(self._on_settings_changed)
        color_layout.addWidget(self.symlog_y)

        color_layout.addStretch()
        layout.addLayout(color_layout)

        # Display mode selection
        display_mode_layout = QHBoxLayout()

        # Show complete plot checkbox
        self.show_complete_plot = QCheckBox("Show Complete Plot")
        self.show_complete_plot.setToolTip("Display all data points across all frames")
        self.show_complete_plot.setChecked(False)
        self.show_complete_plot.stateChanged.connect(self._on_display_mode_changed)
        display_mode_layout.addWidget(self.show_complete_plot)

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
        self.tail_length_spin.valueChanged.connect(self._on_settings_changed)
        display_mode_layout.addWidget(self.tail_length_spin)
        display_mode_layout.addStretch()
        layout.addLayout(display_mode_layout)

        # Plot widget
        self.plot = pg.PlotWidget()
        self.plot.showGrid(x=True, y=True)
        self._legend = None  # Will be created on demand
        layout.addWidget(self.plot)

        # Hover info label
        self.hover_label = QLabel("")
        self.hover_label.setStyleSheet("color: gray; font-style: italic;")
        layout.addWidget(self.hover_label)

        # Connect mouse move for hover detection
        self.plot.scene().sigMouseMoved.connect(self._on_mouse_moved)

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

    def _on_settings_changed(self):
        """Handle plot settings change"""
        self.update_plot()

    def _on_display_mode_changed(self):
        """Handle display mode change"""
        show_complete = self.show_complete_plot.isChecked()

        # Disable animation controls when showing complete plot
        self.up_to_frame_radio.setEnabled(not show_complete)
        self.tail_length_radio.setEnabled(not show_complete)
        self.tail_length_spin.setEnabled(not show_complete and self.tail_length_radio.isChecked())

        self._on_settings_changed()

    def _on_legend_toggled(self, state):
        """Toggle plot legend visibility"""
        if state == Qt.CheckState.Checked.value:
            if self._legend is None:
                self._legend = self.plot.addLegend()
            self.update_plot()  # Redraw to populate legend
        else:
            if self._legend is not None:
                # Remove legend from scene properly
                self._legend.scene().removeItem(self._legend)
                self.plot.plotItem.legend = None
                self._legend = None
                self.update_plot()  # Redraw without legend

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

    def _inverse_symlog(self, y):
        """
        Inverse of symlog transform.

        inverse_symlog(y) = sign(y) * (10^|y| - 1)

        Parameters
        ----------
        y : float or np.ndarray
            Value in symlog space

        Returns
        -------
        float or np.ndarray
            Value in original space
        """
        # Clamp to avoid overflow (10^308 is near float max)
        y_clamped = np.clip(y, -300, 300)
        return np.sign(y_clamped) * (10 ** np.abs(y_clamped) - 1)

    def _get_symlog_ticks(self, view_y_min, view_y_max):
        """
        Generate tick positions and labels for symlog Y-axis.

        Dynamically generates ticks based on the visible range by creating
        evenly-spaced positions in symlog space and converting them to
        "nice" values in original space. Tick density continuously scales
        with zoom level.

        Parameters
        ----------
        view_y_min : float
            Minimum visible Y value (in symlog space)
        view_y_max : float
            Maximum visible Y value (in symlog space)

        Returns
        -------
        list
            List of (position, label) tuples for axis ticks
        """
        symlog_min = view_y_min
        symlog_max = view_y_max

        symlog_span = symlog_max - symlog_min
        if symlog_span <= 0:
            return [(0.0, "0")]

        # Convert visible symlog range to original space for granularity calculation
        visible_orig_min = float(self._inverse_symlog(symlog_min))
        visible_orig_max = float(self._inverse_symlog(symlog_max))
        visible_range_orig = (visible_orig_min, visible_orig_max)

        # Target approximately 8 ticks, regardless of zoom level
        target_ticks = 8
        tick_spacing_symlog = symlog_span / target_ticks

        # Generate evenly-spaced positions in symlog space
        ticks = []

        # Start from a position just below the visible minimum
        start_pos = symlog_min - tick_spacing_symlog
        end_pos = symlog_max + tick_spacing_symlog

        pos = start_pos
        while pos <= end_pos:
            # Convert position from symlog space to original value
            orig_val = float(self._inverse_symlog(pos))

            # Round to a "nice" value based on the visible range
            nice_val = self._round_to_nice(orig_val, tick_spacing_symlog, visible_range_orig)

            # Skip if rounding returned 0 for non-zero input (indicates error)
            if nice_val == 0 and abs(orig_val) > 1e-10:
                pos += tick_spacing_symlog
                continue

            # Get the actual symlog position for this nice value
            nice_pos = float(self._symlog(np.array([nice_val]))[0])

            # Only add if within visible range (with small margin)
            margin = tick_spacing_symlog * 0.5
            if symlog_min - margin <= nice_pos <= symlog_max + margin:
                label = self._format_tick_label(nice_val)
                ticks.append((nice_pos, label))

            pos += tick_spacing_symlog

        # Always try to include 0 if it's in or near the visible range
        zero_margin = tick_spacing_symlog
        if symlog_min - zero_margin <= 0 <= symlog_max + zero_margin:
            # Check if 0 is already in ticks (close enough)
            has_zero = any(abs(t[0]) < tick_spacing_symlog * 0.3 for t in ticks)
            if not has_zero:
                ticks.append((0.0, "0"))

        # Remove duplicates (same position or very close positions)
        ticks = self._dedupe_ticks(ticks, tick_spacing_symlog * 0.3)

        # Sort by position
        ticks.sort(key=lambda x: x[0])

        return ticks

    def _round_to_nice(self, value, symlog_spacing, visible_range_orig=None):
        """
        Round a value to a "nice" number for tick labels.

        The niceness depends on the current zoom level (symlog_spacing) and
        the visible range in original space.

        Parameters
        ----------
        value : float
            Value to round
        symlog_spacing : float
            Current tick spacing in symlog space (indicates zoom level)
        visible_range_orig : tuple, optional
            (min, max) of the visible range in original space, used to
            determine appropriate rounding granularity

        Returns
        -------
        float
            Rounded "nice" value
        """
        if value == 0:
            return 0.0

        sign = np.sign(value)
        abs_val = abs(value)

        if abs_val < 1e-10:
            return 0.0

        # Determine the order of magnitude, with protection against log of 0
        try:
            log_val = np.log10(abs_val)
            if not np.isfinite(log_val):
                return 0.0
            magnitude = 10 ** np.floor(log_val)
        except (ValueError, FloatingPointError):
            return 0.0

        if magnitude == 0 or not np.isfinite(magnitude):
            return 0.0

        # Normalized value (between 1 and 10)
        normalized = abs_val / magnitude

        # Determine appropriate rounding granularity based on both symlog_spacing
        # and the visible range in original space
        if visible_range_orig is not None:
            orig_min, orig_max = visible_range_orig
            orig_span = abs(orig_max - orig_min)
            # Use the span to determine granularity
            # If viewing a small span (e.g., 10-15), we want integer ticks
            if orig_span > 0:
                # Target ~8 ticks, so each tick represents orig_span/8 in original space
                tick_step = orig_span / 8
                # Determine rounding step based on tick_step magnitude
                if tick_step < 0.5:
                    # Very fine - round to 0.1
                    rounding_step = 0.1
                elif tick_step < 2:
                    # Fine - round to 0.5 or 1
                    rounding_step = 0.5 if tick_step < 1 else 1
                elif tick_step < 10:
                    # Medium - round to integers
                    rounding_step = 1
                elif tick_step < 50:
                    # Coarser
                    rounding_step = 5
                else:
                    # Use magnitude-based rounding
                    rounding_step = None
            else:
                rounding_step = None
        else:
            rounding_step = None

        # If we have a specific rounding step, use it directly
        if rounding_step is not None and rounding_step > 0:
            rounded_val = round(abs_val / rounding_step) * rounding_step
            return sign * rounded_val

        # Fallback: magnitude-based rounding with nice factors
        # Choose rounding granularity based on zoom level
        if symlog_spacing < 0.05:
            # Very zoomed in - every 0.1 of normalized
            nice_factors = [i / 10 for i in range(1, 101)]  # 0.1 to 10.0
        elif symlog_spacing < 0.1:
            # Zoomed in - every 0.5 of normalized
            nice_factors = [i / 2 for i in range(1, 21)]  # 0.5 to 10.0
        elif symlog_spacing < 0.3:
            # Moderately zoomed - integers
            nice_factors = list(range(1, 11))  # 1 to 10
        elif symlog_spacing < 0.5:
            # Less zoomed - 1-2-5 pattern
            nice_factors = [1, 2, 5, 10]
        else:
            # Zoomed out - just powers of 10
            nice_factors = [1, 10]

        # Find the closest nice factor
        closest = min(nice_factors, key=lambda f: abs(normalized - f))

        return sign * closest * magnitude

    def _dedupe_ticks(self, ticks, min_spacing):
        """
        Remove duplicate ticks that are too close together.

        Parameters
        ----------
        ticks : list
            List of (position, label) tuples
        min_spacing : float
            Minimum spacing between ticks in symlog space

        Returns
        -------
        list
            Deduplicated list of ticks
        """
        if len(ticks) <= 1:
            return ticks

        # Sort by position
        sorted_ticks = sorted(ticks, key=lambda x: x[0])

        result = [sorted_ticks[0]]
        for tick in sorted_ticks[1:]:
            # Only add if far enough from the last added tick
            if abs(tick[0] - result[-1][0]) >= min_spacing:
                result.append(tick)

        return result

    def _format_tick_label(self, val):
        """
        Format a tick value as a label string.

        Parameters
        ----------
        val : float
            Value to format

        Returns
        -------
        str
            Formatted label
        """
        abs_val = abs(val)
        if abs_val == 0:
            return "0"
        elif abs_val >= 10000:
            return f"{val:.0e}"
        elif abs_val >= 100:
            return f"{val:.0f}"
        elif abs_val >= 1:
            return f"{val:g}"
        elif abs_val >= 0.01:
            return f"{val:.2g}"
        else:
            return f"{val:.1e}"

    def _apply_symlog_ticks(self, view_range):
        """
        Apply symlog tick marks to the plot's Y-axis.

        Parameters
        ----------
        view_range : tuple
            (view_y_min, view_y_max) in symlog space
        """
        view_y_min, view_y_max = view_range
        ticks = self._get_symlog_ticks(view_y_min, view_y_max)
        # Format for pyqtgraph: list of lists, where each inner list is for a tick level
        # Level 0 = major ticks, level 1 = minor ticks (empty)
        axis = self.plot.getAxis('left')
        axis.setTicks([ticks, []])

    def _clear_custom_ticks(self):
        """Clear custom tick marks from the plot's Y-axis."""
        axis = self.plot.getAxis('left')
        axis.setTicks(None)

    def _on_range_changed(self, _viewbox, ranges):
        """Handle plot view range change for dynamic symlog ticks."""
        if not self.symlog_y.isChecked():
            return
        # ranges is [[x_min, x_max], [y_min, y_max]]
        if len(ranges) >= 2:
            y_range = ranges[1]
            self._apply_symlog_ticks(y_range)

    def _on_mouse_moved(self, pos):
        """Handle mouse move for hover detection"""
        if len(self._plot_items) == 0:
            self.hover_label.setText("")
            return

        # Map position to data coordinates
        vb = self.plot.plotItem.vb
        if not self.plot.sceneBoundingRect().contains(pos):
            self.hover_label.setText("")
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

        for track, x_data, y_data in self._plot_items:
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
            self.hover_label.setText(f"Track: {closest_track.name}  |  Tracker: {tracker_name}")
        else:
            self.hover_label.setText("")

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

        self.update_plot()

    def on_frame_changed(self, _frame: int):
        """
        Handle frame change from main viewer.

        Parameters
        ----------
        _frame : int
            Current frame number (unused, frame is read from viewer)
        """
        self.update_plot()

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
        has_uncertainty = False

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

            # Check uncertainty
            if track.has_uncertainty():
                has_uncertainty = True

        if has_geolocation:
            geo_options = ['ARF Azimuth (rad)', 'ARF Elevation (rad)', 'Latitude', 'Longitude']
            x_axis_options.extend(geo_options)
            y_axis_options.extend(geo_options)

        if has_extraction:
            extraction_options = ['Signal Total', 'Signal Pixels', 'Noise']
            x_axis_options.extend(extraction_options)
            y_axis_options.extend(extraction_options)

        if has_uncertainty:
            uncertainty_options = ['Uncertainty Radius']
            x_axis_options.extend(uncertainty_options)
            y_axis_options.extend(uncertainty_options)

        # Update X-axis combo box
        self.x_combo.blockSignals(True)
        current_x = self.x_combo.currentText()
        self.x_combo.clear()
        self.x_combo.addItems(x_axis_options)
        # Try to restore previous selection
        idx = self.x_combo.findText(current_x)
        if idx >= 0:
            self.x_combo.setCurrentIndex(idx)
        self.x_combo.blockSignals(False)

        # Update Y-axis combo box
        self.y_combo.blockSignals(True)
        current_y = self.y_combo.currentText()
        self.y_combo.clear()
        self.y_combo.addItems(y_axis_options)
        # Try to restore previous selection
        idx = self.y_combo.findText(current_y)
        if idx >= 0:
            self.y_combo.setCurrentIndex(idx)
        self.y_combo.blockSignals(False)

        # Set default axes
        if self.x_combo.currentText() == '':
            self.x_combo.setCurrentText('Column')
        if self.y_combo.currentText() == '':
            self.y_combo.setCurrentText('Row')

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

        # Add uncertainty radius if available
        uncertainty_radius = track.get_uncertainty_radius()
        if uncertainty_radius is not None:
            data['Uncertainty Radius'] = uncertainty_radius

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

    def update_plot(self):
        """Update the plot based on current settings and frame"""
        self.plot.clear()
        self._plot_items = []

        # Recreate legend if it was enabled
        if self.show_legend.isChecked():
            self._legend = self.plot.addLegend()

        if len(self.tracks) == 0:
            return

        x_axis = self.x_combo.currentText()
        y_axis = self.y_combo.currentText()

        if not x_axis or not y_axis:
            return

        current_frame = self.viewer.current_frame_number if self.viewer else 0
        show_complete = self.show_complete_plot.isChecked()

        color_by = 'track' if self.color_by_track.isChecked() else 'tracker'
        assignments = self._assign_colors_and_symbols(color_by)

        use_symlog = self.symlog_y.isChecked()

        for track in self.tracks:
            data = self._get_plottable_data(track)

            if x_axis not in data or y_axis not in data:
                continue

            x_data = data[x_axis]
            y_data_original = data[y_axis]
            frames = track.frames

            # Filter data based on display mode
            if show_complete:
                # Show all data points
                mask = np.ones(len(frames), dtype=bool)
            elif self.up_to_frame_radio.isChecked():
                # Show all data up to current frame
                mask = frames <= current_frame
            else:
                # Show only last N frames
                tail_length = self.tail_length_spin.value()
                mask = (frames <= current_frame) & (frames > current_frame - tail_length)

            if not np.any(mask):
                continue

            x_filtered = x_data[mask]
            y_filtered_original = y_data_original[mask]

            # Apply symlog transform if enabled
            y_filtered = self._symlog(y_filtered_original) if use_symlog else y_filtered_original

            assignment = assignments.get(track.uuid, {'color': 'g', 'symbol': 'o', 'name': track.name})

            # Plot scatter with lines
            name = assignment['name'] if self.show_legend.isChecked() else None
            self.plot.plot(
                x_filtered, y_filtered,
                pen=pg.mkPen(assignment['color'], width=2),
                symbol=assignment['symbol'],
                symbolPen=pg.mkPen(assignment['color']),
                symbolBrush=pg.mkBrush(assignment['color']),
                symbolSize=8,
                name=name
            )

            # Store for hover detection (filtered data)
            self._plot_items.append((track, x_filtered, y_filtered))

            # Highlight current frame position with a larger marker
            current_idx = np.where(frames == current_frame)[0]
            if len(current_idx) > 0:
                idx = current_idx[0]
                y_current = self._symlog(np.array([y_data_original[idx]]))[0] if use_symlog else y_data_original[idx]
                self.plot.plot(
                    [x_data[idx]], [y_current],
                    pen=None,
                    symbol=assignment['symbol'],
                    symbolPen=pg.mkPen('w', width=2),
                    symbolBrush=pg.mkBrush(assignment['color']),
                    symbolSize=14,
                )

        # Set axis labels
        self.plot.setLabel('bottom', x_axis)
        y_label = f"{y_axis} (symlog)" if use_symlog else y_axis
        self.plot.setLabel('left', y_label)

        # Apply custom symlog ticks or clear them
        if use_symlog:
            # Get the current view range from the viewbox (in symlog space)
            view_range = self.plot.getViewBox().viewRange()
            y_range = view_range[1]  # [y_min, y_max] in symlog space
            self._apply_symlog_ticks(y_range)
        else:
            self._clear_custom_ticks()

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
        file_path, selected_filter = QFileDialog.getSaveFileName(
            self, "Export Plot", "",
            "PNG Files (*.png);;SVG Files (*.svg);;All Files (*)"
        )

        if not file_path:
            return

        try:
            # Use pyqtgraph's export functionality
            exporter = pg.exporters.ImageExporter(self.plot.plotItem)

            if file_path.lower().endswith('.svg'):
                exporter = pg.exporters.SVGExporter(self.plot.plotItem)

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
        self._plot_items = []
        super().closeEvent(event)
