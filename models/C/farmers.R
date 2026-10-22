# Paper C secondary outcome: farming-sector suicides (farmers_model.csv, 2001-2023).
# NB-GLMMs with SPI-3 (September), the June-September rainfall departure or the El Nino-developing
# indicator, the 2014 definition-break indicator and unit random slopes (Table II), the P16
# true-zero sensitivity key and Supplementary Table S6.
# Run from the models/ folder:  Rscript C/farmers.R   (or via C/run_all.R)

if (!exists("C_DIR")) { source("common/R/load.R"); source("C/helpers.R") }

FARM_X <- list(
  spi = list(var = "spi3_sep", lag = "spi3_sep_lag1", k = 1, invert = TRUE, rain = TRUE,
             label = "per 1-unit decrease in SPI-3 (September)"),
  jjas = list(var = "rain_jjas_dep_pct", lag = "rain_jjas_dep_pct_lag1", k = 10, invert = TRUE, rain = TRUE,
              label = "per 10-point June-September rainfall deficit"),
  developing = list(var = "el_nino_developing_i", lag = NA_character_, k = 1, invert = FALSE, rain = FALSE,
                    label = "El Nino-developing vs other years"))

farm_spec <- function(x, break_term = TRUE)
  nb_spec("farming_sector", fixed = c(x, if (break_term) "definition_break_2014_i"), slopes = x)

# Every P14-rule non-reporting farming_sector cell replaced by its printed value (Ruling P16
# sensitivity): the printed farming_sector record of the source the panel uses for that year
# (ncrb_<year>, or farm_ogd0112 for 2001-2003), summed over pooled-unit members.
true_zero_data <- function(d) {
  rv <- data.table::fread(file.path(REPO_ROOT, "pipeline", "reference", "outcomes_reviewed.csv"))
  p14 <- rv[outcome == "farmer_suicides" & variable == "farming_sector" & disposition == "non_reporting" &
              startsWith(reason, "P14 printed-zero rule:"), .(unit_id, year = as.integer(year))]
  rec <- data.table::as.data.table(utils::read.csv(gzfile(file.path(REPO_ROOT, "data", "derived", "outcomes",
                                                                 "outcome_records_all.csv.gz")),
                                                        stringsAsFactors = FALSE))
  rec <- rec[outcome == "farmer_suicides" & variable == "farming_sector"]
  rec[, want := data.table::fifelse(year <= 2003L, "farm_ogd0112", paste0("ncrb_", year))]
  printed <- rec[source_id == want, .(printed = if (any(is.na(value))) NA_real_ else sum(value)), by = .(unit_id, year)]
  p14 <- merge(p14, printed, by = c("unit_id", "year"), all.x = TRUE)
  d2 <- data.table::copy(d)
  d2[p14, on = c("unit_id", "year"), farming_sector := i.printed]
  list(data = d2, cells = p14)
}

run_farmers <- function() {
  S <- "farmers.R"
  E <- list()
  fa <- prep_farmers()
  s1 <- list()
  add_s1 <- function(label, fit) s1[[length(s1) + 1L]] <<- s1_rows(label, fit$n, fit$re_used, fit$attempts, fit$dropped)

  nr_all <- sum(grepl("farming_sector:non_reporting", fa$sources, fixed = TRUE))
  tz <- true_zero_data(fa)
  nr <- nrow(tz$cells)
  if (anyNA(tz$cells$printed)) stop("farmers: a P14-rule cell has no printed farming_sector record")
  E[["C.farm.n_nonreporting"]] <- entry(nr, fmt_int(nr), S,
    sprintf("farming_sector cells 2001-2023 set non-reporting by the P14/P16 printed-zero rule (reason prefix 'P14 printed-zero rule:' in outcomes_reviewed.csv); %d non_reporting cells in all, the other %d being West Bengal 2012 (printed 'NR') and Chhattisgarh 2012 (P14 reporting-episode ruling)",
            nr_all, nr_all - nr))

  fits <- list()
  for (nm in names(FARM_X)) {
    x <- FARM_X[[nm]]
    log_msg("farmers:", nm)
    ft <- fit_nb(farm_spec(x$var), fa)
    fits[[nm]] <- ft
    add_s1(paste("Farming-sector suicides:", x$label), ft)
  }
  E[["C.farm.n_unit_years"]] <- entry(fits$spi$n, fmt_int(fits$spi$n), S, "Rows in the farming-sector SPI-3 fit")
  est <- function(ft, x) {
    r <- irr_table(ft, x$var)
    if (x$invert) invert_irr(r, x$k) else as.list(r[, .(irr, lo, hi, p)])
  }
  key <- c(spi = "C.farm.irr_spi_dec", jjas = "C.farm.irr_jjas_def10", developing = "C.farm.irr_developing")
  pkey <- c(spi = "C.farm.p_spi", jjas = "C.farm.p_jjas", developing = "C.farm.p_developing")
  for (nm in names(FARM_X)) {
    r <- est(fits[[nm]], FARM_X[[nm]])
    E[[key[[nm]]]] <- entry(r$irr, fmt_ci(r$irr, r$lo, r$hi), S,
      sprintf("Farming-sector suicides IRR %s (re %s; Wald CI)", FARM_X[[nm]]$label, fits[[nm]]$re_used))
    E[[pkey[[nm]]]] <- entry(r$p, fmt_p(r$p), S, sprintf("P value, farming-sector suicides %s", FARM_X[[nm]]$label))
  }

  # ---- sensitivity analyses (Supplementary Table S6)
  write_csv(tz$cells, file.path(C_CACHE, "farm_true_zero_cells.csv"))
  rows <- list()
  add_row <- function(analysis, nm, ft) {
    x <- FARM_X[[nm]]
    if (inherits(ft, "error")) {
      rows[[length(rows) + 1L]] <<- data.table::data.table(Analysis = analysis, Exposure = x$label, re = NA_character_,
        n = NA_integer_, irr = NA_real_, lo = NA_real_, hi = NA_real_, p = NA_real_, status = paste("failed:", conditionMessage(ft)))
      return(NULL)
    }
    r <- est(ft, list(var = ft$spec$slopes, invert = x$invert, k = x$k))
    rows[[length(rows) + 1L]] <<- data.table::data.table(Analysis = analysis, Exposure = x$label, re = ft$re_used, n = ft$n,
      irr = r$irr, lo = r$lo, hi = r$hi, p = r$p, status = "ok")
    r
  }
  safe <- function(expr) tryCatch(expr, error = function(e) e)
  for (nm in names(FARM_X)) add_row("Primary", nm, fits[[nm]])
  for (nm in names(FARM_X)) {
    x <- FARM_X[[nm]]
    log_msg("farmers sensitivity:", nm)
    ft <- safe(fit_nb(farm_spec(x$var), tz$data)); if (!inherits(ft, "error")) add_s1(paste("Farm sensitivity, printed zeros as true zeros:", x$label), ft)
    r <- add_row("Printed zeros (P14 rule) as true zeros", nm, ft)
    if (nm == "spi") {
      E[["C.farm.sens_truezero.irr_spi_dec"]] <- entry(if (is.null(r)) NA else r$irr,
        if (is.null(r)) "not estimated (fit failed)" else fmt_ci(r$irr, r$lo, r$hi), S,
        sprintf("SPI-3 IRR per 1-unit decrease with the %d P14-rule non-reporting cells set to their printed values (Ruling P16)", nrow(tz$cells)))
    }
    ft <- safe(fit_nb(farm_spec(x$var, break_term = FALSE), fa[year <= 2013L]))
    if (!inherits(ft, "error")) add_s1(paste("Farm sensitivity, 2001-2013:", x$label), ft)
    r13 <- add_row("2001-2013 only (no break indicator)", nm, ft)
    if (nm == "developing") {                      # ruling P23 (M6): reported neutrally in Results
      E[["C.farm.sens_pre2014.irr_developing"]] <- entry(if (is.null(r13)) NA else r13$irr,
        if (is.null(r13)) "not estimated (fit failed)" else fmt_ci(r13$irr, r13$lo, r13$hi), S,
        "Pre-specified sensitivity: El Nino-developing vs other years IRR, 2001-2013 only (no break indicator), Wald CI")
      E[["C.farm.sens_pre2014.p_developing"]] <- entry(if (is.null(r13)) NA else r13$p,
        if (is.null(r13)) "not estimated" else fmt_p(r13$p), S, "P value of the 2001-2013 developing-year sensitivity")
    }
    if (!is.na(x$lag)) {
      ft <- safe(fit_nb(farm_spec(x$lag), fa))
      if (!inherits(ft, "error")) add_s1(paste("Farm sensitivity, lag-1 exposure:", x$label), ft)
      add_row("Lag-1 exposure (previous year)", nm, ft)
    }
    if (x$rain) {
      ft <- safe(fit_nb(farm_spec(x$var), droplevels(fa[!unit_id %in% c("JK", "AR")])))
      if (!inherits(ft, "error")) add_s1(paste("Farm sensitivity, excluding JK and AR:", x$label), ft)
      add_row("Excluding Jammu and Kashmir and Arunachal Pradesh", nm, ft)
    }
    ft <- safe(fit_nb(farm_spec(x$var), droplevels(fa[unit_id != "DNH_DD"])))
    if (!inherits(ft, "error")) add_s1(paste("Farm sensitivity, excluding DNH_DD:", x$label), ft)
    add_row("Excluding Dadra and Nagar Haveli and Daman and Diu", nm, ft)
  }
  s6 <- data.table::rbindlist(rows)
  write_csv(s6, file.path(C_CACHE, "farm_sensitivity_raw.csv"))
  s6_out <- s6[, .(Analysis, Exposure = sub("El Nino", "El Ni\u00f1o", Exposure), `Random effects` = re, `Unit-years` = n,
                   `IRR (95% CI)` = fmt_ci(irr, lo, hi), P = fmt_p(p), Status = status)]
  write_csv(s6_out, file.path(C_SUPP, "table_S6.csv"))
  saveRDS(data.table::rbindlist(s1), file.path(C_CACHE, "s1_farmers.rds"))
  save_entries(E, "farmers")
}

if (sys.nframe() == 0L) run_farmers()
