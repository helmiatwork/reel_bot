# frozen_string_literal: true

require "faraday"
require "json"

module Dash
  class CliproxyClient
    DEFAULT_EST_COST = 0.0015
    DEFAULT_URL = "http://cliproxy:8317/v1"

    def self.fetch_cost(mgmt_key: nil, est_cost: nil, url: nil)
      new(mgmt_key: mgmt_key, est_cost: est_cost, url: url).fetch_cost
    end

    def initialize(mgmt_key: nil, est_cost: nil, url: nil)
      @mgmt_key = (mgmt_key || ENV["CLIPROXY_MGMT_KEY"]).to_s.strip
      @est_cost = (est_cost || ENV["EST_COST_PER_REQUEST"].presence || DEFAULT_EST_COST).to_f
      @base_url = (url || ENV.fetch("CLIPROXY_URL", DEFAULT_URL)).sub(%r{/v1\z}, "")
    end

    def fetch_cost
      fallback = build_fallback
      if @mgmt_key.blank?
        return fallback.merge("error" => "CLIPROXY_MGMT_KEY not set")
      end

      response = connection.get("/v0/management/api-key-usage") do |req|
        req.headers["Authorization"] = "Bearer #{@mgmt_key}"
      end
      parse_usage(JSON.parse(response.body))
    rescue StandardError => e
      fallback.merge("error" => e.message)
    end

    def parse_usage(data)
      providers = []
      bucket = {}
      tot_s = 0
      tot_f = 0

      if data.is_a?(Hash)
        data.each do |prov, keys|
          ps, pf = accumulate_provider_keys(keys, bucket)
          tot_s += ps
          tot_f += pf
          providers << {
            "name" => prov,
            "success" => ps,
            "failed" => pf,
            "requests" => ps + pf,
            "est_cost" => ((ps + pf) * @est_cost).round(4)
          }
        end
      end

      series = bucket.keys.sort.map { |t| { "time" => t, "requests" => bucket[t] } }
      total_requests = tot_s + tot_f

      {
        "providers" => providers,
        "series" => series,
        "totals" => {
          "requests" => total_requests,
          "success" => tot_s,
          "failed" => tot_f,
          "est_cost" => (total_requests * @est_cost).round(4),
          "est_per_request" => @est_cost
        }
      }
    end

    def build_fallback
      {
        "providers" => [],
        "series" => [],
        "totals" => {
          "requests" => 0,
          "success" => 0,
          "failed" => 0,
          "est_cost" => 0.0,
          "est_per_request" => @est_cost
        }
      }
    end

    private

    def accumulate_provider_keys(keys, bucket)
      ps = 0
      pf = 0
      return [ ps, pf ] unless keys.is_a?(Hash)

      keys.each_value do |stat|
        next unless stat.is_a?(Hash)

        ps += stat["success"].to_i
        pf += stat["failed"].to_i
        (stat["recent_requests"] || []).each do |rq|
          t = rq["time"].to_s
          bucket[t] = (bucket[t] || 0) + rq["success"].to_i + rq["failed"].to_i
        end
      end

      [ ps, pf ]
    end

    def connection
      Faraday.new(url: @base_url) do |f|
        f.options.open_timeout = 2
        f.options.timeout = 5
        f.adapter Faraday.default_adapter
      end
    end
  end
end
