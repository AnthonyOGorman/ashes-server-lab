# Asset serialization evidence

Unversioned Unreal object values require property mappings beyond package headers. SDK-derived mappings here are inferred candidates. Their memory offset/declaration order has not been independently established as serialization order. Schema versions, hashes, exclusions, unknown types, and SDK provenance limits are saved under `schemas`.

## Class metadata

| Check | Result |
| --- | --- |
| Empty-metaclass baseline | 624 terminal candidates; 6,816 partial exports |
| Strict SDK-schema pass | 7,440 parsed classes; zero explicit failures |
| Visible-cursor replay | 7,440 exact payload consumptions |
| Header reference checks | 16,820 matching references; zero mismatches |
| Function-map checks | All 9,380 labels/targets match function exports |
| Recovered structure | 98,824 child fields; 15,373 metaclass property entries |

The classes comprise 6,299 regular Blueprint generated classes, 414 animation classes, and 727 widget classes. Candidate properties expose construction scripts, inherited component handlers, widget trees, animation metadata, and ubergraph pointers. These references identify further objects to inspect; they do not establish that all those objects have been decoded.

The replay reconstructs a fresh object with a visible archive cursor using the inspected UE5.3+ IoStore export-offset formula. It uses the same parser, not an independent implementation. Exact consumption can coexist with an incorrect same-size field interpretation. Header cross-checks establish reference identity, not gameplay effects.

Raw passes are `index/blueprint-class-schema-v1.jsonl`, `blueprint-class-schema-v2-strict.jsonl`, and `blueprint-class-schema-v3-consumption.jsonl`, with package checkpoints and logs. The completed class experiment is bound to `sdk-offset-order-v1-*` schemas. Its summary is `index/schema-candidate-summary.json`.

The cached tool's implementation listings in `proofs/cue4parse-IoPackage.cs`, `cue4parse-AbstractUePackage.cs`, and `cue4parse-UObject.cs` explain parsing behavior. These listings are analysis-tool code, not game source.

## Default objects

The separate default-object pass resolves generated fields from class metadata and native fields from v2 candidate schemas. The schema revision repairs 709 aligned SDK declarations; evidence is in `index/sdk-declaration-repairs.json`. Earlier schema and trial files are preserved.

| Default-object outcome | Count |
| --- | --- |
| Exact-consumption candidate | 6,907 |
| Explicit parser failure | 277 |
| Under-consumed payload | 240 |
| Over-consumed payload | 16 |

The importer retains 81,099 serialized property entries across parsed objects, including objects needing review. Join property rows to their candidate status before using them. The parser's unknown-zero-property warnings remain in logs. Serialized overrides do not constitute fully resolved defaults: omitted zeros, inherited defaults, nested components, and referenced assets require further checks.

Raw results are `index/blueprint-defaults-v1.jsonl` and `blueprint-defaults-v2.jsonl`, with separate checkpoints/logs. The current summary and grouped errors are in `index/default-candidate-summary.json`. Additional nested exports, failed defaults, and assets outside the selected packages remain future work.

## Selected configuration assets

A separate `--asset-values` pass decoded 653 selected exports with exact byte consumption, matching header identities, and zero recorded parser warnings: 167 InputActions, one mapping context, one input config, 30 data tables, 12 behavior trees, 111 blackboards, and 331 state trees. The candidate tables retain 6,698 properties, 526,357 table rows, and 74,816 references. Two biome grids account for 524,288 of the rows. Reference checking matched 33,275 indexed exports; 41,541 references remain outside the header subset.

See `INPUT_CONFIGURATION.md`, `index/asset-values-summary.json`, and the `asset-value-*` catalogs for results and limits. Nested AI nodes, input triggers/modifiers, and referenced assets need separate payload and behavior review. The mappings remain inferred even when complete payload consumption passes.

## Search and reproduce

The `blueprint_schema_*` SQLite tables and CSV catalogs keep recovered class candidates separate from the original empty-schema baseline. Default results use `blueprint_default_candidates` and `blueprint_default_properties`.

```powershell
python client-research/scripts/query.py sql "SELECT package,cls,name,type FROM blueprint_schema_fields WHERE package LIKE '%Inventory%'"
python client-research/scripts/query.py sql "SELECT p.package,p.name,p.value,c.status FROM blueprint_default_properties p JOIN blueprint_default_candidates c ON c.package=p.package AND c.cls=p.cls WHERE p.name LIKE '%Cooldown%'"
python client-research/scripts/import_schema_candidates.py
python client-research/scripts/import_default_candidates.py
```

The compiled asset helper supports `--class-schema` and `--defaults`, followed by a package limit, struct-schema path, and enum-schema path. Fatal exceptions, terminal gates where applicable, hashes, and measured consumption are recorded. Checkpoints skip attempted packages; retry failures in a new versioned output. The current default-output version derives from the schema filename. Preserve versions used by saved evidence.

`repair_sdk_declarations.py` verifies SDK source hashes and repairs in place. `build_schema_candidates.py --version v2` writes the corrected candidate schemas. `build_index.py` discards derived indexes; do not use it for routine repairs. `coverage.json` is the authoritative changing summary.
