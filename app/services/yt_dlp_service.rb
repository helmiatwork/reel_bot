# frozen_string_literal: true

require "open3"
require "timeout"
require "json"
require "uri"
require "fileutils"
require "tmpdir"

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

    cmd = [ "yt-dlp", "--dump-json", "--no-playlist", youtube_url ]
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

    dest_dir = output_dir.presence || Rails.root.join("data", "videos")
    FileUtils.mkdir_p(dest_dir)
    output_template = File.join(dest_dir, "%(id)s.%(ext)s")

    cmd = [
      "yt-dlp",
      "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
      "--merge-output-format", "mp4",
      "-o", output_template,
      "--no-playlist",
      youtube_url
    ]

    execute_command(*cmd, timeout: timeout || download_timeout)

    # Locate downloaded file in dest_dir
    files = Dir[File.join(dest_dir, "*")].reject { |f| File.directory?(f) }
    newest = files.max_by { |f| File.mtime(f) }
    newest || File.join(dest_dir, "output.mp4")
  end

  private

  def validate_url!(url)
    raise ArgumentError, "URL cannot be blank" if url.blank?

    if url.match?(PROHIBITED_CHARS_REGEX)
      raise ArgumentError, "URL contains invalid or prohibited characters"
    end

    uri = URI.parse(url)
    unless uri.is_a?(URI::HTTP) && uri.host.present?
      raise ArgumentError, "URL must use HTTP or HTTPS scheme and have a host"
    end
  rescue URI::InvalidURIError
    raise ArgumentError, "URL is invalid"
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
