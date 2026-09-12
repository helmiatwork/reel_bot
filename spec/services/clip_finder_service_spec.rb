# frozen_string_literal: true

require "rails_helper"

RSpec.describe ClipFinderService do
  let(:valid_url) { "https://www.youtube.com/watch?v=dQw4w9WgXcQ" }
  let(:sample_segments) do
    [
      { start: 10.0, end: 20.0, text: "First segment text here" },
      { start: 20.0, end: 35.0, text: "Another important moment" },
      { start: 115.0, end: 170.0, text: "The punchline part here" }
    ]
  end
  let(:sample_clips) do
    [
      {
        "start_sec" => 15,
        "end_sec" => 45,
        "title" => "Shocking moment revealed",
        "hook" => "Wait until you see this...",
        "why" => "Pattern interrupt with emotional peak",
        "caption" => "Viewers couldn't look away"
      },
      {
        "start_sec" => 120,
        "end_sec" => 165,
        "title" => "Perfect punchline",
        "hook" => "And then he said...",
        "why" => "Comedic climax with universal appeal",
        "caption" => "Unexpected twist ending"
      }
    ]
  end

  let(:mock_yt_dlp) { instance_double(YtDlpService) }

  before do
    allow(YtDlpService).to receive(:new).and_return(mock_yt_dlp)
    allow(mock_yt_dlp).to receive(:fetch_transcript).with(valid_url).and_return({ segments: sample_segments })
  end

  describe "validation" do
    it "raises ArgumentError on command injection" do
      expect {
        described_class.new(youtube_url: "https://youtube.com/watch?v=1; rm -rf /").call
      }.to raise_error(ArgumentError, /invalid or prohibited/)
    end

    it "raises ArgumentError when youtube_url is blank" do
      expect {
        described_class.new(youtube_url: "").call
      }.to raise_error(ArgumentError, /URL cannot be blank/)
    end

    it "raises ArgumentError on non-HTTP/HTTPS scheme" do
      expect {
        described_class.new(youtube_url: "ftp://example.com/video").call
      }.to raise_error(ArgumentError, /HTTP or HTTPS/)
    end

    it "raises ArgumentError on invalid URI syntax" do
      allow(URI).to receive(:parse).and_raise(URI::InvalidURIError.new("bad"))
      expect {
        described_class.new(youtube_url: valid_url).call
      }.to raise_error(ArgumentError, /URL is invalid/)
    end
  end

  describe "caching behavior" do
    it "returns cached find when available and force is false" do
      cached = ClipFind.create!(
        youtube_url: valid_url,
        clips: sample_clips,
        model: "claude-sonnet-4-6",
        cost_usd: 0.05
      )

      service = described_class.new(youtube_url: valid_url)
      result = service.call

      expect(result[:cached_find]).to be(true)
      expect(result[:clips].size).to eq(2)
      expect(result[:clip_find_id]).to eq(cached.id)
      expect(mock_yt_dlp).not_to have_received(:fetch_transcript)
    end

    it "bypasses cache when force is true" do
      ClipFind.create!(
        youtube_url: valid_url,
        clips: [ { "start_sec" => 0, "end_sec" => 5, "title" => "Old clip" } ],
        model: "claude-sonnet-4-6"
      )

      bridge_response = {
        ok: true,
        result: { clips: sample_clips }.to_json,
        cost_usd: 0.045
      }
      stub_request(:post, "http://localhost:9999/run")
        .to_return(status: 200, body: bridge_response.to_json, headers: { "Content-Type" => "application/json" })

      service = described_class.new(youtube_url: valid_url, force: true)
      result = service.call

      expect(result[:cached_find]).to be(false)
      expect(result[:clips].size).to eq(2)
      expect(result[:cost_usd]).to eq(0.045)
      expect(mock_yt_dlp).to have_received(:fetch_transcript)
    end
  end

  describe "successful clip generation via bridge" do
    it "calls bridge, parses JSON, ranks clips, and saves to database" do
      bridge_response = {
        ok: true,
        result: { clips: sample_clips }.to_json,
        cost_usd: 0.0512
      }
      stub_request(:post, "http://localhost:9999/run")
        .to_return(status: 200, body: bridge_response.to_json, headers: { "Content-Type" => "application/json" })

      service = described_class.new(youtube_url: valid_url, max_clips: 8)
      result = service.call

      expect(result[:cached_find]).to be(false)
      expect(result[:youtube_url]).to eq(valid_url)
      expect(result[:clips].size).to eq(2)
      expect(result[:cost_usd]).to eq(0.0512)

      # Check rankings
      clips = result[:clips]
      expect(clips[0]["rank"]).to eq(1)
      expect(clips[0]["recommended"]).to be(true)
      expect(clips[1]["rank"]).to eq(2)
      expect(clips[1]["recommended"]).to be(false)

      # Check database record created
      created = ClipFind.latest_for(valid_url)
      expect(created).to be_present
      expect(created.clips.size).to eq(2)
      expect(result[:clip_find_id]).to eq(created.id)
    end

    it "handles fenced JSON in bridge response" do
      fenced_result = "```json\n" + { clips: sample_clips }.to_json + "\n```"
      bridge_response = {
        ok: true,
        result: fenced_result,
        cost_usd: 0.05
      }
      stub_request(:post, "http://localhost:9999/run")
        .to_return(status: 200, body: bridge_response.to_json, headers: { "Content-Type" => "application/json" })

      result = described_class.new(youtube_url: valid_url).call
      expect(result[:clips].size).to eq(2)
    end

    it "defaults to empty array when bridge response lacks clips key" do
      bridge_response = {
        ok: true,
        result: {}.to_json,
        cost_usd: 0.01
      }
      stub_request(:post, "http://localhost:9999/run")
        .to_return(status: 200, body: bridge_response.to_json, headers: { "Content-Type" => "application/json" })

      result = described_class.new(youtube_url: valid_url).call
      expect(result[:clips]).to eq([])
    end

    it "clamps max_clips to 1..20" do
      bridge_response = { ok: true, result: { clips: [] }.to_json, cost_usd: 0.01 }
      stub_request(:post, "http://localhost:9999/run")
        .to_return(status: 200, body: bridge_response.to_json, headers: { "Content-Type" => "application/json" })

      service_high = described_class.new(youtube_url: valid_url, max_clips: 100)
      expect(service_high.max_clips).to eq(20)

      service_low = described_class.new(youtube_url: valid_url, max_clips: 0)
      expect(service_low.max_clips).to eq(1)
    end

    it "truncates transcript when text exceeds 45,000 characters" do
      huge_segments = (1..1000).map { |i| { start: i * 5, text: "A" * 100 } }
      allow(mock_yt_dlp).to receive(:fetch_transcript).with(valid_url).and_return({ segments: huge_segments })

      bridge_response = { ok: true, result: { clips: sample_clips }.to_json, cost_usd: 0.05 }
      stub_request(:post, "http://localhost:9999/run")
        .with { |req| req.body.include?("[... transcript truncated ...]") }
        .to_return(status: 200, body: bridge_response.to_json, headers: { "Content-Type" => "application/json" })

      result = described_class.new(youtube_url: valid_url).call
      expect(result[:clips].size).to eq(2)
    end
  end

  describe "error cases" do
    it "raises EmptyTranscriptError when transcript is empty" do
      allow(mock_yt_dlp).to receive(:fetch_transcript).with(valid_url).and_return({ segments: [] })

      expect {
        described_class.new(youtube_url: valid_url).call
      }.to raise_error(ClipFinderService::EmptyTranscriptError, /No transcript/)
    end

    it "raises RateLimitError when bridge returns rate_limit error_type" do
      bridge_response = { ok: false, error_type: "rate_limit", error: "Rate limit exceeded" }
      stub_request(:post, "http://localhost:9999/run")
        .to_return(status: 200, body: bridge_response.to_json, headers: { "Content-Type" => "application/json" })

      expect {
        described_class.new(youtube_url: valid_url).call
      }.to raise_error(ClipFinderService::RateLimitError, /rate limit/)
    end

    it "raises BridgeError when bridge fails with ok: false" do
      bridge_response = { ok: false, error: "Internal model error" }
      stub_request(:post, "http://localhost:9999/run")
        .to_return(status: 200, body: bridge_response.to_json, headers: { "Content-Type" => "application/json" })

      expect {
        described_class.new(youtube_url: valid_url).call
      }.to raise_error(ClipFinderService::BridgeError, /Bridge error/)
    end

    it "raises BridgeError when bridge is unreachable" do
      stub_request(:post, "http://localhost:9999/run").to_raise(Faraday::ConnectionFailed.new("Connection refused"))

      expect {
        described_class.new(youtube_url: valid_url).call
      }.to raise_error(ClipFinderService::BridgeError, /unreachable/)
    end

    it "raises BridgeError when bridge returns malformed JSON" do
      bridge_response = { ok: true, result: "not-json-at-all", cost_usd: 0.05 }
      stub_request(:post, "http://localhost:9999/run")
        .to_return(status: 200, body: bridge_response.to_json, headers: { "Content-Type" => "application/json" })

      expect {
        described_class.new(youtube_url: valid_url).call
      }.to raise_error(ClipFinderService::BridgeError, /parse/)
    end
  end
end
