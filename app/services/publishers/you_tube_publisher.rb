require "faraday"
require "json"
require "uri"

module Publishers
  class YouTubePublisher
    YOUTUBE_UPLOAD_URL = "https://www.googleapis.com"
    RESUMABLE_INIT_PATH = "/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"

    def publish(video_path:, title:, description: nil, tags: [], privacy: "private", credentials: {})
      raise ArgumentError, "Video file not found: #{video_path}" unless File.exist?(video_path)

      access_token = credentials[:access_token] || credentials["access_token"] || credentials[:token] || credentials["token"] || ENV.fetch("YOUTUBE_ACCESS_TOKEN", nil)
      raise ArgumentError, "YouTube access token is required" if access_token.blank?

      file_size = File.size(video_path)
      content_type = "video/mp4"

      init_response = connection.post(RESUMABLE_INIT_PATH) do |req|
        req.headers["Authorization"] = "Bearer #{access_token}"
        req.headers["Content-Type"] = "application/json; charset=UTF-8"
        req.headers["X-Upload-Content-Type"] = content_type
        req.headers["X-Upload-Content-Length"] = file_size.to_s

        req.body = JSON.dump({
          snippet: {
            title: title,
            description: description.to_s,
            tags: Array(tags)
          },
          status: {
            privacyStatus: privacy.presence || "private"
          }
        })
      end

      unless [ 200, 201 ].include?(init_response.status)
        raise Publishers::Error, "YouTube session initiation failed: #{init_response.status} - #{init_response.body}"
      end

      upload_url = init_response.headers["location"] || init_response.headers["Location"]
      if upload_url.blank?
        data = JSON.parse(init_response.body) rescue {}
        upload_url = data["upload_url"]
      end

      raise Publishers::Error, "YouTube did not return upload location header" if upload_url.blank?

      upload_path = upload_url.start_with?("http") ? URI.parse(upload_url).request_uri : upload_url

      upload_response = connection.put(upload_path) do |req|
        req.headers["Authorization"] = "Bearer #{access_token}"
        req.headers["Content-Type"] = content_type
        req.headers["Content-Length"] = file_size.to_s
        req.body = File.binread(video_path)
      end

      unless [ 200, 201 ].include?(upload_response.status)
        raise Publishers::Error, "YouTube video upload failed: #{upload_response.status} - #{upload_response.body}"
      end

      result_data = JSON.parse(upload_response.body.to_s) rescue {}
      video_id = result_data["id"]

      raise Publishers::Error, "YouTube response missing video ID" if video_id.blank?

      {
        "id" => video_id,
        "url" => "https://youtu.be/#{video_id}",
        "platform" => "youtube"
      }
    end

    def connection
      @connection ||= Faraday.new(url: YOUTUBE_UPLOAD_URL) do |builder|
        builder.adapter Faraday.default_adapter
      end
    end
  end
end
