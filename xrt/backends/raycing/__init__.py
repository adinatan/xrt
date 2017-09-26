# -*- coding: utf-8 -*-
"""
Package :mod:`~xrt.backends.raycing` provides the internal backend of xrt. It
defines beam sources in the module :mod:`~xrt.backends.raycing.sources`,
rectangular and round apertures in :mod:`~xrt.backends.raycing.apertures`,
optical elements in :mod:`~xrt.backends.raycing.oes`, material properties
(essentially reflectivity, transmittivity and absorption coefficient) for
interfaces and crystals in :mod:`~xrt.backends.raycing.materials` and screens
in :mod:`~xrt.backends.raycing.screens`.

.. _scriptingRaycing:

Coordinate systems
------------------

The following coordinate systems are considered (always right-handed):

1) *The global coordinate system*. It is arbitrary (user-defined) with one
   requirement driven by code simplification: Z-axis is vertical. For example,
   the system origin of Alba synchrotron is in the center of the ring at the
   ground level with Y-axis northward, Z upright and the units in mm.

   .. note::
       The positions of all optical elements, sources, screens etc. are given
       in the global coordinate system. This feature simplifies the beamline
       alignment when 3D CAD models are available.

2) *The local systems*.

   a) *of the beamline*. The local Y direction (the direction of the source)
      is determined by *azimuth* parameter of
      :class:`~xrt.backends.raycing.BeamLine` -- the angle measured cw from the
      global Y axis. The local beamline Z is also vertical and upward. The
      local beamline X is to the right. At *azimuth* = 0 the global system and
      the local beamline system are parallel to each other. In most of the
      supplied examples the global system and the local beamline system
      coincide.

   b) *of an optical element*. The origin is on the optical surface. Z is
      out-of-surface. At pitch, roll and yaw all zeros the local oe system
      and the local beamline system are parallel to each other.

      .. note::
          Pitch, roll and yaw rotations (correspondingly: Rx, Ry and Rz) are
          defined relative to the local axes of the optical element. The local
          axes rotate together with the optical element!

      .. note::
          The rotations are done in the following default sequence: yaw, roll,
          pitch. It can be changed by the user for any particular optical
          element. Sometimes it is necessary to define misalignment angles in
          addition to the positional angles. Because rotations do not commute,
          an extra set of angles may become unavoidable, which are applied
          after the positional rotations.
          See :class:`~xrt.backends.raycing.oes.OE`.

      The user-supplied functions for the surface height (z) and the normal as
      functions of (x, y) are defined in the local oe system.

   c) *of other beamline elements: sources, apertures, screens*. Z is upward
      and Y is along the beam line. The origin is given by the user. Usually it
      is on the original beam line.

.. imagezoom:: _images/axes.png

Units
-----

For the internal calculations, lengths are assumed to be in mm, although for
reflection geometries and simple Bragg cases (thick crystals) this convention
is not used. Angles are unitless (radians). Energy is in eV.

For plotting, the user may select units and conversion factors. The latter are
usually automatically deduced from the units.

Beam categories
---------------

xrt discriminates rays by several categories:

a) ``good``: reflected within the working optical surface;
b) ``out``: reflected outside of the working optical surface, i.e. outside of
   a metal stripe on a mirror;
c) ``over``: propagated over the surface without intersection;
d) ``dead``: arrived below the optical surface and thus absorbed by the OE.

This distinction simplifies the adjustment of entrance and exit slits. The
user supplies `physical` and `optical` limits, where the latter is used to
define the ``out`` category (for rays between `physical` and `optical` limits).
An alarm is triggered if the fraction of dead rays exceeds a specified level.

Scripting in python
-------------------

The user of :mod:`~xrt.backends.raycing` must do the following:

1) Instantiate class :class:`~xrt.backends.raycing.BeamLine` and fill it with
   sources, optical elements, screens etc.
2) Create a module-level function that returns a dictionary of beams -- the
   instances of :class:`~xrt.backends.raycing.sources.Beam`. Assign this
   function to the module variable `xrt.backends.raycing.run.run_process`.
   The beams should be obtained by the methods shine() of a source, expose() of
   a screen, reflect() or multiple_reflect() of an optical element, propagate()
   of an aperture.
3) Use the keys in this dictionary for creating the plots (instances of
   :class:`~xrt.plotter.XYCPlot`). Note that at the time of instantiation the
   plots are just empty placeholders for the future 2D and 1D histograms.
4) Run :func:`~xrt.runner.run_ray_tracing()` function for the created plots.

Additionally, the user may define a generator that will run a loop of ray
tracing for changing geometry (mimics a real scan) or for different material
properties etc. The generator should modify the beamline elements and output
file names of the plots before *yield*. After the *yield* the plots are ready
and the generator may use their fields, e.g. *intensity* or *dE* or *dy* or
others to prepare a scan plot. Typically, this sequence is within a loop; after
the loop the user may prepare the final scan plot using matplotlib
functionality. The generator is given to :func:`~xrt.runner.run_ray_tracing()`
as a parameter.

See the supplied examples."""
from __future__ import print_function
__module__ = "raycing"
__author__ = "Konstantin Klementiev, Roman Chernikov"
__date__ = "26 Mar 2016"

# import copy
import types
import sys
import numpy as np
from itertools import compress
from collections import OrderedDict
import re
import copy
import inspect

try:
    from matplotlib.backends import qt_compat
except ImportError:
    from matplotlib.backends import qt4_compat
    qt_compat = qt4_compat

if 'pyqt4' in qt_compat.QT_API.lower():  # also 'PyQt4v2'
    QtName = "PyQt4"
    import PyQt4.QtGui as myQtGUI
elif 'pyqt5' in qt_compat.QT_API.lower():
    QtName = "PyQt5"
    import PyQt5.QtWidgets as myQtGUI
else:
    QtName = None

if QtName is not None:
    QApplication = myQtGUI.QApplication

try:  # for Python 3 compatibility:
    unicode = unicode
except NameError:
    # 'unicode' is undefined, must be Python 3
    unicode = str
    basestring = (str, bytes)
else:
    # 'unicode' exists, must be Python 2
    unicode = unicode
    basestring = basestring

from .physconsts import SIE0
zEps = 1e-12  # mm: target accuracy in z while searching for intersection
misalignmentTolerated = 0.1  # for automatic checking of oe center position
accuracyInPosition = 0.1  # accuracy for positioning of oe
dt = 1e-5  # mm: margin around OE within which the intersection is searched
ds = 0.  # mm: margin used in multiple reflections
nrays = 100000
maxIteration = 100  # max number of iterations while searching for intersection
maxHalfSizeOfOE = 1000.
maxDepthOfOE = 100.
# maxZDeviationAtOE = 100.

# colors of the rays in a 0-10 range (red-violet)
hueGood = 3.
hueOut = 8.
hueOver = 1.6
hueDead = 0.2
hueMin = 0.
hueMax = 10.

targetOpenCL = 'auto'
precisionOpenCL = 'auto'


def is_sequence(arg):
    """Checks whether *arg* is a sequence."""
    result = (not hasattr(arg, "strip") and hasattr(arg, "__getitem__") or
              hasattr(arg, "__iter__"))
    if result:
        try:
            arg[0]
        except IndexError:
            result = False
        if result:
            result = not isinstance(arg, (basestring, unicode))
    return result


def distance_xy(p1, p2):
    """Calculates 2D distance between p1 and p2. p1 and p2 are vectors of
    length >= 2."""
    return ((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)**0.5


def distance_xyz(p1, p2):
    """Calculates 2D distance between p1 and p2. p1 and p2 are vectors of
    length >= 3."""
    return ((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2 + (p1[2]-p2[2])**2)**0.5


def rotate_x(y, z, cosangle, sinangle):
    """3D rotaion around *x* (pitch). *y* and *z* are values or arrays.
    Positive rotation is for positive *sinangle*. Returns *yNew, zNew*."""
    return cosangle*y - sinangle*z, sinangle*y + cosangle*z


def rotate_y(x, z, cosangle, sinangle):
    """3D rotaion around *y* (roll). *x* and *z* are values or arrays.
    Positive rotation is for positive *sinangle*. Returns *xNew, zNew*."""
    return cosangle*x + sinangle*z, -sinangle*x + cosangle*z


def rotate_z(x, y, cosangle, sinangle):
    """3D rotaion around *z*. *x* and *y* are values or arrays.
    Positive rotation is for positive *sinangle*. Returns *xNew, yNew*."""
    return cosangle*x - sinangle*y, sinangle*x + cosangle*y


def rotate_beam(beam, indarr=None, rotationSequence='RzRyRx',
                pitch=0, roll=0, yaw=0, skip_xyz=False, skip_abc=False,
                is2ndXtal=False):
    """Rotates the *beam* indexed by *indarr* by the angles *yaw, roll, pitch*
    in the sequence given by *rotationSequence*. A leading '-' symbol of
    *rotationSequence* reverses the sequences.
    """
    angles = {'z': yaw, 'y': roll, 'x': pitch}
    rotates = {'z': rotate_z, 'y': rotate_y, 'x': rotate_x}
    if not skip_xyz:
        coords1 = {'z': beam.x, 'y': beam.x, 'x': beam.y}
        coords2 = {'z': beam.y, 'y': beam.z, 'x': beam.z}
    if not skip_abc:
        vcomps1 = {'z': beam.a, 'y': beam.a, 'x': beam.b}
        vcomps2 = {'z': beam.b, 'y': beam.c, 'x': beam.c}

    if rotationSequence[0] == '-':
        seq = rotationSequence[6] + rotationSequence[4] + rotationSequence[2]
    else:
        seq = rotationSequence[1] + rotationSequence[3] + rotationSequence[5]
    for s in seq:
        angle, rotate = angles[s], rotates[s]
        if not skip_xyz:
            c1, c2 = coords1[s], coords2[s]
        if not skip_abc:
            v1, v2 = vcomps1[s], vcomps2[s]
        if angle != 0:
            cA = np.cos(angle)
            sA = np.sin(angle)
            if indarr is None:
                indarr = slice(None)
            if not skip_xyz:
                c1[indarr], c2[indarr] = rotate(c1[indarr], c2[indarr], cA, sA)
            if not skip_abc:
                v1[indarr], v2[indarr] = rotate(v1[indarr], v2[indarr], cA, sA)


def rotate_xyz(x, y, z, indarr=None, rotationSequence='RzRyRx',
               pitch=0, roll=0, yaw=0):
    """Rotates the arrays *x*, *y* and *z* indexed by *indarr* by the angles
    *yaw, roll, pitch* in the sequence given by *rotationSequence*. A leading
    '-' symbol of *rotationSequence* reverses the sequences.
    """
    angles = {'z': yaw, 'y': roll, 'x': pitch}
    rotates = {'z': rotate_z, 'y': rotate_y, 'x': rotate_x}
    coords1 = {'z': x, 'y': x, 'x': y}
    coords2 = {'z': y, 'y': z, 'x': z}

    if rotationSequence[0] == '-':
        seq = rotationSequence[6] + rotationSequence[4] + rotationSequence[2]
    else:
        seq = rotationSequence[1] + rotationSequence[3] + rotationSequence[5]
    for s in seq:
        angle, rotate = angles[s], rotates[s]
        c1, c2 = coords1[s], coords2[s]
        if angle != 0:
            cA = np.cos(angle)
            sA = np.sin(angle)
            if indarr is None:
                indarr = slice(None)
            c1[indarr], c2[indarr] = rotate(c1[indarr], c2[indarr], cA, sA)
    return x, y, z


def rotate_point(point, rotationSequence='RzRyRx', pitch=0, roll=0, yaw=0):
    """Rotates the *point* (3-sequence) by the angles *yaw, roll, pitch*
    in the sequence given by *rotationSequence*. A leading '-' symbol of
    *rotationSequence* reverses the sequences.
    """
    angles = {'z': yaw, 'y': roll, 'x': pitch}
    rotates = {'z': rotate_z, 'y': rotate_y, 'x': rotate_x}
    ind1 = {'z': 0, 'y': 0, 'x': 1}
    ind2 = {'z': 1, 'y': 2, 'x': 2}
    newp = [coord for coord in point]
    if rotationSequence[0] == '-':
        seq = rotationSequence[6] + rotationSequence[4] + rotationSequence[2]
    else:
        seq = rotationSequence[1] + rotationSequence[3] + rotationSequence[5]
    for s in seq:
        angle, rotate = angles[s], rotates[s]
        if angle != 0:
            cA = np.cos(angle)
            sA = np.sin(angle)
            newp[ind1[s]], newp[ind2[s]] = rotate(
                newp[ind1[s]], newp[ind2[s]], cA, sA)
    return newp


def global_to_virgin_local(bl, beam, lo, center=None, part=None):
    """Transforms *beam* from the global to the virgin (i.e. with pitch, roll
    and yaw all zeros) local system. The resulting local beam is *lo*. If
    *center* is provided, the rotation Rz is about it, otherwise is about the
    origin of *beam*. The beam arrays can be sliced by *part* indexing array.
    *bl* is an instance of :class:`BeamLine`"""
    if part is None:
        part = np.ones(beam.x.shape, dtype=np.bool)
    a0, b0 = bl.sinAzimuth, bl.cosAzimuth
    if center is None:
        center = [0, 0, 0]
    lo.x[part] = beam.x[part] - center[0]
    lo.y[part] = beam.y[part] - center[1]
    lo.z[part] = beam.z[part] - center[2]
    if a0 == 0:
        lo.a[part] = beam.a[part]
        lo.b[part] = beam.b[part]
    else:
        lo.x[part], lo.y[part] = rotate_z(lo.x[part], lo.y[part], b0, a0)
        lo.a[part], lo.b[part] = rotate_z(beam.a[part], beam.b[part], b0, a0)
    lo.c[part] = beam.c[part]  # unchanged


def virgin_local_to_global(bl, vlb, center=None, part=None,
                           skip_xyz=False, skip_abc=False, is2ndXtal=False):
    """Transforms *vlb* from the virgin (i.e. with pitch, roll and yaw all
    zeros) local to the global system and overwrites the result to *vlb*. If
    *center* is provided, the rotation Rz is about it, otherwise is about the
    origin of *beam*. The beam arrays can be sliced by *part* indexing array.
    *bl* is an instance of :class:`BeamLine`"""
    if part is None:
        part = np.ones(vlb.x.shape, dtype=np.bool)
    a0, b0 = bl.sinAzimuth, bl.cosAzimuth
    if a0 != 0:
        if not skip_abc:
            vlb.a[part], vlb.b[part] = rotate_z(
                vlb.a[part], vlb.b[part], b0, -a0)
        if not skip_xyz:
            vlb.x[part], vlb.y[part] = rotate_z(
                vlb.x[part], vlb.y[part], b0, -a0)
    if (center is not None) and (not skip_xyz):
        vlb.x[part] += center[0]
        vlb.y[part] += center[1]
        vlb.z[part] += center[2]


def check_alarm(self, incoming, beam):
    """Appends an alarm string to the list of beamline alarms if the alarm
    condition is fulfilled."""
    incomingSum = incoming.sum()
    if incomingSum > 0:
        badSum = (beam.state == self.lostNum).sum()
        ratio = float(badSum)/incomingSum
        if ratio > self.alarmLevel:
            alarmStr = ('{0}{1} absorbes {2:.2%} of rays ' +
                        'at {3:.0%} alarm level!').format(
                'Alarm! ', self.name, ratio, self.alarmLevel)
            self.bl.alarms.append(alarmStr)
    else:
        self.bl.alarms.append('no incident rays to {0}!'.format(self.name))


def get_x(beam):
    """Used for retrieving data for x-, y- or c-axis of a plot."""
    return beam.x


def get_y(beam):
    """Used for retrieving data for x-, y- or c-axis of a plot."""
    return beam.y


def get_z(beam):
    """Used for retrieving data for x-, y- or c-axis of a plot."""
    return beam.z


def get_s(beam):
    """Used for retrieving data for x-, y- or c-axis of a plot."""
    return beam.s


def get_phi(beam):
    """Used for retrieving data for x-, y- or c-axis of a plot."""
    return beam.phi


def get_r(beam):
    """Used for retrieving data for x-, y- or c-axis of a plot."""
    return beam.r


def get_xprime(beam):
    """Used for retrieving data for x-, y- or c-axis of a plot."""
    return beam.a / beam.b


def get_zprime(beam):
    """Used for retrieving data for x-, y- or c-axis of a plot."""
    return beam.c / beam.b


def get_path(beam):
    """Used for retrieving data for x-, y- or c-axis of a plot."""
    return beam.path


def get_order(beam):
    """Used for retrieving data for x-, y- or c-axis of a plot."""
    return beam.order if hasattr(beam, 'order') else np.ones_like(beam.state)


def get_energy(beam):
    """Used for retrieving data for x-, y- or c-axis of a plot."""
    return beam.E


def get_reflection_number(beam):
    """Used for retrieving data for x-, y- or c-axis of a plot."""
    return beam.nRefl  # if hasattr(beam, 'nRefl') else beam.state


def get_elevation_d(beam):
    """Used for retrieving data for x-, y- or c-axis of a plot."""
    return beam.elevationD
# if hasattr(beam, 'elevationD') else np.zeros_like(beam.x)


def get_elevation_x(beam):
    """Used for retrieving data for x-, y- or c-axis of a plot."""
    return beam.elevationX  # if hasattr(beam, 'elevationX') else beam.x


def get_elevation_y(beam):
    """Used for retrieving data for x-, y- or c-axis of a plot."""
    return beam.elevationY  # if hasattr(beam, 'elevationY') else beam.y


def get_elevation_z(beam):
    """Used for retrieving data for x-, y- or c-axis of a plot."""
    return beam.elevationZ  # if hasattr(beam, 'elevationZ') else beam.z


def get_Es_amp(beam):
    """Used for retrieving data for x-, y- or c-axis of a plot."""
    return np.abs(beam.Es)


def get_Ep_amp(beam):
    """Used for retrieving data for x-, y- or c-axis of a plot."""
    return np.abs(beam.Ep)


def get_Es_phase(beam):
    """Used for retrieving data for x-, y- or c-axis of a plot."""
    return np.angle(beam.Es)
#    return np.arctan2(beam.Es.imag, beam.Es.real)


def get_Ep_phase(beam):
    """Used for retrieving data for x-, y- or c-axis of a plot."""
    return np.angle(beam.Ep)
#    return np.arctan2(beam.Ep.imag, beam.Ep.real)


def get_polarization_degree(beam):
    """Used for retrieving data for x-, y- or c-axis of a plot."""
    I = (beam.Jss + beam.Jpp)
    I[I <= 0] = 1.
    pd = np.sqrt((beam.Jss-beam.Jpp)**2 + 4.*abs(beam.Jsp)**2) / I
    pd[I <= 0] = 0.
    return pd


def get_ratio_ellipse_axes(beam):
    """Used for retrieving data for x-, y- or c-axis of a plot."""
    dI2 = (beam.Jss - beam.Jpp)**2
    return 2. * beam.Jsp.imag /\
        (np.sqrt(dI2 + 4*abs(beam.Jsp)**2) + np.sqrt(dI2 + 4*beam.Jsp.real**2))


def get_circular_polarization_rate(beam):
    """Used for retrieving data for x-, y- or c-axis of a plot."""
    I = (beam.Jss + beam.Jpp)
    I[I <= 0] = 1.
    cpr = 2. * beam.Jsp.imag / I
    cpr[I <= 0] = 0.
    return cpr


def get_polarization_psi(beam):
    """Angle between the semimajor axis of the polarization ellipse relative to
    the s polarization. Used for retrieving data for x-, y- or c-axis of a
    plot."""
#    return 0.5 * np.arctan2(2.*beam.Jsp.real, beam.Jss-beam.Jpp) * 180 / np.pi
    return 0.5 * np.arctan2(2.*beam.Jsp.real, beam.Jss-beam.Jpp)


def get_phase_shift(beam):  # in units of pi!
    """Used for retrieving data for x-, y- or c-axis of a plot."""
    return np.angle(beam.Jsp) / np.pi


def get_incidence_angle(beam):
    """Used for retrieving data for x-, y- or c-axis of a plot."""
    return beam.theta if hasattr(beam, 'theta') else np.zeros_like(beam.x)


def get_a(beam):
    """Used for retrieving data for x-, y- or c-axis of a plot."""
    return beam.a


def get_b(beam):
    """Used for retrieving data for x-, y- or c-axis of a plot."""
    return beam.b

get_theta = get_incidence_angle


def get_output(plot, beamsReturnedBy_run_process):
    """Used by :mod:`multipro` for creating images of *plot* - instance of
    :class:`XYCPlot`. *beamsReturnedBy_run_process* is a dictionary of
    :class:`Beam` instances returned by user-defined :func:`run_process`.

    :func:`get_output` creates an indexing array corresponding to the requested
    properties of rays in *plot*. It also calculates the number of rays with
    various properties defined in `raycing` backend.
     """
    beam = beamsReturnedBy_run_process[plot.beam]
    if plot.beamState is None:
        beamState = beam.state
    else:
        beamState = beamsReturnedBy_run_process[plot.beamState].state
    nrays = len(beam.x)

    locAlive = (beamState > 0).sum()
    part = np.zeros(nrays, dtype=np.bool)
    locGood = 0
    locOut = 0
    locOver = 0
    locDead = 0
    for rayFlag in plot.rayFlag:
        locPart = beamState == rayFlag
        if rayFlag == 1:
            locGood = locPart.sum()
        if rayFlag == 2:
            locOut = locPart.sum()
        if rayFlag == 3:
            locOver = locPart.sum()
        if rayFlag < 0:
            locDead += locPart.sum()
        part = part | locPart
    if hasattr(beam, 'accepted'):
        locAccepted = beam.accepted
        locAcceptedE = beam.acceptedE
        locSeeded = beam.seeded
        locSeededI = beam.seededI
    else:
        locAccepted = 0
        locAcceptedE = 0
        locSeeded = 0
        locSeededI = 0

    if hasattr(beam, 'displayAsAbsorbedPower'):
        plot.displayAsAbsorbedPower = True
    if isinstance(plot.xaxis.data, types.FunctionType):
        x = plot.xaxis.data(beam) * plot.xaxis.factor
    elif isinstance(plot.xaxis.data, np.ndarray):
        x = plot.xaxis.data * plot.xaxis.factor
    else:
        raise ValueError('cannot find data for x!')
    if isinstance(plot.yaxis.data, types.FunctionType):
        y = plot.yaxis.data(beam) * plot.yaxis.factor
    elif isinstance(plot.yaxis.data, np.ndarray):
        y = plot.yaxis.data * plot.yaxis.factor
    else:
        raise ValueError('cannot find data for y!')
    if plot.caxis.useCategory:
        cData = np.zeros_like(beamState)
        cData[beamState == 1] = hueGood
        cData[beamState == 2] = hueOut
        cData[beamState == 3] = hueOver
        cData[beamState < 0] = hueDead
        flux = np.ones_like(x)
    else:
        if plot.beamC is None:
            beamC = beam
        else:
            beamC = beamsReturnedBy_run_process[plot.beamC]
        if isinstance(plot.caxis.data, types.FunctionType):
            cData = plot.caxis.data(beamC) * plot.caxis.factor
        elif isinstance(plot.caxis.data, np.ndarray):
            cData = plot.caxis.data * plot.caxis.factor
        else:
            raise ValueError('cannot find data for cData!')

        if plot.fluxKind.startswith('power'):
            flux = ((beam.Jss + beam.Jpp) *
                    beam.E * beam.accepted / beam.seeded * SIE0)
        elif plot.fluxKind.startswith('s'):
            flux = beam.Jss
        elif plot.fluxKind.startswith('p'):
            flux = beam.Jpp
        elif plot.fluxKind.startswith('+-45'):
            flux = 2*beam.Jsp.real
        elif plot.fluxKind.startswith('left-right'):
            flux = 2*beam.Jsp.imag
        elif plot.fluxKind.startswith('Es'):
            flux = beam.Es
        elif plot.fluxKind.startswith('Ep'):
            flux = beam.Ep
        else:
            flux = beam.Jss + beam.Jpp

    return x[part], y[part], flux[part], cData[part], nrays, locAlive,\
        locGood, locOut, locOver, locDead, locAccepted, locAcceptedE,\
        locSeeded, locSeededI


def append_to_flow(meth, bOut, frame):
    oe = meth.__self__
    if oe.bl is not None:
        if oe.bl.flowSource != 'Qook':
            fdoc = re.findall(r"Returned values:.*", meth.__doc__)
            fdoc = fdoc[0].replace("Returned values: ", '').split(',')
            kwArgsIn = dict()
            kwArgsOut = dict()
            argValues = inspect.getargvalues(frame)
            for arg in argValues.args[1:]:
                if str(arg) == 'beam':
                    kwArgsIn[arg] = id(argValues.locals[arg])
                else:
                    kwArgsIn[arg] = argValues.locals[arg]

            for outstr, outbm in zip(list(fdoc), bOut):
                kwArgsOut[outstr.strip()] = id(outbm)

            oe.bl.flow.append([oe.name, meth.__func__,
                               kwArgsIn, kwArgsOut])


class BeamLine(object):
    u"""
    Container class for beamline components. It also defines the beam line
    direction and height."""
    def __init__(self, azimuth=0., height=0., alignE=9000., alignMode=1):
        u"""
        *azimuth*: float
            Is counted in cw direction from the global Y axis. At
            *azimuth* = 0 the local Y coincides with the global Y.

        *height*: float
            Beamline height in the global system.

        *alignE*: float
            Energy for automatic alignment in [eV]. Plays a role if the *pitch*
            or *bragg* parameters of the energy dispersive optical elements
            were set to 'auto'.

        *alignMode*: int
            Takes values in the range [0-2]. In mode 0 the single alignment ray
            is propagated along the optical axis in order to calculate the
            positions of the optical elements, if one or two coordinates of the
            element were set to 'auto'. This mode is convenient for
            quick alignment. In Mode 1 the full beam propagates together with
            the alignment ray and allow to combine alignment with ray tracing.
            This mode is convenient for the scans where the positions of
            optical element is assumed to change. Mode 2 is similar to
            mode 1 but the alignment ray origin and direction are
            intensity-weighted average for all good rays. Useful in
            asymmetric geometries when the optical axis is blocked by
            apertures.


        """
        self.azimuth = azimuth
#        self.sinAzimuth = np.sin(azimuth)  # a0
#        self.cosAzimuth = np.cos(azimuth)  # b0
        self.height = height
        self.alignE = alignE
        self.alignMode = alignMode
        self.sources = []
        self.oes = []
        self.slits = []
        self.screens = []
        self.alarms = []
        self.name = ''
        self.oesDict = OrderedDict()
        self.unalignedOesDict = OrderedDict()
        self.flow = []
        self.materialsDict = OrderedDict()
        self.beamsDict = OrderedDict()
        self.flowSource = 'Qook'
        self.beamsRevDict = dict()
        self.blViewer = None

    @property
    def azimuth(self):
        return self._azimuth

    @azimuth.setter
    def azimuth(self, value):
        self._azimuth = value
        self.sinAzimuth = np.sin(value)
        self.cosAzimuth = np.cos(value)

    def align(self, startFrom=0):
        if self.alignMode == 0:
            nrays = 2  # Not 1 to keep the array type
        else:
            nrays = 1e4
        if self.oesDict is not None and self.flow is not None:
            for segment in self.flow[startFrom:]:
                tmpNrays = None
                autoBragg = False
                autoPitch = False
                segOE = self.oesDict[segment[0]][0]
                usegOE = self.unalignedOesDict[segment[0]][0]
                fArgs = {}
                for inArg in segment[2].items():
                    if inArg[0].startswith('beam'):
                        if inArg[1] is None:
                            inBeam = None
                            break
                        fArgs[inArg[0]] = self.beamsDict[inArg[1]]
                        inBeam = fArgs['beam']
                    else:
                        fArgs[inArg[0]] = inArg[1]
                try:
                    if inBeam is None:
                        continue
                except:
                    pass
                try:
                    print(segment[0], segOE.center, segment[2]['beam'])
                except:
                    pass
                autoCenter = [x == 'auto' for x in usegOE.center]

                if any(autoCenter):
                    bStart = inBeam
                    bStartC = np.array([bStart.x[0], bStart.y[0], bStart.z[0]])
                    bStartDir = np.array([bStart.a[0], bStart.b[0],
                                          bStart.c[0]])

                    fixedCoord = np.invert(np.array(autoCenter))

                    vLen = np.linalg.norm(np.array(list(compress(
                        bStartC, fixedCoord))) -
                        np.array(list(compress(segOE.center, fixedCoord))))
                    segOE.center = bStartC + vLen * bStartDir

                if hasattr(usegOE, 'pitch'):
                    if usegOE.pitch == 'auto':
                        autoPitch = True

                if hasattr(usegOE, 'bragg'):
                    if usegOE.bragg == 'auto':
                        autoBragg = True

                if autoBragg or autoPitch:
                        braggT = segOE.material.get_Bragg_angle(self.alignE)
                        alphaT = 0 if segOE.alpha is None else segOE.alpha
                        lauePitch = 0

                        braggT += -segOE.material.get_dtheta(self.alignE,
                                                             alphaT)
                        if segOE.material.geom.startswith('Laue'):
                            lauePitch = 0.5 * np.pi

                        loBeam = copy.deepcopy(inBeam)
                        global_to_virgin_local(
                            self, inBeam, loBeam,
                            center=segOE.center)
                        rotate_beam(
                            loBeam,
                            roll=-(segOE.positionRoll + segOE.roll),
                            yaw=-segOE.yaw,
                            pitch=0)
                        theta0 = np.arctan2(-loBeam.c[0], loBeam.b[0])
                        th2pitch = np.sqrt(1. - loBeam.a[0]**2)
                        targetPitch = np.arcsin(np.sin(braggT) / th2pitch) -\
                            theta0
                        targetPitch += alphaT + lauePitch
                        if autoBragg:
                            segOE.bragg = targetPitch-segOE.pitch
                        else:  # autoPitch
                            segOE.pitch = targetPitch

                if len(re.findall('raycing.sou', str(type(segOE)).lower())):
                    if hasattr(segOE, 'nrays'):
                        if segOE.nrays != nrays:
                            tmpNrays = segOE.nrays
                            segOE.nrays = nrays

                outBeams = segment[1](segOE, **fArgs)
                if tmpNrays is not None:
                    segOE.nrays = tmpNrays

                if isinstance(outBeams, tuple):
                    for outBeam, beamName in zip(list(outBeams),
                                                 list(segment[3].values())):
                        self.beamsDict[beamName] = outBeam
                else:
                    if self.alignMode == 0:
                        if len(re.findall('raycing.sou',
                                          str(type(segOE)).lower())):
                            outBeams.x[0] = 0
                            outBeams.y[0] = 0
                            outBeams.z[0] = 0
                            outBeams.a[0] = 0
                            outBeams.b[0] = 1
                            outBeams.c[0] = 0
                            outBeams.state[:] = 1
                            outBeams.E[0] = self.alignE
                    else:
                        good = outBeams.state[1:] > 0
                        intensity = np.sqrt(np.abs(outBeams.Jss[good])**2 +
                                            np.abs(outBeams.Jpp[good])**2)
                        totalI = np.sum(intensity)
                        for fieldName in ['x', 'y', 'z', 'a', 'b', 'c']:
                            field = getattr(outBeams, fieldName)
                            field[0] = np.sum(field[good]*intensity) / totalI
                            setattr(outBeams, fieldName, field)
                        outBeams.state[0] = 1
                        outBeams.E[0] = self.alignE

                    self.beamsDict[str(list(segment[3].values())[0])] =\
                        outBeams

    def prepare_flow(self):
        frame = inspect.currentframe()
        localsDict = frame.f_back.f_locals
        globalsDict = frame.f_back.f_globals
        for objectName, memObject in globalsDict.items():
            if len(re.findall('raycing.materials', str(type(memObject)))) > 0:
                self.materialsDict[objectName] = memObject

        for objectName, memObject in localsDict.items():
            if len(re.findall('sources_beams.Beam', str(type(memObject)))) > 0:
                self.beamsDict[objectName] = memObject
                self.beamsRevDict[id(memObject)] = objectName

        if self.flow is not None and len(self.beamsRevDict) > 0:
            for segment in self.flow:
                for iseg in [2, 3]:
                    for argName, argVal in segment[iseg].items():
                        if len(re.findall('beam', str(argName))) > 0:
                            segment[iseg][argName] =\
                                self.beamsRevDict[argVal]

    def propagate_flow(self, startFrom=0, align=False):
        if align and self.alignMode == 0:
                nrays = 2  # Not 1 to keep the array type
        if self.oesDict is not None and self.flow is not None:
            for segment in self.flow[startFrom:]:
                if align:
                    tmpNrays = None
                    autoBragg = False
                    autoPitch = False
                    usegOE = self.unalignedOesDict[segment[0]][0]
                segOE = self.oesDict[segment[0]][0]

                fArgs = {}
                for inArg in segment[2].items():
                    if inArg[0].startswith('beam'):
                        if inArg[1] is None:
                            inBeam = None
                            break
                        fArgs[inArg[0]] = self.beamsDict[inArg[1]]
                        inBeam = fArgs['beam']
                    else:
                        fArgs[inArg[0]] = inArg[1]
                try:
                    if inBeam is None:
                        continue
                except:
                    pass

                if align:
                    autoCenter = [x == 'auto' for x in usegOE.center]

                    if any(autoCenter):
                        bStart = inBeam
                        bStartC = np.array([bStart.x[0], bStart.y[0],
                                            bStart.z[0]])
                        bStartDir = np.array([bStart.a[0], bStart.b[0],
                                              bStart.c[0]])

                        fixedCoord = np.invert(np.array(autoCenter))

                        vLen = np.linalg.norm(np.array(list(compress(
                            bStartC, fixedCoord))) -
                            np.array(list(compress(segOE.center, fixedCoord))))
                        segOE.center = bStartC + vLen * bStartDir

                    if hasattr(usegOE, 'pitch'):
                        if usegOE.pitch == 'auto':
                            autoPitch = True

                    if hasattr(usegOE, 'bragg'):
                        if usegOE.bragg == 'auto':
                            autoBragg = True

                    if autoBragg or autoPitch:
                            braggT =\
                                segOE.material.get_Bragg_angle(self.alignE)
                            alphaT = 0 if segOE.alpha is None else segOE.alpha
                            lauePitch = 0

                            braggT += -segOE.material.get_dtheta(self.alignE,
                                                                 alphaT)
                            if segOE.material.geom.startswith('Laue'):
                                lauePitch = 0.5 * np.pi

                            loBeam = copy.deepcopy(inBeam)
                            global_to_virgin_local(
                                self, inBeam, loBeam,
                                center=segOE.center)
                            rotate_beam(
                                loBeam,
                                roll=-(segOE.positionRoll + segOE.roll),
                                yaw=-segOE.yaw,
                                pitch=0)
                            theta0 = np.arctan2(-loBeam.c[0], loBeam.b[0])
                            th2pitch = np.sqrt(1. - loBeam.a[0]**2)
                            targetPitch =\
                                np.arcsin(np.sin(braggT) / th2pitch) - theta0
                            targetPitch += alphaT + lauePitch
                            if autoBragg:
                                segOE.bragg = targetPitch-segOE.pitch
                            else:  # autoPitch
                                segOE.pitch = targetPitch

                    if len(re.findall('raycing.sou', str(type(segOE)).lower(
                            ))) and self.alignMode == 0:
                        if hasattr(segOE, 'nrays'):
                            if segOE.nrays != nrays:
                                tmpNrays = segOE.nrays
                                segOE.nrays = nrays

                outBeams = segment[1](segOE, **fArgs)
                if align and self.alignMode == 0:
                    if tmpNrays is not None:
                        segOE.nrays = tmpNrays

                if isinstance(outBeams, tuple):
                    for outBeam, beamName in zip(list(outBeams),
                                                 list(segment[3].values())):
                        self.beamsDict[beamName] = outBeam
                else:
                    if align:
                        if self.alignMode in [0, 1]:
                            if len(re.findall('raycing.sou',
                                              str(type(segOE)).lower())):
                                outBeams.x[0] = 0
                                outBeams.y[0] = 0
                                outBeams.z[0] = 0
                                outBeams.a[0] = 0
                                outBeams.b[0] = 1
                                outBeams.c[0] = 0
                                outBeams.state[:] = 1
                                outBeams.E[0] = self.alignE
                        else:
                            good = outBeams.state[1:] > 0
                            intensity = np.sqrt(np.abs(outBeams.Jss[good])**2 +
                                                np.abs(outBeams.Jpp[good])**2)
                            totalI = np.sum(intensity)
                            for fieldName in ['x', 'y', 'z', 'a', 'b', 'c']:
                                field = getattr(outBeams, fieldName)
                                field[0] =\
                                    np.sum(field[good] * intensity) / totalI
                                setattr(outBeams, fieldName, field)
                            outBeams.state[0] = 1
                            outBeams.E[0] = self.alignE

                    self.beamsDict[str(list(segment[3].values())[0])] =\
                        outBeams

    def glow(self, xrtglowModule):
        if QtName is not None:
            if self.blViewer is None:
                app = QApplication(sys.argv)
                rayPath = self.export_to_glow()
                self.blViewer = xrtglowModule.xrtGlow(rayPath)
                self.blViewer.setWindowTitle("xrtGlow")
                self.blViewer.show()
                sys.exit(app.exec_())
        else:
            raise ImportError("PyQt not installed!")

    def export_to_glow(self):
        if self.flow is not None:
            beamDict = {}
            rayPath = []
            outputBeamMatch = {}
            oesDict = OrderedDict()
            for segment in self.flow:
                print(segment)
                try:
                    methStr = str(segment[1])
                    oeStr = segment[0]
                    segOE = self.oesDict[oeStr][0]
                    oesDict[oeStr] = self.oesDict[oeStr]
                    if 'beam' in segment[2].keys():
                        if str(segment[2]['beam']) == 'None':
                            continue
                        tmpBeamName = segment[2]['beam']
                    if 'beamGlobal' in segment[3].keys():
                        outputBeamMatch[segment[3]['beamGlobal']] = oeStr
                    if len(re.findall('raycing.sou',
                                      str(type(segOE)).lower())):
                        gBeamName = segment[3]['beamGlobal']
                        beamDict[gBeamName] = self.beamsDict[gBeamName]
                    elif len(re.findall(('expose'), methStr)) > 0 and\
                            len(re.findall(('expose_global'), methStr)) == 0:
                        gBeam = self.oesDict[oeStr][0].expose_global(
                            self.beamsDict[tmpBeamName])
                        gBeamName = '{}toGlobal'.format(
                            segment[3]['beamLocal'])
                        beamDict[gBeamName] = gBeam
                        rayPath.append([outputBeamMatch[tmpBeamName],
                                        tmpBeamName, oeStr, gBeamName])
                    elif len(re.findall(('double'), methStr)) +\
                            len(re.findall(('multiple'), methStr)) > 0:
                        lBeam1Name = segment[3]['beamLocal1']
                        gBeam = copy.deepcopy(self.beamsDict[lBeam1Name])
                        segOE.local_to_global(gBeam)
                        g1BeamName = '{}toGlobal'.format(lBeam1Name)
                        beamDict[g1BeamName] = gBeam
                        rayPath.append([outputBeamMatch[tmpBeamName],
                                        tmpBeamName, oeStr, g1BeamName])
                        gBeamName = segment[3]['beamGlobal']
                        beamDict[gBeamName] = self.beamsDict[gBeamName]
                        rayPath.append([oeStr, g1BeamName,
                                       oeStr, gBeamName])
                    elif len(re.findall(('propagate'), methStr)) > 0:
                        lBeam1Name = segment[3]['beamLocal']
                        gBeam = copy.deepcopy(self.beamsDict[lBeam1Name])
                        segOE.local_to_global(gBeam)
                        gBeamName = '{}toGlobal'.format(lBeam1Name)
                        beamDict[gBeamName] = gBeam
                        rayPath.append([outputBeamMatch[tmpBeamName],
                                        tmpBeamName, oeStr, gBeamName])
                    else:
                        gBeamName = segment[3]['beamGlobal']
                        beamDict[gBeamName] = self.beamsDict[gBeamName]
                        rayPath.append([outputBeamMatch[tmpBeamName],
                                        tmpBeamName, oeStr, gBeamName])
                except:
                    continue

        return [rayPath, beamDict, oesDict]
