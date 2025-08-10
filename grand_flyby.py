import bpy
import math
import random
from mathutils import Vector

# -----------------------------
# Scene controls
# -----------------------------
SCENE_NAME      = "GrandFlyBy"
USE_EEVEE       = True
FRAME_START     = 1
FRAME_END       = 600
FPS             = 24
RENDER_RES      = (1920, 1080)

SUN_LOC         = Vector((0, 0, 0))
SUN_RADIUS      = 8.0
SUN_TEMP_K      = 6500

GAS_GIANT_LOC   = Vector((40, 10, -5))
GAS_GIANT_RADIUS= 6.0

ICE_PLANET_LOC  = Vector((-60, -20, 15))
ICE_PLANET_RADIUS= 4.0

ASTEROID_COUNT  = 250
ASTEROID_RING_IN= 30.0
ASTEROID_RING_OUT=60.0

NEBULA_SIZE     = 600.0
NEBULA_DENSITY  = 0.01

STAR_SCALE      = 600.0
STAR_SPREAD     = 0.003

# -----------------------------
# Helpers
# -----------------------------
def safe_set(obj, prop, value):
    if hasattr(obj, prop):
        try:
            setattr(obj, prop, value)
        except Exception:
            pass

def clean_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False, confirm=False)
    w = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)

# -----------------------------
# Build starfield world
# -----------------------------
def build_starfield_world(world, star_scale=STAR_SCALE, star_spread=STAR_SPREAD):
    nt = world.node_tree
    nodes, links = nt.nodes, nt.links

    out = nodes.new("ShaderNodeOutputWorld")
    bg_black = nodes.new("ShaderNodeBackground")
    bg_black.inputs["Color"].default_value = (0, 0, 0, 1)
    bg_black.inputs["Strength"].default_value = 1.0

    mix = nodes.new("ShaderNodeMixShader")
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = (1, 1, 1, 1)
    emission.inputs["Strength"].default_value = 4.0

    vor = nodes.new("ShaderNodeTexVoronoi")
    vor.feature = 'F1'
    vor.distance = 'EUCLIDEAN'
    vor.inputs["Scale"].default_value = star_scale

    cramp = nodes.new("ShaderNodeValToRGB")
    cramp.color_ramp.elements[0].position = star_spread
    cramp.color_ramp.elements[0].color = (0, 0, 0, 1)
    cramp.color_ramp.elements[1].position = star_spread + 0.015
    cramp.color_ramp.elements[1].color = (1, 1, 1, 1)

    texcoord = nodes.new("ShaderNodeTexCoord")
    power = nodes.new("ShaderNodeMath")
    power.operation = 'POWER'
    power.inputs[1].default_value = 6.5

    links.new(texcoord.outputs["Generated"], vor.inputs["Vector"])
    links.new(vor.outputs["Distance"], cramp.inputs["Fac"])
    links.new(cramp.outputs["Color"], power.inputs[0])
    links.new(power.outputs["Value"], mix.inputs["Fac"])
    links.new(bg_black.outputs["Background"], mix.inputs[1])
    links.new(emission.outputs["Emission"], mix.inputs[2])
    links.new(mix.outputs["Shader"], out.inputs["Surface"])

# -----------------------------
# Planet helpers
# -----------------------------
def add_uv_sphere(name, radius, location):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=128, ring_count=64, radius=radius, location=location)
    obj = bpy.context.active_object
    obj.name = name
    bpy.ops.object.shade_smooth()
    return obj

# Gas giant material with bands

def gas_giant_material():
    mat = bpy.data.materials.new("GasGiant")
    mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    for n in list(nodes):
        nodes.remove(n)
    out = nodes.new("ShaderNodeOutputMaterial")
    princ = nodes.new("ShaderNodeBsdfPrincipled")
    texcoord = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 3.0
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.6, 0.3, 0.1, 1)
    ramp.color_ramp.elements[1].color = (0.9, 0.6, 0.2, 1)
    links.new(texcoord.outputs["Object"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], princ.inputs["Base Color"])
    links.new(princ.outputs["BSDF"], out.inputs["Surface"])
    return mat

# Ice planet material

def ice_planet_material():
    mat = bpy.data.materials.new("IcePlanet")
    mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    for n in list(nodes):
        nodes.remove(n)
    out = nodes.new("ShaderNodeOutputMaterial")
    princ = nodes.new("ShaderNodeBsdfPrincipled")
    texcoord = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 12.0
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.05, 0.1, 0.2, 1)
    ramp.color_ramp.elements[1].color = (0.7, 0.9, 1.0, 1)
    links.new(texcoord.outputs["Object"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], princ.inputs["Base Color"])
    links.new(princ.outputs["BSDF"], out.inputs["Surface"])
    return mat

# Asteroid material

def asteroid_material():
    mat = bpy.data.materials.new("Asteroid")
    mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    for n in list(nodes):
        nodes.remove(n)
    out = nodes.new("ShaderNodeOutputMaterial")
    princ = nodes.new("ShaderNodeBsdfPrincipled")
    princ.inputs["Base Color"].default_value = (0.2, 0.2, 0.22, 1)
    princ.inputs["Roughness"].default_value = 1.0
    links.new(princ.outputs["BSDF"], out.inputs["Surface"])
    return mat

# Sun

def add_sun(name, radius, location, kelvin):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=96, ring_count=48, radius=radius, location=location)
    sun = bpy.context.active_object
    sun.name = name
    bpy.ops.object.shade_smooth()
    mat = bpy.data.materials.new(name + "_Mat")
    mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    for n in list(nodes):
        nodes.remove(n)
    out = nodes.new("ShaderNodeOutputMaterial")
    emit = nodes.new("ShaderNodeEmission")
    bb = nodes.new("ShaderNodeBlackbody")
    bb.inputs["Temperature"].default_value = kelvin
    emit.inputs["Strength"].default_value = 15.0
    links.new(bb.outputs["Color"], emit.inputs["Color"])
    links.new(emit.outputs["Emission"], out.inputs["Surface"])
    sun.data.materials.append(mat)
    return sun

# Nebula volume

def nebula_cube(size, density=NEBULA_DENSITY):
    bpy.ops.mesh.primitive_cube_add(size=size, location=(0,0,0))
    cube = bpy.context.active_object
    cube.name = "Nebula"
    mat = bpy.data.materials.new("NebulaVolume")
    mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    for n in list(nodes):
        nodes.remove(n)
    out = nodes.new("ShaderNodeOutputMaterial")
    pvol = nodes.new("ShaderNodeVolumePrincipled")
    pvol.inputs["Density"].default_value = density
    pvol.inputs["Anisotropy"].default_value = 0.3
    texcoord = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 1.0
    noise.inputs["Detail"].default_value = 8.0
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.3
    ramp.color_ramp.elements[0].color = (0,0,0,1)
    ramp.color_ramp.elements[1].position = 0.7
    ramp.color_ramp.elements[1].color = (0.8,0.2,0.9,1)
    mult = nodes.new("ShaderNodeMath")
    mult.operation = 'MULTIPLY'
    mult.inputs[1].default_value = 2.0
    links.new(texcoord.outputs["Object"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], pvol.inputs["Color"])
    links.new(noise.outputs["Fac"], mult.inputs[0])
    links.new(mult.outputs["Value"], pvol.inputs["Emission Strength"])
    links.new(pvol.outputs["Volume"], out.inputs["Volume"])
    cube.data.materials.append(mat)
    safe_set(cube, "display_type", 'WIRE')
    return cube

# Asteroid field

def add_asteroid_field(count, inner, outer):
    mat = asteroid_material()
    for i in range(count):
        r = random.uniform(inner, outer)
        ang = random.uniform(0, 2*math.pi)
        z = random.uniform(-5, 5)
        loc = Vector((r*math.cos(ang), r*math.sin(ang), z))
        size = random.uniform(0.2, 0.8)
        bpy.ops.mesh.primitive_ico_sphere_add(radius=size, location=loc, subdivisions=1)
        rock = bpy.context.active_object
        rock.data.materials.append(mat)
        bpy.ops.object.shade_flat()

# -----------------------------
# Camera path
# -----------------------------
def build_camera_path(start, mid, end):
    bpy.ops.curve.primitive_bezier_curve_add(location=start)
    path = bpy.context.active_object
    path.name = "FlyPath"
    spline = path.data.splines[0]
    spline.bezier_points[0].co = start
    spline.bezier_points[0].handle_left_type = 'AUTO'
    spline.bezier_points[0].handle_right_type = 'AUTO'
    spline.bezier_points.add(1)
    spline.bezier_points[1].co = mid
    spline.bezier_points[1].handle_left_type = 'AUTO'
    spline.bezier_points[1].handle_right_type = 'AUTO'
    spline.bezier_points.add(1)
    spline.bezier_points[2].co = end
    spline.bezier_points[2].handle_left_type = 'AUTO'
    spline.bezier_points[2].handle_right_type = 'AUTO'
    path.data.resolution_u = 64
    path.data.use_path = True
    path.data.path_duration = FRAME_END
    return path

# -----------------------------
# Build scene
# -----------------------------
clean_scene()
scene = bpy.context.scene
scene.name = SCENE_NAME
scene.frame_start = FRAME_START
scene.frame_end   = FRAME_END
scene.render.fps  = FPS
scene.render.resolution_x, scene.render.resolution_y = RENDER_RES

# Engine
engine_items = {e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items}
EEVEE_ID = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in engine_items else (
           'BLENDER_EEVEE' if 'BLENDER_EEVEE' in engine_items else None)
if USE_EEVEE and EEVEE_ID:
    scene.render.engine = EEVEE_ID
    ee = scene.eevee
    safe_set(ee, "use_bloom", True)
    safe_set(ee, "bloom_intensity", 0.05)
    safe_set(ee, "volumetric_end", NEBULA_SIZE*1.5)
else:
    scene.render.engine = 'CYCLES'

# World
build_starfield_world(scene.world)

# Objects
sun = add_sun("Sun", SUN_RADIUS, SUN_LOC, SUN_TEMP_K)

gas = add_uv_sphere("GasGiant", GAS_GIANT_RADIUS, GAS_GIANT_LOC)
gas.data.materials.append(gas_giant_material())

ice = add_uv_sphere("IcePlanet", ICE_PLANET_RADIUS, ICE_PLANET_LOC)
ice.data.materials.append(ice_planet_material())

add_asteroid_field(ASTEROID_COUNT, ASTEROID_RING_IN, ASTEROID_RING_OUT)
nebula = nebula_cube(NEBULA_SIZE)

# Camera
bpy.ops.object.camera_add(location=(-120, -80, 40))
cam = bpy.context.active_object
cam.name = "GrandCamera"
path = build_camera_path(Vector((-120, -80, 40)), Vector((-20, 30, 15)), Vector((90, 0, -20)))

constraint = cam.constraints.new('FOLLOW_PATH')
constraint.target = path
constraint.use_fixed_location = True
constraint.offset_factor = 0.0
constraint.keyframe_insert(data_path="offset_factor", frame=FRAME_START)
constraint.offset_factor = 1.0
constraint.keyframe_insert(data_path="offset_factor", frame=FRAME_END)

# Depth of field
safe_set(cam.data.dof, "use_dof", True)
safe_set(cam.data.dof, "focus_distance", 50.0)

print("\u2705 Grand fly-by scene built. Play timeline to preview.")
