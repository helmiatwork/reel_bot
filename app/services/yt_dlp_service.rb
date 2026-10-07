# frozen_string_literal: true

require "open3"
require "timeout"
require "json"
require "uri"
require "fileutils"
require "tmpdir"
require "securerandom"

class YtDlpService
  class Error < StandardError; end
  class BinaryNotFoundError < Error; end
  class TimeoutError < Error; end
  class ExecutionError < Error; end

  PROHIBITED_CHARS_REGEX = /[;&|`$\n\r<>]/

  attr_reader :metadata_timeout, :transcript_timeout, :download_timeout

  def initialize(metadata_timeout: 60, transcript_timeout: 60, download_timeout: 300)
    @metadata_timeout = metadata_timeout
    @transcript_timeout = transcript_timeout
    @download_timeout = download_timeout
  end

  def fetch_metadata(youtube_url)
    validate_url!(youtube_url)

    cmd = [ "yt-dlp", "--dump-json", "--no-playlist", "--socket-timeout", "30", youtube_url ]
    stdout, = execute_command(*cmd, timeout: metadata_timeout)
    JSON.parse(stdout)
  end

  def fetch_transcript(youtube_url)
    validate_url!(youtube_url)

    Dir.mktmpdir("yt_vtt_") do |tmp_dir|
      output_prefix = File.join(tmp_dir, "subs")
      cmd = [
        "yt-dlp",
        "--write-auto-sub",
        "--write-sub",
        "--sub-langs", "en.*,en,id.*,id,all",
        "--sub-format", "vtt",
        "--skip-download",
        "-o", output_prefix,
        "--no-playlist",
        "--socket-timeout", "30",
        youtube_url
      ]

      begin
        execute_command(*cmd, timeout: transcript_timeout)
      rescue ExecutionError
        return { segments: [] }
      end

      vtt_files = Dir[File.join(tmp_dir, "*.vtt")]
      return { segments: [] } if vtt_files.empty?

      segments = parse_vtt(vtt_files.first)
      { segments: segments }
    end
  end

  def download(youtube_url, output_dir: nil, timeout: nil)
    validate_url!(youtube_url)

    dest_dir = if output_dir.present?
      output_dir.to_s
    else
      Rails.root.join("data", "videos", SecureRandom.uuid).to_s
    end
    FileUtils.mkdir_p(dest_dir)
    output_template = File.join(dest_dir, "%(id)s.%(ext)s")

    cmd = [
      "yt-dlp",
      "--print", "after_move:filepath",
      "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
      "--merge-output-format", "mp4",
      "-o", output_template,
      "--no-playlist",
      "--socket-timeout", "30",
      youtube_url
    ]

    stdout, = execute_command(*cmd, timeout: timeout || download_timeout)

    resolve_downloaded_file(stdout, dest_dir)
  end

  def latest_channel_video(channel_id_or_url)
    channel_str = channel_id_or_url.to_s.strip
    url = if channel_str.start_with?("http://", "https://")
      channel_str
    elsif channel_str.start_with?("UC")
      "https://www.youtube.com/channel/#{channel_str}/videos"
    elsif channel_str.start_with?("@")
      "https://www.youtube.com/#{channel_str}/videos"
    else
      "https://www.youtube.com/@#{channel_str}/videos"
    end

    validate_url!(url)

    cmd = [
      "yt-dlp",
      "--dump-json",
      "--flat-playlist",
      "--playlist-end", "1",
      "--no-warnings",
      "--socket-timeout", "30",
      url
    ]

    stdout, = execute_command(*cmd, timeout: metadata_timeout)
    return nil if stdout.blank?

    line = stdout.lines.first&.strip
    return nil if line.blank?

    data = JSON.parse(line)
    video_id = data["id"] || data["url"]
    return nil if video_id.blank?

    {
      video_id: video_id,
      title: data["title"]
    }
  rescue StandardError => e
    Rails.logger.warn("[YtDlpService] latest_channel_video failed: #{e.message}")
    nil
  end

  private

  def resolve_downloaded_file(stdout, dest_dir)
    printed_lines = stdout.to_s.lines.map(&:strip).reject(&:empty?)

    candidate_paths = printed_lines.flat_map do |line|
      [ line, File.expand_path(line, dest_dir) ]
    end

    matched = candidate_paths.reverse.find { |p| File.file?(p) }
    return matched if matched.present?

    files = Dir[File.join(dest_dir, "*")].reject { |f| File.directory?(f) }
    fallback = files.max_by { |f| File.mtime(f) }

    if fallback.present? && File.file?(fallback)
      return fallback
    end

    raise ExecutionError, "yt-dlp completed but output file not found in #{dest_dir}"
  end

  def validate_url!(url)
    UrlSafetyValidator.validate_youtube_url!(url)
  end

  def execute_command(*cmd, timeout: 60)
    stdout, stderr, status = nil
    begin
      Timeout.timeout(timeout) do
        stdout, stderr, status = Open3.capture3(*cmd)
      end
    rescue Errno::ENOENT => e
      raise BinaryNotFoundError, "yt-dlp binary not found: #{e.message}"
    rescue Timeout::Error => e
      raise TimeoutError, "yt-dlp command timed out after #{timeout}s: #{e.message}"
    end

    unless status.success?
      raise ExecutionError, "yt-dlp execution failed (exit #{status.exitstatus}): #{stderr.presence || stdout}"
    end

    [ stdout, stderr, status ]
  end

  def parse_vtt(file_path)
    content = File.read(file_path, encoding: "utf-8")
    lines = content.lines.map(&:strip)
    segments = []
    i = 0

    while i < lines.length
      line = lines[i]
      if line.include?("-->")
        parts = line.split("-->")
        start_sec = parse_timestamp(parts[0].strip)
        end_sec = parse_timestamp(parts[1].strip.split.first)

        text_lines = []
        i += 1
        while i < lines.length
          next_line = lines[i]
          break if next_line.blank? || next_line.include?("-->")

          cleaned = next_line.gsub(/<[^>]+>/, "").strip
          text_lines << cleaned unless cleaned.blank?
          i += 1
        end

        text = text_lines.join(" ").strip
        if text.present? && start_sec && end_sec
          segments << { start: start_sec.round(2), end: end_sec.round(2), text: text }
        end
      else
        i += 1
      end
    end

    segments
  rescue StandardError
    []
  end

  def parse_timestamp(ts)
    parts = ts.split(":")
    if parts.length == 3
      parts[0].to_f * 3600 + parts[1].to_f * 60 + parts[2].to_f
    elsif parts.length == 2
      parts[0].to_f * 60 + parts[1].to_f
    else
      ts.to_f
    end
  rescue StandardError
    nil
  end
end
