# Paper C: full analysis, one command from the models/ folder:
#   Rscript C/run_all.R              # fresh run (clears models/C/_cache first)
#   Rscript C/run_all.R --use-cache  # reuse cached fits / comparisons / bootstrap results
# Writes papers/C/results.json (every reported number), figure data in
# papers/C/figures/data/ and Supplementary Tables S1-S7 in papers/C/supplementary/.
# Fixed seed: SEED_C (helpers.R) is passed to every stochastic step (validation draws,
# mediation bootstrap, projection draws); the global RNG is also seeded.

source("common/R/load.R")
source("C/helpers.R")
args <- commandArgs(trailingOnly = TRUE)
if (!"--use-cache" %in% args) {
  old <- list.files(C_CACHE, full.names = TRUE)
  if (length(old)) unlink(old, recursive = TRUE)
  log_msg("run_all: cache cleared (", length(old), " files)")
}
set.seed(SEED_C)

source("C/descriptive.R"); source("C/heat.R"); source("C/farmers.R"); source("C/foodgrain.R")
source("C/validate.R"); source("C/mediation.R"); source("C/project.R")

steps <- c("descriptive", "heat", "farmers", "foodgrain", "validate", "mediation", "project")
for (s in steps) {
  log_msg("run_all: step", s)
  get(paste0("run_", s))()
}

# ---- Supplementary Table S1: dropped rows and random-effect structures, every model
s1 <- data.table::rbindlist(lapply(c("heat", "farmers", "foodgrain", "mediation"),
                                   function(n) readRDS(file.path(C_CACHE, paste0("s1_", n, ".rds")))), fill = TRUE)
h <- prep_heat(); fa <- prep_farmers(); fg <- prep_foodgrain()
bl <- data.table::rbindlist(list(cbind(table = "heat_model.csv", attr(h, "blanked")),
                                 cbind(table = "farmers_model.csv", attr(fa, "blanked")),
                                 cbind(table = "foodgrain_model.csv", attr(fg, "blanked"))), fill = TRUE)
bl <- bl[!is.na(variable)]                     # tables with no Lakshadweep row (foodgrain) add nothing
vm <- readRDS(file.path(C_CACHE, "validate_meta.rds"))
re_txt <- c(us = "correlated", diag = "uncorrelated", int = "intercept only")
s1_out <- s1[, .(Model = model, `Unit-years used` = n_used, `Random effects used` = re_txt[re_used],
                 `Structures tried` = attempts, `Dropped: first missing variable` = dropped_variable,
                 `Dropped: unit` = unit_id, `Dropped: years` = years, `Dropped rows` = n_dropped)]
# Plain variable labels for the reader (ruling P23, M11)
VAR_LABEL <- c(rain_jjas_dep_pct = "June-September rainfall departure", spi3_sep = "SPI-3 (September)",
               onset_anom_days = "monsoon onset anomaly", rain_jjas_dep_pct_lag1 = "previous-year rainfall departure",
               spi3_sep_lag1 = "previous-year SPI-3", onset_anom_days_lag1 = "previous-year onset anomaly",
               farming_sector = "farming-sector suicides (non-reporting)", foodgrain_dev_pct = "foodgrain deviation",
               heatwave_days = "heatwave days", tmax_mamj_anom = "March-June temperature anomaly",
               log1p_heat_deaths_lag1 = "previous-year deaths")
plain <- function(v) ifelse(v %in% names(VAR_LABEL), VAR_LABEL[v], v)
VAR_LABEL <- c(VAR_LABEL, oni_jjas = "July-September ONI", el_nino_developing_i = "El Nino-developing year")
# Model labels written by the scripts name some variables internally (ruling P25, N3): plain labels here
for (v in names(VAR_LABEL)[order(-nchar(names(VAR_LABEL)))])
  s1_out[, Model := gsub(v, VAR_LABEL[[v]], Model, fixed = TRUE)]
s1_out[, `Dropped: first missing variable` := plain(`Dropped: first missing variable`)]
bl_vars <- unique(bl$variable[!grepl("_lag1$", bl$variable)])
notes <- data.table::data.table(Model = c(
  sprintf("Rule: rainfall-based variables (%s, and their previous-year values) were set missing for Andaman and Nicobar (already missing in the source) and Lakshadweep (whose gridded rainfall is a Kerala-coast proxy); %d Lakshadweep unit-year values were blanked across the heat and farmer data",
          paste(plain(bl_vars), collapse = ", "), nrow(bl)),
  sprintf("Validation (Table IV): Models A-C scored on identical rows, %d unit-years (leave-one-El-Nino-out) and %d (rolling origin); first-year rows lack the lagged outcome (Supplementary Table S3)",
          vm$n_loeo, vm$n_roll)))
s1_out <- rbind(s1_out, notes, fill = TRUE)
s1_out[, Model := gsub("Nino", "Ni\u00f1o", gsub("Nina", "Ni\u00f1a", Model))]
write_csv(s1_out, file.path(C_SUPP, "table_S1.csv"))

# ---- results.json
E <- do.call(c, lapply(steps, load_entries))
if (anyDuplicated(names(E))) stop("run_all: duplicate result keys: ", paste(names(E)[duplicated(names(E))], collapse = ", "))
write_results(E, file.path(C_PAPER, "results.json"))
log_msg("run_all: wrote", length(E), "keys to papers/C/results.json")
