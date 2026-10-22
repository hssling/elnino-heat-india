# El Niño, heat extremes, drought and mortality in India, 2001–2024

Data and code for the study of the El Niño–Southern Oscillation (ENSO) and recorded heat/sun-stroke deaths (primary outcome), farming-sector suicides and foodgrain production (secondary outcomes) in 34 Indian state-level units, 2001–2024, with projections for 2027.

Repository: https://github.com/hssling/elnino-heat-india

**Paper (manuscript under review):**
Siddalingaiah H S. El Niño, heat extremes, drought and mortality in India, 2001–2024: a state-level analysis with projections for 2027. Manuscript under review.

Please cite the paper once it is published, and this repository through `CITATION.cff`.

Companion repository (same pipeline, malaria and dengue): https://github.com/hssling/elnino-malaria-india (archived at https://doi.org/10.5281/zenodo.23424043).

## Responsible reporting

Farmer suicides are a sensitive outcome. This repository contains only aggregated, state-year counts of suicides in the farming sector as published by the National Crime Records Bureau (NCRB). It contains no individual records, names, methods or locations below the state level. If you report on these data, follow the World Health Organization's guidance for media professionals (*Preventing suicide: a resource for media professionals*, update 2023, https://www.who.int/publications/i/item/9789240076846) and the Press Council of India's norms on reporting suicide, which adopt that guidance. Do not describe suicide as a solution or an inevitable result of drought, and do not report methods.

*If you or someone you know is in distress, Tele-MANAS, India's national tele-mental health helpline, can be reached free of charge on 14416 or 1-800-891-4416 (Press Information Bureau, 29 May 2024, https://pib.gov.in/PressReleasePage.aspx?PRID=2022057).*

## Contents

```
.
├── data/
│   ├── raw_files_manifest.csv         public URL, retrieval time, SHA-256 and size of every raw file used
│   └── derived/
│       ├── outcomes/                  state x year outcome panels and their provenance files
│       ├── model/                     model-ready inputs read by the R analysis
│       ├── climate_unit_year.csv      climate exposures pooled to the 34 units, 1981–2025
│       └── enso_{monthly,annual,episodes}.csv
├── models/                            R analysis (renv-locked)
│   ├── common/                        shared model functions (glmmTMB negative binomial) and testthat suite
│   ├── C/                             the analysis of this study (run_all.R and its steps)
│   ├── renv.lock, renv/, .Rprofile, DESCRIPTION, setup.R
├── papers/C/
│   ├── results.json                   every number reported in the paper (value, display, script, description)
│   ├── supplementary/                 Supplementary Tables S1–S7 (CSV), written by the analysis
│   └── figures/                       figure data (CSV) and the plotting script
├── pipeline/                          Python pipeline: raw sources -> derived tables
│   ├── outcomes/                      parsers, source precedence, gates for the outcome panels
│   └── reference/                     unit frame, source list, reviewed exceptions, QC reviews
├── tests/                             pytest suite for the pipeline (and, with -m r, the R suite)
├── tools/build_subdivision_map.py     builds pipeline/reference/district_to_imd_subdivision.csv
├── run_all.py                         pipeline orchestrator
├── pyproject.toml, requirements.txt
├── LICENSE (code, MIT), DATA_LICENSE.md (derived data, CC BY 4.0), CITATION.cff, .zenodo.json
```

No manuscript text is included. Raw source files are not redistributed (see Provenance and Reproduction).

## Data dictionary

All tables are UTF-8 CSV. Missing is an empty cell (NaN), never 0; a printed 0 is 0 unless a rule below says otherwise.

### The 34-unit frame

`pipeline/reference/state_frame.csv` defines 34 analysis units (`unit_id`, `unit_name`, member GADM state ids, name aliases). Three units pool states, because the outcome sources report them together in some years and separately in others, and the reorganisations would otherwise break the series:

| unit_id | members | reason |
|---|---|---|
| AP_TG | Andhra Pradesh + Telangana | Telangana was formed in 2014; sources before and after report one or two states |
| JK | Jammu and Kashmir + Ladakh | Ladakh became a UT in 2019; GADM and the pre-2019 sources have one unit |
| DNH_DD | Dadra and Nagar Haveli + Daman and Diu | merged in 2020; earlier sources report two rows |

Pooling rule (applied within one source document): member counts are summed with NaN skipped, so a pooled unit-year is NaN only if every member is NaN; a pooled value with a NaN member is recorded as `partial_pool`. Totals and sub-totals ("All India", "Grand Total", "Total (States)") are recognised as `TOTAL` and never summed into units. Climate exposures for the same units (`climate_unit_year.csv`) are pooled as an area-weighted mean over non-NaN members.

### Outcome panels (`data/derived/outcomes/`)

Each panel has one row per unit-year for the units and years shown (NaN rows included): `unit_id`, `unit_name`, `year`, the variables, `provisional_any` and `sources` (winning source per variable, `variable:source_id;...`; `masked` or `non_reporting` where a reviewed disposition blanked the value). Panels hold counts (foodgrain: tonnes); `population` is merged for rate construction. No panel value is provisional.

| File | Units x years | Variables | NaN cells |
|---|---|---|---|
| `heat_deaths_state_year.csv` | 34 x 2001–2024 | `heat_deaths` (accidental deaths due to heat/sun-stroke recorded by NCRB), `population` | none |
| `farmer_suicides_state_year.csv` | 34 x 2001–2023 | `farmers`, `ag_labourers`, `farming_sector` (= `farmers` before 2014; `farmers` + `ag_labourers` from 2014), `definition_break_2014`, `population` | `farmers` 97, `ag_labourers` 479 (all pre-2014 rows plus 37 non-reporting), `farming_sector` 112 |
| `foodgrain_state_year.csv` | 30 x 1997–2016 | `foodgrain_t` (total foodgrain production, tonnes: RBI's '000 tonnes x 1000) | 18 (see Missing-data rules) |
| `population_unit_year.csv` | 34 x 2001–2027 | `population`, `source` | none |

Other files:

- `outcome_records_all.csv.gz`: every parsed heat-death, farmer-suicide and foodgrain record from every source in long format (`outcome, unit_id, raw_label, year, variable, value, source_id, provisional`; 4,524 records), including values later overridden, printed zeros and totals. The three panels are rebuilt exactly from this file plus `pipeline/reference/outcomes_reviewed.csv`. Printed zeros later judged non-reporting are kept here, so the true-zero sensitivity analysis can restore them.
- `cross_source_report.csv`: every pair of sources that disagree on a unit-year-variable, with `provisional_pair`, `lower_bound_pair`, `partial_pool`, `reviewed` and `gating`. All 184 rows are foodgrain pairs against the ICRISAT district-database lower bound (reported, never gating); the heat and farmer sources agree wherever they overlap.
- `missing_sources.csv`: sources that could not be used (NCRB farmer tables 1997–2000, `foodgrain_rbi2023`) and why.

Source precedence. `pipeline/reference/outcomes_sources.csv` lists every source with its public URL, years, `rank` and notes. For each unit-year-variable the value comes from the highest-ranked source that has one, except that a final value beats a provisional one at any rank. Rank 0 means cross-check only, never chosen.

| Outcome | Sources, low to high precedence (ids as in `outcomes_sources.csv`) |
|---|---|
| heat deaths | `heat_pib1721` (2017–21, Ministry of Earth Sciences annexure released by the Press Information Bureau; rank 0, cross-check only; agrees with NCRB for every unit-year), `ncrb_2001` to `ncrb_2024` (NCRB *Accidental Deaths & Suicides in India*, ADSI; rank 2; the panel value in every year) |
| farmer suicides | `farm_ogd0112` (data.gov.in "State/UT-wise professional profile of suicide victim during 2001–2012", rank 1, used for 2001–03 only, and only after the code has checked that it reproduces the NCRB tables of 2004–12), `ncrb_2004` to `ncrb_2023` (rank 2) |
| foodgrain | `foodgrain_dld` (ICRISAT-TCI District Level Database, apportioned to 2011 districts, lower-bound sum of 10 crops; rank 0, cross-check only), `foodgrain_rbi2019` (RBI Handbook of Statistics on Indian States, Table 54, 1997–2016; the only panel source), `foodgrain_rbi2023` (Table 64, 2004–2022; not obtained) |
| population | `census_a02` (Census 2001 and 2011, 1 March), `interpolated_census` (2002–10, between the censuses), `rgi_proj2020` (RGI/National Commission on Population projections, 2012–27) |

NCRB editions and tables used (all published by the NCRB, Ministry of Home Affairs, on https://www.ncrb.gov.in/accidental-deaths-suicides-in-india-adsi.html and https://www.ncrb.gov.in/adsi-all-previous-publications.html; per-year URLs in `outcomes_sources.csv`):

| Data years | ADSI edition(s) | Heat/sun-stroke deaths: table | Farming-sector suicides: table |
|---|---|---|---|
| 2001–2003 | ADSI 2001–2003 (table files) | Table 1.10, natural causes ("Heat Stroke") | Not published by state on the NCRB website; Open Government Data file of NCRB data (`farm_ogd0112`), which reproduces Table 2.11 for 2004–2012 |
| 2004–2008 | ADSI 2004–2008 (table files) | Table 1.10 ("Heat Stroke") | Table 2.11, profession: self-employed (farming/agriculture) |
| 2009–2013 | ADSI 2009–2013 (full reports) | Table 1.10 ("Heat Stroke") | Table 2.11, profession: self-employed (farming/agriculture) |
| 2014 | ADSI 2014 (full report) | Table 1.8 ("Heat/Sun Stroke") | Table 2.7: farmers/cultivators plus agricultural labourers |
| 2015 | ADSI 2015 (full report) | Table 1.8 ("Heat/Sun Stroke") | Table 2A.1, suicides in the farming sector: farmers/cultivators plus agricultural labourers |
| 2016–2019 | ADSI 2016–2019 (full reports; for 2017, the updated full report) | Table 1.8 ("Heat/Sun Stroke") | Table 2.7: farmers/cultivators plus agricultural labourers |
| 2020–2023 | ADSI 2020–2023 (full reports) | Table 1.9 ("Heat/Sun Stroke") | Table 2.7: farmers/cultivators plus agricultural labourers |
| 2024 | ADSI 2024 (full report) | Table 1.9 ("Heat/Sun Stroke") | Not used (the suicide series ends in 2023) |

The 2018–2024 full reports are obtained from the NCRB year pages and are not redistributed (see Reproduction).

### Climate and ENSO tables (`data/derived/`)

`enso_monthly.csv`: one row per ONI season (keyed to the central month): `season`, `year`, `month`, `oni_total`, `oni_anom` (ONI, °C), `phase` (`el_nino`, `la_nina`, `neutral`; NOAA rule: ONI rounded to 0.1 °C ≥ +0.5 or ≤ −0.5 for at least 5 consecutive overlapping seasons), `episode_id`, `provisional`, `ongoing`, `nino34`, `nino34_anom` (ERSSTv5, 1991–2020 base), `dmi` (Dipole Mode Index, HadISST).

`enso_episodes.csv`: one row per El Niño / La Niña episode: `episode_id`, `phase`, `start_season`, `start_year`, `end_season`, `end_year`, `n_seasons`, `peak_anom`, `intensity` (weak < 1.0, moderate 1.0–1.4, strong 1.5–1.9, very_strong ≥ 2.0), `provisional`, `ongoing`.

`enso_annual.csv`: one row per calendar year.

| Column | Definition |
|---|---|
| `oni_jjas` | mean ONI of the four seasons centred on June–September (MJJ, JJA, JAS, ASO); NaN unless all four exist |
| `oni_djf_next` | ONI of the DJF season centred on January of year + 1 |
| `el_nino_developing` / `la_nina_developing` | the JAS season is in an El Niño / La Niña episode |
| `el_nino_decaying` | the DJF season centred on January of this year is in an El Niño episode that started in an earlier year |
| `roni_jjas`, `roni_djf_next` | as `oni_jjas` / `oni_djf_next` for the Relative ONI |
| `nino34_jjas` | June–September mean of the monthly Niño-3.4 anomaly |
| `dmi_jjas`, `dmi_son` | June–September and September–November means of the DMI |

`climate_unit_year.csv`: 34 units x 1981–2025 (1,530 rows), from India Meteorological Department (IMD) gridded data, area-weighted to states and pooled to units. Columns: `rain_annual_mm`, `rain_jjas_mm` (June–September), `rain_jjas_normal_mm` (1981–2010 mean), `rain_jjas_dep_pct` (100 x (JJAS − normal) / normal), `spi3_sep` (3-month SPI ending September), `spi12_dec`, `onset_doy`, `onset_anom_days` (monsoon onset and its anomaly vs 1981–2010), `tmax_mamj_mean`, `tmax_mamj_anom` (March–June mean Tmax and its anomaly vs 1981–2010, °C), `tmax_ge40_days`, `heatwave_days` (Tmax ≥ 45 °C, or ≥ 40 °C and ≥ 4.5 °C above the day-of-year normal; plains rule only), `tmin_mean`, `n_members`, `n_members_used`. SPI: gamma fit per calendar month on 1981–2010 non-zero accumulations, zero-rain probability q (exact zeros at q/2).

### Model inputs (`data/derived/model/`)

`heat_model.csv` (34 x 2001–2024), `farmers_model.csv` (34 x 2001–2023) and `foodgrain_model.csv` (30 x 1997–2016): the panel columns plus the climate columns `rain_jjas_dep_pct`, `spi3_sep`, `tmax_mamj_anom`, `heatwave_days`, `onset_anom_days` and their `_lag1` (previous year, merged on year − 1, never shifted); ENSO exposures `oni_jjas`, `roni_jjas`, `nino34_jjas`, `dmi_jjas` and their `_lag1`, `oni_djf_prev`, `roni_djf_prev`, `dmi_son_prev` (preceding winter or autumn), the phase flags `el_nino_developing`, `el_nino_decaying`, `la_nina_developing`; period indicators (`label2014`: year ≥ 2014, when the NCRB heat-cause label changed; `covid2020`, `covid2020_21`; `nfme2016`, `web_report2019`, `tested_def2022` are malaria-programme indicators carried by the shared builder and not used here); `log_pop`; `log1p_heat_deaths_lag1` (heat), `log1p_farming_sector_lag1` (farmers), `foodgrain_dev_pct` (foodgrain: percentage deviation from the unit's log-linear trend; NaN for units with fewer than 10 valid years). `population_2001_2027.csv`: `unit_id`, `year`, `population`, `log_pop` (2027 denominators for the projections). `folds_decaying.csv` / `folds_developing.csv`: `fold_id`, `year`, `label` (cross-validation folds anchored on El Niño-decaying or developing years; this study uses `folds_decaying.csv`).

### Results

`papers/C/results.json` holds every number reported in the paper as `{"<key>": {"value", "display", "script", "description"}}` (127 keys). `papers/C/supplementary/` holds Supplementary Tables S1–S7 as written by the analysis (missing cells shown as an en dash):

- S1 rows dropped by the missing-data rule and random-effect structure, by model;
- S2 ENSO phase and Indian Ocean Dipole sign combinations by year, 2001–2024;
- S3 out-of-sample validation metrics by fold and by rolling year;
- S4 comparison of ENSO indices (traditional ONI, RONI, Niño-3.4 anomaly);
- S5 sensitivity analyses for recorded heat/sun-stroke deaths;
- S6 sensitivity analyses for farming-sector suicides;
- S7 unit-level projections of expected excess recorded heat/sun-stroke deaths in 2027, by scenario.

`papers/C/figures/data/` holds the data behind each figure (`fig1_data.csv`, `fig2_per_fold.csv`, `fig3_ew2027.csv`, `fig3_ew2027_national.csv`, `figS1_unit_irr.csv`). The list of NCRB editions (Supplementary Table S8 of the paper) is the table under Outcome panels above.

## Missing-data rules

- **General.** Missing is NaN, never 0. In NCRB tables "-" means nil and is read as 0; "NR" is not reported (NaN). A printed 0 is kept as 0 in `outcome_records_all.csv.gz`; whether it reaches a panel as 0 or NaN follows the reviewed rules below. Reviewed exceptions are in `pipeline/reference/outcomes_reviewed.csv` (`outcome, unit_id, year, variable, source_id, check, disposition, reason, evidence`; 313 rows for this study's outcomes and population); `disposition` is `mask` (NaN, source `masked`), `non_reporting` (NaN), `keep` or `use_source:<id>`. The completeness gate fails on any NaN cell that is not listed there.
- **Farmer printed-zero rule (λ ≥ 5; rulings P14 and P16, `pipeline/outcomes/farmer_zeros.py`).** A printed 0 for `farmers`, `ag_labourers` or `farming_sector` is judged non-reporting (panel NaN) when λ, the mean of the 3 most recent non-zero values before it in the unit's series, is ≥ 5 (Poisson P(0 | λ ≥ 5) ≤ 0.7%); otherwise it is a true zero. When λ has to come from the other side of the 2014 break it is scaled by the national ratio between the two categories (0.48 for `farmers`, 1.05 for `farming_sector`); `ag_labourers` has no pre-2014 series and no fallback. A zero member of a pooled unit is dropped from the pool (a `partial_pool` keep row); from 2014, `farming_sector` is NaN whenever a component is non-reporting. The rule generates 245 rows of `outcomes_reviewed.csv` with reason prefix "P14 printed-zero rule:" (242 non-reporting, 3 partial-pool keeps); gate `outcome_farmer_zero_rule` checks them against the records. West Bengal 2012 (printed "NR") and Chhattisgarh 2012 (a reviewed reporting episode) are the other non-reporting cells. The paper's sensitivity analysis (Supplementary Table S6) restores every P14-rule cell to its printed value (`true_zero_data()` in `models/C/farmers.R`).
- **2014 definition break.** Before 2014 `farmers` is NCRB's "Self-employed (Farming/Agriculture)" category (NCRB does not say whether it includes agricultural labourers), and `farming_sector` = `farmers`. From 2014 `farmers` is the farmers/cultivators sub-category, `ag_labourers` is reported separately and `farming_sector` is their sum (the printed farming-sector total). The two series are not comparable: `definition_break_2014` is True from 2014, and the farmer models include a `definition_break_2014` term. The heat cause is labelled "Heat Stroke" to 2013 and "Heat/Sun Stroke" from 2014 (same table family; `label2014` term).
- **Foodgrain masks.** Foodgrain is RBI Table 54 only, 1997–2016, for 30 units (Andaman and Nicobar, Chandigarh, DNH_DD and Lakshadweep have no RBI row and are outside the panel). 1997–99 are masked for Bihar, Madhya Pradesh and Uttar Pradesh (pre-bifurcation boundaries incompatible with later years) and NaN for Chhattisgarh, Jharkhand and Uttarakhand (state not yet formed): 18 cells, disposition `mask`. `year` is the first year of the agricultural year (2010 = 2010–11, whose kharif crop grows in the 2010 June–September monsoon). RBI's state rows sum 1.15% above its printed all-India total for 2011–12 (reviewed national-total exception). The ICRISAT sum is a lower bound (10 crops, 2011 boundaries, 20 states) and a cross-check only.
- **NCRB under-recording.** NCRB counts are deaths recorded by the police as accidental deaths due to heat/sun-stroke; they are a part of all heat-related mortality, and recording practice varies by state and year. Farm-sector suicide counts depend on police recording of the victim's profession. Treat the counts and the projections as recorded deaths, an under-count, not as the absolute burden; analyses are ecological and annual.
- **Plausibility.** A unit-year is flagged when its value is below 0.2 or above 5 times the centred rolling 7-year median of the unit's series (medians below 20 not tested; farmer series split at 2014). A flagged zero with a median ≥ 20 is non-reporting; a flagged non-zero value is kept only when a second source corroborates it or the printed cell matches the parse (21 reviewed keeps for this study).
- **Climate (analysis rule 1).** Rainfall-based variables (`rain_jjas_dep_pct`, `spi3_sep`, `onset_anom_days` and their lags) are set to NaN for Andaman and Nicobar (no valid IMD grid cell) and Lakshadweep (a Kerala-coast proxy) in the models (`blank_rain()` in `models/C/helpers.R`); the blanked cells are listed in Supplementary Table S1. Tamil Nadu and Puducherry 2011–12 rain is masked (IMD grid artefact) and Arunachal Pradesh 1999 is masked; reviewed QC masks are in `pipeline/reference/qc_reviewed.csv`.
- **Population.** The DNH_DD projection for 2012–2027 is implausible (1,448,000 in 2025 against 586,956 in 2011); sensitivity analyses of heat deaths and farmer suicides exclude DNH_DD (Supplementary Tables S5 and S6).
- The R analysis drops rows with a missing model variable and lists every dropped unit-year in Supplementary Table S1.

## Provenance and licences of the sources

Every raw file is listed in `data/raw_files_manifest.csv` (public URL, retrieval time in UTC, SHA-256, bytes; 208 files). The files themselves are not redistributed. For the NCRB 2018–2024 full reports the URL is the NCRB year page from which the PDF is obtained; the SHA-256 is that of the copy analysed. Source-level URLs and notes are in `pipeline/reference/outcomes_sources.csv`.

| Source | Used for | Publisher, URL | Terms and attribution |
|---|---|---|---|
| *Accidental Deaths & Suicides in India* (ADSI), 2001–2024 editions | heat deaths, farmer suicides | National Crime Records Bureau, Ministry of Home Affairs, https://www.ncrb.gov.in/accidental-deaths-suicides-in-india-adsi.html (per-year URLs in `outcomes_sources.csv`) | Public Government of India publications; aggregated state-year counts reproduced with attribution to NCRB; PDFs not redistributed |
| State/UT-wise number of accidental deaths due to heat/sun stroke during 2017–2021 (Lok Sabha annexure) | heat deaths, cross-check only | Ministry of Earth Sciences, released by the Press Information Bureau, 26 July 2023, https://static.pib.gov.in/WriteReadData/specificdocs/documents/2023/jul/doc2023726228401.pdf | Public Government of India document; attribute MoES/PIB |
| State/UT-wise professional profile of suicide victim during 2001–2012 (NCRB data) | farmer suicides 2001–03 | Open Government Data Platform India, https://www.data.gov.in/resource/stateut-wise-professional-profile-suicide-victim-during-2001-2012 (file https://data.gov.in/sites/default/files/datafile/Profession_profile_of_suicide_victims_state.csv) | Government Open Data License – India; attribute NCRB and data.gov.in |
| Handbook of Statistics on Indian States, Table 54 (state-wise production of foodgrains), March 2019 | foodgrain panel | Reserve Bank of India, https://rbi.org.in/Scripts/PublicationsView.aspx?id=18850; file retrieved from the Internet Archive capture https://web.archive.org/web/20250822230316id_/https://rbidocs.rbi.org.in/rdocs/Publications/PDFs/54TABLEA93F71A7ED764906B8575187B1A88681.PDF (the live host serves a human-verification page) | RBI publication (source: Ministry of Agriculture and Farmers Welfare); no explicit licence on the page; aggregated values reproduced with attribution to RBI; PDF not redistributed |
| ICRISAT-TCI District Level Database (apportioned, 2011 districts) | foodgrain, cross-check only | ICRISAT, http://data.icrisat.org/dld/ (API http://data.icrisat.org/dldAPI/apportioned/area-production-yield) | CC BY 4.0, as stated on the DLD About page (http://data.icrisat.org/dld/src/about-dld.html), which asks users to acknowledge ICRISAT through the DOI given on that page; state sums appear only in `outcome_records_all.csv.gz` and `cross_source_report.csv` |
| Census of India 2001/2011 (Table A-02); RGI/NCP population projections 2011–2036 | population | Office of the Registrar General and Census Commissioner, India (https://censusindia.gov.in); National Commission on Population projections (https://nhm.gov.in/New_Updates_2018/Report_Population_Projection_2019.pdf) | Public Government of India data; attribution to RGI and the National Commission on Population |
| Oceanic Niño Index, Relative ONI, Niño-3.4 (ERSSTv5) | ENSO exposure | NOAA Climate Prediction Center, https://www.cpc.ncep.noaa.gov/data/indices/ | US Government (NOAA) public data; attribution to NOAA CPC |
| Dipole Mode Index (HadISST) | IOD exposure | NOAA Physical Sciences Laboratory, https://psl.noaa.gov/gcos_wgsp/Timeseries/Data/dmi.had.long.data | NOAA public data; attribution to NOAA PSL |
| IMD 0.25° daily gridded rainfall; 1° daily gridded Tmax/Tmin | local climate | India Meteorological Department, Pune, https://imdpune.gov.in/cmpg/Griddata/rainfall.php and .../maxtemp.php | IMD gridded-data terms: raw grids are not redistributed here; only area-weighted aggregates are. Cite Pai DS et al. 2014, MAUSAM 65(1):1–18 (rainfall) and Srivastava AK et al. 2009, Atmos Sci Lett 10:249–254 (temperature) |
| IMD sub-divisional rainfall 1901–2017; IMD district list by subdivision | climate validation only | data.gov.in (https://data.gov.in/resource/sub-divisional-monthly-rainfall-1901-2017); IMD (https://mausam.imd.gov.in) | Government Open Data License – India; IMD terms |
| GADM 4.1 India boundaries | area weights, maps | https://gadm.org | Obtained from GADM; not redistributed (GADM licence: free for academic and non-commercial use) |
| NASA POWER (MERRA-2) | climate cross-check only | NASA Langley Research Center, https://power.larc.nasa.gov | Obtained from NASA POWER; not redistributed |

The pipeline also reads a few user-supplied files from `data/external/` (listed with their origins in `pipeline/copy_external.py`): GADM, NASA POWER points, ONI/DMI snapshots used only as a download fallback, and inputs of the companion malaria and dengue study. They are obtained from their publishers and not redistributed.

## Reproduction

### (a) The R analysis from the derived tables

Requirements: R 4.5.3 (checked by `setup.R`), internet access for the first `renv` restore, about 16 GB RAM.

```
cd models
Rscript setup.R          # restores the package library from renv.lock (renv)
Rscript C/run_all.R      # full analysis; clears models/C/_cache first
```

The full run takes about 3–4 hours on an idle machine, most of it the mediation bootstrap (B = 1,000 unit-cluster resamples for each of three mediators); validation uses 200 and the 2027 projections 1,000 joint parameter draws. The bootstrap runs on 6 parallel (PSOCK) workers (`MED_CORES` in `models/C/mediation.R`). On a 16 GB machine keep it at 6 or fewer: with 10 workers while another bootstrap was running, the machine paged heavily. Results do not depend on the number of workers (resample i always uses seed + i − 1; fixed seed `SEED_C` = 20261015). `Rscript C/run_all.R --use-cache` reuses cached fits, comparisons and bootstrap results from `models/C/_cache/`; each step can also be run on its own (`Rscript C/heat.R`, `C/farmers.R`, `C/foodgrain.R`, `C/validate.R`, `C/mediation.R`, `C/project.R`, `C/descriptive.R`).

The analysis reads only `data/derived/model/` (`heat_model.csv`, `farmers_model.csv`, `foodgrain_model.csv`, `folds_decaying.csv`, `population_2001_2027.csv`), `data/derived/enso_annual.csv` and `enso_monthly.csv`, `data/derived/outcomes/outcome_records_all.csv.gz` and `pipeline/reference/outcomes_reviewed.csv` (for the true-zero sensitivity analysis) and `pipeline/reference/state_frame.csv`. It writes `papers/C/results.json`, `papers/C/supplementary/table_S1.csv`–`table_S7.csv` and `papers/C/figures/data/*.csv`; figures are then drawn with `python papers/C/figures/make_figures.py` (the maps also need the GADM file in `data/external/`).

Shared R functions have a testthat suite: `cd models && Rscript common/tests/run.R` (or `python -m pytest -m r` from the repository root).

### (b) Rebuilding the derived tables from the raw sources

A raw → panel rebuild requires downloading the raw files from the official URLs listed in `data/raw_files_manifest.csv` and `pipeline/reference/outcomes_sources.csv`; most downloads are automatic. Compare the SHA-256 of each downloaded file with `data/raw_files_manifest.csv`: documents re-published by the agencies under the same URL may differ.

```
python -m pip install -r requirements.txt   # Python 3.10 or later (tested with 3.14); pdftotext (Poppler) must be on PATH
python run_all.py                           # ENSO download, IMD download and aggregation (1981-2025),
                                            # climate tables, outcome parsing, model inputs, all gates
```

Steps can also be run one at a time: `python -m pipeline.fetch_enso`, `python -m pipeline.outcomes.assemble` (parses the cached raw outcome files and downloads missing ones), `python -m pipeline.outcomes.farmer_zeros` (regenerates the P14/P16 rows of `outcomes_reviewed.csv`, only after the records change), `python -m pipeline.climate_units`, `python -m pipeline.model_inputs`. `python run_all.py --skip-download` rebuilds from files already in `data/raw/`. Notes:

- NCRB ADSI 2018–2024: download each full report from the NCRB year page (`https://www.ncrb.gov.in/accidental-deaths-suicides-in-india-year-wise.html?year=<year>`) and save it as `data/external/ncrb_adsi/ADSI_<year>.pdf`; the parser copies it into `data/raw/outcomes/ncrb_<year>/` and records its SHA-256. The 2001–2017 editions download automatically.
- RBI Table 64 (`foodgrain_rbi2023`, 2004–05 to 2022–23) is served behind an image CAPTCHA, which is not bypassed. If you place `64T_15112023FA45A663E56549F98199708AE35A02F0.PDF` in `data/raw/outcomes/foodgrain_rbi2023/`, a rebuild will use it; until then the foodgrain panel ends in 2016.
- The IMD gridded download is large (45 years of daily grids); the build is resumable.
- Some sources are Internet Archive captures, which may refuse automated requests (HTTP 429).
- The files of `data/external/` (see Provenance) must be supplied by the user (`ELNINO_EXTERNAL_SOURCE_DIR`, see `pipeline/copy_external.py`).
- Without any downloads, the three panels can be checked against their records and reviewed exceptions, and the model inputs rebuilt from the distributed tables:

```
python -c "from pipeline.outcomes import assemble, gates; spec = {k: assemble.GATE_SPEC[k] for k in ('heat_deaths', 'farmer_suicides', 'foodgrain')}; [print(r.passed, r.name, r.detail[:100]) for r in gates.run_outcome_gates(spec=spec)]"
python -m pipeline.model_inputs
```

(`run_outcome_gates` rewrites `cross_source_report.csv`, and `model_inputs` rewrites `data/derived/model/`, with identical content; on Windows pandas writes CRLF line endings, which git normalises.)

Python tests: `python -m pytest` (network tests and the R suite are deselected by default).

### Pipeline scope

The outcome pipeline was written for a wider programme and also contains parsers, reference rows and tests for the malaria and dengue panels of a companion study (https://github.com/hssling/elnino-malaria-india). Those panels and their model inputs are not part of this study and are not distributed here; `pipeline/model_inputs.py` builds their model inputs only when a full rebuild has produced them, and `pipeline/reference/outcomes_sources.csv` keeps their source rows because the parsers' tests check them. Code comments cite internal decision identifiers (for example "Ruling P14"); the decisions that affect the data are described in this README.

## Software

- R 4.5.3; packages pinned in `models/renv.lock` (renv 1.3.1; glmmTMB 1.1.15.2, TMB 1.9.25, data.table 1.18.6.1, jsonlite 2.0.0, mgcv 1.9-4, ggplot2 4.0.3, testthat 3.3.2).
- Python 3.14 (tested; 3.10 or later required) with pandas 2.3, numpy 2.3, scipy 1.16, geopandas 1.1, shapely 2.1, pyogrio 0.12, requests 2.32, matplotlib 3.10, pdfplumber 0.11, Pillow, pytest; pdftotext (Poppler) 4.00.

## Licences

- Code: MIT (`LICENSE`).
- Derived data (`data/derived/`, `data/raw_files_manifest.csv`, `pipeline/reference/`, `papers/C/results.json`, `papers/C/supplementary/`, `papers/C/figures/data/`): CC BY 4.0 (`DATA_LICENSE.md`), subject to the third-party source terms above.

## Contact

Dr Siddalingaiah H S, Department of Community Medicine, Shridevi Institute of Medical Sciences and Research Hospital, Tumakuru, Karnataka, India. E-mail: hssling@yahoo.com. ORCID: https://orcid.org/0000-0002-4771-8285.
