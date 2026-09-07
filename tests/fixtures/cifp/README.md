# CIFP structural test fixtures

All records in these tests are **synthetic**, using the frozen public field positions
recorded in `docs/cifp-support.md`. They are not downloaded FAA data or evidence that
a real SID, STAR, approach, or record family has passed independent validation.

Frozen expectations before implementation:

| Input | Expected result |
|---|---|
| `N37451234`, `W122301234` | 37 + 45/60 + 12.34/3600; -(122 + 30/60 + 12.34/3600) |
| `S90000000`, `E180000000` | -90 and 180 |
| latitude `N90600000`, longitude `E180000001`, decimal/non-ASCII digits | Error; no coerced coordinate |
| 132-character PA with `SYN1`, `SYNTHETIC AIRPORT`, FAA field `ZZ1` | Scoped airport identity, verbatim fields and line provenance; no published geometry |
| Same waypoint name in EA and airport-scoped PC | Two distinct record identities |
| PD/PE/PF raw prefix with continuation `0` | Structural leg associated with a procedure of type SID/STAR/APPROACH; branch remains unverified |
| Procedure continuation `2`, application `E` | Raw continuation retained; never decoded as a primary leg |
| File record number `A1  Z` or blank | Preserved; never required to be numeric (FAA Readme page 6) |
| Malformed supported record or duplicate scoped identity | Error reported with source position; all input counts still balanced |
| Unknown family | Raw frame retained in report context and counted unsupported |
| Every syntactically valid test file | Candidate remains blocked by `cifp-evidence-incomplete`, with no verified capabilities |

Readme excerpts in `test_cifp.py` are based on the FAA Readme volume 2609,
retrieved 2026-09-07, and freeze its actual 09:01 UTC boundaries without applying
those boundaries to any other product.
