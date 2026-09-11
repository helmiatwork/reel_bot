require "faraday"
require "json"
require "uri"

module Publishers
  class TikTokPublisher
    TIKTOK_API_URL = "https://open.tiktokapis.com"
    INIT_PATH = "/v2/post/publish/video/init/"

    def publish(video_path:, title:, credentials: {})
      raise ArgumentError, "Video file not found: #{video_path}" unless File.exist?(video_path)

      access_token = credentials[:access_token] || credentials["access_token"] || credentials[:token] || credentials["token"] || ENV.fetch("TIKTOK_ACCESS_TOKEN", nil)
      raise ArgumentError, "TikTok access token is required" if access_token.blank?

      file_size = File.size(video_path)

      init_payload = {
        post_info: {
          title: title,
          privacy_level: "SELF_ONLY"
        },
        source_info: {
          source: "FILE_UPLOAD",
          video_size: file_size,
          chunk_size: file_size,
          total_chunk_count: 1
        }
      }

      init_response = connection.post(INIT_PATH) do |req|
        req.headers["Authorization"] = "Bearer #{access_token}"
        req.headers["Content-Type"] = "application/json; charset=UTF-8"
        req.body = JSON.dump(init_payload)
      end

      unless [ 200, 201 ].include?(init_response.status)
        raise Publishers::Error, "TikTok video init failed: #{init_response.status} - #{init_response.body}"
      end

      data = JSON.parse(init_response.body.to_s) rescue {}
      error_code = data.dig("error", "code")
      if error_code.present? && error_code != "ok"
        raise Publishers::Error, "TikTok video init error: #{data.dig('error', 'message') || error_code}"
      end

      publish_id = data.dig("data", "publish_id") || data.dig("data", "id")
      upload_url = data.dig("data", "upload_url")

      if upload_url.present?
        upload_path = upload_url.start_with?("http") ? URI.parse(upload_url).request_uri : upload_url

        upload_response = connection.put(upload_path) do |req|
          req.headers["Content-Type"] = "video/mp4"
          req.headers["Content-Range"] = "bytes 0-#{file_size - 1}/#{file_size}"
          req.headers["Content-Length"] = file_size.to_s
          req.body = File.binread(video_path)
        end

        unless [ 200, 201, 204 ].include?(upload_response.status)
          raise Publishers::Error, "TikTok video upload failed: #{upload_response.status} - #{upload_response.body}"
        end
      end

      {
        "id" => publish_id,
        "platform" => "tiktok",
        "status" => "draft"
      }
    end

    def connection
      @connection ||= Faraday.new(url: TIKTOK_API_URL) do |builder|
        builder.adapter Faraday.default_adapter
      end
    end
  end
end
