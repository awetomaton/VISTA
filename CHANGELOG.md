# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.8.2] - 2026-1-29

### Bug Fixes

- 🔧 Fixed bug where removing all points from a detector removes detector from table, but not from viewer.
- 🔧 When a user clicks the color cell or uses bulk color actions, the code searches for tracks by name. This fails or finds the wrong track when:
  - Multiple tracks have the same name (which is allowed)
  - Tracks have been renamed after the table was populated
  - Tracks with the same color might have been created with the same default name
- 🔧 Updated all objects that require looks at equality checks to use `uuid`. This prevents bizarre, difficult to reproduce errors that could occur after long-term usage.

## [1.8.1] - 2026-1-28

### Improvements
- Updated tracks panel bulk actions so that they take effect immediately without having to press the apply button.
- Added the ability to specify whether to show all detections through "complete" column.
- Added more details on detections CSV format to documentation.
- Added the ability to perform bulk actions on detections.

### Bug Fixes

- Fixed issue where lasso could only be used when imagery is loaded.
- Fixed issue where lasso could only select one track even though multiple could be highlighted.
- Fixed issue where when tracks were deleted that have uncertainty ellipses plotted, the ellipses would remain in the imagery viewer.
- Fixed issue where applying bulks actions removed tracks froms selection in the tracks table.
- Fixed `user_guide_tracks_covariance.gif` so that it loops indefinitely.

## [1.8.0] - 2026-1-28

### Improvements
- Added the ability to define covariance matrices for track points.
- Consolidated the static and animated track details plot into a single component

## [1.7.0] - 2026-1-25

### Improvements
- Modified VISTA `SampledSensor` objects to define pointing in an Attitude Reference Frame (ARF) to enable off and on Earth ray projection
- Added a lasso selection for tracks and detections
- Added the ability to identify signal pixels for extracting track energy.
- Added the ability to load AOIs and export selected AOIs.
- Added Track Interpolator algorithm (Filters > Track Filters > Track Interpolator) to fill missing frames in track trajectories.
- Added Savitzky-Golay Filter algorithm (Filters > Track Filters > Savitzky-Golay Filter) to smooth track trajectories.
- Added the ability to load placemarks and shape files into VISTA.
- Added the ability to display all detections for a given detector across all time.
- Added the ability to delete any selected detection points.
- Added button to break tracks into detections.
- Added button to merge detections.
- Enabled manually creating track or detection without imagery.
- Added default histogram bounds.
- Added the ability to bulk label tracks.
- Added decimating coadd option.
- Added the ability to re-order detection and track table columns.
- Added hidden detection/track table column indicator.
- Update detection/track tables so that hidden columns are persisted.
- Added ability to view static or animated plots (synchronized to player) of track data.
- Combined `unix_time` and `unix_fine_time` into `unix_nanoseconds` which provides nanosecond precision until April 11, 2262.
- Added the ability to set track line style as a bulk action.

### Bug Fixes
- Fixed bug where the indices of selected tracks were remembered such that after deleting selected tracks and loading 
  or creating new tracks, the new track would show as highlighted even though they were not yet selected.
- Fixed bug where package distributions were missing some files from MANIFEST
- Fixed several issues that could result in excessive memory usage growth during long sessions.
- Fixed issue where users could only add detection / track labels rather than completely resetting them.
- Fixed bug that could occur when imagery is created with no frames.
- Fixed mistake in error message when trying to create track or detections manually when no sensor is selected.

## [1.6.5] - 2025-12-13

### New Features
- Added `VISTA_LABELS` environment variable to pre-configure labels from CSV files, JSON files, or comma-separated values

### Improvements
- Moved label management into view menu due to issues with actions on primary app menu on iOS

## [1.6.4] - 2025-12-1

### Improvements
- Added settings menu for some global configuration settings
- Improved the speed and effectiveness of computing the image histograms on realistic data
- Added subset frames algorithm to trim imagery
- Updated Robust PCA so that it can be canceled and provides incremental progress updates.
- Updated so that automatic histogram limits set to limits of histogram plot, not data

### Bug Fixes
- Fixed bug where progress dialog would close when loading imagery before the histogram creationg progress dialog would open 
- Forced loaded imagery to cast to float32. All image processing algorithms assume data are floating point values.

## [1.6.3] - 2025-11-30

### Improvements
- Improved imagery read speed by ~30%.

## [1.6.2] - 2025-11-29

### Improvements
- Removed unncessary `requirements.txt`
- Added `vista/simulate/data/earth_image.png` to manifest
- Added `CHANGELOG.md`
- Updated TOML to prevent installing non `vista` directories.

## [1.6.1] - 2025-11-25

### New Features
 - Added new `File` menu option to `Simulate` data to make it easier for new users to get familiar with the tool.

### Improvements
 - Greatly improved playback efficiency for tracks and detections by caching more data to prevent costly lookups
 - Consolidated hundreds of lines of duplicative code
 - Consolidated algorithms widgets into new `algorithms` sub-package under `widgets`
 - Added the ability to re-open the point selection dialog after closing it 
 - Updated Robust PCA to have an indefinite progressbar rather than a four part progress bar that would hang at 25%
 - Histogram gradient settings are now saved across sessions
 - Added logo ICO file to enable create executable distributions with `pyinstaller`.

### Bug Fixes
 - Fixed bug with threshold detector when run on an AOI
 - Fixed bugs with cursor type where it could be an arrow when it should be a crosshair and vice versa.
 - Added logic to prevent being in several states that take actions when the viewer is clicked simultaneously such as track creation and detection editing.

## [1.6.0] - 2025-11-25

### New Features

- Added multi-sensor support
- Added the ability to export imagery data
- Added the ability to label tracks and detections
- Select one or more tracks by clicking in viewer
- Added the ability to use features to aid in point selection
- Added the ability to add selected detections to track

### Improvements
 - Updated detections table line-width and marker size columns so that they have a larger width. 
 - Updated marker symbol columns in detections and tracks table to use full name rather than pyqtgraph abbreviations
 - Improved imagery HDF5 format to enable providing multiple sensors and imagery in a single file. Added warning dialog when user's loads deprecated v1.5 format
 - Improved app sizing
 - Improved geospatial tooltip icon 
 - File exporters now remember last exported location for subsequent exports
 - Removed unnecessary detection selection count and clear selection button
 - Improved the way detector editing works to enable removing or adding detections and only showing detections on each frame rather than all detections across all time

## [1.5.0] - 2025-11-15

### New Features

- Updated as installable Python package
- Updated player so that current frame is kept when switching between imagery (when possible)
- Improved app space utilization
- Added copy and slice methods to `Track` object
- Updated Kalman tracker so that it's resulting tracks have the default track styling
- Added more `Imagery` radiometric properties.

### Fixed Bugs
- Fixed bug with refreshing the tracks table

## [1.4.0] - 2025-11-14

### New Features

- Updated the pixel value tooltip to show coorindates of hover as well as pixel value
- Updated robust PCA to work more like the other image processing algorithms
- refactored data manager
- Added imagery treatments
- Add radiometric imagery components
- Consolidated some duplicative callbacks in the main window
- Updated detectors so that they only run on the currently selected imagery
- Updated how histogram limits are set on imagery so that user defined limits are remembered for each imagery separately
- Added the ability to select tracks by clicking the viewer
- Added the ability to click on the imagery viewer to select tracks
- Added the ability to split tracks
- Added the ability to merge tracks
- Made it easier to know what track in the viewer is selected in the tracks table by temporarily increasing the line width and marker size
 - Updated how track and detection row selection work and how rows are highlighted to be more intuitive
 - Moved track action buttons to their own row. Move clear filters button into the table conext menu


## [1.3.0] - 2025-11-12

### New Features

- Added the ability to run VISTA programmatically
- Updated the documentation to make clear that it is assumed that tracks are at zero altitude.
- Updated tracks export so that it can include track times and geolocation
- Added a multi-stage tracker
- Updated all trackers to use indeterminate progressbars.

## [1.2.0] - 2025-11-12

### New Features

- Updated CFAR and threshold detectors to enable finding pixel groups that are darker, brighter, or both than their threshold.

### Fixes

- Updated documentation to clarify that it is assumed that the x,y least square polynomial arguments correspond to column, row or longitude, latitude.
- Fixed bug where detectors failed to take into account the 0.5, 0.5 pixel offset required to be centered on the detected pixel / pixel group.
- Fixed bug where row / col offsets were being applied to geospatial tooltip arguments to LSQ Polynomials when they shouldn't have been
- Fixed bug where coaddition did not carry forward least square polynomials for geolocation

## [1.1.0] - 2025-11-11

### New Features

- Added the ability to show and hide track table columns in the data manager by right clicking on the track header.
- Added the ability to turn on / off track lines altogether leaving only the marker.
- Added the ability to set the track line style.
- Updated the application so that it remembers it's previous screen location and size
- Improved the behavior of the data manager width and track table column sizing
- Updated several algorithms that do not provide incremental progress to show an indeterminate progress bar instead.
- Updated application so that spacebar can be used to pause / play application even if play button is not in focus.
- Added a citation file.

### Fixes

- Fixed bug where imagery projection least squares polynomials did not carry forward into processed imagery created by the application.
- Fixed bug where tooltips did not take into account imagery row / column offsets.
- Fixed bug where imagery produced by algorithms did not have pre-computed histograms (which improves playback performance)

[1.8.2]: https://github.com/awetomaton/VISTA/releases/tag/1.8.2
[1.8.1]: https://github.com/awetomaton/VISTA/releases/tag/1.8.1
[1.8.0]: https://github.com/awetomaton/VISTA/releases/tag/1.8.0
[1.7.0]: https://github.com/awetomaton/VISTA/releases/tag/1.7.0
[1.6.5]: https://github.com/awetomaton/VISTA/releases/tag/1.6.5
[1.6.4]: https://github.com/awetomaton/VISTA/releases/tag/1.6.4
[1.6.3]: https://github.com/awetomaton/VISTA/releases/tag/1.6.3
[1.6.2]: https://github.com/awetomaton/VISTA/releases/tag/1.6.2
[1.6.1]: https://github.com/awetomaton/VISTA/releases/tag/1.6.1
[1.6.0]: https://github.com/awetomaton/VISTA/releases/tag/1.6.0
[1.5.0]: https://github.com/awetomaton/VISTA/releases/tag/1.5.0
[1.4.0]: https://github.com/awetomaton/VISTA/releases/tag/1.4.0
[1.3.0]: https://github.com/awetomaton/VISTA/releases/tag/1.3.0
[1.2.0]: https://github.com/awetomaton/VISTA/releases/tag/1.2.0
[1.1.0]: https://github.com/awetomaton/VISTA/releases/tag/1.1.0
