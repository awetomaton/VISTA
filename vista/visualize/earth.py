import plotly.graph_objects as go
import numpy as np
from PIL import Image
from vista.visualize.data import EARTH_IMAGE_1K


colorscale=[
    [0.0, 'rgb(30, 59, 117)'],
    [0.1, 'rgb(46, 68, 21)'],
    [0.2, 'rgb(74, 96, 28)'],
    [0.3, 'rgb(115, 141, 90)'],
    [0.4, 'rgb(122, 126, 75)'],
    [0.6, 'rgb(122, 126, 75)'],
    [0.7, 'rgb(141, 115, 96)'],
    [0.8, 'rgb(223, 197, 170)'],
    [0.9, 'rgb(237, 214, 183)'],
    [1.0, 'rgb(255, 255, 255)']
]

def get_earth_ellipsoid(texture):
    N_lon = int(texture.shape[0])
    N_lat = int(texture.shape[1])
    theta = np.pi + np.linspace(0, 2*np.pi, N_lon)
    phi = np.linspace(0, np.pi, N_lat)

    x0 = 6378.137 * np.outer(np.cos(theta), np.sin(phi))
    y0 = 6378.137 * np.outer(np.sin(theta), np.sin(phi))
    z0 = 6356.752314245 * np.outer(np.ones(N_lon), np.cos(phi))

    return x0, y0, z0

def get_earth_fig() -> go.Figure:
    """Get a plotly figure with a WGS-84 Ellipsoid with a 1K Earth image texture"""
    texture = np.sum(np.asarray(Image.open(EARTH_IMAGE_1K)), axis=2).T

    x, y, z = get_earth_ellipsoid(texture)
    surf = go.Surface(x=x, y=y, z=z, surfacecolor=texture, colorscale=colorscale, showscale=False)
    layout = go.Layout(scene=dict(aspectratio=dict(x=1, y=1, z=1)))

    fig = go.Figure(data=[surf], layout=layout)
    fig.update_coloraxes(showscale=False)
    #fig.update_scenes(zaxis=dict(range=[-10, 10]))
    return fig
