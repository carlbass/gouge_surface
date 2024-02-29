# Author- Carl Bass
# Description- make surface gouges

# To Do
# get loft to use rail

import adsk.core, adsk.fusion, adsk.cam, traceback
import os

# Global list to keep all event handlers in scope.
handlers = []

# global variables available in all functions
app = adsk.core.Application.get()
ui  = app.userInterface

# global variables because I can't find a better way to pass this info around -- would be nice if fusion api had some cleaner way to do this
debug = True
use_rail = True
tool_diameter = 0.25

def run(context):
    
    try:

        # Find where the python file lives and look for the icons in the ./.resources folder
        python_file_folder = os.path.dirname(os.path.realpath(__file__))
        resource_folder = os.path.join (python_file_folder, 'resources')

        # Get the CommandDefinitions collection so we can add a command
        command_definitions = ui.commandDefinitions
        
        tooltip = 'Maps lines, arcs and fitted splines from sketch to surface'

        # Create a button command definition.
        offset_button = command_definitions.addButtonDefinition('offset_curves', 'Offset curves', tooltip, resource_folder)
        
        # Connect to the command created event.
        offset_command_created = command_created()
        offset_button.commandCreated.add (offset_command_created)
        handlers.append(offset_command_created)

        # add the Moose Tools and the xy to uv button to the Tools tab
        utilities_tab = ui.allToolbarTabs.itemById('ToolsTab')
        if utilities_tab:
            # get or create the "Moose Tools" panel.
            moose_tools_panel = ui.allToolbarPanels.itemById('MoosePanel')
            if not moose_tools_panel:
                moose_tools_panel = utilities_tab.toolbarPanels.add('MoosePanel', 'Moose Tools')

        if moose_tools_panel:
            # Add the command to the panel.
            control = moose_tools_panel.controls.addCommand(offset_button)
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
        inputs.addBoolValueInput('use_rail', 'Use rail', True, '', use_rail)

        # create debug checkbox widget
        inputs.addBoolValueInput('debug', 'Debug', True, '', debug)

# Event handler for the execute event.
class command_executed (adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        global debug
        global use_rail
        global tool_diameter

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
                    debug_print (f'tool diameter = {tool_diameter} cm = {tool_diameter /2.54} in')   
                elif (input.id == 'use_rail'):
                    use_rail = input.value           
                elif (input.id == 'debug'):
                    debug = input.value           
                else: 
                    debug_print (f'OOOPS --- too much input')

            root_component = design.rootComponent
            sketches = root_component.sketches

            debug_print (f'----------------- {input_sketch.name} -----------------')
            debug_print (f'face: {face.objectType}')

            parent_body = face.body

            face_evaluator = face.evaluator

            sketch_curves = input_sketch.sketchCurves
            debug_print (f'sketch has {sketch_curves.count} curves')

            # only process fixed splines ; more can be added later
            sketch_fixed_splines = input_sketch.sketchCurves.sketchFixedSplines
            debug_print (f'Processing {sketch_fixed_splines.count} fixed splines')


            i = 0
            for spline in sketch_fixed_splines:

                # get the evaluator for this curve
                curve_evaluator = spline.evaluator

                # get the parametric endpoints
                (status, start_p, end_p) = curve_evaluator.getParameterExtents()

                # calculate mid_point in parametric space
                mid_point_p = (start_p + end_p) * 0.5
                debug_print (f'p values = {start_p:.2f}, {end_p:.2f}, {mid_point_p:.2f}')

                # convert parameter coordinate into world coordinates for all three points
                (status, mid_point_wc) = curve_evaluator.getPointAtParameter (mid_point_p)

                # get endpoints in world coordinates
                (status, start_point_wc, end_point_wc) = curve_evaluator.getEndPoints()

                # print world corrdinates of points at beginning, middle and end of curve on the surface
                debug_print_point ('start_point_wc', start_point_wc)
                debug_print_point ('mid_point_wc', mid_point_wc)
                debug_print_point ('end_point_wc', end_point_wc)

                # get normals to surface at middle and both ends of curve
                mid_normal = adsk.core.Vector3D.create ()   
                (status, mid_normal) = face_evaluator.getNormalAtPoint (mid_point_wc)
                
                (status, start_normal) = face_evaluator.getNormalAtPoint (start_point_wc)

                (status, end_normal) = face_evaluator.getNormalAtPoint (end_point_wc)

                # print normals to the surface at these 3 points                
                debug_print (f'start normal = ({start_normal.x:.2f}, {start_normal.y:.2f}, {start_normal.z:.2f})')
                debug_print (f'mid normal = ({mid_normal.x:.2f}, {mid_normal.y:.2f}, {mid_normal.z:.2f})')
                debug_print (f'end normal = ({end_normal.x:.2f}, {end_normal.y:.2f}, {end_normal.z:.2f})')

                # figure out depth of cut for middle of the curve; it's tool radius down along the midpoint normal
                gouge_vector = adsk.core.Vector3D.create ()   
                
                gouge_vector.x = -mid_normal.x * tool_diameter * 0.5
                gouge_vector.y = -mid_normal.y * tool_diameter * 0.5
                gouge_vector.z = -mid_normal.z * tool_diameter * 0.5
                debug_print (f'gouge vector = ({gouge_vector.x:.2f}, {gouge_vector.y:.2f}, {gouge_vector.z:.2f})')
                
                # scale endpoint normals by tool radius -- then circular profiles should be centered on end of these scaled normals and the toolpath curve should be tangent to the circle
                start_normal.scaleBy (tool_diameter * 0.5)
                end_normal.scaleBy (tool_diameter * 0.5)
                
                # get construction planes collection
                construction_planes = root_component.constructionPlanes
                plane_input = construction_planes.createInput()

                # create construction plane at mid_point; function wants 0.5 not real parametric midpoint
                plane_input.setByDistanceOnPath (spline, adsk.core.ValueInput.createByReal(0.5))

                # change default name of construction plane
                construction_plane = construction_planes.add (plane_input)
                construction_plane.name = f'midplane {i}'
                
                # create and name a new sketch on the newly created construction plane
                surface_loft_sketch = sketches.add (construction_plane)
                surface_loft_sketch.name = f'surface loft sketch {i}'

                sketch_points = surface_loft_sketch.sketchPoints
                sketch_lines = surface_loft_sketch.sketchCurves.sketchLines

                gouge_bottom_wc = adsk.core.Point3D.create ()                    
                gouge_bottom_wc.x = mid_point_wc.x + gouge_vector.x 
                gouge_bottom_wc.y = mid_point_wc.y + gouge_vector.y 
                gouge_bottom_wc.z = mid_point_wc.z + gouge_vector.z 

                mid_p1 = surface_loft_sketch.modelToSketchSpace (gouge_bottom_wc)

                # convert endpoints from model coordinates to sketch coordinates
                start_p0 = surface_loft_sketch.modelToSketchSpace (start_point_wc)
                mid_p0 = surface_loft_sketch.modelToSketchSpace (mid_point_wc)
                end_p0 = surface_loft_sketch.modelToSketchSpace (end_point_wc)

                # add normal at both ends 
                start_p1_wc = adsk.core.Point3D.create ()                    
                start_p1_wc.x = start_point_wc.x + start_normal.x
                start_p1_wc.y = start_point_wc.y + start_normal.y
                start_p1_wc.z = start_point_wc.z + start_normal.z

                start_p1 = surface_loft_sketch.modelToSketchSpace (start_p1_wc)                           

                end_p1_wc = adsk.core.Point3D.create ()                    
                end_p1_wc.x = end_point_wc.x + end_normal.x
                end_p1_wc.y = end_point_wc.y + end_normal.y
                end_p1_wc.z = end_point_wc.z + end_normal.z

                debug_print_point ('end_p1_wc: ', end_p1_wc)

                end_p1 = surface_loft_sketch.modelToSketchSpace (end_p1_wc)

                # add three points
                sketch_points.add (mid_p1)
                loft_start_point = sketch_points.add (start_p0)
                loft_end_point = sketch_points.add (end_p0)
                
                # add three lines
                start_line = sketch_lines.addByTwoPoints (start_p0, start_p1)
                mid_line = sketch_lines.addByTwoPoints (mid_p1, mid_p0)
                end_line = sketch_lines.addByTwoPoints (end_p0, end_p1)
                

                # Define the input for a surface loft
                surface_loft_features = root_component.features.loftFeatures
                surface_loft_input = surface_loft_features.createInput(adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
                surface_loft_input.isSolid = False

                surface_loft_sections = surface_loft_input.loftSections
                surface_loft_sections.add(loft_start_point)
                surface_loft_sections.add(mid_line)
                surface_loft_sections.add(loft_end_point)
                
                surface_loft_input.isClosed = False

                surface_loft_input.centerLineOrRails.addRail (spline)

                # create the loft
                surface_loft_feature = surface_loft_features.add(surface_loft_input)
                surface_loft_feature.bodies.item(0).name = f'surface {i}'                                

                surface_loft_face = surface_loft_feature.faces.item(0)

                # create toolpath sketch
                toolpath_sketch = sketches.add (construction_plane)
                toolpath_sketch.name = f'toolpath {i}'
                toolpath_include = toolpath_sketch.include (surface_loft_face)
                    
                debug_print (f'toolpath count: {toolpath_sketch.sketchCurves.count}')

                s0 = toolpath_sketch.sketchCurves.item(0)
                s1 = toolpath_sketch.sketchCurves.item(1)

                debug_print (f's0 = {s0.objectType} length = {s0.length:.3f}')
                debug_print (f's1 = {s1.objectType} length = {s1.length:.3f}')

                #find distances from the curves to point at bottom of gouge at the mid_point
                s0_distance = app.measureManager.measureMinimumDistance (s0, gouge_bottom_wc).value
                s1_distance = app.measureManager.measureMinimumDistance (s1, gouge_bottom_wc).value

                debug_print (f's0 distance = {s0_distance:.2f}')
                debug_print (f's1 distance = {s1_distance:.2f}')
                debug_print (f's0 is valid {s0.isValid} is reference {s0.isReference} is deletable {s0.isDeletable} is valid {s0.isValid}')
                debug_print (f's1 is valid {s1.isValid} is reference {s1.isReference} is deletable {s1.isDeletable} is valid {s1.isValid}')

                # find correct curve and delete other
                if  s0_distance < s1_distance:
                    s1.isReference = False
                    status = s1.deleteMe()
                    rail = s0
                    debug_print (f'delete s1 status = {status}')
                else:
                    s0.isReference = False
                    status = s0.deleteMe()
                    rail = s1
                    debug_print (f'delete s0 status = {status}')

                debug_print (f'toolpath count: {toolpath_sketch.sketchCurves.count}')
                debug_print (f'toolpath curve length: {toolpath_sketch.sketchCurves.item(0).length:.3f}')

                surface_loft_sketch.sketchCurves.sketchCircles.addByCenterRadius (mid_p0, tool_diameter * 0.5)

                # create construction plane at beginning and end of path
                plane_input.setByDistanceOnPath (spline, adsk.core.ValueInput.createByReal(0.0))
                start_construction_plane = construction_planes.add (plane_input)
                start_construction_plane.name = f'start plane {i}'

                plane_input.setByDistanceOnPath (spline, adsk.core.ValueInput.createByReal(1.0))
                end_construction_plane = construction_planes.add (plane_input)
                end_construction_plane.name = f'end plane {i}'

                start_circle_sketch = sketches.add (start_construction_plane)
                end_circle_sketch = sketches.add (end_construction_plane)
                start_circle_sketch.name = f'start circle {i}'
                end_circle_sketch.name = f'end circle {i}'

                # all this code is to get the correct position and orientation of the circle
                projected_entity = start_circle_sketch.project (start_line)
                debug_print (f'projected entities = {projected_entity.count}')
                for p in projected_entity:
                    debug_print (f'entity of {p.objectType}')

                pt0 = projected_entity.item(0).startSketchPoint
                pt1 = projected_entity.item(0).endSketchPoint

                pt0_distance = app.measureManager.measureMinimumDistance (pt0, start_circle_sketch.originPoint).value
                pt1_distance = app.measureManager.measureMinimumDistance (pt1, start_circle_sketch.originPoint).value

                debug_print (f'pt0 distance = {pt0_distance:.2f}')
                debug_print (f'pt1 distance = {pt1_distance:.2f}')

                origin = adsk.core.Point3D.create(0, 0, 0)

                # find correct end of projected line
                if  pt0_distance < pt1_distance:
                    center_point = pt1
                else:
                    center_point = pt0

                start_circle_sketch.sketchCurves.sketchCircles.addByCenterRadius (center_point, tool_diameter * 0.5)

                # now do it for the other end of the curve
                projected_entity = end_circle_sketch.project (end_line)
                debug_print (f'projected entities = {projected_entity.count}')
                for p in projected_entity:
                    debug_print (f'entity of {p.objectType}')

                pt0 = projected_entity.item(0).startSketchPoint
                pt1 = projected_entity.item(0).endSketchPoint

                pt0_distance = app.measureManager.measureMinimumDistance (pt0, end_circle_sketch.originPoint).value
                pt1_distance = app.measureManager.measureMinimumDistance (pt1, end_circle_sketch.originPoint).value

                debug_print (f'pt0 distance = {pt0_distance:.2f}')
                debug_print (f'pt1 distance = {pt1_distance:.2f}')


                # find correct end of projected line
                if  pt0_distance < pt1_distance:
                    center_point = pt1
                else:
                    center_point = pt0

                end_circle_sketch.sketchCurves.sketchCircles.addByCenterRadius (center_point, tool_diameter * 0.5)

                # Define the input for a solid loft that gouges the surface
                solid_loft_features = root_component.features.loftFeatures
                solid_loft_input = solid_loft_features.createInput(adsk.fusion.FeatureOperations.CutFeatureOperation)
                solid_loft_input.isSolid = True

                start_circle_profile = start_circle_sketch.profiles.item(0)
                middle_circle_profile = surface_loft_sketch.profiles.item(0)
                end_circle_profile = end_circle_sketch.profiles.item(0)

                solid_loft_sections = solid_loft_input.loftSections
                solid_loft_sections.add(start_circle_profile)
                solid_loft_sections.add(middle_circle_profile)
                solid_loft_sections.add(end_circle_profile)

                if use_rail:
                    solid_loft_input.centerLineOrRails.addRail (rail)

                participant_bodies = []
                participant_bodies.append (parent_body)
                solid_loft_input.participantBodies = participant_bodies
                
                solid_loft_feature = solid_loft_features.add(solid_loft_input)

                debug_print (f'is rail used = {solid_loft_feature.centerLineOrRails.isCenterLine}')
                debug_print (f'rail count = {solid_loft_feature.centerLineOrRails.count}')

                health_state = solid_loft_feature.healthState

                if health_state == adsk.fusion.FeatureHealthStates.HealthyFeatureHealthState:
                    debug_print ('all good with the gouge cut')
                elif health_state == adsk.fusion.FeatureHealthStates.WarningFeatureHealthState:
                    warning = solid_loft_feature.errorOrWarningMessage
                    debug_print (f'warning: {warning}')
                elif health_state == adsk.fusion.FeatureHealthStates.ErrorFeatureHealthState:
                    error = solid_loft_feature.errorOrWarningMessage
                    debug_print (f'error: {error}')

                # turn off visibility to lots of intermediate geometry
                surface_loft_feature.bodies.item(0).isLightBulbOn = False
                start_circle_sketch.isLightBulbOn = False
                end_circle_sketch.isLightBulbOn = False
                surface_loft_sketch.isLightBulbOn = False

                # check distances to ensure rail touches the 3 circular profiles; not sure why measure manager is barfing; measured manually they're all zero

                debug_print (f'rail is type {rail.objectType}')
                debug_print (f'circle is type {start_circle_sketch.sketchCurves.sketchCircles.item(0).objectType}') 
                                             
                #d1 = app.measureManager.measureMinimumDistance (rail, start_circle_sketch.sketchCurves.sketchCircles.item(0)).value
                #d2 = app.measureManager.measureMinimumDistance (rail, surface_loft_sketch.sketchCurves.sketchCircles.item(0)).value
                #d3 = app.measureManager.measureMinimumDistance (rail, end_circle_sketch.sketchCurves.sketchCircles.item(0)).value

                #debug_print (f'check that rail touches circles {d1:.5f} {d2:.5f} {d3:.5f} ')


                i = i + 1
        except:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))	


def debug_print (msg):
    if debug:
        text_palette = ui.palettes.itemById('TextCommands')
        text_palette.writeText (msg)

def debug_print_point (msg, point):
    if debug:
        text_palette = ui.palettes.itemById('TextCommands')
        text_palette.writeText (f'{msg}, ({point.x:.2f}, {point.y:.2f}, {point.z:.2f})')
        
def stop(context):
    try:

        # Clean up the UI.
        command_definitions = ui.commandDefinitions.itemById('offset_curves')
        if command_definitions:
            command_definitions.deleteMe()
        
        # get rid of this button
        moose_tools_panel = ui.allToolbarPanels.itemById('MoosePanel')
        control = moose_tools_panel.controls.itemById('offset_curves')
        if control:
            control.deleteMe()

        # and if it's the last button, get rid of the moose panel
        if moose_tools_panel.controls.count == 0:
                    moose_tools_panel.deleteMe()

    except:
        if ui:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))	
