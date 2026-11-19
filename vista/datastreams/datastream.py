"""
Base Datastream class for grouping Imagery.

This module defines the Datastream base class, which is a simple class primarily used to group Imagery.
"""

import uuid
from dataclasses import dataclass, field
from typing import ClassVar, Optional


@dataclass
class Datastream:
    """
    Base class for Datastream.

    Core Attributes
    ---------------
    name : str
        Unique name for this datastream
    """

    name: Optional[str] = None
    uuid: str = field(init=False, default=None)

    # Class variable to track total number of datastream instances created
    _instance_count: ClassVar[int] = 0

    def __post_init__(self):
        """
        Initialize datastream instance and increment global counter.

        Generates a unique UUID for this datastream instance and initializes its
        name if not provided.
        """
        # Increment the class-level counter
        Datastream._instance_count += 1
        if self.name is None or self.name == "":
            self.name = f"Unknown Datastream {Datastream._instance_count}"
        self.uuid = uuid.uuid4()

    def __eq__(self, other):
        """Compare Datastreams based on UUID"""
        return hasattr(other, "uuid") and (self.uuid == other.uuid)
