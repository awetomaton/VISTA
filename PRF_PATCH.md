# PRF Patch

This document tracks the local PRF patch as it evolves.

## Sensor-Level PRF API

- `Sensor.get_prf(source_row, source_column, chip_size=None)` is now part of the base sensor API.
- The base `Sensor` implementation raises `NotImplementedError`.
- `SampledSensor.get_prf(...)` implements a constant per-sensor PRF for v1.
- The API returns a local chip: `(rows, columns, prf_values)`.
- `rows` and `columns` are integer detector-pixel index grids; `prf_values` contains the point-source flux fraction assigned to each returned detector pixel.
- Source locations use VISTA detector pixel coordinates with integer pixel edges and pixel centers at `row + 0.5`, `column + 0.5`.
- `SampledSensor` samples the stored oversampled PRF by bilinear interpolation at detector pixel centers.
- Full-frame PRF output and field-dependent PRFs are deferred extensions.

## Sensor HDF5 PRF Storage

- Sensors with PRF data save a `prf/` group in their HDF5 sensor group.
- `prf/oversampled_prf` stores the oversampled PRF table.
- PRF attributes include oversampling, PRF center row/column, coordinate convention, model scope, normalization convention, and JSON construction metadata.
- HDF5 loading restores the oversampled PRF and metadata into `SampledSensor`.
- The Data Manager **Sensors** tab shows a per-sensor **PRF Source** selector.
- Sensor PRF storage supports both an **Associated** PRF loaded from file and a **Fitted** PRF generated inside VISTA.
- The selected PRF Source controls which stored PRF `Sensor.get_prf(...)` uses for PRF-based measurements.

## Current Behavior

- PRF fitting is initiated from **Data Manager -> Sensors -> Fit PRF from Detections**.
- On macOS, Settings is forced to remain in the **File** menu instead of being moved to the application menu by Qt's menu-role heuristic.
- Clicking the Sensors-tab fit button opens a sensor-specific PRF fitting dialog for the selected sensor.
- The dialog configures the PSF model, pixel aperture, detection source, fit tolerance, iteration/evaluation budget, chip size, and stored PRF oversampling.
- The dialog persists the last-used values as convenience defaults, but fitting remains an explicit per-sensor operation.
- VISTA fits a sensor-agnostic PRF model from image detections, then stores the resulting oversampled PRF on the selected sensor.
- PRF fitting can use selected detection chips, visible detection chips, or an automatic strongest-detection-chip subset.
- The automatic subset ranks visible detections by robust local contrast and caps the fit set to reduce noise and runtime.
- Automatic down-selection preserves original detection order after ranking to keep nonlinear fitting stable.
- A minimum of 5 usable detection chips is required.
- The default fitting chip is 11x11 pixels.
- The fitted PRF is generated from a continuous PSF model plus a configurable detector pixel aperture.
- The generated oversampled PRF is normalized for `Sensor.get_prf(...)` so centered detector-pixel samples sum to one unit of source flux.
- The Data Manager **Sensors** PRF Source column updates after a fit succeeds.
- If a sensor already has an associated PRF, VISTA preserves it and stores the fitted PRF separately.
- Fitting a PRF makes the fitted PRF active by default, while the user can switch back to Associated or None in the PRF Source selector.
- The fitted sensor PRF and construction metadata are saved in sensor HDF5 exports.

## Supported Models

- None
- Gaussian
- Elliptical Gaussian
- Airy Disk
- Moffat

`Gaussian` is treated as a circular Gaussian and fits one shared `sigma`.
`Elliptical Gaussian` fits separate `sigma_x`, `sigma_y`, and `theta`.

## Current Defaults

- Model: Elliptical Gaussian
- Pixel aperture: Square
- Minimum detections: 5
- Chip size: 11
- Detection source: Selected detection chips
- Auto max detections: 150
- Tolerance: 0.01 normalized RMS residual
- Max iterations: 50
- Stored PRF oversampling: 9

## Non-Modal Failure Behavior

- If PRF fitting cannot run, VISTA shows a warning dialog and leaves the selected sensor unchanged.
- If fitting reaches the function-evaluation budget, VISTA uses the best fit and emits a warning-style status message.
- If the optimizer stops before the iteration budget but the residual is still above tolerance, VISTA reports that separately as "stopped above tolerance."
- For multi-start models such as Moffat, metadata records total optimizer evaluations, best-start evaluations, and the number of optimizer starts.

## Implementation Notes

- PRF model generation and fitting live in `vista/algorithms/imagery/prf.py`.
- The sensor-specific PRF fitting dialog lives in `vista/widgets/core/data/sensors_panel.py`.
- The fit-and-attach workflow lives in `vista/widgets/core/imagery_viewer.py`.
- Automatic PRF fitting considers only detections from the current imagery sensor and imagery frame range.
- Sensor PRF HDF5 metadata is written from `vista/sensors/sampled_sensor.py`.
- Sensor PRF HDF5 metadata is loaded from `vista/widgets/core/data/data_loader.py`.
- macOS File menu placement is stabilized in `vista/widgets/core/main_window.py`.

## Current Limitations

- Fitting assumes one constant PRF per sensor.
- Field-dependent PRFs and full-frame PRF outputs are deferred extensions.
- Map View no longer auto-fits an imagery-scoped PRF; users explicitly fit the sensor PRF from the Sensors tab.
- Downstream projection/display code can now query `sensor.get_prf(...)`, but full PRF-aware geospatial resampling is still future work.

## Verification

- `python -m compileall vista` passes.
- A synthetic Gaussian PRF fit succeeds on five generated chips.
- A synthetic viewer-level fit attaches an oversampled PRF to the selected sensor and `sensor.get_prf(...)` returns a local chip normalized to unit flux.
- The viewer-level fit path accepts dialog-provided per-sensor fit settings without relying on the global Settings dialog.
- HDF5 export writes sensor PRFs under the sensor `prf/` group.
- The root `prf/oversampled_prf` preserves legacy single-PRF compatibility for the active source.
- The `prf/associated/` and `prf/fitted/` child groups preserve separate associated/fitted PRF provenance when available.
- Imagery-level fitted PRF storage has been removed; PRFs are sensor-level data.
- PRF metadata records tolerance convergence, optimizer status, intuitive optimizer iterations, SciPy function evaluations, and SciPy Jacobian evaluations.
- Automatic strongest-detections mode recovers the known synthetic distortion on the local NYC PRF dataset when enough usable chips are included.
- The Detections tab can estimate per-detection integrated point-source flux in **raw image counts** from a stored sensor PRF.
- PRF flux estimation rejects edge-clipped chips, estimates local background from outer-ring pixels with a sigma-clipped median, ignores sparse bad pixels/NaNs, and marks low-confidence measurements for high residuals, low SNR, or possible saturation.
- Detection and track CSV export include PRF flux columns when estimates are present: `Flux (raw counts)`, `Flux Uncertainty (raw counts)`, `Flux SNR`, `Flux Background (raw counts)`, `Flux Residual Ratio`, and `Flux Status`.
