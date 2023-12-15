import bpy
import gpu
import numpy as np
from gpu_extras.batch import batch_for_shader

vertex_shader = '''
in vec3 position;
in vec3 normal;
in vec4 color;
uniform mat4 model;
uniform mat4 view;
uniform mat4 projection;

uniform vec3 camera_location;
uniform float factor1;
uniform float factor2;

out vec4 fcolor;
void main()
{

    vec3 pos = vec3(model * vec4(position, 1.0));
    vec3 nor = mat3(transpose(inverse(model))) * normal;

    float d = distance(pos, camera_location) * factor1;
    vec3 offset = nor * vec3(d);
    vec3 p = pos + offset;

    vec3 dir = p - camera_location;
    dir = normalize(dir) * vec3(factor2);
    p = p + dir;

    gl_Position = projection * view * vec4(p, 1.0);
    fcolor = color;
}
'''
fragment_shader = '''
in vec4 fcolor;
out vec4 fragColor;
void main()
{
    fragColor = blender_srgb_to_framebuffer_space(fcolor);
}
'''


def draw(self, context, ):
    gpu.state.depth_test_set('LESS')

    self.shader.bind()
    self.shader.uniform_float("model", self.o.matrix_world)
    self.shader.uniform_float("view", bpy.context.region_data.view_matrix)
    self.shader.uniform_float("projection", bpy.context.region_data.window_matrix)

    cl = bpy.context.region_data.view_matrix.inverted().translation
    self.shader.uniform_float("camera_location", cl)
    self.shader.uniform_float("factor1", 0.01)
    self.shader.uniform_float("factor2", 50.0)

    self.batch.draw(self.shader)

    gpu.state.depth_test_set('NONE')


class LLP_OT_draw_mesh_outline(bpy.types.Operator):
    bl_idname = "llp.draw_mesh_outline"
    bl_label = ""

    _timer = None
    _handle_3d = None

    color = (1.0, 1.0, 0.0, 1.0)
    obj_name: bpy.props.StringProperty(name='Object Name', default='')

    def prepare(self, context):
        obj = self.o.evaluated_get(context.view_layer.depsgraph)
        me = obj.data
        me.calc_loop_triangles()

        vs = np.zeros((len(me.vertices) * 3,), dtype=np.float32, )
        me.vertices.foreach_get('co', vs)

        vs.shape = (-1, 3,)
        ns = np.zeros((len(me.vertices) * 3,), dtype=np.float32, )
        me.vertices.foreach_get('normal', ns)
        ns.shape = (-1, 3,)
        fs = np.zeros((len(me.loop_triangles) * 3,), dtype=np.int32, )
        me.loop_triangles.foreach_get('vertices', fs)
        fs.shape = (-1, 3,)
        cs = np.full((len(me.vertices), 4), self.color, dtype=np.float32, )

        shader = gpu.types.GPUShader(vertex_shader, fragment_shader, )
        batch = batch_for_shader(shader, 'TRIS', {"position": vs, "normal": ns, "color": cs, }, indices=fs, )
        return shader, batch

    def tag_redraw(self):
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if (area.type == 'VIEW_3D'):
                    area.tag_redraw()

    def modal(self, context, event):
        if context.window_manager.llp_draw_mesh is False:
            bpy.types.SpaceView3D.draw_handler_remove(self._handle_3d, 'WINDOW')
            self.tag_redraw()
            return {'CANCELLED'}

        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        self.o = context.active_object
        self.shader, self.batch = self.prepare(context)
        self._handle_3d = bpy.types.SpaceView3D.draw_handler_add(draw, (self, context,), 'WINDOW', 'POST_VIEW', )
        context.window_manager.modal_handler_add(self)
        self.tag_redraw()
        return {'RUNNING_MODAL'}


def register():
    bpy.utils.register_class(LLP_OT_draw_mesh_outline)
    bpy.types.WindowManager.llp_draw_mesh = bpy.props.BoolProperty(default=False)


def unregister():
    bpy.utils.unregister_class(LLP_OT_draw_mesh_outline)
    del bpy.types.WindowManager.llp_draw_mesh
