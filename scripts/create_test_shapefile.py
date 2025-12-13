"""Create example shapefiles for testing VISTA features functionality"""
import pathlib

try:
    import shapefile
except ImportError:
    print("Error: pyshp library is required")
    print("Install it with: pip install pyshp")
    exit(1)


def create_polygon_shapefile(output_path):
    """Create a shapefile with polygon features"""
    w = shapefile.Writer(str(output_path), shapeType=shapefile.POLYGON)

    # Define fields
    w.field('name', 'C', size=50)
    w.field('area', 'N', decimal=2)

    # Add a rectangle
    w.poly([
        [[100, 100], [200, 100], [200, 200], [100, 200], [100, 100]]
    ])
    w.record('Rectangle Area', 10000.00)

    # Add a triangle
    w.poly([
        [[250, 100], [350, 100], [300, 200], [250, 100]]
    ])
    w.record('Triangle Area', 5000.00)

    # Add a pentagon
    w.poly([
        [[400, 150], [450, 120], [480, 180], [430, 220], [380, 190], [400, 150]]
    ])
    w.record('Pentagon Area', 7500.00)

    # Add a polygon with a hole
    outer_ring = [[550, 100], [650, 100], [650, 200], [550, 200], [550, 100]]
    hole = [[575, 125], [625, 125], [625, 175], [575, 175], [575, 125]]
    w.poly([outer_ring, hole])
    w.record('Polygon with Hole', 8500.00)

    w.close()
    print(f"Created polygon shapefile: {output_path}")


def create_polyline_shapefile(output_path):
    """Create a shapefile with polyline features"""
    w = shapefile.Writer(str(output_path), shapeType=shapefile.POLYLINE)

    # Define fields
    w.field('name', 'C', size=50)
    w.field('length', 'N', decimal=2)

    # Add a simple line
    w.line([
        [[100, 300], [200, 350], [300, 320], [400, 380]]
    ])
    w.record('Curved Path', 320.50)

    # Add a zigzag line
    w.line([
        [[100, 450], [150, 500], [200, 450], [250, 500], [300, 450]]
    ])
    w.record('Zigzag Path', 260.00)

    # Add a multi-part line
    w.line([
        [[400, 300], [500, 320], [600, 310]],
        [[400, 400], [500, 420], [600, 410]]
    ])
    w.record('Multi-part Path', 410.00)

    w.close()
    print(f"Created polyline shapefile: {output_path}")


def create_point_shapefile(output_path):
    """Create a shapefile with point features"""
    w = shapefile.Writer(str(output_path), shapeType=shapefile.POINT)

    # Define fields
    w.field('name', 'C', size=50)
    w.field('value', 'N', decimal=2)

    # Add individual points
    points_data = [
        ([100, 600], 'Point A', 10.5),
        ([200, 620], 'Point B', 25.3),
        ([300, 590], 'Point C', 15.7),
        ([400, 610], 'Point D', 30.1),
        ([500, 630], 'Point E', 20.9),
        ([150, 700], 'Point F', 18.2),
        ([250, 720], 'Point G', 22.6),
        ([350, 690], 'Point H', 28.4),
    ]

    for coords, name, value in points_data:
        w.point(coords[0], coords[1])
        w.record(name, value)

    w.close()
    print(f"Created point shapefile: {output_path}")


def create_multipoint_shapefile(output_path):
    """Create a shapefile with multipoint features"""
    w = shapefile.Writer(str(output_path), shapeType=shapefile.MULTIPOINT)

    # Define fields
    w.field('name', 'C', size=50)
    w.field('count', 'N')

    # Add a cluster of points
    w.multipoint([
        [550, 600], [560, 610], [570, 605], [555, 620], [565, 615]
    ])
    w.record('Cluster A', 5)

    # Add another cluster
    w.multipoint([
        [620, 650], [630, 660], [640, 655], [625, 670], [635, 665], [645, 660]
    ])
    w.record('Cluster B', 6)

    w.close()
    print(f"Created multipoint shapefile: {output_path}")


def main():
    """Create all example shapefiles"""
    # Create output directory
    output_dir = pathlib.Path(__file__).parent.parent / "data" / "shapefiles"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create different shapefile types
    create_polygon_shapefile(output_dir / "test_polygons.shp")
    create_polyline_shapefile(output_dir / "test_polylines.shp")
    create_point_shapefile(output_dir / "test_points.shp")
    create_multipoint_shapefile(output_dir / "test_multipoints.shp")

    print("\n" + "="*60)
    print("All test shapefiles created successfully!")
    print(f"Location: {output_dir}")
    print("="*60)
    print("\nYou can now load these shapefiles in VISTA:")
    print("File > Load Shapefile")
    print("\nShapefiles created:")
    print("  - test_polygons.shp (rectangles, triangles, pentagon, polygon with hole)")
    print("  - test_polylines.shp (curved paths, zigzag, multi-part lines)")
    print("  - test_points.shp (individual points)")
    print("  - test_multipoints.shp (point clusters)")


if __name__ == "__main__":
    main()
