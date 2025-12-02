"""Widget for configuring and running the Bias Removal treatment"""
import numpy as np

from vista.widgets.algorithms.treatments.base_treatment_widget import BaseTreatmentThread, BaseTreatmentWidget


class BiasRemovalProcessingThread(BaseTreatmentThread):
    """Worker thread for running the bias removal treatment"""

    def __init__(self, imagery, aoi=None):
        super().__init__(imagery, aoi)
        # Pre-compute bias image frame bounds for efficiency
        self.bias_image_frame_bounds = imagery.sensor.bias_image_frames.tolist() + [np.inf]
        self.current_bias_image_index = 0
        self.current_bias_image = imagery.sensor.bias_images[0]

    def process_frame(self, frame_data, frame_index, frame_number):
        """Process a single frame by removing bias"""
        # Update bias image if needed
        if frame_number >= self.bias_image_frame_bounds[self.current_bias_image_index + 1]:
            self.current_bias_image_index += 1
            self.current_bias_image = self.imagery.sensor.bias_images[self.current_bias_image_index]

        # Remove the bias frame
        return frame_data - self.current_bias_image

    def get_processed_name_suffix(self):
        """Get the suffix for processed imagery name"""
        return "BR"


class BiasRemovalWidget(BaseTreatmentWidget):
    """Configuration widget for Bias Removal"""

    def __init__(self, parent=None, imagery=None, aois=None):
        description = "Remove imagery bias using imagery bias frames"

        super().__init__(
            parent=parent,
            imagery=imagery,
            aois=aois,
            window_title="Bias Removal Treatment",
            description=description
        )

    def create_processing_thread(self, imagery, aoi):
        """Create the bias removal processing thread"""
        return BiasRemovalProcessingThread(imagery, aoi)

    def validate_sensor_requirements(self):
        """Validate that sensor has bias images"""
        if self.imagery is None or self.imagery.sensor is None:
            return False, "No sensor information available."

        if not hasattr(self.imagery.sensor, 'bias_images') or self.imagery.sensor.bias_images is None:
            return False, "Sensor does not have bias images. Please load bias calibration data."

        if len(self.imagery.sensor.bias_images) == 0:
            return False, "Sensor has no bias images loaded."

        return True, ""
