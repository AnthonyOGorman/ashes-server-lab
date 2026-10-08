# Client ability cooldown path

This records selected behavior in the exact executable fingerprint from `README.md`. Addresses are RVAs. Constructor-installed virtual dispatch is established statically; subclasses can override it. No game process was launched during this research.

## From reflection to implementation

The class accessor at `0x5cce8c0` references the ability-component name, registration callback `0x5cd2030`, class size `0xce0`, and callback `0x5cd0500`. The registration callback presents 109 native registration entries. Callback `0x5cd0500` loads the object pointer and branches to `0x6b8cd00`. That constructor calls its base initializer and then installs primary vptr `0xb6873d0` at the object's first qword. The inspected 212 table entries all point into executable sections; the count is an explicit bounded inspection, not a recovered universal class ABI.

| Reflected method | Thunk | Slot | Constructor table target |
| --- | --- | --- | --- |
| GetRemainingAbilityCooldown | `0x5cd4b00` | `0x648` | `0x6ba73d0` |
| GetRemainingAbilityCooldownPercent | `0x5cd4c30` | `0x658` | `0x6ba7540` |
| IsAbilityOnCooldown | `0x5cd5300` | `0x668` | `0x6bb40c0` |

`record_cooldown_dispatch.py` checks the executable hash, callback bytes, constructor LEA/store pair, each thunk's slot reference, and each table qword. It saves `proofs/cooldown-dispatch.json`. `inspect_vtable.py` preserves all inspected entries in `proofs/ability-component-vtable.json` and `.csv`. The database stores separate `native_virtual_slots` and `native_dispatch_links` records; these are constructor-table links, not fresh runtime observations.

## Data and matching

AoCAbilityComponent.Cooldowns is at `0xa10`. Its CooldownInstArray.Items field is at `0x108`, giving the array data pointer at component offset `0xb18` and count at `0xb20`. The implementations advance by `0x38`, matching the SDK size of CooldownInst.

| CooldownInst field | Offset | Use in reviewed paths |
| --- | --- | --- |
| AbilityGuid | `0x10` | Resolve the associated ability record |
| bCooldownTriggered | `0x18` | Returned by the active-state check |
| InitialCooldown | `0x1c` | Positive denominator for the remaining fraction |
| CooldownSynchronizedStartTime | `0x20` | Present in SDK; not used by these getters |
| CooldownSynchronizedEndTime | `0x28` | End time used by both numeric getters |
| Charges | `0x30` | Present in SDK; not used by these getters |
| bExpiredOnClient | `0x34` | Present in SDK; not checked here |
| PredictionState | `0x35` | Present in SDK; not checked here |

Lookup helper `0x6ba5490` scans in array order and skips entries whose record cannot be resolved. Matching helper `0x61e53c0` accepts equal Guid values at record offset `0x8`, or a nonzero SharedCooldownTag at `0x340` that equals the requested record's tag. It compares the raw eight-byte tag representation. It returns the first matching index, or `-1`.

This is evidence for shared cooldown grouping in the client. Record-resolution/cache helpers and duplicate-entry lifecycle remain separate work. The GUID field is inherited from DesignDataPlugin.DesignDataRecordBase; SharedCooldownTag is in AoCAbilityRecordBase.

## Numeric getters and active flag

For ordinary finite values, GetRemainingAbilityCooldown returns `max(endTime - timeValue, 0)` as a float for the first resolved matching entry. No match returns zero. The path uses the chained fragment at `0x6ba7501`, whose unwind root is `0x6ba73d0`; the exact instruction proof and Ghidra output include that arithmetic.

GetRemainingAbilityCooldownPercent skips matching entries with nonpositive InitialCooldown. For the first resolved matching entry with a positive denominator, it returns `clamp((endTime - timeValue) / InitialCooldown, 0, 1)` as a float. No qualifying entry returns zero. The upper clamp constant at `0x9ddb290` is exactly double `1.0`. It returns a fraction, rather than multiplying by 100. The exact SSE comparison/min/max instructions are preserved; exceptional floating-point values have not been reviewed as gameplay cases.

IsAbilityOnCooldown calls the matching-index helper. If an entry is found, it returns bCooldownTriggered; otherwise its boolean return byte is zero. It does not itself compare the stored end time to the clock. Ghidra gives this small routine a misleading wider return type; the thunk consumes the low boolean byte and the instructions establish that byte's behavior.

Consequently, a zero remaining-time value and a false active flag are separate observations. The record mutation, trigger/expiry, replication, and prediction paths determine how those states stay consistent and remain unreviewed.

## Time source and inventory connection

Time helper `0x6456100` obtains a world through virtual dispatch, reads its game-instance pointer, and checks it against the class accessor whose name reference identifies AoCGameInstance. On that valid path it returns the greater of two doubles at instance offsets `0x1f60` and `0x1f68`. Their names and update logic are not established by the saved SDK. Failed context/type checks return literal `9115200.0`; the intended role of that fallback remains unresolved.

The previously reviewed inventory helper `0x678a7a0` reaches the same remaining-time and remaining-fraction virtual interfaces through the owning character's AbilityComponent. InventorySlotBase.HandleCooldown uses the fraction for its material parameter `percent` and updates cooldown text/widget state. This ties UI behavior to these constructor-table implementations for objects using that table, while preserving the possibility of overridden dispatch.

## Evidence and remaining work

Exact `.asm`, `.bin`, and hash-bound `.json` fragments are saved under `proofs` for the class accessor, callback, constructor entry, numeric implementations, active predicate, index search, record match, and time-context accessor. Bounded direct-call traces are `trace_6ba73d0.json`, `trace_6ba7540.json`, and `trace_6bb40c0.json`. Ghidra outputs are `decompiled/bulk/function_6ba73d0.c`, `function_6ba7540.c`, `function_6bb40c0.c`, `function_6ba5490.c`, and `function_6456100.c`.

Next inspect record updates, trigger/expiry transitions, prediction-state changes, charges, replication callbacks, shared-tag ordering, clock maintenance, and subclass overrides. These getter observations do not reconstruct authoritative remote cooldown rules.
