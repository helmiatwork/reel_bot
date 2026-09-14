# frozen_string_literal: true

class QualityChecksController < ApplicationController
  include ScriptPermittable

  protect_from_forgery with: :null_session
  skip_before_action :verify_authenticity_token, raise: false

  rescue_from ActionController::ParameterMissing, with: :parameter_missing

  def create
    video_path = params[:video_path].presence || raise(ActionController::ParameterMissing, :video_path)
    script_data = permit_script
    raise ActionController::ParameterMissing, :script if script_data.blank?

    qc_result = QualityCheckService.new.evaluate_quality(video_path, script_data)
    render json: qc_result
  end

  private

  def parameter_missing(exception)
    render json: { error: exception.message }, status: :unprocessable_content
  end
end
