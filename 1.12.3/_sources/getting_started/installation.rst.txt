Installation
============

Requirements
------------

VISTA requires Python 3.9 or higher.

Installing from PyPI
--------------------

The easiest way to install VISTA is from PyPI using pip:

.. code-block:: bash

   pip install vista-imagery

This will install VISTA and all of its dependencies.

.. image:: https://github.com/awetomaton/VISTA/releases/download/MEDIA/vista-1.10.0-install.gif
   :alt: Install
   :align: center

Installing from Source
----------------------

To install VISTA from source, clone the repository and install in development mode:

.. code-block:: bash

   git clone https://github.com/awetomaton/VISTA.git
   cd VISTA
   pip install -e .

Development Installation
------------------------

For development, install with the optional development dependencies:

.. code-block:: bash

   pip install -e ".[dev]"

This installs additional tools for testing and code quality:

* pytest - Testing framework
* pytest-qt - PyQt testing support
* black - Code formatter
* ruff - Fast Python linter

Conda Environment
-----------------

If you prefer using conda, you can create an environment and install VISTA:

.. code-block:: bash

   conda create -n vista python=3.13  # or any version >= 3.9
   conda activate vista
   pip install vista-imagery

Verifying Installation
----------------------

Launch the application:

.. code-block:: bash

   vista

You should see the VISTA main window appear.

Dependencies
------------

VISTA depends on the following packages:

* **astropy** - Astronomy and astrophysics library
* **darkdetect** - Dark mode detection
* **h5py** - HDF5 file support
* **numba** - JIT compilation for performance-critical routines
* **numpy** - Numerical computing
* **pandas** - Data analysis and manipulation
* **Pillow** - Image file I/O
* **PyQt6** - Qt GUI framework
* **pyqtgraph** - Scientific graphics and GUI library
* **pyshp** - Shapefile reading/writing
* **scikit-image** - Image processing
* **scipy** - Scientific computing
* **shapely** - Geometric operations

These dependencies are automatically installed when you install VISTA.

Troubleshooting
---------------

PyQt6 Installation Issues
~~~~~~~~~~~~~~~~~~~~~~~~~~

If you encounter issues installing PyQt6, make sure you have the necessary system dependencies:

**Linux (Ubuntu/Debian):**

.. code-block:: bash

   sudo apt-get install python3-pyqt6

**macOS:**

PyQt6 should install without issues via pip. If you encounter problems, try installing via conda:

.. code-block:: bash

   conda install -c conda-forge pyqt

**Windows:**

PyQt6 should install without issues via pip. Ensure you have the latest version of pip:

.. code-block:: bash

   python -m pip install --upgrade pip

Permission Errors
~~~~~~~~~~~~~~~~~

If you get permission errors during installation, try using a virtual environment:

.. code-block:: bash

   python -m venv vista_env
   source vista_env/bin/activate  # On Windows: vista_env\Scripts\activate
   pip install vista-imagery

Or use the ``--user`` flag:

.. code-block:: bash

   pip install --user vista-imagery
