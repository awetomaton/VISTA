"""Simple nearest-neighbor tracker with automatic parameter adaptation"""
import numpy as np
from scipy.optimize import linear_sum_assignment


class SimpleTrack:
    """
    Simple track using running average for position prediction.

    This track class maintains a history of detected positions and predicts
    future positions using linear extrapolation based on recent velocity.

    Attributes
    ----------
    id : int
        Unique identifier for this track.
    positions : list of ndarray
        List of (x, y) position arrays for each detection/prediction.
    frames : list of int
        Frame numbers corresponding to each position.
    max_search_radius : float
        Maximum distance to search for associated detections.
    hits : int
        Number of times this track was updated with a detection.
    misses : int
        Number of consecutive frames without a detection.
    age : int
        Total number of frames this track has existed.
    """

    def __init__(self, detection_pos, frame, track_id, max_search_radius):
        """
        Initialize a new track.

        Parameters
        ----------
        detection_pos : ndarray
            Initial (x, y) position of the detection.
        frame : int
            Frame number where this track was initiated.
        track_id : int
            Unique identifier for this track.
        max_search_radius : float
            Maximum distance to search for associated detections.
        """
        self.id = track_id
        self.positions = [detection_pos.copy()]
        self.frames = [frame]
        self.max_search_radius = max_search_radius

        # Track quality metrics
        self.hits = 1
        self.misses = 0
        self.age = 1

    def predict_position(self):
        """
        Predict next position using velocity estimate.

        Returns
        -------
        ndarray
            Predicted (x, y) position for the next frame. If fewer than 2
            positions exist, returns the last known position. Otherwise,
            uses linear extrapolation from the last 2-3 positions.

        Notes
        -----
        The prediction uses up to the last 3 positions to estimate velocity,
        providing more stable predictions than using only the last 2 positions.
        """
        if len(self.positions) < 2:
            # No velocity estimate yet, use last position
            return self.positions[-1]

        # Use last 3 positions for velocity estimate if available
        n = min(3, len(self.positions))
        recent_positions = np.array(self.positions[-n:])

        # Simple linear extrapolation
        if n >= 2:
            velocity = recent_positions[-1] - recent_positions[-2]
            return recent_positions[-1] + velocity
        else:
            return recent_positions[-1]

    def distance_to(self, detection_pos):
        """
        Compute Euclidean distance from detection to predicted position.

        Parameters
        ----------
        detection_pos : ndarray
            The (x, y) position of a detection to compare against.

        Returns
        -------
        float
            Euclidean distance between the detection and this track's
            predicted position.
        """
        pred = self.predict_position()
        return np.linalg.norm(detection_pos - pred)

    def update(self, detection_pos, frame):
        """
        Update track with a new detection.

        Parameters
        ----------
        detection_pos : ndarray
            The (x, y) position of the new detection.
        frame : int
            Frame number of the new detection.

        Notes
        -----
        This method appends the new position to the track history, increments
        the hit count, resets the consecutive miss count, and increments age.
        """
        self.positions.append(detection_pos.copy())
        self.frames.append(frame)
        self.hits += 1
        self.misses = 0
        self.age += 1

    def mark_missed(self, frame):
        """
        Mark a frame as missed and add predicted position.

        Parameters
        ----------
        frame : int
            Frame number that was missed (no detection associated).

        Notes
        -----
        When a track is not associated with any detection in a frame,
        this method adds the predicted position to maintain track continuity.
        It increments both the consecutive miss count and the track age.
        """
        pred_pos = self.predict_position()
        self.positions.append(pred_pos)
        self.frames.append(frame)
        self.misses += 1
        self.age += 1

    def quality_score(self):
        """
        Compute track quality score (higher is better).

        Returns
        -------
        float
            Quality score between 0 and 1, representing track reliability.
            Calculated as detection rate multiplied by a recency penalty
            factor that heavily penalizes recent misses.

        Notes
        -----
        The quality score combines two factors:
        - Detection rate: ratio of hits to total age
        - Recency penalty: exponential decay based on consecutive misses

        This score helps identify high-quality tracks for retention and
        low-quality tracks for deletion.
        """
        if self.age == 0:
            return 0
        # Detection rate weighted by age
        detection_rate = self.hits / self.age
        # Penalize recent misses heavily
        recency_penalty = np.exp(-self.misses / 3.0)
        return detection_rate * recency_penalty


def run_simple_tracker(detectors, config):
    """
    Run simple nearest-neighbor tracker with adaptive parameters.

    This tracker automatically adapts to the data and requires minimal configuration.
    It uses Hungarian algorithm for detection-to-track association and automatically
    computes search radius and maximum track age if not provided.

    Parameters
    ----------
    detectors : list of Detector
        List of Detector objects to use as input. Each detector should have
        frames, columns, and rows attributes containing detection data.
    config : dict
        Dictionary containing tracker configuration with the following keys:

        - tracker_name : str, optional
            Name for the resulting tracker. Default is 'Simple Tracker'.
        - max_search_radius : float, optional
            Maximum distance to search for associations. If not provided,
            automatically computed from detection nearest-neighbor statistics.
        - min_track_length : int, optional
            Minimum number of detections for a valid track. Default is 5.
        - max_age : int, optional
            Maximum frames a track can go without detection before deletion.
            If not provided, automatically computed based on frame gaps.

    Returns
    -------
    list of dict
        List of track data dictionaries, each containing:

        - 'frames' : ndarray
            Array of frame numbers where track appears.
        - 'rows' : ndarray
            Array of row (y) coordinates for each frame.
        - 'columns' : ndarray
            Array of column (x) coordinates for each frame.

    Notes
    -----
    The tracker performs the following steps:

    1. Collects all detections organized by frame
    2. Auto-computes max_search_radius using 90th percentile of nearest-neighbor
       distances if not provided
    3. Auto-computes max_age based on average frame gaps if not provided
    4. Associates detections to tracks using Hungarian algorithm
    5. Creates new tracks from unassociated detections
    6. Marks missed detections for tracks without associations
    7. Deletes tracks that exceed max_age or have poor quality scores
    8. Returns tracks that meet minimum length requirement

    Examples
    --------
    >>> config = {
    ...     'tracker_name': 'My Tracker',
    ...     'min_track_length': 5,
    ...     'max_search_radius': 10.0
    ... }
    >>> tracks = run_simple_tracker(detectors, config)
    >>> print(f"Found {len(tracks)} tracks")
    """
    # Extract configuration with smart defaults
    tracker_name = config.get('tracker_name', 'Simple Tracker')
    min_track_length = config.get('min_track_length', 5)

    # Collect all detections by frame
    detections_by_frame = {}
    all_detections_list = []

    for detector in detectors:
        for i, frame in enumerate(detector.frames):
            pos = np.array([detector.columns[i], detector.rows[i]])
            if frame not in detections_by_frame:
                detections_by_frame[frame] = []
            detections_by_frame[frame].append(pos)
            all_detections_list.append(pos)

    # Auto-compute search radius if not provided
    if 'max_search_radius' in config and config['max_search_radius'] is not None:
        max_search_radius = config['max_search_radius']
    else:
        # Estimate based on nearest-neighbor distances in detections
        if len(all_detections_list) > 10:
            all_dets = np.array(all_detections_list)
            # Compute pairwise distances for a sample
            sample_size = min(500, len(all_dets))
            sample_indices = np.random.choice(len(all_dets), sample_size, replace=False)
            sample = all_dets[sample_indices]

            # Find 2nd nearest neighbor for each (1st is itself)
            dists = []
            for det in sample[:100]:  # Use subset for speed
                distances = np.linalg.norm(sample - det, axis=1)
                distances.sort()
                if len(distances) > 1:
                    dists.append(distances[1])

            # Use 90th percentile of nearest neighbor distances * 3
            max_search_radius = np.percentile(dists, 90) * 3 if dists else 50.0
            max_search_radius = max(10.0, min(100.0, max_search_radius))  # Clamp to reasonable range
        else:
            max_search_radius = 30.0

    # Auto-compute max age if not provided
    if 'max_age' in config and config['max_age'] is not None:
        max_age = config['max_age']
    else:
        # Estimate based on detection density
        frames = sorted(detections_by_frame.keys())
        if len(frames) > 1:
            frame_gaps = np.diff(frames)
            avg_gap = np.mean(frame_gaps)
            # Allow tracks to survive ~3x the average frame gap
            max_age = int(max(3, min(10, avg_gap * 3)))
        else:
            max_age = 5

    # Track management
    active_tracks = []
    finished_tracks = []  # Tracks that were deleted but may still be valid
    next_track_id = 1
    frames = sorted(detections_by_frame.keys())

    # Process each frame
    for frame in frames:
        detections = detections_by_frame[frame]

        if len(active_tracks) > 0 and len(detections) > 0:
            # Build cost matrix (distances)
            cost_matrix = np.full((len(active_tracks), len(detections)), max_search_radius * 2)

            for i, track in enumerate(active_tracks):
                for j, detection in enumerate(detections):
                    dist = track.distance_to(detection)
                    if dist < max_search_radius:
                        cost_matrix[i, j] = dist

            # Solve assignment
            track_indices, det_indices = linear_sum_assignment(cost_matrix)

            # Track assignments
            assigned_detections = set()
            assigned_tracks = set()

            for track_idx, det_idx in zip(track_indices, det_indices):
                if cost_matrix[track_idx, det_idx] < max_search_radius:
                    active_tracks[track_idx].update(detections[det_idx], frame)
                    assigned_detections.add(det_idx)
                    assigned_tracks.add(track_idx)

            # Mark missed tracks
            for i, track in enumerate(active_tracks):
                if i not in assigned_tracks:
                    track.mark_missed(frame)

            # Create new tracks from unassigned detections
            for j, detection in enumerate(detections):
                if j not in assigned_detections:
                    new_track = SimpleTrack(detection, frame, next_track_id, max_search_radius)
                    active_tracks.append(new_track)
                    next_track_id += 1

        elif len(detections) > 0:
            # No tracks yet, initialize from detections
            for detection in detections:
                new_track = SimpleTrack(detection, frame, next_track_id, max_search_radius)
                active_tracks.append(new_track)
                next_track_id += 1

        else:
            # No detections, just mark all tracks as missed
            for track in active_tracks:
                track.mark_missed(frame)

        # Delete old/poor tracks
        tracks_to_remove = []
        for track in active_tracks:
            # Delete if too many consecutive misses
            if track.misses > max_age:
                tracks_to_remove.append(track)
            # Delete if quality is too low and track is old enough
            elif track.age > 10 and track.quality_score() < 0.3:
                tracks_to_remove.append(track)

        for track in tracks_to_remove:
            active_tracks.remove(track)
            # Save deleted tracks that might still be valid
            if track.hits >= min_track_length:
                finished_tracks.append(track)

    # Convert to track data, filter by minimum length
    # Combine both active tracks and finished tracks
    all_valid_tracks = []
    for track in active_tracks:
        if track.hits >= min_track_length:
            all_valid_tracks.append(track)
    all_valid_tracks.extend(finished_tracks)

    track_data_list = []
    for track in all_valid_tracks:
        positions = np.array(track.positions)
        frames_array = np.array(track.frames, dtype=np.int_)

        track_data = {
            'frames': frames_array,
            'rows': positions[:, 1],  # y
            'columns': positions[:, 0],  # x
        }
        track_data_list.append(track_data)

    return track_data_list
