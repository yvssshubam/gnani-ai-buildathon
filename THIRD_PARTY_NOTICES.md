# Third-party notices

Surgeline is © 2026 Y.V.S.S.Shubam. It uses the services, data and open-source libraries
below. Each stays under its own owner's terms and licence; this file lists them and gives the
credits their terms ask for.

## Services

| Service | Used for | Terms |
|---|---|---|
| **Gnani AI**: Prisma (speech to text), Timbre (text to speech) | Hearing the caller and speaking the agent's replies | Gnani's API terms; needs your own `GNANI_API_KEY` |
| **Groq** (OpenAI-compatible API) | Reading each caller turn, call notes, the simulated caller | Groq's API terms; needs your own `LLM_API_KEY` |
| **Nominatim** (OpenStreetMap address search) | Placing areas and PIN codes that aren't on our own list | [Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/): at most one request a second, an app-identifying User-Agent, results cached, attribution shown. Surgeline does all four. Turn it off with `GEOCODE_ENABLED=0`. |
| **OpenFreeMap** | Map tiles on the dashboard | [openfreemap.org](https://openfreemap.org); attribution shown on the map |

## Data

- **OpenStreetMap.** Address search results and map tiles come from OpenStreetMap data.
  Map data © OpenStreetMap contributors, available under the
  [Open Database License (ODbL) 1.0](https://www.openstreetmap.org/copyright).
- **OpenMapTiles.** The tile schema used by OpenFreeMap. © OpenMapTiles.
- **Our own locality list** (`backend/app/gazetteer.py`) has approximate area-centre
  coordinates written for this demo.

## Models

- **gpt-oss-20b and gpt-oss-120b** (OpenAI), run on Groq. Released under the
  [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0).

## Open-source libraries

Backend (Python):

| Library | Licence |
|---|---|
| FastAPI | MIT |
| Uvicorn | BSD-3-Clause |
| Pydantic | MIT |
| HTTPX | BSD-3-Clause |
| RapidFuzz | MIT |
| indic-transliteration | MIT |
| pytest (tests only) | MIT |

Frontend (JavaScript):

| Library | Licence |
|---|---|
| React | MIT |
| Vite | MIT |
| MapLibre GL JS | BSD-3-Clause |

Each library's full licence text ships with the package (in `site-packages` for Python and
`node_modules` for JavaScript).