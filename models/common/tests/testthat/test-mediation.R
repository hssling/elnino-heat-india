sim_mediation <- function(seed = 2) {
  d <- sim_panel(slope_sd = 0, seed = seed)
  set.seed(seed)
  d[, m := 0.5 * x + stats::rnorm(.N, 0, 0.5)]                 # a = 0.5
  d[, mu2 := exp(-8 + a + 0.1 * x + 0.4 * m + log_pop)]       # c' = 0.1, b = 0.4
  d[, y := stats::rnbinom(.N, size = 8, mu = mu2)]
  d
}

test_that("mediate recovers a*b and its bootstrap CI covers the truth", {
  skip_if_slow_disabled()                                      # ~5 min: B = 40
  r <- mediate(sim_mediation(), "y", "x", "m", trend_df = 0L, B = 40)
  expect_lt(abs(r$indirect - 0.2), 0.07)
  expect_true(r$ci$indirect[1] < 0.2 && 0.2 < r$ci$indirect[2])
  expect_identical(r$flag, "ok")
})

test_that("bootstrap resampled units become distinct clusters", {
  d <- sim_mediation()
  ids <- bootstrap_units(d, seed = 3)
  expect_equal(length(unique(ids$unit_id)), length(unique(d$unit_id)))
  expect_true(all(grepl("_[0-9]+$", ids$unit_id)))
})

test_that("excess bootstrap failures give NA CI and a flag", {
  d <- sim_mediation()
  n <- 0
  flaky <- function(formula, data, family = glmmTMB::nbinom2()) {
    n <<- n + 1; if (n > 3) stop("fail") else glmmTMB_fit(formula, data, family)
  }
  r <- mediate(d, "y", "x", "m", trend_df = 0L, B = 10, fitter = flaky)
  expect_true(all(is.na(r$ci$indirect)))
  expect_identical(r$flag, "too_many_failed_fits")
})

# ---- additional checks (review focus: same rows, failure threshold, RNG, families) ----

test_that("all three mediation models are fitted on the same complete rows", {
  d <- sim_mediation()
  d[unit_id == "U01" & year == 2005, m := NA]                  # mediator NA: used only by a- and b-paths
  d[unit_id == "U02" & year == 2010, y := NA]                  # outcome NA: used only by b-path and total
  r <- mediate(d, "y", "x", "m", trend_df = 0L, B = 2)
  expect_equal(r$n, nrow(d) - 2L)
  expect_equal(unname(r$n_by_model), rep(nrow(d) - 2L, 3))
  expect_setequal(paste(r$dropped$unit_id, r$dropped$year, r$dropped$variable),
                  c("U01 2005 m", "U02 2010 y"))
})

test_that("the a-path uses the fitter hook with a gaussian family; NB paths the NB2 default", {
  d <- sim_mediation()
  fams <- character()
  spy <- function(formula, data, family = glmmTMB::nbinom2()) {
    fams <<- c(fams, paste(all.vars(formula)[1], family$family))
    glmmTMB_fit(formula, data, family)
  }
  mediate(d, "y", "x", "m", trend_df = 0L, B = 1, fitter = spy)
  expect_setequal(unique(fams), c("m gaussian", "y nbinom2"))
  expect_equal(sum(grepl("^m ", fams)), 2L)                    # point estimate + 1 resample
  expect_equal(sum(grepl("^y ", fams)), 4L)
})

test_that("failures at or below 10% of B keep the CI; the count is reported", {
  d <- sim_mediation()
  n <- 0
  one_bad <- function(formula, data, family = glmmTMB::nbinom2()) {
    n <<- n + 1; if (n == 4) stop("fail") else glmmTMB_fit(formula, data, family)
  }
  r <- mediate(d, "y", "x", "m", trend_df = 0L, B = 10, fitter = one_bad)
  expect_identical(r$B_failed, 1L)
  expect_identical(r$B_ok, 9L)
  expect_identical(r$flag, "ok")
  expect_false(anyNA(r$ci$indirect))
  expect_false(anyNA(r$ci$prop))
})

test_that("point estimates match the separate fits and prop_mediated is indirect / c_total", {
  d <- sim_mediation()
  r <- mediate(d, "y", "x", "m", trend_df = 0L, B = 1)
  fa <- glmmTMB_fit(m ~ x + (1 | unit_id), d, stats::gaussian())
  fb <- glmmTMB_fit(y ~ x + m + offset(log_pop) + (1 | unit_id), d)
  ft <- glmmTMB_fit(y ~ x + offset(log_pop) + (1 | unit_id), d)
  expect_equal(r$a, glmmTMB::fixef(fa)$cond[["x"]], tolerance = 1e-6)
  expect_equal(r$b, glmmTMB::fixef(fb)$cond[["m"]], tolerance = 1e-6)
  expect_equal(r$c_total, glmmTMB::fixef(ft)$cond[["x"]], tolerance = 1e-6)
  expect_equal(r$c_direct, glmmTMB::fixef(fb)$cond[["x"]], tolerance = 1e-6)
  expect_equal(r$indirect, r$a * r$b)
  expect_equal(r$prop_mediated, r$indirect / r$c_total)
})

test_that("mediate is reproducible by seed and leaves the caller's RNG untouched", {
  d <- sim_mediation()
  set.seed(99); before <- .Random.seed
  r1 <- mediate(d, "y", "x", "m", trend_df = 0L, B = 3, seed = 5)
  expect_identical(.Random.seed, before)
  r2 <- mediate(d, "y", "x", "m", trend_df = 0L, B = 3, seed = 5)
  expect_identical(r1$ci, r2$ci)
  b1 <- bootstrap_units(d, seed = 3); b2 <- bootstrap_units(d, seed = 3)
  expect_identical(b1, b2)
  expect_identical(.Random.seed, before)
})

test_that("bootstrap_units keeps whole units and their rows", {
  d <- sim_mediation()
  ids <- bootstrap_units(d, seed = 3)
  expect_true(is.factor(ids$unit_id))
  expect_equal(nrow(ids), nrow(d))                             # balanced panel: same row count
  src <- sub("_[0-9]+$", "", as.character(ids$unit_id))
  expect_true(all(src %in% as.character(d$unit_id)))
  # every pseudo-unit carries exactly the rows of its source unit
  k <- as.character(ids$unit_id)[1]
  expect_equal(ids[unit_id == k]$y, d[unit_id == sub("_[0-9]+$", "", k)]$y)
})

# ---- ruling P14 (R2, R3) ----

test_that("per-resample estimates are kept; CIs are their percentiles; Wald from the point fits", {
  d <- sim_mediation()
  r <- mediate(d, "y", "x", "m", trend_df = 0L, B = 3)
  expect_equal(nrow(r$boot), 3L)
  expect_true(all(c("i", "a", "b", "c_direct", "c_total", "indirect", "prop", "error") %in% names(r$boot)))
  expect_equal(r$boot$indirect, r$boot$a * r$boot$b)
  expect_equal(r$boot$prop, r$boot$indirect / r$boot$c_total)
  q <- function(v) stats::quantile(v, c(0.025, 0.975), names = FALSE)
  expect_equal(r$ci$indirect, q(r$boot$indirect))
  expect_equal(r$ci$c_total, q(r$boot$c_total))
  expect_identical(r$wald$path, c("a", "b", "c_direct", "c_total"))
  expect_equal(r$wald$est, c(r$a, r$b, r$c_direct, r$c_total))
  expect_true(all(r$wald$se > 0 & r$wald$lo < r$wald$est & r$wald$est < r$wald$hi))
  fb <- glmmTMB_fit(y ~ x + m + offset(log_pop) + (1 | unit_id), d)
  expect_equal(r$wald[path == "b"]$se, summary(fb)$coefficients$cond["m", 2], tolerance = 1e-6)
  expect_true(r$prop_flag %in% c("ok", "total_effect_ci_includes_0", "opposite_signs"))
  expect_identical(r$B_prop_nonfinite, 0L)
})

test_that("proportion CI is withheld when the total effect CI includes 0, signs differ, or a ratio is non-finite", {
  bo <- function(ct, ind = rep(0.2, length(ct))) data.table::data.table(indirect = ind, c_total = ct, prop = ind / ct)
  q <- function(v) stats::quantile(v, c(0.025, 0.975), names = FALSE)
  ok <- .prop_ci(0.2, 0.3, bo(seq(0.2, 0.4, length.out = 20)))
  expect_identical(ok$prop_flag, "ok")
  expect_equal(ok$ci, q(0.2 / seq(0.2, 0.4, length.out = 20)))
  inc <- .prop_ci(0.2, 0.05, bo(seq(-0.1, 0.2, length.out = 20)))
  expect_identical(inc$prop_flag, "total_effect_ci_includes_0")
  expect_true(all(is.na(inc$ci)))
  opp <- .prop_ci(0.2, -0.3, bo(seq(-0.4, -0.2, length.out = 20)))
  expect_identical(opp$prop_flag, "opposite_signs")
  expect_true(all(is.na(opp$ci)))
  nf <- bo(c(seq(0.2, 0.4, length.out = 19), 0))               # one resample with c_total = 0
  nf <- .prop_ci(0.2, 0.3, nf, ci_c_total = c(0.1, 0.4))
  expect_identical(nf$prop_flag, "nonfinite_resample_proportion")
  expect_true(all(is.na(nf$ci)))
})

test_that("too many failures: every CI NA, prop_flag not assessed", {
  d <- sim_mediation()
  n <- 0
  flaky <- function(formula, data, family = glmmTMB::nbinom2()) {
    n <<- n + 1; if (n > 3) stop("fail") else glmmTMB_fit(formula, data, family)
  }
  r <- mediate(d, "y", "x", "m", trend_df = 0L, B = 5, fitter = flaky)
  expect_true(all(is.na(unlist(r$ci))))
  expect_identical(r$prop_flag, "not_assessed")
  expect_false(is.na(r$prop_mediated))                        # point estimate kept
  expect_identical(r$fail_messages, "mediate: a-path fit failed: fail")
  expect_true(all(r$boot$error == "mediate: a-path fit failed: fail"))
})

test_that("a-path fitter messages are recorded, not printed", {
  d <- sim_mediation()
  talky <- function(formula, data, family = glmmTMB::nbinom2()) {
    if (identical(family$family, "gaussian")) message("note from the a-path")
    glmmTMB_fit(formula, data, family)
  }
  expect_no_message(r <- mediate(d, "y", "x", "m", trend_df = 0L, B = 1, fitter = talky))
  expect_identical(r$messages$a, "note from the a-path")
  expect_identical(r$messages$b, character())
})

test_that("parallel bootstrap (PSOCK, cores = 2) reproduces the serial result exactly", {
  d <- sim_mediation()
  s <- mediate(d, "y", "x", "m", trend_df = 0L, B = 4, seed = 9)
  p <- mediate(d, "y", "x", "m", trend_df = 0L, B = 4, seed = 9, cores = 2L)
  expect_identical(p$boot, s$boot)
  expect_identical(p$ci, s$ci)
  expect_identical(p$cores, 2L)
  closure <- local({ k <- 0; function(formula, data, family = glmmTMB::nbinom2()) { k <<- k + 1; glmmTMB_fit(formula, data, family) } })
  expect_error(mediate(d, "y", "x", "m", trend_df = 0L, B = 2, fitter = closure, cores = 2L), "closure")
})
