# frozen_string_literal: true

require "net/http"
require "uri"

module Dash
  class ServiceProbe
    SERVICES = [
      { name: "postgres", port: 5432, url: nil },
      { name: "openclaw", port: 18789, url: "http://localhost:18789" },
      { name: "n8n", port: 5678, url: "http://localhost:5678/healthz" },
      { name: "cliproxy", port: 8317, url: "http://localhost:8317/v1/models" },
      { name: "rails", port: 3000, url: "http://localhost:3000/up" },
      { name: "arcreel", port: 1241, url: "http://localhost:1241" }
    ].freeze

    def self.probe_all
      new.probe_all
    end

    def probe_all
      services = probe_services
      {
        services: services,
        live: services.count { |s| s[:up] },
        total: services.size
      }
    end

    def probe_services
      SERVICES.map do |service|
        Thread.new { probe_service(service) }
      end.map(&:value)
    end

    def probe_service(service)
      name = service[:name]
      port = service[:port]
      url = service[:url]

      up = if name == "postgres"
             probe_postgres
      else
             probe_http(url)
      end

      { name: name, port: port, up: up }
    end

    private

    def probe_postgres
      ActiveRecord::Base.connection_pool.with_connection(&:active?)
    rescue StandardError
      false
    end

    def probe_http(url)
      return false if url.blank?

      uri = URI.parse(url)
      http = Net::HTTP.new(uri.host, uri.port)
      http.open_timeout = 1
      http.read_timeout = 2
      http.use_ssl = (uri.scheme == "https")

      path = uri.path.presence || "/"
      path += "?#{uri.query}" if uri.query.present?

      request = Net::HTTP::Get.new(path)
      response = http.request(request)

      response.code.to_i < 500
    rescue StandardError
      false
    end
  end
end
