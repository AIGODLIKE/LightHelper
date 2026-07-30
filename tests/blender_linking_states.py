"""Blender-hosted smoke coverage for LightHelper's native tri-state model."""

from __future__ import annotations

import sys
from pathlib import Path

import bpy


REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY.parent))

import LightHelper  # noqa: E402
from LightHelper.utils import (  # noqa: E402
    ChannelState,
    CollectionType,
    get_effective_item_channel_state,
    get_effective_linking_mode,
    get_item_channel_state,
    init_light_linking,
    set_item_channel_state,
    set_linking_edit_mode,
)


def main() -> None:
    LightHelper.register()
    try:
        scene = bpy.context.scene
        light_data = bpy.data.lights.new("LH Tri-state", 'AREA')
        light = bpy.data.objects.new("LH Tri-state", light_data)
        scene.collection.objects.link(light)

        direct_target = bpy.data.objects.new("LH Direct Target", None)
        scene.collection.objects.link(direct_target)
        inherited_target = bpy.data.objects.new("LH Inherited Target", None)
        target_collection = bpy.data.collections.new("LH Target Collection")
        scene.collection.children.link(target_collection)
        target_collection.objects.link(inherited_target)

        assert init_light_linking(light, bpy.context)
        assert set_item_channel_state(
            light, direct_target, CollectionType.RECEIVER, ChannelState.INCLUDE,
        )
        assert set_item_channel_state(
            light, direct_target, CollectionType.BLOCKER, ChannelState.EXCLUDE,
        )
        assert get_item_channel_state(
            light, direct_target, CollectionType.RECEIVER,
        ) == ChannelState.INCLUDE
        assert get_item_channel_state(
            light, direct_target, CollectionType.BLOCKER,
        ) == ChannelState.EXCLUDE
        assert get_effective_linking_mode(light) == "MIXED"

        assert set_linking_edit_mode(light, "ADVANCED")
        light.light_helper_property.linking_mode = 'EXCLUDE'
        assert get_item_channel_state(
            light, direct_target, CollectionType.RECEIVER,
        ) == ChannelState.INCLUDE

        assert set_item_channel_state(
            light, target_collection, CollectionType.RECEIVER, ChannelState.EXCLUDE,
        )
        inherited = get_effective_item_channel_state(
            light, inherited_target, CollectionType.RECEIVER,
        )
        assert inherited.state == ChannelState.EXCLUDE
        assert inherited.inherited_from == (target_collection,)
        assert not inherited.direct

        assert set_item_channel_state(
            light, inherited_target, CollectionType.RECEIVER, ChannelState.INCLUDE,
        )
        overridden = get_effective_item_channel_state(
            light, inherited_target, CollectionType.RECEIVER,
        )
        assert overridden.state == ChannelState.INCLUDE
        assert overridden.direct
        assert set_item_channel_state(
            light, inherited_target, CollectionType.RECEIVER, ChannelState.OFF,
        )
        inherited_again = get_effective_item_channel_state(
            light, inherited_target, CollectionType.RECEIVER,
        )
        assert inherited_again.state == ChannelState.EXCLUDE
        assert inherited_again.inherited_from == (target_collection,)

        assert set_linking_edit_mode(light, "SIMPLE", "INCLUDE")
        assert get_effective_linking_mode(light) == "INCLUDE"
        assert get_item_channel_state(
            light, direct_target, CollectionType.BLOCKER,
        ) == ChannelState.INCLUDE
        assert get_item_channel_state(
            light, target_collection, CollectionType.RECEIVER,
        ) == ChannelState.INCLUDE
        print("LIGHTHELPER_TRISTATE_OK")
    finally:
        LightHelper.unregister()


if __name__ == "__main__":
    main()
