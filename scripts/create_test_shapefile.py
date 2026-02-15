"""Create example shapefiles for testing VISTA features functionality.

All coordinates are geographic (lon, lat) as required by the shapefile standard.
The caller specifies a bounding box and all shapes are scaled relative to it.
"""
import argparse
import pathlib

try:
    import shapefile
except ImportError:
    print("Error: pyshp library is required")
    print("Install it with: pip install pyshp")
    exit(1)


def create_polygon_shapefile(output_path: str, lon_min: float, lat_min: float, lon_max: float, lat_max: float) -> None:
    """Create a shapefile with polygon features scaled to the given bounding box.

    Parameters
    ----------
    output_path : str
        Output path for the shapefile.
    lon_min : float
        Minimum longitude (degrees).
    lat_min : float
        Minimum latitude (degrees).
    lon_max : float
        Maximum longitude (degrees).
    lat_max : float
        Maximum latitude (degrees).
    """
    w = shapefile.Writer(str(output_path), shapeType=shapefile.POLYGON)
    dlon = lon_max - lon_min
    dlat = lat_max - lat_min

    w.field('name', 'C', size=50)
    w.field('area', 'N', decimal=6)

    # Rectangle in the lower-left quadrant (10-40% of bbox)
    x0, x1 = lon_min + 0.10 * dlon, lon_min + 0.40 * dlon
    y0, y1 = lat_min + 0.10 * dlat, lat_min + 0.40 * dlat
    w.poly([
        [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]
    ])
    w.record('Rectangle', abs((x1 - x0) * (y1 - y0)))

    # Triangle in the upper-left quadrant
    tx0 = lon_min + 0.10 * dlon
    tx1 = lon_min + 0.40 * dlon
    ty0 = lat_min + 0.60 * dlat
    ty1 = lat_min + 0.90 * dlat
    w.poly([
        [[tx0, ty0], [tx1, ty0], [(tx0 + tx1) / 2, ty1], [tx0, ty0]]
    ])
    w.record('Triangle', abs(0.5 * (tx1 - tx0) * (ty1 - ty0)))

    # Pentagon in the upper-right quadrant
    import math
    cx = lon_min + 0.75 * dlon
    cy = lat_min + 0.75 * dlat
    r_lon = 0.12 * dlon
    r_lat = 0.12 * dlat
    pts = []
    for i in range(5):
        angle = math.pi / 2 + 2 * math.pi * i / 5
        pts.append([cx + r_lon * math.cos(angle), cy + r_lat * math.sin(angle)])
    pts.append(pts[0])  # close ring
    w.poly([pts])
    w.record('Pentagon', abs(r_lon * r_lat * 2.378))  # approximate area

    # Polygon with hole in the lower-right quadrant
    ox0, ox1 = lon_min + 0.60 * dlon, lon_min + 0.90 * dlon
    oy0, oy1 = lat_min + 0.10 * dlat, lat_min + 0.40 * dlat
    outer = [[ox0, oy0], [ox1, oy0], [ox1, oy1], [ox0, oy1], [ox0, oy0]]
    # Hole inset by 25% of the sub-rectangle
    hx0 = ox0 + 0.25 * (ox1 - ox0)
    hx1 = ox1 - 0.25 * (ox1 - ox0)
    hy0 = oy0 + 0.25 * (oy1 - oy0)
    hy1 = oy1 - 0.25 * (oy1 - oy0)
    hole = [[hx0, hy0], [hx1, hy0], [hx1, hy1], [hx0, hy1], [hx0, hy0]]
    w.poly([outer, hole])
    w.record('Polygon with Hole', abs((ox1 - ox0) * (oy1 - oy0) - (hx1 - hx0) * (hy1 - hy0)))

    w.close()
    print(f"Created polygon shapefile: {output_path}")


def create_polyline_shapefile(
    output_path: str, lon_min: float, lat_min: float, lon_max: float, lat_max: float,
) -> None:
    """Create a shapefile with polyline features scaled to the given bounding box.

    Parameters
    ----------
    output_path : str
        Output path for the shapefile.
    lon_min : float
        Minimum longitude (degrees).
    lat_min : float
        Minimum latitude (degrees).
    lon_max : float
        Maximum longitude (degrees).
    lat_max : float
        Maximum latitude (degrees).
    """
    w = shapefile.Writer(str(output_path), shapeType=shapefile.POLYLINE)
    dlon = lon_max - lon_min
    dlat = lat_max - lat_min

    w.field('name', 'C', size=50)
    w.field('length', 'N', decimal=6)

    # Curved path across the lower third
    w.line([[
        [lon_min + 0.05 * dlon, lat_min + 0.25 * dlat],
        [lon_min + 0.30 * dlon, lat_min + 0.35 * dlat],
        [lon_min + 0.55 * dlon, lat_min + 0.20 * dlat],
        [lon_min + 0.80 * dlon, lat_min + 0.30 * dlat],
        [lon_min + 0.95 * dlon, lat_min + 0.25 * dlat],
    ]])
    w.record('Curved Path', 0.9 * dlon)

    # Zigzag across the middle
    w.line([[
        [lon_min + 0.05 * dlon, lat_min + 0.50 * dlat],
        [lon_min + 0.20 * dlon, lat_min + 0.60 * dlat],
        [lon_min + 0.35 * dlon, lat_min + 0.45 * dlat],
        [lon_min + 0.50 * dlon, lat_min + 0.60 * dlat],
        [lon_min + 0.65 * dlon, lat_min + 0.45 * dlat],
        [lon_min + 0.80 * dlon, lat_min + 0.60 * dlat],
        [lon_min + 0.95 * dlon, lat_min + 0.50 * dlat],
    ]])
    w.record('Zigzag Path', 1.2 * dlon)

    # Multi-part line (two parallel segments) across the upper third
    w.line([
        [
            [lon_min + 0.10 * dlon, lat_min + 0.75 * dlat],
            [lon_min + 0.45 * dlon, lat_min + 0.80 * dlat],
            [lon_min + 0.90 * dlon, lat_min + 0.75 * dlat],
        ],
        [
            [lon_min + 0.10 * dlon, lat_min + 0.85 * dlat],
            [lon_min + 0.45 * dlon, lat_min + 0.90 * dlat],
            [lon_min + 0.90 * dlon, lat_min + 0.85 * dlat],
        ],
    ])
    w.record('Multi-part Path', 1.6 * dlon)

    w.close()
    print(f"Created polyline shapefile: {output_path}")


def create_point_shapefile(
    output_path: str, lon_min: float, lat_min: float, lon_max: float, lat_max: float,
) -> None:
    """Create a shapefile with point features distributed within the bounding box.

    Parameters
    ----------
    output_path : str
        Output path for the shapefile.
    lon_min : float
        Minimum longitude (degrees).
    lat_min : float
        Minimum latitude (degrees).
    lon_max : float
        Maximum longitude (degrees).
    lat_max : float
        Maximum latitude (degrees).
    """
    w = shapefile.Writer(str(output_path), shapeType=shapefile.POINT)
    dlon = lon_max - lon_min
    dlat = lat_max - lat_min

    w.field('name', 'C', size=50)
    w.field('value', 'N', decimal=2)

    # Points distributed across the bounding box
    points_data = [
        (0.15, 0.20, 'Point A', 10.5),
        (0.35, 0.30, 'Point B', 25.3),
        (0.55, 0.15, 'Point C', 15.7),
        (0.75, 0.25, 'Point D', 30.1),
        (0.90, 0.35, 'Point E', 20.9),
        (0.20, 0.60, 'Point F', 18.2),
        (0.50, 0.70, 'Point G', 22.6),
        (0.80, 0.65, 'Point H', 28.4),
        (0.40, 0.85, 'Point I', 12.0),
        (0.65, 0.90, 'Point J', 35.5),
    ]

    for frac_lon, frac_lat, name, value in points_data:
        lon = lon_min + frac_lon * dlon
        lat = lat_min + frac_lat * dlat
        w.point(lon, lat)
        w.record(name, value)

    w.close()
    print(f"Created point shapefile: {output_path}")


def create_multipoint_shapefile(
    output_path: str, lon_min: float, lat_min: float, lon_max: float, lat_max: float,
) -> None:
    """Create a shapefile with multipoint features within the bounding box.

    Parameters
    ----------
    output_path : str
        Output path for the shapefile.
    lon_min : float
        Minimum longitude (degrees).
    lat_min : float
        Minimum latitude (degrees).
    lon_max : float
        Maximum longitude (degrees).
    lat_max : float
        Maximum latitude (degrees).
    """
    w = shapefile.Writer(str(output_path), shapeType=shapefile.MULTIPOINT)
    dlon = lon_max - lon_min
    dlat = lat_max - lat_min

    w.field('name', 'C', size=50)
    w.field('count', 'N')

    # Cluster A — lower-left region
    cluster_a = [
        [lon_min + 0.20 * dlon, lat_min + 0.20 * dlat],
        [lon_min + 0.22 * dlon, lat_min + 0.23 * dlat],
        [lon_min + 0.25 * dlon, lat_min + 0.21 * dlat],
        [lon_min + 0.21 * dlon, lat_min + 0.26 * dlat],
        [lon_min + 0.24 * dlon, lat_min + 0.24 * dlat],
    ]
    w.multipoint(cluster_a)
    w.record('Cluster A', len(cluster_a))

    # Cluster B — upper-right region
    cluster_b = [
        [lon_min + 0.72 * dlon, lat_min + 0.75 * dlat],
        [lon_min + 0.74 * dlon, lat_min + 0.78 * dlat],
        [lon_min + 0.77 * dlon, lat_min + 0.76 * dlat],
        [lon_min + 0.73 * dlon, lat_min + 0.80 * dlat],
        [lon_min + 0.76 * dlon, lat_min + 0.78 * dlat],
        [lon_min + 0.79 * dlon, lat_min + 0.77 * dlat],
    ]
    w.multipoint(cluster_b)
    w.record('Cluster B', len(cluster_b))

    w.close()
    print(f"Created multipoint shapefile: {output_path}")


def main():
    """Create all example shapefiles"""
    parser = argparse.ArgumentParser(
        description="Create test shapefiles with geographic coordinates for VISTA."
    )
    parser.add_argument(
        "--lon-min", type=float, default=-105.3, help="Minimum longitude in degrees (default: -105.3)"
    )
    parser.add_argument(
        "--lat-min", type=float, default=39.95, help="Minimum latitude in degrees (default: 39.95)"
    )
    parser.add_argument(
        "--lon-max", type=float, default=-105.2, help="Maximum longitude in degrees (default: -105.2)"
    )
    parser.add_argument(
        "--lat-max", type=float, default=40.05, help="Maximum latitude in degrees (default: 40.05)"
    )
    parser.add_argument(
        "--output-dir", type=str, default=None,
        help="Output directory (default: <project>/data/shapefiles)"
    )
    args = parser.parse_args()

    # Create output directory
    if args.output_dir:
        output_dir = pathlib.Path(args.output_dir)
    else:
        output_dir = pathlib.Path(__file__).parent.parent / "data" / "shapefiles"
    output_dir.mkdir(parents=True, exist_ok=True)

    bbox = (args.lon_min, args.lat_min, args.lon_max, args.lat_max)

    print(f"Bounding box: lon [{bbox[0]}, {bbox[2]}], lat [{bbox[1]}, {bbox[3]}]")
    print()

    # Create different shapefile types
    create_polygon_shapefile(output_dir / "test_polygons.shp", *bbox)
    create_polyline_shapefile(output_dir / "test_polylines.shp", *bbox)
    create_point_shapefile(output_dir / "test_points.shp", *bbox)
    create_multipoint_shapefile(output_dir / "test_multipoints.shp", *bbox)

    print()
    print("=" * 60)
    print("All test shapefiles created successfully!")
    print(f"Location: {output_dir}")
    print("=" * 60)
    print("\nYou can now load these shapefiles in VISTA:")
    print("File > Load Shapefile")
    print("\nShapefiles created:")
    print("  - test_polygons.shp (rectangle, triangle, pentagon, polygon with hole)")
    print("  - test_polylines.shp (curved path, zigzag, multi-part lines)")
    print("  - test_points.shp (10 individual points)")
    print("  - test_multipoints.shp (2 point clusters)")


if __name__ == "__main__":
    main()
