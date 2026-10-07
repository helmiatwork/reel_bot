require "faraday"
require "fileutils"
require "json"
require "stringio"

class ArcReelClient
  class Error < StandardError; end

  attr_reader :url, :token

  def initialize(url: nil, token: nil)
    @url = url.presence || ENV.fetch("ARCREEL_URL", "http://localhost:1241")
    @token = token.presence || ENV.fetch("ARCREEL_TOKEN", nil)
  end

  def download_video(project_id, destination_path)
    raise ArgumentError, "project_id cannot be blank" if project_id.blank?
    raise ArgumentError, "destination_path cannot be blank" if destination_path.blank?

    FileUtils.mkdir_p(File.dirname(destination_path))

    response = connection.get("/api/projects/#{project_id}/export", nil, default_headers)

    unless response.status == 200
      raise Error, "ArcReel export request failed: #{response.status} - #{response.body}"
    end

    content_type = response.headers["content-type"].to_s
    if content_type.start_with?("video/")
      write_stream_to_disk(response.body, destination_path)
      return destination_path
    end

    data = parse_json_payload(response.body)
    video_url = data["video_url"] || data["download_url"]

    unless video_url.present?
      raise Error, "ArcReel export response missing video_url: #{response.body}"
    end

    stream_from_url(video_url, destination_path)
    destination_path
  end

  def default_headers
    headers = {}
    headers["Authorization"] = "Bearer #{@token}" if @token.present?
    headers
  end

  def connection
    @connection ||= Faraday.new(url: @url) do |builder|
      builder.headers.merge!(default_headers)
      builder.adapter Faraday.default_adapter
    end
  end

  private

  def stream_from_url(video_url, destination_path)
    File.open(destination_path, "wb") do |file|
      cdn_conn = Faraday.new(url: nil)
      cdn_response = cdn_conn.get(video_url) do |req|
        req.options.on_data = proc do |chunk, _bytes|
          file.write(chunk)
        end
      end

      unless cdn_response.status == 200
        FileUtils.rm_f(destination_path)
        raise Error, "Failed to download video from URL #{video_url}: #{cdn_response.status}"
      end

      if File.empty?(destination_path) && cdn_response.body.present?
        write_stream_to_disk(cdn_response.body, destination_path)
      end
    end
  end

  def write_stream_to_disk(source, destination_path)
    File.open(destination_path, "wb") do |target|
      if source.respond_to?(:read)
        IO.copy_stream(source, target)
      else
        IO.copy_stream(StringIO.new(source.to_s), target)
      end
    end
  end

  def parse_json_payload(body)
    JSON.parse(body.to_s)
  rescue JSON::ParserError => e
    raise Error, "Invalid JSON from ArcReel: #{e.message}"
  end
end
