"""Network flow optimization tracker for VISTA"""
from collections import defaultdict

import numpy as np


def run_network_flow_tracker(detectors, config):
    """
    Run network flow optimization tracker on detections.

    This tracker formulates multi-object tracking as a minimum-cost flow problem
    on a graph where nodes are detections and edges represent possible associations.
    The algorithm finds the globally optimal set of tracks by solving for the
    minimum-cost flow from source to sink using Bellman-Ford successive shortest paths.

    Key features:

    - Negative link costs incentivize longer tracks over many short tracks
    - Smoothness penalty encourages constant-velocity, straight-line paths
    - Global optimization finds better solutions than greedy local association

    Parameters
    ----------
    detectors : list of Detector
        List of Detector objects to use as input
    config : dict
        Dictionary containing tracker configuration:

        - tracker_name: Name for the resulting tracker
        - max_gap: Maximum frame gap to search for associations (default: 5)
        - max_distance: Maximum spatial distance for associations (default: 50.0)
        - entrance_cost: Cost for starting a new track (default: 50.0)
        - exit_cost: Cost for ending a track (default: 50.0)
        - min_track_length: Minimum detections required for valid track (default: 3)

    Returns
    -------
    list of dict
        List of track data dictionaries, each containing:

        - 'frames': numpy array of frame numbers
        - 'rows': numpy array of row coordinates
        - 'columns': numpy array of column coordinates
    """
    # Extract configuration with defaults
    tracker_name = config.get('tracker_name', 'Network Flow Tracker')
    max_gap = config.get('max_gap', 5)
    max_distance = config.get('max_distance', 50.0)
    entrance_cost = config.get('entrance_cost', 50.0)
    exit_cost = config.get('exit_cost', 50.0)
    min_track_length = config.get('min_track_length', 3)

    # Collect all detections with unique IDs
    all_detections = []
    detection_id = 0

    for detector in detectors:
        for i, frame in enumerate(detector.frames):
            all_detections.append({
                'id': detection_id,
                'frame': frame,
                'position': np.array([detector.columns[i], detector.rows[i]]),
                'row': detector.rows[i],
                'column': detector.columns[i]
            })
            detection_id += 1

    # Sort by frame
    all_detections.sort(key=lambda x: x['frame'])

    if len(all_detections) == 0:
        # No detections, return empty list
        return []

    # Build detection index by frame for fast lookup
    detections_by_frame = defaultdict(list)
    for det in all_detections:
        detections_by_frame[det['frame']].append(det)

    frames = sorted(detections_by_frame.keys())

    # Build graph edges with costs
    # Edge types: (1) detection-to-detection, (2) source-to-detection, (3) detection-to-sink
    edges = []

    # 1. Detection-to-detection edges (temporal associations)
    for i, det_i in enumerate(all_detections):
        for j, det_j in enumerate(all_detections):
            if i >= j:
                continue

            frame_gap = det_j['frame'] - det_i['frame']

            # Only consider forward temporal associations within max_gap
            if frame_gap <= 0 or frame_gap > max_gap:
                continue

            # Compute spatial distance
            distance = np.linalg.norm(det_j['position'] - det_i['position'])

            # Skip if too far (likely not same object)
            if distance > max_distance * frame_gap:
                continue

            # Link cost = NEGATIVE (benefit) for linking, plus distance/gap penalties
            # We want linking to be beneficial, so base link value is negative
            # This incentivizes creating longer tracks
            link_benefit = (entrance_cost + exit_cost) * 0.8  # Benefit of linking (avoid starting new track)
            distance_penalty = distance
            gap_penalty = (frame_gap - 1) * 5.0

            # Smoothness penalty: penalize velocity changes (encourages straight paths)
            # Compute velocity from det_i to det_j
            velocity_ij = (det_j['position'] - det_i['position']) / frame_gap

            # Look for detections before det_i to check velocity consistency
            min_velocity_change = None
            for k, det_k in enumerate(all_detections):
                if det_k['frame'] >= det_i['frame']:
                    continue  # Only look at earlier frames

                frame_gap_ki = det_i['frame'] - det_k['frame']
                if frame_gap_ki > max_gap or frame_gap_ki == 0:
                    continue

                # Check if det_k could be part of the same track as det_i
                distance_ki = np.linalg.norm(det_i['position'] - det_k['position'])
                if distance_ki > max_distance * frame_gap_ki:
                    continue

                # Compute velocity from det_k to det_i
                velocity_ki = (det_i['position'] - det_k['position']) / frame_gap_ki

                # Compute velocity change (acceleration)
                velocity_change = np.linalg.norm(velocity_ij - velocity_ki)

                # Track minimum velocity change (best alignment)
                if min_velocity_change is None or velocity_change < min_velocity_change:
                    min_velocity_change = velocity_change

            # Add smoothness penalty (0 if no prior detections found)
            smoothness_penalty = min_velocity_change if min_velocity_change is not None else 0.0

            cost = -link_benefit + distance_penalty + gap_penalty + smoothness_penalty

            edges.append({
                'from': det_i['id'],
                'to': det_j['id'],
                'cost': cost,
                'type': 'link'
            })

    # 2. Source-to-detection edges (track initiation)
    # Use entrance_cost as-is (positive)
    # The cost should be large enough that linking is preferred over starting new tracks
    for det in all_detections:
        edges.append({
            'from': 'source',
            'to': det['id'],
            'cost': entrance_cost,
            'type': 'entrance'
        })

    # 3. Detection-to-sink edges (track termination)
    # Use exit_cost as-is (positive)
    for det in all_detections:
        edges.append({
            'from': det['id'],
            'to': 'sink',
            'cost': exit_cost,
            'type': 'exit'
        })

    # Solve minimum-cost flow using successive shortest path
    # Each detection can only be used once (flow capacity = 1)
    tracks = solve_min_cost_flow(all_detections, edges)

    # Convert to track data
    track_data_list = []
    for track_detections in tracks:
        if len(track_detections) < min_track_length:
            continue

        # Sort by frame
        track_detections.sort(key=lambda x: x['frame'])

        # Extract positions and frames
        frames_array = np.array([d['frame'] for d in track_detections], dtype=np.int_)
        rows = np.array([d['row'] for d in track_detections])
        columns = np.array([d['column'] for d in track_detections])

        track_data = {
            'frames': frames_array,
            'rows': rows,
            'columns': columns,
        }
        track_data_list.append(track_data)

    return track_data_list


def solve_min_cost_flow(detections, edges):
    """
    Solve minimum-cost flow problem using successive shortest path with Bellman-Ford.

    Key insight: Use NEGATIVE link costs to represent the benefit of linking detections.
    This makes longer tracks cheaper than many short tracks. For example:
    - Single detection track: entrance + exit = 100 + 100 = 200
    - Two detection track: entrance + (-80) + exit = 100 - 80 + 100 = 120 (cheaper!)
    - Ten detection track: entrance + 9×(-80) + exit = 100 - 720 + 100 = -520 (much cheaper!)

    Uses Bellman-Ford instead of Dijkstra because we have negative edge weights.
    No negative cycles exist because:
    1. Used detections are removed (no loops back)
    2. Time flows forward only (frame_i → frame_j where j > i)
    3. Sink has no outgoing edges

    Parameters
    ----------
    detections : list
        List of detection dictionaries
    edges : list
        List of edge dictionaries with 'from', 'to', 'cost'

    Returns
    -------
    list : List of tracks, where each track is a list of detection dictionaries
    """
    used_detections = set()
    tracks = []

    # Repeatedly find shortest paths until no more valid paths exist
    while True:
        # Find shortest path from source to sink
        path = find_shortest_path(edges, used_detections)

        if path is None:
            break

        # Extract detections from path (exclude source and sink)
        track_detection_ids = [node for node in path if node not in ['source', 'sink']]

        # Skip empty paths (shouldn't happen but safety check)
        if len(track_detection_ids) == 0:
            continue

        # Mark detections as used
        used_detections.update(track_detection_ids)

        # Build track from detection IDs
        track_detections = [d for d in detections if d['id'] in track_detection_ids]
        if len(track_detections) > 0:
            tracks.append(track_detections)

    return tracks


def find_shortest_path(edges, used_detections):
    """
    Find shortest path from source to sink using Bellman-Ford algorithm.

    Bellman-Ford handles negative edge weights (unlike Dijkstra).
    This is necessary because link costs are negative to incentivize longer tracks.

    Parameters
    ----------
    edges : list
        List of edge dictionaries
    used_detections : list
        Set of detection IDs already used in tracks

    Returns
    -------
    list : List of node IDs representing path from source to sink, or None if no path exists
    """
    # Build edge list excluding used detections
    valid_edges = []
    nodes = {'source', 'sink'}

    for edge in edges:
        from_node = edge['from']
        to_node = edge['to']
        cost = edge['cost']

        # Skip edges involving used detections (but not source/sink)
        if from_node in used_detections or to_node in used_detections:
            continue

        valid_edges.append((from_node, to_node, cost))
        nodes.add(from_node)
        nodes.add(to_node)

    if len(valid_edges) == 0:
        return None

    # Bellman-Ford algorithm
    distances = {node: float('inf') for node in nodes}
    distances['source'] = 0.0
    previous = {}

    # Relax edges V-1 times (where V = number of nodes)
    for _ in range(len(nodes) - 1):
        updated = False
        for from_node, to_node, cost in valid_edges:
            if distances[from_node] != float('inf'):
                new_dist = distances[from_node] + cost
                if new_dist < distances[to_node]:
                    distances[to_node] = new_dist
                    previous[to_node] = from_node
                    updated = True

        # Early termination if no updates
        if not updated:
            break

    # Check if sink is reachable
    if distances['sink'] == float('inf'):
        return None

    # Reconstruct path
    path = []
    node = 'sink'
    while node in previous:
        path.append(node)
        node = previous[node]
    path.append('source')
    path.reverse()
    return path
