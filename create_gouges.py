# Author- Carl Bass
# Description- make surface gouges

# To Do
# get loft to use rail
# save solid loft elements until the end
# do all the gouging at the end so there's no problem with normals once the surface has been gouged

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
tool_radius = tool_diameter * 0.5

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
                elif (input.id == 'use_rail'):
                    use_rail = input.value           
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

            # circles sketch should exist in the same coordinate system as the parent component of the face chosen
            circles_sketch = sketches.add (parent_component.xYConstructionPlane)
            circles_sketch.name = 'circles sketch'

            # get construction planes collection
            construction_planes = parent_component.constructionPlanes
            plane_input = construction_planes.createInput()

            saved_rails = []
            profiles = []

            # rail sketch should exist in the same coordinate system as the parent component of the face chosen
            rail_sketch = sketches.add (parent_component.xYConstructionPlane)
            rail_sketch.name = 'rail sketch'

            i = 0
            
            for spline in sketch_fixed_splines:
                tmp_sketch = sketches.add (parent_component.xYConstructionPlane)
                tmp_sketch.name = f'tmp sketch {i}'

                # get the evaluator for this curve
                curve_evaluator = spline.evaluator

                # get the parametric endpoints
                (status, start_p, end_p) = curve_evaluator.getParameterExtents()
                debug_print (f'start_p = {start_p:.2f}')
                debug_print (f'end_p = {end_p:.2f}')
                
                # calculate mid_point in parametric space
                mid_p = (start_p + end_p) * 0.5
                debug_print (f'mid_p = {mid_p:.2f}')

                # calculate mid_point in cartesian space
                (status, length) = curve_evaluator.getLengthAtParameter (0.0, 1.0)
                (status, ppp) = curve_evaluator.getParameterAtLength (0.0, length * 0.5)


                # convert parameter into cartesian coordinates for all three points
                (status, mid_p0) = curve_evaluator.getPointAtParameter (mid_p)
                debug_print_point ('mid_p0', mid_p0)

                (status, mid_p0) = curve_evaluator.getPointAtParameter (ppp)
                debug_print (f'ppp = {ppp:.3f}')
                debug_print_point ('mid_p0', mid_p0)

                # get endpoints in cartesian coordinates
                (status, start_p0, end_p0) = curve_evaluator.getEndPoints()
                debug_print_point ('start_p0', start_p0)
                debug_print_point ('end_p0', end_p0)

                # get normals to surface at middle and both ends of curve
                (status, start_normal) = face_evaluator.getNormalAtPoint (start_p0)
                (status, mid_normal) = face_evaluator.getNormalAtPoint (mid_p0)
                (status, end_normal) = face_evaluator.getNormalAtPoint (end_p0)

                # figure out depth of cut for middle of the curve; it's tool radius down along the midpoint normal
                gouge_vector = adsk.core.Vector3D.create ()   
                
                gouge_vector.x = -mid_normal.x * tool_radius
                gouge_vector.y = -mid_normal.y * tool_radius
                gouge_vector.z = -mid_normal.z * tool_radius
                #debug_print (f'gouge vector = ({gouge_vector.x:.2f}, {gouge_vector.y:.2f}, {gouge_vector.z:.2f})')
                
                # scale endpoint normals by tool radius -- then circular profiles should be centered on end of these scaled normals and the toolpath curve should be tangent to the circle
                start_normal.scaleBy (tool_radius)
                end_normal.scaleBy (tool_radius)
                
                # this is the bottom of the gouge at the parametric midpoint
                # p0 will be on the orginal surface curve
                # p1 will be above for the endpoints and below for the midpoint
                mid_p1 = adsk.core.Point3D.create ()                    
                mid_p1.x = mid_p0.x + gouge_vector.x 
                mid_p1.y = mid_p0.y + gouge_vector.y 
                mid_p1.z = mid_p0.z + gouge_vector.z 

                mid_p2 = adsk.core.Point3D.create ()                    
                mid_p2.x = mid_p0.x - gouge_vector.x 
                mid_p2.y = mid_p0.y - gouge_vector.y 
                mid_p2.z = mid_p0.z - gouge_vector.z 

                # add normal at start
                start_p1 = adsk.core.Point3D.create ()                    
                start_p1.x = start_p0.x + start_normal.x
                start_p1.y = start_p0.y + start_normal.y
                start_p1.z = start_p0.z + start_normal.z

                # add normal at end
                end_p1 = adsk.core.Point3D.create ()                    
                end_p1.x = end_p0.x + end_normal.x
                end_p1.y = end_p0.y + end_normal.y
                end_p1.z = end_p0.z + end_normal.z

                # have the six critical points in start_p0, mid_p0, end_p0 and start_p1, mid_p1, end_p1
                tmp_sketch_points = tmp_sketch.sketchPoints
                tmp_sketch_lines = tmp_sketch.sketchCurves.sketchLines

                # add points at end to use in loft
                loft_start_point = tmp_sketch_points.add (start_p0)
                loft_end_point = tmp_sketch_points.add (end_p0)
                
                # add three lines
                mid_line = tmp_sketch_lines.addByTwoPoints (mid_p0, mid_p1)
                #end_line = tmp_sketch_lines.addByTwoPoints (end_p0, end_p1)
                #start_line = tmp_sketch_lines.addByTwoPoints (start_p0, start_p1)
                
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
                else:
                    debug_print (f'EEEK surface has face with {surface_loft_face.edges.count} edges')

                # measure distance between two edges of the surface loft and the deepest point in the gouge (mid_p1)
                edge0_distance = app.measureManager.measureMinimumDistance (edge0, mid_p1).value
                edge1_distance = app.measureManager.measureMinimumDistance (edge1, mid_p1).value

                # find bottom curve and make a copy
                if  edge0_distance < edge1_distance:
                    saved_rails.append (edge0.geometry.copy())
                else:
                    saved_rails.append (edge1.geometry.copy())

                status = surface_loft_feature.deleteMe()

                if not (status):
                    debug_print (f'could not delete surface loft')


                # make three temporary construction planes and sketches along the path

                # create construction plane at beginning and end of path
                plane_input.setByDistanceOnPath (spline, adsk.core.ValueInput.createByReal(0.0))
                start_construction_plane = construction_planes.add (plane_input)
                start_construction_plane.name = (f'start {i}')
                
                # create construction plane at beginning of path
                plane_input.setByDistanceOnPath (spline, adsk.core.ValueInput.createByReal(0.5))
                mid_construction_plane = construction_planes.add (plane_input)
                mid_construction_plane.name = (f'mid {i}')

                # create construction plane at end of path
                plane_input.setByDistanceOnPath (spline, adsk.core.ValueInput.createByReal(1.0))
                end_construction_plane = construction_planes.add (plane_input)
                end_construction_plane.name = (f'end {i}')

                # create a sketch on each of the newly created construction planes
                tmp_start_sketch = sketches.add (start_construction_plane)
                tmp_start_sketch.name = f'tmp start sketch {i}'

                tmp_mid_sketch = sketches.add (mid_construction_plane)
                tmp_mid_sketch.name = f'tmp mid sketch {i}'

                tmp_end_sketch = sketches.add (end_construction_plane)
                tmp_end_sketch.name = f'tmp end sketch {i}'

                # add the circles at the three points and include the three circles into circles sketch

                start_p1_local = tmp_start_sketch.modelToSketchSpace (start_p1)
                tmp_circle = tmp_start_sketch.sketchCurves.sketchCircles.addByCenterRadius (start_p1_local, tool_radius)
                included_entities = circles_sketch.include (tmp_circle)
                included_circle = included_entities.item(0)
                included_circle.isReference = False


                mid_p1_local = tmp_mid_sketch.modelToSketchSpace (mid_p1)
                mid_p2_local = tmp_mid_sketch.modelToSketchSpace (mid_p2)
                
                tmp_sketch.sketchPoints.add (mid_p1)
                tmp_sketch.sketchPoints.add (mid_p2)

                debug_print_point ('mid p1', mid_p1)
                debug_print_point ('mid p1 local', mid_p1_local)                
                debug_print_point ('mid p2', mid_p2)
                debug_print_point ('mid p2 local', mid_p2_local)
                
                # need to ensure tangent point is on curve
                # add the toolpath curve to the rail sketch
                toolpath = rail_sketch.sketchCurves.sketchFixedSplines.addByNurbsCurve (saved_rails[i])

                entities = []
                entities.append (toolpath)

                # intersection should be a single sketch point; could be multiple if curve wraps has high curvature
                sketch_entities = tmp_mid_sketch.intersectWithSketchPlane(entities)


                debug_print_point ('intersection pt', sketch_entities[0].geometry)

                tmp_circle = tmp_mid_sketch.sketchCurves.sketchCircles.addByTwoPoints (mid_p2_local, sketch_entities[0].geometry)
                included_entities = circles_sketch.include (tmp_circle)
                included_circle = included_entities.item(0)
                included_circle.isReference = False

                end_p1_local = tmp_end_sketch.modelToSketchSpace (end_p1)
                tmp_circle = tmp_end_sketch.sketchCurves.sketchCircles.addByCenterRadius (end_p1_local, tool_radius)
                included_entities = circles_sketch.include (tmp_circle)
                included_circle = included_entities.item(0)
                included_circle.isReference = False
    
                debug_print (f'circles sketch has {circles_sketch.profiles.count} profile(s)')

                    
                # delete sketches and their construction plane
                #tmp_start_sketch.deleteMe()
                #start_construction_plane.deleteMe()

                #tmp_mid_sketch.deleteMe()
                #mid_construction_plane.deleteMe()

                #tmp_end_sketch.deleteMe()
                #end_construction_plane.deleteMe()

                #tmp_sketch.deleteMe()

                i = i + 1
            

            # take the saved rails and the saved circles and create lofts that gouge the surface
                


            # add all the saved rails (NURBs curves) and put them into the rail sketch                
            #for r in saved_rails:
            #    rail_sketch.sketchCurves.sketchFixedSplines.addByNurbsCurve (r)

            debug_print (f'rail sketch has {rail_sketch.sketchCurves.count} curve(s)')
            debug_print (f'circles sketch has {circles_sketch.sketchCurves.count} curve(s)')
            debug_print (f'circles sketch has {circles_sketch.profiles.count} profile(s)')

            i = 0
            for r in rail_sketch.sketchCurves.sketchFixedSplines:

                # define the input for a solid loft that gouges the surface
                solid_loft_features = parent_component.features.loftFeatures
                solid_loft_input = solid_loft_features.createInput(adsk.fusion.FeatureOperations.CutFeatureOperation)
                solid_loft_input.isSolid = True

                tmp_start_sketch = sketches.itemByName (f'tmp start sketch {i}')
                tmp_mid_sketch = sketches.itemByName (f'tmp mid sketch {i}')
                tmp_end_sketch = sketches.itemByName (f'tmp end sketch {i}')
                start_circle_profile = tmp_start_sketch.profiles.item(0)
                middle_circle_profile = tmp_mid_sketch.profiles.item(0)
                end_circle_profile = tmp_end_sketch.profiles.item(0)

                solid_loft_sections = solid_loft_input.loftSections
                solid_loft_sections.add(start_circle_profile)
                solid_loft_sections.add(middle_circle_profile)
                solid_loft_sections.add(end_circle_profile)

                if use_rail:
                    #solid_loft_input.centerLineOrRails.addCenterLine (r)
                    solid_loft_input.centerLineOrRails.addRail (r)

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
