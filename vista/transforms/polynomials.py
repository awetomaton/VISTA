import numpy as np


def fit_2d_polynomial(x, y, f, order):
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
        raise ValueError(
            f"Input arrays must have the same length. "
            f"Got x: {len(x)}, y: {len(y)}, f: {len(f)}"
        )

    n_points = len(x)
    n_coeffs = (order + 1) * (order + 2) // 2

    # Check for sufficient data points
    if n_points < n_coeffs:
        raise ValueError(
            f"Insufficient data points for order {order} polynomial. "
            f"Need at least {n_coeffs} points, got {n_points}"
        )

    # Build design matrix
    # Each row corresponds to a data point
    # Each column corresponds to a polynomial term
    A = np.zeros((n_points, n_coeffs))

    coeff_idx = 0
    for degree in range(order + 1):
        for x_power in range(degree, -1, -1):
            y_power = degree - x_power
            A[:, coeff_idx] = (x ** x_power) * (y ** y_power)
            coeff_idx += 1

    # Solve least squares problem: A * coeffs = f
    result = np.linalg.lstsq(A, f, rcond=None)
    coeffs = result[0]
    residuals = result[1][0] if len(result[1]) > 0 else 0.0
    rank = result[2]
    singular_values = result[3]

    return coeffs, residuals, rank, singular_values


def evaluate_2d_polynomial(coeffs, x, y, order=None):
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
        Array of polynomial coefficients, length must be (n+1)*(n+2)/2 for some integer n
    x : np.ndarray or float
        X coordinates (can be scalar or array)
    y : np.ndarray or float
        Y coordinates (can be scalar or array)
    order : int, optional
        Order of the polynomial. If None, inferred from length of coeffs.

    Returns
    -------
    np.ndarray or float
        Evaluated polynomial values with same shape as input x and y

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

    # Determine polynomial order if not provided
    if order is None:
        # Solve (n+1)*(n+2)/2 = len(coeffs) for n
        # This gives n^2 + 3n + 2 - 2*len(coeffs) = 0
        n_coeffs = len(coeffs)
        # Using quadratic formula: n = (-3 + sqrt(9 - 8 + 8*n_coeffs)) / 2
        discriminant = 1 + 8 * n_coeffs
        sqrt_disc = np.sqrt(discriminant)
        if sqrt_disc != int(sqrt_disc):
            raise ValueError(
                f"Invalid number of coefficients ({n_coeffs}). "
                f"Must be (n+1)*(n+2)/2 for some non-negative integer n."
            )
        order = int((-3 + sqrt_disc) / 2)

        # Verify
        expected_coeffs = (order + 1) * (order + 2) // 2
        if expected_coeffs != n_coeffs:
            raise ValueError(
                f"Invalid number of coefficients ({n_coeffs}). "
                f"Must be (n+1)*(n+2)/2 for some non-negative integer n."
            )

    # Verify coefficient count matches specified order
    expected_coeffs = (order + 1) * (order + 2) // 2
    if len(coeffs) != expected_coeffs:
        raise ValueError(
            f"For order {order}, expected {expected_coeffs} coefficients, "
            f"but got {len(coeffs)}"
        )

    # Evaluate polynomial
    result = np.zeros_like(x * y)  # Ensures proper broadcasting
    coeff_idx = 0

    # Iterate through degrees
    for degree in range(order + 1):
        # For each degree, iterate through powers of x from high to low
        for x_power in range(degree, -1, -1):
            y_power = degree - x_power
            result = result + coeffs[coeff_idx] * (x ** x_power) * (y ** y_power)
            coeff_idx += 1

    return result

