# Paper C early warning 2027 (Results para 6, Figure 3 (was Figure 4; ruling P20), Supplementary Table S7):
# primary heat model (all years 2001-2024) projected to 2027 under preceding-winter ONI
# scenarios +1.5, +2.0 and +2.5 deg C against a counterfactual ONI of 0, with 1,000 joint
# parameter draws (project()). 2027 population from population_2001_2027.csv (Ruling P12).
# Run from the models/ folder:  Rscript C/project.R   (or via C/run_all.R)

if (!exists("C_DIR")) { source("common/R/load.R"); source("C/helpers.R") }
if (!exists("fit_primary")) source("C/heat.R")

SCENARIOS <- c(s15 = 1.5, s20 = 2.0, s25 = 2.5)
N_DRAWS_PROJ <- 1000L
# CPC publishes DJF 2026-27 about early March 2027; NA until then (rerun with the observed value).
OBSERVED_DJF_2027 <- NA_real_

newdata_2027 <- function(fit, oni_pos) {
  pop <- data.table::fread(file.path(REPO_ROOT, "data", "derived", "model", "population_2001_2027.csv"))
  units <- levels(fit$data$unit_id)
  p27 <- pop[year == 2027L]
  nd <- data.table::data.table(unit_id = factor(units, levels = units), year = 2027L,
                               oni_djf_prev_pos = oni_pos, oni_djf_prev_neg = 0, label2014 = 1L, covid2020 = 0L)
  nd[p27, on = "unit_id", log_pop := i.log_pop]
  nd[]
}

fmt_excess <- function(m, lo, hi) fmt_ci(m, lo, hi, digits = 0, label = "nominal 95% interval", big.mark = ",")

run_project <- function() {
  S <- "project.R"
  E <- list()
  h <- prep_heat()
  fit <- fit_primary(h)
  un <- unit_names()
  out <- list(); tot <- list(); ext <- list(); trend <- NULL
  scen <- SCENARIOS
  if (is.finite(OBSERVED_DJF_2027)) scen <- c(scen, obs = OBSERVED_DJF_2027)
  for (s in names(scen)) {
    log_msg("project: scenario", s, scen[[s]])
    nd <- newdata_2027(fit, max(scen[[s]], 0))
    cf <- newdata_2027(fit, 0)
    pr <- project(fit, nd, cf, exposure_vars = c("oni_djf_prev_pos", "oni_djf_prev_neg"),
                  n_draws = N_DRAWS_PROJ, seed = SEED_C)
    if (nrow(pr$dropped)) stop("project: rows dropped for scenario ", s)
    out[[s]] <- cbind(scenario = s, oni = scen[[s]], pr$by_row,
                      extrapolation = pr$extrapolation)
    tot[[s]] <- cbind(scenario = s, oni = scen[[s]], pr$total)
    ext[[s]] <- pr$extrapolation
    trend <- pr$trend_detail
  }
  by_row <- data.table::rbindlist(out)
  total <- data.table::rbindlist(tot)
  by_row[, unit_name := un[unit_id]]

  for (s in names(SCENARIOS)) {
    t <- total[scenario == s]
    E[[sprintf("C.ew.%s.total", s)]] <- entry(t$excess_mean, fmt_excess(t$excess_mean, t$excess_lo, t$excess_hi), S,
      sprintf("National expected excess recorded heat deaths 2027 at ONI +%.1f deg C vs 0 (sum of unit excess per draw; mean, 2.5/97.5 percentiles of %d joint draws)",
              SCENARIOS[[s]], N_DRAWS_PROJ))
  }
  for (s in c("s15", "s25")) {
    t <- total[scenario == s]
    E[[sprintf("C.ew.%s.total_short", s)]] <- entry(t$excess_mean, fmt_int(t$excess_mean), S,
      sprintf("National expected excess recorded heat deaths 2027 at ONI +%.1f deg C, mean only", SCENARIOS[[s]]))
  }
  top <- by_row[scenario == "s20"][order(-excess_mean)][1:5]
  E[["C.ew.top_units"]] <- entry(paste(top$unit_id, collapse = ";"), and_list(top$unit_name), S,
    "Five units with the largest mean expected excess at ONI +2.0 deg C, descending")
  tmax <- max(fit$data$oni_djf_prev_pos)
  outside <- names(SCENARIOS)[unlist(ext[names(SCENARIOS)])]
  note <- if (!length(outside))
    sprintf("No scenario lies outside the range of the preceding-winter ONI in the training data (maximum %s \u00b0C).",
            fmt_signed(tmax, 2))
  else {
    lab <- paste0(fmt_signed(SCENARIOS[outside], 1), " \u00b0C")
    sprintf("The %s scenario%s outside the range of the preceding-winter ONI in the training data (maximum %s \u00b0C), so %s an extrapolation.",
            and_list(lab), if (length(outside) > 1) "s lie" else " lies", fmt_signed(tmax, 2),
            if (length(outside) > 1) "their projections are" else "its projection is")
  }
  E[["C.ew.extrapolation_note"]] <- entry(paste(outside, collapse = ";"), note, S,
    sprintf("project()$extrapolation over the three scenarios (training max oni_djf_prev %.2f); trend extrapolation %s (training years %d-%d, projected 2027)",
            tmax, TRUE, trend$train_min, trend$train_max))
  if (is.finite(OBSERVED_DJF_2027)) {
    t <- total[scenario == "obs"]
    E[["C.ew.obs.status"]] <- entry(OBSERVED_DJF_2027,
      sprintf("was published as %s \u00b0C, giving expected excess recorded deaths of %s", fmt_signed(OBSERVED_DJF_2027, 2),
              fmt_excess(t$excess_mean, t$excess_lo, t$excess_hi)), S, "Observed DJF 2026-27 traditional ONI and projection")
  } else {
    E[["C.ew.obs.status"]] <- entry(NA, "had not been published at submission, so the values above are scenarios and are provisional", S,
      "Observed DJF 2026-27 traditional ONI not yet published by CPC (expected early March 2027)")
  }

  # Figure 3 data and Supplementary Table S7
  ord <- by_row[scenario == "s20"][order(-excess_mean), unit_id]
  by_row[, rank_s20 := match(unit_id, ord)]
  write_csv(by_row[order(scenario, rank_s20), .(scenario, oni, unit_id, unit_name, rank_s20, mu, mu_cf, excess_mean,
                                                excess_lo, excess_hi, y_lo, y_hi, extrapolation)],
            file.path(C_FIG_DATA, "fig3_ew2027.csv"))
  write_csv(total, file.path(C_FIG_DATA, "fig3_ew2027_national.csv"))
  s7 <- by_row[order(rank_s20, scenario), .(Unit = unit_name, `ONI scenario (deg C)` = fmt_signed(oni, 1),
                  `Expected excess, mean (nominal 95% interval)` = fmt_ci(excess_mean, excess_lo, excess_hi, digits = 1,
                                                                  label = "nominal 95% interval", big.mark = ","),
                  `Expected recorded deaths, mean` = fmt_num(mu, 1),
                  `Prediction interval of recorded deaths (nominal 95%)` = paste0(fmt_int(y_lo), EN_DASH, fmt_int(y_hi)),
                  `ONI outside training range` = data.table::fifelse(extrapolation, "yes", "no"))]
  s7 <- rbind(s7, total[, .(Unit = "India (sum of units)", `ONI scenario (deg C)` = fmt_signed(oni, 1),
                            `Expected excess, mean (nominal 95% interval)` = fmt_excess(excess_mean, excess_lo, excess_hi),
                            `Expected recorded deaths, mean` = EN_DASH,
                            `Prediction interval of recorded deaths (nominal 95%)` = EN_DASH,
                            `ONI outside training range` = data.table::fifelse(unlist(ext[scenario]), "yes", "no"))])
  data.table::setnames(s7, "ONI scenario (deg C)", "ONI scenario (\u00b0C)")
  write_csv(s7, file.path(C_SUPP, "table_S7.csv"))
  saveRDS(list(total = total, trend = trend, ext = ext), file.path(C_CACHE, "project_meta.rds"))
  save_entries(E, "project")
}

if (sys.nframe() == 0L) run_project()
