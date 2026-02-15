"""Diagnostic script to test polynomial round-trip accuracy in simulation."""
import numpy as np

from vista.transforms import evaluate_2d_polynomial, fit_2d_polynomial

# Parameters matching create_all_features_simulation
rows_img = 2048
cols_img = 2048
ifov_rad = 0.0005
polynomial_order = 4
n_samples = 20

center_row = rows_img / 2.0
center_col = cols_img / 2.0

sample_rows = np.linspace(0, rows_img - 1, n_samples)
sample_cols = np.linspace(0, cols_img - 1, n_samples)
col_grid, row_grid = np.meshgrid(sample_cols, sample_rows)
cols_flat = col_grid.flatten()
rows_flat = row_grid.flatten()

col_offset = cols_flat - center_col
row_offset = rows_flat - center_row
azimuth_base = col_offset * ifov_rad
elevation_base = -row_offset * ifov_rad
r_squared = col_offset**2 + row_offset**2
distortion_factor = 1.0 + 1e-8 * r_squared
azimuth = azimuth_base * distortion_factor
elevation = elevation_base * distortion_factor

print("=== Data Ranges ===")
print(f"Pixel rows: [{rows_flat.min():.1f}, {rows_flat.max():.1f}]")
print(f"Pixel cols: [{cols_flat.min():.1f}, {cols_flat.max():.1f}]")
print(f"Azimuth:    [{azimuth.min():.6f}, {azimuth.max():.6f}]")
print(f"Elevation:  [{elevation.min():.6f}, {elevation.max():.6f}]")
print()

# Fit forward polynomials
az_coeffs, az_res, _, _ = fit_2d_polynomial(cols_flat, rows_flat, azimuth, polynomial_order)
el_coeffs, el_res, _, _ = fit_2d_polynomial(cols_flat, rows_flat, elevation, polynomial_order)

# Fit reverse polynomials
row_coeffs, row_res, _, _ = fit_2d_polynomial(azimuth, elevation, rows_flat, polynomial_order)
col_coeffs, col_res, _, _ = fit_2d_polynomial(azimuth, elevation, cols_flat, polynomial_order)

print("=== Polynomial Fit Residuals (sum of squared residuals) ===")
print(f"Forward az:  {az_res:.2e}")
print(f"Forward el:  {el_res:.2e}")
print(f"Reverse row: {row_res:.2e}")
print(f"Reverse col: {col_res:.2e}")
print()

# Check forward accuracy at training points
az_eval = evaluate_2d_polynomial(az_coeffs, cols_flat, rows_flat)
el_eval = evaluate_2d_polynomial(el_coeffs, cols_flat, rows_flat)
print("=== Forward Poly Error at Training Points ===")
print(f"Max az error:  {np.max(np.abs(az_eval - azimuth)):.2e} rad")
print(f"Max el error:  {np.max(np.abs(el_eval - elevation)):.2e} rad")
print()

# Check reverse accuracy at training points
row_eval = evaluate_2d_polynomial(row_coeffs, azimuth, elevation)
col_eval = evaluate_2d_polynomial(col_coeffs, azimuth, elevation)
print("=== Reverse Poly Error at Training Points ===")
print(f"Max row error: {np.max(np.abs(row_eval - rows_flat)):.2e} pixels")
print(f"Max col error: {np.max(np.abs(col_eval - cols_flat)):.2e} pixels")
print()

# Polynomial-only round-trip test (no geometry)
test_points = [(0, 0), (512, 512), (1024, 1024), (1500, 1500), (2047, 2047)]
print("=== Polynomial-Only Round-Trip (pixel -> angle -> pixel) ===")
for row_test, col_test in test_points:
    r = np.array([float(row_test)])
    c = np.array([float(col_test)])
    # Forward
    az = evaluate_2d_polynomial(az_coeffs, c, r)
    el = evaluate_2d_polynomial(el_coeffs, c, r)
    # Reverse
    row_back = evaluate_2d_polynomial(row_coeffs, az, el)
    col_back = evaluate_2d_polynomial(col_coeffs, az, el)
    print(f"  pixel ({row_test:5d}, {col_test:5d}) -> angle ({az[0]:+.6f}, {el[0]:+.6f}) "
          f"-> pixel ({row_back[0]:8.2f}, {col_back[0]:8.2f})  "
          f"error: ({row_back[0] - row_test:+8.2f}, {col_back[0] - col_test:+8.2f})")
print()

# Print polynomial coefficients for inspection
print("=== Reverse Polynomial Coefficients ===")
print(f"row_coeffs: {row_coeffs}")
print(f"col_coeffs: {col_coeffs}")
