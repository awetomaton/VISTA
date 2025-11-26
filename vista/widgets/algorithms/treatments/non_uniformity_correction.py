"""Widget for configuring and running the Non-Uniformity Correction treatment"""
import numpy as np

from vista.widgets.algorithms.treatments.base_treatment_widget import BaseTreatmentThread, BaseTreatmentWidget


class NonUniformityCorrectionProcessingThread(BaseTreatmentThread):
    """Worker thread for running the Non-Uniformity Correction treatment"""

    def __init__(self, imagery, aoi=None):
        super().__init__(imagery, aoi)
        # Pre-compute uniformity gain image frame bounds for efficiency
        self.nuc_image_frame_bounds = imagery.sensor.uniformity_gain_image_frames.tolist() + [np.inf]
        self.current_nuc_image_index = 0
        self.current_nuc_image = imagery.sensor.uniformity_gain_images[0]

    def process_frame(self, frame_data, frame_index, frame_number):
        """Process a single frame by correcting non-uniformity"""
        # Update uniformity gain image if needed
        if frame_number >= self.nuc_image_frame_bounds[self.current_nuc_image_index + 1]:
            self.current_nuc_image_index += 1
            self.current_nuc_image = self.imagery.sensor.uniformity_gain_images[self.current_nuc_image_index]

        # Correct the non-uniform responsivity by multiplying by the uniformity gain
        return frame_data * self.current_nuc_image

    def get_processed_name_suffix(self):
        """Get the suffix for processed imagery name"""
        return "NUC"


class NonUniformityCorrectionWidget(BaseTreatmentWidget):
    """Configuration widget for Non-Uniformity Correction"""

    def __init__(self, parent=None, imagery=None, aois=None):
        description = "Correct for image non-uniform responsivity using the imagery uniformity gain frames"

        super().__init__(
            parent=parent,
            imagery=imagery,
            aois=aois,
            window_title="Non-Uniformity Correction Treatment",
            description=description
        )

    def create_processing_thread(self, imagery, aoi):
        """Create the non-uniformity correction processing thread"""
        return NonUniformityCorrectionProcessingThread(imagery, aoi)

    def validate_sensor_requirements(self):
        """Validate that sensor has uniformity gain images"""
        if self.imagery is None or self.imagery.sensor is None:
            return False, "No sensor information available."

        if not hasattr(self.imagery.sensor, 'uniformity_gain_images') or \
           self.imagery.sensor.uniformity_gain_images is None:
            return False, "Sensor does not have uniformity gain images. Please load NUC calibration data."

        if len(self.imagery.sensor.uniformity_gain_images) == 0:
            return False, "Sensor has no uniformity gain images loaded."

        return True, ""
