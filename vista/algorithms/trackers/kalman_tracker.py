"""Multi-object tracker implementation for VISTA"""
import numpy as np
from scipy.optimize import linear_sum_assignment


class KalmanTrack:
    """Single track with constant velocity Kalman filter"""

    def __init__(self, detection_pos, frame, process_noise, measurement_noise, track_id):
        """
        Initialize track with first detection.

        State vector: [x, vx, y, vy] where x=column, y=row
        """
        self.id = track_id
        self.state = np.array([[detection_pos[0]], [0], [detection_pos[1]], [0]])  # [x, vx, y, vy]

        # Initial covariance (high uncertainty in velocity)
        self.covar = np.diag([measurement_noise, 10.0, measurement_noise, 10.0])

        # Store parameters
        self.process_noise = process_noise
        self.measurement_noise = measurement_noise

        # Track history
        self.frames = [frame]
        self.positions = [detection_pos.copy()]

        # Track management
        self.hits = 1  # Number of detections associated
        self.misses = 0  # Number of consecutive missed detections
        self.age = 1  # Total frames since creation

    def predict(self, dt=1.0):
        """Predict next state using constant velocity model"""
        # State transition matrix
        F = np.array([
            [1, dt, 0,  0],
            [0,  1, 0,  0],
            [0,  0, 1, dt],
            [0,  0, 0,  1]
        ])

        # Process noise covariance
        Q = np.array([
            [dt**4/4, dt**3/2, 0,        0],
            [dt**3/2, dt**2,   0,        0],
            [0,       0,       dt**4/4,  dt**3/2],
            [0,       0,       dt**3/2,  dt**2]
        ]) * self.process_noise

        # Predict
        self.state = F @ self.state
        self.covar = F @ self.covar @ F.T + Q

    def update(self, detection_pos, frame):
        """Update state with new detection"""
        # Measurement matrix (measure position only)
        H = np.array([
            [1, 0, 0, 0],
            [0, 0, 1, 0]
        ])

        # Measurement noise
        R = np.eye(2) * self.measurement_noise

        # Innovation
        z = detection_pos.reshape(2, 1)
        y = z - H @ self.state

        # Innovation covariance
        S = H @ self.covar @ H.T + R

        # Kalman gain
        K = self.covar @ H.T @ np.linalg.inv(S)

        # Update state and covariance
        self.state = self.state + K @ y
        self.covar = (np.eye(4) - K @ H) @ self.covar

        # Update history
        self.frames.append(frame)
        self.positions.append(detection_pos.copy())
        self.hits += 1
        self.misses = 0

    def mark_missed(self, frame):
        """Mark that no detection was associated this frame"""
        self.misses += 1

        # Add predicted position to history
        pred_pos = np.array([self.state[0, 0], self.state[2, 0]])
        self.frames.append(frame)
        self.positions.append(pred_pos)

    def get_predicted_position(self):
        """Get predicted position (x, y)"""
        return np.array([self.state[0, 0], self.state[2, 0]])

    def mahalanobis_distance(self, detection_pos):
        """Compute Mahalanobis distance to detection"""
        # Measurement matrix
        H = np.array([
            [1, 0, 0, 0],
            [0, 0, 1, 0]
        ])

        # Predicted measurement
        z_pred = H @ self.state

        # Innovation covariance
        R = np.eye(2) * self.measurement_noise
        S = H @ self.covar @ H.T + R

        # Innovation
        z = detection_pos.reshape(2, 1)
        y = z - z_pred

        # Mahalanobis distance
        dist = np.sqrt(y.T @ np.linalg.inv(S) @ y)
        return float(dist[0, 0])


def run_kalman_tracker(detectors, config):
    """
    Run Kalman filter tracker on detections using a custom implementation.

    Parameters
    ----------
    detectors : list of Detector
        List of Detector objects to use as input
    config : dict
        Dictionary containing tracker configuration:

        - tracker_name: Name for the resulting tracker
        - process_noise: Process noise for constant velocity model
        - measurement_noise: Measurement noise covariance
        - gating_distance: Mahalanobis distance threshold for gating
        - min_detections: Minimum detections required to initiate track
        - delete_threshold: Covariance trace threshold for track deletion

    Returns
    -------
    list of dict
        List of track data dictionaries, each containing:

        - 'frames': numpy array of frame numbers
        - 'rows': numpy array of row coordinates
        - 'columns': numpy array of column coordinates
    """
    # Extract configuration
    process_noise = config['process_noise']
    measurement_noise = config['measurement_noise']
    gating_distance = config['gating_distance']
    min_detections = config['min_detections']
    delete_threshold = config['delete_threshold']

    # Collect all detections by frame
    detections_by_frame = {}
    for detector in detectors:
        for i, frame in enumerate(detector.frames):
            if frame not in detections_by_frame:
                detections_by_frame[frame] = []
            # Store as [column, row] = [x, y]
            detections_by_frame[frame].append(np.array([detector.columns[i], detector.rows[i]]))

    # Get sorted frame list
    frames = sorted(detections_by_frame.keys())

    # Track management
    active_tracks = []  # List of KalmanTrack objects
    finished_tracks = []  # Tracks that were deleted but may still be valid
    next_track_id = 1
    tentative_tracks = []  # Tracks waiting for confirmation

    # Process each frame
    for frame in frames:
        detections = detections_by_frame[frame]

        # Predict all active tracks and increment age
        for track in active_tracks + tentative_tracks:
            track.predict()
            track.age += 1

        if len(detections) == 0:
            # No detections - mark all tracks as missed
            for track in active_tracks + tentative_tracks:
                track.mark_missed(frame)
            continue

        # Data association using Global Nearest Neighbor with Hungarian algorithm
        if len(active_tracks) + len(tentative_tracks) > 0:
            # Build cost matrix (Mahalanobis distances)
            all_tracks = active_tracks + tentative_tracks
            cost_matrix = np.full((len(all_tracks), len(detections)), gating_distance * 2)

            for i, track in enumerate(all_tracks):
                for j, detection in enumerate(detections):
                    dist = track.mahalanobis_distance(detection)
                    if dist < gating_distance:
                        cost_matrix[i, j] = dist

            # Solve assignment problem
            track_indices, detection_indices = linear_sum_assignment(cost_matrix)

            # Track which detections were associated
            associated_detections = set()
            associated_tracks = set()

            # Update tracks with assignments
            for track_idx, det_idx in zip(track_indices, detection_indices):
                if cost_matrix[track_idx, det_idx] < gating_distance:
                    all_tracks[track_idx].update(detections[det_idx], frame)
                    associated_detections.add(det_idx)
                    associated_tracks.add(track_idx)

            # Mark unassociated tracks as missed
            for i, track in enumerate(all_tracks):
                if i not in associated_tracks:
                    track.mark_missed(frame)
        else:
            associated_detections = set()

        # Initiate new tentative tracks from unassociated detections
        for i, detection in enumerate(detections):
            if i not in associated_detections:
                new_track = KalmanTrack(
                    detection, frame, process_noise,
                    measurement_noise, next_track_id
                )
                tentative_tracks.append(new_track)
                next_track_id += 1

        # Promote tentative tracks that have enough hits
        tracks_to_promote = []
        for track in tentative_tracks:
            if track.hits >= min_detections:
                tracks_to_promote.append(track)

        for track in tracks_to_promote:
            tentative_tracks.remove(track)
            active_tracks.append(track)

        # Delete tracks that have been missed too many times or have high uncertainty
        tracks_to_delete = []

        for track in active_tracks:
            # Delete if too many consecutive misses (3x the min_detections)
            if track.misses > min_detections * 3:
                tracks_to_delete.append(track)
            # Delete if covariance is too large
            elif np.trace(track.covar) > delete_threshold:
                tracks_to_delete.append(track)

        for track in tracks_to_delete:
            active_tracks.remove(track)
            # Save deleted tracks that have enough detections
            if track.hits >= min_detections:
                finished_tracks.append(track)

        # Delete tentative tracks that haven't been confirmed quickly enough
        tentative_to_delete = []
        for track in tentative_tracks:
            if track.age > min_detections * 2 and track.hits < min_detections:
                tentative_to_delete.append(track)

        for track in tentative_to_delete:
            tentative_tracks.remove(track)

    # Convert tracks to track data (include both active and finished)
    all_valid_tracks = active_tracks + finished_tracks

    track_data_list = []
    for track in all_valid_tracks:
        if len(track.frames) < 2:
            continue

        # Extract positions
        positions = np.array(track.positions)
        columns = positions[:, 0]  # x
        rows = positions[:, 1]  # y
        frames_array = np.array(track.frames, dtype=np.int_)

        track_data = {
            'frames': frames_array,
            'rows': rows,
            'columns': columns,
        }
        track_data_list.append(track_data)

    return track_data_list
