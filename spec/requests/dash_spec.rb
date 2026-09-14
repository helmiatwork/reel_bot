# frozen_string_literal: true

require "rails_helper"

RSpec.describe "Dashboards", type: :request do
  describe "GET /dash/services" do
    it "returns list of services with live and total counts" do
      fake_probe = {
        services: [
          { name: "postgres", port: 5432, up: true },
          { name: "openclaw", port: 18789, up: true },
          { name: "n8n", port: 5678, up: false },
          { name: "cliproxy", port: 8317, up: true },
          { name: "rails", port: 3000, up: true },
          { name: "arcreel", port: 1241, up: false }
        ],
        live: 4,
        total: 6
      }
      allow(Dash::ServiceProbe).to receive(:probe_all).and_return(fake_probe)

      get "/dash/services"

      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json["services"].size).to eq(6)
      expect(json["live"]).to eq(4)
      expect(json["total"]).to eq(6)
    end
  end

  describe "GET /dash/overview" do
    let!(:video_project) { VideoProject.create!(title: "Test Project", status: "draft") }

    before do
      PipelineRun.create!(
        video_project: video_project,
        run_id: "run-1",
        status: "done"
      )
      PipelineRun.create!(
        video_project: video_project,
        run_id: "run-2",
        status: "failed"
      )
      ClipFind.create!(
        youtube_url: "https://youtube.com/watch?v=123",
        clips: [ { "start" => 10, "end" => 30 } ]
      )
    end

    it "returns KPIs, series, movers, and channel without 500 when optional tables missing" do
      get "/dash/overview"

      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json).to have_key("kpis")
      expect(json).to have_key("series")
      expect(json).to have_key("movers")
      expect(json).to have_key("channel")

      kpis = json["kpis"]
      expect(kpis["produced"]).to eq(1)
      expect(kpis["clips"]).to eq(1)
      expect(kpis["sources"]).to eq(0)
      expect(kpis["formulas"]).to eq(0)
      expect(kpis["total_views"]).to be_a(Integer)

      expect(json["series"]).to be_an(Array)
      expect(json["movers"]).to be_an(Array)

      channel = json["channel"]
      expect(channel).to have_key("error")
      expect(channel["total_views"]).to eq(0)
      expect(channel["avg_view_pct"]).to eq(0)
      expect(channel["avg_duration"]).to eq(0)
      expect(channel["series"]).to eq([])
      expect(channel["top_videos"]).to eq([])
    end

    it "includes channel analytics when YouTubeService succeeds" do
      channel_data = {
        "total_views" => 5000,
        "avg_view_pct" => 65.5,
        "avg_duration" => 45,
        "series" => [ { "label" => "views channel", "points" => [ { "d" => "09-12", "v" => 500 } ] } ],
        "top_videos" => [ { "title" => "Top Short", "views" => 2500, "retention" => 70.0 } ]
      }
      allow_any_instance_of(YouTubeService).to receive(:channel_analytics).and_return(channel_data)

      get "/dash/overview"

      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json["channel"]["total_views"]).to eq(5000)
      expect(json["channel"]["top_videos"].first["title"]).to eq("Top Short")
    end

    it "handles YouTubeService QuotaError safely in channel analytics" do
      allow_any_instance_of(YouTubeService).to receive(:channel_analytics)
        .and_raise(YouTubeService::QuotaError.new("YouTube API quota exceeded"))

      get "/dash/overview"

      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json["channel"]["error"]).to eq("quota exceeded")
      expect(json["channel"]["total_views"]).to eq(0)
    end

    it "handles generic StandardError safely in channel analytics" do
      allow_any_instance_of(YouTubeService).to receive(:channel_analytics)
        .and_raise(StandardError.new("Network timeout"))

      get "/dash/overview"

      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json["channel"]["error"]).to eq("Network timeout")
      expect(json["channel"]["total_views"]).to eq(0)
    end

    context "when optional sources and performance_snapshots tables exist" do
      before do
        ActiveRecord::Base.connection.create_table :sources, force: true do |t|
          t.string :title
          t.integer :views_at_analysis
        end
        ActiveRecord::Base.connection.create_table :performance_snapshots, force: true do |t|
          t.string :subject_type
          t.bigint :subject_id
          t.integer :views
          t.datetime :captured_at
        end
        ActiveRecord::Base.connection.create_table :formulas, force: true do |t|
          t.string :name
        end

        ActiveRecord::Base.connection.execute(
          "INSERT INTO sources (id, title, views_at_analysis) VALUES (1, 'Source 1', 12000), (2, 'Source 2', 8000)"
        )
        ActiveRecord::Base.connection.execute(
          "INSERT INTO performance_snapshots (subject_type, subject_id, views, captured_at) " \
          "VALUES ('source', 1, 12000, '2026-09-12 10:00:00'), ('source', 2, 8000, '2026-09-12 10:00:00')"
        )
        ActiveRecord::Base.connection.execute("INSERT INTO formulas (name) VALUES ('Test Formula')")
      end

      after do
        ActiveRecord::Base.connection.drop_table :sources, if_exists: true
        ActiveRecord::Base.connection.drop_table :performance_snapshots, if_exists: true
        ActiveRecord::Base.connection.drop_table :formulas, if_exists: true
      end

      it "returns populated sources, formulas, total_views, series, and movers" do
        get "/dash/overview"

        expect(response).to have_http_status(:ok)
        json = JSON.parse(response.body)
        expect(json["kpis"]["sources"]).to eq(2)
        expect(json["kpis"]["formulas"]).to eq(1)
        expect(json["kpis"]["total_views"]).to eq(20000)
        expect(json["series"].size).to eq(2)
        expect(json["movers"].size).to eq(2)
        expect(json["movers"].first["title"]).to eq("Source 1")
        expect(json["movers"].first["views"]).to eq(12000)
      end
    end
  end

  describe "GET /dash/agents" do
    it "returns static roster JSON of 8 content-automation agents" do
      get "/dash/agents"

      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      agents = json["agents"]
      expect(agents.size).to eq(8)

      names = agents.map { |a| a["name"] }
      expect(names).to eq([
        "analyze",
        "analyze-senior",
        "clipfinder",
        "scriptwriter",
        "editor",
        "qcgate",
        "producer",
        "main"
      ])

      analyze = agents.find { |a| a["name"] == "analyze" }
      expect(analyze["role"]).to eq("Frame + audio breakdown (vision)")
      expect(analyze["model"]).to eq("gemini-2.5-flash-lite")

      opus = agents.find { |a| a["name"] == "analyze-senior" }
      expect(opus["role"]).to eq("Deep viral strategy")
      expect(opus["model"]).to eq("claude/opus")
    end
  end

  describe "GET /dash/table/:name" do
    it "returns 404 for unknown table" do
      get "/dash/table/nonexistent_table"

      expect(response).to have_http_status(:not_found)
      json = JSON.parse(response.body)
      expect(json["error"]).to eq("unknown table")
    end

    it "returns empty shell for allowed table when table does not exist in DB" do
      get "/dash/table/sources"

      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json).to eq({
        "columns" => [],
        "rows" => [],
        "total" => 0,
        "limit" => 25,
        "offset" => 0
      })
    end

    it "clamps limit between 1 and 100 and offset >= 0" do
      get "/dash/table/formulas?limit=500&offset=-10"

      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json["limit"]).to eq(100)
      expect(json["offset"]).to eq(0)

      get "/dash/table/formulas?limit=0&offset=15"

      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json["limit"]).to eq(1)
      expect(json["offset"]).to eq(15)
    end

    context "when table exists in DB" do
      before do
        ActiveRecord::Base.connection.create_table :sources, force: true do |t|
          t.string :title
          t.string :niche
          t.string :platform
          t.string :channel
          t.integer :views_at_analysis
          t.string :status
          t.string :youtube_url
          t.string :gen_prompt_format
        end
        ActiveRecord::Base.connection.execute(
          "INSERT INTO sources (title, niche, platform, channel, views_at_analysis, status, youtube_url, gen_prompt_format) " \
          "VALUES ('Video A', 'tech', 'youtube', 'TechChannel', 1000, 'ready', 'http://yt.com/a', 'json')"
        )
      end

      after do
        ActiveRecord::Base.connection.drop_table :sources, if_exists: true
      end

      it "returns paginated rows and total count" do
        get "/dash/table/sources"

        expect(response).to have_http_status(:ok)
        json = JSON.parse(response.body)
        expect(json["total"]).to eq(1)
        expect(json["rows"].size).to eq(1)
        expect(json["rows"].first["title"]).to eq("Video A")
        expect(json["columns"]).to include("id", "title", "views")
      end

      it "falls back to SELECT * when custom select query fails" do
        ActiveRecord::Base.connection.create_table :posts, force: true do |t|
          t.string :custom_content
        end
        ActiveRecord::Base.connection.execute("INSERT INTO posts (custom_content) VALUES ('hello')")

        get "/dash/table/posts"

        expect(response).to have_http_status(:ok)
        json = JSON.parse(response.body)
        expect(json["total"]).to eq(1)
        expect(json["columns"]).to include("id", "custom_content")
      ensure
        ActiveRecord::Base.connection.drop_table :posts, if_exists: true
      end
    end
  end

  describe "GET /dash/formula-performance" do
    it "returns rows: [] when formulas table does not exist" do
      get "/dash/formula-performance"

      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json).to eq({ "rows" => [] })
    end

    context "when formulas table exists" do
      before do
        ActiveRecord::Base.connection.create_table :formulas, force: true do |t|
          t.string :slug
          t.string :name
          t.string :best_for
        end
        ActiveRecord::Base.connection.execute("INSERT INTO formulas (slug, name, best_for) VALUES ('teaser', 'Teaser Hook', 'shorts')")
      end

      after do
        ActiveRecord::Base.connection.drop_table :formulas, if_exists: true
      end

      it "returns formula performance rows" do
        get "/dash/formula-performance"

        expect(response).to have_http_status(:ok)
        json = JSON.parse(response.body)
        expect(json["rows"]).to be_an(Array)
        expect(json["rows"].size).to eq(1)
        expect(json["rows"].first["slug"]).to eq("teaser")
      end

      it "joins sources table when sources table also exists" do
        ActiveRecord::Base.connection.create_table :sources, force: true do |t|
          t.bigint :formula_id
          t.integer :views_at_analysis
        end
        formula_id = ActiveRecord::Base.connection.select_value("SELECT id FROM formulas LIMIT 1")
        ActiveRecord::Base.connection.execute(
          "INSERT INTO sources (formula_id, views_at_analysis) VALUES (#{formula_id}, 1000)"
        )

        get "/dash/formula-performance"

        expect(response).to have_http_status(:ok)
        json = JSON.parse(response.body)
        expect(json["rows"].first["n"]).to eq(1)
        expect(json["rows"].first["total_views"]).to eq(1000)
      ensure
        ActiveRecord::Base.connection.drop_table :sources, if_exists: true
      end

      it "rescues errors and returns empty rows" do
        allow(ActiveRecord::Base.connection).to receive(:select_all).and_raise(ActiveRecord::StatementInvalid.new("DB error"))

        get "/dash/formula-performance"

        expect(response).to have_http_status(:ok)
        json = JSON.parse(response.body)
        expect(json).to eq({ "rows" => [] })
      end
    end
  end

  describe "GET /dash/cost" do
    context "when CLIPROXY_MGMT_KEY is not configured" do
      around do |example|
        old_key = ENV["CLIPROXY_MGMT_KEY"]
        ENV.delete("CLIPROXY_MGMT_KEY")
        example.run
      ensure
        ENV["CLIPROXY_MGMT_KEY"] = old_key
      end

      it "returns fallback shell without raising error" do
        get "/dash/cost"

        expect(response).to have_http_status(:ok)
        json = JSON.parse(response.body)
        expect(json["providers"]).to eq([])
        expect(json["series"]).to eq([])
        expect(json["totals"]["requests"]).to eq(0)
        expect(json["totals"]["est_per_request"]).to eq(0.0015)
        expect(json["error"]).to be_present
      end
    end

    context "when CLIPROXY_MGMT_KEY is configured" do
      around do |example|
        old_key = ENV["CLIPROXY_MGMT_KEY"]
        old_url = ENV["CLIPROXY_URL"]
        ENV["CLIPROXY_MGMT_KEY"] = "mgmt-secret-key"
        ENV["CLIPROXY_URL"] = "http://localhost:8317/v1"
        example.run
      ensure
        ENV["CLIPROXY_MGMT_KEY"] = old_key
        ENV["CLIPROXY_URL"] = old_url
      end

      it "queries Cliproxy management API and returns aggregated stats without exposing upstream keys" do
        cliproxy_response = {
          "openai" => {
            "sk-secret-upstream-key-1" => {
              "success" => 10,
              "failed" => 2,
              "recent_requests" => [
                { "time" => "2026-09-12T10:00:00Z", "success" => 5, "failed" => 1 },
                { "time" => "2026-09-12T11:00:00Z", "success" => 5, "failed" => 1 }
              ]
            }
          },
          "anthropic" => {
            "sk-secret-upstream-key-2" => {
              "success" => 20,
              "failed" => 0,
              "recent_requests" => []
            }
          }
        }
        stub_request(:get, "http://localhost:8317/v0/management/api-key-usage")
          .with(headers: { "Authorization" => "Bearer mgmt-secret-key" })
          .to_return(status: 200, body: cliproxy_response.to_json, headers: { "Content-Type" => "application/json" })

        get "/dash/cost"

        expect(response).to have_http_status(:ok)
        json = JSON.parse(response.body)
        expect(json["providers"].size).to eq(2)
        expect(json["providers"].map { |p| p["name"] }).to contain_exactly("openai", "anthropic")
        expect(response.body).not_to include("sk-secret-upstream-key-1")
        expect(response.body).not_to include("sk-secret-upstream-key-2")

        totals = json["totals"]
        expect(totals["requests"]).to eq(32)
        expect(totals["success"]).to eq(30)
        expect(totals["failed"]).to eq(2)
        expect(totals["est_cost"]).to be > 0
      end

      it "returns fallback shell when Cliproxy request fails" do
        stub_request(:get, "http://localhost:8317/v0/management/api-key-usage")
          .to_raise(Errno::ECONNREFUSED)

        get "/dash/cost"

        expect(response).to have_http_status(:ok)
        json = JSON.parse(response.body)
        expect(json["error"]).to be_present
        expect(json["totals"]["requests"]).to eq(0)
      end
    end
  end

  describe "GET /dash/token-usage" do
    it "returns fallback shell when api_usage table does not exist" do
      get "/dash/token-usage"

      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json["rows"]).to eq([])
      expect(json["series"]).to eq([])
      expect(json["by_agent"]).to eq([])
      expect(json["totals"]).to eq({ "cost_usd" => 0.0, "total_tokens" => 0, "calls" => 0 })
    end

    context "when api_usage table exists" do
      before do
        ActiveRecord::Base.connection.create_table :api_usage, force: true do |t|
          t.string :model
          t.integer :prompt_tokens
          t.integer :completion_tokens
          t.integer :total_tokens
          t.string :agent
          t.decimal :cost_usd, precision: 10, scale: 5
          t.datetime :created_at
        end
        ActiveRecord::Base.connection.execute(
          "INSERT INTO api_usage (model, prompt_tokens, completion_tokens, total_tokens, agent, cost_usd, created_at) " \
          "VALUES ('gemini-2.5-flash', 1000, 500, 1500, 'scriptwriter', 0.00155, '2026-09-12 10:00:00')"
        )
      end

      after do
        ActiveRecord::Base.connection.drop_table :api_usage, if_exists: true
      end

      it "returns token usage aggregated rows, series, and by_agent" do
        get "/dash/token-usage"

        expect(response).to have_http_status(:ok)
        json = JSON.parse(response.body)
        expect(json["rows"].size).to eq(1)
        expect(json["rows"].first["model"]).to eq("gemini-2.5-flash")
        expect(json["rows"].first["total_tokens"]).to eq(1500)
        expect(json["by_agent"].size).to eq(1)
        expect(json["by_agent"].first["agent"]).to eq("scriptwriter")
        expect(json["totals"]["total_tokens"]).to eq(1500)
        expect(json["totals"]["calls"]).to eq(1)
      end

      it "rescues errors and returns fallback shell" do
        allow(ActiveRecord::Base.connection).to receive(:select_rows).and_raise(ActiveRecord::StatementInvalid.new("DB error"))

        get "/dash/token-usage"

        expect(response).to have_http_status(:ok)
        json = JSON.parse(response.body)
        expect(json["rows"]).to eq([])
      end
    end
  end

  describe "GET /dash/analysis" do
    it "returns empty rows and total 0 when video_analysis table does not exist" do
      get "/dash/analysis"

      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json).to eq({
        "rows" => [],
        "total" => 0,
        "limit" => 25,
        "offset" => 0
      })
    end

    it "clamps limit between 1 and 200" do
      get "/dash/analysis?limit=500&offset=-2"

      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json["limit"]).to eq(200)
      expect(json["offset"]).to eq(0)
    end

    context "when video_analysis table exists" do
      before do
        ActiveRecord::Base.connection.create_table :video_analysis, force: true do |t|
          t.text :youtube_url
          t.string :intent
          t.string :hook
          t.string :structure
          t.float :retention
          t.text :tags
          t.string :model
          t.decimal :cost_usd, precision: 10, scale: 5
          t.datetime :created_at
        end
        ActiveRecord::Base.connection.execute(
          "INSERT INTO video_analysis (youtube_url, intent, hook, structure, retention, tags, model, cost_usd, created_at) " \
          "VALUES ('https://youtu.be/xyz', 'entertain', 'shock hook', '3-act', 75.5, '[\"gaming\", \"fun\"]', 'gemini-flash', 0.002, '2026-09-12 12:00:00'), " \
          "('https://youtu.be/abc', 'educate', 'question', 'linear', 60.0, '{bad_json', 'gemini-flash', NULL, NULL), " \
          "('https://youtu.be/def', 'promo', 'cta', 'linear', 50.0, NULL, 'gemini-flash', NULL, NULL)"
        )
      end

      after do
        ActiveRecord::Base.connection.drop_table :video_analysis, if_exists: true
      end

      it "returns video analysis rows with parsed tags array and handles malformed or nil tags" do
        get "/dash/analysis"

        expect(response).to have_http_status(:ok)
        json = JSON.parse(response.body)
        expect(json["total"]).to eq(3)
        expect(json["rows"].size).to eq(3)

        row1 = json["rows"].find { |r| r["youtube_url"] == "https://youtu.be/xyz" }
        expect(row1["tags"]).to eq([ "gaming", "fun" ])
        expect(row1["cost_usd"]).to eq(0.002)

        row2 = json["rows"].find { |r| r["youtube_url"] == "https://youtu.be/abc" }
        expect(row2["tags"]).to eq([])

        row3 = json["rows"].find { |r| r["youtube_url"] == "https://youtu.be/def" }
        expect(row3["tags"]).to eq([])
      end

      it "rescues errors and returns empty rows" do
        allow(ActiveRecord::Base.connection).to receive(:select_all).and_raise(ActiveRecord::StatementInvalid.new("DB error"))

        get "/dash/analysis"

        expect(response).to have_http_status(:ok)
        json = JSON.parse(response.body)
        expect(json["rows"]).to eq([])
      end
    end
  end

  describe "POST /dash/restart/:service and POST /dash/restart-all" do
    let(:auth_token) { "secret-pipeline-token" }
    let(:auth_headers) { { "X-API-Key" => auth_token } }

    around do |example|
      old_key = ENV["PIPELINE_API_KEY"]
      ENV["PIPELINE_API_KEY"] = auth_token
      example.run
    ensure
      ENV["PIPELINE_API_KEY"] = old_key
    end

    describe "API key authorization (fail-closed)" do
      it "rejects requests with missing X-API-Key header when PIPELINE_API_KEY is set" do
        post "/dash/restart/openclaw"

        expect(response).to have_http_status(:unauthorized)
        json = JSON.parse(response.body)
        expect(json["error"]).to eq("invalid API key")
      end

      it "rejects requests with invalid X-API-Key header" do
        post "/dash/restart/openclaw", headers: { "X-API-Key" => "wrong-key" }

        expect(response).to have_http_status(:unauthorized)
        json = JSON.parse(response.body)
        expect(json["error"]).to eq("invalid API key")
      end

      it "allows requests with valid X-API-Key header" do
        post "/dash/restart/openclaw", headers: auth_headers

        expect(response).to have_http_status(:ok)
        json = JSON.parse(response.body)
        expect(json["service"]).to eq("openclaw")
        expect(json["status"]).to eq("restarted")
      end

      context "when PIPELINE_API_KEY is not set or blank" do
        around do |example|
          old_key = ENV["PIPELINE_API_KEY"]
          ENV.delete("PIPELINE_API_KEY")
          example.run
        ensure
          ENV["PIPELINE_API_KEY"] = old_key
        end

        it "rejects requests without X-API-Key header (fail-closed)" do
          post "/dash/restart/cliproxy"

          expect(response).to have_http_status(:unauthorized)
          json = JSON.parse(response.body)
          expect(json["error"]).to eq("invalid API key")
        end

        it "rejects requests even if X-API-Key header is present (fail-closed)" do
          post "/dash/restart/cliproxy", headers: { "X-API-Key" => "any-value" }

          expect(response).to have_http_status(:unauthorized)
          json = JSON.parse(response.body)
          expect(json["error"]).to eq("invalid API key")
        end
      end
    end

    describe "service validation" do
      it "rejects restarting pipeline-api (status 400)" do
        post "/dash/restart/pipeline-api", headers: auth_headers

        expect(response).to have_http_status(:bad_request)
        json = JSON.parse(response.body)
        expect(json["error"]).to match(/cannot restart pipeline-api/i)
      end

      it "rejects restarting rails (status 400)" do
        post "/dash/restart/rails", headers: auth_headers

        expect(response).to have_http_status(:bad_request)
        json = JSON.parse(response.body)
        expect(json["error"]).to match(/cannot restart rails/i)
      end

      it "rejects unknown service (status 400)" do
        post "/dash/restart/unknown_service", headers: auth_headers

        expect(response).to have_http_status(:bad_request)
        json = JSON.parse(response.body)
        expect(json["error"]).to eq("unknown service")
      end

      it "returns unsupported_native for postgres" do
        post "/dash/restart/postgres", headers: auth_headers

        expect(response).to have_http_status(:ok)
        json = JSON.parse(response.body)
        expect(json["service"]).to eq("postgres")
        expect(json["status"]).to eq("unsupported_native")
      end

      it "returns unsupported_native for n8n" do
        post "/dash/restart/n8n", headers: auth_headers

        expect(response).to have_http_status(:ok)
        json = JSON.parse(response.body)
        expect(json["service"]).to eq("n8n")
        expect(json["status"]).to eq("unsupported_native")
      end

      it "returns restarted for restartable service arcreel in test" do
        post "/dash/restart/arcreel", headers: auth_headers

        expect(response).to have_http_status(:ok)
        json = JSON.parse(response.body)
        expect(json["service"]).to eq("arcreel")
        expect(json["status"]).to eq("restarted")
      end
    end

    context "when running in non-test environment" do
      before do
        allow(Rails.env).to receive(:test?).and_return(false)
      end

      it "executes process kill and spawn for restartable service with hardened array syntax" do
        allow_any_instance_of(Dash::ProcessManager).to receive(:system).with("pkill", "-f", "openclaw gateway").and_return(true)
        expect(Process).to receive(:spawn).with("/bin/bash", "-c", "openclaw gateway --port 18789", out: File::NULL, err: File::NULL)

        post "/dash/restart/openclaw", headers: auth_headers

        expect(response).to have_http_status(:ok)
        json = JSON.parse(response.body)
        expect(json["service"]).to eq("openclaw")
        expect(json["status"]).to eq("restarted")
      end

      it "returns error status when process spawn fails" do
        allow_any_instance_of(Dash::ProcessManager).to receive(:system).with("pkill", "-f", "openclaw gateway").and_return(true)
        allow(Process).to receive(:spawn).and_raise(Errno::ENOENT.new("spawn error"))

        post "/dash/restart/openclaw", headers: auth_headers

        expect(response).to have_http_status(:ok)
        json = JSON.parse(response.body)
        expect(json["service"]).to eq("openclaw")
        expect(json["status"]).to eq("error")
      end
    end

    describe "POST /dash/restart-all" do
      it "restarts all restartable services and reports results" do
        post "/dash/restart-all", headers: auth_headers

        expect(response).to have_http_status(:ok)
        json = JSON.parse(response.body)
        expect(json).to have_key("results")
        expect(json).to have_key("restarted")

        services = json["results"].map { |r| r["service"] }
        expect(services).to contain_exactly("postgres", "openclaw", "cliproxy", "n8n", "arcreel")
        expect(json["restarted"]).to eq(3) # openclaw, cliproxy, arcreel
      end
    end
  end
end
