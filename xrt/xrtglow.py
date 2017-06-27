# -*- coding: utf-8 -*-
"""
Created on Tue Jun 20 15:07:53 2017

@author: Roman Chernikov
"""

from OpenGL.GL import *
from OpenGL.GLU import *
from OpenGL.GLUT import *
from OpenGL.arrays import vbo
from PyQt4 import QtGui
from PyQt4 import QtCore
import PyQt4.Qwt5 as Qwt
from PyQt4.QtOpenGL import *
import numpy as np
from functools import partial
import matplotlib as mpl
from matplotlib.backends.backend_qt4agg import FigureCanvasQTAgg as FigureCanvas
import inspect
import backends.raycing as raycing
import backends.raycing.sources as rsources


class xrtGlow(QtGui.QWidget):
    def __init__(self, arrayOfRays):
        super(xrtGlow, self).__init__()
        self.segmentsModel = QtGui.QStandardItemModel()
        self.segmentsModelRoot = self.segmentsModel.invisibleRootItem()
        self.segmentsModel.setHorizontalHeaderLabels(['Beam start',
                                                      'Beam end'])
        self.oesList = arrayOfRays[2]
        for segOE in self.oesList.keys():
            child = QtGui.QStandardItem(str(segOE))
            child.setEditable(False)
            child.setCheckable(True)
            child.setCheckState(0)
            self.segmentsModelRoot.appendRow([child])
            for segment in arrayOfRays[0]:
                if str(segment[0]) == str(segOE):
                    child1 = QtGui.QStandardItem(str(segment[1]))
                    child2 = QtGui.QStandardItem(str(segment[3]))
                    child1.setCheckable(True)
                    child1.setCheckState(2)
                    child1.setEditable(False)
                    child2.setCheckable(True)
                    child2.setCheckState(2)
                    child2.setEditable(False)
                    child.appendRow([child1, child2])

        self.fluxDataModel = QtGui.QStandardItemModel()
#        self.fluxDataModel.appendRow(QtGui.QStandardItem("auto"))
        for rfName, rfObj in inspect.getmembers(raycing):
            if rfName.startswith('get_') and\
                    rfName != "get_output":
                flItem = QtGui.QStandardItem(rfName.replace("get_", ''))
                self.fluxDataModel.appendRow(flItem)

        self.customGlWidget = xrtGlWidget(self, arrayOfRays,
                                          self.segmentsModelRoot)
        self.customGlWidget.rotationUpdated.connect(self.updateRotationFromGL)
        self.customGlWidget.scaleUpdated.connect(self.updateScaleFromGL)
        self.customGlWidget.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customGlWidget.customContextMenuRequested.connect(self.glMenu)
        self.segmentsModel.itemChanged.connect(self.updateRaysList)
#  Zoom panel
        self.zoomPanel = QtGui.QGroupBox(self)
        self.zoomPanel.setFlat(False)
#        self.zoomPanel.setTitle("Scale")
        zoomLayout = QtGui.QGridLayout()
        scaleValidator = QtGui.QDoubleValidator()
        scaleValidator.setRange(-7, 7, 7)
        for iaxis, axis in enumerate(['x', 'y', 'z']):
            axLabel = QtGui.QLabel()
            axLabel.setText(axis+' (log)')
            axLabel.objectName = "scaleLabel_" + axis
            axEdit = QtGui.QLineEdit("0.")
            axEdit.setValidator(scaleValidator)
            axSlider = Qwt.QwtSlider(
                self, QtCore.Qt.Horizontal, Qwt.QwtSlider.TopScale)
            axSlider.setRange(-7, 7, 0.01)
            axSlider.setValue(0)
            axEdit.editingFinished.connect(self.updateScaleFromQLE)
            axSlider.objectName = "scaleSlider_" + axis
            axSlider.valueChanged.connect(self.updateScale)
            zoomLayout.addWidget(axLabel, iaxis*2, 0)
            zoomLayout.addWidget(axEdit, iaxis*2, 1)
            zoomLayout.addWidget(axSlider, iaxis*2+1, 0, 1, 2)
        self.zoomPanel.setLayout(zoomLayout)

#  Rotation panel
        self.rotationPanel = QtGui.QGroupBox(self)
        self.rotationPanel.setFlat(False)
#        self.rotationPanel.setTitle("Rotation")
        rotationLayout = QtGui.QGridLayout()
        rotValidator = QtGui.QDoubleValidator()
        rotValidator.setRange(-180, 180, 9)
        for iaxis, axis in enumerate(['x', 'y', 'z']):
            axLabel = QtGui.QLabel()
            axLabel.setText(axis)
            axLabel.objectName = "rotLabel_" + axis
            axEdit = QtGui.QLineEdit("0.")
            axEdit.setValidator(rotValidator)
            axSlider = Qwt.QwtSlider(
                self, QtCore.Qt.Horizontal, Qwt.QwtSlider.TopScale)
            axSlider.setRange(-180, 180, 0.01)
            axSlider.setValue(0)
            axEdit.editingFinished.connect(self.updateRotationFromQLE)
            axSlider.objectName = "rotSlider_" + axis
            axSlider.valueChanged.connect(self.updateRotation)
            rotationLayout.addWidget(axLabel, iaxis*2, 0)
            rotationLayout.addWidget(axEdit, iaxis*2, 1)
            rotationLayout.addWidget(axSlider, iaxis*2+1, 0, 1, 2)
        self.rotationPanel.setLayout(rotationLayout)

#  Opacity panel
        self.opacityPanel = QtGui.QGroupBox(self)
        self.opacityPanel.setFlat(False)
#        self.opacityPanel.setTitle("Opacity")
        opacityLayout = QtGui.QGridLayout()
        for iaxis, axis in enumerate(
                ['Line opacity', 'Line width', 'Point opacity', 'Point size']):
            axLabel = QtGui.QLabel()
            axLabel.setText(axis)
            axLabel.objectName = "opacityLabel_" + str(iaxis)
            opacityValidator = QtGui.QDoubleValidator()
            axSlider = Qwt.QwtSlider(
                self, QtCore.Qt.Horizontal, Qwt.QwtSlider.TopScale)

            if iaxis in [0, 2]:
                axSlider.setRange(0, 1., 0.001)
                axSlider.setValue(0.1)
                axEdit = QtGui.QLineEdit("0.1")
                opacityValidator.setRange(0, 1., 5)

            else:
                axSlider.setRange(0, 20, 0.01)
                axSlider.setValue(1.)
                axEdit = QtGui.QLineEdit("1")
                opacityValidator.setRange(0, 20., 5)

            axEdit.setValidator(opacityValidator)
            axEdit.editingFinished.connect(self.updateOpacityFromQLE)
            axSlider.objectName = "opacitySlider_" + str(iaxis)
            axSlider.valueChanged.connect(self.updateOpacity)
            opacityLayout.addWidget(axLabel, iaxis*2, 0)
            opacityLayout.addWidget(axEdit, iaxis*2, 1)
            opacityLayout.addWidget(axSlider, iaxis*2+1, 0, 1, 2)
        self.opacityPanel.setLayout(opacityLayout)

#  Color panel
        self.colorPanel = QtGui.QGroupBox(self)
        self.colorPanel.setFlat(False)
#        self.colorPanel.setTitle("Color")
        colorLayout = QtGui.QGridLayout()
        self.mplFig = mpl.figure.Figure(figsize=(4, 4))
        self.mplAx = self.mplFig.add_subplot(111)

        self.drawColorMap('energy')
        self.paletteWidget = FigureCanvas(self.mplFig)
        self.paletteWidget.setSizePolicy(QtGui.QSizePolicy.Expanding,
                                         QtGui.QSizePolicy.Expanding)
        self.paletteWidget.span = mpl.widgets.RectangleSelector(
            self.mplAx, self.onselect, drawtype='box', useblit=True,
            rectprops=dict(alpha=0.4, facecolor='white'), button=1,
            interactive=True)

        colorLayout.addWidget(self.paletteWidget, 0, 0, 1, 2)

        colorCBLabel = QtGui.QLabel()
        colorCBLabel.setText('Color Axis:')

        colorCB = QtGui.QComboBox()
        colorCB.setModel(self.fluxDataModel)
        colorCB.setCurrentIndex(colorCB.findText('energy'))
        colorCB.currentIndexChanged['QString'].connect(self.changeColorAxis)
        colorLayout.addWidget(colorCBLabel, 1, 0)
        colorLayout.addWidget(colorCB, 1, 1)

        axLabel = QtGui.QLabel()
        axLabel.setText("Intensity cut-off")
        axLabel.objectName = "cutLabel_I"
        axEdit = QtGui.QLineEdit("0.01")
        cutValidator = QtGui.QDoubleValidator()
        cutValidator.setRange(0, 1, 9)
        axEdit.setValidator(cutValidator)
        axSlider = Qwt.QwtSlider(
            self, QtCore.Qt.Horizontal, Qwt.QwtSlider.TopScale)
        axSlider.setRange(0, 1, 0.001)
        axSlider.setValue(0.01)
        axEdit.editingFinished.connect(self.updateCutoffFromQLE)
        axSlider.objectName = "cutSlider_I"
        axSlider.valueChanged.connect(self.updateCutoff)
#        globalNormCB = QtGui.QCheckBox()
        colorLayout.addWidget(axLabel, 2, 0)
        colorLayout.addWidget(axEdit, 2, 1)
        colorLayout.addWidget(axSlider, 3, 0, 1, 2)
        self.colorPanel.setLayout(colorLayout)

#  Projection panel
        self.projectionPanel = QtGui.QGroupBox(self)
        self.projectionPanel.setFlat(False)
#        self.projectionPanel.setTitle("Line properties")
        projectionLayout = QtGui.QGridLayout()
        self.projVisPanel = QtGui.QGroupBox(self)
        self.projVisPanel.setFlat(False)
        self.projVisPanel.setTitle("Projection visibility")
        projVisLayout = QtGui.QGridLayout()
        self.projLinePanel = QtGui.QGroupBox(self)
        self.projLinePanel.setFlat(False)
        self.projLinePanel.setTitle("Line properties")
        projLineLayout = QtGui.QGridLayout()

        for iaxis, axis in enumerate(['Show Side (YZ)', 'Show Front (XZ)',
                                      'Show Top (XY)']):
            checkBox = QtGui.QCheckBox()
            checkBox.objectName = "visChb_" + str(iaxis)
            checkBox.setCheckState(0)
            checkBox.stateChanged.connect(self.projSelection)
            visLabel = QtGui.QLabel()
            visLabel.setText(axis)
            projVisLayout.addWidget(checkBox, iaxis*2, 0, 1, 1)
            projVisLayout.addWidget(visLabel, iaxis*2, 1, 1, 1)

        checkBox = QtGui.QCheckBox()
        checkBox.objectName = "visChb_3"
        checkBox.setCheckState(2)
        checkBox.stateChanged.connect(self.checkDrawGrid)
        visLabel = QtGui.QLabel()
        visLabel.setText('Coordinate grid')
        projVisLayout.addWidget(checkBox, 3*2, 0, 1, 1)
        projVisLayout.addWidget(visLabel, 3*2, 1, 1, 1)

        self.projVisPanel.setLayout(projVisLayout)

        for iaxis, axis in enumerate(
                ['Line opacity', 'Line width', 'Point opacity', 'Point size']):
            axLabel = QtGui.QLabel()
            axLabel.setText(axis)
            axLabel.objectName = "projectionLabel_" + str(iaxis)
            projectionValidator = QtGui.QDoubleValidator()
            axSlider = Qwt.QwtSlider(
                self, QtCore.Qt.Horizontal, Qwt.QwtSlider.TopScale)

            if iaxis in [0, 2]:
                axSlider.setRange(0, 1., 0.001)
                axSlider.setValue(0.1)
                axEdit = QtGui.QLineEdit("0.1")
                projectionValidator.setRange(0, 1., 5)

            else:
                axSlider.setRange(0, 20, 0.01)
                axSlider.setValue(1.)
                axEdit = QtGui.QLineEdit("1")
                projectionValidator.setRange(0, 20., 5)

            axEdit.setValidator(projectionValidator)
            axEdit.editingFinished.connect(self.updateProjectionOpacityFromQLE)
            axSlider.objectName = "projectionSlider_" + str(iaxis)
            axSlider.valueChanged.connect(self.updateProjectionOpacity)
            projLineLayout.addWidget(axLabel, iaxis*2, 0)
            projLineLayout.addWidget(axEdit, iaxis*2, 1)
            projLineLayout.addWidget(axSlider, iaxis*2+1, 0, 1, 2)
        self.projLinePanel.setLayout(projLineLayout)
        projectionLayout.addWidget(self.projVisPanel, 0, 0)
        projectionLayout.addWidget(self.projLinePanel, 1, 0)
        self.projectionPanel.setLayout(projectionLayout)

        self.scenePanel = QtGui.QGroupBox(self)
        self.scenePanel.setFlat(False)
#        self.zoomPanel.setTitle("Scale")
        sceneLayout = QtGui.QGridLayout()
        sceneValidator = QtGui.QDoubleValidator()
        sceneValidator.setRange(0, 10, 3)
        for iaxis, axis in enumerate(['x', 'y', 'z']):
            axLabel = QtGui.QLabel()
            axLabel.setText(axis)
            axLabel.objectName = "sceneLabel_" + axis
            axEdit = QtGui.QLineEdit("0.9")
            axEdit.setValidator(scaleValidator)
            axSlider = Qwt.QwtSlider(
                self, QtCore.Qt.Horizontal, Qwt.QwtSlider.TopScale)
            axSlider.setRange(0, 10, 0.01)
            axSlider.setValue(0.9)
            axEdit.editingFinished.connect(self.updateSceneFromQLE)
            axSlider.objectName = "sceneSlider_" + axis
            axSlider.valueChanged.connect(self.updateScene)
            sceneLayout.addWidget(axLabel, iaxis*2, 0)
            sceneLayout.addWidget(axEdit, iaxis*2, 1)
            sceneLayout.addWidget(axSlider, iaxis*2+1, 0, 1, 2)
        self.scenePanel.setLayout(sceneLayout)

#  Navigation panel
        self.navigationPanel = QtGui.QGroupBox(self)
        self.navigationPanel.setFlat(False)
        self.navigationPanel.setTitle("Navigation")
        self.navigationLayout = QtGui.QVBoxLayout()
        self.oeTree = QtGui.QTreeView()
        self.oeTree.setModel(self.segmentsModel)
        self.oeTree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.oeTree.customContextMenuRequested.connect(self.oeTreeMenu)
        self.navigationLayout.addWidget(self.oeTree)
        self.navigationPanel.setLayout(self.navigationLayout)

        mainLayout = QtGui.QHBoxLayout()
        sideLayout = QtGui.QVBoxLayout()

        tabs = QtGui.QTabWidget()
        tabs.addTab(self.zoomPanel, "Scaling")
        tabs.addTab(self.rotationPanel, "Rotation")
        tabs.addTab(self.opacityPanel, "Opacity")
        tabs.addTab(self.colorPanel, "Color")
        tabs.addTab(self.projectionPanel, "Projections")
        tabs.addTab(self.scenePanel, "Scene")
        sideLayout.addWidget(tabs)
        canvasSplitter = QtGui.QSplitter()
        canvasSplitter.setChildrenCollapsible(False)
        mainLayout.addWidget(canvasSplitter)
        sideWidget = QtGui.QWidget()
        self.setMinimumSize(750, 500)
        sideWidget.setLayout(sideLayout)
        canvasSplitter.addWidget(self.customGlWidget)
        canvasSplitter.addWidget(sideWidget)

        sideLayout.addWidget(self.navigationPanel)
        self.setLayout(mainLayout)
        self.resize(1200, 900)
        self.customGlWidget.oesList = self.oesList
        fastSave = QtGui.QShortcut(self)
        fastSave.setKey(QtCore.Qt.Key_F5)
        fastSave.activated.connect(partial(self.saveScene, '_xrtScnTmp_.npy'))
        fastLoad = QtGui.QShortcut(self)
        fastLoad.setKey(QtCore.Qt.Key_F6)
        fastLoad.activated.connect(partial(self.loadScene, '_xrtScnTmp_.npy'))

    def drawColorMap(self, axis):
        xv, yv = np.meshgrid(np.linspace(0, 1, 200),
                             np.linspace(0, 1, 200))
        xv = xv.flatten()
        yv = yv.flatten()
        self.im = self.mplAx.imshow(mpl.colors.hsv_to_rgb(np.vstack((
            xv, np.ones_like(xv)*0.85, yv)).T).reshape((200, 200, 3)),
            aspect='auto', origin='lower',
            extent=(self.customGlWidget.colorMin, self.customGlWidget.colorMax,
                    0, 1))
        self.mplAx.set_xlabel(axis)
        self.mplAx.set_ylabel('Intensity')

    def onselect(self, eclick, erelease):
        extents = list(self.paletteWidget.span.extents)
        self.customGlWidget.selColorMin = np.min([extents[0], extents[1]])
        self.customGlWidget.selColorMax = np.max([extents[0], extents[1]])
        self.customGlWidget.populateVerticesArray(self.segmentsModelRoot)
        self.customGlWidget.glDraw()

    def checkDrawGrid(self, state):
        self.customGlWidget.drawGrid = True if state > 0 else False
        self.customGlWidget.glDraw()

    def changeColorAxis(self, selAxis):
        self.customGlWidget.getColor = getattr(
            raycing, 'get_{}'.format(selAxis))
        self.customGlWidget.newColorAxis = True
        self.customGlWidget.populateVerticesArray(self.segmentsModelRoot)
        self.customGlWidget.selColorMin = self.customGlWidget.colorMin
        self.customGlWidget.selColorMin = self.customGlWidget.colorMax
        self.mplAx.set_xlabel(selAxis)
        self.im.set_extent((self.customGlWidget.colorMin,
                            self.customGlWidget.colorMax,
                            0, 1))
        self.mplFig.canvas.draw()
        self.paletteWidget.span.active_handle = None
        self.paletteWidget.span.to_draw.set_visible(False)

    def projSelection(self, state):
        cPan = self.sender()
        projIndex = int(cPan.objectName[-1])
        self.customGlWidget.projectionsVisibility[projIndex] = state
        self.customGlWidget.glDraw()

    def updateRotation(self, position):
        cPan = self.sender()
        cIndex = cPan.parent().layout().indexOf(cPan)
        cPan.parent().layout().itemAt(cIndex-1).widget().setText(str(position))
        if cPan.objectName[-1] == 'x':
            self.customGlWidget.rotVecX[0] = np.float32(position)
        elif cPan.objectName[-1] == 'y':
            self.customGlWidget.rotVecY[0] = np.float32(position)
        elif cPan.objectName[-1] == 'z':
            self.customGlWidget.rotVecZ[0] = np.float32(position)
        self.customGlWidget.glDraw()

    def updateRotationFromGL(self, rotY, rotZ):
        self.rotationPanel.layout().itemAt(5).widget().setValue(rotY)
        self.rotationPanel.layout().itemAt(8).widget().setValue(rotZ)

    def updateRotationFromQLE(self):
        cPan = self.sender()
        cIndex = cPan.parent().layout().indexOf(cPan)
        value = float(str(cPan.text()))
        cPan.parent().layout().itemAt(cIndex+1).widget().setValue(value)

    def updateScale(self, position):
        cPan = self.sender()
        cIndex = cPan.parent().layout().indexOf(cPan)
        cPan.parent().layout().itemAt(cIndex-1).widget().setText(str(position))
        if cPan.objectName[-1] == 'x':
            self.customGlWidget.scaleVec[0] =\
                np.float32(np.power(10, position))
        elif cPan.objectName[-1] == 'y':
            self.customGlWidget.scaleVec[1] =\
                np.float32(np.power(10, position))
        elif cPan.objectName[-1] == 'z':
            self.customGlWidget.scaleVec[2] =\
                np.float32(np.power(10, position))
        self.customGlWidget.glDraw()

    def updateScaleFromGL(self, scale):
        self.zoomPanel.layout().itemAt(2).widget().setValue(np.log10(scale[0]))
        self.zoomPanel.layout().itemAt(5).widget().setValue(np.log10(scale[1]))
        self.zoomPanel.layout().itemAt(8).widget().setValue(np.log10(scale[2]))

    def updateScaleFromQLE(self):
        cPan = self.sender()
        cIndex = cPan.parent().layout().indexOf(cPan)
        value = float(str(cPan.text()))
        cPan.parent().layout().itemAt(cIndex+1).widget().setValue(value)

    def updateRaysList(self, item):
        self.customGlWidget.populateVerticesArray(self.segmentsModelRoot)
        self.customGlWidget.glDraw()

    def oeTreeMenu(self, position):
        indexes = self.oeTree.selectedIndexes()
        level = 100
        if len(indexes) > 0:
            level = 0
            index = indexes[0]
            selectedItem = self.segmentsModel.itemFromIndex(index)
            while index.parent().isValid():
                index = index.parent()
                level += 1
        if level == 0:
            menu = QtGui.QMenu()
            menu.addAction('Center here',
                           partial(self.centerEl, str(selectedItem.text())))
        else:
            pass

        menu.exec_(self.oeTree.viewport().mapToGlobal(position))

    def updateScene(self, position):
        cPan = self.sender()
        cIndex = cPan.parent().layout().indexOf(cPan)
        cPan.parent().layout().itemAt(cIndex-1).widget().setText(str(position))
        aIndex = int(((cIndex + 1) / 3) - 1)
        self.customGlWidget.aPos[aIndex] = np.float32(position)
        self.customGlWidget.glDraw()

    def updateSceneFromQLE(self):
        cPan = self.sender()
        cIndex = cPan.parent().layout().indexOf(cPan)
        value = float(str(cPan.text()))
        cPan.parent().layout().itemAt(cIndex+1).widget().setValue(value)

    def glMenu(self, position):
        menu = QtGui.QMenu()
        for actText, actFunc in zip(['Export to image', 'Save scene geometry',
                                     'Load scene geometry'],
                                    [self.exportToImage, self.saveSceneDialog,
                                     self.loadSceneDialog]):
            mAction = QtGui.QAction(self)
            mAction.setText(actText)
            mAction.triggered.connect(actFunc)
            menu.addAction(mAction)
        menu.exec_(self.customGlWidget.mapToGlobal(position))

    def exportToImage(self):
        saveDialog = QtGui.QFileDialog()
        saveDialog.setFileMode(QtGui.QFileDialog.AnyFile)
        saveDialog.setAcceptMode(QtGui.QFileDialog.AcceptSave)
        saveDialog.setNameFilter("BMP files (*.bmp);;JPG files (*.jpg);;JPG files (*.jpg);;JPEG files (*.jpeg);;PNG files (*.png);;TIFF files (*.tif)")  # analysis:ignore
        saveDialog.selectNameFilter("PNG files (*.png)")
        if (saveDialog.exec_()):
            image = self.customGlWidget.grabFrameBuffer(withAlpha=True)
            filename = saveDialog.selectedFiles()[0]
            extension = str(saveDialog.selectedNameFilter())[-5:-1].strip('.')
            if not filename.endswith(extension):
                filename = "{0}.{1}".format(filename, extension)
#            print filename
            image.save(filename)

    def saveSceneDialog(self):
        saveDialog = QtGui.QFileDialog()
        saveDialog.setFileMode(QtGui.QFileDialog.AnyFile)
        saveDialog.setAcceptMode(QtGui.QFileDialog.AcceptSave)
        saveDialog.setNameFilter("Numpy files (*.npy)")  # analysis:ignore
        if (saveDialog.exec_()):
            filename = saveDialog.selectedFiles()[0]
            extension = 'npy'
            if not filename.endswith(extension):
                filename = "{0}.{1}".format(filename, extension)
            self.saveScene(filename)

    def loadSceneDialog(self):
        loadDialog = QtGui.QFileDialog()
        loadDialog.setFileMode(QtGui.QFileDialog.AnyFile)
        loadDialog.setAcceptMode(QtGui.QFileDialog.AcceptOpen)
        loadDialog.setNameFilter("Numpy files (*.npy)")  # analysis:ignore
        if (loadDialog.exec_()):
            filename = loadDialog.selectedFiles()[0]
            extension = 'npy'
            if not filename.endswith(extension):
                filename = "{0}.{1}".format(filename, extension)
            self.loadScene(filename)

    def saveScene(self, filename):
        params = dict()
        for param in ['aspect', 'cameraAngle', 'projectionsVisibility',
                      'lineOpacity', 'lineWidth', 'pointOpacity', 'pointSize',
                      'lineProjectionOpacity', 'lineProjectionWidth',
                      'pointProjectionOpacity', 'pointProjectionSize',
                      'coordOffset', 'cutoffI', 'drawGrid', 'aPos', 'scaleVec',
                      'tVec', 'cameraPos', 'rotVecX', 'rotVecY', 'rotVecZ',
                      'visibleAxes', 'signs', 'selColorMin', 'selColorMax',
                      'colorMin', 'colorMax']:
            params[param] = getattr(self.customGlWidget, param)
        params['size'] = self.geometry()
        try:
            np.save(filename, params)
        except:
            print('Error saving file')
            return
        print('Saved scene to {}'.format(filename))

    def loadScene(self, filename):
        try:
            params = np.load(filename).item()
        except:
            print('Error loading file')
            return

        for param in ['aspect', 'cameraAngle', 'projectionsVisibility',
                      'lineOpacity', 'lineWidth', 'pointOpacity', 'pointSize',
                      'lineProjectionOpacity', 'lineProjectionWidth',
                      'pointProjectionOpacity', 'pointProjectionSize',
                      'coordOffset', 'cutoffI', 'drawGrid', 'aPos', 'scaleVec',
                      'tVec', 'cameraPos', 'rotVecX', 'rotVecY', 'rotVecZ',
                      'visibleAxes', 'signs', 'selColorMin', 'selColorMax',
                      'colorMin', 'colorMax']:
            setattr(self.customGlWidget, param, params[param])
        self.setGeometry(params['size'])

        for axis in range(3):
            self.zoomPanel.layout().itemAt((axis+1)*3-1).widget().setValue(
                np.log10(self.customGlWidget.scaleVec[axis]))

        self.rotationPanel.layout().itemAt(2).widget().setValue(
            self.customGlWidget.rotVecX[0])
        self.rotationPanel.layout().itemAt(5).widget().setValue(
            self.customGlWidget.rotVecY[0])
        self.rotationPanel.layout().itemAt(8).widget().setValue(
            self.customGlWidget.rotVecZ[0])

        self.opacityPanel.layout().itemAt(2).widget().setValue(
            self.customGlWidget.lineOpacity)
        self.opacityPanel.layout().itemAt(5).widget().setValue(
            self.customGlWidget.lineWidth)
        self.opacityPanel.layout().itemAt(8).widget().setValue(
            self.customGlWidget.pointOpacity)
        self.opacityPanel.layout().itemAt(11).widget().setValue(
            self.customGlWidget.pointSize)

        for axis in range(3):
            self.projVisPanel.layout().itemAt(axis*2).widget().setCheckState(
                int(self.customGlWidget.projectionsVisibility[axis]))

        self.projVisPanel.layout().itemAt(6).widget().setCheckState(
                        int(self.customGlWidget.drawGrid)*2)

        self.projLinePanel.layout().itemAt(2).widget().setValue(
            self.customGlWidget.lineProjectionOpacity)
        self.projLinePanel.layout().itemAt(5).widget().setValue(
            self.customGlWidget.lineProjectionWidth)
        self.projLinePanel.layout().itemAt(8).widget().setValue(
            self.customGlWidget.pointProjectionOpacity)
        self.projLinePanel.layout().itemAt(11).widget().setValue(
            self.customGlWidget.pointProjectionSize)

        for axis in range(3):
            self.scenePanel.layout().itemAt((axis+1)*3-1).widget(
                ).setValue(self.customGlWidget.aPos[axis])

        self.customGlWidget.newColorAxis = False
        self.customGlWidget.populateVerticesArray(self.segmentsModelRoot)
        self.customGlWidget.glDraw()
        print('Loaded scene from {}'.format(filename))

    def centerEl(self, oeName):
        self.customGlWidget.coordOffset = list(self.oesList[oeName].center)
        self.customGlWidget.tVec = np.float32([0, 0, 0])
        self.customGlWidget.populateVerticesArray(self.segmentsModelRoot)
        self.customGlWidget.glDraw()

    def updateCutoff(self, position):
        cPan = self.sender()
        cIndex = cPan.parent().layout().indexOf(cPan)
        cPan.parent().layout().itemAt(cIndex-1).widget().setText(str(position))
        extents = list(self.paletteWidget.span.extents)
        self.customGlWidget.cutoffI = np.float32(position)
        self.customGlWidget.populateVerticesArray(self.segmentsModelRoot)
        newExtents = (extents[0], extents[1],
                      self.customGlWidget.cutoffI, extents[3])
        self.paletteWidget.span.extents = newExtents
        self.customGlWidget.glDraw()

    def updateCutoffFromQLE(self):
        cPan = self.sender()
        cIndex = cPan.parent().layout().indexOf(cPan)
        value = float(str(cPan.text()))
        cPan.parent().layout().itemAt(cIndex+1).widget().setValue(value)
        self.customGlWidget.glDraw()

    def updateOpacityFromQLE(self):
        cPan = self.sender()
        cIndex = cPan.parent().layout().indexOf(cPan)
        if cPan.objectName[-1] == '0':
            value = float(str(cPan.text()))
        else:
            value = int(str(cPan.text()))
        cPan.parent().layout().itemAt(cIndex+1).widget().setValue(value)
        self.customGlWidget.glDraw()

    def updateOpacity(self, position):
        cPan = self.sender()
        cIndex = cPan.parent().layout().indexOf(cPan)
        cPan.parent().layout().itemAt(cIndex-1).widget().setText(str(position))
        objNameType = cPan.objectName[-1]
        if objNameType == '0':
            self.customGlWidget.lineOpacity = np.float32(position)
        elif objNameType == '1':
            self.customGlWidget.lineWidth = np.float32(position)
        elif objNameType == '2':
            self.customGlWidget.pointOpacity = np.float32(position)
        elif objNameType == '3':
            self.customGlWidget.pointSize = np.float32(position)
        self.customGlWidget.glDraw()

    def updateProjectionOpacityFromQLE(self):
        cPan = self.sender()
        cIndex = cPan.parent().layout().indexOf(cPan)
        if cPan.objectName[-1] == '0':
            value = float(str(cPan.text()))
        else:
            value = int(str(cPan.text()))
        cPan.parent().layout().itemAt(cIndex+1).widget().setValue(value)
        self.customGlWidget.glDraw()

    def updateProjectionOpacity(self, position):
        cPan = self.sender()
        cIndex = cPan.parent().layout().indexOf(cPan)
        cPan.parent().layout().itemAt(cIndex-1).widget().setText(str(position))
        objNameType = cPan.objectName[-1]
        if objNameType == '0':
            self.customGlWidget.lineProjectionOpacity = np.float32(position)
        elif objNameType == '1':
            self.customGlWidget.lineProjectionWidth = np.float32(position)
        elif objNameType == '2':
            self.customGlWidget.pointProjectionOpacity = np.float32(position)
        elif objNameType == '3':
            self.customGlWidget.pointProjectionSize = np.float32(position)
        self.customGlWidget.glDraw()


class xrtGlWidget(QGLWidget):
    rotationUpdated = QtCore.pyqtSignal(np.float32, np.float32)
    scaleUpdated = QtCore.pyqtSignal(np.ndarray)

    def __init__(self, parent, arrayOfRays, modelRoot):
        QGLWidget.__init__(self, parent)
        self.setMinimumSize(500, 500)
        self.aspect = 1.
        self.cameraAngle = 60
        self.setMouseTracking(True)
        self.surfCPOrder = 4
        self.oesToPlot = []
        self.tiles = [10, 1]
#        self.eMin = arrayOfRays[2][0].eMin
#        self.eMax = arrayOfRays[2][0].eMax
        self.arrayOfRays = arrayOfRays
        self.beamsDict = arrayOfRays[1]

        self.projectionsVisibility = [0, 0, 0]
        self.lineOpacity = 0.1
        self.lineWidth = 1
        self.pointOpacity = 0.1
        self.pointSize = 1

        self.lineProjectionOpacity = 0.1
        self.lineProjectionWidth = 1
        self.pointProjectionOpacity = 0.1
        self.pointProjectionSize = 1

        self.coordOffset = [0., 0., 0.]
        self.aaEnabled = False
        self.cutoffI = 0.01
        self.getColor = raycing.get_energy
#        self.selColorMax = 1e20
#        self.selColorMin = -1e20
        self.newColorAxis = True
        self.populateVerticesArray(modelRoot)

        maxC = np.max(self.verticesArray, axis=0)
        minC = np.min(self.verticesArray, axis=0)
        self.maxLen = np.max(maxC - minC)

        self.drawGrid = True
        self.aPos = [0.9, 0.9, 0.9]
        self.prevMPos = [0, 0]
        self.prevWC = np.float32([0, 0, 0])
        self.scaleVec = np.array([1., 1., 1.])
        self.tVec = np.array([0., 0., 0.])
        self.cameraTarget = [0., 0., 0.]
        self.cameraPos = np.float32([3.5, 0., 0.])
        self.rotVecX = np.float32([0., 1., 0., 0.])
        self.rotVecY = np.float32([0., 0., 1., 0.])
        self.rotVecZ = np.float32([0., 0., 0., 1.])
        pModelT = np.identity(4)
        self.visibleAxes = np.argmax(np.abs(pModelT), axis=1)
        self.signs = np.ones_like(pModelT)
        self.oesList = None
        self.glDraw()

    def setPointSize(self, pSize):
        self.pointSize = pSize
        self.glDraw()

    def setLineWidth(self, lWidth):
        self.lineWidth = lWidth
        self.glDraw()

    def populateVerticesArray(self, segmentsModelRoot):
        self.verticesArray = None
        self.oesToPlot = []
        self.footprints = dict()
        colors = None
        alpha = None
        if self.newColorAxis:
            self.colorMax = -1e20
            self.colorMin = 1e20
        for ioe in range(segmentsModelRoot.rowCount()):
            ioeItem = segmentsModelRoot.child(ioe, 0)
            if ioeItem.checkState() == 2:
                self.oesToPlot.append(str(ioeItem.text()))
                self.footprints[str(ioeItem.text())] = None
            if ioeItem.hasChildren():
                for isegment in range(ioeItem.rowCount()):
                    segmentItem0 = ioeItem.child(isegment, 0)
                    segmentItem1 = ioeItem.child(isegment, 1)
#                    beams = str(segmentItem.text())
                    startBeam = self.beamsDict[str(segmentItem0.text())]
                    good = startBeam.state > 0

                    self.colorMax = max(np.max(self.getColor(startBeam)[good]),
                                        self.colorMax)
                    self.colorMin = min(np.min(self.getColor(startBeam)[good]),
                                        self.colorMin)
                    if self.newColorAxis:
                        self.selColorMin = self.colorMin
                        self.selColorMax = self.colorMax

                    if segmentItem0.checkState() == 2 and\
                            segmentItem1.checkState() == 2:

                        endBeam = self.beamsDict[str(segmentItem1.text())]
                        intensity = np.abs(startBeam.Jss**2+startBeam.Jpp**2)
                        intensity /= np.max(intensity)

                        good = np.logical_and(startBeam.state > 0,
                                              intensity >= self.cutoffI)
                        goodC = np.logical_and(startBeam.E <= self.selColorMax,
                                               startBeam.E >= self.selColorMin)

                        good = np.logical_and(good, goodC)

                        alpha = np.repeat(intensity[good], 2).T if\
                            alpha is None else np.concatenate(
                                (alpha.T, np.repeat(intensity[good], 2).T))

                        colors = np.repeat(np.array(self.getColor(
                            startBeam)[good]), 2).T if\
                            colors is None else np.concatenate(
                                (colors.T,
                                 np.repeat(np.array(self.getColor(
                                     startBeam)[good]), 2).T))

                        vertices = np.array(
                            [startBeam.x[good] - self.coordOffset[0],
                             endBeam.x[good] - self.coordOffset[0]]).flatten(
                                 'F')
                        vertices = np.vstack((vertices, np.array(
                            [startBeam.y[good] - self.coordOffset[1],
                             endBeam.y[good] - self.coordOffset[1]]).flatten(
                                 'F')))
                        vertices = np.vstack((vertices, np.array(
                            [startBeam.z[good] - self.coordOffset[2],
                             endBeam.z[good] - self.coordOffset[2]]).flatten(
                                 'F')))

                        self.verticesArray = vertices.T if\
                            self.verticesArray is None else\
                            np.vstack((self.verticesArray, vertices.T))

        colors = (colors - self.colorMin) / (self.colorMax - self.colorMin)
        colors = np.dstack((colors,
                            np.ones_like(alpha)*0.85,
                            alpha))

        colorsRGB = np.squeeze(mpl.colors.hsv_to_rgb(colors))
        alphaColor = np.array([alpha]).T * self.lineOpacity
        self.allColor = np.float32(np.hstack([colorsRGB, alphaColor]))
        self.newColorAxis = False

    def modelToWorld(self, coords, dimension=None):
        if dimension is None:
            return np.float32(((coords + self.tVec) * self.scaleVec) /
                              self.maxLen)
        else:
            return np.float32(((coords[dimension] + self.tVec[dimension]) *
                              self.scaleVec[dimension]) / self.maxLen)

    def paintGL(self):
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(self.cameraAngle, self.aspect, 0.001, 1000)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        gluLookAt(self.cameraPos[0], self.cameraPos[1], self.cameraPos[2],
                  self.cameraTarget[0], self.cameraTarget[1],
                  self.cameraTarget[2],
                  0.0, 0.0, 1.0)
        glMatrixMode(GL_MODELVIEW)

        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_POINT_SMOOTH)

        if self.aaEnabled:
            glEnable(GL_LINE_SMOOTH)
            glHint(GL_LINE_SMOOTH_HINT, GL_NICEST)
        glEnableClientState(GL_VERTEX_ARRAY)
        glEnableClientState(GL_COLOR_ARRAY)
# Coordinate box
        glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)

        glLoadIdentity()
        glRotatef(*self.rotVecX)
        glRotatef(*self.rotVecY)
        glRotatef(*self.rotVecZ)
        axPosModifier = np.ones(3)

        for dim in range(3):
            for iAx in range(3):
                axPosModifier[iAx] = (self.signs[0][iAx] if
                                      self.signs[0][iAx] != 0 else 1)
            if self.projectionsVisibility[dim] > 0:
                projection = self.modelToWorld(np.copy(self.verticesArray))
                projection[:, dim] = -self.aPos[dim] * axPosModifier[dim]
                vertexArray = vbo.VBO(projection)
                vertexArray.bind()
                glVertexPointerf(vertexArray)

                if self.lineProjectionWidth > 0:
                    self.allColor[:, 3] = np.float32(
                        self.lineProjectionOpacity)
                    colorArray = vbo.VBO(self.allColor)
                    colorArray.bind()
                    glColorPointerf(colorArray)
                    glLineWidth(self.lineProjectionWidth)
                    glDrawArrays(GL_LINES, 0, len(self.verticesArray))
                    colorArray.unbind()

                if self.pointProjectionSize > 0:
                    self.allColor[:, 3] = np.float32(
                        self.pointProjectionOpacity)
                    colorArray = vbo.VBO(self.allColor)
                    colorArray.bind()
                    glColorPointerf(colorArray)
                    glPointSize(self.pointProjectionSize)
                    glDrawArrays(GL_POINTS, 0, len(self.verticesArray))

                vertexArray.unbind()

        if self.drawGrid:
            glLoadIdentity()
            glRotatef(*self.rotVecX)
            glRotatef(*self.rotVecY)
            glRotatef(*self.rotVecZ)
            back = np.array([[-self.aPos[0], self.aPos[1], -self.aPos[2]],
                             [-self.aPos[0], self.aPos[1], self.aPos[2]],
                             [-self.aPos[0], -self.aPos[1], self.aPos[2]],
                             [-self.aPos[0], -self.aPos[1], -self.aPos[2]]])

            side = np.array([[self.aPos[0], -self.aPos[1], -self.aPos[2]],
                             [-self.aPos[0], -self.aPos[1], -self.aPos[2]],
                             [-self.aPos[0], -self.aPos[1], self.aPos[2]],
                             [self.aPos[0], -self.aPos[1], self.aPos[2]]])

            bottom = np.array([[self.aPos[0], -self.aPos[1], -self.aPos[2]],
                               [self.aPos[0], self.aPos[1], -self.aPos[2]],
                               [-self.aPos[0], self.aPos[1], -self.aPos[2]],
                               [-self.aPos[0], -self.aPos[1], -self.aPos[2]]])

#  Calculating regular grids in world coordinates
            limits = np.array([-1, 1])[:, np.newaxis] * np.array(self.aPos)
            allLimits = limits * self.maxLen / self.scaleVec - self.tVec
            axGrids = []

            gridLabels = None
            precisionLabels = None

            for iAx in range(3):
                dx = np.abs(allLimits[:, iAx][0] - allLimits[:, iAx][1])*0.15
                decimalX = int(np.abs(np.modf(np.log10(dx))[1])) + 1 if\
                    dx < 10 else 0
                dx = np.round(dx, decimalX)
                gridX = np.arange(np.round(allLimits[:, iAx][0], decimalX),
                                  allLimits[:, iAx][1], dx)
                gridX = gridX if gridX[0] >= allLimits[:, iAx][0] else\
                    gridX[1:]
                gridLabels = np.concatenate((
                    gridLabels, gridX + self.coordOffset[iAx])) if gridLabels\
                    is not None else gridX + self.coordOffset[iAx]
                precisionLabels = np.concatenate((
                    precisionLabels,
                    np.ones_like(gridX)*decimalX)) if precisionLabels\
                    is not None else np.ones_like(gridX)*decimalX
                axGrids.extend([gridX])

            back[:, 0] *= axPosModifier[0]
            side[:, 1] *= axPosModifier[1]
            bottom[:, 2] *= axPosModifier[2]

            xAxis = np.vstack(
                (self.modelToWorld(axGrids, 0),
                 np.ones(len(axGrids[0]))*self.aPos[1]*axPosModifier[1],
                 np.ones(len(axGrids[0]))*-self.aPos[2]*axPosModifier[2]))
            yAxis = np.vstack(
                (np.ones(len(axGrids[1]))*self.aPos[0]*axPosModifier[0],
                 self.modelToWorld(axGrids, 1),
                 np.ones(len(axGrids[1]))*-self.aPos[2]*axPosModifier[2]))
            zAxis = np.vstack(
                (np.ones(len(axGrids[2]))*-self.aPos[0]*axPosModifier[0],
                 np.ones(len(axGrids[2]))*self.aPos[1]*axPosModifier[1],
                 self.modelToWorld(axGrids, 2)))

            xAxisB = np.vstack(
                (self.modelToWorld(axGrids, 0),
                 np.ones(len(axGrids[0]))*-self.aPos[1]*axPosModifier[1],
                 np.ones(len(axGrids[0]))*-self.aPos[2]*axPosModifier[2]))
            yAxisB = np.vstack(
                (np.ones(len(axGrids[1]))*-self.aPos[0]*axPosModifier[0],
                 self.modelToWorld(axGrids, 1),
                 np.ones(len(axGrids[1]))*-self.aPos[2]*axPosModifier[2]))
            zAxisB = np.vstack(
                (np.ones(len(axGrids[2]))*-self.aPos[0]*axPosModifier[0],
                 np.ones(len(axGrids[2]))*-self.aPos[1]*axPosModifier[1],
                 self.modelToWorld(axGrids, 2)))

            xAxisC = np.vstack(
                (self.modelToWorld(axGrids, 0),
                 np.ones(len(axGrids[0]))*-self.aPos[1]*axPosModifier[1],
                 np.ones(len(axGrids[0]))*self.aPos[2]*axPosModifier[2]))
            yAxisC = np.vstack(
                (np.ones(len(axGrids[1]))*-self.aPos[0]*axPosModifier[0],
                 self.modelToWorld(axGrids, 1),
                 np.ones(len(axGrids[1]))*self.aPos[2]*axPosModifier[2]))
            zAxisC = np.vstack(
                (np.ones(len(axGrids[2]))*self.aPos[0]*axPosModifier[0],
                 np.ones(len(axGrids[2]))*-self.aPos[1]*axPosModifier[1],
                 self.modelToWorld(axGrids, 2)))

            xLines = np.vstack(
                (xAxis, xAxisB, xAxisB, xAxisC)).T.flatten().reshape(
                4*xAxis.shape[1], 3)
            yLines = np.vstack(
                (yAxis, yAxisB, yAxisB, yAxisC)).T.flatten().reshape(
                4*yAxis.shape[1], 3)
            zLines = np.vstack(
                (zAxis, zAxisB, zAxisB, zAxisC)).T.flatten().reshape(
                4*zAxis.shape[1], 3)

            axTicks = np.vstack((xAxis.T, yAxis.T, zAxisC.T))
            axGrid = np.vstack((xLines, yLines, zLines))

            for tick, tText, pcs in zip(axTicks, gridLabels, precisionLabels):
                glRasterPos3f(*tick)
                for symbol in "   {0:.{1}f}".format(tText, int(pcs)):
                    glutBitmapCharacter(GLUT_BITMAP_HELVETICA_12, ord(symbol))

            gridColor = np.ones((len(axGrid), 4)) * 0.25
            gridArray = vbo.VBO(np.float32(axGrid))
            gridArray.bind()
            glVertexPointerf(gridArray)
            gridColorArray = vbo.VBO(np.float32(gridColor))
            gridColorArray.bind()
            glColorPointerf(gridColorArray)
            glLineWidth(1.)
            glDrawArrays(GL_LINES, 0, len(gridArray))
            gridArray.unbind()
            gridColorArray.unbind()

            grid = np.vstack((back, side, bottom))

            gridColor = np.ones((len(grid), 4)) * 0.5
            gridArray = vbo.VBO(np.float32(grid))
            gridArray.bind()
            glVertexPointerf(gridArray)
            gridColorArray = vbo.VBO(np.float32(gridColor))
            gridColorArray.bind()
            glColorPointerf(gridColorArray)
            glLineWidth(2.)
            glDrawArrays(GL_QUADS, 0, len(gridArray))
            gridArray.unbind()
            gridColorArray.unbind()

        glLoadIdentity()
        glRotatef(*self.rotVecX)
        glRotatef(*self.rotVecY)
        glRotatef(*self.rotVecZ)

        vertexArray = vbo.VBO(self.modelToWorld(self.verticesArray))
        vertexArray.bind()
        glVertexPointerf(vertexArray)

        if self.oesList is not None:
            glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
            glEnable(GL_DEPTH_TEST)
            glShadeModel(GL_SMOOTH)
            glEnable(GL_LIGHTING)
            glEnable(GL_LIGHT0)
            glLightModeli(GL_LIGHT_MODEL_TWO_SIDE, 0)
            glLightfv(GL_LIGHT0, GL_POSITION, [2, 0, 10, 1])
            lA = 0.8
            glLightfv(GL_LIGHT0, GL_AMBIENT, [lA, lA, lA, 1])
            lD = 1.0
            glLightfv(GL_LIGHT0, GL_DIFFUSE, [lD, lD, lD, 1])
            lS = 1.0
            glLightfv(GL_LIGHT0, GL_SPECULAR, [lS, lS, lS, 1])
            glMaterialfv(GL_FRONT_AND_BACK, GL_AMBIENT, [0.5, 0.5, 0.5, 0.8])
            glMaterialfv(GL_FRONT_AND_BACK, GL_DIFFUSE, [0.7, 0.7, 0.7, 0.8])
            glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, [0.8, 0.8, 0.8, 0.8])
            glMaterialf(GL_FRONT, GL_SHININESS, 80)
            glEnable(GL_MAP2_VERTEX_3)
            glEnable(GL_AUTO_NORMAL)
#            print self.surfCP.shape
#            print len(self.oesToPlot)
            for oeString in self.oesToPlot:
                oeToPlot = self.oesList[oeString]
                if hasattr(oeToPlot, 'limOptX'):  # OE
                    xLimits = list(oeToPlot.limOptX) if\
                        oeToPlot.limOptX is not None else oeToPlot.limPhysX
                    if np.any(np.abs(xLimits) == raycing.maxHalfSizeOfOE):
                        if oeToPlot.footprint is not None:
                            xLimits = oeToPlot.footprint[0][:, 0]
                    yLimits = list(oeToPlot.limOptY) if\
                        oeToPlot.limOptY is not None else oeToPlot.limPhysY
                    if np.any(np.abs(yLimits) == raycing.maxHalfSizeOfOE):
                        if oeToPlot.footprint is not None:
                            yLimits = oeToPlot.footprint[0][:, 1]
#                elif hasattr(oeToPlot, 'opening'):  # aperture
#                    pass

                    for i in range(self.tiles[0]):
                        deltaX = (xLimits[1] - xLimits[0]) /\
                            float(self.tiles[0])
                        xGridOe = np.linspace(xLimits[0] + i*deltaX,
                                              xLimits[0] + (i+1)*deltaX,
                                              self.surfCPOrder)
                        for k in range(self.tiles[1]):
                            deltaY = (yLimits[1] - yLimits[0]) /\
                                float(self.tiles[1])
                            yGridOe = np.linspace(yLimits[0] + k*deltaY,
                                                  yLimits[0] + (k+1)*deltaY,
                                                  self.surfCPOrder)
                            xv, yv = np.meshgrid(xGridOe, yGridOe)
                            xv = xv.flatten()
                            yv = yv.flatten()

                            zv = oeToPlot.local_z(xv, yv)

                            gbp = rsources.Beam(nrays=len(xv))
                            gbp.x = xv
                            gbp.y = yv
                            gbp.z = zv
                            oeToPlot.local_to_global(gbp)
                            surfCP = np.vstack((gbp.x, gbp.y, gbp.z)).T -\
                                self.coordOffset
                            glMap2f(GL_MAP2_VERTEX_3, 0, 1, 0, 1,
                                    self.modelToWorld(surfCP.reshape(
                                        self.surfCPOrder,
                                        self.surfCPOrder, 3)))
                            glMapGrid2f(self.surfCPOrder, 0.0, 1.0,
                                        self.surfCPOrder, 0.0, 1.0)
                            glEvalMesh2(GL_FILL, 0, self.surfCPOrder,
                                        0, self.surfCPOrder)
#                except:
#                    pass

            glDisable(GL_MAP2_VERTEX_3)
            glDisable(GL_AUTO_NORMAL)
            glDisable(GL_DEPTH_TEST)
#            glShadeModel( GL_SMOOTH )
            glDisable(GL_LIGHTING)
            glDisable(GL_LIGHT0)

        glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)

        if self.lineWidth > 0:
            self.allColor[:, 3] = np.float32(self.lineOpacity)
            colorArray = vbo.VBO(self.allColor)
            colorArray.bind()
            glColorPointerf(colorArray)
            glLineWidth(self.lineWidth)
            glDrawArrays(GL_LINES, 0, len(self.verticesArray))
#            vertexArray.unbind()
            colorArray.unbind()

        if self.pointSize > 0:
            self.allColor[:, 3] = np.float32(self.pointOpacity)
            colorArray = vbo.VBO(self.allColor)
            colorArray.bind()
            glColorPointerf(colorArray)
            glPointSize(self.pointSize)
            glDrawArrays(GL_POINTS, 0, len(self.verticesArray))
            colorArray.unbind()

        vertexArray.unbind()
#        print self.verticesArray.shape

        glDisableClientState(GL_VERTEX_ARRAY)
        glDisableClientState(GL_COLOR_ARRAY)
#        glDisable(GL_BLEND)

        glFlush()

    def initializeGL(self):
        glEnable(GL_MULTISAMPLE)
        glClearColor(0.0, 0.0, 0.0, 1.0)
        glViewport(0, 0, 900, 900)
        glutInit()

    def resizeGL(self, widthInPixels, heightInPixels):
        glViewport(0, 0, widthInPixels, heightInPixels)
        self.aspect = np.float32(widthInPixels)/np.float32(heightInPixels)

    def mouseMoveEvent(self, mouseEvent):
        if mouseEvent.buttons() == QtCore.Qt.LeftButton:
            glLoadIdentity()
            glRotatef(*self.rotVecX)
            glRotatef(*self.rotVecY)
            glRotatef(*self.rotVecZ)
            pModelT = np.array(glGetDoublev(GL_TRANSPOSE_MODELVIEW_MATRIX))
            self.visibleAxes = np.argmax(np.abs(pModelT), axis=1)
            self.signs = np.sign(pModelT)

            if mouseEvent.modifiers() == QtCore.Qt.NoModifier:
                self.rotVecY[0] += np.float32(
                    (mouseEvent.y() - self.prevMPos[1])*36./90.)
                self.rotVecZ[0] += np.float32(
                    (mouseEvent.x() - self.prevMPos[0])*36./90.)
                self.rotationUpdated.emit(self.rotVecY[0], self.rotVecZ[0])
            elif mouseEvent.modifiers() == QtCore.Qt.ShiftModifier:
                pProjectionT = glGetDoublev(GL_TRANSPOSE_PROJECTION_MATRIX)
                pView = glGetIntegerv(GL_VIEWPORT)
                pScale = np.float32(pProjectionT[2][3]*1.25)
                self.tVec[self.visibleAxes[1]] +=\
                    self.signs[1][self.visibleAxes[1]] * pScale *\
                    (mouseEvent.x() - self.prevMPos[0]) / pView[2] /\
                    self.scaleVec[self.visibleAxes[1]] * self.maxLen
                self.tVec[self.visibleAxes[2]] -=\
                    self.signs[2][self.visibleAxes[2]] * pScale *\
                    (mouseEvent.y() - self.prevMPos[1]) / pView[3] /\
                    self.scaleVec[self.visibleAxes[2]] * self.maxLen
#                self.verticesArray[:, self.visibleAxes[1]] += \
#                    self.signs[1][self.visibleAxes[1]] * pScale *\
#                    (mouseEvent.x() - self.prevMPos[0]) / pView[2] /\
#                    self.scaleVec[self.visibleAxes[1]] * self.maxLen
#                self.verticesArray[:, self.visibleAxes[2]] -= \
#                    self.signs[2][self.visibleAxes[2]] * pScale *\
#                    (mouseEvent.y() - self.prevMPos[1]) / pView[3] /\
#                    self.scaleVec[self.visibleAxes[2]] * self.maxLen

            elif mouseEvent.modifiers() == QtCore.Qt.AltModifier:
                pProjectionT = glGetDoublev(GL_TRANSPOSE_PROJECTION_MATRIX)
                pView = glGetIntegerv(GL_VIEWPORT)
                pScale = np.float32(pProjectionT[2][3]*1.25)
#                self.verticesArray[:, self.visibleAxes[0]] -= \
#                    self.signs[2][self.visibleAxes[0]] * pScale *\
#                    (mouseEvent.y() - self.prevMPos[1]) / pView[3] /\
#                    self.scaleVec[self.visibleAxes[0]] * self.maxLen
                self.tVec[self.visibleAxes[0]] +=\
                    self.signs[0][self.visibleAxes[0]] * pScale *\
                    (mouseEvent.y() - self.prevMPos[1]) / pView[3] /\
                    self.scaleVec[self.visibleAxes[0]] * self.maxLen

        self.glDraw()
        self.prevMPos[0] = mouseEvent.x()
        self.prevMPos[1] = mouseEvent.y()

    def wheelEvent(self, wEvent):
        ctrlOn = (wEvent.modifiers() == QtCore.Qt.ControlModifier)
        if wEvent.delta() > 0:
            if ctrlOn:
                self.cameraPos *= 0.9
            else:
                self.scaleVec *= 1.1
        else:
            if ctrlOn:
                self.cameraPos *= 1.1
            else:
                self.scaleVec *= 0.9
        if not ctrlOn:
            self.scaleUpdated.emit(self.scaleVec)
        self.glDraw()
