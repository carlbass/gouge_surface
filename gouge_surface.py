# Author- Carl Bass
# Description- make surface gouges of specified radius tapering at both ends

import adsk.core, adsk.fusion, adsk.cam, traceback
import os

# Global list to keep all event handlers in scope.
handlers = []

# global variables available in all functions
app = adsk.core.Application.get()
ui  = app.userInterface

# global variables because I can't find a better way to pass this info around -- would be nice if fusion api had some cleaner way to do this
debug = True
gouge_surface = True
tool_diameter = 0.25
tool_radius = tool_diameter * 0.5

def run(context):
    
    try:

        # Find where the python file lives and look for the icons in the ./resources folder
        python_file_folder = os.path.dirname(os.path.realpath(__file__))
        resource_folder = os.path.join (python_file_folder, 'resources')
        resource_folder =''

        # Get the CommandDefinitions collection so we can add a command
        command_definitions = ui.commandDefinitions
        
        tooltip = 'Gouge the surface along sketch curves'

        # Create a button command definition.
        gouge_button = command_definitions.addButtonDefinition('gouge_surface', 'Gouge surface', tooltip, resource_folder)
        
        # Connect to the command created event.
        gouge_command_created = command_created()
        gouge_button.commandCreated.add (gouge_command_created)
        handlers.append(gouge_command_created)

        # add the Moose Tools and the xy to uv button to the Tools tab
        utilities_tab = ui.allToolbarTabs.itemById('ToolsTab')
        if utilities_tab:
            # get or create the "Moose Tools" panel.
            moose_tools_panel = ui.allToolbarPanels.itemById('MoosePanel')
            if not moose_tools_panel:
                moose_tools_panel = utilities_tab.toolbarPanels.add('MoosePanel', 'Moose Tools')

        if moose_tools_panel:
            # Add the command to the panel.
            control = moose_tools_panel.controls.addCommand(gouge_button)
            control.isPromoted = False
            control.isPromotedByDefault = False
            debug_print ('Moose Tools installed')

    except:
        if ui:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))

# Event handler for the inputChanged event
class input_changed (adsk.core.InputChangedEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            event_args = adsk.core.InputChangedEventArgs.cast(args)
            inputs = event_args.inputs

            if event_args.input.id == 'sketch_select':
                sketch_input: adsk.core.SelectionCommandInput = inputs.itemById('sketch_select')

                # if we have the one sketch required, move on to the face
                if sketch_input.selectionCount == 1:
                    face_input: adsk.core.SelectionCommandInput = inputs.itemById('face_select')
                    face_input.hasFocus = True
        except:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))

# Event handler for the commandCreated event.
class command_created (adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):

        event_args = adsk.core.CommandCreatedEventArgs.cast(args)
        command = event_args.command
        inputs = command.commandInputs
 
        # Connect to the execute event
        onExecute = command_executed()
        command.execute.add(onExecute)
        handlers.append(onExecute)

        # Connect to the execute event
        on_input_changed = input_changed()
        command.inputChanged.add(on_input_changed)
        handlers.append(on_input_changed)

        # create the sketch selection input widget
        sketch_selection_input = inputs.addSelectionInput('sketch_select', 'Sketch', 'Select the sketch')
        sketch_selection_input.addSelectionFilter('Sketches')
        sketch_selection_input.setSelectionLimits(1,1)

        # create the face selection input widget
        face_selection_input = inputs.addSelectionInput('face_select', 'Face', 'Select the face')
        face_selection_input.addSelectionFilter('Faces')
        face_selection_input.setSelectionLimits(1,1)

        # create tool diameter input widget
        inputs.addFloatSpinnerCommandInput ('tool_diameter', 'Tool diameter', 'in', 0.05 , 1.0 , .01, tool_diameter)

        # create swap uv checkbox widget
        inputs.addBoolValueInput('gouge_surface', 'Gouge surface', True, '', gouge_surface)

        # create debug checkbox widget
        inputs.addBoolValueInput('debug', 'Debug', True, '', debug)

# Event handler for the execute event.
class command_executed (adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        global debug
        global gouge_surface
        global tool_diameter
        global tool_radius

        try:
            design = app.activeProduct

            # get current command
            command = args.firingEvent.sender

            for input in command.commandInputs:
                if (input.id == 'sketch_select'):
                    input_sketch = input.selection(0).entity
                elif (input.id == 'face_select'):
                    face = input.selection(0).entity
                elif (input.id == 'tool_diameter'):
                    tool_diameter = input.value    
                    tool_radius = tool_diameter * 0.5
                    debug_print (f'tool diameter = {tool_diameter:.3f} cm')
                elif (input.id == 'gouge_surface'):
                    gouge_surface = input.value           
                elif (input.id == 'debug'):
                    debug = input.value           
                else: 
                    debug_print (f'OOOPS --- too much input')

            root_component = design.rootComponent

            debug_print (f'----------------- {input_sketch.name} -----------------')
            debug_print (f'face: {face.objectType}')

            parent_body = face.body
            parent_component = parent_body.parentComponent

            sketches = parent_component.sketches

            face_evaluator = face.evaluator

            sketch_curves = input_sketch.sketchCurves
            debug_print (f'sketch has {sketch_curves.count} curves')

            # only process fixed splines ; more can be added later
            sketch_fixed_splines = input_sketch.sketchCurves.sketchFixedSplines
            debug_print (f'Processing {sketch_fixed_splines.count} fixed splines')

            # get construction planes collection
            construction_planes = parent_component.constructionPlanes
            plane_input = construction_planes.createInput()

            saved_rails = []

            # rail sketch should exist in the same coordinate system as the parent component of the face chosen
            rail_sketch = sketches.add (parent_component.xYConstructionPlane)
            rail_sketch.name = 'rail sketch'

            debug_print ('------------------------------------')

            # tmp_vector will be used to calculate distance along projected normals to define circle
            tmp_vector = adsk.core.Vector3D.create ()

            # these points will be used in the calculation for each gouge; just allocate them once
            mid_p1 = adsk.core.Point3D.create ()                    
            start_normal_point = adsk.core.Point3D.create()
            mid_normal_point = adsk.core.Point3D.create()
            end_normal_point = adsk.core.Point3D.create()
            start_p1_local = adsk.core.Point3D.create()
            mid_p1_local = adsk.core.Point3D.create()
            end_p1_local = adsk.core.Point3D.create()


            i = 0
            for spline in sketch_fixed_splines:
                debug_print (f'Creating toolpath {i}')

                tmp_sketch = sketches.add (parent_component.xYConstructionPlane)
                tmp_sketch.name = f'tmp sketch {i}'

                # get the evaluator for this curve
                curve_evaluator = spline.evaluator

                # get the parametric endpoints
                (status, start_p, end_p) = curve_evaluator.getParameterExtents()                

                # get endpoints in cartesian coordinates
                (status, start_p0, end_p0) = curve_evaluator.getEndPoints()

                # calculate mid_point in cartesian space
                (status, length) = curve_evaluator.getLengthAtParameter (start_p, end_p)
                (status, mid_p) = curve_evaluator.getParameterAtLength (start_p, length * 0.5)

                # convert parameter into cartesian coordinates for all three points
                (status, mid_p0) = curve_evaluator.getPointAtParameter (mid_p)

                (status, mid_normal) = face_evaluator.getNormalAtPoint (mid_p0)

                # figure out depth of cut for middle of the curve; it's tool radius down along the midpoint normal
                gouge_vector = adsk.core.Vector3D.create ()   
                
                gouge_vector.x = -mid_normal.x * tool_radius
                gouge_vector.y = -mid_normal.y * tool_radius
                gouge_vector.z = -mid_normal.z * tool_radius
                
                # point in middle of curve at depth of gouge
                mid_p1.x = mid_p0.x + gouge_vector.x 
                mid_p1.y = mid_p0.y + gouge_vector.y 
                mid_p1.z = mid_p0.z + gouge_vector.z 

                tmp_sketch_points = tmp_sketch.sketchPoints
                tmp_sketch_lines = tmp_sketch.sketchCurves.sketchLines

                # add points at end to use in loft
                loft_start_point = tmp_sketch_points.add (start_p0)
                loft_end_point = tmp_sketch_points.add (end_p0)
                
                # add midpoint line to use in surface loft
                mid_line = tmp_sketch_lines.addByTwoPoints (mid_p0, mid_p1)
                
                # define the input for a surface loft that will create the toolpath
                surface_loft_features = parent_component.features.loftFeatures
                surface_loft_input = surface_loft_features.createInput(adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
                surface_loft_input.isSolid = False

                surface_loft_sections = surface_loft_input.loftSections
                surface_loft_sections.add (loft_start_point)
                surface_loft_sections.add (mid_line)
                surface_loft_sections.add (loft_end_point)
                
                surface_loft_input.isClosed = False

                surface_loft_input.centerLineOrRails.addRail (spline)

                # create the loft
                surface_loft_feature = surface_loft_features.add(surface_loft_input)
                surface_loft_feature.bodies.item(0).name = f'surface {i}'                                

                surface_loft_face = surface_loft_feature.faces.item(0)
                if surface_loft_face.edges.count == 2:
                    edge0 = surface_loft_face.edges.item(0)
                    edge1 = surface_loft_face.edges.item(1)
                
                # measure distance between two edges of the surface loft and the deepest point in the gouge (mid_p1)
                edge0_distance = app.measureManager.measureMinimumDistance (edge0, mid_p1).value
                edge1_distance = app.measureManager.measureMinimumDistance (edge1, mid_p1).value

                # find bottom curve and make a copy
                if  edge0_distance < edge1_distance:
                    saved_rails.append (edge0.geometry.copy())
                else:
                    saved_rails.append (edge1.geometry.copy())

                # add the toolpath curve to the rail sketch which will get processed later
                toolpath = rail_sketch.sketchCurves.sketchFixedSplines.addByNurbsCurve (saved_rails[i])

                # get rid of the surface loft since we got the bottom curve which is all we needed
                surface_loft_feature.deleteMe()

                debug_print (f'GOuging along toolpath {i}')
                
                # get the parametric endpoints
                (status, start_p, end_p) = toolpath.evaluator.getParameterExtents()                    
                
                # get endpoints in cartesian coordinates
                (status, start_p0, end_p0) = toolpath.evaluator.getEndPoints()

                # calculate mid_point in cartesian space
                (status, length) = toolpath.evaluator.getLengthAtParameter (start_p, end_p)
                (status, mid_p) = toolpath.evaluator.getParameterAtLength (start_p, length * 0.5)

                # convert parameter into cartesian coordinates for all midpoint
                (status, mid_p0) = toolpath.evaluator.getPointAtParameter (mid_p)

                # get normals to surface at middle and both ends of toolpath curve
                (status, start_normal) = face_evaluator.getNormalAtPoint (start_p0)
                (status, mid_normal) = face_evaluator.getNormalAtPoint (mid_p0)
                (status, end_normal) = face_evaluator.getNormalAtPoint (end_p0)

                # make three temporary construction planes and sketches along the toolpath curve

                # create construction plane at beginning of path
                plane_input.setByDistanceOnPath (toolpath, adsk.core.ValueInput.createByReal(0.0))
                start_construction_plane = construction_planes.add (plane_input)
                start_construction_plane.name = (f'start {i}')

                # create construction plane at middle of path
                plane_input.setByDistanceOnPath (toolpath, adsk.core.ValueInput.createByReal(0.5))
                mid_construction_plane = construction_planes.add (plane_input)
                mid_construction_plane.name = (f'mid {i}')

                # create construction plane at end of path
                plane_input.setByDistanceOnPath (toolpath, adsk.core.ValueInput.createByReal(1.0))
                end_construction_plane = construction_planes.add (plane_input)
                end_construction_plane.name = (f'end {i}')

                # create a sketch on each of the newly created construction planes
                start_sketch = sketches.add (start_construction_plane)
                start_sketch.name = f'start sketch {i}'

                mid_sketch = sketches.add (mid_construction_plane)
                mid_sketch.name = f'mid sketch {i}'

                end_sketch = sketches.add (end_construction_plane)
                end_sketch.name = f'end sketch {i}'

                # make normal at start_point into sketch line and project it into start_sketch
                start_p0_local = start_sketch.modelToSketchSpace (start_p0)

                start_normal_point.x = start_p0.x + start_normal.x
                start_normal_point.y = start_p0.y + start_normal.y
                start_normal_point.z = start_p0.z + start_normal.z

                start_normal_point_local = start_sketch.modelToSketchSpace (start_normal_point)
                tmp_point = start_sketch.sketchPoints.add (start_normal_point_local)

                entities = []
                entities = start_sketch.project (tmp_point)
                projected_start_normal = entities[0]
                tmp_point.isReference = False

                tmp_vector.x = projected_start_normal.geometry.x - start_p0_local.x
                tmp_vector.y = projected_start_normal.geometry.y - start_p0_local.y
                tmp_vector.z = projected_start_normal.geometry.z - start_p0_local.z

                tmp_vector.scaleBy (tool_diameter / tmp_vector.length )

                # find point in sketch coordinates that is a tool diameter away from surface along the projected normal 
                start_p1_local.x = start_p0_local.x + tmp_vector.x
                start_p1_local.y = start_p0_local.y + tmp_vector.y
                start_p1_local.z = start_p0_local.z + tmp_vector.z

                start_sketch.sketchCurves.sketchCircles.addByTwoPoints (start_p0_local, start_p1_local)

                # do same thing for midpoint

                # make normal at mid_point into sketch line and project it into mid_sketch
                mid_p0_local = mid_sketch.modelToSketchSpace (mid_p0)

                mid_normal_point.x = mid_p0.x + mid_normal.x
                mid_normal_point.y = mid_p0.y + mid_normal.y
                mid_normal_point.z = mid_p0.z + mid_normal.z

                mid_normal_point_local = mid_sketch.modelToSketchSpace (mid_normal_point)
                tmp_point = mid_sketch.sketchPoints.add (mid_normal_point_local)

                entities = []
                entities = mid_sketch.project (tmp_point)
                projected_mid_normal = entities[0]
                tmp_point.isReference = False

                tmp_vector.x = projected_mid_normal.geometry.x - mid_p0_local.x
                tmp_vector.y = projected_mid_normal.geometry.y - mid_p0_local.y
                tmp_vector.z = projected_mid_normal.geometry.z - mid_p0_local.z

                tmp_vector.scaleBy (tool_diameter / tmp_vector.length )

                mid_p1_local.x = mid_p0_local.x + tmp_vector.x
                mid_p1_local.y = mid_p0_local.y + tmp_vector.y
                mid_p1_local.z = mid_p0_local.z + tmp_vector.z

                mid_sketch.sketchCurves.sketchCircles.addByTwoPoints (mid_p0_local, mid_p1_local)

                # and again at the other end of the curve
               
                # make normal at end_point into sketch line and project it into end_sketch
                end_p0_local = end_sketch.modelToSketchSpace (end_p0)

                end_normal_point.x = end_p0.x + end_normal.x
                end_normal_point.y = end_p0.y + end_normal.y
                end_normal_point.z = end_p0.z + end_normal.z

                end_normal_point_local = end_sketch.modelToSketchSpace (end_normal_point)
                tmp_point = end_sketch.sketchPoints.add (end_normal_point_local)

                entities = []
                entities = end_sketch.project (tmp_point)
                projected_end_normal = entities[0]
                tmp_point.isReference = False

                tmp_vector.x = projected_end_normal.geometry.x - end_p0_local.x
                tmp_vector.y = projected_end_normal.geometry.y - end_p0_local.y
                tmp_vector.z = projected_end_normal.geometry.z - end_p0_local.z

                tmp_vector.scaleBy (tool_diameter / tmp_vector.length )

                end_p1_local.x = end_p0_local.x + tmp_vector.x
                end_p1_local.y = end_p0_local.y + tmp_vector.y
                end_p1_local.z = end_p0_local.z + tmp_vector.z

                end_sketch.sketchCurves.sketchCircles.addByTwoPoints (end_p0_local, end_p1_local)

                i = i + 1
            
            # take the saved rails and the circles in the sketches to create lofts that gouge the surface
                
            debug_print (f'rail sketch has {rail_sketch.sketchCurves.count} curve(s)')

            i = 0
            for r in rail_sketch.sketchCurves.sketchFixedSplines:

                # define the input for a solid loft that gouges the surface
                solid_loft_features = parent_component.features.loftFeatures
                solid_loft_input = solid_loft_features.createInput(adsk.fusion.FeatureOperations.CutFeatureOperation)
                solid_loft_input.isSolid = True

                start_sketch = sketches.itemByName (f'start sketch {i}')
                mid_sketch = sketches.itemByName (f'mid sketch {i}')
                end_sketch = sketches.itemByName (f'end sketch {i}')
                start_circle_profile = start_sketch.profiles.item(0)
                middle_circle_profile = mid_sketch.profiles.item(0)
                end_circle_profile = end_sketch.profiles.item(0)

                solid_loft_sections = solid_loft_input.loftSections
                solid_loft_sections.add(start_circle_profile)
                solid_loft_sections.add(middle_circle_profile)
                solid_loft_sections.add(end_circle_profile)

                solid_loft_input.centerLineOrRails.addRail (r)

                participant_bodies = []
                participant_bodies.append (parent_body)
                solid_loft_input.participantBodies = participant_bodies

                if gouge_surface:               
                    solid_loft_feature = solid_loft_features.add(solid_loft_input)

                    health_state = solid_loft_feature.healthState

                    if health_state == adsk.fusion.FeatureHealthStates.HealthyFeatureHealthState:
                        debug_print (f'toolpath gouge {i} successful')
                    elif health_state == adsk.fusion.FeatureHealthStates.WarningFeatureHealthState:
                        warning = solid_loft_feature.errorOrWarningMessage
                        debug_print (f'warning: {warning}')
                    elif health_state == adsk.fusion.FeatureHealthStates.ErrorFeatureHealthState:
                        error = solid_loft_feature.errorOrWarningMessage
                        debug_print (f'error: {error}')
                
                # clean up a little
                tmp_sketch.deleteMe()

                start_sketch.isVisible = False
                mid_sketch.isVisible = False
                end_sketch.isVisible = False

                i = i + 1

            # clean up a little more
            input_sketch.isVisible = False
            rail_sketch.isVisible = False

        except:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))	


def debug_print (msg):
    if debug:
        text_palette = ui.palettes.itemById('TextCommands')
        text_palette.writeText (msg)

def debug_print_point (msg, point):
    if debug:
        text_palette = ui.palettes.itemById('TextCommands')
        text_palette.writeText (f'{msg}, ({point.x:.3f}, {point.y:.3f}, {point.z:.3f})')
        
def stop(context):
    try:
        global handlers
        
        # Clean up the UI.
        command_definitions = ui.commandDefinitions.itemById('gouge_surface')
        if command_definitions:
            command_definitions.deleteMe()
        
        # get rid of this button
        moose_tools_panel = ui.allToolbarPanels.itemById('MoosePanel')
        control = moose_tools_panel.controls.itemById('gouge_surface')
        if control:
            control.deleteMe()

        # and if it's the last button, get rid of the moose panel
        if moose_tools_panel.controls.count == 0:
                    moose_tools_panel.deleteMe()
        
        handlers = []

    except:
        if ui:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))	
