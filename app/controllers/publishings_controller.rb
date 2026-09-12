# frozen_string_literal: true

class PublishingsController < ApplicationController
  include PipelineRunFindable
  include ScriptPermittable

  protect_from_forgery with: :null_session
  skip_before_action :verify_authenticity_token, raise: false

  rescue_from ActiveRecord::RecordNotFound, with: :record_not_found

  def create
    if params[:pipeline_run_id].present?
      pipeline_run = find_pipeline_run(params[:pipeline_run_id])
      platforms = Array(params[:platforms]).presence || [ "youtube" ]
      PublishVideoJob.perform_later(pipeline_run.id, platforms: platforms)
      render json: { status: "ok", results: { enqueued: true, pipeline_run_id: pipeline_run.id } }
    elsif params[:video_path].present?
      platforms = Array(params[:platforms]).presence || [ "youtube" ]
      script = permit_script
      credentials = permit_credentials
      results = Publishers::MultiPublisher.new.publish_all(
        video_path: params[:video_path],
        script: script,
        platforms: platforms,
        credentials: credentials
      )
      render json: { status: "ok", results: results }
    else
      render json: { error: "Either pipeline_run_id or video_path is required" }, status: :unprocessable_content
    end
  end

  private

  def permit_credentials
    return {} if params[:credentials].blank?

    params.require(:credentials).permit(
      :youtube_token,
      :tiktok_token,
      :ig_token,
      :ig_user_id
    ).to_h
  end

  def record_not_found
    render json: { error: "Pipeline run not found" }, status: :not_found
  end
end
