# frozen_string_literal: true

class PublishingsController < ApplicationController
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
      script = extract_hash(:script)
      credentials = extract_hash(:credentials)
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

  def find_pipeline_run(id_or_run_id)
    if id_or_run_id.to_s =~ /\A\d+\z/
      PipelineRun.find_by(id: id_or_run_id) || PipelineRun.find_by!(run_id: id_or_run_id)
    else
      PipelineRun.find_by!(run_id: id_or_run_id)
    end
  end

  def extract_hash(param_key)
    param = params[param_key]
    return {} if param.blank?

    param.respond_to?(:permit!) ? param.permit!.to_h : param.to_h
  end

  def record_not_found
    render json: { error: "Pipeline run not found" }, status: :not_found
  end
end
