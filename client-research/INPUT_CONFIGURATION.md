# Cooked input and configuration assets

The selected pass decoded 653 configuration exports with exact payload consumption and no recorded parser warnings. It includes 167 InputAction assets, one base-character input config, and one mapping context. Schemas remain inferred; live bindings, nested trigger/modifier behavior, and omitted defaults need separate validation.

The mapping context contains 170 declared bindings; the config has 164 serialized field references. All bindings are saved in `catalogs/input-bindings.csv`; normalized action metadata and original references are in `proofs/input-configuration.json`.

## Selected default bindings

| Action | Key | Trigger references |
| --- | --- | --- |
| IA_Jump | SpaceBar | 1 |
| IA_Sprint | LeftShift | 1 |
| IA_CharacterMoveForward | W | 1 |
| IA_CharacterMoveBackward | S | 1 |
| IA_CharacterMoveLeft | A | 1 |
| IA_CharacterMoveRight | D | 1 |
| IA_Attack1 | E | 1 |
| IA_Dodge | Z | 1 |
| IA_Guard | R | 1 |
| IA_CharacterMoveForward | LeftMouseButton | 1 |

The base-character config maps ToggleSprint to IA_Sprint. This connects the declaration to an action name; the input handler and trigger execution are still needed to establish how it changes sprint requests.

## Data tables

The pass recovered 526,357 rows across 30 tables. Two biome-selection grids contribute 262,144 rows each; those counts should not be presented as hundreds of thousands of gameplay rules. Other tables include vendors, dialogue audio, remappable key bindings, economic regions, and UI styles.

| Table | Rows |
| --- | --- |
| DT_BiomeSelect_V2 | 262,144 |
| DT_BiomeSettingSelection | 262,144 |
| VendorTable | 870 |
| DialogueAudioTable | 614 |
| DT_MasterRichTextStyles | 163 |
| DT_RemappableKeyBindings | 160 |
| DT_CombatTooltipStyles | 51 |
| DT_EconomicRegions | 30 |
| DT_CombatTooltipImagesCustom | 28 |
| DT_LandscapeLayerTagList | 22 |
| DT_BiomeDecalMaterials | 20 |
| DT_HyperLinks_Common | 17 |
| DT_RiverlandsFoliage | 16 |
| DT_HyperLinksForChat | 15 |
| DT_LightTypeDefaultTable | 11 |
| DefaultGeometrySurfacePropertiesTable | 11 |
| DT_BiomeClimateV5 | 8 |
| DT_NodeShapes | 5 |
| DT_CombatTooltipImages | 5 |
| DT_Building_Modules | 3 |
| DT_DesertFoliage | 3 |
| DT_SeasonDesignation | 3 |
| CommonInputData | 3 |
| DT_Archetype_Striketeam_Testing | 3 |
| DT_SocketPairList | 2 |
| ChatDataTable | 2 |
| DT_ChatDataTable | 2 |
| DT_Floor_Patterns | 1 |
| ResourceNodeTable | 1 |

Raw candidates, properties, table rows, and references are in the `asset_value_*` and `asset_table_rows` SQLite tables and corresponding catalogs. The AI/configuration pass also includes 12 behavior trees, 111 blackboards, and 331 state trees. Root references and serialized state metadata are decoded; a referenced object is not automatically a decoded object.

33,275 object references matched separately indexed package headers; 41,541 lie outside that header subset and remain explicitly unresolved. These relationships guide expansion of the header/export map.
