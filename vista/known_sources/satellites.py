"""Class for satellites


"""

from sgp4.api import Satrec, SatrecArray, SGP4_ERRORS


class Satellites():
    """
    Class to hold satellite TLE data, converting to positions as necessary
    """

    # TODO: Don't restrict myself to TLEs only?
    # use more up-to-date OMM files since number of known sats has surpassed TLE ID limits?

    # TODO: require filename on initialization instead?
    def __init__(self):
        self.satellites = SatrecArray([]) # empty satellites array

    def _parse_tle_blocks(self, lines):
        """Generates (name, line1, line2) tuples from raw TLE lines."""
        # TODO: decide what format to use for names
        # or does it even matter what they are in the dictionary?
        # i.e., actual names or just ID numbers?
        
        iterator = iter(lines)
        for line in iterator:
            # Check if line is a TLE header line
            if not line.startswith(('1 ', '2 ')):
                try:
                    line1 = next(iterator)
                    line2 = next(iterator)
                    name = f"SAT_{line1[2:7]}" # use NORAD ID as name for now
                    yield name, line1, line2
                except StopIteration:
                    break  # File ended abruptly
            else:
                # File is a 2-line format without names
                try:
                    line1 = line
                    line2 = next(iterator)
                    name = f"SAT_{line1[2:7]}" # use NORAD ID as name for now
                    yield name, line1, line2
                except StopIteration:
                    break

    def load_tle_file(self, file_path):
        """Parses a TLE file into a SatrecArray of unique objects"""
        satellites = {}
        
        with open(file_path, 'r', encoding='utf-8') as f:
            # Strip lines and ignore blanks
            lines = [line.strip() for line in f if line.strip()]
            
        for name, l1, l2 in self._parse_tle_blocks(lines):
            # Ensure TLE lines are actually valid
            if not (l1.startswith('1 ') and l2.startswith('2 ')):
                raise ValueError(f"Misaligned TLE block for: {name}")

            # Ensure no duplicates in the TLE file
            if name in satellites:
                raise ValueError(f"Satellite {name} is duplicated in the TLE file")
            
            sat = Satrec.twoline2rv(l1, l2)
            satellites[name] = sat

        self.satellites = SatrecArray(list(satellites.values()))
