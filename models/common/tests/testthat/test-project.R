test_that("projection excess is zero when scenarios match and flags extrapolation", {
  d <- sim_panel()
  f <- fit_nb(nb_spec("y", fixed = "x"), d)
  nd <- d[year == 2025]
  p0 <- project(f, nd, nd, "x", n_draws = 200)
  expect_equal(max(abs(p0$by_row$excess_mean)), 0)
  nd2 <- data.table::copy(nd); nd2[, x := max(d$x) + 1]
  cf <- data.table::copy(nd); cf[, x := 0]
  p <- project(f, nd2, cf, "x", n_draws = 200)
  expect_true(p$extrapolation)
  expect_identical(p$extrapolated_vars, "x")
  expect_true(all(p$by_row$excess_lo <= p$by_row$excess_hi))
  expect_equal(nrow(p$total), 1L)
})

test_that("results.json follows the results schema", {
  path <- tempfile(fileext = ".json")
  write_results(list(`A.test.irr` = res_entry(1.123, fmt_ci(1.123, 1.03, 1.21), "models/A/test.R", "test IRR")), path)
  r <- jsonlite::fromJSON(path, simplifyVector = FALSE)
  e <- r[["A.test.irr"]]
  expect_setequal(names(e), c("value", "display", "script", "description"))
  expect_identical(e$display, "1.12 (95% CI 1.03\u20131.21)")
  expect_identical(fmt_int(12345), "12,345")
})

# ---- additional checks: joint draws, totals, intervals, NA rows, RNG, writer contract ----

proj_fixture <- function() {
  d <- sim_panel()
  f <- fit_nb(nb_spec("y", fixed = "x", slopes = "x"), d)
  nd <- d[year %in% c(2024, 2025)]
  cf <- data.table::copy(nd); cf[, x := 0]
  list(d = d, f = f, nd = nd, cf = cf)
}

test_that("both scenarios share ONE joint (beta, b) draw set; excess and totals are per-draw", {
  s <- proj_fixture()
  p <- project(s$f, s$nd, s$cf, "x", n_draws = 300, seed = 7)
  pd <- draw_params(s$f, 300, seed = 7)
  expect_false(is.null(pd$re_draws))                           # random effects drawn jointly (P9)
  mo <- draw_mu(s$f, s$nd, 300, beta_draws = pd$beta_draws, re_draws = pd$re_draws)
  mc <- draw_mu(s$f, s$cf, 300, beta_draws = pd$beta_draws, re_draws = pd$re_draws)
  ex <- mo - mc
  q <- function(v) stats::quantile(v, c(0.025, 0.975), names = FALSE)
  expect_equal(p$by_row$mu, rowMeans(mo))
  expect_equal(p$by_row$mu_cf, rowMeans(mc))
  expect_equal(p$by_row$excess_mean, rowMeans(ex))
  expect_equal(p$by_row$excess_lo, apply(ex, 1, q)[1, ])
  expect_equal(p$by_row$excess_hi, apply(ex, 1, q)[2, ])
  # totals: sum over units within a draw, then quantiles (not a sum of row quantiles)
  for (yr in c(2024L, 2025L)) {
    tot <- colSums(ex[s$nd$year == yr, ])
    r <- p$total[year == yr]
    expect_equal(r$excess_mean, mean(tot))
    expect_equal(c(r$excess_lo, r$excess_hi), q(tot))
    expect_equal(r$n_rows, sum(s$nd$year == yr))
  }
  expect_equal(nrow(p$total), 2L)
  # prediction interval from NB2 draws under the observed scenario, separate from the excess interval
  yd <- draw_y(s$f, mo, seed = 7 + 100000L)
  expect_equal(p$by_row$y_lo, apply(yd, 1, q)[1, ])
  expect_equal(p$by_row$y_hi, apply(yd, 1, q)[2, ])
  expect_false(any(grepl("95", names(p$by_row))))
})

test_that("shared draws make the excess interval narrower than independent draws would", {
  s <- proj_fixture()
  p <- project(s$f, s$nd, s$cf, "x", n_draws = 400, seed = 3)
  mo <- draw_mu(s$f, s$nd, 400, seed = 3)
  mc <- draw_mu(s$f, s$cf, 400, seed = 999)                    # independent draws: wrong
  indep <- apply(mo - mc, 1, function(v) diff(stats::quantile(v, c(0.025, 0.975))))
  expect_lt(stats::median((p$by_row$excess_hi - p$by_row$excess_lo) / indep), 1)
})

test_that("exposures inside the training range are not flagged; counterfactual extrapolation is", {
  s <- proj_fixture()
  p <- project(s$f, s$nd, s$cf, "x", n_draws = 50)
  expect_false(p$extrapolation)
  expect_identical(p$extrapolated_vars, character())
  cf2 <- data.table::copy(s$cf); cf2[, x := min(s$d$x) - 1]
  p2 <- project(s$f, s$nd, cf2, "x", n_draws = 50)
  expect_true(p2$extrapolation)
  expect_identical(p2$extrapolated_vars, "x")
  det <- p2$extrapolation_detail
  expect_true(det[scenario == "counterfactual"]$outside)
  expect_false(det[scenario == "observed"]$outside)
  expect_equal(det$train_max[1], max(s$f$data$x))
})

test_that("a row missing a covariate in either scenario is dropped from both and reported", {
  s <- proj_fixture()
  s$cf[unit_id == "U03" & year == 2025, x := NA]
  s$nd[unit_id == "U05" & year == 2024, log_pop := NaN]
  p <- project(s$f, s$nd, s$cf, "x", n_draws = 50)
  expect_equal(nrow(p$by_row), nrow(s$nd) - 2L)
  expect_false(any(paste(p$by_row$unit_id, p$by_row$year) %in% c("U03 2025", "U05 2024")))
  expect_setequal(paste(p$dropped$unit_id, p$dropped$year, p$dropped$scenario, p$dropped$variable),
                  c("U03 2025 counterfactual x", "U05 2024 observed log_pop"))
  expect_false(anyNA(p$by_row))
  expect_equal(p$total[year == 2025]$n_rows, sum(s$nd$year == 2025) - 1L)
})

test_that("mismatched scenarios and unknown exposure variables are errors", {
  s <- proj_fixture()
  expect_error(project(s$f, s$nd, s$cf[-1], "x", n_draws = 10), "same rows")
  expect_error(project(s$f, s$nd, s$cf, "zz", n_draws = 10), "zz")
})

test_that("project is reproducible by seed and leaves the caller's RNG untouched", {
  s <- proj_fixture()
  set.seed(42); before <- .Random.seed
  p1 <- project(s$f, s$nd, s$cf, "x", n_draws = 50, seed = 11)
  expect_identical(.Random.seed, before)
  p2 <- project(s$f, s$nd, s$cf, "x", n_draws = 50, seed = 11)
  expect_identical(p1$by_row, p2$by_row)
})

test_that("write_results sorts keys bytewise, writes UTF-8, NA value as null, and validates", {
  path <- tempfile(fileext = ".json")
  e <- list(`b.k` = res_entry(NA_real_, "not estimable", "s.R", "d"),
            `B.k` = res_entry(0.5, fmt_pct(0.5), "s.R", "d"),
            `a.k` = res_entry(-0.001, fmt_num(-0.001, 2), "s.R", "\u2264 caf\u00E9"))
  expect_identical(write_results(e, path), path)
  txt <- readLines(path, encoding = "UTF-8", warn = FALSE)
  keys <- sub('^  "([^"]+)": \\{$', "\\1", grep('^  "[^"]+": \\{$', txt, value = TRUE))
  expect_identical(keys, c("B.k", "a.k", "b.k"))              # C-locale order, not collation order
  r <- jsonlite::fromJSON(path, simplifyVector = FALSE)
  expect_null(r[["b.k"]]$value)
  expect_identical(r[["a.k"]]$display, "0.00")                # no "-0.00"
  expect_identical(r[["a.k"]]$description, "\u2264 caf\u00E9")
  expect_identical(r[["B.k"]]$display, "50.0%")
  raw <- readBin(path, "raw", file.size(path))
  expect_true(length(grepRaw(as.raw(c(0xe2, 0x89, 0xa4)), raw)) > 0)   # UTF-8 bytes of U+2264
  expect_error(write_results(list(`bad key` = e[[1]]), path), "bad key")
  expect_error(write_results(list(`A.x` = list(value = 1, display = "1")), path), "exactly the fields")
  expect_error(res_entry(1, NA_character_, "s.R", "d"), "display")
  expect_error(write_results(list(e[[1]]), path), "unique names")
})

test_that("formatters", {
  expect_identical(fmt_ci(c(1.123, 0.5), c(1.03, 0.4), c(1.21, 0.6)),
                   c("1.12 (95% CI 1.03\u20131.21)", "0.50 (95% CI 0.40\u20130.60)"))
  expect_identical(fmt_ci(0.0123, -0.0004, 0.0456, digits = 3), "0.012 (95% CI 0.000\u20130.046)")
  expect_true(is.na(fmt_ci(1, NA, 2)))
  expect_identical(fmt_int(c(1234567, 999, 0, -1234.6)), c("1,234,567", "999", "0", "\u22121,235"))
  expect_identical(fmt_int(3.2e9), "3,200,000,000")
  expect_identical(fmt_num(c(3.14159, -2), 3), c("3.142", "\u22122.000"))
  expect_identical(fmt_pct(0.1234), "12.3%")
  expect_identical(fmt_pct(0.86649, 2), "86.65%")
  expect_true(is.na(fmt_pct(NA)))
})

# ---- ruling P14 minors ----

test_that("trend extrapolation is flagged separately for years beyond the training years", {
  s <- proj_fixture()
  f <- fit_nb(nb_spec("y", fixed = "x"), s$d[year <= 2023])
  nd <- s$d[year %in% c(2023, 2025)]
  cf <- data.table::copy(nd); cf[, x := 0]
  p <- project(f, nd, cf, "x", n_draws = 20)
  expect_true(p$trend_extrapolation)
  expect_false("year" %in% p$extrapolated_vars)
  expect_equal(p$trend_detail$train_min, 2002)
  expect_equal(p$trend_detail$train_max, 2023)
  expect_equal(p$trend_detail$new_max, 2025)
  expect_identical(p$trend_detail$years_outside, "2025")
  p_in <- project(f, nd[year == 2023], cf[year == 2023], "x", n_draws = 20)
  expect_false(p_in$trend_extrapolation)
  f0 <- fit_nb(nb_spec("y", fixed = "x", trend_df = 0L), s$d[year <= 2023])
  expect_false(project(f0, nd, cf, "x", n_draws = 20)$trend_extrapolation)   # no trend term
})

test_that("the exposure range check allows a 1e-8 tolerance", {
  s <- proj_fixture()
  nd <- data.table::copy(s$nd); nd[, x := max(s$f$data$x) + 1e-10]
  expect_false(project(s$f, nd, s$cf, "x", n_draws = 20)$extrapolation)
  nd[, x := max(s$f$data$x) + 1e-6]
  expect_true(project(s$f, nd, s$cf, "x", n_draws = 20)$extrapolation)
})
