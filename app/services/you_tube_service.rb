# frozen_string_literal: true

require "faraday"
require "json"

class YouTubeService
  class Error < StandardError; end
  class NotConfigured < Error; end
  class QuotaError < Error; end
  class NotFoundError < Error; end

  BASE_URL = "https://www.googleapis.com/youtube/v3"
  DAILY_LIMIT = 10_000

  QUOTA_COSTS = {
    "search" => 100,
    "videos" => 1,
    "channels" => 1
  }.freeze

  attr_reader :api_key

  def initialize(api_key: ENV["YOUTUBE_API_KEY"])
    @api_key = api_key
  end

  def search(query, max_results: 10, **filters)
    ensure_configured!
    raise ArgumentError, "query cannot be blank" if query.blank?

    clamped_max = max_results.to_i.clamp(1, 50)
    params = {
      q: query,
      part: "snippet",
      type: "video",
      maxResults: clamped_max,
      key: api_key
    }.merge(filters)

    response = get("search", params)
    data = parse_response(response)
    record_quota(QUOTA_COSTS["search"])

    (data["items"] || []).map do |item|
      snippet = item["snippet"] || {}
      {
        video_id: item.dig("id", "videoId") || item["id"],
        title: snippet["title"],
        channel_title: snippet["channelTitle"],
        channel_id: snippet["channelId"],
        published_at: snippet["publishedAt"],
        thumbnail: snippet.dig("thumbnails", "default", "url")
      }
    end
  end

  def video_metadata(video_id_or_url)
    ensure_configured!
    video_id = extract_video_id(video_id_or_url)
    raise ArgumentError, "video_id cannot be blank" if video_id.blank?

    params = {
      id: video_id,
      part: "snippet,contentDetails,statistics",
      key: api_key
    }

    response = get("videos", params)
    data = parse_response(response)
    record_quota(QUOTA_COSTS["videos"])

    items = data["items"]
    raise NotFoundError, "Video not found: #{video_id}" if items.blank?

    item = items.first
    snippet = item["snippet"] || {}
    content_details = item["contentDetails"] || {}
    statistics = item["statistics"] || {}
    duration_iso = content_details["duration"]

    {
      video_id: item["id"],
      title: snippet["title"],
      description: snippet["description"],
      duration_iso: duration_iso,
      duration_seconds: parse_iso8601_duration(duration_iso),
      duration_s: parse_iso8601_duration(duration_iso),
      view_count: statistics["viewCount"].to_i,
      like_count: statistics["likeCount"].to_i,
      comment_count: statistics["commentCount"].to_i,
      channel_title: snippet["channelTitle"],
      channel_id: snippet["channelId"],
      published_at: snippet["publishedAt"],
      thumbnails: snippet["thumbnails"]
    }
  end

  def channel_info(channel_id_or_handle)
    ensure_configured!
    raise ArgumentError, "channel_id_or_handle cannot be blank" if channel_id_or_handle.blank?

    params = {
      part: "snippet,statistics,contentDetails",
      key: api_key
    }

    if channel_id_or_handle.to_s.start_with?("@")
      params[:forHandle] = channel_id_or_handle
    else
      params[:id] = channel_id_or_handle
    end

    response = get("channels", params)
    data = parse_response(response)
    record_quota(QUOTA_COSTS["channels"])

    items = data["items"]
    raise NotFoundError, "Channel not found: #{channel_id_or_handle}" if items.blank?

    item = items.first
    snippet = item["snippet"] || {}
    statistics = item["statistics"] || {}
    content_details = item["contentDetails"] || {}

    {
      channel_id: item["id"],
      title: snippet["title"],
      description: snippet["description"],
      custom_url: snippet["customUrl"],
      published_at: snippet["publishedAt"],
      thumbnails: snippet["thumbnails"],
      subscriber_count: statistics["subscriberCount"].to_i,
      video_count: statistics["videoCount"].to_i,
      view_count: statistics["viewCount"].to_i,
      uploads_playlist_id: content_details.dig("relatedPlaylists", "uploads")
    }
  end

  def parse_iso8601_duration(duration_str)
    return 0 if duration_str.blank? || !duration_str.is_a?(String) || !duration_str.start_with?("P")

    pattern = /\AP(?:(?<days>\d+)D)?(?:T(?:(?<hours>\d+)H)?(?:(?<minutes>\d+)M)?(?:(?<seconds>\d+)S)?)?\z/
    match = duration_str.match(pattern)
    return 0 unless match
    return 0 if match[:days].nil? && match[:hours].nil? && match[:minutes].nil? && match[:seconds].nil?

    days = match[:days].to_i
    hours = match[:hours].to_i
    minutes = match[:minutes].to_i
    seconds = match[:seconds].to_i
    (days * 86_400) + (hours * 3600) + (minutes * 60) + seconds
  rescue StandardError
    0
  end

  def quota_usage
    today_key = "youtube_quota:#{Date.current}"
    used = (Rails.cache.read(today_key) || self.class.memory_quota[today_key] || 0).to_i
    reset_at = (Time.current.utc.end_of_day + 1.second).beginning_of_day.iso8601

    {
      used: used,
      limit: DAILY_LIMIT,
      reset_at: reset_at
    }
  end

  def self.memory_quota
    @memory_quota ||= {}
  end

  private

  def ensure_configured!
    raise NotConfigured, "YOUTUBE_API_KEY not configured" if api_key.blank?
  end

  def client
    @client ||= Faraday.new(url: BASE_URL) do |f|
      f.options.open_timeout = 2
      f.options.timeout = 5
      f.adapter Faraday.default_adapter
    end
  end

  def get(path, params)
    response = client.get(path, params)
    check_errors!(response)
    response
  rescue Faraday::ConnectionFailed => e
    if e.cause.is_a?(Timeout::Error) || (defined?(Net::OpenTimeout) && e.cause.is_a?(Net::OpenTimeout))
      raise Faraday::TimeoutError, e.message
    end
    raise
  end

  def check_errors!(response)
    if response.status == 403
      body_str = response.body.to_s
      if body_str.include?("quotaExceeded") || body_str.include?("dailyLimitExceeded")
        raise QuotaError, "YouTube API quota exceeded"
      end
      raise Error, "YouTube API forbidden: #{response.body}"
    elsif response.status == 404
      raise NotFoundError, "Resource not found on YouTube"
    elsif response.status >= 400
      raise Error, "YouTube API error HTTP #{response.status}: #{response.body}"
    end
  end

  def parse_response(response)
    JSON.parse(response.body)
  rescue JSON::ParserError => e
    raise Error, "Failed to parse YouTube API response: #{e.message}"
  end

  def extract_video_id(video_id_or_url)
    str = video_id_or_url.to_s.strip
    if (m = str.match(%r{youtu\.be/([^?]+)}))
      m[1]
    elsif (m = str.match(%r{youtube\.com/watch.*[?&]v=([^&]+)}))
      m[1]
    elsif (m = str.match(%r{youtube\.com/shorts/([^?]+)}))
      m[1]
    else
      str
    end
  end

  def record_quota(units)
    today_key = "youtube_quota:#{Date.current}"
    current = (Rails.cache.read(today_key) || self.class.memory_quota[today_key] || 0).to_i + units
    Rails.cache.write(today_key, current, expires_in: 2.days)
    self.class.memory_quota[today_key] = current
  rescue StandardError
    nil
  end
end
