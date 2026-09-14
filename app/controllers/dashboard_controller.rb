class DashboardController < ApplicationController
  def index
    @recent_runs = PipelineRun.includes(:video_project).order(created_at: :desc).limit(20)
    @total_published = PipelineRun.where(status: :completed).count
    @pending_approvals = PipelineRun.where("metadata->>'approval_status' = ?", "awaiting_approval").count
    @avg_qc_score = PipelineRun.where.not(quality_score: nil).average(:quality_score)&.round(1) || 0
    @total_views = AnalyticsSnapshot.sum(:views)
    @insights = Rails.cache.fetch("dashboard_ai_insights", expires_in: 1.hour) do
      AnalyticsFetcherService.new.generate_insights
    end
  end

  def approve
    @pipeline_run = PipelineRun.find(params[:id])
    @pipeline_run.update!(metadata: (@pipeline_run.metadata || {}).merge("approval_status" => "approved"))
    PublishVideoJob.perform_later(@pipeline_run.id)

    respond_to do |format|
      format.html do
        redirect_to root_path, notice: "Pipeline run #{@pipeline_run.run_id} approved for publishing!"
      end
      format.turbo_stream
    end
  end
end
