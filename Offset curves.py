# Author- Carl Bass
# Description- make surface gouges

# To Do
#Circle should be made after line is lofted. 
#Centerpoint where lower curve intersects sketch plane
#Make sketch out of sweep curve


import adsk.core, adsk.fusion, adsk.cam, traceback
import os
import math

# Global list to keep all event handlers in scope.
handlers = []

# global variables available in all functions
app = adsk.core.Application.get()
ui  = app.userInterface

# global variables because I can't find a better way to pass this info around -- would be nice if fusion api had some cleaner way to do this
debug = False
gouge_surface = False
tool_diameter = 0.1

def run(context):
    
    try:

        # Find where the python file lives and look for the icons in the ./.resources folder
        python_file_folder = os.path.dirname(os.path.realpath(__file__))
        resource_folder = os.path.join (python_file_folder, '.resources')

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
        inputs.addBoolValueInput('gouge_surface', 'Gouge surface', True, '', False)

        # create debug checkbox widget
        inputs.addBoolValueInput('debug', 'Debug', True, '', False)

# Event handler for the execute event.
class command_executed (adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        global debug
        global gouge_surface
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
                elif (input.id == 'gouge_surface'):
                    gouge_surface = input.value           
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

                (status, start_p, end_p) = curve_evaluator.getParameterExtents()

                # calculate midpoint in parametric space
                midpoint_p = (start_p + end_p) * 0.5

                # calculate midpoint in world coordinates
                midpoint_wc = adsk.core.Point3D.create ()                    
                (status, midpoint_wc) = curve_evaluator.getPointAtParameter(midpoint_p)
                                            
                # get endpoints in world coordinates
                (status, start_point_wc, end_point_wc) = curve_evaluator.getEndPoints()
                debug_print (f'start (wc) = {start_point_wc.x:.3f}, {start_point_wc.y:.3f}, {start_point_wc.z:.3f}')
                debug_print (f'end (wc) = {end_point_wc.x:.3f}, {end_point_wc.y:.3f}, {end_point_wc.z:.3f}')

                # get normal to surface at middle of curve
                (status, normal) = face_evaluator.getNormalAtPoint (midpoint_wc)

                # figure out depth of cut
                gouge_vector = adsk.core.Vector3D.create ()   
                
                gouge_vector.x = -normal.x * tool_diameter * 0.5
                gouge_vector.y = -normal.y * tool_diameter * 0.5
                gouge_vector.z = -normal.z * tool_diameter * 0.5
                
                # get construction planes collection
                construction_planes = root_component.constructionPlanes
                plane_input = construction_planes.createInput()

                # create construction plane at p = 0.5 on original curve
                distance = adsk.core.ValueInput.createByReal (0.5)
                status = plane_input.setByDistanceOnPath(spline, distance)

                # change default name of construction plane
                construction_plane = construction_planes.add (plane_input)
                construction_plane.name = f'midplane {i}'

                cp_normal = construction_plane.geometry.normal

                dot = cp_normal.dotProduct (normal)
                debug_print (f'dot between contruction plane normal and surface normal = {dot:.3f}')

                # create and name a new sketch on the newly created construction plane
                loft_sketch = sketches.add (construction_plane)
                loft_sketch.name = f'loft sketch {i}'

                sketch_points = loft_sketch.sketchPoints
                sketch_lines = loft_sketch.sketchCurves.sketchLines

                offset_point_wc = adsk.core.Point3D.create ()                    
                offset_point_wc.x = midpoint_wc.x + gouge_vector.x 
                offset_point_wc.y = midpoint_wc.y + gouge_vector.y 
                offset_point_wc.z = midpoint_wc.z + gouge_vector.z 

                offset_point_sketch = loft_sketch.modelToSketchSpace (offset_point_wc)

                # convert endpoints from model coordinates to sketch coordinates
                start_point_sketch = loft_sketch.modelToSketchSpace (start_point_wc)
                end_point_sketch = loft_sketch.modelToSketchSpace (end_point_wc)

                # add these two points as sketch points so they can be used in lofting a spline
                sketch_point_start = sketch_points.add (start_point_sketch)
                sketch_point_end = sketch_points.add (end_point_sketch)

                # show the gouge vector
                gouge_pt_wc = adsk.core.Point3D.create ()                    
                gouge_pt_wc.x = midpoint_wc.x + gouge_vector.x
                gouge_pt_wc.y = midpoint_wc.y + gouge_vector.y
                gouge_pt_wc.z = midpoint_wc.z + gouge_vector.z

                midpoint_sketch = loft_sketch.modelToSketchSpace (midpoint_wc)
                gouge_pt_sketch = loft_sketch.modelToSketchSpace (gouge_pt_wc)             
                gouge_line = sketch_lines.addByTwoPoints(midpoint_sketch, gouge_pt_sketch)


                # Define the input for a surface loft
                loft_features = root_component.features.loftFeatures
                loft_input = loft_features.createInput(adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
                loft_input.isSolid = False

                loft_sections = loft_input.loftSections
                loft_sections.add(sketch_point_start)
                loft_sections.add(gouge_line)
                loft_sections.add(sketch_point_end)
                
                loft_input.isClosed = False

                loft_input.centerLineOrRails.addRail (spline)

                # create the loft
                loft_feature = loft_features.add(loft_input)
                
                if gouge_surface:
                    loft_faces = loft_feature.faces
                    
                    loft_face = loft_faces.item(0)

                    # create toolpath sketch
                    toolpath_sketch = sketches.add (construction_plane)
                    toolpath_sketch.name = f'toolpath {i}'
                    sweep_include = toolpath_sketch.include (loft_face)
                    
                    debug_print (f'sweep include count: {sweep_include.count}')
                    debug_print (f'toolpath count: {toolpath_sketch.sketchCurves.count}')

                    s0 = toolpath_sketch.sketchCurves.item(0)
                    s1 = toolpath_sketch.sketchCurves.item(1)

                    debug_print (f's0 = {s0.objectType}')
                    debug_print (f's1 = {s1.objectType}')

                    # find distances from the curves to point at bottom of gouge at the midpoint
                    s0_distance = app.measureManager.measureMinimumDistance (s0, offset_point_wc).value
                    s1_distance = app.measureManager.measureMinimumDistance (s1, offset_point_wc).value

                    debug_print (f's0 distance = {s0_distance}')
                    debug_print (f's1 distance = {s1_distance}')

                    # find correct curve and delete other
                    if  s0_distance < s1_distance:
                        s1.deleteMe()
                        debug_print ('delete s1')
                        sweep_path = root_component.features.createPath (s0, False)
                    else:
                        s0.deleteMe()
                        debug_print ('delete s0')
                        sweep_path = root_component.features.createPath (s1, False)

                    debug_print (f'toolpath count: {toolpath_sketch.sketchCurves.count}')

                    debug_print(f's0 {s0.isValid}')
                    debug_print(f's1 {s1.isValid}')
                    debug_print(f'sweep path type{sweep_path.objectType} {sweep_path.isValid} {sweep_path.count}')


                    circle_sketch = sketches.add (construction_plane)
                    circle_sketch.name = f'circle {i}'

                    midpoint_circle_sketch = circle_sketch.modelToSketchSpace (midpoint_wc)
                    circle_sketch.sketchCurves.sketchCircles.addByCenterRadius (midpoint_circle_sketch, tool_diameter * 0.5)

                    sweep_profile = circle_sketch.profiles.item(0)

                    sweeps = root_component.features.sweepFeatures
                    
                    # set up the sweep inputs
                    sweep_input = sweeps.createInput(sweep_profile, sweep_path, adsk.fusion.FeatureOperations.CutFeatureOperation)
                    sweep_input.isChainSelection = False
                    sweep_input.extent = 0 #adsk.fusion.SweepExtentTypes.PerpendicularToPathExtentType

                    # limit which bodies are cut
                    participant_bodies = []
                    participant_bodies.append (parent_body)
                    sweep_input.participantBodies = participant_bodies

                    # Create the sweep
                    sweep = sweeps.add (sweep_input)

                i = i + 1
        except:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))	


def debug_print (msg):
    if debug:
        text_palette = ui.palettes.itemById('TextCommands')
        text_palette.writeText (msg)
        
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



# loft point-gouge vector-point to form surface
# find intersection of sweep curve with construction plane
#entities = []
#entities.append (sweep_edge)
#intersection_pts = loft_sketch.intersectWithSketchPlane (entities)
#if intersection_pts.count == 1:
#    intersection_pt = intersection_pts[0]