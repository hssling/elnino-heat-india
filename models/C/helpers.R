# Paper C helpers: data preparation (the analysis rules described in README.md, Missing-data rules),
# Paper C display formatters, and per-script result/output caching.
# Sourced by every models/C script after common/R/load.R (working directory: the models/ folder).

C_DIR <- file.path(MODELS_ROOT, "C")
C_CACHE <- file.path(C_DIR, "_cache")
C_PAPER <- file.path(REPO_ROOT, "papers", "C")
C_FIG_DATA <- file.path(C_PAPER, "figures", "data")
C_SUPP <- file.path(C_PAPER, "supplementary")
for (p in c(C_CACHE, C_FIG_DATA, C_SUPP, file.path(C_DIR, "logs"))) dir.create(p, recursive = TRUE, showWarnings = FALSE)

SEED_C <- 20261015L
RAIN_VARS <- c("rain_jjas_dep_pct", "spi3_sep", "onset_anom_days",
               "rain_jjas_dep_pct_lag1", "spi3_sep_lag1", "onset_anom_days_lag1")
NO_RAIN_UNITS <- c("AN", "LD")          # rule 1: no IMD rain cell (A&N NA upstream; LD Kerala-coast proxy)

log_msg <- function(...) {
  cat(format(Sys.time(), "%H:%M:%S"), "|", ..., "\n")
  flush.console()
}

# ---------------------------------------------------------------- data preparation
# Rule 1: rainfall-based variables NA for AN and LD. Returns the data and the cells blanked
# (non-missing values set NA), for Supplementary Table S1 and the report.
blank_rain <- function(d) {
  blanked <- list()
  for (v in intersect(RAIN_VARS, names(d))) {
    idx <- which(as.character(d$unit_id) %in% NO_RAIN_UNITS & !is.na(d[[v]]))
    if (length(idx))
      blanked[[v]] <- data.table::data.table(unit_id = as.character(d$unit_id[idx]), year = d$year[idx], variable = v)
    data.table::set(d, i = which(as.character(d$unit_id) %in% NO_RAIN_UNITS), j = v, value = NA_real_)
  }
  list(data = d, blanked = data.table::rbindlist(blanked))
}

# Preceding-winter Nino-3.4 anomaly (ERSSTv5, 1991-2020 base): mean of the monthly anomaly for
# December of year t-1 and January-February of year t; NA unless all three months exist.
nino34_djf_prev_table <- function() {
  e <- data.table::fread(file.path(REPO_ROOT, "data", "derived", "enso_monthly.csv"))
  m <- e[, .(year, month, nino34_anom)]
  yrs <- sort(unique(m$year))
  data.table::rbindlist(lapply(yrs, function(t) {
    v <- c(m[year == t - 1L & month == 12L, nino34_anom], m[year == t & month == 1L, nino34_anom],
           m[year == t & month == 2L, nino34_anom])
    data.table::data.table(year = t, nino34_djf_prev = if (length(v) == 3L && all(is.finite(v))) mean(v) else NA_real_)
  }))
}

prep_heat <- function() {
  d <- read_model_input("heat")
  b <- blank_rain(d)
  d <- b$data
  n34 <- nino34_djf_prev_table()
  d <- merge(d, n34, by = "year", all.x = TRUE, sort = FALSE)
  data.table::setorder(d, unit_id, year)
  split_phase(d, c("oni_djf_prev", "roni_djf_prev", "nino34_djf_prev"))
  d[, el_nino_decaying_i := as.integer(el_nino_decaying)]
  d[, el_nino_developing_i := as.integer(el_nino_developing)]
  d[, oni_x_dmi := oni_djf_prev * dmi_son_prev]
  attr(d, "blanked") <- b$blanked
  d[]
}

prep_farmers <- function() {
  d <- read_model_input("farmers")
  b <- blank_rain(d)
  d <- b$data
  d[, definition_break_2014_i := as.integer(definition_break_2014)]
  d[, el_nino_developing_i := as.integer(el_nino_developing)]
  attr(d, "blanked") <- b$blanked
  d[]
}

prep_foodgrain <- function() {
  d <- read_model_input("foodgrain")
  b <- blank_rain(d)
  d <- b$data
  d[, el_nino_developing_i := as.integer(el_nino_developing)]
  attr(d, "blanked") <- b$blanked
  d[]
}

unit_names <- function() {
  f <- data.table::fread(file.path(REPO_ROOT, "pipeline", "reference", "state_frame.csv"))
  stats::setNames(f$unit_name, f$unit_id)
}

# ---------------------------------------------------------------- formatters (results.json display strings)
MINUS <- "\u2212"
fmt_signed <- function(x, digits) {
  out <- fmt_num(x, digits)
  pos <- !is.na(x) & round(x, digits) > 0
  out[pos] <- paste0("+", out[pos])
  out
}
fmt_num3 <- function(x, digits = 3) fmt_num(x, digits)
fmt_cov <- function(x) ifelse(is.na(x), NA_character_, paste0(fmt_num(100 * x, 1), "%"))
fmt_signed_pct <- function(x) paste0(fmt_num(x, 1), "%")
# "34% (95% CI 12-60%)"; negative bounds: "-8% (95% CI -30 to 15%)" (U+2212). x in percent.
fmt_pct_ci <- function(est, lo, hi) {
  neg <- round(lo) < 0 || round(hi) < 0
  paste0(fmt_num(est, 0), "% (95% CI ", fmt_num(lo, 0), if (neg) " to " else EN_DASH, fmt_num(hi, 0), "%)")
}
fmt_mean_sd <- function(x, digits = 1, signed = FALSE) {
  x <- x[is.finite(x)]
  if (!length(x)) return(EN_DASH)
  m <- if (signed) fmt_signed(mean(x), digits) else fmt_num(mean(x), digits)
  paste0(m, " (", fmt_num(stats::sd(x), digits), ")")
}
fmt_median_range <- function(x, digits = 0) {
  x <- x[is.finite(x)]
  if (!length(x)) return(EN_DASH)
  f <- function(v) if (digits == 0) fmt_int(v) else fmt_num(v, digits, big.mark = ",")
  neg <- round(min(x), digits) < 0
  paste0(f(stats::median(x)), " (", f(min(x)), if (neg) " to " else EN_DASH, f(max(x)), ")")
}
fmt_mean_range <- function(x, digits = 2) {
  x <- x[is.finite(x)]
  if (!length(x)) return(EN_DASH)
  paste0(fmt_signed(mean(x), digits), " (", fmt_signed(min(x), digits), " to ", fmt_signed(max(x), digits), ")")
}
# "a, b and c"
and_list <- function(x) {
  x <- as.character(x)
  if (length(x) <= 1L) return(paste(x, collapse = ""))
  paste0(paste(x[-length(x)], collapse = ", "), " and ", x[length(x)])
}
# IRR of a decrease / cooler term: exp(-k beta), bounds swapped. Input: irr_table row.
invert_irr <- function(row, k = 1) {
  list(irr = row$irr^(-k), lo = row$hi^(-k), hi = row$lo^(-k), p = row$p)
}

# ---------------------------------------------------------------- results and outputs
# Each script returns a named list of res_entry() objects; run_all.R merges them.
save_entries <- function(entries, name) {
  saveRDS(entries, file.path(C_CACHE, paste0("entries_", name, ".rds")))
  invisible(entries)
}
load_entries <- function(name) readRDS(file.path(C_CACHE, paste0("entries_", name, ".rds")))

entry <- function(value, display, script, description) {
  res_entry(value = if (is.null(value)) NA else value, display = display,
            script = paste0("models/C/", script), description = description)
}

# Supplementary tables (papers/C/supplementary) show missing cells as an en dash; data CSVs keep "NA".
write_csv <- function(x, path) {
  na <- if (basename(dirname(path)) == "supplementary") EN_DASH else "NA"
  data.table::fwrite(x, path, bom = FALSE, na = na)
}

# Fit summary rows for Supplementary Table S1 (dropped rows collapsed by unit and variable).
s1_rows <- function(model_label, n, re_used, attempts, dropped) {
  base <- data.table::data.table(model = model_label, n_used = n, re_used = re_used,
                                 attempts = paste(attempts, collapse = " > "))
  if (is.null(dropped) || !nrow(dropped))
    return(cbind(base, dropped_variable = EN_DASH, unit_id = EN_DASH, years = EN_DASH, n_dropped = 0L))
  g <- dropped[, .(years = collapse_years(year), n_dropped = .N), by = .(dropped_variable = variable, unit_id)]
  cbind(base[rep(1L, nrow(g))], g)
}
collapse_years <- function(y) {
  y <- sort(unique(as.integer(y)))
  if (!length(y)) return("")
  runs <- split(y, cumsum(c(1L, diff(y) != 1L)))
  paste(vapply(runs, function(r) if (length(r) == 1L) as.character(r) else paste0(r[1], EN_DASH, r[length(r)]),
               character(1)), collapse = ", ")
}
