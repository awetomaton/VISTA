# VISTA - Visual Imagery Software Tool for Analysis

![Logo](/vista/icons/logo-small.jpg)

VISTA is a PyQt6-based desktop application for viewing, analyzing, and managing multi-frame imagery datasets along with associated detection and track overlays. It's designed for scientific and analytical workflows involving temporal image sequences with support for time-based and geodetic coordinate systems, sensor calibration data, and radiometric processing.

![Version](https://img.shields.io/badge/version-1.5.0-blue)
![Python](https://img.shields.io/badge/python-3.9+-blue)
![License](https://img.shields.io/badge/license-MIT-green)
[![PyPI](https://img.shields.io/badge/pypi-vista--imagery-blue)](https://pypi.org/project/vista-imagery/)

## Watch the demo!
[![Watch the demo](/docs/images/vista_demo_thumbnail.png)](https://www.youtube.com/watch?v=O34wxldMEeg)

## Important Assumptions

**Frame Synchronization Across Imagery Datasets:**

VISTA assumes that all loaded imagery datasets are captured from the same sensor or are temporally synchronized. Specifically:

- Frame numbers represent the same temporal moments across all loaded imagery
- Frame 10 in one imagery dataset corresponds to the exact same time as frame 10 in any other loaded imagery
- This assumption is critical for proper visualization and analysis when multiple imagery datasets are loaded simultaneously
- When loading tracks with time-based mapping, the selected imagery's time-to-frame mapping is used as the reference

## Features

### Multi-Frame Imagery Viewer
- Display full image sequences from HDF5 files with optional time and geodetic metadata
- Support for multiple simultaneous imagery datasets (must have unique names)
- **Sensor calibration data support**: bias/dark frames, uniformity gain corrections, bad pixel masks, and radiometric gain values
- Interactive image histogram with dynamic range adjustment
- Frame-by-frame navigation with keyboard shortcuts
- Click-to-create manual tracks on imagery

### Advanced Track Support
- **Multiple coordinate systems**:
  - Pixel coordinates (Row/Column)
  - Geodetic coordinates (Latitude/Longitude/Altitude) with automatic conversion. Note that at this time this software assumes the altitude is always zero (tracks are already projected to ground)
  - Time-based or frame-based indexing
- **Automatic coordinate conversion**:
  - Times → Frames using imagery timestamps
  - Geodetic coordinates (Lat/Lon/Alt) → Pixel coordinates using 4th-order polynomials
- **Priority system**: Row/Column takes precedence over geodetic; Frames takes precedence over times
- **Manual track creation**: Click on imagery to create custom tracks with automatic frame tracking
- Track path rendering with customizable colors and line widths
- Current position markers with selectable styles
- Tail length control (show full history or last N frames)
- Complete track visualization (override current frame)
- Track length calculation (cumulative distance)

### Detection Overlay
- Load detection CSV files with multiple detector support
- Customizable markers (circle, square, triangle, diamond, plus, cross, star)
- Adjustable colors, marker sizes, and line thickness
- Show/hide individual detectors
- Detection styling persistence across sessions

### Built-in Detection Algorithms
- **CFAR (Constant False Alarm Rate)**: Adaptive threshold detector with guard and background windows
  - Supports three detection modes: 'above' (bright objects), 'below' (dark objects), 'both' (absolute deviation)
- **Simple Threshold**: Basic intensity-based detection with configurable threshold
  - Supports three detection modes: 'above' (positive values), 'below' (negative values), 'both' (absolute value)

### Built-in Tracking Algorithms
- **Simple Tracker**: Nearest-neighbor association with maximum distance threshold
- **Kalman Filter Tracker**: State estimation with motion models and measurement uncertainty
- **Network Flow Tracker**: Global optimization using min-cost flow for track assignment
- **Tracklet Tracker**: Two-stage hierarchical tracker optimized for high false alarm scenarios (100:1 or higher)
  - Stage 1: Forms high-confidence tracklets using strict association criteria
  - Stage 2: Links tracklets based on velocity extrapolation and smoothness

### Image Enhancement
- **Coaddition**: Temporal averaging for noise reduction and signal enhancement
  - Configurable frame window for averaging
  - Creates enhanced imagery with improved SNR

### Background Removal Algorithms
- **Temporal Median**: Remove static backgrounds using median filtering
  - Configurable temporal window and offset
  - Preserves moving objects while removing static elements
  - Supports AOI (Area of Interest) processing
- **Robust PCA**: Principal component analysis for background/foreground separation
  - Low-rank matrix decomposition
  - Robust to outliers and sparse foreground
  - Supports AOI (Area of Interest) processing
  - Separates imagery into background and foreground components

### Image Treatments (Sensor Calibration)
- **Bias Removal**: Apply bias/dark frame correction using calibration data
  - Subtracts sensor dark current from imagery
  - Uses frame-specific bias images based on `bias_images` and `bias_image_frames`
  - Supports AOI (Area of Interest) processing
- **Non-Uniformity Correction (NUC)**: Apply flat-field gain correction
  - Corrects pixel-to-pixel response variations
  - Uses frame-specific uniformity gain images based on `uniformity_gain_images` and `uniformity_gain_image_frames`
  - Supports AOI (Area of Interest) processing

### Playback Controls
- Play/Pause with adjustable FPS (-100 to +100 FPS for reverse playback)
- Frame slider and direct frame number input
- **Bounce Mode**: Loop playback between arbitrary frame ranges
- Time display integration when image timestamps are available
- Actual FPS tracking display

### Data Manager Panel
- Tabbed interface for managing Imagery, Tracks, and Detections
- Bulk property editing (visibility, colors, markers, sizes, line thickness)
- Column filtering and sorting for tracks and detections
- Real-time updates synchronized with visualization
- Track editing with complete track toggle

### Geolocation Support
- 4th-order polynomial geodetic coordinate conversion (Lat/Lon/Alt ↔ Row/Column)
- Optional geodetic coordinate tooltip display
- Automatic coordinate system detection in track files
- Imagery selection dialog for tracks requiring conversion

### Robust Data Loading
- Background threading for non-blocking file I/O
- Progress dialogs with cancellation support
- Automatic detection of coordinate systems and time formats
- Intelligent imagery selection for coordinate/time conversion
- Error handling and user-friendly error messages
- Persistent file browser history via QSettings

## Installation

### Prerequisites
- Python 3.9 or higher

### Installation via pip (Recommended)

VISTA is available on PyPI and can be installed with pip:

```bash
pip install vista-imagery
```

After installation, you can launch VISTA using the command:
```bash
vista
```

Or programmatically in Python:
```python
from vista.app import VistaApp
app = VistaApp()
app.exec()
```

### Installation from Source

1. Clone the repository:
```bash
git clone https://github.com/hartzell-stephen-me/vista.git
cd vista
```

2. Install in development mode:
```bash
pip install -e .
```

Or install with development dependencies:
```bash
pip install -e ".[dev]"
```

3. Run the application:
```bash
vista
# Or
python -m vista
```

### Dependencies

The following dependencies are automatically installed with pip:
- PyQt6 - GUI framework
- pyqtgraph - High-performance visualization
- h5py - HDF5 file support
- pandas - Data manipulation
- numpy - Numerical computing
- astropy - Astronomical/geodetic calculations
- darkdetect - Dark mode detection
- scikit-image - Image processing
- scipy - Scientific computing

**Note:** Pillow is automatically included via scikit-image and is required for Earth background simulation feature.

## Input Data Formats

### Imagery Data (HDF5 Format)

VISTA uses HDF5 files to store image sequences with optional time and geodetic metadata.

#### Required Datasets

**`images`** (3D array)
- **Shape**: `(N_frames, height, width)`
- **Data type**: `float32` (recommended)
- **Description**: Stack of grayscale images
- **Storage**: Chunked format supported for large datasets

**`frames`** (1D array)
- **Shape**: `(N_frames,)`
- **Data type**: `int`
- **Description**: Frame number or index for each image

#### Optional Datasets

**Timestamps:**
- **`unix_time`**: 1D array of `int64` (seconds since Unix epoch)
- **`unix_fine_time`**: 1D array of `int64` (nanosecond offset for high-precision timing)

**Geodetic Conversion Polynomials (4th-order, 15 coefficients each):**
- **`poly_row_col_to_lat`**: Shape `(N_frames, 15)` - Convert pixel col/row to latitude
- **`poly_row_col_to_lon`**: Shape `(N_frames, 15)` - Convert pixel col/row to longitude
- **`poly_lat_lon_to_row`**: Shape `(N_frames, 15)` - Convert lon/lat to pixel row
- **`poly_lat_lon_to_col`**: Shape `(N_frames, 15)` - Convert lon/lat to pixel column

Polynomial format: `f(x,y) = c0 + c1*x + c2*y + c3*x^2 + c4*x*y + c5*y^2 + c6*x^3 + c7*x^2*y + c8*x*y^2 + c9*y^3 + c10*x^4 + c11*x^3*y + c12*x^2*y^2 + c13*x*y^3 + c14*y^4`

**Sensor Calibration Data:**

These datasets support sensor calibration and radiometric correction workflows. Each calibration dataset has a corresponding frames array that indicates when each calibration becomes applicable.

- **`bias_images`**: Shape `(N_bias, height, width)` - Dark/bias frames for dark current correction
- **`bias_image_frames`**: Shape `(N_bias,)` - Frame numbers where each bias image becomes applicable
- **`uniformity_gain_images`**: Shape `(N_gain, height, width)` - Flat-field/gain correction images
- **`uniformity_gain_image_frames`**: Shape `(N_gain,)` - Frame numbers where each gain image becomes applicable
- **`bad_pixel_masks`**: Shape `(N_masks, height, width)` - Bad pixel masks (1=bad, 0=good)
- **`bad_pixel_mask_frames`**: Shape `(N_masks,)` - Frame numbers where each mask becomes applicable
- **`radiometric_gain`**: Shape `(N_frames,)` - Per-frame radiometric gain values (converts counts to physical units)

**Calibration Frame Semantics**: Frame N in a calibration frames array applies to all frames >= N until the next calibration frame. For example, if `bias_image_frames = [0, 100]`, then `bias_images[0]` applies to frames 0-99 and `bias_images[1]` applies to frames 100+.

#### Example HDF5 Structure
```
imagery.h5
├── images (Dataset)
│   └── Shape: (100, 512, 512)
│   └── dtype: float32
│   └── Chunks: (1, 512, 512)
├── frames (Dataset)
│   └── Shape: (100,)
│   └── dtype: int64
├── unix_time (Dataset) [optional]
│   └── Shape: (100,)
│   └── dtype: int64
├── unix_fine_time (Dataset) [optional]
│   └── Shape: (100,)
│   └── dtype: int64
├── poly_row_col_to_lat (Dataset) [optional]
│   └── Shape: (100, 15)
├── poly_row_col_to_lon (Dataset) [optional]
│   └── Shape: (100, 15)
├── poly_lat_lon_to_row (Dataset) [optional]
│   └── Shape: (100, 15)
├── poly_lat_lon_to_col (Dataset) [optional]
│   └── Shape: (100, 15)
├── bias_images (Dataset) [optional]
│   └── Shape: (2, 512, 512)
├── bias_image_frames (Dataset) [optional]
│   └── Shape: (2,)
├── uniformity_gain_images (Dataset) [optional]
│   └── Shape: (2, 512, 512)
├── uniformity_gain_image_frames (Dataset) [optional]
│   └── Shape: (2,)
├── bad_pixel_masks (Dataset) [optional]
│   └── Shape: (2, 512, 512)
├── bad_pixel_mask_frames (Dataset) [optional]
│   └── Shape: (2,)
└── radiometric_gain (Dataset) [optional]
    └── Shape: (100,)
```

#### Creating Imagery Files

```python
import h5py
import numpy as np

# Create synthetic imagery
n_frames = 100
height, width = 512, 512
images = np.random.rand(n_frames, height, width).astype(np.float32)
frames = np.arange(n_frames)

# Save to HDF5
with h5py.File("imagery.h5", "w") as f:
    f.create_dataset("images", data=images, chunks=(1, height, width))
    f.create_dataset("frames", data=frames)

    # Optional: Add timestamps
    unix_time = np.arange(1609459200, 1609459200 + n_frames)
    f.create_dataset("unix_time", data=unix_time)
    f.create_dataset("unix_fine_time", data=np.zeros(n_frames, dtype=np.int64))

    # Optional: Add geodetic conversion polynomials
    # Example: Simple linear mapping for demonstration
    poly_row_col_to_lat = np.zeros((n_frames, 15))
    poly_row_col_to_lat[:, 0] = 40.0  # Base latitude
    poly_row_col_to_lat[:, 1] = 0.0001  # Row scaling
    f.create_dataset("poly_row_col_to_lat", data=poly_row_col_to_lat)

    poly_row_col_to_lon = np.zeros((n_frames, 15))
    poly_row_col_to_lon[:, 0] = -105.0  # Base longitude
    poly_row_col_to_lon[:, 2] = 0.0001  # Column scaling
    f.create_dataset("poly_row_col_to_lon", data=poly_row_col_to_lon)

    # Inverse polynomials
    poly_lat_lon_to_row = np.zeros((n_frames, 15))
    poly_lat_lon_to_row[:, 0] = -40.0 / 0.0001
    poly_lat_lon_to_row[:, 1] = 1.0 / 0.0001
    f.create_dataset("poly_lat_lon_to_row", data=poly_lat_lon_to_row)

    poly_lat_lon_to_col = np.zeros((n_frames, 15))
    poly_lat_lon_to_col[:, 0] = 105.0 / 0.0001
    poly_lat_lon_to_col[:, 2] = 1.0 / 0.0001
    f.create_dataset("poly_lat_lon_to_col", data=poly_lat_lon_to_col)
```

### Track Data (CSV Format)

Track files represent trajectories of moving objects over time. VISTA supports multiple coordinate systems with automatic conversion.

#### Coordinate System Options

**Option 1: Frame + Pixel Coordinates (Standard)**
- Requires: `Frames`, `Rows`, `Columns`

**Option 2: Time + Pixel Coordinates**
- Requires: `Times`, `Rows`, `Columns`
- Times automatically mapped to frames using imagery timestamps

**Option 3: Frame + Geodetic Coordinates**
- Requires: `Frames`, `Latitude`, `Longitude`
- Geodetic coordinates automatically converted to pixels using imagery polynomials

**Option 4: Time + Geodetic Coordinates**
- Requires: `Times`, `Latitude`, `Longitude`
- Both conversions performed automatically

**Priority System:**
- If both `Frames` and `Times` are present, `Frames` takes precedence
- If both pixel (`Rows`/`Columns`) and geodetic (`Latitude`/`Longitude`) coordinates are present, pixel takes precedence

#### Required Columns (Choose One Coordinate System)

| Column Name | Data Type | Description | Example |
|------------|-----------|-------------|---------|
| `Track` | string | Unique identifier for the track | "Tracker 0 - Track 0" |
| **Temporal (choose one):** |
| `Frames` | int | Frame number where this point appears | 15 |
| `Times` | string (ISO 8601) | Timestamp for this point | "2024-01-01T12:00:00.000000" |
| **Spatial (choose one):** |
| `Rows` + `Columns` | float | Pixel coordinates in image | 181.87, 79.08 |
| `Latitude` + `Longitude` + `Altitude` | float | Geodetic coordinates | 40.0128, -105.0156, 1500.0 |

#### Optional Columns

| Column Name | Data Type | Default | Description | Valid Values |
|------------|-----------|---------|-------------|--------------|
| `Color` | string | 'g' | Track color | 'r', 'g', 'b', 'w', 'c', 'm', 'y', 'k' |
| `Marker` | string | 'o' | Current position marker style | 'o' (circle), 's' (square), 't' (triangle), 'd' (diamond), '+', 'x', 'star' |
| `Line Width` | float | 2 | Width of track path line | Any positive number |
| `Marker Size` | float | 12 | Size of position marker | Any positive number |
| `Tail Length` | int | 0 | Number of recent frames to show (0 = all) | Any non-negative integer |
| `Visible` | bool | True | Track visibility | True/False |
| `Complete` | bool | False | Show complete track regardless of current frame | True/False |
| `Tracker` | string | (none) | Name of tracker/algorithm | Any string |

#### Example CSV Files

**Standard Format (Frames + Pixel Coordinates):**
```csv
Track,Frames,Rows,Columns,Color,Marker,Line Width,Marker Size,Tracker
"Tracker 0 - Track 0",15,181.87,79.08,g,o,2,12,"Tracker 0"
"Tracker 0 - Track 0",16,183.67,77.35,g,o,2,12,"Tracker 0"
"Tracker 0 - Track 0",17,185.23,75.89,g,o,2,12,"Tracker 0"
```

**Time-Based Format:**
```csv
Track,Times,Rows,Columns,Color,Marker,Line Width,Marker Size
"Track 1",2024-01-01T12:00:00.000000,181.87,79.08,g,o,2,12
"Track 1",2024-01-01T12:00:00.100000,183.67,77.35,g,o,2,12
"Track 1",2024-01-01T12:00:00.200000,185.23,75.89,g,o,2,12
```

**Geodetic Format:**
```csv
Track,Frames,Latitude,Longitude,Altitude,Color
"Track 1",0,40.0128,-105.0156,0.0,g
"Track 1",1,40.0129,-105.0157,0.0,g
"Track 1",2,40.0130,-105.0158,0.0,g
```

**Time + Geodetic Format:**
```csv
Track,Times,Latitude,Longitude,Altitude
"Track 1",2024-01-01T12:00:00.000000,40.0128,-105.0156,0.0
"Track 1",2024-01-01T12:00:00.100000,40.0129,-105.0157,0.0
"Track 1",2024-01-01T12:00:00.200000,40.0130,-105.0158,0.0
```

When loading tracks that require conversion (time-to-frame or geodetic-to-pixel), VISTA will automatically prompt you to select an appropriate imagery dataset with the required metadata.

### Detection Data (CSV Format)

Detection files represent point clouds of detected objects at each frame.

#### Required Columns

| Column Name | Data Type | Description | Example |
|------------|-----------|-------------|---------|
| `Detector` | string | Identifier for the detector/algorithm | "Detector 0" |
| `Frames` | float | Frame number where detection occurs | 0.0 |
| `Rows` | float | Row position in image coordinates | 146.01 |
| `Columns` | float | Column position in image coordinates | 50.27 |

#### Optional Columns

| Column Name | Data Type | Default | Description | Valid Values |
|------------|-----------|---------|-------------|--------------|
| `Color` | string | 'r' | Detection marker color | 'r', 'g', 'b', 'w', 'c', 'm', 'y', 'k' |
| `Marker` | string | 'o' | Marker style | 'o', 's', 't', 'd', '+', 'x', 'star' |
| `Marker Size` | float | 10 | Size of marker | Any positive number |
| `Line Thickness` | int | 2 | Thickness of marker outline | Any positive integer |
| `Visible` | bool | True | Detection visibility | True/False |

#### Example CSV
```csv
Detector,Frames,Rows,Columns,Color,Marker,Marker Size,Line Thickness
"Detector 0",0.0,146.01,50.27,r,o,10,2
"Detector 0",0.0,141.66,25.02,r,o,10,2
"Detector 0",1.0,148.23,51.15,r,o,10,2
"CFAR Detector",0.0,200.45,300.12,b,s,12,3
```

## Usage

### Launching the Application

If installed via pip:
```bash
vista
```

Or using Python module syntax:
```bash
python -m vista
```

### Loading Data

1. **Load Imagery**:
   - Menu: `File → Load Imagery` or Toolbar icon
   - Select HDF5 file with imagery data
   - Multiple imagery datasets supported (must have unique names)

2. **Load Tracks**:
   - Menu: `File → Load Tracks` or Toolbar icon
   - Select CSV file with track data
   - If tracks contain times or geodetic coordinates, select appropriate imagery for conversion
   - System detects coordinate system automatically

3. **Load Detections**:
   - Menu: `File → Load Detections` or Toolbar icon
   - Select CSV file with detection data

### Programmatic Usage

VISTA can be used programmatically to visualize data created in memory, which is useful for debugging workflows, interactive analysis, and Jupyter notebooks.

#### Basic Usage

```python
from vista.app import VistaApp
from vista.imagery.imagery import Imagery
import numpy as np

# Create imagery in memory
images = np.random.rand(10, 256, 256).astype(np.float32)
frames = np.arange(10)
imagery = Imagery(name="Debug Data", images=images, frames=frames)

# Launch VISTA with the imagery
app = VistaApp(imagery=imagery)
app.exec()
```

#### Loading Multiple Data Types

```python
from vista.app import VistaApp
from vista.imagery.imagery import Imagery
from vista.detections.detector import Detector
from vista.tracks.tracker import Tracker
from vista.tracks.track import Track
import numpy as np

# Create imagery
images = np.random.rand(50, 256, 256).astype(np.float32)
imagery = Imagery(name="Example", images=images, frames=np.arange(50))

# Create detections
detector = Detector(
    name="My Detections",
    frames=np.array([0, 1, 2, 5, 10]),
    rows=np.array([128.5, 130.2, 132.1, 135.0, 140.5]),
    columns=np.array([100.5, 102.3, 104.1, 106.5, 110.2]),
    color='r',
    marker='o',
    visible=True
)

# Create tracks
track = Track(
    name="Track 1",
    frames=np.array([0, 1, 2, 3, 4]),
    rows=np.array([128.5, 130.0, 131.5, 133.0, 134.5]),
    columns=np.array([100.5, 101.5, 102.5, 103.5, 104.5]),
    color='g',
    marker='s'
)
tracker = Tracker(name="My Tracker", tracks=[track])

# Launch VISTA with all data
app = VistaApp(imagery=imagery, detections=detector, tracks=tracker)
app.exec()
```

#### Loading Multiple Objects

You can pass lists of imagery, detections, or tracks:

```python
app = VistaApp(
    imagery=[imagery1, imagery2],
    detections=[detector1, detector2],
    tracks=[tracker1, tracker2]
)
app.exec()
```

#### Jupyter Notebook Usage

In Jupyter notebooks, you may need to handle the event loop differently depending on your environment. The basic usage works in most cases:

```python
# In a Jupyter notebook cell
from vista.app import VistaApp
import numpy as np
from vista.imagery.imagery import Imagery

images = np.random.rand(10, 256, 256).astype(np.float32)
imagery = Imagery(name="Notebook Data", images=images, frames=np.arange(10))

app = VistaApp(imagery=imagery)
app.exec()  # Window will open; close it to continue notebook execution
```

**Example Script:** See `scripts/example_programmatic_loading.py` for a complete working example that creates synthetic imagery with a moving bright spot, detections, and tracks.

### Creating Manual Tracks

1. **Enable Track Creation Mode**:
   - Click the "Create Track" icon in the toolbar
   - A track creation dialog will appear

2. **Create Track Points**:
   - Click on the imagery to add points to the current track
   - Each click creates a new point at the current frame
   - Points are automatically associated with the current frame

3. **Navigate and Add Points**:
   - Change frames using playback controls or arrow keys
   - Continue clicking to add points at different frames
   - The system tracks which frame each point belongs to

4. **Finish Track**:
   - Click "Finish Track" in the dialog to save
   - The new track is added to the Data Manager
   - Track is automatically saved when the dialog is closed

### Detection Algorithms

#### Running CFAR Detector

**Menu Path:** `Detections → CFAR`

**Parameters:**
- **Detection Threshold**: SNR threshold for detections (default: 3.0)
- **Guard Window Radius**: Size of guard region around test cell (default: 2)
- **Background Window Radius**: Size of background estimation region (default: 5)
- **Detection Mode**: Controls what type of objects to detect (default: 'above')
  - **'above'**: Detect bright objects (pixel > mean + threshold × std)
  - **'below'**: Detect dark objects (pixel < mean - threshold × std)
  - **'both'**: Detect absolute deviations (|pixel - mean| > threshold × std)

**Output:** Creates a new detector with CFAR detections

#### Running Simple Threshold Detector

**Menu Path:** `Detections → Simple Threshold`

**Parameters:**
- **Threshold**: Intensity threshold value (default: 5.0)
- **Detection Mode**: Controls what type of objects to detect (default: 'above')
  - **'above'**: Detect positive values (pixel > threshold)
  - **'below'**: Detect negative values (pixel < -threshold, useful for background-removed imagery)
  - **'both'**: Detect absolute values (|pixel| > threshold)

**Output:** Creates a new detector with threshold-based detections

### Tracking Algorithms

All tracking algorithms take detections as input and produce tracks as output.

#### Simple Tracker

**Menu Path:** `Tracking → Simple Tracker`

**Description:** Nearest-neighbor association with maximum distance threshold

**Parameters:**
- **Maximum Distance**: Maximum pixel distance for associating detections to tracks (default: 50.0)

#### Kalman Filter Tracker

**Menu Path:** `Tracking → Kalman Tracker`

**Description:** State estimation with constant velocity motion model

**Parameters:**
- **Maximum Distance**: Maximum distance for data association (default: 50.0)
- **Process Noise**: Motion model uncertainty (default: 1.0)
- **Measurement Noise**: Detection position uncertainty (default: 5.0)

#### Network Flow Tracker

**Menu Path:** `Tracking → Network Flow Tracker`

**Description:** Global optimization using min-cost flow

**Parameters:**
- **Maximum Distance**: Maximum distance for associations (default: 50.0)
- **Miss Penalty**: Cost for missing detections (default: 10.0)
- **False Alarm Penalty**: Cost for false alarm detections (default: 10.0)

#### Tracklet Tracker

**Menu Path:** `Tracking → Tracklet Tracker`

**Description:** Two-stage hierarchical tracker optimized for high false alarm scenarios (100:1 or higher)

**Stage 1 Parameters (Tracklet Formation):**
- **Initial Search Radius**: Maximum distance for forming tracklets (default: 10.0 pixels)
- **Max Velocity Change**: Maximum allowed velocity change for smooth motion (default: 5.0 pixels/frame)
- **Min Tracklet Length**: Minimum detections required to save a tracklet (default: 3)
- **Max Consecutive Misses**: Maximum frames without detection before ending tracklet (default: 2)
- **Min Detection Rate**: Minimum hit-to-age ratio for valid tracklets (default: 0.6)

**Stage 2 Parameters (Tracklet Linking):**
- **Max Linking Gap**: Maximum frame gap when linking tracklets (default: 10 frames)
- **Linking Search Radius**: Maximum distance for linking tracklets (default: 30.0 pixels)

**Best for:** Scenarios with smooth target motion and high clutter/false alarm rates

### Image Enhancement

#### Coaddition

**Menu Path:** `Image Processing → Enhancement → Coaddition`

**Description:** Temporal averaging for noise reduction and SNR improvement

**Parameters:**
- **Number of Frames**: Number of frames to average (default: 5)

**Output:** New imagery dataset with enhanced frames

### Background Removal

#### Temporal Median

**Menu Path:** `Image Processing → Background Removal → Temporal Median`

**Parameters:**
- **Background Frames**: Number of frames on each side for median (default: 5)
- **Temporal Offset**: Frames to skip around current frame (default: 2)
- **Start Frame / End Frame**: Frame range to process
- **AOI Selection**: Optional area of interest to process (default: Full Image)

**Output:** New imagery dataset with background removed

#### Robust PCA

**Menu Path:** `Image Processing → Background Removal → Robust PCA`

**Description:** Decomposes imagery into low-rank (background) and sparse (foreground) components using Principal Component Pursuit (PCP).

**Parameters:**
- **Lambda Parameter**: Sparsity parameter controlling background/foreground separation (default: auto-calculated as 1/sqrt(max(m,n)))
- **Tolerance**: Convergence tolerance (default: 1e-7)
- **Max Iterations**: Maximum optimization iterations (default: 1000)
- **Start Frame / End Frame**: Frame range to process
- **AOI Selection**: Optional area of interest to process (default: Full Image)
- **Add Background**: Option to add background component to data manager
- **Add Foreground**: Option to add foreground component to data manager

**Output:** Two new imagery datasets - low-rank background and sparse foreground components

### Image Treatments

#### Bias Removal

**Menu Path:** `Image Processing → Treatments → Bias Removal`

**Description:** Apply bias/dark frame correction using sensor calibration data

**Parameters:**
- **AOI Selection**: Optional area of interest to process (default: Full Image)

**Requirements:**
- Imagery must contain `bias_images` and `bias_image_frames` datasets

**Output:** New imagery dataset with bias frames subtracted

#### Non-Uniformity Correction (NUC)

**Menu Path:** `Image Processing → Treatments → Non-Uniformity Correction`

**Description:** Apply flat-field gain correction to correct pixel-to-pixel response variations

**Parameters:**
- **AOI Selection**: Optional area of interest to process (default: Full Image)

**Requirements:**
- Imagery must contain `uniformity_gain_images` and `uniformity_gain_image_frames` datasets

**Output:** New imagery dataset with uniformity correction applied

### Playback Controls

| Control | Description |
|---------|-------------|
| **Play/Pause** | Start/stop playback |
| **FPS Slider** | Adjust playback speed (-100 to +100 FPS, negative for reverse) |
| **Frame Slider** | Navigate to specific frame |
| **Bounce Mode** | Toggle looping playback between current frame range |
| **Arrow Keys** | Previous/Next frame navigation |
| **A/D Keys** | Previous/Next frame navigation (alternative) |

### Keyboard Shortcuts

- **Left Arrow / A**: Previous frame
- **Right Arrow / D**: Next frame
- **Space**: Play/Pause (when playback controls have focus)

## Generating Test Data

Use the simulation module to generate test datasets with various configurations:

```python
from vista.simulate.simulation import Simulation
import numpy as np

# Standard simulation
sim = Simulation(
    name="Test Simulation",
    frames=50,
    rows=256,
    columns=256,
    num_trackers=1
)
sim.simulate()
sim.save("test_data")

# Simulation with times and geodetic coordinates
sim = Simulation(
    name="Advanced Simulation",
    frames=50,
    enable_times=True,
    frame_rate=10.0,
    start_time=np.datetime64('2024-01-01T12:00:00', 'us'),
    enable_geodetic=True,
    center_lat=40.0,
    center_lon=-105.0,
    pixel_to_deg_scale=0.0001
)
sim.simulate()

# Simulation with sensor calibration data
sim = Simulation(
    name="Calibrated Simulation",
    frames=100,
    rows=256,
    columns=256,
    # Enable sensor calibration features
    enable_bias_images=True,
    num_bias_images=2,
    bias_value_range=(0.5, 2.0),
    enable_uniformity_gain=True,
    num_uniformity_gains=2,
    enable_bad_pixel_masks=True,
    num_bad_pixel_masks=2,
    bad_pixel_fraction=0.01,
    enable_radiometric_gain=True,
    radiometric_gain_mean=1.0,
    radiometric_gain_std=0.05
)
sim.simulate()
sim.save("calibrated_data")

# Simulation with Earth background
sim = Simulation(
    name="Earth Background Simulation",
    frames=50,
    rows=256,
    columns=256,
    enable_earth_background=True,
    earth_jitter_std=2.0,  # Platform jitter in pixels
    earth_scale=1.0  # Scale factor for Earth image intensity
)
sim.simulate()
sim.save("earth_sim")

# Save with different coordinate systems
sim.save("time_based", save_times_only=True)  # Times only
sim.save("geodetic", save_geodetic_tracks=True)  # Geodetic only
sim.save("time_geodetic", save_geodetic_tracks=True, save_times_only=True)  # Both
```

### Pre-configured Test Scenarios

Use the example scripts to generate comprehensive test data:

**Generate all coordinate system variations:**
```bash
python scripts/example_geodetic_time.py
```

This creates 5 directories with different test configurations:
- `sim_normal/` - Standard tracks (Frames + Rows/Columns)
- `sim_times_only/` - Time-based tracks
- `sim_geodetic_only/` - Geodetic tracks
- `sim_times_geodetic/` - Time + Geodetic
- `sim_all_features/` - All features combined

**Generate comprehensive test data with all features:**
```bash
python scripts/create_comprehensive_data.py
```

This creates 5 directories demonstrating different feature sets:
- `sim_basic/` - Basic simulation with minimal features
- `sim_with_times/` - Time-based metadata
- `sim_with_geodetic/` - Geodetic coordinate conversion
- `sim_with_calibration/` - Sensor calibration data (bias, gain, bad pixels, radiometric gain)
- `sim_all_features/` - Complete feature set including Earth background, calibration data, times, and geodetic support

## Project Structure

```
Vista/
├── vista/
│   ├── app.py                       # Main application entry point
│   ├── widgets/
│   │   ├── core/                    # Core UI components
│   │   │   ├── main_window.py       # Main window with menu/toolbar
│   │   │   ├── imagery_viewer.py    # Image display with pyqtgraph
│   │   │   ├── playback_controls.py # Playback UI
│   │   │   ├── imagery_selection_dialog.py  # Imagery picker for conversions
│   │   │   └── data/
│   │   │       ├── data_manager.py  # Data panel with editing
│   │   │       └── data_loader.py   # Background loading thread
│   │   ├── detectors/               # Detection algorithm widgets
│   │   │   ├── cfar_widget.py       # CFAR detector UI
│   │   │   └── simple_threshold_widget.py  # Threshold detector UI
│   │   ├── trackers/                # Tracking algorithm widgets
│   │   │   ├── simple_tracking_dialog.py
│   │   │   ├── kalman_tracking_dialog.py
│   │   │   ├── network_flow_tracking_dialog.py
│   │   │   └── tracklet_tracking_dialog.py
│   │   ├── background_removal/      # Background removal widgets
│   │   │   ├── temporal_median_widget.py
│   │   │   └── robust_pca_dialog.py
│   │   ├── enhancement/             # Enhancement widgets
│   │   │   └── coaddition_widget.py
│   │   └── treatments/              # Sensor calibration widgets
│   │       ├── bias_removal.py
│   │       └── non_uniformity_correction.py
│   ├── imagery/                     # Image data models
│   │   └── imagery.py               # Imagery class with geodetic support
│   ├── tracks/                      # Track data models
│   │   ├── track.py                 # Track class with coordinate conversion
│   │   └── tracker.py               # Tracker container
│   ├── detections/                  # Detection data models
│   │   └── detector.py              # Detector class
│   ├── algorithms/                  # Image processing algorithms
│   │   ├── background_removal/
│   │   │   ├── temporal_median.py
│   │   │   └── robust_pca.py
│   │   ├── detectors/
│   │   │   ├── cfar.py
│   │   │   └── threshold.py
│   │   ├── trackers/
│   │   │   ├── simple_tracker.py
│   │   │   ├── kalman_tracker.py
│   │   │   ├── network_flow_tracker.py
│   │   │   └── tracklet_tracker.py
│   │   └── enhancement/
│   │       └── coadd.py
│   ├── aoi/                         # Area of Interest support
│   │   └── aoi.py                   # AOI data model
│   ├── sensors/                     # Sensor calibration models
│   │   ├── sensor.py                # Base sensor class
│   │   └── sampled_sensor.py        # Sampled sensor implementation
│   ├── utils/                       # Utilities
│   │   ├── color.py                 # Color conversion helpers
│   │   ├── random_walk.py           # Random walk simulation
│   │   ├── time_mapping.py          # Time-to-frame conversion
│   │   └── geodetic_mapping.py      # Geodetic-to-pixel conversion
│   ├── simulate/                    # Data generation utilities
│   │   ├── simulation.py            # Synthetic data simulator
│   │   └── data.py                  # Earth image and other simulation data
│   └── icons/                       # Application icons
├── scripts/                         # Example scripts
│   ├── example_geodetic_time.py     # Generate coordinate system test data
│   ├── create_comprehensive_data.py # Generate comprehensive test data with all features
│   └── example_programmatic_loading.py  # Programmatic API usage example
├── data/                            # Example datasets (gitignored)
├── pyproject.toml                   # Package configuration and dependencies
└── readme.md                        # This file
```

## Architecture

### Design Principles

1. **Data-View Separation**: Imagery, Track, and Detector classes are independent data containers
2. **Async Loading**: Background threads prevent UI freezing during file I/O
3. **Signal-Slot Communication**: PyQt signals coordinate between components
4. **Pre-Compute Expensive Operations for Speed**: Image histograms are computed for all images rather than computed on the fly. 
5. **Automatic Conversion**: Transparent coordinate and time conversion with user prompts
6. **Extensibility**: Modular algorithm framework for custom processing

### Key Classes

- **`Imagery`**: Image data with optional times and geodetic polynomials
- **`Track`**: Single trajectory with automatic coordinate conversion
- **`Tracker`**: Container for multiple tracks
- **`Detector`**: Point cloud detection class with styling
- **`ImageryViewer`**: Visualization widget with interactive tools
- **`PlaybackControls`**: Temporal control widget
- **`DataManagerPanel`**: Data editing and management widget

## Performance Considerations

- **Chunked HDF5**: Use chunked storage for large imagery files to enable progressive loading
- **Lazy Computations**: Coordinate conversions computed on-demand
- **Efficient Playback**: Bounce mode uses efficient frame looping
- **Background Processing**: All file I/O and algorithms run in background threads
- **Memory Management**: Large datasets may require significant memory for processing
- **Frame Synchronization**: Assumes synchronized frame numbers across imagery datasets

## Troubleshooting

### Track Loading Issues

**"No imagery with times defined"**
- Ensure imagery contains `unix_time` and `unix_fine_time` datasets
- Load imagery before loading time-based tracks

**"No imagery with geodetic conversion capability"**
- Ensure imagery contains all four polynomial datasets
- Check that polynomials have correct shape `(N_frames, 15)`

**"Track has times but no frames"**
- Imagery required for time-to-frame mapping
- Verify imagery times overlap with track times

### Coordinate Conversion Issues

**Tracks appear in wrong location**
- Verify polynomial coefficients are correct
- Check that geodetic coordinates are within imagery coverage area
- Ensure frame synchronization across imagery datasets

### General Issues

**Duplicate Imagery Names**
- Each loaded imagery dataset must have a unique name

**Slow Playback**
- Reduce FPS slider value
- Use smaller imagery datasets or chunked HDF5

**Out of Memory**
- Close unused imagery datasets
- Reduce algorithm parameter values (e.g., background frames)

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## License

MIT License

## Acknowledgments

VISTA uses the following open-source libraries:
- PyQt6 for the GUI framework
- pyqtgraph for high-performance visualization
- NumPy and pandas for data processing
- astropy for geodetic coordinate handling
- scikit-learn for machine learning algorithms
- cvxpy for optimization (Network Flow Tracker)
- h5py for HDF5 file support
- Pillow for image processing (Earth background simulation)
