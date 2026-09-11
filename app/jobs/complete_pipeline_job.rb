require "fileutils"

class CompletePipelineJob < ApplicationJob
  queue_as :default

  def perform(pipeline_run_id, auto_publish: false, platforms: [ "youtube", "tiktok" ])
    pipeline_run = find_pipeline_run(pipeline_run_id)
    pipeline_run.running!

    project = pipeline_run.video_project
    raise ArgumentError, "Missing video project" if project.nil?

    script = project.script || {}
    work_dir = Rails.root.join("tmp", "pipeline", pipeline_run.run_id)
    FileUtils.mkdir_p(work_dir)

    completed_steps = []

    # Step 1: ArcReel download
    raw_path = pipeline_run.raw_video_path.presence || work_dir.join("raw.mp4").to_s
    ArcReelClient.new.download_video(project.id, raw_path)
    pipeline_run.update!(raw_video_path: raw_path)
    completed_steps << "download"

    # Step 2: Voiceover generation & FFmpeg audio merge
    voiceover_text = script["voiceover"] || script[:voiceover] || script["script"] || script[:script] || project.hook || project.title
    audio_path = work_dir.join("voiceover.mp3").to_s
    voiceover_svc = VoiceoverService.new
    voiceover_svc.text_to_speech(voiceover_text, audio_path)

    merged_video_path = work_dir.join("merged.mp4").to_s
    voiceover_svc.merge_with_video(raw_path, audio_path, merged_video_path)
    completed_steps << "voiceover"

    # Step 3: Subtitles generation & burn-in
    srt_path = pipeline_run.subtitles_path.presence || work_dir.join("subtitles.srt").to_s
    segments = script["segments"] || script[:segments]
    subtitle_svc = SubtitleService.new
    subtitle_svc.generate_srt(merged_video_path, srt_path, segments: segments)

    final_path = pipeline_run.final_video_path.presence || work_dir.join("final.mp4").to_s
    subtitle_svc.burn_subtitles(merged_video_path, srt_path, final_path)
    pipeline_run.update!(subtitles_path: srt_path, final_video_path: final_path)
    completed_steps << "subtitles"

    # Step 4: Quality check evaluation
    qc_svc = QualityCheckService.new
    qc_result = qc_svc.evaluate_quality(final_path, script)
    overall_score = (qc_result[:overall_score] || qc_result["overall_score"] || 0).to_i
    recommendation = (qc_result[:recommendation] || qc_result["recommendation"] || "review").to_s.downcase
    pipeline_run.update!(quality_score: overall_score)
    completed_steps << "quality_check"

    # Step 5: Checkpoint in pipeline_run.metadata["completed_steps"]
    updated_metadata = (pipeline_run.metadata || {}).merge(
      "completed_steps" => completed_steps,
      "qc_result" => qc_result
    )
    pipeline_run.update!(metadata: updated_metadata)

    # Step 6: Approval gate
    if !auto_publish || recommendation != "approve"
      pipeline_run.update!(metadata: pipeline_run.metadata.merge("approval_status" => "awaiting_approval"))
      TelegramBotService.new.request_approval(pipeline_run)
      return
    end

    # Step 7: Auto-approved
    pipeline_run.update!(metadata: pipeline_run.metadata.merge("approval_status" => "approved"))
    PublishVideoJob.perform_later(pipeline_run.id, platforms: platforms)
  rescue StandardError => e
    pipeline_run&.update!(status: :failed, error_message: e.message)
    raise e
  end

  private

  def find_pipeline_run(id_or_run_id)
    if id_or_run_id.is_a?(Numeric) || id_or_run_id.to_s =~ /\A\d+\z/
      PipelineRun.find(id_or_run_id)
    else
      PipelineRun.find_by!(run_id: id_or_run_id)
    end
  end
end
