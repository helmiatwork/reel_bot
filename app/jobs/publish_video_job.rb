require "cgi"

class PublishVideoJob < ApplicationJob
  queue_as :default

  def perform(pipeline_run_id, platforms: [ "youtube", "tiktok" ], credentials: {})
    pipeline_run = find_pipeline_run(pipeline_run_id)

    video_path = pipeline_run.final_video_path.presence || pipeline_run.raw_video_path
    script = pipeline_run.video_project&.script || {}
    public_url = pipeline_run.metadata["public_url"]

    merged_credentials = resolve_credentials(platforms, credentials)

    publisher = Publishers::MultiPublisher.new
    results = publisher.publish_all(
      video_path: video_path,
      script: script,
      platforms: platforms,
      credentials: merged_credentials,
      public_url: public_url
    )

    updated_metadata = (pipeline_run.metadata || {}).merge("publish_results" => results)
    pipeline_run.update!(status: :completed, metadata: updated_metadata)

    notify_completion(pipeline_run, results)
    results
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

  def resolve_credentials(platforms, passed_credentials)
    creds = (passed_credentials || {}).with_indifferent_access

    Array(platforms).each do |platform|
      plat_key = platform.to_s.downcase
      next if creds[plat_key].present?

      channel_account = ChannelAccount.find_by(platform: plat_key, is_active: true)
      if channel_account&.credentials.present?
        creds[plat_key] = channel_account.credentials
      end
    end

    creds.to_h
  end

  def notify_completion(pipeline_run, results)
    platform_names = CGI.escapeHTML(results.keys.map(&:titleize).join(", "))
    project_title = CGI.escapeHTML((pipeline_run.video_project&.title || "Untitled").to_s)
    run_id = CGI.escapeHTML(pipeline_run.run_id.to_s)

    message = <<~MSG.strip
      🎉 <b>Pipeline Run Completed!</b>

      <b>Run ID:</b> <code>#{run_id}</code>
      <b>Project:</b> #{project_title}
      <b>Published To:</b> #{platform_names}
    MSG

    TelegramBotService.new.notify(message)
  rescue StandardError => e
    Rails.logger.error("Failed to send Telegram completion notification: #{e.message}")
  end
end
