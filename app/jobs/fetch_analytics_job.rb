class FetchAnalyticsJob < ApplicationJob
  queue_as :default

  def perform
    fetcher = AnalyticsFetcherService.new
    youtube_channel = ChannelAccount.find_by(platform: "youtube", is_active: true)

    runs = PipelineRun.where(status: :completed).order(updated_at: :desc).limit(50)

    runs.find_each do |run|
      publish_results = run.metadata["publish_results"] || {}
      yt_result = publish_results["youtube"] || publish_results[:youtube]
      next if yt_result.blank?

      video_id = yt_result["id"] || yt_result[:id]
      next if video_id.blank? || youtube_channel.blank?

      begin
        stats = fetcher.fetch_youtube_analytics(video_id, credentials: youtube_channel.credentials)
        fetcher.record_snapshot(run, youtube_channel, stats)
      rescue StandardError => e
        Rails.logger.error("Failed to fetch analytics for PipelineRun ##{run.id} (video #{video_id}): #{e.message}")
      end
    end
  end
end
