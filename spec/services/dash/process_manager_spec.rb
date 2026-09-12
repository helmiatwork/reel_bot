# frozen_string_literal: true

require "rails_helper"

RSpec.describe Dash::ProcessManager do
  subject(:manager) { described_class.new }

  describe "constants and allowlists" do
    it "defines restartable, unsupported, and forbidden services" do
      expect(described_class::RESTARTABLE_SERVICES).to eq(%w[postgres openclaw cliproxy n8n arcreel])
      expect(described_class::UNSUPPORTED_NATIVE).to eq(%w[postgres n8n])
      expect(described_class::FORBIDDEN_SERVICES).to eq(%w[pipeline-api rails])
    end

    it "identifies forbidden services" do
      expect(described_class.forbidden?("pipeline-api")).to be true
      expect(described_class.forbidden?("rails")).to be true
      expect(described_class.forbidden?("openclaw")).to be false
    end

    it "identifies restartable services" do
      expect(described_class.restartable?("openclaw")).to be true
      expect(described_class.restartable?("postgres")).to be true
      expect(described_class.restartable?("random")).to be false
    end
  end

  describe "#restart_one" do
    it "returns unsupported_native for postgres and n8n" do
      expect(manager.restart_one("postgres")).to eq({ status: "unsupported_native" })
      expect(manager.restart_one("n8n")).to eq({ status: "unsupported_native" })
    end

    it "returns restarted in test environment for restartable services" do
      expect(manager.restart_one("openclaw")).to eq({ status: "restarted" })
      expect(manager.restart_one("cliproxy")).to eq({ status: "restarted" })
      expect(manager.restart_one("arcreel")).to eq({ status: "restarted" })
    end

    context "when running in non-test environment" do
      before do
        allow(Rails.env).to receive(:test?).and_return(false)
      end

      it "uses safe array syntax system('pkill', '-f', pattern) and spawns process" do
        expect(manager).to receive(:system).with("pkill", "-f", "openclaw gateway").and_return(true)
        expect(Process).to receive(:spawn).with(
          "/bin/bash", "-c", "openclaw gateway --port 18789",
          out: File::NULL, err: File::NULL
        )

        result = manager.restart_one("openclaw")
        expect(result).to eq({ status: "restarted" })
      end

      it "handles errors safely and returns status error" do
        expect(manager).to receive(:system).with("pkill", "-f", "openclaw gateway").and_raise(Errno::EPERM.new("Operation not permitted"))

        result = manager.restart_one("openclaw")
        expect(result).to eq({ status: "error" })
      end
    end
  end

  describe "#restart_all" do
    it "iterates through all restartable services and counts restarted ones" do
      result = manager.restart_all
      expect(result).to have_key(:results)
      expect(result).to have_key(:restarted)
      expect(result[:results].size).to eq(5)
      expect(result[:restarted]).to eq(3) # openclaw, cliproxy, arcreel
    end
  end

  describe ".restart_one and .restart_all class methods" do
    it "delegates to instance methods" do
      expect(described_class.restart_one("postgres")).to eq({ status: "unsupported_native" })
      result = described_class.restart_all
      expect(result[:restarted]).to eq(3)
    end
  end
end
