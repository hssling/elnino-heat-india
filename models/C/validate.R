# Paper C out-of-sample validation (A1 item 3): nested Models A/B/C under leave-one-El-Nino-out
# (decaying folds) and rolling-origin validation (Table IV, Figure 2 (was Figure 3; ruling P20), Supplementary Table S3),
# and the ENSO-index comparison ONI / RONI / Nino-3.4 (A1 item 1; Supplementary Table S4).
# Run from the models/ folder:  Rscript C/validate.R   (or via C/run_all.R)

if (!exists("C_DIR")) { source("common/R/load.R"); source("C/helpers.R") }
if (!exists("primary_spec")) source("C/heat.R")

N_DRAWS_VAL <- 200L
MODEL_LABEL <- c(A = "A: trend and reporting", B = "B: A + local climate", C = "C: B + El Nino and Dipole")

nested_specs <- function() {
  a <- nb_spec("heat_deaths", fixed = c("label2014", "covid2020", "log1p_heat_deaths_lag1"), re = "int")
  b <- a; b$fixed <- c(a$fixed, "heatwave_days", "tmax_mamj_anom")
  cc <- b; cc$fixed <- c(b$fixed, "oni_djf_prev_pos", "oni_djf_prev_neg", "dmi_son_prev")
  list(A = a, B = b, C = cc)
}

cached_compare <- function(name, specs, d, splits) {
  f <- file.path(C_CACHE, paste0("cmp_", name, ".rds"))
  if (file.exists(f)) return(readRDS(f))
  log_msg("validate:", name, "-", length(splits), "splits x", length(specs), "models")
  r <- compare_models(specs, d, splits, n_draws = N_DRAWS_VAL, seed = SEED_C)
  saveRDS(r, f)
  r
}

fold_labels <- function() {
  fo <- read_folds("decaying")
  lab <- unique(fo[, .(split_id = as.character(fold_id), label)])
  stats::setNames(lab$label, lab$split_id)
}

# Years each LOEO fold withholds within the data years (ruling P23, M1): e.g. "2003-04", "2015-17", "2024".
fold_withheld <- function(data_years) {
  fo <- read_folds("decaying")[year %in% data_years]
  w <- fo[, .(y0 = min(year), y1 = max(year)), by = .(split_id = as.character(fold_id))]
  w[, txt := data.table::fifelse(y0 == y1, as.character(y0), paste0(y0, EN_DASH, substr(as.character(y1), 3, 4)))]
  stats::setNames(w$txt, w$split_id)
}

run_validate <- function() {
  S <- "validate.R"
  E <- list()
  h <- prep_heat()
  loeo <- loeo_splits(read_folds("decaying"))
  roll <- rolling_splits(2001:2024, first_test = 2015)
  specs <- nested_specs()
  NE <- "not estimated (>10% of refits failed)"

  cl <- cached_compare("nested_loeo", specs, h, loeo)
  cr <- cached_compare("nested_rolling", specs, h, roll)

  for (v in c("loeo", "rolling")) {
    cm <- if (v == "loeo") cl else cr
    for (m in names(specs)) {
      s <- cm$summary[model == m]
      flagged <- !is.na(s$flag)
      E[[sprintf("C.val.%s.%s.male", v, m)]] <- entry(s$male, if (flagged) NE else fmt_num3(s$male), S,
        sprintf("%s mean absolute log error, Model %s (common rows; flag %s)", toupper(v), m, s$flag))
      E[[sprintf("C.val.%s.%s.log_score", v, m)]] <- entry(s$log_score, if (flagged) NE else fmt_num3(s$log_score), S,
        sprintf("%s mean NB negative log score, Model %s", toupper(v), m))
      E[[sprintf("C.val.%s.%s.coverage", v, m)]] <- entry(s$coverage95, if (flagged) NE else fmt_cov(s$coverage95), S,
        sprintf("%s coverage of the nominal 95%% prediction interval (200 joint draws + NB noise), Model %s", toupper(v), m))
    }
    sb <- cm$summary[model == "B"]; sc <- cm$summary[model == "C"]
    gain <- 100 * (1 - sc$male / sb$male)
    E[[sprintf("C.val.%s.skill_gain_pct", v)]] <- entry(gain,
      if (!is.na(sb$flag) || !is.na(sc$flag)) NE else fmt_signed_pct(gain), S,
      sprintf("%s skill gain of Model C over B: 100 x (1 - MALE_C / MALE_B) (positive = C better)", toupper(v)))
  }
  scored_folds <- unique(cl$per_split[scored == TRUE, split_id])
  E[["C.val.loeo.n_folds"]] <- entry(length(scored_folds), as.character(length(scored_folds)), S,
    sprintf("Evaluated LOEO folds (non-skipped, non-failed); skipped: %s",
            paste(unique(unlist(cl$skipped)), collapse = ",")))
  E[["C.val.loeo.n_rows"]] <- entry(cl$common_n, fmt_int(cl$common_n), S, "Scored unit-years per model, LOEO (common_n)")
  E[["C.val.rolling.n_rows"]] <- entry(cr$common_n, fmt_int(cr$common_n), S, "Scored unit-years per model, rolling origin")
  sm <- data.table::dcast(cl$split_metrics, split_id ~ model, value.var = "male")
  n_better <- sum(sm$C < sm$B)
  E[["C.val.loeo.n_folds_C_better"]] <- entry(n_better, sprintf("%d of %d", n_better, nrow(sm)), S,
    "LOEO folds where per-fold MALE of Model C < Model B")

  # Figure 2 data and Supplementary Table S3
  labs <- fold_labels()
  wh <- fold_withheld(unique(h$year))
  f3 <- rbind(cl$split_metrics[, .(validation = "LOEO", model, split_id, label = labs[split_id], withheld = wh[split_id],
                                    male, rmse_log1p, log_score, coverage95, n)],
              cr$split_metrics[, .(validation = "rolling", model, split_id, label = split_id, withheld = split_id,
                                    male, rmse_log1p, log_score, coverage95, n)])
  write_csv(f3, file.path(C_FIG_DATA, "fig2_per_fold.csv"))
  s3_rows <- function(cm, v, labfun) {
    met <- rbind(cm$split_metrics[, .(model, split = labfun(split_id), male, rmse_log1p, log_score, coverage95, n)],
                 cm$summary[, .(model, split = "All (pooled)", male, rmse_log1p, log_score, coverage95, n)])
    info <- cm$split_info[, .(model, split = labfun(split_id), re_used, n_train,
                              unidentified = data.table::fifelse(nzchar(unidentified),
                                 paste0(unidentified, " (", n_test_rows_nonzero_unidentified, " test rows non-zero)"), EN_DASH))]
    out <- merge(met, info, by = c("model", "split"), all.x = TRUE)
    out[, validation := v]
    out
  }
  s3 <- rbind(s3_rows(cl, "Leave-one-El-Nino-out",
                      function(x) ifelse(x %in% names(wh), paste0("Episode ", labs[x], " (withheld ", wh[x], ")"), x)),
              s3_rows(cr, "Rolling origin", function(x) as.character(x)), fill = TRUE)
  s3[, Validation := sub("Nino", "Ni\u00f1o", validation)]
  s3_out <- s3[order(Validation, split, model), .(Validation, Split = split, Model = model, `Unit-years` = n,
                    MALE = fmt_num3(male), `RMSE log(1+y)` = fmt_num3(rmse_log1p), `Log score` = fmt_num3(log_score),
                    Coverage = fmt_cov(coverage95), `Training rows` = n_train,
                    `Unidentified coefficients` = data.table::fifelse(is.na(unidentified), EN_DASH, unidentified))]
  notes <- data.table::data.table(Validation = "Notes", Split = c(
    sprintf("LOEO skipped folds (no test rows): %s", paste(sprintf("%s", labs[unique(unlist(cl$skipped))]), collapse = ", ")),
    sprintf("LOEO failed splits: %s", if (nrow(cl$fail_reasons)) paste(cl$fail_reasons$model, cl$fail_reasons$split_id, cl$fail_reasons$error, collapse = "; ") else "none"),
    sprintf("Rolling failed splits: %s", if (nrow(cr$fail_reasons)) paste(cr$fail_reasons$model, cr$fail_reasons$split_id, cr$fail_reasons$error, collapse = "; ") else "none"),
    sprintf("Rows excluded from the common set (missing a variable of any model): %d (LOEO), %d (rolling)",
            nrow(cl$common_dropped), nrow(cr$common_dropped))))
  s3_out <- rbind(s3_out, notes, fill = TRUE)
  write_csv(s3_out, file.path(C_SUPP, "table_S3.csv"))

  # ---- ENSO-index comparison (A1 item 1)
  ispecs <- list(oni = primary_spec("oni_djf_prev"), roni = primary_spec("roni_djf_prev"),
                 nino34 = primary_spec("nino34_djf_prev"))
  il <- cached_compare("index_loeo", ispecs, h, loeo)
  ir <- cached_compare("index_rolling", ispecs, h, roll)
  for (ix in names(ispecs)) {
    s <- il$summary[model == ix]
    E[[sprintf("C.idx.%s.male", ix)]] <- entry(s$male, if (!is.na(s$flag)) NE else fmt_num3(s$male), S,
      sprintf("LOEO MALE of the primary spec with index %s (common rows %d)", ix, il$common_n))
  }
  common <- complete_rows(h, unique(unlist(lapply(ispecs, spec_vars))))$data
  afits <- lapply(ispecs, function(sp) fit_nb(sp, common))
  aic <- vapply(afits, function(f) stats::AIC(f$model), numeric(1))
  best <- names(which.min(aic))
  dmax <- max(aic) - min(aic)
  E[["C.idx.aic_maxdiff"]] <- entry(dmax, fmt_num(dmax, 2), S,
    sprintf("Largest AIC difference between the three ENSO indices (primary spec, same %d rows): %s", nrow(common),
            paste(names(aic), round(aic, 2), sep = "=", collapse = ", ")))
  for (ix in c("roni", "nino34")) {
    r <- irr_table(afits[[ix]], ispecs[[ix]]$slopes)
    E[[sprintf("C.idx.%s.irr", ix)]] <- entry(r$irr, fmt_ci(r$irr, r$lo, r$hi), S,
      sprintf("IRR per +1 deg C of the El Nino term with %s in place of the traditional ONI (primary spec, all %d rows, re %s), Wald CI",
              ix, nrow(common), afits[[ix]]$re_used))
    E[[sprintf("C.idx.%s.p", ix)]] <- entry(r$p, fmt_p(r$p), S, sprintf("P value of the El Nino term with %s", ix))
  }
  so <- il$summary[model == "oni"]; ro <- ir$summary[model == "oni"]
  E[["C.idx.oni.coverage_loeo"]] <- entry(so$coverage95, fmt_cov(so$coverage95), S,
    "LOEO coverage of the nominal 95% prediction interval of the primary model (traditional ONI; Table S4), the model used for the 2027 projection")
  E[["C.idx.oni.coverage_rolling"]] <- entry(ro$coverage95, fmt_cov(ro$coverage95), S,
    "Rolling-origin coverage of the nominal 95% prediction interval of the primary model (traditional ONI; Table S4)")
  E[["C.idx.best_aic"]] <- entry(best, c(oni = "the traditional ONI", roni = "RONI", nino34 = "the Ni\u00f1o-3.4 anomaly")[[best]], S,
    sprintf("Index with the lowest AIC (same %d rows): %s; RE used %s", nrow(common),
            paste(names(aic), round(aic, 2), sep = "=", collapse = ", "),
            paste(names(afits), vapply(afits, `[[`, "", "re_used"), sep = "=", collapse = ", ")))
  idx_lab <- c(oni = "Traditional ONI", roni = "RONI", nino34 = "Ni\u00f1o-3.4 anomaly (ERSSTv5)")
  s4 <- data.table::rbindlist(lapply(names(ispecs), function(ix) {
    a <- il$summary[model == ix]; b <- ir$summary[model == ix]
    r <- irr_table(afits[[ix]], paste0(ispecs[[ix]]$slopes))
    data.table::data.table(Index = idx_lab[[ix]], `LOEO MALE` = fmt_num3(a$male), `LOEO log score` = fmt_num3(a$log_score),
                           `LOEO coverage` = fmt_cov(a$coverage95), `Rolling MALE` = fmt_num3(b$male),
                           `Rolling log score` = fmt_num3(b$log_score), `Rolling coverage` = fmt_cov(b$coverage95),
                           AIC = fmt_num(aic[[ix]], 1), `El Nino term IRR (95% CI)` = fmt_ci(r$irr, r$lo, r$hi),
                           `Random effects` = afits[[ix]]$re_used,
                           `Failed splits (LOEO/rolling)` = paste0(a$n_failed_splits, "/", b$n_failed_splits))
  }))
  data.table::setnames(s4, "El Nino term IRR (95% CI)", "El Ni\u00f1o term IRR per 1 \u00b0C (95% CI)")
  write_csv(s4, file.path(C_SUPP, "table_S4.csv"))
  saveRDS(list(n_loeo = cl$common_n, n_roll = cr$common_n, idx_n = il$common_n), file.path(C_CACHE, "validate_meta.rds"))
  save_entries(E, "validate")
}

if (sys.nframe() == 0L) run_validate()
