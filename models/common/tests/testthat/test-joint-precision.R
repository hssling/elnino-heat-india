# Ill-conditioned but positive-definite precision: scales spanning 1e-9..1 (rcond ~1e-18 or worse).
ill_Q <- function(n = 8, seed = 7) {
  # D R D with D spanning 1..1e10: like diag random-slope SDs collapsing to ~1e-10 (rcond ~1e-20)
  set.seed(seed)
  A <- matrix(rnorm(n * n), n)
  R <- crossprod(A) / n + diag(n)
  d <- 10^seq(0, 10, length.out = n)
  Q <- R * outer(d, d)
  (Q + t(Q)) / 2
}

test_that("base solve() refuses an ill-conditioned PD precision but the Cholesky inverse works (P17b)", {
  Q <- ill_Q(8)
  expect_true(all(eigen(Q, symmetric = TRUE, only.values = TRUE)$values > 0))
  expect_lt(rcond(Q), .Machine$double.eps)
  expect_error(solve(Q), "singular")
  C <- .invert_joint_precision(Q)
  expect_equal(C, chol2inv(chol(Q)))
  expect_true(all(diag(C) > 0) && isSymmetric(C, tol = 1e-8 * max(abs(C))))
  # draws from N(0, C) reproduce C
  set.seed(1)
  D <- MASS::mvrnorm(2e5, rep(0, nrow(C)), (C + t(C)) / 2)
  # absolute agreement, relative to the largest variance (mvrnorm's eigen step cannot resolve
  # the ~1e-20-scale directions relatively, which does not matter on the scale of the outputs)
  expect_lt(max(abs(stats::cov(D) - C)) / max(abs(C)), 0.02)
})

test_that("a non-positive-definite precision errors clearly, with no fallback (P17b)", {
  Q <- diag(c(1, 2, -3, 4))
  expect_error(.invert_joint_precision(Q), "not positive definite")
  Q2 <- matrix(1, 3, 3)   # singular PSD
  expect_error(.invert_joint_precision(Q2), "not positive definite")
})
