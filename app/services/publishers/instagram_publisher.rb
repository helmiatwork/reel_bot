require "faraday"
require "json"

module Publishers
  class InstagramPublisher
    GRAPH_API_URL = "https://graph.facebook.com"
    API_VERSION = "v19.0"

    def publish(video_path: nil, caption: nil, public_url:, credentials: {})
      raise ArgumentError, "public_url is required for Instagram publishing" if public_url.blank?

      if video_path.present? && !File.exist?(video_path)
        raise ArgumentError, "Video file not found: #{video_path}"
      end

      access_token = credentials[:access_token] || credentials["access_token"] || credentials[:token] || credentials["token"] || ENV.fetch("INSTAGRAM_ACCESS_TOKEN", nil)
      ig_user_id = credentials[:ig_user_id] || credentials["ig_user_id"] || credentials[:account_id] || credentials["account_id"] || ENV.fetch("INSTAGRAM_USER_ID", nil)

      if access_token.blank? || ig_user_id.blank?
        raise ArgumentError, "Instagram access token and ig_user_id are required"
      end

      # Step 1: Create media container
      container_payload = {
        media_type: "REELS",
        video_url: public_url,
        caption: caption.to_s,
        access_token: access_token
      }

      container_response = connection.post("/#{API_VERSION}/#{ig_user_id}/media") do |req|
        req.headers["Content-Type"] = "application/json"
        req.body = JSON.dump(container_payload)
      end

      unless [ 200, 201 ].include?(container_response.status)
        raise Publishers::Error, "Instagram container creation failed: #{container_response.status} - #{container_response.body}"
      end

      container_data = JSON.parse(container_response.body.to_s) rescue {}
      container_id = container_data["id"]

      if container_id.blank?
        raise Publishers::Error, "Instagram container creation missing ID: #{container_response.body}"
      end

      # Step 2: Publish media container
      publish_payload = {
        creation_id: container_id,
        access_token: access_token
      }

      publish_response = connection.post("/#{API_VERSION}/#{ig_user_id}/media_publish") do |req|
        req.headers["Content-Type"] = "application/json"
        req.body = JSON.dump(publish_payload)
      end

      unless [ 200, 201 ].include?(publish_response.status)
        raise Publishers::Error, "Instagram media publish failed: #{publish_response.status} - #{publish_response.body}"
      end

      publish_data = JSON.parse(publish_response.body.to_s) rescue {}
      media_id = publish_data["id"]

      if media_id.blank?
        raise Publishers::Error, "Instagram media publish missing ID: #{publish_response.body}"
      end

      {
        "id" => media_id,
        "platform" => "instagram",
        "status" => "published"
      }
    end

    def connection
      @connection ||= Faraday.new(url: GRAPH_API_URL) do |builder|
        builder.adapter Faraday.default_adapter
      end
    end
  end
end
