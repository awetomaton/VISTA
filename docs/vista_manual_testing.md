# VISTA Manual Testing Checklist

This checklist focuses on VISTA behavior that is hard to cover completely with automated tests:
GUI workflows, HDF5 compatibility, PRF fitting, PRF source selection, flux estimation, project
save/load, and edge cases.

Run commands from the VISTA repository root unless noted otherwise.

```bash
cd /path/to/VISTA
source .venv/bin/activate
```

## 1. Baseline Sanity Checks

Run the automated checks first so manual testing starts from a known baseline.

```bash
python -m pytest tests -q
python -m compileall vista scripts/generate_single_frame.py tests
```

Expected result:

- Tests pass.
- Compilation completes without traceback.
- The VISTA branch has no unintentional local changes before manual testing.

```bash
git status --short --branch
```

## 2. Launch VISTA

```bash
python -m vista
```

Expected result:

- VISTA opens without traceback.
- The top menu includes `File`.
- `File` includes imagery/project actions such as `Load Imagery (HDF5)`, `Load Project`, and
  `Save Project`.
- The right-side Data Manager contains tabs including `Sensors`, `Imagery`, `Tracks`,
  `Detections`, `AOIs`, and `Features`.

Manual checks:

- Switch between Data Manager tabs.
- Confirm no tab switch causes a terminal traceback.
- Confirm the frame slider, playback buttons, and histogram panel are visible after imagery is
  loaded.

## 3. Generate Known-Flux PRF Test Datasets

Generate the standard PRF suite.

```bash
python -m scripts.generate_single_frame
```

Expected output:

- Datasets are written under:

```text
testing_auxiliaries/prf_single_frame_known_flux
```

- Standard cases include Gaussian, Elliptical Gaussian, Airy Disk, and Moffat.
- Each model has square-pixel and circular-pixel variants.
- Each dataset folder contains:
  - `imagery.h5`
  - `detections.csv`
  - `README.txt`
  - `truth.json`

Optional targeted edge cases:

```bash
python -m scripts.generate_single_frame \
  --suite custom \
  --model elliptical_gaussian \
  --pixel-shape square \
  --source-row 2.25 \
  --source-col 3.75 \
  --chip-size 25 \
  --out-dir testing_auxiliaries/prf_edge_case_tests
```

```bash
python -m scripts.generate_single_frame \
  --suite custom \
  --model moffat \
  --pixel-shape circular \
  --sigma-x 2.2 \
  --sigma-y 1.1 \
  --theta-deg 22.5 \
  --beta 3.5 \
  --noise-std 5 \
  --out-dir testing_auxiliaries/prf_noisy_cases
```

The noisy case is a stress test, not a truth-recovery requirement. Large parameter errors are
acceptable when the signal-to-noise ratio is intentionally poor or when the selected model is poorly
conditioned for the chip. Use it to verify that VISTA reports residuals/status cleanly and does not
crash, not to require exact recovery of `alpha_x`, `alpha_y`, `theta`, or `beta`.

If a command fails because an option is not supported, inspect the current script help:

```bash
python -m scripts.generate_single_frame --help
```

## 4. Load Imagery and Detections

In VISTA:

1. Open `File -> Load Imagery (HDF5)`.
2. Select one generated `imagery.h5`, for example:

```text
testing_auxiliaries/prf_single_frame_known_flux/elliptical_gaussian_square_pixel/imagery.h5
```

3. Open `File -> Load Detections (CSV)`.
4. Select the matching `detections.csv`.

Expected result:

- The image appears in the viewer.
- The detection appears at the bright point source.
- Data Manager -> Sensors shows one sensor row.
- Data Manager -> Detections shows the loaded detector row.
- The Sensors table has a `PRF Source` column.
- For generated known-PRF datasets, `PRF Source` should default to `Associated`.

Manual checks:

- Select the detection in Data Manager -> Detections.
- Move the frame slider if the dataset has multiple frames.
- Confirm overlays remain aligned and no terminal traceback occurs.

## 5. Inspect HDF5 PRF Storage

Use this script to inspect a generated VISTA-compatible HDF5 file.

```bash
python - <<'PY'
from pathlib import Path
import h5py
import numpy as np

path = Path("testing_auxiliaries/prf_single_frame_known_flux/elliptical_gaussian_square_pixel/imagery.h5")

with h5py.File(path, "r") as h5:
    print("file:", path)
    print("top-level keys:", list(h5.keys()))
    sensors = h5["sensors"]
    for sensor_id, sensor_group in sensors.items():
        print("\nSENSOR", sensor_id)
        print("sensor attrs:", dict(sensor_group.attrs))
        if "prf" not in sensor_group:
            print("PRF: missing")
            continue
        prf = sensor_group["prf"]
        print("prf keys:", list(prf.keys()))
        print("prf attrs:", dict(prf.attrs))
        for name in ("associated", "fitted"):
            if name in prf:
                group = prf[name]
                arr = group["oversampled_prf"][...]
                print(f"{name}: shape={arr.shape}, min={arr.min()}, max={arr.max()}, sum={arr.sum()}")
                print(f"{name} attrs:", dict(group.attrs))
        if "oversampled_prf" in prf:
            arr = prf["oversampled_prf"][...]
            print(f"legacy active oversampled_prf: shape={arr.shape}, min={arr.min()}, max={arr.max()}, sum={arr.sum()}")
PY
```

Expected result:

- The file has a top-level `sensors` group.
- The sensor has a `prf` group.
- At least one `oversampled_prf` array exists.
- Associated PRF data is finite, nonnegative, and nonzero.
- PRF metadata is present and auditable.
- If both `prf/oversampled_prf` and `prf/associated/oversampled_prf` exist, that is expected
  compatibility storage: the root dataset represents the active/legacy PRF path, while child
  groups preserve separate Associated/Fitted provenance.

## 6. PRF Source Selection

With a known-PRF dataset loaded:

1. Go to Data Manager -> Sensors.
2. Find the `PRF Source` dropdown.
3. Switch between:
   - `Associated`
   - `None`
   - `Fitted`, if available after fitting

Expected result:

- `Associated` uses the PRF loaded from the HDF5 sensor.
- `None` disables PRF-based operations that require an active PRF.
- `Fitted` uses a PRF estimated inside VISTA.
- Switching PRF Source does not destroy either the associated PRF or fitted PRF.
- Invalid choices should warn rather than crash.

Manual edge checks:

- Try estimating flux with `PRF Source = None`.
- Expected: VISTA warns or reports no active PRF; it should not crash.
- Switch back to `Associated` and repeat flux estimation.

## 7. PRF Flux Estimation

With imagery and detections loaded:

1. Go to Data Manager -> Detections.
2. Select the detector row.
3. Click `Estimate PRF Flux`.

Expected result for standard noise-free known-flux datasets:

- The operation completes without traceback.
- The terminal/status output reports successful estimates.
- Mean/median/peak flux should be close to the known injected flux from `truth.json`.
- For the default standard datasets, expected integrated source flux is usually `1000 raw counts`.

Manual HDF5/truth check:

```bash
python - <<'PY'
from pathlib import Path
import json

truth = Path("testing_auxiliaries/prf_single_frame_known_flux/elliptical_gaussian_square_pixel/truth.json")
print(json.loads(truth.read_text())["expected_integrated_source_flux_counts"])
PY
```

Export check:

1. After estimating flux, use `File -> Save Detections (CSV)` if available on the branch, or the
   relevant export path exposed by the UI.
2. Inspect the exported CSV.

Expected PRF flux columns include fields such as:

- `Flux (raw counts)`
- `Flux Uncertainty (raw counts)`
- `Flux SNR`
- `Flux Background (raw counts)`
- `Flux Residual Ratio`
- `Flux Status`

Edge cases to verify:

- Edge-clipped source: should be rejected, not estimated as a misleading valid flux.
- NaN or invalid pixels: this requires a custom HDF5 test file or an imagery product with bad-pixel
  metadata. Sparse invalid pixels should be handled; too many invalid pixels should reject or mark
  low confidence.
- Saturated chip: should warn or mark low confidence.
- Low SNR/noisy chip: should produce status/confidence information.
- PRF Source set to `None`: should warn cleanly.

Flux status values are stored on detections after `Estimate PRF Flux` runs and appear in exported
detection or track CSVs when any status values are present. Common values include `ok`,
`low_confidence:high_residual`, `low_confidence:low_snr`,
`low_confidence:possible_saturation`, `rejected:edge_clipped`, `rejected:no_sensor_prf`,
`rejected:frame_not_in_imagery`, `rejected:invalid_prf`,
`rejected:too_many_bad_pixels_or_nans`, `rejected:insufficient_background_pixels`,
`rejected:invalid_background`, and `rejected:invalid_prf_support`.

## 8. Fit a PRF from Detections

With imagery and detections loaded:

1. Go to Data Manager -> Sensors.
2. Select the relevant sensor row.
3. Click `Fit PRF from Detections`.
4. Use settings appropriate for the dataset.

Suggested settings for standard known-flux datasets:

- Model: match the generated dataset model.
- Pixel aperture: match the generated pixel shape.
- Detection source: `Selected detection chips` for a selected detector, or `Visible detection chips`
  when testing multiple visible detections.
- Chip size: `25`
- Oversampling: `9`
- Minimum detections: `1` for single-frame/single-source verification.
- Max iterations: `50`
- Tolerance: `0.01`

Expected result:

- VISTA logs a fit result without traceback.
- The log includes the fitted model parameters needed to reproduce the model.
- The Sensors table enables or selects `Fitted` as the PRF Source.
- The existing Associated PRF remains available.
- Re-fitting should warn before replacing an existing fitted PRF, if the branch currently exposes
  that warning.

Model-specific checks:

- Gaussian reports one circular scale parameter.
- Elliptical Gaussian reports `sigma_x`, `sigma_y`, and `theta`.
- Airy Disk reports its radius parameter.
- Moffat reports `alpha_x`, `alpha_y`, `theta`, and `beta`.

Important interpretation:

- For generated single-source datasets, the fit may appear extremely accurate because the data was
  generated from the same model family and the associated PRF is noise-free.
- For noisy or mismatched-model data, residuals and flux errors should increase.

## 9. Compare Associated vs Fitted PRF Flux

Use a generated known-PRF dataset.

1. Set Sensors -> `PRF Source` to `Associated`.
2. Estimate PRF flux and record mean/peak/status.
3. Fit a PRF from detections.
4. Set Sensors -> `PRF Source` to `Fitted`.
5. Estimate PRF flux again.

Expected result:

- Associated PRF should be the most accurate for synthetic known-PRF datasets because it is the
  ground-truth PRF.
- Fitted PRF should be close when the selected model matches the true model.
- Fitted PRF should be worse when the selected model is intentionally wrong.
- Switching source should change the measurement path without deleting either PRF.

Edge cases:

- Fit Elliptical Gaussian to a Moffat dataset.
- Fit Gaussian to an Elliptical Gaussian dataset.
- Fit Airy Disk to a Gaussian dataset.

Expected result:

- Fit may complete, but residuals should show model mismatch.
- Flux can be biased because the PRF model family is wrong.

## 10. Edge-Clipped Source Behavior

Use a generated edge case or create one with `--source-row` and `--source-col` near the frame edge.

Manual test:

1. Load edge-case imagery and detections.
2. Estimate PRF flux.
3. Attempt PRF fitting using the edge-clipped detection.

Expected result:

- Flux estimation rejects the detection with an edge-clipped status.
- PRF fitting should report zero usable chips if all selected detections are clipped.
- VISTA should leave the existing sensor PRF unchanged.
- The user-facing message should be a warning/status, not a crash.

Multiple-detection edge case:

- Load or generate a dataset with some centered detections and some edge-clipped detections.

Expected result:

- Centered usable chips contribute to fitting.
- Edge-clipped chips are skipped.
- Fit summary should make clear how many candidates were usable.
- If usable detections are below the configured minimum, fitting should not proceed.

## 11. Project Save/Load

This verifies that VISTA can preserve a whole working session instead of requiring separate manual
imports.

Manual test:

1. Load imagery.
2. Load detections.
3. Fit a PRF, or confirm an associated PRF is active.
4. Estimate PRF flux.
5. Use `File -> Save Project`.
6. Close VISTA.
7. Relaunch VISTA.
8. Use `File -> Load Project`.

Expected result:

- Imagery reloads.
- Sensor rows reload.
- Sensor row order matches the saved project.
- Detections reload.
- PRF Source state reloads.
- Associated/fitted PRF state reloads.
- Flux outputs reload if the project format currently preserves them.
- No stale selection from the previous session remains active after project load.

Manual edge checks:

- Save a project with same-name detectors or tracks.
- Reload it.
- Confirm detector/track identities remain distinct.
- Save a project with PRF Source set to `None`; reload and verify the same source state.
- Save a project with both Associated and Fitted PRFs; reload and switch between them.

## 12. IFOV Compatibility

Use a current IFOV-generated HDF5 file that includes sensor PRF data, for example:

```text
/path/to/ifov/examples/output/simple_scenario_output.h5
```

Before loading, verify that the file is actually HDF5 and nonempty:

```bash
python - <<'PY'
from pathlib import Path
import h5py

path = Path("/path/to/ifov/examples/output/simple_scenario_output.h5")
print("exists:", path.exists())
print("size_bytes:", path.stat().st_size if path.exists() else None)
print("is_hdf5:", h5py.is_hdf5(path) if path.exists() else None)
PY
```

Expected result:

- `size_bytes` is greater than zero.
- `is_hdf5` is `True`.

If `size_bytes` is zero or `is_hdf5` is `False`, regenerate the IFOV output file before testing
VISTA compatibility. VISTA should reject a zero-byte or non-HDF5 file.

Manual test:

1. Launch VISTA.
2. Use `File -> Load Imagery (HDF5)`.
3. Select the IFOV output file.
4. Inspect Data Manager -> Sensors.

Expected result:

- Imagery loads without traceback.
- Sensor row appears.
- `PRF Source` should show `Associated` when IFOV wrote a PRF.
- HDF5 PRF metadata is loaded into the sensor.
- `sensor.get_prf(...)` should work internally for PRF-based operations.

Optional Python check:

```bash
IFOV_OUTPUT_H5=/path/to/ifov/examples/output/simple_scenario_output.h5 python - <<'PY'
import os
from pathlib import Path
import h5py
import numpy as np

path = Path(os.environ["IFOV_OUTPUT_H5"])
with h5py.File(path, "r") as h5:
    for sensor_id, sensor_group in h5["sensors"].items():
        print("sensor:", sensor_id)
        prf = sensor_group.get("prf")
        if prf is None:
            print("  prf: missing")
            continue
        print("  prf keys:", list(prf.keys()))
        if "associated" in prf:
            arr = prf["associated"]["oversampled_prf"][...]
        else:
            arr = prf["oversampled_prf"][...]
        print("  shape:", arr.shape)
        print("  finite:", np.isfinite(arr).all())
        print("  nonnegative:", np.min(arr) >= -1e-12)
        print("  nonzero:", np.sum(arr) > 0)
PY
```

## 13. Geospatial and WMS Behavior

Use geolocated imagery, such as an IFOV MEO scenario or another HDF5 file with geolocation metadata.

Manual test:

1. Load geolocated imagery.
2. Toggle map/geospatial view if available.
3. Pan/zoom through several frames.

Expected result:

- The image maps into the expected geospatial footprint.
- Frame changes do not lose overlays.
- If WMS tiles fail because of local certificate configuration, VISTA should log a WMS fetch error
  without crashing.

Known environmental issue:

- On macOS Python installations, WMS HTTPS requests may fail with
  `CERTIFICATE_VERIFY_FAILED` if Python certificates are not installed/configured.
- This is an environment/certificate issue, not necessarily a VISTA PRF issue.

## 14. Overlay Loading Edge Cases

Manual checks:

- Load detections before imagery.
- Load detections after imagery.
- Load tracks after detections.
- Load AOIs/shapefiles if test files are available.
- Clear overlays with `File -> Clear Overlays`.

Expected result:

- Unsupported order should warn cleanly.
- Supported order should display overlays.
- Clearing overlays should remove detections/tracks/AOIs from the viewer and Data Manager.
- No stale selected detection should remain after clearing or loading a project.

Detection CSV edge cases:

- Marker value uses VISTA-supported symbols, such as `o`, not unsupported names such as `circle`.
- Empty labels should not crash.
- One-row and multi-row detector files should both load.

## 15. Performance Checks

Use a dataset with many visible detections.

Manual test:

1. Set PRF fit detection source to `Visible detection chips`.
2. Try increasing detection counts, for example 50, 150, and 600+ visible detections if available.
3. Record runtime and whether the UI remains responsive enough.

Expected result:

- Automatic or fit-max-detections limiting should keep runtime practical.
- Fit logs should report the number of candidates and usable chips.
- The fit should not silently use far more detections than configured.

Watch for:

- UI freezing for excessive time.
- Repeated recomputation after switching frames when no explicit fit was requested.
- Fit source wording should make clear that detection-centered chips are being used.

## 16. Error Handling Checks

Manually try invalid or marginal inputs.

HDF5 PRF payload issues:

- Missing PRF group.
- All-zero PRF.
- PRF with NaN.
- PRF with materially negative values.
- PRF center outside array bounds.

Expected result:

- Bad PRF payloads should raise or warn clearly during load/construction.
- Tiny negative numerical roundoff should be clipped, not treated as a physical negative PRF.
- Invalid PRFs should not become active silently.

GUI operation issues:

- Click `Fit PRF from Detections` with no imagery loaded.
- Click it with no sensor selected.
- Click it with no usable detections.
- Click `Estimate PRF Flux` with no detection selected.
- Click `Estimate PRF Flux` with PRF Source set to `None`.

Expected result:

- Each case should warn cleanly.
- Existing imagery/sensor/PRF state should remain unchanged.
- No terminal traceback should occur.

## 17. What Automated Tests Do Not Fully Cover

Manual testing is still important for:

- macOS menu behavior.
- Qt dialogs and button wiring.
- Data Manager table behavior.
- HDF5 inspection in third-party viewers.
- WMS/network/certificate behavior.
- Project save/load through the GUI.
- Visual overlay alignment.
- User-facing wording and warning clarity.
- Runtime perception for large detection sets.
- Cross-repo compatibility with current IFOV output files.

## 18. Manual Test Sign-Off Template

Use this as a lightweight record when validating a branch.

```text
VISTA branch:
Commit:
Python:
Date:

Automated checks:
- pytest:
- compileall:
- ruff/functionality lint:

Datasets tested:
- Generated standard PRF suite:
- Edge-clipped source:
- Noisy source:
- IFOV simple scenario:
- IFOV MEO/geolocated scenario:

Manual workflows:
- Launch:
- Load imagery/detections:
- PRF Source switching:
- Associated PRF flux:
- Fitted PRF flux:
- Wrong-model fit:
- Edge-clipped flux rejection:
- Project save/load:
- HDF5 PRF inspection:
- Geospatial/WMS:

Issues observed:
- 

Decision:
- Ready for review:
- Needs follow-up:
```
