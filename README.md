# LightHelper

[English](README.md) | [简体中文](README_CN.md)

**A more intuitive way to control which objects a light illuminates—and to manage lights directly from the objects they affect.**

LightHelper is a Blender extension that turns Light Linking and Shadow Linking into a fast, two-way workflow. Edit a light to choose the objects it affects, or start from an object and choose the lights that include or exclude it.

[Download the latest release](https://github.com/AIGODLIKE/LightHelper/releases/latest) · [Report an issue](https://github.com/AIGODLIKE/LightHelper/issues)

## Highlights

- Edit links from either a **light** or an **object**.
- Switch each light between **Include** and **Exclude** behavior.
- Control **illumination** and **shadow** links independently.
- Edit links directly in the 3D View with a dedicated interactive tool.
- Detect Blender Light objects in supported renderers and emissive-material sources in Cycles.
- Solo lights, adjust energy in EV steps, filter large light lists, and pin working subjects.
- Separate shared linking data manually, or opt in to automatic duplicate handling.
- Restore Blender's default full-lighting behavior with one action.
- Convert a nested or packed World HDRI—or a solid World Background—into one linkable environment dome and restore the original World safely.

## Compatibility

| Workflow | Cycles | Eevee |
| --- | :---: | :---: |
| Native Light / Shadow Linking (Blender 4.2+) | Yes | Blender 4.3+ |
| Emissive-material Light Linking | Yes | No |
| World HDRI / solid-color environment dome | Yes | Hidden |

- Minimum supported Blender version: **4.2**.
- The Light Linking controls are disabled for unsupported render engines.
- LightHelper follows Blender's own Light Linking capabilities and renderer limitations.
- **World Environment Linking and emissive-material light sources require Cycles.** Native Blender Light objects remain available in Eevee where Blender supports Light Linking.

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

Use **Include** when a light should affect only a small, specified set of objects. Use **Exclude** when a light should illuminate the scene normally but skip a few objects.

### Illumination and shadows

LightHelper exposes Blender's two independent linking channels:

- **Illumination channel** — controls whether the object receives illumination from the light.
- **Shadow channel** — controls whether the object casts a shadow for that light.

The illumination and shadow buttons can be toggled separately. This makes it possible to keep illumination while disabling a shadow, or to adjust shadow linking without changing the illumination link.

## Quick start

### Start from a light

Use this workflow when you already know which light you want to edit.

1. Select a light and activate the **Light Linking** tool in the left toolbar.
2. Include mode — the light illuminates only the selected objects.
<img width="1920" height="1034" alt="light-include" src="https://github.com/user-attachments/assets/5f676665-1308-4a64-83ec-27ea2274f2a0" />
3. Exclude mode — the light does not illuminate the selected objects.
<img width="1920" height="1034" alt="light-exclude" src="https://github.com/user-attachments/assets/b8987008-a24b-422a-96ee-8c9c536b02ac" />

### Start from an object

Use this workflow when you already know which object you want to manage lights from.

1. Select the object and open **Object Linking** in the `LH` sidebar.
2. Choose the lights that should include or exclude the object.
3. Each light uses its own current **Include/Exclude** mode.
4. Toggle the illumination or shadow channel as needed.
<img width="1920" height="1034" alt="object-light-exclusion" src="https://github.com/user-attachments/assets/e196495a-bff2-4308-8cd7-31b1c3441d4a" />


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

Hold `Ctrl` and left-click to switch the subject mode from the item under the cursor. A native Blender Light becomes the light subject; a linkable non-light object becomes the object subject.

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

Shadow toggle
<img width="1920" height="1034" alt="shadow-toggle" src="https://github.com/user-attachments/assets/9ee58c6a-88e1-4d5a-a003-aa878f461efb" />


### Viewport overlays

The default **Selected** overlay shows links for the current subject only. **All** displays every visible link, while **Off** hides the visualization.

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

<img width="1920" height="1034" alt="ev-control" src="https://github.com/user-attachments/assets/213f3bc7-63d8-4254-a41c-4bd93c181d9e" />

### World Environment Linking

The **World Environment Linking** panel converts the HDRI or solid Background color connected to the active Cycles World Output into a code-generated inward-facing sphere. This makes the World illumination available as an emissive-mesh source for object-level Light Linking. The workflow is Cycles-only and the panel is hidden in Eevee.

1. Switch the render engine to **Cycles**.
2. Open **3D View → Sidebar → LH → World Environment Linking**.
3. Check the detected World source, then choose **Convert World Environment**.
4. Select the generated environment dome from the light list and use the normal Include/Exclude workflow.
5. Choose **Restore Original World** to remove managed dome data and reassign the untouched original World.

<img width="1920" height="1034" alt="World-Environment-Linking" src="https://github.com/user-attachments/assets/2b2a7d6d-4cc8-4529-a302-12b98a912ad0" />

The converter:

- follows the active World Output through nested node groups, directly reuses packed Image data-blocks, and falls back to the connected Background color when no usable image exists;
- keeps one managed dome per scene, isolates copied scenes on first access, and never identifies user objects by name alone;
- preserves the original World, including its Volume connection, in a scene-local fallback copy while converted;
- automatically gives each Sun an internal Exclude proxy without replacing user-authored receiver links;
- repairs replaced or damaged Sun receivers/proxies without accumulating duplicate records;
- preserves shared, mixed Include/Exclude, and library-linked Sun receiver collections;
- keeps transparent-film renders transparent by disabling the dome's Camera visibility at conversion time;
- exposes the base color for solid-color sources, plus strength, tint, gamma, saturation, radius, ray visibility, and integer Total/Diffuse/Glossy/Transmission depth limits; HDRI sources also expose rotation and mapping.

<img width="1920" height="1034" alt="Sun-Isolation" src="https://github.com/user-attachments/assets/66a7b5cd-a679-415c-95ef-a85773c0731f" />

The four depth controls are material-level artistic gates: `0` keeps direct rays and blocks indirect rays of that type. They do not change the scene-wide Cycles bounce settings.

If no usable Environment Texture image is found, LightHelper converts a constant Background color on the active output path instead. Unsupported procedural World color graphs remain unchanged. If several connected HDRI images are found, LightHelper reports the ambiguity and uses the nearest image on the active output path.

If a converted scene is opened or switched to Eevee, LightHelper preserves the managed dome and its settings without modifying user data. The unsupported World Environment panel and emissive-material source filter are hidden there; switch back to Cycles to edit or restore the managed World.


## Other features

### Emissive-material detection

In Cycles, objects with a connected, non-zero emissive material can appear in the source list. LightHelper follows nested node groups up to the configured **Emission Node Search Depth**. In Eevee, the source list intentionally keeps only native Blender Light objects because Blender does not support Light Linking for emissive meshes there.

For complex materials, a high search depth can make list refreshes slower. Reduce the value if the interface stutters. To use an emissive source as the interactive tool's light subject, select it from the sidebar first or left-click it while the tool is already in Light mode; `Ctrl` + left-click on a non-Light object selects it as an object subject.

Automatic source detection:

https://github.com/user-attachments/assets/833e55e3-7bd2-4476-a275-78cbcd96f6f8

### Solo Light

Solo isolates the chosen native Light from the currently filtered light set. Press it again to restore the previous viewport, render, and local-hide states.
<img width="1920" height="1034" alt="light-solo" src="https://github.com/user-attachments/assets/66429420-9350-4cad-90b3-c1261348c7c8" />


### Shared linking data and duplicates

Duplicated lights can share Blender linking collections. Use **Make Single-User** for one light or **Make All Single-User** when each duplicate needs independent links.

**Auto Fix Shared Linking** is optional and disabled by default. When enabled, it separates shared linking collections only for explicitly detected duplicates and does not run while a file is opening.
<img width="1440" height="776" alt="auto-separate-linking" src="https://github.com/user-attachments/assets/9376a75b-8559-48b9-8350-428f51fe5703" />


### View movement

Choose how selecting a light or linked object affects the viewport:

- **None** — select without moving the view.
- **Maintaining Zoom** — move directly while preserving the current zoom.
- **Animation** — animate the view transition.

https://github.com/user-attachments/assets/9ab4f865-904a-4030-976e-2d6b3d0b5e13


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

## Known limitations

Emissive surfaces can still be visible in Eevee and may contribute through limited screen-space indirect lighting or baked light probes. However, Blender supports emissive-mesh Light Linking only in Cycles. Enabling Eevee ray tracing does not make the inward environment dome replace the native World, nor does it provide this workflow's reliable per-object linking and Light Path depth gates. LightHelper therefore hides these unsupported controls in Eevee; use Cycles for World environment exclusion.

## FAQ

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

- Switch the render engine to **Cycles**; emissive-material sources are intentionally hidden in Eevee.
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
