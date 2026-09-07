# CIFP evidence and support boundary

Evidence reviewed on 2026-09-07. This implementation reads local files only and
does not accept the FAA customer agreement or obtain the agreement-gated ZIP.

## Official evidence

- [FAA CIFP product page](https://www.faa.gov/air_traffic/flight_info/aeronav/digital_products/cifp/)
  describes raw ARINC 424-18 data and a 28-day update cycle. The download workflow
  requires the Customer Agreement for Error Notification, including for a person
  who will neither navigate with nor distribute CIFP data.
- [FAA CIFP Readme](https://aeronav.faa.gov/Upload_313-d/cifp/CIFP%20Readme.pdf),
  volume 2609, dated 2026-08-12, page 1: **2026-09-03 09:01 UTC through
  2026-10-01 09:01 UTC**. These are product-specific boundaries, not AIRAC calendar
  defaults. The URL is mutable; the downloaded evidence belongs with the release's
  immutable raw inputs. Local research cache: `.cache/cifp-evidence/CIFP-Readme.pdf`.
- Readme pages 2-4 specify record families, airport identifier fallback, FAA code
  in the ATA/IATA field, waypoint scope, and field exceptions. PA's airport
  identifier is not always an ICAO code; missing ICAO identifiers must not be
  manufactured from FAA identifiers.
- Readme page 4 applies ARINC 424-19 exceptions to procedure identifier columns
  14-19, route type column 20, route qualifier 1 column 119, the level-of-service
  continuation record, and the circling altitude 1 field. RNAV (RNP) approaches
  use `H` and `F` in the described fields.
- Readme page 6: file record numbers can contain letters or blanks. Record cycle
  dates identify changed records, not the validity interval for the whole product.
  Final and missed approaches share route type; therefore route type alone cannot
  identify or safely split the missed approach.
- Readme page 7 excludes ILS CAT II, ILS CAT III, PRM, converging ILS, GLS, and
  visual procedures. Alternate missed approaches (route type Z) are excluded on
  page 6. Not-In-CIFP coverage and d-TPP chart coverage are independent concepts.

The Readme is not a complete field specification, geometry standard, or golden
sample set. No real SID, STAR or approach has been independently validated in
this change. Those acceptance items remain blocked.

## Public structural reference

The field-position reference is
[jack-laverty/arinc424](https://github.com/jack-laverty/arinc424/tree/f8c65377e38551c15d6429658bdfde891af1c01c),
commit `f8c65377e38551c15d6429658bdfde891af1c01c`, MIT license, reviewed through the
public GitHub API. Relevant source files are `record.py` and
`definitions/{airport,runway,waypoint,vhf_navaid,ndb_navaid,enroute_airways,sid_star_approach}.py`.
Only field positions inform the independently written structural reader. The
reference's decoding routines and its validation assumptions are not adopted.
In particular, its numeric trailing-record-number check conflicts with the FAA
Readme, and it cannot be treated as authority for all CIFP semantics.

All columns below are **one-based, inclusive**, and values are retained verbatim:

| Family | Structural fields read |
|---|---|
| Common | record 1; area 2-4; section 5-6 or 5+13 for terminal P/H; scope 7-10; region 11-12; record number 124-128; changed cycle 129-132 |
| PA | airport 7-10; FAA identifier 14-16; continuation 22; latitude 33-41; longitude 42-51; name 94-123 |
| PG | runway 14-18; continuation 22; length 23-27; bearing 28-31; latitude 33-41; longitude 42-51; description 102-123 |
| EA, PC | waypoint 14-18; point region 20-21; continuation 22; latitude 33-41; longitude 42-51; name 99-123 |
| D-space, DB | navaid 14-17; point region 20-21; continuation 22; frequency 23-27; latitude 33-41; longitude 42-51; name 94-123 |
| ER | route 14-18; sequence 26-29; fix 30-34; fix region 35-36; fix section 37-38; continuation 39; descriptor 40-43; route type 45; direction 47 |
| PD, PE, PF | procedure 14-19; route type 20; transition 21-25; sequence 27-29; fix 30-34; fix region 35-36; fix section 37-38; continuation 39 |
| PD, PE, PF primary | descriptor 40-43; terminator 48-49; altitude descriptor 83; altitude 85-89 / 90-94; speed 100-102; qualifier 119-120 |

Latitude syntax is `N/S + DDMMSSss`; longitude is `E/W + DDDMMSSss`, with
hundredths of arc-seconds. Values outside legal degrees/minutes/seconds are
errors. Raw restriction values remain strings; the reader does not interpret
altitude, speed, course, DME offsets or navigation instructions.

PN identifier width is not enabled: the Readme describes five-letter names while
the inspected NDB helper has a four-character identifier slice. Other families,
continuation semantics, airway branch assembly, fix resolution, final/missed
partitioning, and ARINC 665 data-wrapper CRC semantics remain unverified.

## Machine-visible support

- `parse_cifp` returns structural records, original lines and provenance. Primary
  coordinates are saved as `coordinate_candidate`, never published geometry.
- Syntactically readable rows count as unsupported until independently verified;
  malformed rows count as errors. The report always includes blocking issue
  `cifp-evidence-incomplete`, and `capabilities` is empty. There is no switch that
  lets a caller silently turn this report into a verified release.
- Program legs retain `branch_candidate_key` for inspection; `branch_id` remains
  unset because final/missed segmentation is unverified. Scoped IDs do not merge
  same-name fixes. Continuation rows remain identifiable and raw.
- Resolving this blocker requires the user to obtain a file through the official
  agreement workflow, freeze its SHA-256 plus Readme and format evidence, and have
  independent expected records approved for each enabled family and SID/STAR/
  approach sample. It also requires explicit continuation/reference/branch rules.
  Merely supplying a file or setting the local-use permission is insufficient.

## Independent geometry engine

`geometry_for_legs` uses normalized, explicitly unique fix references, independent
of the unverified CIFP reader. IF shows a point. TF only follows a successfully
rendered adjacent IF/TF in the same named branch and procedure. Unsupported or
unresolved legs break the chain until another IF. Branch filtering does not
create adjacency. Original order is never silently sorted.

GeographicLib WGS84 geodesics are sampled at no more than 1 nautical mile (1852
meters). Segments crossing longitude 180 are split at the exact geodesic crossing,
including reverse direction. The result describes nominal points/lines and
explicit gaps, not complete flight-turn trajectory prediction. Synthetic tests
exercise this engine without asserting FAA data coverage.

## Third-party field reference notice

MIT License

Copyright (c) 2022 Jack Laverty

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
