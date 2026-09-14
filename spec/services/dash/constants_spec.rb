# frozen_string_literal: true

require "rails_helper"

RSpec.describe Dash::Constants do
  describe "AGENTS_ROSTER" do
    it "contains the expected 8 agents" do
      expect(described_class::AGENTS_ROSTER.size).to eq(8)
      names = described_class::AGENTS_ROSTER.map { |a| a[:name] }
      expect(names).to include("analyze", "analyze-senior", "clipfinder", "scriptwriter", "editor", "qcgate", "producer", "main")
    end
  end

  describe "TOKEN_PRICES" do
    it "contains pricing for key models" do
      expect(described_class::TOKEN_PRICES).to have_key("gemini-2.5-flash")
      expect(described_class::DEFAULT_TOKEN_PRICE).to eq([ 0.50, 1.50 ])
    end
  end
end
