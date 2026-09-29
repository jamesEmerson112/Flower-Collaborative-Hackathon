"""Illustrative Shadow Chassis envelope, NOT vendor CAD or mounting geometry.

Vendor envelope: 196 x 126 x 44 mm excluding nub caster.
https://www.sparkfun.com/shadow-chassis.html
"""
import bpy

def create_frame():
    def block(name, location, size, bevel=2):
        bpy.ops.mesh.primitive_cube_add(size=1, location=location)
        obj=bpy.context.object;obj.name=name;obj.dimensions=size
        bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
        modifier=obj.modifiers.new('Illustrative rounded edges','BEVEL');modifier.width=bevel;modifier.segments=3
        bpy.ops.object.modifier_apply(modifier=modifier.name)
        obj['approximate_preview']=True
        return obj
    for height in [-20.5,20.5]:
        plate=block('Illustrative chassis plate',(0,0,height),(196,126,3),1.3)
        for x in [-72,0,72]:
            for y in [-43,43]:
                bpy.ops.mesh.primitive_cylinder_add(vertices=16,radius=5,depth=8,location=(x,y,height))
                cutter=bpy.context.object
                bpy.context.view_layer.objects.active=plate
                modifier=plate.modifiers.new('Illustrative aperture','BOOLEAN');modifier.operation='DIFFERENCE';modifier.object=cutter
                bpy.ops.object.modifier_apply(modifier=modifier.name)
                bpy.data.objects.remove(cutter,do_unlink=True)
    for x in [-85,85]:
        for y in [-52,52]:block('Illustrative side strut',(x,y,0),(8,8,38),1)
