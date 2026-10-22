# Display conventions of results.json (ruling P14, R1).
MINUS <- "\u2212"
ENDASH <- "\u2013"

test_that("negatives use U+2212 by default in every formatter; minus = FALSE gives ASCII", {
  expect_identical(fmt_num(c(-2, 3.14159), 3), c(paste0(MINUS, "2.000"), "3.142"))
  expect_identical(fmt_num(-2, 1, minus = FALSE), "-2.0")
  expect_identical(fmt_int(c(-1234.6, 999)), c(paste0(MINUS, "1,235"), "999"))
  expect_identical(fmt_int(-5, minus = FALSE), "-5")
  expect_identical(fmt_pct(-0.031), paste0(MINUS, "3.1%"))
  expect_identical(.minus(c("-1.0", "2.0", NA)), c(paste0(MINUS, "1.0"), "2.0", NA))
  expect_identical(fmt_num(-0.0004, 3), "0.000")                      # no negative zero
})

test_that("fmt_num can show an explicit plus sign", {
  expect_identical(fmt_num(c(1.18, -0.5, 0), 2, plus = TRUE), c("+1.18", paste0(MINUS, "0.50"), "0.00"))
})

test_that("fmt_ci uses an en dash, or ' to ' when a bound is negative", {
  expect_identical(fmt_ci(1.123, 1.03, 1.21), paste0("1.12 (95% CI 1.03", ENDASH, "1.21)"))
  expect_identical(fmt_ci(-0.84, -1.5, -0.18),
                   paste0(MINUS, "0.84 (95% CI ", MINUS, "1.50 to ", MINUS, "0.18)"))
  expect_identical(fmt_ci(0.2, -0.1, 0.5), paste0("0.20 (95% CI ", MINUS, "0.10 to 0.50)"))
  expect_identical(fmt_ci(0.2, -0.0004, 0.5, digits = 3), paste0("0.200 (95% CI 0.000", ENDASH, "0.500)"))
  expect_identical(fmt_ci(c(1, -1), c(0.5, -2), c(2, -0.5), digits = 1),
                   c(paste0("1.0 (95% CI 0.5", ENDASH, "2.0)"),
                     paste0(MINUS, "1.0 (95% CI ", MINUS, "2.0 to ", MINUS, "0.5)")))
  expect_identical(fmt_ci(1234, 800, 1700, digits = 0, label = "nominal 95% interval", big.mark = ","),
                   paste0("1,234 (nominal 95% interval 800", ENDASH, "1,700)"))
  expect_identical(fmt_ci(-1234, -2500, 15, digits = 0, label = "nominal 95% interval", big.mark = ","),
                   paste0(MINUS, "1,234 (nominal 95% interval ", MINUS, "2,500 to 15)"))
  expect_identical(fmt_ci(-1, -2, -0.5, digits = 1, minus = FALSE), "-1.0 (95% CI -2.0 to -0.5)")
  expect_true(is.na(fmt_ci(1, NA, 2)))
})

test_that("fmt_p: three decimals, '<0.001' below 0.001, optional p prefix", {
  expect_identical(fmt_p(c(0.0123, 0.001, 0.00099, 0.5, 1e-12)), c("0.012", "0.001", "<0.001", "0.500", "<0.001"))
  expect_identical(fmt_p(c(0.0123, 0.0001), prefix = TRUE), c("p = 0.012", "p < 0.001"))
  expect_identical(fmt_p(0.00049), "<0.001")                          # never "0.000"
  expect_true(is.na(fmt_p(NA)))
  expect_error(fmt_p(1.2), "\\[0, 1\\]")
  expect_error(fmt_p(-0.1), "\\[0, 1\\]")
})

test_that("formatter sources carry no literal non-ASCII characters (escapes only)", {
  src <- readLines(file.path(MODELS_ROOT, "common", "R", "results.R"), encoding = "UTF-8", warn = FALSE)
  expect_false(any(grepl("[^\\x01-\\x7F]", src, perl = TRUE)))
})

test_that("res_entry rejects a NULL value; NA values are allowed and written as null", {
  expect_error(res_entry(NULL, "x", "s.R", "d"), "value")
  e <- res_entry(NA, "not estimable", "s.R", "d")
  expect_true(is.na(e$value))
})

test_that("write_results rejects an empty display", {
  path <- tempfile(fileext = ".json")
  bad <- list(`A.x` = list(value = 1, display = "", script = "s.R", description = "d"))
  expect_error(write_results(bad, path), "display")
  expect_false(file.exists(path))
})
