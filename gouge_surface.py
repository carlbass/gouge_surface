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
gouge_surface = True
tool_diameter = 0.25
tool_radius = tool_diameter * 0.5

def run(context):
    
    try:

        # Find where the python file lives and look for the icons in the ./.resources folder
        python_file_folder = os.path.dirname(os.path.realpath(__file__))
        resource_folder = os.path.join (python_file_folder, 'resources')
        resource_folder =''

        # Get the CommandDefinitions collection so we can add a command
        command_definitions = ui.commandDefinitions
        
        tooltip = 'Maps lines, arcs and fitted splines from sketch to surface'

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

            origin = adsk.core.Point3D.create (0.0, 0.0, 0.0)                    

            i = 0
            
            for spline in sketch_fixed_splines:
                debug_print (f'Processing spline {i}')


                tmp_sketch = sketches.add (parent_component.xYConstructionPlane)
                tmp_sketch.name = f'tmp sketch {i}'

                # get the evaluator for this curve
                curve_evaluator = spline.evaluator

                # get the parametric endpoints
                (status, start_p, end_p) = curve_evaluator.getParameterExtents()                

                # calculate mid_point in cartesian space
                (status, length) = curve_evaluator.getLengthAtParameter (start_p, end_p)
                (status, mid_p) = curve_evaluator.getParameterAtLength (start_p, length * 0.5)
                debug_print (f'p = {start_p:.2f} to {mid_p:.2f} to {end_p:.2f}')

                # convert parameter into cartesian coordinates for all three points
                (status, mid_p0) = curve_evaluator.getPointAtParameter (mid_p)

                # get endpoints in cartesian coordinates
                (status, start_p0, end_p0) = curve_evaluator.getEndPoints()
                debug_print_point ('start_p0', start_p0)
                debug_print_point ('mid p0', mid_p0)
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
                
                # scale endpoint normals by tool radius -- then circular profiles should be centered on end of these scaled normals and the toolpath curve should be tangent to the circle
                start_normal.scaleBy (tool_diameter)
                end_normal.scaleBy (tool_diameter)
                
                # this is the bottom of the gouge at the parametric midpoint
                # p0 will be on the orginal surface curve
                # p1 will be above for the endpoints and below for the midpoint
                # p2 will be above for midpoint since we need it for defining middle circular profile

                # point in middle of curve at depth of gouge
                mid_p1 = adsk.core.Point3D.create ()                    
                mid_p1.x = mid_p0.x + gouge_vector.x 
                mid_p1.y = mid_p0.y + gouge_vector.y 
                mid_p1.z = mid_p0.z + gouge_vector.z 

                # point in middle of curve one diameter above the bottom of the gouge
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

                # need to ensure tangent point is on curve
                # add the toolpath curve to the rail sketch
                toolpath = rail_sketch.sketchCurves.sketchFixedSplines.addByNurbsCurve (saved_rails[i])

                (status, toolpath_start, toolpath_end) = toolpath.evaluator.getEndPoints()
                debug_print_point ('toolpath_start', toolpath_start)
                debug_print_point ('toolpath_end', toolpath_end)


                surface_loft_feature.deleteMe()

                # make three temporary construction planes and sketches along the path

                # create construction plane at beginning and end of path
                plane_input.setByDistanceOnPath (toolpath, adsk.core.ValueInput.createByReal(0.0))
                start_construction_plane = construction_planes.add (plane_input)
                start_construction_plane.name = (f'start {i}')

                # create construction plane at beginning of path
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
                x_direction = start_sketch.xDirection
                debug_print_point ('x direction: ', x_direction)
                y_direction = start_sketch.yDirection
                debug_print_point ('y direction: ', y_direction)
                implied_z_vector = x_direction.crossProduct(y_direction)
                debug_print_point ('cross: ', implied_z_vector)
                debug_print_point ('sketch normal ', start_sketch.referencePlane.geometry.normal)
                

                mid_sketch = sketches.add (mid_construction_plane)
                mid_sketch.name = f'mid sketch {i}'

                end_sketch = sketches.add (end_construction_plane)
                end_sketch.name = f'end sketch {i}'

                mid_p0_tmp = tmp_sketch.modelToSketchSpace (mid_p0)
                mid_p2_tmp = tmp_sketch.modelToSketchSpace (mid_p2)

                end_p0_tmp = tmp_sketch.modelToSketchSpace (end_p0)
                end_p1_tmp = tmp_sketch.modelToSketchSpace (end_p1)


                # add the circles at the three points and include the three circles into circles sketch

                # add circle at start of curve
                start_p0_local = start_sketch.modelToSketchSpace (start_p0)
                start_p1_local = start_sketch.modelToSketchSpace (start_p1)
                start_p0_local.z = 0.0
                start_p1_local.z = 0.0

                start_sketch.sketchPoints.add (start_p0_local)
                start_sketch.sketchPoints.add (start_p1_local)

                debug_print_point ('start p0 local', start_p0_local)
                debug_print_point ('start p1 local', start_p1_local)
                check_distance = app.measureManager.measureMinimumDistance (toolpath, start_p0).value
                debug_print (f'start_p0 to toolpath: {check_distance:.4f}')  


                #tmp_circle = start_sketch.sketchCurves.sketchCircles.addByCenterRadius (start_p1_local, tool_radius)
                tmp_circle = start_sketch.sketchCurves.sketchCircles.addByTwoPoints (start_p0_local, start_p1_local)
                check_distance = app.measureManager.measureMinimumDistance (toolpath, tmp_circle).value
                debug_print (f'start circle to toolpath: {check_distance:.4f}')                
                check_distance = app.measureManager.measureMinimumDistance (toolpath, start_sketch.originPoint.geometry).value
                debug_print (f'sketch origin to toolpath: {check_distance:.4f}')

                # convert to sketch coordinates before using to define middle circle
                mid_p1_local = mid_sketch.modelToSketchSpace (mid_p1)
                mid_p2_local = mid_sketch.modelToSketchSpace (mid_p2)                

                entities = []
                entities.append (toolpath)

                # intersection should be a single sketch point; could be multiple if curve wraps has high curvature
                sketch_entities = mid_sketch.intersectWithSketchPlane(entities)

                debug_print_point ('intersection pt', sketch_entities[0].geometry)

                #tmp_circle = mid_sketch.sketchCurves.sketchCircles.addByTwoPoints (mid_p2_local, sketch_entities[0].geometry)
                tmp_circle = mid_sketch.sketchCurves.sketchCircles.addByTwoPoints (mid_sketch.originPoint.geometry, mid_p2_local)
                check_distance = app.measureManager.measureMinimumDistance (toolpath, tmp_circle).value
                debug_print (f'mid circle to toolpath: {check_distance:.4f}')

                #check_distance = app.measureManager.measureMinimumDistance (tmp_circle, mid_p1).value

                end_p0_local = end_sketch.modelToSketchSpace (end_p0)
                end_p1_local = end_sketch.modelToSketchSpace (end_p1)
                end_p0_local.z = 0.0
                end_p1_local.z = 0.0

                tmp_circle = end_sketch.sketchCurves.sketchCircles.addByTwoPoints (end_sketch.originPoint.geometry, end_p1_local)
                check_distance = app.measureManager.measureMinimumDistance (toolpath, tmp_circle).value
                debug_print (f'end circle to toolpath: {check_distance:.4f}')

                tmp_sketch.deleteMe()

                i = i + 1
            

            # take the saved rails and the circles in the sketches to create lofts that gouge the surface
                
            debug_print (f'rail sketch has {rail_sketch.sketchCurves.count} curve(s)')

            i = 0
            for r in rail_sketch.sketchCurves.sketchFixedSplines:
                    
                debug_print ('------------------------------------')

                debug_print (f'gouging along spline {i}')

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

                # not sure which is better to use; interactively it suggests center line if you have one rail

                #solid_loft_input.centerLineOrRails.addCenterLine (r)
                solid_loft_input.centerLineOrRails.addRail (r)

                participant_bodies = []
                participant_bodies.append (parent_body)
                solid_loft_input.participantBodies = participant_bodies

                if gouge_surface:               
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
        text_palette.writeText (f'{msg}, ({point.x:.3f}, {point.y:.3f}, {point.z:.3f})')
        
def stop(context):
    try:

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
