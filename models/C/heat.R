# Paper C heat associations: primary NB-GLMM (El Nino / La Nina terms), decaying-year (H3),
# Dipole interaction, heatwave-day and Tmax exposure-response models, random-slope summaries,
# Supplementary Figure S1 data (ruling P20; was Figure 2), sensitivity analyses (Supplementary Table S5) and Table S1 rows.
# Run from the models/ folder:  Rscript C/heat.R   (or via C/run_all.R)

if (!exists("C_DIR")) { source("common/R/load.R"); source("C/helpers.R") }

HEAT_COV <- c("label2014", "covid2020")
primary_spec <- function(idx = "oni_djf_prev", re = "us")
  nb_spec("heat_deaths", fixed = c(paste0(idx, "_pos"), paste0(idx, "_neg"), HEAT_COV),
          slopes = paste0(idx, "_pos"), re = re)

fit_primary <- function(h) {
  f <- file.path(C_CACHE, "fit_primary.rds")
  if (file.exists(f)) return(readRDS(f))
  fit <- fit_nb(primary_spec(), h)
  saveRDS(fit, f)
  fit
}

irr_entries <- function(E, S, fit, term, key_est, key_p, desc, invert = FALSE, k = 1) {
  r <- irr_table(fit, term)
  if (invert) r <- invert_irr(r, k)
  E[[key_est]] <- entry(r$irr, fmt_ci(r$irr, r$lo, r$hi), S, paste0(desc, "; Wald 95% CI; lo=", signif(r$lo, 6),
                                                                     " hi=", signif(r$hi, 6)))
  if (!is.null(key_p)) E[[key_p]] <- entry(r$p, fmt_p(r$p), S, paste0("P value: ", desc))
  E
}

run_heat <- function() {
  S <- "heat.R"
  E <- list()
  h <- prep_heat()
  s1 <- list()
  add_s1 <- function(label, fit) s1[[length(s1) + 1L]] <<- s1_rows(label, fit$n, fit$re_used, fit$attempts, fit$dropped)

  log_msg("heat: primary fit")
  fit <- fit_primary(h)
  add_s1("Heat: primary (El Nino and La Nina terms)", fit)
  E[["C.heat.n_unit_years"]] <- entry(fit$n, fmt_int(fit$n), S, "Unit-years in the primary heat fit")
  E[["C.heat.n_units"]] <- entry(nlevels(fit$data$unit_id), as.character(nlevels(fit$data$unit_id)), S,
                                 "Units in the primary heat fit")
  tot <- sum(fit$data$heat_deaths)
  E[["C.heat.total_deaths"]] <- entry(tot, fmt_int(tot), S, "Sum of heat_deaths over the primary-fit rows")
  ny <- length(unique(fit$data$year))
  E[["C.enso.n_years_heat"]] <- entry(ny, as.character(ny), S, "Calendar years in the primary heat fit")
  re_txt <- c(us = "correlated random intercept and slope", diag = "uncorrelated random intercept and slope",
              int = "random-intercept-only")[[fit$re_used]]
  E[["C.heat.re_used"]] <- entry(fit$re_used, re_txt, S, "Random-effect structure used by the primary heat fit")

  E <- irr_entries(E, S, fit, "oni_djf_prev_pos", "C.heat.irr_elnino", "C.heat.p_elnino",
                   "IRR per +1 deg C of the El Nino term max(oni_djf_prev, 0), primary model")
  E <- irr_entries(E, S, fit, "oni_djf_prev_neg", "C.heat.irr_lanina", "C.heat.p_lanina",
                   "IRR per 1 deg C cooler La Nina term min(oni_djf_prev, 0): exp(-beta), bounds swapped", invert = TRUE)

  # random slope SD, LRT vs random intercept, unit-specific IRRs
  vc <- glmmTMB::VarCorr(fit$model)$cond$unit_id
  sds <- attr(vc, "stddev")
  slope_sd <- if ("oni_djf_prev_pos" %in% names(sds)) unname(sds["oni_djf_prev_pos"]) else NA_real_
  E[["C.heat.slope_sd"]] <- entry(slope_sd, if (is.na(slope_sd)) "not estimated (random-intercept-only fit)"
                                  else fmt_num(slope_sd, 2), S,
                                  "SD of the unit random slope on the El Nino term (log-rate scale), primary model")
  fit_int <- fit_nb(primary_spec(re = "int"), fit$data)
  add_s1("Heat: primary, random intercept only (LRT reference and sensitivity)", fit_int)
  if (fit$re_used == "int") {
    E[["C.heat.p_slope_lrt"]] <- entry(NA, "not applicable (random-intercept-only fit)", S,
                                       "LRT primary vs random intercept only: primary already intercept-only")
  } else {
    ll1 <- as.numeric(stats::logLik(fit$model)); ll0 <- as.numeric(stats::logLik(fit_int$model))
    df <- attr(stats::logLik(fit$model), "df") - attr(stats::logLik(fit_int$model), "df")
    stat <- max(0, 2 * (ll1 - ll0))
    p <- stats::pchisq(stat, df = df, lower.tail = FALSE)
    E[["C.heat.p_slope_lrt"]] <- entry(p, fmt_p(p), S,
      sprintf("Likelihood-ratio test, primary (%s) vs random intercept only, same rows: chi2 = %.3f, df = %d (boundary test, conservative)",
              fit$re_used, stat, as.integer(df)))
  }
  b_pos <- glmmTMB::fixef(fit$model)$cond[["oni_djf_prev_pos"]]
  re <- glmmTMB::ranef(fit$model)$cond$unit_id
  unit_slope <- if ("oni_djf_prev_pos" %in% names(re)) re[["oni_djf_prev_pos"]] else rep(0, nrow(re))
  un <- unit_names()
  fig2 <- data.table::data.table(unit_id = rownames(re), unit_name = un[rownames(re)],
                                 random_slope = unit_slope, log_irr = b_pos + unit_slope,
                                 irr = exp(b_pos + unit_slope))
  write_csv(fig2, file.path(C_FIG_DATA, "figS1_unit_irr.csv"))
  n_gt1 <- sum(fig2$irr > 1)
  # Ruling P20: when the unit-specific IRRs collapse to one value at the displayed precision (slope
  # variance at the boundary), the display gives that common value instead of "34 of 34".
  collapsed <- fmt_num(min(fig2$irr), 2) == fmt_num(max(fig2$irr), 2)
  E[["C.heat.n_units_irr_gt1"]] <- entry(n_gt1,
    if (collapsed) sprintf("IRR %s in all %d units", fmt_num(fig2$irr[1], 2), nrow(fig2))
    else sprintf("%d of %d", n_gt1, nrow(fig2)), S,
    sprintf("Units whose conditional IRR (fixed + conditional-mode random slope) for the El Nino term exceeds 1 (%d of %d); unit IRR range %.4f-%.4f%s",
            n_gt1, nrow(fig2), min(fig2$irr), max(fig2$irr), if (collapsed) " (collapsed to one value at 2 decimals; P20 display)" else ""))

  # decaying-year model (H3 test)
  log_msg("heat: decaying-year model")
  fd <- fit_nb(nb_spec("heat_deaths", c("el_nino_decaying_i", HEAT_COV), slopes = "el_nino_decaying_i"), h)
  add_s1("Heat: El Nino-decaying indicator", fd)
  saveRDS(irr_table(fd, "el_nino_decaying_i"), file.path(C_CACHE, "heat_decaying_irr.rds"))
  E <- irr_entries(E, S, fd, "el_nino_decaying_i", "C.heat.irr_decaying", "C.heat.p_decaying",
                   sprintf("IRR El Nino-decaying vs other years (re %s)", fd$re_used))

  # Dipole model
  log_msg("heat: Dipole model")
  sp <- primary_spec()
  sp$fixed <- c(sp$fixed, "dmi_son_prev", "oni_x_dmi")
  fdm <- fit_nb(sp, h)
  add_s1("Heat: primary + Dipole Mode Index + ONI x DMI", fdm)
  E <- irr_entries(E, S, fdm, "dmi_son_prev", "C.heat.irr_dmi", "C.heat.p_dmi",
                   sprintf("IRR per +1 deg C dmi_son_prev, primary + DMI + oni_djf_prev:dmi_son_prev (re %s)", fdm$re_used))
  E <- irr_entries(E, S, fdm, "oni_x_dmi", "C.heat.irr_oni_x_dmi", "C.heat.p_oni_x_dmi",
                   "IRR of the interaction oni_djf_prev x dmi_son_prev (per deg C^2; linear ONI)")

  # direct exposure-response
  log_msg("heat: heatwave-day and Tmax models")
  fhw <- fit_nb(nb_spec("heat_deaths", c("heatwave_days", HEAT_COV), slopes = "heatwave_days"), h)
  add_s1("Heat: heatwave days", fhw)
  E <- irr_entries(E, S, fhw, "heatwave_days", "C.heat.rr_hwday", "C.heat.p_hwday",
                   sprintf("IRR per additional heatwave day (re %s)", fhw$re_used))
  ftx <- fit_nb(nb_spec("heat_deaths", c("tmax_mamj_anom", HEAT_COV), slopes = "tmax_mamj_anom"), h)
  add_s1("Heat: March-June Tmax anomaly", ftx)
  E <- irr_entries(E, S, ftx, "tmax_mamj_anom", "C.heat.rr_tmax", "C.heat.p_tmax",
                   sprintf("IRR per +1 deg C tmax_mamj_anom (re %s)", ftx$re_used))

  # ---- sensitivity analyses (Supplementary Table S5)
  log_msg("heat: sensitivity analyses")
  sens_def <- list(
    list(label = "Symmetric single ONI term (spec section 4 form)", term = "oni_djf_prev", symmetric = TRUE,
         spec = nb_spec("heat_deaths", c("oni_djf_prev", HEAT_COV), slopes = "oni_djf_prev"), data = h),
    list(label = "RONI in place of the traditional ONI", term = "roni_djf_prev_pos",
         spec = primary_spec("roni_djf_prev"), data = h),
    list(label = "Random intercepts only", term = "oni_djf_prev_pos", fit = fit_int),
    list(label = "Excluding 2020-2021", term = "oni_djf_prev_pos", spec = primary_spec(),
         data = h[!year %in% c(2020L, 2021L)]),
    list(label = "Excluding Dadra and Nagar Haveli and Daman and Diu", term = "oni_djf_prev_pos",
         spec = primary_spec(), data = h[unit_id != "DNH_DD"]))
  prim <- irr_table(fit, "oni_djf_prev_pos")
  s5 <- list(data.table::data.table(analysis = "Primary (reference)", re_used = fit$re_used, n = fit$n,
                                    prim[, .(irr, lo, hi, p)], status = "ok"))
  # Ruling P23: the symmetric single-ONI term is a different estimand (per 1 deg C over the whole ONI
  # range), so it is reported separately and not in the El Nino-term range.
  sens_irr <- c(); sym <- NULL
  for (sd_ in sens_def) {
    ft <- if (!is.null(sd_$fit)) sd_$fit else tryCatch(fit_nb(sd_$spec, droplevels(sd_$data)), error = function(e) e)
    if (inherits(ft, "error")) {
      s5[[length(s5) + 1L]] <- data.table::data.table(analysis = sd_$label, re_used = NA_character_, n = NA_integer_,
                                                      irr = NA_real_, lo = NA_real_, hi = NA_real_, p = NA_real_,
                                                      status = paste("failed:", conditionMessage(ft)))
      next
    }
    if (is.null(sd_$fit)) add_s1(paste("Heat sensitivity:", sd_$label), ft)
    r <- irr_table(ft, sd_$term)
    if (isTRUE(sd_$symmetric)) sym <- r else sens_irr <- c(sens_irr, stats::setNames(r$irr, sd_$label))
    same <- !isTRUE(sd_$symmetric) && ft$n == fit$n &&
            max(abs(c(r$irr, r$lo, r$hi) - c(prim$irr, prim$lo, prim$hi))) < 1e-6
    st <- if (same) "ok; identical to the primary model (unit slope SD estimated at 0)" else
          if (isTRUE(sd_$symmetric)) "ok; different estimand (per 1 \u00b0C over the whole ONI range)" else "ok"
    s5[[length(s5) + 1L]] <- data.table::data.table(analysis = sd_$label, re_used = ft$re_used, n = ft$n,
                                                    r[, .(irr, lo, hi, p)], status = st)
  }
  s5 <- data.table::rbindlist(s5)
  n_failed <- sum(!startsWith(s5$status, "ok"))
  rng <- range(sens_irr)
  E[["C.sens.elnino_range"]] <- entry(rng, paste0(fmt_num(rng[1], 2), " to ", fmt_num(rng[2], 2)), S,
    sprintf("Min and max point IRR of the El Nino term across %d sensitivity fits (RONI, random intercept only, excluding 2020-2021, excluding DNH_DD; ruling P23 moved the symmetric single-ONI fit to C.sens.symmetric_irr); min from '%s', max from '%s'; %d failed",
            length(sens_irr), names(sens_irr)[which.min(sens_irr)], names(sens_irr)[which.max(sens_irr)], n_failed))
  E[["C.sens.symmetric_irr"]] <- entry(if (is.null(sym)) NA else sym$irr,
    if (is.null(sym)) "not estimated (fit failed)" else fmt_ci(sym$irr, sym$lo, sym$hi), S,
    "IRR per +1 deg C of a single symmetric oni_djf_prev term (spec section 4 form; a different estimand from the El Nino term), Wald CI")
  s5_out <- s5[, .(Analysis = analysis, `Random effects` = re_used, `Unit-years` = n,
                   irr_ci = fmt_ci(irr, lo, hi), P = fmt_p(p), Status = status)]
  data.table::setnames(s5_out, "irr_ci", "IRR per 1 \u00b0C (95% CI)")
  write_csv(s5_out, file.path(C_SUPP, "table_S5.csv"))
  write_csv(s5, file.path(C_CACHE, "heat_sensitivity_raw.csv"))

  saveRDS(data.table::rbindlist(s1), file.path(C_CACHE, "s1_heat.rds"))
  save_entries(E, "heat")
}

if (sys.nframe() == 0L) run_heat()
