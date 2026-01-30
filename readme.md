# VISTA - Visual Imagery Software Tool for Analysis
## Now an open-source MIT-licensed Awetomaton project for the GEOINT community

![Logo](/vista/icons/logo-small.jpg)

VISTA is a PyQt6-based desktop application for viewing, analyzing, and managing multi-frame imagery datasets along with associated detection and track overlays. It's designed for scientific and analytical workflows involving temporal image sequences with support for time-based and geodetic coordinate systems, sensor calibration data, and radiometric processing.

![Version](https://img.shields.io/badge/version-1.8.2-blue)
![Python](https://img.shields.io/badge/python-3.13+-blue)
![License](https://img.shields.io/badge/license-MIT-green)
[![PyPI](https://img.shields.io/badge/pypi-vista--imagery-blue)](https://pypi.org/project/vista-imagery/)

**Documentation**: https://awetomaton.github.io/VISTA/

**Source Code**: https://github.com/awetomaton/VISTA

## Watch the demo!
[![Watch the demo](docs/source/_static/images/vista_demo_thumbnail.png)](https://www.youtube.com/watch?v=9eRo5S4yLTs)

## Important Assumptions

**Frame Synchronization Across Imagery Datasets per Sensor:**

VISTA assumes that all loaded imagery datasets for a given sensor are temporally synchronized. Specifically:

- Frame numbers represent the same temporal moments across all imagery
- Frame 10 in one imagery dataset corresponds to the exact same time as frame 10 in any other imagery for the same sensor
- This assumption is critical for proper visualization and analysis when multiple imagery datasets are loaded simultaneously
- When loading tracks with time-based mapping, the selected imagery's time-to-frame mapping is used as the reference

## Features

### Multi-Frame Imagery Viewer
- Display full image sequences from HDF5 files with optional time and geodetic metadata
- Support for multiple simultaneous imagery datasets (must have unique names)
- **Sensor calibration data support**: bias/dark frames, uniformity gain corrections, bad pixel masks, and radiometric gain values
- Interactive image histogram with dynamic range adjustment
- Frame-by-frame navigation with keyboard shortcuts
- **Interactive AOI (Area of Interest) Drawing**: Right-click context menu to draw rectangular regions for focused processing
- **Geolocation tooltip**: Display latitude/longitude coordinates when hovering over imagery (requires geolocation data)
- **Pixel value tooltip**: Display pixel intensity values when hovering over imagery

### Advanced Track Support
- **Multiple coordinate systems**:
  - Pixel coordinates (Row/Column)
  - Geodetic coordinates (Latitude/Longitude/Altitude) with automatic conversion including altitude support
  - Time-based or frame-based indexing
- **Automatic coordinate conversion**:
  - Times → Frames using imagery timestamps
  - Geodetic coordinates (Lat/Lon/Alt) → Pixel coordinates using ray casting
- **Priority system**: Row/Column takes precedence over geodetic; Frames takes precedence over times
- **Manual track creation and editing**:
  - Click-to-create tracks with automatic frame tracking
  - Edit existing tracks by adding/removing points
  - **Intelligent point selection modes** for precise point placement:
    - **Verbatim**: Use exact clicked location
    - **Peak**: Automatically snap to brightest pixel within configurable radius
    - **CFAR**: Use CFAR detection algorithm to find signal blob centroid with full parameter control
  - Point selection settings persist across sessions
- Track path rendering with customizable colors and line widths
- Current position markers with selectable styles
- Tail length control (show full history or last N frames)
- Complete track visualization (override current frame)
- Track length calculation (cumulative distance)

### Detection Overlay
- Load detection CSV files with multiple detector support
- **Manual detection creation and editing**: Click-to-add detection points at current frame with intelligent point selection modes (Verbatim, Peak, CFAR)
- Customizable markers (circle, square, triangle, diamond, plus, cross, star)
- Adjustable colors, marker sizes, and line thickness
- Show/hide individual detectors
- Detection styling persistence across sessions
- Detection selection and deletion

### Track and Detection Labeling
- **Flexible labeling system**: Assign custom text labels to individual tracks and detections for classification and organization
- **Label management**: Create, rename, and delete labels through the centralized Labels Manager
- **Bulk label assignment**: Apply labels to multiple tracks or detections simultaneously from the data manager
- **Label-based filtering**: Filter tracks and detections by label in the data manager tables for focused analysis
- **Label persistence**: Labels are saved with data and persist across sessions
- **Classification workflows**: Support for analyst review, ground truth annotation, and multi-class classification tasks
- **Menu Access**: `Labels` menu item for centralized label management

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
- Tabbed interface for managing Imagery, Tracks, Detections, AOIs, and Features
- Bulk property editing (visibility, colors, markers, sizes, line thickness)
- **Label assignment and filtering**: Apply labels to tracks/detections and filter by label
- Column filtering and sorting for tracks and detections
- Real-time updates synchronized with visualization
- Track editing with complete track toggle

### Feature Support (Shapefiles and Placemarks)
- **Shapefile Import**: Load ESRI shapefiles with polygons, polylines, points, and multipoints
- **Placemark Creation**: Create point markers using pixel or geodetic coordinates
- **Dual Coordinate Systems**: Automatic conversion between pixel and geodetic coordinates when geolocation is available
- **Feature Management**: Toggle visibility, rename, and delete features
- **Persistent Overlays**: Features don't change with time and display across all frames

### Geolocation Support
- **Attitude Reference Frame (ARF) based geolocation** for robust pixel↔geodetic coordinate conversion
- Supports targets at altitude (not just ground-projected tracks)
- Gracefully handles off-Earth pixels (returns NaN for sky/space pixels)
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
git clone https://github.com/awetomaton/VISTA.git
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

**ARF-Based Geolocation Data (Attitude Reference Frame):**

The geolocation system uses an Attitude Reference Frame (ARF) to convert between pixel coordinates and geodetic coordinates via intermediate angular coordinates (azimuth/elevation). This approach supports off-Earth pixels and targets at altitude.

- **`pointing`**: Shape `(3, N_frames)` - Sensor pointing vector in ECEF coordinates (unit vector per frame)
- **`poly_pixel_to_arf_azimuth`**: Shape `(N_coefficients,)` - Convert pixel row/col to ARF azimuth angle (radians)
- **`poly_pixel_to_arf_elevation`**: Shape `(N_coefficients,)` - Convert pixel row/col to ARF elevation angle (radians)
- **`poly_arf_to_row`**: Shape `(N_coefficients,)` - Convert ARF azimuth/elevation to pixel row
- **`poly_arf_to_col`**: Shape `(N_coefficients,)` - Convert ARF azimuth/elevation to pixel column
- **`frames`**: Shape `(N_frames,)` - Frame indices for sensor position/pointing data

The polynomials use an arbitrary-order 2D format where the number of coefficients determines the polynomial order. For an order-N polynomial, there are (N+1)(N+2)/2 coefficients arranged as:
`f(x,y) = c0 + c1*x + c2*y + c3*x² + c4*xy + c5*y² + c6*x³ + ...`

Additionally, the sensor requires position and time information:
- **`sensor_positions`**: Shape `(3, N_samples)` - Sensor positions in ECEF coordinates (meters)
- **`sensor_times`**: Shape `(N_samples,)` - Timestamps for sensor positions (microseconds since epoch)

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
├── geolocation/ (Group) [optional]
│   ├── pointing (Dataset)
│   │   └── Shape: (3, 100)
│   ├── poly_pixel_to_arf_azimuth (Dataset)
│   │   └── Shape: (15,)
│   ├── poly_pixel_to_arf_elevation (Dataset)
│   │   └── Shape: (15,)
│   ├── poly_arf_to_row (Dataset)
│   │   └── Shape: (15,)
│   ├── poly_arf_to_col (Dataset)
│   │   └── Shape: (15,)
│   ├── frames (Dataset)
│   │   └── Shape: (100,)
│   ├── sensor_positions (Dataset)
│   │   └── Shape: (3, 1)
│   └── sensor_times (Dataset)
│       └── Shape: (1,)
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

    # Optional: Add ARF-based geolocation data
    # For generating proper geolocation data with realistic sensor models,
    # use the Simulation class with enable_geodetic=True (see "Generating Test Data")
    #
    # Manual creation requires:
    # - Sensor position(s) in ECEF coordinates
    # - Sensor pointing vector(s) in ECEF coordinates
    # - Polynomials mapping pixel↔ARF angles (fitted from sensor geometry)
    geo_group = f.create_group("geolocation")
    # ... see Simulation class for complete implementation
```

#### Understanding the Attitude Reference Frame (ARF)

VISTA uses an Attitude Reference Frame (ARF) based approach for converting between pixel coordinates and geodetic (latitude/longitude/altitude) coordinates. This approach offers significant advantages over direct polynomial mappings:

**Why ARF?**

Traditional approaches use polynomials to directly map pixel coordinates to latitude/longitude. This has two major limitations:
1. **Off-Earth pixels**: When part of the image shows sky or space (no Earth intersection), direct polynomials produce invalid results
2. **Altitude handling**: Direct lat/lon polynomials assume ground-level targets and cannot properly back-project tracks at altitude

**How ARF Works**

The ARF is a local Cartesian coordinate system centered at the sensor where the X-axis points along the sensor's boresight (pointing direction). The conversion process works as follows:

**Pixel → Geodetic (Forward Conversion):**
1. Convert pixel (row, col) to ARF angles (azimuth, elevation) using polynomials
2. Convert ARF angles to a unit direction vector in ARF coordinates
3. Transform the direction vector from ARF to ECEF using the sensor pointing
4. Ray-cast from sensor position along this direction to find Earth intersection
5. If the ray misses Earth, return NaN (graceful handling of off-Earth pixels)
6. Convert ECEF intersection point to geodetic coordinates (lat, lon, alt)

**Geodetic → Pixel (Inverse Conversion):**
1. Convert geodetic coordinates (lat, lon, alt) to ECEF position
2. Compute direction vector from sensor position to target
3. Transform direction vector from ECEF to ARF using sensor pointing
4. Convert direction vector to ARF angles (azimuth, elevation)
5. Convert ARF angles to pixel coordinates (row, col) using inverse polynomials

**Key Components:**

- **Sensor Position**: ECEF coordinates (meters) of the sensor at each time/frame
- **Pointing Vector**: Unit vector in ECEF indicating where the sensor boresight points
- **ARF Transform**: Built from the pointing vector; transforms between ECEF and ARF coordinates
- **Polynomials**: Map between pixel coordinates and ARF angles (azimuth, elevation)

**Altitude Support:**

When converting geodetic→pixel, the target's altitude is respected. The system computes where a target at the specified altitude would appear in the image, rather than assuming ground projection.

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
Track,Frames,Latitude (deg),Longitude (deg),Altitude (km),Color
"Track 1",0,40.0128,-105.0156,0.0,g
"Track 1",1,40.0129,-105.0157,0.0,g
"Track 1",2,40.0130,-105.0158,0.0,g
```

**Time + Geodetic Format:**
```csv
Track,Times,Latitude (deg),Longitude (deg),Altitude (km)
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

### Creating and Editing Manual Tracks and Detections

VISTA provides powerful tools for manual track and detection creation with intelligent point placement.

#### Point Selection Modes

When creating or editing tracks/detections, a **Point Selection Dialog** appears with three modes for determining point locations:

**1. Verbatim Mode**
- Uses the exact pixel location where you click
- Best for: Precise manual placement with full control
- No automatic adjustments

**2. Peak Mode**
- Automatically finds the brightest pixel within a configurable radius of your click
- **Configurable Parameters:**
  - Search Radius: 1-50 pixels (default: 5)
- **Best for:** Bright objects like stars, satellites, or aircraft
- Points are placed at pixel center (+0.5 offset) for sub-pixel accuracy

**3. CFAR Mode**
- Runs CFAR detection algorithm in a local region around your click
- Finds the centroid of the detected signal blob
- **Configurable Parameters:**
  - Search Radius: 10-200 pixels (defines local processing area)
  - Background Radius: Outer radius for neighborhood statistics
  - Ignore Radius: Inner radius excluded from statistics
  - Threshold Deviation: Number of standard deviations for detection
  - Annulus Shape: Circular or Square neighborhood
  - Detection Mode: Above (bright), Below (dark), or Both
  - Includes visual preview of CFAR annulus
- **Best for:** Precise blob centroid location in varying backgrounds
- All settings persist across sessions

#### Creating Manual Tracks

1. **Enable Track Creation Mode**:
   - Click the "Create Track" icon in the toolbar
   - The Point Selection Dialog appears automatically

2. **Configure Point Selection**:
   - Choose your preferred mode (Verbatim, Peak, or CFAR) by selecting the appropriate tab
   - Adjust parameters as needed
   - Settings are saved and remembered for future use

3. **Create Track Points**:
   - Click on the imagery to add points to the current track
   - The point location is refined based on your selected mode
   - Each click creates a new point at the current frame
   - Click near an existing point to remove it

4. **Navigate and Add Points**:
   - Change frames using playback controls, arrow keys, or **A**/**D** keys
   - Continue clicking to add points at different frames
   - The system tracks which frame each point belongs to
   - Temporary visualization shows your track as you build it

5. **Finish Track**:
   - Click "Finish Track" in the dialog to save
   - The new track is added to the Data Manager
   - Point Selection Dialog closes automatically

#### Editing Existing Tracks

1. **Enable Track Editing Mode**:
   - In the Data Manager's Tracks panel, select a track
   - Click the "Edit Track" button
   - The Point Selection Dialog appears with current track data

2. **Modify Track Points**:
   - Navigate to any frame and click to add new points
   - Click near existing points to remove them
   - Use your preferred point selection mode for precise placement

3. **Finish Editing**:
   - Click "Finish Editing" to save changes
   - Updated track appears in the Data Manager

#### Creating and Editing Manual Detections

The same workflow applies to detections:

1. **Create Detections**: Use "Create Detection" toolbar icon
2. **Edit Detections**: Select detector in Data Manager and click "Edit Detection"
3. **Add Multiple Points**: Unlike tracks, you can add multiple detection points per frame
4. **Point Selection**: All three modes (Verbatim, Peak, CFAR) work identically for detections

### Managing Track and Detection Labels

VISTA provides a flexible labeling system for organizing, classifying, and filtering tracks and detections. This is useful for ground truth annotation, classification workflows, and analyst review.

#### Opening the Labels Manager

**Menu Path:** `Labels` (in menu bar)

The Labels Manager provides centralized control over all labels in your project:
- **View all labels**: See all labels currently defined in the project
- **Create new labels**: Add custom labels for your classification scheme
- **Rename labels**: Update label names (automatically updates all assigned labels)
- **Delete labels**: Remove labels (automatically removes from all assigned tracks/detections)
- **See label usage**: View which tracks and detections are assigned each label

#### Assigning Labels to Tracks

1. **Open the Data Manager**: Ensure the Tracks tab is selected
2. **Select tracks**: Click on one or more tracks in the table (use Ctrl/Cmd for multiple selection)
3. **Assign label**:
   - Right-click on selected tracks
   - Choose "Assign Label" from context menu
   - Select an existing label or create a new one
4. **Verify assignment**: The "Label" column shows the assigned label for each track

#### Assigning Labels to Detections

1. **Open the Data Manager**: Ensure the Detections tab is selected
2. **Select detections**: Click on one or more detections in the table
3. **Assign label**: Use the same workflow as tracks (right-click → "Assign Label")
4. **Bulk assignment**: Select multiple detections to assign the same label to all

#### Filtering by Label

**In the Tracks Panel:**
1. Click the "Label" column header dropdown filter
2. Select which labels to display (supports multiple label selection)
3. Table updates to show only tracks with selected labels
4. Clear filter to show all tracks again

**In the Detections Panel:**
1. Use the same filtering workflow as tracks
2. Quickly isolate detections by classification
3. Useful for reviewing specific object types or classes

#### Label Persistence

- Labels are saved automatically with track and detection data
- When exporting tracks/detections to CSV, labels are included in the "Label" column
- When loading CSV files with a "Label" column, labels are automatically imported
- Labels persist across VISTA sessions

#### Pre-configured Labels via Environment Variable

The `VISTA_LABELS` environment variable allows you to pre-configure labels that will be automatically loaded when VISTA starts. This is useful for:
- Establishing consistent labeling schemes across teams
- Setting up standardized classification workflows
- Automating label setup in scripts or CI/CD pipelines

**Supported Formats:**

1. **CSV File Path**: Point to a CSV file containing labels
   ```bash
   export VISTA_LABELS="/path/to/labels.csv"
   ```

   CSV format with header:
   ```csv
   label
   Aircraft
   Satellite
   Bird
   Debris
   ```

   Or simple format (one label per line):
   ```csv
   Aircraft
   Satellite
   Bird
   Debris
   ```

2. **JSON File Path**: Point to a JSON file containing an array of labels
   ```bash
   export VISTA_LABELS="/path/to/labels.json"
   ```

   JSON format:
   ```json
   ["Aircraft", "Satellite", "Bird", "Debris"]
   ```

3. **Comma-Separated Values**: Specify labels directly in the environment variable
   ```bash
   export VISTA_LABELS="Aircraft,Satellite,Bird,Debris"
   ```

**Behavior:**
- Fixture labels are merged with any existing labels in VISTA's settings
- Duplicate labels are ignored (case-insensitive comparison)
- Once merged, labels are persisted to settings and remain available even if the environment variable is removed
- Labels can still be managed (added/deleted) through the Labels Manager UI

#### Common Labeling Workflows

**Ground Truth Annotation:**
1. Load automated tracker results
2. Review each track and assign labels: "True Positive", "False Positive", "Missed Detection"
3. Filter by label to review each category
4. Export labeled data for algorithm validation

**Multi-Class Classification:**
1. Create labels for each object class: "Aircraft", "Satellite", "Bird", "Debris"
2. Assign labels to detections or tracks as you review
3. Use label filtering to focus on specific classes
4. Generate classification statistics by counting labels

**Analyst Review:**
1. Create labels for review status: "Reviewed", "Needs Review", "Uncertain"
2. Assign labels during manual review process
3. Filter by "Needs Review" to see remaining work
4. Track review progress through label counts

### Drawing Areas of Interest (AOI)

AOIs allow you to define rectangular regions for focused algorithm processing (background removal, treatments, etc.).

**Creating an AOI:**
1. **Access the Draw AOI Tool**:
   - Right-click on the imagery viewer
   - Select "Draw AOI" from the context menu

2. **Draw the Rectangle**:
   - Click and drag to define the rectangular region
   - The AOI is created immediately upon mouse release

3. **Use AOI in Algorithms**:
   - Many algorithms (Temporal Median, Robust PCA, Bias Removal, NUC) support AOI selection
   - Select your AOI from the dropdown in the algorithm dialog
   - Processing is restricted to the selected region
   - Output imagery inherits the AOI boundaries (with row/column offsets)

**Managing AOIs:**
- AOIs appear in the Data Manager
- Toggle visibility to show/hide AOI rectangles on the display
- Delete unwanted AOIs from the Data Manager

### Working with Features (Shapefiles and Placemarks)

VISTA supports persistent feature overlays that don't change with time, including shapefiles and placemarks.

#### Loading Shapefiles

**Menu Path:** `File → Load Shapefile`

**Supported Geometry Types:**
- Polygons (including multi-part polygons with holes)
- Polylines (including multi-part polylines)
- Points and MultiPoints
- All Z and M variants (PolygonZ, PolyLineZ, etc.)

**Workflow:**
1. Select one or more `.shp` files from the file dialog
2. Shapefiles appear in the **Features** tab of the Data Manager
3. Each shapefile is displayed as a separate feature with all its geometries

**Requirements:**
- The `pyshp` library is required: `pip install pyshp`
- Shapefile coordinates should be in pixel space (row/column) to match imagery

#### Creating Placemarks

Placemarks are point features that mark specific locations in your imagery using either pixel or geodetic coordinates.

**Menu Path:** Features tab → **"Create Placemark"** button

**Creating a Placemark:**

1. **Load Imagery First**: Placemarks require loaded imagery
2. **Open Create Placemark Dialog**:
   - Go to the **Features** tab in the Data Manager
   - Click the **"Create Placemark"** button

3. **Enter Placemark Details**:
   - **Name**: Descriptive name for the placemark (e.g., "Building A", "GCP-1")
   - **Coordinate System**: Choose between two options

4. **Option A: Using Pixel Coordinates (Row/Column)**
   - Select "Pixel (Row/Column)" radio button
   - Enter row and column coordinates
   - If geolocation is available, geodetic coordinates are automatically calculated

5. **Option B: Using Geodetic Coordinates (Lat/Lon/Alt)**
   - **Note:** Only available if imagery has geolocation capability (`can_geolocate`)
   - Select "Geodetic (Lat/Lon/Alt)" radio button
   - Enter latitude (degrees), longitude (degrees), and altitude (km)
   - Coordinates are automatically converted to pixel coordinates for display
   - If location is outside the sensor's field of view, a warning is displayed

6. **Save**: Click OK to create the placemark

**Placemark Display:**
- Circular marker (size 12) at the specified location
- Text label showing the placemark name above the marker
- Default color: yellow (customizable via feature.color)

**Stored Data:**
Each placemark stores both coordinate systems (when available):
- **row/col**: Pixel coordinates (always stored)
- **lat/lon/alt**: Geodetic coordinates (stored when geolocation is available)

**Use Cases:**
- **Marking Points of Interest**: Identify specific features in imagery
- **Ground Control Points**: Mark known geodetic locations for calibration
- **Target Locations**: Mark locations for analysis or tracking
- **Reference Points**: Create landmarks for navigation in the imagery

#### Loading Placemarks from CSV

**Menu Path:** `File → Load Placemarks (CSV)`

You can bulk-load placemarks from CSV files in two coordinate formats:

**Option 1: Pixel Coordinates**
```csv
Name,Row,Column
Target Alpha,100.5,200.3
Target Bravo,150.0,250.0
Reference Point 1,200.5,300.8
```

**Required Columns:**
- `Name` - Placemark name
- `Row` - Pixel row coordinate
- `Column` - Pixel column coordinate

**Option 2: Geodetic Coordinates**
```csv
Name,Latitude,Longitude,Altitude
GCP-1,40.0128,-105.0156,1.5
GCP-2,40.0135,-105.0165,1.5
Site A,40.0142,-105.0174,1.6
```

**Required Columns:**
- `Name` - Placemark name
- `Latitude` - Latitude in degrees
- `Longitude` - Longitude in degrees

**Optional Columns:**
- `Altitude` - Altitude in km (defaults to 0.0)

**Requirements for Geodetic Coordinates:**
- Imagery must be loaded with geolocation capability
- Locations outside the sensor's field of view are skipped with warnings

**Workflow:**
1. Prepare CSV file(s) with placemarks
2. Load imagery (required for geodetic coordinates)
3. Select **File → Load Placemarks (CSV)**
4. Choose one or more CSV files
5. Review any warnings about failed conversions
6. Placemarks appear in the **Features** tab

**Example Files:**
See `data/placemarks/` directory for example CSV files and detailed documentation.

#### Managing Features

**In the Features Tab:**
- **Toggle Visibility**: Use checkboxes to show/hide individual features
- **Rename Features**: Click on feature names to edit them
- **Delete Features**: Select features and click "Delete Selected"
- **View Feature Type**: See whether each feature is a shapefile or placemark

**Feature Persistence:**
- Features remain in the Data Manager until deleted
- Feature visibility state is maintained independently
- Multiple features can be loaded and managed simultaneously

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

VISTA provides convenient keyboard shortcuts for efficient navigation and control:

| Shortcut | Action | Description |
|----------|--------|-------------|
| **Left Arrow** or **A** | Previous Frame | Navigate backward one frame in the sequence |
| **Right Arrow** or **D** | Next Frame | Navigate forward one frame in the sequence |
| **Spacebar** | Play/Pause | Toggle playback on/off |

**Notes:**
- Keyboard shortcuts work when the main window has focus
- The **A** and **D** keys provide an alternative to arrow keys, useful when your hand is on the mouse
- Use **Spacebar** for quick playback control without reaching for the play button
- During playback, use the FPS slider to control playback speed (supports negative values for reverse playback)

## Generating Test Data

Users can create simulated data to get familiar with the tool by clicking `File` > `Simulate`.

use the simulation module to generate test datasets with various configurations:

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
│   │   │   ├── point_selection_dialog.py    # Point selection mode dialog
│   │   │   └── data/
│   │   │       ├── data_manager.py  # Data panel with editing
│   │   │       ├── data_loader.py   # Background loading thread
│   │   │       ├── tracks_panel.py  # Track editing panel
│   │   │       └── detections_panel.py  # Detection editing panel
|   |   ├── algorithms/             
│   │   |   ├── detectors/                      # Detection algorithm widgets
│   │   |   │   ├── cfar_widget.py              # CFAR detector UI
│   │   |   │   ├── cfar_config_widget.py       # Reusable CFAR configuration widget
│   │   |   │   └── simple_threshold_widget.py  # Threshold detector UI
│   │   |   ├── trackers/                       # Tracking algorithm widgets
│   │   |   │   ├── simple_tracking_dialog.py
│   │   |   │   ├── kalman_tracking_dialog.py
│   │   |   │   ├── network_flow_tracking_dialog.py
│   │   |   │   └── tracklet_tracking_dialog.py
│   │   |   ├── background_removal/             # Background removal widgets
│   │   |   │   ├── temporal_median_widget.py
│   │   |   │   └── robust_pca_dialog.py
│   │   |   ├── enhancement/                    # Enhancement widgets
│   │   |   │   └── coaddition_widget.py
│   │   |   └── treatments/                     # Sensor calibration widgets
│   │   |       ├── bias_removal.py
│   │   |       └── non_uniformity_correction.py
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
│   │   ├── geodetic_mapping.py      # Geodetic-to-pixel conversion
│   │   └── point_refinement.py      # Point selection algorithms
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

- **`Imagery`**: Image data with optional times and geolocation data
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
- Ensure imagery contains a `geolocation` group with ARF data (pointing, polynomials, sensor position)
- Check that all required datasets are present: `pointing`, `poly_pixel_to_arf_azimuth`, `poly_pixel_to_arf_elevation`, `poly_arf_to_row`, `poly_arf_to_col`

**"Track has times but no frames"**
- Imagery required for time-to-frame mapping
- Verify imagery times overlap with track times

### Coordinate Conversion Issues

**Tracks appear in wrong location**
- Verify ARF polynomial coefficients are correctly fitted for the sensor geometry
- Check that geodetic coordinates are within the sensor's field of view
- Ensure frame synchronization across imagery datasets
- For off-Earth locations, NaN values are expected and handled gracefully

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

## Building an Executable
Users can build an executable version of this tool with `pyinstaller` using the commands below:

**Windows:**
```bash
pyinstaller vista/app.py --onefile -n vista --icon=vista/icons/logo.ico --hidden-import pyqtgraph.graphicsItems.PlotItem.plotConfigTemplate_pyqt6 --hidden-import pyqtgraph.imageview.ImageViewTemplate_pyqt6 --hidden-import pyqtgraph.graphicsItems.ViewBox.axisCtrlTemplate_pyqt6 --add-data="vista/icons*;vista" --add-data="vista/simulate/data*;vista"
```

**MacOS/Linux:**
```bash
pyinstaller vista/app.py --onefile --windowed -n vista --icon=vista/icons/logo.icns --hidden-import pyqtgraph.graphicsItems.PlotItem.plotConfigTemplate_pyqt6 --hidden-import pyqtgraph.imageview.ImageViewTemplate_pyqt6 --hidden-import pyqtgraph.graphicsItems.ViewBox.axisCtrlTemplate_pyqt6 --add-data="vista/icons:vista/icons/" --add-data="vista/simulate/data:vista/simulate/data/"
```

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
