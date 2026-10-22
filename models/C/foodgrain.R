# Paper C secondary outcome: foodgrain production deviation from trend (foodgrain_model.csv,
# 1997-2016, 30 units). Gaussian LMMs with unit random intercepts, no offset and no trend
# (the outcome is already detrended), one exposure per model (Table II).
# Run from the models/ folder:  Rscript C/foodgrain.R   (or via C/run_all.R)

if (!exists("C_DIR")) { source("common/R/load.R"); source("C/helpers.R") }

fit_food <- function(x, d) {
  cr <- complete_rows(d, c("foodgrain_dev_pct", x, "unit_id"))
  dd <- droplevels(cr$data)
  m <- glmmTMB_fit(stats::as.formula(paste("foodgrain_dev_pct ~", x, "+ (1 | unit_id)"), env = globalenv()),
                   dd, family = stats::gaussian())
  if (!.converged(m)) stop("foodgrain: Gaussian LMM for ", x, " did not converge")
  co <- summary(m)$coefficients$cond[x, ]
  list(model = m, n = nrow(dd), dropped = cr$dropped, est = co[[1]], se = co[[2]], p = co[[4]])
}

run_foodgrain <- function() {
  S <- "foodgrain.R"
  E <- list()
  fg <- prep_foodgrain()
  s1 <- list()
  defs <- list(
    jjas = list(var = "rain_jjas_dep_pct", k = -10, key = "C.food.diff_jjas_def10", pkey = "C.food.p_jjas",
                label = "difference per 10-point June-September rainfall deficit (-10 beta, bounds swapped)"),
    oni = list(var = "oni_jjas", k = 1, key = "C.food.diff_oni", pkey = "C.food.p_oni",
               label = "difference per +1 deg C oni_jjas"),
    developing = list(var = "el_nino_developing_i", k = 1, key = "C.food.diff_developing", pkey = "C.food.p_developing",
                      label = "difference, El Nino-developing vs other years"))
  for (nm in names(defs)) {
    x <- defs[[nm]]
    log_msg("foodgrain:", nm)
    f <- fit_food(x$var, fg)
    s1[[length(s1) + 1L]] <- s1_rows(paste("Foodgrain deviation (Gaussian LMM):", x$var), f$n, "int", "int", f$dropped)
    lo <- x$k * (f$est - 1.959964 * f$se); hi <- x$k * (f$est + 1.959964 * f$se)
    v <- x$k * f$est
    b <- sort(c(lo, hi))
    E[[x$key]] <- entry(v, fmt_ci(v, b[1], b[2], digits = 1), S,
                        sprintf("Foodgrain deviation from trend (percentage points), %s; Wald 95%% CI; n = %d", x$label, f$n))
    E[[x$pkey]] <- entry(f$p, fmt_p(f$p), S, sprintf("P value, foodgrain %s", x$label))
    if (nm == "jjas") E[["C.food.n_unit_years"]] <- entry(f$n, fmt_int(f$n), S, "Rows in the foodgrain rainfall fit")
  }
  saveRDS(data.table::rbindlist(s1), file.path(C_CACHE, "s1_foodgrain.rds"))
  save_entries(E, "foodgrain")
}

if (sys.nframe() == 0L) run_foodgrain()
