"""Run with Blender --background --factory-startup --python-exit-code 1."""

from __future__ import annotations

import sys
from pathlib import Path

PACKAGE_PARENT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PACKAGE_PARENT))

import bpy  # noqa: E402

import LightHelper  # noqa: E402
from LightHelper.core.light_group_plan import (  # noqa: E402
    CompositeConnectionDecision,
    GroupAdjustment,
)
from LightHelper.core.profiles import UUID_KEY, make_document  # noqa: E402
from LightHelper.utils.light_groups import (  # noqa: E402
    MANAGED_OWNER_KEY,
    build_light_group_compositor,
    ensure_used_light_groups,
    remove_light_group,
    remove_managed_light_group_compositor,
)
from LightHelper.utils.profile_runtime import (  # noqa: E402
    ProfileHooks,
    apply_link_payload,
    apply_light_group_payload,
    apply_profile,
    apply_studio_payload,
    apply_world_payload,
    capture_link_payload,
    capture_light_group_payload,
    capture_profile,
    capture_studio_payload,
    capture_world_payload,
)
from LightHelper.utils.studio import create_flag, remove_studio_object  # noqa: E402


def compositor_tree(scene):
    return scene.node_tree if hasattr(scene, "node_tree") else scene.compositing_node_group


def output_input(node):
    return node.inputs.get("Image") or next(item for item in node.inputs if item.enabled)


LightHelper.register()
try:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    view_layer = bpy.context.view_layer
    data = bpy.data.lights.new("Key", "AREA")
    data.energy = 777.0
    light = bpy.data.objects.new("Key", data)
    scene.collection.objects.link(light)
    light.lightgroup = "Key"
    flag = create_flag(scene, width=3.0, height=2.0, color=(0.1, 0.2, 0.3))
    group_setting = scene.light_helper_light_group_settings.add()
    group_setting.name = "Key"
    group_setting.ev = 1.25
    group_setting.tint = (1.0, 0.8, 0.6)

    hooks = ProfileHooks(
        capture_links=capture_link_payload,
        apply_links=apply_link_payload,
        capture_world=capture_world_payload,
        apply_world=apply_world_payload,
        capture_studio=capture_studio_payload,
        apply_studio=apply_studio_payload,
        capture_light_groups=capture_light_group_payload,
        apply_light_groups=apply_light_group_payload,
    )
    profile = capture_profile(scene, "Smoke", hooks=hooks)
    make_document([profile])
    data.energy = 1.0
    report = apply_profile(scene, profile, context=bpy.context, hooks=hooks)
    assert report.matched == len(profile["lights"]), report
    assert abs(data.energy - 777.0) < 1e-6
    assert len(profile["studio"]["items"]) == 1
    assert profile["light_groups"]["settings"][0]["ev"] == 1.25

    light_payload = next(item for item in profile["lights"] if item["ref"]["name_full"] == "Key")
    profile_uuid = light_payload["ref"]["uuid"]
    bpy.data.objects.remove(light, do_unlink=True)
    if data.users == 0:
        bpy.data.lights.remove(data)
    assert remove_studio_object(flag)
    report = apply_profile(
        scene, profile, context=bpy.context, hooks=hooks, create_missing=True
    )
    assert report.created == 1, report
    light = next(obj for obj in scene.objects if obj.get(UUID_KEY) == profile_uuid)
    assert light.data.type == "AREA"
    assert abs(light.data.energy - 777.0) < 1e-6
    studio_uuid = profile["studio"]["items"][0]["ref"]["uuid"]
    recreated_flag = next(
        obj for obj in scene.objects if obj.get(UUID_KEY) == studio_uuid
    )
    assert recreated_flag.get("light_helper_studio_shape") == "RECTANGLE"

    ensure_used_light_groups(scene, view_layer)
    if hasattr(scene, "node_tree"):
        scene.use_nodes = True
        composite = next(
            node
            for node in scene.node_tree.nodes
            if node.bl_idname == "CompositorNodeComposite"
        )
        for link in tuple(composite.inputs["Image"].links):
            scene.node_tree.links.remove(link)
    adjustments = {
        "Key": GroupAdjustment("Key", ev=1.25, tint=(1.0, 0.8, 0.6))
    }
    first = build_light_group_compositor(scene, view_layer, adjustments)
    tree = compositor_tree(scene)
    owner_uuid = scene.get(UUID_KEY)
    managed_count = sum(
        node.get(MANAGED_OWNER_KEY) == owner_uuid for node in tree.nodes
    )
    assert first.connection == CompositeConnectionDecision.CONNECT

    second = build_light_group_compositor(scene, view_layer, adjustments)
    managed_count_second = sum(
        node.get(MANAGED_OWNER_KEY) == owner_uuid for node in tree.nodes
    )
    assert second.connection == CompositeConnectionDecision.REPLACE_MANAGED
    assert managed_count_second == managed_count, (managed_count, managed_count_second)

    assert tree.nodes[second.output_node].get(MANAGED_OWNER_KEY) == owner_uuid
    target = tree.nodes[second.target_node]
    target_input = output_input(target)
    for link in tuple(target_input.links):
        tree.links.remove(link)
    user_source = tree.nodes.new("CompositorNodeRLayers")
    user_source.name = "User Render Layers"
    user_source.layer = view_layer.name
    tree.links.new(user_source.outputs.get("Image") or user_source.outputs[0], target_input)
    third = build_light_group_compositor(scene, view_layer, adjustments)
    assert third.connection == CompositeConnectionDecision.PRESERVE_USER
    assert target_input.is_linked
    assert target_input.links[0].from_node == user_source

    removed = remove_managed_light_group_compositor(scene)
    assert removed > 0
    assert target_input.is_linked
    assert target_input.links[0].from_node == user_source
    assert not any(node.get(MANAGED_OWNER_KEY) == owner_uuid for node in tree.nodes)
    assert remove_light_group(scene, view_layer, "Key", context=bpy.context)
    assert view_layer.lightgroups.get("Key") is None
    print(f"LIGHTHELPER_PROFILE_AOV_SMOKE_OK {bpy.app.version_string}")
finally:
    LightHelper.unregister()
