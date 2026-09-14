# frozen_string_literal: true

require "rails_helper"

RSpec.describe "Keywords", type: :request do
  describe "POST /keywords/ideas" do
    context "when Google Ads credentials are not configured" do
      before do
        allow_any_instance_of(KeywordService).to receive(:generate_ideas)
          .and_raise(KeywordService::ProviderNotConfiguredError.new("Google Ads API credentials not configured"))
      end

      it "returns HTTP 503 service_unavailable with error and detail fields" do
        post "/keywords/ideas", params: { seeds: [ "video editing" ], geo: "ID", lang: "id" }, as: :json

        expect(response).to have_http_status(:service_unavailable)
        json = JSON.parse(response.body)
        expect(json["error"]).to include("Google Ads API credentials not configured")
        expect(json["detail"]).to include("Google Ads API credentials not configured")
      end
    end

    context "when seeds parameter is missing or empty" do
      it "returns HTTP 400 bad request" do
        post "/keywords/ideas", params: { seeds: [] }, as: :json
        expect(response).to have_http_status(:bad_request)
        json = JSON.parse(response.body)
        expect(json["error"]).to be_present

        post "/keywords/ideas", params: {}, as: :json
        expect(response).to have_http_status(:bad_request)
      end
    end

    context "when successful" do
      let(:fake_keywords) do
        [
          {
            "id" => 1,
            "keyword" => "capcut tutorial",
            "source" => "google_ads",
            "region" => "ID:id",
            "avg_monthly_searches" => 50_000,
            "competition" => "MEDIUM",
            "competition_index" => 50,
            "score" => 25_000.0
          }
        ]
      end

      before do
        allow_any_instance_of(KeywordService).to receive(:generate_ideas)
          .with(seeds: [ "capcut" ], geo: "ID", lang: "id", niche: nil)
          .and_return(fake_keywords)
      end

      it "returns HTTP 200 OK with keywords list" do
        post "/keywords/ideas", params: { seeds: [ "capcut" ], geo: "ID", lang: "id" }, as: :json

        expect(response).to have_http_status(:ok)
        json = JSON.parse(response.body)
        expect(json).to have_key("keywords")
        expect(json["keywords"].size).to eq(1)
        expect(json["keywords"].first["keyword"]).to eq("capcut tutorial")
        expect(json["keywords"].first["score"]).to eq(25_000.0)
      end

      it "supports comma-separated string seeds" do
        allow_any_instance_of(KeywordService).to receive(:generate_ideas)
          .with(seeds: [ "capcut", "editing" ], geo: "ID", lang: "id", niche: "tech")
          .and_return(fake_keywords)

        post "/keywords/ideas", params: { seeds: "capcut, editing", geo: "ID", lang: "id", niche: "tech" }, as: :json

        expect(response).to have_http_status(:ok)
        json = JSON.parse(response.body)
        expect(json["keywords"]).to be_an(Array)
      end
    end
  end

  describe "GET /keywords" do
    before do
      create(:keyword, keyword: "kw_top", score: 9_000.0, avg_monthly_searches: 18_000, niche: "education", source: "google_ads", region: "ID:id")
      create(:keyword, keyword: "kw_mid", score: 4_500.0, avg_monthly_searches: 9_000, niche: "education", source: "google_ads", region: "ID:id")
      create(:keyword, keyword: "kw_low", score: 500.0, avg_monthly_searches: 1_000, niche: "gaming", source: "youtube_suggest", region: "US:en")
    end

    it "returns all keywords ordered by score DESC in keywords wrapper" do
      get "/keywords"

      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json).to have_key("keywords")
      expect(json["keywords"].map { |k| k["keyword"] }).to eq([ "kw_top", "kw_mid", "kw_low" ])
    end

    it "filters keywords by niche, source, min_volume, region, and limit" do
      get "/keywords", params: {
        niche: "education",
        source: "google_ads",
        min_volume: 10_000,
        region: "ID:id",
        limit: 10
      }

      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json["keywords"].map { |k| k["keyword"] }).to eq([ "kw_top" ])
    end

    it "returns empty array when no keywords match" do
      get "/keywords", params: { niche: "nonexistent" }

      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json["keywords"]).to eq([])
    end
  end
end
