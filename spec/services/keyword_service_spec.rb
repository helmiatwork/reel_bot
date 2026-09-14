# frozen_string_literal: true

require "rails_helper"

RSpec.describe KeywordService do
  subject(:service) { described_class.new(adapter: adapter) }

  let(:adapter) { nil }

  describe "configuration and error handling" do
    context "when Google Ads credentials are not configured and no adapter is provided" do
      around do |example|
        old_env = ENV.to_h
        ENV.delete("GOOGLE_ADS_DEVELOPER_TOKEN")
        ENV.delete("GOOGLE_ADS_CLIENT_ID")
        ENV.delete("GOOGLE_ADS_CLIENT_SECRET")
        ENV.delete("GOOGLE_ADS_REFRESH_TOKEN")
        ENV.delete("GOOGLE_ADS_LOGIN_CUSTOMER_ID")
        ENV.delete("GOOGLE_ADS_CUSTOMER_ID")
        example.run
      ensure
        ENV.replace(old_env)
      end

      it "raises ProviderNotConfiguredError when calling generate_ideas" do
        expect {
          service.generate_ideas(seeds: [ "video editing" ])
        }.to raise_error(KeywordService::ProviderNotConfiguredError, /Google Ads.*credentials not configured/i)
      end
    end
  end

  describe "#generate_ideas" do
    let(:mock_adapter) { double("GoogleAdsAdapter") }
    let(:adapter) { mock_adapter }

    let(:raw_adapter_response) do
      {
        "results" => [
          {
            "text" => "video editing tutorial",
            "keyword_idea_metrics" => {
              "avg_monthly_searches" => 14_600,
              "competition" => 3, # MEDIUM
              "competition_index" => 67,
              "low_top_of_page_bid_micros" => 500_000,
              "high_top_of_page_bid_micros" => 2_500_000
            }
          },
          {
            "text" => "best free video editor",
            "keyword_idea_metrics" => {
              "avg_monthly_searches" => 8_200,
              "competition" => 2, # LOW
              "competition_index" => 23,
              "low_top_of_page_bid_micros" => 100_000,
              "high_top_of_page_bid_micros" => 500_000
            }
          },
          {
            "text" => "adobe premiere pro tutorial",
            "keyword_idea_metrics" => {
              "avg_monthly_searches" => nil,
              "competition" => nil,
              "competition_index" => nil,
              "low_top_of_page_bid_micros" => nil,
              "high_top_of_page_bid_micros" => nil
            }
          }
        ]
      }
    end

    before do
      allow(mock_adapter).to receive(:generate_ideas)
        .with(seeds: [ "video editing" ], geo: "ID", lang: "id")
        .and_return(raw_adapter_response)
    end

    it "fetches ideas from adapter, computes score, and upserts into database" do
      result = service.generate_ideas(seeds: [ "video editing" ], geo: "ID", lang: "id", niche: "tech")

      expect(result).to be_an(Array)
      expect(result.size).to eq(3)

      kw0 = result.find { |k| k["keyword"] == "video editing tutorial" || k[:keyword] == "video editing tutorial" }
      expect(kw0).not_to be_nil
      expect(kw0["source"] || kw0[:source]).to eq("google_ads")
      expect(kw0["region"] || kw0[:region]).to eq("ID:id")
      expect(kw0["avg_monthly_searches"] || kw0[:avg_monthly_searches]).to eq(14_600)
      expect(kw0["competition"] || kw0[:competition]).to eq("MEDIUM")
      expect(kw0["competition_index"] || kw0[:competition_index]).to eq(67)
      expect(kw0["score"] || kw0[:score]).to be_within(0.1).of(14_600 * (1 - 0.67) * 1.0)
      expect(kw0["niche"] || kw0[:niche]).to eq("tech")

      # Verify persisted in database
      expect(Keyword.count).to eq(3)
      persisted = Keyword.find_by(keyword: "video editing tutorial", region: "ID:id", source: "google_ads")
      expect(persisted).to be_present
      expect(persisted.competition).to eq("MEDIUM")
    end

    it "safely handles null/empty metrics" do
      result = service.generate_ideas(seeds: [ "video editing" ], geo: "ID", lang: "id")

      kw_null = result.find { |k| k["keyword"] == "adobe premiere pro tutorial" || k[:keyword] == "adobe premiere pro tutorial" }
      expect(kw_null).not_to be_nil
      expect(kw_null["avg_monthly_searches"] || kw_null[:avg_monthly_searches]).to be_nil
      expect(kw_null["competition"] || kw_null[:competition]).to be_nil
      expect(kw_null["competition_index"] || kw_null[:competition_index]).to be_nil
      expect((kw_null["score"] || kw_null[:score]).to_f).to eq(0.0)
    end

    it "accepts comma-separated seeds string and normalizes to array" do
      allow(mock_adapter).to receive(:generate_ideas)
        .with(seeds: [ "video editing", "premiere" ], geo: "ID", lang: "id")
        .and_return(raw_adapter_response)

      result = service.generate_ideas(seeds: "video editing, premiere", geo: "ID", lang: "id")
      expect(result.size).to eq(3)
    end

    it "performs idempotent bulk UPSERT without creating duplicate records" do
      service.generate_ideas(seeds: [ "video editing" ], geo: "ID", lang: "id")
      expect(Keyword.count).to eq(3)

      updated_response = {
        "results" => [
          {
            "text" => "video editing tutorial",
            "keyword_idea_metrics" => {
              "avg_monthly_searches" => 20_000,
              "competition" => 4, # HIGH
              "competition_index" => 85,
              "low_top_of_page_bid_micros" => 800_000,
              "high_top_of_page_bid_micros" => 3_000_000
            }
          }
        ]
      }

      allow(mock_adapter).to receive(:generate_ideas)
        .with(seeds: [ "video editing" ], geo: "ID", lang: "id")
        .and_return(updated_response)

      service.generate_ideas(seeds: [ "video editing" ], geo: "ID", lang: "id")

      expect(Keyword.count).to eq(3)
      updated_record = Keyword.find_by(keyword: "video editing tutorial", region: "ID:id", source: "google_ads")
      expect(updated_record.avg_monthly_searches).to eq(20_000)
      expect(updated_record.competition).to eq("HIGH")
      expect(updated_record.competition_index).to eq(85)
      expect(updated_record.score).to be_within(0.1).of(20_000 * (1 - 0.85) * 1.0)
    end
  end

  describe "#query_keywords" do
    before do
      create(:keyword, keyword: "kw_high", score: 10_000.0, avg_monthly_searches: 20_000, niche: "education", source: "google_ads", region: "ID:id")
      create(:keyword, keyword: "kw_med", score: 5_000.0, avg_monthly_searches: 10_000, niche: "education", source: "google_ads", region: "ID:id")
      create(:keyword, keyword: "kw_low", score: 1_000.0, avg_monthly_searches: 2_000, niche: "gaming", source: "youtube_suggest", region: "US:en")
    end

    it "returns all keywords ordered by score DESC by default" do
      result = service.query_keywords
      expect(result.size).to eq(3)
      scores = result.map { |k| (k["score"] || k[:score]).to_f }
      expect(scores).to eq([ 10_000.0, 5_000.0, 1_000.0 ])
    end

    it "filters by niche" do
      result = service.query_keywords(niche: "education")
      expect(result.size).to eq(2)
      keywords = result.map { |k| k["keyword"] || k[:keyword] }
      expect(keywords).to eq([ "kw_high", "kw_med" ])
    end

    it "filters by source" do
      result = service.query_keywords(source: "youtube_suggest")
      expect(result.size).to eq(1)
      expect(result.first["keyword"] || result.first[:keyword]).to eq("kw_low")
    end

    it "filters by min_volume" do
      result = service.query_keywords(min_volume: 10_000)
      expect(result.size).to eq(2)
      keywords = result.map { |k| k["keyword"] || k[:keyword] }
      expect(keywords).to eq([ "kw_high", "kw_med" ])
    end

    it "filters by region" do
      result = service.query_keywords(region: "US:en")
      expect(result.size).to eq(1)
      expect(result.first["keyword"] || result.first[:keyword]).to eq("kw_low")
    end

    it "clamps limit parameter between 1 and 200" do
      result = service.query_keywords(limit: 1)
      expect(result.size).to eq(1)
      expect(result.first["keyword"] || result.first[:keyword]).to eq("kw_high")
    end

    it "supports class-level delegation via .query_keywords" do
      result = described_class.query_keywords(limit: 2)
      expect(result.size).to eq(2)
    end
  end

  describe "class methods and adapter edge cases" do
    it "supports class-level delegation via .generate_ideas" do
      mock_adapter = double("GoogleAdsAdapter")
      allow(mock_adapter).to receive(:generate_ideas).and_return({ "results" => [] })
      allow_any_instance_of(described_class).to receive(:resolve_adapter).and_return(mock_adapter)

      result = described_class.generate_ideas(seeds: [ "test" ])
      expect(result).to eq([])
    end

    it "raises ArgumentError when seeds list is empty" do
      expect {
        service.generate_ideas(seeds: [])
      }.to raise_error(ArgumentError, /seeds list is required/i)
    end

    it "raises ProviderNotConfiguredError when adapter does not respond to generate_ideas" do
      invalid_adapter = Object.new
      invalid_service = described_class.new(adapter: invalid_adapter)
      expect {
        invalid_service.generate_ideas(seeds: [ "test" ])
      }.to raise_error(KeywordService::ProviderNotConfiguredError, /Adapter unavailable or invalid/i)
    end

    context "when Google Ads credentials are configured and using default GoogleAdsAdapter" do
      around do |example|
        old_env = ENV.to_h
        ENV["GOOGLE_ADS_DEVELOPER_TOKEN"] = "dev-tok"
        ENV["GOOGLE_ADS_CLIENT_ID"] = "client-id"
        ENV["GOOGLE_ADS_CLIENT_SECRET"] = "client-secret"
        ENV["GOOGLE_ADS_REFRESH_TOKEN"] = "refresh-tok"
        ENV["GOOGLE_ADS_LOGIN_CUSTOMER_ID"] = "login-cust-id"
        ENV["GOOGLE_ADS_CUSTOMER_ID"] = "123-456-7890"
        example.run
      ensure
        ENV.replace(old_env)
      end

      it "calls OAuth token endpoint and Google Ads API successfully" do
        stub_request(:post, "https://oauth2.googleapis.com/token")
          .to_return(status: 200, body: { access_token: "mock-access-token" }.to_json, headers: { "Content-Type" => "application/json" })

        ads_response = {
          "results" => [
            {
              "text" => "video editor pro",
              "keyword_idea_metrics" => {
                "avg_monthly_searches" => 30_000,
                "competition" => 2,
                "competition_index" => 20
              }
            }
          ]
        }

        stub_request(:post, "https://googleads.googleapis.com/v17/customers/1234567890:generateKeywordIdeas")
          .to_return(status: 200, body: ads_response.to_json, headers: { "Content-Type" => "application/json" })

        default_service = described_class.new
        result = default_service.generate_ideas(seeds: [ "video editor" ])

        expect(result.size).to eq(1)
        expect(result.first["keyword"] || result.first[:keyword]).to eq("video editor pro")
      end

      it "raises error when OAuth token exchange fails" do
        stub_request(:post, "https://oauth2.googleapis.com/token")
          .to_return(status: 400, body: { error: "invalid_grant" }.to_json, headers: { "Content-Type" => "application/json" })

        default_service = described_class.new
        expect {
          default_service.generate_ideas(seeds: [ "video editor" ])
        }.to raise_error(/OAuth token refresh failed/)
      end

      it "raises error when Google Ads API request fails" do
        stub_request(:post, "https://oauth2.googleapis.com/token")
          .to_return(status: 200, body: { access_token: "mock-access-token" }.to_json, headers: { "Content-Type" => "application/json" })

        stub_request(:post, "https://googleads.googleapis.com/v17/customers/1234567890:generateKeywordIdeas")
          .to_return(status: 500, body: { error: "internal server error" }.to_json, headers: { "Content-Type" => "application/json" })

        default_service = described_class.new
        expect {
          default_service.generate_ideas(seeds: [ "video editor" ])
        }.to raise_error(/Google Ads API error: HTTP 500/)
      end
    end
  end
end
