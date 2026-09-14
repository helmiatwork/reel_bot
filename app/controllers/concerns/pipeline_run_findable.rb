# frozen_string_literal: true

module PipelineRunFindable
  extend ActiveSupport::Concern

  private

  def find_pipeline_run(id_or_run_id)
    if id_or_run_id.to_s =~ /\A\d+\z/
      PipelineRun.find_by(id: id_or_run_id) || PipelineRun.find_by!(run_id: id_or_run_id)
    else
      PipelineRun.find_by!(run_id: id_or_run_id)
    end
  end
end
