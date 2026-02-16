Object Detection
================

VISTA provides tools for detecting objects and points of interest in multi-frame imagery.
Detections represent individual observations without temporal association—they are
"what" and "where" without "when" continuity. To connect detections across time, see :doc:`tracks`.

.. _detection-overview:

Overview
--------

Detections in VISTA are:

**Frame-Specific**
   Each detection belongs to a specific frame and has pixel coordinates (row, column)

**Unassociated**
   Unlike tracks, detections are independent observations without temporal relationships

**Labeled**
   Each detection can have multiple labels for categorization (e.g., "bright", "moving")

**Styled**
   Customize color, marker shape, size, and visibility for visualization

**Exportable**
   Save detections to CSV or other formats for analysis or sharing

Loading Detections
------------------

1. Click **File → Load Detections**
2. Select an CSV file (``.csv``)

.. note::
   Alternatively users can drag and drop a detections file onto the **Detectors** panel in the **Data Manager**.

CSV Format
~~~~~~~~~~

.. code-block:: text

   Detector,Frame,Row,Column,Labels
   Threshold Detections,0,512.5,1024.3,"bright, moving"
   Threshold Detections,0,450.2,890.7,dim
   Threshold Detections,1,600.0,800.0,bright
   CFAR Detections,2,300.5,500.2,

CSV Columns
~~~~~~~~~~~

:Detector: Name of the detector (string)
:Frame: Frame number (integer)
:Row: Row pixel coordinate (float)
:Column: Column pixel coordinate (float)
:Color: Detector marker color. PyQtGraph color string (e.g., 'r', 'g', 'b', '#FF0000') (string, optional)
:Marker: Marker style ('o', 's', 't', 'd', '+', 'x', 'star') (string, optional)
:Line Thickness: Detector marker line thickness (integer, optional)
:Visible: Determines if detector should be visible by default or not (bool, optional)
:Complete: Show detections regardless of current frame (bool, optional)
:Labels: Comma-separated labels (string, optional)

CSV Requirements
~~~~~~~~~~~~~~~~

- Must have columns: Detector (or use name parameter), Frame, Row, Column
- Labels column is optional
- Multiple detectors can be in same CSV (grouped by Detector column)

.. _manual-detection_creation:

Manually Create Detections
--------------------------
Users can create detections manually using the create detections tool. With this tool selection users can click 
points using one of several methods:

 - Verbatim: Use the exact location where you click.
 - Peak: Uses the peak pixel within a radius of your clicked location.
 - CFAR: Selects the weighted centroid of the pixel group closest to the clicked location that exceeds the local noise.

.. image:: https://github.com/awetomaton/VISTA/releases/download/MEDIA/user_guide_detectors_create.gif
   :alt: Create detections
   :align: center

De-select the create detections tool to create a new set of detections (a detector) in the Detections Panel.

Convert Tracks into Detections
------------------------------
Users can also create detections by converting a track into detections by selecting tracks in the Tracks Panel and 
pressing the Break Into Detections button.

.. image:: https://github.com/awetomaton/VISTA/releases/download/MEDIA/user_guide_detectors_from_tracks.gif
   :alt: Create detections from tracks
   :align: center

.. _detection-algorithms:

Detection Algorithms
--------------------

VISTA includes built-in detection algorithms and supports custom detectors. Choose an
algorithm based on your imagery characteristics and detection requirements.

Simple Threshold Detector
~~~~~~~~~~~~~~~~~~~~~~~~~~

The Simple Threshold detector identifies pixels above a specified intensity threshold.
It's fast and effective for high-contrast objects against low-background imagery.

**When to Use:**
   - High signal-to-noise ratio imagery
   - Objects significantly brighter than background
   - Quick initial detection pass
   - Testing detection parameters

**Algorithm Parameters:**

:threshold: Intensity value above which pixels are detected (float)
:min_area: Minimum connected component size in pixels (int, optional)
:max_area: Maximum connected component size in pixels (int, optional)

**Example Usage:**

.. code-block:: python

   from vista.algorithms.detectors.threshold import SimpleThreshold

   # Create detector
   detector = SimpleThreshold(
       threshold=50.0,      # Detect pixels > 50
       min_area=5,          # Minimum 5-pixel objects
       max_area=500         # Maximum 500-pixel objects
   )

   # Run on single frame
   frame_data = imagery.images[frame_idx]
   rows, columns = detector(frame_data)

   print(f"Found {len(rows)} detections")

**Advantages:**
   - Very fast execution
   - Simple to understand and tune
   - Deterministic results
   - No training required

**Limitations:**
   - Sensitive to background variations
   - No spatial context consideration
   - May produce false positives in noisy imagery

CFAR Detector
~~~~~~~~~~~~~

The Constant False Alarm Rate (CFAR) detector adapts to local background statistics,
making it robust to spatially-varying backgrounds and noise levels.

**When to Use:**
   - Varying background intensity across image
   - Unknown or changing noise levels
   - Need consistent false alarm rate
   - Cluttered imagery with complex backgrounds

**Algorithm Parameters:**

:name: Detector identifier (string)
:kernel: Detection kernel size determining analysis window (int, odd number)
:n_pixels: Number of standard deviations above mean for detection (float)

**Example Usage:**

.. code-block:: python

   from vista.algorithms.detectors.cfar import CFAR

   # Create CFAR detector
   detector = CFAR(
       name="CFAR Detector",
       kernel=21,          # 21x21 pixel analysis window
       n_pixels=3.0        # 3-sigma threshold
   )

   # Process single frame
   frame_data = imagery.images[frame_idx]
   rows, columns = detector(frame_data)

**How It Works:**

1. For each pixel, compute local statistics in surrounding window
2. Calculate threshold as mean + n_pixels × std_dev
3. Detect pixels exceeding adaptive threshold
4. Return coordinates of detected pixels

**Advantages:**
   - Adapts to local background
   - Robust to illumination changes
   - Maintains consistent false alarm rate
   - Works well in cluttered scenes

**Limitations:**
   - Slower than simple threshold
   - Requires tuning kernel size and threshold
   - May miss detections near bright features

PSTNN Detector
~~~~~~~~~~~~~~

The Partial Sum of Tensor Nuclear Norm (PSTNN) detector uses tensor decomposition to separate
low-rank background from sparse targets across the temporal image sequence. It exploits both
spatial and temporal structure for robust small target detection in complex scenes.

**When to Use:**
   - Small targets in complex, slowly-varying backgrounds
   - Multi-frame imagery where temporal correlation can aid detection
   - Scenes where single-frame detectors produce excessive false alarms
   - Infrared or electro-optical imagery with low signal-to-noise ratio

**Algorithm Parameters:**

:patch_size: Size of spatial patches for tensor construction (int, default 40)
:stride: Stride between patches; equal to patch_size for non-overlapping (int, default 40)
:lambda_param: Sparsity weight; None for automatic selection (float or None)
:max_iterations: Maximum ADMM iterations (int, default 50)
:n_skipped_singular_values: Top singular values to preserve as background (int, default 1)
:threshold_multiplier: Standard deviations above mean for adaptive thresholding (float, default 5.0)
:min_area: Minimum connected component size in pixels (int, default 1)
:max_area: Maximum connected component size in pixels (int, default 1000)

**Example Usage:**

.. code-block:: python

   from vista.algorithms.detectors.pstnn import PSTNN

   # Create PSTNN detector
   detector = PSTNN(
       patch_size=40,
       stride=40,
       max_iterations=50,
       n_skipped_singular_values=1,
       threshold_multiplier=5.0,
       min_area=1,
       max_area=500,
       use_gpu=True
   )

   # Decompose multi-frame imagery into sparse target component
   sparse_targets = detector.decompose(imagery.images)

   # Detect blobs in a single frame's sparse target image
   rows, columns = detector.detect(sparse_targets[0])

**How It Works:**

1. Construct a 3D patch-tensor from the image sequence
2. Decompose the tensor into low-rank background + sparse targets via ADMM
3. Threshold the sparse component to identify target pixels
4. Group connected pixels into blobs and compute weighted centroids

**Advantages:**
   - Exploits temporal correlation across frames for robust background separation
   - Adapts to complex, non-uniform backgrounds without manual tuning
   - GPU acceleration available for SVD operations via PyTorch
   - Effective for small, dim targets that single-frame detectors may miss

**Limitations:**
   - Requires multiple frames (at least 2, more is better)
   - Computationally intensive; GPU recommended for large datasets
   - Patch size must be larger than expected targets
   - Memory usage scales with image size, patch count, and frame count

Running Detection Algorithms
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Via GUI:**

1. Open **Image Processing → Detectors** menu
2. Select detection algorithm (Simple Threshold, CFAR, or PSTNN)
3. Configure parameters in dialog
4. Click **Run** to execute on current imagery
5. Detections appear in the Detections Panel

.. image:: https://github.com/awetomaton/VISTA/releases/download/MEDIA/user_guide_detectors_running.gif
   :alt: Shapefiles
   :align: center

**Programmatically:**

.. code-block:: python

   from vista.algorithms.detectors.threshold import SimpleThreshold
   from vista.detections.detector import Detector

   # Create detection algorithm
   detector_algo = SimpleThreshold(threshold=50.0, min_area=5)

   # Run on multiple frames
   all_frames = []
   all_rows = []
   all_cols = []

   for frame_idx in range(len(imagery)):
       frame_data = imagery.images[frame_idx]
       rows, cols = detector_algo(frame_data)

       # Collect results
       all_frames.extend([frame_idx] * len(rows))
       all_rows.extend(rows)
       all_cols.extend(cols)

   # Create Detector object
   detections = Detector(
       name="Threshold Detections",
       frames=np.array(all_frames),
       rows=np.array(all_rows),
       columns=np.array(all_cols),
       sensor=imagery.sensor,
       description="Simple threshold detector with threshold=50.0"
   )

.. _managing-detections:

Managing Detections
-------------------

The **Detections Panel** provides tools for viewing, filtering, and managing detection results.

Detections Panel Overview
~~~~~~~~~~~~~~~~~~~~~~~~~~

The Detections Panel displays:

- **Visible**: Toggle detection display on/off
- **Name**: Name of detector or detections group (resizable)
- **Labels**: Text labels for categorization (resizable)
- **Color**: Track color (click to change)
- **Marker**: Marker style for current position
- **Marker Size**: Size of marker
- **Line Thickness**: Thickness of the marker border
- **Complete**: Show detections regardless of current frame

.. image:: https://github.com/awetomaton/VISTA/releases/download/MEDIA/user_guide_detectors_controls.gif
   :alt: Detector controls
   :align: center

Reorder / Hide Columns
^^^^^^^^^^^^^^^^^^^^^^
Users can reorder columns by clicking and dragging. Users can hide columns by right clicking on the table header and 
navigating to the "Show/Hide Columns" menu.

.. image:: https://github.com/awetomaton/VISTA/releases/download/MEDIA/user_guide_detections_reorder_columns.gif
   :alt: Reorder detection columns
   :align: center

Manually Reorder Columns
^^^^^^^^^^^^^^^^^^^^^^^^
Users can manually re-order columns by selecting rows in the table content and dragging them. Rows cannot be dragged
from the row header.

.. image:: https://github.com/awetomaton/VISTA/releases/download/MEDIA/user_guide_detections_reorder.gif
   :alt: Detector reordering
   :align: center

Undo
^^^^
Users can also undo previous actions in the Detections Panel by pressing the Undo button or pressing ``ctrl`` + ``z``. 
The undo depth is configurable through the global VISTA settings on the Data Manager tab.

Export Detections
~~~~~~~~~~~~~~~~~
Users can export selected detections by pressing the Export Detections button in the Detections Panel.

Merge Detections
~~~~~~~~~~~~~~~~
Users may merge detectors by selecting multiple detector rows and pressing Merge Detections.

.. image:: https://github.com/awetomaton/VISTA/releases/download/MEDIA/user_guide_detectors_merge.gif
   :alt: Merge detections
   :align: center

Copy Detections
~~~~~~~~~~~~~~~
Users may copy detectors between sensors or on the same sensor by selecting detector rows and pressing the Copy to 
Sensor button. Users may copy only detections that are filtered by label by checking the Copy only filtered detections.

.. image:: https://github.com/awetomaton/VISTA/releases/download/MEDIA/user_guide_detectors_copy.gif
   :alt: Merge detections
   :align: center

.. note::
   For real world applications, copying detections between sensors may require mapping detections in one sensor to 
   another through some transform operation. The functionality built into VISTA directly copies the detection frames, 
   rows, columns. It is left to users to add any transforms needed for their real-world applications.

Detection Selection Actions
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Users can conduct several actions in the Detections Panel once detections are selected. Users can select detections with 
the select detections or lasso tools.

Create Track
^^^^^^^^^^^^
Users can create a track from detections by pressing the Create Track button.

.. image:: https://github.com/awetomaton/VISTA/releases/download/MEDIA/user_guide_detectors_create_track.gif
   :alt: Merge detections
   :align: center

Add to Track
^^^^^^^^^^^^
Users can create a track from detections by pressing the Add to Track button.

.. image:: https://github.com/awetomaton/VISTA/releases/download/MEDIA/user_guide_detectors_add_to_track.gif
   :alt: Merge detections
   :align: center

Edit Detector
^^^^^^^^^^^^^
Users can add or remove detections by selecting a single detector row and pressing the Edit Detector button. Users can 
add new detection points using any of the options described in the :ref:`Manually Create Detections section <manual-detection_creation>`.
Users may also remove existing detections by clicking on them.

.. image:: https://github.com/awetomaton/VISTA/releases/download/MEDIA/user_guide_detectors_edit.gif
   :alt: Edit detections
   :align: center

Labeling Detections
~~~~~~~~~~~~~~~~~~~
Users can label detections by pressing the Label Detections button. Users may filter detections for a specific set of 
labels by right clicking on the Labels column in the detections table and setting a filter.

.. image:: https://github.com/awetomaton/VISTA/releases/download/MEDIA/user_guide_detectors_label.gif
   :alt: Label detections
   :align: center

Programmatically Filtering Detections
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Filter detections by various criteria:

**By Frame Range:**

.. code-block:: python

   # Get detections in frame range
   frame_mask = (detector.frames >= start_frame) & (detector.frames <= end_frame)
   filtered_detector = detector[frame_mask]

**By Spatial Region:**

.. code-block:: python

   # Get detections in AOI
   x_min, y_min, x_max, y_max = aoi.get_bounds()
   spatial_mask = (
       (detector.columns >= x_min) & (detector.columns <= x_max) &
       (detector.rows >= y_min) & (detector.rows <= y_max)
   )
   filtered_detector = detector[spatial_mask]

**By Labels:**

.. code-block:: python

   # Get detections with specific label
   labeled_mask = [
       'bright' in labels
       for labels in detector.labels
   ]
   filtered_detector = detector[np.array(labeled_mask)]

Styling Detections
~~~~~~~~~~~~~~~~~~

Customize detection appearance:

.. code-block:: python

   # Change color
   detector.color = 'g'  # Green

   # Change marker
   detector.marker = 's'  # Square
   # Available: 'o' (circle), 's' (square), 't' (triangle),
   #            'd' (diamond), '+' (plus), 'x' (cross), 'star'

   # Change size
   detector.marker_size = 15

   # Change line thickness
   detector.line_thickness = 3

   # Toggle visibility
   detector.visible = False

**In GUI:**

1. Select detector in Detections Panel
2. Click on color/marker controls
3. Changes apply immediately to viewer

Labeling Detections
~~~~~~~~~~~~~~~~~~~

Add categorical labels to detections for classification:

.. code-block:: python

   # Add labels to specific detections
   detector.labels[0] = {'bright', 'moving'}
   detector.labels[1] = {'dim', 'stationary'}

   # Get all unique labels
   all_labels = detector.get_unique_labels()

   # Filter by label
   bright_detections = [
       i for i, labels in enumerate(detector.labels)
       if 'bright' in labels
   ]

Labels enable:
   - Detection categorization
   - Quality filtering
   - Algorithm comparison
   - Ground truth annotation

.. _exporting-detections:

Programmatic Detection Usage
----------------------------

Save detections for analysis, sharing, or archival.

Programmatically Export to CSV
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Export to CSV
   detector.to_csv('detections.csv')

   # Or use DataFrame for more control
   df = detector.to_dataframe()
   df.to_csv('detections.csv', index=False)

Programmatically Import from CSV
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Load previously exported detections:

.. code-block:: python

   import pandas as pd
   from vista.detections.detector import Detector

   # Read CSV
   df = pd.read_csv('detections.csv')

   # Create detector from DataFrame
   detector = Detector.from_dataframe(
       df,
       sensor=imagery.sensor,
       name="Imported Detections"
   )

.. _detection-workflows:

Common Programmatic Workflows
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Workflow 1: Multi-Algorithm Detection
'''''''''''''''''''''''''''''''''''''

Run multiple algorithms and compare results:

.. code-block:: python

   from vista.algorithms.detectors.threshold import SimpleThreshold
   from vista.algorithms.detectors.cfar import CFAR

   # Run threshold detector
   threshold_det = SimpleThreshold(threshold=50.0)
   threshold_rows, threshold_cols = threshold_det(frame_data)

   # Run CFAR detector
   cfar_det = CFAR(kernel=21, n_pixels=3.0)
   cfar_rows, cfar_cols = cfar_det(frame_data)

   # Compare detection counts
   print(f"Threshold: {len(threshold_rows)} detections")
   print(f"CFAR: {len(cfar_rows)} detections")

Workflow 2: Detection Validation
''''''''''''''''''''''''''''''''

Compare algorithm detections with ground truth:

.. code-block:: python

   # Load ground truth placemarks
   ground_truth_positions = [
       (placemark.geometry['row'], placemark.geometry['col'])
       for placemark in placemarks
   ]

   # Find detections near ground truth (within radius)
   radius = 5.0  # pixels
   true_positives = 0

   for gt_row, gt_col in ground_truth_positions:
       distances = np.sqrt(
           (detector.rows - gt_row)**2 +
           (detector.columns - gt_col)**2
       )
       if np.any(distances < radius):
           true_positives += 1

   # Calculate detection rate
   detection_rate = true_positives / len(ground_truth_positions)
   print(f"Detection rate: {detection_rate:.1%}")

Workflow 3: Spatial Filtering
'''''''''''''''''''''''''''''

Focus detections in specific regions using AOIs:

.. code-block:: python

   from vista.aoi.aoi import AOI

   # Define search zones
   search_zone_1 = AOI(name="Zone 1", x=100, y=200, width=400, height=300)
   search_zone_2 = AOI(name="Zone 2", x=600, y=150, width=500, height=400)

   # Filter detections by zone
   for aoi in [search_zone_1, search_zone_2]:
       x_min, y_min, x_max, y_max = aoi.get_bounds()

       mask = (
           (detector.columns >= x_min) & (detector.columns <= x_max) &
           (detector.rows >= y_min) & (detector.rows <= y_max)
       )

       zone_detections = detector[mask]
       print(f"{aoi.name}: {len(zone_detections.frames)} detections")

Workflow 4: Temporal Analysis
'''''''''''''''''''''''''''''

Analyze detection patterns over time:

.. code-block:: python

   # Count detections per frame
   unique_frames, counts = np.unique(detector.frames, return_counts=True)

   # Find frames with most detections
   busy_frames = unique_frames[counts > np.percentile(counts, 90)]
   print(f"Busy frames (>90th percentile): {busy_frames}")

   # Plot detection rate over time
   import matplotlib.pyplot as plt
   plt.figure(figsize=(10, 4))
   plt.bar(unique_frames, counts)
   plt.xlabel('Frame Number')
   plt.ylabel('Detection Count')
   plt.title('Detections Over Time')
   plt.show()

.. _detection-tips:

Tips and Best Practices
------------------------

**Algorithm Selection**

- Start with Simple Threshold for high-contrast imagery
- Use CFAR for variable backgrounds or unknown noise levels
- Use PSTNN for small targets in complex scenes with multi-frame data
- Run multiple algorithms and compare results
- Tune parameters on representative sample frames first

**Parameter Tuning**

- **Threshold**: Set to ~3-5× background noise level
- **CFAR kernel**: Should be 2-3× larger than expected object size
- **CFAR n_pixels**: Start with 3.0, increase to reduce false alarms
- **Min area**: Set to smallest object of interest in pixels
- **Max area**: Set to avoid detecting large background features

**Performance**

- Process subset of frames first to validate parameters
- Use spatial filtering (AOIs) to focus computation
- Simple Threshold is faster than CFAR (use for real-time)
- Cache results rather than re-running detection

**Validation**

- Always visually inspect detection results
- Compare with known targets or ground truth
- Check false positive and false negative rates
- Validate across different imagery conditions

**Organization**

- Use descriptive detector names (include algorithm and key parameters)
- Add descriptions documenting parameter choices
- Export results to CSV for external analysis
- Save validated parameters for future use

**Common Issues**

**Too many detections:**
   - Increase threshold value
   - Increase CFAR n_pixels parameter
   - Apply spatial filtering with AOIs
   - Increase min_area to filter small noise

**Too few detections:**
   - Decrease threshold value
   - Decrease CFAR n_pixels parameter
   - Check that objects are visible in imagery
   - Verify coordinate system is correct

**False positives:**
   - Use CFAR instead of threshold for adaptive background
   - Apply size filtering (min_area, max_area)
   - Label and filter detections by confidence
   - Validate against ground truth

Keyboard Shortcuts
------------------
 - ``Delete``: Delete selected detector

See Also
--------

**Related Sections:**

- :doc:`tracks` - Connecting detections into trajectories
- :doc:`features` - AOIs and placemarks for spatial reference
- :doc:`imagery` - Preprocessing imagery before detection

**API References:**

- :class:`vista.detections.detector.Detector` - Detection data model
- :class:`vista.algorithms.detectors.threshold.SimpleThreshold` - Threshold detector
- :class:`vista.algorithms.detectors.cfar.CFAR` - CFAR detector
- :class:`vista.algorithms.detectors.pstnn.PSTNN` - PSTNN tensor decomposition detector
