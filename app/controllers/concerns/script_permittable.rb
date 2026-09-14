# frozen_string_literal: true

module ScriptPermittable
  extend ActiveSupport::Concern

  private

  def permit_script
    return {} if params[:script].blank?
    return { "script" => params[:script] } if params[:script].is_a?(String)

    params.require(:script).permit(
      :title,
      :hook,
      :topic,
      :voiceover,
      :script,
      segments: %i[start_time end_time text]
    ).to_h
  end
end
