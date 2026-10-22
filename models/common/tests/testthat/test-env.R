test_that("pinned R and locked packages load", {
  expect_identical(as.character(getRversion()), "4.5.3")
  for (p in c("glmmTMB", "data.table", "jsonlite", "ggplot2", "mgcv", "MASS", "splines")) {
    expect_true(requireNamespace(p, quietly = TRUE), info = p)
  }
  lock <- jsonlite::fromJSON(file.path(MODELS_ROOT, "renv.lock"))
  expect_true(all(c("glmmTMB", "data.table", "jsonlite", "testthat") %in% names(lock$Packages)))
})
