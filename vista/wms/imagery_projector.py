"""Imagery projection engine for projecting VISTA imagery to geodetic coordinates."""
from astropy import units
from astropy.coordinates import EarthLocation
import numpy as np
from numpy.typing import NDArray
from scipy.ndimage import map_coordinates

try:
    import torch
    import torch.nn.functional as F
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

from vista.sensors.sensor import Sensor


class ImageryProjector:
    """Projects VISTA imagery from pixel coordinates to a geodetic (lon, lat) grid.

    For a given output grid in (lon, lat), uses sensor.geodetic_to_pixel() to find
    the corresponding source pixel for each output grid point, then performs bilinear
    interpolation to produce the projected image.

    Parameters
    ----------
    sensor : Sensor
        Sensor with forward and reverse geolocation capability.
    coarse_grid_size : int
        Maximum dimension of the coarse grid used to accelerate coordinate mapping.
        Set to 0 to disable coarse grid sampling and compute every pixel directly.
        Default is 64.
    """

    def __init__(self, sensor: Sensor, coarse_grid_size: int = 64):
        self.sensor = sensor
        self.coarse_grid_size = coarse_grid_size

    def compute_footprint(
        self,
        frame: int,
        n_rows: int,
        n_cols: int,
        row_offset: int = 0,
        column_offset: int = 0,
    ) -> tuple[float, float, float, float] | None:
        """Compute the geodetic bounding box of the imagery footprint for a given frame.

        Samples the image corners and edges using sensor.pixel_to_geodetic() to find
        the full extent on the ground.

        Parameters
        ----------
        frame : int
            Frame number.
        n_rows : int
            Number of rows in the image.
        n_cols : int
            Number of columns in the image.
        row_offset : int
            Row offset of the imagery.
        column_offset : int
            Column offset of the imagery.

        Returns
        -------
        tuple[float, float, float, float] or None
            Bounding box as (lon_min, lat_min, lon_max, lat_max) in degrees, or None if
            the footprint could not be computed (e.g., no valid intersections).
        """
        if not self.sensor.can_geolocate():
            return None

        # Sample points along the image boundary (corners + edge midpoints + more)
        n_edge_samples = 10
        rows = []
        cols = []

        # Top edge
        for i in range(n_edge_samples + 1):
            rows.append(row_offset)
            cols.append(column_offset + i * (n_cols - 1) / n_edge_samples)
        # Bottom edge
        for i in range(n_edge_samples + 1):
            rows.append(row_offset + n_rows - 1)
            cols.append(column_offset + i * (n_cols - 1) / n_edge_samples)
        # Left edge
        for i in range(1, n_edge_samples):
            rows.append(row_offset + i * (n_rows - 1) / n_edge_samples)
            cols.append(column_offset)
        # Right edge
        for i in range(1, n_edge_samples):
            rows.append(row_offset + i * (n_rows - 1) / n_edge_samples)
            cols.append(column_offset + n_cols - 1)

        rows_arr = np.array(rows)
        cols_arr = np.array(cols)

        locations = self.sensor.pixel_to_geodetic(frame, rows_arr, cols_arr)
        lats = locations.lat.deg
        lons = locations.lon.deg

        # Filter out NaN values (pixels that don't intersect Earth)
        valid = ~(np.isnan(lats) | np.isnan(lons))
        if not np.any(valid):
            return None

        lats = lats[valid]
        lons = lons[valid]

        return (float(np.min(lons)), float(np.min(lats)), float(np.max(lons)), float(np.max(lats)))

    def _compute_coordinate_mapping(
        self,
        frame: int,
        output_bbox: tuple[float, float, float, float],
        output_width: int,
        output_height: int,
        row_offset: int = 0,
        column_offset: int = 0,
    ) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        """Compute the (lon, lat) → (row, col) coordinate mapping for a projection.

        Uses a coarse grid with bilinear interpolation to avoid calling the expensive
        sensor.geodetic_to_pixel() at every output pixel. The sensor model is polynomial,
        so interpolation from a 64x64 grid gives sub-pixel accuracy.

        Parameters
        ----------
        frame : int
            Frame number for geolocation.
        output_bbox : tuple[float, float, float, float]
            Output bounding box as (lon_min, lat_min, lon_max, lat_max).
        output_width : int
            Width of the output projected image in pixels.
        output_height : int
            Height of the output projected image in pixels.
        row_offset : int
            Row offset of the imagery.
        column_offset : int
            Column offset of the imagery.

        Returns
        -------
        src_rows : NDArray[np.float64]
            Flattened array of source row coordinates (length output_height * output_width).
        src_cols : NDArray[np.float64]
            Flattened array of source column coordinates (length output_height * output_width).
        """
        lon_min, lat_min, lon_max, lat_max = output_bbox

        # Determine coarse grid size — only use coarse grid when it saves significant work
        coarse_max = self.coarse_grid_size
        use_coarse = coarse_max > 0 and (output_width > coarse_max or output_height > coarse_max)

        if use_coarse:
            # Maintain aspect ratio in the coarse grid
            aspect = output_width / max(1, output_height)
            if aspect >= 1:
                coarse_w = coarse_max
                coarse_h = max(4, int(round(coarse_max / aspect)))
            else:
                coarse_h = coarse_max
                coarse_w = max(4, int(round(coarse_max * aspect)))

            coarse_lons = np.linspace(lon_min, lon_max, coarse_w)
            coarse_lats = np.linspace(lat_min, lat_max, coarse_h)
            coarse_lon_grid, coarse_lat_grid = np.meshgrid(coarse_lons, coarse_lats)

            earth_locs = EarthLocation.from_geodetic(
                lon=coarse_lon_grid.ravel() * units.deg,
                lat=coarse_lat_grid.ravel() * units.deg,
                height=0 * units.m,
            )
            c_rows, c_cols = self.sensor.geodetic_to_pixel(frame, earth_locs)
            c_rows = (c_rows - row_offset).reshape(coarse_h, coarse_w)
            c_cols = (c_cols - column_offset).reshape(coarse_h, coarse_w)

            # Handle NaN values: replace with 0, interpolate, then restore NaN from mask
            nan_mask = np.isnan(c_rows) | np.isnan(c_cols)
            c_rows_clean = np.where(nan_mask, 0.0, c_rows)
            c_cols_clean = np.where(nan_mask, 0.0, c_cols)

            # Interpolate coarse coordinate maps to full resolution using map_coordinates
            fy = np.linspace(0, coarse_h - 1, output_height)
            fx = np.linspace(0, coarse_w - 1, output_width)
            fy_grid, fx_grid = np.meshgrid(fy, fx, indexing='ij')
            interp_coords = np.array([fy_grid.ravel(), fx_grid.ravel()])

            src_rows = map_coordinates(c_rows_clean, interp_coords, order=1, mode='nearest')
            src_cols = map_coordinates(c_cols_clean, interp_coords, order=1, mode='nearest')

            # Restore NaN where the coarse grid had invalid points
            if np.any(nan_mask):
                validity = map_coordinates(
                    (~nan_mask).astype(np.float64), interp_coords, order=1, mode='nearest'
                )
                invalid = validity < 0.5
                src_rows[invalid] = np.nan
                src_cols[invalid] = np.nan
        else:
            # Small output — compute directly at every pixel
            lons = np.linspace(lon_min, lon_max, output_width)
            lats = np.linspace(lat_min, lat_max, output_height)
            lon_grid, lat_grid = np.meshgrid(lons, lats)

            earth_locs = EarthLocation.from_geodetic(
                lon=lon_grid.ravel() * units.deg,
                lat=lat_grid.ravel() * units.deg,
                height=0 * units.m,
            )
            src_rows, src_cols = self.sensor.geodetic_to_pixel(frame, earth_locs)
            src_rows = src_rows - row_offset
            src_cols = src_cols - column_offset

        return src_rows, src_cols

    def project_frame_cpu(
        self,
        image: NDArray[np.float32],
        frame: int,
        output_bbox: tuple[float, float, float, float],
        output_width: int,
        output_height: int,
        row_offset: int = 0,
        column_offset: int = 0,
    ) -> NDArray[np.float32]:
        """Project a single frame onto a geodetic grid using CPU interpolation.

        Uses a coarse-grid approach for the expensive geodetic_to_pixel() call: the
        coordinate mapping is computed on a small grid (64x64) and bilinearly interpolated
        to full resolution, since the sensor model is smooth (polynomial-based).

        Parameters
        ----------
        image : NDArray[np.float32]
            Source image array with shape (height, width).
        frame : int
            Frame number for geolocation.
        output_bbox : tuple[float, float, float, float]
            Output bounding box as (lon_min, lat_min, lon_max, lat_max).
        output_width : int
            Width of the output projected image in pixels.
        output_height : int
            Height of the output projected image in pixels.
        row_offset : int
            Row offset of the imagery.
        column_offset : int
            Column offset of the imagery.

        Returns
        -------
        NDArray[np.float32]
            Projected image array with shape (output_height, output_width). Pixels outside
            the source image bounds are set to NaN.
        """
        src_rows, src_cols = self._compute_coordinate_mapping(
            frame, output_bbox, output_width, output_height, row_offset, column_offset,
        )

        img_h, img_w = image.shape

        # Determine downsampling factor if source resolution >> output resolution
        valid_mask = (
            (src_rows >= 0) & (src_rows < img_h) &
            (src_cols >= 0) & (src_cols < img_w) &
            ~np.isnan(src_rows) & ~np.isnan(src_cols)
        )
        if np.sum(valid_mask) > 1:
            valid_rows = src_rows[valid_mask]
            valid_cols = src_cols[valid_mask]
            src_row_span = np.max(valid_rows) - np.min(valid_rows)
            src_col_span = np.max(valid_cols) - np.min(valid_cols)
            src_area = src_row_span * src_col_span
            out_area = output_width * output_height
            downsample_factor = max(1, int(np.sqrt(src_area / max(out_area, 1)) / 2))
        else:
            downsample_factor = 1

        # Downsample source image if needed to reduce aliasing
        work_image = image
        if downsample_factor > 1:
            from skimage.transform import downscale_local_mean
            work_image = downscale_local_mean(image, (downsample_factor, downsample_factor)).astype(np.float32)
            src_rows = src_rows / downsample_factor
            src_cols = src_cols / downsample_factor

        # Reshape for map_coordinates
        coords = np.array([src_rows, src_cols])

        # Bilinear interpolation; pixels outside bounds get cval=np.nan
        projected_flat = map_coordinates(
            work_image, coords, order=1, mode='constant', cval=np.nan
        )

        # Mask out-of-bounds pixels that map_coordinates might have interpolated at the boundary
        work_h, work_w = work_image.shape
        out_of_bounds = (
            (src_rows < -0.5) | (src_rows > work_h - 0.5) |
            (src_cols < -0.5) | (src_cols > work_w - 0.5) |
            np.isnan(src_rows) | np.isnan(src_cols)
        )
        projected_flat[out_of_bounds] = np.nan

        return projected_flat.reshape(output_height, output_width).astype(np.float32)

    def project_frame_gpu(
        self,
        gpu_image: 'torch.Tensor',
        frame: int,
        output_bbox: tuple[float, float, float, float],
        output_width: int,
        output_height: int,
        row_offset: int = 0,
        column_offset: int = 0,
    ) -> NDArray[np.float32]:
        """Project a single frame using GPU acceleration with torch.nn.functional.grid_sample.

        Down-samples the source image on GPU if needed, then uses grid_sample for bilinear
        interpolation. The coordinate mapping (geodetic_to_pixel) is computed on CPU, and the
        resulting grid is uploaded to GPU for interpolation.

        Parameters
        ----------
        gpu_image : torch.Tensor
            Source image tensor on GPU with shape (height, width).
        frame : int
            Frame number for geolocation.
        output_bbox : tuple[float, float, float, float]
            Output bounding box as (lon_min, lat_min, lon_max, lat_max).
        output_width : int
            Width of the output projected image in pixels.
        output_height : int
            Height of the output projected image in pixels.
        row_offset : int
            Row offset of the imagery.
        column_offset : int
            Column offset of the imagery.

        Returns
        -------
        NDArray[np.float32]
            Projected image array with shape (output_height, output_width) on CPU.
            Pixels outside the source image bounds are set to NaN.
        """
        if not HAS_TORCH:
            raise RuntimeError("PyTorch is required for GPU projection")

        device = gpu_image.device
        lon_min, lat_min, lon_max, lat_max = output_bbox

        # Build output grid on CPU
        lons = np.linspace(lon_min, lon_max, output_width)
        lats = np.linspace(lat_min, lat_max, output_height)  # lat increases upward (row 0 = south)
        lon_grid, lat_grid = np.meshgrid(lons, lats)
        flat_lons = lon_grid.ravel()
        flat_lats = lat_grid.ravel()

        # Reverse-project to pixel coordinates (on CPU)
        earth_locs = EarthLocation.from_geodetic(
            lon=flat_lons * units.deg,
            lat=flat_lats * units.deg,
            height=0 * units.m,
        )
        src_rows, src_cols = self.sensor.geodetic_to_pixel(frame, earth_locs)
        src_rows = src_rows - row_offset
        src_cols = src_cols - column_offset

        img_h, img_w = gpu_image.shape

        # Determine downsampling factor
        valid_mask = (
            (src_rows >= 0) & (src_rows < img_h) &
            (src_cols >= 0) & (src_cols < img_w) &
            ~np.isnan(src_rows) & ~np.isnan(src_cols)
        )
        if np.sum(valid_mask) > 1:
            valid_rows = src_rows[valid_mask]
            valid_cols = src_cols[valid_mask]
            src_row_span = np.max(valid_rows) - np.min(valid_rows)
            src_col_span = np.max(valid_cols) - np.min(valid_cols)
            src_area = src_row_span * src_col_span
            out_area = output_width * output_height
            downsample_factor = max(1, int(np.sqrt(src_area / max(out_area, 1)) / 2))
        else:
            downsample_factor = 1

        # Downsample on GPU if needed
        work_image = gpu_image
        if downsample_factor > 1:
            # Use adaptive average pooling for downsampling
            new_h = max(1, img_h // downsample_factor)
            new_w = max(1, img_w // downsample_factor)
            work_image = F.adaptive_avg_pool2d(
                gpu_image.unsqueeze(0).unsqueeze(0), (new_h, new_w)
            ).squeeze(0).squeeze(0)
            src_rows = src_rows / downsample_factor
            src_cols = src_cols / downsample_factor

        work_h, work_w = work_image.shape

        # Normalize coordinates to [-1, 1] for grid_sample
        # grid_sample expects (x, y) where x corresponds to width and y to height
        norm_x = 2.0 * src_cols / (work_w - 1) - 1.0  # col -> x
        norm_y = 2.0 * src_rows / (work_h - 1) - 1.0  # row -> y

        # Mark out-of-bounds as large values (grid_sample with zeros padding will zero them)
        out_of_bounds = (
            np.isnan(src_rows) | np.isnan(src_cols) |
            (src_rows < -0.5) | (src_rows > work_h - 0.5) |
            (src_cols < -0.5) | (src_cols > work_w - 0.5)
        )
        norm_x[out_of_bounds] = -10.0
        norm_y[out_of_bounds] = -10.0

        # Build grid tensor: (1, output_height, output_width, 2)
        grid_np = np.stack([
            norm_x.reshape(output_height, output_width),
            norm_y.reshape(output_height, output_width),
        ], axis=-1).astype(np.float32)
        grid_tensor = torch.from_numpy(grid_np).unsqueeze(0).to(device)

        # Prepare source image: (1, 1, H, W)
        src_tensor = work_image.unsqueeze(0).unsqueeze(0).float()

        # grid_sample with bilinear interpolation
        result = F.grid_sample(
            src_tensor, grid_tensor, mode='bilinear', padding_mode='zeros', align_corners=True
        )

        # Convert back to numpy
        projected = result.squeeze().cpu().numpy().astype(np.float32)

        # Set out-of-bounds pixels to NaN
        out_of_bounds_2d = out_of_bounds.reshape(output_height, output_width)
        projected[out_of_bounds_2d] = np.nan

        return projected
