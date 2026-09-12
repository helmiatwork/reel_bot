# frozen_string_literal: true

class DashController < ApplicationController
  protect_from_forgery with: :null_session
  skip_before_action :verify_authenticity_token, raise: false

  before_action :verify_admin_key!, only: %i[restart_service restart_all]

  ALLOWED_TABLES = {
    "sources" => "SELECT id, COALESCE(title,'-') title, COALESCE(niche,'-') niche, COALESCE(platform,'-') platform, " \
                 "COALESCE(channel,'-') channel, COALESCE(views_at_analysis,0) views, status, youtube_url, " \
                 "COALESCE(gen_prompt_format, '') gen_prompt_format FROM sources ORDER BY id DESC",
    "formulas" => "SELECT id, slug, name, COALESCE(best_for,'-') best_for FROM formulas ORDER BY id",
    "posts" => "SELECT id, platform, COALESCE(status,'-') status, COALESCE(external_url,'-') url, " \
               "scheduled_at, posted_at FROM posts ORDER BY id DESC",
    "clips" => "SELECT id, source_id, start_sec, end_sec, COALESCE(presenter_gender,'-') gender, " \
               "COALESCE(age_bracket,'-') age, COALESCE(activity,'-') activity, COALESCE(hook_score,0) hook " \
               "FROM clips ORDER BY id DESC"
  }.freeze

  AGENTS_ROSTER = Dash::Constants::AGENTS_ROSTER
  TOKEN_PRICES = Dash::Constants::TOKEN_PRICES
  DEFAULT_TOKEN_PRICE = Dash::Constants::DEFAULT_TOKEN_PRICE

  def overview
    render json: {
      kpis: build_overview_kpis,
      series: build_overview_series,
      movers: build_overview_movers,
      channel: fetch_channel_analytics
    }
  end

  def services
    render json: Dash::ServiceProbe.probe_all
  end

  def agents
    render json: { agents: AGENTS_ROSTER }
  end

  def table
    table_name = params[:name].to_s
    return render json: { error: "unknown table" }, status: :not_found unless ALLOWED_TABLES.key?(table_name)

    limit = params[:limit].present? ? params[:limit].to_i.clamp(1, 100) : 25
    offset = params[:offset].present? ? [ params[:offset].to_i, 0 ].max : 0

    unless table_exists?(table_name)
      return render json: { columns: [], rows: [], total: 0, limit: limit, offset: offset }
    end

    total = ActiveRecord::Base.connection.select_value("SELECT count(*) FROM #{table_name}").to_i
    result = fetch_paginated_table(table_name, limit, offset)

    render json: {
      columns: result.columns,
      rows: result.to_a,
      total: total,
      limit: limit,
      offset: offset
    }
  end

  def formula_performance
    return render json: { rows: [] } unless table_exists?("formulas")

    query = if table_exists?("sources")
              "SELECT f.slug, f.name, count(s.id) n, " \
              "COALESCE(round(avg(s.views_at_analysis)),0) avg_views, " \
              "COALESCE(sum(s.views_at_analysis),0) total_views, " \
              "COALESCE(max(s.views_at_analysis),0) best_views " \
              "FROM formulas f LEFT JOIN sources s ON s.formula_id = f.id " \
              "GROUP BY f.id, f.slug, f.name ORDER BY avg_views DESC NULLS LAST"
    else
              "SELECT f.slug, f.name, 0 AS n, 0 AS avg_views, 0 AS total_views, 0 AS best_views " \
              "FROM formulas f GROUP BY f.id, f.slug, f.name"
    end

    rows = ActiveRecord::Base.connection.select_all(query).map do |r|
      {
        "slug" => r["slug"],
        "name" => r["name"],
        "n" => r["n"].to_i,
        "avg_views" => r["avg_views"].to_i,
        "total_views" => r["total_views"].to_i,
        "best_views" => r["best_views"].to_i
      }
    end

    render json: { rows: rows }
  rescue StandardError => e
    Rails.logger.error("[formula_performance] #{e.class}: #{e.message}")
    render json: { rows: [] }
  end

  def cost
    render json: Dash::CliproxyClient.fetch_cost
  end

  def token_usage
    fallback = { "rows" => [], "series" => [], "by_agent" => [],
                 "totals" => { "cost_usd" => 0.0, "total_tokens" => 0, "calls" => 0 } }
    return render json: fallback unless table_exists?("api_usage")

    render json: build_token_usage_stats(fallback)
  rescue StandardError => e
    Rails.logger.error("[token_usage] #{e.class}: #{e.message}")
    render json: fallback
  end

  def analysis
    limit = params[:limit].present? ? params[:limit].to_i.clamp(1, 200) : 25
    offset = params[:offset].present? ? [ params[:offset].to_i, 0 ].max : 0

    unless table_exists?("video_analysis")
      return render json: { rows: [], total: 0, limit: limit, offset: offset }
    end

    total = ActiveRecord::Base.connection.select_value("SELECT count(*) FROM video_analysis").to_i
    rows = fetch_analysis_rows(limit, offset)

    render json: { rows: rows, total: total, limit: limit, offset: offset }
  rescue StandardError => e
    Rails.logger.error("[analysis] #{e.class}: #{e.message}")
    render json: { rows: [], total: 0, limit: limit, offset: offset }
  end

  def restart_service
    service = params[:service].to_s.strip
    if Dash::ProcessManager.forbidden?(service)
      return render json: { error: "cannot restart #{service} from itself" }, status: :bad_request
    end

    unless Dash::ProcessManager.restartable?(service)
      return render json: { error: "unknown service" }, status: :bad_request
    end

    result = Dash::ProcessManager.restart_one(service)
    render json: { service: service, **result }
  end

  def restart_all
    render json: Dash::ProcessManager.restart_all
  end

  private

  def verify_admin_key!
    env_key = ENV["PIPELINE_API_KEY"].to_s.strip
    header_key = request.headers["X-API-Key"].to_s.strip

    if env_key.present? && header_key.present? && ActiveSupport::SecurityUtils.secure_compare(header_key, env_key)
      return
    end

    render json: { error: "invalid API key" }, status: :unauthorized
  end

  def table_exists?(table_name)
    return false if table_name.blank?

    ActiveRecord::Base.connection.table_exists?(table_name)
  rescue StandardError
    false
  end

  def build_overview_kpis
    sources_count = if table_exists?("sources")
                      ActiveRecord::Base.connection.select_value("SELECT count(*) FROM sources").to_i
    else
                      0
    end
    formulas_count = if table_exists?("formulas")
                       ActiveRecord::Base.connection.select_value("SELECT count(*) FROM formulas").to_i
    else
                       0
    end
    clips_count = begin
      ClipFind.count
    rescue StandardError
      0
    end
    produced_count = begin
      PipelineRun.where(status: "done").count
    rescue StandardError
      0
    end

    {
      "sources" => sources_count,
      "total_views" => calculate_total_views,
      "produced" => produced_count,
      "formulas" => formulas_count,
      "clips" => clips_count
    }
  end

  def calculate_total_views
    if table_exists?("performance_snapshots")
      ActiveRecord::Base.connection.select_value(
        "SELECT COALESCE(sum(v),0) FROM (SELECT DISTINCT ON (subject_type,subject_id) views v " \
        "FROM performance_snapshots ORDER BY subject_type,subject_id,captured_at DESC) t"
      ).to_i
    elsif table_exists?("analytics_snapshots")
      AnalyticsSnapshot.sum(:views).to_i
    else
      0
    end
  rescue StandardError
    0
  end

  def build_overview_series
    return [] unless table_exists?("sources") && table_exists?("performance_snapshots")

    series = []
    top_sources = ActiveRecord::Base.connection.select_rows(
      "SELECT s.id, COALESCE(s.title,'source '||s.id) FROM sources s " \
      "JOIN performance_snapshots p ON p.subject_type='source' AND p.subject_id=s.id " \
      "GROUP BY s.id ORDER BY max(p.views) DESC NULLS LAST LIMIT 2"
    )
    top_sources.each do |sid, title|
      pts = ActiveRecord::Base.connection.select_rows(
        ActiveRecord::Base.sanitize_sql_array([
          "SELECT to_char(captured_at,'MM-DD') d, max(views) v FROM performance_snapshots " \
          "WHERE subject_type='source' AND subject_id=? GROUP BY d ORDER BY d", sid
        ])
      )
      series << {
        "label" => (title.to_s)[0..27],
        "points" => pts.map { |d, v| { "d" => d, "v" => v.to_i } }
      }
    end
    series
  rescue StandardError
    []
  end

  def build_overview_movers
    return [] unless table_exists?("sources")

    movers_rows = ActiveRecord::Base.connection.select_rows(
      "SELECT COALESCE(title,'source '||id), COALESCE(views_at_analysis,0) " \
      "FROM sources ORDER BY views_at_analysis DESC NULLS LAST LIMIT 5"
    )
    movers_rows.map { |t, v| { "title" => (t.to_s)[0..47], "views" => v.to_i } }
  rescue StandardError
    []
  end

  def fetch_channel_analytics
    error_shell = {
      "error" => "",
      "total_views" => 0,
      "avg_view_pct" => 0,
      "avg_duration" => 0,
      "series" => [],
      "top_videos" => []
    }
    YouTubeService.new.channel_analytics
  rescue YouTubeService::NotConfigured
    error_shell.merge("error" => "youtube api key not set")
  rescue YouTubeService::QuotaError
    error_shell.merge("error" => "quota exceeded")
  rescue StandardError => e
    error_shell.merge("error" => e.message)
  end

  def fetch_paginated_table(table_name, limit, offset)
    select_sql = ALLOWED_TABLES[table_name]
    ActiveRecord::Base.transaction(requires_new: true) do
      ActiveRecord::Base.connection.select_all("#{select_sql} LIMIT #{limit} OFFSET #{offset}")
    end
  rescue StandardError
    ActiveRecord::Base.connection.select_all("SELECT * FROM #{table_name} LIMIT #{limit} OFFSET #{offset}")
  end


  def build_token_usage_stats(fallback)
    rows_data = ActiveRecord::Base.connection.select_rows(
      "SELECT model, COALESCE(sum(prompt_tokens),0), COALESCE(sum(completion_tokens),0), " \
      "COALESCE(sum(total_tokens),0), count(*) FROM api_usage " \
      "GROUP BY model ORDER BY sum(total_tokens) DESC NULLS LAST"
    )

    rows = []
    tot_cost = 0.0
    tot_tok = 0
    tot_calls = 0

    rows_data.each do |m, pt, ct, tt, n|
      pin, pout = TOKEN_PRICES[m] || DEFAULT_TOKEN_PRICE
      cost = ((pt.to_i / 1_000_000.0) * pin) + ((ct.to_i / 1_000_000.0) * pout)
      rows << {
        "model" => m,
        "prompt_tokens" => pt.to_i,
        "completion_tokens" => ct.to_i,
        "total_tokens" => tt.to_i,
        "calls" => n.to_i,
        "cost_usd" => cost.round(4)
      }
      tot_cost += cost
      tot_tok += tt.to_i
      tot_calls += n.to_i
    end

    series_data = ActiveRecord::Base.connection.select_rows(
      "SELECT to_char(created_at,'MM-DD') d, COALESCE(sum(total_tokens),0) " \
      "FROM api_usage GROUP BY d ORDER BY d"
    )
    series = series_data.map { |d, t| { "d" => d, "tokens" => t.to_i } }

    by_agent_data = ActiveRecord::Base.connection.select_rows(
      "SELECT agent, count(*), COALESCE(sum(total_tokens),0), COALESCE(sum(cost_usd),0) " \
      "FROM api_usage GROUP BY agent ORDER BY COALESCE(sum(cost_usd),0) DESC"
    )
    by_agent = by_agent_data.map do |agent, calls, tokens, cost|
      {
        "agent" => agent,
        "calls" => calls.to_i,
        "total_tokens" => tokens.to_i,
        "cost_usd" => cost.to_f.round(4)
      }
    end

    {
      "rows" => rows,
      "series" => series,
      "by_agent" => by_agent,
      "totals" => {
        "cost_usd" => tot_cost.round(4),
        "total_tokens" => tot_tok,
        "calls" => tot_calls
      }
    }
  rescue StandardError => e
    Rails.logger.error("[build_token_usage_stats] #{e.class}: #{e.message}")
    fallback
  end

  def fetch_analysis_rows(limit, offset)
    res = ActiveRecord::Base.connection.select_all(
      "SELECT id, youtube_url, intent, hook, structure, retention, tags, model, " \
      "cost_usd, created_at FROM video_analysis ORDER BY id DESC LIMIT #{limit} OFFSET #{offset}"
    )
    res.map do |row|
      tags = row["tags"]
      tags = if tags.is_a?(String)
               begin
                 JSON.parse(tags)
               rescue StandardError
                 []
               end
      elsif tags.is_a?(Array)
               tags
      else
               []
      end

      row["tags"] = tags
      row["cost_usd"] = row["cost_usd"]&.to_f
      row["created_at"] = row["created_at"]&.iso8601 if row["created_at"].respond_to?(:iso8601)
      row
    end
  end
end
