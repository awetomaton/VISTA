Contributing to VISTA
=====================

Thank you for your interest in contributing to VISTA!

.. note::
   This section is under development. More detailed contribution guidelines will be added in future versions.

Development Setup
-----------------

See :doc:`../getting_started/installation` for setting up a development environment.

Code Style
----------

VISTA follows specific coding conventions:

* NumPy-style docstrings
* 120 character line length
* Alphabetical import ordering with ``vista`` imports last
* See ``CLAUDE.md`` in the repository for complete style guidelines

Submitting Changes
------------------

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Submit a pull request

Testing
-------

Run tests using pytest:

.. code-block:: bash

   pytest

For PyQt6 GUI testing:

.. code-block:: bash

   pytest --pyqt

Reporting Issues
----------------

Report bugs and feature requests at: https://github.com/awetomaton/VISTA/issues
