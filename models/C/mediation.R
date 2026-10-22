# Paper C mediation (Table III): product of coefficients, preceding-winter ONI (single linear
# term) -> mediator -> recorded heat deaths, for heatwave days, March-June Tmax anomaly and
# monsoon onset anomaly (AN, LD set NA), each on its own complete rows; unit cluster bootstrap
# B = 1,000 (mediate(cores = MED_CORES), 6 PSOCK workers; see below). Also the H3 verdict (fixed rule, below).
# Run from the models/ folder:  Rscript C/mediation.R   (or via C/run_all.R)

if (!exists("C_DIR")) { source("common/R/load.R"); source("C/helpers.R") }

MED <- list(hw = list(var = "heatwave_days", unit = "days"),
            tmax = list(var = "tmax_mamj_anom", unit = "deg C"),
            onset = list(var = "onset_anom_days", unit = "days"))
MED_B <- 1000L
# 6 PSOCK workers, not 10: with 10 workers and another bootstrap running at the same time, a
# 16 GB machine paged (0.2-0.8 GB free; a resample took 75 s elapsed for 12 s CPU).
# Results do not depend on cores (resample i always uses seed + i - 1); hw ran with 4 workers.
MED_CORES <- 6L
# PSOCK workers start R in models/, where .Rprofile activates renv; renv's sandbox set-up took
# > 60 s per worker when 10 started at once, and a worker missed the cluster connection timeout.
# Disabling the sandbox for this process (inherited by the workers) only skips that set-up step;
# the library and package versions are unchanged.
Sys.setenv(RENV_CONFIG_SANDBOX_ENABLED = "FALSE")

run_one_mediation <- function(h, m) {
  f <- file.path(C_CACHE, paste0("med_", m, ".rds"))
  if (file.exists(f)) return(readRDS(f))
  log_msg("mediation:", m, "B =", MED_B, "cores =", MED_CORES)
  r <- mediate(h, "heat_deaths", "oni_djf_prev", MED[[m]]$var, covars = c("label2014", "covid2020"),
               B = MED_B, seed = SEED_C, cores = MED_CORES)
  saveRDS(r, f)
  log_msg("mediation:", m, "done; B_ok =", r$B_ok, "flag =", r$flag, "prop_flag =", r$prop_flag)
  r
}

PROP_FLAG_TXT <- c(total_effect_ci_includes_0 = "the bootstrap CI of the total association includes the null",
                   opposite_signs = "the indirect and total associations have opposite signs",
                   nonfinite_resample_proportion = "a bootstrap resample had a total association of zero",
                   not_assessed = "more than 10% of bootstrap refits failed")

run_mediation <- function() {
  S <- "mediation.R"
  E <- list()
  h <- prep_heat()
  res <- lapply(stats::setNames(names(MED), names(MED)), function(m) run_one_mediation(h, m))
  rows <- list(); s1 <- list()
  for (m in names(MED)) {
    r <- res[[m]]
    w <- r$wald
    wa <- w[path == "a"]; wb <- w[path == "b"]
    E[[sprintf("C.med.%s.a", m)]] <- entry(r$a, fmt_ci(wa$est, wa$lo, wa$hi, 2), S,
      sprintf("a-path: change in %s (%s) per +1 deg C ONI, Gaussian LMM, Wald CI; n = %d", MED[[m]]$var, MED[[m]]$unit, r$n))
    E[[sprintf("C.med.%s.b", m)]] <- entry(exp(r$b), fmt_ci(exp(wb$est), exp(wb$lo), exp(wb$hi)), S,
      sprintf("b-path: IRR per 1 unit of %s, NB GLMM with ONI, Wald CI", MED[[m]]$var))
    ind_disp <- if (r$flag == "ok") fmt_ci(exp(r$indirect), exp(r$ci$indirect[1]), exp(r$ci$indirect[2]))
                else paste0(fmt_num(exp(r$indirect), 2), " (CI not estimated: >10% of bootstrap refits failed)")
    E[[sprintf("C.med.%s.indirect", m)]] <- entry(exp(r$indirect), ind_disp, S,
      sprintf("Indirect IRR per +1 deg C ONI through %s, exp(a*b), cluster-bootstrap percentile CI (B = %d, ok %d)",
              MED[[m]]$var, r$B, r$B_ok))
    pct <- 100 * r$prop_mediated
    prop_disp <- if (r$flag != "ok") paste0(fmt_num(pct, 0), "% (CI not estimated: >10% of bootstrap refits failed)")
                 else if (r$prop_flag != "ok") "not estimable"
                 else fmt_pct_ci(pct, 100 * r$ci$prop[1], 100 * r$ci$prop[2])
    E[[sprintf("C.med.%s.prop", m)]] <- entry(pct, prop_disp, S,
      sprintf("Proportion mediated through %s = indirect / c_total x 100 (point %.2f%%); flag %s; prop_flag %s%s",
              MED[[m]]$var, pct, r$flag, r$prop_flag,
              if (r$prop_flag != "ok") paste0(" (", PROP_FLAG_TXT[[r$prop_flag]], ")") else ""))
    rows[[m]] <- data.table::data.table(mediator = m, n = r$n, a = r$a, b = r$b, c_direct = r$c_direct, c_total = r$c_total,
      indirect = r$indirect, prop = r$prop_mediated, ci_ind_lo = r$ci$indirect[1], ci_ind_hi = r$ci$indirect[2],
      ci_prop_lo = r$ci$prop[1], ci_prop_hi = r$ci$prop[2], ci_ctot_lo = r$ci$c_total[1], ci_ctot_hi = r$ci$c_total[2],
      B = r$B, B_ok = r$B_ok, B_failed = r$B_failed, B_prop_nonfinite = r$B_prop_nonfinite, flag = r$flag,
      prop_flag = r$prop_flag)
    s1[[m]] <- s1_rows(sprintf("Mediation (a-path, b-path and total models, random intercepts): %s", MED[[m]]$var),
                       r$n, "int", "int", r$dropped)
  }
  wt <- res$hw$wald[path == "c_total"]
  E[["C.med.total_irr"]] <- entry(exp(res$hw$c_total), fmt_ci(exp(wt$est), exp(wt$lo), exp(wt$hi)), S,
    "Total IRR per +1 deg C ONI, exp(c_total), heatwave-days run, Wald CI from the total model")
  med_tab <- data.table::rbindlist(rows)
  write_csv(med_tab, file.path(C_CACHE, "mediation_summary.csv"))
  saveRDS(data.table::rbindlist(s1), file.path(C_CACHE, "s1_mediation.rds"))

  # ---- H3 verdict (fixed, pre-specified rule)
  dec_lo <- readRDS(file.path(C_CACHE, "heat_decaying_irr.rds"))$lo     # written by heat.R
  cond_i <- is.finite(dec_lo) && dec_lo > 1
  props <- med_tab$prop; names(props) <- med_tab$mediator
  hw <- med_tab[mediator == "hw"]
  cond_ii <- hw$flag == "ok" && hw$prop_flag == "ok" && which.max(props) == which(names(props) == "hw") &&
             is.finite(hw$ci_prop_lo) && hw$ci_prop_lo > 0
  verdict <- if (cond_i && cond_ii) "consistent with" else "not consistent with"
  E[["C.h3.verdict"]] <- entry(verdict, verdict, S,
    sprintf("H3 rule: (i) decaying IRR lower bound %.4f > 1: %s; (ii) heatwave-days proportion largest (props: %s) with bootstrap lower bound > 0 (lower bound %s; flag %s; prop_flag %s): %s",
            dec_lo, cond_i, paste(names(props), sprintf("%.3f", props), sep = "=", collapse = ", "),
            format(hw$ci_prop_lo), hw$flag, hw$prop_flag, cond_ii))
  save_entries(E, "mediation")
}

if (sys.nframe() == 0L) run_mediation()
