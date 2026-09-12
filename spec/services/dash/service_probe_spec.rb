# frozen_string_literal: true

require "rails_helper"

RSpec.describe Dash::ServiceProbe do
  subject(:probe) { described_class.new }

  describe ".probe_all and #probe_all" do
    let(:stubbed_results) do
      [
        { name: "postgres", port: 5432, up: true },
        { name: "openclaw", port: 18789, up: true },
        { name: "n8n", port: 5678, up: false },
        { name: "cliproxy", port: 8317, up: true },
        { name: "rails", port: 3000, up: true },
        { name: "arcreel", port: 1241, up: false }
      ]
    end

    it "returns all 6 services with live and total counts" do
      allow(probe).to receive(:probe_services).and_return(stubbed_results)

      result = probe.probe_all
      expect(result[:services]).to eq(stubbed_results)
      expect(result[:live]).to eq(4)
      expect(result[:total]).to eq(6)
    end

    it "works via class method .probe_all" do
      instance = instance_double(described_class)
      allow(described_class).to receive(:new).and_return(instance)
      allow(instance).to receive(:probe_all).and_return({ services: stubbed_results, live: 4, total: 6 })

      result = described_class.probe_all
      expect(result[:live]).to eq(4)
      expect(result[:total]).to eq(6)
    end
  end

  describe "individual service probing" do
    describe "postgres probe" do
      it "returns up: true when connection pool connection is active" do
        conn = instance_double(ActiveRecord::ConnectionAdapters::AbstractAdapter, active?: true)
        allow(ActiveRecord::Base.connection_pool).to receive(:with_connection).and_yield(conn)
        service = probe.probe_service({ name: "postgres", port: 5432, url: nil })

        expect(service).to eq({ name: "postgres", port: 5432, up: true })
      end

      it "returns up: false when connection pool raises an error" do
        allow(ActiveRecord::Base.connection_pool).to receive(:with_connection).and_raise(ActiveRecord::ConnectionNotEstablished)
        service = probe.probe_service({ name: "postgres", port: 5432, url: nil })

        expect(service).to eq({ name: "postgres", port: 5432, up: false })
      end
    end

    describe "HTTP probes" do
      let(:openclaw_check) { { name: "openclaw", port: 18789, url: "http://localhost:18789" } }

      it "returns up: true when response status is < 500" do
        stub_request(:get, "http://localhost:18789").to_return(status: 200, body: "ok")

        service = probe.probe_service(openclaw_check)
        expect(service).to eq({ name: "openclaw", port: 18789, up: true })
      end

      it "returns up: true when response status is 404 (service is running)" do
        stub_request(:get, "http://localhost:18789").to_return(status: 404, body: "not found")

        service = probe.probe_service(openclaw_check)
        expect(service).to eq({ name: "openclaw", port: 18789, up: true })
      end

      it "returns up: false when response status is >= 500" do
        stub_request(:get, "http://localhost:18789").to_return(status: 502, body: "bad gateway")

        service = probe.probe_service(openclaw_check)
        expect(service).to eq({ name: "openclaw", port: 18789, up: false })
      end

      it "returns up: false when connection fails" do
        stub_request(:get, "http://localhost:18789").to_raise(Errno::ECONNREFUSED)

        service = probe.probe_service(openclaw_check)
        expect(service).to eq({ name: "openclaw", port: 18789, up: false })
      end

      it "returns up: false when connection times out" do
        stub_request(:get, "http://localhost:18789").to_timeout

        service = probe.probe_service(openclaw_check)
        expect(service).to eq({ name: "openclaw", port: 18789, up: false })
      end
    end
  end
end
