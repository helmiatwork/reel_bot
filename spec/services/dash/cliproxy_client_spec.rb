# frozen_string_literal: true

require "rails_helper"

RSpec.describe Dash::CliproxyClient do
  subject(:client) { described_class.new(mgmt_key: mgmt_key, est_cost: 0.002, url: "http://localhost:8317/v1") }

  let(:mgmt_key) { "test-mgmt-key" }

  describe "#fetch_cost" do
    context "when management key is blank" do
      let(:mgmt_key) { "" }

      it "returns fallback shell with error message" do
        result = client.fetch_cost
        expect(result["error"]).to eq("CLIPROXY_MGMT_KEY not set")
        expect(result["providers"]).to eq([])
        expect(result["totals"]["requests"]).to eq(0)
        expect(result["totals"]["est_per_request"]).to eq(0.002)
      end
    end

    context "when management key is present" do
      let(:upstream_data) do
        {
          "openai" => {
            "sk-secret-upstream-token" => {
              "success" => 5,
              "failed" => 1,
              "recent_requests" => [
                { "time" => "2026-09-12T10:00:00Z", "success" => 5, "failed" => 1 }
              ]
            }
          }
        }
      end

      it "queries Cliproxy management endpoint and aggregates usage" do
        stub_request(:get, "http://localhost:8317/v0/management/api-key-usage")
          .with(headers: { "Authorization" => "Bearer test-mgmt-key" })
          .to_return(status: 200, body: upstream_data.to_json, headers: { "Content-Type" => "application/json" })

        result = client.fetch_cost
        expect(result["providers"].size).to eq(1)
        expect(result["providers"].first["name"]).to eq("openai")
        expect(result["providers"].first["requests"]).to eq(6)
        expect(result["totals"]["requests"]).to eq(6)
        expect(result["totals"]["success"]).to eq(5)
        expect(result["totals"]["failed"]).to eq(1)
        expect(result["totals"]["est_cost"]).to eq((6 * 0.002).round(4))
      end

      it "handles connection errors and returns fallback with error" do
        stub_request(:get, "http://localhost:8317/v0/management/api-key-usage")
          .to_raise(Errno::ECONNREFUSED.new("Connection refused"))

        result = client.fetch_cost
        expect(result["error"]).to include("Connection refused")
        expect(result["totals"]["requests"]).to eq(0)
      end
    end
  end

  describe ".fetch_cost class method" do
    it "delegates to instance method" do
      instance = instance_double(described_class)
      allow(described_class).to receive(:new).with(mgmt_key: "abc", est_cost: nil, url: nil).and_return(instance)
      allow(instance).to receive(:fetch_cost).and_return({ "ok" => true })

      expect(described_class.fetch_cost(mgmt_key: "abc")).to eq({ "ok" => true })
    end
  end
end
