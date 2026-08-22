# Data sources

## Training (not live)

INDOFLOODS (https://zenodo.org/records/14584655) local copies:

| File | Role |
| --- | --- |
| floodevents_indofloods.csv | Event labels (`Flood` / `Severe Flood`), dates |
| precipitation_variables_indofloods.csv | Cumulative precip T1d–T10d |
| catchment_characteristics_indofloods.csv | Static catchment / climate |

`metadata_indofloods.csv` was not present in `dataset/` and is not required by the training script.

## Live

| Signal | Primary | Fallback |
| --- | --- | --- |
| Weather / humidity / wind / pressure | OpenWeather (`OPENWEATHER_API_KEY`) | Open-Meteo (no key) |
| 24h rainfall + 10-day precip forecast | Open-Meteo | OpenWeather 3h forecast |
| River / dam stage proxy | Open-Meteo Flood API (Yamuna ITO, Hathnikund) mapped onto configured danger level `205.80 m` | Last Mongo observation, else `DATA SOURCE UNAVAILABLE` |
| Routing / traffic | Curated Delhi road graph + runtime blockage flags | TomTom key is accepted in env for future live traffic; current route costs use stored `traffic` and `flood_exposure` |
| Map tiles | OpenStreetMap | — |

India-WRIS authenticated gauge APIs are **not** called unless a working key/URL is provided. The backend does not invent CWC readings.

## Operational geography

Delhi NCR coordinates for Yamuna (ITO), Hathnikund Barrage, Okhla, public-facility shelters, and NDRF/DFS/police staging points are curated real locations with explicit capacities used by the shelter engine.
