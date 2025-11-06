# VISTA - Visual Imagery Software Tool for Analysis

![Logo](/vista/icons/logo.jpg)

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

### Image Processing Algorithms
- **Background Removal**: Temporal Median algorithm for removing static backgrounds
- Configurable algorithm parameters via dedicated dialogs
- Background processing with progress tracking and cancellation support
- Automatic creation of new imagery datasets with processed results
- Non-blocking execution preserves UI responsiveness

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

### Image Processing

VISTA includes built-in image processing algorithms that can be applied to loaded imagery.

#### Running Image Processing Algorithms

1. **Load Imagery**: Ensure imagery is loaded and selected
2. **Open Algorithm Dialog**: Navigate to `Image Processing` menu and select the desired algorithm
3. **Configure Parameters**: Adjust algorithm-specific parameters in the dialog
4. **Run Processing**: Click "Run" to start processing
5. **Monitor Progress**: Watch the progress bar and cancel if needed
6. **View Results**: Processed imagery is automatically added and selected for viewing

#### Background Removal - Temporal Median

The Temporal Median algorithm removes static backgrounds by computing the median of nearby frames while excluding a temporal window around the current frame.

**Menu Path:** `Image Processing → Background Removal → Temporal Median`

**Parameters:**
- **Background Frames** (default: 5): Number of frames on each side of the temporal window to use for median computation. Higher values provide more robust background estimates but require more memory.
- **Temporal Offset** (default: 2): Number of frames to skip immediately before and after the current frame. This prevents the current frame from contaminating the background estimate, preserving moving objects.

**Algorithm Behavior:**
- For each frame `i`, the algorithm selects background frames from:
  - Left window: frames `[i - offset - background : i - offset]`
  - Right window: frames `[i + offset + 1 : i + offset + background + 1]`
- Computes the median across all selected background frames
- Returns the median background for frame `i`

**Output:**
- Creates a new Imagery dataset with name: `"{original_name} Temporal Median"`
- Preserves frame numbers and timestamps from the original imagery
- New imagery is automatically added to the Data Manager and selected for viewing

**Use Cases:**
- Removing static backgrounds from surveillance footage
- Isolating moving objects in temporal sequences
- Background estimation for change detection algorithms

**Example:**
If you have imagery named "my_imagery", running Temporal Median with default parameters will create a new imagery dataset named "my_imagery Temporal Median" containing the computed background for each frame.

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
│   │   ├── playback_controls.py  # Playback UI
│   │   └── temporal_median_widget.py  # Temporal Median algorithm UI
│   ├── imagery/                  # Image data models
│   │   ├── imagery.py            # Base Imagery class
│   │   └── geolocated_imagery.py # Extendable geolocation class
│   ├── tracks/                   # Track data models
│   │   ├── track.py              # Individual Track class
│   │   └── tracker.py            # Tracker container
│   ├── detections/               # Detection data models
│   │   └── detector.py           # Detector class
│   ├── algorithms/               # Image processing algorithms
│   │   └── background_removal/   # Background removal algorithms
│   │       └── temporal_median.py  # Temporal Median algorithm
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

# Load imagery programmatically
# Note: Currently, imagery loading is primarily done through the UI
# The Imagery class can be instantiated directly with numpy arrays

import numpy as np
import h5py

# Load from HDF5 manually
with h5py.File("imagery.h5", "r") as f:
    images = f['images'][:]
    frames = f['frames'][:]
    imagery = Imagery(name="My Imagery", images=images, frames=frames)

# Load tracks
tracker = Tracker.from_csv("tracks.csv", name="My Tracker")

# Load detections
detector = Detector.from_csv("detections.csv", name="My Detector")
```

### Creating Custom Image Processing Algorithms

You can extend VISTA with custom image processing algorithms by following the pattern established by TemporalMedian:

#### 1. Create the Algorithm Class

```python
from dataclasses import dataclass, field
import numpy as np
from numpy.typing import NDArray
from typing import Tuple
from vista.imagery.imagery import Imagery


@dataclass
class MyCustomAlgorithm:
    """Custom image processing algorithm"""

    name: str = "My Custom Algorithm"
    imagery: Imagery
    parameter1: int = 10
    parameter2: float = 0.5
    _current_frame: int = field(init=False, default=-1)

    def __call__(self) -> Tuple[int, NDArray]:
        """
        Process the next frame incrementally.

        Returns:
            Tuple of (frame_index, processed_frame)
        """
        self._current_frame += 1

        # Your processing logic here
        processed_frame = self.process_frame(self._current_frame)

        return self._current_frame, processed_frame

    def process_frame(self, frame_idx: int) -> NDArray:
        """Process a single frame"""
        # Implement your algorithm here
        frame = self.imagery.images[frame_idx]
        # ... processing ...
        return processed_frame
```

#### 2. Create a Configuration Widget

Create a widget following the pattern in [temporal_median_widget.py](vista/widgets/temporal_median_widget.py):

```python
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QSpinBox, QPushButton
from PyQt6.QtCore import QThread, pyqtSignal
from vista.imagery.imagery import Imagery


class MyAlgorithmProcessingThread(QThread):
    """Worker thread for processing"""
    progress_updated = pyqtSignal(int, int)
    processing_complete = pyqtSignal(object)
    error_occurred = pyqtSignal(str)

    def __init__(self, imagery, param1, param2):
        super().__init__()
        self.imagery = imagery
        self.param1 = param1
        self.param2 = param2
        self._cancelled = False

    def run(self):
        # Process imagery with your algorithm
        # Emit progress_updated signals
        # Emit processing_complete with new Imagery object
        pass


class MyAlgorithmWidget(QDialog):
    """Configuration dialog for your algorithm"""
    imagery_processed = pyqtSignal(object)

    def __init__(self, parent=None, imagery=None):
        super().__init__(parent)
        self.imagery = imagery
        self.init_ui()

    def init_ui(self):
        # Create UI with parameter controls
        pass
```

#### 3. Integrate with Main Window

Add your algorithm to the menu in [main_window.py](vista/widgets/main_window.py):

```python
# In create_menu_bar method
my_algorithm_action = QAction("My Custom Algorithm", self)
my_algorithm_action.triggered.connect(self.open_my_algorithm_widget)
image_processing_menu.addAction(my_algorithm_action)

# Add handler method
def open_my_algorithm_widget(self):
    if not self.viewer.imagery:
        QMessageBox.warning(self, "No Imagery", "Please load imagery first.")
        return

    widget = MyAlgorithmWidget(self, self.viewer.imagery)
    widget.imagery_processed.connect(self.on_algorithm_complete)
    widget.exec()

def on_algorithm_complete(self, processed_imagery):
    # Add processed imagery to viewer
    self.viewer.add_imagery(processed_imagery)
    self.viewer.select_imagery(processed_imagery)
    self.data_manager.refresh()
```

**Key Design Principles:**
- Algorithms should be **callable** and return incremental results
- Use **background threads** to prevent UI blocking
- Emit **progress signals** for user feedback
- Create **new Imagery objects** rather than modifying originals
- Follow naming convention: `"{original_name} {algorithm_name}"`

## Performance Considerations

- **Chunked HDF5**: Use chunked storage for large imagery files to enable progressive loading
- **Lazy Histograms**: Histograms are computed on-demand and cached
- **Efficient Playback**: Bounce mode uses efficient frame looping
- **Background Loading**: All file I/O happens in background threads
- **Image Processing**: Algorithms run in background threads with incremental progress updates
- **Memory Usage**: Image processing algorithms may create full copies of imagery in memory. Monitor system memory when processing large datasets.

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

### Image Processing Issues
- **Out of Memory**: Processing large imagery datasets may require significant memory. Try reducing the imagery size or closing other applications.
- **Processing Cancelled**: If processing is cancelled, the partial results are discarded and no new imagery is created.
- **Processing Errors**: Check the error message for details. Common issues include invalid parameter values or corrupted imagery data.

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## License

MIT License

## Recent Updates

- v1.0.0: Initial release with multi-imagery support, geodetic tooltips, enhanced track filtering, and image processing capabilities
  - Added Image Processing menu with Background Removal algorithms
  - Implemented Temporal Median algorithm for background removal
  - Background processing with progress tracking and cancellation support
  - Automatic creation and management of processed imagery datasets
