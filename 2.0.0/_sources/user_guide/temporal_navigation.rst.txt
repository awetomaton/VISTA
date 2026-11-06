Time and Frame Navigation
=========================

VISTA can align imagery, detections, and tracks by timestamp or by frame number. The active display timeline is rebuilt
from the selected imagery and the visible overlays for the selected sensor.

Choosing the Timeline Type
--------------------------

VISTA uses the following rules:

1. If every displayed item has timestamps, VISTA uses a **time-based** timeline.
2. Otherwise, if every displayed item has frame numbers, VISTA uses a **frame-based** timeline.
3. If the items do not share either coordinate system, VISTA cannot build a timeline. Add matching times or frames,
   hide the incompatible overlays, or select compatible data.

When data contains both timestamps and frame numbers, timestamps are preferred. The timeline contains the sorted union
of the values present in the selected imagery and visible tracks and detectors.

Sparse and Multi-Rate Imagery
-----------------------------

Selected imagery layers do not need identical sampling rates or identical frame lists. For each timeline value, VISTA
shows the exact imagery sample when one exists. Otherwise, it keeps showing the nearest preceding sample. A layer is
blank before its first available value.

This behavior supports:

* imagery datastreams with different cadences
* spatial crops recorded only at selected times or frames
* tracks or detections at values not represented by every imagery layer

Playback Controls
-----------------

The slider and previous/next buttons move through timeline indices rather than assuming contiguous frame numbers.
The label identifies the active **Time** or **Frame** value and its position in the timeline.

* **Play/Pause** or ``Space`` starts and stops playback.
* **Previous/Next** or ``Left``/``Right`` and ``A``/``D`` moves one timeline sample.
* **Reverse** changes playback direction.
* **FPS** accepts positive or negative values; a negative value selects reverse playback.
* **Bounce Mode** reverses direction at configured start and end indices.

Without Bounce Mode, playback wraps at the beginning or end of the timeline.

Loading CSV Overlays
--------------------

If exactly one imagery is selected and it contains both times and frames, VISTA can fill a missing temporal coordinate
for loaded tracks or detections by exact lookup. For example, a time-only CSV can receive corresponding frame numbers.
Values without an exact match remain unavailable in the other coordinate system.

See :doc:`tracks` and :doc:`detections` for the supported CSV columns.

Map View
--------

Map View requires all of the following:

* a selected imagery layer;
* a selected sensor that supports geolocation;
* a time-based display timeline.

See Also
--------

* :doc:`imagery`
* :doc:`tracks`
* :doc:`detections`
* :doc:`../api/temporal_data`
