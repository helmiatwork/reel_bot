# frozen_string_literal: true

class VoiceoversController < ApplicationController
  include ScriptPermittable

  protect_from_forgery with: :null_session
  skip_before_action :verify_authenticity_token, raise: false

  rescue_from ActionController::ParameterMissing, with: :parameter_missing

  def create
    text = extract_voiceover_text
    raise ActionController::ParameterMissing, :script if text.blank?

    voice = params[:voice].presence || "male_neutral"
    output_dir = params[:output_dir].presence || Rails.root.join("tmp", "voiceover", SecureRandom.hex(6)).to_s
    output_path = output_dir.end_with?(".mp3") ? output_dir : File.join(output_dir, "voiceover.mp3")

    audio_path = VoiceoverService.new.text_to_speech(text, output_path, voice: voice)
    render json: { status: "ok", audio_path: audio_path }
  end

  def merge
    video_path = params[:video_path].presence || raise(ActionController::ParameterMissing, :video_path)
    audio_path = params[:audio_path].presence || raise(ActionController::ParameterMissing, :audio_path)
    output_path = params[:output_path].presence || raise(ActionController::ParameterMissing, :output_path)
    bg_music = params[:bg_music] || params[:bg_music_path]

    out_video_path = VoiceoverService.new.merge_with_video(
      video_path,
      audio_path,
      output_path,
      bg_music_path: bg_music
    )

    render json: { status: "ok", video_path: out_video_path }
  end

  private

  def extract_voiceover_text
    script_param = params[:script]
    return nil if script_param.blank?

    if script_param.is_a?(String)
      script_param
    else
      permitted = permit_script
      permitted["voiceover"] || permitted[:voiceover] ||
        permitted["script"] || permitted[:script] ||
        permitted["hook"] || permitted[:hook]
    end
  end

  def parameter_missing(exception)
    render json: { error: exception.message }, status: :unprocessable_content
  end
end
