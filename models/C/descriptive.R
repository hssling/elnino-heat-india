# Paper C descriptive results: panel and ENSO classification keys, Table I (C.t1.*),
# Figure 1 data and Supplementary Table S2 (ENSO phase x Dipole sign by year).
# Run from the models/ folder:  Rscript C/descriptive.R   (or via C/run_all.R)

if (!exists("C_DIR")) { source("common/R/load.R"); source("C/helpers.R") }

run_descriptive <- function() {
  S <- "descriptive.R"
  E <- list()
  h <- prep_heat()
  fa <- prep_farmers()
  fg <- prep_foodgrain()
  ea <- data.table::fread(file.path(REPO_ROOT, "data", "derived", "enso_annual.csv"))

  # ENSO classification, 2001-2024
  e24 <- ea[year >= 2001 & year <= 2024]
  dec_years <- e24[el_nino_decaying == TRUE, year]
  E[["C.enso.n_decaying"]] <- entry(length(dec_years), as.character(length(dec_years)), S,
                                    "Years 2001-2024 with el_nino_decaying TRUE (enso_annual.csv)")
  E[["C.enso.decaying_years"]] <- entry(paste(dec_years, collapse = ";"), and_list(dec_years), S,
                                        "El Nino-decaying years 2001-2024")

  # ---- Table I panel A: decaying vs other years, 2001-2024 (heat_model.csv)
  nat <- h[, .(deaths = sum(heat_deaths, na.rm = TRUE),
               pop = sum(population[!is.na(heat_deaths)]),
               oni = oni_djf_prev[1], dec = el_nino_decaying[1]), by = year]
  nat[, rate := deaths / pop * 1e7]
  grp <- list(dec = TRUE, odec = FALSE)
  for (g in names(grp)) {
    yrs <- nat[dec == grp[[g]], year]
    hu <- h[year %in% yrs]
    E[[sprintf("C.t1.%s.n_years", g)]] <- entry(length(yrs), as.character(length(yrs)), S,
      sprintf("Years 2001-2024 in group %s (el_nino_decaying %s)", g, grp[[g]]))
    E[[sprintf("C.t1.%s.oni", g)]] <- entry(mean(nat[dec == grp[[g]], oni]), fmt_mean_range(nat[dec == grp[[g]], oni]), S,
      sprintf("Preceding-winter traditional ONI (oni_djf_prev) by year, mean (range), group %s", g))
    E[[sprintf("C.t1.%s.deaths", g)]] <- entry(stats::median(nat[dec == grp[[g]], deaths]),
      fmt_median_range(nat[dec == grp[[g]], deaths]), S,
      sprintf("National recorded heat deaths per year (sum over units), median (range), group %s", g))
    E[[sprintf("C.t1.%s.rate", g)]] <- entry(stats::median(nat[dec == grp[[g]], rate]),
      fmt_median_range(nat[dec == grp[[g]], rate], 1), S,
      sprintf("National heat deaths per 10 million population per year, median (range), group %s", g))
    E[[sprintf("C.t1.%s.hw", g)]] <- entry(mean(hu$heatwave_days, na.rm = TRUE), fmt_mean_sd(hu$heatwave_days, 1), S,
      sprintf("Unit heatwave_days, mean (SD) over unit-years, group %s", g))
    E[[sprintf("C.t1.%s.tmax", g)]] <- entry(mean(hu$tmax_mamj_anom, na.rm = TRUE),
      fmt_mean_sd(hu$tmax_mamj_anom, 2, signed = TRUE), S,
      sprintf("Unit tmax_mamj_anom (deg C), mean (SD) over unit-years, group %s", g))
    E[[sprintf("C.t1.%s.onset", g)]] <- entry(mean(hu$onset_anom_days, na.rm = TRUE),
      fmt_mean_sd(hu$onset_anom_days, 1, signed = TRUE), S,
      sprintf("Unit onset_anom_days (AN, LD excluded), mean (SD) over unit-years, group %s", g))
  }

  # ---- Table I panel B: developing vs other years
  fa23 <- fa[year >= 2001 & year <= 2023]
  devy <- unique(fa23[, .(year, dev = el_nino_developing)])
  farm_nat <- fa23[, .(fs = if (all(is.na(farming_sector))) NA_real_ else sum(farming_sector, na.rm = TRUE),
                       dev = el_nino_developing[1]), by = year]
  grp <- list(dev = TRUE, odev = FALSE)
  for (g in names(grp)) {
    yrs <- devy[dev == grp[[g]], year]
    fu <- fa23[year %in% yrs]
    E[[sprintf("C.t1.%s.n_years", g)]] <- entry(length(yrs), as.character(length(yrs)), S,
      sprintf("Years 2001-2023 in group %s (el_nino_developing %s)", g, grp[[g]]))
    E[[sprintf("C.t1.%s.jjas", g)]] <- entry(mean(fu$rain_jjas_dep_pct, na.rm = TRUE),
      fmt_mean_sd(fu$rain_jjas_dep_pct, 1, signed = TRUE), S,
      sprintf("Unit rain_jjas_dep_pct 2001-2023 (farmers_model.csv; AN, LD excluded), mean (SD), group %s", g))
    E[[sprintf("C.t1.%s.spi", g)]] <- entry(mean(fu$spi3_sep, na.rm = TRUE),
      fmt_mean_sd(fu$spi3_sep, 2, signed = TRUE), S,
      sprintf("Unit spi3_sep 2001-2023 (AN, LD excluded), mean (SD), group %s", g))
    pre <- farm_nat[dev == grp[[g]] & year <= 2013, fs]
    post <- farm_nat[dev == grp[[g]] & year >= 2014, fs]
    E[[sprintf("C.t1.%s.farm_pre", g)]] <- entry(if (length(pre)) stats::median(pre, na.rm = TRUE) else NA,
      fmt_median_range(pre), S,
      sprintf("National farming_sector suicides per year 2001-2013 (sum over units with data), median (range), group %s", g))
    E[[sprintf("C.t1.%s.farm_post", g)]] <- entry(if (length(post)) stats::median(post, na.rm = TRUE) else NA,
      fmt_median_range(post), S,
      sprintf("National farming_sector suicides per year 2014-2023 (sum over units with data), median (range), group %s", g))
    fd <- fg[el_nino_developing == grp[[g]], foodgrain_dev_pct]
    E[[sprintf("C.t1.%s.food", g)]] <- entry(mean(fd, na.rm = TRUE), fmt_mean_sd(fd, 1, signed = TRUE), S,
      sprintf("Unit foodgrain_dev_pct 1997-2016, mean (SD), group %s", g))
  }

  # ---- Figure 1 data
  fig1 <- nat[order(year), .(year, deaths, population = pop, rate_per_10m = rate, oni_djf_prev = oni,
                             el_nino_decaying = dec)]
  write_csv(fig1, file.path(C_FIG_DATA, "fig1_data.csv"))

  # ---- Supplementary Table S2: ENSO phase (preceding-winter ONI) x Dipole sign, 2001-2024
  yr <- unique(h[, .(year, oni_djf_prev, dmi_son_prev)])[order(year)]
  yr[, enso_phase := data.table::fifelse(round(oni_djf_prev, 1) >= 0.5, "El Nino",
                      data.table::fifelse(round(oni_djf_prev, 1) <= -0.5, "La Nina", "Neutral"))]
  yr[, dipole_sign := data.table::fifelse(dmi_son_prev > 0, "positive", "negative or zero")]
  s2 <- yr[, .(n_years = .N, years = paste(year, collapse = ", ")), by = .(enso_phase, dipole_sign)]
  s2[, enso_phase := factor(enso_phase, levels = c("El Nino", "Neutral", "La Nina"))]
  data.table::setorder(s2, enso_phase, dipole_sign)
  s2[, enso_phase := sub("Nino", "Ni\u00f1o", sub("Nina", "Ni\u00f1a", as.character(enso_phase)))]
  data.table::setnames(s2, c("ENSO phase (preceding-winter ONI)", "Sign of preceding Sep-Nov DMI", "Years, n", "Years"))
  write_csv(s2, file.path(C_SUPP, "table_S2.csv"))

  save_entries(E, "descriptive")
}

if (sys.nframe() == 0L) run_descriptive()
