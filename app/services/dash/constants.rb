# frozen_string_literal: true

module Dash
  module Constants
    AGENTS_ROSTER = [
      { name: "analyze", role: "Frame + audio breakdown (vision)", model: "gemini-2.5-flash-lite" },
      { name: "analyze-senior", role: "Deep viral strategy", model: "claude/opus" },
      { name: "clipfinder", role: "Pick clip-worthy moments", model: "sonnet" },
      { name: "scriptwriter", role: "Formula-driven Short script", model: "gemini-2.5-flash" },
      { name: "editor", role: "EDL assembly decisions", model: "sonnet" },
      { name: "qcgate", role: "Pre-publish QC gate", model: "sonnet" },
      { name: "producer", role: "Run-sheet / next steps", model: "sonnet" },
      { name: "main", role: "Telegram orchestrator", model: "gemini-flash" }
    ].freeze

    TOKEN_PRICES = {
      "gemini-2.5-flash-lite" => [ 0.10, 0.40 ],
      "gemini-2.5-flash" => [ 0.30, 2.50 ],
      "deepseek-v4-flash" => [ 0.14, 0.28 ],
      "deepseek-v4-pro" => [ 0.40, 0.89 ],
      "claude-haiku-4-5" => [ 1.00, 5.00 ],
      "claude-sonnet-4-6" => [ 3.00, 15.00 ],
      "claude-opus-4-6" => [ 5.00, 25.00 ],
      "claude-opus-4-7" => [ 5.00, 25.00 ]
    }.freeze

    DEFAULT_TOKEN_PRICE = [ 0.50, 1.50 ].freeze
  end
end
