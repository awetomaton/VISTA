# PRF Projection Patch

This document tracks the local PRF projection patch as it evolves.

## Current Behavior

- PRF projection is opt-in from **File -> Settings -> Imagery**.
- On macOS, Settings is forced to remain in the **File** menu instead of being moved to the application menu by Qt's menu-role heuristic.
- The default model is **None**, which preserves VISTA's existing projection behavior.
- When a PRF model is selected, VISTA attempts to fit a sensor-agnostic PRF from user-selected detections before entering Map View.
- A minimum of 5 selected detections is required.
- The default fitting chip is 11x11 pixels.
- The fitted PRF is generated from a continuous PSF model plus a configurable pixel aperture.
- Projection uses the fitted PRF as a conservative source-image prefilter before VISTA's existing geodetic resampling path.
- Fitted PRF metadata and kernel data are saved with imagery in HDF5 exports.
- Fitted PRF metadata is read back when HDF5 imagery is loaded.

## Supported Models

- None
- Gaussian
- Elliptical Gaussian
- Airy Disk
- Moffat

`Gaussian` is treated as a circular Gaussian and fits one shared `sigma`.
`Elliptical Gaussian` fits separate `sigma_x`, `sigma_y`, and `theta`.

## Current Defaults

- Model: None
- Pixel shape: Square
- Minimum detections: 5
- Chip size: 11
- Tolerance: 0.01 normalized RMS residual
- Max iterations: 50

## Non-Modal Failure Behavior

- If PRF fitting cannot run, VISTA emits a status message and falls back to existing projection.
- If fitting reaches the iteration budget, VISTA uses the best fit and emits a warning-style status message.
- If the optimizer stops before the iteration budget but the residual is still above tolerance, VISTA reports that separately as "stopped above tolerance."

## Implementation Notes

- Settings live in `vista/widgets/core/settings_dialog.py`.
- PRF model generation and fitting live in `vista/algorithms/imagery/prf.py`.
- Map View fitting is initiated by `vista/widgets/core/imagery_viewer.py`.
- Projection prefiltering is applied in `vista/wms/imagery_projector.py`.
- HDF5 metadata is written from `vista/imagery/imagery.py`.
- HDF5 metadata is loaded from `vista/widgets/core/data/data_loader.py`.
- macOS File menu placement is stabilized in `vista/widgets/core/main_window.py`.

## Current Limitations

- The first projection implementation applies a PRF prefilter rather than a full PRF-aware area-overlap resampler.
- Fitting assumes one constant PRF for the imagery sequence.
- PRF fitting is driven by detections selected before Map View is enabled.

## Verification

- `python -m compileall vista` passes.
- A synthetic Gaussian PRF fit succeeds on five generated chips.
- HDF5 export writes a `prf/` group containing fit attributes and the fitted kernel.
- PRF metadata records both tolerance convergence and the underlying optimizer status.
