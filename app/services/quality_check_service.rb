require "base64"
require "faraday"
require "fileutils"
require "json"
require "open3"

class QualityCheckService
  class Error < StandardError; end

  DEFAULT_API_URL = "http://localhost:8317/v1"
  DEFAULT_MODEL = "gemini-2.5-flash"

  attr_reader :api_url, :api_key, :model

  def initialize(api_url: nil, api_key: nil, model: nil)
    @api_url = api_url.presence || ENV.fetch("CLIPROXY_URL", DEFAULT_API_URL)
    @api_key = api_key.presence || ENV.fetch("CLIPROXY_KEY", "local-proxy-key")
    @model = model.presence || DEFAULT_MODEL
  end

  def extract_sample_frames(video_path, count: 5)
    raise ArgumentError, "Video not found: #{video_path}" unless File.exist?(video_path)

    out_dir = Rails.root.join("tmp", "qc_frames", SecureRandom.hex(6))
    FileUtils.mkdir_p(out_dir)

    # 1. Get video duration via ffprobe
    stdout, _stderr, status = Open3.capture3(
      "ffprobe", "-v", "quiet",
      "-show_entries", "format=duration",
      "-of", "csv=p=0",
      video_path
    )

    duration = if status.success? && stdout.strip.present?
                 stdout.strip.to_f
    else
                 60.0
    end

    frames = []
    interval = duration / (count + 1).to_f

    (1..count).each do |i|
      t = (interval * i).round(2)
      frame_path = File.join(out_dir, format("frame_%03d.jpg", i))

      _fout, _ferr, fstatus = Open3.capture3(
        "ffmpeg", "-y",
        "-ss", t.to_s,
        "-i", video_path,
        "-vframes", "1",
        "-q:v", "3",
        frame_path
      )

      if fstatus.success? && File.exist?(frame_path)
        min = (t / 60).to_i
        sec = (t % 60).to_i
        frames << {
          path: frame_path,
          timestamp: format("%02d:%02d", min, sec)
        }
      end
    end

    frames
  end

  def evaluate_quality(video_path, script)
    frames = extract_sample_frames(video_path, count: 5)
    if frames.blank?
      return {
        overall_score: 0,
        recommendation: "reject",
        issues: [ "no_frames_extracted" ]
      }
    end

    # Build vision prompt payload with base64 frames
    user_content = [
      {
        type: "text",
        text: "Video Script: #{script.to_json}\nReview the extracted video frames for visual quality, narrative alignment, and safety. Return JSON ONLY: {\"overall_score\": 0-100, \"recommendation\": \"approve\"|\"review\"|\"reject\", \"issues\": []}"
      }
    ]

    frames.each do |frame|
      b64_data = Base64.strict_encode64(File.binread(frame[:path]))
      user_content << {
        type: "image_url",
        image_url: {
          url: "data:image/jpeg;base64,#{b64_data}"
        }
      }
    end

    payload = {
      model: @model,
      messages: [
        {
          role: "system",
          content: 'You are an automated video QC reviewer. Return strictly JSON with keys: overall_score (integer 0-100), recommendation ("approve", "review", or "reject"), and issues (array of strings).'
        },
        {
          role: "user",
          content: user_content
        }
      ]
    }

    response = cliproxy_connection.post("/v1/chat/completions") do |req|
      req.headers["Authorization"] = "Bearer #{@api_key}"
      req.headers["Content-Type"] = "application/json"
      req.body = JSON.dump(payload)
    end

    unless response.status == 200
      return {
        overall_score: 50,
        recommendation: "review",
        issues: [ "quality_check_api_error" ]
      }
    end

    parse_qc_response(response.body)
  ensure
    if frames.present?
      frames.each { |f| FileUtils.rm_f(f[:path]) }
      frames.map { |f| File.dirname(f[:path]) }.uniq.each do |dir|
        FileUtils.rm_rf(dir) if dir.to_s.include?("qc_frames")
      end
    end
  end

  def cliproxy_connection
    @cliproxy_connection ||= Faraday.new(url: @api_url) do |builder|
      builder.adapter Faraday.default_adapter
    end
  end

  private

  def parse_qc_response(response_body)
    data = JSON.parse(response_body.to_s)
    raw_content = data.dig("choices", 0, "message", "content").to_s.strip

    # Clean potential markdown fences
    cleaned = raw_content.gsub(/^```json\s*/, "").gsub(/^```\s*/, "").gsub(/```$/, "").strip
    parsed = JSON.parse(cleaned)

    {
      overall_score: parsed["overall_score"].to_i,
      recommendation: parsed["recommendation"].to_s.downcase.presence || "review",
      issues: Array(parsed["issues"])
    }
  rescue => _e
    {
      overall_score: 50,
      recommendation: "review",
      issues: [ "parse_error" ]
    }
  end
end
