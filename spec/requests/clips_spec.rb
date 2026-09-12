# frozen_string_literal: true

require "rails_helper"

RSpec.describe "Clips API", type: :request do
  let(:valid_url) { "https://www.youtube.com/watch?v=dQw4w9WgXcQ" }
  let(:sample_clips) do
    [
      {
        "start_sec" => 10,
        "end_sec" => 25,
        "title" => "Hook moment",
        "caption" => "Viral hook",
        "why" => "High energy",
        "rank" => 1,
        "recommended" => true
      },
      {
        "start_sec" => 60,
        "end_sec" => 75,
        "title" => "Punchline",
        "caption" => "Payoff",
        "why" => "Strong conclusion",
        "rank" => 2,
        "recommended" => false
      }
    ]
  end

  # ── POST /clips/transcript ──────────────────────────────────────────────────
  describe "POST /clips/transcript" do
    let(:yt_dlp) { instance_double(YtDlpService) }

    before do
      allow(YtDlpService).to receive(:new).and_return(yt_dlp)
    end

    it "returns 200 with segments on valid request" do
      segments = [
        { "start" => 0.0, "end" => 5.0, "text" => "Hello" },
        { "start" => 5.0, "end" => 10.0, "text" => "World" }
      ]
      allow(yt_dlp).to receive(:fetch_transcript).with(valid_url).and_return({ segments: segments })

      post "/clips/transcript", params: { youtube_url: valid_url }, as: :json
      expect(response).to have_http_status(:ok)
      body = JSON.parse(response.body)
      expect(body["segments"].size).to eq(2)
      expect(body["segments"][0]["text"]).to eq("Hello")
    end

    it "returns 400 Bad Request on command injection" do
      allow(yt_dlp).to receive(:fetch_transcript).and_raise(ArgumentError.new("URL contains prohibited characters"))

      post "/clips/transcript", params: { youtube_url: "https://youtube.com/watch?v=1; rm -rf /" }, as: :json
      expect(response).to have_http_status(:bad_request)
      body = JSON.parse(response.body)
      expect(body["error"] || body["detail"]).to be_present
    end

    it "returns 504 Gateway Timeout when transcript fetch times out" do
      allow(yt_dlp).to receive(:fetch_transcript).and_raise(YtDlpService::TimeoutError.new("timed out"))

      post "/clips/transcript", params: { youtube_url: valid_url }, as: :json
      expect(response).to have_http_status(:gateway_timeout)
    end

    it "returns 500 Internal Server Error when binary is missing or execution fails" do
      allow(yt_dlp).to receive(:fetch_transcript).and_raise(YtDlpService::BinaryNotFoundError.new("yt-dlp missing"))

      post "/clips/transcript", params: { youtube_url: valid_url }, as: :json
      expect(response).to have_http_status(:internal_server_error)
    end
  end


  # ── POST /clips/find-claude ─────────────────────────────────────────────────
  describe "POST /clips/find-claude" do
    let(:finder_double) { instance_double(ClipFinderService) }

    it "returns 200 with response shape on success" do
      result = {
        youtube_url: valid_url,
        clips: sample_clips,
        model: "claude-sonnet-4-6",
        cost_usd: 0.0512,
        cached_find: false
      }
      allow(ClipFinderService).to receive(:new).with(hash_including(youtube_url: valid_url)).and_return(finder_double)
      allow(finder_double).to receive(:call).and_return(result)

      post "/clips/find-claude", params: { youtube_url: valid_url, max_clips: 8 }, as: :json
      expect(response).to have_http_status(:ok)
      body = JSON.parse(response.body)
      expect(body["youtube_url"]).to eq(valid_url)
      expect(body["clips"].size).to eq(2)
      expect(body["model"]).to eq("claude-sonnet-4-6")
      expect(body["cost_usd"]).to eq(0.0512)
      expect(body["cached_find"]).to be(false)
    end

    it "returns 400 on invalid URL" do
      allow(ClipFinderService).to receive(:new).and_raise(ArgumentError.new("Invalid URL format"))

      post "/clips/find-claude", params: { youtube_url: "invalid-url" }, as: :json
      expect(response).to have_http_status(:bad_request)
    end

    it "returns 422 when no transcript is available" do
      allow(ClipFinderService).to receive(:new).and_return(finder_double)
      allow(finder_double).to receive(:call).and_raise(
        ClipFinderService::EmptyTranscriptError.new("No transcript/subtitles available for this video — clip-finder needs a transcript")
      )

      post "/clips/find-claude", params: { youtube_url: valid_url }, as: :json
      expect(response).to have_http_status(:unprocessable_content)
      body = JSON.parse(response.body)
      expect(body["detail"] || body["error"]).to include("No transcript")
    end

    it "returns 429 on bridge rate limit" do
      allow(ClipFinderService).to receive(:new).and_return(finder_double)
      allow(finder_double).to receive(:call).and_raise(
        ClipFinderService::RateLimitError.new("Claude usage/rate limit reached — please retry later")
      )

      post "/clips/find-claude", params: { youtube_url: valid_url }, as: :json
      expect(response).to have_http_status(:too_many_requests)
    end

    it "returns 502 on bridge error" do
      allow(ClipFinderService).to receive(:new).and_return(finder_double)
      allow(finder_double).to receive(:call).and_raise(
        ClipFinderService::BridgeError.new("Bridge error: model unavailable")
      )

      post "/clips/find-claude", params: { youtube_url: valid_url }, as: :json
      expect(response).to have_http_status(:bad_gateway)
    end

    it "supports cached find with force=false" do
      result = {
        youtube_url: valid_url,
        clips: sample_clips,
        model: "claude-sonnet-4-6",
        cost_usd: nil,
        cached_find: true
      }
      allow(ClipFinderService).to receive(:new).with(hash_including(youtube_url: valid_url, force: false)).and_return(finder_double)
      allow(finder_double).to receive(:call).and_return(result)

      post "/clips/find-claude", params: { youtube_url: valid_url }, as: :json
      expect(response).to have_http_status(:ok)
      body = JSON.parse(response.body)
      expect(body["cached_find"]).to be(true)
    end
  end

  # ── POST /clips/auto ────────────────────────────────────────────────────────
  describe "POST /clips/auto" do
    let(:finder_double) { instance_double(ClipFinderService) }
    let(:render_double) { instance_double(ClipRenderService) }
    let(:yt_dlp) { instance_double(YtDlpService) }

    before do
      allow(YtDlpService).to receive(:new).and_return(yt_dlp)
      allow(yt_dlp).to receive(:download).and_return("/tmp/fake_source.mp4")
    end

    it "finds clips and renders recommended clip in one call" do
      find_result = {
        youtube_url: valid_url,
        clips: sample_clips,
        model: "claude-sonnet-4-6",
        cost_usd: 0.05,
        cached_find: false,
        clip_find_id: 123
      }
      allow(ClipFinderService).to receive(:new).and_return(finder_double)
      allow(finder_double).to receive(:call).and_return(find_result)

      render_result = {
        status: "ok",
        video_path: "/data/renders/uuid-1/output.mp4",
        render_id: "uuid-1",
        clip: sample_clips.first
      }
      allow(ClipRenderService).to receive(:new).and_return(render_double)
      allow(render_double).to receive(:call).and_return(render_result)

      post "/clips/auto", params: { youtube_url: valid_url }, as: :json
      expect(response).to have_http_status(:ok)
      body = JSON.parse(response.body)
      expect(body["status"]).to eq("ok")
      expect(body["clip_find_id"]).to eq(123)
      expect(body["render_id"]).to eq("uuid-1")
      expect(body["video_path"]).to eq("/data/renders/uuid-1/output.mp4")
      expect(body["clip"]["title"]).to eq("Hook moment")
      expect(body["clip"]["recommended"]).to be(true)
      expect(body["cached_find"]).to be(false)
    end

    it "returns 422 with detail 'no_clips' when no clips found" do
      find_result = {
        youtube_url: valid_url,
        clips: [],
        model: "claude-sonnet-4-6",
        cost_usd: 0.01,
        cached_find: false
      }
      allow(ClipFinderService).to receive(:new).and_return(finder_double)
      allow(finder_double).to receive(:call).and_return(find_result)

      post "/clips/auto", params: { youtube_url: valid_url }, as: :json
      expect(response).to have_http_status(:unprocessable_content)
      body = JSON.parse(response.body)
      expect(body["detail"]).to eq("no_clips")
    end

    it "renders clip specified by explicit clip_index" do
      find_result = {
        youtube_url: valid_url,
        clips: sample_clips,
        model: "claude-sonnet-4-6",
        cost_usd: 0.05,
        cached_find: false,
        clip_find_id: 123
      }
      allow(ClipFinderService).to receive(:new).and_return(finder_double)
      allow(finder_double).to receive(:call).and_return(find_result)

      second_clip = sample_clips.second
      render_result = {
        status: "ok",
        video_path: "/data/renders/uuid-2/output.mp4",
        render_id: "uuid-2",
        clip: second_clip
      }
      allow(ClipRenderService).to receive(:new).with(hash_including(clip: second_clip)).and_return(render_double)
      allow(render_double).to receive(:call).and_return(render_result)

      post "/clips/auto", params: { youtube_url: valid_url, clip_index: 1 }, as: :json
      expect(response).to have_http_status(:ok)
      body = JSON.parse(response.body)
      expect(body["clip"]["title"]).to eq("Punchline")
      expect(body["clip"]["rank"]).to eq(2)
    end
  end

  # ── POST /clips/render ──────────────────────────────────────────────────────
  describe "POST /clips/render" do
    let(:render_double) { instance_double(ClipRenderService) }
    let(:yt_dlp) { instance_double(YtDlpService) }

    before do
      allow(YtDlpService).to receive(:new).and_return(yt_dlp)
      allow(yt_dlp).to receive(:download).and_return("/tmp/fake_source.mp4")
    end

    it "renders clip loaded from clip_find_id" do
      clip_find = ClipFind.create!(youtube_url: valid_url, clips: sample_clips)

      render_result = {
        status: "ok",
        video_path: "/data/renders/test-render/output.mp4",
        render_id: "test-render",
        clip: sample_clips.first
      }
      allow(ClipRenderService).to receive(:new).and_return(render_double)
      allow(render_double).to receive(:call).and_return(render_result)

      post "/clips/render", params: { clip_find_id: clip_find.id }, as: :json
      expect(response).to have_http_status(:ok)
      body = JSON.parse(response.body)
      expect(body["status"]).to eq("ok")
      expect(body["video_path"]).to eq("/data/renders/test-render/output.mp4")
      expect(body["render_id"]).to eq("test-render")
    end

    it "renders clip from inline youtube_url and clips array" do
      render_result = {
        status: "ok",
        video_path: "/data/renders/test-render/output.mp4",
        render_id: "test-render",
        clip: sample_clips.first
      }
      allow(ClipRenderService).to receive(:new).and_return(render_double)
      allow(render_double).to receive(:call).and_return(render_result)

      post "/clips/render", params: { youtube_url: valid_url, clips: sample_clips }, as: :json
      expect(response).to have_http_status(:ok)
      body = JSON.parse(response.body)
      expect(body["status"]).to eq("ok")
    end

    it "returns 404 when clip_find_id does not exist" do
      post "/clips/render", params: { clip_find_id: 999_999 }, as: :json
      expect(response).to have_http_status(:not_found)
    end

    it "returns 400 when neither clip_find_id nor youtube_url is provided" do
      post "/clips/render", params: { clips: sample_clips }, as: :json
      expect(response).to have_http_status(:bad_request)
    end

    it "returns 400 when clips array is empty" do
      post "/clips/render", params: { youtube_url: valid_url, clips: [] }, as: :json
      expect(response).to have_http_status(:bad_request)
    end
  end

  # ── GET /clips/renders/:id/download ─────────────────────────────────────────
  describe "GET /clips/renders/:id/download" do
    let(:render_id) { "12345678-1234-1234-1234-123456789abc" }
    let(:render_dir) { Rails.root.join("data", "renders", render_id) }
    let(:mp4_path) { File.join(render_dir, "output.mp4") }

    after do
      FileUtils.rm_rf(render_dir) if Dir.exist?(render_dir)
    end

    it "sends the mp4 file when it exists" do
      FileUtils.mkdir_p(render_dir)
      File.write(mp4_path, "fake-rendered-mp4-data")

      get "/clips/renders/#{render_id}/download"
      expect(response).to have_http_status(:ok)
      expect(response.body).to eq("fake-rendered-mp4-data")
    end

    it "returns 400 Bad Request on path traversal or invalid render_id" do
      get "/clips/renders/..-traversal-id/download"
      expect(response).to have_http_status(:bad_request)

      get "/clips/renders/invalid_id/download"
      expect(response).to have_http_status(:bad_request)
    end

    it "returns 404 Not Found when render file does not exist" do
      get "/clips/renders/#{render_id}/download"
      expect(response).to have_http_status(:not_found)
    end
  end

  # ── GET /dash/clip-finds ────────────────────────────────────────────────────
  describe "GET /dash/clip-finds" do
    it "returns paginated clip finds with rows, total, limit, and offset" do
      3.times do |i|
        ClipFind.create!(
          youtube_url: "https://www.youtube.com/watch?v=video_#{i}",
          clips: sample_clips,
          model: "claude-sonnet-4-6",
          cost_usd: 0.05
        )
      end

      get "/dash/clip-finds", params: { limit: 2, offset: 0 }
      expect(response).to have_http_status(:ok)
      body = JSON.parse(response.body)

      expect(body["total"]).to eq(3)
      expect(body["limit"]).to eq(2)
      expect(body["offset"]).to eq(0)
      expect(body["rows"].size).to eq(2)

      row = body["rows"].first
      expect(row["youtube_url"]).to be_present
      expect(row["clips"]).to be_an(Array)
      expect(row["clips"].size).to eq(2)
      expect(row["model"]).to eq("claude-sonnet-4-6")
      expect(row["cost_usd"]).to eq(0.05)
    end

    it "clamps limit to 1..200 and offset >= 0" do
      get "/dash/clip-finds", params: { limit: 500, offset: -5 }
      expect(response).to have_http_status(:ok)
      body = JSON.parse(response.body)
      expect(body["limit"]).to eq(200)
      expect(body["offset"]).to eq(0)
    end

    it "returns empty rows when database has no records" do
      get "/dash/clip-finds"
      expect(response).to have_http_status(:ok)
      body = JSON.parse(response.body)
      expect(body["rows"]).to eq([])
      expect(body["total"]).to eq(0)
    end
  end
end
