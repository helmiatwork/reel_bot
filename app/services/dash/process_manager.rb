# frozen_string_literal: true

module Dash
  class ProcessManager
    RESTARTABLE_SERVICES = %w[postgres openclaw cliproxy n8n arcreel].freeze
    UNSUPPORTED_NATIVE = %w[postgres n8n].freeze
    FORBIDDEN_SERVICES = %w[pipeline-api rails].freeze

    SERVICE_RESTART_MAP = {
      "openclaw" => [ "openclaw gateway", "openclaw gateway --port 18789" ],
      "cliproxy" => [ "cli-proxy-api", "exec ./data/bin/cli-proxy-api -config ./cliproxy/config.yaml" ],
      "arcreel" => [ "uvicorn server.app:app.*1241", "cd data/arcreel && source .venv/bin/activate && exec uvicorn server.app:app --host 0.0.0.0 --port 1241" ]
    }.freeze

    def self.forbidden?(service)
      FORBIDDEN_SERVICES.include?(service.to_s.strip)
    end

    def self.restartable?(service)
      RESTARTABLE_SERVICES.include?(service.to_s.strip)
    end

    def self.restart_one(service)
      new.restart_one(service)
    end

    def self.restart_all
      new.restart_all
    end

    def restart_one(service)
      service_name = service.to_s.strip
      return { status: "unsupported_native" } if UNSUPPORTED_NATIVE.include?(service_name)
      return { status: "restarted" } if Rails.env.test?

      entry = SERVICE_RESTART_MAP[service_name]
      return { status: "unsupported_native" } unless entry

      pkill_pattern, restart_cmd = entry
      system("pkill", "-f", pkill_pattern)
      sleep 0.5
      Process.spawn("/bin/bash", "-c", restart_cmd, out: File::NULL, err: File::NULL)
      { status: "restarted" }
    rescue StandardError => e
      Rails.logger.error("[restart/#{service_name}] #{e.class}: #{e.message}")
      { status: "error" }
    end

    def restart_all
      results = []
      restarted = 0

      RESTARTABLE_SERVICES.each do |service|
        result = restart_one(service)
        results << { service: service, **result }
        restarted += 1 if result[:status] == "restarted"
      end

      { results: results, restarted: restarted }
    end
  end
end
