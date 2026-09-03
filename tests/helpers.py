from dataclasses import fields

import numpy as np


def assert_constructor_fields_equal(actual, expected) -> None:
    assert type(actual) is type(expected)

    for data_field in fields(expected):
        if not data_field.init:
            continue

        actual_value = getattr(actual, data_field.name)
        expected_value = getattr(expected, data_field.name)
        if isinstance(expected_value, np.ndarray):
            np.testing.assert_array_equal(actual_value, expected_value)
        else:
            assert actual_value == expected_value, data_field.name
