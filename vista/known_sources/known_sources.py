"""Base source class for known sources like stars, planets, asteroids, satellites, etc."""

import uuid
from typing import Tuple, Union

import numpy as np
from astropy import units as u
from astropy.coordinates import EarthLocation
from astropy.time import Time
from numpy.typing import NDArray

from vista.imagery.imagery import Imagery
from vista.tracks.track import Track
from vista.transforms.earth_intersection import los_to_earth


class KnownSources:
    """
    Base class for known sources like stars, planets, asteroids, satellites, etc.

    It is expected that subclasses are implemented which contain *groups* of self-similar
    sources loaded together, i.e. an array of satellites, an array of stars, etc.

    Parameters
    ----------
    name : str
        unique name of the group of sources, stored in KnownSources.name.
        Examples: "GAIA stars", "APASS stars", "LEO satellites"

    Attributes
    ----------
    source_types : list[str]
        list of source types.
        Examples: ["star", "star", "star"], ["satellite", "GEO satellite", "LEO satellite"]
    source_names : list[str]
        list of unique names for all the sources
    """

    def __init__(self, name: str):
        self.name = name
        self.source_types = []
        self.source_names = []
        self.uuid = uuid.uuid4()

        # parameters for Tracks
        self._color = "g"
        self._marker = "o"
        self._marker_size = 5

    def get_geodetics(self, times: Union[np.datetime64, NDArray[np.datetime64], Time]) -> EarthLocation:
        """
        Return an EarthLocation containing the positions of the sources at the provided time(s).
        Subclasses should implement this function based on the source types

        Parameters
        ----------
        times : np.datetime64 | NDArray[np.datetime64] | astropy.time.Time
            Time or array of times for which to retrieve positions

        Returns
        -------
        EarthLocation
            Astropy EarthLocation object containing geodetic coordinates
        """
        raise NotImplementedError

    def get_pixels(self, imagery: Imagery, frame: Union[int, NDArray]) -> Tuple[NDArray, NDArray]:
        """
        Return the pixel positions of the source for the provided imagery and frame number(s).
        Sources which are off-frame or behind the Earth have NaN locations

        Parameters
        ----------
        imagery: Imagery
            The imagery we want to project the source onto
        frame : int, NDArray
            The frame number(s) to project onto

        Returns
        -------
        rows : NDArray
            Row coordinates of source positions in the frame(s)
        cols : NDArray
            Column coordinates of source positions in the frame(s)
        """
        sensor = imagery.sensor  # get the imagery sensor

        # get times for the desired frame(s)
        _, times = sensor.get_imagery_frames_and_times()
        times = times[frame]

        # geodetic positions for the source at those times
        source_positions = self.get_geodetics(times)

        # check if object is on the other side of the earth via intersection along LOS
        sensor_positions = sensor.get_positions(np.atleast_1d(times))
        dx = source_positions.x.to(u.km).value - sensor_positions[0]
        dy = source_positions.y.to(u.km).value - sensor_positions[1]
        dz = source_positions.z.to(u.km).value - sensor_positions[2]
        # normalize for los_to_earth function
        los_sensor_to_source = np.array([dx, dy, dz]) / np.sqrt(dx**2 + dy**2 + dz**2)
        # calculate intersection of los from sensor to source with the Earth
        d, intersection = los_to_earth(sensor_positions, los_sensor_to_source)
        # if intersection distance is farther than the source, los from sensor
        # to source does not intersect the earth
        d[d**2 > dx**2 + dy**2 + dz**2] = np.nan
        # values which are not nan are the ones that are blocked by the earth
        # set their source positions to nan, as we don't care about their pixel positions
        source_positions[~np.isnan(d)] = np.nan

        # convert from ECEF to ARF to pixels
        rows, columns = sensor.geodetic_to_pixel(frame, source_positions)

        # Only display objects within the image frame
        # TODO: Handle when there's a cropped image
        _, max_rows, max_cols = imagery.images.shape
        # where is the valid region...
        where = (rows >= 0) & (rows <= max_rows + 1) & (columns >= 0) & (columns <= max_cols + 1)
        # ... so negate it to set invalid pixels to nan
        rows[~where] = np.nan
        columns[~where] = np.nan

        return rows, columns

    def _get_slices(self, values):
        """
        Given a list of values, find the slices that give groupings of non-nan values.
        e.g.,   given [nan, 2, 3, nan, 5, 6, 7, nan, 9, nan],
                return [[1:3], [4:7], [8:9]]
        """
        # 1. Create a boolean mask for NaNs
        is_nan = np.isnan(values)
        # 2. Pad with True at the edges to catch groups touching the ends
        padded = np.concatenate(([True], is_nan, [True]))
        # 3. Find transition points (indices where True/False changes)
        changes = np.nonzero(np.diff(padded))[0]
        # 4. Generate slice objects
        slices = []
        for start, end in zip(changes[0::2], changes[1::2]):
            slices.append(slice(start, end))
        return slices

    def create_tracks(self, imagery: Imagery) -> list[Track]:
        """
        Create a list of Tracks for the sources for the provided imagery.
        Ignores positions which are off-frame or behind the Earth.
        Sources which reappear after passing behind the Earth will therefore have multiple tracks

        Parameters
        ----------
        imagery: Imagery
            The imagery we want to create tracks for

        Returns
        -------
        tracks : list[Tracks]
            list of Track objects
        """

        tracks = []

        rows = []
        columns = []
        for frame in imagery.frames:
            r, c = self.get_pixels(imagery, frame)
            rows.append(r)
            columns.append(c)
        # after looping over frames, rows and columns have shape (num_frames, num_sources)
        # transpose so each source has a row and column
        rows = np.array(rows).T
        columns = np.array(columns).T

        for source, source_type, row, column in zip(self.source_names, self.source_types, rows, columns):
            slices = self._get_slices(row)  # columns should have the same valid slices
            for slice in slices:
                track = Track(
                    name=source,
                    frames=imagery.frames[slice],
                    rows=row[slice],
                    columns=column[slice],
                    sensor=imagery.sensor,
                    color=self._color,
                    marker=self._marker,
                    marker_size=self._marker_size,
                    tracker=self.name,
                    labels={source_type},
                )
                tracks.append(track)
        return tracks
