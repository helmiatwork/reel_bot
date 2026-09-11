require "fileutils"
require "open3"

class SubtitleService
  class Error < StandardError; end

  def generate_srt(media_path, srt_path, segments: nil)
    raise ArgumentError, "Media path not found: #{media_path}" unless File.exist?(media_path)

    FileUtils.mkdir_p(File.dirname(srt_path))

    # If segments provided, build SRT directly
    if segments.present?
      srt_content = build_srt_content(segments)
      File.write(srt_path, srt_content, encoding: "UTF-8")
      return srt_path
    end

    # If no segments given, write empty SRT or detect silence
    File.write(srt_path, "", encoding: "UTF-8")
    srt_path
  end

  def burn_subtitles(video_path, srt_path, output_path)
    raise ArgumentError, "Video not found: #{video_path}" unless File.exist?(video_path)
    raise ArgumentError, "SRT file not found: #{srt_path}" unless File.exist?(srt_path)

    FileUtils.mkdir_p(File.dirname(output_path))

    # Escaping for FFmpeg filter syntax:
    # 1. Backslashes become forward slashes
    # 2. Colons become \:
    # 3. Single quotes become \'
    escaped_srt = File.expand_path(srt_path).to_s
                      .gsub("\\", "/")
                      .gsub(":", '\:')
                      .gsub("'", "\\\\'")

    style = "Bold=1,FontSize=16,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,BorderStyle=1,Alignment=2,MarginV=20"
    vf_arg = "subtitles='#{escaped_srt}':force_style='#{style}'"

    cmd = [
      "ffmpeg", "-y",
      "-i", video_path,
      "-vf", vf_arg,
      "-c:v", "libx264",
      "-preset", "fast",
      "-crf", "23",
      "-c:a", "copy",
      output_path
    ]

    _out, err, status = Open3.capture3(*cmd)
    unless status.success? && File.exist?(output_path)
      FileUtils.rm_f(output_path)
      raise Error, "FFmpeg subtitle burning failed: #{err}"
    end

    output_path
  end

  def format_timestamp(seconds)
    total_ms = (seconds.to_f * 1000).round
    ms = total_ms % 1000
    total_s = total_ms / 1000
    s = total_s % 60
    m = (total_s / 60) % 60
    h = total_s / 3600
    format("%02d:%02d:%02d,%03d", h, m, s, ms)
  end

  private

  def build_srt_content(segments)
    lines = []
    segments.each_with_index do |seg, idx|
      start_ts = format_timestamp(seg[:start_time] || seg["start_time"] || 0.0)
      end_ts = format_timestamp(seg[:end_time] || seg["end_time"] || 0.0)
      text = (seg[:text] || seg["text"] || "").to_s.strip
      next if text.blank?

      lines << (idx + 1).to_s
      lines << "#{start_ts} --> #{end_ts}"
      lines << text
      lines << ""
    end
    lines.join("\n")
  end
end
