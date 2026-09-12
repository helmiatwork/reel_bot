# frozen_string_literal: true

class PipelinesController < ApplicationController
  include PipelineRunFindable
  include ScriptPermittable

  protect_from_forgery with: :null_session
  skip_before_action :verify_authenticity_token, raise: false

  rescue_from ActiveRecord::RecordNotFound, with: :record_not_found
  rescue_from ActionController::ParameterMissing, with: :parameter_missing

  def create
    arcreel_project_id = params[:arcreel_project_id].presence || raise(ActionController::ParameterMissing, :arcreel_project_id)
    script_params = permit_script
    raise ActionController::ParameterMissing, :script if script_params.blank?

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

    metadata = {
      "arcreel_project_id" => arcreel_project_id,
      "user_id" => params[:user_id],
      "voice" => params[:voice],
      "auto_publish" => auto_publish,
      "platforms" => platforms
    }.compact

    pipeline_run = video_project.pipeline_runs.create!(
      run_id: params[:run_id],
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
    limit = params.fetch(:limit, 50).to_i.clamp(1, 100)
    offset = [ params.fetch(:offset, 0).to_i, 0 ].max
    render json: PipelineRun.order(created_at: :desc).limit(limit).offset(offset)
  end

  def show
    pipeline_run = find_pipeline_run(params[:id])
    render json: pipeline_run
  end

  private

  def record_not_found
    render json: { error: "Pipeline run not found" }, status: :not_found
  end

  def parameter_missing(exception)
    render json: { error: exception.message }, status: :unprocessable_content
  end
end
