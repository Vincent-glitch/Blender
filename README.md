# Blender
Base repo for all Blender code.

## Space Scene Builder

The repository includes `space_scene.py`, a Blender 4.x compatible script
that procedurally generates a small, spaced-out solar system fly‑through:

* Procedural starfield world
* Earth‑like planet with rings and a moon
* Gas giant, wide asteroid belt, and distant glowing sun
* Volumetric nebula
* Animated camera path with depth of field

### Usage

1. Open Blender 4.x and switch to the **Scripting** workspace.
2. Load `space_scene.py` in the text editor.
3. Press **Run Script** to build the scene.

The script supports both Eevee Next and Cycles render engines.

## Grand Flyby Scene

`grand_flyby.py` builds a much larger system with a blazing sun, two distant planets,
a broad asteroid field, and a long camera path that sweeps through the nebula‑filled void.

### Usage

1. Open Blender 4.x and switch to the **Scripting** workspace.
2. Load `grand_flyby.py`.
3. Press **Run Script** to generate the scene.

The camera is animated along a Bézier path for a cinematic fly‑by.
