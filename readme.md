# VISTA - Visual Imagery Software Tool for Analysis

VISTA is a PyQt6-based desktop application for viewing, analyzing, and managing multi-frame imagery datasets along with associated detection and track overlays. It's designed for scientific and analytical workflows involving temporal image sequences.

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![Python](https://img.shields.io/badge/python-3.x-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## Features

### Multi-Frame Imagery Viewer
- Display full image sequences from HDF5 files
- Support for multiple simultaneous imagery datasets (must have unique names)
- Interactive image histogram with dynamic range adjustment
- Frame-by-frame navigation with keyboard shortcuts

### Playback Controls
- Play/Pause with adjustable FPS (-100 to +100 FPS for reverse playback)
- Frame slider and direct frame number input
- **Bounce Mode**: Loop playback between arbitrary frame ranges
- Time display integration when image timestamps are available
- Actual FPS tracking display

### Detection Overlay
- Load detection CSV files with multiple detector support
- Customizable markers (circle, square, triangle, diamond, plus, cross, star)
- Adjustable colors and marker sizes
- Show/hide individual detectors

### Track Visualization
- Load tracking CSV files with support for multiple trackers and tracks
- Track path rendering with customizable colors and line widths
- Current position markers with selectable styles
- Tail length control (show full history or last N frames)
- Track length calculation (cumulative distance)

### Data Manager Panel
- Tabbed interface for managing Imagery, Tracks, and Detections
- Bulk property editing (visibility, colors, markers, sizes)
- Column filtering and sorting for tracks and detections
- Real-time updates synchronized with visualization

### Geolocation Support
- Optional geodetic coordinate tooltip (latitude/longitude display)
- Infrastructure for custom imagery implementations (via `Imagery` subclass)

### Robust Data Loading
- Background threading for non-blocking file I/O
- Progress dialogs with cancellation support
- Error handling and user-friendly error messages
- Persistent file browser history via QSettings

## Installation

### Prerequisites
- Python 3.x

### Dependencies
```bash
pip install PyQt6 h5py pandas numpy pyqtgraph astropy
```

Optional (for example scripts):
```bash
pip install plotly
```

### Setup
1. Clone the repository:
```bash
git clone <repository-url>
cd vista
```

2. Set the PYTHONPATH (optional):
```bash
export PYTHONPATH=/path/to/vista  # Linux/Mac
set PYTHONPATH=C:\path\to\vista   # Windows
```

3. Run the application:
```bash
python -m vista.app
# Or
python vista/app.py
```

## Input Data Formats

### Imagery Data (HDF5 Format)

VISTA uses HDF5 files to store image sequences. The file must contain the following datasets:

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

#### Optional Datasets (for Timestamps)

**New Format:**
- **`unix_time`**: 1D array of `int64` (seconds since Unix epoch)
- **`unix_fine_time`**: 1D array of `int64` (nanosecond offset for high-precision timing)

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
└── unix_fine_time (Dataset) [optional]
    └── Shape: (100,)
    └── dtype: int64
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
    unix_time = np.arange(1609459200, 1609459200 + n_frames)  # Starting from 2021-01-01
    f.create_dataset("unix_time", data=unix_time)
    f.create_dataset("unix_fine_time", data=np.zeros(n_frames, dtype=np.int64))
```

### Track Data (CSV Format)

Track files represent trajectories of moving objects over time.

#### Required Columns

| Column Name | Data Type | Description | Example |
|------------|-----------|-------------|---------|
| `Track` | string | Unique identifier for the track | "Tracker 0 - Track 0" |
| `Frames` | int | Frame number where this point appears | 15 |
| `Rows` | float | Row position in image coordinates | 181.87 |
| `Columns` | float | Column position in image coordinates | 79.08 |

#### Optional Columns

| Column Name | Data Type | Default | Description | Valid Values |
|------------|-----------|---------|-------------|--------------|
| `Color` | string | 'g' | Track color | 'r', 'g', 'b', 'w', 'c', 'm', 'y', 'k' |
| `Marker` | string | 'o' | Current position marker style | 'o' (circle), 's' (square), 't' (triangle), 'd' (diamond), '+', 'x', 'star' |
| `Line Width` | float | 2 | Width of track path line | Any positive number |
| `Marker Size` | float | 12 | Size of position marker | Any positive number |
| `Tracker` | string | (none) | Name of tracker/algorithm | Any string |

#### File Structure

Each row represents one point in a track's trajectory. Multiple rows with the same `Track` identifier form a continuous path.

**Example CSV:**
```csv
Track,Frames,Rows,Columns,Color,Marker,Line Width,Marker Size,Tracker
"Tracker 0 - Track 0",15,181.87,79.08,g,o,2,12,"Tracker 0"
"Tracker 0 - Track 0",16,183.67,77.35,g,o,2,12,"Tracker 0"
"Tracker 0 - Track 0",17,185.23,75.89,g,o,2,12,"Tracker 0"
"Tracker 1 - Track 5",10,245.12,150.34,b,s,3,15,"Tracker 1"
"Tracker 1 - Track 5",11,247.89,152.01,b,s,3,15,"Tracker 1"
```

#### Data Organization
- **Single Tracker**: All tracks belong to one tracker
- **Multiple Trackers**: Tracks are grouped by the `Tracker` column
- **Hierarchy**: Tracker → Track → Points
- Points do not need to be sequential or sorted in the file

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

#### File Structure

Each row represents a single detection. Multiple detections can exist at the same frame, and detections are stateless (no history tracking).

**Example CSV:**
```csv
Detector,Frames,Rows,Columns,Color,Marker,Marker Size
"Detector 0",0.0,146.01,50.27,r,o,10
"Detector 0",0.0,141.66,25.02,r,o,10
"Detector 0",1.0,148.23,51.15,r,o,10
"Detector 1",0.0,200.45,300.12,b,s,12
```

#### Data Organization
- **Multiple Detectors**: Detections are grouped by the `Detector` column
- **Point Cloud**: Each frame can have zero or more detections
- Supports false alarms and sparse detection patterns

### Alternative HDF5 Formats

For advanced use cases, detections and tracks can also be loaded from HDF5 files:

**Detections HDF5:**
```
detections.h5
├── frames (Dataset)
├── rows (Dataset)
├── columns (Dataset)
└── attributes: color, marker, marker_size
```

**Tracks HDF5:**
```
tracks.h5
├── track_0 (Group)
│   ├── frames (Dataset)
│   ├── rows (Dataset)
│   └── columns (Dataset)
├── track_1 (Group)
│   └── ...
```

## Usage

### Launching the Application

```bash
python -m vista.app
```

### Loading Data

1. **Load Imagery**:
   - Menu: `File → Load Imagery` or Toolbar icon
   - Select HDF5 file with imagery data
   - Multiple imagery datasets supported (must have unique names)

2. **Load Tracks**:
   - Menu: `File → Load Tracks` or Toolbar icon
   - Select CSV or HDF5 file with track data

3. **Load Detections**:
   - Menu: `File → Load Detections` or Toolbar icon
   - Select CSV or HDF5 file with detection data

### Playback Controls

| Control | Description |
|---------|-------------|
| **Play/Pause** | Start/stop playback |
| **FPS Slider** | Adjust playback speed (-100 to +100 FPS, negative for reverse) |
| **Frame Slider** | Navigate to specific frame |
| **Bounce Mode** | Toggle looping playback between current frame range |
| **Arrow Keys** | Previous/Next frame navigation |
| **A/D Keys** | Previous/Next frame navigation (alternative) |

### Data Manager

The Data Manager panel provides tabs for managing:
- **Imagery**: Visibility, histogram controls
- **Tracks**: Filtering, sorting, bulk editing of colors/markers/sizes
- **Detections**: Filtering, sorting, bulk editing of colors/markers/sizes

### Keyboard Shortcuts

- **Left Arrow / A**: Previous frame
- **Right Arrow / D**: Next frame
- **Space**: Play/Pause (when playback controls have focus)

## Generating Example Data

Use the provided simulation scripts to generate example datasets:

```bash
# Basic scenario with imagery, tracks, and detections
python scripts/simulate_basic.py

# Imagery with timestamps
python scripts/simulate_timed_imagery.py

# Many tracks for stress testing
python scripts/simulate_many_tracks.py

# Large imagery dataset (chunked HDF5)
python scripts/large_imagery.py

# Sub-sampled temporal data
python scripts/simulate_sub_sampled_imagery.py
```

Example data will be saved to the `data/` directory.

## Project Structure

```
Vista/
├── vista/
│   ├── app.py                    # Main application entry point
│   ├── widgets/                  # UI components
│   │   ├── main_window.py        # Main window with menu/toolbar
│   │   ├── imagery_viewer.py     # Image display with pyqtgraph
│   │   ├── data_manager.py       # Data panel with editing
│   │   ├── data_loader.py        # Background loading thread
│   │   └── playback_controls.py  # Playback UI
│   ├── imagery/                  # Image data models
│   │   ├── imagery.py            # Base Imagery class
│   │   └── geolocated_imagery.py # Extendable geolocation class
│   ├── tracks/                   # Track data models
│   │   ├── track.py              # Individual Track class
│   │   └── tracker.py            # Tracker container
│   ├── detections/               # Detection data models
│   │   └── detector.py           # Detector class
│   ├── simulate/                 # Data generation utilities
│   │   └── simulation.py         # Synthetic data simulator
│   ├── utils/                    # Utilities
│   │   ├── color.py              # Color conversion helpers
│   │   └── random_walk.py        # Random walk simulation
│   └── icons/                    # Application icons
├── scripts/                      # Example data generation scripts
│   ├── simulate_basic.py
│   ├── simulate_timed_imagery.py
│   ├── simulate_many_tracks.py
│   └── ...
├── data/                         # Example datasets (gitignored)
└── readme.md                     # This file
```

## Architecture

### Design Principles

1. **Data-View Separation**: Imagery, Track, and Detector classes are independent data containers
2. **Async Loading**: Background threads prevent UI freezing during file I/O
3. **Signal-Slot Communication**: PyQt signals coordinate between components
4. **Lazy Evaluation**: Histograms computed on-demand and cached
5. **Extensibility**: `Imagery` base class for customization

### Key Classes

- **`Imagery`**: Base class for image data (can be subclassed for custom formats)
- **`Track`**: Single trajectory with styling attributes
- **`Tracker`**: Container for multiple tracks
- **`Detector`**: Point cloud detection class
- **`ImageryViewer`**: Widget for visualization
- **`PlaybackControls`**: Widget for temporal control
- **`DataManagerPanel`**: Widget for data editing

## Advanced Usage

### Programmatic Data Loading

```python
from vista.imagery.imagery import Imagery
from vista.tracks.tracker import Tracker
from vista.detections.detector import Detector

# Load imagery
imagery = Imagery.from_hdf5("imagery.h5", name="My Imagery")

# Load tracks
tracker = Tracker.from_csv("tracks.csv", name="My Tracker")

# Load detections
detector = Detector.from_csv("detections.csv", name="My Detector")
```

## Performance Considerations

- **Chunked HDF5**: Use chunked storage for large imagery files to enable progressive loading
- **Lazy Histograms**: Histograms are computed on-demand and cached
- **Efficient Playback**: Bounce mode uses efficient frame looping
- **Background Loading**: All file I/O happens in background threads

## Troubleshooting

### Duplicate Imagery Names
If you see "An imagery dataset with this name already exists", ensure each loaded imagery dataset has a unique name.

### Slow Playback
- Reduce FPS slider value
- Use smaller imagery datasets
- Ensure HDF5 files use chunked storage

### Missing Data
- Verify CSV column names match exactly (case-sensitive)
- Check that HDF5 files contain required datasets: `images` and `frames`
- Ensure coordinate values (rows/columns) are within image bounds

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## License

MIT License

## Recent Updates

- v1.0.0: Initial release with multi-imagery support, geodetic tooltips, and enhanced track filtering
