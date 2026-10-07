# Roadmap

This is an ordered list of useful directions, not a delivery schedule.

## Stabilize exploration

1. Measure walking prediction differences using matched input/time/position traces. Resolve correction pushback without hiding large genuine errors.
2. Decode the period-key walk toggle and Shift/sprint state. Match speed, acceleration, braking and movement-mode transitions to the client.
3. Make live settings readback and initialization failures easier to diagnose and recover.
4. Cover longer sessions, timestamp wraparound, reconnects, lower frame rates and multiple local clients.

## Improve world fidelity

1. Implement reliable static-prop extraction and transforms, including collision channels/responses, complex/simple selection and unsupported shape admission.
2. Study water, swimming, movement bases, slopes, step-up behavior and streaming boundaries.
3. Add explicit separate-map selection and collision admission before attempting travel.

## Make the foundation maintainable

1. Refactor dense generated code into documented stages and protocol types.
2. Add a build-profile layer for offsets, schemas and evidence. New profiles need actual native verification.
3. Add CI for source-only synthetic checks and offline format fixtures that contain no game assets.
4. Improve deterministic replay and sanitized bug-report export.

## Only then expand gameplay

NPCs, combat, inventory, abilities, quests, progression, persistence, social systems and safe public hosting require substantial research and implementation. Nothing in the current demo establishes those systems. Start with a small, verified vertical slice.
