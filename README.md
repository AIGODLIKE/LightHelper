# LightHelper

**A more intuitive way to control which objects a light illuminates—and to manage lights directly from the objects they affect.**


LightHelper is a Blender extension that turns Light Linking and Shadow Linking into a fast, two-way workflow. Edit a light to choose the objects it affects, or start from an object and choose the lights that include or exclude it.

[Download the latest release](https://github.com/AIGODLIKE/LightHelper/releases/latest) · [Report an issue](https://github.com/AIGODLIKE/LightHelper/issues)

## Highlights

- Edit links from either a **light** or an **object**.
- Switch each light between **Include** and **Exclude** behavior.
- Control **illumination** and **shadow** links independently.
- Edit links directly in the 3D View with a dedicated interactive tool.
- Detect both Blender Light objects and objects using emissive materials.
- Solo lights, adjust energy in EV steps, filter large light lists, and pin working subjects.
- Separate shared linking data manually, or opt in to automatic duplicate handling.
- Restore Blender's default full-lighting behavior with one action.

## Compatibility

| Blender version | Cycles | Eevee |
| --- | :---: | :---: |
| 4.2 | Yes | No |
| 4.3 or newer | Yes | Yes |

- Minimum supported Blender version: **4.2**.
- The Light Linking controls are disabled for unsupported render engines.
- LightHelper follows Blender's own Light Linking capabilities and renderer limitations.

## Installation

1. Download the ZIP from the [latest release](https://github.com/AIGODLIKE/LightHelper/releases/latest). Do not extract it.
2. In Blender, open **Edit → Preferences → Get Extensions** (or **Add-ons**, depending on the Blender version).
3. Open the menu in the top-right corner and choose **Install from Disk**.
4. Select the downloaded ZIP and enable **Light Helper** if Blender does not enable it automatically.
5. In the 3D View, press `N` and open the **LH** tab.

The sidebar tab is named `LH` by default. You can rename it in the extension preferences.

## Core concepts

### Include and Exclude

Every initialized light has its own linking mode:

| Mode | Result |
| --- | --- |
| **Include** | The light illuminates only the objects or collections listed in its links. |
| **Exclude** | The light illuminates everything except the objects or collections listed in its links. |

Use **Include** when a light should affect a small, controlled group. Use **Exclude** when a light should behave normally except for a few objects.

### Illumination and shadows

LightHelper exposes Blender's two independent linking channels:

- **Light channel** — controls whether the object receives illumination from the light.
- **Shadow channel** — controls whether the object can cast a shadow for that light.

The light and shadow buttons can be toggled separately. This makes it possible to keep illumination while disabling a shadow, or to manage shadow linking without changing the light link.

## Quick start

### Start from a light

Use this workflow when you know which light you want to edit.

1. Select a Light object, or choose a detected emissive-material source from the **Light Linking** list.
2. Open **3D View → Sidebar → LH → Light Linking**.
3. Click **Init** if the light has not been initialized.
4. Choose **Include** or **Exclude**.
5. Add an object, add a collection, or select objects in the viewport and use **Add Selected Objects**.
6. Use the light and shadow buttons beside each item to control the two channels independently.

![Editing links from a light](https://github.com/user-attachments/assets/eff68fc8-f2e2-4d68-bd0a-cd298b62a424)

### Start from an object

Use this workflow when you know which object you want to control.

1. Select the object and open **Object Linking** in the `LH` sidebar.
2. Choose the lights that should include or exclude the object.
3. Each light uses its own current **Include/Exclude** mode, shown beside the light name.
4. Toggle the illumination or shadow channel as needed.

![Editing lights from an object](https://github.com/user-attachments/assets/efd17d36-cb3e-4593-85fb-3530c8edba33)

### Restore default full lighting

Use **Restore** on a light when you want to remove its Light Linking and Shadow Linking collections completely. The light then returns to Blender's default behavior and illuminates all eligible objects.

Removing the final light link from the object-first workflow also restores the affected light's default full-lighting state.

## Interactive Light Linking tool

The **Light Linking** tool is available in the left toolbar of the 3D View while Blender is in **Object Mode**. It provides direct picking, a movable shortcut HUD, and link overlays.

### Subject modes

| Subject mode | Left-click behavior |
| --- | --- |
| **Light** | Click a light to make it the subject; click an object to toggle that object's link. |
| **Object** | Click an object to make it the subject; click a light to toggle that light's link to the object. |

Use `Ctrl` + left-click to switch the subject mode from the item under the cursor. A true Blender Light becomes the light subject; a linkable non-light object becomes the object subject.

### Shortcuts

| Input | Action |
| --- | --- |
| Left-click | Select a new subject or toggle both link channels for the item under the cursor. |
| `Ctrl` + left-click | Switch between Light and Object subject modes from the item under the cursor. |
| `L` or `Space` | Toggle the illumination channel for the item under the cursor. In Object mode, place the cursor over a light. |
| `S` | Toggle the shadow channel for the item under the cursor. In Object mode, place the cursor over a light. |
| `A` | Switch the relevant light between Include and Exclude. In Object mode, place the cursor over a light. |
| `X` | Cycle overlay display through Off, Selected, and All. |
| `Ctrl` + mouse wheel | Move to the previous or next filtered light/object subject. |
| Left-drag on the HUD | Reposition the shortcut HUD. |
| `Esc` | Exit to the previously active tool. |

### Viewport overlays

The default **Selected** overlay shows links for the current subject. **All** displays every visible link at once, while **Off** hides the visualization.

- Green indicates Include illumination links.
- Red indicates Exclude illumination links.
- Blue indicates shadow-only links.
- Gray indicates an item with neither active channel.

For dense scenes, LightHelper limits object outlines while continuing to draw link lines. Change **Linking Tool Max Outlines** in the preferences if needed.

## Sidebar controls

### Light Linking

The main panel lists available light sources and their linked items.

- Filter sources by **All**, **Light**, or **Emission Material**.
- Filter link state by **All**, **General**, or **Linking**.
- Search, sort, invert visibility, and hide sources that are not in the current scene.
- Initialize or restore one light, initialize all lights, and clear selected links.
- Add objects or collections and toggle their illumination/shadow membership.
- Pin a light so selection changes do not interrupt the current setup.
- Make one light—or all affected lights—use independent linking data.

### Object Linking

The object-first panel shows the lights currently linked to the selected object.

- See each light's Include/Exclude mode at a glance.
- Toggle illumination and shadow channels independently.
- Remove a light from the object while safely restoring default behavior when no links remain.
- Pin the object or show the global list of linked objects.

### Light Properties

LightHelper brings the relevant Blender light settings into the same sidebar workflow. For native Light objects, the panel also provides:

- `-1 EV`, `-0.5 EV`, `+0.5 EV`, and `+1 EV` energy adjustments.
- Built-in Cycles or Eevee light settings for the active renderer.
- Multi-light EV adjustment when multiple native Light objects are selected.

Each EV operation multiplies the light energy by `2^EV`.

## Other features

### Emissive-material detection

Objects with a connected, non-zero emissive material can appear in the source list. LightHelper follows nested node groups up to the configured **Emission Node Search Depth**.

For complex materials, a high search depth can make list refreshes slower. Reduce the value if the interface stutters. To use an emissive source as the interactive tool's light subject, select it from the sidebar first or left-click it while the tool is already in Light mode; `Ctrl` + left-click on a non-Light object selects it as an object subject.

Automatic source detection:

https://github.com/user-attachments/assets/833e55e3-7bd2-4476-a275-78cbcd96f6f8

### Solo Light

Solo isolates the chosen native Light from the currently filtered light set. Press it again to restore the previous viewport, render, and local-hide states.

### Shared linking data and duplicates

Duplicated lights can share Blender linking collections. Use **Make Single-User** for one light or **Make All Single-User** when each duplicate needs independent links.

**Auto Fix Shared Linking** is optional and disabled by default. When enabled, it separates shared linking collections only for explicitly detected duplicates and does not run while a file is opening.

### View movement

Choose how selecting a light or linked object affects the viewport:

- **None** — select without moving the view.
- **Maintaining Zoom** — move directly while preserving the current zoom.
- **Animation** — animate the view transition.

https://github.com/user-attachments/assets/9ab4f865-904a-4030-976e-2d6b3d0b5e13

## Additional workflow examples

Create exclusions from lights and emissive sources:

https://github.com/user-attachments/assets/19dbc501-e501-43d4-a0cd-50ad1fae7993

Exclude a light from the illuminated object:

https://github.com/user-attachments/assets/148198df-3886-43a5-8b65-91353f642ad3

Quickly select linked objects:

https://github.com/user-attachments/assets/667f8efc-6102-4559-a724-23071a143399

Quickly select lights linked to an object:

https://github.com/user-attachments/assets/216b665c-66dd-4fa0-90c2-59fa6c2cc686

## Preferences

| Setting | Purpose |
| --- | --- |
| **Panel Name** | Rename the default `LH` sidebar tab. |
| **Emission Node Search Depth** | Set how deeply nested material node groups are searched for emission. |
| **List Filter Type** | Show all sources, native lights only, or emissive-material sources only. |
| **Link Filter Type** | Show all sources, unlinked sources, or linked sources. |
| **View Movement Type** | Choose whether selection moves or animates the viewport. |
| **Auto Fix Shared Linking** | Opt in to separating shared linking data for detected duplicate lights. |
| **Linking Tool Max Outlines** | Limit viewport outlines in dense scenes; link lines remain visible. |
| **Shortcut Tip Scale / HUD X / HUD Y** | Resize or position the interactive tool HUD. |
| **Reset Linking HUD** | Restore the default HUD size and position. |
| **Clean Up Legacy Data** | Remove only legacy data explicitly managed by older LightHelper versions. |

## Known limitation

When an emissive material is used as a light source, indirect-light exclusion may not behave reliably in Eevee. This is a limitation of Blender's current Light Linking implementation rather than a LightHelper setting. Use native Blender Light objects when predictable exclusion is required.

## Troubleshooting

### The `LH` tab is missing

- Press `N` while the mouse is over the 3D View.
- Confirm that **Light Helper** is enabled in Preferences.
- Check whether **Panel Name** was changed in the extension preferences.

### The Light Linking tool is unavailable

- Switch Blender to **Object Mode**.
- In Blender 4.2, use **Cycles**. Blender 4.3 or newer also supports Eevee.
- Confirm that the current render engine supports Blender Light Linking.

### A duplicated light changes another light's links

The lights are probably sharing linking collections. Use **Make Single-User**, or enable **Auto Fix Shared Linking** if you want LightHelper to handle detected duplicates automatically.

### An emissive object does not appear in the source list

- Confirm that the material uses nodes and has a connected, non-zero emission path.
- Switch the source filter to **All** or **Emission Material**.
- Increase **Emission Node Search Depth** if the emission is inside deeply nested node groups.

### A light does not return to normal full lighting

Use **Restore** for that light. Restore removes the receiver and blocker collections instead of leaving an initialized but intentionally restricted link setup.

### The viewport overlay is too busy or slow

Press `X` to use **Selected** or **Off**, or lower **Linking Tool Max Outlines** in the preferences.

## Feedback and support

If you find an edge case, a confusing interaction, or a better light-exclusion workflow, please [open an issue](https://github.com/AIGODLIKE/LightHelper/issues). Clear reproduction steps, the Blender version, render engine, and a small `.blend` example are especially helpful.

## License

LightHelper is licensed under [GNU GPL v3.0 or later](https://www.gnu.org/licenses/gpl-3.0.html).
