# frozen_string_literal: true

class ClipsController < ApplicationController
  protect_from_forgery with: :null_session
  skip_before_action :verify_authenticity_token, raise: false

  rescue_from ArgumentError, with: :bad_request
  rescue_from ActiveRecord::RecordNotFound, with: :not_found
  rescue_from ClipFinderService::EmptyTranscriptError, with: :unprocessable_content
  rescue_from ClipFinderService::RateLimitError, with: :rate_limited
  rescue_from ClipFinderService::BridgeError, with: :bridge_error
  rescue_from YtDlpService::TimeoutError, with: :gateway_timeout
  rescue_from ClipRenderService::TimeoutError, with: :gateway_timeout
  rescue_from Timeout::Error, with: :gateway_timeout
  rescue_from YtDlpService::BinaryNotFoundError, with: :internal_server_error
  rescue_from ClipRenderService::BinaryNotFoundError, with: :internal_server_error
  rescue_from YtDlpService::ExecutionError, with: :internal_server_error
  rescue_from ClipRenderService::ExecutionError, with: :internal_server_error

  def transcript
    url = params[:youtube_url].presence || raise(ArgumentError, "youtube_url is required")
    result = YtDlpService.new.fetch_transcript(url)
    render json: result, status: :ok
  end

  def find_claude
    url = params[:youtube_url].presence || raise(ArgumentError, "youtube_url is required")
    force = ActiveModel::Type::Boolean.new.cast(params[:force]) || false
    result = ClipFinderService.new(
      youtube_url: url,
      max_clips: params[:max_clips],
      model: params[:model],
      force: force
    ).call

    render json: result, status: :ok
  end

  def auto
    url = params[:youtube_url].presence || raise(ArgumentError, "youtube_url is required")
    force = ActiveModel::Type::Boolean.new.cast(params[:force]) || false

    find_result = ClipFinderService.new(
      youtube_url: url,
      max_clips: params[:max_clips],
      model: params[:model],
      force: force
    ).call

    clips = find_result[:clips] || []
    if clips.empty?
      return render json: { detail: "no_clips", error: "No clips found" }, status: :unprocessable_content
    end

    chosen_clip = select_clip(clips, params[:clip_index])
    source_path = YtDlpService.new.download(url)
    render_result = ClipRenderService.new(input_path: source_path, clip: chosen_clip).call

    render json: {
      status: "ok",
      clip_find_id: find_result[:clip_find_id],
      render_id: render_result[:render_id],
      video_path: render_result[:video_path],
      clip: render_result[:clip],
      cached_find: find_result[:cached_find]
    }, status: :ok
  end

  def render_clip
    youtube_url = params[:youtube_url]
    clips = params[:clips]

    if params[:clip_find_id].present?
      clip_find = ClipFind.find(params[:clip_find_id])
      youtube_url = clip_find.youtube_url
      clips = clip_find.clips
    end

    if youtube_url.blank?
      return render json: { error: "youtube_url required", detail: "youtube_url required" }, status: :bad_request
    end

    if clips.blank?
      return render json: { error: "no clips provided", detail: "no clips provided" }, status: :bad_request
    end

    chosen_clip = select_clip(clips, params[:clip_index])
    source_path = YtDlpService.new.download(youtube_url)
    render_result = ClipRenderService.new(input_path: source_path, clip: chosen_clip).call

    render json: {
      status: "ok",
      video_path: render_result[:video_path],
      render_id: render_result[:render_id],
      clip: render_result[:clip]
    }, status: :ok
  end

  def download_render
    render_id = params[:id].to_s

    if render_id.include?("..") || render_id.include?("/") || render_id.include?("\\")
      return render json: { error: "Path traversal not allowed", detail: "Path traversal not allowed" }, status: :bad_request
    end

    unless render_id.match?(/\A[a-f0-9\-]{36}\z/i)
      return render json: { error: "Invalid render_id", detail: "Invalid render_id" }, status: :bad_request
    end

    renders_base = Rails.root.join("data", "renders").cleanpath
    mp4_file = renders_base.join(render_id, "output.mp4").cleanpath

    unless mp4_file.to_s.start_with?(renders_base.to_s)
      return render json: { error: "Path traversal not allowed", detail: "Path traversal not allowed" }, status: :bad_request
    end

    unless File.exist?(mp4_file)
      return render json: { error: "Render not found", detail: "Render not found" }, status: :not_found
    end

    send_file mp4_file, type: "video/mp4", filename: "clip_#{render_id[0...8]}.mp4", disposition: "attachment"
  end

  def dash_clip_finds
    limit = params.fetch(:limit, 25).to_i.clamp(1, 200)
    offset = [ params.fetch(:offset, 0).to_i, 0 ].max

    total = ClipFind.count
    records = ClipFind.recent.limit(limit).offset(offset)

    rows = records.map do |r|
      parsed_clips = r.clips.is_a?(String) ? JSON.parse(r.clips) : (r.clips || [])
      {
        id: r.id,
        youtube_url: r.youtube_url,
        clips: parsed_clips,
        model: r.model,
        cost_usd: r.cost_usd&.to_f,
        created_at: r.created_at&.iso8601
      }
    end

    render json: { rows: rows, total: total, limit: limit, offset: offset }, status: :ok
  end

  private

  def select_clip(clips, explicit_index)
    if explicit_index.present?
      idx = explicit_index.to_i
      return clips[idx] if idx < clips.size && clips[idx].present?
    end

    recommended = clips.find do |c|
      c.is_a?(Hash) && (c["recommended"] == true || c[:recommended] == true)
    end
    recommended || clips.first
  end

  def bad_request(exception)
    render json: { error: exception.message, detail: exception.message }, status: :bad_request
  end

  def not_found(exception)
    render json: { error: exception.message, detail: exception.message }, status: :not_found
  end

  def unprocessable_content(exception)
    render json: { error: exception.message, detail: exception.message }, status: :unprocessable_content
  end

  def rate_limited(exception)
    render json: { error: exception.message, detail: exception.message }, status: :too_many_requests
  end

  def bridge_error(exception)
    render json: { error: exception.message, detail: exception.message }, status: :bad_gateway
  end

  def gateway_timeout(exception)
    render json: { error: exception.message, detail: exception.message }, status: :gateway_timeout
  end

  def internal_server_error(exception)
    render json: { error: exception.message, detail: exception.message }, status: :internal_server_error
  end
end
