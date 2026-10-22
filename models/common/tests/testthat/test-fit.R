test_that("fit_nb recovers a known ENSO coefficient with random slopes", {
  d <- sim_panel()
  s <- nb_spec("y", fixed = "x", slopes = "x")
  f <- fit_nb(s, d)
  expect_true(f$re_used %in% c("us", "diag", "int"))
  est <- glmmTMB::fixef(f$model)$cond[["x"]]
  expect_lt(abs(est - 0.3), 0.1)
  expect_true(isTRUE(f$model$sdr$pdHess))
  irr <- irr_table(f, "x")
  expect_true(irr$lo < exp(0.3) && exp(0.3) < irr$hi)
})

test_that("rows with NA are dropped explicitly and reported, never imputed", {
  d <- sim_panel()
  d[unit_id == "U01" & year == 2010, x := NA]
  d[unit_id == "U02" & year == 2011, y := NA]
  f <- fit_nb(nb_spec("y", fixed = "x"), d)
  expect_equal(f$n, nrow(d) - 2L)
  expect_setequal(paste(f$dropped$unit_id, f$dropped$year, f$dropped$variable),
                  c("U01 2010 x", "U02 2011 y"))
})

test_that("non-convergence falls back us -> diag -> int and records it", {
  d <- sim_panel()
  calls <- character()
  fake <- function(formula, data) {
    re <- if (grepl("diag(", deparse1(formula), fixed = TRUE)) "diag" else if (grepl("x | unit_id", deparse1(formula), fixed = TRUE)) "us" else "int"
    calls <<- c(calls, re)
    if (re == "us") stop("simulated non-convergence")
    glmmTMB_fit(formula, data)
  }
  f <- fit_nb(nb_spec("y", fixed = "x", slopes = "x"), d, fitter = fake)
  expect_identical(f$re_used, "diag")
  expect_identical(f$attempts, c("us", "diag"))
})

test_that("all structures failing is an error, not a silent return", {
  d <- sim_panel()
  bad <- function(formula, data) stop("nope")
  expect_error(fit_nb(nb_spec("y", fixed = "x", slopes = "x"), d, fitter = bad), "no structure converged")
})

test_that("spec_formula builds trend, offset and random-effect terms", {
  s <- nb_spec("cases", fixed = c("oni_jjas", "log_aber"), slopes = c("oni_jjas"))
  f <- deparse1(spec_formula(s))
  expect_match(f, "splines::ns(year, df = 4)", fixed = TRUE)
  expect_match(f, "offset(log_pop)", fixed = TRUE)
  expect_match(f, "(1 + oni_jjas | unit_id)", fixed = TRUE)
  expect_match(deparse1(spec_formula(s, "diag")), "diag(1 + oni_jjas | unit_id)", fixed = TRUE)
  expect_match(deparse1(spec_formula(s, "int")), "(1 | unit_id)", fixed = TRUE)
})

test_that("a non-convergent return (pdHess FALSE) triggers fallback", {
  d <- sim_panel()
  fake <- function(formula, data) {
    m <- glmmTMB_fit(formula, data)
    if (!grepl("diag(", deparse1(formula), fixed = TRUE) && grepl("x | unit_id", deparse1(formula), fixed = TRUE)) m$sdr$pdHess <- FALSE
    m
  }
  f <- fit_nb(nb_spec("y", fixed = "x", slopes = "x"), d, fitter = fake)
  expect_identical(f$attempts, c("us", "diag"))
  expect_identical(f$re_used, "diag")
})

test_that("fallback never climbs to a more complex structure", {
  d <- sim_panel()
  seen <- character()
  fail_diag <- function(formula, data) {
    txt <- deparse1(formula)
    seen <<- c(seen, txt)
    if (grepl("diag(", txt, fixed = TRUE)) stop("no")
    glmmTMB_fit(formula, data)
  }
  f <- fit_nb(nb_spec("y", fixed = "x", slopes = "x", re = "diag"), d, fitter = fail_diag)
  expect_identical(f$attempts, c("diag", "int"))
  expect_identical(f$re_used, "int")
  seen <- character()
  always_fail <- function(formula, data) { seen <<- c(seen, deparse1(formula)); stop("no") }
  expect_error(fit_nb(nb_spec("y", fixed = "x", slopes = "x", re = "int"), d, fitter = always_fail),
               "no structure converged")
  expect_length(seen, 1L)
  expect_false(any(grepl("diag(", seen, fixed = TRUE)))
})

test_that("an invalid re errors up front", {
  d <- sim_panel()
  expect_error(fit_nb(nb_spec("y", fixed = "x", slopes = "x", re = "bogus"), d))
})

test_that("no slopes means a single intercept-only attempt", {
  d <- sim_panel()
  n <- 0L
  counting <- function(formula, data) { n <<- n + 1L; glmmTMB_fit(formula, data) }
  f <- fit_nb(nb_spec("y", fixed = "x"), d, fitter = counting)
  expect_identical(f$attempts, "int")
  expect_identical(f$re_used, "int")
  expect_equal(n, 1L)
})

test_that("complete_rows validates columns and treats non-finite as missing", {
  d <- sim_panel()
  expect_error(complete_rows(d, c("x", "nope")), "nope")
  d[unit_id == "U03" & year == 2005, x := -Inf]
  d[unit_id == "U04" & year == 2006, `:=`(x = NA_real_, y = NA_real_)]
  cr <- complete_rows(d, c("y", "x"))
  expect_equal(nrow(cr$data), nrow(d) - 2L)
  expect_setequal(paste(cr$dropped$unit_id, cr$dropped$year, cr$dropped$variable),
                  c("U03 2005 x", "U04 2006 y"))
  expect_true(all(is.finite(cr$data$x)))
})

test_that("fit_nb errors clearly when no rows remain", {
  d <- sim_panel()
  d[, x := NA_real_]
  expect_error(fit_nb(nb_spec("y", fixed = "x"), d), "no complete rows.*dropped")
})

test_that("spec_formula handles empty fixed, empty slopes and trend_df = 0", {
  s <- nb_spec("y", fixed = character(), trend_df = 0L)
  f <- deparse1(spec_formula(s))
  expect_identical(f, "y ~ offset(log_pop) + (1 | unit_id)")
  expect_identical(deparse1(spec_formula(s, "diag")), f)
})

test_that("irr_table errors on a missing term", {
  f <- fit_nb(nb_spec("y", fixed = "x"), sim_panel())
  expect_error(irr_table(f, c("x", "zzz")), "zzz")
})

test_that("a fit with pdHess TRUE but non-finite cov.fixed is not converged and falls back (P17b)", {
  d <- sim_panel()
  calls <- character()
  fake <- function(formula, data) {
    re <- if (grepl("diag(", deparse1(formula), fixed = TRUE)) "diag" else if (grepl("x | unit_id", deparse1(formula), fixed = TRUE)) "us" else "int"
    calls <<- c(calls, re)
    m <- glmmTMB_fit(formula, data)
    if (re == "us") m$sdr$cov.fixed[] <- NaN
    m
  }
  f <- fit_nb(nb_spec("y", fixed = "x", slopes = "x"), d, fitter = fake)
  expect_identical(f$attempts, c("us", "diag"))
  expect_identical(f$re_used, "diag")
  bad <- glmmTMB_fit(y ~ x + offset(log_pop) + (1 | unit_id), d)
  expect_true(.converged(bad))
  bad$sdr$cov.fixed[] <- NaN
  expect_true(isTRUE(bad$sdr$pdHess))
  expect_false(.converged(bad))
})
