Features and Annotations
=========================

VISTA provides several types of features and annotations for marking regions of interest,
importing geospatial data, and creating persistent overlays on imagery. These tools enable
spatial analysis, data organization, and collaborative workflows.

Overview
--------

VISTA supports three main types of features:

**Areas of Interest (AOIs)**
   Rectangular regions for extracting sub-imagery, defining analysis zones, or organizing
   spatial data. AOIs are frame-independent and persist across the entire imagery sequence.

**Placemarks**
   Point features marking specific locations with pixel coordinates and optional geodetic
   coordinates (latitude, longitude, altitude). Useful for marking landmarks, targets,
   or points of interest.

**Shapefiles**
   Vector geospatial data imported from standard shapefile formats (.shp). Supports points,
   lines, and polygons with associated attribute data.

.. _aois-areas-of-interest:

Areas of Interest (AOIs)
------------------------

AOIs define rectangular regions on imagery for analysis, extraction, or organization. They
are frame-independent, meaning the same AOI applies to all frames in the imagery sequence.

Creating AOIs
~~~~~~~~~~~~~

.. image:: https://github.com/awetomaton/VISTA/releases/download/MEDIA/user_guide_features_create_aoi.gif
   :alt: Create AOI
   :align: center

**Interactive Creation:**

1. Open the **AOIs Panel** from the Data Panels
2. Click **Add AOI** button
3. Draw a rectangle on the imagery viewer by clicking and dragging
4. Adjust size and position by dragging the corner handles
5. Double-click the AOI to rename it

**Programmatic Creation:**

.. code-block:: python

   from vista.aoi.aoi import AOI

   # Create an AOI at (row=100, col=200) with width=150, height=100
   aoi = AOI(
       name="Target Region",
       x=200,          # Column (x-coordinate)
       y=100,          # Row (y-coordinate)
       width=150,      # Width in pixels
       height=100,     # Height in pixels
       color='r',      # Red color
       visible=True
   )

   # Check if a point is inside the AOI
   is_inside = aoi.contains_point(x=250, y=120)  # True

   # Get bounding box
   x_min, y_min, x_max, y_max = aoi.get_bounds()

AOI Controls
~~~~~~~~~~~~
 * Rename AOI by double-clicking on the Name column
 * Users can drag any selected AOIs. AOIs are selected by default. De-select AOIs by holding ctrl/cmd and clicking on 
   their row in the AOIs table.
 * Change AOI size by clicking and dragging on the lower-right corner

.. image:: https://github.com/awetomaton/VISTA/releases/download/MEDIA/user_guide_features_control_aoi.gif
   :alt: Control AOI
   :align: center

AOI Properties
~~~~~~~~~~~~~~

Each AOI has the following properties:

:name: Unique identifier for the AOI (string)
:x: Left edge column coordinate (pixels)
:y: Top edge row coordinate (pixels)
:width: Width of rectangle (pixels)
:height: Height of rectangle (pixels)
:color: Display color ('r', 'g', 'b', 'y', 'c', 'm', etc.)
:visible: Whether the AOI is displayed (boolean)

AOI Operations
~~~~~~~~~~~~~~

**Extracting Sub-Imagery**

Extract imagery data within an AOI:

.. code-block:: python

   # Get imagery data within AOI bounds
   x_min, y_min, x_max, y_max = aoi.get_bounds()

   # Extract from single frame
   sub_image = imagery.images[frame_idx,
                               int(y_min):int(y_max),
                               int(x_min):int(x_max)]

   # Or use imagery slicing with AOI
   aoi_imagery = imagery.get_aoi(x_min, y_min, x_max, y_max)

Saving and Loading AOIs from CSV
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

AOIs can be saved to and loaded from CSV (Comma-Separated Values) files for sharing,
backup, or batch processing. This allows you to define AOIs in a spreadsheet or text
editor and import them into VISTA.

**CSV Format Requirements**

The CSV file must contain the following columns (case-sensitive):

:Name: Unique identifier for the AOI (string, required)
:X: Left edge column coordinate in pixels (float, required)
:Y: Top edge row coordinate in pixels (float, required)
:Width: Width of rectangle in pixels (float, required)
:Height: Height of rectangle in pixels (float, required)
:Color: Display color code (string, optional, default: 'y')
:Visible: Visibility flag (boolean, optional, default: True)

**Example CSV File**

.. code-block:: text

   Name,X,Y,Width,Height,Color,Visible
   Search Zone,100.0,200.0,500.0,300.0,r,True
   Analysis Area,600.0,150.0,400.0,450.0,g,True
   Background Region,50.0,50.0,200.0,200.0,b,False
   Target Zone,800.0,600.0,150.0,100.0,y,True

**Loading AOIs via GUI:**

1. Open the **AOIs Panel** from the Data Panels
2. Click **File → Import → AOIs from CSV**
3. Select your CSV file
4. AOIs are automatically created and displayed on the imagery

**Loading AOIs Programmatically:**

.. code-block:: python

   import pandas as pd
   from vista.aoi.aoi import AOI

   # Read CSV file
   df = pd.read_csv('aois.csv')

   # Create AOIs from DataFrame
   aois = []
   for idx in range(len(df)):
       # Get single row as DataFrame
       row_df = df.iloc[idx:idx+1]
       aoi = AOI.from_dataframe(row_df)
       aois.append(aoi)

   # Or process row by row
   for idx, row in df.iterrows():
       aoi = AOI(
           name=row['Name'],
           x=row['X'],
           y=row['Y'],
           width=row['Width'],
           height=row['Height'],
           color=row.get('Color', 'y'),
           visible=row.get('Visible', True)
       )
       aois.append(aoi)

**Exporting AOIs to CSV:**

Save your AOIs for sharing or documentation:

.. code-block:: python

   import pandas as pd
   from vista.aoi.aoi import AOI

   # Export single AOI
   aoi = AOI(name="My Region", x=100, y=200, width=500, height=300)
   df = aoi.to_dataframe()
   df.to_csv('single_aoi.csv', index=False)

   # Export multiple AOIs
   aoi_dataframes = [aoi.to_dataframe() for aoi in aois_list]
   combined_df = pd.concat(aoi_dataframes, ignore_index=True)
   combined_df.to_csv('all_aois.csv', index=False)

**CSV Format Notes:**

- **Required columns**: Name, X, Y, Width, Height must be present
- **Coordinate system**: X and Y are pixel coordinates (column, row)
- **Dimensions**: Width and Height are in pixels
- **Color codes**: Use single character codes ('r', 'g', 'b', 'y', 'c', 'm', 'k', 'w')
- **Boolean values**: Use True/False (case-sensitive) for Visible column
- **Decimal precision**: Use floating-point values for sub-pixel positioning (e.g., 100.5)
- **Header row**: First row must contain column names exactly as shown above
- **Encoding**: Use UTF-8 encoding for compatibility

**Common CSV Workflows:**

**Batch Create Analysis Regions:**
   Define multiple AOIs in a spreadsheet and import them all at once.

**Template-Based AOIs:**
   Create a template CSV with standard AOI layouts for consistent analysis across datasets.

**Automated AOI Generation:**
   Use Python scripts to generate AOI CSV files based on detection results or grid patterns.

**Collaborative Workflows:**
   Share AOI definitions between team members or projects via CSV files.

**Validation and Documentation:**
   Export AOIs to CSV to document analysis regions for reports or publications.

**Dictionary-Based Saving and Loading**

AOIs can also be saved as dictionaries for programmatic workflows:

.. code-block:: python

   # Save AOI to dictionary
   aoi_dict = aoi.to_dict()

   # Create AOI from dictionary
   restored_aoi = AOI.from_dict(aoi_dict)

**Managing Multiple AOIs**

The AOIs Panel provides tools for:

- **Show/Hide**: Toggle visibility of individual AOIs
- **Delete**: Remove AOIs from the project
- **Rename**: Change AOI names
- **Color**: Modify display colors
- **Export**: Save AOI definitions to file
- **Import**: Load AOI definitions from file

Use Cases
~~~~~~~~~

**Spatial Analysis Zones**
   Define regions for statistical analysis (mean, std, max, etc.)

**Chip Extraction**
   Extract image chips around detections or targets

**Masking**
   Define regions to include or exclude from processing

**Collaborative Workflows**
   Share AOI definitions between team members

.. _placemarks:

Placemarks
----------

Placemarks are point features that mark specific locations on imagery with both pixel
and optional geodetic coordinates.

.. image:: https://github.com/awetomaton/VISTA/releases/download/MEDIA/user_guide_features_placemarks.gif
   :alt: Shapefiles
   :align: center

Creating Placemarks
~~~~~~~~~~~~~~~~~~~

**Interactive Creation:**

1. Open the **Features Panel** from the Data Panels
2. Click **Add Placemark** button
3. Click on the imagery to place the placemark
4. Enter a name and optional description

**Programmatic Creation:**

.. code-block:: python

   from vista.features.feature import PlacemarkFeature

   # Create placemark with pixel coordinates
   placemark = PlacemarkFeature(
       name="Launch Site",
       geometry={
           'row': 512.5,
           'col': 1024.3,
           'lat': 28.5721,     # Optional: latitude in degrees
           'lon': -80.6480,    # Optional: longitude in degrees
           'alt': 0.0          # Optional: altitude in km
       },
       color='r',
       visible=True
   )

Loading Placemarks from CSV
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Placemarks can be imported in bulk from CSV (Comma-Separated Values) files. This is useful
for loading predefined reference points, ground truth data, or coordinate lists.

**CSV Format Requirements**

The CSV file must contain the following columns (case-sensitive):

:Name: Descriptive name for the placemark (string, required)
:Row: Pixel row coordinate (float, required)
:Col: Pixel column coordinate (float, required)
:Lat: Latitude in decimal degrees (float, optional)
:Lon: Longitude in decimal degrees (float, optional)
:Alt: Altitude in kilometers (float, optional)
:Color: Display color code (string, optional, default: 'y')
:Visible: Visibility flag (boolean, optional, default: True)

**Example CSV File**

.. code-block:: text

   Name,Row,Col,Lat,Lon,Alt,Color,Visible
   Launch Pad,512.5,1024.3,28.5721,-80.6480,0.0,r,True
   Airport,450.2,890.7,28.4294,-81.3089,0.029,b,True
   Target Site,600.0,800.0,28.3922,-80.6077,0.0,g,True
   Waypoint 1,300.5,500.2,,,,,False

**Loading via GUI:**

1. Open the **Features Panel** from the Data Panels
2. Click **File → Import → Placemarks from CSV**
3. Select your CSV file
4. Placemarks are automatically created and displayed

**Loading Programmatically:**

.. code-block:: python

   import pandas as pd
   from vista.features.feature import PlacemarkFeature

   # Read CSV file
   df = pd.read_csv('placemarks.csv')

   # Create placemarks from DataFrame
   placemarks = []
   for idx, row in df.iterrows():
       placemark = PlacemarkFeature(
           name=row['Name'],
           geometry={
               'row': row['Row'],
               'col': row['Col'],
               'lat': row.get('Lat', None),
               'lon': row.get('Lon', None),
               'alt': row.get('Alt', None)
           },
           color=row.get('Color', 'y'),
           visible=row.get('Visible', True)
       )
       placemarks.append(placemark)

   # Add to viewer
   for placemark in placemarks:
       viewer.add_feature(placemark)

**CSV Format Notes:**

- **Required columns**: Name, Row, Col must be present
- **Optional coordinates**: Lat, Lon, Alt can be empty or omitted
- **Color codes**: Use single character codes ('r', 'g', 'b', 'y', 'c', 'm', 'k', 'w')
- **Coordinate precision**: Use sufficient decimal places for pixel coordinates (e.g., 512.5, not 512)
- **Missing values**: Leave cells empty for optional fields (do not use "NaN" or "null")
- **Header row**: First row must contain column names exactly as shown above
- **Encoding**: Use UTF-8 encoding to support special characters in names

**Exporting Placemarks to CSV:**

Save your placemarks for sharing or backup:

.. code-block:: python

   import pandas as pd

   # Collect placemark data
   data = []
   for feature in viewer.features:
       if feature.feature_type == 'placemark':
           data.append({
               'Name': feature.name,
               'Row': feature.geometry['row'],
               'Col': feature.geometry['col'],
               'Lat': feature.geometry.get('lat', ''),
               'Lon': feature.geometry.get('lon', ''),
               'Alt': feature.geometry.get('alt', ''),
               'Color': feature.color,
               'Visible': feature.visible
           })

   # Create DataFrame and save
   df = pd.DataFrame(data)
   df.to_csv('exported_placemarks.csv', index=False)

**Common CSV Workflows:**

**Load GPS Waypoints:**
   If you have a GPS waypoint list, create a CSV with Lat/Lon coordinates.
   VISTA will convert to pixel coordinates if imagery has geolocation data.

**Batch Import Reference Points:**
   Create a CSV with known landmark locations for validation or calibration.

**Ground Truth Data:**
   Import target positions from external sources for algorithm validation.

**Coordinate Conversion:**
   Load placemarks with pixel OR geodetic coordinates. VISTA can convert between
   coordinate systems when sensor data is available.

Placemark Properties
~~~~~~~~~~~~~~~~~~~~

:name: Descriptive name for the placemark
:geometry: Dictionary containing:
   - ``row``: Pixel row coordinate (float)
   - ``col``: Pixel column coordinate (float)
   - ``lat``: Latitude in degrees (float or None)
   - ``lon``: Longitude in degrees (float or None)
   - ``alt``: Altitude in kilometers (float or None)
:color: Display color
:visible: Whether the placemark is displayed
:uuid: Unique identifier (automatically generated)

Coordinate Conversion
~~~~~~~~~~~~~~~~~~~~~

When imagery has sensor and geolocation data, placemarks can convert between
pixel and geodetic coordinates:

.. code-block:: python

   from vista.transforms import pixel_to_geodetic, geodetic_to_pixel

   # Convert pixel coordinates to geodetic (if sensor data available)
   lat, lon, alt = pixel_to_geodetic(
       imagery,
       frame_idx=0,
       row=512.5,
       col=1024.3
   )

   # Convert geodetic coordinates to pixel
   row, col = geodetic_to_pixel(
       imagery,
       frame_idx=0,
       lat=28.5721,
       lon=-80.6480,
       alt=0.0
   )

Use Cases
~~~~~~~~~

**Landmark Identification**
   Mark known geographic features or locations

**Target Designation**
   Flag objects or areas of interest

**Ground Truth Data**
   Store reference points for validation

**Navigation Waypoints**
   Define locations for flight planning or navigation

.. _shapefiles:

Shapefiles
----------

VISTA can import and visualize vector geospatial data from standard ESRI shapefile format.
Shapefiles provide a way to overlay geospatial features (roads, boundaries, facilities, etc.)
on imagery.

.. image:: https://github.com/awetomaton/VISTA/releases/download/MEDIA/user_guide_features_shapefiles.gif
   :alt: Shapefiles
   :align: center


Importing Shapefiles
~~~~~~~~~~~~~~~~~~~~

**Via GUI:**

1. Open the **Features Panel**
2. Click **Import Shapefile** button
3. Select a `.shp` file
4. The shapefile is automatically converted to pixel coordinates if imagery has geolocation

**Programmatic Import:**

.. code-block:: python

   import shapefile
   from vista.features.feature import ShapefileFeature

   # Read shapefile
   sf = shapefile.Reader("data/boundaries.shp")

   # Create feature
   shapefile_feature = ShapefileFeature(
       name="Region Boundaries",
       geometry={
           'shapes': sf.shapes(),
           'records': sf.records(),
           'fields': sf.fields
       },
       color='g',
       visible=True
   )

Shapefile Geometry Types
~~~~~~~~~~~~~~~~~~~~~~~~~

VISTA supports the following shapefile geometry types:

**Point (Type 1)**
   Individual point locations (e.g., cities, facilities)

**PolyLine (Type 3)**
   Connected line segments (e.g., roads, rivers, flight paths)

**Polygon (Type 5)**
   Closed regions with boundaries (e.g., countries, lakes, restricted areas)

**MultiPoint (Type 8)**
   Collection of points (e.g., sensor network locations)

Coordinate Transformation
~~~~~~~~~~~~~~~~~~~~~~~~~~

Shapefiles typically use geodetic coordinates (latitude/longitude). VISTA automatically
transforms these to pixel coordinates using the imagery's geolocation data:

.. code-block:: python

   # Shapefile coordinates are in (lon, lat) format
   shapefile_lon = -80.6480
   shapefile_lat = 28.5721

   # Transform to pixel coordinates using imagery sensor data
   if imagery.sensor is not None:
       row, col = geodetic_to_pixel(
           imagery,
           frame_idx=0,
           lat=shapefile_lat,
           lon=shapefile_lon,
           alt=0.0
       )

Shapefile Attributes
~~~~~~~~~~~~~~~~~~~~

Shapefiles often contain attribute data (properties) associated with each feature:

.. code-block:: python

   # Access shapefile records (attributes)
   for record, shape in zip(sf.records(), sf.shapes()):
       name = record['NAME']        # Attribute field
       population = record['POP']   # Another attribute
       # Process shape and attributes...

Styling Shapefiles
~~~~~~~~~~~~~~~~~~

Customize the appearance of imported shapefiles:

.. code-block:: python

   shapefile_feature.color = 'b'    # Blue
   shapefile_feature.visible = True

   # In the Features Panel:
   # - Change color using the color picker
   # - Toggle visibility with checkbox
   # - Adjust line width or fill opacity

Use Cases
~~~~~~~~~

**Geographic Context**
   Overlay political boundaries, coastlines, or terrain features

**Infrastructure Mapping**
   Display roads, airports, facilities, or utilities

**Restricted Areas**
   Show no-fly zones, exclusion zones, or protected areas

**Mission Planning**
   Import flight paths, survey regions, or search areas

.. _feature-management:

Feature Management
------------------

Managing Features in the GUI
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The **Features Panel** provides centralized management of all features:

**Feature List**
   - Displays all placemarks, shapefiles, and custom features
   - Shows visibility status, color, and type
   - Allows selection of multiple features

**Actions**
   - **Show/Hide**: Toggle individual feature visibility
   - **Delete**: Remove features from the project
   - **Rename**: Change feature names
   - **Edit Properties**: Modify colors, styles, and attributes
   - **Export**: Save features to file
   - **Import**: Load features from file

**Filtering**
   - Filter by feature type (placemark, shapefile, polygon, etc.)
   - Search by name
   - Show only visible or hidden features

Saving and Loading Features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Features are automatically saved with VISTA project files (.h5):

.. code-block:: python

   # Save project with features
   # File → Save Project (includes all features)

   # Load project
   # File → Open Project (restores all features)

Export and Import
~~~~~~~~~~~~~~~~~

Features can be exported independently for sharing or backup:

**Export Features:**

.. code-block:: python

   import json

   # Export all features to JSON
   features_data = [feature.to_dict() for feature in features_list]

   with open('features.json', 'w') as f:
       json.dump(features_data, f, indent=2)

**Import Features:**

.. code-block:: python

   from vista.features.feature import Feature, PlacemarkFeature, ShapefileFeature

   # Import features from JSON
   with open('features.json', 'r') as f:
       features_data = json.load(f)

   features = []
   for data in features_data:
       if data['feature_type'] == 'placemark':
           features.append(PlacemarkFeature.from_dict(data))
       elif data['feature_type'] == 'shapefile':
           features.append(ShapefileFeature.from_dict(data))
       else:
           features.append(Feature.from_dict(data))

Performance Considerations
~~~~~~~~~~~~~~~~~~~~~~~~~~

**Large Shapefiles**
   - Shapefiles with thousands of polygons may slow rendering
   - Consider simplifying geometry or using level-of-detail techniques
   - Toggle visibility of unused layers

**Many Features**
   - Limit the number of visible features to improve performance
   - Use filtering to show only relevant features
   - Group related features into layers

**Coordinate Transformations**
   - Transformations are cached to improve performance
   - Re-transformation occurs when sensor data changes

.. _feature-workflows:

Common Workflows
----------------

Workflow 1: Extract Detections in AOI
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Extract and analyze only detections within a specific region:

.. code-block:: python

   # Define AOI
   aoi = AOI(name="Search Zone", x=100, y=200, width=500, height=300)

   # Filter detections within AOI
   filtered_detections = []
   for detection in detections:
       if aoi.contains_point(detection.col, detection.row):
           filtered_detections.append(detection)

   print(f"Found {len(filtered_detections)} detections in AOI")

Workflow 2: Overlay Reference Data
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Import shapefile with known features and compare with detections:

.. code-block:: python

   # Import shapefile with known facility locations
   facilities_shapefile = import_shapefile("facilities.shp")

   # Convert shapefile points to pixel coordinates
   # Compare with detected objects
   # Flag detections near known facilities

Workflow 3: Multi-Region Analysis
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Define multiple AOIs for comparative analysis:

.. code-block:: python

   # Create multiple AOIs
   aoi_north = AOI(name="North Sector", x=0, y=0, width=512, height=384)
   aoi_south = AOI(name="South Sector", x=0, y=384, width=512, height=384)

   # Extract statistics for each region
   for aoi in [aoi_north, aoi_south]:
       x_min, y_min, x_max, y_max = aoi.get_bounds()
       sub_image = imagery.images[0, int(y_min):int(y_max), int(x_min):int(x_max)]
       print(f"{aoi.name}: mean={sub_image.mean():.2f}, std={sub_image.std():.2f}")

Workflow 4: Geodetic Reference Points
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Create placemarks with known geodetic coordinates for validation:

.. code-block:: python

   # Create ground truth placemarks
   ground_truth = [
       PlacemarkFeature(
           name="Airport",
           geometry={'row': 512, 'col': 1024,
                    'lat': 28.4294, 'lon': -81.3089, 'alt': 0.029}
       ),
       PlacemarkFeature(
           name="Launch Pad",
           geometry={'row': 600, 'col': 800,
                    'lat': 28.5721, 'lon': -80.6480, 'alt': 0.0}
       )
   ]

   # Compare detected positions with ground truth
   # Calculate position errors

Controls
--------



Tips and Best Practices
------------------------

**Organization**
   - Use descriptive names for AOIs and features
   - Color-code features by type or purpose
   - Group related features using naming conventions (e.g., "Target_1", "Target_2")

**Performance**
   - Hide unused features to improve rendering speed
   - Simplify complex shapefiles before importing
   - Limit the number of visible AOIs to 10-20 for best performance

**Coordinate Systems**
   - Always verify coordinate system of imported shapefiles
   - Check that geodetic coordinates match your imagery's projection
   - Use sensor calibration data for accurate transformations

**Collaboration**
   - Export features as JSON for sharing with team members
   - Document AOI purposes in the name or description
   - Use consistent naming conventions across projects

**Validation**
   - Cross-check placemark coordinates with known landmarks
   - Verify AOI boundaries match intended regions
   - Test shapefile imports on small datasets first

See Also
--------

**API References:**

- :class:`vista.aoi.aoi.AOI` - AOI data model
- :class:`vista.features.feature.Feature` - Generic feature class
- :class:`vista.features.feature.PlacemarkFeature` - Placemark feature class
- :class:`vista.features.feature.ShapefileFeature` - Shapefile feature class

**Related Sections:**

- :doc:`imagery` - Working with imagery data
- :doc:`detections` - Detection and tracking
- :doc:`interface` - User interface overview
