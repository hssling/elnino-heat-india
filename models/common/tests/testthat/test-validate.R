test_that("linear_predictor reproduces glmmTMB predictions on training rows", {
  d <- sim_panel()
  f <- fit_nb(nb_spec("y", fixed = "x", slopes = "x"), d)
  ref <- predict(f$model, newdata = f$data, type = "link")
  expect_equal(linear_predictor(f, f$data), as.numeric(ref), tolerance = 1e-6)
})

test_that("oos_metrics matches hand computation", {
  y <- c(0, 10, NA); mu <- c(1, 8, 5)
  m <- oos_metrics(y, mu, theta = 2, lo = c(0, 9, 0), hi = c(3, 20, 9))
  expect_equal(m$male, mean(abs(log1p(c(0, 10)) - log1p(c(1, 8)))))
  expect_equal(m$log_score, -mean(dnbinom(c(0, 10), size = 2, mu = c(1, 8), log = TRUE)))
  expect_equal(m$coverage95, 1)
  expect_equal(m$n, 2L)
})

test_that("LOEO never trains on held-out years and scores only them", {
  d <- sim_panel()
  splits <- loeo_splits(data.table::data.table(fold_id = c(1, 1, 2), year = c(2003, 2004, 2015), label = "x"))
  seen <- list()
  spy <- function(formula, data) { seen[[length(seen) + 1]] <<- sort(unique(data$year)); glmmTMB_fit(formula, data) }
  cv <- cv_predict(nb_spec("y", fixed = "x"), d, splits, n_draws = 50, fitter = spy)
  expect_false(any(c(2003, 2004) %in% seen[[1]]))
  expect_false(2015 %in% seen[[2]])
  expect_setequal(unique(cv$pred[split_id == "1"]$year), c(2003, 2004))
  expect_true(all(cv$pred$lo <= cv$pred$hi))
})

test_that("rolling-origin trains only on the past", {
  s <- rolling_splits(2002:2025, first_test = 2015)
  expect_length(s, 11)
  expect_identical(s[[1]]$test_years, 2015L)
  expect_identical(s[[1]]$train_max, 2014L)
})

test_that("nested models are scored on identical rows", {
  d <- sim_panel()
  d[unit_id == "U03" & year == 2015, x_lag1 := NA]          # only model C uses x_lag1
  specs <- list(B = nb_spec("y", fixed = character()), C = nb_spec("y", fixed = c("x", "x_lag1")))
  cmp <- compare_models(specs, d, loeo_splits(data.table::data.table(fold_id = 1, year = 2015, label = "x")), n_draws = 50)
  ns <- cmp$per_split[, .N, by = model]$N
  expect_identical(ns[1], ns[2])
  expect_false(any(cmp$per_split$unit_id == "U03" & cmp$per_split$year == 2015))
})

test_that("too many failed refits gives NA metrics with a flag", {
  d <- sim_panel()
  bad <- function(formula, data) stop("nope")
  cmp <- compare_models(list(C = nb_spec("y", fixed = "x")), d, rolling_splits(2002:2025, 2020), n_draws = 10, fitter = bad)
  expect_true(is.na(cmp$summary$male))
  expect_identical(cmp$summary$flag, "too_many_failed_fits")
})

test_that("a test unit absent from training is excluded and recorded", {
  d <- sim_panel()
  d <- d[!(unit_id == "U05" & year != 2015)]                # U05 exists only in the test year
  cv <- cv_predict(nb_spec("y", fixed = "x"), d, loeo_splits(data.table::data.table(fold_id = 1, year = 2015, label = "x")), n_draws = 20)
  expect_true(any(cv$excluded$unit_id == "U05" & cv$excluded$reason == "unit_not_in_training"))
  expect_false(any(cv$pred$unit_id == "U05"))
})

# ---- additional tests beyond the brief ----

test_that("draw_mu reuses a supplied beta_draws matrix exactly (ruling P1)", {
  d <- sim_panel()
  f <- fit_nb(nb_spec("y", fixed = "x", slopes = "x"), d)
  nd <- f$data[year %in% 2010:2012]
  B <- MASS::mvrnorm(25, glmmTMB::fixef(f$model)$cond, stats::vcov(f$model)$cond)
  m1 <- draw_mu(f, nd, n_draws = 25, seed = 1, beta_draws = B, re_uncertainty = FALSE)
  m2 <- draw_mu(f, nd, n_draws = 25, seed = 999, beta_draws = B, re_uncertainty = FALSE)
  expect_identical(m1, m2)
  expect_identical(dim(m1), c(nrow(nd), 25L))
  # column k equals exp(linear_predictor) at the k-th beta draw
  expect_equal(m1[, 3], exp(linear_predictor(f, nd, beta = B[3, ])), tolerance = 1e-10)
  expect_error(draw_mu(f, nd, n_draws = 10, seed = 1, beta_draws = B, re_uncertainty = FALSE), "beta_draws")
  # with RE uncertainty on, beta_draws must come with re_draws (no unseeded RE draws)
  expect_error(draw_mu(f, nd, n_draws = 25, seed = 1, beta_draws = B), "re_draws")
})

test_that("shared beta and RE draws give identical mu and reproduce the seeded draw (P1, P7)", {
  d <- sim_panel()
  f <- fit_nb(nb_spec("y", fixed = "x", slopes = "x"), d)
  nd <- f$data[year %in% 2010:2012]
  p <- draw_params(f, n_draws = 25, seed = 4)
  expect_identical(dim(p$re_draws), c(20L, 2L, 25L))
  m1 <- draw_mu(f, nd, beta_draws = p$beta_draws, re_draws = p$re_draws)
  m2 <- draw_mu(f, nd, beta_draws = p$beta_draws, re_draws = p$re_draws)
  expect_identical(m1, m2)
  expect_identical(m1, draw_mu(f, nd, n_draws = 25, seed = 4))
  nd2 <- data.table::copy(nd)[, x := x + 1]                 # a second scenario on the same draws
  m3 <- draw_mu(f, nd2, beta_draws = p$beta_draws, re_draws = p$re_draws)
  expect_identical(m3, draw_mu(f, nd2, n_draws = 25, seed = 4))
})

# Reference joint covariance of (beta, b), computed independently of predict.R (ruling P9)
ref_joint <- function(f) {
  obj <- f$model$obj
  Q <- TMB::sdreport(obj, par.fixed = f$model$fit$par, getJointPrecision = TRUE)$jointPrecision
  nm <- rownames(Q)
  list(J = solve(as.matrix(Q)), ib = which(nm == "beta"), ibb = which(nm == "b"))
}

for (re_struct in c("us", "diag", "int")) {
  test_that(sprintf("joint draws map b onto (unit, term) correctly: %s structure (P9)", re_struct), {
    d <- sim_panel()
    f <- fit_nb(nb_spec("y", fixed = "x", slopes = "x", re = re_struct), d)
    expect_identical(f$re_used, re_struct)
    n <- 6000L
    p <- draw_params(f, n_draws = n, seed = 2)
    r <- glmmTMB::ranef(f$model, condVar = TRUE)$cond$unit_id
    modes <- as.matrix(r)
    K <- ncol(modes)
    expect_identical(dimnames(p$re_draws)[1:2], dimnames(modes))
    expect_identical(dim(p$re_draws), c(20L, K, n))
    # glmmTMB's own (unit, term) labelling of modes and conditional variances, checked against the draws
    cv <- attr(r, "condVar")
    v_ref <- t(vapply(seq_len(nrow(modes)), function(u) cv[cbind(seq_len(K), seq_len(K), u)], numeric(K)))
    if (K == 1L) v_ref <- matrix(v_ref, ncol = 1)
    m_draw <- apply(p$re_draws, c(1, 2), mean)
    v_draw <- apply(p$re_draws, c(1, 2), stats::var)
    expect_true(all(abs(m_draw - modes) < 5 * sqrt(v_ref / n)))
    expect_true(all(abs(v_draw / v_ref - 1) < 0.1))
    # fixed effects: centred on fixef with the vcov variances
    b <- glmmTMB::fixef(f$model)$cond
    expect_equal(colMeans(p$beta_draws), b, tolerance = 0.01)
    expect_equal(apply(p$beta_draws, 2, stats::var), diag(stats::vcov(f$model)$cond), tolerance = 0.1)
  })
}

test_that("draws reproduce the joint (beta, b) covariance, including Cov(beta, b_u) (P9)", {
  d <- sim_panel()
  f <- fit_nb(nb_spec("y", fixed = "x", slopes = "x"), d[year <= 2018])
  expect_identical(f$re_used, "us")
  ref <- ref_joint(f)
  n <- 20000
  p <- draw_params(f, n_draws = n, seed = 11)
  D <- cbind(p$beta_draws[, "(Intercept)"], p$beta_draws[, "x"],
             p$re_draws["U01", "(Intercept)", ], p$re_draws["U01", "x", ], p$re_draws["U02", "(Intercept)", ])
  idx <- c(ref$ib[1:2], ref$ibb[1:3])                         # b is unit-major: U01 int, U01 x, U02 int
  Jsub <- ref$J[idx, idx]
  se <- sqrt((outer(diag(Jsub), diag(Jsub)) + Jsub^2) / n)
  expect_true(all(abs(stats::cov(D) - Jsub) < 5 * se))
  # the test discriminates: Cov(beta0, b_U01) is far from 0, so independent draws would fail it
  expect_gt(abs(Jsub[1, 3]), 10 * se[1, 3])
})

test_that("mu draws carry the joint variance of the linear predictor; re_uncertainty = FALSE is fixed-only (P9)", {
  d <- sim_panel()
  f <- fit_nb(nb_spec("y", fixed = "x", slopes = "x"), d[year <= 2018])
  ref <- ref_joint(f)
  nd <- d[year >= 2019]
  X <- .fixed_design(f, nd)$X
  units <- match(as.character(nd$unit_id), rownames(as.matrix(glmmTMB::ranef(f$model)$cond$unit_id)))
  sd_joint <- vapply(seq_len(nrow(nd)), function(r) {
    a <- numeric(nrow(ref$J)); a[ref$ib] <- X[r, ]
    a[ref$ibb[(units[r] - 1L) * 2L + 1:2]] <- c(1, nd$x[r])
    sqrt(drop(a %*% ref$J %*% a))
  }, numeric(1))
  V <- stats::vcov(f$model)$cond
  sd_fixed <- unname(sqrt(rowSums((X %*% V) * X)))
  m_joint <- draw_mu(f, nd, n_draws = 4000, seed = 7)
  m_fixed <- draw_mu(f, nd, n_draws = 4000, seed = 7, re_uncertainty = FALSE)
  expect_equal(apply(log(m_joint), 1, stats::sd), sd_joint, tolerance = 0.06)
  expect_equal(apply(log(m_fixed), 1, stats::sd), sd_fixed, tolerance = 0.06)
  # independent beta + marginal b draws would overstate it: the joint sd is below that sum
  v_b <- vapply(seq_len(nrow(nd)), function(r) {
    i <- ref$ibb[(units[r] - 1L) * 2L + 1:2]; z <- c(1, nd$x[r])
    drop(z %*% ref$J[i, i] %*% z)
  }, numeric(1))
  expect_lt(stats::median(sd_joint / sqrt(sd_fixed^2 + v_b)), 0.98)
})

test_that("joint draws error clearly when the joint precision is unavailable (P9)", {
  d <- sim_panel()
  f <- fit_nb(nb_spec("y", fixed = "x"), d)
  old <- get(".joint_precision", envir = globalenv())
  assign(".joint_precision", function(fit) NULL, envir = globalenv())
  res <- tryCatch(draw_params(f, n_draws = 5, seed = 1), error = function(e) e,
                  finally = assign(".joint_precision", old, envir = globalenv()))
  expect_s3_class(res, "error")
  expect_match(conditionMessage(res), "joint precision")
  # fixed-only draws do not need it
  assign(".joint_precision", function(fit) NULL, envir = globalenv())
  res <- tryCatch(draw_params(f, n_draws = 5, seed = 1, re_uncertainty = FALSE), error = function(e) e,
                  finally = assign(".joint_precision", old, envir = globalenv()))
  expect_false(inherits(res, "error"))
})

test_that("a failure while drawing is recorded as a failed split, not an abort (P9)", {
  d <- sim_panel()
  old <- get("draw_params", envir = globalenv())
  assign("draw_params", function(...) stop("boom-draw"), envir = globalenv())
  cv <- tryCatch(cv_predict(nb_spec("y", fixed = "x"), d, rolling_splits(2002:2025, 2024), n_draws = 5),
                 finally = assign("draw_params", old, envir = globalenv()))
  expect_identical(cv$failed, c("2024", "2025"))
  expect_true(all(grepl("boom-draw", cv$fail_reasons$error)))
  expect_identical(nrow(cv$pred), 0L)
})

test_that("draw_mu is reproducible under a seed and centred on the point prediction", {
  d <- sim_panel()
  f <- fit_nb(nb_spec("y", fixed = "x"), d)
  nd <- f$data[year == 2015]
  a <- draw_mu(f, nd, n_draws = 400, seed = 7)
  b <- draw_mu(f, nd, n_draws = 400, seed = 7)
  expect_identical(a, b)
  pt <- exp(linear_predictor(f, nd))
  expect_equal(apply(log(a), 1, stats::median), log(pt), tolerance = 0.05)
  y <- draw_y(f, a, seed = 3)
  expect_identical(dim(y), dim(a))
  expect_true(all(y >= 0 & y == round(y)))
})

test_that("linear_predictor errors on units the model has not seen", {
  d <- sim_panel()
  f <- fit_nb(nb_spec("y", fixed = "x"), d[unit_id != "U07"])
  expect_error(linear_predictor(f, d[unit_id == "U07"]), "U07")
})

test_that("rolling-origin train data never reach the test year or later", {
  d <- sim_panel()
  seen <- list()
  spy <- function(formula, data) { seen[[length(seen) + 1]] <<- range(data$year); glmmTMB_fit(formula, data) }
  cv <- cv_predict(nb_spec("y", fixed = "x"), d, rolling_splits(2002:2025, 2023), n_draws = 20, fitter = spy)
  expect_identical(vapply(seen, `[`, numeric(1), 2), c(2022, 2023, 2024))
  expect_setequal(unique(cv$pred$year), 2023:2025)
})

test_that("splits with no test rows are skipped, not failed, and leave the failure denominator", {
  d <- sim_panel()
  folds <- data.table::data.table(fold_id = c(1, 1, 2, 3), year = c(1997, 1998, 2015, 2019), label = "x")
  cv <- cv_predict(nb_spec("y", fixed = "x"), d, loeo_splits(folds), n_draws = 20)
  expect_identical(cv$skipped, "1")
  expect_length(cv$failed, 0)
  flaky_fitter <- function() {
    calls <- 0L
    function(formula, data) { calls <<- calls + 1L; if (calls == 1L) stop("boom"); glmmTMB_fit(formula, data) }
  }
  skip97 <- loeo_splits(data.table::data.table(fold_id = 0, year = 1997, label = "x"))
  # 9 evaluable + 1 skipped, 1 failure: 1 > 0.9 flags (it would not if the skipped split counted)
  cmp <- compare_models(list(C = nb_spec("y", fixed = "x")), d, c(skip97, rolling_splits(2002:2025, 2017)),
                        n_draws = 10, fitter = flaky_fitter())
  expect_identical(cmp$summary$n_failed_splits, 1L)
  expect_identical(cmp$summary$n_splits, 9L)
  expect_identical(cmp$summary$flag, "too_many_failed_fits")
  expect_true(is.na(cmp$summary$male))
  # 11 evaluable + 1 skipped, 1 failure: 1 <= 1.1 does not flag
  cmp <- compare_models(list(C = nb_spec("y", fixed = "x")), d, c(skip97, rolling_splits(2002:2025, 2015)),
                        n_draws = 10, fitter = flaky_fitter())
  expect_identical(cmp$summary$n_failed_splits, 1L)
  expect_true(is.na(cmp$summary$flag))
  expect_false(is.na(cmp$summary$male))
})

test_that("a split failed by one model is unscored for every model", {
  d <- sim_panel()
  calls <- 0L
  flaky <- function(formula, data) {
    calls <<- calls + 1L
    if (calls == 1L) stop("boom")                           # model B, first rolling split
    glmmTMB_fit(formula, data)
  }
  specs <- list(B = nb_spec("y", fixed = character()), C = nb_spec("y", fixed = "x"))
  cmp <- compare_models(specs, d, rolling_splits(2002:2025, 2014), n_draws = 10, fitter = flaky)
  expect_identical(cmp$summary$n_failed_splits, c(1L, 0L))
  sc <- cmp$per_split[scored == TRUE]
  expect_false(any(sc$split_id == "2014"))
  expect_identical(sc[model == "B", .(split_id, unit_id, year)], sc[model == "C", .(split_id, unit_id, year)])
  expect_identical(cmp$summary$n[1], cmp$summary$n[2])
  expect_identical(cmp$common_n, nrow(sc[model == "B"]))
  # B's failed split leaves C's predicted rows for that split unscored, and that is counted
  expect_identical(cmp$summary$n_unscored_other_model,
                   c(0L, nrow(cmp$per_split[model == "C" & split_id == "2014"])))
  expect_gt(cmp$summary$n_unscored_other_model[2], 0L)
})

test_that("test rows with a missing model variable are excluded with the variable named", {
  d <- sim_panel()
  d[unit_id == "U02" & year == 2015, y := NA]
  cv <- cv_predict(nb_spec("y", fixed = "x"), d, loeo_splits(data.table::data.table(fold_id = 1, year = 2015, label = "x")), n_draws = 20)
  expect_true(any(cv$excluded$unit_id == "U02" & cv$excluded$reason == "missing:y"))
  expect_false(any(cv$pred$unit_id == "U02"))
  expect_false(anyNA(cv$pred$y))
})

# ---- fix round 1: unidentified coefficients (P5), lag buffer (P6), minors (P8) ----

step_panel <- function() {
  d <- sim_panel()
  d[, z := as.numeric(year >= 2016)]                         # programme step: all 0 before 2016
  d[]
}

test_that("a constant-in-training indicator predicts with coefficient 0 and is recorded (P5)", {
  d <- step_panel()
  sp <- rolling_splits(2002:2025, 2015)[1:3]                 # 2015, 2016, 2017
  cv <- cv_predict(nb_spec("y", fixed = c("x", "z")), d, sp, n_draws = 20)
  expect_length(cv$failed, 0)
  expect_false(anyNA(cv$pred$mu)); expect_false(anyNA(cv$pred$lo))
  si <- cv$split_info
  expect_identical(si[split_id == "2015"]$unidentified, "z")
  expect_identical(si[split_id == "2015"]$n_test_rows_nonzero_unidentified, 0L)
  expect_identical(si[split_id == "2016"]$unidentified, "z")      # train <= 2015: z all 0; test z = 1
  expect_identical(si[split_id == "2016"]$n_test_rows_nonzero_unidentified, 20L)
  expect_identical(si[split_id == "2017"]$unidentified, "")
  expect_identical(si[split_id == "2017"]$n_test_rows_nonzero_unidentified, 0L)
  # coefficient 0 == the model without z, fitted on the same training rows
  cv0 <- cv_predict(nb_spec("y", fixed = "x"), d, sp[2], n_draws = 20)
  expect_equal(cv$pred[split_id == "2016"]$mu, cv0$pred$mu, tolerance = 1e-5)
})

test_that("NA coefficients are never used silently (P5)", {
  d <- step_panel()
  f <- fit_nb(nb_spec("y", fixed = c("x", "z")), d[year <= 2015])
  expect_true(is.na(glmmTMB::fixef(f$model)$cond[["z"]]))
  nd <- d[year == 2016]
  expect_error(linear_predictor(f, nd), "unidentified.*z")
  expect_error(draw_mu(f, nd, n_draws = 5, seed = 1), "unidentified.*z")
  lp <- linear_predictor(f, nd, na_coef = "zero")
  expect_false(anyNA(lp))
  b0 <- glmmTMB::fixef(f$model)$cond; b0[["z"]] <- 0
  expect_equal(lp, linear_predictor(f, nd, beta = b0))
  m <- draw_mu(f, nd, n_draws = 30, seed = 1, na_coef = "zero")
  expect_false(anyNA(m))
  p <- draw_params(f, n_draws = 30, seed = 1, na_coef = "zero")
  expect_true(all(p$beta_draws[, "z"] == 0))
})

test_that("rolling-origin over a step indicator completes and compares (P5, real-data style)", {
  d <- step_panel()
  specs <- list(B = nb_spec("y", fixed = "x"), C = nb_spec("y", fixed = c("x", "z")))
  cmp <- compare_models(specs, d, rolling_splits(2002:2025, 2015), n_draws = 20)
  expect_identical(cmp$summary$n_failed_splits, c(0L, 0L))
  expect_false(anyNA(cmp$summary$male))
  expect_identical(nrow(cmp$per_split[model == "C"]), 11L * 20L)
  expect_true(all(c("unidentified", "n_test_rows_nonzero_unidentified") %in% names(cmp$split_info)))
})

lag_panel <- function() {
  d <- sim_panel()
  data.table::setorder(d, unit_id, year)
  d[, log1p_y_lag1 := log1p(data.table::shift(y)), by = unit_id]
  d[]
}

test_that("a lagged-outcome covariate buffers the year after the test fold (P6)", {
  d <- lag_panel()
  sp <- loeo_splits(data.table::data.table(fold_id = 1, year = c(2010, 2011), label = "x"))
  seen <- list()
  spy <- function(formula, data) { seen[[length(seen) + 1]] <<- sort(unique(data$year)); glmmTMB_fit(formula, data) }
  cv_predict(nb_spec("y", fixed = c("x", "log1p_y_lag1")), d, sp, n_draws = 10, fitter = spy)
  cv_predict(nb_spec("y", fixed = "x"), d, sp, n_draws = 10, fitter = spy)
  expect_false(2012 %in% seen[[1]])                          # its lag carries the held-out 2011 outcome
  expect_true(2013 %in% seen[[1]])
  expect_true(2012 %in% seen[[2]])                           # no lag covariate: no buffer
  expect_false(any(2010:2011 %in% seen[[2]]))
  # in a comparison the buffer applies to every model, lagged or not
  seen <- list()
  specs <- list(B = nb_spec("y", fixed = "x"), C = nb_spec("y", fixed = c("x", "log1p_y_lag1")))
  cmp <- compare_models(specs, d, sp, n_draws = 10, fitter = spy)
  expect_length(seen, 2)
  expect_false(any(vapply(seen, function(y) 2012 %in% y, logical(1))))
  expect_true(isTRUE(cmp$lag_buffer))
  seen <- list()
  compare_models(list(A = nb_spec("y", fixed = character()), B = nb_spec("y", fixed = "x")), d, sp,
                 n_draws = 10, fitter = spy)
  expect_true(all(vapply(seen, function(y) 2012 %in% y, logical(1))))
})

test_that("factor fixed effects are refused rather than mis-encoded (P8)", {
  d <- sim_panel()
  d[, grp := factor(ifelse(year < 2010, "a", "b"))]
  f <- fit_nb(nb_spec("y", fixed = c("x", "grp")), d)
  expect_error(linear_predictor(f, d[year == 2015]), "numeric")
})

test_that("draws and CV leave the caller's RNG stream untouched (P8)", {
  d <- sim_panel()
  f <- fit_nb(nb_spec("y", fixed = "x"), d)
  set.seed(5); r0 <- stats::runif(3)
  set.seed(5)
  invisible(draw_mu(f, f$data[year == 2015], n_draws = 5, seed = 1))
  invisible(draw_y(f, matrix(5, 2, 2), seed = 1))
  invisible(cv_predict(nb_spec("y", fixed = "x"), d, rolling_splits(2002:2025, 2025), n_draws = 5))
  expect_identical(stats::runif(3), r0)
})

test_that("rank-deficiency messages are captured in the fit record, not printed (P8)", {
  d <- step_panel()
  expect_silent(f <- fit_nb(nb_spec("y", fixed = c("x", "z")), d[year <= 2015]))
  expect_true(any(grepl("rank-deficient", f$messages)))
})
