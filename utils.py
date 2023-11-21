import bpy
from dataclasses import dataclass

from enum import Enum, auto, unique


@unique
class StateValue(Enum):
    """the state of the light linking"""
    EXCLUDE = 'EXCLUDE'
    INCLUDE = 'INCLUDE'


@unique
class StateType(Enum):
    """the type of the collection, using in dict"""
    RECEIVER = 'receiver'
    BLOCKER = 'blocker'


def get_linking_coll(obj: bpy.types.Object, type: StateType):
    """get the linking collection from the object"""
    if type == StateType.RECEIVER:
        return obj.light_linking.receiver_collection
    elif type == StateType.BLOCKER:
        return obj.light_linking.blocker_collection
    else:
        raise ValueError(f"StateType {type} is not supported")


def get_coll_obj_linking_state(coll_obj: bpy.types.CollectionObject) -> StateValue:
    """returns the linking state of the collection object
    :returns str value in StateValue: 'EXCLUDE' or 'INCLUDE'
    """
    if coll_obj.light_linking.link_state == 'EXCLUDE':
        return StateValue.EXCLUDE
    else:
        return StateValue.INCLUDE


def enum_coll_objs_from_coll(coll: bpy.types.Collection) -> dict[bpy.types.Object:bpy.types.CollectionObject]:
    """Since that the CollectionObject can not be accessed directly from the Collection, this function is used to
    :returns dict[bpy.types.Object:bpy.types.CollectionObject]: {obj:coll_obj}
    """
    return {obj: coll.collection_objects[i] for i, obj in enumerate(coll.objects)}


def get_light_effect_obj_state(light: bpy.types.Object, obj: bpy.types.Object) -> dict[str:str]:
    """get the light effect state of the object from the light,both the receiver and the block collection, return a dict that contains the light linking state of the object

    :return dict[str:str]: {StateType.RECEIVER.value:str|None, StateType.BLOCKER.value:str|None
    """

    # first get the receiver collection and the block collection
    receiver_coll = get_linking_coll(light, StateType.RECEIVER)
    blocker_coll = get_linking_coll(light, StateType.BLOCKER)

    state = {
        StateType.RECEIVER: None,
        StateType.BLOCKER: None
    }

    def get_obj_state_from_coll(coll: bpy.types.Collection) -> str | None:
        """get the state of the object from the collection"""
        coll_objs = enum_coll_objs_from_coll(coll)
        coll_obj = coll_objs.get(obj)
        if coll_obj:
            return get_coll_obj_linking_state(coll_obj)
        return None

    # if the receiver collection exists, get the state of the object from the receiver collection

    if receiver_coll:
        state[StateType.RECEIVER] = get_obj_state_from_coll(receiver_coll)
    if blocker_coll:
        state[StateType.BLOCKER] = get_obj_state_from_coll(blocker_coll)

    return state


def get_all_light_effect_obj_state(light: bpy.types.Object) -> dict[bpy.types.Object:dict[str:str]]:
    """get all the objects that are affected by the light and their receiver and blocker state
    version for all object because the function above runs multiple times function:enum_coll_objs_from_coll is not efficient
    :return dict{bpy.types.Object:dict: {'receiver':str|None, 'blocker':str|None}}
    """
    receiver_coll = get_linking_coll(light, StateType.RECEIVER)
    blocker_coll = get_linking_coll(light, StateType.BLOCKER)

    obj_state = {}  # {bpy.types.Object:dict: {'receiver':str|None, 'blocker':str|None}} Note: the str is the link state, None means the object is not in the collection

    #
    if receiver_coll:
        coll_objs = enum_coll_objs_from_coll(receiver_coll)
        for obj in coll_objs:
            obj_state[obj] = {
                StateType.RECEIVER: get_coll_obj_linking_state(coll_objs[obj]),
                StateType.BLOCKER: None
            }

    if blocker_coll:
        coll_objs = enum_coll_objs_from_coll(blocker_coll)
        for obj in coll_objs:
            if obj_state.get(obj):
                obj_state[obj][StateType.BLOCKER] = get_coll_obj_linking_state(coll_objs[obj])
            else:
                obj_state[obj] = {
                    StateType.RECEIVER: None,
                    StateType.BLOCKER: get_coll_obj_linking_state(coll_objs[obj])
                }

    return obj_state


def set_light_effect_obj_state(light: bpy.types.Object, obj: bpy.types.Object,
                               state: tuple[StateType, StateValue]) -> None:
    """set the light effect state of the object from the light,in the receiver or the block collection

    :param light: the light object
    :param obj: the object that is affected by the light
    :param state: the state to set for the object, dict[StateType.value:StateValue.value]
    """

    def set_obj_state_from_coll(coll: bpy.types.Collection, state_value: StateValue):
        """set the state of the object from the collection"""
        coll_objs = enum_coll_objs_from_coll(coll)
        coll_obj = coll_objs.get(obj)
        if coll_obj:
            coll_obj.light_linking.link_state = state_value.value

    if state[0] == StateType.RECEIVER:
        set_obj_state_from_coll(get_linking_coll(light, StateType.RECEIVER), state[1])
    elif state[0] == StateType.BLOCKER:
        set_obj_state_from_coll(get_linking_coll(light, StateType.BLOCKER), state[1])

    return
