# frozen_string_literal: true

class SnoopWatcherJob < ApplicationJob
  queue_as :default

  def perform
    SnoopTarget.find_each do |target|
      process_target(target)
    rescue StandardError => e
      Rails.logger.error("[SnoopWatcherJob] Failed processing target #{target.channel_id}: #{e.message}")
    end
  end

  private

  def process_target(target)
    latest = fetch_latest_video(target)
    return if latest.blank?

    video_id = latest[:video_id] || latest["video_id"]
    return if video_id.blank?
    return if video_id == target.last_seen_video_id

    youtube_url = "https://www.youtube.com/watch?v=#{video_id}"
    video_title = latest[:title] || latest["title"]

    clips, clipping_succeeded = discover_clips(youtube_url)

    if clipping_succeeded && clips.present? && !clips.empty?
      SnoopResult.create!(
        channel_id: target.channel_id,
        video_id: video_id,
        video_title: video_title,
        clips: clips
      )
      target.update!(last_seen_video_id: video_id)
    else
      SnoopResult.create!(
        channel_id: target.channel_id,
        video_id: video_id,
        video_title: video_title,
        clips: []
      )
    end
  end

  def fetch_latest_video(target)
    identifier = target.channel_id

    begin
      video = youtube_service.latest_channel_video(identifier)
      return video if video.present?
    rescue StandardError => e
      Rails.logger.warn("[SnoopWatcherJob] YouTubeService failed for #{identifier}: #{e.message}; falling back to YtDlpService")
    end

    begin
      yt_dlp_service.latest_channel_video(identifier)
    rescue StandardError => e
      Rails.logger.error("[SnoopWatcherJob] YtDlpService failed for #{identifier}: #{e.message}")
      nil
    end
  end

  def discover_clips(youtube_url)
    finder = ClipFinderService.new(youtube_url: youtube_url)
    result = finder.call
    clips = result[:clips] || result["clips"] || []
    [ clips, clips.present? && !clips.empty? ]
  rescue StandardError => e
    Rails.logger.error("[SnoopWatcherJob] Clip finder failed for #{youtube_url}: #{e.message}")
    [ [], false ]
  end

  def youtube_service
    @youtube_service ||= YouTubeService.new
  end

  def yt_dlp_service
    @yt_dlp_service ||= YtDlpService.new
  end
end
