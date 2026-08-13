# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.12.4] - 2026-8-XX

Major thanks to [@nolanking90] for the contributions that made this release possible!

### Improvements

 - 🔧 Fixed issues in TOML formatting specifications and dependencies.
 - 🛠️ Added github actions workflow to check formatting for PRs upon push to main

## [1.12.3] - 2026-6-26

### Improvements

 - 🔧 Fixed bug where an index error was thrown if the histogram was turned off and VISTA was run programmatically.

## [1.12.2] - 2026-6-25

### Improvements

 - 🔧 Fixed bug where the slider frame range for selected sensor is based on max of frames of detections and tracks across all sensors.
 - 🛠️ Removed `sensors` as a programmatic argument. It is already required for the `Imagery`, `Detector` and `Track` objects. The unique sensors list is determined from these.

## [1.12.1] - 2026-5-22

### Improvements

 - 🔧 Fixed bug where static median / subspace were not disabled while loading imagery.
 - 🛠️ Improved AOI creation logic so that it creates AOI based on user's view rather than image extent preventing issues where users couldn't see AOIs they cerate when zoomed in.

## [1.12.0] - 2026-5-21

### Improvements

 - ✨ Added median and subspace background removal algorithms for static targets.

## [1.11.1] - 2026-4-30

### Bug Fixes

 - 🔧 Fixed bug where frame slider range didn't update when changing sensor selection ([#11](https://github.com/awetomaton/VISTA/issues/11)).

### Contributors
- @nolanking90 — reported issue #11, identified the root cause, provided code to reproduce the issue, and provided the fix!

## [1.11.0] - 2026-4-19

### Improvements

 - ✨ Added the ability to set the user's name in the Settings dialog. Label user name and label time is stored and saved to exported detections and tracks.

## [1.10.3] - 2026-3-21

### Improvements

 - 🛠️ Reduced duplicative calls to `set_frame_number` when adding imagery or changing imagery selection.
 - 🛠️ Fixed issue where user detections table selection was eliminated when a bulk action is applied.

### Bug Fixes

 - 🔧 Fixed bug where imagery didn't always match histogram after changing imagery selection or creating new imagery.

## [1.10.2] - 2026-2-17

### Improvements

 - ✨ Added EWMA background removal filter to help users analyze data while it's loading and to provide quicker background removal.

### Bug Fixes

 - 🔧 Fixed bug where auto histogram range was inadvertently getting stored as user histogram limits
 - 🔧 Fixed bug where loaded imagery was inadvertently using built-in auto-historamming `pyqtgraph` to build histogram.

## [1.10.1] - 2026-2-16

### Improvements

 - ✨ Updated GoDec to enable running in overlapping blocks.
 - ✨ Added the ability to delete AOIs with the `delete` key.
 - ✨ Added detector and track projected lat / lon caching to drastically speed up viewing these overlays in the geographic view.
 - 🛠️ Updated track plot window to reset zoom view when axes are changed.
 - 🛠️ Updated projection cache default.
 - 🛠️ Updated data loader to allow loading a slice of imagery incrementally.
 - 🛠️ Improved how invalid projected tracks are handled so that invalid track projects simply aren't shown rather than projecting them to the North pole.
 - 🛠️ Updated pixel-geodetic sensor conversions to handle converting either many rows / cols on a single frame or arrays of rows / cols / frames of equal length for sensor geolocation models that are expedited that way.
 - 🛠️ Fixed nusance issue where the histogram zoom pan was not reset when changing imagery.
 - 🛠️ Eliminated error raising when imagery or detections are created with a name that matches another existing dataset.
 - 📙 Corrected some mistakes in the documentation.

### Bug Fixes

 - 🔧 Fixed edge-case bug where small images might not be able to project into the geographic view.
 - 🔧 Corrected where preventing histogram plot updates takes effect when histogram is hidden.
 - 🔧 Fixed bug where when multiple imagery were created and one of them had a name that exists in the imagery panel.
 - 🔧 Fixed bug where track points from all frames were projected using the current frame's geolocation metadata.
 - 🔧 Fixed bug that could occur when viewing track details for tracks that contained frames that do not exist in the imagery.

## [1.10.0] - 2026-2-15

### Improvements

- ⚖️ Updated license to require modified versions of VISTA retain the about page.
- 🥳 Updated app to support GPU PyTorch tensors.
- 🥳 Added PSTNN detector.
- 🥳 Imagery now loads and displays in the viewer incrementally.
- 🥳 Added sliding window subspace background removal algorithm.
- 🥳 Added GoDec background removal with GPU support.
- 🥳 Added the ability to drag and drop imagery, tracks, or detections into their respective data manager panels.
- ✨ Updated to use `numba` to fuse multiple numpy imagery operations into a single memory pass.
- ✨ Added the ability to hide the histogram widget to improve playback performance.
- ✨ Added the ability set the tooltip text font, color, and weight.
- ✨ Added `delete` key shortcut for removing tracks, detection points, detectors, and features.
- ✨ Added About page and corresponding toolbar action.
- 🛠️ Updated shape files load to only interpret them as providing geographic coordinates.
- 🛠️ Updated to track point selection, all detectors, and extraction window to enable selecting exceedingly dark, bright, or both pixels.
- 🛠️ Updated the track export to include track metadata fields such as signal total, signal pixels, noise std, etc.
- 🛠️ Improved imagery simulation to better handle large image sizes that could produce numerical instability that degraded polynomial accuracy.
 
### Bug Fixes

- 🔧 Fixed bug where lasso'ed selected detection highlights were still shown after starting manually create a track.

## [1.9.1] - 2026-2-7

### Improvements

- ✨ Updated to automatically de-select AOI after processing.
- ✨ Updated the track plot window so that the zoom resets each time the x/y axis is changed.
- ✨ Added the ability to set the tracker name of a group of selected tracks as a bulk action.
- ✨ Updated the frame subset method so that copies histograms from the original imagery rather than recomputing, when possible.
- 🛠️ Added text to explain how manipulating AOIs works using the table.
- 🛠️ Removed success dialogs after running image processing algorithms.
- 🛠️ Tracks loaded from time data are trimmed to the times that overlap with the selected imagery to prevent loading unncessary data.
- 🛠️ Updated the track plot window to not reset cached track data each time the selection is changed.
 
### Bug Fixes

- 🔧 Fixed bug where track extraction did not work if applied in an AOI.
- 🔧 Fixed bugs resulting from parsing track names as numbers instead of strings when all track names in a CSV were numbers.
 
## [1.9.0] - 2026-2-1

### Improvements

- 🥳 Addded undo with `ctrl` + `z` shortcut to tracks and detections panels.
- ✨ Made `Tracker` column editable in the Tracks Panel.
- ✨ Added a button on the tracks panel to re-order track rows by multiple ordered columns.
- 👷 Eliminated the `Tracker` object in favor of a flat list of `Track` objects with a `tracker` attribute.
- 🛠️ Updated all tracker to produce green tracks with circle by default.
- 🛠️ Updated track merging behavior so that new merged track tracker name is combines the unique tracker names in all the merged tracks.
- 🛠️ Updated tracks and detections tables so that some columns are resizable.
- 🛠️ Removed unnecessary `_resize_track_column` function.

### Bug Fixes

- 🔧 Fixed bug tracks with labels that are parsed as numeric would not load such as `1`.
- 🔧 Fixed bug where adding detections to track could get stuck as on and disabled when user selects detections, presses add to track, makes a new detection selection, and then cancels that selection.
- 🔧 Fixed bug where changing sensor did not clear track uncertainty ellipses from the previously selected sensor.

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

[1.12.2]: https://github.com/awetomaton/VISTA/releases/tag/1.12.2
[1.12.1]: https://github.com/awetomaton/VISTA/releases/tag/1.12.1
[1.12.0]: https://github.com/awetomaton/VISTA/releases/tag/1.12.0
[1.11.1]: https://github.com/awetomaton/VISTA/releases/tag/1.11.1
[1.11.0]: https://github.com/awetomaton/VISTA/releases/tag/1.11.0
[1.10.3]: https://github.com/awetomaton/VISTA/releases/tag/1.10.3
[1.10.2]: https://github.com/awetomaton/VISTA/releases/tag/1.10.2
[1.10.1]: https://github.com/awetomaton/VISTA/releases/tag/1.10.1
[1.10.0]: https://github.com/awetomaton/VISTA/releases/tag/1.10.0
[1.9.1]: https://github.com/awetomaton/VISTA/releases/tag/1.9.1
[1.9.0]: https://github.com/awetomaton/VISTA/releases/tag/1.9.0
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
