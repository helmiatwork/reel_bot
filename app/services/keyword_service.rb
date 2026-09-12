# frozen_string_literal: true

require "faraday"
require "json"

class KeywordService
  class ProviderNotConfiguredError < StandardError; end

  REQUIRED_ENV_VARS = %w[
    GOOGLE_ADS_DEVELOPER_TOKEN
    GOOGLE_ADS_CLIENT_ID
    GOOGLE_ADS_CLIENT_SECRET
    GOOGLE_ADS_REFRESH_TOKEN
    GOOGLE_ADS_LOGIN_CUSTOMER_ID
    GOOGLE_ADS_CUSTOMER_ID
  ].freeze

  COMPETITION_MAP = {
    2 => "LOW",
    3 => "MEDIUM",
    4 => "HIGH",
    "2" => "LOW",
    "3" => "MEDIUM",
    "4" => "HIGH",
    "LOW" => "LOW",
    "MEDIUM" => "MEDIUM",
    "HIGH" => "HIGH"
  }.freeze

  RETURNING_COLUMNS = %w[
    id seed keyword source search_volume_min search_volume_max
    avg_monthly_searches competition competition_index
    cpc_low_micros cpc_high_micros region niche score raw fetched_at
  ].freeze

  attr_reader :adapter

  class << self
    def generate_ideas(...)
      new.generate_ideas(...)
    end

    def query_keywords(...)
      new.query_keywords(...)
    end
  end

  def initialize(adapter: nil)
    @adapter = adapter
  end

  def generate_ideas(seeds:, geo: "ID", lang: "id", niche: nil)
    seed_list = normalize_seeds(seeds)
    raise ArgumentError, "seeds list is required" if seed_list.empty?

    active_adapter = resolve_adapter
    raw_response = call_adapter(active_adapter, seeds: seed_list, geo: geo, lang: lang)

    records = normalize_ideas(raw_response, seeds: seed_list, geo: geo, lang: lang, niche: niche)
    return [] if records.empty?

    unique_records = records.index_by { |r| [ r[:keyword], r[:region], r[:source] ] }.values

    upsert_result = Keyword.upsert_all(
      unique_records,
      unique_by: [ :keyword, :region, :source ],
      returning: RETURNING_COLUMNS
    )

    upsert_result.to_a.map(&:with_indifferent_access)
  end

  def query_keywords(niche: nil, source: nil, min_volume: nil, region: nil, limit: 50)
    clamped_limit = (limit || 50).to_i.clamp(1, 200)

    scope = Keyword.by_score
    scope = scope.by_niche(niche)
    scope = scope.by_source(source)
    scope = scope.by_region(region)
    scope = scope.min_volume(min_volume)
    scope = scope.limit(clamped_limit)

    scope.map { |k| k.attributes.with_indifferent_access }
  end

  private

  def configured?
    REQUIRED_ENV_VARS.all? { |var| ENV[var].present? }
  end

  def resolve_adapter
    if @adapter.present?
      @adapter
    elsif configured?
      GoogleAdsAdapter.new
    else
      missing = REQUIRED_ENV_VARS.reject { |var| ENV[var].present? }
      raise ProviderNotConfiguredError,
            "Google Ads API credentials not configured. Missing: #{missing.join(', ')}"
    end
  end

  def call_adapter(target_adapter, seeds:, geo:, lang:)
    if target_adapter.respond_to?(:generate_ideas)
      target_adapter.generate_ideas(seeds: seeds, geo: geo, lang: lang)
    elsif target_adapter.respond_to?(:generate_keyword_ideas)
      target_adapter.generate_keyword_ideas(seeds: seeds, geo: geo, lang: lang)
    else
      raise ProviderNotConfiguredError, "Adapter unavailable or invalid"
    end
  end

  def normalize_seeds(seeds)
    if seeds.is_a?(String)
      seeds.split(",").map(&:strip).reject(&:blank?)
    else
      Array(seeds).map(&:to_s).map(&:strip).reject(&:blank?)
    end
  end

  def normalize_ideas(raw_response, seeds:, geo:, lang:, niche:)
    results = if raw_response.is_a?(Hash)
                raw_response["results"] || raw_response[:results] || []
    elsif raw_response.is_a?(Array)
                raw_response
    else
                []
    end

    now = Time.current
    region = "#{geo}:#{lang}"
    seed_str = seeds.join(" ")

    results.filter_map do |item|
      text = (item["text"] || item[:text]).to_s.strip
      next if text.blank?

      metrics = item["keyword_idea_metrics"] || item[:keyword_idea_metrics] || item
      avg_monthly_searches = metrics["avg_monthly_searches"] || metrics[:avg_monthly_searches]
      competition_raw = metrics["competition"] || metrics[:competition]
      competition_str = COMPETITION_MAP[competition_raw] || competition_raw&.to_s
      competition_index = metrics["competition_index"] || metrics[:competition_index]
      cpc_low = metrics["low_top_of_page_bid_micros"] || metrics[:low_top_of_page_bid_micros] ||
                metrics["cpc_low_micros"] || metrics[:cpc_low_micros]
      cpc_high = metrics["high_top_of_page_bid_micros"] || metrics[:high_top_of_page_bid_micros] ||
                 metrics["cpc_high_micros"] || metrics[:cpc_high_micros]
      search_vol_min = metrics["search_volume_min"] || metrics[:search_volume_min]
      search_vol_max = metrics["search_volume_max"] || metrics[:search_volume_max]

      score = Keyword.calculate_score(
        avg_monthly_searches: avg_monthly_searches,
        competition_index: competition_index,
        niche_fit: 1.0
      )

      {
        seed: seed_str,
        keyword: text,
        source: "google_ads",
        search_volume_min: search_vol_min,
        search_volume_max: search_vol_max,
        avg_monthly_searches: avg_monthly_searches,
        competition: competition_str,
        competition_index: competition_index,
        cpc_low_micros: cpc_low,
        cpc_high_micros: cpc_high,
        region: region,
        niche: niche,
        score: score,
        raw: item.as_json,
        fetched_at: now,
        created_at: now,
        updated_at: now
      }
    end
  end

  class GoogleAdsAdapter
    GEO_CONSTANTS = {
      "ID" => 2360,
      "US" => 2840
    }.freeze

    LANG_CONSTANTS = {
      "id" => 1025,
      "en" => 1000
    }.freeze

    def generate_ideas(seeds:, geo: "ID", lang: "id")
      geo_id = GEO_CONSTANTS[geo.to_s.upcase] || 2360
      lang_id = LANG_CONSTANTS[lang.to_s.downcase] || 1025
      customer_id = ENV["GOOGLE_ADS_CUSTOMER_ID"].to_s.gsub("-", "")

      access_token = fetch_oauth_access_token

      conn = Faraday.new(url: "https://googleads.googleapis.com") do |f|
        f.request :json
        f.response :json, content_type: /\bjson$/
        f.adapter Faraday.default_adapter
      end

      payload = {
        customerId: customer_id,
        language: "languageConstants/#{lang_id}",
        geoTargetConstants: [ "geoTargetConstants/#{geo_id}" ],
        keywordSeed: {
          keywords: seeds
        }
      }

      response = conn.post("/v17/customers/#{customer_id}:generateKeywordIdeas", payload) do |req|
        req.headers["Authorization"] = "Bearer #{access_token}"
        req.headers["developer-token"] = ENV["GOOGLE_ADS_DEVELOPER_TOKEN"]
        req.headers["login-customer-id"] = ENV["GOOGLE_ADS_LOGIN_CUSTOMER_ID"] if ENV["GOOGLE_ADS_LOGIN_CUSTOMER_ID"].present?
        req.headers["Content-Type"] = "application/json"
      end

      unless response.success?
        raise "Google Ads API error: HTTP #{response.status} #{response.body}"
      end

      response.body
    end

    private

    def fetch_oauth_access_token
      token_conn = Faraday.new(url: "https://oauth2.googleapis.com") do |f|
        f.request :url_encoded
        f.response :json, content_type: /\bjson$/
        f.adapter Faraday.default_adapter
      end

      resp = token_conn.post("/token", {
        client_id: ENV["GOOGLE_ADS_CLIENT_ID"],
        client_secret: ENV["GOOGLE_ADS_CLIENT_SECRET"],
        refresh_token: ENV["GOOGLE_ADS_REFRESH_TOKEN"],
        grant_type: "refresh_token"
      })

      unless resp.success? && resp.body["access_token"].present?
        raise "OAuth token refresh failed: #{resp.body}"
      end

      resp.body["access_token"]
    end
  end
end
