# License Review

Research used the following repositories at pinned revisions:

| Project | Revision | License | Use in this repository |
|---|---|---|---|
| `trovis-modbus_python-library` | `c4a8349` | Apache-2.0 | Behavioral and matrix research; possible future dependency. |
| `samson_trovis_557x` | `ebfeaaa` | Apache-2.0 | Behavior, integration, discussions, and FW evidence. |
| `modbus-connection` | `28ebad9` | Apache-2.0 | Optional live dependency and architecture reference. |
| Pydantic | runtime dependency | MIT | Validation and serialization. |

The Phase-1 implementation was written for this repository; no third-party
source file was vendored or copied. Source locations are cited in documentation
and matrix metadata. Installing the optional `live` extra downloads the
dependencies under their own licenses; distributions must retain their license
and notice files as required.

Official SAMSON manuals and the local TROVIS-VIEW exports are reference
material, not project code. They remain under their respective rights and are
not relicensed by the project's Apache-2.0 metadata. Before public distribution,
confirm that the locally supplied PDF and `.tro_55xx` may be redistributed;
otherwise keep them out of release artifacts and publish only derived facts
that are permitted to be shared.

No dependency license conflict was identified for an Apache-2.0 application.
This review is technical inventory, not legal advice.
