Object Tracking
===============

This guide covers creating, managing, and analyzing object tracks in VISTA. Tracks represent object trajectories across 
multiple frames, linking detections or manual observations to form continuous motion paths.

Overview
--------

What are Tracks?
~~~~~~~~~~~~~~~~

A **Track** represents a single object's trajectory across multiple frames. While detections identify objects at 
specific points in time, tracks link these observations to form continuous motion paths. Each track contains:

- **Temporal coordinates**: Frame numbers or timestamps
- **Spatial coordinates**: Pixel positions (row/column) or geodetic coordinates (lat/lon/alt)
- **Visualization properties**: Color, marker style, line width, tail length
- **Motion metadata**: Velocity estimates, quality metrics, length
- **Analysis data**: Optional extraction metadata (image chips, signal masks)

Tracks differ from detections in that they:

- Represent motion over time rather than static observations
- Support gap interpolation and smoothing operations
- Track single objects rather than multiple independent observations
- Enable trajectory analysis and prediction

Tracks in VISTA
~~~~~~~~~~~~~~~

VISTA provides two ways to create tracks:

1. **Manual track creation**: Click points across frames to manually define trajectories
2. **Automated tracking**: Use tracking algorithms to link detections into tracks

The application stores tracks in a hierarchical structure where each Sensor can have multiple Trackers, and each Tracker contains multiple Tracks. This organization allows you to:

- Compare results from different tracking algorithms
- Maintain tracks from different sensors separately
- Export and import tracks in CSV or HDF5 format
- Apply visualization and analysis operations to entire trackers

.. _manual-track-creation:

Manual Track Creation
---------------------

Creating Tracks Manually
~~~~~~~~~~~~~~~~~~~~~~~~

To create a track manually by clicking points across frames:

1. Open the **Data Manager** panel (Ctrl+D or View menu)
2. Select the **Tracks** tab
3. Select a Sensor from the dropdown
4. Click **Manual Track** button
5. Navigate through frames and click to add track points:
   - Left-click to add a point at the clicked location
   - Re-click a point to remove it
6. Uncheck the **Manual Track** tool to complete the track.

.. image:: /_static/images/user_guide_tracks_create.gif
   :alt: Create track
   :align: center

.. tip::
   Use keyboard shortcuts for efficient manual tracking:

   - Use left/right or A/D keys to navigate frames
   - Click near expected object locations
   - Use the zoom tool (mouse wheel) for precise placement
   - Click on a point again to delete it

Loading Tracks from CSV
~~~~~~~~~~~~~~~~~~~~~~~~

To load tracks from a CSV file:

1. In the Tracks panel, select a Sensor
2. Click **Load Tracks** button
3. Browse to your CSV file
4. Tracks are loaded and added to the selected Sensor

See :ref:`tracks-csv-format` for CSV format details.

.. _tracking-algorithms:

Tracking Algorithms
-------------------

VISTA provides four tracking algorithms for automatically linking detections into tracks. Access these through 
**Algorithms > Tracking** in the main menu.

.. image:: /_static/images/user_guide_tracks_trackers.gif
   :alt: Run trackers
   :align: center

.. _simple-tracker:

Simple Tracker
~~~~~~~~~~~~~~

The **Simple Tracker** is a nearest-neighbor tracker that uses frame-to-frame association with velocity prediction. It's 
the easiest algorithm to use and requires minimal configuration.

**How it Works**

1. Associates detections between consecutive frames based on proximity
2. Uses linear velocity prediction for position estimates
3. Creates new tracks for unassociated detections
4. Deletes tracks after too many consecutive missed detections
5. Automatically adapts search radius based on detection density

**Parameters**

- **Tracker Name**: Name for the output tracker
- **Input Detectors**: Select which detectors to use as input
- **Max Search Radius**: Maximum distance (pixels) to search for associations. If not provided, automatically computed from detection statistics
- **Max Age**: Maximum consecutive frames without detection before track deletion. If not provided, automatically computed from frame gaps
- **Min Track Length**: Minimum number of detections required for a valid track (default: 5)

**When to Use**

- Fast-moving objects with consistent motion
- Scenes with low to moderate detection density
- When you want automatic parameter adaptation
- As a baseline for comparison with more sophisticated algorithms

**Example Usage**

.. code-block:: python

   from vista.algorithms.trackers.simple_tracker import run_simple_tracker

   config = {
       'tracker_name': 'Simple Tracker',
       'max_search_radius': 20.0,      # Optional: auto-computed if not provided
       'max_age': 5,                    # Optional: auto-computed if not provided
       'min_track_length': 5
   }

   # Run tracker on detectors
   track_data_list = run_simple_tracker(detectors, config)

.. _kalman-tracker:

Kalman Tracker
~~~~~~~~~~~~~~

The **Kalman Tracker** uses a constant velocity Kalman filter for state estimation, providing better prediction in the 
presence of measurement noise.

**How it Works**

1. Maintains state estimate (position + velocity) with uncertainty covariance
2. Predicts future positions using constant velocity motion model
3. Associates detections using Mahalanobis distance (accounts for uncertainty)
4. Updates state estimates when detections are associated
5. Uses tentative track confirmation based on detection rate

**Parameters**

- **Tracker Name**: Name for the output tracker
- **Input Detectors**: Select which detectors to use as input
- **Process Noise**: Process noise parameter for motion model (default: 1.0). Higher values allow more velocity variation
- **Measurement Noise**: Measurement noise covariance (default: 1.0). Higher values indicate less trust in detection positions
- **Gating Distance**: Mahalanobis distance threshold for association (default: 5.0). Larger values allow more distant associations
- **Min Detections**: Minimum detections before track confirmation (default: 3)
- **Delete Threshold**: Covariance trace threshold for track deletion (default: 100.0). Tracks with high uncertainty are deleted

**When to Use**

- Noisy detection positions
- Objects with relatively constant velocity
- Scenes where prediction quality matters
- When you need probabilistic state estimation

**Example Usage**

.. code-block:: python

   from vista.algorithms.trackers.kalman_tracker import run_kalman_tracker

   config = {
       'tracker_name': 'Kalman Tracker',
       'process_noise': 1.0,
       'measurement_noise': 1.0,
       'gating_distance': 5.0,
       'min_detections': 3,
       'delete_threshold': 100.0
   }

   track_data_list = run_kalman_tracker(detectors, config)

.. _network-flow-tracker:

Network Flow Tracker
~~~~~~~~~~~~~~~~~~~~

The **Network Flow Tracker** formulates tracking as a minimum-cost flow optimization problem, finding globally optimal 
track assignments rather than greedy frame-to-frame associations.

**How it Works**

1. Builds a graph where nodes are detections and edges represent possible associations
2. Assigns costs to edges based on distance, smoothness, and temporal gaps
3. Adds entrance/exit costs to control track initiation/termination
4. Uses Bellman-Ford algorithm to find minimum-cost flow from source to sink
5. Reconstructs tracks from flow solution

**Key Features**

- **Negative link costs** incentivize longer tracks over many short tracks
- **Smoothness penalties** encourage constant-velocity motion
- **Global optimization** finds better solutions than greedy association
- **Gap bridging** can link detections across multiple frames

**Parameters**

- **Tracker Name**: Name for the output tracker
- **Input Detectors**: Select which detectors to use as input
- **Max Gap**: Maximum frame gap to search for associations (default: 5)
- **Max Distance**: Maximum spatial distance for associations (default: 50.0 pixels)
- **Entrance Cost**: Cost for starting a new track (default: 50.0). Higher values prefer longer tracks
- **Exit Cost**: Cost for ending a track (default: 50.0). Higher values prefer longer tracks
- **Min Track Length**: Minimum detections for a valid track (default: 3)

**When to Use**

- Complex scenarios with occlusions or detection gaps
- When global optimization is preferred over local greedy decisions
- Scenarios where you want to minimize fragmented tracks
- When track smoothness is important

**Example Usage**

.. code-block:: python

   from vista.algorithms.trackers.network_flow_tracker import run_network_flow_tracker

   config = {
       'tracker_name': 'Network Flow',
       'max_gap': 5,
       'max_distance': 50.0,
       'entrance_cost': 50.0,
       'exit_cost': 50.0,
       'min_track_length': 3
   }

   track_data_list = run_network_flow_tracker(detectors, config)

.. _tracklet-tracker:

Tracklet Tracker
~~~~~~~~~~~~~~~~

The **Tracklet Tracker** uses a two-stage hierarchical approach optimized for high false alarm scenarios. It first forms 
high-confidence "tracklets" with strict criteria, then links tracklets using global optimization.

**How it Works**

**Stage 1: Tracklet Formation**

1. Associates detections using strict criteria (small search radius, velocity consistency)
2. Implements "M out of N" logic (allows small detection gaps)
3. Filters tracklets by detection rate and quality score
4. Only retains high-confidence trajectory segments

**Stage 2: Tracklet Linking**

1. Extrapolates tracklets forward/backward in time
2. Scores potential links based on position and velocity consistency
3. Uses Hungarian algorithm for optimal non-overlapping links
4. Combines linked tracklets into final tracks

**Parameters**

- **Tracker Name**: Name for the output tracker
- **Input Detectors**: Select which detectors to use as input
- **Initial Search Radius**: Max distance for tracklet formation (default: 10.0 pixels). Keep small to avoid false associations
- **Max Velocity Change**: Max velocity change for tracklet formation (default: 5.0 pixels/frame). Enforces smooth motion
- **Min Tracklet Length**: Minimum detections for valid tracklet (default: 3)
- **Max Consecutive Misses**: Max consecutive missed detections in Stage 1 (default: 2)
- **Min Detection Rate**: Minimum detection rate (hits/age) for tracklets (default: 0.6)
- **Max Linking Gap**: Maximum frame gap to link tracklets (default: 10)
- **Linking Search Radius**: Max distance for tracklet linking (default: 30.0 pixels)
- **Smoothness Weight**: Weight for smoothness in linking cost (default: 1.0)
- **Min Track Length**: Minimum detections for final track (default: 5)

**When to Use**

- **High false alarm scenarios** (100:1 false alarm ratio or higher)
- Real targets with smooth, consistent motion
- When you want to filter out spurious detections early
- Scenarios where tracklet-based reasoning is beneficial

**Example Usage**

.. code-block:: python

   from vista.algorithms.trackers.tracklet_tracker import run_tracklet_tracker

   config = {
       'tracker_name': 'Tracklet Tracker',
       'initial_search_radius': 10.0,
       'max_velocity_change': 5.0,
       'min_tracklet_length': 3,
       'max_consecutive_misses': 2,
       'min_detection_rate': 0.6,
       'max_linking_gap': 10,
       'linking_search_radius': 30.0,
       'smoothness_weight': 1.0,
       'min_track_length': 5
   }

   track_data_list = run_tracklet_tracker(detectors, config)

Algorithm Comparison
~~~~~~~~~~~~~~~~~~~~

.. list-table:: Tracking Algorithm Comparison
   :header-rows: 1
   :widths: 15 25 25 20 15

   * - Algorithm
     - Best For
     - Strengths
     - Weaknesses
     - Complexity
   * - Simple
     - Fast objects, low clutter
     - Fast, automatic parameters
     - Local associations only
     - Low
   * - Kalman
     - Noisy measurements
     - Probabilistic, smooth predictions
     - Assumes constant velocity
     - Medium
   * - Network Flow
     - Complex scenarios, gaps
     - Global optimization, gap bridging
     - Higher computational cost
     - High
   * - Tracklet
     - High false alarms
     - Robust to clutter, two-stage filtering
     - Many parameters to tune
     - High

Tracks Panel Overview
---------------------
The **Tracks Panel** in the Data Manager provides tools for viewing, modifying, and analyzing tracks. The Tracks panel 
displays all tracks for the selected Sensor in a table with columns:

- **Visible**: Checkbox to show/hide track
- **Name**: Track identifier
- **Tracker**: Parent tracker name
- **Frames**: Number of frames in track
- **Length**: Total trajectory length in pixels
- **Color**: Track color (click to change)
- **Marker**: Marker style for current position
- **Line Width**: Width of trajectory line
- **Marker Size**: Size of position marker
- **Complete**: Show entire track regardless of current frame
- **Show Line**: Whether to draw connecting line
- **Line Style**: Line style (solid, dashed, etc.)
- **Tail Length**: Number of previous frames to show (0 = all)
- **Labels**: Text labels for categorization

Bulk Actions
~~~~~~~~~~~~

Apply property changes to multiple selected tracks:

1. Select tracks in the table (Ctrl+Click or Shift+Click for multiple)
2. Choose a **Property** from the dropdown (Visibility, Color, Marker, etc.)
3. Set the **Value** using the appropriate control
4. Click **Apply to Selected**

This is useful for:

- Hiding multiple tracks at once
- Applying consistent styling across tracks
- Batch labeling tracks
- Setting tail length for multiple tracks

Track Selection Actions
-----------------------

These actions work on one or more selected tracks:

Export Tracks
~~~~~~~~~~~~~
Export selected tracks to CSV file with all coordinates and styling.

Copy to Sensor
~~~~~~~~~~~~~~
Copy selected tracks to a different sensor or the same sensor (useful for comparing across sensors).

.. note::
   For real world applications, copying tracks between sensors may require mapping tracks in one sensor to 
   another through some transform operation. The functionality built into VISTA directly copies the tracks' frames, 
   rows, columns. It is left to users to add any transforms needed for their real-world applications.

Merge Selected
~~~~~~~~~~~~~~
Merge multiple selected tracks into a single track by concatenating their points

Delete Selected
~~~~~~~~~~~~~~~
Remove selected tracks from the tracker

Label Selected
~~~~~~~~~~~~~~
Apply labels to selected tracks for categorization

Plot Track Details
~~~~~~~~~~~~~~~~~~
Open a plotting window showing track details as a static plot or animated over time.

.. _track-operations:

Track Operations
----------------
These actions require selecting exactly one track.

Split Track
~~~~~~~~~~~

To split a track at a specific frame:

1. Select a single track in the Tracks panel
2. Navigate to the frame number where the split should occur
3. Click **Split Track**

.. image:: /_static/images/user_guide_tracks_split.gif
   :alt: Split track
   :align: center

Use cases:

- Correcting tracking errors where two objects were merged
- Isolating specific trajectory segments for analysis
- Removing problematic sections while preserving good data

Merge Tracks
~~~~~~~~~~~~

To combine multiple tracks into one:

1. Select two or more tracks in the Tracks panel (Ctrl+Click)
2. Click **Merge Selected**
3. A new track is created containing all points from selected tracks
4. Points are automatically sorted by frame number
5. Original tracks are preserved

Use cases:

- Combining fragmented tracks from the same object
- Manually fixing tracking gaps
- Consolidating results from multiple tracking runs

.. warning::
   Merging tracks does not remove duplicate frames. If tracks overlap in time, you may need to manually edit the merged result.

Edit Track
~~~~~~~~~~

Interactive track editing allows manual refinement:

1. Select a single track
2. Click **Edit Track** (button becomes highlighted)
3. Edit track points:

   - **Move point**: Click and drag existing point
   - **Add point**: Navigate to frame, Ctrl+Click at desired location
   - **Delete point**: Right-click on point
   - **Navigate**: Use arrow keys or Page Up/Down to change frames

4. Click **Save Changes** or press Enter to accept
5. Click **Cancel** or press Escape to discard changes

Tips for editing:

- Zoom in for precise positioning
- Use keyboard navigation for efficiency
- Changes are shown in real-time
- Editing is non-destructive until saved

.. _track-extraction:

Track Extraction
----------------

Track extraction analyzes imagery around track points to extract signal information and refine positions.

What is Track Extraction?
~~~~~~~~~~~~~~~~~~~~~~~~~~

For each track point, extraction:

1. Extracts a square image chip centered on the track position
2. Detects signal pixels using CFAR-like thresholding
3. Computes local noise statistics from background annulus
4. Optionally updates track coordinates to signal blob centroid

Extraction results are stored in the track's ``extraction_metadata`` and can be:

- Viewed as overlays in the viewer
- Edited interactively to refine signal masks
- Exported for external analysis

Running Track Extraction
~~~~~~~~~~~~~~~~~~~~~~~~~

To extract signal information for a track:

1. Select a single track in the Tracks panel
2. Click **Extract** button
3. Configure extraction parameters:

   **Chip Parameters**
      - **Chip Radius**: Radius of square chip to extract (pixels)
      - Chip diameter = 2 × radius + 1

   **Background Estimation**
      - **Background Radius**: Outer radius for noise calculation (pixels)
      - **Ignore Radius**: Inner guard region to exclude (pixels)
      - **Annulus Shape**: Circular or square background region

   **Detection Parameters**
      - **Threshold Deviation**: Number of standard deviations above mean for signal detection
      - **Search Radius**: Only keep signal blobs within central search region (optional)

   **Centroid Update**
      - **Update Centroids**: If checked, refine track positions using signal blob centroids
      - **Max Centroid Shift**: Maximum allowed position update (pixels)

4. Click **Run**
5. Extraction metadata is stored in the track

Viewing Extraction Results
~~~~~~~~~~~~~~~~~~~~~~~~~~~

To view extracted signal pixels:

1. Select a track with extraction metadata
2. Click **View Extraction** (button becomes highlighted)
3. Navigate through frames to see signal pixel overlay
4. Signal pixels are highlighted in the viewer
5. Click **View Extraction** again to hide overlay

Editing Extraction Results
~~~~~~~~~~~~~~~~~~~~~~~~~~~

To manually refine signal masks:

1. Select a track with extraction metadata
2. Click **Edit Extraction** (button becomes highlighted)
3. Paint or erase signal pixels:

   - **Paint**: Left-click and drag to mark pixels as signal
   - **Erase**: Right-click and drag to remove signal pixels
   - **Adjust brush**: Use mouse wheel to change brush size
   - **Navigate**: Arrow keys or Page Up/Down to change frames

4. Click **Save Changes** to update extraction metadata
5. Click **Cancel** or press Escape to discard changes

Use cases:

- Correcting false positives in signal detection
- Adding missed signal pixels
- Refining masks before exporting for machine learning

.. _track-analysis:

Track Analysis and Refinement
------------------------------

VISTA provides several algorithms for analyzing and refining track trajectories, accessible through **Algorithms > Track Analysis** in the main menu.

Interpolation
~~~~~~~~~~~~~

**Track Interpolation** fills gaps in track data by interpolating missing frames between existing track points.

**How it Works**

- Identifies missing frames between first and last tracked frames
- Uses scipy interpolation to estimate positions for missing frames
- Creates a new track with continuous frame coverage

**Parameters**

- **Track**: Select track to interpolate
- **Method**: Interpolation method

  - ``linear``: Linear interpolation (default)
  - ``nearest``: Nearest-neighbor
  - ``quadratic``: Quadratic spline
  - ``cubic``: Cubic spline

- **Output Name**: Name for interpolated track

**When to Use**

- Filling detection gaps in sparse tracks
- Creating uniform time sampling for analysis
- Preparing tracks for smoothing algorithms

**Example**

.. code-block:: python

   from vista.algorithms.tracks.interpolation import TrackInterpolation

   interpolator = TrackInterpolation(track, method='cubic')
   results = interpolator()
   interpolated_track = results['interpolated_track']

Smoothing (Savitzky-Golay)
~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Savitzky-Golay Filter** smooths track positions while preserving trajectory features better than simple averaging.

**How it Works**

- Fits polynomial to successive windows of track points
- Uses least-squares to determine optimal polynomial coefficients
- Preserves features like relative maxima, minima, and width

**Parameters**

- **Track**: Select track to smooth
- **Radius**: Radius of smoothing window (window length = 2 × radius + 1)
- **Poly Order**: Polynomial order (must be < window length)
- **Output Name**: Name for smoothed track

**When to Use**

- Noisy track positions from detections
- Before computing velocities or accelerations
- Visualizing underlying motion trends

**Constraints**

- Requires at least 3 track points
- Window length must be ≤ number of points
- Polynomial order must be < window length

**Example**

.. code-block:: python

   from vista.algorithms.tracks.savitzky_golay import SavitzkyGolayFilter

   filter = SavitzkyGolayFilter(track, radius=3, polyorder=2)
   results = filter()
   smoothed_track = results['smoothed_track']

Exporting and Importing Tracks
-------------------------------

.. _tracks-csv-format:

CSV Format
~~~~~~~~~~

Tracks can be exported to and imported from CSV files with the following format:

**Required Columns**

One temporal coordinate (choose one):
  - ``Frames``: Frame numbers (preferred)
  - ``Times``: Timestamps in ISO format (requires sensor with imagery times)

One spatial coordinate system (choose one):
  - ``Rows`` and ``Columns``: Pixel coordinates (preferred)
  - ``Latitude (deg)``, ``Longitude (deg)``, ``Altitude (km)``: Geodetic coordinates (requires sensor with geolocation)

**Optional Columns**

- ``Track``: Track name (required for multi-track files)
- ``Tracker``: Tracker name
- ``Color``: PyQtGraph color string (e.g., 'r', 'g', 'b', '#FF0000')
- ``Marker``: Marker style ('o', 's', 't', 'd', '+', 'x', 'star')
- ``Line Width``: Integer line width
- ``Marker Size``: Integer marker size
- ``Visible``: Boolean visibility
- ``Complete``: Boolean to show entire track
- ``Show Line``: Boolean to draw connecting line
- ``Line Style``: Line style string ('SolidLine', 'DashLine', 'DotLine', 'DashDotLine', 'DashDotDotLine')
- ``Tail Length``: Integer (0 = show all history)
- ``Labels``: Comma-separated label strings

**Example CSV (Pixel Coordinates)**

.. code-block:: text

   Track,Frames,Rows,Columns,Color,Marker,Visible
   Object_1,100,250.5,300.2,r,o,True
   Object_1,101,252.3,305.8,r,o,True
   Object_1,102,254.1,311.4,r,o,True
   Object_2,100,180.2,420.5,g,s,True
   Object_2,101,182.5,422.1,g,s,True

**Example CSV (Geodetic Coordinates)**

.. code-block:: text

   Track,Frames,Latitude (deg),Longitude (deg),Altitude (km),Color
   Satellite_1,100,38.5,77.0,400.0,y
   Satellite_1,101,38.6,77.1,401.0,y
   Satellite_1,102,38.7,77.2,402.0,y

**Example CSV (Time-based)**

.. code-block:: text

   Track,Times,Rows,Columns,Labels
   Target_A,2024-01-15T10:30:00.000,250.5,300.2,"aircraft,commercial"
   Target_A,2024-01-15T10:30:01.000,252.3,305.8,"aircraft,commercial"
   Target_A,2024-01-15T10:30:02.000,254.1,311.4,"aircraft,commercial"

Loading from CSV
~~~~~~~~~~~~~~~~

Via GUI:

1. Open Data Manager > Tracks tab
2. Select a Sensor
3. Click **Load Tracks**
4. Browse to CSV file
5. Tracks are loaded and added to the sensor

Via Python:

.. code-block:: python

   import pandas as pd
   from vista.tracks.track import Track

   # Load CSV
   df = pd.read_csv('tracks.csv')

   # Create tracks from DataFrame
   for track_name, track_df in df.groupby('Track'):
       track = Track.from_dataframe(track_df, sensor, name=track_name)
       # Add to sensor or tracker

Exporting to CSV
~~~~~~~~~~~~~~~~

Via GUI:

1. Select tracks in Tracks panel
2. Click **Export Tracks**
3. Choose save location
4. Tracks are exported with all columns

Via Python:

.. code-block:: python

   # Export single track
   track.to_csv('my_track.csv')

   # Export tracker with multiple tracks
   tracker.to_csv('all_tracks.csv')

Common Workflows
----------------

Workflow 1: Manual Tracking
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Create tracks by clicking through frames:

1. Load imagery for a sensor
2. Open Data Manager > Tracks tab
3. Click **Manual Track**
4. Navigate through frames, clicking object positions
5. Press Enter to finish
6. Repeat for additional objects
7. Export tracks to CSV when complete

Workflow 2: Automated Tracking
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Use detection algorithms to create tracks automatically:

1. Run detection algorithm (e.g., Simple Threshold or CFAR)
2. Review detections in Data Manager > Detections tab
3. Go to **Algorithms > Tracking** menu
4. Select tracking algorithm (e.g., Simple Tracker)
5. Configure parameters and select input detectors
6. Run algorithm
7. Review tracks in Tracks tab
8. Refine using split, merge, or edit operations

Workflow 3: Track Refinement
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Improve track quality through analysis operations:

1. Load or create initial tracks
2. Run **Algorithms > Track Analysis > Interpolation** to fill gaps
3. Run **Algorithms > Track Analysis > Savitzky-Golay** to smooth positions
4. Select track and click **Extract** for signal analysis
5. Click **Edit Extraction** to refine signal masks
6. Export refined tracks for further analysis

Workflow 4: Comparative Analysis
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Compare multiple tracking algorithms:

1. Run detection algorithm on your data
2. Run multiple tracking algorithms with different parameters:

   - Simple Tracker with default settings
   - Kalman Tracker for smooth motion
   - Network Flow for global optimization
   - Tracklet Tracker for high clutter

3. Each produces a separate Tracker in the Tracks panel
4. Use **Plot Track Details** to compare trajectories
5. Use **Copy to Sensor** to compare across sensors
6. Export best results to CSV

Tips and Best Practices
------------------------

Track Creation Tips
~~~~~~~~~~~~~~~~~~~

- **Use appropriate tracking algorithm for your scenario**:

  - Fast objects with low clutter → Simple Tracker
  - Noisy detections → Kalman Tracker
  - Complex scenarios with gaps → Network Flow
  - High false alarms → Tracklet Tracker

- **Start with conservative parameters**:

  - Smaller search radius reduces false associations
  - Higher minimum track length filters spurious tracks
  - Let automatic parameter estimation guide you

- **Review detection quality first**:

  - Poor detections → poor tracks
  - Filter detections by confidence before tracking
  - Adjust detection thresholds if needed

Track Management Tips
~~~~~~~~~~~~~~~~~~~~~

- **Use labels for organization**:

  - Label tracks by object type (aircraft, vehicle, person)
  - Label by behavior (inbound, stationary, turning)
  - Label by quality (verified, suspicious)

- **Use tail length for visualization**:

  - Set tail length = 10-20 for recent history
  - Set tail length = 0 to see full trajectory
  - Use "Complete" mode to show track regardless of frame

- **Adjust styling for clarity**:

  - Use distinct colors for different objects
  - Increase line width for long-range objects
  - Use dashed lines for predicted/interpolated sections

Analysis Tips
~~~~~~~~~~~~~

- **Interpolate before smoothing**:

  - Fill gaps with interpolation first
  - Then apply Savitzky-Golay smoothing
  - This produces better results than smoothing sparse tracks

- **Choose appropriate smoothing parameters**:

  - Larger radius = more smoothing
  - Cubic polynomials preserve features better than linear
  - Window length should be < 10% of track length

- **Use extraction for quality assessment**:

  - Extract chips to verify object presence
  - Check noise_std values for track reliability
  - Use signal masks to identify tracking errors

Performance Tips
~~~~~~~~~~~~~~~~

- **Limit track visualization**:

  - Hide tracks you're not currently analyzing
  - Use tail length to reduce rendering overhead
  - Toggle off "Show Line" for many tracks

- **Use appropriate tracking algorithm complexity**:

  - Simple Tracker is fastest
  - Network Flow is slower but more accurate
  - Consider computational cost for large datasets

- **Filter detections before tracking**:

  - Remove low-confidence detections
  - Apply spatial or temporal filtering
  - This improves both speed and accuracy

Troubleshooting
~~~~~~~~~~~~~~~

**No tracks created by algorithm**

- Check that detectors have sufficient detections
- Reduce minimum track length parameter
- Increase max search radius or max gap
- Verify detection density is adequate

**Fragmented tracks**

- Increase max gap or max age parameters
- Use Network Flow tracker for better gap bridging
- Consider interpolation to fill gaps post-tracking
- Manually merge related track fragments

**Track switches (two objects swap identities)**

- Reduce max search radius to prevent ambiguous associations
- Use Kalman or Tracklet tracker for better discrimination
- Increase process noise in Kalman tracker
- Manually split incorrectly merged tracks

**Tracks drift from objects over time**

- Run extraction to identify tracking errors
- Use Edit Track to manually correct positions
- Try smoothing with smaller window radius
- Check if detections are properly centered on objects

See Also
--------

- :doc:`detections` - Creating and managing detections
- :doc:`algorithms` - Overview of all algorithms
- :doc:`../api/tracks` - Track API reference
- :doc:`../api/algorithms` - Tracking algorithms API reference
