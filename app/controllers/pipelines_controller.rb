# frozen_string_literal: true

class PipelinesController < ApplicationController
  protect_from_forgery with: :null_session
  skip_before_action :verify_authenticity_token, raise: false

  rescue_from ActiveRecord::RecordNotFound, with: :record_not_found
  rescue_from ActionController::ParameterMissing, with: :parameter_missing

  def create
    arcreel_project_id = params[:arcreel_project_id].presence || raise(ActionController::ParameterMissing, :arcreel_project_id)
    script_params = extract_script_params
    if script_params.blank?
      raise ActionController::ParameterMissing, :script
    end

    title = script_params["title"] || script_params[:title] || "ArcReel Project #{arcreel_project_id}"
    hook = script_params["hook"] || script_params[:hook]
    topic = script_params["topic"] || script_params[:topic]

    video_project = VideoProject.create!(
      title: title,
      hook: hook,
      topic: topic,
      script: script_params
    )

    platforms = Array(params[:platforms]).presence || [ "youtube" ]
    auto_publish = ActiveModel::Type::Boolean.new.cast(params[:auto_publish]) || false
    run_id = "run-#{SecureRandom.hex(6)}"

    metadata = {
      "arcreel_project_id" => arcreel_project_id,
      "user_id" => params[:user_id],
      "voice" => params[:voice],
      "auto_publish" => auto_publish,
      "platforms" => platforms
    }.compact

    pipeline_run = video_project.pipeline_runs.create!(
      run_id: run_id,
      status: :pending,
      metadata: metadata
    )

    CompletePipelineJob.perform_later(
      pipeline_run.id,
      auto_publish: auto_publish,
      platforms: platforms
    )

    render json: { status: "started", run_id: pipeline_run.run_id }, status: :accepted
  end

  def index
    render json: PipelineRun.order(created_at: :desc)
  end

  def show
    pipeline_run = find_pipeline_run(params[:id])
    render json: pipeline_run
  end

  private

  def find_pipeline_run(id_or_run_id)
    if id_or_run_id.to_s =~ /\A\d+\z/
      PipelineRun.find_by(id: id_or_run_id) || PipelineRun.find_by!(run_id: id_or_run_id)
    else
      PipelineRun.find_by!(run_id: id_or_run_id)
    end
  end

  def extract_script_params
    return {} if params[:script].blank?

    params[:script].respond_to?(:permit!) ? params[:script].permit!.to_h : params[:script].to_h
  end

  def record_not_found
    render json: { error: "Pipeline run not found" }, status: :not_found
  end

  def parameter_missing(exception)
    render json: { error: exception.message }, status: :unprocessable_content
  end
end
