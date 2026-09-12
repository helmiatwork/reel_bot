# frozen_string_literal: true

class YouTubeController < ApplicationController
  protect_from_forgery with: :null_session
  skip_before_action :verify_authenticity_token, raise: false

  rescue_from YouTubeService::NotConfigured, with: :not_configured
  rescue_from YouTubeService::QuotaError, with: :quota_exceeded
  rescue_from YouTubeService::NotFoundError, with: :not_found
  rescue_from Faraday::TimeoutError, with: :gateway_timeout

  def search
    query = params[:q].presence || params[:query].presence
    if query.blank?
      return render json: { error: "Query parameter q or query is required" }, status: :bad_request
    end

    max_results = params[:max_results].present? ? params[:max_results].to_i : 50
    results = youtube_service.search(query, max_results: max_results)
    render json: results, status: :ok
  end

  def video
    metadata = youtube_service.video_metadata(params[:id])
    render json: metadata, status: :ok
  end

  def channel
    info = youtube_service.channel_info(params[:id])
    render json: info, status: :ok
  end

  def quota
    usage = youtube_service.quota_usage
    render json: usage, status: :ok
  end

  private

  def youtube_service
    @youtube_service ||= YouTubeService.new
  end

  def not_configured(exception)
    render json: { error: exception.message }, status: :unauthorized
  end

  def quota_exceeded(exception)
    render json: { error: exception.message }, status: :too_many_requests
  end

  def not_found(exception)
    render json: { error: exception.message }, status: :not_found
  end

  def gateway_timeout(exception)
    render json: { error: exception.message }, status: :gateway_timeout
  end
end
