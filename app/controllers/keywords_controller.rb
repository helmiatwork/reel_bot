# frozen_string_literal: true

class KeywordsController < ApplicationController
  protect_from_forgery with: :null_session
  skip_before_action :verify_authenticity_token, raise: false

  rescue_from KeywordService::ProviderNotConfiguredError, with: :service_unavailable

  def ideas
    seeds = params[:seeds]
    if seeds.blank?
      return render json: { error: "seeds is required", detail: "seeds is required" }, status: :bad_request
    end

    seed_list = if seeds.is_a?(String)
                  seeds.split(",").map(&:strip).reject(&:blank?)
    else
                  Array(seeds).map(&:to_s).map(&:strip).reject(&:blank?)
    end

    if seed_list.empty?
      return render json: { error: "seeds is required", detail: "seeds is required" }, status: :bad_request
    end

    geo = params[:geo].presence || "ID"
    lang = params[:lang].presence || "id"
    niche = params[:niche].presence

    service = KeywordService.new
    keywords = service.generate_ideas(seeds: seed_list, geo: geo, lang: lang, niche: niche)
    keywords = keywords[:keywords] if keywords.is_a?(Hash)

    render json: { keywords: keywords }, status: :ok
  end

  def index
    service = KeywordService.new
    keywords = service.query_keywords(
      niche: params[:niche].presence,
      source: params[:source].presence,
      min_volume: params[:min_volume].presence,
      region: params[:region].presence,
      limit: params[:limit].presence
    )
    keywords = keywords[:keywords] if keywords.is_a?(Hash)

    render json: { keywords: keywords }, status: :ok
  end

  private

  def service_unavailable(error)
    render json: { error: error.message, detail: error.message }, status: :service_unavailable
  end
end
