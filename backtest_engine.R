set.seed(as.integer(Sys.time()))

generate_backtest <- function(n_trades = 200,
                              win_rate = 0.55,
                              rr_ratio = 1.8,
                              risk_per_trade = 1000) {
  wins <- rbinom(n_trades, 1, win_rate) == 1

  profit_per_trade <- numeric(n_trades)
  profit_per_trade[wins] <- rr_ratio * risk_per_trade
  profit_per_trade[!wins] <- -risk_per_trade

  equity <- cumsum(profit_per_trade)

  gross_profit <- sum(profit_per_trade[profit_per_trade > 0])
  gross_loss <- sum(profit_per_trade[profit_per_trade < 0])
  profit_factor <- ifelse(gross_loss == 0, NA, gross_profit / abs(gross_loss))

  cummax_equity <- cummax(c(0, equity))
  drawdowns <- c(0, equity) - cummax_equity
  max_drawdown <- min(drawdowns)

  list(
    n_trades = n_trades,
    profit_per_trade = profit_per_trade,
    equity = equity,
    gross_profit = gross_profit,
    gross_loss = gross_loss,
    profit_factor = profit_factor,
    max_drawdown = max_drawdown
  )
}

run_backtest <- function() {
  bt <- generate_backtest()

  # 実行中のスクリプトファイルの絶対パスからディレクトリを特定（作業ディレクトリに依存しない）
  script_dir <- tryCatch({
    args <- commandArgs(trailingOnly = FALSE)
    file_arg_index <- grep("^--file=", args)
    if (length(file_arg_index) > 0) {
      file_arg <- sub("^--file=", "", args[file_arg_index[1]])
      dirname(normalizePath(file_arg))
    } else {
      getwd()
    }
  }, error = function(e) {
    getwd()
  })

  equity_df <- data.frame(
    Trade = seq_along(bt$equity),
    Equity = bt$equity
  )

  equity_image_name <- "equity_curve.png"
  equity_image_path <- file.path(script_dir, equity_image_name)

  # Base R のみで資産曲線を描画
  png(filename = equity_image_path, width = 960, height = 480, res = 120, bg = "white")
  par(bg = "white")
  plot(
    equity_df$Trade,
    equity_df$Equity,
    type = "l",
    col = "darkgreen",
    lwd = 2,
    main = "Equity Curve (Dummy Backtest)",
    xlab = "Trade",
    ylab = "Cumulative P&L"
  )
  dev.off()

  # シンプルなテキスト形式で結果を出力（Python 側でパースしやすい形式）
  pf_val <- ifelse(is.na(bt$profit_factor), NA, bt$profit_factor)

  cat(paste0("total_trades: ", bt$n_trades, "\n"))
  cat(paste0("final_pnl: ", tail(bt$equity, 1), "\n"))
  cat(paste0("profit_factor: ", pf_val, "\n"))
  cat(paste0("max_drawdown: ", bt$max_drawdown, "\n"))
  cat(paste0("equity_curve_path: ", equity_image_name, "\n"))
}

run_backtest()

