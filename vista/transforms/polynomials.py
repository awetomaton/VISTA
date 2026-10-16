from typing import Optional, Union

import numpy as np
from numpy.typing import NDArray


def fit_2d_polynomial(x: NDArray, y: NDArray, f: NDArray, order: int) -> tuple[NDArray, float, int, NDArray]:
    """
    Fit a 2D polynomial to data using least squares.

    Given arrays of x, y coordinates and corresponding function values f,
    finds the polynomial coefficients that minimize the squared error.

    Parameters
    ----------
    x : np.ndarray
        X coordinates of data points (1D array)
    y : np.ndarray
        Y coordinates of data points (1D array)
    f : np.ndarray
        Function values at each (x, y) point (1D array)
    order : int
        Order of the polynomial to fit

    Returns
    -------
    coeffs : np.ndarray
        Array of fitted polynomial coefficients, length (order+1)*(order+2)/2
    residuals : float
        Sum of squared residuals
    rank : int
        Rank of the design matrix
    singular_values : np.ndarray
        Singular values of the design matrix

    Raises
    ------
    ValueError
        If input arrays have inconsistent shapes or if there are insufficient data points

    Examples
    --------
    >>> # Fit a linear function f(x,y) = 1 + 2*x + 3*y
    >>> x = np.array([0, 1, 0, 1, 2])
    >>> y = np.array([0, 0, 1, 1, 1])
    >>> f = 1 + 2*x + 3*y
    >>> coeffs, _, _, _ = fit_2d_polynomial(x, y, f, order=1)
    >>> # coeffs should be approximately [1, 2, 3]

    >>> # Fit with noisy data
    >>> x = np.random.rand(100)
    >>> y = np.random.rand(100)
    >>> f_true = 1 + 2*x + 3*y + x*y
    >>> f_noisy = f_true + 0.1 * np.random.randn(100)
    >>> coeffs, residuals, _, _ = fit_2d_polynomial(x, y, f_noisy, order=2)

    Notes
    -----
    The polynomial terms follow the same ordering as evaluate_2d_polynomial:
    ordered by total degree, then by decreasing powers of x.
    """
    # Convert to numpy arrays and flatten
    x = np.asarray(x).flatten()
    y = np.asarray(y).flatten()
    f = np.asarray(f).flatten()

    # Validate input shapes
    if len(x) != len(y) or len(x) != len(f):
        raise ValueError(f"Input arrays must have the same length. Got x: {len(x)}, y: {len(y)}, f: {len(f)}")

    n_points = len(x)
    n_coeffs = (order + 1) * (order + 2) // 2

    # Check for sufficient data points
    if n_points < n_coeffs:
        raise ValueError(
            f"Insufficient data points for order {order} polynomial. Need at least {n_coeffs} points, got {n_points}"
        )

    # Build design matrix
    # Each row corresponds to a data point
    # Each column corresponds to a polynomial term
    A = np.zeros((n_points, n_coeffs))

    coeff_idx = 0
    for degree in range(order + 1):
        for x_power in range(degree, -1, -1):
            y_power = degree - x_power
            A[:, coeff_idx] = (x**x_power) * (y**y_power)
            coeff_idx += 1

    # Column-scale the design matrix for numerical stability.
    # Without scaling, high-order terms (e.g. x^4 with x in [0, 2047]) create columns
    # spanning many orders of magnitude, causing lstsq to produce inaccurate coefficients.
    # Scaling each column to unit norm and then adjusting the coefficients back preserves
    # the original coordinate semantics so evaluate_2d_polynomial works unchanged.
    col_norms = np.linalg.norm(A, axis=0)
    col_norms[col_norms == 0] = 1.0
    A_scaled = A / col_norms

    # Solve least squares problem: A_scaled * coeffs_scaled = f
    result = np.linalg.lstsq(A_scaled, f, rcond=None)
    coeffs = result[0] / col_norms
    residuals = result[1][0] if len(result[1]) > 0 else 0.0
    rank = result[2]
    singular_values = result[3]

    return coeffs, residuals, rank, singular_values


def evaluate_2d_polynomial(
    coeffs: NDArray, x: Union[NDArray, float], y: Union[NDArray, float], order: Optional[int] = None
) -> Union[NDArray, float]:
    """
    Evaluate a 2D polynomial of arbitrary order.

    The polynomial terms are ordered by total degree, then by decreasing powers of x:
    - Order 0: c0
    - Order 1: c1*x + c2*y
    - Order 2: c3*x^2 + c4*x*y + c5*y^2
    - Order 3: c6*x^3 + c7*x^2*y + c8*x*y^2 + c9*y^3
    - etc.

    For a polynomial of order n, there are (n+1)*(n+2)/2 coefficients.

    Parameters
    ----------
    coeffs : np.ndarray
        Array whose last axis corresponds to list of polynomical coefficients. Last axis must
        be of length (n+1)*(n+2)/2 for some integer n. Other axes must be broadcastable to the
        shapes of x and y
    x : np.ndarray or float
        X coordinates (can be scalar or array). Must be broadcastable to the shape of y
    y : np.ndarray or float
        Y coordinates (can be scalar or array). Must be broadcastable to the shape of x
    order : int, optional
        Order of the polynomial. If None, inferred from length of last axis of coeffs.

    Returns
    -------
    np.ndarray or float
        Evaluated polynomial values. The dimension and shape of the resulting array is the
        same as whichever of coeffs[...,0], x, or y has higher dimension

    Raises
    ------
    ValueError
        If the length of coeffs doesn't correspond to a valid polynomial order

    Examples
    --------
    >>> # Evaluate f(x,y) = 1 + 2*x + 3*y (order 1)
    >>> coeffs = np.array([1, 2, 3])
    >>> evaluate_2d_polynomial(coeffs, 1.0, 2.0)
    9.0

    >>> # Evaluate f(x,y) = 1 + x + y + x^2 + xy + y^2 (order 2)
    >>> coeffs = np.array([1, 1, 1, 1, 1, 1])
    >>> evaluate_2d_polynomial(coeffs, 2.0, 3.0, order=2)
    24.0
    """
    coeffs = np.asarray(coeffs)
    x = np.asarray(x)
    y = np.asarray(y)

    # Determine polynomial order if not provided
    if order is None:
        # Solve (n+1)*(n+2)/2 = len(coeffs) for n
        # This gives n^2 + 3n + 2 - 2*len(coeffs) = 0
        n_coeffs = coeffs.shape[-1]
        # Using quadratic formula: n = (-3 + sqrt(9 - 8 + 8*n_coeffs)) / 2
        discriminant = 1 + 8 * n_coeffs
        sqrt_disc = np.sqrt(discriminant)
        if sqrt_disc != int(sqrt_disc):
            raise ValueError(
                f"Invalid number of coefficients ({n_coeffs}). Must be (n+1)*(n+2)/2 for some non-negative integer n."
            )
        order = int((-3 + sqrt_disc) / 2)

        # Verify
        expected_coeffs = (order + 1) * (order + 2) // 2
        if expected_coeffs != n_coeffs:
            raise ValueError(
                f"Invalid number of coefficients ({n_coeffs}). Must be (n+1)*(n+2)/2 for some non-negative integer n."
            )

    # Verify coefficient count matches specified order
    expected_coeffs = (order + 1) * (order + 2) // 2
    if coeffs.shape[-1] != expected_coeffs:
        raise ValueError(f"For order {order}, expected {expected_coeffs} coefficients, but got {coeffs.shape[-1]}")

    # lists of powers corresponding to the coefficients list
    x_powers = []
    y_powers = []
    for degree in range(order + 1):
        powers = np.arange(degree, -1, -1)
        x_powers.extend(powers)
        y_powers.extend(degree - powers)

    # append leading dimensions to broadcast over last axis of coeffs
    x_powers = np.reshape(x_powers, (1,) * x.ndim + coeffs.shape[-1:])
    y_powers = np.reshape(y_powers, (1,) * y.ndim + coeffs.shape[-1:])
    # append trailing dimension for powers
    new_x = x.reshape(x.shape + (1,))
    new_y = y.reshape(y.shape + (1,))

    # resulting multiplication over all arrays
    result = coeffs * new_x**x_powers * new_y**y_powers
    # the resulting sum for the 2d polynomial occurs along the -1 (coefficients) axis
    result = np.sum(result, axis=-1)
    return result
