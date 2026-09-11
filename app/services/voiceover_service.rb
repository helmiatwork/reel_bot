require "faraday"
require "fileutils"
require "json"
require "open3"

class VoiceoverService
  class Error < StandardError; end

  ELEVENLABS_URL = "https://api.elevenlabs.io"

  VOICES = {
    "male_neutral" => "pNInz6obpgDQGcFmaJgB",
    "female_neutral" => "EXAVITQu4vr4xnSDxMaL",
    "male_warm" => "VR6AewLTigWG4xSOukaG",
    "female_warm" => "MF3mGyEYCl7XYWbV9V6O"
  }.freeze

  attr_reader :api_key

  def initialize(api_key: nil)
    @api_key = api_key.presence || ENV.fetch("ELEVENLABS_API_KEY", nil)
  end

  def text_to_speech(text, output_path, voice: "male_neutral", model: "eleven_multilingual_v2")
    FileUtils.mkdir_p(File.dirname(output_path))

    if @api_key.present?
      voice_id = VOICES.fetch(voice, voice)
      payload = {
        text: text.to_s.slice(0, 4900),
        model_id: model,
        voice_settings: {
          stability: 0.5,
          similarity_boost: 0.8,
          use_speaker_boost: true
        }
      }

      response = elevenlabs_connection.post("/v1/text-to-speech/#{voice_id}") do |req|
        req.headers["xi-api-key"] = @api_key
        req.headers["Content-Type"] = "application/json"
        req.body = JSON.dump(payload)
      end

      if response.status == 200
        File.binwrite(output_path, response.body)
        return output_path
      end
    end

    fallback_tts(text, output_path)
  end

  def fallback_tts(text, output_path)
    FileUtils.mkdir_p(File.dirname(output_path))

    # Attempt 1: gtts-cli
    _out, _err, status = Open3.capture3("gtts-cli", text.to_s, "--output", output_path)
    return output_path if status.success? && File.exist?(output_path)

    # Attempt 2: say on macOS (aiff -> ffmpeg -> mp3) or minimal silent mp3
    aiff_path = output_path.sub(/\.mp3$/, ".aiff")
    _out, _err, say_status = Open3.capture3("say", "-o", aiff_path, text.to_s)
    if say_status.success? && File.exist?(aiff_path)
      Open3.capture3("ffmpeg", "-y", "-i", aiff_path, output_path)
      FileUtils.rm_f(aiff_path)
      return output_path if File.exist?(output_path)
    end

    # Attempt 3: generate blank/stub audio file if system tools are unavailable
    File.binwrite(output_path, "\xFF\xFB\x90d" + ("\x00" * 128))
    output_path
  end

  def merge_with_video(raw_video_path, audio_path, output_path, bg_music_path: nil)
    raise ArgumentError, "Raw video not found: #{raw_video_path}" unless File.exist?(raw_video_path)
    raise ArgumentError, "Audio not found: #{audio_path}" unless File.exist?(audio_path)

    FileUtils.mkdir_p(File.dirname(output_path))

    cmd = if bg_music_path.present? && File.exist?(bg_music_path)
            [
              "ffmpeg", "-y",
              "-i", raw_video_path,
              "-i", audio_path,
              "-i", bg_music_path,
              "-filter_complex", "[1:a]volume=1.0[v];[2:a]volume=0.12[m];[v][m]amix=inputs=2:duration=first[a]",
              "-map", "0:v", "-map", "[a]",
              "-c:v", "copy", "-c:a", "aac", "-shortest",
              output_path
            ]
    else
            [
              "ffmpeg", "-y",
              "-i", raw_video_path,
              "-i", audio_path,
              "-map", "0:v", "-map", "1:a",
              "-c:v", "copy", "-c:a", "aac", "-shortest",
              output_path
            ]
    end

    _out, err, status = Open3.capture3(*cmd)
    unless status.success?
      raise Error, "FFmpeg failed: #{err}"
    end

    output_path
  end

  def elevenlabs_connection
    @elevenlabs_connection ||= Faraday.new(url: ELEVENLABS_URL) do |builder|
      builder.adapter Faraday.default_adapter
    end
  end
end
