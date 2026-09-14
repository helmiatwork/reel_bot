# frozen_string_literal: true

class AnalyticsController < ApplicationController
  protect_from_forgery with: :null_session
  skip_before_action :verify_authenticity_token, raise: false

  def data
    limit = params.fetch(:limit, 100).to_i.clamp(1, 500)
    offset = [ params.fetch(:offset, 0).to_i, 0 ].max
    records = AnalyticsSnapshot.order(recorded_at: :desc).limit(limit).offset(offset).as_json
    total = AnalyticsSnapshot.count

    render json: { records: records, total: total }
  end

  def summary
    total_published = PipelineRun.where(status: :completed).count
    platform_counts = ChannelAccount.group(:platform).count
    avg_score = PipelineRun.where.not(quality_score: nil).average(:quality_score)&.round(1) || 0.0

    render json: {
      total_videos_published: total_published,
      platform_counts: platform_counts,
      avg_quality_score: avg_score.to_f
    }
  end

  def insights
    insights_data = AnalyticsFetcherService.new.generate_insights
    render json: { status: "ok", insights: insights_data }
  end
end
