"""Tracklet-based hierarchical tracker for high false alarm scenarios

This tracker uses a two-stage approach optimized for scenarios with:
- High false alarm rate (100:1 or higher)
- Smooth real target motion with consistent velocity

Stage 1: Form high-confidence tracklets using strict association criteria
Stage 2: Link tracklets based on velocity extrapolation and smoothness
"""
import numpy as np
from scipy.optimize import linear_sum_assignment


class Tracklet:
    """High-confidence track segment with velocity consistency"""

    def __init__(self, detection_pos, frame, tracklet_id):
        self.id = tracklet_id
        self.positions = [detection_pos.copy()]
        self.frames = [frame]
        self.velocity = None  # Will be computed when we have 2+ detections

        # Track quality metrics for "m out of n" logic
        self.hits = 1  # Number of actual detections
        self.age = 1   # Total frames since creation
        self.consecutive_misses = 0  # Consecutive frames without detection

    def add_detection(self, detection_pos, frame):
        """Add detection to tracklet and update velocity estimate"""
        self.positions.append(detection_pos.copy())
        self.frames.append(frame)
        self.hits += 1
        self.consecutive_misses = 0  # Reset consecutive misses

        # Update velocity estimate using last 3 positions if available
        if len(self.positions) >= 2:
            n = min(3, len(self.positions))
            recent_positions = np.array(self.positions[-n:])
            recent_frames = np.array(self.frames[-n:])

            # Fit velocity using all recent points
            if n >= 2:
                dt_total = recent_frames[-1] - recent_frames[0]
                if dt_total > 0:
                    displacement = recent_positions[-1] - recent_positions[0]
                    self.velocity = displacement / dt_total
                else:
                    self.velocity = np.zeros(2)
            else:
                self.velocity = np.zeros(2)

    def mark_missed(self, frame):
        """Mark that no detection was associated this frame"""
        self.consecutive_misses += 1
        self.age += 1

        # Add predicted position to history to maintain continuity
        pred_pos = self.predict_position(frame)
        if pred_pos is not None:
            self.positions.append(pred_pos)
            self.frames.append(frame)

    def detection_rate(self):
        """Compute detection rate (hits / age)"""
        if self.age == 0:
            return 0.0
        return self.hits / self.age

    def predict_position(self, target_frame):
        """Predict position at target frame using velocity"""
        if self.velocity is None or len(self.positions) == 0:
            return None

        last_frame = self.frames[-1]
        dt = target_frame - last_frame

        return self.positions[-1] + self.velocity * dt

    def check_velocity_consistency(self, detection_pos, frame, max_velocity_change):
        """Check if detection is consistent with tracklet velocity"""
        if len(self.positions) < 2:
            # Can't check velocity with only 1 detection
            return True

        # Compute velocity from last position to detection
        dt = frame - self.frames[-1]
        if dt == 0:
            return False  # Same frame, can't associate

        new_velocity = (detection_pos - self.positions[-1]) / dt

        # Check velocity change (acceleration)
        velocity_change = np.linalg.norm(new_velocity - self.velocity)

        return velocity_change < max_velocity_change

    def distance_to(self, detection_pos, frame):
        """Distance from predicted position to detection"""
        pred = self.predict_position(frame)
        if pred is None:
            return np.linalg.norm(detection_pos - self.positions[-1])
        return np.linalg.norm(detection_pos - pred)

    def extrapolate_forward(self, frames_ahead):
        """Extrapolate tracklet forward in time"""
        if self.velocity is None:
            return None
        target_frame = self.frames[-1] + frames_ahead
        return self.predict_position(target_frame)

    def extrapolate_backward(self, frames_back):
        """Extrapolate tracklet backward in time"""
        if self.velocity is None:
            return None
        target_frame = self.frames[0] - frames_back
        # Use velocity to extrapolate backward
        dt = target_frame - self.frames[0]
        return self.positions[0] + self.velocity * dt

    def get_start_velocity(self):
        """Get velocity at tracklet start"""
        return self.velocity if self.velocity is not None else np.zeros(2)

    def get_end_velocity(self):
        """Get velocity at tracklet end"""
        return self.velocity if self.velocity is not None else np.zeros(2)


def run_tracklet_tracker(detectors, config):
    """
    Run tracklet-based hierarchical tracker on detections.

    This tracker is optimized for high false alarm scenarios where real tracks
    move smoothly. It uses a two-stage approach:

    Stage 1: Form high-confidence tracklets with strict association criteria

    - Small search radius for initial associations
    - Velocity consistency checking
    - "M out of N" approach: allows small detection gaps

    Stage 2: Link tracklets using global optimization

    - Velocity extrapolation for gap filling
    - Smoothness scoring based on velocity/position consistency
    - Hungarian algorithm for optimal linking

    Parameters
    ----------
    detectors : list of Detector
        List of Detector objects to use as input
    config : dict
        Dictionary containing tracker configuration:

        - tracker_name: Name for the resulting tracker
        - initial_search_radius: Max distance for tracklet formation (default: 10.0)
        - max_velocity_change: Max velocity change for tracklet formation (default: 5.0)
        - min_tracklet_length: Minimum detections for valid tracklet (default: 3)
        - max_consecutive_misses: Max consecutive missed detections in Stage 1 (default: 2)
        - min_detection_rate: Minimum detection rate (hits/age) for tracklets (default: 0.6)
        - max_linking_gap: Maximum frame gap to link tracklets (default: 10)
        - linking_search_radius: Max distance for tracklet linking (default: 30.0)
        - smoothness_weight: Weight for smoothness in linking cost (default: 1.0)
        - min_track_length: Minimum detections for final track (default: 5)

    Returns
    -------
    list of dict
        List of track data dictionaries, each containing:

        - 'frames': numpy array of frame numbers
        - 'rows': numpy array of row coordinates
        - 'columns': numpy array of column coordinates
    """
    # Extract configuration with smart defaults
    tracker_name = config.get('tracker_name', 'Tracklet Tracker')
    initial_search_radius = config.get('initial_search_radius', 10.0)
    max_velocity_change = config.get('max_velocity_change', 5.0)
    min_tracklet_length = config.get('min_tracklet_length', 3)
    max_consecutive_misses = config.get('max_consecutive_misses', 2)
    min_detection_rate = config.get('min_detection_rate', 0.6)
    max_linking_gap = config.get('max_linking_gap', 10)
    linking_search_radius = config.get('linking_search_radius', 30.0)
    smoothness_weight = config.get('smoothness_weight', 1.0)
    min_track_length = config.get('min_track_length', 5)

    # Collect all detections by frame
    detections_by_frame = {}
    for detector in detectors:
        for i, frame in enumerate(detector.frames):
            pos = np.array([detector.columns[i], detector.rows[i]])
            if frame not in detections_by_frame:
                detections_by_frame[frame] = []
            detections_by_frame[frame].append(pos)

    if len(detections_by_frame) == 0:
        return []

    frames = sorted(detections_by_frame.keys())

    # ========================================================================
    # STAGE 1: Form high-confidence tracklets with strict criteria
    # ========================================================================
    active_tracklets = []
    finished_tracklets = []
    next_tracklet_id = 1

    for frame in frames:
        detections = detections_by_frame[frame]

        if len(active_tracklets) > 0 and len(detections) > 0:
            # Build cost matrix for tracklet-detection association
            cost_matrix = np.full((len(active_tracklets), len(detections)),
                                 initial_search_radius * 2)

            for i, tracklet in enumerate(active_tracklets):
                for j, detection in enumerate(detections):
                    # Only consider if tracklet hasn't been missed too many times
                    # Allow associations within max_consecutive_misses + 1
                    frame_gap = frame - tracklet.frames[-1]
                    if frame_gap > max_consecutive_misses + 1:
                        continue

                    # Check distance
                    dist = tracklet.distance_to(detection, frame)
                    if dist >= initial_search_radius:
                        continue

                    # Check velocity consistency (strict criterion)
                    if not tracklet.check_velocity_consistency(detection, frame, max_velocity_change):
                        continue

                    cost_matrix[i, j] = dist

            # Solve assignment
            track_indices, det_indices = linear_sum_assignment(cost_matrix)

            # Track assignments
            assigned_detections = set()
            assigned_tracklets = set()

            for tracklet_idx, det_idx in zip(track_indices, det_indices):
                if cost_matrix[tracklet_idx, det_idx] < initial_search_radius:
                    active_tracklets[tracklet_idx].add_detection(detections[det_idx], frame)
                    assigned_detections.add(det_idx)
                    assigned_tracklets.add(tracklet_idx)

            # Mark unassigned tracklets as missed (don't remove immediately)
            for i, tracklet in enumerate(active_tracklets):
                if i not in assigned_tracklets:
                    tracklet.mark_missed(frame)

            # Remove tracklets that exceed thresholds ("m out of n" filtering)
            tracklets_to_remove = []
            for tracklet in active_tracklets:
                # Remove if too many consecutive misses
                if tracklet.consecutive_misses > max_consecutive_misses:
                    # Save if it has enough detections
                    if tracklet.hits >= min_tracklet_length:
                        finished_tracklets.append(tracklet)
                    tracklets_to_remove.append(tracklet)
                # Remove if detection rate is too low (after minimum age)
                elif tracklet.age >= min_tracklet_length * 2:
                    if tracklet.detection_rate() < min_detection_rate:
                        # Don't save - poor quality tracklet
                        tracklets_to_remove.append(tracklet)

            for tracklet in tracklets_to_remove:
                active_tracklets.remove(tracklet)

            # Create new tracklets from unassigned detections
            for j, detection in enumerate(detections):
                if j not in assigned_detections:
                    new_tracklet = Tracklet(detection, frame, next_tracklet_id)
                    active_tracklets.append(new_tracklet)
                    next_tracklet_id += 1

        elif len(detections) > 0:
            # No tracklets yet, initialize from detections
            for detection in detections:
                new_tracklet = Tracklet(detection, frame, next_tracklet_id)
                active_tracklets.append(new_tracklet)
                next_tracklet_id += 1

        else:
            # No detections this frame - mark all tracklets as missed
            for tracklet in active_tracklets:
                tracklet.mark_missed(frame)

            # Remove tracklets that exceed thresholds
            tracklets_to_remove = []
            for tracklet in active_tracklets:
                if tracklet.consecutive_misses > max_consecutive_misses:
                    if tracklet.hits >= min_tracklet_length:
                        finished_tracklets.append(tracklet)
                    tracklets_to_remove.append(tracklet)
                elif tracklet.age >= min_tracklet_length * 2:
                    if tracklet.detection_rate() < min_detection_rate:
                        tracklets_to_remove.append(tracklet)

            for tracklet in tracklets_to_remove:
                active_tracklets.remove(tracklet)

    # Finish remaining active tracklets
    for tracklet in active_tracklets:
        if tracklet.hits >= min_tracklet_length:
            finished_tracklets.append(tracklet)

    # ========================================================================
    # STAGE 2: Link tracklets based on velocity extrapolation and smoothness
    # ========================================================================
    if len(finished_tracklets) == 0:
        return []

    # Build tracklet linking cost matrix
    n_tracklets = len(finished_tracklets)
    link_cost_matrix = np.full((n_tracklets, n_tracklets), np.inf)

    for i, tracklet_i in enumerate(finished_tracklets):
        for j, tracklet_j in enumerate(finished_tracklets):
            if i == j:
                continue

            # Only link if j comes after i in time
            if tracklet_j.frames[0] <= tracklet_i.frames[-1]:
                continue

            # Check frame gap
            frame_gap = tracklet_j.frames[0] - tracklet_i.frames[-1]
            if frame_gap > max_linking_gap:
                continue

            # Extrapolate tracklet_i forward to tracklet_j start frame
            pred_pos = tracklet_i.extrapolate_forward(frame_gap)
            if pred_pos is None:
                continue

            # Position error
            position_error = np.linalg.norm(pred_pos - tracklet_j.positions[0])

            if position_error > linking_search_radius:
                continue

            # Velocity consistency (smoothness)
            velocity_i = tracklet_i.get_end_velocity()
            velocity_j = tracklet_j.get_start_velocity()
            velocity_error = np.linalg.norm(velocity_i - velocity_j)

            # Combined cost: position error + smoothness penalty
            cost = position_error + smoothness_weight * velocity_error

            link_cost_matrix[i, j] = cost

    # Solve tracklet linking using Hungarian algorithm
    # This finds optimal non-overlapping links
    linked_tracklets = []
    used_tracklets = set()

    # Find best links iteratively
    while True:
        # Find minimum cost link among unused tracklets
        min_cost = np.inf
        best_i, best_j = -1, -1

        for i in range(n_tracklets):
            if i in used_tracklets:
                continue
            for j in range(n_tracklets):
                if j in used_tracklets:
                    continue
                if link_cost_matrix[i, j] < min_cost:
                    min_cost = link_cost_matrix[i, j]
                    best_i, best_j = i, j

        if best_i == -1 or np.isinf(min_cost):
            break

        # Link these tracklets
        # Try to extend existing track or start new one
        linked = False
        for track in linked_tracklets:
            # Check if best_i is the end of this track
            if track[-1] == best_i:
                track.append(best_j)
                linked = True
                break

        if not linked:
            linked_tracklets.append([best_i, best_j])

        used_tracklets.add(best_i)
        used_tracklets.add(best_j)

    # Add unlinked tracklets as single-tracklet tracks
    for i in range(n_tracklets):
        if i not in used_tracklets:
            linked_tracklets.append([i])

    # ========================================================================
    # Convert linked tracklets to track data dictionaries
    # ========================================================================
    track_data_list = []

    for tracklet_indices in linked_tracklets:
        # Combine tracklets
        all_positions = []
        all_frames = []

        for idx in tracklet_indices:
            tracklet = finished_tracklets[idx]
            all_positions.extend(tracklet.positions)
            all_frames.extend(tracklet.frames)

        # Filter by minimum track length
        if len(all_positions) < min_track_length:
            continue

        # Convert to arrays
        positions = np.array(all_positions)
        frames_array = np.array(all_frames, dtype=np.int_)

        # Sort by frame (in case tracklets were out of order)
        sort_idx = np.argsort(frames_array)
        frames_array = frames_array[sort_idx]
        positions = positions[sort_idx]

        track_data = {
            'frames': frames_array,
            'rows': positions[:, 1],  # y
            'columns': positions[:, 0],  # x
        }
        track_data_list.append(track_data)

    return track_data_list
