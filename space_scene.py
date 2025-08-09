# Blender 4.5.1 LTS — Eevee Next compatible rich space scene builder
# Builds a procedural starfield, Earth-like planet with rings and moon, gas giant,
# asteroid belt, glowing sun, volumetric nebula, and animated camera fly-through.
# Robust to Blender 4.x changes: engine id, Principled BSDF renames, Eevee props.

import bpy
import math
import random
from mathutils import Vector, Euler

# -----------------------------
# Quick controls
# -----------------------------
SCENE_NAME      = "SpaceFlythrough"
USE_EEVEE       = True         # True = Eevee Next, False = Cycles
FRAME_START     = 1
FRAME_END       = 300
FPS             = 24
RENDER_RES      = (1920, 1080)

PLANET_LOC      = Vector((0, 0, 0))
PLANET_RADIUS   = 2.0

RING_INNER      = 3.0
RING_OUTER      = 5.5

MOON_RADIUS     = 0.6
MOON_DISTANCE   = 4.0  # from planet center

GAS_GIANT_LOC   = Vector((-14, 10, -3))
GAS_GIANT_RADIUS = 4.0

SUN_LOC         = Vector((15, -8, 6))
SUN_RADIUS      = 2.5
SUN_TEMP_K      = 5800

ASTEROID_COUNT  = 300
ASTEROID_INNER  = 10.0
ASTEROID_OUTER  = 18.0
ASTEROID_Z      = 1.5

NEBULA_SIZE     = 120.0
NEBULA_DENSITY  = 0.03

STAR_SCALE      = 300.0   # star density
STAR_SPREAD     = 0.005   # lower = more stars

CAMERA_START    = Vector((-25, -18, 6))
CAMERA_END      = Vector((6, 4, 2))
FOCUS_TARGET    = Vector((0, 0, 0))

# -----------------------------
# Small helpers
# -----------------------------
def safe_set(obj, prop, value):
    """Set an attribute only if it exists (prevents AttributeError)."""
    if hasattr(obj, prop):
        try:
            setattr(obj, prop, value)
        except Exception:
            pass

def set_input(node, names, value):
    """Set a socket by trying multiple possible names (BSDF rename compatibility)."""
    for name in names:
        sock = node.inputs.get(name)
        if sock is not None:
            try:
                sock.default_value = value
            except Exception:
                pass
            return

def clean_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False, confirm=False)
    # reset world
    w = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)

# -----------------------------
# Build
# -----------------------------
clean_scene()
scene = bpy.context.scene
scene.name = SCENE_NAME
scene.frame_start = FRAME_START
scene.frame_end   = FRAME_END
scene.render.fps  = FPS
scene.render.resolution_x, scene.render.resolution_y = RENDER_RES

# Engine selection (works on 3.x/4.x, Eevee Next if available)
engine_items = {e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items}
EEVEE_ID = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in engine_items else (
           'BLENDER_EEVEE' if 'BLENDER_EEVEE' in engine_items else None)

if USE_EEVEE and EEVEE_ID:
    scene.render.engine = EEVEE_ID
    ee = scene.eevee
    # Only set if present in this build:
    safe_set(ee, "use_bloom", True)
    safe_set(ee, "bloom_intensity", 0.04)
    safe_set(ee, "use_gtao", True)
    safe_set(ee, "volumetric_end", NEBULA_SIZE * 1.2)
    safe_set(ee, "volumetric_start", 0.1)
else:
    scene.render.engine = 'CYCLES'
    safe_set(scene.cycles, "samples", 128)
    safe_set(scene.cycles, "use_adaptive_sampling", True)

# -----------------------------
# World: starfield (procedural)
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
    emission.inputs["Strength"].default_value = 3.0

    vor = nodes.new("ShaderNodeTexVoronoi")
    vor.feature = 'F1'
    vor.distance = 'EUCLIDEAN'
    vor.inputs["Scale"].default_value = star_scale

    cramp = nodes.new("ShaderNodeValToRGB")
    cramp.color_ramp.elements[0].position = star_spread
    cramp.color_ramp.elements[0].color = (0, 0, 0, 1)
    cramp.color_ramp.elements[1].position = star_spread + 0.02
    cramp.color_ramp.elements[1].color = (1, 1, 1, 1)

    texcoord = nodes.new("ShaderNodeTexCoord")
    power = nodes.new("ShaderNodeMath")
    power.operation = 'POWER'
    power.inputs[1].default_value = 6.0  # sharpen stars

    # links
    links.new(texcoord.outputs["Generated"], vor.inputs["Vector"])
    links.new(vor.outputs["Distance"], cramp.inputs["Fac"])
    links.new(cramp.outputs["Color"], power.inputs[0])
    links.new(power.outputs["Value"], mix.inputs["Fac"])
    links.new(bg_black.outputs["Background"], mix.inputs[1])
    links.new(emission.outputs["Emission"], mix.inputs[2])
    links.new(mix.outputs["Shader"], out.inputs["Surface"])

build_starfield_world(scene.world)

# -----------------------------
# Mesh helpers
# -----------------------------
def add_uv_sphere(name, radius, location):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=128, ring_count=64, radius=radius, location=location)
    obj = bpy.context.active_object
    obj.name = name
    bpy.ops.object.shade_smooth()
    return obj

# -----------------------------
# Planet material (no Musgrave; 4.x-safe sockets)
# -----------------------------
def planet_material():
    mat = bpy.data.materials.new("PlanetProcedural")
    mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links

    # clean
    for n in list(nodes):
        nodes.remove(n)
    out = nodes.new("ShaderNodeOutputMaterial")

    princ = nodes.new("ShaderNodeBsdfPrincipled")
    set_input(princ, ["Specular", "Specular IOR Level"], 0.35)  # 4.x renamed
    set_input(princ, ["Roughness"], 0.6)

    texcoord = nodes.new("ShaderNodeTexCoord")
    mapping  = nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (1.0, 1.0, 1.0)

    # Continents (large noise) -> land/sea
    noise_cont = nodes.new("ShaderNodeTexNoise")
    noise_cont.inputs["Scale"].default_value = 5.0
    noise_cont.inputs["Detail"].default_value = 8.0
    noise_cont.inputs["Roughness"].default_value = 0.5

    ramp_landsea = nodes.new("ShaderNodeValToRGB")
    ramp_landsea.color_ramp.elements[0].position = 0.48
    ramp_landsea.color_ramp.elements[0].color = (0.07, 0.14, 0.25, 1)  # ocean
    ramp_landsea.color_ramp.elements[1].position = 0.55
    ramp_landsea.color_ramp.elements[1].color = (0.18, 0.32, 0.07, 1)  # land

    # Fine detail for roughness/bump
    noise_detail = nodes.new("ShaderNodeTexNoise")
    noise_detail.inputs["Scale"].default_value = 35.0
    noise_detail.inputs["Detail"].default_value = 4.0
    noise_detail.inputs["Roughness"].default_value = 0.6

    # Patchiness variation via Voronoi
    vor = nodes.new("ShaderNodeTexVoronoi")
    vor.feature = 'F1'
    vor.distance = 'EUCLIDEAN'
    vor.inputs["Scale"].default_value = 12.0

    mix_rough = nodes.new("ShaderNodeMixRGB")
    mix_rough.blend_type = 'MULTIPLY'
    mix_rough.inputs["Fac"].default_value = 0.6

    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.5
    bump.inputs["Distance"].default_value = 0.1

    mix_height = nodes.new("ShaderNodeMath")
    mix_height.operation = 'MULTIPLY'

    # links
    links.new(texcoord.outputs["Object"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], noise_cont.inputs["Vector"])
    links.new(mapping.outputs["Vector"], noise_detail.inputs["Vector"])
    links.new(mapping.outputs["Vector"], vor.inputs["Vector"])

    links.new(noise_cont.outputs["Fac"], ramp_landsea.inputs["Fac"])
    links.new(ramp_landsea.outputs["Color"], princ.inputs["Base Color"])

    links.new(noise_detail.outputs["Fac"], mix_rough.inputs["Color1"])
    links.new(vor.outputs["Distance"],   mix_rough.inputs["Color2"])
    links.new(mix_rough.outputs["Color"], princ.inputs["Roughness"])

    links.new(noise_cont.outputs["Fac"], mix_height.inputs[0])
    links.new(noise_detail.outputs["Fac"], mix_height.inputs[1])
    links.new(mix_height.outputs["Value"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], princ.inputs["Normal"])

    links.new(princ.outputs["BSDF"], out.inputs["Surface"])
    return mat

planet = add_uv_sphere("Planet", PLANET_RADIUS, PLANET_LOC)
planet.data.materials.append(planet_material())

# -----------------------------
# Rings (banded disc with transparency)
# -----------------------------
def create_ring_mesh(name, r_inner, r_outer, z=0.0):
    # Create thin outer disc
    bpy.ops.mesh.primitive_cylinder_add(vertices=256, radius=r_outer, depth=0.01, location=(0, 0, z))
    outer = bpy.context.active_object
    outer.name = name

    # Inner subtraction
    bpy.ops.mesh.primitive_cylinder_add(vertices=256, radius=r_inner, depth=0.02, location=(0, 0, z))
    inner = bpy.context.active_object
    inner.name = name + "_inner"

    # Boolean
    bool_mod = outer.modifiers.new("RingHole", 'BOOLEAN')
    bool_mod.operation = 'DIFFERENCE'
    bool_mod.solver = 'FAST'
    bool_mod.object = inner
    bpy.context.view_layer.objects.active = outer
    bpy.ops.object.modifier_apply(modifier=bool_mod.name)

    # remove helper
    bpy.data.objects.remove(inner, do_unlink=True)
    bpy.ops.object.shade_smooth()
    return outer

def ring_material():
    mat = bpy.data.materials.new("RingsProcedural")
    mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links

    # clean
    for n in list(nodes):
        nodes.remove(n)
    out = nodes.new("ShaderNodeOutputMaterial")

    princ = nodes.new("ShaderNodeBsdfPrincipled")
    set_input(princ, ["Roughness"], 0.3)
    set_input(princ, ["Specular", "Specular IOR Level"], 0.6)

    texcoord = nodes.new("ShaderNodeTexCoord")
    mapping  = nodes.new("ShaderNodeMapping")
    wave     = nodes.new("ShaderNodeTexWave")
    wave.wave_type = 'RINGS'
    wave.rings_direction = 'X'
    wave.inputs["Scale"].default_value = 50.0
    wave.inputs["Distortion"].default_value = 0.0

    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.46
    ramp.color_ramp.elements[0].color = (0.9, 0.9, 0.95, 1)
    ramp.color_ramp.elements[1].position = 0.54
    ramp.color_ramp.elements[1].color = (0.6, 0.6, 0.7, 1)

    transp = nodes.new("ShaderNodeBsdfTransparent")
    mix_shader = nodes.new("ShaderNodeMixShader")

    # links
    links.new(texcoord.outputs["Object"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], wave.inputs["Vector"])
    links.new(wave.outputs["Color"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], princ.inputs["Base Color"])
    links.new(ramp.outputs["Color"], mix_shader.inputs["Fac"])
    links.new(transp.outputs["BSDF"], mix_shader.inputs[1])
    links.new(princ.outputs["BSDF"], mix_shader.inputs[2])
    links.new(mix_shader.outputs["Shader"], out.inputs["Surface"])

    # Eevee transparency settings — guard properties to avoid AttributeError
    safe_set(mat, "blend_method", 'HASHED')
    safe_set(mat, "shadow_method", 'HASHED')
    return mat

ring = create_ring_mesh("PlanetRings", RING_INNER, RING_OUTER, z=PLANET_LOC.z)
ring.rotation_euler = Euler((math.radians(15), 0, math.radians(25)), 'XYZ')
ring.data.materials.append(ring_material())

# Parent rings to planet
ring.location = planet.location
ring.parent = planet

# -----------------------------
# Moon
# -----------------------------
def moon_material():
    mat = bpy.data.materials.new("MoonMaterial")
    mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    princ = nodes.new("ShaderNodeBsdfPrincipled")
    set_input(princ, ["Base Color"], (0.4, 0.4, 0.42, 1))
    set_input(princ, ["Roughness"], 0.9)
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 25.0
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.4
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], princ.inputs["Normal"])
    links.new(princ.outputs["BSDF"], out.inputs["Surface"])
    return mat

def add_moon(parent, radius, distance):
    bpy.ops.object.empty_add(type='PLAIN_AXES', location=parent.location)
    pivot = bpy.context.active_object
    pivot.name = "MoonPivot"
    bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=radius, location=(parent.location.x + distance, parent.location.y, parent.location.z))
    moon = bpy.context.active_object
    moon.name = "Moon"
    bpy.ops.object.shade_smooth()
    moon.data.materials.append(moon_material())
    moon.parent = pivot
    pivot.parent = parent
    # orbit animation
    pivot.rotation_euler = Euler((0, 0, 0), 'XYZ')
    pivot.keyframe_insert("rotation_euler", frame=FRAME_START)
    pivot.rotation_euler.z = math.radians(360)
    pivot.keyframe_insert("rotation_euler", frame=FRAME_END)
    return moon

moon = add_moon(planet, MOON_RADIUS, MOON_DISTANCE)

# -----------------------------
# Gas giant
# -----------------------------
def gas_giant_material():
    mat = bpy.data.materials.new("GasGiantMaterial")
    mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    princ = nodes.new("ShaderNodeBsdfPrincipled")
    set_input(princ, ["Specular", "Specular IOR Level"], 0.1)
    set_input(princ, ["Roughness"], 0.7)

    texcoord = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    mapping.inputs["Rotation"].default_value = (0, 0, math.radians(90))
    wave = nodes.new("ShaderNodeTexWave")
    wave.wave_type = 'BANDS'
    wave.bands_direction = 'Z'
    wave.inputs["Scale"].default_value = 2.5
    wave.inputs["Distortion"].default_value = 0.4

    ramp = nodes.new("ShaderNodeValToRGB")
    c0 = ramp.color_ramp.elements[0]
    c1 = ramp.color_ramp.elements[1]
    c0.color = (0.8, 0.6, 0.4, 1)
    c1.color = (0.4, 0.3, 0.2, 1)

    links.new(texcoord.outputs["Object"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], wave.inputs["Vector"])
    links.new(wave.outputs["Color"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], princ.inputs["Base Color"])
    links.new(princ.outputs["BSDF"], out.inputs["Surface"])
    return mat

gas_giant = add_uv_sphere("GasGiant", GAS_GIANT_RADIUS, GAS_GIANT_LOC)
    
# tilt
gas_giant.rotation_euler = Euler((math.radians(12), math.radians(8), math.radians(25)), 'XYZ')
gas_giant.data.materials.append(gas_giant_material())

# -----------------------------
# Asteroid belt
# -----------------------------
def asteroid_material():
    mat = bpy.data.materials.new("AsteroidMaterial")
    mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    princ = nodes.new("ShaderNodeBsdfPrincipled")
    set_input(princ, ["Base Color"], (0.25, 0.2, 0.15, 1))
    set_input(princ, ["Roughness"], 0.95)
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 40.0
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.35
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], princ.inputs["Normal"])
    links.new(princ.outputs["BSDF"], out.inputs["Surface"])
    return mat

asteroid_mat = asteroid_material()


def create_asteroid_field(count=ASTEROID_COUNT, inner=ASTEROID_INNER, outer=ASTEROID_OUTER, zrange=ASTEROID_Z):
    asteroids = []
    for i in range(count):
        ang = random.uniform(0, 2*math.pi)
        rad = random.uniform(inner, outer)
        x = PLANET_LOC.x + rad * math.cos(ang)
        y = PLANET_LOC.y + rad * math.sin(ang)
        z = PLANET_LOC.z + random.uniform(-zrange, zrange)
        scale = random.uniform(0.1, 0.4)
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=scale, location=(x, y, z))
        ast = bpy.context.active_object
        ast.name = f"Asteroid_{i:03d}"
        bpy.ops.object.shade_smooth()
        tex = bpy.data.textures.new(f"AstTex_{i}", 'CLOUDS')
        mod = ast.modifiers.new("Displace", 'DISPLACE')
        mod.texture = tex
        mod.strength = scale * 0.5
        bpy.context.view_layer.objects.active = ast
        bpy.ops.object.modifier_apply(modifier=mod.name)
        ast.data.materials.append(asteroid_mat)
        asteroids.append(ast)
    return asteroids

create_asteroid_field()

# -----------------------------
# Sun (emissive sphere + optional point light)
# -----------------------------
def add_sun(name, radius, location, kelvin):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=96, ring_count=48, radius=radius, location=location)
    sun = bpy.context.active_object
    sun.name = name
    bpy.ops.object.shade_smooth()

    mat = bpy.data.materials.new(name + "_Mat")
    mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links

    # clean
    for n in list(nodes):
        nodes.remove(n)
    out = nodes.new("ShaderNodeOutputMaterial")
    emit = nodes.new("ShaderNodeEmission")
    bb   = nodes.new("ShaderNodeBlackbody")
    bb.inputs["Temperature"].default_value = kelvin
    emit.inputs["Strength"].default_value = 10.0  # Eevee Next likes a bit more

    links.new(bb.outputs["Color"], emit.inputs["Color"])
    links.new(emit.outputs["Emission"], out.inputs["Surface"])
    sun.data.materials.append(mat)
    return sun

sun = add_sun("Sun", SUN_RADIUS, SUN_LOC, SUN_TEMP_K)

# Small point light for specular hints
bpy.ops.object.light_add(type='POINT', radius=1.0, location=SUN_LOC)
pt = bpy.context.active_object
safe_set(pt.data, "energy", 1000.0)

# -----------------------------
# Nebula Volume (principled volume)
# -----------------------------
def nebula_cube(size, density=NEBULA_DENSITY):
    bpy.ops.mesh.primitive_cube_add(size=size, location=(0, 0, 0))
    cube = bpy.context.active_object
    cube.name = "Nebula"

    mat = bpy.data.materials.new("NebulaVolume")
    mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links

    # clean
    for n in list(nodes):
        nodes.remove(n)
    out = nodes.new("ShaderNodeOutputMaterial")

    pvol = nodes.new("ShaderNodeVolumePrincipled")
    pvol.inputs["Density"].default_value = density
    pvol.inputs["Anisotropy"].default_value = 0.4

    texcoord = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 1.2
    noise.inputs["Detail"].default_value = 8.0
    noise.inputs["Roughness"].default_value = 0.6

    cramp = nodes.new("ShaderNodeValToRGB")
    cramp.color_ramp.elements[0].position = 0.35
    cramp.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1)
    cramp.color_ramp.elements[1].position = 0.72
    cramp.color_ramp.elements[1].color = (0.6, 0.2, 0.9, 1)  # purple-ish

    mult = nodes.new("ShaderNodeMath"); mult.operation = 'MULTIPLY'
    mult.inputs[1].default_value = 1.5

    # links
    links.new(texcoord.outputs["Object"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], cramp.inputs["Fac"])
    links.new(cramp.outputs["Color"], pvol.inputs["Color"])
    links.new(noise.outputs["Fac"], mult.inputs[0])
    links.new(mult.outputs["Value"], pvol.inputs["Emission Strength"])
    links.new(pvol.outputs["Volume"], out.inputs["Volume"])

    cube.data.materials.append(mat)
    # Display as wire to see through in viewport
    safe_set(cube, "display_type", 'WIRE')
    return cube

nebula = nebula_cube(NEBULA_SIZE)

# -----------------------------
# Camera + Fly-through
# -----------------------------
bpy.ops.object.camera_add(location=CAMERA_START)
cam = bpy.context.active_object
cam.name = "FlyCam"

# Target empty
bpy.ops.object.empty_add(type='PLAIN_AXES', location=FOCUS_TARGET)
target = bpy.context.active_object
target.name = "FocusTarget"

# Track-to
t = cam.constraints.new(type='TRACK_TO')
t.target = target
t.track_axis = 'TRACK_NEGATIVE_Z'
t.up_axis = 'UP_Y'

def keyframe_vec(obj, attr, frame, vec):
    setattr(obj, attr, vec)
    obj.keyframe_insert(data_path=attr, frame=frame)

# Animate camera motion
keyframe_vec(cam, "location", FRAME_START, CAMERA_START)
keyframe_vec(cam, "location", FRAME_END,   CAMERA_END)

# Slight target drift for parallax
keyframe_vec(target, "location", FRAME_START, FOCUS_TARGET)
keyframe_vec(target, "location", FRAME_END,   FOCUS_TARGET + Vector((1.5, 0.7, 0.2)))

# ---- Interpolation helper (no imports; uses existing keyframes to read enums)
def apply_interp(action, desired='LINEAR'):
    allowed = set()
    try:
        # probe allowed enums from an existing keyframe if possible
        for fcu in action.fcurves:
            if fcu.keyframe_points:
                kfp = fcu.keyframe_points[0]
                allowed = {e.identifier for e in kfp.bl_rna.properties['interpolation'].enum_items}
                break
    except Exception:
        pass
    use = desired if desired in allowed else ('BEZIER' if 'BEZIER' in allowed else 'LINEAR')
    for fcu in action.fcurves:
        for kp in fcu.keyframe_points:
            kp.interpolation = use

# Apply interpolation
if cam.animation_data and cam.animation_data.action:
    apply_interp(cam.animation_data.action, 'LINEAR')  # constant speed
if target.animation_data and target.animation_data.action:
    apply_interp(target.animation_data.action, 'SINE') # gentle ease (fallbacks handled)
if bpy.data.objects.get("MoonPivot") and bpy.data.objects["MoonPivot"].animation_data:
    apply_interp(bpy.data.objects["MoonPivot"].animation_data.action, 'LINEAR')

# Depth of field
safe_set(cam.data.dof, "use_dof", True)
safe_set(cam.data.dof, "focus_object", target)
safe_set(cam.data.dof, "aperture_fstop", 2.8)

# Final touch
planet.rotation_euler = Euler((math.radians(15), math.radians(6), math.radians(12)), 'XYZ')
scene.view_settings.exposure = -0.2

print("✅ Eevee-Next rich scene built. Spacebar = preview. Ready to render!")
