# frozen_string_literal: true

require "open3"
require "timeout"
require "securerandom"
require "fileutils"

class ClipRenderService
  class Error < StandardError; end
  class BinaryNotFoundError < Error; end
  class TimeoutError < Error; end
  class ExecutionError < Error; end

  attr_reader :input_path, :clip, :render_id, :output_dir, :timeout

  def initialize(input_path:, clip:, render_id: nil, output_dir: nil, timeout: 300)
    @input_path = input_path.to_s
    @clip = clip.is_a?(Hash) ? clip.stringify_keys : {}
    @render_id = render_id.presence || SecureRandom.uuid
    @output_dir = output_dir
    @timeout = timeout

    validate_inputs!
  end

  def call
    dest_dir = output_dir.presence || Rails.root.join("data", "renders", render_id)
    FileUtils.mkdir_p(dest_dir)
    output_path = File.join(dest_dir, "output.mp4")

    start_sec = clip["start_sec"]
    end_sec = clip["end_sec"]

    cmd = [
      "ffmpeg",
      "-y",
      "-ss", start_sec.to_s,
      "-to", end_sec.to_s,
      "-i", input_path,
      "-c", "copy",
      output_path
    ]

    execute_command(*cmd, timeout: timeout)

    unless File.exist?(output_path)
      raise ExecutionError, "Output file was not created: #{output_path}"
    end

    {
      status: "ok",
      video_path: output_path,
      render_id: render_id,
      clip: clip
    }
  end

  private

  def validate_inputs!
    if input_path.include?("..")
      raise ArgumentError, "Path traversal attempt detected in input_path"
    end

    unless File.exist?(input_path)
      raise ArgumentError, "Input file does not exist: #{input_path}"
    end

    start_sec = clip["start_sec"]
    end_sec = clip["end_sec"]

    if start_sec.nil? || end_sec.nil?
      raise ArgumentError, "start_sec and end_sec are required in clip"
    end

    if start_sec.to_f >= end_sec.to_f
      raise ArgumentError, "start_sec must be less than end_sec"
    end
  end

  def execute_command(*cmd, timeout: 300)
    stdout, stderr, status = nil
    begin
      Timeout.timeout(timeout) do
        stdout, stderr, status = Open3.capture3(*cmd)
      end
    rescue Errno::ENOENT => e
      raise BinaryNotFoundError, "ffmpeg binary not found: #{e.message}"
    rescue Timeout::Error => e
      raise TimeoutError, "ffmpeg command timed out after #{timeout}s: #{e.message}"
    end

    unless status.success?
      raise ExecutionError, "ffmpeg error: #{stderr.presence || stdout}"
    end

    [ stdout, stderr, status ]
  end
end
